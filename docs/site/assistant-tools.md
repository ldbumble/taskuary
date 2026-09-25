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

## Every tool, in detail

| Tool | Bucket | Needs | What it does | Runs |
|---|---|---|---|---|
| `reply` | table | text | write a reply to the sender - text: the gist, in the owner's words. Nothing is sent | at once - a draft, nothing sent |
| `approve` | table | - | send the drafted reply as it stands | you confirm |
| `redraft` | table | text | write the draft again - text: the change | at once - a draft, nothing sent |
| `mine` | table | - | make it a task on the owner's own list - no agent | you confirm |
| `regular_agent` | table | text, as? | send it to a non-coding agent - text: the job; as: a profile from agents.list, only when one fits | you confirm |
| `coder` | table | text, as? | send it to a coding agent - text: what is wanted; as: the repository (repos.list), only when sure. Not sure which repository is no reason to ask - CALL it, and its card offers every repository to pick | you confirm |
| `not_ours` | table | - | file it, just this once - its card asks whether from now on, or as a rule | you confirm |
| `not_ours_sender` | table | - | file everything from this sender from now on - their mail still arrives and stays readable | you confirm |
| `block_sender` | table | - | an exclusion rule in Settings: the sender never reaches triage again - only when they ask for a rule | you confirm |
| `close` | table | - | Mark done - the task behind the item is finished | at once |
| `done` | table | - | the owner handled it - Mark done on a task; on an idea, a report or an fyi it is read and settled | at once |
| `next` | table | - | move on to the next thing | at once |
| `answer_agent` | table | text | answer the agent waiting on the owner - text | you confirm |
| `stop_agent` | table | - | save and end the agent's session on the item | at once |
| `rerun` | table | - | run the report on the table again | you confirm |
| `remember` | table | text | keep a fact - text | you confirm |
| `setup` | table | text | build a report, a connection to another system or an automation - text: the request. Never a to-do | you confirm |
| `clear` | table | text | clear these from the pipe - text: which | you confirm |
| `confirm` | table | - | the owner's yes to the card already waiting - only when one is | at once |
| `cancel` | table | - | the owner's no to it | at once |
| `task.update` | task | priority/title/assignee | change a task's priority, title or owner - any of priority: low / normal / high / urgent, title, assignee ('me', or an agent's role); ref when it is not the one on the table | you confirm |
| `task.set_kind` | task | kind | say what kind of work a task is - kind: task (the owner does it) / general (a non-coding agent) / coding; ref | you confirm |
| `task.set_repo` | task | repo | put a coding task in the repository it belongs in - repo (its name, as the repositories list says it); ref | you confirm |
| `task.check` | task | item, done? | tick a checklist item on a task - item: its number (1 is the first) or words from it; done: false un-ticks; ref | you confirm |
| `task.comment` | task | text | file a note on a task - text; ref | you confirm |
| `task.split` | task | text | split one arrival into two jobs - text | you confirm |
| `task.merge` | task | into | fold a task into the one it duplicates - into: the survivor's ref (TQ-0123); ref is the one folded away | you confirm |
| `task.reopen` | task | - | reopen a task that was marked done - ref | you confirm |
| `task.not_a_task` | task | - | delete a task and teach triage it was never work - ref | you confirm |
| `task.complete` | task | - | Mark done - the task is finished | you confirm |
| `task.defer` | task | until | Remind me: put an open task away until a day and bring it back that morning - until: a date (2026-10-09), "2 weeks", "3 days", "monday", or "none" to bring it back now; ref names the task (TQ-0123) when it is not the one on the table | at once, with an undo |
| `task.handoff` | task | who, note? | hand a task to a PERSON - who (a name or address that has written here), note optional: writes the forward for the owner's yes, nothing is sent from this card; ref | you confirm |
| `task.clarify` | task | text | prepare a question for the task's sender - text: the question; it waits for the owner's yes, never sent from here; ref | you confirm |
| `review.approve` | task | - | send the drafted reply as it stands | you confirm |
| `review.reject` | task | - | reject the draft reply waiting on a task - nothing is sent, the task stays open; ref names the task | you confirm |
| `dispatch.prepare` | agents | kind, instructions? | start an agent on an EXISTING task - kind: coding / general, instructions optional; a coding task asks which repository when it is not clear; ref | you confirm |
| `agent.continue` | agents | - | pick up the agent's own last session on a task where it left off - ref | you confirm |
| `agent.answer` | agents | text | answer the agent that is waiting - text; ref names its task when it is not the one on the table | you confirm |
| `agent.stop` | agents | - | save and end an agent's session - the one on the table, or the task ref names; never a guess at which | you confirm |
| `routing.remember` | agents | field, value | remember how work like this should be ROUTED next time - field: kind / profile / system, and value. kind: coding (an agent in a checkout) / general (the assistant) / task (the owner, no agent). system: where the work actually lives when no repository here can touch it, named plainly ("ADP"). It teaches triage and moves nothing - say it when the owner tells you a verdict was wrong, or where a kind of job really belongs. | you confirm |
| `task.create_from_text` | new | kind, text | a new job with no message behind it - kind: task (a to-do or reminder the owner does themselves, no agent) / general (a regular agent) / coding, and text. Never for a task that already exists (a TQ ref): starting an agent on one is dispatch.prepare, and its own last session is agent.continue | you confirm |
| `task.create_from_message` | new | kind | hand this message to an agent or put it on the list - kind: coding / general / task | you confirm |
| `task.setup` | new | text | open a walk-through with the assistant, for a set-up that needs digging first - text | you confirm |
| `pipe.clear` | pipe | - | clear a SET of items from the pipe at once - takes select (below); read, never deleted | you confirm |
| `item.settle` | pipe | verb | put the item down - verb: done / later / skip (the item on the table is the target) | you confirm |
| `message.file` | pipe | - | file it - not ours, just this one | you confirm |
| `message.archive` | pipe | - | archive it: off the pipe and closed, nothing deleted | you confirm |
| `preference.exclude_sender` | pipe | scope | teach triage to file this sender or subject from now on - their mail still arrives (scope: sender / subject) | you confirm |
| `preference.sender_rule` | pipe | - | an exclusion rule in Settings: this sender never reaches triage again and what already arrived leaves the Timeline | you confirm |
| `report.create` | reports | config | create a scheduled report or workflow - config; the composer builds it from what the owner asked for | you confirm |
| `report.run` | reports | - | run a report or workflow now - title (or source_id); it lands in the pipe when done | at once, with an undo |
| `report.rerun` | reports | - | run that report again | you confirm |
| `report.pause` | reports | - | stop a report or workflow running on its clock - title | at once, with an undo |
| `report.resume` | reports | - | put a paused report or workflow back on its clock - title | at once, with an undo |
| `report.reach` | reports | reach | change when a report reaches the owner - title, reach: always / wrong / rule | at once, with an undo |
| `report.edit` | reports | config | change a report's configuration - title, config: only the keys to change (title, cron, daily_at, every_minutes, deliver, alert...) | at once, with an undo |
| `report.delete` | reports | - | delete a report or workflow for good - title; asks first | you confirm |
| `setting.set` | app | setting, value | change one setting - setting (its key, or label: part of its name) and value; the schema says what it takes | at once, with an undo |
| `connection.create` | app | type, name | add a system Taskuary talks to - type, name; created OFF and never carrying a secret, which the owner gives on the card | you confirm |
| `connection.test` | app | - | test a connection now and say what it answered - name | at once, with an undo |
| `connection.pause` | app | - | switch a connection off - name; nothing is deleted | at once, with an undo |
| `connection.resume` | app | - | switch a connection back on - name | at once, with an undo |
| `script.start` | app | name | start a script by its name: walk me through my tasks / set up Taskuary / set up a report | at once, with an undo |
| `memory.remember` | app | note | keep a fact - note | you confirm |
| `hub.publish` | app | title, body, topic?, kind?, why_earned? | save to the company Hub - title: one durable claim, body: why it matters and what to do, topic, kind: new_idea / technical_solve / howto / gotcha / decision / system / people, why_earned. Only a reusable discovery reached through real work, or a developed idea with its reasons - never a transcript, a task log or a routine answer. When the owner asks to save something there, or a turn clearly earns it | you confirm |
| `task.read` | look | - | everything on one task - its summary, status, the messages on it, what agents said and did. ref: TQ-0401 (or id) | at once |
| `timeline.search` | look | - | find messages anywhere in the history, however old - takes the same SELECT fields below, plus limit; here contains matches the subject, the sender AND the body, best match first. Returns m-numbers, refs, senders, subjects and dates; open one with message.read or its task with task.read | at once |
| `tasks.list` | look | - | the tasks - status: open (the default: open, in progress or waiting) / done / all; contains: words; limit | at once |
| `message.read` | look | - | one message in full - who, when, its task and the whole text. mid: the m-number timeline.search printed | at once |
| `sender.read` | look | - | one person at a glance - how often they write, their recent messages, their open tasks, when you last wrote back and what the owner told you to remember about them. who: a name or an address | at once |
| `docs.search` | look | - | how Taskuary works and how to set it up (the help pages), and the owner's own docs (SOUL, TRIAGE, COUNSEL...). query: the words. Use it for any "how do I", "what does X do" or "why did it" about the app | at once |
| `agents.now` | look | - | every agent session running now - its task, which CLI, and whether it is working, idle, stuck or asking the owner something | at once |
| `approvals.list` | look | - | everything waiting for the owner's yes: drafted replies and the actions agents proposed, with their tasks | at once |
| `pipe.list` | look | - | everything waiting on the owner, lane by lane - replies, asks, approvals, stopped agents, reports: the whole work rail. Use it for "what's waiting", "what's left", "what do I have" | at once |
| `calendar.read` | look | - | the owner's meetings - from: today (the default) / tomorrow / YYYY-MM-DD; days: how many (7 by default). Reads the calendar live, so it takes a moment | at once |
| `activity.list` | look | - | what happened, from the audit trail: counts by kind and the latest entries. days (1 by default); who: you / agents / all | at once |
| `errors.list` | look | - | what is failing and what failed: the bell (dismissed ones marked), failed agent runs, report runs, drafts, triage and actions over days (3 by default), and the last errors in the log. Use it for any "what broke", "why did X not happen", "is anything wrong" | at once |
| `memory.list` | look | - | everything kept about the owner: the saved notes (from "remember this", their verdicts, Settings) and what LEARNED.md has learned from their verdicts. about: words to narrow it (a sender, a topic). Use it for "what do you remember", "what do you know about me" | at once |
| `rules.list` | look | - | the standing filters on the owner's mail - queue mutes set with a reason, and the policy rules (skip, ignore, escalate...) that decide before any model reads it. about: words to narrow it. Use it for "why did I never see X", "what am I filtering" | at once |
| `report.read` | look | - | a report or workflow and its last runs - what it said, whether it failed and why, and its source_id. title: part of its name (or source_id) | at once |
| `reports.list` | look | - | every report and workflow: name, source_id, clock, how it reaches the owner, last outcome | at once |
| `settings.list` | look | - | the settings in one group (or, with no group, the groups themselves and how many knobs each has) | at once |
| `setting.read` | look | - | one setting, its value in words and what it does. key (or label: part of its name) | at once |
| `connections.list` | look | - | every live connection: name, type, whether it has a key, last sync, last error - and how many catalogue cards are off | at once |
| `connection.read` | look | - | one connection in full. name: part of its name (or connector_id) | at once |
| `agents.list` | look | - | the agents and profiles, and which brain answers which job | at once |
| `repos.list` | look | - | the repositories a coding agent can work in, and what each one is for | at once |
| `tools.list` | look | - | every tool in one bucket (table, task, agents, new, pipe, reports, app, look) - what each does and needs | at once |
| `tools.describe` | look | - | one tool in full - kind: its name | at once |
| `knowledge.search` | look | - | what the company knows - the Hub, the indexed documents and the facts the owner asked to keep. query: the words to look for. Call it FIRST whenever the owner asks about a person, a site, a policy, a system or how something is done here - never offer to look it up instead of looking | at once |
