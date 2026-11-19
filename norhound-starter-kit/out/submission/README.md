# NorHound — Signalpost submission package

Generated from run `newsdepth-20261118T120128Z` by `scripts/promote_run.sh`. Keyless corpus: no
API key, no login, no paid account; $0 per 100-company run.

| File | What it is |
|---|---|
| `envelopes.jsonl` | 1,000 terminal envelopes, one per organisation number: claims, the evidence behind every claim, run and operations sections |
| `observations.jsonl` | 31911 external observations with source URL, retrieval time, dates and content hash |
| `labels.jsonl` | The verifier's label per observation (`exact_entity` gates publication) |
| `summaries.jsonl` | Deterministic per-company brief (no model, no key) |
| `eval.json` | Footprint score: entity precision, wrong-entity publications, coverage |
| `measure.json` | The six-field recall proxy used to compare runs |
| `manifest.jsonl` | The organisation-number manifest |
| `profiles-promoted.jsonl` | The frozen profiles the claims were derived from |
| `official-run-report.json` | The machine-readable run report: runtime, request count, third-party cost, identity precision, declared source rights |
| `refresh-report.json` | The material changes found against the previous snapshot, and the changes preserved |
| `site/` | The static viewer: `index.html` (search/sort/compare), `c/<org>.html`, `c/<org>.json`, `companies.csv` |
| `smoke-100/` | The 100-company smoke test: `smoke-envelopes.jsonl` (one complete result per input) and `smoke-report.json` (requested vs returned, per-company claim/evidence counts) |

Checks on this package:

- entity precision 1.0, 0 wrong-company publications, 0 unsupported publications
- 105,266 claims backed by 35,421 evidence records
- published 31885 of 31911 observations
- every published fact carries source URL, retrieval time, reporting date,
  content hash and extraction method
- company recall per fact family: financials 994/1000, hiring 49/84, identity 1000/1000, news 1000/998, other 1000/1000, reviews 32/323, roles 994/1000, social 204/177, website 597/577
- six-field recall proxy 22.38 / 50

Reproduce the evaluator's command: `scripts/run_official_batch.sh --batch
organisations.jsonl` (add `--previous-envelopes <prior envelopes.jsonl>` for a
refresh). See the repository README for the local 1,000-company run.
