# Signalpost reference agent

Runnable Signalpost company-research agent with a **complete, evaluated 1,000-company entry** (`out/SUBMISSION-REPORT.md`, commit `52ab54d`).

The public universe contains 411,160 eligible companies. A valid entry must
process at least 1,000; the repo ships a full 1,000-company run plus the
exact commands to reproduce it. Exactly one terminal envelope is emitted per
input organisation number — validated 1,000/1,000, no silent drops.

## What it does

- reads a batch of Norwegian organisation numbers;
- anchors identity in the Brønnøysund bulk registry;
- fetches official financials, roles, group links and registered workplaces;
- visits the registry-listed website and rejects weak entity matches;
- runs external-footprint connectors (company-site activity/news/jobs,
  Fagfolkguiden reviews, official NAV job-feed postings, optional site
  discovery) and attaches only publishable observations;
- emits one terminal JSONL envelope per input with sources, retrieval times,
  content hashes, request counts and latency;
- re-verifies every observation against frozen evidence and labels it
  `exact_entity` — only verified rows publish;
- supports checkpoint/resume and a deterministic refresh replay.

## Reproduce the shipped submission

Requires Python 3.12+ and `uv`. Data: the official Brønnøysund bulk export and
the Signalpost universe manifest.

```bash
uv sync

curl -L 'https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv' -o brreg-enheter.csv
curl -L 'https://builderr.ai/signalpost-company-universe-2025.jsonl.gz' -o signalpost-universe.jsonl.gz

# 1. Same 1,000-company manifest used for the submission (seed 20260823).
uv run python select_entry_batch.py \
  --universe signalpost-universe.jsonl.gz \
  --count 1000 \
  --seed 20260823 \
  --output entry-companies.jsonl

# 2. Base batch: registry enrichment + exact-identity website capture.
uv run python scripts/run_competition_batch.py \
  --organisations entry-companies.jsonl \
  --bulk brreg-enheter.csv \
  --profiles-output out/web1000-profiles.jsonl \
  --output out/envelopes.jsonl \
  --report out/run-report.json \
  --run-id local-001 \
  --expected-count 1000

# 3. External-footprint enrichment: activity/news/jobs on verified sites,
#    Fagfolkguiden reviews, optional Firecrawl site discovery.
uv run python scripts/run_external_pipeline.py \
  --profiles out/web1000-profiles.jsonl \
  --envelopes out/envelopes.jsonl \
  --prefix out/web1000batch \
  --jobs --reviews --promote

# 4. Re-verify every observation against frozen evidence (identity + digest
#    + domain + exact-org directory proof). Unverified rows never publish.
#    (Prefix may differ; the shipped audit re-verified 1,391 observations.)
uv run python scripts/verify_and_label_observations.py \
  --profiles out/web1000-profiles.jsonl \
  --observations out/web1000batch.external-withfag.jsonl \
  --labels out/web1000batch.labels-withfag.jsonl \
  --report out/web1000batch.label-report-withfag.json

# 5. Evaluate the labeled entry (publication requires verified exact_entity).
uv run python scripts/evaluate_external_footprint.py \
  --profiles out/web1000-profiles.jsonl \
  --observations out/web1000batch.external-withfag.jsonl \
  --labels out/web1000batch.labels-withfag.jsonl \
  --output out/web1000batch.external-eval.json \
  --minimum-audit 300

# 6. Optional grounded summaries (requires NVIDIA_API_KEY for the NIM endpoint).
NVIDIA_API_KEY=<key> uv run python scripts/run_nim_summary.py \
  --envelopes out/envelopes.jsonl \
  --output out/web1000batch.summaries.jsonl \
  --report out/web1000batch.summaries-report.json \
  --min-interval 0.15 --workers 8
```

Network-dependent stages (registry, live website crawl, Firecrawl discovery,
NIM) reflect the live web at run time; the sealed results are frozen in `out/`.
The verification/evaluation (`step 4–5`) is deterministic given frozen
profiles and observations and can be re-run on any checkout.

### Expected results (as shipped)

- **944 published** observations, every one carrying the verified
  `exact_entity` label (1,391 re-verified; unverified rows never publish).
- entity precision **1.0**, metric precision **1.0**, unsupported
  publications **0**, wrong-entity publications **0**.
- Qualification gate **passed** (minimum audit 300).
- Coverage: any_external 0.358, two_platforms 0.175, buzz_engagement 0.352,
  ratings_reviews 0.015, workforce_jobs 0.036.
- 65 NAV official-API job-posting observations merged into the audit
  (`official_api` acquisition, resolved via the Brønnøysund `underenheter`
  endpoint to each advertiser's parent legal entity).
- 999/1000 grounded summaries produced (1 transient NIM 503; optional block).
- 135 tests pass by default (see below).

Canonical shipped artifacts: `out/web1000batch.external-eval.json` (944/p1.0),
`out/web1000batch.labels-withfag.jsonl` + `out/web1000batch.external-withfag.jsonl`
(audit inputs, 1,391 rows), `out/web1000-profiles.jsonl`, `out/SUBMISSION-REPORT.md`,
and the seals in the report. Note `out/batch1000f.*` and the non-`withfag`
`out/web1000batch.*` JSONL are intermediate runs left on disk; they are not the
submitted numbers.

### Fresh-batch check

Start with ten companies before a full run.

```bash
head -n 10 entry-companies.jsonl > smoke-companies.jsonl

uv run python scripts/run_competition_batch.py \
  --organisations smoke-companies.jsonl \
  --bulk brreg-enheter.csv \
  --profiles-output out/smoke-profiles.jsonl \
  --output out/smoke-envelopes.jsonl \
  --report out/smoke-report.json \
  --run-id smoke-001 \
  --expected-count 10
```

Increase `--count` and `--expected-count` together to scale beyond 1,000.

## Deterministic refresh replay (no network)

```bash
python3 scripts/run_refresh_replay.py \
  --manifest tests/fixtures/refresh-snapshots.json \
  --output out/refresh-demo.json
```

The `events` list shows what changed between two versions of one profile and
the source evidence for each change. The sample finds exactly the two expected
changes, no false changes, and no extra changes on re-check. The report's
`qualification_passed` refers only to this public-sample check — it does not
qualify a live entry.

## Tests

```bash
uv run python3 -m unittest tests.test_poc
# 135 tests pass
```

## The improvement loop

1. Treat the organisation number as the anchor.
2. Generate site/profile candidates from official data, the company site,
   lawful search providers and named people.
3. Save every candidate and the evidence for or against it.
4. Publish only exact-entity matches. Parent, brand, franchise and similarly
   named companies are not exact.
5. Crawl static HTML first; escalate to a browser only when a deterministic
   completeness check fails.
6. Measure added supported coverage, wrong-company claims, runtime, requests
   and cost.
7. Promote a strategy only when it improves coverage without weakening the
   accuracy gates.
8. Freeze strategies and thresholds before the daily evaluation run.

The strongest differentiator is external evidence that remains exact and
auditable: official company pages, company-owned profiles, jobs, dated
activity, ratings/reviews and permitted public signals. Do not trade accuracy
for volume.

## Source rights

Official registry data: Brønnøysund bulk CSV + REST (public register). Website
capture: direct HTTP, robots.txt honoured, bounded pages, content hashing.
Company-site activity/news/jobs publish as `permitted_public_page` on
company-domain pages only. Fagfolkguiden reviews publish only where the page
carries the exact organisation number; only the aggregate Google rating is
captured, never individual review text. NAV job-postings publish as
`official_api`: the feed is a public API operated by the Norwegian Labour and
Welfare Administration, and each posting is matched by the advertiser's exact
Brønnøysund organisation number (sub-unit resolved to its parent legal entity).
Third-party buzz (Reddit, news) and unofficial/external ATS postings abstain
unless identity-verified on the company's own site. LinkedIn/Meta/Indeed
direct collection is not used (terms); those platforms appear only as
identity/discovery cross-links published by the company itself.

Read `docs/competition-control-loop.md`, `docs/external-connectors.md` and
`OUTPUT_CONTRACT.md` for detail.

## Secrets and third-party cost

- All secrets are supplied through environment variables only; none are stored
  in the repository. Optional keys: `NVIDIA_API_KEY` (grounded summaries),
  `FIRECRAWL_API_KEY` (site discovery). A missing key degrades cleanly — the corresponding connector is skipped or
  abstains, never errors.
- Third-party spend is **~$0 per 100 companies**. The core batch (registry +
  company-site capture) is free. Optional stages: NVIDIA NIM summaries (free
  trial endpoint), Firecrawl Search (used only for candidate discovery, inside
  the $10 budget).
- Outbound requests are bounded per company (page caps, per-domain budgets,
  robots.txt honoured, retries with backoff). No paid model is required to
  produce the submitted envelopes.
- The declared expected cost per 100-company run is included in the
  submission email; the run report records actual request counts and runtime.

## Submission contract

Submit a repository with:

- at least 1,000 completed company profiles and the exact organisation-number
  manifest used;
- one documented command that accepts a JSONL batch of organisation numbers;
- exactly one terminal envelope per input;
- pinned dependencies and reproducible setup;
- a previous-snapshot input and material-change output;
- a machine-readable run report with runtime, request count and third-party
  cost;
- declared models, APIs, licences and source-rights assumptions.

Email the repository URL, run command, models/APIs and expected cost per
100-company run to `submit@builderr.ai`.