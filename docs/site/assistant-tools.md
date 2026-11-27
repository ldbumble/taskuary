<!-- Written by `python -m taskuary.toolcatalog` from taskuary/toolcatalog.py - edit the catalogue, not this page. -->

What the Assistant is told about its tools. It gets the **summary** on every turn: the buckets, and
each tool's name and what it needs. It asks for the **detail** of a bucket (`tools.list`) or a tool
(`tools.describe`) only when a turn needs it. Everything it can change, it brings up for you to press:
the button that does it, lit, or the page that holds it. On a phone it asks yes or no.

## The summary, sent every turn

| Bucket | What it is for | Tools, and what each needs |
|---|---|---|
| **table** | decide about the item on the table | reply(text), approve, send_close, redraft(text), mine, regular_agent(text, new?), coding_agent(text, as?, new?), not_ours, not_ours_sender, block_sender, not_ours_kind, close, next, answer_agent(text), stop_agent, rerun, report_off, remember(text, subject, about?), setup(text), confirm, cancel, let_go, accept_invite, decline_invite, propose_time, find_time, prepare, elsewhere |
| **task** | change any task - the table's or one by ref | task.update(priority/title/assignee/due), task.set_kind(kind), task.set_repo(repo), task.check(item, done?, note?), task.checklist(add?, items?, emails?, drop?), task.watch(what?), task.comment(text), task.split(text), task.merge(into), task.reopen, task.not_a_task, task.complete(note?), task.defer(until), task.handoff(who, note?), task.clarify(text), task.share(who, about?), review.approve, review.reject |
| **agents** | a task's agent; where work belongs | dispatch.prepare(kind, instructions?), agent.continue, agent.answer(text), agent.tell(text), agent.stop, agents.stop(refs/all), routing.remember(field, value), task.ask_agent(who, text) |
| **new** | new work with no task yet | task.create_from_text(kind, text, channel?, to?), task.create_from_message(kind), meeting.new(who?, about?, when?, minutes?), task.setup(text) |
| **pipe** | the walk and sets of items, and filing mail | pipe.clear(select, scope?), pipe.defer(select, until), pipe.close(select), pipe.remove(select, learn?), pipe.block(select, how?), pipe.mine(select), review.each, button.light(button, ref?, note?), item.settle(verb), message.file, message.archive, preference.exclude_sender(scope), preference.sender_rule, message.retriage |
| **reports** | reports and workflows | report.create(config), report.run, report.rerun, report.pause, report.resume, report.route(line, how, to?), report.edit(config), report.delete, advisor.ideas |
| **app** | settings, connections, scripts, memory, rules, bell, Hub, Board, Search | setting.set(setting, value), connection.create(type), connection.test, connection.pause, connection.resume, app.repair(name, how), issue.draft(kind, trying, happened), script.start(name), memory.remember(note, subject, about?, signature?, doc?), memory.wrong(key, how?), people.relate(who), rule.change(about, how?), deleted.restore(what), hub.publish(title, body, topic?, kind?, why_earned?), hub.comment(post, text), hub.vote(post, up?), page.open(page, query?), problems.dismiss |
| **look** | look-ups - they run at once and change nothing | app.find, task.read, timeline.search, tasks.list, asks.list, message.read, sender.read, docs.search, agents.now, approvals.list, pipe.list, pipe.read, calendar.read, activity.list, errors.list, memory.about, memory.list, outputs.find, deleted.list, rules.list, missed.check, report.read, reports.list, settings.list, setting.read, connections.list, connection.read, app.health, agents.list, repos.list, tools.list, tools.describe, knowledge.search |

A task you name goes in `ref` ("TQ-0123"); otherwise the tool acts on what is on the table.

## Table

Decide about the item on the table.

### `reply`

The "Reply" button ("Draft reply" when nothing is drafted yet): ask the task's agent to write a reply to the sender. Its card waits for his Send; nothing is sent.

- `text` - the gist, in the owner's words, anyone to loop in named there

<p class="runs">At once - asks the task's agent, nothing sent.</p>

### `approve`

The "Send" button ("Approve" on an agent's proposal or a task's finish card): the owner's yes to what is drafted on the item: sends the reply as it stands - on a task's finish card it merges the pull request or closes the issue FIRST, then sends the reply; on an agent's proposal it runs that action and only that. It never closes the task - that is send_close, or close, the owner's own Mark done - and never continues an agent's session - that is agent.continue.

<p class="runs">Brings up its button for you to press.</p>

### `send_close`

The "Send and close" button ("Approve and close" on a task's finish card with its reply): the same send, then the task closes - unless an agent or anything else on it still waits.

<p class="runs">Brings up its button for you to press.</p>

### `redraft`

The "Redraft" button ("Draft with AI" when nothing is drafted yet): ask the task's agent to write the draft again.

- `text` - the change

<p class="runs">At once - asks the task's agent, nothing sent.</p>

### `mine`

The "Make it a task" button: make it a task on the owner's own list - no agent.

<p class="runs">Brings up its button for you to press.</p>

### `regular_agent`

The "Send to agent" button: send it to an agent that does not write code - it becomes a task of its own. Taskuary's own settings, connections and update are its own screens (app.find); a meeting is meeting.new.

- `text` - the job
- `new` (optional) - true when the job is NOT about the item on the table

<p class="runs">Brings up its button for you to press.</p>

### `coding_agent`

The "Send to coding agent" button: send it to a coding agent; without it, its card offers every repository to pick.

- `text` - what is wanted
- `as` (optional) - the repository (repos.list)
- `new` (optional) - true when the job is NOT about the item on the table

<p class="runs">Brings up its button for you to press.</p>

### `not_ours`

The "Not for me" button: file it, just this once - its card asks whether from now on, or as a rule.

<p class="runs">Brings up its button for you to press.</p>

### `not_ours_sender`

The "Ignore this sender" button: file mail like this from this sender from now on - their mail still arrives and stays readable, and another kind from them is still judged.

<p class="runs">Brings up its button for you to press.</p>

### `block_sender`

The "Block this sender" button: an exclusion rule in Settings: the sender never reaches triage again.

<p class="runs">Brings up its button for you to press.</p>

### `not_ours_kind`

The "No more ideas like this" button: an Advisor idea only: put it down AND no more ideas like it - the Advisor's next run reads that.

<p class="runs">Brings up its button for you to press.</p>

### `close`

The "Mark done" button: the task behind the item is finished.

<p class="runs">Brings up its button for you to press.</p>

### `next`

The "Next" button: move on to the next thing - this one is put down, still theirs, marked nothing (pipe.clear marks read) - "walk me through the reports" starts at that section's first row, as a click on its heading does.

- `section` - a rail heading (Tasks, Watching, For later, Reports, Advisor, FYI)

<p class="runs">At once.</p>

### `answer_agent`

The "Answer it" button: answer the agent waiting on the owner.

- `text`

<p class="runs">Brings up its button for you to press.</p>

### `stop_agent`

The "Stop and save" button: stop the agent working on the item now - on the desk the x on its running turn, at once; on a phone the yes-or-no that ends its session.

<p class="runs">Brings up its button for you to press.</p>

### `rerun`

The "Run it again" button: run the report on the table again.

<p class="runs">Brings up its button for you to press.</p>

### `report_off`

The "Pause this report" button: pause the report on the table - off its clock.

<p class="runs">Brings up its button for you to press.</p>

### `remember`

Keep a fact about how the owner works in their memory.

- `text` - , their words ("I don't care about the legacy export job any more" too)
- `subject`
- `about` (optional) - , as memory.remember's

<p class="runs">Brings up its button for you to press.</p>

### `setup`

Build a report, a skill (how one kind of recurring request is handled from now on), a connection to another system or an automation.

- `text` - the request

<p class="runs">Brings up its button for you to press.</p>

### `confirm`

The owner's yes to the card already waiting.

<p class="runs">At once.</p>

### `cancel`

The owner's no to it.

<p class="runs">At once.</p>

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

The "Propose a new time" button: ask the invite's agent to propose another time - its answer is a card for their Send.

<p class="runs">Brings up its button for you to press.</p>

### `find_time`

The "Find a time" button: ask the task's agent to find a time for the meeting a thread asks for - its invite is a card for their Send.

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

Change any task - the table's or one by ref.

### `task.update`

Change a task's priority, title, owner or due day. Any other value is refused with the allowed ones.

- `priority` - regular | important | urgent
- `title`
- `assignee` - exactly `owner` (the owner takes it) or `none` (nobody holds it)
- `due` - the day the work is due (2026-10-30, "friday", "2 weeks", or "none" to clear it)
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.set_kind`

Say who does a task - an agent kind starts that agent on it.

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

Watch it - a task that is someone else's to move but the owner wants kept open and followed ("watch this", "tell me when Paula answers"): it moves under Watching, still walked after Tasks, and goes back to Tasks when the thread moves or after 7 quiet days; nothing is sent.

- `what` (optional) - off stops it
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

Remind me: put an open task away until a day and bring it back then - calendar or not: the app picks the time, or says there is none to pick from, or "none" to bring it back now. "Remind me about <a task that exists>" - named by ref, sender or subject - is this.

- `until` - a date (2026-10-09), "2 weeks", "3 days", "monday", with the time they said kept ("tomorrow 9am", "friday 2pm"), "after_meetings" whenever they mean once the day's meetings or calls are over
- `ref` (optional) - the task (TQ-0123) when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.handoff`

Hand a task to a PERSON (send, forward or pass it on) - the task's agent writes the hand-off and raises it as its card for the owner's Send, nothing is sent from the chat.

- `who` - any email address, or the name of someone who has written here
- `note` (optional) - a line for them
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.clarify`

Prepare a question for the task's sender; it waits for the owner's yes, never sent from here.

- `text` - the question
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.share`

Email what a task's work found; the task's agent writes it and raises its card for the owner's yes, never sent.

- `who` - an address
- `about` (optional)
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `review.approve`

The owner's yes to what is drafted: sends the reply as it stands - and on a task's finish card merges the pull request (or closes the issue) FIRST, sending the reply only if that worked. The task stays open: task.complete (Mark done) is the close.

<p class="runs">Brings up its button for you to press.</p>

### `review.reject`

Reject the draft waiting on a task - nothing is sent, the task stays open. A REPLY draft is never rejected: Redraft (redraft) writes it again, Mark done (close) closes the task with nothing sent.

- `ref` (optional) - the task

<p class="runs">Brings up its button for you to press.</p>

## Agents

A task's agent; where work belongs.

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

Answer the agent that is waiting. With no agent on the task (TASK NOW says so) nobody hears it; agent.continue or dispatch.prepare starts one. An agent still WORKING, not asking, takes words as agent.tell.

- `text`
- `ref` (optional) - its task when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `agent.tell`

Tell the agent WORKING on a task something new, as the owner's next prompt ("tell the agent to use the main branch", "also check the March file"). It goes in when the agent stops at its prompt - never mid-step. With no agent at work nobody hears it.

- `text` - the words, as the owner would type them
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Runs at once and says what it changed.</p>

### `agent.stop`

Stop the agent working on a task now - the x on its running turn: the one on the table, or the task `ref` names. On the desk it stops at once and typing to it carries it on; on a phone it is the yes-or-no that ends its session. Several at once is agents.stop.

- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `agents.stop`

Stop a SET of agents at once. Each is its task's Stop and save: written up and saved, nothing thrown away, the task left open. One with no agent running is said, never pressed. Runs at once; the receipt lists every task as its link.

- `refs` - the TQ refs of the tasks they are on, as agents.now or pipe.read printed them
- `all` - true for every agent running ("stop all the agents")

<p class="runs">Runs at once and says what it changed.</p>

### `routing.remember`

Remember how work like this should be ROUTED next time. kind: coding (an agent in a checkout) | general (the assistant) | task (the owner, no agent). system: where the work actually lives when no repository here can touch it, named plainly ("ADP"). It teaches triage and moves nothing.

- `field` - kind | system
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

A new job with no message behind it. MAKING something - a picture, a flyer, a document, a spreadsheet - is a general agent's job. A job that REPEATS on a clock, or a report, is a general agent's too - it sets the routine up for their press. A task that already exists (a TQ ref, or a row on THE RAIL BY NAME) takes dispatch.prepare to start an agent, agent.continue for its own last session, and task.defer for "remind me about it"

- `kind` - todo (a to-do or reminder the owner does themselves, no agent) | general (a regular agent) | coding | send (a new message the owner starts, to someone - `channel`: email | whatsapp | telegram | teams | slack, the one they said; `to`: the name of the person, chat or group as they said it (never the channel word), or an address; drafted in their voice for their Send, never sent from here) | goal (an outcome with a date, its steps tasks) | dashboard (a page of numbers kept up to date)
- `text`
- `channel` (optional)
- `to` (optional)
- `title` - a short name for the job

<p class="runs">Brings up its button for you to press.</p>

### `task.create_from_message`

Hand this message to an agent or put it on the list.

- `kind` - coding | general | task

<p class="runs">Brings up its button for you to press.</p>

### `meeting.new`

Set up a meeting or call ("a meeting with Gail about the budget friday") - 15, 30, 45 or 60 ("an hour" is 60) - else 30, `ref` optional: the task it is about (TQ-0123) when it is not the one on the table. On a task whose thread asks for a time it lights that task's Find a time; with none it brings up New → Meeting filled in, whose Find times reads the calendars; with no calendar, the card that connects one. Nothing goes out before the owner's Send. Never an agent's job.

- `who` (optional) - the names or addresses it is with
- `about` (optional) - its subject
- `when` (optional) - the day they said as YYYY-MM-DD (a weekday they name - "Thursday" - is its next date), or this_week / next_week
- `minutes` (optional) - the length they said
- `ref` (optional) - the task (TQ-0123), when it is not the one on the table

<p class="runs">Brings up its button for you to press.</p>

### `task.setup`

Open a walk-through with the assistant, for a set-up that needs digging first.

- `text`
- `title` - a few words naming the job for the task list

<p class="runs">Brings up its button for you to press.</p>

## Pipe

The walk and sets of items, and filing mail.

### `pipe.clear`

Clear a SET of items from the pipe at once - takes `select` (below); read, never deleted. "Clear all the FYI" and "mark the FYI read" - one FYI on the table or many - are this with kind: fyi. Their words naming the set are the press: it is marked read at once and the count said. It only marks read - "dismiss them", "get rid of them" is pipe.remove; "from now on" is preference.exclude_sender or preference.sender_rule. Rows already filed as not ours (pipe.remove, Not ours) are off the rail: "those should be read, not Not ours" is this with `keys` - their m-numbers, as the Not ours receipt listed them - and each one's Not ours is taken back (nothing taught from it) and it is marked read.

- `select` - below
- `scope` (optional) - all (the default - every one waiting that `select` matches, the batch on the table and every one after it: "all the FYI", "mark every FYI read", "ignore all the FYI") | table (only those on the table: "mark these read", "these four")
- `keys`

<p class="runs">Runs at once and says what it changed.</p>

### `pipe.defer`

Put a SET away until a day. Runs at once and the count is said.

- `select` - below
- `until` - (as task.defer takes it): "snooze everything from Gail until Monday" is select sender: Gail

<p class="runs">Runs at once and says what it changed.</p>

### `pipe.close`

Close a SET at once. "Close all the tasks from Priya" is select sender: Priya. Runs at once and the count is said.

- `select` - (below): each task in it is marked done, each notice read

<p class="runs">Runs at once and says what it changed.</p>

### `pipe.remove`

Not for me for a SET at once - "dismiss the spam", "get rid of these newsletters" - triage learns from each; otherwise it teaches nothing. Never touches work waiting on the owner, an agent at work, a draft waiting for its Send or a goal - those are left and said. Runs at once; the receipt lists every row as its link.

- `select` - (below; `keys`: the rows you judged, from pipe.read): each mail is filed, each task removed (Not for me), nothing deleted
- `learn` (optional) - true (the owner's "from now on")

<p class="runs">Runs at once and says what it changed.</p>

### `pipe.block`

Stop a SET's senders for good ("and stop them", "block them", "unsubscribe me")

- `select` - as pipe.remove takes it
- `how` (optional) - rule (the default: an exclusion rule per sender in Settings, their mail never reaches triage again) | unsubscribe (a mailing list: its Unsubscribe comes up lit, one list at a time - the owner presses it)

<p class="runs">Runs at once and says what it changed.</p>

### `pipe.mine`

Make it a task for a SET of mail; each becomes a task of the owner's, no agent. A row already a task is left as it is.

- `select`

<p class="runs">Runs at once and says what it changed.</p>

### `review.each`

"approve all the drafts": brings the next draft waiting for a Send up with its Send lit, and says how many are left - each one still goes only by its own press; CALL it again for the one after.

<p class="runs">Brings up its button for you to press.</p>

### `button.light`

Light any button a row draws, by its name. A put-down (close, close_note with its note, remove, not_ours) is pressed.

- `button` - the verb (THE BUTTONS BY NAME, or a row's own: review_changes, attach, pick_repo, change_kind...)
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

Teach triage to file this kind of mail from this sender, or this subject, from now on - their mail still arrives (`scope`: sender | subject)

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
- `to` (optional) - send or alert: who gets it - an address, or a name as the owner said it
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

### `advisor.ideas`

The Advisor's pass for ideas for the owner's job, run now instead of waiting for its day - "look for ideas for my job now", "run the advisor ideas". It starts at once and says here how many ideas it raised, under Advisor. With two of its ideas already waiting, or no AI connected, nothing starts and the line says why.

<p class="runs">Runs at once and says what it changed.</p>

## App

Settings, connections, scripts, memory, rules, bell, Hub, Board, Search.

### `setting.set`

Change one setting; the schema says what it takes.

- `setting` - its key, or `label`: part of its name
- `value`

<p class="runs">Brings up its button for you to press.</p>

### `connection.create`

Bring up a connector card to connect it; a second one of a kind opens with its Add another. An email account is a mailbox: gmail, outlook, else imap (Zoho Mail, Yahoo, a domain address) - never another product of the same company. Never carrying a secret: the owner gives it on the card. A system the catalogue has no card for is a feature request: issue.draft.

- `type` - the catalogue type or title (linkedin, slack, "QuickBooks Online")
- `name` (optional)

<p class="runs">Brings up its button for you to press.</p>

### `connection.test`

Test a connection now; it answers with what the connection said.

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

Run the simple repair app.health named for a part of Taskuary, then read it again - and a sync the owner asks for now ("sync my work mail now") is this with how: sync.

- `name` - the connection
- `how` - restart_bridge (the WhatsApp bridge this computer runs), sync or test, as app.health said

<p class="runs">Runs at once and says what it changed.</p>

### `issue.draft`

Draft a bug report or a feature request for Taskuary's own public tracker, when the owner says Taskuary ITSELF did something wrong or wishes it could do something it cannot - never about their work, their mail or a person. It is scrubbed and comes up under your answer for them to read, edit and submit on GitHub themselves - nothing is filed from here.

- `kind` - bug or feature
- `trying` - what they were trying to do in the app, in general words with no names, mail, companies or task titles
- `happened` - what went wrong (a bug) or what would help (a feature), the same way

<p class="runs">Drafts it for you to read, edit and submit on GitHub yourself - nothing is filed.</p>

### `script.start`

Start a script by its name: walk me through my tasks | set up a report.

- `name`

<p class="runs">Brings up its button for you to press.</p>

### `memory.remember`

Keep a fact or rule the owner tells you, at once; nothing of it shows on his screen - triage, every agent on a task it bears on, every draft and you read it from then on - the same subject as a line it corrects, which it then replaces (memory.about and memory.list show each line's subject) - it becomes their saved signature - their title, company, the systems they use ("I'm now the AP lead") - or counsel for how they want to be spoken to ("be shorter with me"): appended to SOUL.md or COUNSEL.md, never rewritten. Who reports to whom and who owns what is people.relate.

- `note` - it, in the owner's words ("Gail moved to Ops", "Ray handles payroll for me", "no meetings before 10", "write Mrs <surname> to women", "I don't care about the legacy export job any more")
- `subject` - , always: what it is about in a few words ("meeting hours", "who handles payroll", "Gail's role")
- `about` (optional) - the person it is about (an address or name), never the owner himself
- `signature` (optional) - true when the note IS how they sign, the block under every email ("Best,\nAlex")
- `doc` (optional) - soul for who the owner IS, lasting

<p class="runs">Runs at once and says what it changed.</p>

### `memory.wrong`

Take a line out of the memory, or confirm one. "forget that Ray does payroll", "that is wrong about Erin". A line the owner said himself takes forget or ended - a correction of it is memory.remember on its subject.

- `key` - from memory.about or memory.list
- `how` (optional) - wrong (a learned line that was never true: never learned again) | forget (out for now) | ended (it was true and stopped: kept as history) | keep (the owner said a learned line is right: used from then on)

<p class="runs">Runs at once and says what it changed.</p>

### `people.relate`

Who someone is to the owner, on their org chart. "Erin is my manager", "Ray owns payroll", "Gail reports to me" - triage and agents read the chart.

- `who` - a name or address
- `relation` - manager | report | none (none clears it)
- `owns` - areas they are responsible for ("payroll, benefits"), added
- `drops` - areas taken off
- `forget` - true takes them off the chart

<p class="runs">Runs at once and says what it changed.</p>

### `rule.change`

Change or delete one routing rule (its page: rules). Adding a rule for a sender is preference.sender_rule.

- `about` - words naming it, as rules.list says it (its sender, pattern or name)
- `how` (optional) - edit (the default) | remove

<p class="runs">Brings up its page, at the thing, for you to press.</p>

### `deleted.restore`

Bring back something removed in the last 30 days - a report, workflow, dashboard, routing rule or Hub post. A Hub post the vote took off is not here: it is on the Hub's own removed shelf, restored there.

- `what` - its title as deleted.list says it (or its kind, "hub post", when it is the only one)

<p class="runs">Brings up its page, at the thing, for you to press.</p>

### `hub.publish`

Save to the company Hub. The Hub holds reusable discoveries reached through real work and developed ideas with their reasons. At the desk the Hub comes up at its Write one with your words, theirs to post.

- `title` - one durable claim
- `body` - why it matters and what to do
- `topic` (optional)
- `kind` (optional) - new_idea | technical_solve | howto | gotcha | decision | system | people
- `why_earned` (optional)

<p class="runs">Brings up its button for you to press.</p>

### `hub.comment`

Add a comment to a Hub post. Others read the Hub: it goes only by the owner's press.

- `post` - its number (#12, as knowledge.search prints it)
- `text` - the comment in the owner's words

<p class="runs">Brings up its page, at the thing, for you to press.</p>

### `hub.vote`

Vote a Hub post up or down.

- `post` - its number
- `up` (optional) - false for down

<p class="runs">Brings up its page, at the thing, for you to press.</p>

### `page.open`

Bring up a page app.find cannot link. Finding something to answer from is timeline.search or tasks.list - this only shows the owner.

- `page` - board (every agent and task at work, as columns) | search (the search over everything - tasks, mail, chats, PRs, settings)
- `query` (optional) - the words to search for, with search

<p class="runs">Brings up its page, at the thing, for you to press.</p>

### `problems.dismiss`

Put down what the bell shows, as its Dismiss or Got it does; none when the bell holds one. It comes back if it fails again after working.

- `which` - words of the problem's title as errors.list prints it, or all

<p class="runs">Runs at once and says what it changed.</p>

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

Find messages anywhere in the history, however old - takes the same SELECT fields below, plus `limit`; here `contains` matches the subject, the sender AND the body, best match first. Returns m-numbers, refs, senders, subjects and dates - the owner's own sent mail too, marked "you (sent)": "did I answer it" is a search; open one with message.read or its task with task.read.

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

How Taskuary works and how to set it up (the help pages), and the owner's own docs - STYLE.md (how they write: greeting, sign-off, tone), TRIAGE.md, DIGEST.md (the morning brief) - each read whole as `section` "your doc <name>" (your doc style) - and what each release changed (help/whats-new). It answers "how do I", "what does X do", "what changed" and "why did it" about the app.

- `query` - the words
- `section` - one section read whole, as its contents list names it

<p class="runs">Runs at once and changes nothing.</p>

### `agents.now`

Every agent session running now - its task, which CLI, and whether it is working, idle, stuck or asking the owner something.

<p class="runs">Runs at once and changes nothing.</p>

### `approvals.list`

Everything waiting for the owner's yes: drafted replies and the actions agents proposed, with their tasks.

<p class="runs">Runs at once and changes nothing.</p>

### `pipe.list`

Everything waiting on the owner, lane by lane - replies, asks, approvals, stopped agents, reports: the whole work rail: "what's waiting", "what's left", "what do I have"

<p class="runs">Runs at once and changes nothing.</p>

### `pipe.read`

Every row on the work rail WITH WHAT IT SAYS - sender, subject, lane, age and the sender's own words (quoted history cut) - in one call, however many rows - "summarize my FYI", "what's in reports", "anything from Erin on the rail"

- `section` - task | later | reports | ideas | fyi (or a lane; none for all)
- `who` - a sender

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

What is failing and what failed: the bell (dismissed ones marked), failed agent runs, report runs, drafts, triage and actions over `days` (3 by default), and the last errors in the log - "what broke", "why did X not happen", "is anything wrong"

- `days` - 3 by default

<p class="runs">Runs at once and changes nothing.</p>

### `memory.about`

Who someone is to the owner: every line the memory holds about them, with its key, and what the org chart says - "who's Gail to me", "what do you know about Ray"; its keys are what memory.remember corrects and memory.wrong takes out.

- `who` - a name or address

<p class="runs">Runs at once and changes nothing.</p>

### `memory.list`

Everything kept about the owner: what they said (each line with its key and subject), the facts, what was learned from what they did - confirmed, or still waiting on their word. "what do you remember", "what do you know about me"

- `about` - words to narrow it (a sender, a topic)

<p class="runs">Runs at once and changes nothing.</p>

### `outputs.find`

The files agents made on tasks - workbooks, PDFs, documents, charts, pages - each once, its newest version, with its task and the link that downloads it.

- `query` - words of the task or the file ("vendor pricing")
- `kind` (optional) - xlsx | pdf | doc | deck | csv | picture | page
- `ref` (optional) - one task

<p class="runs">Runs at once and changes nothing.</p>

### `deleted.list`

What was removed in the last 30 days and can still come back - reports, workflows, dashboards, rules and Hub posts the owner removed (one the vote took off waits on the Hub's own removed shelf)

<p class="runs">Runs at once and changes nothing.</p>

### `rules.list`

The standing filters on the owner's mail - queue mutes set with a reason, and the policy rules (skip, ignore, escalate...) that decide before any model reads it - "why did I never see X", "what am I filtering"

- `about` - words to narrow it

<p class="runs">Runs at once and changes nothing.</p>

### `missed.check`

Whether the owner missed anything: asks nobody answered, people who have not answered the owner, anything marked urgent, and every place that could not be checked - with the answer written out. "did I miss anything", "anything slip", "am I behind on anything"

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

Why a part of Taskuary itself is not working, read now - the connection, the WhatsApp bridge asked directly, its log, the last sync and error - and the simple repair it has, if any - whether it is switched on under Chats, and where its messages went.

- `name` (optional) - the connection (whatsapp, telegram, outlook...), claude or codex for a slow agent start (is its agent connector installed), or none for everything failing
- `chat` (optional) - one WhatsApp chat or group by its name

<p class="runs">Runs at once and changes nothing.</p>

### `agents.list`

The agents, and which brain answers which job.

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

What the company knows - the Hub, the indexed documents and the facts the owner asked to keep - a person, a site, a policy, a system or how something is done here.

- `query` - the words to look for

<p class="runs">Runs at once and changes nothing.</p>

