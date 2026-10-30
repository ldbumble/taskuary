# The walk has one owner - design

Date: 2026-10-30. Status: design, not built. Rules approved by the owner on 2026-10-30 (final).

## 1. Why

Next, Back and every close decide "what is on the table now" in at least five places that disagree:

| where | what it holds |
|---|---|
| server settings | `walk_place` (funnel.mark_place / walk_place), `walk_started_at` (processing_unread.WALK_KEY), `assistant_current:<dock>` (concierge.set_current) |
| server per-row marks | funnel_state `surfaced` + `Until` (the put-down / RETURN_MINUTES clock), receipts (`read`), `put_down`, `passed`, `back`, `actionable` (processing_unread.card_for) |
| server pickers | funnel_selection `_eligible` / `below` / `first_at_start`, funnel.next_item, funnel.section_next, concierge.surface / move_on / prepare_next, remote_assistant._move_on + doorway_browse.hold |
| the page | AssistantView `leftRef`, `downRef`, `bounced` (landed's bounce), `drawNextEarly` / `earlyRef` / `carryRef` / `adoptRef` / `movedOnRef`, `aheadRef` / `drawAhead`, `preparedRef`, `sectionRef`, `lastReportRef`, `walkAtRef`; funnelPile `rowAbove` / `backFrom` / `sectionNext` |
| one road per button | canvas `actions.next` / `advance` / `settleDone` / `done` / `putDown` / `pickUp`; TaskPage `finish` / `closedHere` / `sent`; ReviewDecision's closing Send; Remind me; Not a task; the agent's own close (selfclose) |

Each disagreement is a bug the owner has hit. Three from today alone:

1. **Next after a Send skipped a task.** The page had that task in `leftRef` from earlier in the same walk. The server offered it, and `landed` put it down unseen and asked again (`bounced`).
2. **Back onto an FYI batch read it.** `surface` settled the batch's members `surfaced` as it put them up. Fixed in e1c3ef16a by passing `read=False`, but the road that could read is still there.
3. **A walk opened out of order walked down past the rows above it.** `below()` measures from `walk_place`, and `first_at_start` lifts "on you" rows. Rows above where the owner clicked were never reached, and only the end-of-walk Opens mentioned them.

The fix is structural. **One server module owns the walk's state and rules.** The page sends an action, draws what comes back, and remembers only which row is on its table.

## 2. The rules (owner-approved 2026-10-30, final)

1. **The rail order is fixed.** Tasks, then Reports, then FYI, each oldest first by arrival (`funnel.order_key`, `funnel.arrived`). Rows never move.
2. **Next is the row directly below the one on screen.** That includes a row the owner clicked anywhere on the rail.
3. **Back is the row directly above the one on screen,** even if the walk did not start at the top. It is greyed out at the top. Back never reads or passes anything.
4. **Next on a task leaves the task on the rail.** Next on a report, an FYI (single or batch) or an agent-finished task reads it, and it leaves the rail. Opening, clicking or looking never reads.
5. **These close the row and move on to the row that was below it, in one step:** Mark done, Close with a note, a Send that closes the task, Remind me, Not a task.
6. **Never skip.** Next is always the row directly below. There is no hidden "passed" state for tasks and no "seen in this walk" skipping. Rows leave the rail only by rule 4 or 5, or by being closed somewhere else.
7. **The next item draws at once.** Prepared-next / draw-ahead may stay only if it asks the same module. Dots show until the item lands. The canvas is never blank and the owner never presses twice.

**Walk start** (the button, words asking for it, or a new chat) is the TOP of the rail.

### 2.1 Rulings these supersede

These are recorded in docstrings and memory. Each is removed, not kept beside the new rules.

| ruling (date, where) | what it said | replaced by |
|---|---|---|
| Next is seen in this walk (2026-10-21; `processing_unread.this_walk`, `WALK_KEY`, `funnel.new_walk`, the page's `leftRef` "next-is-seen-in-this-walk") | an open task passed with Next is skipped for the rest of this walk | rule 6. Nothing about a task changes on Next. |
| Passed band and the return clock (2026-09-23, R3/R6 2026-09-25; `RETURN_MINUTES = 180`, `settle(put_down=True)` writing `Until`, `card['put_down']`, `passed`, `back_at` for put-down rows) | Next puts work "in Passed" and the quiet hours bring it back | rule 4 / 6. A task stays in its place under Tasks. A read row leaves. No clock. |
| What waits on you leads the walk (2026-09-10, 2026-10-14; `funnel.leads`, `funnel_selection.first_at_start`) | the walk starts on the first on-you row, not the top | walk start is the top. |
| Shown-but-not-read marks on approve / blocked / queued / stopped / saved / working (2026-09-14, 09-18, 10-21; processing_unread `shown`) | the shown mark keeps Next from bouncing back to a waving agent | rule 6. Next measures from a place, so it can never bounce. |
| A new walk raises waiting agents again (2026-09-03, R11 2026-09-25; `funnel.reset_walk`'s marks clearing) | clears `surfaced` marks so blocked rows return | not needed for the walk. `reset_walk` keeps only alert/notice acks. |
| One rule for what is on the table (2026-10-25; `leftRef` / `downRef` / `isLeft` / `bounced`) | the page refuses to redraw an item it left | the server never answers with a row that is not the one directly below or above. |
| Back from the first FYI goes to the last report read (trust audit F1, 2026-10-28; `funnelPile.backFrom`, `lastReportRef`) | Back reaches a report that Next read off the rail | rule 3: the row directly above on the rail. Owner to confirm (Q2). |
| Section walks keep a `seen` set (2026-09-29; `funnel.section_next`, `funnelPile.sectionNext`, `doorway_browse.hold`) | Next stays inside a clicked section, then "X done." | a heading click opens that section's first row, and Next walks down the line from there (rule 2). |
| Next on a meeting holds it until it starts (2026-09-28; `funnel.settle`'s `meeting:` branch) | Next on a meeting writes `later` until its start | owner to decide (Q3). The default below treats a due meeting as a Tasks row. |
| A closed Current is cleared (PW-162, `concierge.restore_current` `over`) | a task closed under the table empties the table | the row on screen stays on screen, drawn closed. Next and Back measure from its last place. |

These stay as they are: the rail is fixed by arrival (2026-10-22), Next walks down (2026-10-22), urgent is walked in its place (2026-10-22), a task an agent is working is walked like any task (2026-10-21), shown is not acted on (2026-10-13), a Send keeps the item on the table unless it closes the task (2026-10-18, 2026-10-29), the "Next" / "Read" badge (2026-10-23), and Next on the Reports page reads the report open there (2026-10-30).

## 3. The one module: `taskuary/railwalk.py`

`taskuary/walk.py` is already taken by the scripted setup tour, so the new module gets its own name. It owns:

- **The line.** Which rows the walk stands on, in what order.
- **The place.** Where the walk stands now, kept even after that row has left the rail.
- **Effects.** What each action reads, puts down or closes, and nothing else does it for a walk move.
- **The answer.** Which row comes up next, built by one function for the prepared answer and the committed one alike.

`concierge` still builds the words, chips and card for a row (`present_turn`, carved out of `surface`). `operations` still runs the closes. `railwalk` decides *which row* and *which effect*, and calls them.

### 3.1 The line

```
line(pile) = [r for r in pile.items in funnel.order_key order
              if not r.settling            # still being triaged: not arrived in a section yet
              and level_of(r) != 'later']  # For later rows left the walk by Remind me (rule 5)
```

- **It is the rail's own drawing order,** minus For later and minus rows still settling. Sections are taken from lanes.json: Tasks, (For later), Reports, Advisor ideas, FYI.
- **Nothing else filters it.** There is no `actionable`, `put_down`, `surfaced`, `unread` or `not_yet` test, and no `exclude`. If the rail draws a row, the walk can stand on it.
- **One pile.** The line is read from the cached `funnel.pile` build (the same one `/api/funnel/pile` serves). It never triggers a second build.
- **A scoped walk** (`only`: mail, or a `view:` filter) is the same line filtered by that scope.

**Where a row sits on the line:** its `order_key`. For a row that is not on the rail, its place is the order_key it would have:

- a closed task opened by name is placed under Tasks by its arrival (`funnelPile.pulledRow` is the page's mirror; band 2, not deferred)
- a For later row clicked sits where the rail draws it
- the row on screen that has since left keeps the place stored in the walk state

### 3.2 FYI batches

The walk never puts a batch together any other way than this.

- **Next onto FYI:** the batch is the first FYI row directly below, plus the FYI rows that follow it, up to `fyi_batch_size(store)` rows in all. It never crosses out of the FYI section. Ideas are their own section and always walked alone (`batchable`).
- **Back onto FYI:** the batch is the FYI row directly above, plus up to `size - 1` FYI rows above that. This keeps Back-then-Next symmetric: Next from that batch lands on the first member of the batch you came back from.
- **Below a batch** is the row directly below its last member. **Above a batch** is the row directly above its first member.
- **A batch's place** is its last member's order_key for Next, and its first member's for Back. Both are stored.
- **A single FYI row** clicked on the rail is a single on the table. Next from it reads it, then brings the batch that starts at the row below.

### 3.3 State (persisted)

One setting, `rail_walk`, is written only by railwalk under its lock:

```json
{"v": 1,
 "on":      "processing:pi_..." | "fyis:a,b,c" | null,   // the row on screen; null = no row (walk start, or the end)
 "members": ["processing:pi_...", ...],                 // a batch's rows; [on] for a single
 "first":   [order_key of the first member],            // where Back measures from
 "last":    [order_key of the last member],             // where Next measures from
 "kind":    "stays" | "reads" | "none",                 // the row's effect class WHEN IT WAS PUT ON SCREEN (3.5)
 "ended":   false,                                       // Next ran off the bottom; `last` still says where
 "presses": {"<press id>": "<answer hash>", ...}         // the last 32, so a repeated press returns the same answer
}
```

**This replaces** `walk_place`, `walk_started_at` and `assistant_current:<dock>`. `concierge.current_key` / `set_current` / `restore_current` become thin readers of `rail_walk.on`.

**No other walk state anywhere.** In particular there are no funnel_state `surfaced` + `Until` marks written by a walk move. `funnel_state` keeps only the owner's real decisions: `done`, `later` (Remind me), `ack`, and the read receipts that make a read row leave the rail.

**One walk, not one per chat.** The desk and the phone walk the same line from the same place. The tab already follows the walk's Current on a hand-off (2026-10-23), so this matches. See Q5.

### 3.4 API

Every call takes the lock, reads the line from the cached pile, writes the state and any effects, and returns an **Answer**:

```
{item | None, say, chips, options,        # concierge.present_turn(item) - the same function the prepared answer uses
 walk: {on, members, above: key|None, ended},
 answer_hash, pile}                       # the rail as the move left it (design B), with the next prepared answer in it
```

| call | does |
|---|---|
| `start()` | Puts the TOP row of the line on screen (a batch if it is FYI). `ended = False`. Reads nothing. Used by the Walk button, words asking for a walk, and a new chat (`funnel.reset_walk` calls it instead of `new_walk`). |
| `next(from_key, press)` | `from_key` is the row the page has on screen; with none, the stored `on`. (1) Apply the **Next effect** of the row being left, by its stored `kind` (3.5). (2) Answer with the row directly below `from`'s place. A key that is no longer on the rail still resolves: through `last` when it is `on`, else by `item_for_key`'s place. At the bottom it answers `item=None, ended=True` and keeps `last`. With nothing below and already ended, it is a no-op that returns the same end answer and writes no new line. |
| `back(from_key, press)` | Answers with the row directly above `from`'s `first` place. Writes nothing but the walk state: no read, no mark, no badge. At the top it returns `above=None`, and the page has the button greyed already. |
| `open(key, press)` | A rail click, a name, a link, a section heading (its first row), the Board's open, a search hit. Puts that row on screen at its place. **Reads nothing** (rule 4; tasks: see Q1). Next and Back then measure from it. |
| `leave(key, how, press, note=None, until=None)` | Runs the act for `how` (3.6) through the existing operation, applies its effect, and **in the same call** answers with the row that was directly below `key`'s place. If the act did not close the row (a Send that kept the task open), it answers with the same row on screen, re-presented, and does not move. |
| `peek()` | Pure, with no writes. Returns `{below, above}` for the stored `on`: the Answer `next` would give (minus its effects) and the key `back` would bring. `/api/funnel/pile` carries it as `walk`. |

**Idempotent by construction.** `next(from=X)` is a function of X's place and the line. Pressing twice, or a retry after a timeout, returns the same row, and reading X again is a no-op. The press id only spares the second line in the chat.

This removes the need for `selection_revision` / `expected_next_key` / `NavigationStale` / `SelectionStale` / the 409 "list changed" retries (PW-050, PW-118). A press is bound to *the row the owner saw* (`from_key`), not to a captured pick that can go stale.

### 3.5 Effects per action per row kind

**Effect class** is taken from the row's section **at the moment it was put on screen**, and stored in `kind`:

- `stays` covers every row under **Tasks**: an open task, an urgent row, a task an agent is working, an agent waiting on you, a draft ready to send, a goal, a loose end, a slipped follow-up, an owed-reply row with no task behind it, a due meeting (default, Q3), and a closed task opened by name (`kind = none`, see below).
- `reads` covers every row under **Reports** (report, dashboard, a failed report, an agent-finished task `agentdone`), **Advisor ideas**, and **FYI** (a single, a batch, a thread row with its folded mails via `funnel.thread_of`).
- A row whose class changed while it was on screen keeps the class it was shown as. For example, a task whose agent closed it becomes an `agentdone` row in Reports. That conservative choice means Next never reads a result the owner did not see as a result.

| action | `stays` row (Tasks) | `reads` row (Reports / Ideas / FYI single / FYI batch) | closed task opened by name | For later row (clicked) |
|---|---|---|---|---|
| open / click / name / heading | no read, no mark | no read, no mark | no read | no read |
| Back | nothing written | nothing written; a batch's members stay unread | nothing | nothing |
| Next | nothing written but the "Next" badge (`concierge._stamp_next`); the row stays in its place | `funnel.settle(key, 'surfaced', read=True)` with **no `Until`** (every member, for a batch); it leaves the rail; badge "Read" / "All read" | nothing | nothing; it stays For later |
| All read, next (batch button) | - | the same as Next | - | - |
| Mark done | `task.complete` then settle `done`; leaves; move on | a report has no Mark done; an `agentdone` row: settle `done` | - (Reopen task only) | `task.complete`; leaves; move on |
| Close with a note | `task.complete` with the note; leaves; move on | - | - | as Mark done |
| Send that closes | the send has gone through first (ReviewDecision), then `concierge.close_after_send`. **Closed:** leaves; move on. **Kept open:** stays on screen folded "Sent", no move | - | - | - |
| Remind me | `task.defer` until the day; it goes to For later (off the line); move on | - | - | moves its day; stays For later; stays on screen |
| Not a task | `task.not_a_task`; leaves; move on | - | - | as Tasks |
| Not ours (message.file) | files the message; leaves; move on | an FYI's Not ours: files it; leaves; move on | - | - |
| Put it on my list (report or FYI to task) | - | the act runs; the new task appears under Tasks at its arrival; **the table keeps the new task, no move**; Next/Back measure from the report's stored place | - | - |
| Remove (delete task) | as Not a task (leaves; move on) | - | - | - |

**"Move on"** means the answer is `next`'s answer measured from the left row's `last` place. The left row is gone from the line, so this is exactly "the row that was below it".

**Closes made somewhere else** never move the table. This covers TaskPage in another tab, the Tasks list, the Board's Close agent, the agent's own `--done` (selfclose), a typed close on a row that is not on screen, and a bulk clear. Their effect is the act's own (the row leaves the rail). If that row was `on`, the screen keeps it, drawn as it now is (closed, or the agent's result). The owner's Next or Back then measures from its stored place. No auto-navigation (see memory: ask before changing interaction).

### 3.6 `how` values for `leave`

| how | the act it runs (unchanged code) |
|---|---|
| `done` | `operations` `task.complete` |
| `note` | `task.complete` with the note |
| `sent` | `concierge.close_after_send`, called after the send's own endpoint has succeeded |
| `remind` | `task.defer` / `/api/tasks/{id}/remind` with `until` |
| `not_task` | `task.not_a_task` |
| `not_ours` | `message.file` (`learn` as the card asked) |
| `removed` | the delete (recentlydeleted keeps it) |

Typed put-downs (`concierge._put_down`, `PUT_DOWN`) and the phone's settled acts (`remote_assistant._settled_the_table`) call `railwalk.leave` when their target is `on`. Otherwise they run the act alone.

## 4. What the page keeps, and what it calls

**The page keeps:** the Answer it is drawing, i.e. `on` (the row on its table) and the line it is filling in place. It also keeps the last `walk.below` / `walk.above` that came with the rail, for drawing at the press.

**It keeps nothing about the rules.** These are gone: `leftRef`, `downRef`, `isLeft`, `leave` / `unleave`, `bounced`, `walkAtRef` / `noteWalk`, `sectionRef` / `sectionNext`, `lastReportRef` / `backFrom` / `rowAbove`, `earlyRef` / `carryRef` / `adoptRef` / `movedOnRef` / `drawNextEarly`, `selectionRef` / `ensureNextSelection` / the stale-retry loop, and the walk-on parts of `advance` / `settleDone`.

| page event | call |
|---|---|
| Walk button, a new chat, the opener's Walk | `POST /api/walk/start` |
| Next (button, typed "next", phone tap) | `POST /api/walk/next {from_key, press}` |
| Back | `POST /api/walk/back {from_key, press}` |
| rail row, section heading, link, search, Board open, `#msg=` / `#task=` | `POST /api/walk/open {key, press}` |
| Mark done / Close with a note / Remind me / Not a task / Not ours / Remove on the row on screen | `POST /api/walk/leave {key, how, note?, until?, press}` |
| Send (ReviewDecision): its own send endpoint first; if `closes`, then | `POST /api/walk/leave {key, how: 'sent', press}` |
| the rail | `GET /api/funnel/pile` now carries `walk: {on, ended, below: Answer|null, above: key|null}` |

- **`/api/concierge/next`** and **`/api/concierge/stream` with `mode: 'next'`** stay as wrappers during the migration. With a key they call `open`; without one, `next`. The stream keeps its `done` / `pile` events.
- **TaskPage inside the canvas.** `CanvasItem` hands TaskPage an `onFinish` / `onReminded` / `onLeave` that calls `leave`. TaskPage outside the canvas (the Tasks tab) keeps its own `completeTask` and list movement. That list is not the walk.

### 4.1 Drawing at once (rule 7), the same answer twice

1. Every rail payload carries `walk.below`, which is `railwalk.peek()`: the full Answer `next` would give from the stored `on`, built by `concierge.present_turn`, with its `answer_hash`.
2. **At the press,** the page folds the card it leaves and draws `walk.below` in its place in the same frame. This is today's `drawAhead` with one source. Its `held` card waits for its first read exactly as now (PW-118 note: a card's first reads write).
3. **The committed Answer** fills that same line in place. Same hash: nothing is redrawn. Different hash (the list moved between peek and press): the line's id is kept and its content replaced. There is no blank frame, no second press, and no "the list changed".
4. **A `leave` press** draws `walk.below` too. For the row on screen, the row below it is exactly what `leave` answers when the act closes the row. If the act keeps the row (a Send kept open), the answer puts the same row back and the drawn-ahead line comes down, the same road as a failed press.
5. **Nothing prepared** (a cold rail, a rail row not yet read): the dots stand on the canvas from the press until the Answer lands. The folded card stays above them, and the canvas is never empty.
6. **A failed press** takes the drawn-ahead line down and unfolds the card it left. That is today's `unshow`, with nothing to "unleave".
7. **Back** has no prepared Answer. It draws the rail row for `walk.above` at the press (the row-click road: frame, title, the view's own loading state) and the Answer fills it.

## 5. Edge cases

| case | behaviour |
|---|---|
| **The row on screen leaves the rail.** Closed elsewhere, closed by its agent, removed, a Send closed it in another tab. | The screen keeps it, drawn as it is now. `next` measures from `last`, `back` from `first`. No read is applied for a row that is no longer there. If its agent closed it, the `agentdone` row in Reports is reached later in its own place (3.5: effect class as shown). |
| **A row arrives above the place.** For example a new task arrives while the walk is in Reports. | Next does not go back up to it. Back reaches it in its place. The next walk (top) includes it. |
| **A row arrives below the place.** | Next reaches it in order. |
| **A row on screen changes section.** Put it on my list, a report becoming a task. | The table shows the new row. The stored place is the old one, so Next continues in Reports. |
| **The bottom of the rail.** | `next` from the last row applies its effect and answers `item=None, ended=True`. **Desk:** today's end row is kept as is: the Walk again chip by the prompt, plus up to three Opens of rows still under Tasks above where the walk is. Back stays enabled (the row above `last`). **Phone:** "That's the bottom of the list." and Walk again. Next pressed again at the end is a no-op, unless a row has arrived below since. |
| **FYI batches.** | 3.2. Back onto a batch never reads it. Next from it reads every member. A member closed elsewhere while it is on screen is simply not read. |
| **The phone's Next** (remote_assistant) | `carry_out` / `_move_on` / `_ran` / section taps call `railwalk.next` / `leave` / `open`. `doorway_browse.hold` / `next_in` and the `seen` list go. A section pick is `open(first row of section)`. |
| **The Board** (BoardView) | Its open calls `open`. Its Close agent is a close somewhere else (above). It never moves the desk's table. |
| **Remind me's For later rows** | They leave the line. A For later row clicked is on screen at its drawn place. Next goes to the row below on the rail (the next For later row, then the first Report). Back goes to the row above (the previous For later row, then the last Task). Next from the last Task goes to the first Report, not into For later (Q4). |
| **A closed task opened by name** | On screen with Reopen only (`item_for_key`'s `closed`). Placed under Tasks by its arrival. Next goes to the row below that place, Back to the row above. Nothing is read. |
| **Urgent rows** | Walked in their place. Start is still the top. |
| **A meeting not yet due** | Drawn under Tasks, so it is on the line and walked in its place (never skip). Next leaves it (default Q3). It leaves the rail on its own after its grace minutes. |
| **A row still settling** (being triaged) | Not on the line. When triage lands it is an arrival (above or below). |
| **A new chat** | `start()`. The old `on` is forgotten. Read stays read. |
| **Two tabs / desk and phone** | One walk. Each surface sends its own `from_key`, so a press moves from the row that surface showed. The other surface follows `on` on its next rail read, as the tab follows Current today. |
| **A double press / retry** | The same `from_key` gives the same row. The press id dedupes the chat line. |
| **Reports page open over the table, Next** | `next(from=the report open on that page)`. It reads that report's rows (2026-10-30 ruling), then moves to the row below it. |

## 6. The table-driven test

### 6.1 The world

Both runners use the **demo world** (`taskuary --demo`, `taskuary/demo.py`), plus a small fixture `tests/walkworld.py` that adds whatever rows the demo lacks. Rows are named by symbol and resolved to keys **by their place on the rail**, so the table never names a real key. People and companies are invented (CLAUDE.md).

```
Tasks:      T1 (task, oldest)  T2 (urgent ask)  T3 (agent working)  T4 (draft ready, Erin Blake)  T5 (task)  M1 (meeting, due in 10 min)
For later:  L1 (reminded task)
Reports:    R1 (report)  R2 (agent-finished task)  R3 (dashboard)
Ideas:      I1 (Advisor idea)
FYI:        F1 .. F7   (fyi_batch set to 4 by the owner, so B1 = F1-F4, B2 = F5-F7)
Off rail:   C1 (closed task, arrived between T2 and T3)
```

**The file:** `tests/fixtures/walk_table.json`. Each case is

```json
{"id": "W04", "rule": [2], "steps": ["start", "open T4"], "action": "next",
 "expect": "T5", "read": [], "rail": {"has": ["T1","T2","T3","T4"], "not": []}, "back": true}
```

- `steps` are replayed to reach the starting state, using the same verbs as `action`: `start`, `open X`, `next`, `back`, `leave X how`, `send X closes|kept`, `arrive X after Y`, `close-elsewhere X`, `agent-closes X`, `new-chat`, `phone next`.
- `expect` is the row on screen afterwards: a symbol, a batch `F1-F4`, or `END`.
- `read` lists the rows that left the rail by being read. `rail.has` / `rail.not` are spot checks. `back` says whether Back is enabled.

| id | rule | from (steps) | action | expect on screen | read | rail after | Back |
|---|---|---|---|---|---|---|---|
| W01 | start | (new chat) | start | T1 | - | all | off |
| W02 | 2,4 | start | next | T2 | - | T1 stays | on |
| W03 | 2 | start | open T4 | T4 | - | all | on |
| W04 | 2 | start, open T4 | next | T5 | - | T1-T4 stay | on |
| W05 | 3 | start, open T4 | back | T3 | - | all | on |
| W06 | 3 | (new chat), open T3 | back | T2 | - | all | on |
| W07 | 3 | start | back | T1 (no-op; button greyed) | - | all | off |
| W08 | 1,6 | start, urgent T2 present | start | T1 (urgent walked in place) | - | all | off |
| W09 | 2,6 | start, open M1 | next | R1 (For later not walked) | - | L1 stays | on |
| W10 | 4 | open R1 | next | R2 | R1 | R1 gone | on |
| W11 | 4 | open R1, open R2 | - | R2 | - (opening never reads) | R1 stays | on |
| W12 | 3,4 | open R2 | back | R1 | - | R1 stays | on |
| W13 | 3,4 | open R2, back | next | R2 | R1 | R1 gone | on |
| W14 | 4 | open R2 | next | R3 | R2 (agent-finished) | R2 gone | on |
| W15 | 4 | open R3 | next | I1 | R3 (dashboard) | R3 gone | on |
| W16 | 4 | open I1 | next | F1-F4 | I1 | I1 gone | on |
| W17 | 4 | open I1, next | next | F5-F7 | F1-F4 | F1-F4 gone | on |
| W18 | 4 | open I1, next | leave F1-F4 all_read | F5-F7 | F1-F4 | F1-F4 gone | on |
| W19 | 3,4 | open I1, next | back | I1 | - | F1-F4 stay | on |
| W20 | 3,4 | open F5 | back | F1-F4 (batch ending at F4) | - | all FYI stay | on |
| W21 | 3,4 | open F5, back | next | F5-F7 | F1-F4 | F1-F4 gone | on |
| W22 | 2,4 | open F6 | next | F7 | F6 | F6 gone | on |
| W23 | 4 | open F5, next(→F5-F7) | next | END | F5-F7 | FYI F5-F7 gone; tasks stay | on |
| W24 | 6 | (W23), next | next | END (no-op, no new line) | - | unchanged | on |
| W25 | 2 | (W23), arrive F8 | next | F8 | - | F8 on | on |
| W26 | 5 | start, next(→T2) | leave T2 done | T3 | - | T2 gone | on |
| W27 | 5 | start, next | leave T2 note | T3 | - | T2 gone | on |
| W28 | 5 | open T4 | send T4 closes | T5 | - | T4 gone | on |
| W29 | 5 | open T4 (held agent step) | send T4 kept | T4 (folded "Sent") | - | T4 stays | on |
| W30 | 5 | start, next | leave T2 remind | T3 | - | T2 under For later | on |
| W31 | 5 | open T5 | leave T5 not_task | M1 | - | T5 gone | on |
| W32 | 5,7 | read R1-R3 and I1, close-elsewhere M1, open T5 | leave T5 not_task (last task) | F1-F4; dots, never blank, until it lands | - | T5 gone | on |
| W33 | 6 (bug 1) | start, next(→T2), open T1 | send T1 closes | T2 (not T3) | - | T1 gone | off |
| W34 | 3,4 (bug 2) | open F5, back(→F1-F4) | reload rail | F1-F4 still on screen | - | F1-F4 all still on rail, unread | on |
| W35 | 3,4 (bug 2) | open R3 | back, then reload rail | R2, R2 unread and on rail | - | R2 stays | on |
| W36 | 6 (bug 3) | (new chat), open T4 | next ×N to END | END; screen offers Walk + Open T1..T3 | reports/FYI as walked | T1-T3 still on rail | on |
| W37 | start (bug 3) | (W36) | start | T1 | - | - | off |
| W38 | edge | open T3, close-elsewhere T3 | next | T4 | - | T3 gone | on |
| W39 | edge | open T3, close-elsewhere T3 | back | T2 | - | - | on |
| W40 | edge | open T3, agent-closes T3 | next | T4 (agent result not read) | - | A3 in Reports | on |
| W41 | edge | open R2, arrive T6 | next | R3 | R2 | T6 under Tasks | on |
| W42 | edge | open R1, next(→R2), arrive T6, back(→M1: a meeting's arrival is its start, so it stays last in Tasks) | back | T6 | R1 (from the next) | - | on |
| W43 | edge | open T5, arrive T6 (newest, below T5) | next | T6 | - | - | on |
| W44 | edge | open C1 (by name) | next | T3 | - | C1 not on rail | on |
| W45 | edge | open C1 | back | T2 | - | - | on |
| W46 | edge (Q4) | open L1 | next | R1 | - | L1 stays | on |
| W47 | edge (Q4) | open L1 | back | M1 (last task) | - | - | on |
| W48 | start | heading "Reports" | next | R2 | R1 | - | on |
| W49 | edge | open R1 | leave R1 put_on_list | new task on screen; then next gives R2 | - | new T under Tasks | on |
| W50 | edge | start, next(→T2), new-chat | start | T1 | - | - | off |
| W51 | phone | phone start, phone next | - | T2 on phone; desk follows T2 | - | - | on |
| W52 | 7 | start (T2 prepared), close-elsewhere T2 | next | T3, drawn in place of the prepared T2; one press | - | - | on |
| W53 | 4 | open T3 (agent working) | next | T4 | - | T3 stays | on |
| W54 | edge | start | next ×2 same press id | T2 once, one chat line | - | - | on |
| W55 | 4 | Reports page open on R1 over T2 | next | row below T2 (T3) | R1 | R1 gone | on |

**Coverage:**

| rule / edge | cases |
|---|---|
| rule 1 | W08, W09 |
| rule 2 | W02, W04, W06, W22 |
| rule 3 | W05-W07, W12, W19, W20 |
| rule 4 | W10-W18, W53 |
| rule 5 | W26-W32 |
| rule 6 | W24, W33 |
| rule 7 | W32, W52 + the recorder |
| walk start | W01, W37, W48, W50 |
| today's three bugs | W33, W34/W35, W36/W37 |
| left rail | W38-W40 |
| arrivals | W25, W41-W43 |
| closed by name | W44, W45 |
| For later | W30, W46, W47 |
| phone | W51 |
| put-on-list | W49 |

### 6.2 The two runners, one table

- **`tests/test_walk_table.py`** runs every case in process against `railwalk` on a seeded demo home (`TASKUARY_HOME` set to a temp dir first; importing the server migrates the live home otherwise). It resolves symbols through `railwalk.line(pile)` and asserts:
  - the Answer's row
  - the read receipts, through `funnel_state` / `pile.items`
  - `walk.above is not None` == `back`
  - the line equals the rail's own drawing order with For later and settling rows removed (the invariant that keeps page and server one order)
- **`website/browser/walk-table.test.mjs`** reads the same JSON. It drives the demo app with `walkdriver.mjs`: `clickRow`, `pressNext`, a `pressBack` on `[data-tq-walk-back]`, `doVerb` for the leaves, and the fixture API for `arrive` / `close-elsewhere` / `agent-closes`. It asserts:
  - the ringed rail row (`.tq-pile-row.current`)
  - the live card's key
  - the rail's rows per section (`[data-tq-run]`)
  - Back's `disabled`
- **The frame recorder,** in the same browser file, wraps each case's `action`. It starts a `requestAnimationFrame` sampler (`walkdriver.watch` / `unwatch`, extended) at the press and stops it when the expected row is ringed. Each sampled frame must have either a visible `.tq-live-card` with content or visible `.tq-typing` dots; that is today's `next-never-blank` check, generalised. The run must also show:
  - **one press:** the button is not pressed again by the test, and the Answer lands
  - **no wrong row:** the ring never stands on a row other than the start row, the prepared row and the expected row, and a prepared row is replaced in place (same line id)
  - **no stray line:** at most one new assistant line per action
- **CI.** The Python table runs in the normal suite. The browser table joins the smoke gate (memory: smoke gate, not full browser) as one file, so it blocks a release.

## 7. Migration

### 7.1 What is deleted

**Server**

- `funnel_selection.py`: `_eligible`'s put-down clause, `below`, `first_at_start`, `SelectionCapture` revision / `validate_selection` / `recheck_selection` / `same_pick` / `same_backing`, `SelectionStale`, `capture_from_rail`. `_batch` moves to railwalk. The module goes once nothing imports it.
- `funnel.py`:
  - `next_item`'s keyless road, `mark_place`, `walk_place`, `PLACE_KEY`, `leads`, `new_walk`, `section_next`, `fyi_batch` (moves)
  - `settle`'s `put_down` / `RETURN_MINUTES` `Until` and its `meeting:` branch (per Q3)
  - `reset_walk`'s surfaced-clearing (it keeps notice / alert acks and calls `railwalk.start`)
  - `_apply_states`' surfaced / put-down band (legacy store path)
- `processing_unread.py`: `RETURN_MINUTES`, `WALK_KEY`, `walk_started_at`, `this_walk`, `back` / `why_open`'s walk clause, `passed`, the shown-mark block for approve / blocked / queued / stopped / saved / working, `card['put_down']`, `back_at` for put-down rows, and `actionable`'s `put_down` clause. A task row's read state drives only its `+N` (`news_since_seen`) and never its place or walkability.
- `concierge.py`:
  - `surface`'s keyless selection, `move_on`, `prepare_next`, `opened_reads`
  - the end-of-walk `skipped` / `waiting` computation (it moves to railwalk as the end Answer)
  - the `leaving` / `exclude` parameters
  - `restore_current`'s `over` clearing
- `processing_navigation.py`: `reserve` / `Reservation` / `NavigationStale` / `NavigationRebind`. A press-id dedupe in railwalk replaces them. `chat_change`'s New-chat lock stays if still used.
- `server.py`:
  - `_navigation_reservation`
  - the selection fields, `prepared_next` and `walk_at` in `_pile_payload`
  - `/api/funnel/settle`'s `put_down`
  - the `NavigationStale` / `SelectionUnavailable` stream branches for Next
  - the `leaving` / `exclude` fields of `SurfaceBody` / `ConciergeStreamBody`
- `remote_assistant.py`: `_move_on`'s section hold, and `doorway_browse.hold` / `held` / `next_in` with their `seen` list.

**Page**

- `AssistantView.jsx`: everything listed in section 4, the "Reports page" settle loop in `surface` (it becomes `next(from=report)`), the walk-on half of `advance` / `settleDone` / `done`, and the canvas `putDown` / `pickUp` drawNextEarly hooks (`pickUp` keeps only "unfold, say why").
- `funnelPile.js`: `rowAbove`, `backFrom`, `sectionNext`. `sectionDone`'s words can stay if Q6 keeps them.
- `assistantSelection` helpers: `captureNextSelection`, `nextSelectionBody`, `nextSelectionScope`, `sameSelectionScope`, `replaceSelectionToken`, `withdrawSelection`, `selectionGuardDetail`.
- `TaskPage.jsx` / `CanvasItem.jsx`: in the canvas, `onFinish` / `onReminded` / `sent({closes})` / `onLeave` / `onStay` route through `leave`. The Tasks tab keeps its own road.

**Tests to replace by the table** (each read first; a case not covered gets a table row):

- Python: `test_walk_follows_the_rail.py`, `test_walk_order*.py`, `test_new_walk_off_the_lifespan.py`, the walk parts of `test_lifecycle.py` / `test_funnel.py` / `test_phone_rewalk.py`
- Browser: `new-walk-forgets-left`, `next-bounce`, `never-back`, `walk-down-after-put-down`, `back-next-reads`, `report-back-unread`, `next-never-blank`, `walk-again-last-task`, `next-off-the-task`
- Unit: `website/test/assistantSelection.test.mjs`

### 7.2 What moves

| what | from | to |
|---|---|---|
| FYI batch assembly | `funnel_selection._batch`, `funnel.fyi_batch`, `concierge._fyi_card` | railwalk (the card words stay in concierge's `present_turn`) |
| the place of a pulled row | `funnelPile.pulledRow` mirror, `surface`'s `pulled` | railwalk `place_of(key)` |
| end-of-walk Opens | `surface` | railwalk's end Answer |
| Current | `concierge.set_current` / `current_key` | `rail_walk.on` |

### 7.3 Risks

- **The PW-050 / PW-118 guarantees** ("a press acts on what the page showed", "a write mid-press must not refuse it"). They now rest on `from_key` and idempotent `next`. The contract tests must be rewritten against that, not dropped.
- **Speed.** `line()` must read the cached pile (`funnel.pile`) and never build. `peek()` runs on every rail payload, so it must stay O(rows) with no keyed builds. Keep the existing perf probes (`assistant-speed.probe`, the 2026-10-20 / P4 notes) in the slice gates.
- **Alerts and the Advisor read `surfaced`.** `alerts()` skips surfaced rows, and the Advisor read timing uses `unconfirmedRef`. Removing walk-written marks may re-raise an alert the walk used to silence; the ack marks stay, but check `alerts()` against the table world.
- **The legacy (non-processing) store path** (`_apply_states`) still has its own surfaced band. Either migrate it in the same slice or confirm no live home uses it.
- **Demo mode** (`demo.LOCAL_OPS`) runs the closes locally. railwalk must call the same roads so the demo world behaves like a real one.
- **One walk across desk and phone** (Q5) changes what a hand-back shows.
- **Removing "passed"** changes the rail's look. The Passed band and the `back_at` gutter on put-down tasks go, and any CSS / words / lanes.json hint for them must go too, so no dead UI is left.
- **Settings migration.** Drop `walk_place` / `walk_started_at` / `assistant_current:*` once `rail_walk` is written. One read-through on first start.

### 7.4 Slices (each lands on master on its own targeted tests, per iterate-fast-trunk)

0. **The table first.** `tests/walkworld.py`, `tests/fixtures/walk_table.json`, `tests/test_walk_table.py` and `website/browser/walk-table.test.mjs` with the recorder. Cases that fail today are marked `xfail` with the bug named. This pins today's behaviour before anything moves.
1. **railwalk, read side.** `line`, `place_of`, the batch rules, `peek`. `/api/funnel/pile` carries `walk` beside the old fields. No writes. The table's navigation-only cases run against `peek`.
2. **railwalk, write side.** State, lock, press ids, `start` / `next` / `back` / `open` / `leave` with the effects of 3.5. The `/api/walk/*` routes. `concierge.surface` and `/api/concierge/next` / stream `mode: 'next'` delegate to it. The Python table goes green.
3. **Page cutover.** AssistantView sends actions and draws Answers. Delete the page state in section 4. Back comes from `walk.above`, draw-ahead from `walk.below`. The browser table and recorder go green on desk cases.
4. **Close roads.** CanvasItem / TaskPage / ReviewDecision Send / RemindMe / Not a task / Not ours / typed put-downs call `leave`. Closes elsewhere (selfclose, Board, Tasks tab) stop touching the walk.
5. **Phone.** `remote_assistant` and `doorway_browse` go through railwalk (W51 + the phone tests).
6. **Deletion.** processing_unread's passed / this_walk / RETURN_MINUTES, funnel_selection, processing_navigation, the selection helpers, the old tests, the settings migration, and the lanes.json hint texts that mention "for this walk".
7. **Release gate.** The full browser table + recorder, plus the agent-buttons gate (memory), then ship.

## 8. Open questions for the owner

1. **Does opening a task clear its "+N"?** Rule 4 says opening never reads. A task cannot leave the rail by being read, but today opening it clears its "+N new" mark (2026-10-23). Proposed: yes, opening a task clears its +N; it changes nothing else.
2. **Can Back reach a report Next just read?** Today Back from the first FYI goes back to the last report the walk read (trust audit F1, 2026-10-28). Under rule 3 that report is off the rail, so Back goes to the row now above. Proposed: the rule as written; the report stays reachable from the Reports page.
3. **What does Next do on a meeting?** Today it hides the meeting until it starts (2026-09-28: "should not have to dismiss invite a 100 times"). Under rule 6 a strict walk shows it once per walk anyway. Proposed: treat it like a task (it stays, and leaves the rail by itself after its grace minutes). The alternative is to keep it as a read row that leaves on Next.
4. **For later in the walk.** Proposed: Next from the last task goes to the first report, not into For later (those rows left by Remind me). A For later row you click walks down the rail from there. Confirm.
5. **One walk or one per surface?** Proposed: the desk and the phone walk the same line from the same place, and the other surface follows. The alternative is one walk per surface.
6. **Section heading click.** Proposed: open the section's first row, then Next walks down the whole rail past the section's end, with no "Reports done." stop. Keep that line at the section boundary, or drop it?
7. **The Passed band and "back at" gutter on tasks disappear.** Nothing is "passed" any more. Confirm that removing them is fine, and that no replacement mark is wanted.


## Decisions on the open questions (2026-10-30, decided by the seven rules; the owner pre-authorized the build)

1. Opening a task clears its "+N" mark and nothing else - opening never reads.
2. Back after Next read a report goes to the row now above it: a read report has left the rail.
3. A meeting is walked like a task, in its place - never skipped, never hidden until it starts.
4. For later is not on the walk's line: Next from the last task goes to Reports. A For later row clicked walks down the rail from its place.
5. The desk and the phone share one walk.
6. A section heading clicked carries on down the rail - no "Reports done." stop.
7. The Passed band and the tasks' "back at" time are removed; with no skipping they say nothing.
