# NorHound company research agent

Runnable company-research agent for Norwegian organisation numbers, with a
**complete, evaluated 1,000-company run** (`out/SUBMISSION-REPORT.md`).

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
  Wikidata company profiles, registry contacts/structure, dated registry feed,
  sitemap lastmod, official NAV job-feed postings) and attaches only
  publishable observations;
- emits one terminal JSONL envelope per input with sources, retrieval times,
  content hashes, request counts and latency;
- re-verifies every observation against frozen evidence and labels it
  `exact_entity` — only verified rows publish;
- supports checkpoint/resume and a deterministic refresh replay.

## Reproduce the shipped submission

### One command (recommended — `norhound_live.sh`)

Everything the submission needs — manifest, base batch, external connectors
(company-site activity/news/jobs, Wikidata, registry contacts/structure/updates,
sitemap lastmod, dated registry feed, Fagfolkguiden reviews, official NAV job
feed, GLEIF, Google News RSS, Kunngjoringer), verification, evaluation,
deterministic summaries, and the searchable viewer — runs from a single
command. It is fully live and credential-free: no pre-built files, no API
keys, no Apify, no Google Places. Collects everything from public sources
within the 45-minute / 2,000-request per 100-company budget.

```bash
bash scripts/norhound_live.sh
```

With an evaluator-supplied batch file:

```bash
bash scripts/norhound_live.sh /path/to/official-batch.jsonl
```

It prints a final scorecard and writes the viewer to `out/norhound-site/`.
Inside Docker the same script is the `norhound-full` entrypoint, so the grader
needs only `docker compose run --rm norhound-full`.

Useful knobs:

```bash
# Dry run (10 companies) — same chain, fewer companies
SMOKE=1 bash scripts/norhound_live.sh

# Smaller full-fidelity run
COUNT=100 bash scripts/norhound_live.sh

# Re-run verify/eval independently
VERIFY_RECHECK=1 bash scripts/norhound_live.sh

# Reuse cached data/ inputs
SKIP_DOWNLOAD=1 bash scripts/norhound_live.sh

# Per-connector timeout cap (default 3600s exceeds the 45-min budget)
NORHOUND_STAGE_TIMEOUT_S=900 bash scripts/norhound_live.sh
```

Re-running the same command is how refresh history is produced: before the run
overwrites anything it copies the previous `<prefix>-envelopes.jsonl` to
`<prefix>-envelopes.prev.jsonl` and passes it to `run_competition_batch.py
--previous-envelopes`, so the emitted envelopes keep the earlier version of
each profile and gain `refresh`/`changes` events. The first run records a
baseline with no change events, which is the correct result for a first run.
`scripts/run_refresh_replay.py` replays a frozen fixture for auditing this
diff; it is a test harness, not a pipeline stage.

Each connector subprocess is bounded by `NORHOUND_STAGE_TIMEOUT_S` (default
3600) and is killed as a process group, so a stalled site can no longer block
the pipeline indefinitely. Note the default exceeds the 45-minute per-100-company
budget, so lower it for an official batch.

### Alternative: One-shot Python runner (`run_one_shot.py`)

The same pipeline is available as a single Python command, also fully live
and credential-free:

```bash
uv run python scripts/run_one_shot.py --out out/submission
```

One-time index builds (free, run once before the first submission):

```bash
uv run python scripts/run_wikidata_connector.py --build-index --organisations data/entry-manifest.jsonl --index data/wikidata-index.jsonl --workers 24
uv run python scripts/run_nav_job_feed_connector.py --build-index --index data/nav-job-index.jsonl --days 183 --workers 24
uv run python scripts/run_nav_job_feed_connector.py --resolve-parents --index data/nav-job-index.jsonl --workers 24
```

It prints a final scorecard and writes the viewer to `out/submission/`.

---

### Alternative: Multi-step live script (deprecated in favor of `norhound_live.sh`)

The multi-step commands below are kept for debugging individual stages. The
single `bash scripts/norhound_live.sh` command above runs the same chain and
is the recommended entry point.

### Container (no local setup required)

Everything (Python 3.12, `uv`, dependencies) is pinned inside the image, so the
grader needs only Docker — nothing installed on the host. Run it from this
folder:

```bash
docker compose up                 # offline saved-data proof (a few seconds)
docker compose run --rm norhound  # same check, explicit
```

```bash
docker compose build               # one-time image build
docker compose run --rm norhound-full   # full live pipeline (registry download +
                                        # 1000-company crawl + external pipeline)
```

`COUNT`/`EXPECTED` defaults to 1000 (the publicity guard rejects smaller
manifests); scale is set via `docker compose run -e COUNT=... norhound-full`
where supported. Downloaded data and crawl output stay on the host in the
`norhound-data` / `norhound-out` volumes so a run survives container teardown.
The same scripts/commands below run inside the container, unchanged.

### Official run (evaluator-supplied batch)

One command researches exactly the organisations in the file the evaluator
supplies — the agent never substitutes a list of its own, and the expected
envelope count is read from that file:

```bash
bash scripts/norhound_live.sh /path/to/official-batch.jsonl
```

The batch file may be JSONL, a JSON array, or plain text of organisation
numbers; every format `read_organisation_inputs()` accepts is read the same
way the batch runner reads it, so one terminal envelope is produced per input
organisation and the count check is derived rather than declared.

### Native (Python 3.12+ and `uv` installed)

Requires Python 3.12+ and `uv`. Data: the official Brønnøysund bulk export and
the company-universe manifest. The single `bash scripts/norhound_live.sh`
command above runs the same chain; the multi-step commands below are kept for
debugging individual stages.

```bash
uv sync

curl -L 'https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv' -o brreg-enheter.csv
curl -L 'https://builderr.ai/signalpost-company-universe-2025.jsonl.gz' -o norhound-universe.jsonl.gz

# 1. Same 1,000-company manifest used for the submission (seed 20260823).
#    --website-only reproduces the shipped entry-web1000.jsonl exactly.
#    --bulk validates against the live registry and auto-replaces any org
#    numbers that left the register since the universe snapshot.
uv run python select_entry_batch.py \
  --universe norhound-universe.jsonl.gz \
  --count 1000 \
  --seed 20260823 \
  --website-only \
  --bulk brreg-enheter.csv \
  --output entry-web1000.jsonl

# 2. Base batch: registry enrichment + exact-identity website capture.
uv run python scripts/run_competition_batch.py \
  --organisations entry-web1000.jsonl \
  --bulk brreg-enheter.csv \
  --profiles-output out/web1000-profiles.jsonl \
  --output out/envelopes.jsonl \
  --report out/run-report.json \
  --run-id local-001 \
  --expected-count 1000

# 3. External-footprint enrichment: all free, keyless connectors (live, no API keys).
#    --keyless runs contacts, site description, substructure, sitemap, registry
#    feed, Wikidata; --nav runs the official NAV job feed; --reviews runs
#    Fagfolkguiden; --jobs runs company-site job extraction;
#    --google-news and --kunngjoring add dated official activity.
uv run python scripts/run_external_pipeline.py \
  --profiles out/web1000-profiles.jsonl \
  --envelopes out/envelopes.jsonl \
  --prefix out/web1000batch \
  --jobs --reviews --keyless --nav --google-news --kunngjoring --gleif \
  --nav-index data/nav-job-index.jsonl \
  --wikidata-index data/wikidata-index.jsonl

# 4. Re-verify every observation against frozen evidence (identity + digest
#    + domain + exact-org directory proof). Unverified rows never publish.
uv run python scripts/verify_and_label_observations.py \
  --profiles out/web1000-profiles.jsonl \
  --observations out/web1000batch.external.jsonl \
  --labels out/web1000batch.labels.jsonl \
  --report out/web1000batch.label-report.json

# 5. Evaluate the labeled entry (publication requires verified exact_entity).
uv run python scripts/evaluate_external_footprint.py \
  --profiles out/web1000-profiles.jsonl \
  --observations out/web1000batch.external.jsonl \
  --labels out/web1000batch.labels.jsonl \
  --output out/web1000batch.external-eval.json \
  --minimum-audit 300

# 6. Deterministic grounded summaries (no API key, no model calls) plus a
#    static site you can open over file://.
uv run python scripts/build_deterministic_summaries.py \
  --envelopes out/envelopes.jsonl \
  --output out/summaries.jsonl \
  --report out/summaries-report.json
uv run python scripts/build_static_site.py \
  --envelopes out/envelopes.jsonl --summaries out/summaries.jsonl \
  --labels out/web1000batch.labels.jsonl --observations out/web1000batch.external.jsonl \
  --out out/site
```

Network-dependent stages (registry, live website crawl, Firecrawl discovery)
reflect the live web at run time; the sealed results are frozen in `out/`.
The verification/evaluation (`step 4–5`) is deterministic given frozen
profiles and observations and can be re-run on any checkout.

### Expected results (as shipped)

- **Published observations** every one carrying the verified `exact_entity`
  label (1,391+ re-verified; unverified rows never publish).
- entity precision **1.0**, metric precision **1.0**, unsupported
  publications **0**, wrong-entity publications **0**.
- Qualification gate **passed** (minimum audit 300).
- 65 NAV official-API job-posting observations merged into the audit
  (`official_api` acquisition, resolved via the Brønnøysund `underenheter`
  endpoint to each advertiser's parent legal entity). A live chain re-check
  (2026-09-22) re-confirmed the feed detail carries `employer.orgnr`.
- Deterministic, no-API-key summaries produced for every profile with
  evidence (answers carry confidence and citation-integrity validation); a
  static site renders the directory and per-company pages over `file://`.
- 199 tests pass by default (see below).

Canonical shipped artifacts: `out/web1000batch.external-eval.json` (944/p1.0),
`out/web1000batch.labels.jsonl` + `out/web1000batch.external.jsonl`
(audit inputs), `out/web1000-profiles.jsonl`, `out/SUBMISSION-REPORT.md`,
and the seals in the report.

### Fresh-batch check

Start with ten companies before a full run.

```bash
head -n 10 entry-web1000.jsonl > smoke-companies.jsonl

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
uv run python3 -m unittest discover -s tests -p "test_*.py"
# 199 tests pass
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
  in the repository. The shipped revision needs **no API keys**: summaries are
  deterministic and all external connectors use free public sources. Optional
  keys exist only for legacy/optional connectors and degrade cleanly when
  absent (`NVIDIA_API_KEY`, `FIRECRAWL_API_KEY`).
- Third-party spend is **~$0 per 100 companies**. The core batch (registry +
  company-site capture) is free; waste connectors (Wikidata/Wikipedia CC0,
  Brønnøysund REST + registry feed, NAV public job-feed token, sitemaps) are
  free public/government sources.
- Outbound requests are bounded per company (page caps, per-domain budgets,
  robots.txt honoured, retries with backoff). No paid model is required to
  produce the submitted envelopes.
- The declared expected cost per 100-company run is included in the
  submission email; the run report records actual request counts and runtime.

## Submission contract

Submit a repository with:

- at least 1,000 completed company profiles and the exact organisation-number
  manifest used;
- one documented command that accepts a JSONL batch of organisation numbers:
  `bash scripts/norhound_live.sh <batch.jsonl>` (the batch argument is the
  evaluator's file; without it the script builds a self-contained manifest);
- exactly one terminal envelope per input;
- pinned dependencies and reproducible setup;
- a previous-snapshot input and material-change output;
- a machine-readable run report with runtime, request count and third-party
  cost;
- declared models, APIs, licences and source-rights assumptions.

Email the repository URL, run command, models/APIs and expected cost per
100-company run to the contest intake address.