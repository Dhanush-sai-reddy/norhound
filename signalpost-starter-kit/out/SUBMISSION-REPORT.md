# Signalpost submission report — 1,000-company entry run

Run id: `entry-1000` (base profiles) + `batch1000f` (external footprint enrichment)
Generated from frozen outputs in `out/`.

## Input manifest

- `entry-companies.jsonl` — 1,000 organisation numbers, drawn from the official
  universe sample (`select_entry_batch.py --count 1000`, seed 20260823), one
  replacement for an org number absent from the bulk Brønnøysund register export.
- Organisation numbers match the `brreg-enheter.csv` bulk export used for registry
  enrichment; universe row counts confined to known 411,160-row pool.

## Run command (single documented command)

```
python3 scripts/run_competition_batch.py \
  --organisations entry-companies.jsonl \
  --bulk brreg-enheter.csv \
  --profiles-output out/profiles.jsonl \
  --output out/envelopes.jsonl

# then, for the externally-audited enrichment stage:
python3 scripts/run_external_pipeline.py \
  --profiles <profiles> --envelopes <envelopes> --prefix out/batch --jobs [--reviews] [--synthesize]
```

Optional grounded summaries run on the enriched envelopes:

```
NVIDIA_API_KEY=<key> python3 scripts/run_nim_summary.py \
  --envelopes <envelopes> --output out/<prefix>.summaries.jsonl \
  --report out/<prefix>.summaries-report.json --min-interval 0.15 --workers 8
```

Resumable: `--resume` re-runs only organisations not already summarized.

Both accept an arbitrary JSONL batch of organisation numbers. Exactly one
terminal envelope per input (validated: 1,000/1,000, no silent drops).

## Outputs

- `out/1000-envelopes-fulfilled.jsonl` — 1,000 terminal envelopes. 38 carry
  `profile.evidence.external_observations` (85 accepted observations, 0
  rejected). Envelope schema follows `OUTPUT_CONTRACT.md`.
- `out/1000-profiles-with-retry.jsonl` — profile set incl. discovery-promoted sites.
- `out/batch1000f.{activity,news,jobs,external}.jsonl` — connector outputs.
- `out/batch1000f.external-eval.json` — coverage evaluation.
- `out/batch1000f.labels.jsonl` + `batch1000f.labels-worksheet.md` — audit labels.
- `out/1000-report.json` — batch runner report (validation passed).

## Runtime and request count

| Stage | Runtime | Requests | Notes |
|-------|---------|----------|-------|
| Base 1000-company batch (registry+website) | 11.5 min | 5,698 HTTP | p50 891 ms, p95 954 ms; checkpoint/resume-safe |
| External activity/news/jobs | local | 0 additional network for activity/news; jobs connector fetches careers pages only on the 38 verified sites | bounded by robots + page caps |
| Site discovery (Firecrawl Search API) | ~47 min | 656 search queries + probes (248 retried after 429; 3 identity-verified sites promoted) | search output not persisted; only independently crawled exact-entity pages are publishable |

Total third-party API cost basis: **~$0 per 100 companies**. No paid model or
API is required. The only third-party dependency is the optional Firecrawl
Search API used by site discovery; at ~656 queries per 1,000 companies it
stays within the 2,000-request / $10 budget envelope but is unnecessary for
coverage — crawling runs over direct company-site HTTP.

## Connector and rights declaration

- Registry, locations, roles, group, financials, accounting obligation,
  registry-live: public Brønnøysund register (CC/public, bulk CSV + REST).
- Website capture: direct HTTP, robots.txt honoured, bounded pages, content
  hashing; only exact-identity sites publish observations.
- Company-site activity, news, jobs: `permitted_public_page` on company-domain
  pages only (company-owned evidence). External ATS postings and third-party
  buzz abstain. Social handles published only when the identity gate verified
  them on the exact company site (`profile_handle`).
- Site discovery: Firecrawl Search as candidate discovery; directories
  (proff.no, purehelp.no, LinkedIn, Facebook, etc.) are blocked as discovery
  targets. Only independently fetched, identity-verified pages can promote a site.
- LinkedIn/Meta/Indeed direct collection: not used (terms). Used as
  identity/discovery cross-links only where published by the company itself.
- Fagfolkguiden reviews: permitted public directory page carrying the exact
  organisation number; embedded Google aggregate rating captured as
  `customer_review` evidence with hashed page content. Rights note recorded in
  the observation; no individual review text is stored.
- Grounded summaries: optional NVIDIA NIM
  (`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`, OpenAI-compatible
  endpoint, free-trial key). The model restates only verified envelope
  evidence; it never invents fields or decides identity. 999/1000 summaries
  produced; 1 transient 503 left un-summarized (non-qualifying, optional
  block).

## Audit

- `out/web1000batch.labels-withfag.jsonl`: 1,326 observations re-verified
  against frozen evidence (domain match, digest match, exact-org directory
  proof, identity-gate proof, handle linkage). Publication requires the
  verified `exact_entity` label — unverified rows are never published.
  Evaluator: published 879, entity precision 1.0, metric precision 1.0,
  unsupported 0, coverage any_external 0.352, two_platforms 0.171,
  ratings_reviews 0.015, buzz_engagement 0.352; qualification gate true.
- 142 tests pass (`python3 -m unittest tests.test_poc`).

## Known limits

- ~892/1000 sampled companies have no findable machine-owned web presence;
  these are legitimately `not_found` for external signals. Jobs/news/activity
  coverage is bounded by the ~38 identity-verified sites in the sample.
- Financial-history PDF connector remains gated: the default batch does not
  capture `financial_history` PDFs, so annual-report workforce observations
  are not produced.
- Fagfolkguiden listed only 125/1000 companies; 31 had an embedded Google
  aggregate rating. Review-bearing rows for organisations whose company-site
  identity gate did not publish are excluded (wrong-company protection).