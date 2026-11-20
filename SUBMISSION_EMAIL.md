Subject: Signalpost revision — NorHound Company Research Agent (commit a99b4a4)

Hi,

Submitting the NorHound agent for the Signalpost challenge. This revision is
**fully keyless**: every stage runs without an API key, a login or a paid
account, so the external cost per official batch is **$0**.

The headline is precision, not volume: 1,000 company profiles, 40,106 published
observations, **entity precision 1.0** and **zero wrong-company publications**.

REPOSITORY
https://github.com/Dhanush-sai-reddy/norhound

COMMIT HASH
a99b4a4  (branch: main, github.com/Dhanush-sai-reddy/norhound)

This is the commit that contains the code and the shipped v2 corpus. The only
commits after it are documentation-only. My earlier submission (commit d16266a,
sent 19 Nov) is superseded by this revision; please score this hash.

DEADLINE NOTE
Entries and revisions are accepted through **22 November 2026**, and up to
four revised exact commit hashes are allowed through that date (five versions
in total). The October dates still shown on the Unstop listing (share 17 Oct,
revisions 18 Oct, run through 21 Oct) are superseded: the current Builderr
brief says "New entries and revisions are accepted through 22 November 2026",
and Builderr's platform rules say the challenge page wins when a summary
conflicts with it.

ONE COMMAND TO RUN
  cd norhound-starter-kit
  uv sync
  uv run playwright install chromium     # one-time, for the browser rescue stage
  scripts/run_official_batch.sh --batch organisations.jsonl

`organisations.jsonl` is the JSONL batch of organisation numbers you supply —
one per line, either as a bare number or as an object with
"organisation_number". That command checks the input count before any work
starts, runs the whole pipeline over your batch, attaches the refresh history
against the previous snapshot, and writes:

  out/run-<run-id>/envelopes-final.jsonl    one terminal envelope per input
  out/run-<run-id>/official-run-report.json runtime, requests, cost, audit

For the local 1,000-company reproduction (the same pipeline, selecting its own
batch with seed 20260823) the command is:

  scripts/run_full_batch.sh

It runs all 14 stages in order: select the 1,000-company manifest, registry
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
  company: 113,439 claims backed by 43,756 evidence records
- `out/submission/observations.jsonl` + `out/submission/labels.jsonl` — the
  40,144-row re-verified corpus (40,106 rows published)
- `out/submission/summaries.jsonl` — 1,000/1,000 deterministic summaries
  (what it does, financials, staff, hiring, the changes since the previous run
  and the unknowns — 361 of them state a detected change and its source)
- `out/submission/eval.json` — the audit report
- `out/submission/measure.json` — the six-field recall proxy
- `out/submission/measure-family.json` — the per-family recall report
- `out/submission/site/` — the searchable viewer (1,000 company pages + compare
  view + bulk export)
- `out/submission/smoke-100/smoke-envelopes.jsonl` +
  `out/submission/smoke-100/smoke-report.json` — the 100-company smoke test:
  **100 requested, 100 returned, complete**, 10,306 claims and 3,399 evidence
  records, produced by `scripts/build_smoke_report.py --run-dir <run> --count
  100 --output-dir <dir>` (exit code 1 if any requested company comes back
  missing or incomplete): 100 requested, 100 returned, complete, 11,165 claims
  and 4,297 evidence records. This is the artifact the brief asks for.
- `scripts/promote_run.sh` also writes `out/norhound-signalpost-submission.zip`
  (the same package as one archive). `out/` is gitignored, so the archive is
  built locally rather than committed — every file inside it is committed
  under `out/submission/`.

The 1,000-company corpus, the manifest and the viewer are shipped as evidence
of what the agent does. The brief is explicit that precomputed profiles and a
company manifest are not submitted for scoring: "Freshness, exact attribution
and reproducible execution — not a submitted static profile file — are what the
official run tests."

PRECISION (the gates that matter more than volume)
- entity precision **1.0**, metric precision **1.0**
- wrong-company publications **0**, unsupported publications **0**
- 40,106 of 40,144 re-verified observations published; unverified rows never
  publish
- every published fact carries source URL, retrieval time, reporting or
  effective date, content hash and extraction method
- 629 tests pass (`uv run python -m unittest discover -s tests`)

REFRESH AND THE RUN REPORT
The brief asks for refresh metadata and material changes since the previous
run, with idempotent refresh and prior snapshots preserved. The agent takes
the previous run's envelopes and emits, for every company, typed old -> new
change records with the source URL, retrieval time, effective date and the
content hash of both the old and the new value; the earlier evidence behind a
recorded change is preserved even when the current run no longer carries it.
A change is keyed by a content hash, so re-running the same comparison records
nothing twice — the stage is idempotent by construction, not by convention.

`out/run-<run-id>/official-run-report.json` is the machine-readable run
report: runtime, request count, third-party cost, envelope and claim counts,
the identity precision, and the declared source rights. A count that was not
measured is reported as a bound with the reason, not as a guess.

RECALL — what is measured, and what each number means
These are **our own reproducible measurements, not official scores**. The
challenge publishes no score for this revision, so nothing below is presented
as one.

Six-field external recall proxy (`scripts/measure_recall.py`, mean of six
fields × 50): **22.51 / 50** (up from 22.38 in the 19 Nov revision).

| field | recall | what it counts |
|---|---|---|
| any_external | 0.994 | ≥1 source outside the register |
| two_platforms | 0.629 | ≥2 independent sources outside the register |
| workforce_jobs | 0.020 | a real role card, job-feed item or apply action |
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
| other | 1000 / 1000 | 1.000 |
| news | 1000 / 998 | 1.000 |
| website | 602 / 577 | 1.000 |
| social | 205 / 177 | 1.000 |
| hiring | 49 / 84 | 0.583 |
| reviews (not scored by the rubric) | 32 / 323 | 0.099 |

Opportunity-weighted over the scored families this reads 49.60/50 for
all-claims coverage and **13.73/50 for claims backed by a source outside the
register**, which is the variant that tracks external recall — the all-claims
variant counts the register's own facts, which every company has. I am
reporting the lower one rather than the flattering one.

The hiring row needs its definition: **49** companies publish a hiring-family
claim, **15** of them have a real role card (NAV job-feed items and verified
company-site role cards) and the other 34 publish an explicit `careers_page` signal —
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
- `workforce_jobs` (8.16): bounded by how many real adverts a keyless source
  holds. NAV's feed reaches 14 companies, and the new company-site role-card
  connector adds role titles with apply actions on verified sites (20 cards
  over 8 companies, all on companies that already had a hiring claim, so the
  **company** recall is unchanged — only claim depth grows). Finn.no is excluded
  (no organisation numbers, terms of service forbid it) and NAV's live search
  answers HTTP 429 to unauthenticated bulk.
- `two_platforms` (3.09): 371 of the 374 directory-only companies state a
  website domain, and 175 of those domains are declared by the same organisation
  number in the register's sole-declarer index (0 mismatches). Fetching them and
  requiring a legal-name match yields a proven second platform for a small
  number more; the identity gate is not widened. The remaining companies have
  no verified website, no Wikidata item and no other keyless source that states
  their organisation number — closing it would mean trading the 95 % precision
  gate for a fraction of a point.

The full write-up, with the probes and the arithmetic, is in
`norhound-starter-kit/RECALL_LEVERS.md`.

WHAT CHANGED IN THIS REVISION (v2, commit a99b4a4)
- **Real role cards from verified company sites.** A role title must name a role
  and carry an apply action (link, button, mailto or a real form); a bare careers
  page still emits only `careers_page`, and a page naming another legal entity
  is rejected before the host-only proof. 20 role cards over 8 companies on the
  fresh corpus (an earlier live probe over the old corpus found 28 over 11 after
  the same precision rules). The titles are real: "Senior digital markedsfører",
  "BPA-assistenter over hele Norge", "Operatør – sammenstilling av missiler",
  four roles at STATICUS NORGE AS.
- **Sitemap-driven news depth.** The site's own sitemap now seeds candidate news
  pages (the bounded crawl never reaches them all): per-company sitemap cap 10 →
  60, news candidates 12 → 24, dated items 8 → 16. News observations **194 over
  86 companies → 490 over 140 companies, 447 dated**; sitemap observations
  2,475 → **10,389**. Undated navigation pages and prose-only dates on
  additional pages are still never published.
- **A proven second platform for directory-only companies.** 175 of the 374
  directory-only companies have a website domain declared by their own
  organisation number alone in the register's sole-declarer index. Fetching
  those domains and requiring the legal name on the page (plus a parked-domain
  filter) yields 10 new company-site observations, with a proof the verifier
  re-derives from the index, the registry field and the stored body.
- **GLEIF identity actually publishes.** The LEI connector already emitted 13
  exact-entity rows, but the verifier did not recognise its proof type and
  rejected all 13. It now re-derives the validatedAs organisation number, the
  Brønnøysund registration authority and the body hash before trusting the row.
- **ATS false positives fixed** — jobbnorge navigation links are no longer
  marked as role cards.
- **One dated news item per page, not one per company** (v1, retained). The news
  connector publishes every captured news page with a machine-readable
  publication timestamp, keeps a bounded first-party body, and never publishes
  a prose-mined date on an additional page or an undated navigation page as
  padding.
- **Hiring integrity fixed** (v1, retained). A discovered link can no longer
  become a role title; a bare careers page is an explicit `careers_page` signal.
- **Three recall fields de-tautologised.** `workforce_jobs` was counting
  headcount; `any_external` and `two_platforms` were counting the register,
  which every profiled company has; `buzz_engagement` was counting
  Brønnøysund annual-account announcements, which every filer has. Each is now
  defined over something the company actually has to earn — a source outside
  the register, a real advert, a third-party mention. The proxy fell from a
  flattering 33.43 to an honest 22.38 (22.51 in v2); the coverage it claims is
  now coverage that exists.
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

EXPECTED COST PER OFFICIAL BATCH
- External spend: **$0**. No paid API is called and no model key is needed.
- Requests: **23,096 measured** for the shipped 1,000-company v2 corpus
  (`out/submission/official-run-report.json`). The count is taken at the
  interpreter level, so every subprocess is included; only the host, method and
  status are recorded, never a URL or a payload.
- Runtime: **~187 minutes active work** for the v2 1,000-company corpus (55 min
  base batch + ~120 min external connectors + finalize/post). The wall-clock
  start-to-finish figure in the report is 1,016 min because the machine
  restarted between the base batch and the resumed external pipeline — no work
  ran in that gap, and both numbers are recorded in `official-run-report.json`.
  (The opt-in OCR stage would add ≈3 h 20 m and measures 0 scored points, so it
  stays off; `SLOW_STAGES=1` turns it on.) The brief says each official run has
  a fixed time and resource budget Builderr supplies — send me the limit and I
  will fit the run to it.
- Models: none. Licences: NLOD (registry), CC0 (Wikidata/GLEIF), ODbL where
  applicable; website content is quoted at claim level with source URL,
  retrieval time and content hash.

CONTACT
Dhanush Sai Reddy
(Registered on Unstop as Dhanush-sai-reddy)

Regards,
Dhanush
