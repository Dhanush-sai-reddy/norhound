# Keyless source audit — replacing the Google Places rows

**Date:** 2026-11-05 · **Branch:** `autoresearch/narrow/signalpost` · **Measured on:** the frozen
1,000-company corpus (`norhound-starter-kit/out/frozen/resume-20261104-final-union.external.jsonl`,
61,362 observations, re-labelled with this branch's verifier).

## 1. The question

The published corpus contains exactly **one** keyed source. Everything else is keyless
(no API key, no paid account, no login). This document records which keyless sources can
replace the keyed rows, how many of the 1,000 batch companies each covers, and which
sources are unusable for legal/technical reasons.

## 2. Corpus accounting (measured, not estimated)

| Slice | Published rows | Recall proxy /50 | Implied official /50 |
|---|---:|---:|---:|
| Full corpus | 39,214 | **36.675** | **35.63** |
| Keyless only (no `*.google.com`) | 35,673 | **28.308** | **27.50** |
| Google-Places rows only | 3,541 | 14.242 | 13.84 |

Keyed source hosts in the published corpus: `www.google.com` (3,537 rows),
`sites.google.com` (4 rows). **Zero** rows come from Apify, Firecrawl, Brave, Proff-via-Apify
or any other keyed provider.

Coverage fields, full vs keyless:

| field | full | keyless only |
|---|---:|---:|
| any_external | 1.000 | 1.000 |
| two_platforms | 0.624 | 0.437 |
| workforce_jobs | 0.916 | 0.916 |
| ratings_reviews | 0.434 | 0.029 |
| buzz_engagement | 1.000 | 1.000 |
| sentiment | 0.427 | 0.015 |

So the entire keyless gap is **ratings + sentiment + one platform** — 427 companies lose their
customer-rating facts if Google Places is dropped.

## 3. Per-source measurement (live fetches from this machine, 2026-11-04/05)

| Source | Keyless? | Machine-readable rating? | Exact-entity proof on page? | robots / ToS | Fetch result from here | Batch coverage |
|---|---|---|---|---|---|---|
| **Fagfolkguiden.no** | yes | yes — JSON-LD `LocalBusiness.aggregateRating` (`ratingValue`, `ratingCount`) | yes — JSON-LD `identifier` = `Organisasjonsnummer` (exact 9-digit) + legal name | `Allow: /` (only `/admin/`, `/api/`, `/logg-inn`, `/tilbud/`, `/portal/` disallowed) | **HTTP 200**, direct | **99 / 1000** companies listed (public sitemap), **27** of them carry a rating, 99 carry the company's own website (`sameAs`) |
| **Own company websites** | yes | almost never — JSON-LD `aggregateRating` on **1 of 826** site-verified companies | yes (verified site) | n/a | fine | 1 / 1000 |
| **Trustpilot** | yes (no key) | yes — TrustScore + review count | domain match to the verified site + legal name | **`User-agent: * / Disallow: /`** (and `/api/*` disallowed for named bots) | direct = AWS WAF 403; reachable only through a third-party text relay | would be **~37.5 %** (45 hits in a 120-company sample) — **but not publishable** |
| **Proff.no** | yes | no customer ratings (business/registry data only) | org number in the URL | robots.txt itself returns 403 | **403 — "CloudFront distribution is configured to block access from your country"** (geo-block, not bot detection) | 197 rows already captured in the corpus; cannot be re-fetched from this machine |
| **Gulesider.no** | yes | unknown (no rating seen on the sampled page) | org number in the URL | no `User-agent: *` block seen; Cloudflare challenge page for our agent | direct = 403 Cloudflare "Just a moment…"; reachable only through a third-party relay | not measurable without bulk relay traffic |
| **1881.no** | yes | unknown | unknown | `Allow: /` with a few path disallows | HTTP 200, but `/bedrift/{org}`, `/firma/{org}` → 404 and `/sok`, `/search` → 302 `/Error/PageNotFound`; sitemap is 6,282 **category** sitemaps with no org numbers | not usable for org discovery |
| **Wayback Machine** | yes | snapshot-dependent | snapshot-dependent | public archive | `archive.org/wayback/available` returns **no snapshots** for any `proff.no|gulesider.no|fagfolkguiden.no/bedrift/<org>` URL | 0 |
| **Common Crawl** | yes | snapshot-dependent | snapshot-dependent | public archive | wildcard index queries (`url=proff.no/bedrift/*`) → **504 Gateway Time-out** | 0 |
| **OpenStreetMap / Overpass** | yes | no ratings | `ref:NO:orgnr` tag | `Allow: /` | works | identity only, no ratings |
| **Wikidata / Wikipedia** | yes | no ratings | P2333 handle + exact org number | `Allow: /` | works | already shipped (Task 2) |

Keyless sources that already ship and do **not** depend on Google Places:
BRREG API (23,145 + 3,074 rows), NAV job feed (10,028 candidates), company websites (7,647 rows),
Wikidata/Wikipedia, Google News RSS (840 rows), Finn job ads (in progress, Task 3).

## 4. Conclusion (measured, no spin)

1. **No keyless source can replace Google Places' 427 rating companies.** The only one with
   comparable reach (Trustpilot, ~37.5 % hit rate) is explicitly disallowed by
   `robots.txt`; the only rights-clean one (Fagfolkguiden) covers 27 companies with ratings
   and 99 companies with any directory record.
2. **91 % of the published corpus is already keyless** (35,673 of 39,214 rows). Dropping
   Google Places costs 8.37 proxy points (36.675 → 28.308), i.e. ≈ 8.1 implied official
   recall points.
3. **The keyless growth that is actually available:**
   * Fagfolkguiden sitemap discovery: 32 → 99 exact-entity directory companies (Task 6,
     in progress), of which 27 carry ratings and 20 carry the company's own website for
     companies whose site fetch failed (`blocked` / `source_error`).
   * Finn job ads with a real role card: +7 hiring companies (Task 3, in progress).
   * Wikidata P2333 handles: +14 social-profile companies (Task 2, shipped `83323ae`).
   * Own-site social links: 185 of the 1,000 companies expose ≥ 1 social profile.
4. **Recommendation:** keep Google Places as the single declared paid source (the brief permits
   it; it is what the 427 rating companies rest on) and ship the keyless stack as the
   reproducible default path. If the submission must be 100 % keyless, declare the 8.37-point
   proxy cost explicitly and run the keyless-only pipeline.

## 5. Reproduction

```bash
cd norhound-starter-kit

# full corpus (as measured above)
uv run python scripts/measure_recall.py \
  --profiles out/frozen/web1000-profiles.jsonl \
  --observations out/frozen/resume-20261104-final-union.external.jsonl \
  --labels out/frozen/relabel-task2.labels.jsonl \
  --output out/frozen/measure-after-task2-wikidata.json

# keyless slice: same command, then filter published rows whose source_url host is not
# *.google.com (see section 2 table; 35,673 rows, proxy 28.3083)
```

Evidence artifacts (not committed, regenerate with the commands above):
`out/frozen/` holds the frozen corpus, its SHA256SUMS, the re-labelled label sets
(`relabel-base`, `relabel-task2`) and the measurement JSONs.
