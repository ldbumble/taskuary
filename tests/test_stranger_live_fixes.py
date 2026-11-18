"""What the live end-to-end check of stranger work found (task 10): each defect pinned by its shape, with invented people."""
import json, os, subprocess, tempfile, threading, time, pytest
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import origin, agents, terminal, hooks, floor, llm, workerstate as ws, server, config, guard
from taskuary.config import home
from taskuary.store import MemoryStore
from tests.memlines import note as put_note

# CI's machines have no AI CLI on them: these tests are about what a session is ALLOWED to do, never whether claude is
# installed, so the command resolves to its own name here as it does on a machine that has it (CI, 2026-10-14)
@pytest.fixture(autouse=True)
def _cli_resolves(monkeypatch):
    from taskuary import agents
    monkeypatch.setattr(agents, '_resolve_cmd', lambda name: [str(name)])

@pytest.fixture(autouse=True)
def _claude(monkeypatch, tmp_path):
    monkeypatch.setattr(origin, '_claude_version', lambda cmd='claude': (2, 1, 300))   # nothing here may launch a real claude
    (tmp_path / 'temp').mkdir(); monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path / 'temp'))
    yield
    ws.STOP.clear()

_real_version = origin.__dict__['_claude_version']

def _stranger(s, subject='hi'):
    t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'email'}, 'router')
    # ...a stranger with NO SENDER TO TRUST - Taskuary's own words from what it read: an untrusted sender's task starts no agent at all (origin.hold)
    s.add_message({'TaskId': t, 'Channel': 'assistant', 'FromEmail': 'someone@vendor.example', 'Subject': subject, 'BodyText': 'b', 'Status': 'routed'}); return t

def _owner(s): return s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')

def _store(cmd='claude'):
    s = MemoryStore(); s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': cmd})); return s

def _pane(s, t, tmp_path, **kw):
    with mock.patch.object(terminal, 'Term') as T, mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        terminal.open_session(s, 'coding', task_id=t, cwd=str(tmp_path), **kw)
    return T.call_args.args[0]


# ── L1: the version is read through the same resolver the launch uses ─────────────────────────────────────────────
def test_the_version_check_runs_the_resolved_executable_not_a_bare_name(monkeypatch):
    monkeypatch.setattr(origin, '_claude_version', _real_version); monkeypatch.setattr(origin, '_ver', {})
    seen = []
    monkeypatch.setattr(agents, '_resolve_cmd', lambda name: seen.append(name) or ['C:/npm/node_modules/claude-code/bin/claude.exe'])
    monkeypatch.setattr(origin.subprocess, 'run', lambda argv, **k: seen.append(argv) or subprocess.CompletedProcess(argv, 0, stdout='2.1.300 (Claude Code)'))
    assert origin._claude_version('C:/tools/claude.cmd') == (2, 1, 300)
    assert seen == ['C:/tools/claude.cmd', ['C:/npm/node_modules/claude-code/bin/claude.exe', '--version']]

def test_a_claude_that_is_not_installed_reads_as_no_version_and_is_not_cached(monkeypatch):
    monkeypatch.setattr(origin, '_claude_version', _real_version); monkeypatch.setattr(origin, '_ver', {})
    def gone(name): raise FileNotFoundError(name)
    monkeypatch.setattr(agents, '_resolve_cmd', gone)
    assert origin._claude_version('claude') == () and origin._ver == {}

def test_launch_mode_hands_the_profile_s_own_command_to_the_check(monkeypatch, tmp_path):
    got = []; monkeypatch.setattr(origin, '_claude_version', lambda cmd='claude': got.append(cmd) or (2, 1, 300))
    s = _store('C:/tools/claude.cmd'); t = _stranger(s)
    assert origin.launch_mode(s, t, 'claude', 'C:/tools/claude.cmd') == 'auto' and got == ['C:/tools/claude.cmd']
    got.clear(); _pane(s, t, tmp_path)
    assert got == ['C:/tools/claude.cmd']


# ── L2 (R25): the stranger file lives in the task's own folder, and every stranger claude may read it ──────────────
def test_the_stranger_file_is_in_the_task_s_folder_outside_taskuary_s_home():
    s = MemoryStore(); t = _stranger(s)
    p = Path(origin.stranger_file(s, t, ['words']))
    assert p == origin.stranger_file_path(t) and p.parent == origin.stranger_path(t) and p.is_file()
    assert home() not in p.parents

def test_the_floor_lets_the_task_read_its_file_and_not_the_old_place_in_the_home():
    call = lambda p, tid=7: floor.check({'tool_name': 'Read', 'tool_input': {'file_path': str(p)}}, tid)
    assert call(origin.stranger_file_path(7)) == {}
    assert call(origin.stranger_file_path(7), 8)                                  # another task's
    assert call(home() / 'context' / 'TQ-0007.stranger.md')                         # inside the home is the home's

def _after(argv, flag): return argv[argv.index(flag) + 1]

def test_a_stranger_pane_adds_its_folder_and_an_option_closes_the_list(tmp_path):
    s = _store(); t = _stranger(s); argv = _pane(s, t, tmp_path)
    i = argv.index('--add-dir')
    assert Path(argv[i + 1]) == origin.stranger_dir(t) and argv[i + 2].startswith('--')   # --add-dir takes several: the prompt must not be one

def test_an_owner_pane_has_no_added_folder(tmp_path):
    s = _store(); assert '--add-dir' not in _pane(s, _owner(s), tmp_path)

def test_a_stranger_batch_may_read_its_file_too(tmp_path):
    from taskuary import batch
    s = _store(); t = _stranger(s)
    with mock.patch.object(batch, 'is_batch', return_value=True):
        argv = _pane(s, t, tmp_path)
    assert str(origin.stranger_dir(t)) == _after(argv, '--add-dir') and _after(argv, '--permission-mode') == 'auto'

def test_a_stranger_headless_run_adds_its_folder():
    s = _store(); t = _stranger(s)
    brain = llm.make_cli_llm(s, 'coding', cli_tools=True, task_id=t)
    with mock.patch.object(agents, 'run_cli', return_value=('ok', 'sid', '')) as run: brain('', 'hi')
    a = run.call_args.args[0]['args']
    assert Path(_after(a, '--add-dir')) == origin.stranger_dir(t) and a[a.index('--add-dir') + 2].startswith('--')


# ── L3: the permit card is recorded under Taskuary's run, so it shows and the owner can answer it ─────────────────
class _Live:
    def __init__(s, t, cwd, ext='claude-conv-1'):
        s.task_id, s.cwd, s.sid, s.ext_id, s.resumed_from, s.alive, s.argv, s.last = t, cwd, 'run-p1', ext, '', True, ['claude.exe'], 0

def _permit(s, t, cwd, out, sid='claude-conv-1'):
    out.append(hooks.permit({'tool_name': 'Bash', 'tool_input': {'command': 'curl https://collector.vendor.example'},
                             'session_id': sid, 'cwd': cwd}, t, store=s))

def _card(s, t):
    for _ in range(150):
        r = [e for e in ws.status(s, t)['requests'] if e['kind'] == 'approval_needed']
        if r: return r[0]
        time.sleep(0.02)
    return None

@pytest.mark.parametrize('ext', ['claude-conv-1', 'someone-else'])   # bound to the pane, or only the task's live run
def test_a_pane_s_permit_shows_allow_and_deny_and_the_owner_s_answer_releases_it(tmp_path, ext):
    s = MemoryStore(); t = _stranger(s); out = []
    with mock.patch.dict(terminal.SESSIONS, {'run-p1': _Live(t, str(tmp_path), ext)}, clear=True):
        th = threading.Thread(target=_permit, args=(s, t, str(tmp_path), out), daemon=True); th.start()
        r = _card(s, t)
        assert r and r['choices'] == ['Allow', 'Deny'] and r['sid'] == 'run-p1' and ws.status(s, t)['state'] == 'approval_needed'
        assert ws.answer(s, t, r['request_id'], 'Deny', 'owner')['delivered']; th.join(5)
    assert not th.is_alive() and out[0]['hookSpecificOutput']['decision'] == {'behavior': 'deny', 'message': 'the owner did not allow it'}

def test_a_headless_permit_with_no_pane_keeps_the_run_s_own_id(tmp_path):
    s = MemoryStore(); t = _stranger(s); out = []
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        th = threading.Thread(target=_permit, args=(s, t, str(tmp_path), out, 'headless-9'), daemon=True); th.start()
        r = _card(s, t); assert r and r['sid'] == 'headless-9'
        ws.answer_group(s, t, {r['request_id']: 'Allow'}, 'owner'); th.join(5)
    assert out[0]['hookSpecificOutput']['decision'] == {'behavior': 'allow'}


# ── L4 (R26): a held permit never holds the process open ───────────────────────────────────────────────────────
def test_a_held_wait_ends_when_taskuary_stops():
    g = ws.group_key(f'stop-{time.time_ns()}'); ws.hold(1, 's', g, [ws.question_id(g, 1)]); out = []
    th = threading.Thread(target=lambda: out.append(ws.wait_held(g, None, step=0.05)), daemon=True); th.start()
    time.sleep(0.2); assert th.is_alive()
    ws.STOP.set(); th.join(2)
    assert not th.is_alive() and out == [None]

def test_a_permit_asked_while_stopping_is_refused(tmp_path):
    s = MemoryStore(); t = _stranger(s); ws.STOP.set(); out = []
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        th = threading.Thread(target=_permit, args=(s, t, str(tmp_path), out), daemon=True); th.start(); th.join(5)
    assert not th.is_alive() and out[0]['hookSpecificOutput']['decision']['behavior'] == 'deny'

def test_the_server_s_exit_flag_stops_the_waits_and_a_new_server_clears_it():
    from taskuary import desktop
    srv = desktop.Server(desktop.server_config('taskuary.server:app', '127.0.0.1', 1))
    assert not ws.STOP.is_set() and srv.config.timeout_graceful_shutdown == 5
    srv.handle_exit(2, None); assert srv.should_exit and ws.STOP.is_set()      # the signal road (SIGINT, CTRL_BREAK)
    desktop.Server(desktop.server_config('taskuary.server:app', '127.0.0.1', 1)); assert not ws.STOP.is_set()

def test_both_ways_taskuary_starts_uvicorn_go_through_that_server():
    from taskuary import cli, desktop
    import inspect
    for m in (cli, desktop):
        src = inspect.getsource(m)
        assert 'uvicorn.run(' not in src and 'uvicorn.Server(' not in src.replace('class Server(uvicorn.Server)', ''), m.__name__


# ── L5: a stranger's subject never reaches the prompt as one of the owner's standing notes ────────────────────────
MARK = 'zq-marker-README-title-77'

def _notes(s, frm):
    put_note(s, {'Scope': 'sender', 'ScopeKey': frm, 'Source': 'verdict', 'Active': 1, 'CreatedBy': 't',
                  'Note': f'2026-10-14: "{MARK}" from {frm} - MADE A TASK: triage filed it, but the owner promoted it as real work'})
    put_note(s, {'Scope': 'sender', 'ScopeKey': frm, 'Source': 'manual', 'Active': 1, 'CreatedBy': 't', 'Note': 'OWNERNOTE ask Erin before merging'})

def test_a_stranger_s_seed_keeps_the_owner_s_notes_and_drops_the_quoted_subject():
    s = MemoryStore(); t = _stranger(s, MARK); _notes(s, 'someone@vendor.example')
    seed = terminal.seed_text(s, t)
    assert MARK not in seed and 'OWNERNOTE ask Erin before merging' in seed

def test_an_owner_s_seed_still_carries_every_note():
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
    t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'email'}, 'router')
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'erin@northwind.example', 'Subject': MARK, 'BodyText': 'b', 'Status': 'routed'})
    _notes(s, 'erin@northwind.example')
    seed = terminal.seed_text(s, t)
    assert seed.count(MARK) >= 2 and 'OWNERNOTE' in seed                         # the subject line and the note both
    msgs = [m for m in s.list_messages(t)]
    assert agents.memory_block(s, msgs) == agents.memory_block(s, msgs, owner_only=False)


# ── L6: a floor denial is recorded on the task, an allow is not ────────────────────────────────────────────────
def _hdr(tid):
    srv = config.load()['server']; return {'X-Taskuary-Token': srv['agent_token'], guard.TASK_HDR: guard.task_proof(srv, tid)}

def test_a_floor_denial_is_recorded_on_the_task_with_its_reason(monkeypatch, tmp_path):
    s = MemoryStore(); t = _stranger(s); monkeypatch.setattr(server, 'store', s)
    c = TestClient(server.app)
    with mock.patch.dict(terminal.SESSIONS, {'run-p1': _Live(t, str(tmp_path))}, clear=True):
        body = lambda p: {'tool_name': 'Read', 'tool_input': {'file_path': p}, 'session_id': 'claude-conv-1', 'cwd': str(tmp_path)}
        assert c.post(f'/api/hooks/claude/floor?task={t}', json=body(str(tmp_path / 'app.py')), headers=_hdr(t)).json() == {}
        assert not [e for e in s.worker_events(t) if e['Kind'] == 'floor_denied']
        ws.record(s, t, 'run-p1', 'working', text='go')
        r = c.post(f'/api/hooks/claude/floor?task={t}', json=body(str(home() / 'config.toml')), headers=_hdr(t)).json()
        assert r['hookSpecificOutput']['permissionDecision'] == 'deny'
        ev = [e for e in s.worker_events(t) if e['Kind'] == 'floor_denied']
        assert len(ev) == 1 and ev[0]['Sid'] == 'run-p1' and 'config.toml is a protected file' in ev[0]['Text']
        assert ws.status(s, t)['state'] == 'working'                              # a refusal is a note on the run, not its state

# ── L7: his line on a held task is kept, and nothing claims an agent took it (2026-11-17) ─────────────────────────
# A no-reply sender's task, held for Trust, got Send to agent with a typed line: a session opened, its first turn was refused inside it, the
# line was gone, and the row read "agent done - type to carry on" over a chat no agent had worked. Invented people.
def _held(s):
    t = s.create_task({'Title': 'Your order shipped', 'Kind': 'general', 'Source': 'email', 'Status': 'open'}, 'router')
    s.add_message({'TaskId': t, 'Channel': 'email', 'SourceName': 'alex@northwind.example', 'FromEmail': 'no-reply@vendor.example',
                   'FromName': 'Vendor', 'Subject': 'Shipped', 'BodyText': 'Your order shipped.', 'Status': 'routed'})
    assert origin.hold(s, t); return t

def test_a_line_sent_to_a_held_task_waits_by_the_box_and_starts_nothing(monkeypatch):
    from taskuary import general, funnel, taskstate
    s = MemoryStore(); t = _held(s); monkeypatch.setattr(server, 'store', s); started, opening = [], []
    monkeypatch.setattr(general, 'provider_options', lambda *a, **k: [{'pick': 'cli:claude', 'type': 'cli'}])
    class Ses:
        provider, model, quick = 'Claude Code', '', False
        def send_prompt(self, text, **kw): opening.append(t in general.OPENING)
        def info(self, tail=0): return {'sid': 's1'}
    monkeypatch.setattr(general, 'start_session', lambda *a, **k: started.append(a) or Ses())
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        r = TestClient(server.app).post(f'/api/tasks/{t}/dispatch', json={'kind': 'general', 'instruction': 'Reply and say thanks'})
        assert r.status_code == 200, r.text
        out = r.json()
        assert not out['started'] and out['held'] == origin.hold(s, t)['line']
        assert [w['text'] for w in general.waiting_lines(s, t)] == ['Reply and say thanks'], 'his line is kept'
        assert started == [] and opening == [] and t not in general.OPENING and general.session_for(t) is None
        assert taskstate.state(s, s.get_task(t)) != 'working'

def test_a_chat_session_that_never_ran_a_turn_is_not_done_nor_waiting_on_him(monkeypatch):
    "A session another road opened, whose first turn was refused for the hold: no turn ran, so no 'agent done' and no agent row."
    from taskuary import funnel, taskstate
    s = MemoryStore(); t = _held(s)
    parked = {'taskId': t, 'sid': 'g1', 'agent': 'assistant', 'mode': 'assistant', 'alive': True, 'waiting': True, 'state': 'parked', 'tail': []}
    assert not taskstate.done_for_now(s, s.get_task(t), parked)
    assert funnel.from_agents(s, live_state=[parked]) == []

def test_send_prompt_keeps_the_line_before_it_refuses_for_the_hold():
    from taskuary import general
    s = MemoryStore(); t = _held(s)
    with pytest.raises(origin.RefusedForStranger): general.GeneralSession(s, t).send_prompt('Reply and say thanks')
    assert [w['text'] for w in general.waiting_lines(s, t)] == ['Reply and say thanks']

# ── L8: Trust starts the held agent with his kept line, and a start that breaks is kept on the task (2026-11-17) ──────────
# His Trust on a held task raised TypeError (_spawn took no `vouched`): nobody started, while the chat read "You trusted the sender".
def _held_with_line(monkeypatch):
    from taskuary import general
    s = MemoryStore(); t = _held(s); monkeypatch.setattr(server, 'store', s)
    general.wait_line(s, t, 'Reply and say thanks'); return s, t

def test_trust_with_an_agent_on_the_task_hands_it_the_line_vouched_for(monkeypatch):
    "A session the old dispatch road had opened is still on it (live_agent): Trust hands the thread on, his press its vouch."
    from taskuary import ingest
    s, t = _held_with_line(monkeypatch); got, done = [], threading.Event()
    monkeypatch.setattr(ingest, 'live_agent', lambda *a: 'general')
    monkeypatch.setattr(ingest, 'thread_moved', lambda *a, **k: (got.append((a, k)), done.set()))
    r = TestClient(server.app).post(f'/api/tasks/{t}/trust')
    assert r.status_code == 200 and r.json()['started'] == 'handed', r.text
    assert done.wait(5) and got[0][0][1] == t and got[0][1] == {'vouched': True}

def test_trust_with_no_agent_yet_starts_one_whose_first_turn_takes_his_line(monkeypatch):
    from taskuary import general
    s, t = _held_with_line(monkeypatch); prompts, done = [], threading.Event()
    monkeypatch.setattr(general, 'provider_options', lambda *a, **k: [{'pick': 'cli:claude', 'type': 'cli'}])
    s.set_setting('general_auto_enabled', '1', 't')
    class Ses:
        quick = False
        def send_prompt(self, text, *a, **kw):   # the first turn takes every line still kept with it (GeneralSession.send_prompt, take_kept)
            prompts.append('\n\n'.join([text, *(w['text'] for w in general.waiting_lines(s, t))])); done.set(); return 'ok'
        def info(self, tail=0): return {'sid': 's1'}
    monkeypatch.setattr(general, 'start_session', lambda *a, **k: Ses())
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        r = TestClient(server.app).post(f'/api/tasks/{t}/trust')
        assert r.status_code == 200 and r.json()['started'] == 'started', r.text
        assert done.wait(5) and 'Reply and say thanks' in prompts[0]
    general.OPENING.discard(t)

def test_a_start_trust_makes_that_breaks_is_kept_on_the_task_not_a_500(monkeypatch):
    s, t = _held_with_line(monkeypatch)
    def boom(tid): raise RuntimeError('the CLI would not come up')
    monkeypatch.setattr(server, '_trusted_starts', boom)
    r = TestClient(server.app).post(f'/api/tasks/{t}/trust')
    assert r.status_code == 200 and r.json()['started'] == '', r.text
    assert any('would not come up' in (c['Body'] or '') for c in s.list_comments(t, internal=True)) and s.get_dispatch(t)

def test_trust_pressed_twice_hands_the_waiting_line_over_once(monkeypatch):
    """Pressed twice - a double tap, or the phone and the desk both - the second press found the task trusted and an agent on it, and
    handed the same thread over again: the agent was told the stranger's mail twice. A press that changes nothing starts nothing."""
    from taskuary import ingest
    s, t = _held_with_line(monkeypatch); got = []
    monkeypatch.setattr(ingest, 'live_agent', lambda *a: 'general')
    monkeypatch.setattr(ingest, '_spawn', lambda fn, *a, **k: got.append(fn))
    c = TestClient(server.app)
    assert c.post(f'/api/tasks/{t}/trust').json()['started'] == 'handed'
    again = c.post(f'/api/tasks/{t}/trust')
    assert again.status_code == 200 and again.json()['origin'] == 'trusted'
    assert len(got) == 1, got
    assert again.json()['started']          # ...and it still says an agent has it: the first press's is at work
