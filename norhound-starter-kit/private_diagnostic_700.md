# Private diagnostic — 700-company capture (received 27 Sep 2026)

**Status: private diagnostic. NOT an official score, NOT a qualification decision,
NOT a leaderboard update.** Evidence, product and safety review are still running.
Applies only to the immutable 700-company capture used for this technical review;
it does not replace any result sent for another run or revision.

Diagnostic score: **48.69 / 100** (our run in the 700-company capture).

## What changed in the evaluation model

Three corrections, all of which change the measuring ruler versus the 16 Sep review:

1. **Company count 700**, not our 1,000-company entry batch.
2. **Scoring reads only the sources captured in our first run.** No second live
   crawl. A fact is only as good as the source body we retained in the capture.
3. **The shared reference collection now includes a fact when it can be
   independently verified from ANY participant's captured source**, not only from
   the organizer's own collector. Fairer to builders who found valid information
   the organizer did not find — but it enlarges the recall denominator, so our
   coverage percentages are measured against a growing union.

**Consequence: 48.69 is not comparable to 54.92.** Different company set, larger
reference union, and validation restricted to our own captured bodies. Do not
read the delta as a regression on its own — read it together with the three
specific gaps below, which are unambiguous.

## What the reviewer credited

- Official-data base (Brønnøysund registry) is useful.
- Basic website and social discovery are useful.

## The three gaps, quoted

> The main gaps are no validated news or hiring recovery and no submitted
> data-linked product surface. Next, retain bounded first-party pages, extract
> social links from markup and structured data, and show source links in a
> searchable viewer. One cited source body is missing from our capture; we own
> that repair.

> For jobs, a generic careers page is not enough: publish a hiring fact only when
> you have a real role card, job-feed item, or apply action. We are tightening
> this definition, so do not optimize for generic careers keywords.

## Diagnosis against the repo (measured 2026-09-27)

Each gap was traced to a specific file in the working tree. **The first two are
shipped-artifact regressions, not discovery gaps.**

### 1. Hiring: the shipped artifact contains zero hiring facts

| file | job_board rows | company_directory rows |
|---|---:|---:|
| `out/final-keyless.external.jsonl` (shipped keyless revision) | **0** | **0** |
| `out/keyless-nav-all.external.jsonl` (earlier, uncommitted) | 10,044 | 93 |
| `out/web1000batch.external-withfag.jsonl` (earlier, committed) | 65 | 93 |

`out/final-eval.json` — the evaluation report we shipped — reports
`job_board: 65` and `company_directory: 45`, which describes
`out/web1000batch.external-withfag.jsonl`, **not** the artifact we shipped. The
report and the data disagree.

Cause: `scripts/run_external_pipeline.py:54` still declares `--nav` and
`--reviews` as opt-in flags, and the consolidation list at
`scripts/run_external_pipeline.py:176` only appends the NAV output when the flag
was passed. The keyless revision was run without them. This is AGENTS.md
"Next Action #1", still not done.

`out/keyless-nav-all.external.jsonl` already holds 10,044 official-API job-feed
observations and `data/nav-job-index.jsonl` holds 9,979 publishable postings
across 3,625 organisations. The supply exists; the merge dropped it. A NAV job
feed item is precisely the "real job-feed item" the tightened hiring definition
accepts.

### 2. News: claims carry a hash and a page title, no body

Published news/activity observations look like:

```json
{"signal_type": "public_post",
 "source_url": "https://comex-group.com/pl/news/",
 "content_sha256": "5c831d6f...",
 "evidence_span": "News | Comex Group – Technologie sortowania i proszkownia",
 "metrics": {"captured_news_pages": 1}}
```

`evidence_span` is the page title. The observation records a content hash but no
retained body, so a judge working only from the capture cannot confirm the fact.
Under the corrected evaluation model this is unverifiable, which is what "no
validated news" means. Volumes are also thin: 56 activity observations across
1,000 companies, of which 8 dated.

### 3. Product surface: the viewer was never submitted

`scripts/build_static_site.py` exists and `tests/test_static_site.py` passes, but
there is no `out/site/` in the repository. `out/` is gitignored; only 22 files
under it were force-added (`git ls-files out` → 22), and the site is not among
them. The reviewer cannot open a viewer, so "no submitted data-linked product
surface" and the searchable-viewer request both cost full marks for code we
already wrote.

### 4. Social: extraction exists, yield is low

`src/norway_company_agent/website.py:103` (`_social_links`, markup) and
`:122` (`structured_social_links`, JSON-LD `sameAs`) already implement what the
reviewer asks for. Yield is the problem: across 1,000 companies the shipped eval
records facebook 120, instagram 100, linkedin 68, youtube 17, tiktok 9, x 7, and
`two_platforms` coverage 0.359. We crawl the homepage only, and
`_priority_links` caps follow-up links at 6, so social links that live on
contact/about/footer pages are missed.

### 5. Reporting hygiene

`out/SUBMISSION-REPORT.md` is stale: it describes the `batch1000f` run (85
accepted observations across 38 profiles) and still documents `run_nim_summary.py`
with `NVIDIA_API_KEY` as the summary path, which the keyless deterministic
summaries replaced.

## Actions the reviewer explicitly does not want

- **Do not optimize for generic careers keywords.** A careers page is not a
  hiring fact. Under the tightened definition a hiring fact requires a real role
  card, a job-feed item, or an apply action. Treat a bare `/karriere` page as an
  explicit `careers_page` signal, never as `hiring: true`.
- **Do not reply on the thread yet.** "No action is needed now. If you make an
  iteration, send the pinned commit when it is ready."

## Carried-forward rules from the 16 Sep review

Unchanged and still binding: never fabricate financial values; never publish a
fact under the wrong company; always carry source URL, retrieval time and
reporting period; use explicit availability states instead of zeros; refresh must
be idempotent; exactly 100 terminal envelopes per daily batch. The reviewer's own
framing — "evidence beats volume" — now has teeth, because evidence is literally
what is scored.
