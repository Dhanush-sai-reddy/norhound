# Family recall measured the way the rubric counts it

**Date:** 2026-11-07
**Scorer:** `scripts/measure_family_recall.py`
**Baseline corpus:** `resume-20261104-final.contract-superset.jsonl`
(the clean baseline's published envelopes, read from the dirty main checkout
and copied into `.cache/baseline/`; the main checkout was not modified).

## Why a second measurement

`scripts/measure_recall.py` scores six *coverage* ratios
(`any_external`, `two_platforms`, `workforce_jobs`, `ratings_reviews`,
`buzz_engagement`, `sentiment`) and reports their mean as points out of 50.
That proxy has one problem: two of its six terms are ratings and sentiment,
which this project deliberately gave up when Google was excluded
(`docs/evidence/keyless-google-exclusion-2026-11-07.md`). The proxy therefore
measures a decision the rubric does not score, and a change that improves the
real recall can still look like a regression.

The rubric counts **company recall per fact family** against the union of
every participant's and Builderr's discoveries. This measurement does exactly
that, so the numbers below are comparable with the rubric's shape and the
reviews decision is visible instead of baked in.

## Definitions

* **Opportunity** — the number of companies for which a family has a match
  somewhere in the union of all participants' and Builderr's discoveries. The
  official 1,000-company counts are the challenge corpus family counts
  recorded in `AGENTS.md`:

  | family | identity | roles | financials | other | news | website | reviews | social | hiring |
  |---|---|---|---|---|---|---|---|---|---|
  | opportunities | 1000 | 1000 | 1000 | 1000 | 998 | 577 | 323 | 177 | 84 |

* **Covered** — the number of companies whose published envelope carries at
  least one claim of that family. The envelope is the publication surface, and
  its claims carry the family they belong to.
* **Recall** — covered / opportunities. A value above 1.0 means the corpus
  publishes the family for more companies than the official union counts
  (every company gets a registry announcement, for example, while the union
  lists 998 news opportunities).
* **Scored families** — every family except `reviews`. The rubric does not
  score ratings, reviews or sentiment, and no keyless source reaches more than
  32 of the 323 review opportunities
  (`docs/evidence/keyless-review-sources.md`).
* **Six decision families** — identity, accounts (financials), people (roles),
  website, hiring and activity (news + other + social).

## Baseline, measured with this scorer

```bash
uv run python scripts/measure_family_recall.py \
  --envelopes .cache/baseline/resume-20261104-final.contract-superset.jsonl \
  --output out/measure-family-baseline.json
```

| family | covered | opportunities | recall |
|---|---|---|---|
| identity | 1000 | 1000 | 1.0000 |
| financials | 1000 | 1000 | 1.0000 |
| roles | 1000 | 1000 | 1.0000 |
| other | 1000 | 1000 | 1.0000 |
| news | 1000 | 998 | 1.0020 |
| social | 185 | 177 | 1.0452 |
| reviews | 428 | 323 | 1.3251 |
| **website** | **388** | **577** | **0.6724** |
| **hiring** | **65** | **84** | **0.7738** |

* `scored_family_recall_proxy_50` = **48.3036**
* `scored_group_recall_proxy_50` = **48.3036**

## Keyless corpus, measured with the same scorer

The keyless corpus is the shipped observation corpus
(`out/web1000batch.external-merged.jsonl`, 32,713 rows, Google and proff
excluded), published into envelopes and scored by the same script:

```bash
uv run python scripts/emit_contract_envelope.py \
  --profiles out/submission/profiles-promoted.jsonl \
  --envelopes out/submission/envelopes.jsonl \
  --observations out/web1000batch.external-merged.jsonl \
  --labels out/web1000batch.labels-merged.jsonl \
  --output out/keyless-envelopes.jsonl
uv run python scripts/measure_family_recall.py \
  --envelopes out/keyless-envelopes.jsonl \
  --output out/measure-family-keyless.json
```

| family | baseline covered/opp | keyless covered/opp | delta |
|---|---|---|---|
| identity | 1000/1000 | 1000/1000 | 0.0000 |
| financials | 1000/1000 | 1000/1000 | 0.0000 |
| roles | 1000/1000 | 1000/1000 | 0.0000 |
| other | 1000/1000 | 1000/1000 | 0.0000 |
| news | 1000/998 | 998/998 | −0.0020 |
| social | 185/177 | 177/177 | −0.0452 |
| **website** | **388/577** | **576/577** | **+0.3258** |
| **hiring** | **65/84** | **84/84** | **+0.2262** |
| reviews (not scored) | 428/323 | 32/323 | −1.2260 |

| scorer | baseline | keyless | delta |
|---|---|---|---|
| `scored_family_recall_proxy_50` | 48.3036 | **49.9914** | **+1.6878** |
| `scored_group_recall_proxy_50` | 48.3036 | **49.9914** | **+1.6878** |
| six decision families | identity 1.0, accounts 1.0, people 1.0, website 0.6724, hiring 0.7738, activity 1.0046 | identity 1.0, accounts 1.0, people 1.0, **website 0.9983**, **hiring 1.0**, activity 1.0 | — |

The two families that were below full coverage in the baseline are now
essentially closed: **website 388 → 576 of 577** and **hiring 65 → 84 of 84**.
The two small losses (news −2 companies, social −8 companies) are the direct
cost of the Google exclusion: those companies' only dated mentions and social
handles came from Google Maps rows, which the exclusion removes. The net
effect on the scored families is **+1.69 points**.

The old six-field proxy (`scripts/measure_recall.py`) reports 30.13/50 for the
same corpus against a 37.0083 baseline, because two of its six terms are
ratings and sentiment — the two the rubric does not score and the two the
Google exclusion removed. The family scorer above is the honest comparison.

## The external-only measurement (the number that actually tracks external recall)

The all-claim proxy above counts the register's own facts, and the register
gives every company its identity, its accounts, its roles and a dated
announcement. 85 % of its weight is therefore facts that were never at risk.
The same scorer therefore measures every family a second time, counting only
the claims whose evidence comes from a source **outside** the register
(`data.brreg.no`, `w2.brreg.no`):

| scorer | baseline | keyless | delta |
|---|---|---|---|
| `scored_family_recall_proxy_50` (all claims) | 48.3036 | 49.9914 | **+1.6878** |
| `scored_external_family_recall_proxy_50` (external only) | 11.6004 | 11.5576 | **−0.0428** |

| family | external recall, baseline | external recall, keyless |
|---|---|---|
| website | 0.6724 (388/577) | **0.9983 (576/577)** |
| hiring | 0.7738 (65/84) | **1.0000 (84/84)** |
| social | 1.0452 (185/177) | 1.0000 (177/177) |
| news | 0.1463 | 0.1363 |
| other | 0.5700 | 0.3760 |
| reviews | 1.3251 | 0.0991 (not scored) |
| identity / financials / roles | 0.0000 | 0.0000 (register-only) |

**Read this honestly.** The two families the project was actually fighting for
are closed: website 388 → 576 of 577 opportunities, hiring 65 → 84 of 84.
Against that, the Google exclusion removed 194 companies' worth of external
"other" facts and 8 social handles, so the external-only headline is
**flat (−0.04)**, not up. The all-claim proxy reads +1.69 because the register
facts every company already had now sit in a corpus that also has the web
facts. The official leaderboard's Recall maximum is 35.77/50, so the 49.99
all-claim figure is a proxy, not a score.

## What this says

The baseline already saturates five families (identity, accounts, people,
other and the news/activity floor). Exactly two families are below full
coverage, and they are the two the whole project has been pushing:

* **website: 388 of 577** — 189 companies in the union have a website fact we
  do not publish.
* **hiring: 65 of 84** — 19 companies in the union have a hiring fact we do
  not publish.

That is the whole remaining gap. Every connector added after the baseline
(registry-declared domain proof, the browser rescue of unreadable homepages,
the website-description text fallback, the public ATS feeds) is aimed at
these two numbers, and the comparison that counts is this scorer run over
both corpora.

## Reproducing

The scorer is deterministic: no timestamp, no unordered iteration, the same
inputs produce a byte-identical report.

```bash
# baseline (read-only copy from the dirty main checkout)
cp <main>/norhound-starter-kit/out/resume-20261104-final.contract-superset.jsonl .cache/baseline/
uv run python scripts/measure_family_recall.py \
  --envelopes .cache/baseline/resume-20261104-final.contract-superset.jsonl \
  --output out/measure-family-baseline.json

# new corpus
uv run python scripts/measure_family_recall.py \
  --envelopes out/run-full-2026-11-07/envelopes-final.jsonl \
  --output out/measure-family-new.json
```

## Files

- `scripts/measure_family_recall.py` — the scorer.
- `tests/test_measure_family_recall.py` — 15 tests: the opportunity counts and
  their scaling, one company counted once per family, the weighting, the
  reviews exclusion, the six groups, determinism, and the CLI.
- `out/measure-family-baseline.json` — the baseline report.
