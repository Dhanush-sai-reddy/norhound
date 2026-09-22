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
