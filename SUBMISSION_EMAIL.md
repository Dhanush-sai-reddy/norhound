Subject: Signalpost submission — NorHound Company Research Agent (commit 427a3b6)

Hi,

Submitting the NorHound agent for the Signalpost challenge.

REPOSITORY
https://github.com/Dhanush-sai-reddy/norhound

COMMIT HASH
427a3b6ce8086a13d2d15fd0b9f3188f89856ccb

ONE COMMAND TO RUN
  uv run python scripts/run_one_shot.py \
    --out out/submission \
    --external-data "out/proff-ratings.external.jsonl"

The command runs the full pipeline: base batch (BRREG registry + verified website crawl), external footprint (jobs, reviews, keyless connectors, NAV index, Wikidata), verify-and-label against frozen evidence, evaluation, deterministic summaries, and builds the static viewer. All required artifacts land in out/submission/: profiles/envelopes (1000 companies), manifest.jsonl (organisation numbers), observations.jsonl (~25k verified), summaries.jsonl, eval.json and the site/ viewer.

WHAT'S NEW IN THIS REVISION (vs 97a43bf)
- Useful summaries: deterministic per-company answers (what it does, financial trend, staff, hiring) with source links and explicit "not available" states — 1000/1000 produced, zero model cost.
- Ease of use: searchable/sortable directory, company pages with five-area completeness badges, published-identity audit banner, compare view, per-company PDF print and JSON download, bulk JSON/CSV export page.
- Broader discovery: 24-deep priority-link crawl of verified company sites (152 job postings, 7 dated news pages, 324 social handles), Fagfolkguiden review pages with ratings and derived sentiment (32 companies), Proff.no financial/credit data (60 companies), NAV job-feed index (14 companies), Wikidata/Wikipedia profiles and handles (6 companies).
- Exact-entity precision: 1.0 entity precision, 1.0 metric precision, 0 wrong-company publications across 24,951 published observations.

MODELS / APIs / LICENCES
- No LLMs or paid models. All extraction is deterministic/rule-based.
- Sources: Brønnøysund Enhetsregisteret + Regnskapsregisteret (NLOD open licence), company websites (permitted public pages), NAV Arbeidsplassen job feed, Wikidata (CC0), Fagfolkguiden public directory pages, Proff.no public pages.
- Apify platform used for hosted scraper runs (Proff.no connector); all other use is direct public APIs/pages.

EXPECTED COST PER 100-COMPANY RUN
- API calls: ~2 requests/company average (registry + site + external connectors), within the 2,000-request budget.
- External spend: $0–0.50 per 100 companies (Apify free-tier covers the small Proff.no volume; other sources are free/open).
- Runtime: ~45 minutes for 100 companies including crawl politeness delays.

CONTACT
Dhanush Sai Reddy
(Registered on Unstop as Dhanush-sai-reddy)

Regards,
Dhanush