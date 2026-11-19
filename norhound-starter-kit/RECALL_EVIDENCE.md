# Recall measurement — reproducible evidence

Two corpora, one scorer, same command. Numbers below were re-derived on
17 Nov 2026 from the artifacts already on disk; nothing here is remembered or
estimated.

## Scorer

`scripts/measure_recall.py` — deterministic: "The report contains no timestamp
and no unordered iteration, so the same inputs always produce a byte-identical
report."

## Baseline (the previous shipped corpus, `out/baseline-3013/`)

```bash
uv run python scripts/measure_recall.py \
  --profiles out/baseline-3013/profiles-promoted.jsonl \
  --observations out/baseline-3013/observations.jsonl \
  --labels out/baseline-3013/labels.jsonl \
  --output /tmp/opencode/m-base.json
```

- `recall_proxy_50` = **13.0083**
- `entity_precision` = 1.0, `wrong_entity_publications` = 0

## Current corpus (`out/run-newsdepth-20261118T120128Z/`)

```bash
uv run python scripts/measure_recall.py \
  --profiles out/run-newsdepth-20261118T120128Z/batch-rescued-profiles.jsonl \
  --observations out/run-newsdepth-20261118T120128Z/external-final.jsonl \
  --labels out/run-newsdepth-20261118T120128Z/labels-final.jsonl \
  --output /tmp/opencode/m1.json
```

- `recall_proxy_50` = **22.3833**  (+9.38 over baseline)
- `entity_precision` = 1.0, `wrong_entity_publications` = 0

Both corpora are scored with the **same, current** scorer. Earlier versions of
this file reported 30.13 / 33.43 for the same two corpora, because the scorer
counted `workforce_snapshot` (registry and annual-report headcount) as
`workforce_jobs`, counted the register itself towards `any_external` and
`two_platforms`, and counted Brønnøysund annual-account announcements as
`buzz_engagement`. Each of those made a field tautological: the register
answers all three for every profiled company. They are now defined over
something the company has to earn — a source outside the register, a real
advert, a third-party mention — and the headline is lower because it is true.

`scripts/evaluate_external_footprint.py` imports the same definitions, so the
audit report and this report cannot print different coverage numbers for one
corpus.

## Determinism check

Each command was run twice on identical inputs:

```
b00f0be7687a14a73f531838bd3019e4b78c9e4b05a385e9abb5b9bba706245f  /tmp/opencode/mcur1.json
b00f0be7687a14a73f531838bd3019e4b78c9e4b05a385e9abb5b9bba706245f  /tmp/opencode/mcur2.json
8258bf950d0452350fa18b7acb696a06e7699c7eec9687ce5d27edf350f2df14  /tmp/opencode/mbase1.json
8258bf950d0452350fa18b7acb696a06e7699c7eec9687ce5d27edf350f2df14  /tmp/opencode/mbase2.json
```

Byte-identical, so the gain is a property of the corpus, not of run order or of
a timestamp.

## What produced the gain

Per-field coverage, both corpora measured by the command above:

| field | baseline | current | what moved it |
|---|---|---|---|
| any_external | 0.639 | **0.994** | registry-proved website connector + Purehelp |
| two_platforms | 0.276 | **0.620** | a second independent source for 344 more companies |
| workforce_jobs | 0.072 | 0.014 | a careers-page link is not a role card; see below |
| workforce_snapshot (headcount, not in the proxy) | 0.915 | 0.575 | the annual-report OCR stage is off by default and earns 0 points |
| buzz_engagement | 0.510 | **0.994** | third-party profile, mention or post; registry announcements excluded |
| ratings_reviews | 0.032 | 0.032 | no keyless source reaches more |
| sentiment | 0.032 | 0.032 | derived from the same rating rows |

`workforce_jobs` fell because the company-site jobs connector was emitting
`job_posting` for every link it *discovered* on a careers page without fetching
the posting — "Digitalt testament" and "Marketing" were published as job
titles. It now emits an explicit `careers_page` signal, and a discovered link
can no longer become a role title. The honest value is the number of companies
with a real role card: 14 companies, all from NAV's official feed. The public
ATS boards find postings for 3 more companies, but the identity gate rejects
them: the posting pages sit on third-party boards and the frozen site evidence
cannot re-derive the board link.

## Precision gate

`out/run-newsdepth-20261118T120128Z/eval-final.json`:
`entity_precision 1.0`, `wrong_entity_publications 0`,
`unsupported_publications 0`, `metric_precision 1.0`,
`published_audited 31778 of 31804`.

Gate is 0.95; measured is 1.0.
