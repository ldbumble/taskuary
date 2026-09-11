# Agent profiles: CODER.md is one profile, not the ground

Profile documents now seed into the database, including on existing installations. Opening a
missing or blank document restores its starter instructions without replacing nonempty edits.
Coding workers share `CODER.md` by default; `rules_doc` can explicitly choose a shared or separate
document. Docs groups workers by that document, so Coder and Codex appear together.

Use **Docs → Profiles → Add profile** to set the worker's name, CLI, work type and routing purpose.
With **Available to triage for new tasks** enabled, saving adds it to the roster used by the next
triage call. Turning that off keeps it available for manual use. New workers get starter
instructions, and both coding and general sessions load the assigned worker's rules.

> **BUILT 2026-09-10** — the minimal version of this shipped. A profile is an `agent` row and its
> rules document is the `doc` row of the same name; `coder` already was that, so no table and no
> migration were needed. Five profiles ship (researcher, analyst, coordinator, marketer, trader),
> triage names one from a roster it is shown and code validates the answer against that roster, the
> chosen profile rides on `Assignee`, and `terminal.rules_text` seeds THAT profile's document.
> Routing keys on **triage naming the profile** — the open question below is answered. Still open and
> deliberately not built: profile authority ceilings (authority stays in `scopes.py`), profiles
> accreting from sessions the way playbooks do, and the two compensating patches, which were left in
> place. The section below is the reasoning as it stood before the work; the answered questions are
> marked.

*A captured idea, 2026-09-08 — **not a design yet**, and deliberately so. It is recorded now because
it reframes something the codebase currently hardcodes, and deferred because designing it against no
real second profile is how you get an abstraction shaped like nothing. The owner's words: "playbooks
are really what give agents a name — stock trader, web research — so instead of CODER.md being used
in the agent sessions we should have agent names for other tasks… CODER.md is only one playbook or
agent (though it's a different CLI)."*

## The observation

Every worker session is seeded with `CODING RULES (CODER.md)`, unconditionally
(`terminal.py:1075`). A stock-trading task, a spend-monitoring task and a meeting-prep task all get
a document whose first rule is "work only in the repository the task names". The system compensates
with special cases — the router's `NO REPOSITORY` line (`terminal.py:999`), and the "THIS IS NOT A
CODE CHANGE" tail inside `playbooks.seed_block` — rather than by not sending the wrong document.

The reframe: **`coder` is a profile, and it is currently the ground.** There should be others, named,
routed to.

## Why this is cheaper than it looks

Two seams already exist and neither was built for this:

- **`brief.rules(store, doc, chars)` is a generic operator-document loader.** It takes a document
  *name*. `AGENT.md` and `CODER.md` are just two names, and CODER.md's only privilege is that
  `terminal.py` hardcodes the call. Loading a routed profile's document is the same function with a
  different argument.
- **Named agents are already an addressing scheme.** "AI CLI agents" is a connector category,
  `llm.make_cli_llm(store, agent_name, …)` resolves one by name, and `run_agent` already accepts
  `{"agent": "coder"}`. Nothing but scheduled reports uses it yet, but the road exists — and it is
  what makes the owner's parenthesis ("though it's a different CLI") land: a profile can name its own
  CLI, so a research profile need not run the coding CLI.

So the change is small at the seam and large in blast radius. Both halves of that are true and the
second is the reason this is a separate piece of work.

## The model — two levels (decided 2026-09-08)

A **playbook** is a *job*. A **profile** is a *worker*. They are different granularities, and
collapsing them means one profile per job, with the CLI choice, the connector list and the authority
defaults copy-pasted across every job an accountant does.

- **Profile** — identity, which CLI, which connectors, a base rules document, default authority.
  `coder` becomes one row in this table rather than a hardcoded append.
- **Playbook** — one job, naming its profile. When it names none, the profile is **inferred from
  `uses:`**, which is already a list of connector types (`playbooks.uses_of`).

That inference is what makes the owner's intended flow fall out rather than be built: adding the
Alpaca card offers a `stock-trader` profile, and a playbook whose `uses:` line says `alpaca` lands on
it without being told. "They can add an agent or a playbook when they add connectors."

The alternative considered and rejected was one level (a playbook gaining `agent:` and `cli:` lines).
It is cheaper to build and worse to live with for any company whose accountant does more than one
kind of job.

## What it deletes

This is the part that argues for doing it at all. Two current special cases stop being special:

- The router's `NO REPOSITORY` line exists to counteract a document that should not have been sent.
- `CODING RULES (CODER.md)` riding along under `NO_REPO` — a seed that says both "this is a general
  question" and "work only in the repository the task names" — needs no `if` at all when the routed
  profile simply is not `coder`.

A design that removes two patches is worth more than one that adds a feature.

## What it costs

The core of the app: seed assembly in `terminal.py` and `general.py` (PW-206 already gave both worker
kinds one task-brief structure, which helps), the routing decision that picks the profile, the Docs
tab that edits the documents, and a migration where every existing install defaults to the `coder`
profile so nothing regresses on upgrade — the same reasoning `scopes.DEFAULT_SCOPE` uses ("these
match what it could already do, so nothing regresses").

It is well outside the "connectors and playbooks only" constraint the finance work is built under,
and larger than all of that work combined.

## Why it waits

Deferred until the finance connectors land
(`docs/superpowers/specs/2026-09-08-finance-agent-design.md`), for a reason that is not process:
that work produces **two concrete profiles to design against** — a stock trader and a spend watcher —
instead of hypothetical ones. Connectors do not touch the seed, so nothing built there is built
twice.

Open questions, to be answered when this is designed properly and not before:

- ~~Where a profile is stored~~ — **answered 2026-09-10: an `agent` row plus the `doc` row of the
  same name. Neither is new, and the Agents panel edits both in one place.**
- Whether profiles accrete from sessions the way playbooks do (`playbooks.draft`) or are only ever
  written by the owner. The trading case argues for owner-written; the research case may not.
- ~~What routing actually keys on~~ — **answered 2026-09-10: triage names the profile in its own
  field, validated against the roster it was shown. `kind` keeps its three meanings.**
- Whether a profile carries its own authority ceiling, or whether that stays entirely in `scopes.py`
  on the connector card. Two places to set authority is one too many.
