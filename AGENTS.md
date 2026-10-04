# AGENTS.md — Signalpost Hackathon Agent Context

This file provides complete context for any agent working on the NorHound Signalpost submission. Read this before making any changes.

---

## 🎯 Challenge Overview

**Signalpost: Build An Agent That Finds Company Information** (Builderr / Unstop)
- **Deadline:** 17 Oct 2026 (project sharing), 18 Oct (code revisions), 21 Oct (entries close)
- **Prize Pool:** $2,500 ($2,000 main + $500 JBOX bonus + $400 community awards)
- **Submit to:** submit@builderr.ai

### The Task
Build an agent that, given a Norwegian company number (organisasjonsnummer), searches **permitted public sources** and returns a company profile with facts, source links, and dates. Must produce 1,000+ profiles; tested on 100 random companies daily.

**Key constraint:** Every fact must be correctly matched to its company — a material wrong-company match fails the entry.

---

## 📊 Scoring Breakdown (100 pts)

> **⚠️ SUPERSEDED 1 Oct 2026** — the rubric changed to
> **Recall 50 / Evidence 30 / Synthesis 12 / UX 8**. See
> "🔄 CURRENT RUBRIC — Re-evaluation" below. Kept for the original review only.

| Category | Points | What It Measures |
|----------|--------|-----------------|
| **Coverage** | 35 | How much information found (70% company coverage + 30% claim count, per field type) |
| **Correctness** | 30 | Facts match the right company, with valid source + date |
| **Update correctness** | 20 | Refresh shows real changes, preserves history, no duplicates |
| **Useful summary** | 10 | Profile explains what company does, changes, unknowns |
| **Usability** | 5 | User can find, compare, verify on desktop and mobile |

### Qualification Gates (ALL must pass)
- ≥ **65/100 overall**
- ≥ **21/35 coverage**
- ≥ **60% weighted external company recall** (across ≥3 field types with ≥15 opportunities)
- ≥ **95% external precision** (exact entity match)
- **No fabricated financial values**
- **No material wrong-company publication**
- Return exactly 100 terminal envelopes per daily batch
- Idempotent refresh (same input → same output + preserved history)

### Daily Run Limits
- **45 minutes**
- **2,000 outbound requests**
- **$10 external API costs** per batch of 100 companies

---

## 🔄 CURRENT RUBRIC — Re-evaluation after re-submission (as of 1 Oct 2026)

**THE SCORING CHANGED. The 100-point split above (Coverage 35 / Correctness 30 /
Updates 20 / Summary 10 / Usability 5) is SUPERSEDED. Use this instead.**

| New category | Max | **Our score** | Position |
|---|---|---|---|
| **Recall** | 50 | **12.89** | THE bottleneck — 37 of our 57 missing pts |
| **Evidence** | 30 | **18.92** | flat — all builders 18.92–18.93 |
| **Synthesis** | 12 | **7.20** | flat — all six builders exactly 7.20 |
| **UX** | 8 | **3.20** | **tied best** (Karthik only 1.60) |
| **Total** | 100 | **42.21** | **6th — NOT QUALIFIED** |

### Leaderboard (post re-evaluation)

| # | Builder | Recall/50 | Evidence/30 | Synthesis/12 | UX/8 | Total |
|---|---|---|---|---|---|---|
| 1 | Karthik | 17.86 | 18.93 | 7.20 | 1.60 | 45.59 |
| 2 | Hardik | 13.96 | 18.92 | 7.20 | 3.20 | 43.28 |
| 3 | Ajai | 13.60 | 18.92 | 7.20 | 3.20 | 42.92 |
| 4 | Vishwajit | 12.97 | 18.92 | 7.20 | 3.20 | 42.29 |
| 5 | Devansh | 12.94 | 18.92 | 7.20 | 3.20 | 42.26 |
| 6 | **Dhanush (us)** | **12.89** | **18.92** | **7.20** | **3.20** | **42.21** |

**Nobody qualified.** Gap to 1st = 3.38 pts, almost entirely Recall (−4.97).

### What this means strategically
- **Recall is the only real battleground** — Evidence and Synthesis are *identical*
  across all six builders (18.92 / 7.20), so whatever caps them is shared and
  structural; we cannot differentiate there.
- **UX we already lead** at 3.20 (mobile + search work paid off). Max left: 4.8.
- Recall ≈ simple mean of our six field recalls: internal evaluator predicts
  **13.27/50**, official gave **12.89/50** → our `coverage` dict is a valid
  proxy for the official Recall metric. Diagnose with it.

### Our field recalls (internal eval, 1,000-company run, commit `b9698de`)
| field | recall | status |
|---|---|---|
| any_external | 0.823 | good — improved from 0.354 |
| two_platforms | 0.361 | room |
| buzz_engagement | 0.352 | room |
| **workforce_jobs** | **0.041** | **DEAD** — only 41/1000 companies have jobs (219 postings: 152 company_site + 67 NAV); NAV index = 3,625 rows |
| **ratings_reviews** | **0.015** | **DEAD** — only 32 of 1,000 companies have a Fagfolkguiden rating page |
| **sentiment** | **0.000** | **HARD ZERO** — see below |

### Root causes of the three dead fields (verified 1 Oct 2026)
1. **`sentiment = 0.000`** — `sentiment_label` is only ever set by
   `normalize_google_maps_results.py:284` (not run) and `run_nim_summary.py:91`
   (deprecated, needs `NVIDIA_API_KEY`). Our Fagfolkguiden connector extracts
   `metrics.rating` (e.g. 4.9/5) but **never sets `sentiment_label`**. Zero
   published rows carry it → sentiment recall structurally 0.
   *Fix:* derive deterministically from rating (4.9/5 → positive) — no model, no
   API. **Caps at 0.032** (32 companies have ratings).
2. **`ratings_reviews = 0.015`** — connector *attempted all 1,000* (all run by
   default, `--reviews` is a no-op); the **source only covers 32 companies**.
   Not a rate-limit. Needs a second directory source.
3. **`workforce_jobs = 0.041`** — biggest single lever. NAV feed only reaches
   41 companies. **Finn.no** (Norway's #1 job board) is the missing source.
4. **Viewer has NO sentiment tab** — sections are Summary / Questions / Facts /
   Observations / Evidence / Changes. Costs both Recall and UX.

---

## 📋 Official Review — Commit 97a43bf (17 Sep 2026) *(OLD rubric, superseded above)*

**Score: 54.92 / 100 — NOT QUALIFIED** (qualification line = 65)

### Score Breakdown
| Category | Score | Max | Notes |
|----------|-------|-----|-------|
| Information found | 8.92 | 35 | **Biggest gap** — registry facts covered; loss is company websites, social profiles, job postings, dated news |
| Correct facts and sources | 30 | 30 | **Perfect** — nothing published was wrong |
| Updates | 16 | 20 | Rerun should keep earlier versions and flag actual changes |
| Useful summaries | 0 | 10 | Missing entirely — need to answer: what company does, revenue/staff growth, hiring |
| Ease of use | 0 | 5 | Missing entirely — need search, open company, see evidence |

### Reviewer Feedback (Soham Sinha)
> "The biggest opportunity is breadth and product completeness: add verified website, social, jobs and dated-activity discovery; preserve refresh history and changes; and make the results easy to search, inspect and understand."

> "Nothing you published was wrong. The missing points are information you didn't find or features you didn't build."

### Revision Target
- **Target:** ≥ 65
- **Strategy math:** summaries (10) + UX (5) + updates (4) ≈ 73.92 **before coverage work**
- **Coverage is the main bottleneck** — all top entries (Ajai 67.46, Anmol 69.57, Penge 65.12) are close to qualification but coverage holds them back

---

## 📩 Private Diagnostic — 700-company capture (received 27 Sep 2026)

**Private diagnostic. NOT an official score, qualification decision, or leaderboard
update.** Ours: **48.69/100**. Applies only to that immutable 700-company capture and
does not replace results sent for other runs/revisions. Full note with per-gap file
diagnosis: **`norhound-starter-kit/private_diagnostic_700.md`**.

**Do not reply on the review thread yet** — "no action is needed now; send the pinned
commit when an iteration is ready."

### Evaluation model changed (why 48.69 ≠ comparable to 54.92)
- 700 companies, not our 1,000-company batch.
- **Scoring uses only the sources captured in our first run** — no second live crawl. A
  fact is worth exactly what its retained source body proves.
- Reference collection admits any fact verifiable from **any participant's** captured
  source, not just the organizer's collector → fairer, but a larger recall denominator.
- ⇒ read the three gaps below, not the score delta.

### Three gaps (all traced to files; first two are shipped-artifact regressions)
| Gap | Evidence in tree | Status |
|---|---|---|
| **No validated hiring** | `out/final-keyless.external.jsonl` has **0** job_board / **0** company_directory rows; `out/keyless-nav-all.external.jsonl` has 10,044 / 93; shipped `out/final-eval.json` reports 65/45 and describes a *different* file | `--nav`/`--reviews` still opt-in at `scripts/run_external_pipeline.py:54`, consolidation `:176` |
| **No validated news** | observations carry `content_sha256` + `evidence_span` = page title, **no retained body**; 56 activity obs / 8 dated per 1,000 | needs bounded first-party body retention + re-verify |
| **No submitted product surface** | `scripts/build_static_site.py` exists, `tests/test_static_site.py` passes, but **no `out/site/` in repo** — `out/` gitignored, only 22 files force-added | build + commit the viewer |

Social extraction already exists (`src/norway_company_agent/website.py:103` markup,
`:122` JSON-LD `sameAs`); the gap is **yield** — homepage-only crawl, `_priority_links`
capped at 6. Also `out/SUBMISSION-REPORT.md` is stale (describes `batch1000f`, still
documents the NIM/`NVIDIA_API_KEY` path).

### Hiring-definition constraint (reviewer is tightening this)
**Do not optimize for generic careers keywords.** Publish a hiring fact only with a real
**role card**, **job-feed item**, or **apply action**. A bare `/karriere` page must emit
an explicit `careers_page` signal, never `hiring: true`. A NAV job-feed item qualifies.

---

## 🔧 Current Repository State

### Workdir
All code lives in `norhound-starter-kit/`. Entry points: `select_entry_batch.py` and `scripts/run_competition_batch.py`.

### Pipeline Stages (from README)
1. **Select entry batch** — 1,000 companies from universe (seed 20260823)
2. **Base batch** — Registry enrichment + exact-identity website capture
3. **External pipeline** — Activity/news/jobs on verified sites, Fagfolkguiden reviews, optional Firecrawl discovery
4. **Verify & label** — Re-verify every observation against frozen evidence
5. **Evaluate** — Score labeled entry (publication requires verified exact_entity)
6. **Deterministic summaries** — Rule-based summaries (no API key)

### Current Coverage (from shipped evaluation)
```
any_external:      0.358  (35.8%)
two_platforms:     0.175  (17.5%)
buzz_engagement:   0.352  (35.2%)
ratings_reviews:   0.015  (1.5%)
workforce_jobs:    0.036  (3.6%)
sentiment:         0.000  (0%)  ← FIXED: added customer_review to eligible sources
```

### Test Status
- **199 tests pass** (was 135)
- All tests in `tests/test_poc.py` and related test files

---

## 📦 Existing Connectors (Built but Not All Enabled)

| Connector | Script | Acquisition | Platform | Signal Types | Status |
|-----------|--------|-------------|----------|--------------|--------|
| BRREG Registry | Core | `official_api` | `brreg` | Identity, roles, subunits, financials | ✅ Core |
| Company Website Crawl | Core | `permitted_public_page` | `company_site` | Description, news, jobs, social | ✅ Core |
| Fagfolkguiden Reviews | `run_fagfolkguiden_reviews_connector.py` | `permitted_public_page` | `company_directory` | `review_summary`, `profile_metrics`, `buzz_metrics` | ✅ `--reviews` flag |
| **NAV Job Feed** | `run_nav_job_feed_connector.py` | `official_api` | `job_board` | `job_posting` | ⚠️ **Built, not in default pipeline** |
| **Wikidata (P2333)** | `run_wikidata_connector.py` | `official_api` | `wikidata`, `wikipedia` | `company_profile`, `profile_handle` | ⚠️ `--keyless` only |
| **Registry Contacts** | `extract_registry_contacts.py` | `official_api` | `brreg` | `contact_email`, `contact_phone` | ⚠️ `--keyless` only (zero cost) |
| **Registry Updates** | `run_registry_updates_connector.py` | `official_api` | `brreg` | `registry_update` | ⚠️ `--keyless` only |
| **Site Description** | `extract_site_description.py` | `permitted_public_page` | `company_site` | `website_description` | ⚠️ `--keyless` only |
| **Substructure/Sitemap** | `extract_substructure.py`, `extract_sitemap_pages.py` | `permitted_public_page` | `company_site` | `sitemap_page` | ⚠️ `--keyless` only |

### NAV Job Feed — High Impact
- Added **65 official_api job postings** in shipped audit
- Free, official, exact-entity (resolves sub-units to parent enhet)
- Requires one-time index build (walks 6 months of feed)

### Wikidata — High Impact
- ~6 requests per 100 companies
- Adds `wikidata` + `wikipedia` platforms + social handles as `profile_handle`
- Boosts `two_platforms` and `buzz_engagement`

---

## 🚀 Immediate Coverage Wins (Enable What's Built)

### 1. Enable `--keyless` + NAV in Pipeline
Edit `scripts/run_external_pipeline.py` to:
- Add `--keyless` flag to default run
- Include `nav.jsonl` in observation consolidation

### 2. One-Time Index Builds
```bash
# Wikidata index (run once)
uv run python scripts/run_wikidata_connector.py --build-index --organisations entry-web1000.jsonl --index data/wikidata-index.jsonl

# NAV job feed index (run once)
uv run python scripts/run_nav_job_feed_connector.py --build-index --index data/nav-job-index.jsonl --days 183 --workers 24
uv run python scripts/run_nav_job_feed_connector.py --resolve-parents --index data/nav-job-index.jsonl --workers 24
```

### 3. Full Pipeline Command
```bash
uv run python scripts/run_external_pipeline.py \
  --profiles out/web1000-profiles.jsonl \
  --envelopes out/envelopes.jsonl \
  --prefix out/web1000batch \
  --jobs --reviews --keyless \
  --wikidata-index data/wikidata-index.jsonl
```

---

## 🔨 Recent Improvements Made

### 1. Annual Report Workforce Connector (`run_annual_report_workforce_connector.py`)
- Added 3 new regex patterns for Norwegian "employees" and "årsverk" phrasing
- Captures: "total antall ansatte", "sum antall ansatte", "gjennomsnittlig/total årsverk"

### 2. Fagfolkguiden Reviews Connector (`run_fagfolkguiden_reviews_connector.py`)
- Added microdata/schema.org fallback for aggregate rating (not just JSON-LD)
- Flexible identity check: only requires org number on page (not strict name match)
- Added `name_verified` flag

### 3. Company Site News Extraction (`extract_company_site_news.py`)
- Expanded `NEWS_PATH` regex to 15+ Norwegian paths: `/media`, `/nyhetsarkiv`, `/pressemeldinger`, `/rapporter`, `/publikasjoner`, `/insights`, `/case`, `/cases`, `/referanser`, `/prosjekter`

### 4. Sentiment Eligibility Fix (`src/norway_company_agent/sentiment.py`)
- Added `customer_review`, `employee_review`, `public_mention` to `INDEPENDENT_SOURCE_CLASSES`
- **Activates sentiment scoring** on Fagfolkguiden reviews (was 0%)

### 5. Deterministic Summaries (`build_deterministic_summaries.py`)
- 1000/1000 summaries produced (no API key, zero cost)
- Answers: what_it_does, financial_health, staff, hiring
- All answers cite evidence URLs; unknowns explicitly listed with reasons

### 6. README Updated
- Step 6 now uses deterministic summaries (no NVIDIA_API_KEY)
- Removed NIM references; only `FIRECRAWL_API_KEY` optional
- Test count updated to 199

---

## 🎯 Missing High-Value Sources (From Source Policy)

| Source | Why It Matters | Effort |
|--------|----------------|--------|
| **Finn.no** | Norway's #1 job board | Medium |
| **E24/DN/Finansavisen** | Norwegian business news | Medium |
| **Brønnøysund Announcements** | Bankruptcy, mergers, dissolutions | Low |
| **Beneficial Owners Register** | UBO data (mandatory Jul 2025) | Low |
| **Norid RDAP** | Domain ownership verification | Low |
| **Google Jobs Search** | Aggregated job postings | Medium |

---

## 📝 Source Rights Rules (Must Follow)

From `https://builderr.ai/starter-briefs/signalpost-sources.md`:
- **Search results = candidates only, not claim evidence**
- **Profile/domain must resolve to exact legal entity before publishing facts**
- **Group/parent/subsidiary/franchise = labelled, not collapsed**
- **Every claim records: source URL, retrieval time, effective/reporting date, content hash, extraction method**
- **Missing/blocked/ambiguous = explicit states**
- **Company-owned copy = describes business but NOT independent sentiment**
- **Evidence beats volume** — rewards exact-company, decision-useful coverage with valid evidence

### Restricted Platforms
- LinkedIn, Meta, Glassdoor, Indeed, similar platforms — **access restrictions apply**
- Unofficial clients may be tested privately but **cannot be sole support for published claims**

---

## 📁 Key Files to Know

| File | Purpose |
|------|---------|
| `README.md` | Full reproduction commands, expected results |
| `AGENTS.md` | This file — agent context |
| `official_review.md` | Official score review (54.92, not qualified) |
| `report.md` | Research report with scoring, sources, architecture |
| `context.md` | Hackathon metadata from Unstop |
| `source_map.md` | Quick decision tree for finding specific fact types |
| `OUTPUT_CONTRACT.md` | Terminal envelope schema |
| `scripts/run_external_pipeline.py` | Main external pipeline orchestrator |
| `scripts/run_competition_batch.py` | Base batch runner |
| `src/norway_company_agent/` | Core agent modules |

---

## 🎯 Next Actions Priority

1. **Patch `run_external_pipeline.py`** to include `--keyless` + NAV jobs by default
2. **Run full pipeline** with all keyless connectors + NAV + Wikidata + reviews + jobs
3. **Verify coverage improvement** — target ≥21/35 coverage
4. **Implement deterministic summaries** in submission pipeline (already done)
5. **Consider Finn.no job connector** for next coverage jump

---

## 🔑 Submission Requirements

Email to `submit@builderr.ai` with:
- Repository URL
- Exact commit hash
- One command to run the agent
- Models, APIs, licences used
- Expected cost per 100-company run
- Contact details
- 1,000+ completed profiles + organisation-number manifest

---

## ⚠️ Critical Rules (Non-Negotiable)

- **Never fabricate financial values** — instant disqualification
- **Never publish fact under wrong company** — 95% precision gate
- **Always include source URL, retrieval date, reporting period**
- **Use explicit availability states** — never replace missing with zero
- **Make refresh idempotent** — same input → same output + preserved history
- **Return exactly 100 terminal envelopes per daily batch**
- **Document source rights, secrets, safe URL handling**
- **Pinned dependencies + reproducible run command**

---

*Last updated: 23 Sep 2026 — Context compiled from official_review.md, report.md, builderr.ai challenge page, and repository state*