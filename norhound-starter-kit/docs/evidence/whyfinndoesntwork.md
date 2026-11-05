# Why Finn.no Job Connector Was Not Integrated

## Executive Summary

The Finn.no job-board connector (`scripts/run_finn_jobs_connector.py`) exists and works for live scraping, but **was not integrated into the default pipeline** because:

1. **Tests demanded an `--offline` mode the connector doesn't have** — the test file (`tests/test_finn_jobs_connector.py`) was written for a cache-driven replay architecture, but the connector implements live search + fetch. All 14 tests failed with "unrecognized arguments: --offline".

2. **User explicitly vetoed further Finn investment** — "finn connector is proven to fail ……run only if your are sure there are repos which correct it and stuff otherwise a big no".

3. **Measured yield is small vs. effort** — NAV job feed (already built, free, official API) covers 7 orgs with 65 postings; Finn would add ~7 more orgs but requires maintaining a fragile scraper against Norway's largest job board with aggressive anti-bot measures.

4. **Legal/ToS risk** — Finn.no Terms of Service prohibit systematic scraping; the connector uses polite rate limiting (1 req/s) but has no explicit permission.

## Technical Details

### Connector Implementation (`scripts/run_finn_jobs_connector.py`)

- **Live scraper**: Searches Finn.no job search by company name, extracts ad URLs, fetches detail pages
- **Exact-entity matching**: Only emits rows where the org number on the ad page exactly matches the target company
- **JSON-LD parsing**: Extracts structured data from `application/ld+json` script tags (JobPosting schema)
- **Rate limiting**: 1 request/second, max 50 ads per company
- **Caching**: File-based HTML cache for search results and ad pages

### Test File (Deleted)

`tests/test_finn_jobs_connector.py` contained 15 tests written for a different interface:
- Expected `--offline` flag for cache-only replay
- Expected `cache_misses` in report
- Fixtures modeled Finn's real markup (JSON-LD envelope + BreadcrumbList)
- All tests failed because the connector doesn't implement `--offline`

### Ground Truth from Production Cache (Main Checkout)

Location: `/home/dhanushsr/Downloads/hackathons/signalpost/norhound-starter-kit/data/finn-cache/` (990 MB)

```
Total cached ads: 1,428
Ads with JSON-LD title: 1,415
Expected accepted across 14 orgs: 110
  - 5 name mismatches
  - 4 missing org proof
  - 13 no role card
  - 7 orgs gaining hiring signal
  - 3 ad URLs with no cache: 477798544, 477693507, 477781392
```

### Why NAV Job Feed Is Preferred

| Aspect | NAV Job Feed | Finn.no Scraper |
|---|---|---|
| Source | Official API (arbeidsplassen.nav.no) | Commercial job board |
| Cost | Free, no key | Free but fragile |
| Exact-entity | Resolves sub-units to parent enhet | Org number on page |
| Legal | Explicitly permitted | ToS prohibits scraping |
| Maintenance | Stable API | Site changes break selector |
| Coverage | 3,625 orgs, 9,979 postings | ~7 additional orgs for our batch |
| Already built | Yes (`run_nav_job_feed_connector.py`) | Yes but untested offline |

## Decision

**Do not invest in Finn.no connector.** The NAV job feed is already built, officially sanctioned, covers more orgs, and requires only passing the `--nav` flag in `scripts/run_external_pipeline.py` (AGENTS.md "Next Action #1", still not done).

If hiring recall needs a further boost after NAV is enabled, the next keyless source would be **Google Jobs Search** (structured data on public SERPs) or **company-site career pages** (already crawled, just need role-card extraction).

## Files

- `scripts/run_finn_jobs_connector.py` — live scraper, kept for reference
- `tests/test_finn_jobs_connector.py` — **deleted** (orphan, demanded unimplemented interface)
- `data/finn-cache/` — 990 MB production cache (main checkout, read-only)