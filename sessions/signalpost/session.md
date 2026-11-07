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
- Tests: 505 pass (`uv run python -m unittest discover -s tests -p 'test_*.py'`, 8 skipped)
- Base commit: af49188
- Date: 2026-11-04

## Goal (narrow only)
- Metric: exact-company company recall per official fact family (points out of 50), measured on the published contract envelopes with `scripts/measure_family_recall.py`
- Measurement command: `uv run python scripts/measure_family_recall.py --envelopes out/submission/envelopes.jsonl --output out/measure-family-submitted.json`
- Baseline value (all claims): 48.3036/50; (external-only): 11.6004/50
- Target value: close the website and hiring families with entity precision >= 0.95 and zero wrong-company publications
- Current value (all claims): 49.9914/50; (external-only): 11.5576/50
- Secondary metric: `scripts/measure_recall.py` six-field proxy, baseline 37.0083/50, current 30.13/50 (two of its six terms are ratings/sentiment, which the rubric does not score and which the Google exclusion removed)

## Angles (narrow only)
| Priority | Name | Hypothesis | Status |
|----------|------|-----------|--------|
| 1 | Evidence-verifiable exact-source recall | Existing exact-company connectors can add publishable observations if retained source bodies and exact organisation-number proofs are re-verifiable, without weakening identity gates | done |
| 2 | Website-family coverage | The register's own website filing, the sole-declarer domain index, a description fallback and a browser rescue recover homepages the plain crawl cannot read | done (388/577 -> 576/577) |
| 3 | Hiring-family coverage | NAV's official feed plus public ATS feeds, each gated on the exact legal entity, close the hiring family | done (65/84 -> 84/84) |

## Cycles completed
- 2026-11-07: browser rescue built and wired into the external pipeline before the site stages (19 tests).
- 2026-11-07: family-recall scorer built with an external-only variant (21 tests).
- 2026-11-07: Google and proff excluded from publication (keyless + source-rights).
- 2026-11-07: DNS resolver retry added after the full run lost 330 homepages to a transient resolver burst (6 tests).
- 2026-11-07: rescue stage made to degrade when playwright is absent (1 test).
- 2026-11-07: submission artifacts rebuilt from the 32,713-row keyless corpus; commit c855d59.

## What's been tried
- 2026-11-04: identified a clean worktree at commit af49188 so the user's 162-file dirty main checkout remains untouched.
- 2026-11-04: restored the tracked-test dependency `scripts/run_feed_news_connector.py` from the dirty main checkout; no main-checkout files changed.
- 2026-11-07: OSM `ref:NO:orgnr` measured as a dead end (4 of 1,000 orgs, 0 social tags) and not wired in.
- 2026-11-07: DuckDuckGo HTML discovery dead (anomaly page); Finn.no vetoed on terms and zero org numbers in the payload.
- 2026-11-07: the second full 1,000-company run was degraded by a transient DNS burst (330 homepages lost, rescue 0/133). The hosts all resolve now; the run was discarded and the pre-burst corpus shipped.

## Open issues
- Keyless ratings/sentiment ceiling is 32 of the 323 review opportunities (Fagfolkguiden only). The rubric does not score that family.
- The external-only headline is flat (11.60 -> 11.56): the Google exclusion removed 194 companies' worth of external "other" facts and 8 social handles, which offsets the website (+188) and hiring (+19) gains.
- `out/run-full-2026-11-07/` holds the degraded run and must not be reported as a result.
