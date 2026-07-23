# Ledgerproof

Financial research agent where every number is verified against the filing it came from.

---

## What It Is

Ledgerproof is a financial research agent that answers questions about public company financials using SEC EDGAR data. Every number in the output is verified programmatically against the filing it came from before it reaches the user.

The model investigates a question by calling tools. It fetches structured XBRL data from the SEC, selects arithmetic operations, and assembles an answer. It does not supply figures from memory. A verification pass runs on the structured output before anything is printed. Figures that fail the check are removed and reported as unverified.

This is not a chatbot, a stock picker, or a framework demonstration. It is a small agent with a hard verification layer and a measured error rate.

---

## The Problem

Language models reason well but recall exact numbers badly. Ask a model for a specific line item from a specific quarter and it returns a confident, plausible, frequently wrong figure with no way to tell good from bad.

This is the main reason language models are not trusted for financial analysis. The reasoning is often fine. The facts underneath it are unverifiable.

Ledgerproof makes the model structurally incapable of supplying a number from memory. Figures may only come from a live SEC data fetch performed during that run. A verification pass confirms each one exists in the fetched data before printing. Anything failing the check is removed and reported as unverified.

---

## How Verification Works

From v1 onward, the agent returns structured output rather than a formatted string. Every figure is an object containing:

- the numeric value
- the XBRL concept name (for example `Revenues`)
- the fiscal period (for example `FY2024Q3`)
- the filing accession number the value came from

Before any output reaches the user, code walks the structured output and confirms each figure exists in the JSON that was actually fetched during this run. The check is exact: same concept, same period, same value.

Figures that pass are printed with their citation metadata attached. Figures that fail are moved to an unverified list and are not printed. The agent is also required to include a "could not determine" section for questions it cannot answer from the data available.

Fetching is deterministic. Verification is deterministic. The model does not get to override either step.

---

## Why It Is Agentic

The sequence of steps is not known in advance. A single company, two quarter question takes four tool calls. A two company comparison across six quarters with mismatched fiscal calendars takes thirty, and requires noticing the calendar mismatch partway through and correcting for it. The model chooses the next action based on what the previous tool returned.

Fetching and verification are deterministic code. Only the investigation sequence is agentic. That boundary is deliberate.

A fixed pipeline would need to anticipate every question shape in advance. Financial research questions do not have a fixed shape. The agent decides what to fetch, when to compute, and when it has enough to answer.

---

## Quickstart

**Requirements:** Python 3.11+, a Google AI Studio API key (free tier).

```bash
git clone https://github.com/VedVar43789/Ledgerproof.git
cd Ledgerproof
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export GEMINI_API_KEY=your_key_here
export SEC_USER_AGENT="Your Name your@email.com"
```

The SEC EDGAR API requires a User-Agent header identifying you. Set `SEC_USER_AGENT` before running.

```bash
python -m agent.run "What was Datadog's revenue in Q3 and Q4 FY2024?"
```

### Example Output (v1)

```
Question: What was Datadog's revenue in Q3 and Q4 FY2024?

Verified figures:
  Q3 FY2024 revenue: $690.0M
    concept: Revenues
    period: FY2024Q3
    filing: 0001561550-24-000045

  Q4 FY2024 revenue: $737.7M
    concept: Revenues
    period: FY2024Q4
    filing: 0001561550-25-000012

  Q4 over Q3 growth: 6.9%
    computed from verified figures above

Could not determine:
  None. Both quarters were present in the fetched XBRL data.

Unverified (removed):
  None.
```

If the model cites a figure not present in the fetched data, that figure appears under "Unverified (removed)" and is not included in the answer body.

---

## Architecture

### Data Source

All financial data comes from the SEC EDGAR XBRL companyfacts endpoint:

```
https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
```

This endpoint is free, requires no API key, and returns every concept a company has reported, structured by fiscal period. Requests require a User-Agent header. Rate limit is ten requests per second.

### Tools (v0)

| Tool | Purpose |
| --- | --- |
| `get_company_facts(ticker)` | Resolve ticker to CIK, fetch companyfacts JSON, return a trimmed subset of relevant concepts |
| `calculate(expression)` | Evaluate an arithmetic expression in Python and return the result |
| `done(answer)` | Signal that the investigation is complete |

The model never performs arithmetic. It selects the operation. Python computes the result.

### Model Provider

Primary development model is Gemini 3 Flash on the Google AI Studio free tier. Two reasons: no cost during development, and the agent loop mechanics being learned are model agnostic.

Free tier constraints shape the code:

| Constraint | Limit |
| --- | --- |
| Requests per minute | ~10 |
| Tokens per minute | 250,000 |
| Requests per day | 1,500 |
| Available models | Flash and Flash-Lite only (Pro models moved behind billing in April 2026) |

Quota is per Google Cloud project, not per API key. It resets at midnight Pacific, not on a rolling window. Free tier prompts may be used for training, which is acceptable here because all data sent is public SEC filing data.

### Provider Abstraction

`agent/llm.py` exposes a single function that takes messages and tool definitions and returns either a tool call request or a final answer. All provider specific code lives only in this file. Swapping between Gemini, Anthropic, and OpenAI is a config change rather than a rewrite. This exists to make the two model evaluation comparison cheap.

### Rate Limiting and Retry (v0)

The binding constraint is tokens per minute, not requests per day. The fetched companyfacts payload is resent on every iteration of a trajectory. An eight step run can move roughly 100,000 tokens in under a minute, so two consecutive runs approach the ceiling.

v0 includes client side rate limiting, exponential backoff with jitter on HTTP 429, and disk caching of EDGAR responses so repeated development runs against the same company hit the network once. Tool and API failure handling is part of agent engineering practice, not a workaround.

### Agent Loop

The loop is roughly forty lines of Python. No framework until v4.

```
messages = [system_prompt, user_question]

for iteration in range(MAX_ITERATIONS):
    response = llm.call(messages, tools=[get_company_facts, calculate, done])

    if response.tool == "get_company_facts":
        result = fetch_edgar(response.ticker)
        messages.append(tool_result(result))

    elif response.tool == "calculate":
        result = eval_arithmetic(response.expression)  # safe eval, not model math
        messages.append(tool_result(result))

    elif response.tool == "done":
        structured = response.answer
        verified, unverified = verify(structured, fetched_data)
        print(format_output(verified, unverified))
        break
```

### Example Trajectory

Question: "What was Datadog's revenue in Q3 FY2024?"

```
[1] get_company_facts("DDOG")
    -> fetched CIK 0001561550, 847 concepts, trimmed to 42

[2] (model reads Revenues for FY2024Q3 from tool result)

[3] done({
      figures: [{value: 690000000, concept: "Revenues", period: "FY2024Q3", accession: "0001561550-24-000045"}],
      could_not_determine: []
    })

[4] verify() -> 1 figure checked, 1 passed, 0 failed
```

A comparison question across two companies and six quarters produces a trajectory of twenty to thirty steps. The model decides when to fetch each company, which periods to align, and when it has enough to answer.

### Repository Layout

```
Ledgerproof/
  agent/
    loop.py           # agent loop
    llm.py            # provider abstraction (Gemini, Anthropic, OpenAI)
    tools.py          # tool definitions and dispatch
    verify.py         # verification pass (v1)
    memory.py         # notes and compaction (v3)
    prompts.py
  data/
    edgar.py          # companyfacts fetching, CIK resolution, disk cache
  eval/
    questions.json    # ground truth set (v2)
    runner.py
    results/
  graph/              # LangGraph version (v4)
```

### Stack

| Piece | Choice |
| --- | --- |
| Language | Python 3.11+ |
| Model (development) | Gemini 3 Flash via Google AI Studio free tier |
| Model (evaluation) | Gemini 3 Flash and a Sonnet class model via `agent/llm.py` |
| Data | SEC EDGAR companyfacts API |
| Storage | JSON files (v0 to v2), SQLite (v3+) |
| Framework | None until v4, then LangGraph |

---

## Version Roadmap

Each version runs end to end and does something useful. If you stop at any point, you have a working project.

| Version | Scope |
| --- | --- |
| **v0** | Raw agent loop, three tools, trajectory printed to terminal, provider abstraction in `agent/llm.py`, client side rate limiting, exponential backoff on 429, EDGAR disk cache, no verification |
| **v1** | Structured output with XBRL concept, fiscal period, and filing accession on every figure. Programmatic verification pass. "Could not determine" section. |
| **v2** | Hand verified evaluation suite of 20 to 30 questions, run against Gemini 3 Flash and a Sonnet class model. Scores numerical accuracy, citation validity, and appropriate refusal separately. Produces two dimensional hallucination rate table per model, before and after verification. |
| **v3** | Multi company comparisons, fiscal calendar alignment, notes tool, context compaction, SQLite run history |
| **v4** | LangGraph rebuild with checkpointing and interrupts. Written comparison against the hand built version. |
| **v5** | Optional voice input and output. Spoken rendering generated from the same verified structure. |

Current status: early development. See [project_overview.md](project_overview.md) for the full build plan.

---

## Cost

| Component | Cost |
| --- | --- |
| SEC EDGAR companyfacts API | Free |
| yfinance (ticker to CIK lookup) | Free |
| Python, SQLite, local execution | Free |
| Gemini 3 Flash during development | Free (Google AI Studio tier) |
| v2 evaluation runs (Sonnet class model) | Paid, budget roughly $10 to $20 |

Everything except the paid evaluation runs costs nothing. Development and iteration run entirely on the free tier.

---

## Evaluation

The headline deliverable of this project is a measured hallucination rate, not the architecture.

The evaluation suite contains 20 to 30 hand verified questions with ground truth answers checked against the filings directly. Questions range from single value lookups to multi company comparisons to deliberately unanswerable cases. Three dimensions are scored separately:

| Dimension | What it measures |
| --- | --- |
| Numerical accuracy | Is the value correct within a defined tolerance |
| Citation validity | Does the cited concept and period actually contain that value (checked by code) |
| Appropriate refusal | On unanswerable questions, did the agent say so rather than guess |

The suite runs against both Gemini 3 Flash and a Sonnet class model. Each model is tested on v0 (no verification) and v1 (with verification). Paid runs for the Sonnet class model are budgeted at roughly $10 to $20.

**Citation hallucination rate (citation validity dimension)**

| Model | Before verification | After verification |
| --- | --- | --- |
| Gemini 3 Flash | TBD | TBD |
| Sonnet class | TBD | TBD |

A single before/after number would only show that verification helps on one model. A two dimensional table shows that verification reduces hallucination across models with different baseline error rates. That is the central claim: the verification layer works independently of model quality, not because one particular model is careful enough on its own.

Target claim shape once measured:

> Citation hallucination rate was X% before programmatic verification and Y% after on Gemini 3 Flash, and A% before and B% after on a Sonnet class model, measured across a hand verified 25 question evaluation suite.

This is the minimum version worth putting on a resume. It is the first one with a number attached.
