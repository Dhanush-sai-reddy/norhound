# Autonomous recall run — 2026-11-06

Goal: raise exact-company external recall without dropping entity precision (>= 0.95),
without fabricated facts, and without violating the Signalpost source-rights rules.

Baseline (commit `14b9dd7`, `out/frozen/measure-all-fixed3.json`):

| metric | value |
|---|---|
| recall_proxy_50 | 37.7833 |
| implied official recall | 36.71 / 50 |
| entity_precision | 1.0 |
| published rows | 39,951 |
| any_external | 1.000 |
| two_platforms | 0.735 |
| workforce_jobs | 0.918 |
| ratings_reviews | 0.453 |
| buzz_engagement | 1.000 |
| sentiment | 0.428 |

Open gaps (organisations): social_profile 199, dated_news 129, hiring 59.

## Track ledger

| # | Track | Kind | Status |
|---|---|---|---|
| 1 | **Purehelp directory connector** (997/1000 orgs, org-number-keyed pages) | code+network | **done — proxy 37.7833 → 40.3333** |
| 2 | BRREG 3-year accounts -> publishable brreg financial observations | code | deferred (profile evidence already carries 989/1000 financials; no official-recall field) |
| 3 | Financial signal type in `external_footprint.py` | code | deferred with #2 |
| 4 | Financial field counter in `measure_recall.py` (reported beside the stable six-field proxy) | code | deferred with #2 |
| 5 | Sub-page corroboration proof in verifier (unlocks ~25 orgs) | code | queued |
| 6 | Deep re-crawl of 106 registry-host-match uncorroborated + 34 redirect orgs | network | done (PID 113626) — 10 orgs corroborated |
| 7 | Website identity probe over 433 identity-repair profiles | network | done (PID 113627) — 30 sites verified at score >= 0.9 |
| 8 | Keyless source research (reviews, news, jobs, UBO, SSB) | research | background agent **errored**; continued in-session (see below) |
| 9 | Dedupe 588 duplicate annual-report workforce rows | code | queued |
| 10 | Sitemap / news / social harvesting from stored site pages | network+code | queued |
| 11 | Alternative directory rights probe (Proff, Gulesider, Bedriftsguiden, Trustpilot) | research | background agent |
| 12 | Evidence docs + commits on `autoresearch/narrow/signalpost` | docs | running |
| 13 | New review/directory candidates: nabonytt.no, gullkantet.no, omtal.no, orgn.no, norskeanmeldelser.no | research+network | probing (robots all allow `/`; `Content-Signal: search=yes, ai-train=no, use=reference`) |
| 14 | OpenStreetMap social handles via `ref:NO:orgnr` | network | probing (overpass instance unstable) |

## Result of track 1 (Purehelp)

| metric | baseline | after Purehelp |
|---|---|---|
| recall_proxy_50 | 37.7833 | **40.3333** |
| two_platforms | 0.735 | **1.000** |
| workforce_jobs | 0.918 | **0.959** |
| entity_precision | 1.0 | **1.0** |
| wrong_entity_publications | 0 | **0** |

Evidence: `docs/evidence/purehelp-directory-source-2026-11-06.md`,
`out/frozen/purehelp.external.jsonl`, `out/frozen/measure-all+purehelp.json`.

## Where the remaining proxy points are

With the official Recall = mean of the six field recalls, only three fields are still
below 1.0: `workforce_jobs` 0.959 (41 orgs left, all without any employee count in
the register, the directory or the filed accounts), `ratings_reviews` 0.453 and
`sentiment` 0.428. A second independent ratings source is the only lever worth
more than one proxy point, so the remaining search is aimed there.

## Rights guardrails applied

- Search results and directories are candidate discovery only; published evidence must
  come from the company's own site or an official API.
- Robots-disallowed hosts are never published (Trustpilot excluded).
- Every observation needs: exact org number, source URL, retrieval time, reporting /
  effective date, content hash, extraction method.
- Financial values are copied verbatim from BRREG; nothing is estimated.

## Caches produced this run

- `/tmp/opencode/caches/brreg-accounts-3y.jsonl` — 1,000 orgs, 988 HTTP 200, 2-5 periods each
- `/tmp/opencode/caches/1881-candidates.jsonl` — 1,000 rows, 656 leiCode hits
- `/tmp/opencode/caches/1881-sites.jsonl` + `1881-sites/*.html` — 210 fetched, 191 corroborate
- `/tmp/opencode/caches/rdap.jsonl` — 999 domains, 104 HTTP 200, 0 org-number matches (dead end)
- `/tmp/opencode/caches/targets.json` — 971 orgs with at least one missing field
- `/tmp/opencode/caches/deepcrawl.jsonl` — deep re-crawl result
- `/tmp/opencode/caches/probe-repair.jsonl` — identity probe result

## Dead ends recorded

- Norid RDAP: registrar org number, never the domain owner (0/999 matches).
- Norwegian news RSS over the 1,000-org corpus: 1 org covered.
- 1881.no: candidate-only (ToS forbids extraction); own-site candidates only added
  ~10 orgs. Weak lever.
- Finn.no: user decision — documented, not integrated (`docs/evidence/whyfinndoesntwork.md`).
