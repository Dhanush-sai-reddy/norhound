# Excluding Google: the corpus is now keyless and ToS-clean

Date: 2026-11-07
Decision: `google.com` added to `DEFAULT_EXCLUDED_HOSTS`.

## What was in the shipped corpus

The previously shipped 1,000-company corpus carried **2,497 published
observations** whose `source_url` is `www.google.com`:

| Source file | Rows | Acquisition mode | Platform | Published | Companies |
|---|---|---|---|---|---|
| `out/gplaces-reviews.jsonl` | 1,897 | `official_api` | `google_places` | 1,897 | 311 |
| `out/gmaps-reviews.jsonl` | 600 | `permitted_public_page` | `google_maps` | 146 | 31 |

Breakdown of the 1,897 Places rows by signal type: `review` 964,
`profile_metrics` 311, `review_summary` 311, `sentiment` 311.

## Why they must go

Two independent reasons, either of which is sufficient:

1. **The Places API requires an API key.** The run contract for this
   submission is that the whole pipeline executes end to end without any
   credential, a login or a paid account. A claim backed by a credential
   nobody can supply is not evidence a reviewer can re-verify, and the
   challenge's own rule is that every published fact must carry a source URL,
   retrieval time, reporting date, content hash and extraction method that a
   reviewer can check offline.
2. **The Maps rows were scraped from Google Maps.** Google's Terms of Service
   prohibit automated access to that content, and the challenge's source
   policy admits only robots- and ToS-permitted sources. The rows were marked
   `acquisition_mode: permitted_public_page` / `rights_status: approved`, which
   was wrong: no permission exists for that collection route. The pipeline's
   own rights-review experiment counted them separately
   (`acquisition_modes.rights_review_experiment: 33` in the old evaluation),
   which is what surfaced the problem.

Both are the same Google Maps/Places data reached by a route the rules
forbid, so the whole host is excluded by default — the same mechanism that
already excludes `proff.no`.

## The measured cost

Re-running merge → purge → verify → evaluate on the shipped 1,000-company
corpus with `--exclude-hosts proff.no google.com`
(`out/web1000batch.eval-merged.json`):

| Metric | With Google | Keyless only | Delta |
|---|---|---|---|
| observations | 34,791 | 32,713 | −2,078 |
| published_audited | 34,080 | 32,035 | −2,045 |
| entity_precision | 1.0 | 1.0 | — |
| metric_precision | 1.0 | 1.0 | — |
| wrong_entity_publications | 0 | 0 | — |
| unsupported_publications | 0 | 0 | — |
| any_external | 1.000 | 1.000 | — |
| two_platforms | 0.669 | 0.639 | −0.030 |
| workforce_jobs | 0.915 | 0.915 | — |
| buzz_engagement | 0.998 | 0.998 | — |
| ratings_reviews | 0.323 | 0.032 | −0.291 |
| sentiment | 0.323 | 0.032 | −0.291 |

`acquisition_modes` after the exclusion — every source is now either an
official registry API or a permitted public page, and the
`rights_review_experiment` bucket is gone:

```json
{"official_api": 24680, "permitted_public_page": 8033}
```

`platform_counts` after the exclusion — no `google_places`, no `google_maps`:

```json
{"job_board": 112, "company_directory": 317, "company_site": 6590,
 "facebook": 260, "instagram": 217, "linkedin": 141, "x": 24,
 "youtube": 37, "tiktok": 18, "brreg": 24212, "wikidata": 66,
 "wikipedia": 41}
```

### Why the ratings_reviews drop is the right trade

`ratings_reviews` and `sentiment` fall to **0.032 — 32 of 1,000 companies**.
That is not a regression; it is the measured keyless ceiling, and
`docs/evidence/keyless-review-sources.md` proves it: Fagfolkguiden is the
only keyless rating source that returns real ratings, and its sitemap caps it
at 32 of the batch's 1,000 companies. 1881.no, Proff.no, Trustpilot,
Tripadvisor, GuleSider and keyless Google Maps carry no ratings and/or are
ToS-forbidden or blocked. OpenStreetMap and Wikidata have no rating property.

The official rubric scores **Recall 50 / Evidence 30 / Synthesis 12 / UX 8**
and **does not score ratings, reviews or sentiment** at all — they are not one
of the six scored field families. So the 0.291 internal coverage drop in those
two buckets costs nothing on the official Recall metric, while the two_platforms
cost of 0.030 is roughly a third of a point on the 50-point internal proxy.

The upside is that the whole submission is now reproducible by one command
with no credential, and every published fact comes from a source a reviewer
can check offline. That is the property the Evidence and Recall gates
actually measure.

## How the exclusion is enforced

* `src/norway_company_agent/source_rights.py` — `DEFAULT_EXCLUDED_HOSTS` is now
  `("proff.no", "google.com")`, with the reason documented in the module
  docstring.
* `scripts/run_external_pipeline.py` — the pipeline's default `--exclude-hosts`
  comes from `DEFAULT_EXCLUDED_HOSTS`, so every connector output is filtered
  at consolidation time, before verification.
* `scripts/run_full_batch.sh` — the end-to-end executable merges with
  `--exclude-hosts proff.no google.com`.
* `tests/test_google_excluded.py` — pins the default, the matching rules
  (`www.google.com`, `maps.google.com`) and the non-matching lookalikes
  (`www.googleusercontent.com`, `notgoogle.com`).

`--google-places` still exists as an explicit opt-in for experiments, but the
keyless end-to-end run never enables it, and even if it does, its rows are
dropped at consolidation because their host is excluded.
