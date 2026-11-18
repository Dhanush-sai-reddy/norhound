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

### The evaluator's command — `run_official_batch.sh`

This is the command named in the submission email. It takes a JSONL batch of
organisation numbers and produces one terminal envelope per input, the refresh
history and the machine-readable run report:

```bash
uv run playwright install chromium     # one-time, for the browser rescue stage
scripts/run_official_batch.sh --batch organisations.jsonl
```

`organisations.jsonl` holds one organisation number per line, either as a bare
number or as an object with `"organisation_number"`.

| Flag | What it does |
|---|---|
| `--batch PATH` | the organisation numbers to research (required) |
| `--previous-envelopes PATH` | the prior snapshot: every envelope then carries the refresh metadata and the material changes since that run |
| `--out-dir PATH`, `--run-id ID` | where the run writes and how it is named |
| `--rebuild-indexes` | rebuild the NAV job-feed and Wikidata indexes from their live sources instead of using the frozen copies in `data/`. The rebuild also re-keys the NAV index to the parent company of each advertising sub-unit (`--resolve-parents`); without that step the NAV postings fall from 52 companies to 3 in a 1,000-company run |
| `--workers N`, `--min-audit N` | parallelism and the minimum number of audited observations |

Outputs:

| Artifact | What it is |
|---|---|
| `out/run-<run-id>/envelopes-final.jsonl` | one terminal envelope per input company |
| `out/run-<run-id>/official-run-report.json` | runtime, request count, third-party cost, identity precision, declared source rights |
| `out/run-<run-id>/refresh-report.json` | the changes found against the previous snapshot, and the changes preserved |

### The local 1,000-company run — `run_full_batch.sh`

The same pipeline, selecting its own batch (seed 20260823, identical to the
shipped manifest):

```bash
scripts/run_full_batch.sh
```

It runs all 14 stages in order: select the 1,000-company manifest, registry
enrichment with exact-identity website capture, the headless-browser rescue of
unreadable homepages, every keyless connector (NAV job feed, Wikidata,
Fagfolkguiden, Brønnøysund announcements, public ATS feeds), the wrong-company
purge, re-verification against frozen evidence, evaluation, terminal contract
envelopes, deterministic summaries, the static viewer and the recall
measurement. Optional overrides: `COUNT`, `RUN_ID`, `WORKERS`,
`WORKFORCE_WORKERS`, `MIN_AUDIT`, `ENTRY_MANIFEST`.

### Historical paths (kept for debugging, not the submission)

`scripts/run_one_shot.py` and `scripts/norhound_live.sh` are the earlier
drivers. They expect precomputed external files and still mention sources the
current pipeline no longer uses (Google Places rows, Finn job files), so they
are **not** the reproducible path: use `run_official_batch.sh` for the
evaluator and `run_full_batch.sh` for a local 1,000-company run.

---

### Alternative: Multi-step live script (`norhound_live.sh`)

For debugging individual stages, the multi-step live script is also available:

```bash
bash scripts/norhound_live.sh
```

Useful knobs:

```bash
SMOKE=1 bash scripts/norhound_live.sh          # 10-company dry run of the same chain
COUNT=100 bash scripts/norhound_live.sh        # smaller full-fidelity run
VERIFY_RECHECK=1 bash scripts/norhound_live.sh # re-run verify/eval independently
SKIP_DOWNLOAD=1 bash scripts/norhound_live.sh   # reuse existing data/ inputs
NORHOUND_STAGE_TIMEOUT_S=900 bash scripts/norhound_live.sh  # per-connector cap
```

It prints a final scorecard and writes the viewer to `out/norhound-site/`.
Inside Docker the same script is the `norhound-full` entrypoint, so the grader
needs only `docker compose run --rm norhound-full`.

Re-running the same command is how refresh history is produced. The official
command compares the new envelopes with the previous snapshot
(`--previous-envelopes`) and writes, for every company, typed old -> new
change records with the source URL, retrieval time, effective date and the
content hash of both values, plus the earlier evidence behind a recorded
change. A change is keyed by a content hash, so repeating the comparison
records nothing twice. The first run has no previous snapshot, so it records a
baseline with no change events, which is the correct result for a first run.
`scripts/run_refresh_replay.py` replays a frozen fixture for auditing this
diff; it is a test harness, not a pipeline stage.

Each connector subprocess is bounded by `NORHOUND_STAGE_TIMEOUT_S` (default
3600) and is killed as a process group, so a stalled site can no longer block
the pipeline indefinitely. The brief states that each official run has a fixed
time and resource budget supplied by Builderr; the measured runtime of the
shipped pipeline is **11.8 minutes per 100 companies** (117.7 min per 1,000,
measured end-to-end on the 17 Nov 2026 rehearsal), so lower the stage timeout
if the budget you are given is tighter.

**Note on steps 4–5 below:** `run_external_pipeline.py` already runs
`verify_and_label_observations.py` and `evaluate_external_footprint.py`
internally — that internal run is what makes publication conditional on a
verified `exact_entity` label. The standalone commands are kept for inspection
only, and read the pipeline's own `<prefix>.external.jsonl` /
`<prefix>.labels.jsonl` (an earlier revision emitted `<prefix>.external-withfag.jsonl`,
which the current pipeline no longer writes).

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
the company-universe manifest.

```bash
uv sync

curl -L 'https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv' -o brreg-enheter.csv
curl -L 'https://builderr.ai/signalpost-company-universe-2025.jsonl.gz' -o norhound-universe.jsonl.gz

# 1. Same 1,000-company manifest used for the submission (seed 20260823).
#    --website-only reproduces the shipped entry-web1000.jsonl exactly; the
#    shipped external-footprint eval ran on this website-bearing batch.
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
#    Runs the website-bearing manifest produced in step 1 (this is the exact
#    batch the shipped external-footprint eval ran on).
uv run python scripts/run_competition_batch.py \
  --organisations entry-web1000.jsonl \
  --bulk brreg-enheter.csv \
  --profiles-output out/web1000-profiles.jsonl \
  --output out/envelopes.jsonl \
  --report out/run-report.json \
  --run-id local-001 \
  --expected-count 1000

# 3. External-footprint enrichment: registry contacts + structure, dated
#    registry feed, sitemap lastmod, company-site news/description, Wikidata,
#    official NAV job-feed postings. The --keyless flag runs every no-API-key
#    connector (contacts, site description, substructure, sitemap, registry
#    feed, Wikidata) and folds their rows into the same verify/label/eval chain.
uv run python scripts/run_external_pipeline.py \
  --profiles out/web1000-profiles.jsonl \
  --envelopes out/envelopes.jsonl \
  --prefix out/web1000batch \
  --jobs --reviews --promote --keyless

# 3b. Same deterministic connectors, one at a time if you prefer:
uv run python scripts/extract_registry_contacts.py --profiles out/web1000-profiles.jsonl --output out/contacts.jsonl --report out/contacts-report.json
uv run python scripts/extract_site_description.py --profiles out/web1000-profiles.jsonl --output out/sitedesc.jsonl --report out/sitedesc-report.json
uv run python scripts/extract_substructure.py --profiles out/web1000-profiles.jsonl --output out/substruct.jsonl --report out/substruct-report.json
uv run python scripts/run_registry_updates_connector.py --profiles out/web1000-profiles.jsonl --output out/updates.jsonl --report out/updates-report.json
uv run python scripts/extract_sitemap_pages.py --profiles out/web1000-profiles.jsonl --output out/sitemap.jsonl --report out/sitemap-report.json
uv run python scripts/run_wikidata_connector.py --profiles out/web1000-profiles.jsonl --index data/wikidata-index.jsonl --output out/wikidata.jsonl --report out/wikidata-report.json

# 4. Re-verify every observation against frozen evidence (identity + digest
#    + domain + exact-org directory proof). Unverified rows never publish.
#    (Prefix may differ; the shipped audit re-verified 1,391 observations, and
#    the full 1,000-company live run re-verified 24,887.)
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

# 6. Deterministic grounded summaries (no API key, no model calls) plus a
#    static site you can open over file:// and a refresh-history pass that
#    attaches changes/previous-run versions to the envelopes. Each summary
#    answers what the company does, its financial/staff/hiring position, what
#    changed since the previous run, and what is unknown and why; every
#    answerable sentence carries the evidence ids it rests on.
uv run python scripts/build_deterministic_summaries.py \
  --envelopes out/envelopes.jsonl \
  --output out/summaries.jsonl \
  --report out/summaries-report.json
uv run python scripts/build_static_site.py \
  --envelopes out/envelopes.jsonl --summaries out/summaries.jsonl \
  --labels out/norhound.labels.jsonl --observations out/norhound.external.jsonl \
  --out out/site
```

Network-dependent stages (registry, live website crawl, Firecrawl discovery)
reflect the live web at run time; the sealed results are frozen in `out/`.
The verification/evaluation (`step 4–5`) is deterministic given frozen
profiles and observations and can be re-run on any checkout.

### Expected results (as shipped)

Run `fresh-20261117T213100Z`, promoted to `out/submission/` by
`scripts/promote_run.sh`.

- **31,778 published observations** out of 31,804 re-verified, every one
  carrying the verified `exact_entity` label (unverified rows never publish).
- entity precision **1.0**, metric precision **1.0**, unsupported
  publications **0**, wrong-entity publications **0**.
- **105,164 claims** backed by **35,314 evidence records** across 1,000
  terminal envelopes.
- **50 published job-posting observations** across 14 companies merged
  into the audit (NAV's official feed, `official_api` acquisition, resolved via
  the Brønnøysund `underenheter` endpoint to each advertiser's parent legal
  entity). A live
  chain re-check (2026-09-22) re-confirmed the feed detail carries
  `employer.orgnr`. A discovered careers-page link is **not** a job posting: it
  is published as an explicit `careers_page` signal.
- Deterministic, no-API-key summaries produced for every profile with
  evidence (answers carry confidence and citation-integrity validation); a
  static site renders the directory and per-company pages over `file://`.
- Coverage over sources outside the register: any_external 0.994,
  two_platforms 0.620, buzz_engagement 0.994, workforce_jobs 0.014,
  workforce_snapshot 0.575 (headcount, reported separately), ratings_reviews
  0.032, sentiment 0.032. Six-field recall proxy **22.38 / 50**.
- 593 tests pass by default (8 skipped).

Canonical shipped artifacts: `out/submission/envelopes.jsonl` (1,000 terminal
envelopes), `out/submission/observations.jsonl` + `out/submission/labels.jsonl`
(the 31,804-row audit corpus), `out/submission/profiles-promoted.jsonl`,
`out/submission/manifest.jsonl`, `out/submission/summaries.jsonl`,
`out/submission/eval.json`, `out/submission/measure.json`,
`out/submission/measure-family.json`, `out/submission/site/` (the viewer) and `out/norhound-signalpost-submission.zip`
(the same package as one archive, rebuilt locally by `promote_run.sh` because
`out/` is gitignored). Older `out/batch1000f.*` and
`out/web1000batch.*` JSONL are intermediate runs left on disk; they are not the
submitted numbers.

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
# 593 tests pass (8 skipped)
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
- Third-party spend is **$0 per official batch**. The core batch (registry +
  company-site capture) is free; the other connectors (Wikidata/Wikipedia CC0,
  Brønnøysund REST + registry feed, NAV public job feed, sitemaps) are free
  public/government sources.
- Outbound requests are bounded per company (page caps, per-domain budgets,
  robots.txt honoured, retries with backoff). No paid model is required to
  produce the submitted envelopes.
- The declared expected cost per official batch is included in the submission
  email; `out/run-<run-id>/official-run-report.json` records the request
  count, the runtime and the third-party cost of the run.

## Submission contract

The current brief (retrieved 17 Nov 2026, see
`docs/evidence/signalpost-requirements-2026-11-17.md`) asks for a repository
with:

- a **100-company smoke-test result or report**;
- one documented command that accepts a JSONL batch of organisation numbers:
  `scripts/run_official_batch.sh --batch <batch.jsonl>`;
- exactly one terminal envelope per input;
- pinned dependencies and reproducible setup;
- a previous-snapshot input and material-change output:
  `--previous-envelopes <prior envelopes.jsonl>`;
- a machine-readable run report with runtime, request count and third-party
  cost: `out/run-<run-id>/official-run-report.json`;
- declared models, APIs, licences and source-rights assumptions.

Email the repository URL, the exact commit hash, the smoke-test result, the
run command, models/APIs/licences and the expected cost per official batch to
`submit@builderr.ai`. Precomputed profiles and a company manifest are **not**
submitted for scoring — the 1,000-company corpus in `out/submission/` is
evidence of what the agent does.