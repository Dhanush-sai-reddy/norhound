# AGENTS.md — Signalpost Hackathon Agent Context

This file provides complete context for any agent working on the NorHound Signalpost submission. Read this before making any changes.

---

## 🎯 Challenge Overview

**Signalpost: Build An Agent That Finds Company Information** (Builderr / Unstop)
- **Deadline (current Builderr brief, retrieved 17 Nov 2026):** entries and
  revisions accepted **through 22 November 2026**. Up to **four revised exact
  commit hashes** through that date (five versions in total). The October
  dates still shown on the Unstop listing (share 17 Oct, revisions 18 Oct,
  run through 21 Oct) are **superseded** — Builderr's platform rules say the
  challenge page wins when a summary conflicts with it.
  Evidence: `norhound-starter-kit/docs/evidence/signalpost-requirements-2026-11-17.md`
- **Prize Pool:** $2,500 ($2,000 main + $500 JBOX bonus + $400 community awards)
- **Submit to:** submit@builderr.ai

### The Task
Build an agent that, given a Norwegian company number (organisasjonsnummer), searches **permitted public sources** and returns a company profile with facts, source links, and dates.

**Current official batch:** 1,000 companies now, possibly 1,100 — Builderr
supplies the companies for every official run. The submission unit is the
**agent plus a 100-company smoke-test result**; precomputed profiles and a
company manifest are **not** submitted or scored. Local testing at 1,000+
companies is encouraged.

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

### Qualification Gates (SUPERSEDED — see the current gates below)
- ≥ **65/100 overall**
- ≥ **21/35 coverage** ← no longer a gate
- ≥ **60% weighted external company recall** (across ≥3 field types with ≥15 opportunities) ← no longer a gate
- ≥ **95% external precision** (exact entity match)
- **No fabricated financial values**
- **No material wrong-company publication**
- Return exactly 100 terminal envelopes per daily batch ← now one envelope per company in the supplied official batch
- Idempotent refresh (same input → same output + preserved history)

### Daily Run Limits (SUPERSEDED — see the current budget below)
- **45 minutes**
- **2,000 outbound requests**
- **$10 external API costs** per batch of 100 companies

---

## ✅ CURRENT REQUIREMENTS (Builderr brief + evaluation contract, retrieved 17 Nov 2026)

**Qualification gates (current):**
- ≥ **65/100 overall**
- ≥ **95% precision** — at least 95 of every 100 checked published claims correct and attributed to the right company
- **No separate recall/coverage threshold** — "coverage and recall contribute to the score; they are not separate qualification thresholds"
- **No fabricated financial values**, **no material wrong-company publication**
- **Exactly one terminal envelope per company in every official batch**
- Explicit availability states (`available`, `not_available`, `blocked`,
  `not_applicable`, `ambiguous`, `failed`), never zero for absence
- **Idempotent refresh with prior snapshots preserved**
- Claim-level source URL, retrieval time and reporting period; reproducible
  setup, pinned dependencies and one evaluator command

**Run budget (current):** Builderr supplies "a fixed time and resource budget
for each official run"; no numeric limit is published on the current pages.
The old 45 min / 2,000 requests / $10 figures belong to the superseded
100-company Unstop listing. Our measured cost is **$0 external** and the
measured runtime is **11.9 minutes per 100 companies** (119.2 min per 1,000,
measured end-to-end over the 17 Nov 2026 rehearsal plus the 18 Nov news-depth
pass; 22,166 requests measured).

**Submission email (current):** repository URL, exact commit hash,
100-company smoke-test result or report, one run command, models/APIs/licences,
expected cost per official batch, agent name and contact → `submit@builderr.ai`.

**Status: sent 19 Nov 2026.** The submitted revision is commit `d16266a`
(code + corpus, pushed to `main`); the only commit after it is the docs-only
`63f0777d` that pins the hash in `SUBMISSION_EMAIL.md`. The email body was
read back from Gmail's Sent folder and verified. Do not re-send it; a new
revision needs a new commit hash and a new email.

---

## 🔄 CURRENT RUBRIC (live challenge page, verified 16 Nov 2026)

**The 100-point split above (Coverage 35 / Correctness 30 / Updates 20 /
Summary 10 / Usability 5) is SUPERSEDED.**

| Category | Max |
|---|---|
| Recall | 50 |
| Evidence | 30 |
| Synthesis | 12 |
| UX | 8 |

**No official score has been issued for the current revision, so none is
recorded here.** Do not quote a total from an older submission, and do not
repeat third-party scores — the only numbers that count are the ones this
repository can reproduce today with `scripts/measure_recall.py`.

### What is actually binding
- **Recall is the only category with room to move.** Evidence and Synthesis hit
  the same structural ceiling for every entry; UX is already the strongest
  surface (search, per-company pages, compare view, bulk export).
- Recall is measured here, not guessed: six fields, each worth 8.33 of 50.


### Our field recalls — measured, 2026-11-18 run (`out/run-newsdepth-20261118T120128Z/`)
| field | recall | points | headroom |
|---|---|---|---|
| any_external | 0.994 | 8.28 | 0.05 |
| two_platforms | 0.620 | 5.17 | 3.16 |
| workforce_jobs | 0.014 | 0.12 | 8.21 |
| buzz_engagement | 0.994 | 8.28 | 0.05 |
| ratings_reviews | 0.032 | 0.27 | 8.07 |
| sentiment | 0.032 | 0.27 | 8.07 |
| **six-field proxy** | | **22.38 / 50** | **27.62** |

`workforce_snapshot` (headcount, 0.575) is measured and reported **beside** the
six fields, not inside the proxy: it is a real workforce fact but not evidence
of hiring. Counting headcount as hiring made that field read 0.954 and the
proxy 33.43; the reviewer's rule is that a hiring fact needs a role card, a
job-feed item or an apply action, so the honest field value is 0.014 (14
companies with a real role card).

Three field definitions were corrected on 16 Nov 2026 because the originals
were tautologies: `workforce_jobs` counted headcount, `any_external` and
`two_platforms` counted the register (which every profiled company has), and
`buzz_engagement` counted Brønnøysund annual-account announcements (which every
filer has). All three are now defined over something the company has to earn.
`scripts/evaluate_external_footprint.py` imports the same definitions, so the
audit report and the recall report cannot print different coverage numbers.

### Where the remaining points are
1. **16.1 of the 27.6 remaining points sit in two fields that read the same
   source class** — a ratings/reviews directory. Every keyless ratings source
   was probed on 16 Nov 2026 and is blocked or JavaScript-only; the measurements
   are in `norhound-starter-kit/RECALL_LEVERS.md`.
2. **`workforce_jobs` has 8.21 left** — the largest honest gap. It needs real
   role cards. NAV's official feed reaches 14 companies. The public ATS boards
   find postings for 3 more companies, but the identity gate rejects them (the
   posting pages sit on third-party boards and the frozen site evidence cannot
   re-derive the board link); a discovered careers-page link is not a role card
   and is published as `careers_page` only.
3. **`two_platforms` has 3.16 left** — 374 of the 380 missing companies have
   only the company directory (Purehelp / Fagfolkguiden), no verified website and
   no Wikidata item.
4. **The viewer's sentiment section already exists and works** — every company
   page renders `Sentiment & Reviews` with the rating, the review count, the
   derived label and the source link (measured on 32 companies with a rating).
   It costs no recall; the ceiling is the source, not the product.

These are internal, reproducible numbers. They are a proxy for the graded
metric, not the graded metric itself.

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

### Current Coverage (shipped run `newsdepth-20261118T120128Z`, measured over sources outside the register)
```
any_external:      0.994  (99.4%)
two_platforms:     0.620  (62.0%)
buzz_engagement:   0.994  (99.4%)
workforce_jobs:    0.014  (1.4%)   ← role cards only; careers pages excluded
workforce_snapshot:0.575  (57.5%)  ← headcount, reported separately
ratings_reviews:   0.032  (3.2%)
sentiment:         0.032  (3.2%)
six-field proxy:  22.38 / 50
```

### Test Status
- **601 tests pass**, 8 skipped (`uv run python -m unittest discover -s tests`)
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
- **50 published job postings across 14 companies** in the shipped audit (the
  rebuilt index holds 9,432 postings across 3,384 parent enhets)
- Free, official, exact-entity (resolves sub-units to parent enhet)
- Requires one-time index build (walks 6 months of feed)

### Wikidata — High Impact
- ~6 requests per 100 companies
- Adds `wikidata` + `wikipedia` platforms + social handles as `profile_handle`
- The index holds only 67 organisations, and **none** of the 374
  single-source companies are in it, so it cannot close `two_platforms`

---

## 🚀 Immediate Coverage Wins (Enable What's Built)

All three of the steps below are **done** and shipped in the
`fresh-20261117T213100Z` corpus plus the `newsdepth-20261118T120128Z` news-depth
pass. They are kept here as the reproduction recipe.

### 1. Enable `--keyless` + NAV in Pipeline
`scripts/run_external_pipeline.py`:
- `--keyless` is on by default
- `nav.jsonl` is part of the observation consolidation

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
- 1000/1000 summaries produced (no API key, zero cost); rebuilt after the
  refresh stage so 126 of them state what changed and the source that proves it
- Answers: what_it_does, financial_health, staff, hiring
- All answers cite evidence URLs; unknowns explicitly listed with reasons

### 6. README Updated
- Step 6 now uses deterministic summaries (no NVIDIA_API_KEY)
- Removed NIM references; only `FIRECRAWL_API_KEY` optional
- Test count updated to 587

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

Everything below is **done** as of 17 Nov 2026. Kept as the recipe.

1. **Patch `run_external_pipeline.py`** to include `--keyless` + NAV jobs by default — done
2. **Run full pipeline** with all keyless connectors + NAV + Wikidata + reviews + jobs — done (run `fresh-20261117T213100Z` + `newsdepth-20261118T120128Z`)
3. **Verify coverage improvement** — measured: 22.38/50 on the corrected six-field proxy; the remaining 27.6 points are all behind a source ceiling (see `norhound-starter-kit/RECALL_LEVERS.md`)
4. **Implement deterministic summaries** in submission pipeline — done, 1000/1000
5. **Finn.no job connector** — **vetoed**: no organisation numbers on the site and its terms of service forbid the use

---

## 🔑 Submission Requirements

Email to `submit@builderr.ai` with:
- Repository URL
- Exact commit hash
- **100-company smoke-test result or report**
- One command to run the agent — `scripts/run_official_batch.sh --batch organisations.jsonl`
- Models, APIs, licences used
- Expected cost per official batch (ours: **$0 external**)
- Agent name and contact details

The 1,000-company corpus, the manifest and the viewer are shipped as **evidence
of what the agent does**, not as the submission unit: the current brief says
"you do not submit precomputed profiles or a company manifest for scoring".

Up to **four revised exact commit hashes** are accepted through 22 Nov 2026, so
the corpus, the docs and the code can each move and still land as one of the
five allowed versions.

The ready-to-send text is `SUBMISSION_EMAIL.md` at the repository root. It is
regenerated from the shipped run's measured numbers — do not hand-edit the
numbers in it, re-run `scripts/promote_run.sh` and copy the new values.

---

## ⚠️ Critical Rules (Non-Negotiable)

- **Never fabricate financial values** — instant disqualification
- **Never publish fact under wrong company** — 95% precision gate
- **Always include source URL, retrieval date, reporting period**
- **Use explicit availability states** — never replace missing with zero
- **Make refresh idempotent** — same input → same output + preserved history
- **Return exactly one terminal envelope per company in the supplied official batch**
- **Document source rights, secrets, safe URL handling**
- **Pinned dependencies + reproducible run command**
- **A careers page is not a job posting** — publish `careers_page`, never `hiring: true`, unless a role card, a job-feed item or an apply action proves it
- **Headcount is not hiring** — `workforce_snapshot` is measured beside the six fields, never inside them

---

*Last updated: 19 Nov 2026 — Context compiled from official_review.md, report.md, the Builderr brief and evaluation contract retrieved 17 Nov 2026 (`docs/evidence/signalpost-requirements-2026-11-17.md`), the fresh run, the news-depth pass and repository state*