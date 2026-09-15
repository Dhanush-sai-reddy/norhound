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
  --profiles <profiles> --envelopes <envelopes> --prefix out/batch --jobs
```

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

## Audit

- `out/batch1000f.labels.jsonl`: 85/85 observations re-verified against frozen
  evidence (domain match, digest match, identity-gate proof, handle linkage).
  Evaluator: entity precision 1.0, metric precision 1.0, unsupported 0,
  coverage any_external 0.038, two_platforms 0.02, workforce_jobs 0.001.
- 120/120 tests pass (`python3 -m unittest discover -s tests`).

## Known limits

- ~892/1000 sampled companies have no findable machine-owned web presence;
  these are legitimately `not_found` for external signals. Jobs/news/activity
  coverage is bounded by the ~38 identity-verified sites in the sample.
- Financial-history PDF connector remains gated: the default batch does not
  capture `financial_history` PDFs, so annual-report workforce observations
  are not produced.