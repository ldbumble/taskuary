# Worker Lifecycle and Results Implementation Plan (Stream B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the open worker-lifecycle items: an agent's question is answered through the assistant against the exact request and run, API workers emit their own lifecycle signals, the agent's real final answer is what gets saved, peers hear about each other as they start and stop, hooks are installed against a known CLI version, and every scenario the spec enumerates has a test.

**Architecture:** Everything builds on `taskuary/workerstate.py` (the one status model: events keyed by task, run, request) and `taskuary/blackboard.py` (`live_notes` is the one live selection). The chat's `agent.answer` operation stops bypassing that model; `GeneralSession` emits `turn_end` and a structured ask marker; `selfclose.declare` records the run's last spoken message as the Finished result; `terminal.open_session` and `Term._pump` announce peer changes through the waiting room; `hooks.install` records the installed CLI version. No provider protocol is changed.

**Tech Stack:** Python 3.10, FastAPI, SQLite, pytest/unittest, loguru.

**Spec:** `docs/processing-walkthrough-todos.md` sections at lines 807 (PW-137..142), 987 (PW-173, 175), 1012 (PW-178, 179, 181), 1043 (PW-185, 187), 1187 (PW-214), 1247 (PW-223..229), 1292 (PW-230, 234).

## Global Constraints

- Owner rules (2026-09-06): no hardcoded words or regex intent routing (the model reads intent; code validates verb and target); shown in chat = read; an agent's question or approval stays in Unread, marked, until answered; dense fast.ai code style; no formatters; preserve each file's line endings (`taskuary/server.py` is CRLF); never write a backslash line-continuation through a heredoc.
- Never touch the main checkout, the sibling worktree, or `~/.taskuary`. No push, merge, tag or release. Stop at the review gate.
- Tests from the worktree root: `python -m pytest <files> -q -p no:cacheprovider`. Full suite once before the report.
- PW-227 stands: an event from a run that is not the task's current one is rejected; a duplicate open request is one request; answering one request must not clear others.
- PW-226 stands: `turn_end` is never a finish; no explicit result or request means `unknown`, never a guessed hand raise.
- Stream A (sibling branch) edits `taskuary/general.py` lines ~300-330 (`_prompt`'s COUNSEL block). Do not edit that region; the ask marker goes into `GeneralSession.send_prompt`, next to `POST_LINE`.
- Left OPEN by decision, with a note in the spec: PW-224 (Codex App Server integration: a provider protocol change that needs the installed protocol validated with the owner present) and PW-214 (live browser exercise of the All-detail buttons: needs the puppeteer harness against a demo server; code-traced findings PW-211..213 are already done).

---

### Task 1: The chat's answer to an agent goes to the exact request (PW-138, PW-140)

**Files:** `taskuary/workerstate.py` (add `delivery_path`, `answer_open`), `taskuary/server.py` (`agent.answer` branch, ~line 559), `tests/test_agent_answer_route.py`

**Interfaces:**
- `ws.delivery_path(sess) -> str|None`: `'api'` when the session has `send_prompt`, `'pty'` when it is a `Term` (has `typed`/no `send_prompt`) and is alive, `None` otherwise.
- `ws.answer_open(store, tid, text, actor) -> dict`: answers the newest open request of the task's current run (approval first) via `ws.answer`; when the run has NO open request it returns `{'delivered': False, 'state': 'no_request'}` so the caller falls back to the waiting room.

- [ ] Test (RED):
```python
"""The assistant's answer to an agent lands on the exact outstanding request of the run that asked (PW-138); the
delivery path is the integration's own, and with none it falls back to the waiting room (PW-140)."""
import unittest
from unittest import mock
from taskuary import server, terminal as term, workerstate as ws
from tests.test_worker_events import Base, live


class AnswerRoute(Base):
    def test_a_chat_answer_is_bound_to_the_open_request_not_typed_blind(self):
        s = live(self.tid); typed = []; s.send_prompt = lambda t: typed.append(t); term.SESSIONS['run1'] = s
        ws.record(self.s, self.tid, 'run1', 'input_needed', text='Which branch?', choices=['main', 'dev'], source='hook')
        out = ws.answer_open(self.s, self.tid, 'main', 'owner')
        self.assertTrue(out['delivered']); self.assertEqual(typed, ['main']); self.assertEqual(out['path'], 'api')
        self.assertEqual(ws.status(self.s, self.tid)['requests'], [])

    def test_no_open_request_means_the_waiting_room(self):
        s = live(self.tid); term.SESSIONS['run1'] = s
        self.assertEqual(ws.answer_open(self.s, self.tid, 'carry on', 'owner')['state'], 'no_request')

    def test_the_operation_uses_the_request_when_there_is_one(self):
        s = live(self.tid); s.send_prompt = lambda t: None; term.SESSIONS['run1'] = s
        ws.record(self.s, self.tid, 'run1', 'approval_needed', text='Run the migration?', source='hook')
        with mock.patch.object(server, 'store', self.s), mock.patch.object(server, 'waitroom_add') as wr:
            out = server._run_operation_kind('agent.answer', self.tid, {'text': 'yes'})
        self.assertFalse(wr.called); self.assertTrue(out['delivered'])
```
Read `server.py` around line 520-560 first: the function that holds `if kind == 'agent.answer': return waitroom_add(...)` is the one to call in the third test; use its real name and signature (the plan calls it `_run_operation_kind`), and adjust the test.

- [ ] Implement in `workerstate.py`:
```python
def delivery_path(sess) -> str | None:
    """The integration's own reply road (PW-140): an API session takes a prompt, a pty is typed into; None = open the workspace."""
    if not sess or not getattr(sess, 'alive', False): return None
    return 'api' if hasattr(sess, 'send_prompt') else 'pty'

def answer_open(store, tid: int, text: str, actor: str = 'owner') -> dict:
    """The chat's answer, bound to the newest open request of the run that has the task (approval first)."""
    req = asking_of(store, _live(tid)) if _live(tid) else None
    if not req: return {'delivered': False, 'state': 'no_request', 'why': 'no open request from a live run'}
    out = answer(store, tid, req['request_id'], text, actor)
    return {**out, 'path': delivery_path(_live(tid)), 'request_id': req['request_id']}
```
and in `server.py` replace the `agent.answer` line with:
```python
    if kind == 'agent.answer':
        # the exact outstanding request of the run that asked (PW-138/139); with none, the waiting room (PW-140)
        from . import workerstate as ws
        out = ws.answer_open(store, tid, str(p.get('text') or 'yes'), ACTOR)
        if out['state'] == 'no_request': return waitroom_add(tid, {'text': str(p.get('text') or 'yes')})
        if not out['delivered']: raise RuntimeError(f"{out['state']}: {out.get('why') or ''}")
        return out
```
- [ ] Run: `python -m pytest tests/test_agent_answer_route.py tests/test_worker_events.py tests/test_chat_proposals.py -q -p no:cacheprovider` → PASS
- [ ] Commit: `feat: the chat's answer to an agent lands on the exact open request, else the waiting room (PW-138, PW-140)`

### Task 2: API workers emit their own lifecycle signals (PW-225)

**Files:** `taskuary/selfclose.py` (ASK marker), `taskuary/general.py` (`send_prompt` only), `tests/test_api_worker_signals.py`

**Interfaces:**
- `selfclose.ASK_MARKER = '[[TASKUARY-ASK]]'`, `selfclose.ASK_LINE` (prompt text), `selfclose.ask_marker(text) -> (cleaned, question, choices)`; a reply ending `[[TASKUARY-ASK]] question | choice | choice` is an explicit Input-needed request.
- `GeneralSession.send_prompt` records `turn_end` after every reply (text = reply[:4000]), `input_needed` when the ask marker is present (request id from the question), and appends `ASK_LINE` next to `POST_LINE`/`CHAT_LINE` in the system prompt.

- [ ] Test (RED):
```python
"""A regular (API) worker says what it needs and when its turn ended, as events - not prose a judge reads (PW-225)."""
import unittest
from unittest import mock
from taskuary import general, selfclose, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory


class ApiWorkerSignals(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.fx = Factory(self.s); self.tid = self.fx.task(title='Compare vendors', kind='general')

    def test_the_ask_marker_parses_question_and_choices(self):
        cleaned, q, ch = selfclose.ask_marker('I compared them.\n[[TASKUARY-ASK]] Which vendor? | Acme | Globex')
        self.assertEqual((cleaned, q, ch), ('I compared them.', 'Which vendor?', ['Acme', 'Globex']))
        self.assertEqual(selfclose.ask_marker('plain reply'), ('plain reply', None, []))

    def test_a_turn_records_turn_end_and_an_ask_records_input_needed(self):
        sess = general.GeneralSession(self.s, self.tid)
        brain = lambda system, user, **kw: 'Two options.\n[[TASKUARY-ASK]] Which vendor? | Acme | Globex'
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=brain), mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')):
            sess.pick = 'api:test'; reply = sess.send_prompt('compare them')
        self.assertNotIn('TASKUARY-ASK', reply)
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['state'], 'input_needed'); self.assertEqual(st['requests'][0]['choices'], ['Acme', 'Globex'])
        kinds = [e['Kind'] for e in ws.events(self.s, self.tid)]
        self.assertEqual(kinds[:3], ['working', 'turn_end', 'input_needed'])
```
Read `GeneralSession.__init__` and `_selected` first and adapt the patching so `send_prompt` runs with a fake brain and no real provider.

- [ ] Implement: in `selfclose.py` after `chat_marker`:
```python
ASK_MARKER = '[[TASKUARY-ASK]]'
_ASK_RE = re.compile(r'\[\[\s*TASKUARY[-_ ]?ASK\s*\]\]\s*:?\s*(.*)', re.I | re.S)
ASK_LINE = (f'ASKING THE OWNER: when you cannot continue without their answer, end your reply with a final line: '
            f'{ASK_MARKER} <the exact question> | <choice> | <choice> (choices optional). Taskuary shows it as a question '
            f'waiting for them and brings their answer back to you. Only for a real blocker, never for a rhetorical question.')

def ask_marker(text: str) -> tuple:
    """(cleaned reply, question, choices) - or (text, None, []) when the reply asks nothing structurally."""
    m = _ASK_RE.search(text or '')
    if not m: return text, None, []
    parts = [' '.join(p.split()) for p in m.group(1).split('|')]
    return text[:m.start()].rstrip(), (parts[0] or None), [p for p in parts[1:] if p]
```
In `general.py` `send_prompt`: where `system = f'{system}\n\n{POST_LINE}'` is appended (both places), also append `selfclose.ASK_LINE` (for API picks too: it is a reply marker, not a shell command). After `reply, closing = selfclose.chat_marker(reply)` add:
```python
            reply, asked, choices = selfclose.ask_marker(reply)
            try:
                from . import workerstate as ws
                ws.record(self.store, self.task_id, self.sid, 'turn_end', text=reply[:4000], source='api')
                if asked: ws.record(self.store, self.task_id, self.sid, 'input_needed', request_id=ws.request_id_for(asked), text=asked, choices=choices, source='api')
            except Exception as e: logger.debug(f'api worker event skipped: {e}')
```
- [ ] Run: `python -m pytest tests/test_api_worker_signals.py tests/test_worker_events.py tests/test_general*.py -q -p no:cacheprovider` → PASS
- [ ] Commit: `feat: a regular worker says what it needs and when its turn ended, as events (PW-225)`

### Task 3: The agent's own last message is the saved result (PW-230, Claude half)

**Files:** `taskuary/selfclose.py` (`declare`), `tests/test_final_answer_capture.py`

- [ ] Test (RED):
```python
"""`taskuary --done "<sentence>"` saves the agent's actual final answer - the Stop hook's last message for that run - as the
Finished result; the sentence is the summary (PW-230)."""
from unittest import mock
from taskuary import selfclose, terminal as term, workerstate as ws
from tests.test_worker_events import Base, live


class FinalAnswer(Base):
    def test_the_finished_event_carries_the_runs_last_spoken_message(self):
        s = live(self.tid); term.SESSIONS['run1'] = s
        ws.record(self.s, self.tid, 'run1', 'turn_end', text='I fixed the cron: the schedule was UTC. Tests pass.', source='hook')
        with mock.patch.object(selfclose, 'blocked', return_value=''), mock.patch.object(selfclose, '_mark', return_value=True), \
             mock.patch.object(selfclose, 'stays_open', return_value=False), mock.patch.object(selfclose, '_wrap', return_value={'closed': True}):
            selfclose.declare(self.s, self.tid, 'cron fixed', 'coder')
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['state'], 'finished'); self.assertEqual(st['result'], 'I fixed the cron: the schedule was UTC. Tests pass.')

    def test_with_no_spoken_message_the_sentence_is_the_result(self):
        s = live(self.tid); term.SESSIONS['run1'] = s
        with mock.patch.object(selfclose, 'blocked', return_value=''), mock.patch.object(selfclose, '_mark', return_value=True), \
             mock.patch.object(selfclose, 'stays_open', return_value=False), mock.patch.object(selfclose, '_wrap', return_value={'closed': True}):
            selfclose.declare(self.s, self.tid, 'cron fixed', 'coder')
        self.assertEqual(ws.status(self.s, self.tid)['result'], 'cron fixed')
```
- [ ] Implement in `selfclose.declare`: before the two `ws.record(... 'finished', text=line ...)` calls compute once
```python
    from . import workerstate as ws
    s = term.session_for(tid); sid = getattr(s, 'sid', None) or ws.current_sid(store, tid) or 'cli'
    # the agent's OWN final answer (PW-230): the Stop hook kept this run's last message; the --done sentence is the summary
    spoken = next((e['Text'] for e in reversed(ws.events(store, tid, sid)) if e['Kind'] == 'turn_end' and e['Text']), '')
    result = spoken or line
```
and record `text=result` in both places (dedupe the two try blocks into one helper `_finished(store, tid, sid, result)` if that reads cleaner). Keep the comment lines using `line`. Note in the spec under PW-230: "Codex App Server capture remains open (PW-224)".
- [ ] Run: `python -m pytest tests/test_final_answer_capture.py tests/test_worker_events.py tests/test_selfclose*.py -q -p no:cacheprovider` → PASS
- [ ] Commit: `feat: an explicit finish saves the agent's own last message as the result (PW-230)`

### Task 4: Peers hear about each other as they start and stop (PW-173)

**Files:** `taskuary/blackboard.py` (`peer_update`), `taskuary/terminal.py` (two call sites), `tests/test_peer_updates.py`

**Interfaces:** `blackboard.peer_update(store, cwd, text, exclude_sid) -> int` queues one waiting-room note per live peer session on the same checkout (different sid, has a task) and returns how many; the waiting room delivers when each peer parks (PW-173: a briefing, not a lock).

- [ ] Test (RED):
```python
"""Coordination context refreshes as peers start and stop: a one-line update lands in each live peer's waiting room (PW-173)."""
from types import SimpleNamespace
from taskuary import blackboard as bb, terminal as term
from tests.test_worker_events import Base, live


class PeerUpdates(Base):
    def test_start_and_stop_queue_one_note_per_live_peer_on_the_same_checkout(self):
        other = self.fx.task(title='Other job', kind='coding'); elsewhere = self.fx.task(title='Elsewhere', kind='coding')
        term.SESSIONS['a'] = live(self.tid, 'a'); term.SESSIONS['b'] = live(other, 'b'); term.SESSIONS['c'] = live(elsewhere, 'c', cwd=r'C:\code\else')
        n = bb.peer_update(self.s, r'C:\code\repo', 'PEER: TQ-0002 (coder) started in this checkout', exclude_sid='a')
        self.assertEqual(n, 1)
        self.assertEqual([w['Note'] for w in self.s.waiting_notes(other)], ['PEER: TQ-0002 (coder) started in this checkout'])
        self.assertEqual(self.s.waiting_notes(elsewhere), [])
        self.assertEqual(self.s.waiting_notes(self.tid), [])
```
Read `store.add_waiting` and `waiting_notes` column names first (`Note` may be `Body`); adjust.
- [ ] Implement in `blackboard.py`:
```python
def peer_update(store, cwd: str, text: str, exclude_sid: str = None) -> int:
    """Refresh the peers' coordination context (PW-173): one line into each live peer's waiting room on this
    checkout - typed when it parks. A briefing, never a lock or a worktree."""
    from . import terminal as term, waitroom
    n = 0
    for t in list(term.SESSIONS.values()):
        if not getattr(t, 'alive', False) or not getattr(t, 'task_id', None) or str(getattr(t, 'sid', '')) == str(exclude_sid or ''): continue
        if norm(getattr(t, 'cwd', '')) != norm(cwd): continue
        try: waitroom.add(store, t.task_id, text, actor='router'); n += 1
        except Exception as e: logger.debug(f'peer update to task {t.task_id} skipped: {e}')
    return n
```
In `terminal.py` `open_session`, right after `SESSIONS[t.sid] = t`, when `agent and task_id and cwd`:
```python
        try:
            from . import blackboard as _bb
            _bb.peer_update(store, cwd, f'PEER UPDATE: {task_ref(task_id)} ({agent}) just started in this checkout - `taskuary --board` for its live notes; coordinate before touching shared files.', exclude_sid=t.sid)
        except Exception as e: logger.debug(f'peer update skipped: {e}')
```
and in `Term._pump` right after `self.alive, self.ended = False, time.time()`, when `self.task_id and self.agent`:
```python
        try:
            from . import blackboard as _bb
            _bb.peer_update(self.store, self.cwd, f'PEER UPDATE: {task_ref(self.task_id)} ({self.agent}) has stopped - its wall notes are history now, not file ownership.', exclude_sid=self.sid)
        except Exception as e: logger.debug(f'peer update skipped: {e}')
```
Check `task_ref` is importable there (`from .store import task_ref`). Waitroom notes to a task whose session is parked are typed at once by `waitroom.add` → `deliver`; that is the intended behaviour.
- [ ] Run: `python -m pytest tests/test_peer_updates.py tests/test_waitroom.py tests/test_blackboard.py tests/test_agent_wall.py -q -p no:cacheprovider` → PASS
- [ ] Commit: `feat: peers hear about each other as they start and stop, through the waiting room (PW-173)`

### Task 5: Hooks are installed against a known CLI version (PW-223)

**Files:** `taskuary/hooks.py` (`cli_version`, audit in `install`), `tests/test_hooks_version.py`

- [ ] Test (RED):
```python
"""Claude Code hooks are validated against the installed CLI: the version is recorded, an unknown one warns (PW-223)."""
import unittest
from unittest import mock
from taskuary import hooks


class HooksVersion(unittest.TestCase):
    def test_the_installed_version_is_read_and_a_missing_cli_is_none(self):
        with mock.patch.object(hooks.subprocess, 'run', return_value=mock.Mock(stdout='2.1.3 (Claude Code)\n', returncode=0)):
            self.assertEqual(hooks.cli_version('claude'), '2.1.3')
        with mock.patch.object(hooks.subprocess, 'run', side_effect=OSError('no such file')):
            self.assertIsNone(hooks.cli_version('claude'))

    def test_supported_is_the_floor_that_carries_every_event_we_install(self):
        self.assertTrue(hooks.supported('2.0.0')); self.assertTrue(hooks.supported('2.1.3'))
        self.assertFalse(hooks.supported('1.0.90')); self.assertFalse(hooks.supported(None))
```
- [ ] Implement in `hooks.py` (add `import re, subprocess` to the imports):
```python
MIN_VERSION = (2, 0, 0)     # PostToolUse, Stop, UserPromptSubmit and Notification with last_assistant_message all exist from here

def cli_version(cmd: str = 'claude') -> str | None:
    """`claude --version` -> '2.1.3', or None when the CLI is not there or will not say."""
    try: out = subprocess.run([cmd, '--version'], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError): return None
    m = re.search(r'(\d+)\.(\d+)\.(\d+)', str(out or '')); return m.group(0) if m else None

def supported(version: str | None) -> bool:
    if not version: return False
    return tuple(int(x) for x in version.split('.')[:3]) >= MIN_VERSION
```
and at the end of `install`'s success path (after `logger.info(...)`), record what we installed against:
```python
        v = cli_version(); (logger.info if supported(v) else logger.warning)(f'claude hooks installed for claude {v or "unknown version"}' + ('' if supported(v) else f' - events validated for >= {".".join(map(str, MIN_VERSION))}; status may be incomplete'))
```
Do not call the CLI from tests except through the mock.
- [ ] Run: `python -m pytest tests/test_hooks_version.py tests/test_worker_events.py -q -p no:cacheprovider` → PASS
- [ ] Commit: `feat: hooks record the installed Claude Code version and warn below the validated floor (PW-223)`

### Task 6: Scenario tests the spec enumerates (PW-142, PW-175, PW-181, PW-187, PW-228, PW-229, PW-234)

**Files:** `tests/test_worker_scenarios.py` (new), `tests/test_worker_brief.py` (extend), `tests/test_blackboard.py` (extend)

Write each test against the real modules; where a test fails because of a real defect, fix the defect in the smallest change and say so in the commit body. The scenarios, one test each (names are the test names):

- PW-142 (`tests/test_worker_scenarios.py`, class `Relay(Base)`): `two_waiting_agents_each_get_their_own_answer` (two tasks, two live sessions, two open requests; answering one leaves the other open); `a_duplicate_click_delivers_once` (second `ws.answer` for the same request returns `resolved`); `a_stale_approval_after_a_run_change_is_refused` (request from `run1`, live session now `run2` → `stale`); `restart_recovery_keeps_the_open_request` (events persist; a new `MemoryStore` view via `ws.status` after clearing `term.SESSIONS` reports `disconnected` with the request still listed); `acceptance_is_visible_in_the_discussion` (the delivered answer's comment names the run).
- PW-229 (class `Providers(Base)`): `long_silence_of_a_working_run_raises_no_hand` (working + no request → `waiting_of` False); `repaint_noise_is_not_a_question` (tail with `?`-less repaint; `waiting_of` decided by events, screen ignored when events exist); `approval_deny_is_an_answer_too` (answer 'no' resolves the approval request); `response_end_without_completion_is_unknown`; `explicit_finish_is_finished_with_result`; `an_error_is_failed_not_finished`; `an_empty_workspace_has_no_status` (`unknown`, no requests); `duplicate_and_stale_events_are_dropped`; `reconnection_replays_nothing` (same `event_id` twice → one row); `one_hand_raise_per_request_in_the_pile` (funnel `from_agents` shows one blocked row for one request: use `funnel.from_agents(store, live_state=[...])` as `tests/test_worker_surfaces.py` does).
- PW-228 (class `Unread(Base)`): `a_working_run_is_a_working_row_not_a_chat_turn` (the row's lane is `working`; `concierge.record` was not called — patch it); `a_request_is_promoted_with_its_text`; `a_finished_result_is_a_result_row_not_blocked` (kind `agentdone`); `the_same_event_is_announced_once` (`funnel.announce` twice → one event); `a_waiting_session_still_takes_a_desk` (`blackboard.live_count` counts a session with an open request).
- PW-234 (class `Completion(Base)`): `automatic_and_manual_starts_both_save_before_close` (`coder.wrap` order: patch `session_artifacts.coding` to raise → task stays open, session alive, comment written); `an_incomplete_checklist_is_kept` (checklist items not blindly ticked — read `session_artifacts.coding` for the field it reads and assert on the task's Checklist after a wrap with one item reported done); `a_pending_approval_blocks_the_automatic_road` (`selfclose.blocked` with an open approval → not closed); `duplicate_finish_hooks_do_not_duplicate_artifacts` (two `declare` calls → one artifact); `follow_up_context_is_retained` (the CODER REPORT comment feeds `terminal.seed_text` for a continuation — extend the existing test in `tests/test_worker_brief.py::test_live_coordination_only_when_peers_exist_and_a_continuation_carries_its_own_last_result` only if it does not already assert this).
- PW-175 (`tests/test_blackboard.py`, extend): `two_similar_tasks_both_launch_when_capacity_permits` (patch `likely_overlap` to report a hit; both dispatch; no queue row); `the_advisory_reaches_the_seed` (`terminal.seed_text` contains `SIMILAR WORK`); `capacity_queue_and_retry_limits_are_retained` (existing tests cover `full_house_queues_for_a_slot` and `failed_start_stays_queued_until_successful_retry` — reference them in the evidence, do not duplicate); `an_obsolete_overlap_blocker_does_not_double_start` (a queued task whose blocker ended drains once).
- PW-181 (`tests/test_agent_wall.py`, extend): `an_approval_waiting_run_is_live` (session alive with open approval request → its note is live); `a_stopped_runs_note_leaves_every_surface` (`live_notes`, `wall_text`, `chat_text`/`house_wall` all drop it); `restarting_the_same_task_does_not_revive_the_old_runs_notes` (note with `Sid='old'`, new live session `sid='new'` on the same task → not live); `a_headless_general_run_is_live_by_its_running_run_row` (no pty, `store.running_runs()` row → live via task id); `ui_prompt_and_command_read_one_selection` (`live_wall`, `wall_text` and the `/api/board/notes` route return the same note ids — use `TestClient` like `tests/test_worker_events.py` does for routes).
- PW-187 (`tests/test_worker_brief.py`, extend): `both_kinds_share_agent_rules_and_only_coding_gets_coder_rules`; `no_blanket_soul_in_either_prompt`; `approval_boundaries_survive_in_agent_md`; `the_brief_is_fresh_each_turn` (a new message on the task appears in the next prompt); `live_and_continuation_info_are_scoped` — extend only where `tests/test_worker_brief.py` lacks the assertion (read its eleven tests first).

- [ ] Write the tests, run each file, fix real defects minimally, run the covering files.
- [ ] Commit: `test: the worker lifecycle scenarios the walkthrough enumerates (PW-142, PW-175, PW-181, PW-187, PW-228, PW-229, PW-234)`

### Task 7: PW-185 audit of the worker prompt, spec ticks, gates

**Files:** `docs/processing-walkthrough-todos.md`, `docs/processing-acceptance-ledger.md`, `docs/processing-implementation-evidence.md`, possibly `taskuary/general.py` outside lines 300-330 / `taskuary/terminal.py` `seed_text`

- [ ] PW-185: build one coding seed (`terminal.seed_text`) and one general prompt (`general._prompt`) on a task with a playbook and saved preferences (read `tests/test_worker_brief.py::test_no_duplicate_rule_blocks` for the fixture); assert each block header (`RULES`, `PROCEDURE FOR THIS JOB`, `ASSISTANT STYLE`, `OTHER AGENTS`, `THE WALL`, `ASK`) appears at most once and that STYLE.md text appears only when the task is a writing task. If it already holds, tick PW-185 with that test as evidence; if not, fix the duplicate source and say so.
- [ ] Tick PW-137, 138, 140, 142, 173, 175, 178, 179, 181, 185, 187, 223, 225, 228, 229, 230, 234 with one indented evidence line each naming the test file. Leave PW-224 and PW-214 open with the notes from Global Constraints. Ledger rows → `implemented` with test files; one evidence block "Section: worker lifecycle (Stream B)" in the evidence doc, in the style of the last block.
- [ ] Gates: `python -m pytest -q -p no:cacheprovider`; `node --test taskuary/whatsapp/`; website tests only if JSX changed (it should not).
- [ ] Commit: `docs: record worker lifecycle acceptance (PW-137..142, PW-173..187, PW-223..234)`
- [ ] Stop. Report per the directive.
