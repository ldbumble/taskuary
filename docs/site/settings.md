Settings is a rail of pages, each one long page you scroll. This reference covers the
**Configuration** page — every knob, in the sections the app itself shows them in.

:::note This page writes itself
Everything below the next heading is generated from `taskuary/settings_schema.json`, the same file
the Settings page and the assistant read. A knob added to the app appears here on the next build,
with the same name, the same group and the same help text. It cannot drift, and nobody has to
remember to update it.
:::

The other Settings pages are documented where their subject is: **About you** and the per-channel
identities, **Routing policies** ([the deterministic layer](how-it-works#what-triage-actually-decides)),
**Audit integrity**, and **Updates** ([updating](index#updating)).

## How to read this

Each setting shows what it does, and its shipped default. A few notes that apply throughout:

- **Blank is meaningful.** For a brain or model setting, blank means "decide from what is
  connected" rather than "off" — the specific fallback is given per knob.
- **A switch that is off is off for everything**, not just the surface you are looking at.
- Four AI slots — the triage brain, the default coding CLI, the assistant and the general agent,
  plus the judge that decides where a report run goes — are set on the cards at the top of the
  Configuration page rather than as plain rows. They appear below with their fallback rows, which
  is what you see if those cards cannot load.

<!-- generated: settings -->

## Routing policies

Rules evaluated **before** any AI touches a message; no model confidence overrides them.
Precedence runs `ignore` → `escalate` → `auto_answer` → `draft` → `task_only`, and within one
action the lowest order number wins.

**Kinds**: `keyword` (pipe-separated substrings matched against subject and body), `sender`
(exact addresses), `sender_domain`, `noreply` (a built-in matcher for automated addresses), and
`first_time_sender` (fires when the address has never been seen).

**Actions**: `ignore` files it with no task, and it stays visible; `escalate` puts it in front of
you and marks the task urgent — this is the only thing that marks one urgent, so name the senders
whose mail should jump your queue; `auto_answer` auto-approves the draft, which is still never
sent; `draft` is the targeted default; `task_only` files a task and drafts nothing.

Nothing writes into this table by itself. **Not a task** teaches a verdict in your memory
(`LEARNED.md`), not a rule here, and muting a sender is **Skip this sender**.

## Your memory

There is one memory: `LEARNED.md`, in Settings → Docs. Every fact you tell the Assistant ("remember
that…", "I don't care about the legacy export any more") goes in at once as your own line, under
the section it is about. A verdict you give — **Not ours**, **Not a task**, **Not for the agent**, a
kind or a road you corrected, an Advisor idea taken up or turned down — goes in when it teaches
something about you, as one line saying what kind of work it is and why; a verdict that repeats what
is already there adds nothing, and one that sharpens an older line replaces it. A line about one
sender, domain or topic ends with `(about: …)`. Triage, report routing, the Advisor, agents
and the Assistant each read the sections that help them; edit a line, or press **Forget**, to
change what they read.

## Audit integrity

Every consequential thing Taskuary does is one row in an append-only log: a message routed or
filed and why, a verdict, a reply sent, an agent session opened or wrapped, a connector saved, a
setting changed, a task deleted.

Each row stores a hash of its own contents **plus** the hash of the row before it, so the rows
form a chain. Change any row after the fact — even one character in the database — and its hash
no longer matches, and every row after it points at a parent that no longer exists.

**Verify** recomputes the whole chain from the first row:

| Result | Means |
|---|---|
| Intact | The record you see is the record that was written |
| Contents altered | Named rows were changed after writing — the thing this log exists to catch |
| Out of order | Two writers raced at the same instant once; nothing was changed, and it cannot recur |

The history below it is that log, newest first: when, who, what was done, and to what. It is the
answer to "why did this happen" and "who did this" for anything on the rail or the Board.
