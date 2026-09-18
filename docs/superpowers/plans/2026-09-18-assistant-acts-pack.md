# Assistant Acts Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The chat assistant can run, pause, resume, edit, re-aim and delete reports and workflows, set any setting by name, test or pause a connection, and start a script - by name from the chat or as a verb on a stop - with the tiers the spec fixes (reads at once; undoable writes at once with an undo; irreversible writes confirm first), and a run asked for from a chat reports back to that chat.

**Architecture:** New kinds in `operations.KINDS` and `toolcatalog.PURPOSE`; `concierge.call_turn` resolves names through `appfacts` before proposing and marks instant kinds `auto` (both surfaces already execute an auto proposal at once); `server._run_operation` gains one handler per kind, each returning an `undo` in its outcome; `concierge.receipt` says the undo and records it as a one-click proposal card; `remote_assistant` keeps the asking chat in a thread-local so `report.run` can send the landed summary back. The regex settings table goes.

**Tech Stack:** Python 3.10, FastAPI; React/Vite; pytest; Node 22 tests.

**Spec:** `docs/superpowers/specs/2026-09-18-assistant-runs-the-app-design.md` (Acts, Tiers, Results come back to whoever asked).

## Global Constraints

- Every new kind is dispatched by `server._run_operation`; the catalogue is generated (`toolcatalog.block`), never edited.
- Instant kinds (`toolcatalog.INSTANT`): report.run, report.pause, report.resume, report.reach, report.edit, setting.set, connection.test, connection.pause, connection.resume, script.start. Confirm-first: report.delete. `connection.create`, `report.create` stay proposals.
- A name that resolves to nothing never proposes: the answer lists what exists.
- Secrets never pass through chat: connection.create carries a name and a type only.
- Every write audits with actor `assistant` (`store.audit(entity, id, action, 'assistant', detail=...)`).
- Full pytest before push; frontend gates under Node 22.

---

### Task 1: The kinds, in the registry and the catalogue

Files: `taskuary/operations.py` (KINDS), `taskuary/toolcatalog.py` (PURPOSE, INSTANT), tests in `tests/test_zz_toolcatalog.py`.

KINDS additions (target kind, required params, correction=None):
```
'report.run': ('source', (), None), 'report.pause': ('source', (), None), 'report.resume': ('source', (), None),
'report.reach': ('source', ('reach',), None), 'report.edit': ('source', ('config',), None), 'report.delete': ('source', (), None),
'setting.set': ('setting', ('key', 'value'), None),
'connection.test': ('connector', (), None), 'connection.pause': ('connector', (), None), 'connection.resume': ('connector', (), None),
'script.start': ('script', ('name',), None),
```
PURPOSE lines say the name parameter: report kinds take `title` (part of the name) or `source_id`; connection kinds `name` or `connector_id`; setting.set `key` or `label` plus `value`; script.start `name` (one of appfacts.SCRIPTS). `INSTANT = frozenset({...})` and `is_instant(kind)`. Test: each kind in KINDS, in block(), instant set as listed, `valid('setting.set', {'key': 'x'})` says it needs value.

### Task 2: Name resolution and the auto flag in call_turn

`concierge.call_turn`: before `_propose_raw`, for target kind `source` resolve `appfacts.find_report(store, params.pop('title',''), params.pop('source_id', None))` - a miss returns `{'say': 'No report by that name. The ones set up: ...'}` with no proposal; `connector` likewise with `find_connection`; `setting` resolves `key` or `label` against `appfacts.settings` and stores `params['key']`, target 0; `script` validates `name` against `appfacts.SCRIPTS`. The proposal's summary is the resolved name. If `toolcatalog.is_instant(kind)`: `prop['auto'] = True` and `prop['say']` says what is being done ("Running Monthly AR Report."). Tests in `tests/test_chat_proposals.py`: a CALL with `title: 'ar report'` proposes `report.run` on the AR source with auto; a miss lists reports; `report.delete` is not auto.

### Task 3: The handlers

`server._run_operation` branches:
- `report.run`: `report_rerun(tid, asked=remote_assistant.asking())` → `{'queued': True, 'title', 'undo': None}`.
- `report.pause`/`report.resume`: `store.save_source({'SourceId': tid, 'Active': 0|1}, ACTOR)`; audit; outcome `{'active', 'title', 'undo': {'kind': resume|pause, 'target': tid, 'label': 'Resume X'|'Pause X'}}`.
- `report.reach`: validate `reach` in `reports.REACH` (`always|wrong|rule`); cfg patch; undo = previous reach.
- `report.edit`: `config` is a dict patch merged over the current ConfigJson (title cannot be blanked); undo = previous config.
- `report.delete`: `delete_source(tid)` (the route function); no undo.
- `setting.set`: key in `settings_schema.knobs()`; coerce by type (switch: on/off/true/false/1/0 → '1'/'0'; number: int; select: one of options; else str); `prev = store.get_settings().get(key)`; `store.set_setting(key, value, ACTOR)`; audit; outcome `{'key', 'label', 'value', 'said': settings_schema.describe(key, value), 'undo': {'kind': 'setting.set', 'target': 0, 'params': {'key', 'value': prev}, 'label': 'Put <label> back to <prev in words>'}}`.
- `connection.test`: `channels.test_connector(store, tid)` → its dict.
- `connection.pause`/`resume`: `store.save_connector({'ConnectorId': tid, 'Active': 0|1}, ACTOR)`; undo is the inverse.
- `script.start`: `{'script': name}`.
`report_rerun` gains `asked: dict | None`: after the run lands, `remote_assistant.send(store, asked['channel'], asked['chat'], f"{title} landed: {summary or 'done'} - say 'read <title>' for the whole thing", asked.get('connector_id'))`. Tests in `tests/test_chat_proposals.py` with a TestClient: propose + execute each kind on a seeded store and assert the row changed and the outcome's undo names the inverse.

### Task 4: Receipts carry the undo

`concierge._outcome_line` for the new kinds (`Done - Auto-drafts (Replies): off. Undo: put it back to on.`); `concierge.receipt`: when `op.outcome.undo` is present, propose the undo (`operations.propose(store, undo.kind, undo.target, undo.params)`) and record a proposal card `{'kind': 'proposal', 'op': <id>, 'title': undo.label}` under the receipt line, so the desktop shows a one-click card; store its id under setting `assistant_last_undo`. `remote_assistant.intercept`: the word `undo` (alone) runs `assistant_last_undo` through `run_proposal` and clears it; the phone receipt ends with "Reply undo to put it back." `describe_op` labels for the kinds.

### Task 5: The asking chat

`remote_assistant`: `_ASKING = threading.local()`; `asking()` returns `{'channel', 'chat', 'connector_id'}` or None; set around the `concierge.say` + `carry_out` block in the inbound handler and cleared in `finally`. Test: with the thread-local set, `report_rerun` sends to that chat (patch `remote_assistant.send`).

### Task 6: The regex table goes

Delete `SWITCH_ASKS` and `switch_ask`; `_carry_out`'s `setting` verb answers: "Name the setting and the value - e.g. auto-drafts off - and I change it; settings.list <group> shows the knobs." (the model has the schema in its facts and will CALL setting.set). Remove the tests that pinned the regex table, if any.

### Task 7: The audit list on Settings

`GET /api/audit/assistant` → `[{'when', 'action', 'entity', 'detail'}]` from `store.list_audit(limit=200)` filtered to `Actor == 'assistant'`. SettingsView: a "What the assistant changed" list at the top of Configuration, hidden when empty. Node test: the view fetches the route and the server defines it.

### Task 8: script.start on the desktop

AssistantView: after a confirmed proposal with `res.outcome.script`, run the matching action: `tasks` → the walk's Next (`advance`), `setup` → `setup()` (the walk chip), `report` → `askSetup()`. Test in `website/test/onboardingWalk.test.mjs` (source assertion).

### Task 9: Gates and landing

Full pytest; Node tests; eslint undef; build; commit per task; push from the worktree; note the shas in the spec.
