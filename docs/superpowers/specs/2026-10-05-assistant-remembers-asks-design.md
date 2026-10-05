# The assistant remembers what you asked - and says when it moves

2026-10-05. Second of two specs; the first gave a task its close definition (output slots,
`2026-10-05-task-close-slots-design.md`). This one makes the assistant remember the work you handed it and bring it
back to you by itself - without a memory system, a new item type, or a single extra model call.

## The problem

The assistant is deliberately light: it hands work off to tasks and keeps nothing of its own. So it forgets.

- It cannot answer "what did I ask you?" or "where's the tab check?" without you naming the task.
- "Add Omar to that" has no "that".
- Finished work is silent: `funnel.announce` stopped writing `done` notices, and the phone hears only during a
  handed-over walk (`remote_assistant.push_alerts`). Work you started from WhatsApp never comes back to WhatsApp unless
  it was a report rerun (`server._rerun_report`, the one road that already reports back to the chat that asked).

## Decisions (the owner, 2026-10-05)

- **An ask is a task.** No new item. The task is marked as yours and where you asked; nothing else is stored.
- **What counts:** work you typed - in the Assistant chat, on WhatsApp/Telegram, or a task you made with New - once an
  agent works it. A to-do you do yourself has nothing to report. Mail-born work does not count (triage started it).
- **Where it reports:** the phone only when you asked from the phone or WhatsApp mode (the handed-over walk) is on;
  otherwise the desktop Assistant chat.
- **The rail is unchanged.** An asked task follows every task's rule - on the rail until seen, done included. The
  report-back line is an extra word at the right door, not a rail row.
- **It reports, never proposes.** "Paula hasn't answered, nudge her?" is judgement; it belongs to the Advisor (the
  Assistant report), later, using asks as evidence. The Advisor skips threads already tied to an open ask.
- **Lightweight is the constraint:** zero extra model calls; a few hundred prompt characters; event-driven, not polled.

## Design

### 1. The mark - `task.AskedVia`

One nullable column. Written once, at creation:

| door | value | where |
|---|---|---|
| Assistant chat (desktop) | `desktop` | `concierge.setup_task` (every chat hand-off lands there) |
| WhatsApp / Telegram turn | `whatsapp:<chat>` / `telegram:<chat>` | same call; the door is `remote_assistant.asking()` - already set for the turn |
| New (the task page) | `desktop` | `POST /api/tasks` |

`asks.of(task)` = the door, or None. Nothing else marks a task; nothing un-marks one.

### 2. Where an ask stands - `asks.state(store, tid) -> (phase, sentence)`

Derived fresh from what the task page already knows; never stored, so never stale:

| phase | from | sentence (examples) |
|---|---|---|
| `idle` | no agent has touched it | - (a to-do: nothing to say) |
| `working` | live session or running run | "the agent is on it" |
| `needs_you` | agent asking/parked/approval (workerstate), a pending draft, slot or close-out | "2 of 4 emails drafted, waiting on your yes" |
| `stuck` | stalled, failed run, browser that never opened | "stopped - it needs your login" |
| `done` | task closed | "done" + the agent's own summary (`coder.agent_found`) |

Wording comes from the existing one-sentence-per-state source (`workerstate.says`, `lanes.json`) and the slot counts
(`slots.open_`/`all_`), so chat, phone and rail say the same thing.

### 3. The assistant knows your asks - light always, deep on demand

- **A block in every Assistant turn, on any brain** (`asks.block(store)`), at most 6 lines, about 400 characters:
  ```
  YOUR OPEN ASKS
  - TQ-0812 Check the four tabs (2h ago, WhatsApp) - 2 of 4 emails drafted, waiting on your yes
  - TQ-0809 Research vendor pricing (yesterday) - the agent is on it
  ```
  Open asks newest first, plus finished ones not yet seen. Enough for "where's the tab check?" and for "add Omar to
  that" to land on TQ-0812 through the existing `task.*` operations.
- **A look-up, `asks.list`,** beside `tasks.list`/`sender.read` in `lookups.READ` and `toolcatalog`: every ask, any
  age, with phase - "what did I ask you last week?". Costs nothing unless called.

An ask leaves the block when it is `done`, has been told, and has been seen (the rail's own seen mark).

### 4. Saying it moved - event-driven, durable

- **Trigger:** `store._poke('task-changed', task_id=...)` and `workerstate.record` (the agent hooks) put the task id
  on a small debounced queue (2 s) - only if the task has `AskedVia`. One worker drains it. No poll on the hot path.
- **A safety sweep** every 5 minutes over open asks only, for anything an event missed (an agent going quiet).
- **The check:** `phase = asks.state(...)`; compare with the last phase told, kept as `funnel_state` key `ask:<tid>`
  (survives restarts - unlike `announce`, which forgets on restart). Speak on a change INTO `needs_you`, `stuck` or
  `done`; record the new phase either way. `working` and `idle` are never said.
- **The door:** `whatsapp:<chat>` asks, or any ask while the walk is handed to the phone, go to that chat through
  `remote_assistant.send` - only when `quiet()` (the 90 s gap; never between a card and its answer), else the next
  event or sweep tries again. Everything else is one line in the desktop Assistant chat (`concierge.record` on the dock
  task) carrying the TQ link.
- **The line is a template:** `TQ-0812 Check the four tabs - 4 emails drafted, waiting on your yes.` /
  `TQ-0809 Research vendor pricing - done: <agent summary>.` No model.

### 5. Finding an address - recipients, not just senders

`sender.read` resolves a name only among people who wrote in (`store.senders_like`). One shared resolver,
`people.resolve(store, name) -> {'address'} | {'candidates': [...]} | {}`, searches BOTH the people who wrote in and the
people the owner wrote to or copied (To/Cc of the owner's sent mail - the Sent folder is already ingested), ranked by
how recently and how often.

It is used wherever a name has to become an address, so "send an email to Gail" just works:
- `sender.read` (the assistant's look-up) - finds people you only ever wrote to.
- `slots.add` / `slots.draft` - a slot named "Gail Moreno" takes her address when exactly ONE person in your own mail
  matches; with several, the slot keeps the name and the card lists the candidates to pick from; with none, it keeps
  the `?`. A unique match in the owner's own correspondence is not a guess; anything less is never filled in silently.
- the hand-off brief - the agent is told the resolved addresses, so it does not have to hunt for them.

The company directory (Graph People/Contacts) needs a tenant consent and is a later, separate step.

## Not in this spec

- Proactive chasing / suggestions (the Advisor's job, later).
- Wake-ups ("remind me Friday") - an ask with `RemindAt` would ride the same check as a `due` phase; later.
- "Tell me when it's finished" about a mail-born task - setting `AskedVia` by a chat sentence; later.
- Directory lookups behind Graph consent.

## Testing

- `tests/test_asks.py`: the mark at each door (chat, phone turn via `asking()`, New); `asks.state` for each phase from
  real store rows (a slot task, a parked agent via workerstate, a closed task); the block's cap, order and aging; a
  phase change speaks once and only into needs_you/stuck/done; restart (fresh process state) does not repeat a told
  phase; the door rules (asked on phone → phone; desktop ask during a handed walk → phone; else desktop chat); the phone
  waits for `quiet()`; a mail-born task never speaks; a to-do with no agent never speaks.
- `people.resolve`: a name only the owner wrote to resolves; a unique match fills a slot; two matches keep the name
  and list both; no match keeps `?`; `sender.read` finds a person the owner only wrote to.
- Prompt size: the block stays under 600 characters with 20 open asks.
- Whole suite before any push.
