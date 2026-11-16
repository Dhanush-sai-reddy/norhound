# Recall measurement — reproducible evidence

Two corpora, one scorer, same command. Numbers below were re-derived on
16 Nov 2026 from the artifacts already on disk; nothing here is remembered or
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

- `recall_proxy_50` = **23.1083**
- `entity_precision` = 1.0, `wrong_entity_publications` = 0

## Current corpus (`out/run-fresh-20261115T073743Z/`)

```bash
uv run python scripts/measure_recall.py \
  --profiles out/run-fresh-20261115T073743Z/profiles-promoted.jsonl \
  --observations out/run-fresh-20261115T073743Z/external-final.jsonl \
  --labels out/run-fresh-20261115T073743Z/labels-final.jsonl \
  --output /tmp/opencode/m1.json
```

- `recall_proxy_50` = **25.9083**  (+2.80 over baseline)
- `entity_precision` = 1.0, `wrong_entity_publications` = 0

Both numbers are lower than the 30.13 / 33.43 this file reported until 16 Nov
2026, because the scorer used to count `workforce_snapshot` (registry and
annual-report headcount) as `workforce_jobs`. The reviewer's rule is that a
hiring fact needs a role card, a job-feed item or an apply action, so headcount
is now reported as its own coverage field and excluded from the proxy. Only 51
of 1,000 companies publish an actual job posting.

## Determinism check

The command was run twice on identical inputs:

```
sha256 3acca7eab34957c0795f23ac9598e0dc442d72a7d5c961299c5e0e38542f5b98  /tmp/opencode/m1.json
sha256 3acca7eab34957c0795f23ac9598e0dc442d72a7d5c961299c5e0e38542f5b98  /tmp/opencode/m2.json
```

Byte-identical, so the improvement is a property of the corpus, not of run
order or of a timestamp.

## What produced the gain

Per-family company recall, `out/run-fresh-20261115T073743Z/measure-family-final.json`:

| family | baseline | current |
|---|---|---|
| any_external (coverage field) | 1.000 | 1.000 |
| two_platforms (coverage field) | 0.639 | **0.994** |
| workforce_jobs (coverage field) | 0.072 | 0.051 |
| workforce_snapshot (headcount, not in the proxy) | 0.915 | 0.954 |
| buzz_engagement (coverage field) | 0.998 | 1.000 |
| ratings_reviews (coverage field) | 0.032 | 0.032 |
| sentiment (coverage field) | 0.032 | 0.032 |

The gain is `two_platforms` (0.639 → 0.994) from the registry-proved website
connector plus Purehelp, and `buzz_engagement` (0.998 → 1.000).
`workforce_jobs` moved slightly down (0.072 → 0.051): the headcount gain is real
but it is not hiring, and it is reported on its own line instead of being
counted as a job signal.

## Precision gate

`out/run-fresh-20261115T073743Z/eval-final.json`:
`entity_precision 1.0`, `wrong_entity_publications 0`,
`unsupported_publications 0`, `metric_precision 1.0`,
`published_audited 32439 of 32466`, `qualification_passed true`.

Gate is 0.95; measured is 1.0.
