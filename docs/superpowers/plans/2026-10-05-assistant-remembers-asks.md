# Assistant remembers asks - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline, the owner's choice). Steps use `- [ ]`.

**Goal:** Work you type (Assistant chat, WhatsApp/Telegram, New + an agent) is remembered as an ask, known to the
assistant every turn, and said back at the door you asked from when its lane moves to something that needs you or ends.

**Architecture:** One column (`task.AskedVia`), one module (`taskuary/asks.py`: door, state from the rail's own lane,
block, check/notice/watch), one resolver (`taskuary/people.py`). Event-driven off `store._poke('task-changed')` with a
5-minute safety sweep. No model calls.

**Spec:** `docs/superpowers/specs/2026-10-05-assistant-remembers-asks-design.md`

## Global Constraints
- Zero extra model calls. The said line is a template.
- One vocabulary: an ask's state is its task's rail lane and that lane's own sentence.
- Phone only when asked from the phone or the walk is handed to it; otherwise the desktop Assistant chat.
- The background worker never runs in tests unless a test starts it (`asks.watch` is patched in conftest like
  `waitroom.watch`); `asks.notice` is a no-op until `watch` has started.
- Invented people only (Alex Doyle, Paula Vance, Gail Moreno...; `*.example`).
- Whole suite from the repo root before any push. Work in a scratch worktree; commit there; ff-merge.

## Review Focus
1. A poke storm (a 150-row catch-up) must not run 150 checks: the queue de-dupes task ids and debounces.
2. The asks check writes (funnel_state, a chat comment) - those writes poke again; that must not loop.
3. A phone ask whose chat is busy must be retried later, not marked told and lost.
4. A mail-born task, or a to-do no agent touched, never speaks.
5. A restart does not repeat what was already told.

---

### Task 1: The mark - `task.AskedVia`
Files: `taskuary/store.py` (TASK_COLS :46, CREATE TABLE :238, migration ~:820), `taskuary/asks.py` (new: `door()`),
`taskuary/concierge.py` (`setup_task` dict ~:2032), `taskuary/server.py` (`create_task` :569). Test: `tests/test_asks.py`.
Produces: `asks.door() -> str` ('desktop' | '<channel>:<chat>'), `asks.of(task) -> str|None`.
- [ ] Tests: chat hand-off on desktop → 'desktop'; same inside `remote_assistant._ASKING.chat={'channel':'whatsapp','chat':'c1'}`
  → 'whatsapp:c1'; `POST /api/tasks` → 'desktop'; a triage-made task → None; column survives `update_task`.
- [ ] RED, implement (column + whitelist + migration; `'AskedVia': asks.door()` in setup_task; server sets it), GREEN, commit.

### Task 2: Where an ask stands - `asks.state`
Files: `taskuary/asks.py`. Test: `tests/test_asks.py`.
Consumes: `funnel.full_items(store)` (cached rail build, items carry `tid`, `lane`, `why`), `funnel.agent_found`,
`slots.open_/all_`. Produces: `asks.state(store, tid) -> (lane, sentence)`; lane `'finished'` for a closed task,
`'quiet'` when the task is on no rail row; `asks.SAID = {'blocked','approve','stopped','broken','finished'}`;
`asks.agent_touched(store, tid) -> bool` (Assignee agent:, a run, a transcript).
- [ ] Tests with `funnel.full_items` patched to fixed items: lane/why passed through; slot count appended on approve;
  closed → finished + agent summary; absent → quiet. One integration: a typed task with two slot drafts reads `approve`.
- [ ] RED, implement, GREEN, commit.

### Task 3: Saying it moved - check, door, notice, watch
Files: `taskuary/asks.py`, `taskuary/store.py` (`_poke` → `asks.notice`), `taskuary/server.py` (`_lifespan` → `asks.watch`),
`tests/conftest.py` (patch `asks.watch`). Test: `tests/test_asks.py`.
Produces: `asks.check(store, tid) -> str|None` (the line said, or None), `asks.notice(store, tid)`, `asks.drain(store)`,
`asks.watch(store)`, `asks.sweep(store)`.
- [ ] Tests: lane change into a SAID lane speaks once; same lane again silent; `working` silent; told survives a fresh
  module state (funnel_state `ask:<tid>`); mail-born task silent; to-do without agent silent; phone ask → `remote_assistant.send`
  to its chat when `quiet`, and NOT marked told when not quiet; desktop ask while a walk is handed → that chat; else a
  line on the dock task; `notice` before `watch` is a no-op; `notice` de-dupes ids and `drain` runs each once; the check's
  own writes do not re-queue the same task forever.
- [ ] RED, implement, GREEN; full lifespan test file passes; commit.

### Task 4: The assistant knows your asks - block + look-up
Files: `taskuary/asks.py` (`block`, `listing`), `taskuary/concierge.py` (`_say` user string ~:3076, beside `facts`),
`taskuary/lookups.py` (READ), `taskuary/toolcatalog.py` (READS, `need` map, WHERE example), docs page regenerated.
Produces: `asks.block(store) -> str` (≤6 lines, '' when none), look-up `asks.list` (`status`: open|all, `limit`).
- [ ] Tests: block lists newest open asks with ref, age, door, sentence; cap 6; under 600 chars with 20 asks; a finished
  ask off the rail is gone; `asks.list` returns older ones; `test_lookups`/`test_task_tools` pass; prompt carries the block.
- [ ] RED, implement, GREEN, regenerate `docs/site/assistant-tools.md` + `build:docs`, commit.

### Task 5: Names resolve against the people you wrote to - `people.resolve`
Files: `taskuary/people.py` (new), `taskuary/store.py` (`recipients_like`), `taskuary/lookups.py` (`sender_read` falls
back to recipients), `taskuary/slots.py` (`add` resolves a bare name: one match → address; several → `out.candidates`).
Produces: `people.resolve(store, name) -> {'address': str} | {'candidates': [..]} | {}`.
- [ ] Tests: a name only in the owner's sent To/Cc resolves; two matches → candidates, slot keeps the name; none → {};
  `sender.read` finds a person the owner only wrote to; an address passes through untouched.
- [ ] RED, implement, GREEN, commit.

### Task 6: The Advisor never repeats what a task just said
Files: `taskuary/asks.py` (`touched(store, hours) -> {'tids','convs','people'}`, `told_lines(store, days)`),
`taskuary/assistant.py` (`candidates` filter; ALREADY SAID gains the told lines via `assistantblocks._already_said`).
- [ ] Tests: a follow-up candidate on a task told an hour ago is dropped; same at 25 h comes through; one whose
  sender got a slot email an hour ago is dropped; the ALREADY SAID text carries the told lines.
- [ ] RED, implement, GREEN, commit.

### Task 7: Whole suite, review, land
- [ ] Full pytest from repo root; website node tests if UI touched; fresh-context reviewer on the branch; one fix pass;
  ff-merge; push; watch CI.
