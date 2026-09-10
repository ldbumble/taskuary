# Agent profiles: CODER.md is one profile, not the ground

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

- Where a profile is stored: a fourth kind of operator document, a connector row, or a folder beside
  `~/.taskuary/playbooks/`.
- Whether profiles accrete from sessions the way playbooks do (`playbooks.draft`) or are only ever
  written by the owner. The trading case argues for owner-written; the research case may not.
- What routing actually keys on — triage's `kind`, the matched playbook, the connectors the task
  names, or a profile the router picks directly.
- Whether a profile carries its own authority ceiling, or whether that stays entirely in `scopes.py`
  on the connector card. Two places to set authority is one too many.
