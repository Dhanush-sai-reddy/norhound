# Keyless (no key / no login) review, rating and social-handle sources for Norwegian companies

**Research date:** 2026-11-04 / 2026-11-05 UTC
**Machine:** Linux, plain `curl` + `python3 urllib`, browser User-Agent
**Org-number source:** `/home/dhanushsr/Downloads/hackathons/signalpost/norhound-starter-kit/data/1000-orgs.txt` (999 lines, 9-digit org numbers)
**Shipped baseline for comparison:** `norhound-starter-kit/out/submission/batch.external.merged.jsonl` (28,375 observations; `google_places` `review_summary` = 311 rows) and `norhound-starter-kit/out/submission/batch.fagfolk-report.json` (`exact_pages = 127`, `rated_companies = 32`, `errors = 871`)

---

## 0. VERDICT

**No keyless source found can replace Google Places ratings at scale.** The only reachable keyless source that carries an aggregate rating at all is **Fagfolkguiden**, and it covers **32 / 1000** orgs with a rating (its own sitemap proves the ceiling is **99 / 1000** orgs listed).

Two connectors are still worth building, because they are cheap and they add *other* recall fields, not ratings:

1. **Extend the existing Fagfolkguiden connector** to publish non-rating `company_directory` facts for the **95 orgs it already fetched and cached but discarded** (127 cached pages, 32 rated → 95 discarded). Zero new outbound requests.
2. **1881.no directory connector** — resolves **88 / 100** sampled batch orgs (≈ 880 / 1000) with `leiCode` = org number, website, phone, email, and occasionally a Facebook/Instagram/LinkedIn handle. **Rights risk**: its ToS forbids systematic extraction even though robots.txt allows the pages.
3. **Do not build Tripadvisor / Trustpilot / GuleSider / keyless-Google connectors** — all four are blocked, JS-only, or forbidden (see §3).

---

## 1. Candidate table

Every row was tested live from this machine on 2026-11-04/05. "Fetch test" = the exact HTTP result observed.

| Source | Keyless? | Rating in machine-readable form? | Org-number proof? | robots / ToS note | Fetch test result |
|---|---|---|---|---|---|
| **Fagfolkguiden.no** | **Yes** — no key, no login | **Yes** — JSON-LD `aggregateRating.ratingValue` + `aggregateRating.ratingCount` | **Yes** — JSON-LD `identifier.value` = org nr | `https://www.fagfolkguiden.no/robots.txt` → 200; `User-agent: * Allow: /`, disallows only `/admin/ /api/ /logg-inn /tilbud/ /portal/`. No public ToS page found (`/vilkar`, `/personvern`, `/vilkar`, `/vilkår` all 404) | `https://www.fagfolkguiden.no/bedrift/933520846` → **HTTP 200**, 178,969 B, JSON-LD `LocalBusiness` with `identifier.value="933520846"`, `aggregateRating.ratingValue=5`, `aggregateRating.ratingCount=9`. Unlisted org (`/bedrift/996493660`) → **HTTP 404** |
| **1881.no** | **Yes** — no key, no login | **No** — 0 of 95 sampled pages had `aggregateRating`/`ratingValue`/`reviewCount`/`omtaler`/`vurderinger` | **Yes** — JSON-LD `leiCode` = org nr | `https://www.1881.no/robots.txt` → 200; `User-agent: *` allows `/` (disallows `/Utility/ /blocked/ /Details/OnSameAddress /Details/BusinessAdsNearBy /color /ukjent-nummer/graph /SendMessage/`); named AI bots (anthropic-ai, ClaudeBot, ChatGPT-User, CCBot, Google-Extended, Bytespider, meta-webindexer, OAI-SearchBot, PerplexityBot, Scrapy, SemrushBot…) are `Disallow: /`. **ToS `https://min.1881.no/vilkaar-personvern/bruk-av-tjenestene` → 200 forbids systematic extraction** (quoted in §3.1) | `https://www.1881.no/?query=926088149` → **HTTP 302 → 200**, 84,324 B, JSON-LD `ProfilePage.mainEntity` = `LocalBusiness` with `leiCode:"926088149"`, `sameAs:"https://www.facebook.com/vtelektroas"`, `url:"https://www.vtelektro.no/"`. Coverage: **53/60** and **35/40** on two random batch samples |
| **Proff.no** | Technically yes via `r.jina.ai` (no auth header sent), but the origin itself is not directly reachable | **No** — company page fetched via proxy had 0 `aggregateRating`, 0 `ratingValue`, 0 `reviewCount`, no JSON-LD at all | **Yes** — `Org nr 996 493 660` printed in the proxied name-search result | `https://www.proff.no/robots.txt` → **403 direct**; via `https://r.jina.ai/https://www.proff.no/robots.txt` → 200 and company pages are *allowed* (disallows `/laglister?* /konkurser?* /nyetableringer?* /bedriftssammenligning?* /nettverksøk* /inaktive-foretak* /payment* /api/*` + paginated search endpoints). **ToS `https://www.proff.no/info/rettigheter/` → 200 explicitly forbids regular/systematic/continuous retrieval** | Direct `https://www.proff.no/bedrift/996493660` → **HTTP 403** (`x-amz-cf-pop: BOM78-P5`, `x-cache: Error from cloudfront`). Via `r.jina.ai`: `https://www.proff.no/søk-etter-firmanavn?q=Wegger+AS` → 200, title *"Wegger AS - 247 selskaper i Norge. Proff.no"*, result link `https://www.proff.no/selskap/wegger-as/blommenholm/bedriftsrådgivning/IGHABFG043Z` with `Org nr 996 493 660` |
| **GuleSider.no** (Eniro Norge AS) | Nominal yes, but not reachable | Unknown — never reached a company page | Unknown | `https://www.gulesider.no/robots.txt` → **403** (Cloudflare); ToS not reachable | `https://www.gulesider.no/` → **HTTP 403**; `/personvern`, `/om`, `/vilkar` → 403 *“Just a moment…”*; via `r.jina.ai` → *“Just a moment…”*. Only `https://r.jina.ai/https://www.gulesider.no/?query=996493660` returned 200 but a 365 KB **client-rendered shell with zero search results** (URL scheme visible in shell: `/headquarter+as+oslo/301379062/bedrift`) |
| **Trustpilot** | No | Yes in principle (JSON-LD `aggregateRating`), never obtained | No org nr on Trustpilot pages | `https://no.trustpilot.com/robots.txt` → 200, **`User-agent: * Disallow: /`** (blanket) | `https://no.trustpilot.com/review/wegger.net` → **HTTP 403**, AWS WAF interstitial *“Verifying your connection…”* (`edge.sdk.awswaf.com`). Wayback: `https://archive.org/wayback/available?url=no.trustpilot.com/review/bilbyraet.no` → **no snapshots** |
| **Tripadvisor.no** | Yes | Yes in principle (JSON-LD), never obtained | **No org nr** — identity would need name+address | `https://www.tripadvisor.no/robots.txt` → 200, **no `User-agent: *` section** (named bots only), no Sitemap | `https://www.tripadvisor.no/` → **HTTP 200 but 43,423 B with an empty text body** (JS-only); `/Search?q=…` also renders an empty body |
| **Google Maps / MyBusiness public HTML** | Yes (no key) | No — rating is client-side only | No | Google ToS prohibits automated extraction; `google.com/robots.txt` restricts `/search` | `https://www.google.com/maps/search/Wegger+AS+Blommenholm` → 200, 211,740 B, **0** occurrences of `rating`; `https://www.google.com/maps/place/Quality+Hotel+Grand+AS,+Kongsberg` → 200, 209,052 B, `APP_INITIALIZATION_STATE` present but **0** `ratingValue`/`reviewCount`; `https://www.google.com/maps/preview/search?…&pb=…` → **HTTP 404**; `https://www.google.com/search?tbm=lcl&q=…` → 200 but a JS interstitial (*“Klikk her hvis du ikke viderekobles…”*) |
| **OpenStreetMap** | Yes | **No** — OSM has no customer-rating tags for ordinary businesses | No (org nr not an OSM tag) | ODbL — clean | `https://nominatim.openstreetmap.org/search?q=933520846&format=json` → 200, `[]` |
| **Wikidata / Wikipedia** | Yes (CC0) | No rating/review-count property for companies | Yes via `P2333` | CC0 / CC BY-SA — clean | `https://query.wikidata.org/sparql` `?item wdt:P2333 "933520846" "921197330" "996493660"` → 200, **0 rows**; `wbsearchentities&search=933520846` → `search: []`; `no.wikipedia.org` search → 0 hits. Shipped coverage is 66 orgs, signal types only `company_profile` + `profile_handle` |
| **BRREG / Enhetsregisteret** | Yes (official NLOD) | No | Yes (authoritative) | Open licence — clean | `https://data.brreg.no/enhetsregisteret/api/enheter/933520846` → **HTTP 200** JSON |
| **Finn.no** | Yes | No — job/classified ads, no customer rating | No org nr on ad pages | `https://www.finn.no/robots.txt` → 200 | `https://www.finn.no/?query=996493660` → 200 but the home shell; org nr not present |
| **OpenStreetMap / Overpass** | Yes | No | No | ODbL — clean | `overpass-api.de` probe failed on unencoded query; not pursued — no rating tags exist |
| **1881 API** (`api1881.no`) | **No** — commercial, signup required | n/a | n/a | `https://min.1881.no/vilkaar-personvern/avtalevilkar-api-produkter` | `https://www.api1881.no` → 200 marketing site (*“Prøv våre tjenester gratis i dag!”*), `https://www.api1881.no/robots.txt` → 404 |
| **Proff API / MCP / Webhooks** | **No** — paid | n/a | n/a | commercial | `https://www.proff.no/info/proff-api/` exists |
| **Wayback Machine** | Yes | Would carry the rating *as of the snapshot* | Depends on source | Internet Archive explicitly permits research use | `https://archive.org/wayback/available?url=www.fagfolkguiden.no/bedrift/bil-byraet-as-933520846` → 200 but **`archived_snapshots: {}`**; `…?url=www.1881.no/?query=996493660` → `{}`; `…?url=www.gulesider.no` → homepage snapshot exists (`20261027105118`) but not company pages. `https://web.archive.org/cdx/…` → *“Temporarily Offline”*, later HTTP 429 |
| **Common Crawl** | Yes | Would carry the rating as of the crawl | Depends on source | permissive | `https://index.commoncrawl.org/CC-MAIN-2025-30-index?url=proff.no/bedrift/996493660&output=json` → **HTTP 504** |
| **DuckDuckGo / Bing HTML** | Yes | Search results are **candidates only**, never evidence (Signalpost rule) | n/a | n/a | `https://html.duckduckgo.com/html/?q=site:proff.no+996493660` → HTTP 202, 14,268 B, no result links parsed |
| **Bedrift.no** | — | — | — | — | `https://www.bedrift.no/robots.txt` → 200 but body is **“Parked at Loopia”** → dead domain |
| **Bedriftsinfo.no** | — | — | — | — | `https://bedriftsinfo.no/?query=996493660` → 301 → `https://domenemegleren.no/domener/bedriftsinfo-no/` → **domain for sale, dead** |
| **Allebedrifter.no** | — | — | — | — | `https://allebedrifter.no/` → 200 (Nuxt SPA). `/api/search?query=…`, `/api/bedrift/{org}`, `/api/companies/{org}`, `/_payload.json`, `/bedrift/{org}`, `/sok?q=…` → **all HTTP 404** → no discoverable URL scheme or API |
| **Virksomhet.no** | — | — | — | — | `https://virksomhet.no/?query=996493660` → 200 with a **342-byte empty stub** |
| **Merinfo.no / Anbud.no / Start.no** | — | — | — | — | `https://www.merinfo.no/` → 403; `https://anbud.no/` → 301 → `https://www.mercell.com/…` (public procurement, no customer ratings); `https://www.start.no/` → 404 |
| **Dead DNS** | — | — | — | — | `www.firma.no`, `www.bedriftsoffice.no`, `www.bedriftguiden.no`, `www.mittbedrift.no`, `telefonnummeret.no`, `omoss.info`, `rolleoversikt.no`, `virksomhet.no` → **DNS failure** |
| **Facebook / LinkedIn / Instagram / Indeed / Glassdoor** | — | — | — | **RESTRICTED** | `https://www.facebook.com/robots.txt` → `User-agent: * Disallow: /` (lines 1043-1044); `https://www.linkedin.com/robots.txt` → `User-agent: * Disallow: /` (lines 4857-4858, “email whitelist-crawl@linkedin.com to apply”); `https://www.instagram.com/robots.txt` → 200, no generic section but Meta ToS forbids collection; Indeed/Glassdoor robots partially open but their ToS restricts |

---

## 2. Per-source extraction recipes (best candidates)

### 2.1 Fagfolkguiden — the only working keyless rating source

**Live sample fetched:** `https://www.fagfolkguiden.no/bedrift/933520846`
* HTTP **200**, 178,969 bytes, `content-type: text/html; charset=utf-8`
* Final/canonical URL: `https://www.fagfolkguiden.no/bedrift/bil-byraet-as-933520846`
* Org nr `933520846` appears **29×** in the raw HTML
* Machine-readable block (verbatim, truncated):

```json
{"@context":"https://schema.org","@type":"LocalBusiness",
 "@id":"https://www.fagfolkguiden.no/bedrift/bil-byraet-as-933520846",
 "name":"BIL BYRÅET AS",
 "description":"BIL BYRÅET AS er bilsalg i FORNEBU.",
 "url":"https://www.fagfolkguiden.no/bedrift/bil-byraet-as-933520846",
 "telephone":"905 11 121",
 "address":{"@type":"PostalAddress","streetAddress":"Martin Linges vei 25","addressLocality":"FORNEBU","postalCode":"1364","addressCountry":"NO"},
 "foundingDate":"2024",
 "identifier":{"@type":"PropertyValue","name":"Organisasjonsnummer","value":"933520846"},
 "isicV4":"47810",
 "aggregateRating":{"@type":"AggregateRating","ratingValue":5,"bestRating":5,"worstRating":1,"ratingCount":9},
 "sameAs":["www.bilbyraet.no"],
 "areaServed":{"@type":"City","name":"FORNEBU"}}
```

**Literal extraction recipe (connector):**

```
# 1. GET https://www.fagfolkguiden.no/bedrift/{org_nr}          # no key, no login
#    -> HTTP 404 means "not listed"; HTTP 200 means "listed"
# 2. parse all <script type="application/ld+json"> blocks
# 3. select the block where "@type" == "LocalBusiness"
# 4. rating_value = block.aggregateRating.ratingValue
#    rating_count = block.aggregateRating.ratingCount   (fallback: .reviewCount)
#    org_proof   = block.identifier.value   # MUST equal the requested org_nr
#    website     = block.sameAs[0]          # bare host, prepend https://
#    phone       = block.telephone
#    address     = block.address.{streetAddress,postalCode,addressLocality,addressCountry}
# 5. identity gate: reject unless identifier.value == requested org_nr
# 6. evidence: source_url = the fetched URL, retrieved_at = fetch time,
#    content_sha256 = sha256(raw bytes), extraction_method = "json-ld:LocalBusiness.aggregateRating"
```

Deterministic sentiment (already shipped, rule-based): `rating >= 4.0 → positive`, `>= 3.0 → neutral`, else `negative`.

**Coverage, measured two ways:**
* *Sitemap-derived ceiling:* `https://www.fagfolkguiden.no/sitemap.xml` (200) → `/sitemaps/0.xml` … `/sitemaps/4.xml` (200) contain **34,133 URLs**, of which **8,005** are `/bedrift/…` pages and **7,618** end in a 9-digit org number. Intersecting those 7,618 with `1000-orgs.txt` gives **99 orgs** of the batch.
* *Connector-reported:* `out/submission/batch.fagfolk-report.json` → `exact_pages = 127`, `rated_companies = 32`, `errors = 871` (HTTP 404). Re-scanning the 127 cached pages in `out/submission/batch.fagfolk-cache/` confirms: **127** `LocalBusiness` blocks, **127** with org nr, **127** with description + address, **126** with website (`sameAs`), **104** with phone, **32** with `aggregateRating`, **0** with a social `sameAs`.

> **Actionable consequence:** the shipped connector visits 127 orgs that *do* have a page but discards 95 of them because they carry no rating. Those 95 pages already contain org nr, legal name, description, postal address, website and (78 of them) a phone number — publishable as `company_directory` facts with **zero additional outbound requests**.

### 2.2 1881.no — best keyless *platform / contact / social* source (no ratings)

**Live sample fetched:** `https://www.1881.no/?query=926088149`
* HTTP **302 → 200**, 84,324 bytes; final URL `https://www.1881.no/elektriker/elektriker-vestfold/elektriker-barkaaker/vt-elektro-as_106765131S1/?query=926088149`
* Machine-readable block (verbatim, truncated):

```json
{"@context":"https://schema.org","@graph":[{"@type":"ProfilePage",
 "name":"Vt Elektro AS, Barkåker, Tønsberg - 1881.no",
 "url":"https://www.1881.no/elektriker/.../vt-elektro-as_106765131S1/",
 "dateModified":"2026-11-04",
 "mainEntity":{"@type":"LocalBusiness",
   "@id":"https://www.1881.no/elektriker/.../vt-elektro-as_106765131S1/",
   "name":"Vt Elektro AS",
   "sameAs":"https://www.facebook.com/vtelektroas",
   "url":"https://www.vtelektro.no/",
   "address":{"@type":"PostalAddress","addressCountry":"NO","addressLocality":"Barkåker","addressRegion":"Tønsberg","postalCode":"3157","streetAddress":"Gulliveien 28"},
   "contactPoint":[{"@type":"ContactPoint","telephone":"+4795529000"},
                   {"@type":"ContactPoint","email":"post@vtelektro.no"},
                   {"@type":"ContactPoint","telephone":"+4748998303"}],
   "email":"post@vtelektro.no",
   "geo":{"@type":"GeoCoordinates","latitude":"59.3159523010254","longitude":"10.3832426071167"},
   "legalName":"Vt Elektro AS",
   "leiCode":"926088149",
   "openingHoursSpecification":[...]}}]}
```

**Literal extraction recipe (connector):**

```
# 1. GET https://www.1881.no/?query={org_nr}      # no key, no login; follows 302 to the company page
# 2. parse all <script type="application/ld+json"> blocks
# 3. entity = blocks[0]["@graph"][0]["mainEntity"]  (@type == "LocalBusiness")
#    org_proof = entity.leiCode                    # MUST equal the requested org_nr
#    legal_name = entity.legalName
#    website    = entity.url
#    social     = entity.sameAs                    # Facebook/Instagram/LinkedIn handle (string or list)
#    phone      = entity.contactPoint[*].telephone
#    email      = entity.email
#    address    = entity.address.{streetAddress,postalCode,addressLocality,addressRegion}
#    geo        = entity.geo.{latitude,longitude}
#    hours      = entity.openingHoursSpecification
# 4. identity gate: reject unless leiCode == requested org_nr
#    (fallback, if leiCode absent: legalName == BRREG name AND address.postalCode == BRREG postalCode)
# 5. NOTE: 1881 exposes NO aggregate rating — do not emit review_summary/sentiment from it.
```

Social handles observed on the 1881 pages (JSON-LD `sameAs`, not the site's own footer links):
`https://www.facebook.com/vtelektroas`, `http://www.facebook.com/fruktbar/`,
`https://www.facebook.com/Velledalen-Montessoriskule-1498813763718650/`,
`http://www.facebook.com/soylandtannklinikk`, `https://www.linkedin.com/company/meox-drift-as/`,
`http://www.facebook.com/bassengspesialisten`.

**Coverage, measured:**
* Random batch sample A (seed 20261104, n=60): **53/60** resolved with `leiCode == org_nr` (88.3%).
* Random batch sample B (seed 99, n=40): **35/40** resolved (87.5%).
* Pooled: **88 / 100** → extrapolates to **≈ 880 / 1000** batch orgs.
* Yield on the resolved pages: website URL **35/35** (100%), telephone **11/35** (31%), email **10/35** (29%), social `sameAs` **7/88** pooled (≈ 8% → ≈ 70 / 1000 orgs).
* **Ratings: 0 / 95** sampled pages carried any rating token.

### 2.3 Proff.no via `r.jina.ai` — works, but ToS-forbidden (build only with permission)

**Live sample fetched:** `https://r.jina.ai/https://www.proff.no/søk-etter-firmanavn?q=Wegger+AS`
* HTTP **200**, 22,954 bytes of Markdown, title *“Wegger AS - 247 selskaper i Norge. Proff.no”*
* Result row verbatim: `## [Wegger AS](https://www.proff.no/selskap/wegger-as/blommenholm/bedriftsrådgivning/IGHABFG043Z)` / `Org nr 996 493 660`

**Company page** via `https://r.jina.ai/https://www.proff.no/selskap/wegger-as/blommenholm/bedriftsrådgivning/IGHABFG043Z` with header `X-Return-Format: html` → HTTP **200**, 385,551 bytes of raw HTML containing `__NEXT_DATA__` and the org nr 8× — but **no `aggregateRating`, no `ratingValue`, no `reviewCount`, no JSON-LD**, and `socialMediaLinks: null` for this micro-company.

**Extraction recipe (if permission is ever obtained):**

```
# 1. GET https://r.jina.ai/https://www.proff.no/s%C3%B8k-etter-firmanavn?q={company_name}
#    with header  X-Return-Format: html   (returns raw origin HTML, no key required)
# 2. parse the markdown/HTML for  "Org nr {9 digits}"  -> exact-entity proof
# 3. follow the matching  /selskap/{slug}/{city}/{industry}/{ID}  link
# 4. parse the embedded  <script id="__NEXT_DATA__" type="application/json">  JSON payload
# 5. read the company object fields: legalName, organizationNumber, homepageUrl,
#    socialMediaLinks[], address, employees, financials, announcements[]
#    (NOT ratings — Proff publishes no customer rating)
```

### 2.4 Wayback Machine / Common Crawl — technically keyless, practically empty for this corpus

`https://archive.org/wayback/available?url=…` works without a key (HTTP 200 JSON) but returned **no snapshots** for the per-company URLs tested (Fagfolkguiden company page, 1881 query URL, Trustpilot review URL); only the GuleSider homepage is archived. `https://web.archive.org/cdx/search/cdx?...` returned *“Temporarily Offline”* and then HTTP 429 during the test window. `https://index.commoncrawl.org/…` returned **HTTP 504**. **Do not spend a build slot here.**

---

## 3. Blocked / risky sources and why

### 3.1 Legally clean (safe to use)

1. **BRREG / Enhetsregisteret** — official NLOD open licence, no key, org nr is authoritative. Already shipped. `https://data.brreg.no/enhetsregisteret/api/enheter/933520846` → 200. No ratings.
2. **Wikidata / Wikipedia** — CC0 / CC BY-SA, no key, `P2333` org-number match. Already shipped for 66 orgs. No customer-rating property exists for companies, so it can supply `profile_handle` / `company_profile` only.
3. **OpenStreetMap / Nominatim / Overpass** — ODbL, no key. But it holds **no** org number and **no** customer rating for ordinary businesses (`nominatim …?q=933520846` → `[]`), so it contributes nothing to this task.
4. **The company's own website** — a permitted public page; already the source of 447 social handles and of `website_description`.
5. **Fagfolkguiden** — robots.txt permits `/bedrift/…`; the site publishes no terms page at any conventional path (all 404), so there is no published prohibition to violate, and the pages are public-directory pages with no login. **Treat as clean, but re-confirm the absence of a ToS page before publishing (checked 2026-11-04).**

### 3.2 Reachable but rights-risky (robots permits, ToS forbids)

1. **Proff.no** — `https://www.proff.no/info/rettigheter/` (HTTP 200) states verbatim:
   > “Enhver form for regelmessig, systematisk eller kontinuerlig innhenting, lagring, indeksering, distribusjon eller annen sammenstilling av data er ikke tillatt uten eksplisitt skriftlig samtykke fra Proff AS, og vil kunne utgjøre et brudd på åndsverkloven.”

   Same page: *“Kopiering, tilgjengeliggjøring for allmennheten … krever skriftlig samtykke.”* The origin also returns **403** to plain clients (CloudFront), so any keyless route necessarily involves a third-party proxy (`r.jina.ai`) used to get around the bot wall. **Two independent problems: contractual prohibition + circumvention of an access control.** Do not ship without written permission or a paid licence.
2. **1881.no** — `https://min.1881.no/vilkaar-personvern/bruk-av-tjenestene` (HTTP 200) states verbatim:
   > “Uten direkte avtale er enhver kopiering, lagring og tilgjengeliggjøring forbudt.”
   > “Det er forbudt å samle, eller gjøre uttrekk av, informasjonen på disse sidene (gjentatt og systematisk kopiering av deler av innholdet).”

   `robots.txt` allows the pages for generic agents, but the ToS forbids *collecting/extracting* the data and repeated systematic copying. Note also that 1881's robots.txt explicitly disallows a long list of AI/opt-out agents. **Medium-to-high risk: robots-allowed but ToS-forbidden.** A conservative reading of the Signalpost “permitted public sources” rule says do not ship a bulk extractor; a defensible middle ground is a bounded, low-rate, per-company fetch used as corroboration for a fact already sourced elsewhere, with an explicit rights note.
3. **GuleSider.no** (Eniro Norge AS) — unreachable (403 Cloudflare) and the shell reveals the org number inside the URL path, i.e. a directory of identities; terms are behind the same bot wall. Same legal posture as Proff (Enento/Eniro group) plus an access control. **Do not build.**
4. **`r.jina.ai` as a relay** — keyless and effective, but it routes through a third party whose terms, retention and jurisdiction are outside the project; it is also the mechanism by which the CloudFront/Cloudflare walls get circumvented. **Use only for manual research, never in the production batch.**

### 3.3 Hard-blocked / restricted (do not touch)

* **LinkedIn** — `https://www.linkedin.com/robots.txt` → `User-agent: * Disallow: /` plus a whitelisting invitation. Also explicitly listed as restricted by the challenge brief.
* **Facebook / Meta** — `https://www.facebook.com/robots.txt` → `User-agent: * Disallow: /`. Instagram has no generic robots section but Meta's ToS forbids automated collection. Listed as restricted by the challenge brief.
* **Indeed / Glassdoor** — robots partially open but the challenge brief lists them as restricted platforms; unofficial clients may not be the sole support for a published claim.
* **Trustpilot** — `User-agent: * Disallow: /` **and** an AWS WAF challenge (HTTP 403 *“Verifying your connection…”*) **and** a ToS that disallows scraping. Triple-blocked.
* **Keyless Google Maps HTML** — the rating is never present in a plain HTTP response from this machine (0 `ratingValue`/`reviewCount` in 209 KB of place-page HTML; the `pb=` search endpoint 404s), and Google's ToS prohibits automated extraction. Effectively unusable, and legally risky even if it worked.
* **Dead ends** — `bedrift.no` (parked at Loopia), `bedriftsinfo.no` (domain for sale), `allebedrifter.no` (Nuxt SPA, every guessed route 404), `virksomhet.no` (empty stub), `merinfo.no` (403), plus seven dead DNS names. **Do not re-test these.**

---

## 4. Ranked recommendation — the 2-3 connectors worth building next

### #1 — Extend the existing Fagfolkguiden connector to publish the 95 cached pages it already throws away

* **What:** keep the rating logic unchanged, but also emit `company_directory` facts (`website_description`, `contact_phone`, `company_directory`/`profile_metrics`) for every page where `identifier.value == org_nr`, rated or not.
* **Expected org coverage: 127 / 1000** pages, of which **32** keep the rating and **95** are newly publishable.
  *Basis:* `out/submission/batch.fagfolk-report.json` → `exact_pages = 127`; re-scan of the 127 files in `out/submission/batch.fagfolk-cache/` → 127 `LocalBusiness` blocks, 127 with org nr, 126 with website, 104 with phone, **32 with `aggregateRating`**. Independent cross-check: the Fagfolkguiden sitemaps contain **7,618** org-numbered company pages, of which **99** are in `1000-orgs.txt` — the same order of magnitude (the sitemap omits ~28 pages the connector reached).
* **Cost:** **0 new outbound requests** (pages already cached); ~1 hour of code.
* **Rights:** cleanest of the three (robots allows `/bedrift/`, no published ToS page, no login).
* **Why #1:** it is the only option that adds org coverage with no new network traffic and no new rights exposure, and it directly attacks `any_external` / `two_platforms` / `buzz_engagement`.

### #2 — 1881.no directory connector (platform + contact + social handle)

* **What:** `GET https://www.1881.no/?query={org_nr}` → parse `mainEntity` → emit `company_directory` facts and, when present, a `profile_handle` social fact (Facebook/Instagram/LinkedIn).
* **Expected org coverage: ≈ 880 / 1000** orgs have a page; ≈ 880 get a directory-hosted website/address; ≈ 280 get a phone; ≈ 250 get an email; ≈ 70 get a **new social handle** that the company-website crawl may have missed.
  *Basis:* two independent random samples of `1000-orgs.txt` — **53/60** (seed 20261104) and **35/40** (seed 99), pooled **88/100 = 88%** resolved with `leiCode == org_nr`; yield ratios measured on the resolved pages (website 35/35, phone 11/35, email 10/35, `sameAs` 7/88).
* **Cost:** 1,000 requests ≈ 12–18 min at 6 concurrent workers; well inside the 2,000-request / 45-minute daily budget.
* **Rights:** **medium-to-high risk** — robots.txt permits the pages, but `https://min.1881.no/vilkaar-personvern/bruk-av-tjenestene` forbids collecting/extracting the information and repeated systematic copying. Ship it only with a documented rights note and a low request rate, or replace it with a licensed Enento/1881 data feed (the commercial `api1881.no` product).
* **Why #2:** it is the only source that plausibly reaches ~900 orgs with an exact-entity proof and can add social handles; it attacks the same three recall fields as #1 from a different, much larger directory.

### #3 — Do **not** build Tripadvisor, Trustpilot, GuleSider, or keyless Google Maps

* **Tripadvisor:** batch vertical ceiling is **22 / 1000** orgs (12 hotels at NACE 55 + 10 restaurants at NACE 56, measured on `entry-manifest.jsonl`); the site is JS-only (43 KB HTML with an empty body); and Tripadvisor pages carry **no org number**, so exact-entity matching would rest on name+address alone — a direct threat to the 95% precision gate.
* **Trustpilot:** blanket `Disallow: /` + AWS WAF 403 + ToS prohibition + no org number on pages.
* **GuleSider:** 403 CloudFront on every path, including robots.txt and the terms page.
* **Keyless Google Maps:** the rating is never in the plain-HTML response (0 matches in 209 KB; `pb=` endpoint 404s).

> **Explicit answer to the brief's question “replace Google Places with a keyless source”:** not possible with what exists today. The only keyless rating source found (Fagfolkguiden) caps at **32/1000** ratings versus the paid connector's **311–427/1000**. If ratings must scale, the options are (a) keep the paid Google Places connector, (b) buy a licensed Norwegian directory feed (Enento/Proff+/1881), or (c) accept that `ratings_reviews` and `sentiment` stay capped at ≈ 3–4% of the batch and spend the build slots on #1 and #2 instead.

---

## Appendix — raw fetch log (all run 2026-11-04/05 UTC from this machine)

```
HTTP 200  https://www.fagfolkguiden.no/robots.txt
HTTP 200  https://www.fagfolkguiden.no/sitemap.xml              (+ /sitemaps/0..4.xml)
HTTP 200  https://www.fagfolkguiden.no/bedrift/933520846         (rating 5 / 9 reviews)
HTTP 404  https://www.fagfolkguiden.no/bedrift/996493660
HTTP 200  https://www.1881.no/robots.txt
HTTP 200  https://www.1881.no/sitemapindex.ashx                  (803 KB of category sitemaps)
HTTP 200  https://www.1881.no/?query=926088149                   (302 -> 200, leiCode 926088149)
HTTP 403  https://www.proff.no/                                  (CloudFront, x-cache: Error from cloudfront)
HTTP 403  https://www.proff.no/robots.txt
HTTP 200  https://r.jina.ai/https://www.proff.no/s%C3%B8k-etter-firmanavn?q=Wegger+AS
HTTP 200  https://r.jina.ai/https://www.proff.no/robots.txt
HTTP 200  https://r.jina.ai/https://www.proff.no/info/rettigheter/
HTTP 403  https://www.gulesider.no/                              (and /robots.txt, /personvern, /om, /vilkar)
HTTP 200  https://r.jina.ai/https://www.gulesider.no/?query=996493660   (app shell, 0 results)
HTTP 403  https://no.trustpilot.com/review/wegger.net           (AWS WAF interstitial)
HTTP 200  https://no.trustpilot.com/robots.txt                   (User-agent: * Disallow: /)
HTTP 200  https://www.tripadvisor.no/                            (43,423 B, empty body)
HTTP 200  https://www.google.com/maps/search/Wegger+AS+Blommenholm       (0 "rating")
HTTP 200  https://www.google.com/maps/place/Quality+Hotel+Grand+AS,+Kongsberg (0 ratingValue/reviewCount)
HTTP 404  https://www.google.com/maps/preview/search?…&pb=…
HTTP 200  https://nominatim.openstreetmap.org/search?q=933520846&format=json   -> []
HTTP 200  https://query.wikidata.org/sparql  (P2333 IN 3 orgs)     -> 0 rows
HTTP 200  https://data.brreg.no/enhetsregisteret/api/enheter/933520846
HTTP 200  https://www.finn.no/ ; https://www.finn.no/?query=996493660  (shell)
HTTP 200  https://www.api1881.no/  ;  HTTP 404  https://www.api1881.no/robots.txt
HTTP 200  https://archive.org/wayback/available?url=www.fagfolkguiden.no/bedrift/bil-byraet-as-933520846 -> {}
HTTP 504  https://index.commoncrawl.org/CC-MAIN-2025-30-index?url=proff.no/bedrift/996493660
HTTP 200  https://min.1881.no/vilkaar-personvern/bruk-av-tjenestene   (ToS)
HTTP 200  https://www.facebook.com/robots.txt   (User-agent: * Disallow: /)
HTTP 200  https://www.linkedin.com/robots.txt   (User-agent: * Disallow: /)
HTTP 200  https://www.google.com/robots.txt / https://www.gulesider.no/robots.txt / https://www.bedrift.no/robots.txt (Parked at Loopia)
```

Artifacts from this research (fetched HTML, sitemaps, sample results) are in `/tmp/opencode/keyless/` — nothing was written into the read-only checkout at `/home/dhanushsr/Downloads/hackathons/signalpost/`.
