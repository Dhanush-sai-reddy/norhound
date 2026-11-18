# Official-run rehearsal — 17–18 November 2026

Evidence for the Signalpost submission: a full 1,000-company run through the
**evaluator's own command**, with every number below measured by the run
itself (no estimate, no hand-copy).

- Run id: `fresh-20261117T213100Z`
- Run directory: `norhound-starter-kit/out/run-fresh-20261117T213100Z/`
- Promoted package: `norhound-starter-kit/out/submission/`
- Machine-readable report: `out/submission/official-run-report.json`
- Requirements this run is checked against:
  [`signalpost-requirements-2026-11-17.md`](signalpost-requirements-2026-11-17.md)

---

## 1. The command an evaluator runs

```bash
cd norhound-starter-kit
scripts/run_official_batch.sh \
  --batch out/run-fresh-20261118T185829Z/entry.jsonl \
  --run-id fresh-20261117T213100Z \
  --previous-envelopes out/submission/envelopes.jsonl
```

The same script without `--previous-envelopes` is the plain official run. The
wrapper does, in order: read the supplied batch → prepare the frozen source
indexes → run the 14-stage pipeline over the batch → attach the refresh
comparison → rebuild the summaries over the refreshed envelopes → rebuild the
viewer → write the run report.

The summary rebuild is not cosmetic. The pipeline builds the summaries before
the refresh stage attaches the change records, so a summary built earlier says
"no prior version to compare against" while the envelope carries the detected
changes. The rubric asks the summary to explain "the company, changes and
unknowns", so the command rebuilds the summaries over the refreshed envelopes:
126 of the 1,000 summaries now state what changed and the source that proves
it.

No API key, no login, no paid account, no model provider. **External cost: $0.**

### Frozen indexes used

| index | state | note |
|---|---|---|
| `data/nav-job-index.jsonl` | rebuilt 17 Nov 2026 19:32 UTC, parents resolved 21:25 UTC | 9,432 postings, 3,384 parent enhets, 3 postings dropped (unresolved parent). A rebuilt index **must** be re-keyed with `--resolve-parents`, otherwise postings collapse onto the sub-unit instead of the legal entity. |
| `data/wikidata-index.jsonl` | committed | 67 organisations |
| `data/registry-domain-unique.jsonl.gz` | committed | sole-declarer domain index |

`--rebuild-indexes` rebuilds the NAV and Wikidata indexes from their live
sources; the rehearsal used the committed copies because they had been rebuilt
and re-verified on 17 Nov.

---

## 2. What the run produced

| measurement | value |
|---|---|
| organisations in | 1,000 |
| terminal envelopes out | **1,000** (one per input) |
| observations re-verified | 31,804 |
| observations published | 31,778 |
| claims | 105,164 |
| evidence records | 35,314 |
| summaries | 1,000 / 1,000 deterministic |
| runtime | **117.7 min** (7,059,204 ms) = **11.8 min per 100 companies** |
| outbound requests | **21,159** (measured) |
| third-party cost | **$0** |
| entity precision | **1.0** |
| wrong-company publications | **0** |
| unsupported publications | **0** |

Request counting is interpreter-level (`sitecustomize.py`): every subprocess of
the run is counted, and only the host, method and status are recorded — no URL,
no payload. The one exception is the headless-browser rescue stage, whose
requests come from the browser process rather than Python; it is reported as
page counts instead (110 pages rescued of 171 eligible).

Busiest hosts: `data.brreg.no` 6,989 · `www.fagfolkguiden.no` 1,007 ·
`purehelp.no` 1,000 · `news.google.com` 1,000 · `w2.brreg.no` 1,000.

---

## 3. Recall and evidence

### Six-field recall proxy (`scripts/measure_recall.py`)

`mean(any_external, two_platforms, workforce_jobs, ratings_reviews,
buzz_engagement, sentiment) × 50` = **22.3833 / 50**

| field | recall | points |
|---|---|---|
| any_external | 0.994 | 8.28 |
| two_platforms | 0.620 | 5.17 |
| workforce_jobs | 0.014 | 0.12 |
| ratings_reviews | 0.032 | 0.27 |
| buzz_engagement | 0.994 | 8.28 |
| sentiment | 0.032 | 0.27 |

`workforce_snapshot` (headcount, 0.575) is measured and reported **beside** the
six fields, never inside them: headcount is not evidence of hiring.

This is **our proxy, not an official score.** The official recall metric is
measured by the organisers against the union of what all participants found.

### Company recall per official fact family (`scripts/measure_family_recall.py`)

| family | covered / opportunities | recall |
|---|---|---|
| financials | 994 / 1,000 | 0.994 |
| hiring | 49 / 84 | 0.583 |
| identity | 1,000 / 1,000 | 1.000 |
| news | 1,000 / 998 | 1.000 |
| other | 1,000 / 1,000 | 1.000 |
| reviews | 32 / 323 | 0.099 |
| roles | 994 / 1,000 | 0.994 |
| social | 204 / 177 | 1.000 |
| website | 597 / 577 | 1.000 |

Hiring split: **14 companies with a real role card** (every one from NAV's
official feed), 35 with a `careers_page` signal only. A careers-page link is
never published as `hiring: true`.

---

## 4. Refresh and idempotency

`scripts/attach_refresh_changes.py` compares the new envelopes with the
previous snapshot, keyed by a content hash.

| measurement | value |
|---|---|
| envelopes compared | 1,000 |
| material changes detected | 252 |
| companies with changes | 126 |
| summaries that state the change and its source | **126** (of 1,000) |
| changes already recorded (re-run over the refreshed corpus) | 252 |
| new changes on the re-run | **0** |

A second pass over the refreshed corpus detected **0** new changes and
preserved all 252 recorded ones: the same input produces the same output and
the earlier evidence behind every recorded change is kept.

---

## 5. 100-company smoke test

`out/submission/smoke-100/smoke-report.json`

| measurement | value |
|---|---|
| requested | 100 |
| returned | **100** |
| complete | **true** |
| missing | none |
| duplicated | none |
| claims | 10,290 |
| evidence records | 3,383 |

---

## 6. Qualification gates, checked

| gate (current brief, 17 Nov 2026) | status | evidence |
|---|---|---|
| ≥ 65 / 100 overall | not ours to award — no official score issued | — |
| ≥ 95 % precision | **pass** — entity precision 1.0 over 31,778 published observations | `eval.json` |
| no material wrong-company publication | **pass** — 0 | `eval.json` |
| no fabricated financial values | **pass** — every financial claim carries a registry source URL, retrieval time and reporting period | `evidence` records |
| exactly one terminal envelope per company | **pass** — 1,000 in, 1,000 out | `official-run-report.json` |
| explicit availability states | **pass** — `available`, `not_available`, `blocked`, `not_applicable`, `ambiguous`, `failed`; never zero for absence | envelopes |
| idempotent refresh, history preserved | **pass** — 0 new on re-run, 252 preserved | §4 |
| claim-level URL, retrieval time, reporting period | **pass** — 35,314 evidence records | `evidence` records |
| reproducible setup, pinned deps, one command | **pass** — `scripts/run_official_batch.sh --batch organisations.jsonl` | `README.md` |

---

## 7. Known limitations (measured, not guessed)

1. **Ratings and sentiment are capped at 0.032.** Every keyless ratings source
   was probed on 16 Nov 2026: Trustpilot, Gulesider, Proff.no and Bygghjemme
   answer HTTP 403 to any non-browser request, 1881.no serves no rating markup
   in its HTML, and 0 of 17 checked company homepages embed a review widget.
   Fagfolkguiden is the only directory that answers, and only 32 of the 323
   companies with a rating have a page there.
2. **Hiring is capped by the keyless advert sources.** NAV's official feed
   reaches 14 companies. The public ATS boards find postings for 3 more
   companies, but the identity gate rejects them: the posting pages sit on
   third-party boards and the frozen site evidence cannot re-derive the board
   link, so the fail-safe rule keeps them out. Finn.no is excluded (no
   organisation numbers, and its terms of service forbid it); NAV's live search
   answers HTTP 429 to unauthenticated bulk.
3. **374 companies have exactly one source outside the register** — the company
   directory (Purehelp / Fagfolkguiden). None of them has a verified website
   or a Wikidata item, which is why `two_platforms` reads 0.620.

The measurements behind these limits are in
[`RECALL_LEVERS.md`](../../RECALL_LEVERS.md).

---

## 8. Reproducing this run

```bash
cd norhound-starter-kit
uv run python -m unittest discover -s tests          # 593 tests, 8 skipped
scripts/run_official_batch.sh --batch organisations.jsonl
```

The promoted artifacts in `out/submission/` are the output of exactly that
path, produced on 17–18 Nov 2026.
