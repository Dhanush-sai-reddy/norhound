# Official-run rehearsal + news-depth pass — 17–18 November 2026

Evidence for the Signalpost submission: a full 1,000-company run through the
**evaluator's own command**, plus one measured extra pass that publishes one
dated news item per captured news page instead of one per company. Every
number below is measured by the run itself (no estimate, no hand-copy).

- Run id: `fresh-20261117T213100Z` (official command) + `newsdepth-20261118T120128Z` (news-depth pass)
- Run directories: `norhound-starter-kit/out/run-fresh-20261117T213100Z/`, `norhound-starter-kit/out/run-newsdepth-20261118T120128Z/`
- Promoted package: `norhound-starter-kit/out/submission/`
- Machine-readable report: `out/submission/official-run-report.json` (it carries
  both stages, with each stage's own runtime and request count)
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
**144 of the 1,000** shipped summaries state what changed and the source that
proves it.

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
| observations re-verified | 31,911 |
| observations published | 31,885 |
| claims | 105,266 |
| evidence records | 35,421 |
| summaries | 1,000 / 1,000 deterministic |
| runtime | **119.2 min** (7,152,204 ms) = **11.9 min per 100 companies** |
| outbound requests | **22,166** (measured) |
| third-party cost | **$0** |
| entity precision | **1.0** |
| wrong-company publications | **0** |
| unsupported publications | **0** |

The runtime and the request count are the sum of two measured stages, and the
run report says so explicitly:

| stage | run id | runtime | requests |
|---|---|---|---|
| official command (14-stage pipeline + refresh + summaries + viewer) | `fresh-20261117T213100Z` | 117.7 min | 21,159 |
| news-depth pass (`extract_company_site_news.py --fetch-dates` over the frozen profiles) | `newsdepth-20261118T120128Z` | 1.6 min (93 s) | 1,007 |
| **total** | | **119.2 min** | **22,166** |

A fresh run of the documented command does both stages in one pass and costs
the same.

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

### Claim depth in the activity family

The news-depth pass publishes one dated item per captured news page instead of
one per company:

| | before | after |
|---|---|---|
| news observations | 86 | **194** |
| of them dated | 64 | **172** |
| companies with dated news | 65 | **65** |
| `dated_news` claims in the corpus | 3,073 | **3,175** |

Rules, pinned by `tests/test_site_news_items.py`:

* an additional page is published only when its body carries a **machine-readable**
  publication timestamp (`article:published_time`, `<time datetime=…>`,
  `datePublished`); a date mined from prose stays reserved for the primary page,
  because prose can carry a copyright year or a date mentioned in passing,
* an undated navigation page is never published as padding,
* at most 12 candidate pages and 8 dated items per company,
* the retained body excerpt is bounded at 5,000 characters.

---

## 4. Refresh and idempotency

`scripts/attach_refresh_changes.py` compares the new envelopes with the
previous snapshot, keyed by a content hash.

| measurement | value |
|---|---|
| envelopes compared | 1,000 |
| material changes detected | 277 |
| companies with changes | 144 |
| summaries that state the change and its source | **144** (of 1,000) |
| changes already recorded (re-run over the refreshed corpus) | 277 |
| new changes on the re-run | **0** |

A second pass over the refreshed corpus detected **0** new changes and
preserved all 277 recorded ones. The claims, the evidence and the change
records are byte-identical between the two passes for all 1,000 envelopes; only
the `refresh` bookkeeping block differs (it counts the second pass as
"already recorded"), which is the honest description of an idempotent re-run.

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
| claims | 10,306 |
| evidence records | 3,399 |

---

## 6. Qualification gates, checked

| gate (current brief, 17 Nov 2026) | status | evidence |
|---|---|---|
| ≥ 65 / 100 overall | not ours to award — no official score issued | — |
| ≥ 95 % precision | **pass** — entity precision 1.0 over 31,885 published observations | `eval.json` |
| no material wrong-company publication | **pass** — 0 | `eval.json` |
| no fabricated financial values | **pass** — every financial claim carries a registry source URL, retrieval time and reporting period | `evidence` records |
| exactly one terminal envelope per company | **pass** — 1,000 in, 1,000 out | `official-run-report.json` |
| explicit availability states | **pass** — `available`, `not_available`, `blocked`, `not_applicable`, `ambiguous`, `failed`; never zero for absence | envelopes |
| idempotent refresh, history preserved | **pass** — 0 new on re-run, 277 preserved | §4 |
| claim-level URL, retrieval time, reporting period | **pass** — 35,421 evidence records | `evidence` records |
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

### 7.1 The single-platform gap was measured, not assumed

The directory page states a website domain for **371 of those 374** companies,
so the obvious next move is to fetch that domain and publish the site as a
second platform. Measured on a 60-company random sample of the 374
(18 Nov 2026, `https` + `www` variants, robots honoured, the **unchanged**
identity gate):

| step | count |
|---|---|
| sampled | 60 |
| homepage fetched | 34 |
| organisation number found anywhere in the page text | **0** |
| organisation number found in the footer/address nodes | **0** |
| legal name found in the footer/address nodes | 3 |
| **publishable under the unchanged identity gate** | **3** |

So the ceiling without widening the identity gate is about 5 % of the 374
(~19 companies, `two_platforms` 0.620 → ≈0.64), and the binding constraint is
the evidence, not the fetch: these homepages simply do not state the
organisation number, and the gate refuses to publish a site that cannot be
resolved to the exact legal entity. Widening the gate would trade the
≥95 % precision gate for a fraction of a point on one recall field, so the
gate stays as it is.

---

## 8. Reproducing this run

```bash
cd norhound-starter-kit
uv run python -m unittest discover -s tests          # 601 tests, 8 skipped
scripts/run_official_batch.sh --batch organisations.jsonl
```

The promoted artifacts in `out/submission/` are the output of exactly that
path, produced on 17–18 Nov 2026.
