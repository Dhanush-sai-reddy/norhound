# Autoresearch session: signalpost

## Skill version
2.0.0

## Mode
narrow

## Target
- Path: /home/dhanushsr/.local/share/opencode/worktree/85c9ea/autoresearch-improve-recall/norhound-starter-kit
- Stack: Python 3.12
- Test command: `uv run python -m unittest discover -s tests -p 'test_*.py'`
- Linter: none
- Branch: autoresearch/narrow/signalpost
- Config: none
- Scope: external recall connectors, exact-entity verification, recall measurement, and tests

## Baseline
- Tests: pending clean baseline (`uv run pytest -q` currently collects under system Python 3.14 and cannot import the tracked feed-news module; the missing module is restored from the user's dirty main checkout)
- Base commit: af49188
- Date: 2026-11-04

## Goal (narrow only)
- Metric: exact-company six-field external recall proxy (points out of 50)
- Measurement command: `python3 scripts/measure_recall.py --observations out/recall-baseline.external.jsonl --labels out/recall-baseline.labels.jsonl --profiles out/recall-baseline.profiles.jsonl --output out/recall-baseline.measure.json`
- Baseline value: 37.0083/50 (freshly labeled frozen-source superset, 1000 companies)
- Target value: > 37.0083/50 with entity precision >= 0.95 and zero wrong-company publications
- Current value: 37.0083/50

## Angles (narrow only)
| Priority | Name | Hypothesis | Status |
|----------|------|-----------|--------|
| 1 | Evidence-verifiable exact-source recall | Existing exact-company connectors can add publishable observations if retained source bodies and exact organisation-number proofs are re-verifiable, without weakening identity gates | in-progress |

## Cycles completed

## What's been tried
- 2026-11-04: identified a clean worktree at commit af49188 so the user's 162-file dirty main checkout remains untouched.
- 2026-11-04: restored the tracked-test dependency `scripts/run_feed_news_connector.py` from the dirty main checkout; no main-checkout files changed.

## Open issues
- The repository's documented `uv run pytest -q` command is not self-contained because pytest is absent from project dependencies and resolves to system Python 3.14.
- The baseline superset artifacts are untracked files in the dirty main checkout; copy them into the isolated worktree before running the reproducible measurement.
- Direct reviewer-gap counts are social 185, dated news 143, hiring 918; six-field proxy remains the measurable narrow-mode metric.
