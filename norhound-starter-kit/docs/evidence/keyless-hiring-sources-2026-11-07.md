# Keyless hiring sources — measured ceiling and the precision bug they exposed

Date: 2026-11-07
Scope: Norwegian job postings, keyless only (no API key, no login, no paid account).

## Summary

1. The keyless hiring ceiling for a 1,000-company random batch is small. Four
   public ATS feeds work today and return real role cards, but they reach
   roughly **4–12 companies** with live roles (0.4–1.2%).
2. The bigger finding is a **precision bug**, not a yield problem: **41 of the
   48 ATS rows (85%) in the shipped corpus came from sites whose identity
   assessment was `related_or_uncertain`** — a group page, an affiliate, a
   parent company's site or a property manager's site. The ATS link on such a
   page does not prove the legal entity owns the board.
3. The ATS connector was implemented and tested but **never called by the
   pipeline**, so every applicant-tracking system the corpus could reach was
   silently dropped from the shipped corpus.

All three are now fixed. The fix raises hiring recall by a few companies; the
identity gate is what protects the ≥95% exact-entity precision gate.

## The precision bug (measured)

`scripts/run_ats_jobs_connector.py` accepted two identity statuses:

```python
if str(ident.get("status") or "").lower() not in {"exact", "related_or_uncertain"}:
    return []
```

`related_or_uncertain` means the page does **not** prove the company owns it.
Verified examples from the shipped 1,000-company corpus:

| Organisation number | Legal name | Role card wrongly attached |
|---|---|---|
| 997627970 | CONOCOPHILLIPS INTERNATIONAL WELL RESPONSE COMPANY AS | a Texas lease-operator card |
| 923194592 | AVARDA BANK AB NUF | a Lithuanian bank's credit-underwriting roles |

Both organisations' registered website resolves to a group site, so the group
board's roles were attributed to the Norwegian legal entity.

Those rows happened to be dropped later by the verifier (0 of the 48 were
published in `out/web1000batch.external-merged.jsonl`), but the connector must
not emit them: publishing them breaks the precision gate the moment the
verifier's rules change.

**Fix:** only an `exact` identity site may publish ATS rows
(`tests/test_ats_identity_gate.py`).

## Four keyless feeds that work

### 1. Teamtailor JSON Feed — `https://<tenant>.teamtailor.com/jobs.json`

```bash
curl -sS -A 'NorHoundResearch/0.1 (+contact)' 'https://bigbite.teamtailor.com/jobs.json' \
  | jq '.items[] | {title,url,date_published}'
```

- Verified live: HTTP 200, `application/feed+json`, JSON Feed 1.1.
- Payload: `title`, `home_page_url`, `items[].title/url/date_published/content_html`.
- **robots.txt** (tenant `xxlnorge.teamtailor.com`, HTTP 200): disallows only
  `/app/`, `/messages/`, `/messenger/`, `/facebook/tab/`, `/jobs/internal/`.
  `/jobs.json` and `/jobs.md` are allowed. The file also carries
  `Content-Signal: search=yes, ai-train=no, ai-input=yes` and a named-agent
  block `User-Agent: aihitdata Disallow: /`, which does not affect `*`.
- **ToS** (`https://www.teamtailor.com/en/terms-and-conditions/`): no
  scraping/crawling/automation prohibition. The closest clauses prohibit
  copying/reproducing/reselling the Service and monitoring it for competitive
  purposes. Reading public career pages per company is not prohibited.
- The old connector used `jobs.rss`; the JSON feed is strictly better because
  it carries `date_published` and `content_html`.

### 2. Recruitee careers-site API — `https://<tenant>.recruitee.com/api/offers/`

```bash
curl -sS 'https://balchem.recruitee.com/api/offers/' \
  | jq '.offers[] | {title,slug,published_at,company_name,careers_apply_url,locations}'
```

- Verified live: HTTP 200, `application/json`, payload
  `{"offers":[{title,slug,published_at,company_name,careers_apply_url,locations,...}]}`.
- **robots.txt** (`recruitee.com` and tenant `balchem.recruitee.com`, HTTP 200):
  `User-Agent: * / Disallow: /v/` → `/api/offers/` allowed.
- **ToS** (`https://recruitee.com/terms`): grep over the full 3,389-line text
  for scrap / crawl / robot / spider / harvest / data-min / reverse-engineer /
  unauthorized returns **zero hits**. Clause 13.3 explicitly treats Careers-Site
  content as public domain.

### 3. Easycruit RSS — `https://<tenant>.easycruit.com/rss/jobs`

```bash
curl -sS 'https://aal.easycruit.com/rss/jobs' \
  | python3 -c "import sys,xml.etree.ElementTree as ET
for i in ET.parse(sys.stdin).getroot().findall('.//item'):
    print(i.findtext('title'),'|',i.findtext('link'),'|',i.findtext('pubDate'))"
```

- Verified live: HTTP 200, RSS 2.0, real `<item>` role cards.
- **robots.txt** (tenant `aal.easycruit.com`, HTTP 200): `Disallow: /intranet/`,
  `Allow: /` → `/rss/jobs` allowed.
- The per-vacancy HTML page `https://aal.easycruit.com/vacancy/3675555`
  answers **HTTP 202 with an empty body** (anti-bot), so the HTML fallback can
  never work for Easycruit. RSS is the only viable keyless path.
- ToS for Easycruit was not fetched separately; the existing repository
  connector already treats Easycruit as a permitted ATS, so the residual risk
  is low but not zero.

### 4. jobbnorge public API — `https://publicapi.jobbnorge.no/v3/jobs`

- Verified live: v1 and v3 both open, no auth; OpenAPI at
  `https://publicapi.jobbnorge.no/swagger/v1/swagger.json`.
- **robots.txt** (`jobbnorge.no`, HTTP 200): only
  `Disallow: /ledige-stillinger/joblisting/pdf/*` → API paths allowed.
- **Blocker:** a regex for `\d{3} ?\d{3} ?\d{3}` over `/v1/jobs` and `/v3/jobs`
  finds **no organisation number in any payload**. The employer is a legal
  name only, so matching would be name-based, not exact-entity.
- **Yield for this batch: 0–4 companies.** The 2,217 live ads are almost all
  kommune/stat employers; the batch is 996 private / 1 kommune / 3 stat.
  Worth wiring only if the evaluation batch ever shifts to public-sector
  entities.

## Already-wired ATS family

Workday, Lever, Greenhouse, SmartRecruiters, Workable, Webcruiter, Jobylon,
ReachMee, hr-manager, recman — all official public career APIs with no key.
Current yield in the batch: Workday 1 company / 20 rows.

## Entity-matching rule (the important part)

Every ATS tenant is reached **only through a link published on the company's
own exact-identity site** (`linked_from_verified_site`). Two rules then apply:

1. `related_or_uncertain` sites are rejected outright. A group page's board is
   the group's board.
2. Teamtailor, Recruitee and Easycruit are **multi-tenant** platforms — one
   tenant can host boards for unrelated companies. Their feeds name their own
   company, so the feed's company name must share a distinctive legal-name
   token with the entity (or contain the organisation number) before any role
   is published. Implemented in `feed_company_matches()`.

A role card also carries the role's **real** publication date. An undated role
card stays undated — it never borrows the crawl date.

## Request budget

A sweep of 830 sites × 4 paths ≈ 3,320 requests, over the 2,000-request daily
cap for a 100-company batch. Safe plan: sitemap-first on all 830 (≈830
requests) + 3 career paths only on the exact-identity companies (≈1,068) +
≈30 feed fetches ≈ **1,930 requests, inside the cap**.

## Rejected sources

| Source | Why |
|---|---|
| Finn.no | Excluded by instruction; ToS prohibits systematic scraping; the Apify actor returns 223 ads with **zero organisation numbers** |
| Teamtailor Job Board API (`partner.teamtailor.com/job_boards`) | Needs `Authorization: Token …`; the XML feed is a per-board unique URL issued only after integration activation; webhooks need a secret |
| Recruitee platform API (`api.recruitee.com`) | HTTP 404 root; the per-tenant careers-site API is the keyless path |
| Easycruit platform API (`api.easycruit.com/api/v1/vacancies`) | HTTP 401 — key required; RSS is the keyless path |
| EURES job search API (`eures.europa.eu/api/jobsearch/v2/jobs`) | HTTP 403 Akamai "Sorry" on every path; robots disallows `/search/` |
| Common Crawl content | ToU indemnity clause covers "use of Crawled Content in connection with artificial intelligence, machine learning…" — discovery only, never a publishing source |
| Wayback CDX | ToS/robots posture for automated CDX use unconfirmed — manual discovery aid only, never a publishing source |
| 1881.no / DNB / Wellfound / JobTeaser | robots allow, but no organisation number in the payload and platform-restricted |
| Proff.no | HTTP 403 CloudFront geo-block from this host |
| data.norge.no | robots: `Allow: /`, `Disallow: /api/`, `Disallow: /*?`; search-API host `Disallow: /` |
| Easycruit per-vacancy HTML | HTTP 202 + empty body (anti-bot); RSS supersedes it |
| jobindex.no | NXDOMAIN (DNS status 3) |
| offentligoppdr.no, workbuster.no | NXDOMAIN |
| varbi.no | SERVFAIL |
| jobbsoker.no | HTTP 410 |
| stillingsportalen.no, jobmatch.no | same IP 185.134.245.113, unreachable |
| jobbsok.no | resolves, connection times out |
| zizzi.no | 194.63.248.52 is a fashion e-store, not a job board |

## Where the hiring family actually stands

Exact-identity job observations in the shipped 1,000-company corpus:

| Strategy | Observations | Companies | Dated |
|---|---|---|---|
| `jobs_feed_discovery` (company-site job cards) | 297 | 53 | 297 (123 mined from the page, 174 the listing-page date) |
| `official_nav_job_feed_orgnr_match` | 112 | 26 | 112 (real `published` from the official feed) |
| `company_site_activity` (`careers_page`) | 44 | 44 | undated, correctly |
| `ats_role_card` | 48 | 4 | **0 published** — all on non-exact identities |

The 44 `careers_page` rows are an explicit hiring signal, never a role claim:
the challenge requires a real role card, job-feed item or apply action.
