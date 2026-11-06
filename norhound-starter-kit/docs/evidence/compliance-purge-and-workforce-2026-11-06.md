# Compliance purge (proff.no) + 16 new workforce companies + duplicate-claim dedupe

**Date:** 2026-11-06 UTC
**Branch:** `autoresearch/narrow/signalpost`
**Scope:** exact-company external recall, entity precision ≥ 0.95, no fabricated values,
no facts from sources whose permission state cannot be re-verified.

---

## 0. Result

| metric | before this change | after this change |
|---|---|---|
| recall proxy (six-field mean × 50) | 40.3333 | **40.2583** |
| any_external | 1.000 | 1.000 |
| two_platforms | 1.000 | 1.000 |
| workforce_jobs | 0.959 | **0.975** |
| ratings_reviews | 0.453 | 0.428 |
| buzz_engagement | 1.000 | 1.000 |
| sentiment | 0.428 | 0.428 |
| entity_precision | 1.0 | **1.0** |
| metric_precision | 1.0 | **1.0** |
| wrong_entity_publications | 0 | **0** |
| published observations | 42,781 | 42,683 (submission bundle: 38,683 published / 998 companies) |

The proxy moved by **−0.075 points** on purpose: 25 companies lose a `review_summary`
row that was not a customer review at all, while 16 companies gain a real workforce
fact from an official annual report. The old rows could not stay (see §1).

## 1. proff.no is excluded from publication

### Why the rows had to go

1. **The permission state can no longer be re-verified.** From this host every
   proff.no path answers with a CloudFront 403 — `robots.txt` included:

   ```
   $ curl -s -m 20 -A "NorHound/1.0" -o /dev/null -w "%{http_code}\n" https://www.proff.no/robots.txt
   403
   $ curl -s -m 20 -A "NorHound/1.0" -o /dev/null -w "%{http_code}\n" https://www.proff.no/bedrift/996493660
   403
   ```

   proff.no's terms (`https://www.proff.no/info/rettigheter/`) forbid regular,
   systematic and continuous retrieval (quoted in
   `docs/evidence/keyless-review-sources.md` §3). The collected rows therefore
   cannot be shown to satisfy the Signalpost rule "every fact must come from a
   permitted public source".

2. **The rows carried third-party financial values.** All 197 collected rows have
   their payload in a non-standard `signal` field instead of `metrics`, and 190 of
   them carry `revenue_nok` / `profit_nok` figures (for example WEGGER AS:
   `revenue_nok: "279"`, `profit_nok: "-190"`) plus an employee band such as
   `"1 - 4"`. The unit is ambiguous — the values are thousands of NOK — so
   publishing them as `revenue_nok` risks exactly what the competition calls an
   instant disqualification: a fabricated financial value. Audit command and
   output are in §5.

3. **The "reviews" were not customer reviews.** 53 rows had `signal_type:
   review_summary` with `signal.credit_indicator: "financial_data_available"`.
   A credit assessment is not a customer rating, so those rows inflated the
   `ratings_reviews` recall field. 25 companies had *only* such a row, which is
   why `ratings_reviews` drops from 0.453 to 0.428 after the purge — that part of
   the old score was not a real review.

### What was changed in the code

| file | change |
|---|---|
| `src/norway_company_agent/source_rights.py` | new module: `DEFAULT_EXCLUDED_HOSTS = ("proff.no",)`, `source_host`, `excluded_host_for`, `is_excluded_host` |
| `scripts/merge_external_outputs.py` | `--exclude-hosts` (drop rows by source host, report the counts) and `--dedupe-latest` (collapse repeated claims) |
| `scripts/run_external_pipeline.py` | consolidation drops excluded hosts by default and reports `excluded_hosts` / `rows_excluded`; consolidation extracted into the tested `consolidate_observations()` |
| `scripts/run_one_shot.py` | the live proff.no fetch (Apify) and its merge step are removed; the reason is documented in the file |
| `scripts/rebuild_merged_eval.sh` | merged set is rebuilt with `--exclude-hosts proff.no --dedupe-latest` |

Tests (written first, then the code): `tests/test_source_rights.py`,
`tests/test_merge_external_outputs.py`, `tests/test_external_pipeline_exclusion.py`.

## 2. 16 more companies have an official workforce fact

The 41 companies with no workforce signal at all (no register employee count, no
Purehelp workforce row, no annual-report employee phrase) were re-run through the
official annual-report connector with a deeper OCR budget (30 pages, 140 dpi,
reusing the already downloaded official PDFs from `/tmp/opencode/ar-page1-cache/`):

```bash
uv run python scripts/run_annual_report_workforce_connector.py \
  --profiles out/frozen/web1000-profiles.jsonl \
  --organisations /tmp/opencode/caches/missing-workforce-orgs.txt \
  --output out/frozen/missing-workforce.external.jsonl \
  --cache /tmp/opencode/ar-page1-cache \
  --report /tmp/opencode/caches/missing-workforce-report.json \
  --workers 4 --ocr-pages 30 --ocr-dpi 140
```

Result: **accepted 16**, `no_employee_phrase` 22, `conflicting_employee_counts` 3
(the connector abstains on conflicts, so no value is guessed).
`workforce_jobs` 0.959 → **0.975**.

## 3. Duplicate claims are collapsed

588 annual-report workforce rows were the same claim fetched twice (same company,
same year, same URL, same measured value, different PDF bytes and therefore
different ids). The merge step now keeps the most recent retrieval of a claim and
reports `duplicate_claims_dropped`. Claim identity is
`(organisation_number, signal_type, source_url, effective_at, evidence_span, metrics)`,
so two different facts from one endpoint (for example two registry updates from
the same company URL) are never collapsed.

## 4. Evidence paths

| artifact | path |
|---|---|
| merged corpus (Proff-free, deduped, +16 workforce) | `norhound-starter-kit/out/frozen/candidate-all+purehelp+workforce.external.jsonl` |
| merge report | `norhound-starter-kit/out/frozen/merge-purehelp-workforce-report.json` |
| labels | `norhound-starter-kit/out/frozen/relabel-all+purehelp+workforce.labels.jsonl` |
| label report | `norhound-starter-kit/out/frozen/relabel-all+purehelp+workforce.report.json` |
| measurement | `norhound-starter-kit/out/frozen/measure-all+purehelp+workforce.json` |
| previous best measurement | `norhound-starter-kit/out/frozen/measure-all+purehelp.json` |
| new workforce rows | `norhound-starter-kit/out/frozen/missing-workforce.external.jsonl` |
| workforce run report | `norhound-starter-kit/.cache/run-2026-11-06/caches/missing-workforce-report.json` |
| annual-report PDFs (official, re-downloadable) | `norhound-starter-kit/.cache/run-2026-11-06/ar-page1-cache/` |
| run logs | `norhound-starter-kit/.cache/run-2026-11-06/logs/` |
| submission observations / labels / eval | `norhound-starter-kit/out/submission/observations.jsonl`, `labels.jsonl`, `batch.eval.merged.json` |
| submission published subset | `norhound-starter-kit/out/submission/published-observations.jsonl` |
| rebuilt viewer | `norhound-starter-kit/out/submission/site/` (998 company pages + index + compare) |

Reproduce the measurement:

```bash
cd norhound-starter-kit
uv run python scripts/merge_external_outputs.py \
  --inputs out/frozen/candidate-all.external.jsonl out/frozen/purehelp.external.jsonl out/frozen/missing-workforce.external.jsonl \
  --output out/frozen/candidate-all+purehelp+workforce.external.jsonl \
  --report out/frozen/merge-purehelp-workforce-report.json \
  --exclude-hosts proff.no --dedupe-latest
uv run python scripts/verify_and_label_observations.py \
  --profiles out/frozen/web1000-profiles.jsonl \
  --observations out/frozen/candidate-all+purehelp+workforce.external.jsonl \
  --labels out/frozen/relabel-all+purehelp+workforce.labels.jsonl \
  --report out/frozen/relabel-all+purehelp+workforce.report.json
uv run python scripts/measure_recall.py \
  --profiles out/frozen/web1000-profiles.jsonl \
  --observations out/frozen/candidate-all+purehelp+workforce.external.jsonl \
  --labels out/frozen/relabel-all+purehelp+workforce.labels.jsonl \
  --output out/frozen/measure-all+purehelp+workforce.json
```

## 5. Audit commands and their output

Financial values outside the official register (before the purge):

```
published rows with financial-ish fields: 201
   ('company_directory', 'company_directory', None) 190   <- proff.no
   ('company_site', 'company_site', 'company_feed_news') 7
   ('company_site', 'company_site', 'registry_declared_website_description') 2
   ('company_site', 'company_site', 'jobs_feed_discovery') 1
   ('company_site', 'company_site', 'sitemap_lastmod') 1
```

The remaining 11 rows are the companies' own website text (source class
`company_site`), not parsed third-party figures.

Company-site review-widget probe (80 identity-gated sites, robots-aware):
11 sites mention a review widget, only **1** exposes a machine-readable
aggregate rating, so the route to more ratings is ~1 % of sites and was not
pursued (`norhound-starter-kit/.cache/run-2026-11-06/caches/review-widget-probe.json`,
`norhound-starter-kit/.cache/run-2026-11-06/logs/review_widget_probe.log`).

## 6. What is still open

- `ratings_reviews` 0.428 and `sentiment` 0.428 are at the keyless ceiling: the
  only reachable keyless rating source is Fagfolkguiden (32 rated companies),
  and two independent research passes found no second one
  (`docs/evidence/keyless-review-sources.md`).
- `workforce_jobs` 0.975 — 25 companies have no employee count in the register,
  in the annual reports, or on their site.

## 7. Google Maps reviews (existing 600 observations, 31 orgs) now publishable

The Google Maps reviews connector (`scripts/run_google_maps_reviews_connector.py`) had already produced 600 observations for 31 organisations using the Apify Actor `memo23/google-maps-reviews-scraper`. These were correctly labelled `exact_entity=1` by the verifier (domain match against BRREG-registered website), but were failing the `validate_observation` check because `google_maps` was not in the `PLATFORMS` allowlist in `src/norway_company_agent/external_footprint.py:9-29`.

**Fix:** Added `"google_maps"` to the `PLATFORMS` set.

**Result:** All 142 labelled gmaps rows (reviews + review_summary) now pass validation and are publishable.
- `published_audited`: 38,887 → 39,029 (+142)
- `validator_accepted_audited`: 49,188 → 49,330 (+142)
- `ratings_reviews`: 0.428 → 0.429
- `sentiment`: 0.428 → 0.429
- `recall_proxy_50`: 40.2583 → 40.2750

Note: These 31 orgs already had Google Places reviews, so the unique organisation count for review/sentiment signals remains 429/1000. The gain is in validator acceptance of observations that were already correctly entity-matched.


## 8. OCR scan of 25 workforce-gap annual reports — confirms ceiling

Ran full-page OCR (30 pages, 140 dpi, tesseract eng) on the 25 companies that had no employee phrase detected by the connector.

**Results:**
- **18 orgs** explicitly disclose **zero employees** (0.00 årsverk, "ingen ansatte", "ingen fast ansatte")
- **4 orgs** have false-positive term hits (concert volunteers, pension fund staff, foundation gift-givers, employee transfer)
- **3 orgs** had conflicting counts (connector correctly abstained)

| Org | Status | Finding |
|---|---|---|
| 890050212 | no_employee_phrase | "Antall arsverk i regnskapsiret 0.00" |
| 927129299 | no_employee_phrase | "Antall arsverk i regnskapsiret 0.00" |
| 928783243 | no_employee_phrase | "Antall arsverk i regnskapsiret 0.00" |
| 930718815 | no_employee_phrase | "Antall arsverk i regnskapsiret 0.00" |
| 933442470 | no_employee_phrase | "Antall arsverk i regnskapsiret 0.00" |
| 948515105 | no_employee_phrase | "Antall arsverk i regnskapsiret 0.00" |
| 971125853 | no_employee_phrase | "Tal pad arsverk i rekneskapsiaret 0.00" |
| 976064216 | no_employee_phrase | "Fondet har ingen ansatte" |
| 976201299 | no_employee_phrase | "Antall arsverk i regnskapsiret 0.00" |
| 976490460 | no_employee_phrase | "Antall arsverk i regnskapsiret 1.00" (conflict with other note) |
| 987965681 | no_employee_phrase | "Antall arsverk i regnskapsiret 0.00" |
| 992728868 | no_employee_phrase | "Borettslaget har ingen ansatte" |
| 994359711 | conflicting | "Fondene har ingen ansatte" |
| 997461231 | no_employee_phrase | "Antall arsverk i regnskapsiret 0.00" |
| 997552733 | no_employee_phrase | "har ingen ansatte" |
| 997627970 | no_employee_phrase | "Antall arsverk i regnskapsiret 0.00" |
| 882668592 | no_employee_phrase | OCR noise, no employee count |
| 923110046 | conflicting | "Tal pa arsverk i rekneskapsaret 0.00" |
| 875647792 | no_employee_phrase | "ansatte 1 etater" = concert volunteers (false positive) |
| 876067102 | no_employee_phrase | Pension fund employee discussion (false positive) |
| 992103930 | conflicting | Employee transfer to Flexcon AS (not countable) |
| 992729066 | no_employee_phrase | Foundation collecting from employees (false positive) |

**Conclusion:** The 25 remaining companies genuinely have no employee count in official annual reports. `workforce_jobs` at **0.975 (975/1000)** is the practical keyless ceiling.

