# Product guide

## The workflow

Work arrives as messages, but work is tasks—and people usually become the translation
layer. They read the message, decide what it means, open the ticket, do the work, and write
back.

Taskuary automates the ends and leaves you the middle:

1. Mail, chats, issues, incidents, and reports arrive on one Timeline.
2. AI triage files noise, drafts answers to questions, and turns concrete work into tasks.
3. Tasks run in the coding CLI and repository you configured, in a terminal you can watch.
4. Results and replies return for review. Nothing sends, closes, or ships without approval.

Nothing leaves the machine except calls to services you explicitly configure.

## Timeline and workspace

![The Timeline: mail, chats, reports, and an Assistant post on one day-grouped rail.](screenshot-timeline-crop.png)

The Timeline is the front door. Its chips distinguish work that needs you from completed,
filed, informational, promotional, and automated items. Open a row to see the complete
message, inline attachments, triage reasoning, a drafted reply, and the available actions.

The rest of the workspace answers a specific question:

- **Board** shows queued, working, waiting, and completed agent tasks. Working cards include
  a live terminal view and the files modified so far.
- **Studio** renders agent capacity as a floor: one desk per slot, an occupied desk for a
  running task, and a raised hand for a session waiting on you.
- **Wall** puts every live terminal side by side, with a prompt box under each session.
- **Tasks** is the full interactive terminal for one task. Pause preserves a handoff; Done
  reads the transcript, writes the report, and prepares the reply.
- **Review** is the outbound decision queue. Approved replies go back through the channel
  where the conversation started.
- **Reports** turns connected data into scheduled Timeline items, spreadsheets, charts, and
  summaries. Every report can be previewed before it is scheduled.
- **Connectors** controls sources and their roles: trigger, feed, report, tool, and notify.
- **Docs** contains the Markdown documents that govern Taskuary's behavior.
- **Settings** contains routing policies, assistant thresholds, notification preferences,
  agent capacity, learned memory, and audit verification.

Calendar-aware drafts use connected Outlook or Google calendars. They avoid offering busy
times and say when a calendar cannot be read instead of inventing availability.

## The Assistant

![The Assistant's evidence-backed suggestions, controls, reviewed material, and note to its next check.](screenshot-assistant.png)

The Assistant runs on its own schedule and when the app opens. It posts only when it finds
something useful: an unanswered reply, context for an upcoming meeting, a quiet task, or a
pattern across incoming work. Each suggestion names its evidence and offers **Make it a
task**, **Done**, **Snooze a day**, and **Not this**.

Every post also records what it reviewed and leaves a note for the next check. That keeps it
from researching the same silence or repeating the same suggestion. **Not this** teaches it
which kinds of nudges you do not want.

Three controls shape it:

- `COUNSEL.md` on the Docs tab controls how it speaks and how readily it takes a position.
- The **Assistant** report controls what it watches for, its schedule, and the model it uses.
- **Settings → Assistant** controls thresholds such as how long a reply or task must be quiet.

Delete the Assistant report to turn it off.

## Learning from your decisions

Every verdict is evidence. Editing a draft teaches voice; rejecting one teaches what should
not be drafted; choosing **Not our task** teaches where your responsibility ends. The exact
decision is kept with its date, sender, and subject so future triage can judge whether a new
message is genuinely similar.

![How repeated verdicts become a general lesson in LEARNED.md.](learning-loop.svg)

General lessons take a stricter path so one unusual decision does not become a permanent
rule. Each machine-written line in `LEARNED.md` has a score and receipts:

```text
- John drops greetings and signs off in one word. [s:4 | ev: rv12,rv15,rv31 | seen: 2026-08-19]
```

- `s` is the strength. A hypothesis starts at 2, gains a point when evidence agrees, loses
  one when evidence contradicts it, becomes active at 4, and is removed at 0.
- `ev` identifies the verdicts that taught the lesson.
- `seen` is the last date on which it held.

Delete a learned line and it is gone. Lines you write yourself have no machine tag and are
never changed. A learned rule that would hide mail waits for explicit approval, and
`SOUL.md` always outranks `LEARNED.md`. One Settings switch disables the learning loop.

**Generate from history** on `TRIAGE.md` and `STYLE.md` can bootstrap this process from the
last three months of mail. It compares inbound threads with what you actually answered and
distills the result into a marked block, preserving anything you wrote outside that block.

## Processing modes

Each inbound connector chooses how tasks it creates reach agents:

- **One by one** dispatches in arrival order. When all agent slots are occupied, tasks wait
  first in, first out.
- **Ranked together** orders a shared queue by value and runs only the top tasks. New work
  reranks the queue rather than automatically joining the end.

Ranked value begins with deterministic evidence such as whether you were directly addressed,
how many people received the message, whether somebody already answered, urgency, and the
author. When multiple tasks wait, the triage brain adds a short comparative reason. Waiting
tasks gain value over time so the bottom cannot starve.

The Timeline and Board expose the same order. **Start now** pins a task to the top; **Later**
moves it down without deleting it.

## Multiple agents in one repository

![Working cards show each agent's modified files while a potentially overlapping task waits.](screenshot-board.png)

Taskuary can auto-dispatch several coding sessions while reducing collisions in a shared
checkout:

- **Affinity routing** asks whether a queued task is likely to modify the same files as a
  running task. Likely overlap waits and starts automatically when the first session ends.
- **Tell the agent** queues new prompts until the CLI returns to its prompt. Notes never land
  in the middle of a turn or on top of a question waiting for you. Lists drip in one item per
  stop; pasted screenshots are saved locally and named in the note.
- **The blackboard** shows files each session has actually modified, calculated from Git and
  the run trace rather than from its plan. A new agent in the same checkout receives that
  picture at startup.
- **First in has control.** The newcomer is told which files belong to another session and
  must not edit, revert, stash, or commit them.

![The Wall shows three live agent terminals side by side.](screenshot-wall.png)

The Wall supports the same sessions side by side. Panes can be rearranged and resized, and
each has its own queued-prompt box and waiting indicator.

## The operator documents

Taskuary's behavior is governed by plain Markdown on the Docs tab:

| Document | Purpose | Read by |
|---|---|---|
| `TRIAGE.md` | What makes an item a task, reply, or FYI; can generate a history block from answered and ignored mail | Triage |
| `STYLE.md` | Greeting, tone, length, and phrasing; can generate a history block from sent mail | Reply drafts |
| `COUNSEL.md` | How the Assistant speaks to you and how strongly it takes a position | Assistant and reply drafts |
| `SOUL.md` | The constitution: rules, voice, escalation lines, and repository map | Triage, replies, coding agents |
| `CODER.md` | How coding agents work and close out | Coding agents |
| `LEARNED.md` | The profile learned from verdicts; always subordinate to `SOUL.md` | Triage, replies, coding agents |
| `DIGEST.md` | The current morning brief written by the Morning digest report | You |

![The seven operator documents and the parts of Taskuary they guide.](seven-docs.svg)

Each coding session also receives a context file under `~/.taskuary/context/`. It contains
the task thread, relevant sender and topic history, the learned profile, and reports from
related closed tasks so the agent starts with what Taskuary already knows.

## Bring your own coding agent

Every run can choose a configured CLI and, when supported, a model. Built-in presets cover
Claude Code, Codex, Gemini, Cursor, and Copilot. Any CLI that accepts a prompt on stdin can
work; the connector lets you define its command, arguments, model argument, and working
directory behavior.

Headless agents need their noninteractive or auto-approval flag so they do not hang waiting
for a click that cannot occur. The connector's **Test** action runs a small prompt through the
CLI before it receives real work. Claude Code JSON output is parsed for resumable sessions;
plain-text CLIs work as well.

## Related documentation

- [Getting started](getting-started.md)
- [Integrations](integrations.md)
- [Status and roadmap](roadmap.md)
- [Contributing](../CONTRIBUTING.md)
