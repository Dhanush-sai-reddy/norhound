# Recall measurement — reproducible evidence

Two corpora, one scorer, same command. Numbers below were re-derived on
16 Nov 2026 from the artifacts already on disk; nothing here is remembered or
estimated.

## Scorer

`scripts/measure_recall.py` — deterministic: "The report contains no timestamp
and no unordered iteration, so the same inputs always produce a byte-identical
report."

## Baseline (the shipped corpus, `out/submission/`)

```bash
uv run python scripts/measure_recall.py \
  --profiles out/submission/profiles-promoted.jsonl \
  --observations out/submission/observations.jsonl \
  --labels out/submission/labels.jsonl \
  --output /tmp/opencode/m-base.json
```

- `recall_proxy_50` = **30.1333**
- `entity_precision` = 1.0, `wrong_entity_publications` = 0

## Current corpus (`out/run-fresh-20261115T073743Z/`)

```bash
uv run python scripts/measure_recall.py \
  --profiles out/run-fresh-20261115T073743Z/profiles-promoted.jsonl \
  --observations out/run-fresh-20261115T073743Z/external-final.jsonl \
  --labels out/run-fresh-20261115T073743Z/labels-final.jsonl \
  --output /tmp/opencode/m1.json
```

- `recall_proxy_50` = **33.4333**  (+3.3 over baseline)
- `entity_precision` = 1.0, `wrong_entity_publications` = 0

## Determinism check

The command was run twice on identical inputs:

```
sha256 05c5aac5c210781f94fc5248d18cbc5e9c98d1820473e3ae541b9f1b07c3e038  /tmp/opencode/m1.json
sha256 05c5aac5c210781f94fc5248d18cbc5e9c98d1820473e3ae541b9f1b07c3e038  /tmp/opencode/m2.json
```

Byte-identical, so the improvement is a property of the corpus, not of run
order or of a timestamp.

## What produced the gain

Per-family company recall, `out/run-fresh-20261115T073743Z/measure-family-final.json`:

| family | baseline | current |
|---|---|---|
| any_external (coverage field) | 1.000 | 1.000 |
| two_platforms (coverage field) | 0.639 | **0.994** |
| workforce_jobs (coverage field) | 0.915 | **0.954** |
| buzz_engagement (coverage field) | 0.998 | 1.000 |
| ratings_reviews (coverage field) | 0.032 | 0.032 |
| sentiment (coverage field) | 0.032 | 0.032 |

The workforce gain comes from the official annual-report connector
(`batch.workforce-pdf-report.json`: `eligible 668, accepted 585`) and the
two-platform gain from the registry-proved website connector plus Purehelp.

## Precision gate

`out/run-fresh-20261115T073743Z/eval-final.json`:
`entity_precision 1.0`, `wrong_entity_publications 0`,
`unsupported_publications 0`, `metric_precision 1.0`,
`published_audited 32439 of 32466`, `qualification_passed true`.

Gate is 0.95; measured is 1.0.
