# Dead Ends — Sources Tested and Why They Cannot Be Used

Every source below was tested live on 5–6 Oct 2026 from the working environment
(Norway-routed and plain HTTP). Each entry records the exact failure mode so no
one wastes time re-trying them. "Dead" here means: **not usable for the
evaluator's live one-command run, and/or not legally/practically matchable to
an exact organisasjonsnummer.**

## Hard-blocked by bot protection (Cloudflare / WAF) — confirmed 403 or challenge

| Source | Test | Result | Why it matters |
|---|---|---|---|
| **Trustpilot** `trustpilot.com/review/<domain>` | plain urllib → **403** (all 10/10 companies); Playwright Chromium → **Cloudflare "Verifying Connection"** interstitial | Blocked at layer 7 for both plain HTTP and headless browser. Needs residential proxy farm. Also: Trustpilot ToS disallows scraping; reviewer explicitly disallows unofficial clients as sole evidence. |
| **Proff.no** search + profile | plain urllib → **403**; Playwright Chromium → **403 "request could not be satisfied"** | Cloudflare block. Only usable via pre-computed cache (60 companies scraped earlier through Apify were reused) or the paid Apify Actor with proxies. |
| **Gulesider.no** | plain urllib → **403**; Apify `crawlerbros/gulesider-scraper` → ran 7+ min, **0 items with org numbers** (actor does not fetch `organizationNumber` even with fetchDetails) | Cloudflare + the available actor's output lacks org numbers → **no exact-entity matching possible**. Dead on both axes. |
| **Purehelp.no** | plain urllib → **200 but body is the Cloudflare "Just a moment…" challenge page** (5.5KB JS shell; zero data; no org number in DOM) | Fake 200. SPA behind Cloudflare — data never loads without solving the challenge. |
| **1881.no** | search + profile URL guesses → **404 on every tested pattern** | No working URL pattern found that exposes company data; presumed SPA/blocked. |

## Reachable but structurally useless for this task

| Source | Test | Result |
|---|---|---|
| **Finn.no jobs** (`abotapi/finn-no-jobs-scraper` Apify Actor) | Ran on 50 companies → 223 job postings returned, **zero org numbers in output** (schema has no org field; employer names only) | Our batch is small local companies (housing co-ops, local consultancies) that don't post on Finn.no; name-only matching ≠ exact entity. Wasted $0.06, aborted. |
| **Instagram** (`apify/instagram-profile-scraper`) | Connector fetched 795 company websites, found 497 candidate IG links; Actor calls → **206 errors, 1 observation** | Actor failing at scale (rate limits/oganizational restrictions). Instagram scraping also violates platform ToS → unusable as sole published evidence anyway. |
| **Google Maps via Apify `memo23` scraper** | Works (600 obs / 31 companies) BUT **only ~30 reviews per 50-company batch regardless of maxItems** — actor caps results | Superseded by Google Places API (New) with official key. Kept as fallback: `out/gmaps-reviews.jsonl`. |
| **NewsAPI.org key** | Acquired but **free tier = 2,000 req/day, no Norwegian local coverage** | Small local firms are not in international news indices. RSS feeds of NRK/E24/Dagbladet/Nettavisen are free and equivalent → no key needed. |
| **NAV pam-stilling-feed legacy endpoint** | `pam-api.nav.no/public-feed/v2/events` → **404** | Wrong path; working search API is `arbeidsplassen.nav.no/stillinger/api/search` (200 ✅). Already covered by `run_nav_job_feed_connector.py`. |

## Working sources (kept, in pipeline)

| Source | Status | Notes |
|---|---|---|
| BRREG Enhetsregisteret / Regnskapsregisteret / virksomhet.brreg.no | ✅ 200 | Core identity + financials + workforce snapshot |
| Company websites (deep crawl, 24 priority links) | ✅ | Social handles, jobs, news, descriptions |
| Fagfolkguiden `/bedrift/<orgnr>` | ✅ direct HTTP 200 | Embedded Google aggregate rating + sentiment |
| NAV arbeidsplassen search API | ✅ 200 | Jobs with org-number resolution via feed index |
| Wikidata SPARQL | ✅ | Profiles/handles for larger companies |
| E24 / NRK / Dagbladet / Nettavisen RSS | ✅ 200 | Dated activity/news with retained body text |
| **Google Places API (New)** | ✅ verified 5 Oct 2026 | Text search → place details; **exact match via website domain**; rating, review count, review texts. Key: `GOOGLE_PLACES_KEY` env / `.env` |

## Rule distilled

A source is usable for published claims only if **all three** hold:

1. **Reachable** without solving a bot challenge from a clean IP (200 with real content, not a challenge shell).
2. **Matchable** to the exact organisasjonsnummer — via org number on page/API, or exact website-domain equality.
3. **Rights-clean** — permitted public page or official API; platform-restricted scrapes (LinkedIn/Instagram/Meta/Glassdoor/Indeed) may not be sole evidence.

Everything in the top two tables fails at least one rule.
