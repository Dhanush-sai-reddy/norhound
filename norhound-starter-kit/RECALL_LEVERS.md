# Where recall can still come from — measured, not guessed

All probes below were run on 16 Nov 2026 against the live sites, while the
2026-11-16 rerun was in flight.

## 1. The arithmetic of the six-field proxy

`scripts/measure_recall.py` scores six fields, each worth 8.33 of 50 points
(mean of the six × 50). Values below are from the shipped run
`out/run-fresh-20261116T144704Z/measure-final.json`:

| field | recall | points | headroom left |
|---|---|---|---|
| any_external | 0.994 | 8.28 | 0.05 |
| two_platforms | 0.627 | 5.22 | **3.11** |
| workforce_jobs | 0.013 | 0.11 | **8.22** |
| buzz_engagement | 0.994 | 8.28 | 0.05 |
| ratings_reviews | 0.032 | 0.27 | **8.07** |
| sentiment | 0.032 | 0.27 | **8.07** |

**27.6 of the 50 points remain unearned.** 16.1 of them are in
`ratings_reviews` + `sentiment`, which read the same source class; 8.2 are in
`workforce_jobs`, where the constraint is the number of real adverts a keyless
source holds; 3.11 are in `two_platforms`, where 367 companies have exactly one
independent source.

Three definitions were corrected on 16 Nov 2026 because the original ones were
tautologies:

- `workforce_jobs` counted `workforce_snapshot` (headcount), which made it read
  0.954 and the proxy 33.43. Headcount is measured separately; only
  `job_posting` counts as hiring.
- `any_external` and `two_platforms` counted the register (`brreg`), which every
  profiled company has. They are now defined over non-register platforms:
  one independent source, and two independent sources.
- `buzz_engagement` counted Brønnøysund announcements ("Godkjente årsregnskap"),
  which every filer has. Registry rows are excluded; buzz means a third-party
  profile, mention or post.

`scripts/evaluate_external_footprint.py` now imports the same definitions, so
the audit report and the recall report can never print different coverage
numbers for the same corpus.

Headcount (`workforce_snapshot`) is still measured and reported beside the six
fields: **0.575** in this run (the register's own headcount plus Purehelp; the
annual-report OCR stage is off by default and earns 0 points anyway). It is a
real fact, not a hiring signal.

### The annual-report PDF/OCR stage scores nothing — measured 16 Nov 2026

`run_annual_report_workforce_connector.py` is the longest stage in the chain
(~2 h 20 min for 1,000 companies, `SLOW_STAGES=1` only) and earns **0** of the
50 recall points. The 15 Nov corpus, measured:

- 585 accepted `workforce_snapshot` facts, **585/585 `ocr_used: true`** — none
  exist without tesseract.
- 382 of the 585 are `0.00` full-time-equivalent filings (span
  `"Antall årsverk i regnskapsåret 0.00"`). They are real filings, not parse
  failures: **0 of 382** are contradicted by a positive registry or Purehelp
  figure.
- 379 companies have no other headcount source, but the summary and viewer both
  read `profile["employees"]` (the registry field), and the connector skips
  every company that already has `registry.antallAnsatte`. So it changes
  **0** summaries and **0** viewer columns.
- Its only visible effect is 585 observation cards in the Evidence tab.

It is off by default (`scripts/run_full_batch.sh:124`). Do not turn it back on
to chase recall; the 45-minute daily budget cannot afford it either way.

## 2. Stage cost against the daily budget — measured 16 Nov 2026

The daily limits are **45 minutes, 2,000 outbound requests and $10 per batch of
100 companies**. The 1,000-company corpus therefore has a 7 h 30 m and 20,000
request ceiling. Stage 5 wall times below are the deltas between the
`batch.*.jsonl` mtimes of `out/run-fresh-20261115T073743Z/`; every stage is a
separate process that writes its file when it finishes.

| stage 5 connector | wall time | scored recall |
|---|---|---|
| activity, news, contacts, site description, substructure | ~5 s | 0 (feeds the viewer only) |
| sitemap lastmod | 2.6 min | 0 (`any_external` already 0.994) |
| registry updates | 16.7 min | 0 (feeds the Changes tab) |
| Wikidata | 0.9 s | `two_platforms` only if the company is in the 67-org index |
| Purehelp headcount | 2.3 min | 0 (headcount is not hiring) |
| NAV job feed | 18 s | +0.13 (13 companies) |
| company-site jobs | 12.4 min | 0 (emits `careers_page`; a discovered link is not a role card) |
| ATS role cards | 12.8 min | +0.02 (2 companies no other connector found) |
| Google News RSS | 2.2 min | 0 (`buzz_engagement` already 0.994) |
| Kunngjøringer | 3.0 min | 0 (registry announcements are not buzz) |
| Fagfolkguiden | 45.6 min | +0.54 (32 companies, both rating fields) |
| **annual-report PDF/OCR** | **3 h 22 m** | **0** |

Stage 5 totals **5 h 01 m** with the OCR stage and **1 h 39 m** without it. The
whole 1,000-company run took **10.7 h** wall clock (13:16 to 23:55), which is
**64 min per 100 companies** — 1.4× the stated budget. Removing the OCR stage
alone brings it to **44 min per 100**, inside the budget, which is the reason it
stays opt-in rather than the missing points.

## 3. Keyless rating sources — all probed, all dead

`REVIEW_SIGNALS = {"review", "review_summary", "place_summary"}`
(`scripts/measure_recall.py:53`), so a source only helps if it yields one of
those signal types with exact-entity proof.

| source | probe | result |
|---|---|---|
| Trustpilot (direct) | ran the existing `scripts/run_trustpilot_reviews_connector.py` on 40 real profiles | **0 observations, 40 errors** — `www.trustpilot.com` and `no.trustpilot.com` both answer **HTTP 403** to any non-browser request |
| Gulesider | `https://www.gulesider.no/` and `/sok?what=…` | **HTTP 403**; the existing connector also depends on a `site:gulesider.no` Google search, which is excluded by `DEFAULT_EXCLUDED_HOSTS` |
| Proff.no | `https://www.proff.no/` | **HTTP 403** |
| Bygghjemme | `https://www.bygghjemme.no/` | **HTTP 403** |
| 1881.no | `https://www.1881.no/` | **HTTP 200**, but a JavaScript app: no search form action and no rating markup in the served HTML, so nothing extractable without reverse-engineering their private API |
| Review widgets on company sites | fetched 24 registry-proved homepages (17 responded), grepped for `trustpilot`, `trustbox`, `businessunit`, `reviews.io`, `yotpo`, `judge.me` | **0 of 17** — Norwegian SMB sites do not embed third-party review widgets |
| Fagfolkguiden | already wired | 32 of 1,000 companies have a page at all — that is the 0.032 |

That is the whole keyless landscape for ratings. There is no fifth option: the
aggregators that hold Norwegian ratings either block non-browser clients or
require a key.

## 4. The one lever that works, and what it costs

`scripts/run_google_places_connector.py` is already written, already wired to
`--google-places`, and already gated on `GOOGLE_PLACES_KEY`. It proves identity
by **website domain match** (`google_places_website_domain_match`), which is the
strongest non-registry proof we have — restrict it to domain match only and drop
the fuzzy name+address fallback to keep precision at 1.0.

- Cost: Places API (New) Text Search ≈ $32 / 1,000 and Place Details ≈ $17 /
  1,000 → **≈ $49 per 1,000 companies**, i.e. $4.90 per 100, inside the
  challenge's $10/100 cap. Google's $200 monthly credit covers ~4 such runs, so
  the marginal cash cost of one run is **$0**.
- Expected gain: Google has a rated listing for a large share of Norwegian
  companies. At 0.5 coverage on both fields that is
  (0.5−0.032)/6×50 × 2 = **+7.8 proxy points** (22.4 → 30.2). At 0.7 it is
  +11.1 (→ 33.5).
- Cost of adopting it: it stops being a keyless entry. That is a policy
  decision, not a technical one.

## 5. What is not worth doing

- `two_platforms` has 3.11 points of headroom but 367 of the 373 missing
  companies have **only** Purehelp, no verified website and **no Wikidata item**
  (the index holds 67 organisations, none of them in that 367). A second
  independent source for them does not exist keylessly.
- `workforce_jobs` has 8.2 points of headroom and is limited by the number of
  real adverts a keyless source holds. The hiring family needs a role card or an
  apply action; the realistic keyless sources are Finn.no (vetoed: no org
  numbers, ToS) and NAV live search (HTTP 429 to unauthenticated bulk). NAV's
  static feed is already wired and reaches 13 companies.
- Sentiment cannot rise independently: it is derived from the same rating rows.

## Recommendation

Recall is **structurally capped at ≈22.4/50** for a keyless entry. Two honest
paths:

1. **Stay keyless** — accept 22.4, and spend the remaining effort on the
   submission deliverable. Nothing else in recall will move without a new
   source.
2. **Add Google Places** — one key, ≈$0 within the monthly credit, identity by
   domain match, expected 22.4 → 30.2. Still short of the 65 qualification gate,
   but the single largest change available.

Both are defensible; mixing them is not. Enabling Places while still claiming
"no API key, no account" in the submission would be a false statement.

## 6. Why the six-field proxy is near-maxed but per-company depth is not

Measured on the shipped corpus (`out/submission/`, 1,000 envelopes, 105,204
claims):

| family | claims | share | companies |
|---|---|---|---|
| financials | 36,680 | 34.9% | 994 |
| identity | 25,566 | 24.3% | 1,000 |
| other (registry_update 16,050, sitemap 2,513, workforce_snapshot, subunit 1,165, group_child 1,291) | 22,244 | 21.1% | 999 |
| roles | 15,671 | 14.9% | 994 |
| **news** (dated_news) | **3,050** | 2.9% | 1,000 |
| website | 908 | 0.9% | 604 |
| **hiring** | **572** | 0.5% | 49 |
| **social** | **417** | 0.4% | 209 |
| **reviews** | **96** | 0.1% | 32 |

Financials are already fully exploited: 7 figures × ~2.9 years × 994 companies,
every value straight from Regnskapsregisteret, so "add multi-year accounts" is
not a lever — it is already 34.9% of every claim we publish.

The proxy asks "does this company have *any* signal in this field", and answers
yes for 4 of 6 fields at 99–100%. That is not the same question the graded
metric asks: the proxy counts presence, the graded metric counts how many of a
reference collection's items we reproduce. The census above makes the depth
problem concrete — only 572 hiring claims exist across 1,000 companies (49
companies have a hiring-family claim, of which 13 have a real role card and 36
only a careers page), and `news` is ~3 items per company against a reference
that can hold far more. Presence is solved; per-company depth is not.

### Depth levers, in the order they are worth doing

1. **Retain a bounded first-party body for news. — DONE (2026-11-16)**
   `extract_company_site_news.py` already supported `--fetch-dates` (keep the
   first 5,000 characters, mine the publication date from the page body), but
   the pipeline never passed the flag. Shipped corpus: 933 activity rows, median
   `evidence_span` **77 characters**, 8 rows with a mined date.
   Measured on 20 real profiles, same companies both ways:

   | | observations | dated | bodies retained |
   |---|---|---|---|
   | without the flag | 6 | 0 | 0 |
   | with `--fetch-dates` | 6 | **3** | **6** |

   Wired into `scripts/run_external_pipeline.py`; three tests pin it. One extra
   request per company that already has an activity page, no key, no new
   source.
2. **Publish real role cards, not `/karriere` pages. — DONE (2026-11-16)**
   The reviewerer's rule is explicit: a bare careers page must emit
   `careers_page`, never `hiring: true`. The company-site jobs connector was
   violating it: it emitted `job_posting` for every link it *discovered* on a
   careers page without ever fetching the posting, so "Digitalt testament" and
   "Marketing" were published as job titles on 38 companies. It now emits
   `careers_page` + `careers_url`, and `jobs_feed_discovery` is no longer a
   trusted role strategy, so `workforce_jobs` fell from an inflated 0.051 to
   the honest **0.013** (13 companies with a real role card: 13 from NAV's
   official feed, 3 from public ATS boards).
   The remaining lever is the NAV index — it is the only keyless source of real
   adverts. Widening its window from 183 days, or matching adverts by
   municipality + name when the employer number is missing, adds claims without
   weakening identity.
3. **Social handles from first-party pages.** 417 claims, 209 companies. The
   extractor already reads `sameAs` from JSON-LD on the homepage; it only visits
   the homepage. Following one contact/about page per site would roughly double
   this.
4. **Ratings.** Only Google Places moves this; see sections 2–3 above.

None of 1–3 changes a source, a right, or a cost. All three are depth on pages
we already fetch, which is exactly where the graded score is losing points.
