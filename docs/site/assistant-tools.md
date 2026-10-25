<!-- Written by `python -m taskuary.toolcatalog` from taskuary/toolcatalog.py - edit the catalogue, not this page. -->

What the Assistant is told about its tools. It gets the **summary** on every turn: the buckets, and
each tool's name and what it needs. It asks for the **detail** of a bucket (`tools.list`) or a tool
(`tools.describe`) only when a turn needs it. Everything it can change, it brings up for you to press:
the button that does it, lit, or the page that holds it. On a phone it asks yes or no.

## The summary, sent every turn

| Bucket | What it is for | Tools, and what each needs |
|---|---|---|
| **table** | decide about the item on the table | reply(text, cc?), approve, redraft(text), mine, regular_agent(text, as?, new?), coding_agent(text, as?, new?), not_ours, not_ours_sender, block_sender, not_ours_kind, close, next, answer_agent(text), stop_agent, rerun, remember(text), setup(text), confirm, cancel, chase, let_go, accept_invite, decline_invite, propose_time, find_time, prepare, elsewhere |
| **task** | change any task - the table's, or one named by ref | task.update(priority/title/assignee/due), task.set_kind(kind), task.set_repo(repo), task.check(item, done?, note?), task.checklist(add?, items?, emails?, drop?), task.watch(what?), task.comment(text), task.split(text), task.merge(into), task.reopen, task.not_a_task, task.complete(note?), task.defer(until), task.handoff(who, note?), task.clarify(text), task.share(who, about?), review.approve, review.reject |
| **agents** | start, continue, answer or stop a task's agent; teach where work belongs | dispatch.prepare(kind, instructions?), agent.continue, agent.answer(text), agent.stop, routing.remember(field, value), task.ask_agent(who, text) |
| **new** | new work with no task yet | task.create_from_text(kind, text), task.create_from_message(kind), task.setup(text) |
| **pipe** | the walk and sets of items, and filing mail | pipe.clear, pipe.defer(select, until), pipe.close(select), review.each, button.light(button, ref?, note?), item.settle(verb), message.file, message.archive, preference.exclude_sender(scope), preference.sender_rule, message.retriage |
| **reports** | reports and workflows | report.create(config), report.run, report.rerun, report.pause, report.resume, report.route(line, how), report.edit(config), report.delete |
| **app** | settings, connections, roles, scripts and kept facts | setting.set(setting, value), connection.create(type), role.apply(role, portal?, route_mail?), connection.test, connection.pause, connection.resume, app.repair(name, how), script.start(name), memory.remember(note), people.relate(who), hub.publish(title, body, topic?, kind?, why_earned?) |
| **look** | look-ups - they run at once and change nothing | app.find, task.read, timeline.search, tasks.list, asks.list, message.read, sender.read, docs.search, agents.now, approvals.list, pipe.list, calendar.read, activity.list, errors.list, memory.list, rules.list, missed.check, report.read, reports.list, settings.list, setting.read, connections.list, connection.read, app.health, agents.list, repos.list, tools.list, tools.describe, knowledge.search |

A task you name goes in `ref` ("TQ-0123"); otherwise the tool acts on what is on the table.

## Table

Decide about the item on the table.

### `reply`

The "Reply" button: write a reply to the sender. Nothing is sent.

- `text` - the gist, in the owner's words
- `cc` (optional) - people to loop in on it, by name or address ("loop Gail in and ask her" is a reply with Gail copied, never an agent)

<p class="runs">At once - a draft, nothing sent.</p>

### `approve`

The "Send" button ("Approve" on an agent's proposal or a task's close-out): the owner's yes to what is drafted on the item: sends the reply as it stands - on a task's close-out it merges the pull request or closes the issue FIRST, then sends the reply; on an agent's proposal it runs that action and only that. It never closes the task - that is close, the owner's own Mark done, a separate step - and never continues an agent's session - that is agent.continue.

<p class="runs">Brings up its button for you to press.</p>

### `redraft`

The "Redraft" button ("Draft with AI" when nothing is drafted yet): write the draft again.

- `text` - the change

<p class="runs">At once - a draft, nothing sent.</p>

### `mine`

The "Put it on my list" button: make it a task on the owner's own list - no agent.

<p class="runs">Brings up its button for you to press.</p>

### `regular_agent`

The "Send to agent" button: send it to an agent that does not write code - it becomes a task of its own. Never for Taskuary's own settings, connections or update: those are its own screens (app.find)

- `text` - the job
- `as` (optional) - a profile from agents.list, only when one fits
- `new` (optional) - true when the job is NOT about the item on the table

<p class="runs">Brings up its button for you to press.</p>

### `coding_agent`

The "Send to coding agent" button: send it to a coding agent. Not sure which repository is no reason to ask - CALL it, and its card offers every repository to pick.

- `text` - what is wanted
- `as` (optional) - the repository (repos.list), only when sure
- `new` (optional) - true when the job is NOT about the item on the table

<p class="runs">Brings up its button for you to press.</p>

### `not_ours`

The "Not ours" button: file it, just this once - its card asks whether from now on, or as a rule.

<p class="runs">Brings up its button for you to press.</p>

### `not_ours_sender`

The "Ignore this sender" button: file everything from this sender from now on - their mail still arrives and stays readable.

<p class="runs">Brings up its button for you to press.</p>

### `block_sender`

The "Block this sender" button: an exclusion rule in Settings: the sender never reaches triage again - only when they ask for a rule.

<p class="runs">Brings up its button for you to press.</p>

### `not_ours_kind`

The "No more ideas like this" button: an Advisor idea only: put it down AND no more ideas like it - the Advisor's next run reads that.

<p class="runs">Brings up its button for you to press.</p>

### `close`

The "Mark done" button: the task behind the item is finished.

<p class="runs">Brings up its button for you to press.</p>

### `next`

The "Next" button: move on to the next thing - this one is put down, still theirs, marked nothing. Never for "mark ... read" or "clear ..." - those name a set: pipe.clear.

<p class="runs">At once.</p>

### `answer_agent`

The "Answer it" button: answer the agent waiting on the owner.

- `text`

<p class="runs">Brings up its button for you to press.</p>

### `stop_agent`

The "Stop and save" button: save and end the agent's session on the item.

<p class="runs">Brings up its button for you to press.</p>

### `rerun`

The "Run it again" button: run the report on the table again.

<p class="runs">Brings up its button for you to press.</p>

### `remember`

Keep a fact.

- `text`

<p class="runs">Brings up its button for you to press.</p>

### `setup`

Build a report, a playbook (how one kind of recurring request is handled from now on), a connection to another system or an automation. Never a to-do, and never an agent's job.

- `text` - the request

<p class="runs">Brings up its button for you to press.</p>

### `confirm`

The owner's yes to the card already waiting - only when one is.

<p class="runs">At once.</p>

### `cancel`

The owner's no to it.

<p class="runs">At once.</p>

### `chase`

The "Chase them" button: chase the person who has gone quiet on the item - a short nudge in the owner's voice is drafted on the thread, copying whoever the ledger says moves them; nothing is sent.

<p class="runs">Brings up its button for you to press.</p>

### `let_go`

The "Let it go" button: let the quiet item go - the step somebody owed is dropped, or the follow-up is put down; three on one person and the Advisor stops raising them.

<p class="runs">Brings up its button for you to press.</p>

### `accept_invite`

The "Accept" button: accept the invite waiting on the owner - drafted for their Send.

<p class="runs">Brings up its button for you to press.</p>

### `decline_invite`

The "Decline" button: decline the invite waiting on the owner - drafted for their Send.

<p class="runs">Brings up its button for you to press.</p>

### `propose_time`

The "Propose a new time" button: propose another time for the invite from its free times - drafted for their Send.

<p class="runs">Brings up its button for you to press.</p>

### `find_time`

The "Find a time" button: free times for the meeting a thread asks for - the pick drafted as an invite for their Send.

<p class="runs">Brings up its button for you to press.</p>

### `prepare`

The "Prepare" button: a meeting on the table only: an agent researches its people and subject through the owner's saved mail and chats and files a short brief on the meeting's task. Nothing is sent.

- `text` - anything the owner wants it to look into

<p class="runs">Brings up its button for you to press.</p>

### `elsewhere`

The "They answered elsewhere" button: they answered elsewhere; the step somebody owed closes as done, or the follow-up is put down.

- `text` - where (a call, a meeting)

<p class="runs">Brings up its button for you to press.</p>

## Task

Change any task - the table's, or one named by ref.

### `task.update`

Change a task's priority, title, owner or due day. Any other value is refused with the allowed ones.

- `priority` - low | normal | high | urgent
- `title`
- `assignee` - exactly `owner` (the owner takes it) or `agent:<profile>` (a worker on the roster)
- `due` - the day the work is due (2026-10-30, "friday", "2 weeks", or "none" to clear it)
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.set_kind`

Say what kind of work a task is.

- `kind` - task (the owner does it) | general (a non-coding agent) | coding
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.set_repo`

Put a coding task in the repository it belongs in.

- `repo` - its name, as the repositories list says it
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.check`

Tick, untick or note one to-do on a task - with only a note it is not ticked.

- `item` - its NUMBER (1 is the first; the facts list them numbered)
- `done` (optional) - false un-ticks
- `note` (optional) - words kept under it ("Gail has it"; "" removes it)
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.checklist`

Change what a task's checklist asks for.

- `add` (optional) - new to-dos to append ("add a to-do: call the bank")
- `items` (optional) - the full list of item words in order (one left out is removed, emails untouched)
- `emails` (optional) - [{to, about}] to add emails that must go out before it closes
- `drop` (optional) - recipients whose email is no longer owed
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.watch`

Tell the owner here when something happens on a task nobody needs to start.

- `what` (optional) - done (when it is finished) | reply (when someone writes on it) | any (the default) | off
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.comment`

File a note on a task.

- `text`
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.split`

Split one arrival into two jobs.

- `text`

<p class="runs">Brings up its button for you to press.</p>

### `task.merge`

Fold a task into the one it duplicates.

- `into` - the survivor's ref (TQ-0123)
- `ref` (optional) - the task that is the one folded away

<p class="runs">Brings up its button for you to press.</p>

### `task.reopen`

Reopen a task that was marked done.

- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.not_a_task`

Delete a task and teach triage it was never work.

- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.complete`

Mark done - the task is finished - kept on the task.

- `note` (optional) - (optional): what came of it, in the owner's words when they said it ("the GL export reconciled fine")

<p class="runs">Brings up its button for you to press.</p>

### `task.defer`

Remind me: put an open task away until a day and bring it back then - calendar or not: the app picks the time, or says there is none to pick from - never a day guessed instead, or "none" to bring it back now. "Remind me about <a task that exists>" - named by ref, sender or subject - is this, never a new to-do.

- `until` - a date (2026-10-09), "2 weeks", "3 days", "monday", with the time they said kept ("tomorrow 9am", "friday 2pm"), "after_meetings" whenever they mean once the day's meetings or calls are over
- `ref` (optional) - the task (TQ-0123) when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.handoff`

Hand a task to a PERSON.

- `who` - a name or address that has written here
- `note` (optional) - writes the forward for the owner's yes, nothing is sent from this card
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.clarify`

Prepare a question for the task's sender; it waits for the owner's yes, never sent from here.

- `text` - the question
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.share`

Email what a task's work found; a draft for the owner's yes, never sent.

- `who` - an address
- `about` (optional)
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `review.approve`

The owner's yes to what is drafted: sends the reply as it stands - and on a task's close-out merges the pull request (or closes the issue) FIRST, sending the reply only if that worked. The task stays open: task.complete (Mark done) is the close.

<p class="runs">Brings up its button for you to press.</p>

### `review.reject`

Reject the draft reply waiting on a task - nothing is sent, the task stays open.

- `ref` (optional) - the task

<p class="runs">Brings up its button for you to press.</p>

## Agents

Start, continue, answer or stop a task's agent; teach where work belongs.

### `dispatch.prepare`

Start an agent on an EXISTING task; a coding task asks which repository when it is not clear.

- `kind` - coding | general
- `instructions` (optional)
- `ref` - the task (TQ-0123) - always named, the one on the table included; a new job is task.create_from_text

<p class="runs">Brings up its button for you to press.</p>

### `agent.continue`

Pick up the agent's own last session on a task where it left off, coding or not.

- `ref` - the task (TQ-0123) - the one on the table when it has a saved session to reopen
- `note` - when the owner said what to tell it as it picks up

<p class="runs">Brings up its button for you to press.</p>

### `agent.answer`

Answer the agent that is waiting. With no agent on the task (TASK NOW says so) nobody hears it - say so; agent.continue or starting one is the owner's call, never this.

- `text`
- `ref` (optional) - its task when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `agent.stop`

Save and end an agent's session - the one on the table, or the task `ref` names; never a guess at which.

- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `routing.remember`

Remember how work like this should be ROUTED next time. kind: coding (an agent in a checkout) | general (the assistant) | task (the owner, no agent). system: where the work actually lives when no repository here can touch it, named plainly ("ADP"). It teaches triage and moves nothing - say it when the owner tells you a verdict was wrong, or where a kind of job really belongs.

- `field` - kind | profile | system
- `value`

<p class="runs">Brings up its button for you to press.</p>

### `task.ask_agent`

Ask a trusted teammate's coding agent over Reason Network; the reply is noted on the task.

- `who` - their name or person/session
- `text` - the question
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

## New

New work with no task yet.

### `task.create_from_text`

A new job with no message behind it. Never for a task that already exists (a TQ ref, or a row on THE RAIL BY NAME): starting an agent on one is dispatch.prepare, its own last session is agent.continue, and "remind me about it" is task.defer on it.

- `kind` - task (a to-do or reminder the owner does themselves, no agent) | general (a regular agent) | coding
- `text` - , and a short `title` in your own words for the job (never "send it to the agent")

<p class="runs">Brings up its button for you to press.</p>

### `task.create_from_message`

Hand this message to an agent or put it on the list.

- `kind` - coding | general | task

<p class="runs">Brings up its button for you to press.</p>

### `task.setup`

Open a walk-through with the assistant, for a set-up that needs digging first.

- `text`
- `title` - a few words naming the job for the task list

<p class="runs">Brings up its button for you to press.</p>

## Pipe

The walk and sets of items, and filing mail.

### `pipe.clear`

Clear a SET of items from the pipe at once - takes `select` (below); read, never deleted. "Clear all the FYI" and "mark the FYI read" - one FYI on the table or many - are this with kind: fyi, never next. Their words naming the set are the press: it is marked read at once and the count said. It only clears: when the owner says "from now on" too, also CALL preference.exclude_sender or preference.sender_rule.

- `select` - below

<p class="runs">Brings up its button for you to press.</p>

### `pipe.defer`

Put a SET away until a day. Runs at once and the count is said.

- `select` - below
- `until` - (as task.defer takes it): "snooze everything from Gail until Monday" is select sender: Gail

<p class="runs">Brings up its button for you to press.</p>

### `pipe.close`

Close a SET at once. "Close all the tasks from Priya" is select sender: Priya. Runs at once and the count is said.

- `select` - (below): each task in it is marked done, each notice read

<p class="runs">Brings up its button for you to press.</p>

### `review.each`

"approve all the drafts": brings the next draft waiting for a Send up with its Send lit, and says how many are left - each one still goes only by its own press; CALL it again for the one after.

<p class="runs">Brings up its button for you to press.</p>

### `button.light`

Light any button a row draws, by its name. A put-down (close, close_note with its note, remove, not_ours) is pressed.

- `button` - the verb (THE BUTTONS BY NAME, or a row's own: review_changes, run_another, attach, pick_repo, change_kind...)
- `ref` (optional) - the task (TQ-0123), when it is not the row on the table
- `note` (optional) - a close_note's note, the owner's reason in their words

<p class="runs">Brings up its button for you to press.</p>

### `item.settle`

Put the item down, read and settled.

- `verb` - done (the item on the table is the target)

<p class="runs">Brings up its button for you to press.</p>

### `message.file`

File it - not ours, just this one.

<p class="runs">Brings up its button for you to press.</p>

### `message.archive`

Archive it: off the pipe and closed, nothing deleted.

<p class="runs">Brings up its button for you to press.</p>

### `preference.exclude_sender`

Teach triage to file this sender or subject from now on - their mail still arrives (`scope`: sender | subject)

- `scope` - sender | subject

<p class="runs">Brings up its button for you to press.</p>

### `preference.sender_rule`

An exclusion rule in Settings: this sender never reaches triage again and what already arrived leaves the work rail.

<p class="runs">Brings up its button for you to press.</p>

### `message.retriage`

Triage reads the message on the table again - one it could not sort.

<p class="runs">Brings up its button for you to press.</p>

## Reports

Reports and workflows.

### `report.create`

Create a scheduled report or workflow; the composer builds it from what the owner asked for.

- `config`

<p class="runs">Brings up its button for you to press.</p>

### `report.run`

Run a report or workflow now; a report lands in the pipe when done, a workflow starts as its task at once (the ref comes back)

- `title` - or `source_id`

<p class="runs">Brings up its button for you to press.</p>

### `report.rerun`

Run that report again.

<p class="runs">Brings up its button for you to press.</p>

### `report.pause`

Stop a report or workflow running on its clock.

- `title`

<p class="runs">Brings up its button for you to press.</p>

### `report.resume`

Put a paused report or workflow back on its clock.

- `title`

<p class="runs">Brings up its button for you to press.</p>

### `report.route`

Change where one line of a report's route card goes.

- `line` - timeline | alert | send
- `how` - always | ai | rule | never
- `title`
- `when` - for ai: what to look for
- `rule` - /`count`/`text` (for rule)

<p class="runs">Brings up its button for you to press.</p>

### `report.edit`

Change a report's configuration.

- `config` - only the keys to change (title, cron, daily_at, every_minutes, deliver, alert...)
- `title`

<p class="runs">Brings up its button for you to press.</p>

### `report.delete`

Remove a report or workflow.

- `title` - kept 30 days under Recently deleted

<p class="runs">Brings up its button for you to press.</p>

## App

Settings, connections, roles, scripts and kept facts.

### `setting.set`

Change one setting; the schema says what it takes.

- `setting` - its key, or `label`: part of its name
- `value`

<p class="runs">Brings up its button for you to press.</p>

### `connection.create`

Bring up a connector card to connect it; a second one of a kind opens with its Add another. Never carrying a secret: the owner gives it on the card.

- `type` - the catalogue type or title (linkedin, slack, "QuickBooks Online")
- `name` (optional)

<p class="runs">Brings up its button for you to press.</p>

### `role.apply`

Set Taskuary up for the owner's job in one go - its worker, playbooks and daily workflow. Before calling, ASK the owner, one question at a time: the address of their bill-approval portal (`portal`; fine to leave out), and whether their own non-coding mail should go to that worker (`route_mail`: true or false - when they are only trying it out, false). The workflow is created OFF: after the yes, offer to run it once (report.run), and say they sign in to the portal themselves in the browser pane.

- `role` - ap (accounts payable)
- `portal` (optional)
- `route_mail` (optional) - true or false - when they are only trying it out

<p class="runs">Brings up its button for you to press.</p>

### `connection.test`

Test a connection now and say what it answered.

- `name`

<p class="runs">Brings up its button for you to press.</p>

### `connection.pause`

Switch a connection off; nothing is deleted.

- `name`

<p class="runs">Brings up its button for you to press.</p>

### `connection.resume`

Switch a connection back on.

- `name`

<p class="runs">Brings up its button for you to press.</p>

### `app.repair`

Run the simple repair app.health named for a part of Taskuary, then read it again.

- `name` - the connection
- `how` - restart_bridge (the WhatsApp bridge this computer runs), sync or test, as app.health said

<p class="runs">Runs at once and says what it changed.</p>

### `script.start`

Start a script by its name: walk me through my tasks | set up a report.

- `name`

<p class="runs">Brings up its button for you to press.</p>

### `memory.remember`

Keep a fact.

- `note`

<p class="runs">Brings up its button for you to press.</p>

### `people.relate`

Who someone is to the owner, on their org chart. "Erin is my manager", "Ray owns payroll", "Gail reports to me" - never memory.remember for these: triage and agents read the chart.

- `who` - a name or address
- `relation` - manager | report | none (none clears it)
- `owns` - areas they are responsible for ("payroll, benefits"), added
- `drops` - areas taken off
- `forget` - true takes them off the chart

<p class="runs">Runs at once and says what it changed.</p>

### `hub.publish`

Save to the company Hub. Only a reusable discovery reached through real work, or a developed idea with its reasons - never a transcript, a task log or a routine answer. When the owner asks to save something there, or a turn clearly earns it.

- `title` - one durable claim
- `body` - why it matters and what to do
- `topic` (optional)
- `kind` (optional) - new_idea | technical_solve | howto | gotcha | decision | system | people
- `why_earned` (optional)

<p class="runs">Brings up its button for you to press.</p>

## Look

Look-ups - they run at once and change nothing.

### `app.find`

Bring ANYTHING in the app up by words - a setting, a connector card (the catalogue's and the owner's own, by name), a page, a report or workflow, a document: `query`, the words that name it ("sound", "signature", "second outlook"). It returns the best candidates with their links: link the one that fits, [its name](its link), and it opens.

- `query`

<p class="runs">Runs at once and changes nothing.</p>

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

### `asks.list`

What the owner asked you to do (the work they handed over in this chat, on the phone or with New) and where each stands. YOUR OPEN ASKS in the turn already shows the newest.

- `status` - open (the default) | all
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

### `missed.check`

Whether the owner missed anything: asks nobody answered, people who have not answered the owner, anything marked urgent, and every place that could not be checked - with the answer written out. Use it for "did I miss anything", "anything slip", "am I behind on anything"

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

### `app.health`

Why a part of Taskuary itself is not working, read now - the connection, the WhatsApp bridge asked directly, its log, the last sync and error - and the simple repair it has, if any.

- `name` (optional) - the connection (whatsapp, telegram, outlook...), or none for everything failing

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

