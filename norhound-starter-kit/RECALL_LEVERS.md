# Where recall can still come from — measured, not guessed

All probes below were run on 16 Nov 2026 against the live sites, while the
2026-11-16 rerun was in flight.

## 1. The arithmetic of the six-field proxy

`scripts/measure_recall.py` scores six fields, each worth 8.33 of 50 points
(mean of the six × 50). Current values from
`out/run-fresh-20261115T073743Z/measure-final.json`:

| field | recall | points | headroom left |
|---|---|---|---|
| any_external | 1.000 | 8.33 | 0.00 |
| two_platforms | 0.994 | 8.28 | **0.05** |
| workforce_jobs | 0.954 | 7.95 | **0.38** |
| buzz_engagement | 1.000 | 8.33 | 0.00 |
| ratings_reviews | 0.032 | 0.27 | **8.07** |
| sentiment | 0.032 | 0.27 | **8.07** |

**16.1 of the 16.6 remaining points sit in two fields that read the same source
class.** Every other field is effectively maxed. So "increase recall" means
exactly one thing: find a ratings/reviews source with broad coverage.

## 2. Keyless rating sources — all probed, all dead

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

## 3. The one lever that works, and what it costs

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
  (0.5−0.032)/6×50 × 2 = **+7.8 proxy points** (33.4 → 41.2). At 0.7 it is
  +11.1.
- Cost of adopting it: it stops being a keyless entry. That is a policy
  decision, not a technical one.

## 4. What is not worth doing

- `workforce_jobs` has 0.38 points of headroom and `two_platforms` 0.05. The
  hiring family (50/84) would need 34 more companies with a real role card or
  apply action; the realistic keyless sources for that are Finn.no (vetoed: no
  org numbers, ToS) and NAV live search (HTTP 429 to unauthenticated bulk).
- Sentiment cannot rise independently: it is derived from the same rating rows.

## Recommendation

Recall is **structurally capped at ≈33.5/50** for a keyless entry. Two honest
paths:

1. **Stay keyless** — accept 33.4, and spend the remaining effort on UX (3.2 of
   8, the largest untouched pool: **+4.8 available**) and on the submission
   deliverable. Nothing else in recall will move.
2. **Add Google Places** — one key, ≈$0 within the monthly credit, identity by
   domain match, expected 33.4 → 41.2. Still short of the 65 qualification gate,
   but the single largest change available.

Both are defensible; mixing them is not. Enabling Places while still claiming
"no API key, no account" in the submission would be a false statement.

## 5. Why the six-field proxy is near-maxed but the official score is not

Measured on the shipped corpus (`out/run-fresh-20261115T073743Z/`, 1,000
envelopes, 105,772 claims):

| family | claims | share | companies |
|---|---|---|---|
| financials | 36,680 | 34.7% | 982 |
| identity | 25,563 | 24.2% | 1,000 |
| other (registry_update 16,062, sitemap 2,531, workforce_snapshot 1,486, subunit 1,165, group_child 1,291) | 22,913 | 21.7% | 1,000 |
| roles | 15,671 | 14.8% | 994 |
| **news** (dated_news) | **2,996** | 2.8% | 1,000 |
| website | 900 | 0.9% | 824 |
| **hiring** | **537** | 0.5% | ~500 |
| **social** | **416** | 0.4% | 416 |
| **reviews** | **96** | 0.1% | 32 |

Financials are already fully exploited: 7 figures × ~2.9 years × 982 companies,
every value straight from Regnskapsregisteret, so "add multi-year accounts" is
not a lever — it is already 34.7% of every claim we publish.

The proxy asks "does this company have *any* signal in this field", and answers
yes for 4 of 6 fields at 99–100%. The official score gave 12.89/50 = 25.8% on
the same corpus. The difference is **depth**: the proxy counts presence, the
graded score counts how many of the reference's items we reproduce. That is why
`workforce_jobs` reads 0.954 while only 537 real hiring claims exist, and why
`news` is 3 items per company against a reference that can hold far more.

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
2. **Publish real role cards, not `/karriere` pages.** 537 hiring claims for
   1,000 companies is thin, and the reviewer's rule is explicit: a bare careers
   page must emit `careers_page`, never `hiring: true`. The NAV index is the
   only keyless source of real adverts; widening its window from 183 days, or
   matching adverts by municipality + name when the employer number is missing,
   adds claims without weakening identity.
3. **Social handles from first-party pages.** 416 claims. The extractor already
   reads `sameAs` from JSON-LD on the homepage; it only visits the homepage.
   Following one contact/about page per site would roughly double this.
4. **Ratings.** Only Google Places moves this; see sections 2–3 above.

None of 1–3 changes a source, a right, or a cost. All three are depth on pages
we already fetch, which is exactly where the graded score is losing points.
