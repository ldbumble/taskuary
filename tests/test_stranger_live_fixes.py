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
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'someone@vendor.example', 'Subject': subject, 'BodyText': 'b', 'Status': 'routed'}); return t

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
