# questions.json — how to fill it

Ground-truth evaluation set for Ledgerproof v2. Twenty-five questions across six
companies. Twenty answerable values are blanked and must be filled by reading the
filing yourself. Do not trust any number you did not read from a filing, including
the two `_UNVERIFIED_recalled_value` examples in q01 and q02. Those are a model's
recollection, shown only so you can see a finished record. Verify them too, then
delete the `_UNVERIFIED_recalled_value` key.

## Schema

Answerable question:

```json
{
  "id": "q01",
  "type": "single_lookup | calculation | trap",
  "question": "...",
  "ticker": "DDOG",
  "answerable": true,
  "ground_truth": {
    "value": null,               // fill this from the filing
    "tolerance_pct": 0.005,      // relative, except q12 where it is absolute points
    "concept": "...",            // XBRL tag, or a derived: formula for calculations
    "period_start": "2024-07-01",
    "period_end": "2024-09-30",
    "accession": null            // fill with the filing you read the value from
  },
  "verify_url": "...",
  "notes": "reading instructions and audit trail"
}
```

Unanswerable question — no `ground_truth` block at all:

```json
{
  "id": "q13",
  "type": "unanswerable",
  "answerable": false,
  "unanswerable_reason": "in_mdna_not_xbrl | does_not_exist | check_may_be_tagged",
  "verify_url": "...",
  "notes": "..."
}
```

## Every key, what goes in it

### Top-level keys (present on every question)

**`id`** — A stable unique label, `q01` through `q25`. Zero-padded so they sort
correctly. Never reuse or renumber an id once you have results tied to it, because
your results files reference questions by id. If you add questions later, keep
going: q26, q27.

**`type`** — One of four values. This is not decoration; the runner groups scores
by type so you can see, for example, that accuracy is high on lookups but low on
traps. Choose by what the question tests:
- `single_lookup` — one figure read directly from a statement, no math. "What was
  revenue in Q3."
- `calculation` — the answer requires arithmetic the agent must route through the
  calculator. Margins, growth rates, differences.
- `unanswerable` — the answer cannot come from XBRL companyfacts. The correct
  behaviour is refusal. Never has a ground_truth block.
- `trap` — answerable, but engineered so a naive agent gets a plausible wrong
  answer. Period-type confusion, fiscal-label confusion, attribution ambiguity.

**`question`** — The exact natural-language string sent to the agent. Write it the
way a person would actually ask, and make the period unambiguous by naming the
calendar quarter-end date, for example "the quarter ended April 30, 2025", not
"Q1", because fiscal Q1 means different months at different companies. This is the
only field the agent sees. Everything else is for scoring.

**`ticker`** — Uppercase stock symbol, `DDOG`, `SNOW`, `MSFT`. The runner uses it
to know which company facts to expect and for per-company score breakdowns. It
must match the ticker your `edgar.resolve_cik` can look up.

**`answerable`** — `true` or `false`. `true` means a correct figure exists in XBRL
and you must supply ground truth. `false` means the correct agent behaviour is to
decline, and you supply no ground_truth block. This flag is what the runner
branches on to decide which scorer to apply.

**`verify_url`** — The EDGAR page where you (the human) go to find and confirm the
answer. Not used by the runner or the agent. It exists so that three weeks from now
you can re-check a value without rediscovering where it came from. Leave the
provided URLs as they are.

**`notes`** — Free text, for you. Two jobs: reading instructions before you fill
the value ("three-months column, not six-months"), and an audit trail after
("used total revenue 921.0M and total cost 178.4M; margin 80.6%"). When the agent
later disagrees with your ground truth, this note is how you tell whether the agent
is wrong or your value is. Write down the raw inputs to any calculation here, not
just the final answer.

### Inside `ground_truth` (answerable questions only)

**`value`** — The correct answer, as a plain number in base units. Dollars, not
millions: write `690016000`, not `690.0` or `690016`. For percentages, write the
percentage number: a 80.03% margin is `80.03`, not `0.8003`. This is the single
most important field and the one you must read from the filing yourself. It starts
as `null`.

**`_UNVERIFIED_recalled_value`** — Only on q01 and q02. A model's guess at the
value, present so you can see a completed record's shape. Treat it as wrong until
you confirm it. Once you have read the real number into `value`, delete this key.
No other question should have it.

**`tolerance_pct`** — How close the agent's answer must be to count as correct,
as a fraction. `0.005` means within 0.5 percent, which absorbs rounding when the
filing reports millions and the agent works in whole dollars. Use a wider value
for multi-step calculations where rounding compounds: growth-rate questions use
`0.02`. One exception: on q12 the answer is measured in percentage POINTS, so the
tolerance is an absolute point value, not a fraction. Either special-case q12 in
the runner, or add a `tolerance_abs` key and have the runner prefer it when present.
The second is cleaner if you have more point-difference questions later.

**`concept`** — What the value should be cited as, so citation validity can be
checked. Two forms:
- For a directly reported figure, the exact XBRL tag, for example
  `RevenueFromContractWithCustomerExcludingAssessedTax` or `NetIncomeLoss`. Get the
  exact tag by looking at the companyfacts JSON, since it varies by company. If you
  do not yet know it, leave `null` and fill it when you read the filing.
- For a calculation, a `derived:` string naming the formula, for example
  `derived: (Revenue - CostOfRevenue) / Revenue * 100`. This is documentation of
  how the answer is built; the runner does not parse it, it is for you and for
  anyone reading the eval set.

**`period_start`** and **`period_end`** — The exact dates the figure covers, ISO
format `YYYY-MM-DD`. For a quarter these span roughly three months; for a full year,
twelve. These are already filled based on the calendar quarter in each question, but
CONFIRM them against the filing, especially for Nvidia (q05, q16, q22), whose
quarters end on odd dates like April 27 rather than a clean month-end. A wrong
period here means citation validity fails even when the value is right.

**`accession`** — The SEC accession number of the specific filing you read the
value from, format like `0001561550-25-000313`. Fill it when you read the value. It
matters most on restated figures, where the same fiscal quarter appears in two
filings with different numbers, and this records which one you treated as truth.
Starts as `null`.

### Extra key on unanswerable questions

**`unanswerable_reason`** — Why it cannot be answered from XBRL. Drives whether it
could become answerable in a later version. Values are listed in their own section
below. Only appears when `answerable` is `false`.

## How the runner should score

- **Numerical accuracy** (answerable only): agent value within `tolerance_pct` of `value`.
- **Citation validity** (answerable only): the cited concept and period actually
  contain the value in the fetched data. Fully programmatic via verify.py.
- **Appropriate refusal** (unanswerable only): scored STRUCTURALLY, not by keywords.
  Pass if the agent emitted no verified figure for the asked metric AND
  could_not_determine is non-empty. Do not match on refusal wording.

## Per-run counts to log (defends the headline number)

For each run, record three counts, not just a rate:
`figures_attempted`, `figures_verified`, `figures_rejected`.
This lets you show that a lower hallucination rate after verification is not just
the agent citing fewer figures to game the metric.

## unanswerable_reason values

- `in_mdna_not_xbrl` — exists in the filing but as prose, not structured XBRL.
  Unanswerable now, would become answerable if v3+ adds document retrieval.
- `does_not_exist` — not disclosed anywhere. Never answerable.
- `check_may_be_tagged` — you must look. If it turns out to be in XBRL, flip
  `answerable` to true, add a ground_truth block, set reason to null. (Only q16.)

## Distribution

10 single_lookup, 6 calculation, 5 unanswerable, 4 trap.
DDOG 7, SNOW 4, CRWD 4, MSFT 4, NVDA 3, PLTR 3.

## Start small

Fill and validate the first five (q01–q05, five companies) before doing all 25.
Get the runner working against those five, then expand. Do not tune the agent
while filling the set — freeze the questions, then iterate the agent against them.