# Signalpost: Project Analysis & Recall Improvement Strategy

## 📊 Where We Stand (measured 18 Nov 2026, run `newsdepth-20261118T120128Z`)

**No official score has been issued for the current revision.** The only numbers
below are the ones this repository reproduces itself with
`scripts/measure_recall.py`; they are a proxy for the graded Recall metric, not
the graded metric.

| Field | Recall | Points of 50 | Headroom |
|---|---|---|---|
| any_external | 0.994 | 8.28 | 0.05 |
| two_platforms | 0.629 | 5.24 | 3.09 |
| workforce_jobs | 0.020 | 0.17 | 8.16 |
| buzz_engagement | 0.994 | 8.28 | 0.05 |
| ratings_reviews | 0.032 | 0.27 | 8.07 |
| sentiment | 0.032 | 0.27 | 8.07 |
| **Six-field proxy** | | **22.51 / 50** | **27.49** |

Source: `out/run-newsdepth-20261118T120128Z/measure-final.json`.

`workforce_snapshot` (headcount: 0.575 of companies) is reported beside these
six fields and excluded from the proxy. Only **14 of 1,000** companies have a
real role card — 14 companies, all from NAV's official feed. The public ATS
boards find postings for 3 more companies, but the identity gate rejects them
(the posting pages sit on third-party boards and the frozen site evidence
cannot re-derive the board link).
Counting headcount as hiring is what produced the earlier 0.954 and the
inflated 33.43 headline; counting a discovered careers-page link as a posting
is what produced 0.051.

Three field definitions were corrected on 16 Nov 2026 because the originals
were tautologies: `workforce_jobs` counted headcount, `any_external` and
`two_platforms` counted the register (which every profiled company has), and
`buzz_engagement` counted Brønnøysund annual-account announcements (which every
filer has). The headline fell from 25.91 to 22.51 because the coverage it
claims is now coverage that exists.

> [!IMPORTANT]
> **Recall is the ONLY real battleground.** Evidence and Synthesis hit the same
> structural ceiling for every entry, and UX is already the strongest surface
> here (search, per-company pages, compare view, bulk export). The competition
> comes down to who can find more verified facts about more companies.

### Where the 27.62 remaining points sit

1. **16.1** sit in `ratings_reviews` + `sentiment`, which read the same source
   class (a ratings/reviews directory). Every keyless ratings source probed on
   16 Nov 2026 is blocked or JavaScript-only — measurements in
   `RECALL_LEVERS.md`.
2. **8.2** in `workforce_jobs` — needs real role cards, not `/karriere` pages.
   NAV's official feed is the only keyless source of
   adverts; Finn.no is excluded (no org numbers, terms of service).
3. **3.2** in `two_platforms` — 374 of the 380 missing companies have only
   Purehelp, no verified website and no Wikidata item.

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

### Review 3 — Re-evaluation (new rubric, 1 Oct)

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

Measured 18 Nov 2026 (`out/run-newsdepth-20261118T120128Z/`), six fields, each worth
8.33 of 50:

| Field | Recall | Points | Status | Why |
|-------|--------|--------|--------|-----|
| `any_external` | **0.994** | 8.28 | ✅ Done | 994 companies have at least one source outside the register |
| `two_platforms` | **0.629** | 5.24 | 🟡 Bounded | 374 of the 380 missing companies have only the company directory (Purehelp /
   Fagfolkguiden) — no verified website, no Wikidata item |
| `buzz_engagement` | **0.994** | 8.28 | ✅ Done | A third-party profile, mention or post; registry announcements excluded |
| `workforce_jobs` | **0.020** | 0.17 | 🔴 Largest honest gap | 14 companies have a real role card (all NAV); the ATS boards' postings fail the identity gate, so NAV is the only keyless advert source that publishes |
| `ratings_reviews` | **0.032** | 0.27 | 🔴 Capped | Only 32 of 1,000 companies have any rating page |
| `sentiment` | **0.032** | 0.27 | 🔴 Capped | Same 32 companies; every other ratings directory is blocked or JS-only |

> [!CAUTION]
> The two capped fields (`ratings_reviews`, `sentiment`) carry **16.1 of the
> 27.6** remaining points, and they read the same source class. Closing them is
> a source-access problem, not an extraction problem — see `RECALL_LEVERS.md`
> for the 16 Nov 2026 probe results. The other 8.2 sits in `workforce_jobs`,
> where the constraint is the number of real adverts the keyless NAV feed holds.

### How the Recall Score Is Computed

```
Recall ≈ mean(any_external, two_platforms, workforce_jobs, ratings_reviews, buzz_engagement, sentiment) × 50
       ≈ mean(0.994, 0.629, 0.020, 0.032, 0.994, 0.032) × 50
       ≈ 0.449 × 50
       ≈ 22.51 six-field proxy
```

`workforce_snapshot` (0.575) is reported separately and excluded: headcount is a
workforce fact, but the reviewer's rule is that hiring needs a role card, a
job-feed item or an apply action.

This is an internal proxy. No official Recall figure exists for the current
revision.

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

> **Status: exploration only, not the shipped plan.** The shipped pipeline is
> keyless and costs $0, and the Google Maps / Google Search actors would need a
> Google credential or a paid Apify account — a credential tied to our own
> account cannot be reproduced by the organiser ("What we cannot use is a
> credential tied to your own account on another service, because we cannot
> reproduce your run with it"). The "$10/batch" figure below belongs to the
> superseded Unstop listing; the current brief states that each official run
> has a fixed budget supplied by Builderr and publishes no numbers. This
> section is kept for the record of what was evaluated and why it was not
> used.

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

The table below was written on 4 Oct 2026 against the old field values. The
"outcome" column records what actually happened when each lever was built and
measured, so the projections can be checked rather than trusted.

| Strategy | Effort | Projected | Outcome (measured 15 Nov 2026) |
|----------|--------|-----------|-------------------------------|
| 1. Fix Sentiment | 30 min | +0.8 | Done — `sentiment` now 0.032, capped by the 32 companies that have a rating page |
| 2. Retain News Body | 2 hrs | +2-4 | Done — `--fetch-dates` wired in by default; bodies + mined dates now retained |
| 3. Finn.no Jobs | 4-6 hrs | +3-6 | **Not done** — vetoed (ToS, no org numbers on listings) |
| 4. Deeper Site Crawl | 3 hrs | +2-3 | Done — `two_platforms` 0.994, `any_external` 1.000 |
| 5. Brønnøysund Announcements | 2 hrs | +1-2 | Done — kunngjøring rows now carry a real `retrieved_at` |
| 6. Norid RDAP | 1 hr | +0.5-1 | Not needed — domain resolution already exact-entity |
| 7. Trustpilot/Proff.no | 3-4 hrs | +1-2 | **Blocked** — 403 / JS-only, measured 16 Nov 2026 |
| 8. Business News | 4-5 hrs | +2-3 | Partially done — first-party news bodies retained, third-party news not keyless |
| 9. Google Jobs | 4 hrs | +2-4 | **Not done** — not keyless |

> [!TIP]
> The levers that worked were the ones already inside the permitted, keyless
> surface. The two that were projected to add the most (Finn.no, Trustpilot)
> are exactly the two that are closed to a keyless agent. See
> `RECALL_LEVERS.md` for the probe evidence.

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
7. **Cost** — the shipped pipeline is keyless: **$0 external spend** per official batch
8. **Run budget** — the current brief states each official run has a fixed time and resource budget supplied by Builderr and publishes no numbers. The older 45 min / 2,000 requests / $10 figures belong to the superseded 100-company Unstop listing; the measured rate of the shipped pipeline is **11.9 minutes per 100 companies** (119.2 min per 1,000, measured end-to-end over the 17 Nov 2026 rehearsal plus the 18 Nov news-depth pass, 22,166 requests measured)
9. **One envelope per company** in every official batch, with explicit availability states and idempotent refresh
