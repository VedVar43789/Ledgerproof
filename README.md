# Ledgerproof

A verified financial research agent over SEC XBRL data. Every number in the output is traceable to a specific value in a specific SEC filing, and that trace is checked by code rather than promised by the model.

## Problem

Large language models are good at reasoning and bad at remembering exact numbers. This project produces financial analysis where every figure can be traced back to a real SEC filing—and anything that fails verification is removed.

## Approach

- The model never supplies numbers from memory; it may only report figures fetched from SEC data during the run.
- A verification pass confirms every cited number exists in the fetched data before output reaches the user.
- An agent loop decides what to fetch next based on prior results—not a fixed pipeline.

## Status

Early stage. See [project_overview.md](project_overview.md) for the full build plan.
