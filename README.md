# NorHound company research agent

Runnable company-research agent for Norwegian organisation numbers, with a
**complete, evaluated 1,000-company run** (`norhound-starter-kit/out/SUBMISSION-REPORT.md`).

> **Workdir:** all code and commands below live in `norhound-starter-kit/`. `cd norhound-starter-kit` before running anything. Entry point: `select_entry_batch.py` and `scripts/run_competition_batch.py`.

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
- generates deterministic, citation-verified summaries (what it does,
  financials, staff, hiring) with no API key;
- supports checkpoint/resume and a deterministic refresh replay.

## Reproduce the shipped submission

**The command an evaluator runs** — it takes a JSONL batch of organisation
numbers and produces one terminal envelope per input, the refresh history and
the machine-readable run report:

```bash
cd norhound-starter-kit
uv sync
uv run playwright install chromium     # one-time, for the browser rescue stage
scripts/run_official_batch.sh --batch organisations.jsonl
```

`organisations.jsonl` holds one organisation number per line, either as a bare
number or as an object with `"organisation_number"`. The command writes:

| Artifact | What it is |
|---|---|
| `out/run-<run-id>/envelopes-final.jsonl` | one terminal envelope per input company |
| `out/run-<run-id>/official-run-report.json` | runtime, request count, third-party cost, identity precision, declared source rights |
| `out/run-<run-id>/refresh-report.json` | the material changes found against the previous snapshot, and the changes preserved |

Add `--previous-envelopes <prior envelopes.jsonl>` to run it as a refresh: every
envelope then carries the previous run id, the typed old -> new change records
and the earlier evidence behind a recorded change.

**The local 1,000-company run** (the same pipeline, selecting its own batch
with seed 20260823) is one command as well:

```bash
cd norhound-starter-kit
scripts/run_full_batch.sh
```

`scripts/run_full_batch.sh` runs all 14 stages in order: select the
1,000-company manifest (seed 20260823, identical to the shipped one), registry
enrichment with exact-identity website capture, the headless-browser rescue of
unreadable homepages, every keyless connector (NAV job feed, Wikidata,
Fagfolkguiden, Brønnøysund announcements, public ATS feeds), the wrong-company
purge, re-verification against frozen evidence, evaluation, terminal contract
envelopes, deterministic summaries, the static viewer and the recall
measurement.

Optional overrides: `COUNT=1000`, `RUN_ID=...`, `WORKERS=8`,
`WORKFORCE_WORKERS=8`, `MIN_AUDIT=300`, `ENTRY_MANIFEST=entry-web1000.jsonl`
(run on an existing manifest instead of selecting one).

The stages that read the live web reflect the live web at run time; the sealed
results are frozen in `out/submission/` and can be re-verified on any checkout.

### Container (no local setup required)

Everything (Python 3.12, `uv`, dependencies) is pinned inside the image, so the
grader needs only Docker — nothing installed on the host. From
`norhound-starter-kit/`:

```bash
docker compose up                 # offline saved-data proof (a few seconds)
docker compose run --rm norhound  # same check, explicit
```

```bash
docker compose build                    # one-time image build
docker compose run --rm norhound-full   # full live pipeline (registry download +
                                        # 1000-company crawl + external pipeline)
```

`COUNT`/`EXPECTED` default to 1000 (the publicity guard rejects smaller
manifests). Downloaded data and crawl output stay on the host in the
`norhound-data` / `norhound-out` volumes so a run survives container teardown.
The same scripts/commands below run inside the container, unchanged.

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

# 6. Deterministic summaries (no API key required — zero cost).
uv run python scripts/build_deterministic_summaries.py \
  --envelopes out/envelopes.jsonl \
  --output out/summaries.jsonl \
  --report out/summaries-report.json
```

Network-dependent stages (registry, live website crawl, Firecrawl discovery)
reflect the live web at run time; the sealed results are frozen in `out/`.
The verification/evaluation (`step 4–5`) and summaries (`step 6`) are
deterministic given frozen profiles and observations and can be re-run on any
checkout.

### Expected results (as shipped)

Run `fresh-20261116T144704Z`, promoted to `out/submission/` by
`scripts/promote_run.sh`.

- **31,829 published** observations out of 31,855 re-verified, every one
  carrying the verified `exact_entity` label (unverified rows never publish).
- entity precision **1.0**, metric precision **1.0**, unsupported
  publications **0**, wrong-entity publications **0**.
- **105,204 claims** backed by **35,361 evidence records** across 1,000
  terminal envelopes.
- Coverage, measured over sources **outside** the register:
  any_external 0.994, two_platforms 0.627, buzz_engagement 0.994,
  workforce_jobs 0.013, workforce_snapshot 0.575 (headcount, reported
  separately — it is not evidence of hiring), ratings_reviews 0.032,
  sentiment 0.032. Six-field recall proxy **22.43 / 50**.
- Company recall per official fact family
  (`scripts/measure_family_recall.py`): identity **1000/1000**, financials
  **994/1000**, roles **994/1000**, other **999/1000**, news **1000/998**,
  website **604/577**, social **209/177**, hiring **49/84**. Reviews are
  **32/323** and are not scored by the rubric.
- Of the 49 companies with a hiring-family claim, **13 have a real role card**
  (a NAV job-feed item or a public ATS role card); the other 36 publish an
  explicit `careers_page` signal, which proves a page exists and not that a
  position is open. `measure-family.json` reports the split under
  `hiring_evidence`.
- **1000/1000 deterministic summaries** produced (what it does, financials,
  staff, hiring; all answers cite evidence; unknowns listed with reasons).
- The 100-company smoke test returns **100/100 complete** (10,305 claims,
  3,396 evidence records).
- 559 tests pass by default (8 skipped).

Canonical shipped artifacts: `out/submission/envelopes.jsonl` (1,000 terminal
envelopes), `out/submission/observations.jsonl` + `out/submission/labels.jsonl`
(the 31,855-row audit corpus), `out/submission/profiles-promoted.jsonl`,
`out/submission/manifest.jsonl` (the organisation-number manifest),
`out/submission/summaries.jsonl`, `out/submission/eval.json`,
`out/submission/measure.json`, `out/submission/measure-family.json`,
`out/submission/site/` (the viewer). `scripts/promote_run.sh` also writes
`out/norhound-signalpost-submission.zip`, the same package as one archive;
`out/` is gitignored, so the archive is built locally while every file inside
it is committed under `out/submission/`.
Where the recall numbers can still come from, and which keyless sources were
probed and found blocked, is written up in
`norhound-starter-kit/RECALL_LEVERS.md`.

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
uv run python -m unittest discover -s tests -p 'test_*.py'
# 559 tests pass (8 skipped)
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
  in the repository. The shipped pipeline needs **no key at all**; the optional
  key `FIRECRAWL_API_KEY` (site discovery) is not used by
  `scripts/run_full_batch.sh`. A missing key degrades cleanly — the
  corresponding connector is skipped or abstains, never errors.
- Third-party spend is **$0 per official batch**. Every source is a public
  registry, a public feed or a public page: Brønnøysund, NAV, Wikidata, GLEIF,
  Fagfolkguiden and the companies' own websites.
- Outbound requests are bounded per company (page caps, per-domain budgets,
  robots.txt honoured, retries with backoff). No paid model is required to
  produce the submitted envelopes.
- The declared expected cost per official batch is included in the submission
  email; the run report records the request count, the runtime and the cost.

## Submission contract

The current brief (retrieved 17 Nov 2026, see
`norhound-starter-kit/docs/evidence/signalpost-requirements-2026-11-17.md`)
asks for a repository with:

- a **100-company smoke-test result or report**;
- one documented command that accepts a JSONL batch of organisation numbers;
- exactly one terminal envelope per input;
- pinned dependencies and reproducible setup;
- a previous-snapshot input and material-change output;
- a machine-readable run report with runtime, request count and third-party
  cost;
- declared models, APIs, licences and source-rights assumptions.

Email the repository URL, the exact commit hash, the smoke-test result, the
run command, models/APIs/licences and the expected cost per official batch to
`submit@builderr.ai`. Precomputed profiles and a company manifest are **not**
submitted for scoring — the 1,000-company corpus in `out/submission/` is
evidence of what the agent does.