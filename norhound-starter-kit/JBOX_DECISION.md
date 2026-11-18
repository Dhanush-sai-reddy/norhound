# JBOX — what it is, and whether it helps this entry

Decision note, 16 Nov 2026. Question asked: "what is JBOX and will using it make
stuff feasible for us?"

## What JBOX is

JBOX is an **AI application builder** — a brief-to-app generator, not a data
source. It takes a plain-language product brief, maps screens/roles/flows, and
emits a working **Next.js + Supabase + GitHub** app it can also host.

Evidence — <https://jboxai.com> (retrieved 16 Nov 2026):

> "Describe it. Jbox builds it." … "The working build uses Next.js, Supabase,
> GitHub, Jbox Hosting" … "Get started free — 50 credits · no card" …
> "$20 / 100 additional credits" … "No subscription" … "Export to production
> code"

Its co-founders are Jacques Louw, Saurav Chanda, and Håvard Liltved Dalen (CPO
at Fronted, Managing Director at Dr.Dropin).

## Why it appears in this challenge

The Signalpost challenge has a **separate sponsor prize** from JBOX. Evidence —
<https://builderr.ai/challenges/signalpost> (retrieved 16 Nov 2026):

> "Separate JBOX bonus — $500: $250 / $150 / $100 for **qualifying agents built
> with JBOX**."

> "The winning builder gets the opportunity to partner with Håvard Liltved Dalen
> to launch Signalpost in Norway. Håvard is CPO at Fronted and co-founder of
> JBOX."

> "Only qualified entries enter the hosted Builderr gallery."

## Does JBOX raise recall?

**No.** Recall (50 of 100 points) is graded on *facts collected
about the company*. JBOX produces UI code; it serves no Norwegian registry,
account, job, review or news data. Nothing in it can add an observation, a
source URL, or a dated fact. Adopting it leaves every recall number in
`out/run-*/measure-final.json` unchanged.

## Could it help anywhere else?

Only UX (8 points). JBOX could rebuild
the static viewer in `site/` as a Next.js app with search, compare and per-claim
evidence. That is a **maximum +4.8 points**, and it is a rewrite of a working
surface, not a new capability.

## The blocker on the $500

The bonus is for *qualifying* agents. **No official score has been issued for
the current revision**, and the only figures this repository can reproduce are
its own six-field proxy (22.38/50, `RECALL_LEVERS.md`). An agent that cannot be
shown to qualify cannot collect a qualifying-agent bonus, whatever it is built
with.

## Cost / constraint check

- JBOX's free tier is 50 credits, no card — so it is not a spend, but it **is an
  account signup**, which breaks the entry's stated posture of "no login, no
  account" for the parts that touch company facts.
- JBOX-generated apps run on Supabase + Jbox Hosting, i.e. a new runtime and a
  new data store for a submission that currently ships as static files with a
  one-command reproduction.

## Decision

**Do not adopt JBOX for this entry.**

1. It cannot move the bottleneck (recall) by a single observation.
2. The only prize it unlocks is gated behind a score we are 22.8 points short of.
3. The UX upside (+4.8 max) does not justify replacing a working viewer with a
   hosted third-party runtime that also adds an account dependency.

Revisit only if the score crosses ~60 and UX becomes the marginal point.

## Correction to the repo's own notes

`AGENTS.md` says entries close **21 Oct 2026** and the rubric is
Recall/Evidence/Synthesis/UX. The live challenge page (retrieved 16 Nov 2026)
says **"Closes Nov 22"** and **"Scored on 50 recall · 30 precision · 12 synthesis
· 8 UX"**, and adds:

> "You do not need to submit precomputed profiles or a company manifest.
> Builderr supplies the companies for every official run."

So the deadline is still open, and the submission unit is **repository + exact
commit + one command + a 100-company smoke test** — not the 1,000-company
profile bundle. The bundle stays as evidence, not as the deliverable.
