# JOB.md — the eighth operator document

*2026-10-12. Decided in conversation with the owner; this is the record.*

## Why

SOUL.md says how the funnel behaves: what counts as a task, how replies sound, when to escalate. Nothing
said what the owner's job *is* — the mission, the responsibilities, who they serve, the cadences the month
runs on, the decisions that are theirs. Triage could judge the kind of an arrival but not its importance,
because it had never been told what matters.

## What it is

`JOB.md` is a separate document, not a section of SOUL.md:

- triage reads only the first 2,500 characters of SOUL.md, so a spliced job section would be cut;
- SOUL.md is conduct rules plus machine-maintained blocks (connections, projects, repositories), and a
  generated prose block in the middle fights with docsync;
- the two regenerate on different clocks — STYLE and TRIAGE learn weekly, a job changes quarterly.

Shipped as `taskuary/templates/job.md` with the same shape as STYLE.md: an owner section and a
`fromhistory` marked block. **Generate from history** (`histgen.gen_job`) reads three months of mail in
both directions — who writes in and whether they are answered, who the owner writes to, which subjects
recur and in how many weeks, which threads the owner opened — and writes six sections: what the job is,
responsibilities by frequency, who the owner works with, recurring cadences, decisions made and handed up,
what to protect. The prompt forbids defining intent: the job weighs importance, TRIAGE.md decides kind.

## Who reads it

| Reader | Gets |
|---|---|
| triage (`classify_intent`, `job=`) | first 2,500 characters, after the operator's document |
| the Assistant report (`assistant.think`) | whole, beside SOUL.md |
| the concierge chat (`concierge._system`) | whole |
| the morning brief (`digest.system`) | first 1,500 characters |
| the evalset replay | the same as triage |
| working agents (coder, general) | **nothing** — PW-184 kept SOUL off the workers so a task is not widened; the same reason holds harder for the mission |

`triage.job_doc(store)` is the one door: comments and template placeholders stripped, owner tokens
rendered, and empty until the document says something real — an untouched template never rides into a
prompt as noise (the rule `responder.style_doc` already lives by). `tests/test_docs_flow.py` pins that
triage gets it and the coder and the reply writer do not.

## Where it shows

Settings → Docs lists it second, after SOUL.md, with its own Generate from history button. The setup walk's
Docs stop names it. The demo world seeds an invented one for Dana at Northwind Facilities; the static web
demo's fixtures carry the template. `docs/site/how-it-works.md` gained the row and a redrawn
`img/operator-docs.svg` (eight documents; the old seven-document diagram was orphaned).

## Left out, on purpose

- A pull door for workers (JOB.md in the coder's context folder). Decided against for now: the task seed
  should carry the relevant lines when work is written *as* the owner, chosen by triage or the Assistant.
- The "lived job versus written job" Assistant report section. It needs this document first; it is the
  natural next report once a few installs have generated one.
- Startup auto-generation. No document is generated at launch today (STYLE and TRIAGE are not either);
  the walk's Docs stop is where all three are offered.
