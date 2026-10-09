Subject: Signalpost submission — NorHound Company Research Agent (commit d9d08b4)

Hi,

Submitting the NorHound agent for the Signalpost challenge.

REPOSITORY
https://github.com/Dhanush-sai-reddy/norhound

COMMIT HASH
d9d08b4c8086a13d2d15fd0b9f3188f89856ccb

ONE COMMAND TO RUN
  uv run python scripts/run_one_shot.py \
    --out out/submission \
    --external-data "out/gplaces-reviews.jsonl,out/site-social-handles.jsonl,out/company-feed-news.jsonl,out/company-article-dates.jsonl,out/finn-jobs.external.jsonl,out/ats-jobs.external.jsonl,out/probed-site-signals.jsonl,out/registry-workforce.jsonl,out/wikidata-ext.jsonl,out/gleif-ext.jsonl,out/norwegian-news-rss.jsonl,out/gate474.sitedesc.jsonl,out/gate474.sitemap.jsonl,out/gate474.news.jsonl,out/gate474.handles.jsonl"

The command runs the full pipeline: base batch (BRREG registry + verified website crawl), external footprint (jobs, reviews, keyless connectors, NAV index, Wikidata, Google Places, Fagfolkguiden reviews, gate474 gated-website extractors), verification-and-label against frozen evidence with wrong-company purge, evaluation, deterministic summaries, and builds the static viewer. All required artifacts land in out/submission/: profiles/envelopes (1000 companies), manifest.jsonl (organisation numbers), observations.jsonl (~33k verified), summaries.jsonl, eval.json and the site/ viewer.

WHAT'S NEW IN THIS REVISION (vs 97a43bf)
- Useful summaries: deterministic per-company answers (what it does, financial trend, staff, hiring) with source links and explicit "not available" states — 1000/1000 produced, zero model cost.
- Ease of use: searchable/sortable directory, company pages with five-area completeness badges, published-identity audit banner, compare view, per-company PDF print and JSON download, bulk JSON/CSV export page.
- Broader discovery: 24-deep priority-link crawl of verified company sites (152 job postings, 129 dated news pages, 447 social handles), Google Places API data (1897 rows, +5.72 recall), Fagfolkguiden review pages with ratings and derived sentiment (32 companies), Proff.no financial/credit data (60 companies), NAV job-feed index (14 companies), Wikidata/Wikipedia profiles and handles (66 orgs), deterministic gated-website extraction (gate474, 37 new publishable sites).
- Exact-entity precision: 1.0 entity precision, 1.0 metric precision, 0 wrong-company publications across 32490 published observations.

MODELS / APIs / LICENCES
- No LLMs or paid models. All extraction is deterministic/rule-based.
- Sources: Brønnøysund Enhetsregisteret + Regnskapsregisteret (NLOD open licence), company websites (permitted public pages), NAV Arbeidsplassen job feed, Google Maps Platform Places API (New) (key: GOOGLE_PLACES_KEY, expected cost ~$3.50/100 companies; credential-free fallback still qualifies ~75/100), Wikidata (CC0), Fagfolkguiden public directory pages, Proff.no public pages.
- Apify platform used for hosted scraper runs (Proff.no connector); all other use is direct public APIs/pages.

EXPECTED COST PER 100-COMPANY RUN
- API calls: ~2 requests/company average (registry + site + external connectors), within the 2,000-request budget.
- External spend: ~$3.50 per 100 companies (Google Places dominates; all other sources free/open).
- Runtime: ~45 minutes for 100 companies including crawl politeness delays.

CONTACT
Dhanush Sai Reddy
(Registered on Unstop as Dhanush-sai-reddy)

Regards,
Dhanush