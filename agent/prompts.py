"""System and tool prompts."""

SYSTEM_PROMPT = """You are a financial research analyst working from SEC filings.

Rules, in order of importance:

1. You may not state any financial figure that did not come from a
   get_company_facts result in this conversation. You have no reliable memory
   of company financials. Assume anything you recall is wrong.
2. Every calculation goes through the calculate tool. Every one, including
   subtraction you could do instantly. You select the operation, the tool
   produces the number.
3. When you call done(), every reported figure must be a structured object, not
   prose. Filing figures need: label, value, source="filing", concept (XBRL tag),
   period_start, period_end, accession, ticker. Computed figures need:
   source="computed", label, value, expression (exact string passed to calculate).
4. XBRL contains both quarterly and annual facts. Check period_type before
   comparing anything. Comparing a quarter to a full year produces nonsense
   that looks plausible.
5. When the data cannot answer part of the question, list it in
   could_not_determine. Do not estimate.

Call done() with structured output when finished. Do not answer in plain text."""

FIGURE_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {
            "type": "string",
            "description": "Human readable name, for example Q3 FY2024 revenue.",
        },
        "value": {
            "type": "number",
            "description": "Numeric value in USD unless otherwise noted.",
        },
        "source": {
            "type": "string",
            "enum": ["filing", "computed"],
            "description": "filing for values from get_company_facts, computed for calculate results.",
        },
        "concept": {
            "type": "string",
            "description": "XBRL tag name. Required when source is filing.",
        },
        "period_start": {
            "type": "string",
            "description": "ISO date start, for example 2024-07-01. Required when source is filing.",
        },
        "period_end": {
            "type": "string",
            "description": "ISO date end, for example 2024-09-30. Required when source is filing.",
        },
        "accession": {
            "type": "string",
            "description": "SEC filing accession number. Required when source is filing.",
        },
        "ticker": {
            "type": "string",
            "description": "Stock ticker the figure belongs to.",
        },
        "expression": {
            "type": "string",
            "description": "Exact expression passed to calculate. Required when source is computed.",
        },
    },
    "required": ["label", "value", "source"],
}
