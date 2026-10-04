# Signalpost: Project Analysis & Recall Improvement Strategy

## 📊 Where We Stand (4 Oct 2026)

| Metric | Value | Position |
|--------|-------|----------|
| **Total Score** | **42.21 / 100** | 6th of 6 — NOT QUALIFIED |
| Recall | 12.89 / 50 | 37 of 57 missing pts come from here |
| Evidence | 18.92 / 30 | Flat — all builders at 18.92–18.93 |
| Synthesis | 7.20 / 12 | Flat — all builders exactly 7.20 |
| UX | 3.20 / 8 | **Tied best** (only Karthik lower at 1.60) |

> [!IMPORTANT]
> **Recall is the ONLY real battleground.** Evidence and Synthesis are structurally capped at identical scores for everyone. UX we already lead. The entire competition comes down to who can find more verified facts about more companies.

### Leaderboard (post re-evaluation)

| # | Builder | Recall/50 | Total/100 | Gap to us |
|---|---------|-----------|-----------|-----------|
| 1 | Karthik | 17.86 | 45.59 | +4.97 recall |
| 2 | Hardik | 13.96 | 43.28 | +1.07 |
| 3 | Ajai | 13.60 | 42.92 | +0.71 |
| 4 | Vishwajit | 12.97 | 42.29 | +0.08 |
| 5 | Devansh | 12.94 | 42.26 | +0.05 |
| 6 | **Us** | **12.89** | **42.21** | — |

**Nobody has qualified (65 threshold).** Gap to #1 is only 3.38 total points, almost entirely Recall.

---

## 🔍 What the Reviewer Actually Said (Decoded)

### Review 1 — Official (54.92/100, commit 97a43bf, 17 Sep)

> *"Nothing you published was wrong. The missing points are information you didn't find or features you didn't build."*

**Translation:** Perfect precision (30/30). Zero wrong-company publications. But coverage is terrible (8.92/35) — we only have registry facts, no company websites, social profiles, job postings, or dated news.

### Review 2 — Private Diagnostic (48.69/100, 700-company capture, 27 Sep)

> *"The main gaps are no validated news or hiring recovery and no submitted data-linked product surface."*

Three specific gaps traced to FILES:

| Gap | Root Cause | File |
|-----|-----------|------|
| **Zero hiring facts shipped** | `--nav`/`--reviews` were opt-in flags; keyless revision ran without them | [run_external_pipeline.py](file:///home/dhanushsr/Downloads/hackathons/signalpost/norhound-starter-kit/scripts/run_external_pipeline.py#L73-L87) — **FIXED since then** |
| **News has hash + title only, no body** | `evidence_span` = page title; no retained body → unverifiable | [extract_company_site_news.py](file:///home/dhanushsr/Downloads/hackathons/signalpost/norhound-starter-kit/scripts/extract_company_site_news.py) |
| **No viewer submitted** | `out/site/` missing from repo — code exists but wasn't committed | [build_static_site.py](file:///home/dhanushsr/Downloads/hackathons/signalpost/norhound-starter-kit/scripts/build_static_site.py) |

### Review 3 — Re-evaluation (42.21/100, new rubric, 1 Oct)

The rubric CHANGED from Coverage/Correctness/Updates/Summary/UX → **Recall/Evidence/Synthesis/UX**. Recall now dominates at 50 points.

> *"For jobs, a generic careers page is not enough: publish a hiring fact only when you have a real role card, job-feed item, or apply action."*

**Reviewer constraint:** Don't optimize for generic `/karriere` keywords. Only real job postings count.


---

## 📋 Comprehensive Coverage Matrix (Addressing ALL Points by Soham Sinha)

Below is the complete mapping of every single requirement, diagnostic note, and constraint stated by reviewer **Soham Sinha** across his official review (17 Sep), private diagnostic (27 Sep), and re-evaluation rubric (1 Oct), matched with our exact solution and targeted recall gain:

| # | Soham Sinha's Feedback / Diagnostic Requirement | Root Cause in Code | Solution / Strategy | Targeted Field | Recall Impact |
|---|------------------------------------------------|--------------------|---------------------|----------------|---------------|
| 1 | **"No validated hiring"** (generic `/karriere` pages rejected; requires real role cards, job-feed items, apply actions) | `extract_company_site_jobs.py` emitted `hiring: true` on generic pages; `--nav` opt-in flag omitted in keyless run | 1. Finn.no Job Connector (`run_finn_jobs_connector.py`) with role card validation<br>2. Google Jobs API (`apify/google-search-scraper`) with apply markers<br>3. NAV pam-stilling feed full index | `workforce_jobs` | 0.041 → **0.35+** (+3.0–6.0 pts) |
| 2 | **"No validated news"** (observations carry title/SHA256 only, no retained body text → unverifiable) | `extract_company_site_news.py` set `evidence_span` = title without storing body excerpt | 1. Retain first 2,000–5,000 characters of news text in `evidence_body`<br>2. Extract explicit publication ISO dates (`observed_at`) from news articles | `buzz_engagement` & `any_external` | 0.352 → **0.55+** (+2.0–4.0 pts) |
| 3 | **"Website/Social Coverage Low"** (missing social profiles, secondary company links) | Homepage-only crawl with `_priority_links` capped at 6 | 1. Increase deep crawl `_priority_links` 6 → 24 in `website.py`<br>2. Parse schema.org `sameAs` JSON-LD + markup on `/kontakt`, `/om-oss` | `two_platforms` & `any_external` | `two_platforms` 0.361 → **0.60+** (+2.0–3.0 pts) |
| 4 | **"Sentiment = 0.000"** (sentiment missing entirely across published rows) | `sentiment_label` only set by deprecated NIM script | 1. Derive `sentiment_label` deterministically from Fagfolkguiden/Trustpilot star ratings (4.0+ positive, <3.0 negative) | `sentiment` | 0.000 → **0.20+** (+1.5–2.5 pts) |
| 5 | **"Ratings/Reviews Low"** (Fagfolkguiden only reaches 32/1,000 companies) | Source coverage exhaustion on Fagfolkguiden | 1. Apify Google Maps Scraper (`compass/google-maps-scraper`) matching by name + postal code<br>2. Trustpilot Scraper by domain (`company.no`) | `ratings_reviews` | 0.015 → **0.25+** (+2.0–4.0 pts) |
| 6 | **"No submitted product surface"** (missing `out/site/` in git repository) | `out/` folder was gitignored while site builder script was present | 1. Run `build_static_site.py` to generate 1,000 interactive company pages<br>2. Force-commit `out/site/` viewer package | UX Score | 3.20 → **8.00** (Tied Best / Winner) |
| 7 | **"Preserve refresh history & changes"** (idempotency, lineage, and deltas) | Envelopes missing explicit `changes` array across re-runs | 1. Lineage tracking with `content_sha256`, `retrieved_at`, `observed_at`<br>2. Enforce `changes` diff calculation in envelope consolidation | Updates / Lineage Gate | Qualification Gate Passed |

---

## 📉 Field-by-Field Recall Diagnosis

Our internal eval (1,000-company run, commit `b9698de`) maps directly to the official Recall metric:

| Field | Recall | Status | Why |
|-------|--------|--------|-----|
| `any_external` | **0.823** | ✅ Good | Improved from 0.354 via keyless connectors |
| `two_platforms` | **0.361** | 🟡 Room | Need more second-platform sources |
| `buzz_engagement` | **0.352** | 🟡 Room | Need `public_post`, `public_mention`, or `profile_metrics` |
| `workforce_jobs` | **0.041** | 🔴 DEAD | Only 41/1000 companies have jobs (219 postings: 152 company_site + 67 NAV); NAV index = 3,625 rows |
| `ratings_reviews` | **0.015** | 🔴 DEAD | Only 32 of 1,000 companies have a Fagfolkguiden rating page |
| `sentiment` | **0.000** | 🔴 HARD ZERO | `sentiment_label` never set in any active code path |

> [!CAUTION]
> The three DEAD fields (`sentiment`, `ratings_reviews`, `workforce_jobs`) together contribute **0.056 recall** out of a possible **~1.0** each. Even small improvements here move the needle dramatically because the mean of six field recalls IS the Recall score.

### How the Recall Score Is Computed

```
Recall ≈ mean(any_external, two_platforms, buzz_engagement, workforce_jobs, ratings_reviews, sentiment) × 50
       ≈ mean(0.823, 0.361, 0.352, 0.041, 0.015, 0.000) × 50
       ≈ 0.265 × 50
       ≈ 13.27 predicted → 12.89 actual (close proxy)
```

---

## 🔬 Root Causes of Dead Fields

### 1. `sentiment = 0.000` — Structurally Zero

**Problem:** `sentiment_label` is only set in two places:
- [normalize_google_maps_results.py:284](file:///home/dhanushsr/Downloads/hackathons/signalpost/norhound-starter-kit/scripts/normalize_google_maps_results.py) — not run
- [run_nim_summary.py:91](file:///home/dhanushsr/Downloads/hackathons/signalpost/norhound-starter-kit/scripts/run_nim_summary.py) — deprecated, requires `NVIDIA_API_KEY`

Our Fagfolkguiden connector extracts `metrics.rating` (e.g., 4.9/5) but **never sets `sentiment_label`**.

**Fix:** Deterministic derivation from rating:
```python
# rating >= 4.0 → "positive", 3.0-3.9 → "neutral", < 3.0 → "negative"
```
No model, no API. **Caps at 0.032** (32 companies have ratings).

### 2. `ratings_reviews = 0.015` — Source Exhaustion

**Problem:** Fagfolkguiden connector runs against all 1,000 companies — it only covers 32. This is a SOURCE problem, not a code problem.

**Fix needed:** Add a second directory/review source. Candidates:
- **Google Places API** — paid, probably too expensive
- **TripAdvisor** — terms may block scraping
- **Trustpilot** — Norwegian companies are on it, terms allow reading
- **Proff.no** — Norwegian business directory with some reviews

### 3. `workforce_jobs = 0.041` — Biggest Single Lever

**Problem:** NAV feed only reaches 41 companies in our 1,000-company batch (despite 3,625 orgs in the full index). Company-site job extraction yields 152 postings but from very few companies.

**Fix needed:**
- **Finn.no** — Norway's #1 job board. Would dramatically increase coverage.
- Deeper company-site crawl for `/karriere`, `/ledige-stillinger` pages with actual job listings (not just page detection)

---

## 🚀 9 Prioritized Strategies to Increase Recall

### Strategy 1: Fix Sentiment (Trivial, +0.8 pts)

> **Effort:** 30 minutes | **Impact:** sentiment 0.000 → ~0.032 | **Recall gain:** ~+0.8 pts

Add deterministic sentiment derivation from existing Fagfolkguiden ratings in [sentiment.py](file:///home/dhanushsr/Downloads/hackathons/signalpost/norhound-starter-kit/src/norway_company_agent/sentiment.py):

```python
def derive_sentiment_from_rating(rating: float) -> str:
    if rating >= 4.0: return "positive"
    if rating >= 3.0: return "neutral"
    return "negative"
```

Patch the Fagfolkguiden connector to set `sentiment_label` on every observation that carries a rating.

---

### Strategy 2: Retain News Body Text (Medium, +2-4 pts)

> **Effort:** 2 hours | **Impact:** buzz_engagement/any_external improvement | **Recall gain:** ~+2-4 pts

Current news observations carry only `evidence_span` = page title. Under the current evaluation model this is **unverifiable**.

**Fix:** In [extract_company_site_news.py](file:///home/dhanushsr/Downloads/hackathons/signalpost/norhound-starter-kit/scripts/extract_company_site_news.py):
- Retain the first 2,000 chars of page body text as `evidence_body`
- Parse and attach dates from news pages (currently only 8/1000 are dated)
- This makes the observations verifiable → counted in Recall

---

### Strategy 3: Finn.no Job Connector (High Impact, +3-6 pts)

> **Effort:** 4-6 hours | **Impact:** workforce_jobs 0.041 → potentially 0.15-0.30 | **Recall gain:** ~+3-6 pts

Finn.no is Norway's largest job board. Their job search API is publicly accessible.

**Implementation:**
1. Build a `run_finn_jobs_connector.py` script
2. Search by company name (org number not in Finn's schema)
3. Verify entity match using Brreg registry (name + address matching)
4. Each real job posting qualifies as a `job_posting` signal with exact role card data

> [!WARNING]
> Finn.no must be accessed lawfully. Check `robots.txt` and terms. Their public search results page is likely permitted; scraping deep pages may not be.

---

### Strategy 4: Deeper Company Site Crawl (+2-3 pts)

> **Effort:** 3 hours | **Impact:** two_platforms, buzz_engagement, any_external | **Recall gain:** ~+2-3 pts

Currently we crawl **homepage only** and `_priority_links` is capped at 6. Social links on `/contact`, `/about`, footer pages are missed.

**Fix in** [website.py](file:///home/dhanushsr/Downloads/hackathons/signalpost/norhound-starter-kit/src/norway_company_agent/website.py):
- Increase `_priority_links` cap from 6 to 12-15
- Explicitly target Norwegian paths: `/kontakt`, `/om-oss`, `/about`, `/contact`
- Extract social links from ALL crawled pages (not just homepage)
- This boosts `two_platforms` (need 2+ external platforms per company)

---

### Strategy 5: Brønnøysund Announcements (Low Effort, +1-2 pts)

> **Effort:** 2 hours | **Impact:** buzz_engagement, freshness | **Recall gain:** ~+1-2 pts

Official bankruptcy, merger, and dissolution announcements from Brønnøysund. Free, official API, exact-entity by org number.

**Implementation:**
- Hit the Brønnøysund kunngjøringer (announcements) API
- Each announcement = `public_mention` signal type
- Dates are built-in (announcement date)
- These are official-source `public_mention` observations → boost `buzz_engagement`

---

### Strategy 6: Norid RDAP Domain Verification (Low Effort, +0.5-1 pts)

> **Effort:** 1 hour | **Impact:** Evidence quality, any_external | **Recall gain:** ~+0.5-1 pts

Norid RDAP provides `.no` domain ownership data. Free, no auth.

**Implementation:**
- Query `https://rdap.norid.no/domain/{domain}` for each company's domain
- Verify domain ownership matches the company
- Adds a `company_directory` platform signal
- Strengthens evidence chain for website observations

---

### Strategy 7: Trustpilot/Proff.no Review Source (+1-2 pts)

> **Effort:** 3-4 hours | **Impact:** ratings_reviews 0.015 → 0.05-0.10 | **Recall gain:** ~+1-2 pts

Fagfolkguiden only covers 32/1000 companies. Need a second review directory.

**Trustpilot approach:**
- Norwegian companies have Trustpilot pages
- Search by company name, verify org number match
- Extract `review_summary` (average rating, review count)
- Check robots.txt — Trustpilot's public review pages are generally accessible

**Proff.no approach:**
- Norwegian business directory
- Shows employee count, financial data, and basic company info
- May have review/rating data for some companies

---

### Strategy 8: E24/DN Norwegian Business News (+2-3 pts)

> **Effort:** 4-5 hours | **Impact:** buzz_engagement, freshness | **Recall gain:** ~+2-3 pts

Norwegian business news sites (E24.no, DN.no, Finansavisen.no) mention companies by name with dates.

**Implementation:**
- Search E24.no RSS feeds or public article listings
- Match company names to our org numbers via registry
- Each dated article = `public_mention` signal
- Retain article excerpt (first 2,000 chars) as evidence body

> [!NOTE]
> This is medium-effort because entity resolution (matching news mentions to exact org numbers) requires careful name matching to avoid wrong-company publications.

---

### Strategy 9: Google Jobs Search API (Medium, +2-4 pts)

> **Effort:** 4 hours | **Impact:** workforce_jobs | **Recall gain:** ~+2-4 pts

Google Jobs aggregates postings from multiple Norwegian job boards including Finn.no, NAV, and company career pages.

**Implementation:**
- Use Google's structured job posting search
- Each result contains company name, job title, location, date
- Verify entity match via org number
- Real role cards = valid `job_posting` signals


---

## 🐝 Apify Actors Analysis (Boost Recall via Pre-built Crawlers)

Using Apify Actors fits within our permitted public sources and daily batch budget limits ($10/batch). Below are top candidate Apify Actors evaluated for Norwegian company coverage:

### 1. Google Maps Scraper (`compass/google-maps-scraper` or `scraping_experts/google-maps-scraper`)
- **Target Fields:** `ratings_reviews` (0.015 → 0.20+), `sentiment` (0.000 → 0.20+), `two_platforms`
- **Why It Helps:** Google Maps / Google Business Profiles cover virtually every registered Norwegian business with physical or registered addresses. Extracts star ratings, review count, customer reviews text, exact address, and verified website link.
- **Cost & Rate Limit:** ~$1.00 - $2.00 per 1,000 queries. Extremely efficient.
- **Entity Matching:** Match by `company_name + city / postal_code` (from Brreg registry). High precision when verified against website or address.

### 2. Trustpilot Scraper (`epctex/trustpilot-scraper` or `dan.m/trustpilot-scraper`)
- **Target Fields:** `ratings_reviews`, `sentiment`
- **Why It Helps:** Many Norwegian e-commerce, B2C, and service companies have Trustpilot profiles. Extracts aggregate ratings, star breakdowns, and review texts.
- **Cost:** ~$0.50 - $1.00 per 1,000 companies.
- **Entity Matching:** Search by domain name (e.g. `domain.no`) derived from verified website URL. High precision matching.

### 3. Google Search Scraper (`apify/google-search-scraper`)
- **Target Fields:** `workforce_jobs`, `buzz_engagement`, `two_platforms`
- **Why It Helps:** Execute targeted queries like `"site:finn.no/job/inline" "Company Name"` or `"Company Name" site:e24.no`. Returns indexed job listings and news articles with titles and snippets without direct site blocking.
- **Cost:** ~$1.50 per 1,000 queries.

### 4. Gulesider Scraper (Directory Scraper)
- **Target Fields:** `ratings_reviews`, `buzz_engagement`, `two_platforms`
- **Why It Helps:** Gulesider / 1881 are the primary Norwegian phone and business directories. Contains org numbers, ratings, addresses, phone numbers, and categories for nearly all Norwegian entities.

---

## 📈 Projected Impact Summary

| Strategy | Effort | Recall Gain (pts) | New Recall | Priority |
|----------|--------|-------------------|------------|----------|
| 1. Fix Sentiment | 30 min | +0.8 | 13.7 | 🔥 DO NOW |
| 2. Retain News Body | 2 hrs | +2-4 | 15.7-17.7 | 🔥 DO NOW |
| 3. Finn.no Jobs | 4-6 hrs | +3-6 | 18.7-23.7 | 🔥 HIGH |
| 4. Deeper Site Crawl | 3 hrs | +2-3 | 20.7-26.7 | HIGH |
| 5. Brønnøysund Announcements | 2 hrs | +1-2 | 21.7-28.7 | MEDIUM |
| 6. Norid RDAP | 1 hr | +0.5-1 | 22.2-29.7 | MEDIUM |
| 7. Trustpilot/Proff.no | 3-4 hrs | +1-2 | 23.2-31.7 | MEDIUM |
| 8. Business News | 4-5 hrs | +2-3 | 25.2-34.7 | LOWER |
| 9. Google Jobs | 4 hrs | +2-4 | 27.2-38.7 | LOWER |

> [!TIP]
> **Doing just strategies 1-4 could push Recall from 12.89 to ~20-24**, which would put us at 49-53 total — **#1 on the current leaderboard** and significantly closer to qualification.

---

## ⚡ Recommended Execution Order

```
Phase 1 (Day 1 — Quick wins):
  ✅ Strategy 1: Fix sentiment (30 min)
  ✅ Strategy 2: Retain news body text (2 hrs)
  ✅ Strategy 6: Norid RDAP (1 hr)

Phase 2 (Day 2-3 — Big movers):
  🔧 Strategy 3: Finn.no jobs connector (4-6 hrs)
  🔧 Strategy 4: Deeper company site crawl (3 hrs)

Phase 3 (Day 4-5 — Polish):
  🔧 Strategy 5: Brønnøysund announcements (2 hrs)
  🔧 Strategy 7: Trustpilot/Proff.no reviews (3-4 hrs)

Phase 4 (If time permits):
  🔧 Strategy 8: Business news (4-5 hrs)
  🔧 Strategy 9: Google Jobs (4 hrs)
```

---

## 🛡️ Constraints to Remember

1. **Never fabricate financial values** — instant disqualification
2. **Never publish fact under wrong company** — 95% precision gate
3. **Generic careers page ≠ hiring fact** — need real role cards/job-feed items
4. **Evidence beats volume** — retained source body must prove the fact
5. **Company-owned copy ≠ independent sentiment** — promotional text can't be sentiment evidence
6. **Restricted platforms** — LinkedIn, Meta, Glassdoor, Indeed scraping prohibited
7. **$10 external API limit** per 100-company batch
8. **2,000 outbound requests** limit per batch
9. **45 minutes** time limit per daily run
