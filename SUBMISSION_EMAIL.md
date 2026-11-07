Subject: Signalpost submission — NorHound Company Research Agent (commit 78244c1)

Hi,

Submitting the NorHound agent for the Signalpost challenge. This revision is
**fully keyless**: every stage runs without an API key, a login or a paid
account, so the cost per 100-company run is $0.

REPOSITORY
https://github.com/Dhanush-sai-reddy/norhound

COMMIT HASH
78244c19778634aad7565ff8abd22081b999cd3a
(branch: autoresearch/narrow/signalpost)

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
- `out/submission/profiles-promoted.jsonl` — 1,000 company profiles
- `out/submission/manifest.jsonl` — the organisation-number manifest (1,000 rows)
- `out/submission/envelopes.jsonl` — 1,000 terminal contract envelopes, one per
  company
- `out/submission/observations.jsonl` + `out/submission/labels.jsonl` — the
  32,713-row re-verified corpus
- `out/submission/summaries.jsonl` — 1,000/1,000 deterministic summaries
- `out/submission/eval.json` — the audit report
- `out/submission/site/` — the searchable viewer (1,000 company pages + compare
  view + bulk export)
- `out/measure-family-submitted.json` — the recall report

RECALL (measured with `scripts/measure_family_recall.py`, against the official
per-family opportunity counts; same scorer run on the baseline corpus for
comparison)
| fact family | baseline | this revision |
|---|---|---|
| website | 388 / 577 | **576 / 577** |
| hiring | 65 / 84 | **84 / 84** |
| social | 185 / 177 | 177 / 177 |
| news | 1000 / 998 | 998 / 998 |

The two families that were below full coverage in the baseline are now closed.
The all-claims proxy reads 49.99/50 against 48.30 for the baseline; the
external-only variant (claims backed by a source outside the register) reads
11.56 against 11.60, because dropping Google removed 194 companies' worth of
external "other" facts and 8 social handles. I am reporting both numbers
rather than the flattering one. Full write-up:
`docs/evidence/family-recall-measurement-2026-11-07.md`.

PRECISION (the gates that matter more than volume)
- entity precision **1.0**, metric precision **1.0**
- wrong-company publications **0**, unsupported publications **0**
- 32,035 of 32,713 re-verified observations published; unverified rows never
  publish
- coverage: any_external 1.0, two_platforms 0.639, buzz_engagement 0.998,
  workforce_jobs 0.915, ratings_reviews 0.032, sentiment 0.032
- 504 tests pass (`uv run python -m unittest discover -s tests -p 'test_*.py'`)

WHAT CHANGED IN THIS REVISION
- **Website coverage closed.** The register's own website filing, the
  sole-declarer domain index, a website-description text fallback and the
  headless-browser rescue recover homepages the plain HTTP crawl could not
  read. Website family recall 388/577 -> 576/577.
- **Hiring coverage closed.** NAV's official job feed plus the public ATS
  feeds (Teamtailor, Recruitee, Easycruit, Workday, Lever, Greenhouse,
  SmartRecruiters), each gated on the exact legal entity — a feed company
  name must corroborate the organisation number, and a role card's published
  date is the published date, never the crawl date. 65/84 -> 84/84.
- **Google excluded.** The Places API needs a key and the Maps rows had been
  scraped against Google's Terms of Service, so neither is published. This
  costs the ratings/sentiment coverage (32 companies still have a Fagfolkguiden
  rating) and the review family, and the rubric does not score ratings,
  reviews or sentiment.
- **Resolver fix.** The 1,000-company run lost 330 homepages to a transient
  DNS burst (all 231 flipped hosts resolve normally when asked again). The
  resolver now retries a failed lookup with a bounded backoff, and the browser
  rescue goes from 0/133 to recovering eligible pages.
- **Browser rescue.** A headless Chromium recovers JavaScript-rendered and
  connection-failed homepages, re-running the unchanged identity gate so the
  exact-entity judgement is never widened.

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

EXPECTED COST PER 100-COMPANY RUN
- External spend: **$0**. No paid API is called.
- Outbound requests: roughly 40-60 public page/API requests per company, well
  inside the 2,000-request budget for a 100-company batch.
- Runtime: about 1 hour for the full 1,000-company run on 8 workers; roughly
  6 minutes per 100 companies.
- Models: none. Licences: NLOD (registry), CC0 (Wikidata/GLEIF), ODbL where
  applicable; website content is quoted at claim level with source URL,
  retrieval time and content hash.

CONTACT
Dhanush Sai Reddy
(Registered on Unstop as Dhanush-sai-reddy)

Regards,
Dhanush
