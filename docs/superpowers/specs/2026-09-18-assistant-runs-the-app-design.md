# The assistant runs the app, and the report does the thinking

2026-09-18

## The problem

Asked from WhatsApp to "run me the AR report", the assistant has no road. It has one look-up for
reports, which returns a run's words but not the id the rerun verb needs; it has no list of reports,
workflows, settings or connections in view at all; and when a run it queued lands, nothing tells the
chat that asked. Settings are reached through a regex table of a few phrases. Connections can be
created and nothing else. The phone pushes interruptions and nothing that finished.

The owner's words (2026-09-18): "I need the assistant to have full control and full context of the
app, update settings, walk through tasks, run reports, set up new reports, same for workflows." And,
sharpening it over the same conversation: the walk through the tasks is the core; deterministic
scripts for the common jobs and a general road for everything else; and the chat assistant stays
lightweight - "it should be the assistant that hands things off to other agents or marks things
read" - while "thinking of new ideas or new connectors should come from the assistant ideas in
reports, not from the actual assistant."

## The shape this takes

Nothing here is a new interaction model. Three pieces already exist and this makes each complete:

- **The registry.** `operations.KINDS` is what `server._run_operation` dispatches on, and
  `toolcatalog.py` generates the model's catalogue from it, so the catalogue cannot drift from what
  runs (PW-123/124). It has 26 operations and 3 look-ups today. Coverage grows; the mechanism does not.
- **The walk.** `concierge` takes you through the pile one item at a time; a stop's verbs are the
  registry's operations; a typed ask is answered beside the walk, and the walk keeps its place.
  The setup walk (`walk.py`) proved the rule: deterministic steps, the model only for anything off
  script.
- **The Assistant report.** `assistant.py` runs on a clock, thinks with whatever brain it is given,
  and posts ideas (asked, cold, follow-up, prep, promise) that enter the pile as rows. It is the one
  place in the product that is allowed to propose.

Two roads, one registry, one vocabulary:

**Scripts** are deterministic, need no model, and are the same every time: *walk me through my
tasks*, *walk me through setup*, *set up a report*, *connect a system*. Each has a fixed order of
stops and its own buttons, keeps its place, and works before an AI is connected. A script owns the
floor until it is done or left; a general ask typed during one is answered beside it and the script
resumes. Scripts never call the general road.

**The general road** is one small brain with the full catalogue and the app's facts. It takes
anything said in the owner's words, on the desktop or the phone, and answers with a call from the
registry. It can start a script by name. It never invents: it carries what the report proposed.

The chat assistant therefore stays what it is - the hands. It walks, hands off, marks read, closes,
answers the agent, opens the tab, runs the stop's verbs, and now also runs, edits and reads the
things the app is made of. Its turns stay quick and its model stays small. Anything that requires
thinking about what the owner *should* do lives in the report, arrives as a row, and is met in the
walk like every other row: taken or declined, the decline remembered.

## Facts: the app's state in view

The assistant knows the pile and almost nothing else. `concierge.facts()` grows a **state block**,
generated from the same sources the tabs read, never hand-written:

| Facts | Source |
|---|---|
| reports and workflows: title, schedule, last run and outcome, reach rule, `is_workflow` | `store.list_sources()` where Channel = report, `report_runs` |
| settings: every key with label, current value, type and options | the settings schema `aidefaults.SETTINGS` and the Settings page's config groups |
| connections: name, type, active, has secret, last poll and error | `store.list_connectors()` |
| agents and brains: profiles, which brain answers which job | `store.list_agents()`, the four brain settings |
| scripts: the deterministic flows by name | a static list, so the general road can offer them |

Look-ups grow to match, one per family, each taking a name OR an id and resolving names the way
`report.read` already does (case-insensitive containment on the title): `reports.list`,
`report.read`, `settings.list`, `setting.read`, `connections.list`, `connection.read`,
`agents.list`. A look-up that misses lists what exists, so a second try finds it.

The block is bounded: counts and names first, detail only for what the ask names. It rides in every
turn of the general road and in none of the scripts.

## Acts: the registry grows

New operations, each on the same road as the 26 that exist - the model names it, the app proposes
it, the tier decides whether it runs at once or asks, a receipt comes back.

| Operation | Target | Params | Tier |
|---|---|---|---|
| `report.run` | report by name or id | | run now, undo = nothing to undo; receipt when it lands |
| `report.edit` | report | `config` patch | run now with undo |
| `report.pause` / `report.resume` | report | | run now with undo |
| `report.delete` | report | | confirm first |
| `report.reach` | report | `reach`: every run / only when wrong / only when… | run now with undo |
| `setting.set` | setting key | `value`, validated against the schema | run now with undo |
| `connection.test` | connection | | run now |
| `connection.pause` / `connection.resume` | connection | | run now with undo |
| `connection.create` (exists) | type | `name`, never a secret | proposes; the secret is typed on the card |
| `script.start` | script name | | run now |

`report.rerun` becomes `report.run` with name resolution; the old kind stays as an alias for the
stop's chip. `switch_ask`'s regex table (`concierge.SWITCH_ASKS`) is deleted: a setting is named by
the model from the schema in the facts block, validated by code, and `propose_switch` keeps the
Review road for the tier that asks first.

### Tiers

- **Reads** run at once.
- **Undoable writes** run at once and the receipt carries the undo: "Auto-drafts off - *undo*".
  Running a report, changing a setting, pausing a report or connection.
- **Irreversible writes** confirm first, as proposals do today: deleting anything, sending to a
  person, spending money, stopping an agent mid-run.

Every write already lands in the `audit` table; the Settings page gains a "what the assistant
changed" list read from it, with the undo beside each row while it still applies.

### Results come back to whoever asked

A run started from a chat records the asking channel and chat on the run (`report_run.asked_from`).
When the run lands, `remote_assistant.send` delivers its summary there with "the whole report" as a
follow-up; on the desktop the pile row is the receipt, as now. A run that will take long says so in
the receipt at the moment it is queued ("running - it lands in about two minutes").

## Ideas: the report proposes

Two new idea kinds in `assistant.py`, both entering the pile through `funnel.from_forgotten` like
the five that exist, both judged by triage like every idea (PW-200), both declinable with the
decline remembered on the idea's key so it never comes back for the same thing.

**App health.** A report that failed its last three runs; a workflow that never ran since it was
saved; a connection whose last poll errored for a day; a brain setting left blank while work waits on
it; an agent stopped on a task for more than a day. One row each, the door is the tab that fixes it.

**Connect a system.** Evidence the app already holds: sender domains and system names across the
last thirty days of mail and chat; the systems triage learned from corrections (`routing_fact`
field `system`); systems named in SOUL.md; reports whose config points at a system with no
connection. Matched against the catalogue, one row per system, at most one new suggestion a day:
"Six threads this month were about ADP and nothing here reads it. Connect ADP?" Doors: *Connect*,
which opens the card; *Not for us*, remembered. Where the card is only planned, the row still lands,
worded as a vote for it, so declines and takes tell us what to build next.

This needs one structural change: the connector catalogue lives in `website/src/connectorCatalog.js`,
which the server cannot read. It moves to `taskuary/connectorcatalog.json` with, per card, `type`,
`title`, `desc`, `category`, `planned`, and a new `match`: domains and keywords. The Connections tab
reads it over `/api/connectors/catalog`; nothing visible changes.

## Talking to it from a chat

The chat is a doorway to the same assistant, not a second one. How it works today, and what each
channel needs:

**The mechanism (built, WhatsApp and Telegram).** On the connection card the owner picks the
assistant's chat: their own thread, and only that. `remote_assistant.own_thread` refuses a group
with people in it, so the assistant can never answer a question about the owner's mail in front of a
room. The connector's poll reads the chat like any other; a line the OWNER wrote in that one thread is
intercepted (`remote_assistant.intercept`) before triage ever sees it and becomes an assistant turn -
the same `concierge` turn the desktop makes, same walk, same verbs, same receipts. The answer goes
back with the channel's own sender (`messengers.wa_send`, `messengers.tg_send`), split on paragraph
boundaries so a long answer is several bubbles with the summary first. Numbered options ride under a
turn so "2" is an answer. The walk can be HANDED to a chat: the desktop tab locks behind it, the chat
says hello, interruptions are pushed there (`push_alerts`), and "take it back" returns it. One walk,
wherever it is.

**What this design adds to every doorway.**
- The welcome line names the scripts - *walk me through my tasks*, *set up a report*, *walk me through
  setup* - so the deterministic roads are discoverable by name, and the general road takes anything
  else in the owner's words.
- Receipts come back to the chat that asked: a run that landed, a change applied, an agent that
  finished. Today only interruptions are pushed.
- Facts answer directly: "what reports do we have", "is Teams connected", "what did the AR report say"
  are reads and never wait on a confirmation.
- The tiers hold on a phone exactly as on the desktop. A confirm-first act is a numbered yes/no, the
  way proposals already are; an undoable act carries "reply *undo*" for the length of the walk.

**Per channel.**

| Channel | Today | To become a doorway |
|---|---|---|
| WhatsApp | doorway, built (bridge + `wa_send`) | nothing new beyond the additions above |
| Telegram | doorway, built (`tg_send`) | nothing new |
| iMessage | read and send exist (`imessage.send_text`, macOS only) | the own-thread rule and `intercept` wired to its poll; a doorway only on a Mac that runs Taskuary |
| Teams | read only; writes go through the Review road as replies to people | a Graph chat-message send for the owner's own 1:1 with themselves, the own-thread rule, `intercept` on its poll. Tenant consent for chat write is the gate, as it was for mail |
| Slack, Discord | read only | the same three pieces, when wanted; not in this scope |

The rule for any new doorway is the one WhatsApp taught (2026-09-17): the assistant lives in exactly
one thread the owner alone can see, chosen on the card, and nothing said anywhere else reaches it.

**The morning line.** Today the chat speaks first only for a hand-off, a review ping, or a report
aimed at it - so a doorway nobody opens stays shut (the owner, 2026-09-18: "does WhatsApp surface the
option to click to get started once a day so you will interact with it"). Once a day, at the digest's
slot, the assistant's chat gets one line: what is waiting in a breath ("7 in the pipe · 2 on you")
and the scripts as numbered options, so one reply starts the walk there. Quiet when the pipe is
empty; never twice in a day (the digest's `once_per_day` rule); the Morning digest itself may be
delivered to the same chat, since delivery already takes a chat as a destination - the line is the
door, the digest is the reading. One switch under *Assistant on your phone*, on by default once a
chat is chosen. The options are always the same three - *walk me through my tasks*, *set up
Taskuary*, *set up a report* - and set-up never drops off the list once the checklist is done: "there
always is more to set up" (the owner, 2026-09-18), and the setup walk is the tour of the app too.
Picked from a chat with the checklist complete, it opens on what is connected - the Connections stop
first, as words: each live connection with its state, then what is planned - and offers the rest of
the walk from there ("or at least see my connectors").

Long results: the summary in the first bubble, the whole thing as a follow-up on request. Pictures
(a snapshot from the browser pane, a chart from a report) go as attachments where the channel allows
and as a link to the desktop where it does not.

## Guardrails that do not move

Nothing is sent to another person without the owner's yes. Secrets never pass through a chat. The
agent token reaches none of this - only the owner's assistant does. One vocabulary (`lanes.json`,
`PROPOSALS`, the catalogue's purpose lines) so the phone, the desktop and the receipts say the same
words. The chat assistant proposes nothing of its own.

## Testing

- `tests/test_zz_toolcatalog.py`: every new kind has a purpose line, a target and a tier; the
  catalogue is generated, never edited.
- `tests/test_chat_proposals.py`: each operation by name resolves its target, or lists what exists.
- `tests/test_assistant_ideas.py` (new): the two idea kinds fire on seeded evidence, not on noise; a
  decline is remembered; one connector suggestion a day.
- `tests/test_remote_assistant.py`: a run asked from a chat delivers its receipt to that chat; the
  welcome line names the scripts; a group with people in it is still refused.
- `website/test/connectorCatalog.test.mjs`: the tab renders the server's catalogue; every card has a
  category and a match list.
- A live proof on a scratch home, the way the pane and the walk were proved: from a phone, list the
  reports, run one, change a setting, set up a workflow, open a task and hand it off, and check every
  receipt lands where the ask came from.

## Order of work

1. **Facts pack** - the state block, the look-ups, the scripts named. The walk and the chat already
   improve; nothing writes yet. About a day.
   Landed 2026-09-18: 973a4c92 (settings schema to the server), a821c521 (appfacts), b7e9c8d2 (the
   look-ups), 8bd7e19d (the state block on the general road), 98192ce4 (bundle). Plan: docs/superpowers/plans/2026-09-18-assistant-facts-pack.md.
2. **Stop verbs and by-name acts** - the report, setting and connection operations, the tiers, the
   undo receipts, results back to the asking chat, the audit list. About four days.
   Landed 2026-09-18: 2b4ecb0b (the kinds, the tiers, the undo, results back to the asking chat, the
   audit list), 7339837c (tests re-pinned to the tiers). Plan: docs/superpowers/plans/2026-09-18-assistant-acts-pack.md.
   Left out on purpose: a connector's own switch (github use_as_tracker) is not a schema knob and is not reachable by setting.set.
3. **Ideas in the report** - app health, connect-a-system, the catalogue moved server-side, the
   remembered no. About three days.
   Landed 2026-09-18: 1d61fa6b (assistant.health_ideas / connect_ideas, taskuary/connectorcatalog.json read by
   the tab and the report, the doors on the idea card, the decline remembered by key).
4. **Doorways and the live proof** - the welcome line, receipts to the asking chat, and the proof
   run from a phone. About a day and a half. iMessage and Teams as doorways are their own packs
   after this, each about a day, when wanted.
   Landed 2026-09-18: 30665092 (the morning line, once a day, the three scripts numbered; a script named in
   words runs with no model), 296b4627 (bundle). The proof from a real phone is still to run on the owner's
   install; the unit tests cover the doorway end to end with a mocked sender.

Each pack lands on master on its own, with its tests, and the app is restarted once per pack.

## What this deliberately leaves out

- A tool map of the API. The 305 routes are not offered to the model; the registry is, because the
  registry is what carries approval, receipts and one vocabulary.
- A bigger brain for the chat. The chat stays quick; the report thinks.
- Autonomous proposals from the chat. If the chat seems to be "suggesting", it is reading a row the
  report wrote.
- Secrets over chat, and anything an agent token could use to act as the owner.
