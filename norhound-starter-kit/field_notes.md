# Field notes — public Signalpost repos (read 22 Sep 2026)

Saved clones: `/home/dhanushsr/Downloads/hackathons/signalpost-field/` (13 repos).

## Board status (16 Sep 2026 review)
Anmol 76.71 · Ajai 70.32 · digikuo 66.92 · Harsh 66.92 · Rakesh 66.92 ·
Sanjai 65.92 · Karthik/AAFA 65.19 (all qualified) · Sudhir 62.92 · Hardik 57.16 ·
Dhanush (us) 54.92 (not qualified). Gates: 65 overall / 21 coverage /
60% external recall / 95% external precision. 5 versions max, revisions close Oct 18.

## Who is who (public repos)
- **AnSa30-06/signalpost-norway** — board #1 (76.71). Independent build. Fully mined.
- **Rakesh-Tummala/signalpost-company-agent** — almost certainly board "Rakesh" (66.92).
  Same starter-kit lineage as us. Has: build_viewer.py (single-file offline viewer),
  extract_company_site_careers.py (careers-page hiring signal),
  extract_prior_year_financials.py (prior-year figures anchored on known API value),
  fetch_financial_history.py, run_exa_discovery.py.
- **meet252501/signalpost-norway-agent-** — "Meet", unscored 13 Sep, gone 16 Sep.
  Same lineage. Extra connectors (bing, press, places/play, purehelp). Has
  run_places_bypass_connector.py — policy edge, DO NOT touch. Its "95.191" is self-scored.
- **TusharTechs/fotavtrykk** — independent, unscored. Best-written codebase in the field.
  Has: synthesis.py (deterministic summaries with FORM_WORDS, _money formatting,
  unknowns list, changes prose), viewer.py (static evidence viewer),
  connectors/wikidata.py (P2333 exact-orgnr lookup, ~6 reqs/100 cos, handles+wiki),
  connectors/news.py (Norwegian date parsing, per-post dated observations),
  diff.py (typed changes + idempotency), audit.py.
- **officialarghya29/kildespor** — independent, unscored, MIT, precision-first.
  Claims public NAV feed carries no orgnrs (CONTRADICTS our 65 postings — audit ours).
  Only registry-listed domains auto-verified (8.6% website coverage).
- **divyanshAgarwal123/signalpost-company-research-agent** — starter-kit based, unscored
  ("not independently scored"). Valuable docs: PRIZE_STRATEGY.md, EVALUATION_ASSESSMENT.md.
  Design rule adopted: bounded-scan absence = deferred, never published as withdrawal.
- **Faizi-khan / HemantSharma1803 / rahul25118 / ramsai676 / Balram-1 /
  biswajeetdev / iamjaydatt2006** — small or same-lineage forks. rahul = Streamlit UI,
  Hemant = FastAPI server (both need a server — weaker than static file:// for submission).
- **Board entries with NO public repo**: Ajai, Penge, digikuo, Harsh, Sanjai,
  Karthik/AAFA, Sudhir, Hardik. Cannot be read.

## Steal list (reimplement, don't paste; respect licenses; cite)
1. Wikidata P2333 connector (fotavtrykk) — VERIFIED LIVE 22 Sep (Equinor 923609016 → Q1776022).
2. Summary polish (fotavtrykk synthesis.py) — form words, money fmt, unknowns, changes prose.
3. Per-post dated news with NO date parsing (fotavtrykk news.py).
4. Careers-page extractor (Rakesh).
5. Prior-year OCR anchoring (Rakesh) — for trend answers.
6. Defer-don't-withdraw refresh rule (divyansh docs).

## Do NOT take
- meet's places_bypass connector or anything "bypass"-named.
- Faizi's difflib 0.72 matcher (weaker than our gate).
- Any secrets/keys (none seen). Server-based UX (Streamlit/FastAPI) as submission format.

## Builderr previous challenges (pattern research, 22 Sep 2026)- No past company-research challenge — Signalpost is the first of its kind.
- Trading Round 1: Arnav Chauhan won (+5.91% vs QQQ -3.91%); winner's code is PUBLIC
  and runs as the benchmark every later entrant must beat. Lesson: on Builderr,
  winning code becomes the public benchmark — plan for our code to be read too.
- Local dictation: Sankeerth won; approach shipped into the RambleFix product.
  Lesson: Builderr winners ship into real products (also: $100k live book for trading).
  A clean, well-documented repo has value beyond the prize.
- Same builder "Anmol" is #3 (below bar) on the dictation board — active across challenges.
- Soham's dev.to post (12 Sep 2026) confirms the union-scoring design: checked reference
  collection from all submissions + own crawlers; 70/30 company-vs-claim weighting;
  coverage is against the checked collection, not the whole web.

## Devpost mining — investigation-hackathon winners (22 Sep 2026)
Saved clones: `/home/dhanushsr/Downloads/hackathons/devpost-field/` (5 repos).
Different domain (cyber forensics), same problem shape (autonomous investigation +
evidence + zero hallucinations). Transferable patterns only — no code copied.

- **calebevans/mulder (FIND EVIL 1st, $10k)** — anti-hallucination AT THE API BOUNDARY:
  every finding must cite evidence_refs that are real tool_call_ids in the append-only
  audit log; fabricated citations are structurally impossible to submit. Plus an
  adversarial "Alternative Narrative" phase and quality gates with bounded retries.
  Publishes every run + scorecard unmodified. Lesson for us: our verify_and_label is
  the analog of their skeptic; gap = no check that summary evidence_ids resolve to
  envelope evidence (add a validator).
- **tupils1/protocol-siftpp (top-5)** — per-finding verdicts confirmed/inferred/refuted
  + confidence; read-only tool layer; per-finding citation {command + output hash}.
  Lesson: add confirmed-vs-inferred status + confidence to our deterministic answers.
- **allisterb/Camel (3rd)** — code-mode/agent infra for LLM investigations. Not
  transferable (we run no LLM in-pipeline). Skipped.
- **nebulae/trudi (2nd)** — hypothesis-driven causal chains. LLM-domain. Skipped.
- **Sentinel / sherlock (Commons) / ANGELA** (Devpost writeups only, not cloned) —
  "every finding cites a specific public record"; deterministic fallbacks at every
  layer; all three report entity resolution as the hardest problem. Validates our
  gate-first investment and degrade-cleanly design.
- FIND EVIL compliance note: building on open-source tools explicitly allowed, novel
  contribution documented (MIT). Same posture as ours: reimplement ideas, cite sources.

## Internal directives (carry-over)
- Deterministic, no-API-key summaries. Static file:// site, no server.
- Do not mention removals/scrub or the requirements sheet in Builderr emails.

## API cost audit (verified live 22 Sep 2026)
FREE, no key: Brreg oppdateringer (HTTP 200, Anmol code has zero auth) · registry
contacts (already in our bulk) · site parsing/sitemap (our crawls) · Wikidata/Wikipedia
(CC0, verified live) · NAV feed (public token) · iTunes Search API (verified live, no
auth — app-presence signal) · OSM Nominatim (HTTP 200; free under 1 req/s + UA policy) ·
Fagfolkguiden · Regnskapsregisteret/roller/underenheter/konsern (in use).
KEY-GATED (skip): Brave ($5/1k) · Firecrawl · Exa/Tavily · Google Places (paid) ·
NIM (replaced by deterministic) · Bing (key) · Google Play (no official API, unofficial
only) · LinkedIn/Indeed/Meta direct (terms-blocked at any price).

## NAV proof-quality audit (2026-09-22) — RESOLVED: feed carries orgnrs
- kildespor claims the public pam-stilling-feed.nav.no feed carries no orgnrs. Verified LIVE: false for current postings.
- Full chain verified: feed detail `ad_content.employer.orgnr` = 971686294 (uuid 4c38bf0e…, Favorit As, from our frozen index) →
  brreg underenhet GET returns navn=FAVORIT AS, overordnetEnhet=811598992 → brreg enhet GET returns navn=FAVORIT AS @ 811598992.
- Confusion source: an INACTIVE posting (first feed page = oldest entries) returns {sistEndret,status,uuid} with no ad_content;
  ACTIVE postings carry full ad_content.employer.orgnr. Our build filters ACTIVE before the detail fetch → never affected.
- Frozen index (data/nav-job-index.jsonl, built 2026-09-15, posting_count=9979, resolved_parent_enhets=3625) is genuine.
- Thus the 65 NAV job observations on the 1000-batch are precise and exact-entity. Residual caveat: postings expire/drop INACTIVE,
  so org existence on the feed is time-bound — matches our dated-claim model.

## Coverage connectors shipped on web1000 batch (2026-09-22) — intermediate verified eval
- Ran the new keyless connectors against the REAL shipping corpus `out/web1000-profiles.jsonl` (1000 website-bearing orgs).
- Baseline (frozen shipped): 1391 observations, 944 published/audited, any_external 0.358, two_platforms 0.175.
- Merged + re-verify + re-eval (local connectors only: registry contacts 1858, site description 481, substructure 2444):
  - published_audited **5186**, entity_precision **1.0**, metric_precision **1.0**, wrong_entity **0**, unsupported **0**.
  - coverage: any_external **0.818**, two_platforms **0.356**, workforce_jobs 0.036, ratings_reviews 0.015, buzz 0.352.
- Still to merge: sitemap lastmod (1939 publishable, all exact) + registry-update feed + wikidata (sampled index, P2333 sparse).
- Verify/label runs ~100ms/row (tldextract suffix fetch), ~6174 rows ≈ 10 min in-process; final merge ≈ 8k+ rows.
- The claims are official-API / company-site-bound exact-entity rows keyed by organisation number; see each connector's claim_boundary.

## Competitor + Devpost context (saved 2026-09-23)

- This is a **Devpost-hosted** contest: "signalpost-norway" (Builderr Signalpost,
  Norwegian company-signal footprints, minimum 1,000 companies per entry).
- Competitor clone pulled for comparison, stored at `/tmp/anmol` (ephemeral —
  wiped on reboot) = `https://github.com/AnSa30-06/signalpost-norway.git`,
  HEAD `e89e7b1` "Revision 3 artifact from a6b044a: 1,000 profiles under the
  strict website gate; audit, full-run and judge-shaped numbers".
- Their canonical numbers (eval/report.json): official_website 0.118,
  accounts/roles/workplaces 0.999/0.999/0.757, dated_activity 1.0,
  precision 1.0, recall 0.643, wrong 0. Their 0.999 accounts/roles and 1.0
  dated_activity are *registry-feed-driven* (official NAV/Brreg feed), not
  external-website footprint.
- Ours (shipped 944/p1.0): any_external **0.821 (keyless) / 0.358 bare**,
  workforce 0.036, ratings 0.015; precision **1.0/1.0, wrong 0**. Keyless =
  $0, no key, no secret to revoke.
- **Head-to-head (same 1.0/1.0 precision gate, 0 wrong both):** our official-
  website any_external 0.821 vs their 0.118 (~7x), workforce 0.036 vs 0.036
  (tie), ratings 0.015 vs ~0.015 (tie). They only "lead" on the
registry-feed
  axes (accounts/roles/dated_activity) which are registry-derived, not
  external-footprint — so under a sheet that scores "external footprint" as
  its own sub-category, that lead doesn't count as external size evidence.
- The rub (only thing I'm unsure about): the sheet's coverage sub-category may
  expect the *shipped* 944/p1.0 gate number (0.358) rather than the keyless
  0.821. Both are real; which ships depends on the sub-cat name. Revisit once
  the coverage sub-cat name is pasted.

## Similar-agent-hackathon patterns (inspiration only, saved 2026-09-23)

Swept agent+web-research+evidence hackathons (Devpost, lablab/Bright Data, AWS agent
series, Jaseci/UC-series). Winner and runner-up code was read for DESIGN ONLY; no
clones are kept and this repo carries no references to any of them. Patterns that
transfer to our deterministic, precision-first pipeline (reimplement from the idea):

- **Corroboration gate = the precision lever.** Escalate a finding to a higher
  status/verified only when ≥2 *independent* specialist signals agree; a single
  signal caps lower. The documented best precision (98%) across these contests came
  exactly from this rule. For us: publish high-impact claims only on independent-path
  evidence; one source alone never clears the exact-entity bar.
- **Decision bands enforced in code, not prose.** Derive the label from a numeric
  score in code so a chat/external text can never contradict the decision.
  (Mirror of our verify_and_label: label is recomputed from frozen evidence.)
- **Citation verifier post-pass.** After collection, every claim's source must trace
  to a real collected source id, else it is flagged/refused — done at the API/state
  boundary, not trusted to the model. We have the evidence_ids gap covered by
  verify_and_label; keep the "resolve-and-reject" step explicit.
- **Tamper-evident provenance.** Snapshot each source, SHA-256(url+content+timestamp)
  per file, combine into a merkle/leaf tree so any later edit is provable. We already
  store content hashes; optional upgrade: chain/merkle them so evidence is
  tamper-evident end-to-end.
- **Deterministic extraction, LLM reasons but never computes.** Compute all facts
  with code; tier claims VERIFIED / qualified / inferred / UNVERIFIABLE. Closest to
  our deterministic engine — adopt the tier vocabulary for answers.
- **Agent-per-source + caching** to cut cost and raise per-source accuracy (our
  connector isolation + request budgets already mirror this).
- **Adversarial reviewer + pause/abstain.** A second pass raises objections; when
  blocking evidence is missing, abstain instead of inventing past ambiguity.
- **Adaptive / peer-relative thresholds** beat hardcoded cut-offs; always output a
  cited case file (source url + date per claim), never a bare score.
- Deeper reads (all 9 clones) added these details:
  - **Drop the LLM from synthesis entirely.** One winner's synthesis run is pure
    rule-based Python over the specialist findings (they dumped the LLM after
    latency/unreliability) — corroboration, risk level, reasoning narrative and
    action are all derived in code, plus an `agent_signals` boolean array per case
    so the user sees *which* signals fired. Direct validation of our
    deterministic-first stance.
  - **Citation match at two levels:** exact source URL, else domain match,
    plus an authoritative-source allowlist (sanctions/registry domains verified
    even without a scraped page). Our verify_and_label could add the domain-level
    fallback for official-registry sources.
  - **Hash the exact ISO timestamp string, byte-for-byte** (never re-format it),
    because the verifier must re-hash the same bytes the collector did; report
    per-source mismatches, not just root mismatch. Content-hash caveat for our
    re-verify step.
  - **Citation JSONPath with prefix fallbacks:** LLM cites `financials.1` → try
    each of the six known state roots; tier by path (`verified`/`qualitative`/
    `inferred`/`unverifiable`); flag **contradictions** (same citation, opposing
    claims) and tag failed claims with originating agent + failure reason. Tier
    vocabulary + contradiction pass beat our current label-only audit.
  - **Judge must not extract its own claims** — it verifies the pre-extracted,
    numbered claim list only; then **majority-vote over multiple judge passes**,
    with a conservative tie-break (correct==incorrect → incorrect) and
    correction/source carried on the winning verdict. Cheap multi-pass agreement
    beats a single gate for high-impact claims.
  - **Tool-defaulted confidence + sha256 fingerprint for dedup** (tool|kind|value),
    not whole-text. Our rows could carry a similar stable identity key.
  - **Agent-per-source + cache layer** as the cost control; run-level rate-limit
    precheck before the pipeline starts (IP/key-based) so you never start a batch
    you can't finish.
- Winners in several series published no code; several non-winners were the useful
  ones. Nothing here is copied, cited, or referenced outside this note.

## Builderr winner precedent (platform fact, saved 2026-09-23)

- Builderr PUBLISHES the previous round's winning code as the next benchmark (trading
  Round 1 winner has a public repo + method brief; the dictation winner's approach
  shipped into the sponsor's product). Consequences:
  - If we win, **our code becomes the public benchmark** → keep the repo clean,
    keyless, deterministic, well-documented.
  - Winner code from their own rounds was standard-library, no network/LLM calls in
    the decision loop, explicit state machine — same no-API-key stance as ours.
  - Winning entries ship into real products; a clean repo has value beyond the prize.

## Signalpost board + spec reload (fresh 2026-09-23)

- Board live page is UNCHANGED since the 16 Sep review: 10 submissions / 10 assessed /
  7 qualified · Anmol 76.71 · Ajai 70.32 · digikuo 66.92 · Harsh 66.92 · Rakesh
  66.92 · Sanjai 65.92 · Karthik/AAFA 65.19 (qualified) · Sudhir 62.92 ·
  Hardik 57.16 · Dhanush (us) 54.92.
- Published spec (`builderr.ai/api/challenge/signalpost`) adds two nuances vs the
  16 Sep reading:
  - **Scoring is now explicitly dimensional, not gated**: "Qualification requires
    an official run and 65 overall; coverage, recall and precision are scored
    dimensions, not separate qualification thresholds." → the old 21-coverage /
    60% recall / 95% precision gates are NOT separate bars; only 65/100 + no
    material wrong-company match gates. (Still: accuracy carries 30/100.)
  - **Sparse-recall carve-out**: recall "not measured below 15 positive company-field
    opportunities across at least three external field families; not a qualification
    gate." → niche family coverage can't sink us; concentrate on the big families.
  - External coverage weights: **70% company recall / 30% claim recall** against the
    cumulative verified union; **every entrant is rescored whenever the union
    expands** → the union only grows, so coverage numbers drift as entries verify.
  - The traded-leader feed-driven accounts/roles/dated_activity rows do not expand
    the external (website/jobs/reviews/activity) union, so our external-footprint
    lead on those axes should hold or widen as the union grows.
- `/api/leaderboard` served the trading round only; the signalpost board is not in
  the public API — board values above were scraped from the challenge page.

## 700-company private diagnostic (received 27 Sep 2026) — full note in `private_diagnostic_700.md`

Private diagnostic, **not** an official score / qualification decision / leaderboard
update. Ours: **48.69/100**. Applies only to the immutable 700-company capture; does
not replace results sent for other runs or revisions. Do not reply on the thread yet.

Evaluation model changed in three ways, all of which move the ruler:
- 700 companies instead of our 1,000-company entry batch.
- **Scoring reads only sources captured in our first run** — no second live crawl. A
  fact is only as good as the body we retained.
- Reference collection now admits a fact verifiable from **any** participant's captured
  source, not just the organizer's collector. Fairer, but the recall denominator grows.
- ⇒ 48.69 is **not comparable to 54.92**. Read the three gaps, not the delta.

Credited: official-data base; basic website + social discovery.

Three gaps, and each traces to a file in the tree — the first two are shipped-artifact
regressions, not discovery gaps:
1. **Hiring: the shipped artifact has 0 job_board and 0 company_directory rows.**
   `out/final-keyless.external.jsonl` = 0/0; `out/keyless-nav-all.external.jsonl` = 10,044/93.
   `out/final-eval.json` reports 65/45, describing a *different* file than the one we
   shipped. Cause: `--nav` / `--reviews` still opt-in at
   `scripts/run_external_pipeline.py:54`, consolidation at `:176` only appends NAV when
   flagged. AGENTS.md "Next Action #1", still not done. The supply already exists — NAV
   index holds 9,979 publishable postings over 3,625 orgs — and a NAV feed item is
   exactly the "real job-feed item" the tightened hiring definition accepts.
2. **News: hash + page title, no body.** `evidence_span` is literally the page title
   (`"News | Comex Group"`); no retained body ⇒ unverifiable under the corrected model.
   Volumes also thin: 56 activity obs / 1,000 cos, 8 dated. ⇒ "retain bounded
   first-party pages".
3. **No submitted data-linked product surface.** `scripts/build_static_site.py` exists
   and its test passes, but there is no `out/site/` in the repo — `out/` is gitignored
   and only 22 files under it were force-added. Full marks lost for code we already wrote.

Also: social extraction already exists (`website.py:103` markup, `:122` JSON-LD `sameAs`)
— the gap is *yield* (homepage-only crawl, `_priority_links` capped at 6).
And `out/SUBMISSION-REPORT.md` is stale (describes `batch1000f`, 85 obs / 38 profiles,
still documents the NIM/`NVIDIA_API_KEY` summary path).

Reviewer constraint to respect: **do not optimize for generic careers keywords.** A
generic careers page is not a hiring fact — publish one only with a real role card, a
job-feed item, or an apply action. Emit bare `/karriere` pages as an explicit
`careers_page` signal, never `hiring: true`.
