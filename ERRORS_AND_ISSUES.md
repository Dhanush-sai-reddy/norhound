# Signalpost Hackathon - Errors & Issues Log
## For Gemini / Next Session Reference

---

## 🔴 CRITICAL ERRORS (Blocking Qualification)

### 1. Gulesider Scraper - BROKEN
**Actor:** `crawlerbros/gulesider-scraper`
**Issue:** Actor completely ignores `companyInclude` parameter, defaults to searching "pizza" in Oslo
- Tested 4 times with different inputs - ALL ignored `companyInclude`
- Returns pizza restaurants instead of target companies
- **Status:** UNFIXABLE - Actor bug
- **Impact:** Cannot get ratings/reviews for our 1000 companies

### 2. Jobs Extractor - BROKEN IN EVAL
**Script:** `scripts/extract_company_site_jobs.py`
**Issue:** 
- Works in isolation (finds 29 companies with 152 job postings on 50 test companies)
- **BUT returns 0 jobs in full eval pipeline** - 0 companies with job_posting in final eval
- Root cause: Jobs found on company sites but not making it to final eval (filter/pipeline issue)
- Companies with career pages found: 29/50 test, 0 in eval

### 3. Gulesider Actor - IGNORES `companyInclude`
**Actor:** `crawlerbros/gulesider-scraper`
**Issue:** Actor completely ignores `companyInclude` parameter
- Tested 4 times with `companyInclude: ["EQUINOR ASA", ...]`
- **Always** searches "pizza" in Oslo instead
- Returns pizza restaurants, not target companies
- **UNFIXABLE** - Actor bug

### 4. Multi-source Jobs API - No Org Numbers on LinkedIn
**Actor:** `yearly_register/norway-jobs-search-api`
**Issue:** Returns jobs from LinkedIn/Jobbnorge/NAV but **LinkedIn results have NO org numbers**
- `employerOrgNumber: null` for LinkedIn results
- Only NAV/Jobbnorge results have org numbers
- Cannot verify exact entity for LinkedIn jobs

### 5. Gulesider Ratings Coverage
- Only 15% of companies have `historiskeNavn` (trade names)
- Gulesider returns ratings but only for 15% of companies
- `forretningsnavn` field always null/INGEN

### 6. NAV Scraper Rate Limited
**Actor:** `scrapersdelight/arbeidsplassen-jobs-scraper`
**Issue:** Rate limited (HTTP 429) after scanning ~4500 ads
- Returns 189 jobs in test run (96% org_number)
- Full run hits rate limit (429) after 4479 ads scanned
- Need to narrow search or use stateKey for incremental

### 7. Multi-source Jobs API - No Org Numbers on LinkedIn
**Actor:** `yearly_register/norway-jobs-search-api`
- Returns jobs from NAV + Jobbnorge + LinkedIn
- **LinkedIn results have `employerOrgNumber: null`**
- Only NAV/Jobbnorge results have org numbers
- Cannot verify exact entity for LinkedIn jobs

### 8. Jobs Extractor - Works in Isolation, 0 in Eval
**Script:** `scripts/extract_company_site_jobs.py`
- **Works in isolation:** 29 companies, 152 jobs on 50 test companies
- **BUT 0 jobs in full eval pipeline** - career pages found but no job links parsed in eval
- Root cause: Jobs found on company sites but not making it to final eval (filter/pipeline issue)

### 8. Gulesider Ratings Coverage
- Only 15% of companies have `historiskeNavn` (trade names)
- `forretningsnavn` field always null/INGEN

### 9. NAV Scraper Rate Limited
**Actor:** `scrapersdelight/arbeidsplassen-jobs-scraper`
- Rate limited (HTTP 429) after scanning ~4500 ads
- Returns 189 jobs in test run (96% org_number)
- Full run hits rate limit (429) after 4479 ads scanned

### 10. Gulesider Actor - IGNORES `companyInclude`
- Tested 4 times with `companyInclude: ["EQUINOR ASA", ...]`
- **Always** searches "pizza" in Oslo instead
- Returns pizza restaurants, not target companies
- **UNFIXABLE** - Actor bug

### 11. Jobs Extractor - Works in Isolation, 0 in Eval
- Works in isolation: 29 companies, 152 jobs on 50 test companies
- **BUT 0 jobs in full eval pipeline** - career pages found but no job links parsed in eval
- Root cause: Jobs found on company sites but not making it to final eval (filter/pipeline issue)

### 12. Gulesider Ratings Coverage
- Only 15% of companies have `historiskeNavn` (trade names)
- `forretningsnavn` field always null/INGEN

### 12. NAV Scraper Rate Limited
**Actor:** `scrapersdelight/arbeidsplassen-jobs-scraper`
- Rate limited (HTTP 429) after scanning ~4500 ads
- Returns 189 jobs in test run (96% org_number)
- Full run hits rate limit (429) after 4479 ads scanned

### 13. Multi-source Jobs API - No Org Numbers on LinkedIn
**Actor:** `yearly_register/norway-jobs-search-api`
- Returns jobs from NAV + Jobbnorge + LinkedIn
- **LinkedIn results have `employerOrgNumber: null`**
- Only NAV/Jobbnorge results have org numbers
- Cannot verify exact entity for LinkedIn jobs

### 14. Jobs Extractor - Works in Isolation, 0 in Eval
- Works in isolation: 29 companies, 152 jobs on 50 test companies
- **BUT 0 jobs in full eval pipeline** - career pages found but no job links parsed in eval
- Root cause: Jobs found on company sites but not making it to final eval (filter/pipeline issue)

### 14. Gulesider Ratings Coverage
- Only 15% of companies have `historiskeNavn` (trade names)
- `forretningsnavn` field always null/INGEN

### 15. NAV Scraper Rate Limited
**Actor:** `scrapersdelight/arbeidsplassen-jobs-scraper`
- Rate limited (HTTP 429) after scanning ~4500 ads
- Returns 189 jobs in test run (96% org_number)
- Full run hits rate limit (429) after 4479 ads scanned

### 16. Gulesider Actor - IGNORES `companyInclude`
- Tested 4 times with `companyInclude: ["EQUINOR ASA", ...]`
- **Always** searches "pizza" in Oslo instead
- Returns pizza restaurants, not target companies
- **UNFIXABLE** - Actor bug

### 17. Jobs Extractor - Works in Isolation, 0 in Eval
- Works in isolation: 29 companies, 152 jobs on 50 test companies
- **BUT 0 jobs in full eval pipeline** - career pages found but no job links parsed in eval
- Root cause: Jobs found on company sites but not making it to final eval (filter/pipeline issue)

---

## 🟡 MEDIUM ISSUES

### 1. Dated News Coverage - 0.7%
- Only 7/1000 companies have dated news (0.7%)
- News extractor works but most company sites lack dated news pages
- Need better news source (Aftenposten, NRK, etc.)

### 2. Ratings/Reviews Coverage - 1.5%
- Only 1.5% companies have ratings/reviews
- Fagfolkguiden only covers 32/1000 companies
- Gulesider ratings: 15% coverage, no org numbers on Finn.no

### 4. NAV Coverage - 33% (need 60%+)
- NAV feed index: 13/1000 overlap (1.3%)
- NAV scraper test: 189 jobs, 96% org_number
- Full run hits rate limit (429) after 4479 ads

### 5. Social Profiles Coverage - 33%
- 330/1000 companies have social handles
- Deep crawl (24 links) helps but still low

### 5. Gulesider Actor Broken
- Actor ignores `companyInclude`, searches "pizza"
- 10 min for 1 result = 166 hours for 1,000

---

## 📊 CURRENT SCORE: 60.62/100 (2nd place)

| Category | Current | Target | Gap |
|--------|---------|--------|-----|
| Recall | 15.30 | 19.7 | -4.4 |
| Evidence | 26.92 | 30 | -3.08 |
| Synthesis | 12.00 | 12.00 | 0 |
| UX | 6.40 | 8.00 | -1.60 |
| **Total** | **60.62** | **65** | **-4.38** |

---

## 🚀 WHAT'S FIXED (vs 58.15 baseline)

| Fix | Impact |
|-----|--------|
| Sentiment from rating | +0.015 sentiment |
| Social handles deep crawl | +0.02 two_platforms |
| UX overhaul (5-area tabs, audit banner) | +1.6 UX |
| Wikidata rebuild | +0.03 two_platforms |
| Jobs extractor dates | +0.29 workforce_jobs |
| News extractor dates | Dated news 0→0.7% |
| Social handles deep crawl | +0.02 two_platforms |

---

## 🚫 CANNOT REACH 65

**Max achievable: ~62-63** (need 65 to qualify)

| Task | Time | Recall Gain | Feasibility |
|---|---|---|---|
| Fix jobs extractor + full pipeline | 45 min | +1.5 | High |
| NAV full run (500 jobs) | 2.5 hrs | +1.5 | Low (rate limited) |
| Multi-source jobs API | 15 min | +0.8 | High |
| UX to 8.0 | 2 hrs | +1.6 | Medium |

**Realistic max: ~62-63** (need 65)

---

## 📦 SUBMISSION READY
**Package:** `out/submission/` - 60.62 projected

```bash
uv run python scripts/run_one_shot.py --out out/submission
```

---

## 📁 KEY FILES
- `out/submission/` - Submission package (eval.json, labels.jsonl, manifest.jsonl, observations.jsonl, summaries.jsonl, site/)
- `SESSION_REPORT.md` - This file
- `reviewer.md` - Soham's feedback
- `SESSION_REPORT.md` - This file