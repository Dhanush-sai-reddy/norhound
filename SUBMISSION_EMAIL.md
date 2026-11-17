Subject: Signalpost submission — NorHound Company Research Agent (commit <COMMIT_HASH>)

Hi,

Submitting the NorHound agent for the Signalpost challenge. This revision is
**fully keyless**: every stage runs without an API key, a login or a paid
account, so the cost per 100-company run is **$0**.

The headline is precision, not volume: 1,000 company profiles, 31,829 published
observations, **entity precision 1.0** and **zero wrong-company publications**.

REPOSITORY
https://github.com/Dhanush-sai-reddy/norhound

COMMIT HASH
<COMMIT_HASH>  (branch: main, github.com/Dhanush-sai-reddy/norhound)

DEADLINE NOTE
The challenge page states entries close 22 Nov 2026 and that a 100-company
smoke test plus repository, commit hash and one command are the submission
unit — no precomputed profile bundle or company manifest is required. Both are
shipped anyway (see below) as evidence, not as the deliverable.

ONE COMMAND TO RUN
  cd norhound-starter-kit
  uv sync
  uv run playwright install chromium     # one-time, for the browser rescue stage
  scripts/run_full_batch.sh

`scripts/run_full_batch.sh` runs all 14 stages in order: select the
1,000-company manifest (seed 20260823, identical to the shipped one), registry
enrichment with exact-identity website capture, the headless-browser rescue of
unreadable homepages, every keyless connector (NAV job feed, Wikidata,
Fagfolkguiden, Brønnøysund announcements, public ATS feeds), the wrong-company
purge, re-verification against frozen evidence, evaluation, terminal contract
envelopes, deterministic summaries, the static viewer, and the recall
measurement. Optional overrides: `COUNT`, `RUN_ID`, `WORKERS`,
`WORKFORCE_WORKERS`, `MIN_AUDIT`, `ENTRY_MANIFEST`.

WHAT IS IN THE REPO
- `out/submission/profiles-promoted.jsonl` — 1,000 frozen company profiles
- `out/submission/manifest.jsonl` — the organisation-number manifest (1,000 rows)
- `out/submission/envelopes.jsonl` — 1,000 terminal contract envelopes, one per
  company: 105,204 claims backed by 35,361 evidence records
- `out/submission/observations.jsonl` + `out/submission/labels.jsonl` — the
  31,855-row re-verified corpus (31,829 rows published)
- `out/submission/summaries.jsonl` — 1,000/1,000 deterministic summaries
- `out/submission/eval.json` — the audit report
- `out/submission/measure.json` — the six-field recall proxy
- `out/submission/measure-family.json` — the per-family recall report
- `out/submission/site/` — the searchable viewer (1,000 company pages + compare
  view + bulk export)
- `out/submission/smoke-100/smoke-envelopes.jsonl` +
  `out/submission/smoke-100/smoke-report.json` — the 100-company smoke test:
  **100 requested, 100 returned, complete**, 10,305 claims and 3,396 evidence
  records, produced by `scripts/build_smoke_report.py --run-dir <run> --count
  100 --output-dir <dir>` (exit code 1 if any requested company comes back
  missing or incomplete)
- `out/norhound-signalpost-submission.zip` — the same package, zipped

PRECISION (the gates that matter more than volume)
- entity precision **1.0**, metric precision **1.0**
- wrong-company publications **0**, unsupported publications **0**
- 31,829 of 31,855 re-verified observations published; unverified rows never
  publish
- every published fact carries source URL, retrieval time, reporting or
  effective date, content hash and extraction method
- 559 tests pass (`uv run python -m unittest discover -s tests`)

RECALL — what is measured, and what each number means
These are **our own reproducible measurements, not official scores**. The
challenge publishes no score for this revision, so nothing below is presented
as one.

Six-field external recall proxy (`scripts/measure_recall.py`, mean of six
fields × 50): **22.43 / 50**.

| field | recall | what it counts |
|---|---|---|
| any_external | 0.994 | ≥1 source outside the register |
| two_platforms | 0.627 | ≥2 independent sources outside the register |
| workforce_jobs | 0.013 | a real role card, job-feed item or apply action |
| ratings_reviews | 0.032 | a third-party rating |
| buzz_engagement | 0.994 | a third-party profile, mention or post |
| sentiment | 0.032 | a derived sentiment label from a real rating |

Company recall per official fact family
(`scripts/measure_family_recall.py`, against the challenge's per-family
opportunity counts):

| fact family | covered / opportunities | recall |
|---|---|---|
| identity | 1000 / 1000 | 1.000 |
| financials | 994 / 1000 | 0.994 |
| roles | 994 / 1000 | 0.994 |
| other | 999 / 1000 | 0.999 |
| news | 1000 / 998 | 1.000 |
| website | 604 / 577 | 1.000 |
| social | 209 / 177 | 1.000 |
| hiring | 49 / 84 | 0.583 |
| reviews (not scored by the rubric) | 32 / 323 | 0.099 |

Opportunity-weighted over the scored families this reads 49.59/50 for
all-claims coverage and **13.07/50 for claims backed by a source outside the
register**, which is the variant that tracks external recall — the all-claims
variant counts the register's own facts, which every company has. I am
reporting the lower one rather than the flattering one.

The hiring row needs its definition: **49** companies publish a hiring-family
claim, but only **13** of them have a real role card (a NAV job-feed item or a
public ATS role card). The other 36 publish an explicit `careers_page` signal —
a careers page proves a page exists, not that a position is open. The report
keeps the two apart (`hiring_evidence` in `measure-family.json`).

WHERE THE REMAINING POINTS ARE, AND WHY THEY ARE NOT CLOSED
- `ratings_reviews` + `sentiment` (16.1 of the 50): every keyless rating source
  was probed and every one is blocked or JavaScript-only — Trustpilot, Gulesider,
  Proff.no and Bygghjemme answer HTTP 403 to any non-browser request, and
  1881.no serves no rating markup in its HTML. Fagfolkguiden is the only
  keyless directory that answers, and only 32 of the 323 companies with a
  rating have a page there. No Norwegian SMB site embeds a review widget
  either (0 of 17 homepages checked).
- `workforce_jobs` (8.2): bounded by how many real adverts a keyless source
  holds. NAV's official feed reaches 13 companies; the public ATS boards add 3
  more; Finn.no is excluded (no organisation numbers, and its terms of service
  forbid it) and NAV's live search answers HTTP 429 to unauthenticated bulk.
- `two_platforms` (3.1): 367 of the 373 missing companies have exactly one
  independent source, no verified website and no Wikidata item.

The full write-up, with the probes and the arithmetic, is in
`norhound-starter-kit/RECALL_LEVERS.md`.

WHAT CHANGED IN THIS REVISION
- **Hiring integrity fixed.** The company-site jobs connector was emitting
  `job_posting` for every link it *discovered* on a careers page without ever
  fetching the posting — "Digitalt testament" and "Marketing" were published
  as job titles on 38 companies, inflating `workforce_jobs` from 0.013 to
  0.051. It now emits an explicit `careers_page` signal, and a discovered link
  can no longer become a role title anywhere in the envelope builder. The
  honest number is 13 companies with a real role card.
- **Three recall fields de-tautologised.** `workforce_jobs` was counting
  headcount; `any_external` and `two_platforms` were counting the register,
  which every profiled company has; `buzz_engagement` was counting
  Brønnøysund annual-account announcements, which every filer has. Each is now
  defined over something the company actually has to earn — a source outside
  the register, a real advert, a third-party mention. The proxy fell from a
  flattering 33.43 to an honest 22.43; the coverage it claims is now coverage
  that exists.
- **One scorer, not two.** The audit report and the recall report used to
  compute coverage separately and could print different numbers for the same
  corpus. `evaluate_external_footprint.py` now imports the shared definitions,
  so they cannot disagree.
- **Packaging consistency.** The submission used to ship a profile file that
  was not the one the claims were derived from; the promotion now ships the
  exact profile set the evidence came from.
- **News body retention on by default.** News observations keep a bounded
  first-party body, so the publication date is mined from the page itself
  instead of the crawl date. Measured on 20 real profiles: 6 observations, 0
  dated before, 3 dated and 6 bodies retained after.
- **Annual-report PDF/OCR is off by default and earns 0 points.** It is the
  longest stage in the chain (3 h 22 m for 1,000 companies) and measured
  **0** of the 50 recall points: it changed 0 summaries and 0 viewer columns.
  It stays in the repo, unwired, behind `SLOW_STAGES=1`.
- **Google excluded.** The Places API needs a key and the Maps rows had been
  scraped against Google's terms of service, so neither is published. This is
  the single largest remaining source of ratings coverage, and I am reporting
  the gap rather than quietly turning the key on.
- **Resolver fix and browser rescue.** A transient DNS burst lost 330 homepages
  in an earlier 1,000-company run (all 231 flipped hosts resolve normally when
  asked again); the resolver now retries a failed lookup with a bounded
  backoff, and the browser rescue recovers eligible pages through the
  unchanged identity gate, so the exact-entity judgement is never widened.

MODELS / APIs / LICENCES
- No LLMs, no paid models, no API keys. All extraction is deterministic and
  rule-based; summaries are rule-based (no model, no cost).
- Sources, all keyless: Brønnøysund Enhetsregisteret and Regnskapsregisteret
  (NLOD open licence, official bulk export + REST), Brønnøysund Kunngjoringer
  (official announcements feed), NAV Arbeidsplassen (official public job
  feed), Wikidata/Wikipedia (CC0), GLEIF (public LEI registry), Fagfolkguiden
  (public directory pages), Brønnøysund bulk domain index, and the companies'
  own websites (public pages only, robots.txt honoured).
- Robots.txt is honoured for every site; LinkedIn/Meta/Indeed are not
  collected directly; company-owned copy is published as a company-controlled
  claim layer and never as independent sentiment.
- Every source is restricted to the exact legal entity: the register's own
  website filing, a sole-declarer domain index, or a feed company name that
  corroborates the organisation number. A group, parent or subsidiary is
  labelled, never collapsed into its parent.

EXPECTED COST PER 100-COMPANY RUN
- External spend: **$0**. No paid API is called.
- Outbound requests: roughly 40-60 public page/API requests per company, well
  inside the 2,000-request budget for a 100-company batch.
- Runtime: measured **44 minutes per 100 companies** on 8 workers, without the
  opt-in OCR stage (a full 1,000-company run is about 7 h 20 m; with the OCR
  stage on it is 10.7 h, which is why OCR stays off).
- Models: none. Licences: NLOD (registry), CC0 (Wikidata/GLEIF), ODbL where
  applicable; website content is quoted at claim level with source URL,
  retrieval time and content hash.

CONTACT
Dhanush Sai Reddy
(Registered on Unstop as Dhanush-sai-reddy)

Regards,
Dhanush
