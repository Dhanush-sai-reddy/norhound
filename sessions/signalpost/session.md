# Autoresearch session: signalpost

## Skill version
2.0.0

## Mode
narrow

## Target
- Path: /home/dhanushsr/.local/share/opencode/worktree/85c9ea/autoresearch-improve-recall/norhound-starter-kit
- Stack: Python 3.12
- Test command: `uv run python -m unittest discover -s tests -p 'test_*.py'`
- Linter: none
- Branch: autoresearch/narrow/signalpost
- Config: none
- Scope: external recall connectors, exact-entity verification, recall measurement, and tests

## Baseline
- Tests: 505 pass (`uv run python -m unittest discover -s tests -p 'test_*.py'`, 8 skipped)
- Base commit: af49188
- Date: 2026-11-04

## Goal (narrow only)
- Metric: exact-company company recall per official fact family (points out of 50), measured on the published contract envelopes with `scripts/measure_family_recall.py`
- Measurement command: `uv run python scripts/measure_family_recall.py --envelopes out/submission/envelopes.jsonl --output out/measure-family-submitted.json`
- Baseline value (all claims): 48.3036/50; (external-only): 11.6004/50
- Target value: close the website and hiring families with entity precision >= 0.95 and zero wrong-company publications
- Current value (shipped run `newsdepth-20261118T120128Z`): family recall website 597/577, hiring 49/84, identity 1000/1000, news 1000/998, other 1000/1000, financials 994/1000, roles 994/1000, social 204/177, reviews 32/323; external-only proxy 13.2454/50; entity precision 1.0, 0 wrong-company publications
- Secondary metric: `scripts/measure_recall.py` six-field proxy, **22.3833/50** on the shipped corpus (any_external 0.994, two_platforms 0.620, workforce_jobs 0.014, ratings_reviews 0.032, buzz_engagement 0.994, sentiment 0.032)

## Angles (narrow only)
| Priority | Name | Hypothesis | Status |
|----------|------|-----------|--------|
| 1 | Evidence-verifiable exact-source recall | Existing exact-company connectors can add publishable observations if retained source bodies and exact organisation-number proofs are re-verifiable, without weakening identity gates | done |
| 2 | Website-family coverage | The register's own website filing, the sole-declarer domain index, a description fallback and a browser rescue recover homepages the plain crawl cannot read | done (388/577 -> 576/577) |
| 3 | Hiring-family coverage | NAV's official feed plus public ATS feeds, each gated on the exact legal entity, close the hiring family | done (65/84 -> 84/84 on the 7 Nov run; 49/84 on the 17 Nov run after the role-card rule was tightened) |
| 4 | Official-run path | One documented command must run the whole pipeline over a supplied batch, refresh idempotently and report runtime, requests and cost | done (rehearsed over 1,000 companies on 17 Nov 2026) |

## Cycles completed
- 2026-11-07: browser rescue built and wired into the external pipeline before the site stages (19 tests).
- 2026-11-07: family-recall scorer built with an external-only variant (21 tests).
- 2026-11-07: Google and proff excluded from publication (keyless + source-rights).
- 2026-11-07: DNS resolver retry added after the full run lost 330 homepages to a transient resolver burst (6 tests).
- 2026-11-07: rescue stage made to degrade when playwright is absent (1 test).
- 2026-11-07: submission artifacts rebuilt from the 32,713-row keyless corpus; commit c855d59.
- 2026-11-17/18: the evaluator's command (`scripts/run_official_batch.sh`) rehearsed over 1,000 companies end to end: 1,000 envelopes, precision 1.0, 0 wrong-company, 21,159 measured requests, 117.7 min, $0; refresh 252 changes over 126 companies, idempotent re-run 0 new; commit 5a7aeed.
- 2026-11-18: news-depth pass — the news connector now publishes one dated item per captured news page (machine-readable timestamps only for additional pages), so the shipped corpus carries 194 news observations over 86 companies, 172 dated (was 86/64) and 3,175 `dated_news` claims (was 3,073). Measured cost: 1,007 requests, 93 s. Shipped totals: 105,266 claims, 35,421 evidence, 31,885 of 31,911 published, precision 1.0, 0 wrong-company, 22,166 requests, 119.2 min, $0; refresh 277 changes over 144 companies, idempotent re-run 0 new and 277 preserved.

## What's been tried
- 2026-11-04: identified a clean worktree at commit af49188 so the user's 162-file dirty main checkout remains untouched.
- 2026-11-04: restored the tracked-test dependency `scripts/run_feed_news_connector.py` from the dirty main checkout; no main-checkout files changed.
- 2026-11-07: OSM `ref:NO:orgnr` measured as a dead end (4 of 1,000 orgs, 0 social tags) and not wired in.
- 2026-11-07: DuckDuckGo HTML discovery dead (anomaly page); Finn.no vetoed on terms and zero org numbers in the payload.
- 2026-11-07: the second full 1,000-company run was degraded by a transient DNS burst (330 homepages lost, rescue 0/133). The hosts all resolve now; the run was discarded and the pre-burst corpus shipped.
- 2026-11-18: the public ATS boards find postings for 3 companies, but the identity gate rejects them (posting pages sit on third-party boards and the frozen site evidence cannot re-derive the board link). Left unpublished: the gain would be 3 role-card companies, the risk is a wrong-company publication.
- 2026-11-18: every keyless ratings source re-probed and still blocked (403) or JavaScript-only; 0 of 17 homepages embed a widget. Not retried further.
- 2026-11-18: the directory-stated website domain was measured as the only remaining route to a second platform for the 374 single-platform companies. On a 60-company random sample: 34 homepages fetched, **0** stated the organisation number anywhere (including the footer), 3 passed the unchanged identity gate. The ceiling without widening the exact-entity rule is ~5 % of the 374, so the rule was left alone.
- 2026-11-18: the careers-page route to hiring was checked and not wired. Measured over the publishable profiles: 46 companies have a captured careers-path page (73 pages in all); 31 of those pages, across 25 companies, carry role-listing wording ("vi søker", "ledige stillinger", "søknadsskjema"), but the wording is generic open-application copy rather than a role card with a role title and an apply action. The only company with real per-role pages is Glencore Nikkelverk (`/no/careers/apprentice`, `/no/careers/summer-job`, `/no/careers/available-positions`); the other deep paths under a careers segment are news slugs that merely contain "karriere" (Heia Nord-Norge, org 926941836). A bare careers page stays a `careers_page` signal, never `hiring: true`.

## Open issues
- Keyless ratings/sentiment ceiling is 32 of the 323 review opportunities (Fagfolkguiden only). The rubric does not score that family.
- `workforce_jobs` sits at 0.014 (14 companies, all NAV). The ATS postings cannot be re-derived from frozen evidence, so the gate keeps them out.
- 374 of 1,000 companies have exactly one source outside the register (the company directory) and no verified website or Wikidata item; `two_platforms` is capped at 0.620 by that.

