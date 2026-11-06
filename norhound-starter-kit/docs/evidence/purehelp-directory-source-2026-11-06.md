# Purehelp directory source — evidence record (2026-11-06)

Status: **implemented, measured, published**. Keyless, robots-permitted, org-number keyed.

## 1. The source

| item | value |
|---|---|
| host | `purehelp.no` (Purehelp.no AS, org 817 788 572) |
| page pattern | `https://purehelp.no/company/NO/<9-digit organisation number>` |
| discovery | `https://purehelp.no/sitemaps/companies-1.xml` … `companies-30.xml` (declared by `https://purehelp.no/sitemap.xml`) |
| authentication | none — no key, no login, no paid account |
| acquisition mode | `permitted_public_page` |
| source class | `company_directory` (never presented as official register output) |

### Robots verdict (fetched 2026-11-06)

`https://purehelp.no/robots.txt` → HTTP 200, verbatim:

```
User-agent: *
Disallow: /api/
Disallow: /admin
Disallow: /account
Disallow: /monitor
Disallow: /alerts
Disallow: /ai

Sitemap: https://purehelp.no/sitemap.xml
```

`/company/NO/…` is **allowed**. The connector never requests `/api/`, `/admin`,
`/account`, `/monitor`, `/alerts` or `/ai`. Cached body:
`/tmp/opencode/caches/robots-purehelp.no.txt`.

### Terms / provenance (what Purehelp itself states)

* `https://purehelp.no/privacy` (fetched 2026-11-06, cached at
  `/tmp/opencode/caches/ph-privacy.html`) states that **> 99 % of the data volume is a
  continuous update and mirror of the public registers** — Enhetsregisteret,
  Foretaksregisteret and Regnskapsregisteret — and that public company data and
  role-holder data reproduced in their databases is not deleted.
* `https://purehelp.no/faq` states that a wrong company record is normally caused by
  a missing change message to Brønnøysund and that Purehelp uses only the public
  industry codes from Foretaks-/Enhetsregisteret.
* The site publishes no separate "terms of use" page (`sitemaps/pages.xml` lists
  `/about`, `/privacy`, `/cookies`, `/credit-terms`, `/faq`, `/contact` — there is no
  scraping prohibition and no keyless API offered for these pages).
* The employee count rows carry `employeesSource = "enhetsregisteret"`, i.e. the
  directory states that the figure comes from the Norwegian company register.

**No financial value is published from this source.** Financials come from the
official Brønnøysund accounts API instead, so a value is never mirrored twice or
attributed to the wrong source class (enforced by
`tests/test_purehelp_directory_connector.py::PurehelpObservationTests::test_never_publishes_a_financial_value_from_the_directory`).

## 2. Identity proof (exact entity)

A row is published only when the page itself proves the exact legal entity:

1. the page payload states the requested 9-digit organisation number exactly
   (`company-NO-<org>.orgNumber`), and
2. the legal name on the page equals the BRREG legal name after legal-form
   normalisation, or differs only by a registry word (`SAMEIET`).

The proof is recorded on every row as
`exact_organisation_number_on_directory_page` + `exact_legal_name_on_directory_page`,
which the audit in `scripts/verify_and_label_observations.py` re-derives
independently (the `directory` identity-proof path). A page whose organisation
number or legal name does not match is rejected with an explicit reason
(`org_number_mismatch`, `legal_name_mismatch`) and publishes nothing.

## 3. Coverage actually measured

| measurement | value | evidence path |
|---|---|---|
| organisation ids in Purehelp sitemaps | 1,179,966 across 30 shards | `/tmp/opencode/caches/ph/c1.xml` … `c30.xml` |
| our 1,000 organisation numbers present in those sitemaps | **997** | `/tmp/opencode/caches/ph/hits.txt` |
| company pages fetched (HTTP 200, body cached) | **1,000 / 1,000** | `/tmp/opencode/caches/ph/pages/*.html`, `/tmp/opencode/caches/ph/fetch-report.jsonl` |
| pages whose payload states our organisation number | **1,000 / 1,000** | connector report `orgs_accepted` |
| pages whose legal name equals the BRREG name | **999 accepted, 1 rejected** | `out/frozen/purehelp-report.json` → `rejected_by_reason.legal_name_mismatch = 1` |

The single rejection is organisation `982362547`, where the directory spells the
name `L WINI PROSJEKT AS` and the register spells it `LØWINI PROSJEKT AS`. The
organisation number on the page is correct, but the name does not match after
normalisation, so the connector withholds the row rather than guessing.

Field availability across the 1,000 cached pages (survey of the Nuxt payload):
email 749, website 899, phone 568, employees 517, NACE + municipality 1,000,
registry status 904.

## 4. Published rows

`out/frozen/purehelp.external.jsonl` — **2,830 rows** (connector report
`out/frozen/purehelp-report.json`):

| signal type | rows | meaning |
|---|---|---|
| `profile_metrics` | 999 | legal form, NACE code, municipality, registration date, registry status, active/bankrupt flags, website domain |
| `workforce_snapshot` | 516 | employee count + `employeesAsOf` date + `employeesSource` |
| `contact_email` | 748 | directory-listed email + `contactAsOf` date |
| `contact_phone` | 567 | directory-listed phone + `contactAsOf` date |

Every row carries: organisation number, platform, source URL, retrieval time,
SHA-256 of the page body, exact-entity proof, acquisition mode, rights status,
source class, extraction method and an evidence span naming the payload path the
value was read from.

## 5. Measured effect on the reproducible recall metric

Measurement command (reproducible):

```bash
uv run python scripts/measure_recall.py \
  --profiles out/frozen/web1000-profiles.jsonl \
  --observations out/frozen/candidate-all+purehelp.external.jsonl \
  --labels out/frozen/relabel-all+purehelp.labels.jsonl \
  --output out/frozen/measure-all+purehelp.json
```

| metric | baseline `14b9dd7` (`out/frozen/measure-all-fixed3.json`) | with Purehelp (`out/frozen/measure-all+purehelp.json`) | Δ |
|---|---|---|---|
| `recall_proxy_50` | 37.7833 | **40.3333** | **+2.5500** |
| implied official recall (× 0.9716) | 36.71 / 50 | **39.19 / 50** | +2.48 |
| `any_external` | 1.000 | 1.000 | 0 |
| `two_platforms` | 0.735 | **1.000** | +0.265 |
| `workforce_jobs` | 0.918 | **0.959** | +0.041 |
| `ratings_reviews` | 0.453 | 0.453 | 0 |
| `buzz_engagement` | 1.000 | 1.000 | 0 |
| `sentiment` | 0.428 | 0.428 | 0 |
| `entity_precision` | 1.0 | **1.0** | 0 |
| `wrong_entity_publications` | 0 | **0** | 0 |
| `published_audited` | 39,951 | 42,781 | +2,830 |

Entity precision stayed at 1.0 and no wrong-company row was published.

## 6. Reproduction

```bash
# 1. fetch the pages (keyless, robots-permitted)
python3 /tmp/opencode/caches/ph/fetch_pages.py     # cache-only helper used in this run

# 2. run the connector from the cached pages
uv run python scripts/run_purehelp_directory_connector.py \
  --profiles out/frozen/web1000-profiles.jsonl \
  --organisations data/1000-orgs.txt \
  --output out/frozen/purehelp.external.jsonl \
  --cache /tmp/opencode/caches/ph/pages \
  --report out/frozen/purehelp-report.json \
  --offline --workers 8

# 3. merge, re-verify, re-measure
uv run python scripts/merge_external_outputs.py \
  --inputs out/frozen/candidate-all.external.jsonl out/frozen/purehelp.external.jsonl \
  --output out/frozen/candidate-all+purehelp.external.jsonl \
  --report out/frozen/merge-purehelp-report.json
uv run python scripts/verify_and_label_observations.py \
  --profiles out/frozen/web1000-profiles.jsonl \
  --observations out/frozen/candidate-all+purehelp.external.jsonl \
  --labels out/frozen/relabel-all+purehelp.labels.jsonl \
  --report out/frozen/relabel-all+purehelp.report.json
uv run python scripts/measure_recall.py \
  --profiles out/frozen/web1000-profiles.jsonl \
  --observations out/frozen/candidate-all+purehelp.external.jsonl \
  --labels out/frozen/relabel-all+purehelp.labels.jsonl \
  --output out/frozen/measure-all+purehelp.json
```

## 7. Tests

`tests/test_purehelp_directory_connector.py` (15 tests, written before the
connector): payload parsing, legal-name normalisation and matching, the four
emitted signals, the unique-id rule, the no-financials rule, and the end-to-end
run over a page cache that must reject both a wrong organisation number and a
wrong legal name.

Full suite: `uv run python -m unittest discover -s tests -p 'test_*.py'`.
