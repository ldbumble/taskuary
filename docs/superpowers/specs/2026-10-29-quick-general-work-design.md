# Quick general work: answer most tasks in one call, keep the agent for deep work

**Status:** design, approved in conversation 2026-10-29. Builder check done; the calls below are the designer's.

## Why

Almost everything that is not FYI now goes to an agent. A message like "does it make sense to go to this
event?" starts a full general-agent conversation. That conversation carries the whole worker prompt,
its tools and a saved CLI session, and a hundred emails mean a hundred of them, mostly waiting on the
agent cap. The owner: "a agent on each email is overkill ... we could have 100 agents running."

Most of this work is short: read the message and what Taskuary knows, recommend, draft the reply, or ask
the owner what to do. It needs one model call, not an agent session.

## What exists (read before building)

- `general.GeneralSession` already runs its CLI headless, one turn at a time, and resumes the CLI's own
  conversation id (`cli_sid`). There is no terminal pane for general work. Coding work uses
  `terminal.Term`, a real PTY.
- `ingest._start_general` auto-starts a general session on arrival, gated by `auto_start_ok` and capped by
  `auto_sessions` ("Waiting its turn: N agents are already running").
- `general._prompt` builds the worker prompt: AGENT.md rules, the profile, the assistant style and the
  repository map.
- `brainroute.choose` picks which brain and model runs each AI job, by JOB name. It does not decide how much
  work a task needs.
- Triage already returns per-task readings that steer the work: coding vs general, `needs_browser`,
  `asks_owner`, `same_problem`, and the combine level.

## The change

Triage decides, per general task, how deep the work is. It returns a new verdict field, `depth`, set to
`quick` or `deep`, read by the model from the message and its context. No word lists. Coding tasks
are untouched: they keep the CLI terminal.

- **deep:** today's path, unchanged. `_start_general` opens the general session and sends the brief.
- **quick:** a single orchestrator call through `brainroute` (a new job slot, e.g. `quick_work`). It
  gets the context the general agent would read: the message, the task, LEARNED.md, the calendar for
  today, and AGENT.md and the profile as the general agent reads them. It may use only the read-only lookups a headless
  general run already has (web search/fetch, Taskuary search). It returns exactly what a finished general
  turn returns today:
  - the agent's report on the task ("what the agent found"),
  - a reply draft, when the task owes one,
  - a question to the owner, when it needs their decision, shown as today's "Taskuary asked you something".

  It is written to the task through the same functions the general session's turn uses, so every view,
  button, receipt and Advisor read it exactly as a general run's.
- **Escalation:** a quick call that finds it needs more than a lookup returns `escalate` with one line of
  why. Examples: booking across sites, files to work through, multi-step research. The task then takes the
  deep path, starting the general session with the quick call's notes as its brief, and a task comment
  says so.
- **The owner answers a quick question:** the answer goes into a general session on that task, started then,
  carrying the quick call's question and notes. From there it is today's flow. No screen opens on its own.
- **Any brain, not only a CLI** (the owner, 2026-10-29). The quick call goes through `brainroute`, so it runs
  on whatever the owner connected: a CLI headless (`claude -p`), or an API connector such as the HIPAA AI
  gateway. On an API brain, the orchestrator holds the shared background once and gives each small job
  that context and the read-only lookups as tools, using function calling where the connector supports
  it. the shared background is AGENT.md and the profile, LEARNED.md and today's calendar, cached where the provider caches
  prompts. Same output contract either way.
- **Concurrency:** quick calls run in a small pool, e.g. 8 at once, separate from the agent cap, so a
  burst of mail is answered in parallel without opening sessions.

## Hard constraints (the owner's)

- **Nothing in the UI or the actions changes.** Same Agent pane, same "what the agent found", same
  permission asks, same Approve / Continue / Run another, same receipts. Continue and Run another on a
  quick task start the general session exactly as they do on a finished general task today.
- **Never auto-send**, and anything that acts is held for Approve. A quick call cannot act at all: it has
  no tools that write, send, pay or browse with a login.
- **Strangers:** a quick call on a stranger's task gets what the general agent would get there (no mail,
  memory or tools), per the existing stranger rules.
- **No hard-coded words**: depth and escalate are the model's structured output.
- Auto-start rules (`auto_start_ok`: switches, danger hold, stranger gate) apply to quick calls
  unchanged.

## Non-goals

- No change to coding agents, routines or reports.
- No new settings page. If a switch is needed, it lives beside "Starting an agent by itself" and
  defaults on.

## Calls made after the builder check (the designer's, for the owner to check)

- **No new triage field.** Triage already returns `difficulty: quick|standard|hard`. `difficulty=quick`
  takes the quick path, and `standard`/`hard` take today's deep path, so the two can never disagree.
  `needs_browser=true` always takes the deep path.
- **Context is fetched up front, not live tools.** The quick call gets the message, the task, the thread's
  history (as `history_brief` builds it for mail), LEARNED.md and today's calendar in its prompt, plus the
  provider's own web search. There is no shell, no local file access and no new tool-calling layer. Anything
  needing more escalates to deep. This keeps it small and keeps the quick path unable to act.
- **The worker's instructions.** The quick call reads AGENT.md and the profile, as `general._prompt` gives the
  general agent today. It does not read SOUL.md, which stays with triage (PW-184).
- **How a quick task ends: exactly as a general turn ends today.** With a reply draft, the task stays open
  with the draft waiting for Send. With a question, it waits on the owner. With nothing owed, the quick call
  may declare it done through the same close path the general agent's close marker uses (`selfclose`).
  The call's turns are written into the task's general history, so Continue, `carry_on_why` and the
  record read them as a general run's.
- **More mail on a quick task.** If the task has a general session, it carries on that session as today
  (`_carry_on`, `auto_continue`). Otherwise triage's reading of the new message decides again: quick
  again, or deep.
- **Scope.** New general tasks from the release on. Open tasks are not migrated.

## Left to the builder

- The exact prompt for the quick call, and whether it shares `general._prompt` or uses a slimmer cut of it.
- The pool size, and whether the quick call runs on the general agents' brain or its own `brainroute` slot.
- How a quick run is recorded so the Agent pane's record, the replay and the "earlier runs" list show it as
  one run.

## How we know it works

- A replay of the last two weeks of the owner's general tasks, offline and with counts only: how many would
  be quick, and how many quick ones escalate.
- Tests: depth reaches the router; a quick verdict writes the report, draft and question through the same
  functions; escalate starts the general session with the notes; an owner answer to a quick question
  resumes as a general session; the pool limit holds; nothing quick can send or act.
- The browser smoke set and the agent-presses tests pass unchanged. They are the proof the UI did not
  move.
