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
