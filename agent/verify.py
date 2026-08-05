"""Verification pass (v1): confirm cited figures exist in fetched data."""

from __future__ import annotations


def _values_match(expected: float, actual: float) -> bool:
    if expected is None or actual is None:
        return False
    expected = float(expected)
    actual = float(actual)
    if expected == actual:
        return True
    tolerance = max(1.0, abs(expected) * 1e-6)
    return abs(expected - actual) <= tolerance


def _concept_matches(snapshot: dict, concept: str) -> str | None:
    """Return the xbrl_tag if concept matches a fetched concept block."""
    concept = (concept or "").strip()
    if not concept:
        return None

    for canonical_name, concept_data in snapshot.get("concepts", {}).items():
        tag = concept_data.get("xbrl_tag", "")
        if concept in (tag, canonical_name):
            return tag
    return None


def _find_filing_fact(
    fetched_snapshots: list[dict],
    figure: dict,
) -> tuple[bool, str | None]:
    ticker = (figure.get("ticker") or "").strip().upper()
    concept = figure.get("concept", "")
    period_start = figure.get("period_start")
    period_end = figure.get("period_end")
    value = figure.get("value")
    accession = (figure.get("accession") or "").strip()

    for snapshot in fetched_snapshots:
        if ticker and snapshot.get("ticker", "").upper() != ticker:
            continue

        tag = _concept_matches(snapshot, concept)
        if tag is None:
            continue

        concept_data = next(
            (
                data
                for data in snapshot["concepts"].values()
                if data.get("xbrl_tag") == tag
            ),
            None,
        )
        if concept_data is None:
            continue

        for period in concept_data.get("periods", []):
            if period_start and period.get("start") != period_start:
                continue
            if period_end and period.get("end") != period_end:
                continue
            if accession and period.get("accession") != accession:
                continue
            if _values_match(period.get("value"), value):
                return True, None

    reasons = []
    if not ticker:
        reasons.append("missing ticker")
    if not concept:
        reasons.append("missing concept")
    if not period_start or not period_end:
        reasons.append("missing period")
    if not reasons:
        reasons.append("no matching fact in fetched data")
    return False, "; ".join(reasons)


def _find_calculated_result(calculate_history: list[dict], figure: dict) -> tuple[bool, str | None]:
    expression = (figure.get("expression") or "").strip()
    value = figure.get("value")

    if not expression:
        return False, "computed figure missing expression"

    for entry in calculate_history:
        if entry.get("error"):
            continue
        if entry.get("expression") != expression:
            continue
        if _values_match(entry.get("result"), value):
            return True, None

    return False, "expression and result not found in calculate history"


def verify(
    structured: dict,
    fetched_snapshots: list[dict],
    calculate_history: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Walk structured output and split figures into verified and unverified lists.

    Filing figures must match concept, period, and value in data fetched this run.
    Computed figures must match an expression and result from calculate this run.
    """
    verified: list[dict] = []
    unverified: list[dict] = []

    for figure in structured.get("figures") or []:
        source = figure.get("source")
        if source == "filing":
            ok, reason = _find_filing_fact(fetched_snapshots, figure)
        elif source == "computed":
            ok, reason = _find_calculated_result(calculate_history, figure)
        else:
            ok, reason = False, f"unknown source {source!r}"

        item = dict(figure)
        if ok:
            verified.append(item)
        else:
            item["reason"] = reason
            unverified.append(item)

    return verified, unverified


def _format_money(value: float) -> str:
    value = float(value)
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.2f}"


def format_output(
    structured: dict,
    verified: list[dict],
    unverified: list[dict],
) -> str:
    """Render verified output for the terminal."""
    lines: list[str] = []

    summary = (structured.get("summary") or "").strip()
    if summary:
        lines.append(summary)
        lines.append("")

    lines.append("Verified figures:")
    if verified:
        for figure in verified:
            label = figure.get("label", "Figure")
            value = figure.get("value")
            lines.append(f"  {label}: {_format_money(value)}")

            if figure.get("source") == "filing":
                lines.append(f"    concept: {figure.get('concept')}")
                period = figure.get("period_start"), figure.get("period_end")
                if period[0] and period[1]:
                    lines.append(f"    period: {period[0]} to {period[1]}")
                if figure.get("accession"):
                    lines.append(f"    filing: {figure.get('accession')}")
            elif figure.get("source") == "computed":
                lines.append(f"    computed: {figure.get('expression')}")
            lines.append("")
    else:
        lines.append("  None.")
        lines.append("")

    could_not = structured.get("could_not_determine") or []
    lines.append("Could not determine:")
    if could_not:
        for item in could_not:
            lines.append(f"  {item}")
    else:
        lines.append("  None.")
    lines.append("")

    lines.append("Unverified (removed):")
    if unverified:
        for figure in unverified:
            label = figure.get("label", "Figure")
            reason = figure.get("reason", "failed verification")
            lines.append(f"  {label}: {reason}")
    else:
        lines.append("  None.")

    return "\n".join(lines).rstrip()
