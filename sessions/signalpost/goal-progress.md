# Goal progress

cycle | value (0-50) | delta from baseline | delta from previous
0 | 37.0083 | 0.0000 | 0.0000
1 | 30.13 | -6.8783 | -6.8783
2 | 22.4333 | -14.5750 | -7.6967
3 | 22.3833 | -14.6250 | -0.0500
4 | 22.3833 | -14.6250 | 0.0000

## Reading

- **Cycle 1 (30.13)** — the scorer counted the register and headcount as
  external evidence. The fall was a correction, not a regression.
- **Cycle 2 (22.4333)** — the three tautological fields were re-defined
  (16 Nov 2026). The headline fell again for the same reason: the coverage it
  claimed was coverage that did not exist.
- **Cycle 3 (22.3833)** — the six-field proxy on the corpus produced by the
  evaluator's own command (`scripts/run_official_batch.sh`, run
  `fresh-20261117T213100Z`). The last 0.05 is run-to-run noise: 13 role cards
  became 14 and `two_platforms` moved 0.627 -> 0.620.
- **Cycle 4 (22.3833)** — the news-depth pass (`newsdepth-20261118T120128Z`)
  deepened the claim count without moving the proxy: 86 news observations over
  86 companies became 194 over the same 86 (172 dated, was 64), and the corpus
  grew from 105,164 to 105,266 claims and from 35,314 to 35,421 evidence
  records. The six-field proxy counts *whether* a company has a dated news
  fact, not how many, and those 86 companies already had one, so the proxy is
  unchanged at 22.3833 by construction. Precision held at 1.0 with 0
  wrong-company publications. The two remaining levers were measured and
  closed as source ceilings: the directory-domain route to a second platform
  (~5 % ceiling on a 60-company sample) and the careers-page route to hiring
  (46 companies, generic open-application copy, no role card with an apply
  action).

The six-field proxy is **our** measure, not the graded metric. The graded
Recall metric is measured by the organisers against the union of what all
participants found, so it is not reproducible here.

Secondary metric (family recall, per official fact family, from
`scripts/measure_family_recall.py`):

| family | cycle 3 value |
|---|---|
| website | 597 / 577 (1.000) — closed |
| identity | 1000 / 1000 (1.000) — closed |
| news | 1000 / 998 (1.000) — closed |
| other | 1000 / 1000 (1.000) — closed |
| financials | 994 / 1000 (0.994) — closed |
| roles | 994 / 1000 (0.994) — closed |
| social | 204 / 177 (1.000) — closed |
| hiring | 49 / 84 (0.583) — **source-capped** |
| reviews | 32 / 323 (0.099) — **source-capped**, not scored by the rubric |

Precision held at **1.0** with **0** wrong-company publications throughout.

### Why hiring cannot be closed keylessly

14 companies have a real role card (all NAV job-feed items). The public ATS
boards find postings for 3 more companies, but the posting pages sit on
third-party boards and the frozen site evidence cannot re-derive the board
link, so the fail-safe identity gate rejects them. Finn.no is excluded (no
organisation numbers; its terms of service forbid the use). NAV's live search
answers HTTP 429 to unauthenticated bulk.
