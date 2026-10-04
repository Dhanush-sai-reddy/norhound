# Signalpost — Execution Spec for Nemotron

**Read this fully before touching code. Every number below is verified against live data.**

---

## 1. Mission

We are **4th at 58.15/100**. First place is **60.51**. The gap is **2.36 points**.

| # | Builder | Recall /50 | Evidence /30 | Synthesis /12 | UX /8 | Total |
|---|---|---|---|---|---|---|
| 1 | Nikita | 13.59 | 26.92 | 12.00 | 8.00 | **60.51** |
| 2 | Mangal | 12.83 | 26.92 | 12.00 | 8.00 | 59.75 |
| 2 | Siri Nandan | 12.83 | 26.92 | 12.00 | 8.00 | 59.75 |
| **4** | **Dhanush R2 (us)** | **12.83** | 26.92 | **12.00** | **6.40** | **58.15** |
| 5 | Biswajeet v4 | 8.75 | 29.00 | 12.00 | 8.00 | 57.75 |

Board reviewed **3 Oct 2026**. **0 of 19 entries qualified.** Batch is now **1,200** companies.
Qualification (65) is unreachable for everyone — **the winner is whoever reaches ~60.5.**

### Two levers. Do both and we win.

| Task | Move | Gain |
|---|---|---|
| **A** | UX 6.40 → 8.00 (match the three 8.00 holders) | **+1.60** |
| **B** | Recall 12.83 → 13.59 (just match Nikita) | **+0.76** |
| | **Total** | **+2.36 → 60.51, 1st** |

### ✅ Progress since spec written (3 Oct 2026)

| Done | Impact |
|---|---|
| **B1 — Sentiment from rating** (20 min) | sentiment 0.000 → 0.015, +0.11 official recall |
| **B3 — Social handles crawl depth** (1 min) | `_priority_links` limit 6 → 24, more platform handles |
| **Task A — UX overhaul** | Site rebuilt with 5-area tabs, audit banner, completeness filter |

Current internal recall: **0.2975** (14.88/50) → projected official **12.94/50** (+0.11 vs 12.83)
Gap to Nikita recall 13.59: need **+0.65 official** = +0.75 internal = sum fields +0.045

---

## 2. Non-negotiable rules

1. **Precision is 1.0 with 0 wrong-entity publications.** Do not regress it. A single material
   wrong-company publication is worse than losing all 2.36 points. When adding any source, match
   on **legal entity number only** — never fuzzy name matching.
2. **Synthesis is already 12.00/12 — perfect and tied #1.** Do not touch summary generation.
   Any change there risks losing up to 4.8 points. Leave it alone.
3. **Evidence is 26.92/30** and identical for almost every builder. Not a differentiator. Ignore.
4. **Never fabricate a financial value.** Instant disqualification.
5. **Never publish `hiring: true` from a bare careers page.** The reviewer explicitly tightened
   this. A `/karriere` page must emit `careers_page`, never `hiring`.

---

## 3. Traps — do not repeat these mistakes

### Trap 1: the phantom eval file
`out/norhound.external-eval.json` (dated 3 Oct) reports `workforce_jobs: 0.332`.
**This is false.** It was computed against an unshipped input file. The real shipped data
(`out/norhound.external.pre-workforce.jsonl`) has **41 orgs with `job_posting` = 0.041** and
**zero** workforce snapshots. Never quote 0.332. Never trust an eval JSON without re-running it
against the file you are shipping.

### Trap 2: NAV is exhausted — not untapped
`data/nav-job-index.jsonl` holds 3,625 org numbers. Overlap with our 1,000-company batch: **13**
(verified with `zfill(9)` format normalisation — not a matching bug).

NAV is **mathematically capped at 1.3% company coverage**. Do not spend time extending the index,
raising `--days`, or re-running `--resolve-parents`. Only 13 of our companies ever posted a job
inside the statutory 183-day window.

### Trap 3: internal eval now OVERSTATES official
Internal evaluator says Recall **14.75**. Official says **12.83**. Ratio **0.87**, not the 0.97
from the previous review cycle. Treat internal gains as roughly **0.87×** their official value.

### Trap 4: `workforce_snapshot` is not hiring
`evaluate_external_footprint.py:80` counts `{"job_posting", "workforce_snapshot"}` as
`workforce_jobs`. Our registry/annual-report employee counts are a `workforce_snapshot`, which is
headcount — **not** evidence of hiring. Counting it may flatter our internal number while the
official evaluator ignores it. Only real role cards, job-feed items, or apply actions qualify.

---

## 4. TASK A — UX 6.40 → 8.00 (+1.60)

**Entry point:** `scripts/build_static_site.py` (20,684 bytes, modified 3 Oct 12:00).
Site is **already committed** — 1,001 files under `out/site/`. Do not re-litigate shipping it.

**Current tabs** (at lines 232–284): Summary · Questions · Facts · Observations · Evidence · Changes

### What the 8.00-scoring reference product has that we lack

Reference: `https://www.builderr.ai/signalpost`. It publishes its own audit numbers on the landing
page and has this exact surface:

1. **Published audit banner** — reference shows:
   - `0 wrong-company publications`
   - `201 / 203 fields matched` (fresh PDF audit)
   - `48 / 100 have data in all five categories` (evidence coverage)
   **We show none of this.** Add it to the index page. This is the single clearest UX differentiator.
2. **"All five areas" completeness filter + "Most data found" sort.** Reference sorts profiles by
   verified-data density and filters to companies complete in all five categories. Add a
   completeness score per company and expose both the filter and the sort.
3. **Tab naming aligned to reviewer language.** Reference uses: *Company brief · Latest financials ·
   Who runs it? · Working here · Recent activity*, plus a **"Check the evidence"** affordance.
   Rename/alias our tabs to match that vocabulary so a reviewer scanning for "hiring" or
   "financials" finds them. Keep existing tab ids stable so deep links do not break.
4. **A sentiment/ratings surface.** We have **zero** sentiment rows published. There is no tab a
   reviewer can use to check ratings. Even an explicit *verified-unknown* state scores better than
   an absent surface — the source policy says missing/blocked/ambiguous must be **explicit states**.
5. **Per-company completeness breakdown** — which of the five areas are covered and which are
   explicitly unavailable, with the reason.

### Acceptance criteria for Task A
- [ ] Index page renders the audit banner with values computed from the actual shipped eval JSON —
      **read the file at build time, never hardcode the numbers.**
- [ ] Sort by "Most data found" and filter "All five areas" both work on desktop **and** mobile.
- [ ] Every one of the five areas is either filled or an explicit labelled unknown with a reason.
- [ ] `python -m pytest tests/test_static_site.py -q` passes.
- [ ] Site rebuilds from frozen inputs with no network access.

---

## 5. TASK B — Recall 12.83 → 13.59 (+0.76)

Recall = **mean of six field recalls × 50**. Verified current values:

| field | recall | status |
|---|---|---|
| any_external | **1.000** | maxed |
| two_platforms | 0.362 | headroom |
| buzz_engagement | 0.352 | headroom |
| workforce_jobs | 0.041 | capped by Trap 2 |
| ratings_reviews | **0.015** | near-dead, real headroom |
| sentiment | **0.000** | **hard zero** |

Mean = 0.2950 → 14.75 internal.

### The arithmetic you need

`+0.76 official` ≈ `+0.87 internal` ≈ **+0.0105 mean** ≈ **+0.063 summed across six fields.**

That is a small target. **Any one of these closes it:**

| Fix | Field gain | Internal pts | Effort |
|---|---|---|---|
| **Derive sentiment from rating** | sentiment 0.000 → ~0.032 | +0.27 | ~20 min |
| **Second review directory** | ratings_reviews 0.015 → ~0.10 | +0.71 | hours |
| Social handle harvesting | two_platforms 0.362 → ~0.45 | +0.73 | ~3 hrs |

### B1 — Sentiment hard zero (cheapest, do first)

**Root cause, already diagnosed:** `sentiment_label` is only ever written by
`normalize_google_maps_results.py:284` (not in the pipeline) and `run_nim_summary.py:91`
(deprecated, needs `NVIDIA_API_KEY`). Our Fagfolkguiden connector extracts `metrics.rating`
(e.g. 4.9/5) but **never sets `sentiment_label`**. Zero published rows carry it.

**Fix:** derive deterministically from the rating band. **No model, no API call.**

Suggested bands — confirm against `src/norway_company_agent/sentiment.py` conventions:
```
rating >= 4.0  -> positive
rating >= 3.0  -> neutral
rating <  3.0  -> negative
```
Source class `customer_review` is **already** in `INDEPENDENT_SOURCE_CLASSES` in `sentiment.py`,
so eligibility is unblocked.

**Ceiling is 0.032** — only 32 of 1,000 companies have a Fagfolkguiden rating. This alone does not
win, but it removes a hard zero and is nearly free.

**Acceptance criteria for B1**
- [ ] Deterministic: same input → same label. No randomness, no network, no API key.
- [ ] Only applied where a rating was actually extracted. **Never** default to a label.
- [ ] Label is traceable to the rating value and the source URL on the observation.
- [ ] `sentiment_audited` in the eval JSON becomes **> 0** and `sentiment_accuracy` becomes a
      non-null number.

### B2 — Second review directory (the real Recall win)

Fagfolkguiden covers only **32 of 1,000** companies, yet the connector runs on all 1,000 by
default. This is **not** a rate limit — the source simply lacks the other 968.

Find a second Norwegian review/ratings source with **broad** coverage. Requirements:
- Publicly accessible page containing the rating
- Page must resolve to the **exact legal entity** (org number on page, or a link we can verify)
- Must yield a real `review_summary` / `profile_metrics` / `place_summary` signal

Candidate categories worth investigating: Norwegian trade directories, municipal business
listings, industry association member directories.

**Hard constraint:** no fuzzy name matching. If the page does not prove the entity, abstain.
Abstaining is correct and expected — the source policy requires explicit states over guesses.

**Acceptance criteria for B2**
- [ ] Coverage measured and reported before/after on the same 1,000 profiles.
- [ ] `wrong_entity_publications` still **0** after the change. Non-negotiable.
- [ ] Any company without a verified page gets an explicit *unavailable* state, not a blank.

### B3 — Social handles for `two_platforms`

`src/norway_company_agent/website.py:103` (markup) and `:122` (JSON-LD `sameAs`) already parse
handles. The gap is **yield**: homepage-only crawl and `_priority_links` capped at **6**.

Raise the crawl depth / link cap and harvest `sameAs` profiles as `profile_handle` observations.
Current platform counts show the ceiling: facebook 120, instagram 102, linkedin 67, youtube 17,
tiktok 9, x 6 — versus **2,957** company_site. Social is badly under-extracted.

---

## 6. Verify your work — run these

```bash
cd /home/dhanushsr/Downloads/hackathons/signalpost/norhound-starter-kit

# full test suite — must stay green
uv run python -m pytest tests/ -q

# re-score the ACTUAL shipped observations (never trust a stale eval JSON)
uv run python scripts/evaluate_external_footprint.py \
  --profiles out/web1000-profiles.jsonl \
  --observations out/norhound.external.pre-workforce.jsonl \
  --labels out/norhound.labels.jsonl \
  --output out/TRUE-SCORE.json \
  --minimum-audit 300

# confirm gates before claiming anything improved
python3 -c "
import json; d=json.load(open('out/TRUE-SCORE.json')); c=d['coverage']
assert d['wrong_entity_publications']==0, 'PRECISION GATE BROKEN'
assert d['entity_precision']==1.0, 'PRECISION GATE BROKEN'
m=sum(c.values())/6
[print(f'  {k:18s} {v}') for k,v in c.items()]
print(f'  MEAN {m:.4f} -> internal Recall {m*50:.2f}/50')
print(f'  projected official ~{m*50*0.87:.2f}/50')
"
```

**Report back:** the six field recalls, the new mean, and confirmation that
`wrong_entity_publications == 0`. If precision moved off 1.0, the change is a net loss — revert it.

---

## 7. Anti-goals — do not do these

| Do NOT | Why |
|---|---|
| Extend the NAV index or raise `--days` | Capped at 13/1000 orgs (Trap 2) |
| Modify summary generation | Synthesis is perfect 12/12 |
| Add any fuzzy/name-based entity matching | Risks the precision gate — costs more than it gains |
| Trust `out/norhound.external-eval.json` | Phantom numbers (Trap 1) |
| Wire in NVIDIA/NIM for synthesis | Deprecated; costs money; Synthesis already maxed |
| Chase Evidence points | 26.92/30 for nearly every builder; structural |
| Rebuild the annual-report workforce pipeline | Headcount, not hiring (Trap 4). Stopped deliberately. |

---

## 8. Definition of done

- [ ] UX at parity with the 8.00 entries → **+1.60**
- [ ] Recall ≥ 13.59 official-equivalent → **+0.76**
- [ ] `wrong_entity_publications == 0`, `entity_precision == 1.0`
- [ ] All tests pass
- [ ] Total projected **≥ 60.51 → first place**

**If precision breaks, ship nothing.** A disqualified entry scores zero.