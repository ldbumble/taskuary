<!-- Written by `python -m taskuary.toolcatalog` from taskuary/toolcatalog.py - edit the catalogue, not this page. -->

What the Assistant is told about its tools. It gets the **summary** on every turn: the buckets, and
each tool's name and what it needs. It asks for the **detail** of a bucket (`tools.list`) or a tool
(`tools.describe`) only when a turn needs it. Everything it can change becomes a card you confirm,
except the few that can be undone, which run at once with an undo on the receipt.

## The summary, sent every turn

| Bucket | What it is for | Tools, and what each needs |
|---|---|---|
| **table** | decide about the item on the table | reply(text), approve, redraft(text), mine, regular_agent(text, as?), coder(text, as?), not_ours, not_ours_sender, block_sender, close, done, next, answer_agent(text), stop_agent, rerun, remember(text), setup(text), clear(text), confirm, cancel |
| **task** | change any task - the one on the table or one named with ref | task.update(priority/title/assignee), task.set_kind(kind), task.set_repo(repo), task.check(item, done?), task.comment(text), task.split(text), task.merge(into), task.reopen, task.not_a_task, task.complete, task.defer(until), task.handoff(who, note?), task.clarify(text), review.approve, review.reject |
| **agents** | start, continue, answer or stop the agent on a task, and teach where work belongs | dispatch.prepare(kind, instructions?), agent.continue, agent.answer(text), agent.stop, routing.remember(field, value) |
| **new** | new work with no task yet | task.create_from_text(kind, text), task.create_from_message(kind), task.setup(text) |
| **pipe** | the walk and sets of items, and filing mail | pipe.clear, item.settle(verb), message.file, message.archive, preference.exclude_sender(scope), preference.sender_rule |
| **reports** | reports and workflows | report.create(config), report.run, report.rerun, report.pause, report.resume, report.reach(reach), report.edit(config), report.delete |
| **app** | settings, connections, scripts and kept facts | setting.set(setting, value), connection.create(type, name), connection.test, connection.pause, connection.resume, script.start(name), memory.remember(note), hub.publish(title, body, topic?, kind?, why_earned?) |
| **look** | look-ups - they run at once and change nothing | task.read, timeline.search, tasks.list, message.read, sender.read, docs.search, agents.now, approvals.list, pipe.list, calendar.read, activity.list, errors.list, memory.list, rules.list, report.read, reports.list, settings.list, setting.read, connections.list, connection.read, agents.list, repos.list, tools.list, tools.describe, knowledge.search |

A task you name goes in `ref` ("TQ-0123"); otherwise the tool acts on what is on the table.

## Table

Decide about the item on the table.

### `reply`

Write a reply to the sender. Nothing is sent.

- `text` - the gist, in the owner's words

<p class="runs">At once - a draft, nothing sent.</p>

### `approve`

Send the drafted reply as it stands.

<p class="runs">Waits for your yes on a card.</p>

### `redraft`

Write the draft again.

- `text` - the change

<p class="runs">At once - a draft, nothing sent.</p>

### `mine`

Make it a task on the owner's own list - no agent.

<p class="runs">Waits for your yes on a card.</p>

### `regular_agent`

Send it to a non-coding agent.

- `text` - the job
- `as` (optional) - a profile from agents.list, only when one fits

<p class="runs">Waits for your yes on a card.</p>

### `coder`

Send it to a coding agent. Not sure which repository is no reason to ask - CALL it, and its card offers every repository to pick.

- `text` - what is wanted
- `as` (optional) - the repository (repos.list), only when sure

<p class="runs">Waits for your yes on a card.</p>

### `not_ours`

File it, just this once - its card asks whether from now on, or as a rule.

<p class="runs">Waits for your yes on a card.</p>

### `not_ours_sender`

File everything from this sender from now on - their mail still arrives and stays readable.

<p class="runs">Waits for your yes on a card.</p>

### `block_sender`

An exclusion rule in Settings: the sender never reaches triage again - only when they ask for a rule.

<p class="runs">Waits for your yes on a card.</p>

### `close`

Mark done - the task behind the item is finished.

<p class="runs">At once.</p>

### `done`

The owner handled it - Mark done on a task; on an idea, a report or an fyi it is read and settled.

<p class="runs">At once.</p>

### `next`

Move on to the next thing.

<p class="runs">At once.</p>

### `answer_agent`

Answer the agent waiting on the owner.

- `text`

<p class="runs">Waits for your yes on a card.</p>

### `stop_agent`

Save and end the agent's session on the item.

<p class="runs">At once.</p>

### `rerun`

Run the report on the table again.

<p class="runs">Waits for your yes on a card.</p>

### `remember`

Keep a fact.

- `text`

<p class="runs">Waits for your yes on a card.</p>

### `setup`

Build a report, a connection to another system or an automation. Never a to-do.

- `text` - the request

<p class="runs">Waits for your yes on a card.</p>

### `clear`

Clear these from the pipe.

- `text` - which

<p class="runs">Waits for your yes on a card.</p>

### `confirm`

The owner's yes to the card already waiting - only when one is.

<p class="runs">At once.</p>

### `cancel`

The owner's no to it.

<p class="runs">At once.</p>

## Task

Change any task - the one on the table or one named with ref.

### `task.update`

Change a task's priority, title or owner.

- `priority` - low | normal | high | urgent
- `title`
- `assignee` - 'me', or an agent's role
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Waits for your yes on a card.</p>

### `task.set_kind`

Say what kind of work a task is.

- `kind` - task (the owner does it) | general (a non-coding agent) | coding
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Waits for your yes on a card.</p>

### `task.set_repo`

Put a coding task in the repository it belongs in.

- `repo` - its name, as the repositories list says it
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Waits for your yes on a card.</p>

### `task.check`

Tick a checklist item on a task.

- `item` - its number (1 is the first) or words from it
- `done` (optional) - false un-ticks
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Waits for your yes on a card.</p>

### `task.comment`

File a note on a task.

- `text`
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Waits for your yes on a card.</p>

### `task.split`

Split one arrival into two jobs.

- `text`

<p class="runs">Waits for your yes on a card.</p>

### `task.merge`

Fold a task into the one it duplicates.

- `into` - the survivor's ref (TQ-0123)
- `ref` (optional) - the task that is the one folded away

<p class="runs">Waits for your yes on a card.</p>

### `task.reopen`

Reopen a task that was marked done.

- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Waits for your yes on a card.</p>

### `task.not_a_task`

Delete a task and teach triage it was never work.

- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Waits for your yes on a card.</p>

### `task.complete`

Mark done - the task is finished.

<p class="runs">Waits for your yes on a card.</p>

### `task.defer`

Remind me: put an open task away until a day and bring it back that morning.

- `until` - a date (2026-10-09), "2 weeks", "3 days", "monday", or "none" to bring it back now
- `ref` (optional) - the task (TQ-0123) when it is not the one on the table

<p class="runs">Runs at once, with an undo on the receipt.</p>

### `task.handoff`

Hand a task to a PERSON.

- `who` - a name or address that has written here
- `note` (optional) - writes the forward for the owner's yes, nothing is sent from this card
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Waits for your yes on a card.</p>

### `task.clarify`

Prepare a question for the task's sender; it waits for the owner's yes, never sent from here.

- `text` - the question
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Waits for your yes on a card.</p>

### `review.approve`

Send the drafted reply as it stands.

<p class="runs">Waits for your yes on a card.</p>

### `review.reject`

Reject the draft reply waiting on a task - nothing is sent, the task stays open.

- `ref` (optional) - the task

<p class="runs">Waits for your yes on a card.</p>

## Agents

Start, continue, answer or stop the agent on a task, and teach where work belongs.

### `dispatch.prepare`

Start an agent on an EXISTING task; a coding task asks which repository when it is not clear.

- `kind` - coding | general
- `instructions` (optional)
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Waits for your yes on a card.</p>

### `agent.continue`

Pick up the agent's own last session on a task where it left off.

- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Waits for your yes on a card.</p>

### `agent.answer`

Answer the agent that is waiting.

- `text`
- `ref` (optional) - its task when it is not the one on the table

<p class="runs">Waits for your yes on a card.</p>

### `agent.stop`

Save and end an agent's session - the one on the table, or the task `ref` names; never a guess at which.

- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Waits for your yes on a card.</p>

### `routing.remember`

Remember how work like this should be ROUTED next time. kind: coding (an agent in a checkout) | general (the assistant) | task (the owner, no agent). system: where the work actually lives when no repository here can touch it, named plainly ("ADP"). It teaches triage and moves nothing - say it when the owner tells you a verdict was wrong, or where a kind of job really belongs.

- `field` - kind | profile | system
- `value`

<p class="runs">Waits for your yes on a card.</p>

## New

New work with no task yet.

### `task.create_from_text`

A new job with no message behind it. Never for a task that already exists (a TQ ref): starting an agent on one is dispatch.prepare, and its own last session is agent.continue.

- `kind` - task (a to-do or reminder the owner does themselves, no agent) | general (a regular agent) | coding
- `text`

<p class="runs">Waits for your yes on a card.</p>

### `task.create_from_message`

Hand this message to an agent or put it on the list.

- `kind` - coding | general | task

<p class="runs">Waits for your yes on a card.</p>

### `task.setup`

Open a walk-through with the assistant, for a set-up that needs digging first.

- `text`

<p class="runs">Waits for your yes on a card.</p>

## Pipe

The walk and sets of items, and filing mail.

### `pipe.clear`

Clear a SET of items from the pipe at once - takes `select` (below); read, never deleted.

- `select` - below

<p class="runs">Waits for your yes on a card.</p>

### `item.settle`

Put the item down.

- `verb` - done | later | skip (the item on the table is the target)

<p class="runs">Waits for your yes on a card.</p>

### `message.file`

File it - not ours, just this one.

<p class="runs">Waits for your yes on a card.</p>

### `message.archive`

Archive it: off the pipe and closed, nothing deleted.

<p class="runs">Waits for your yes on a card.</p>

### `preference.exclude_sender`

Teach triage to file this sender or subject from now on - their mail still arrives (`scope`: sender | subject)

- `scope` - sender | subject

<p class="runs">Waits for your yes on a card.</p>

### `preference.sender_rule`

An exclusion rule in Settings: this sender never reaches triage again and what already arrived leaves the Timeline.

<p class="runs">Waits for your yes on a card.</p>

## Reports

Reports and workflows.

### `report.create`

Create a scheduled report or workflow; the composer builds it from what the owner asked for.

- `config`

<p class="runs">Waits for your yes on a card.</p>

### `report.run`

Run a report or workflow now; it lands in the pipe when done.

- `title` - or `source_id`

<p class="runs">Runs at once, with an undo on the receipt.</p>

### `report.rerun`

Run that report again.

<p class="runs">Waits for your yes on a card.</p>

### `report.pause`

Stop a report or workflow running on its clock.

- `title`

<p class="runs">Runs at once, with an undo on the receipt.</p>

### `report.resume`

Put a paused report or workflow back on its clock.

- `title`

<p class="runs">Runs at once, with an undo on the receipt.</p>

### `report.reach`

Change when a report reaches the owner.

- `reach` - always | wrong | rule
- `title`

<p class="runs">Runs at once, with an undo on the receipt.</p>

### `report.edit`

Change a report's configuration.

- `config` - only the keys to change (title, cron, daily_at, every_minutes, deliver, alert...)
- `title`

<p class="runs">Runs at once, with an undo on the receipt.</p>

### `report.delete`

Delete a report or workflow for good; asks first.

- `title`

<p class="runs">Waits for your yes on a card.</p>

## App

Settings, connections, scripts and kept facts.

### `setting.set`

Change one setting; the schema says what it takes.

- `setting` - its key, or `label`: part of its name
- `value`

<p class="runs">Runs at once, with an undo on the receipt.</p>

### `connection.create`

Add a system Taskuary talks to; created OFF and never carrying a secret, which the owner gives on the card.

- `type`
- `name`

<p class="runs">Waits for your yes on a card.</p>

### `connection.test`

Test a connection now and say what it answered.

- `name`

<p class="runs">Runs at once, with an undo on the receipt.</p>

### `connection.pause`

Switch a connection off; nothing is deleted.

- `name`

<p class="runs">Runs at once, with an undo on the receipt.</p>

### `connection.resume`

Switch a connection back on.

- `name`

<p class="runs">Runs at once, with an undo on the receipt.</p>

### `script.start`

Start a script by its name: walk me through my tasks | set up Taskuary | set up a report.

- `name`

<p class="runs">Runs at once, with an undo on the receipt.</p>

### `memory.remember`

Keep a fact.

- `note`

<p class="runs">Waits for your yes on a card.</p>

### `hub.publish`

Save to the company Hub. Only a reusable discovery reached through real work, or a developed idea with its reasons - never a transcript, a task log or a routine answer. When the owner asks to save something there, or a turn clearly earns it.

- `title` - one durable claim
- `body` - why it matters and what to do
- `topic` (optional)
- `kind` (optional) - new_idea | technical_solve | howto | gotcha | decision | system | people
- `why_earned` (optional)

<p class="runs">Waits for your yes on a card.</p>

## Look

Look-ups - they run at once and change nothing.

### `task.read`

Everything on one task - its summary, status, the messages on it, what agents said and did.

- `ref` - TQ-0401 (or `id`)

<p class="runs">Runs at once and changes nothing.</p>

### `timeline.search`

Find messages anywhere in the history, however old - takes the same SELECT fields below, plus `limit`; here `contains` matches the subject, the sender AND the body, best match first. Returns m-numbers, refs, senders, subjects and dates; open one with message.read or its task with task.read.

- `limit`
- `contains`

<p class="runs">Runs at once and changes nothing.</p>

### `tasks.list`

The tasks.

- `status` - open (the default: open, in progress or waiting) | done | all
- `contains` - words
- `limit`

<p class="runs">Runs at once and changes nothing.</p>

### `message.read`

One message in full - who, when, its task and the whole text.

- `mid` - the m-number timeline.search printed

<p class="runs">Runs at once and changes nothing.</p>

### `sender.read`

One person at a glance - how often they write, their recent messages, their open tasks, when you last wrote back and what the owner told you to remember about them.

- `who` - a name or an address

<p class="runs">Runs at once and changes nothing.</p>

### `docs.search`

How Taskuary works and how to set it up (the help pages), and the owner's own docs (SOUL, TRIAGE, COUNSEL...). Use it for any "how do I", "what does X do" or "why did it" about the app.

- `query` - the words

<p class="runs">Runs at once and changes nothing.</p>

### `agents.now`

Every agent session running now - its task, which CLI, and whether it is working, idle, stuck or asking the owner something.

<p class="runs">Runs at once and changes nothing.</p>

### `approvals.list`

Everything waiting for the owner's yes: drafted replies and the actions agents proposed, with their tasks.

<p class="runs">Runs at once and changes nothing.</p>

### `pipe.list`

Everything waiting on the owner, lane by lane - replies, asks, approvals, stopped agents, reports: the whole work rail. Use it for "what's waiting", "what's left", "what do I have"

<p class="runs">Runs at once and changes nothing.</p>

### `calendar.read`

The owner's meetings. Reads the calendar live, so it takes a moment.

- `from` - today (the default) | tomorrow | YYYY-MM-DD
- `days` - how many (7 by default)

<p class="runs">Runs at once and changes nothing.</p>

### `activity.list`

What happened, from the audit trail: counts by kind and the latest entries.

- `days` - 1 by default
- `who` - you | agents | all

<p class="runs">Runs at once and changes nothing.</p>

### `errors.list`

What is failing and what failed: the bell (dismissed ones marked), failed agent runs, report runs, drafts, triage and actions over `days` (3 by default), and the last errors in the log. Use it for any "what broke", "why did X not happen", "is anything wrong"

- `days` - 3 by default

<p class="runs">Runs at once and changes nothing.</p>

### `memory.list`

Everything kept about the owner: the saved notes (from "remember this", their verdicts, Settings) and what LEARNED.md has learned from their verdicts. Use it for "what do you remember", "what do you know about me"

- `about` - words to narrow it (a sender, a topic)

<p class="runs">Runs at once and changes nothing.</p>

### `rules.list`

The standing filters on the owner's mail - queue mutes set with a reason, and the policy rules (skip, ignore, escalate...) that decide before any model reads it. Use it for "why did I never see X", "what am I filtering"

- `about` - words to narrow it

<p class="runs">Runs at once and changes nothing.</p>

### `report.read`

A report or workflow and its last runs - what it said, whether it failed and why, and its source_id.

- `title` - part of its name (or `source_id`)

<p class="runs">Runs at once and changes nothing.</p>

### `reports.list`

Every report and workflow: name, source_id, clock, how it reaches the owner, last outcome.

<p class="runs">Runs at once and changes nothing.</p>

### `settings.list`

The settings in one `group` (or, with no group, the groups themselves and how many knobs each has)

- `group` - or, with no group, the groups themselves and how many knobs each has

<p class="runs">Runs at once and changes nothing.</p>

### `setting.read`

One setting, its value in words and what it does.

- `key` - or `label`: part of its name

<p class="runs">Runs at once and changes nothing.</p>

### `connections.list`

Every live connection: name, type, whether it has a key, last sync, last error - and how many catalogue cards are off.

<p class="runs">Runs at once and changes nothing.</p>

### `connection.read`

One connection in full.

- `name` - part of its name (or `connector_id`)

<p class="runs">Runs at once and changes nothing.</p>

### `agents.list`

The agents and profiles, and which brain answers which job.

<p class="runs">Runs at once and changes nothing.</p>

### `repos.list`

The repositories a coding agent can work in, and what each one is for.

<p class="runs">Runs at once and changes nothing.</p>

### `tools.list`

Every tool in one `bucket` (table, task, agents, new, pipe, reports, app, look) - what each does and needs.

- `bucket` - table, task, agents, new, pipe, reports, app, look

<p class="runs">Runs at once and changes nothing.</p>

### `tools.describe`

One tool in full.

- `kind` - its name

<p class="runs">Runs at once and changes nothing.</p>

### `knowledge.search`

What the company knows - the Hub, the indexed documents and the facts the owner asked to keep. Call it FIRST whenever the owner asks about a person, a site, a policy, a system or how something is done here - never offer to look it up instead of looking.

- `query` - the words to look for

<p class="runs">Runs at once and changes nothing.</p>

