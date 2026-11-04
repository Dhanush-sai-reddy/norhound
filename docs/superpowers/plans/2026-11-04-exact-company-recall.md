# Exact-company external recall — implementation plan

**Date:** 2026-11-04
**Branch:** `autoresearch/narrow/signalpost`
**Worktree:** `/home/dhanushsr/.local/share/opencode/worktree/85c9ea/autoresearch-improve-recall`
**Goal:** increase exact-company external recall without reducing entity precision (≥ 0.95) and without fabricating facts.

---

## 1. Baseline (frozen corpus, re-labelled from scratch)

| Artifact | Path |
|---|---|
| Profiles (1,000 companies) | `norhound-starter-kit/out/web1000-profiles.jsonl` |
| Observations (61,362) | `norhound-starter-kit/out/resume-20261104-final-union.external.jsonl` |
| Labels (re-derived) | `norhound-starter-kit/out/resume-20261104-final-union.labels.jsonl` |
| Evaluation | `norhound-starter-kit/out/resume-20261104-final-union.eval.json` |

Measured baseline (see `/tmp/opencode/norhound_recall_analysis.json`):

* entity precision **1.0**, metric precision **1.0**, wrong-company publications **0**
* six-field recall proxy **37.0083 / 50**
  (`any_external 1.000`, `two_platforms 0.642`, `workforce_jobs 0.918`, `ratings_reviews 0.453`, `buzz_engagement 1.000`, `sentiment 0.428`)
* direct reviewer gaps (the honest measure, `worthknowing.md` §2):
  * social profile (`profile_handle`): **185 / 1,000**
  * dated news (`public_post` with machine-readable publication date): **143 / 1,000**
  * hiring (`job_posting`): **59 / 1,000** (`workforce_snapshot` adds 916 more orgs but is not a hiring signal)

The six-field proxy is saturated (`any_external` and `buzz_engagement` are pinned at 1.0 by registry rows), so the
direct gap counts are the primary metric and the proxy is the non-regression guard.

## 2. Angle

**Evidence-verifiable exact-source recall**: observations that are already captured (or cached) and carry a *decisive*
exact-entity proof — an exact Norwegian organisation number on the source itself — are rejected today by
`scripts/verify_and_label_observations.py` for reasons that belong to a *different* proof kind.

Two concrete, source-backed gaps:

1. **Wikidata P2333 social handles** — 50 rows / 24 orgs are rejected solely by
   `handle_present_in_gate_socials`, which requires the handle to appear in the frozen company-site `social_links`.
   The rows carry `organisation_number_on_wikidata` proof: the Wikidata entity carries property **P2333 (Norwegian
   organisation number) equal to the profile organisation number** — a decisive key, no name matching involved.
   The verifier already treats Wikidata as a trusted API source for every other signal type; the handle rule is the
   only inconsistency.
2. **Finn.no role cards** — the committed connector already caches 1,000 search pages and 1,428 ad bodies under
   `data/finn-cache/`. 115 cached ads belong to batch companies, but the connector drops every ad whose advertiser
   organisation number differs from the *searched* company, so ads found through a similarly named company are lost.
   With the JSON-LD `JobPosting` payload unwrapped, the ad's employer name and organisation number can be checked
   against the profile's legal name and organisation number.

## 3. Explicitly rejected alternatives (red team)

| Alternative | Why rejected |
|---|---|
| Let `organisation_number_on_directory_page` rows bypass the company-site gate | contradicts the shipped safety policy encoded in `tests/test_poc.py::test_directory_review_still_requires_verified_company_site_gate`; would publish 231 orgs of directory rows whose primary-entity status is not proven |
| Trust `domain_resolved_to_exact_entity` (Google Maps reviews) globally | the type is also emitted by the Trustpilot connector; 31 site URLs are shared by more than one profile (`usbl.no` × 25, `vestbo.no` × 13), so domain attribution can land on a group portal |
| Publish ATS role cards linked from a verified site | the ATS host can be a group portal serving several legal entities (parent/subsidiary collapse); role cards carry no organisation number |
| Publish `independent_news_discovery` rows | `acquisition_mode = rights_review_experiment`; search results are candidates, not claim evidence, and no article body is retained |
| Promote registry-declared websites (`promote_registry_declared_sites.py`) | measured A/B regresses two-platforms 0.642 → 0.625, workforce 0.918 → 0.916, ratings 0.453 → 0.435 |
| Trust `organisation_number_on_job_posting` (legacy NAV rows) as a global proof type | those rows carry `content_sha256 = "placeholder"` and an empty `source_url`, so trusting them would create unsupported publications |

## 4. Tasks

### Task 1 — reproducible recall measurement (`scripts/measure_recall.py`)

*New file* `norhound-starter-kit/scripts/measure_recall.py`:

* CLI: `--profiles --observations --labels --output [--minimum-audit 100]`.
* Reuses `publishable_observation` from `norway_company_agent.external_footprint`.
* Emits one JSON report with:
  * `entity_precision`, `metric_precision`, `wrong_entity_publications`, `unsupported_publications`;
  * `coverage` (the six existing fields) and `recall_proxy_50`;
  * `direct_reviewer_gaps`: `social_profile` (`profile_handle`), `dated_news` (`public_post` with
    `metrics.published_at` / `metrics.published_date` / top-level `published_at`), `hiring` (`job_posting`);
  * `direct_reviewer_gap_score` = mean of the three gap coverage ratios (0–1).
* **Test** `tests/test_measure_recall.py`: a three-company fixture proves each gap is counted exactly once per
  organisation, that a rejected row is never counted, and that a labelled-but-unpublishable row is excluded.

### Task 2 — Wikidata P2333 handles are exact-entity social profiles

*File* `norhound-starter-kit/scripts/verify_and_label_observations.py`:
* keep the existing trusted-proof classification (`official_api`, `wikidata`);
* replace the unconditional handle rule

  ```python
  if obs.get("signal_type") == "profile_handle":
      exact_entity = exact_entity and checks.get("handle_present_in_gate_socials", False)
  ```

  with

  ```python
  if obs.get("signal_type") == "profile_handle":
      exact_entity = exact_entity and (
          checks.get("handle_present_in_gate_socials", False) or trusted_api_row
      )
  ```

  so a handle that is proved by an exact organisation number on a trusted API (Wikidata P2333) is exact without a
  company-site cross-link, while website-proved handles keep the existing rule unchanged.
* **Tests** `tests/test_wikidata_verifier.py`:
  * RED first: a P2333 handle with matching organisation number and QID is rejected today.
  * GREEN: it is labelled `exact_entity = 1`;
  * a P2333 proof whose organisation number differs from the profile stays rejected;
  * a P2333 proof with a malformed/missing QID stays rejected;
  * a website-linked handle without the trusted proof is still rejected (unchanged behaviour).

### Task 3 — Finn role cards from the cached corpus (offline, strict)

*File* `norhound-starter-kit/scripts/run_finn_jobs_connector.py`:
* `_parse_job_ad`: unwrap Finn's `{"script:ld+json": …}` JSON-LD envelope so `hiringOrganization.name`, `title` and
  `datePosted` are read; extract the advertiser organisation number from the `Org.nr.` label **and** from the
  `virksomhet.brreg.no/nb/oppslag/enheter/{org}` link; drop the loose "first 9-digit number in any meta tag"
  fallback;
* attribution: an ad is attributed to the organisation number stated on the ad (not to the company whose search
  surfaced it) when that number is in `--organisations`; the advertiser name must match the profile's legal name;
* a row is only emitted for a real role card (JSON-LD `JobPosting` with a title);
* new `--offline` flag: never touch the network, fail loudly on a cache miss;
* identity proof: `exact_organisation_number_on_job_ad` plus the corroborating legal-name match and the Brønnøysund
  entity link.
* **Tests** `tests/test_finn_jobs_connector.py` (fixture HTML strings):
  * RED: the current parser cannot read the employer name out of Finn's JSON-LD envelope;
  * GREEN: employer name, title and date are parsed;
  * an ad whose `Org.nr.` label and Brønnøysund link disagree is rejected;
  * an ad for a different organisation number is rejected;
  * an ad whose employer name does not match the legal name is rejected;
  * `--offline` never calls the network.

### Task 4 — verifier accepts job ads proved by an exact organisation number

*File* `norhound-starter-kit/scripts/verify_and_label_observations.py`:
* add proof type `exact_organisation_number_on_job_ad` to a new `job_board` proof kind;
* a `job_board` row is trusted **only** when `signal_type == "job_posting"`, so no other signal type can borrow it;
* trusted rows bypass the company-site gate and the source-domain check (as official-API rows already do).
* **Tests**: a job ad with the exact organisation number is exact without a company website; a job ad with a different
  organisation number is rejected; a `review` row carrying the same proof type is rejected.

### Task 5 — rebuild, re-label, measure, document

1. Copy the frozen baseline artifacts into the isolated worktree (`out/`), never touching the dirty main checkout.
2. Run the Finn connector in `--offline` mode over the cached corpus → `out/finn-jobs-offline.jsonl`.
3. Re-derive every label from the frozen profiles with the new verifier over the union corpus + the new rows.
4. Run `scripts/measure_recall.py` on the baseline corpus/labels and on the candidate corpus/labels.
5. Write `docs/evidence/recall-improvement.md` with the exact command lines, artifact paths, before/after numbers,
   the precision result and the rejected-alternatives table.
6. Commit code, tests and evidence on `autoresearch/narrow/signalpost`.

## 5. Verification commands

```bash
cd norhound-starter-kit
uv run python -m unittest discover -s tests -p 'test_*.py'          # all tests
uv run python scripts/measure_recall.py \
  --profiles out/web1000-profiles.jsonl \
  --observations out/resume-20261104-final-union.external.jsonl \
  --labels out/resume-20261104-final-union.labels.jsonl \
  --output out/recall-baseline.measure.json
uv run python scripts/verify_and_label_observations.py \
  --profiles out/web1000-profiles.jsonl \
  --observations out/recall-candidate.external.jsonl \
  --labels out/recall-candidate.labels.jsonl \
  --report out/recall-candidate.label-report.json
```

## 6. Success criteria

| Criterion | Baseline | Target |
|---|---|---|
| entity precision | 1.0 | ≥ 0.95, wrong-company publications = 0 |
| metric precision | 1.0 | unchanged, unsupported publications = 0 |
| six-field recall proxy | 37.0083 / 50 | ≥ 37.0083 (non-regression) |
| social profile (direct gap) | 185 | > 185 |
| hiring / job postings (direct gap) | 59 | > 59 |
| tests | 272 pass | all pass |
