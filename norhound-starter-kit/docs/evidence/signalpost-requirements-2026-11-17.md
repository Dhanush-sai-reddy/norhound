# Signalpost requirements — retrieved 17 Nov 2026

> **Retrieval note.** The Builderr brief, live challenge page, source policy, agent
> playbook, learning harness and evaluation contract were retrieved on **2026-11-17**.
> The research session crossed midnight; the Unstop listing, starter-kit archive,
> Builderr rules page and start page were retrieved or re-checked on **2026-11-18**.
> The table below records the exact retrieval date for each URL. All requirements
> below come from those organiser-owned pages or the official starter archive; no
> requirement is filled from search-result snippets or prior knowledge.

## Sources retrieved (table: URL, status, retrieved date)

| URL | Status | Retrieved |
|---|---|---|
| [Signalpost source policy](https://builderr.ai/starter-briefs/signalpost-sources.md) | HTTP 200 | 2026-11-17 |
| [Signalpost participant brief](https://builderr.ai/starter-briefs/signalpost.md) | HTTP 200 | 2026-11-17 |
| [Live Signalpost challenge page](https://builderr.ai/challenges/signalpost) | HTTP 200 | 2026-11-17 |
| [Alternative guessed URL](https://builderr.ai/hackathons/signalpost) | **HTTP 404** | 2026-11-17 |
| [Signalpost public product sample](https://builderr.ai/signalpost) | HTTP 200 | 2026-11-17 |
| [Signalpost agent playbook](https://builderr.ai/starter-briefs/signalpost-agent-playbook.md) | HTTP 200 | 2026-11-17 |
| [Signalpost learning harness](https://builderr.ai/starter-briefs/signalpost-learning-harness.md) | HTTP 200 | 2026-11-17 |
| [Signalpost evaluation contract](https://builderr.ai/docs/signalpost-evaluation-harness.md) | HTTP 200 | 2026-11-17 |
| [Unstop listing](https://unstop.com/hackathons/signalpost-build-an-agent-that-finds-company-information-builderrai-1754883) | HTTP 200 | 2026-11-18 |
| [Unstop listing, AMP rendering](https://unstop.com/hackathons/signalpost-build-an-agent-that-finds-company-information-builderrai-1754883/amp) | HTTP 200 | 2026-11-18 |
| [Official starter-kit archive](https://builderr.ai/signalpost-starter-kit.tar.gz) | HTTP 200, `application/gzip` | 2026-11-18 |
| [Official public company universe archive](https://builderr.ai/signalpost-company-universe-2025.jsonl.gz) | HTTP 200, `application/gzip` | 2026-11-18 |
| [Builderr platform rules](https://builderr.ai/guidelines) | HTTP 200 | 2026-11-18 |
| [Builderr start page](https://builderr.ai/start) | HTTP 200 | 2026-11-18 |

## A. Deadline

### Current Builderr deadline — authoritative

The current brief says:

> “Status: Open. New entries and revisions are accepted through 22 November 2026.
> Before choosing winners, we’ll test the leading agents on a larger company set.
> Result and winner announcement dates will be confirmed after evaluation.”

Source: [participant brief](https://builderr.ai/starter-briefs/signalpost.md), retrieved
2026-11-17.

The live challenge page says:

> “New entries and revisions are open through **November 22**; the four-revision
> limit remains.”

Its summary card says **“Closes Nov 22”**. Source: [live challenge
page](https://builderr.ai/challenges/signalpost), retrieved 2026-11-17.

The current Builderr pages therefore give **22 November 2026** as the combined
entries-and-revisions cutoff, but **do not give a closing time or time zone**.

### Earlier three-stage Unstop deadline — superseded by the current Builderr pages

The Unstop listing still contains the earlier schedule:

> “Register and share your project link on Unstop by 17 October, 11:59 PM IST.
> Send the complete Signalpost entry to submit@builderr.ai. Builderr accepts code
> revisions until 18 October and runs the competition through 21 October.”

Source: [Unstop listing](https://unstop.com/hackathons/signalpost-build-an-agent-that-finds-company-information-builderrai-1754883/amp),
retrieved 2026-11-18.

Its header separately says:

> “Registration Deadline **17 Oct'26, 10:29 PM IST**”

That is an internal Unstop discrepancy: the stage instructions say **11:59 PM IST**,
while the header says **10:29 PM IST**. Neither time is the current Builderr close
time.

**Current answer by requested stage:**

| Requested stage | Current official statement | Exact time |
|---|---|---|
| Project sharing | Not separated in the current Builderr brief. Earlier Unstop wording: share by **17 October, 11:59 PM IST** | Earlier time only; current cutoff has no time |
| Code revisions | Current entries and revisions accepted through **22 November 2026** | **Could not retrieve** |
| Entries close | Current challenge page: **“Closes Nov 22”** / **22 November 2026** | **Could not retrieve** |

The old Unstop statement says code revisions were accepted “until 18 October” and
the competition ran “through 21 October”, but gives no time for either date.

## B. Task

### Current task statement

The current brief says:

> “Build an agent that finds company information online.
>
> Give it a Norwegian company number. It should search company websites, public
> registries and other permitted sources, then return a company profile with links
> to the facts it found. Check that each fact belongs to the right company, include
> its source and date, and clearly mark information you could not find. Run it again
> to keep the profile current.”

Source: [participant brief](https://builderr.ai/starter-briefs/signalpost.md), retrieved
2026-11-17.

The live page expands the required information as:

> “Build a company research agent. Collect company details, people, locations,
> financial results, jobs and public activity where available.”

and:

> “Your starting list: 411,160 eligible Norwegian companies with 2025 annual-account
> records. Your agent must work from a company number, including companies it has
> not researched before.”

Source: [live challenge page](https://builderr.ai/challenges/signalpost), retrieved
2026-11-17.

### Input

- Input is a **Norwegian organisation number**.
- Builderr supplies the official company numbers for scoring; the entrant must not
  replace that supplied batch with its own list. The brief says: “Builderr supplies
  organisation numbers, cutoff and output contract—not the companies' official sites
  or social identities.” Source: [participant brief](https://builderr.ai/starter-briefs/signalpost.md).
- The current official batch is **1,000 companies now** and **may grow to 1,100**.
  Every eligible frozen entry receives the same current batch. Source: [evaluation
  contract](https://builderr.ai/docs/signalpost-evaluation-harness.md).

### Required output

One company profile/result for every supplied organisation number, with:

- legal identity and public brand;
- latest annual accounts and available history;
- leadership and registered workplaces;
- verified official website and company-owned profiles;
- hiring and dated public activity from permitted sources;
- claim-level evidence and explicit availability states;
- refresh metadata and material changes since the previous run.

Source: [participant brief](https://builderr.ai/starter-briefs/signalpost.md).

### How many profiles are required now?

**1,000+ completed profiles are no longer a submission or scoring requirement.**
The current brief says:

> “Local scale test: run your agent on 100 companies before submitting. You may test
> on 1,000 companies or more, but those outputs are not part of the score.”

It also says:

> “Submit your agent's code, run instructions and a 100-company smoke-test result.
> You may use the public company list at any scale, but you do not submit precomputed
> profiles or a company manifest for scoring.”

Source: [participant brief](https://builderr.ai/starter-briefs/signalpost.md).

The live page repeats:

> “Use the public company list to test at any scale, including 1,000 companies or
> more. You do not need to submit precomputed profiles or a company manifest.
> Builderr supplies the companies for every official run.”

Source: [live challenge page](https://builderr.ai/challenges/signalpost).

**Important internal conflict:** the current live page’s small summary area still
says **“Submit 1,000+ profiles”**, but the detailed current submission section,
current participant brief and current evaluation contract all say that 1,000-company
local output is not submitted or scored. The detailed, repeated current wording is
the operative requirement. See “Conflicts between sources”.

## C. Output contract

### Required envelope sections — verbatim

The current brief says:

> “Every input must end in one terminal envelope, even when sources are missing or
> blocked.
>
> Required sections:
>
> 1. Legal identity and public brand
> 2. Latest annual accounts and available history
> 3. Leadership and registered workplaces
> 4. Verified official website and company-owned profiles
> 5. Hiring and dated public activity from permitted sources
> 6. Claim-level evidence and availability state
> 7. Refresh metadata and material changes since the previous run
>
> Use explicit states such as `available`, `not_available`, `blocked`,
> `not_applicable`, `ambiguous` and `failed`. Never turn absence into zero.”

Source: [participant brief](https://builderr.ai/starter-briefs/signalpost.md), retrieved
2026-11-17.

The evaluation contract says:

> “Exactly one terminal envelope per input organisation number. Envelopes must
> contain legal identity, claims, evidence references, availability states, source
> snapshots, refresh metadata and errors. Valid states are `available`,
> `not_available`, `blocked`, `not_applicable`, `ambiguous` and `failed`.”

Source: [evaluation contract](https://builderr.ai/docs/signalpost-evaluation-harness.md),
retrieved 2026-11-17.

### Minimal JSON field list — official starter contract

The official starter archive contains `signalpost-starter-kit/OUTPUT_CONTRACT.md`,
titled “Minimal output contract”. Its complete example field list is:

- `organisation_number`
- `run`
  - `run_id`
  - `started_at`
  - `completed_at`
  - `terminal_status`
- `claims[]`
  - `field`
  - `value`
  - `availability`
  - `confidence`
  - `evidence_ids[]`
- `evidence[]`
  - `id`
  - `source_url`
  - `source_class`
  - `retrieved_at`
  - `content_sha256`
  - `claim_span`
- `changes[]`
- `errors[]`
- `operations`
  - `requests`
  - `runtime_ms`
  - `third_party_cost_usd`

Source: official [starter-kit archive](https://builderr.ai/signalpost-starter-kit.tar.gz),
file `signalpost-starter-kit/OUTPUT_CONTRACT.md`, retrieved 2026-11-18.

The contract’s exact availability rule is:

> “Allowed availability states are `available`, `not_available`, `blocked`,
> `not_applicable`, `ambiguous` and `failed`. A checked source that has zero jobs or
> zero locations is different from a source that was not checked.”

### Required metadata per claim

The source policy says:

> “Every claim records source URL or source identifier, retrieval time,
> effective/reporting date where relevant, content hash and extraction method.”

Source: [source policy](https://builderr.ai/starter-briefs/signalpost-sources.md),
retrieved 2026-11-17.

The playbook further says immutable snapshots should store:

- requested and final URL;
- redirect chain and response status;
- retrieval timestamp and relevant effective/reporting date;
- content hash;
- parser and extractor version;
- source class and access policy.

Every published claim should point to a snapshot plus a selector, character span,
table cell or PDF page. Source: [agent playbook](https://builderr.ai/starter-briefs/signalpost-agent-playbook.md),
retrieved 2026-11-17.

### “Terminal envelope” concept

The live page says:

> “We hand your agent a company batch and need one result per input, including the
> ones you found nothing for.”

and:

> “If we hand you a batch and some results are missing, we cannot tell whether the
> rest were blocked, empty or crashed, so the run cannot be scored. ‘I found
> nothing’ is a valid answer. A missing row is not.”

Source: [live challenge page](https://builderr.ai/challenges/signalpost).

The current official batch is **1,000, possibly 1,100**, not necessarily 100. A
terminal envelope is therefore required for **every input in the supplied official
batch**.

## D. Scoring rubric and gates

### Current 100-point split

The current brief says “Scoring — 100 points” and “Scoring version 2 applies to
every Round 1 entrant from 26 August 2026.” Its category wording is:

1. **50 — Recall and coverage: how much information did you find?** “For each
   information type, 70% measures company coverage and 30% measures individual facts
   found.”
2. **30 — Is the information correct?** “We check that each fact belongs to the
   right company and has a valid source and date.”
3. **12 — Is the summary useful?** “It should explain the company, changes and
   unknowns without making unsupported claims.”
4. **8 — Is it easy to use and verify?** “A user should be able to find, compare
   and verify the information on desktop and mobile.”

Source: [participant brief](https://builderr.ai/starter-briefs/signalpost.md), retrieved
2026-11-17.

The evaluation contract names the same split:

> “1. Recall and coverage — 50
> 2. Precision, exact identity and evidence — 30
> 3. Decision-useful synthesis — 12
> 4. UX and interaction — 8”

Source: [evaluation contract](https://builderr.ai/docs/signalpost-evaluation-harness.md).

### How recall is measured

For each external field family:

> “coverage is 70% company recall and 30% individual-claim recall against the
> independently verified union of discoveries from every submitted crawler and
> Builderr’s own crawlers.”

The checked collection is cumulative and versioned; new verified findings cause all
entrants to be rescored against the new version. The final union freezes after all
eligible final submissions are verified. Source: [evaluation
contract](https://builderr.ai/docs/signalpost-evaluation-harness.md).

Special measurement rule:

> “If the verified pool has fewer than 15 positive company-field opportunities
> across at least three external field families, recall is reported as not measured
> for that batch rather than as 0%.”

The contract explicitly says this “remains a scored observation, not a qualification
gate”. Source: [evaluation contract](https://builderr.ai/docs/signalpost-evaluation-harness.md).

### Current qualification gates

The current brief says:

> “An entry qualifies with an official run, at least 65/100 overall and at least 95%
> precision: at least 95% of checked published claims must be correct and attributed
> to the right company.”

It continues:

> “Coverage and recall contribute to the score; they are not separate qualification
> thresholds. Company-matching precision is separate from factual accuracy;
> fabricated financial values or a material wrong-company publication prevent the run
> from becoming official.”

Source: [participant brief](https://builderr.ai/starter-briefs/signalpost.md).

The current gates are therefore:

- **Official run required.**
- **At least 65/100 overall.**
- **At least 95% precision:** at least 95 correct claims per 100 checked published
  claims.
- **No separate minimum recall/coverage percentage.**
- **No fabricated financial values.**
- **No material wrong-company publication.**
- **Exactly one terminal envelope per company in every official batch.**
- Missing data must use explicit states, never zero.

Source: [participant brief](https://builderr.ai/starter-briefs/signalpost.md) and
[evaluation contract](https://builderr.ai/docs/signalpost-evaluation-harness.md).

**The old 21/35 coverage gate and the claimed 60% weighted external-company recall
gate do not appear in the current official rubric or qualification text.** The
current text says recall/coverage are not separate qualification thresholds.

### Official-run integrity checks

The current brief lists:

- “No fabricated financial values or material wrong-company publication”
- “Submitted public artifact includes a 100-company smoke-test result or report”
- “Exactly one terminal envelope for every company in each official batch”
- “Claim-level source, retrieval time and reporting period where relevant”
- “Honest availability states”
- “Idempotent refresh with prior snapshots preserved”
- “Reproducible setup, pinned dependencies and one evaluator command”
- “Declared source rights, server-side secrets and safe URL handling”

Source: [participant brief](https://builderr.ai/starter-briefs/signalpost.md).

Refresh is not optional history logging: “Preserve earlier evidence and avoid
duplicate records when rerunning.” Source: [live challenge
page](https://builderr.ai/challenges/signalpost).

### Ranking and failed runs

- Final ranking uses the mean across every scheduled daily batch while the frozen
  version is active.
- An entrant-caused failed or missed batch scores zero after a clean reproduction.
- A Builderr harness, infrastructure or shared-source failure is void and rerun with
  the same code.
- Tie-break order: fewer wrong-company publications, then higher weighted company
  recall, then lower declared third-party cost.

Source: [evaluation contract](https://builderr.ai/docs/signalpost-evaluation-harness.md).

## E. Daily run limits

### Current official batch and budget wording

The current brief says:

> “Daily schedule: the current shared company set per scheduled test day; it is
> 1,000 companies now and may grow to 1,100.”

and:

> “Builderr supplies the current shared input set and a fixed time and resource
> budget for each official run.”

The live page says:

> “Each official run has a fixed time and resource budget.”

and:

> “Each run has a small external API budget, and if you need a model key for scoring,
> ask and we will supply one.”

Sources: [participant brief](https://builderr.ai/starter-briefs/signalpost.md) and
[live challenge page](https://builderr.ai/challenges/signalpost), retrieved
2026-11-17.

**The current official pages do not publish numeric limits for time, outbound
requests or external API cost.** The exact budget is supplied for each official
run. The current official batch is 1,000 companies, potentially 1,100.

### Earlier numeric limits still visible on Unstop

The organiser-authored Unstop listing says:

> “Daily limits: 45 minutes, 2,000 outbound requests and $10 in declared external
> API costs. Development and API usage can incur costs.”

It also says:

> “Every agent receives the same 100 random companies each day.”

Source: [Unstop listing](https://unstop.com/hackathons/signalpost-build-an-agent-that-finds-company-information-builderrai-1754883/amp),
retrieved 2026-11-18.

These numeric limits describe the earlier **100-company daily listing**. The
current Builderr pages instead describe a **fixed budget supplied per run** and a
**1,000-company shared batch**. No current official source connects the old
“45 minutes / 2,000 requests / $10” numbers to the new 1,000-company batch.

## F. Submission requirements

### Current required email

The brief’s final instruction is:

> “Email `submit@builderr.ai` with the repository URL, exact commit hash,
> 100-company smoke-test result or report, one run command, models/APIs/licences,
> expected cost per official batch, agent name and contact for results.”

Source: [participant brief](https://builderr.ai/starter-briefs/signalpost.md), retrieved
2026-11-17.

The live page says:

> “The models, APIs and licences you use, expected cost per official run, and
> contact details.”

Its submission email template contains these labelled fields:

- `Agent name`
- `Repository URL`
- `Exact commit hash`
- `100-company smoke-test result or report URL`
- `One-command run instruction`
- `Models / APIs / licences`
- `Expected cost per official run`
- `Contact for results`

Source: [live challenge page](https://builderr.ai/challenges/signalpost).

The official starter README adds that the submitted repository should contain:

- a 100-company smoke-test result or report;
- one documented command accepting a JSONL batch of organisation numbers;
- exactly one terminal envelope per input;
- pinned dependencies and reproducible setup;
- a previous-snapshot input and material-change output;
- a machine-readable run report with runtime, request count and third-party cost;
- declared models, APIs, licences and source-rights assumptions.

Source: official [starter-kit archive](https://builderr.ai/signalpost-starter-kit.tar.gz),
file `signalpost-starter-kit/README.md`, retrieved 2026-11-18.

### Revisions

> “Your first submission is version 1; you may send up to four revised exact commit
> hashes through 22 November 2026, for five versions total.”

Revisions take effect only after being frozen for the next daily run and never
replace earlier batch results. Source: [evaluation
contract](https://builderr.ai/docs/signalpost-evaluation-harness.md).

### Is a precomputed profile bundle required?

**No.** The current brief explicitly says entrants “do not submit precomputed
profiles or a company manifest for scoring”. The evaluation contract says:

> “Freshness, exact attribution and reproducible execution—not a submitted static
> profile file—are what the official run tests.”

Source: [participant brief](https://builderr.ai/starter-briefs/signalpost.md) and
[evaluation contract](https://builderr.ai/docs/signalpost-evaluation-harness.md).

A 100-company smoke-test result or report is required. A public 411,160-company
universe archive is available for local testing. The official companies are supplied
by Builderr at run time.

## G. Source rights and permitted sources

### Preferred sources — verbatim list

The source policy lists:

**Official Norwegian records**

- “Brønnøysundregistrene Enhetsregisteret bulk data and entity API for identity,
  legal form, address, industry and registered employee count”
- “Regnskapsregisteret API and annual-account copies for filed financial data and
  history”
- “Official roles endpoints for management and board roles”
- “Official subunit records for registered workplaces”

**Company-owned sources**

- “Verified official website”
- “Sitemap, news, investor, careers, location and contact pages”
- “Structured data embedded by the company”
- “Social or video profiles linked by the verified company site, subject to the
  destination platform's access terms”

**External sources**

- “Official or licensed platform APIs”
- “Search APIs used to discover candidates”
- “Public pages whose terms permit the submitted access pattern”
- “Licensed news, review, jobs, traffic or company-data feeds”

Source: [source policy](https://builderr.ai/starter-briefs/signalpost-sources.md),
retrieved 2026-11-17.

### What counts as evidence

The policy says:

> “Search results generate candidates; they are not claim evidence.”

The playbook’s source ladder is:

1. Official registers and annual accounts
2. Verified company-owned sites and feeds
3. Official or licensed platform APIs
4. Permitted public pages with recorded terms and provenance
5. Search/discovery providers for candidate generation only

It adds: “Never use search rank or an unofficial scraper response as the evidence
for a published fact. Re-fetch the underlying permitted source and preserve it.”
Sources: [source policy](https://builderr.ai/starter-briefs/signalpost-sources.md) and
[agent playbook](https://builderr.ai/starter-briefs/signalpost-agent-playbook.md).

### Exact-company and relationship handling

- “A profile or domain must resolve to the exact legal entity before its facts are
  published.”
- “Group, parent, subsidiary, franchise and public-brand relationships must be
  labelled, not collapsed.”
- The official register is the identity anchor, but “does not, by itself, identify
  the public brand or website.”

Source: [source policy](https://builderr.ai/starter-briefs/signalpost-sources.md).

### Missing, blocked and ambiguous states

> “Missing, blocked and ambiguous are explicit states.”

The current brief adds: “Never turn absence into zero.” Sources: [source
policy](https://builderr.ai/starter-briefs/signalpost-sources.md) and [participant
brief](https://builderr.ai/starter-briefs/signalpost.md).

### Company-owned copy vs independent sentiment

> “Company-owned promotional copy may describe the business but cannot provide an
> independent sentiment claim.”

Source: [source policy](https://builderr.ai/starter-briefs/signalpost-sources.md).

### Restricted platforms and unofficial crawlers

> “Do not scrape a platform when its terms or applicable law prohibit the submitted
> method. This includes treating unofficial LinkedIn, Meta, Glassdoor, Indeed or
> Google clients as automatically acceptable simply because code exists on GitHub.”

> “An unofficial connector may be tested privately as a candidate-discovery
> experiment. For competition scoring, the entrant must declare the connector,
> demonstrate permitted access and independently verify any published claim from a
> durable permitted source.”

Source: [source policy](https://builderr.ai/starter-briefs/signalpost-sources.md).

The playbook repeats that LinkedIn, Meta, Glassdoor, Indeed and similar platforms
have access restrictions; only official, licensed or otherwise permitted access is
allowed, and an unofficial client cannot be the sole support for a published claim.
Source: [agent playbook](https://builderr.ai/starter-briefs/signalpost-agent-playbook.md).

### Evidence beats volume

> “The competition does not reward request count, pages downloaded or raw posts
> collected. It rewards exact-company, decision-useful coverage with valid evidence
> and reproducible refresh behavior.”

Source: [source policy](https://builderr.ai/starter-briefs/signalpost-sources.md).

## H. Other current rules, prizes, disqualifiers

### Prizes and bonus tracks

- **Main final pool — $2,000:** `$1,200 / $500 / $300` for first, second and third.
- **Separate JBOX bonus pool — $500:** `$250 / $150 / $100` for the best Signalpost
  sites built with JBOX. “Send the site link with your submission by 7 November,
  23:59 IST.” This deadline had passed by retrieval.
- **Community awards — $100 × 4:** 6 September, 20 September, 4 October and
  18 October.
- Total displayed prize pool: **$2,500**.

Source: [participant brief](https://builderr.ai/starter-briefs/signalpost.md).

The live page also says:

> “Public voting never changes the technical ranking.”

and:

> “Only qualified entries enter the hosted Builderr gallery. Builderr covers hosting
> during the competition.”

Source: [live challenge page](https://builderr.ai/challenges/signalpost).

The JBOX track is separate from the agent score and main prizes. The live page’s
JBOX public vote banner said it closed **16 Nov**; the current brief retains the
**7 November, 23:59 IST** JBOX submission deadline.

### Framework and language

- The playbook says: “This is the reference architecture, not a mandated framework.”
- The bundled starter requires Python 3.12+ and `uv`.
- The saved-example run needs “no API key, registry download or live web requests.”

Sources: [agent playbook](https://builderr.ai/starter-briefs/signalpost-agent-playbook.md)
and official [starter archive](https://builderr.ai/signalpost-starter-kit.tar.gz).

### API keys, logins and paid accounts

The live page says:

> “You can [use an LLM]. Each run has a small external API budget, and if you need a
> model key for scoring, ask and we will supply one. What we cannot use is a
> credential tied to your own account on another service, because we cannot reproduce
> your run with it.”

The evaluation contract requires “server-side secrets supplied through documented
environment variables only”. Sources: [live challenge
page](https://builderr.ai/challenges/signalpost) and [evaluation
contract](https://builderr.ai/docs/signalpost-evaluation-harness.md).

The current official pages do not require a paid account or login for the reference
starter. Individual source licences and platform terms still apply.

### Finn.no

**Could not retrieve an official organiser statement specifically naming Finn.no.**
The source policy requires checking each source’s terms, rate limits and licence;
the official starter README says to use permitted APIs, licensed providers,
company-owned outbound links, or return `blocked`/`not_available`. No retrieved
official page explicitly permits or forbids Finn.no. Source: official
[starter archive](https://builderr.ai/signalpost-starter-kit.tar.gz),
`signalpost-starter-kit/README.md`.

### Disqualifiers, invalid official runs and integrity failures

The current brief and evaluation contract make these consequential:

- timeout or missing result: the run is not scored;
- a material wrong-company publication: the run cannot become official until
  corrected;
- fabricated financial values: the run cannot become official;
- an entrant-caused missed batch after clean reproduction: that batch scores zero;
- unsafe source or secret handling, fabricated claims and compromised evidence are
  investigated with named ownership;
- no pinned dependencies, clean-machine setup or one evaluator command;
- undocumented source rights, secrets or unsafe outbound URL handling.

Sources: [participant brief](https://builderr.ai/starter-briefs/signalpost.md),
[evaluation contract](https://builderr.ai/docs/signalpost-evaluation-harness.md), and
[live challenge page](https://builderr.ai/challenges/signalpost).

The platform rules add that an entry can be invalidated for a mandatory-rule
failure, forbidden information or evaluator internals, fabricated evidence/results/
identities/eligibility, malicious code, credential access, evaluator tampering or
deliberate service abuse. They also say a provisional winner must provide read-only
access to the exact agent version; an entry that cannot be reproduced or audited is
prize-ineligible. Source: [Builderr platform rules](https://builderr.ai/guidelines),
retrieved 2026-11-18.

### Authority rule

Builderr’s platform rules explicitly say:

> “Each challenge page is the source of truth for its task, deadline, prize,
> scoring, benchmark, budget, eligibility, revisions and submission format.”

and:

> “If a global summary conflicts with the challenge page, the challenge page wins.”

Source: [Builderr platform rules](https://builderr.ai/guidelines), retrieved
2026-11-18.

## What could not be retrieved

1. **Exact current closing time and time zone for 22 November 2026.** The current
   Builderr brief and challenge page give only the date. The current Unstop header’s
   17 October times belong to the superseded schedule.
2. **Exact current numeric official-run limits** for wall-clock time, outbound
   requests and external API cost. Current Builderr pages say the budget is fixed
   and supplied per run; they do not publish the numbers.
3. **Exact times for the old 18 October code-revision cutoff and 21 October
   entries-close date.** The Unstop listing gives dates only.
4. **A current official statement specifically naming Finn.no permissions or
   restrictions.** None appeared in the retrieved organiser-owned pages.
5. **A current organiser statement that 1,000+ precomputed profiles must be
   submitted.** The only current occurrence is a stale summary label on the live
   page; the detailed page, brief and evaluation contract say the opposite.
6. `https://builderr.ai/hackathons/signalpost` returned **HTTP 404**. The live page
   is `https://builderr.ai/challenges/signalpost`.
7. The general `websearch` integration failed with **HTTP 402** during this
   research. Official URLs were still retrieved directly and located through
   alternate web search; no requirement in this report relies on a search snippet.

## Conflicts between sources

### 1. Current Builderr rules vs the older Unstop listing

| Topic | Current Builderr page/brief | Unstop listing |
|---|---|---|
| Deadline | Entries and revisions through **22 Nov 2026** | Share by **17 Oct, 11:59 PM IST**; revisions until **18 Oct**; runs through **21 Oct** |
| Daily batch | **1,000 now**, may grow to **1,100** | **100 random companies each day** |
| Rubric | **50 / 30 / 12 / 8** | **35 / 30 / 20 / 10 / 5** |
| Coverage gate | **No separate recall/coverage threshold** | “at least 21/35 coverage” |
| Precision gate | **95%** | “all published accuracy, evidence and execution requirements” |
| Profiles | **No precomputed profiles or manifest**; 100-company smoke test | “At least 1,000 company profiles” |
| Limits | Fixed budget supplied per official run | **45 min, 2,000 outbound requests, $10** |

**Authority:** the current Builderr challenge page and its linked brief/evaluation
contract are authoritative. Builderr’s platform rules say the challenge page wins
when summaries conflict, and they call the current deadline, budget and submission
format challenge-page-controlled. The Unstop page is organiser-authored but still
describes the earlier schedule and rubric.

### 2. Internal conflict on the current Builderr live page

The summary area still says **“Submit 1,000+ profiles”**. The detailed submission
section on the same page says:

> “Use the public company list to test at any scale, including 1,000 companies or
> more. You do not need to submit precomputed profiles or a company manifest.”

The participant brief and evaluation contract agree with the detailed section.
Therefore the current submission requirement is a **100-company smoke test**, not a
submitted 1,000-profile bundle.

### 3. Internal conflict in the Unstop listing

The Unstop header says **“Registration Deadline 17 Oct'26, 10:29 PM IST”**, while
the stage text says **“share your project link on Unstop by 17 October, 11:59 PM
IST”**. Both describe the superseded schedule; neither is the current 22 November
cutoff.

### 4. Earlier cached Builderr revision (not used as current evidence)

A web-search index exposed an earlier cached Builderr revision with “Aug 23–Oct 21,
2026”, “Entries close: Oct 21, 2026”, the old 35/30/20/10/5 rubric and a
requirement to submit 1,000 profiles. The live Builderr page and its linked brief
now supersede it. The search cache was not used to assert any current requirement.
