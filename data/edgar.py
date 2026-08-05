"""
EDGAR data layer.

Three jobs:
  1. Turn a ticker like DDOG into a CIK number, which is what SEC uses internally.
  2. Fetch the companyfacts JSON for that CIK, caching it to disk.
  3. Trim that JSON down from megabytes to something small enough to send to a model.

Step 3 is the one that matters most. The raw file for a large company can be
several megabytes. You need maybe eight concepts. Sending the whole thing would
cost a fortune in tokens and would make the model less accurate, not more.
"""

import json
import os
import pathlib
import time
import urllib.request
import urllib.error

# SEC requires a User-Agent that identifies you. Set this or they will block you.
USER_AGENT = os.environ.get("SEC_USER_AGENT", "Ledgerproof research vedant@example.com")

CACHE_DIR = pathlib.Path(".cache/edgar")
CACHE_TTL_SECONDS = 60 * 60 * 24  # one day

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


# ---------------------------------------------------------------------------
# Concept aliasing
#
# This dictionary exists because XBRL concept names are NOT standardized across
# companies. Datadog reports revenue under "Revenues". Snowflake reports it
# under "RevenueFromContractWithCustomerExcludingAssessedTax". Same idea,
# different tag. If you hardcode one tag, your agent silently fails on half the
# companies you try.
#
# You discover this by hand-verifying evaluation questions, not by design.
# ---------------------------------------------------------------------------
CONCEPT_ALIASES = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "cost_of_revenue": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
    ],
    "gross_profit": ["GrossProfit"],
    "research_and_development": ["ResearchAndDevelopmentExpense"],
    "sales_and_marketing": ["SellingAndMarketingExpense"],
    "general_and_administrative": ["GeneralAndAdministrativeExpense"],
    "operating_expenses": ["OperatingExpenses"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
}


def _http_get_json(url: str) -> dict:
    """Plain GET with the required User-Agent header."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _cached_get_json(url: str, cache_name: str) -> dict:
    """
    Same as above, but writes the result to disk first.

    This matters more than it looks. During development you will run the agent
    against the same company fifty times in an afternoon. Without this you make
    fifty identical network calls and wait for each one.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / cache_name

    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < CACHE_TTL_SECONDS:
            return json.loads(cache_path.read_text())

    payload = _http_get_json(url)
    cache_path.write_text(json.dumps(payload))
    return payload


def resolve_cik(ticker: str) -> tuple[str, str]:
    """
    Ticker to CIK. Returns (padded_cik, company_name).

    CIK must be zero-padded to ten digits for the companyfacts URL.
    """
    ticker = ticker.strip().upper()
    mapping = _cached_get_json(TICKER_MAP_URL, "company_tickers.json")

    for entry in mapping.values():
        if entry["ticker"].upper() == ticker:
            return str(entry["cik_str"]).zfill(10), entry["title"]

    raise ValueError(f"Could not find a CIK for ticker {ticker}")


def _classify_period(start: str, end: str) -> str | None:
    """
    XBRL stores quarterly and year-to-date values under the SAME concept name.
    They are distinguished only by the start and end dates on each fact.

    If you skip this step, a Q4 value and a full-year value look identical and
    your margins come out wildly wrong for one quarter per year. This is the
    single most common beginner mistake with XBRL.

    We keep only clean quarterly and annual durations and discard the rest.
    """
    from datetime import date

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    days = (end_date - start_date).days

    if 80 <= days <= 100:
        return "quarterly"
    if 350 <= days <= 380:
        return "annual"
    return None  # six-month and nine-month year-to-date figures, dropped


def _extract_concept(all_facts: dict, alias_list: list[str], max_periods: int) -> dict | None:
    """
    Find the first alias this company actually reports, then pull its history.
    """
    us_gaap = all_facts.get("facts", {}).get("us-gaap", {})

    for tag in alias_list:
        if tag not in us_gaap:
            continue

        usd_facts = us_gaap[tag].get("units", {}).get("USD")
        if not usd_facts:
            continue

        # Deduplicate by (start, end), keeping whichever was filed most recently.
        # This is a crude first pass at the restatement problem: the same fiscal
        # quarter can appear with different values in different filings.
        by_period: dict[tuple[str, str], dict] = {}
        for fact in usd_facts:
            if "start" not in fact or "end" not in fact:
                continue
            if fact.get("form") not in ("10-Q", "10-K"):
                continue

            kind = _classify_period(fact["start"], fact["end"])
            if kind is None:
                continue

            key = (fact["start"], fact["end"])
            existing = by_period.get(key)
            if existing is None or fact.get("filed", "") > existing.get("filed", ""):
                fact = dict(fact)
                fact["period_type"] = kind
                by_period[key] = fact

        if not by_period:
            continue

        periods = sorted(by_period.values(), key=lambda f: f["end"], reverse=True)
        periods = periods[:max_periods]

        return {
            "xbrl_tag": tag,
            "periods": [
                {
                    "value": p["val"],
                    "start": p["start"],
                    "end": p["end"],
                    "period_type": p["period_type"],
                    "fiscal_year": p.get("fy"),
                    "fiscal_period": p.get("fp"),
                    "form": p.get("form"),
                    "accession": p.get("accn"),
                    "filed": p.get("filed"),
                }
                for p in periods
            ],
        }

    return None


def get_company_facts(ticker: str, max_periods: int = 12) -> dict:
    """
    The public entry point. This is what the tool layer calls.

    Returns a compact dict, roughly 3k to 6k tokens instead of several megabytes.
    """
    cik, company_name = resolve_cik(ticker)
    raw = _cached_get_json(
        COMPANYFACTS_URL.format(cik=cik),
        f"companyfacts_{cik}.json",
    )

    concepts = {}
    for canonical_name, aliases in CONCEPT_ALIASES.items():
        extracted = _extract_concept(raw, aliases, max_periods)
        if extracted is not None:
            concepts[canonical_name] = extracted

    return {
        "ticker": ticker.upper(),
        "cik": cik,
        "company_name": company_name,
        "source": "SEC EDGAR XBRL companyfacts",
        "note": (
            "period_type distinguishes single quarters from full years. "
            "Only 10-Q and 10-K facts are included. Values are USD."
        ),
        "concepts": concepts,
    }
