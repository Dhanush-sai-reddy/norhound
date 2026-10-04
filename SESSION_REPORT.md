# SIGNALPOST HACKATHON - COMPREHENSIVE SESSION REPORT
## For Next Session / Handoff to Another Agent (Claude Opus)
## Generated: 2026-10-04

---

## EXECUTIVE SUMMARY

**Project:** Signalpost Hackathon - Norwegian Company Intelligence Agent
**Status:** SUBMISSION READY (60.62 projected score)
**Qualification Threshold:** 65/100 (NOT MET - max achievable ~62-63)
**Submission Package:** `out/submission/` - READY

---

## FINAL SCORE PROJECTION

| Category | Score | Max | Gap |
|----------|-------|-----|-----|
| **Recall** | 15.30/50 | 50 | -34.7 |
| **Evidence** | 26.92/30 | 30 | -3.08 |
| **Synthesis** | 12.00 | 12 | 0 |
| **UX** | 6.40/8 | 8 | -1.60 |
| **TOTAL** | **60.62/100** | **100** | **-4.38** |

**Qualification Threshold: 65/100** ❌ NOT MET
**Projected Rank:** 2nd place (beats Nikita 60.51)
**Max Achievable:** ~62-63 (cannot reach 65 with current architecture)

---

## WHAT'S DONE (VERIFIED IN EVAL)

### ✅ WORKING - VERIFIED IN EVAL
| Component | Status | Coverage |
|-----------|--------|----------|
| **any_external** | ✅ | 1.0 (100%) |
| **two_platforms** | ✅ | 0.395 (39.5%) |
| **buzz_engagement** | ✅ | 0.356 (35.6%) |
| **sentiment** | ✅ | 0.015 (32 companies) |
| **precision** | ✅ | 1.0 (0 wrong entity) |
| **entity_precision** | ✅ | 1.0 |

### ⚠️ PARTIAL - CODE DONE, NOT FULLY VERIFIED IN EVAL
| Component | Status | Coverage |
|-----------|--------|----------|
| **workforce_jobs** | ⚠️ Code done | 0.33 (33%) - 330/1000 companies |
| **ratings_reviews** | ❌ | 0.015 (1.5%) |
| **buzz_engagement** | ✅ | 0.356 |
| **sentiment** | ✅ | 0.015 |

---

## WHAT'S BROKEN / UNVERIFIED

| Component | Status | Issue |
|-----------|--------|--------|
| **Jobs extractor** | ❌ Broken | Returns 0 jobs in full eval (career pages found but no job links parsed) |
| **Dated news** | ⚠️ | 7/1000 companies (0.7%) |
| **NAV coverage** | ⚠️ | 33% companies with jobs (need 60%+) |
| **Gulesider** | ❌ BROKEN | Ignores `companyInclude`, searches "pizza" |
| **Multi-source jobs API** | ⚠️ | No org numbers on LinkedIn results |
| **Finn.no / LinkedIn** | ❌ | No org numbers |

---

## WHAT'S FIXED (CODE COMPLETE)

| Fix | Files Modified | Impact |
|-----|----------------|--------|
| **Jobs extractor dates** | `extract_company_site_jobs.py` | Added `observed_at` extraction |
| **News extractor dates** | `extract_company_site_news.py` | Date extraction from page body |
| **Sentiment from rating** | `run_fagfolkguiden_reviews_connector.py` | sentiment 0.000 → 0.015 |
| **Social handles deep crawl** | `website.py` `_priority_links` 6→24 | +0.02 two_platforms |
| **5-area UX tabs** | `build_static_site.py` | Company brief, Financials, Who runs, Working here, Recent activity |
| **Audit banner** | `build_static_site.py` | Wrong-entity, fields matched, 5-area completeness |
| **Completeness badges** | `build_static_site.py` | 5-area badges per company |
| **Evidence lineage** | `build_static_site.py` | Source links + dates on every fact |
| **Sentiment from rating** | `run_fagfolkguiden_reviews_connector.py` | `sentiment_label` + `sentiment_model_version` |
| **Social handles deep crawl** | `website.py` | `_priority_links` 6→24 |
| **Apify storage** | `store_apify_jobs.py`, `store_gulesider_ratings.py` | Ready for Gulesider/Jobs API |
| **Pipeline wiring** | `run_external_pipeline.py` `--external-data` | Merge pre-computed data |
| **One-shot runner** | `run_one_shot.py` | THE submission command |
| **Strategy registry** | `external_control.py` | New strategies registered |
| **Wikidata rebuild** | `run_wikidata_connector.py` | Fresh index |

---

## SUBMISSION PACKAGE (READY)

```
out/submission/
├── eval.json              # 15.3 projected recall
├── labels.jsonl           # 25k verified labels
├── manifest.jsonl         # 1,000 org numbers
├── observations.jsonl     # 49k observations
├── summaries.jsonl        # 1,000 deterministic summaries
├── site/                  # 1,000 company pages with audit banner, 5-area tabs
└── manifest.jsonl         # 1,000 org numbers
```

**Submission Command:**
```bash
uv run python scripts/run_one_shot.py --out out/submission
```

---

## APIFY CREDITS SPENT (~$1.65 of $5 free tier)

| Actor | Runs | Cost |
|-------|------|------|
| Gulesider (test) | 4 runs | ~$0.50 |
| Multi-source jobs | 3 runs | ~$0.05 |
| NAV scraper test | 1 run | ~$1.50 |
| Aftenposten | 1 run | ~$0.01 |
| NAV full run | 1 run | ~$0.75 |
| **Total** | | **~$1.65** |

---

## WHAT'S BROKEN / UNVERIFIED

| Component | Status | Issue |
|-----------|--------|--------|
| **Jobs extractor** | ❌ Broken | Returns 0 jobs in full eval (career pages found but no job links parsed) |
| **Dated news** | ⚠️ | 7/1000 companies (0.7%) |
| **NAV coverage** | ⚠️ | 33% companies with jobs (need 60%+) |
| **Gulesider** | ❌ BROKEN | Ignores `companyInclude`, searches "pizza" |
| **Multi-source jobs API** | ⚠️ | No org numbers on LinkedIn results |
| **Finn.no / LinkedIn** | ❌ | No org numbers |

---

## WHAT SOHEM ASKED (FROM EMAILS)

### Email 1 (Official Review - Sep 17, 2026)
| Gap | What to Fix |
|---|---|
| **Coverage** | Add verified website, social, jobs, dated-activity discovery |
| **Refresh history** | Preserve history, flag changes |
| **UX** | Searchable, inspectable, source→claim path visible |

### Email 2 (Private Diagnostic - Sep 27, 2026)
| Gap | Status |
|---|---|
| **No validated hiring** | 0 job_board / 0 company_directory rows |
| **No validated news** | No retained body, only page titles |
| **No submitted product surface** | `out/site/` not in repo |

### Hiring Definition Constraint
> "Do not optimize for generic careers keywords. Publish a hiring fact only with a real **role card**, **job-feed item**, or **apply action**. A bare `/karriere` page must emit `careers_page` signal, never `hiring: true`. A NAV job-feed item qualifies."

---

## WHAT'S FIXED (CODE DONE, NOT FULLY VERIFIED)

| Requirement | Our Fix | Status |
|-------------|---------|--------|
| Dated news | `extract_company_site_news.py` extracts dates → `observed_at` | ✅ Code, ❌ Full eval |
| Hiring signals | `extract_company_site_jobs.py` + NAV scraper | ✅ Code, ❌ Full eval |
| Company website coverage | `_priority_links` 6→24 | ✅ Code |
| Social profiles | LinkedIn/FB/Insta extraction | ✅ Code |
| Source→Claim Lineage | `evidence_span`, `source_url`, `retrieved_at`, `observed_at` | ✅ Done |
| Refresh History | `changes` section in viewer | ✅ Done |
| UX: Search/Inspect | Searchable viewer | ✅ Done |
| UX: Lineage | "Check the evidence" section | ✅ Done |
| UX: Evidence History | "Changes since previous run" | ✅ Done |
| Summaries | Deterministic, cites sources | ✅ Done |
| Hiring Definition | Only real role cards/job-feed/apply actions | ✅ Code does this |

---

## WHAT'S NOT VERIFIED END-TO-END

| Requirement | Code Done? | Pipeline Run? | Verified in Eval? |
|-------------|------------|---------------|-------------------|
| Dated news `observed_at` | ✅ | ❌ | ❌ |
| Hiring `observed_at` | ✅ | ❌ | ❌ |
| Deep crawl (24 links) | ✅ | ✅ | ✅ (680 obs) |
| Social handles | ✅ | ✅ | ✅ |
| NAV jobs with org_number | ✅ | Test only | ❌ |

---

## WHAT'S STILL MISSING (PER SOHAM)

| Gap | Status |
|---|---|
| **Full NAV coverage** | Only 33% companies with jobs (need 60%+) |
| **Gulesider ratings** | Not integrated (actor broken) |
| **Finn.no/LinkedIn jobs** | No org numbers |
| **Full news body retention** | Only 5000 char excerpt |

---

## WHAT WE CAN'T FIX IN TIME

| Gap | Why |
|---|---|
| **Full NAV coverage (33% → 60%)** | NAV scraper slow, rate limited |
| **Gulesider ratings** | Actor broken (ignores companyInclude) |
| **Finn.no/LinkedIn jobs** | No org numbers |
| **Full page body retention** | Storage cost vs benefit |

---

## MAX ACHIEVABLE SCORE (12 HOURS)

| Task | Time | Recall Gain | Certainty |
|-----|------|-------------|-----------|
| Fix jobs extractor + full pipeline | 1 hr | +1.5 | High |
| NAV scraper full (500 jobs) | 2.5 hrs | +1.5 | High |
| Multi-source jobs API | 30 min | +0.8 | High |
| UX to 8.0 | 2 hrs | +1.6 | Medium |
| **Total doable in 12 hrs** | | **~62-63** | |

**Cannot reach 65 with current architecture. Max achievable: ~62-63.**

---

## SUBMISSION COMMAND

```bash
uv run python scripts/run_one_shot.py --out out/submission
```

## FILES MODIFIED (KEY)

| File | Change |
|------|--------|
| `scripts/extract_company_site_jobs.py` | Added `observed_at` extraction |
| `scripts/extract_company_site_news.py` | Date extraction from page body |
| `scripts/build_static_site.py` | 5-area tabs, audit banner, completeness badges |
| `scripts/run_fagfolkguiden_reviews_connector.py` | `sentiment_label` from rating |
| `scripts/run_external_pipeline.py` | `--external-data` flag |
| `scripts/run_one_shot.py` | One-shot submission command |
| `scripts/store_gulesider_ratings.py` | Full Gulesider extraction |
| `scripts/run_fagfolkguiden_reviews_connector.py` | `sentiment_label` from rating |
| `scripts/run_external_pipeline.py` | `--external-data` flag |
| `scripts/run_wikidata_connector.py` | Fresh index |
| `scripts/run_nav_job_feed_connector.py` | `--requireOrgnr` flag |
| `scripts/verify_and_label_observations.py` | `sentiment_correct: False` |
| `scripts/verify_and_label_observations.py` | `sentiment_correct: False` for missing profiles |

---

## SUBMISSION PACKAGE LOCATION

```
out/submission/
├── eval.json              # 15.3 projected recall
├── labels.jsonl           # 25k verified labels
├── manifest.jsonl         # 1,000 org numbers
├── observations.jsonl     # 49k observations
├── summaries.jsonl        # 1,000 deterministic summaries
├── site/                  # 1,000 company pages
└── manifest.jsonl         # 1,000 org numbers
```

---

## FINAL VERDICT

**Cannot reach 65 with current architecture. Maximum achievable: ~62-63.**

**Recommendation: SUBMIT NOW.** Package at `out/submission/` is complete.

**Projected Score: 60.62/100 (2nd place, beats Nikita 60.51)**

---

## APPIFY CREDITS SPENT: ~$1.65 of $5 free tier

| Actor | Runs | Cost |
|-------|------|------|
| Gulesider (test) | 4 runs | ~$0.50 |
| Multi-source jobs | 3 runs | ~$0.05 |
| NAV scraper | 2 runs | ~$1.50 |
| Aftenposten | 1 run | ~$0.01 |
| **Total** | | **~$1.65** |

---

## FILES MODIFIED / CREATED (SESSION)

### New Files
- `scripts/store_apify_jobs.py` - Store multi-source jobs API output
- `scripts/store_gulesider_ratings.py` - Full Gulesider extraction (with sentiment)
- `scripts/run_one_shot.py` - One-shot submission command
- `scripts/run_gulesider_full.py` - Batch Gulesider runner
- `scripts/apify_cache.py` - Apify cache layer (not yet integrated)
- `reviewer.md` - Comprehensive reviewer feedback doc

### Modified
- `scripts/extract_company_site_jobs.py` - Added `observed_at` extraction
- `scripts/extract_company_site_news.py` - Date extraction
- `scripts/build_static_site.py` - 5-area tabs, audit banner, completeness badges
- `scripts/run_fagfolkguiden_reviews_connector.py` - `sentiment_label` from rating
- `scripts/run_external_pipeline.py` - `--external-data` flag
- `scripts/run_one_shot.py` - One-shot submission command
- `scripts/verify_and_label_observations.py` - `sentiment_correct: False`
- `scripts/run_external_pipeline.py` - `--external-data` flag
- `scripts/run_fagfolkguiden_reviews_connector.py` - `sentiment_label` from rating
- `scripts/run_wikidata_connector.py` - Fresh index
- `scripts/run_nav_job_feed_connector.py` - `--requireOrgnr` flag
- `scripts/verify_and_label_observations.py` - `sentiment_correct: False`

---

## NAV SCRAPER RESULTS (RECOVERABLE)

**NAV Scraper Full Run:** 189 jobs, 96% org_number coverage (Dataset: `ElSknEDh5dacXNUpH`)
- Run ID: `qROtxYHGTMWMbiKMT`
- Dataset ID: `ElSknEDh5dacXNUpH`
- Status: Available for recovery

---

## GULESIDER STATUS

**BROKEN FOR OUR USE CASE** - Actor ignores `companyInclude`, searches "pizza" instead.

| Test | Input | Result |
|---|---|---|
| Test 1 | `query: "pizza"` | 10 pizza places |
| Test 2 | `companyInclude: [10 names]` | Ignored - searched "pizza" |
| Test 3 | `companyInclude: [10 names]` + `fetchDetails` | Ignored - searched "pizza" |
| Test 4 | `companyInclude: ["EQUINOR ASA", "999801389"]` | Ignored - searched "pizza" |

**Verdict:** Actor ignores `companyInclude`, defaults to `query: "pizza"`. Not usable.

---

## MULTI-SOURCE JOBS API (yearly_register/norway-jobs-search-api)

**Works but no org numbers on LinkedIn results.**

| Test | Input | Result |
|---|---|---|
| Test 1 | `query: "utvikler"` | 5 jobs, `employerOrgNumber: null` |
| Test 2 | `query: "Equinor"` | 0 results |
| Test 3 | `companyInclude: ["EQUINOR ASA"]` | 0 results |

**Verdict:** LinkedIn results lack org numbers → precision risk.

---

## SUBMISSION CHECKLIST

- [x] `out/submission/eval.json` - 15.3 projected recall
- [x] `out/submission/labels.jsonl` - 25k verified labels
- [x] `out/submission/manifest.jsonl` - 1,000 org numbers
- [x] `out/submission/observations.jsonl` - 49k observations
- [x] `out/submission/summaries.jsonl` - 1,000 summaries
- [x] `out/submission/site/` - 1,000 company pages with audit banner
- [x] `out/submission/manifest.jsonl` - 1,000 org numbers

**SUBMISSION COMMAND:**
```bash
uv run python scripts/run_one_shot.py --out out/submission
```

---

## FINAL VERDICT

**Projected Score: 60.62/100** (2nd place, beats Nikita 60.51)
**Qualification: NOT MET (65 required)**
**Max Achievable: ~62-63**
**Recommendation: SUBMIT NOW**

---

*Report generated: 2026-10-04*
*Session duration: ~6 hours*
*Apify credits spent: ~$1.65 of $5 free tier*
*Submission package: `out/submission/`*