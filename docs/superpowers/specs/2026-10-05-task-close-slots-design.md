# A task says what closes it - output slots

2026-10-05. First of two specs; the second is the assistant remembering what it was asked and bringing it
back by itself (reply to the door that asked, "tell me when it's finished", wake-ups).

## The problem

A task has exactly one way to end, and it is implied by where it came from: a mail is closed by the reply
to its sender, a pull request by merging it, an issue by closing it, a report by its findings. An ask
whose result is several messages to several people has nowhere to live:

- the agent's only door for an answer, `coder.agent_reply`, writes ONE review, addressed to the message
  the task came from - and refuses outright on work the owner typed ("there is no one to reply to");
- `store.pending_review` / `held_review` are `LIMIT 1`, and the task page shows the newest pending reply
  only (`taskLifecycle.pendingReplyReview`);
- sending any reply runs `proposals.closed_out` -> `concierge.close_task`, which marks every other pending
  review `superseded`. Four drafts: approving the first silently retires the other three.

The shape to support: "check the four tabs of the finance dashboard and draft an email to each owner" -
one ask, four addressed drafts, each approved on its own, the task closing when the last is sent.

## Decision

The close definition is data on the task, written when the task is made and editable later, as
**output slots** carried by the existing checklist. Nothing else about a task changes; a task without
slots behaves exactly as it does today.

### 1. Data - a slot is a checklist item

`task.Checklist` items are `{id, text, done}`. A slot adds two optional fields:

```json
{"id": "a1b2c3d4", "text": "Tell Paula where tab 1 stands", "done": false,
 "out": {"kind": "email", "to": "paula@northwind.example", "subject": ""}, "rid": 812}
```

- `out.kind` - from a closed list, `email` only in this spec. A new kind is a new entry, never a branch.
- `out.to` - an address, or the name as said until someone resolves it (the card shows `?` beside it).
  Never guessed into an address.
- `rid` - the review (draft) that fills the slot, once there is one.
- `done` - sent, or dropped by the owner.
- `set_task_checklist` / `merge_task_checklist` carry `out` and `rid` across an edit whose text is
  unchanged, the same way they already carry `done`. Plain items are untouched.

The implied close of the source stays implied: a mail task still owes its reply, a PR its merge. Slots are
ADDED to that, never a replacement (see Not in this spec).

### 2. Closing - one more guard in `closed_out`

`proposals.closed_out` already holds a task open while its playbook proposal waits ("whichever half lands
second closes the task, from every door"). Slots are the same pattern:

- `slots_open(store, tid)` - slot items not `done`.
- `closed_out`: with open slots the task stays open, audited `closed_out`, with one comment
  ("2 of 4 sent - the task closes when the rest are sent or dropped").
- Sending a slot's draft (`verdicts._settle_task_after_sent_reply`, matched by `rid`) ticks that slot,
  then runs the same check. The last one sent closes the task.
- Rejecting a slot's draft ticks the slot as dropped and runs the same check, like `_playbook_decided`.
- The owner's Done closes everything, as today (done ticks every box; pending drafts are superseded).
- `coder.finish` does NOT pass through `closed_out` when nobody is behind the task: it sets `done` directly
  (`'waiting' if (mid or due) else 'done'`), and `done` supersedes every pending draft. Open slots count
  like `due` there - the run ends `waiting`, never `done`. That one condition is the only change to `finish`.
- The checklist's non-owner cap (12 items) covers slots too - plenty for this shape; not raised.

### 3. Who writes slots

| door | change |
|---|---|
| triage, per message | the verdict gains `outputs: [{to, about}]` (nullable in `verdict_schema`, one line in `TASK_FIELDS`), answered only when the message asks the owner to send something to OTHER people. A reply to the sender stays implied and is never an output. `ingest` writes them as slot items beside the checklist it already writes. |
| the assistant, creating | the hand-made task reader (`triage.py` ~464, which already returns `summary` + `checklist` for typed work) also returns `outputs`; `concierge.handoff_task` writes them as slots. "Draft four emails to..." shows four slots on the card at once - a wrong count or recipient is fixed before work starts. |
| the assistant, editing | one new operation `task.checklist` (add, reword, remove an item or slot) in `operations.KINDS`, running the page's own `PUT /api/tasks/{id}/checklist` handler in `server._run_operation`. |
| the agent | `taskuary --draft --to X [--subject S] [--slot ID]` (+ `--draft-file`) and a `[[TASKUARY-DRAFT to=... subject=...]]` block in the general chat, both reaching a new `coder.agent_draft`: fills the slot named by id, else the open slot whose `to` matches, else ADDS a slot and says so in a comment. The draft is a pending `draft_reply` review with `Deliver {channel:'email', to, subject}`, `DraftBy agent:<name>`, `TaskId` set - the same row `outbox.compose` and `deliver_findings` already file, approved and sent by the same `verdicts.decide` -> `outbound.send_out`. `agent_reply` is unchanged. |

The kind list is validated in code; the model only picks from it (no word lists).

### 4. The task page

- Slots render as their own block under the checklist: recipient, a state chip (to draft / waits for
  your yes / sent / dropped), and that slot's draft in its own `ReviewDecision` (approve, edit, reject).
- "Approve all (N)" when two or more slot drafts wait - a loop over the existing approve call, no new
  endpoint.
- `pendingReplyReview` skips slot drafts, so a slot draft can never take the reply card's place.
- The work rail shows the task once, saying how many drafts wait ("4 drafts wait for your yes"), not one
  row per draft. How the rail picks these up is checked in the plan (`funnel.py` reads the newest review
  per message today).

## Not in this spec

- Triage REPLACING a source's default close ("forward to Erin instead of replying"). That is the step that
  moves `coder.finish`'s cascade into data; it is a follow-up, not needed for any shape above.
- Kinds beyond `email` (file, setting, wait_for).
- Remembering asks, reporting back to the door that asked, "tell me when it's finished", wake-ups - spec 2.
- A nudge to an agent that stopped with slots unfilled - spec 2 (it is part of "follow up").

## Testing

- `tests/test_close_slots.py`: four slots stay open through three sends and close on the fourth; a
  rejected slot counts as done; a task with a reply AND slots closes only when both are settled; a task
  with no slots closes on its reply exactly as before; the playbook guard still works beside it;
  `set_task_checklist` keeps `out`/`rid` across a rewording of another item.
- The agent door: fills by slot id, by recipient, adds an unmatched one; refuses an empty body.
- Triage: `outputs` parsed and validated (unknown kinds dropped, fyi never gets outputs); the triage
  evalset run before and after - no regression on intent.
- UI: `npm run lint:undef` + the esbuild gate; a demo-world shot of a four-slot task (invented people only).
- The whole suite from the repo root before any push.
