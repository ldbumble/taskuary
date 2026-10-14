"""Every launch road asks where the task's words came from (spec 2026-10-14): a stranger's task runs in the CLI's own
auto mode with a trimmed environment, or is refused; the owner's and trusted work launch exactly as before."""
import json, os, inspect, tempfile, threading, pytest
from pathlib import Path
from unittest import mock
from taskuary import terminal, origin, llm, agents, general, floor, workerstate as ws, hooks, ingest, blackboard
from taskuary.store import MemoryStore

@pytest.fixture(autouse=True)
def _claude(monkeypatch):
    monkeypatch.setattr(origin, '_claude_version', lambda: (2, 1, 299))   # nothing here may launch a real claude

def _stranger(s):
    t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'email'}, 'router')
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'someone@vendor.example', 'Status': 'routed'}); return t

def _owner(s): return s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')

def _store(cmd='claude', name='coder'):
    s = MemoryStore(); s.upsert_agent(name, 'coding', 'cli', json.dumps({'cmd': cmd})); return s

def _pane(s, t, tmp_path, agent='coder', **kw):
    with mock.patch.object(terminal, 'Term') as T, mock.patch.dict(terminal.SESSIONS, {}, clear=True):   # no stand-in outlives the test
        terminal.open_session(s, agent, task_id=t, cwd=str(tmp_path), **kw)
    return T.call_args.args[0], T.call_args.kwargs


# ── the pane ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_stranger_s_pane_starts_in_auto_mode_with_its_settings_and_a_trimmed_env(tmp_path):
    s = _store(); t = _stranger(s)
    argv, kw = _pane(s, t, tmp_path)
    assert '--dangerously-skip-permissions' not in argv and argv[argv.index('--permission-mode') + 1] == 'auto' and '--strict-mcp-config' in argv
    assert argv.count('--settings') == 1 and argv[argv.index('--settings') + 1] == origin.session_settings(s, t)
    assert kw['mode'] == 'auto'

def test_the_stranger_s_settings_keep_the_owner_s_pane_theme(tmp_path):
    s = _store(); t = _stranger(s); s.set_setting('pane_theme', 'dark', 'owner')
    argv, _ = _pane(s, t, tmp_path)
    assert json.loads(Path(argv[argv.index('--settings') + 1]).read_text(encoding='utf-8')).get('theme') == 'dark'

def test_an_owner_pane_is_unchanged(tmp_path):
    s = _store(); t = _owner(s)
    argv, kw = _pane(s, t, tmp_path)
    assert '--dangerously-skip-permissions' in argv and '--permission-mode' not in argv and kw.get('mode', 'full') == 'full'
    base, _ = _pane(s, None, tmp_path)          # the same launch as a pane with no task behind it, flag for flag
    strip = lambda a: [x for i, x in enumerate(a) if not (i and a[i - 1] in ('--session-id',)) and x != '--session-id']
    assert strip(argv) == strip(base)

def test_a_pane_on_the_owner_s_own_mail_is_unchanged(tmp_path):
    s = _store(); t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'email'}, 'router')
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'erin@northwind.example', 'Direction': 'out', 'Status': 'routed'})
    argv, kw = _pane(s, t, tmp_path)
    assert '--dangerously-skip-permissions' in argv and kw.get('mode', 'full') == 'full'

def test_a_resumed_stranger_pane_stays_in_auto_mode(tmp_path):
    s = _store(); t = _stranger(s)
    argv, kw = _pane(s, t, tmp_path, resume='abc')
    assert '--dangerously-skip-permissions' not in argv and 'auto' in argv and kw['mode'] == 'auto'

def test_a_stranger_s_task_on_a_cli_with_no_reviewer_is_refused(tmp_path):
    s = _store('gemini', 'g'); t = _stranger(s)
    with pytest.raises(ValueError, match="no built-in reviewer, so it cannot run a stranger's task - start it with claude"):
        terminal.open_session(s, 'g', task_id=t, cwd=str(tmp_path))

def test_an_owner_task_on_that_cli_still_starts(tmp_path):
    s = _store('gemini', 'g'); t = _owner(s)
    _, kw = _pane(s, t, tmp_path, agent='g')
    assert kw.get('mode', 'full') == 'full'

def test_a_dangerous_stranger_batch_stays_read_only(tmp_path):
    from taskuary import batch
    s = _store(); t = _stranger(s)
    with mock.patch.object(batch, 'is_batch', return_value=True), mock.patch.object(batch, 'locked', return_value=True):
        argv, kw = _pane(s, t, tmp_path)
    assert argv[argv.index('--permission-mode') + 1] == 'dontAsk' and 'auto' not in argv and '--dangerously-skip-permissions' not in argv
    assert kw['mode'] == 'auto'


# ── the environment ──────────────────────────────────────────────────────────────────────────────────────────────
def test_the_strict_env_keeps_the_cli_s_key_and_drops_the_rest(monkeypatch):
    for k, v in (('AWS_SECRET_ACCESS_KEY', 'x'), ('GH_TOKEN', 'y'), ('ANTHROPIC_API_KEY', 'z'), ('LC_ALL', 'C')): monkeypatch.setenv(k, v)
    env = terminal.clean_env({'TASKUARY_TASK': '7'}, strict=True)
    assert 'AWS_SECRET_ACCESS_KEY' not in env and 'GH_TOKEN' not in env and env['ANTHROPIC_API_KEY'] == 'z' and env['TASKUARY_TASK'] == '7'
    assert 'PATH' in {k.upper() for k in env} and env['LC_ALL'] == 'C'

def test_the_owner_s_env_is_unchanged(monkeypatch):
    monkeypatch.setenv('GH_TOKEN', 'y')
    assert terminal.clean_env({'A': '1'}) == terminal.clean_env({'A': '1'}, strict=False) and terminal.clean_env()['GH_TOKEN'] == 'y'

def test_a_pane_s_pty_takes_the_strict_env_from_its_mode():
    seen = []
    with mock.patch.object(terminal, 'clean_env', side_effect=lambda e=None, strict=False: seen.append(strict) or {}):
        if os.name == 'nt':
            with mock.patch('winpty.PtyProcess.spawn'): terminal._WinPty(['x'], '.', 10, 10, {}, True); terminal._WinPty(['x'], '.', 10, 10, {})
        else:
            with mock.patch.object(terminal.subprocess, 'Popen'), mock.patch.object(terminal.os, 'close'):
                terminal._UnixPty(['x'], '.', 10, 10, {}, True); terminal._UnixPty(['x'], '.', 10, 10, {})
    assert seen == [True, False]
    # conftest guards Term.__init__ (no unreviewed pty), so the wiring is read from the source
    assert "mode == 'auto'" in inspect.getsource(terminal.Term)

def test_a_headless_run_trims_its_env_only_when_the_profile_says_so(monkeypatch):
    monkeypatch.setenv('GH_TOKEN', 'y'); monkeypatch.setenv('ANTHROPIC_API_KEY', 'z')
    strict = agents.spawn_env({'strict_env': True}, {'TASKUARY_TASK': '7'})
    assert 'GH_TOKEN' not in strict and strict['ANTHROPIC_API_KEY'] == 'z' and strict['TASKUARY_TASK'] == '7'
    assert agents.spawn_env({}, {'A': '1'}) == agents.child_env({**os.environ, 'A': '1'})


# ── headless and general ─────────────────────────────────────────────────────────────────────────────────────────
def _headless(s, t, **kw):
    brain = llm.make_cli_llm(s, 'coder', cli_tools=True, task_id=t, **kw)
    with mock.patch.object(agents, 'run_cli', return_value=('ok', 'sid', '')) as run: brain('', 'hi')
    return run.call_args.args[0]

def test_a_stranger_s_headless_run_is_in_auto_mode_in_its_own_folder_outside_taskuary():
    s = _store(); t = _stranger(s)
    p = _headless(s, t)
    a = p['args']
    assert '--dangerously-skip-permissions' not in a and a[a.index('--permission-mode') + 1] == 'auto' and '--settings' in a
    assert p['strict_env'] is True and not p.get('acp_ok')
    assert Path(p['cwd']) == origin.stranger_dir(t) and origin.stranger_dir(t).is_dir()
    assert origin.stranger_dir(t).parent == Path(tempfile.gettempdir()) / 'taskuary-stranger'

def test_an_owner_s_headless_run_is_unchanged():
    s = _store(); t = _owner(s)
    assert _headless(s, t) == _headless(s, None)

def test_a_stranger_s_headless_run_on_a_cli_with_no_reviewer_is_refused():
    s = _store('gemini'); t = _stranger(s)
    with pytest.raises(ValueError, match='no built-in reviewer'): llm.make_cli_llm(s, 'coder', cli_tools=True, task_id=t)

def test_the_classifier_road_ignores_the_task():
    s = _store('gemini'); t = _stranger(s)
    assert llm.make_cli_llm(s, 'coder', task_id=t)      # no hands: it already runs with every tool off

def test_build_llm_forwards_the_task():
    s = _store(); t = _stranger(s)
    with mock.patch.object(llm, 'make_cli_llm', return_value=lambda *a, **k: 'x') as m: llm.build_llm(s, pick='cli:coder', cli_tools=True, task_id=t)
    assert m.call_args.kwargs['task_id'] == t

def test_a_backup_brain_that_cannot_run_a_stranger_s_task_is_skipped():
    s = _store(); s.upsert_agent('g', 'coding', 'cli', json.dumps({'cmd': 'gemini'})); t = _stranger(s)
    s.set_setting('triage_backup_ai', 'cli:g', 'owner')
    assert llm.build_llm(s, pick='cli:coder', cli_tools=True, task_id=t)

def _general_build(s, t):
    with mock.patch.object(llm, 'build_llm', return_value=lambda *a, **k: 'done') as b, mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        general.start_session(s, t, pick='cli:coder').send_prompt('go', pick='cli:coder')
    return b.call_args.kwargs

def test_a_general_agent_s_turn_names_its_task():
    s = _store(); t = s.create_task({'Title': 'x', 'Kind': 'general', 'Source': 'email'}, 'router')
    assert _general_build(s, t)['task_id'] == t

def test_the_owner_s_guide_chat_is_not_a_stranger_s_task():
    s = _store(); d, _ = general.dock_task(s)
    assert origin.of_task(s, d['TaskId'])[0] == 'stranger'          # an assistant-sourced task, by the origin rules...
    assert _general_build(s, d['TaskId']).get('task_id') is None    # ...but the dock is the owner's own chat, so it launches as before


# ── the floor follows the folder ─────────────────────────────────────────────────────────────────────────────────
def test_the_stranger_folder_passes_the_floor_and_another_task_s_does_not():
    mine, theirs = origin.stranger_dir(7), origin.stranger_dir(8)
    assert floor.check({'tool_name': 'Read', 'tool_input': {'file_path': str(mine / 'notes.md')}}, 7) == {}
    assert floor.check({'tool_name': 'Bash', 'cwd': str(mine), 'tool_input': {'command': 'cat ./notes.md'}}, 7) == {}
    r = floor.check({'tool_name': 'Read', 'tool_input': {'file_path': str(theirs / 'notes.md')}}, 7)
    assert r.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny'


# ── doors that type and doors that wait ──────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('mode', ['', 'full', 'weird'])
def test_a_stranger_s_line_reaches_only_an_auto_session(monkeypatch, mode):
    s = MemoryStore(); t = _stranger(s); typed = []
    monkeypatch.setattr(terminal, 'say_to_task', lambda *a, **k: typed.append(a)); monkeypatch.setattr(terminal, 'mode_of_task', lambda tid: mode)
    ingest._hand_to_agent(s, {'answer_to_agent': 'auto'}, t, {'from_email': 'someone@vendor.example'}, 'router')
    assert typed == []

def test_an_auto_start_that_is_refused_says_so_on_the_task_and_does_not_retry(monkeypatch):
    s = _store('gemini'); t = _stranger(s)
    monkeypatch.setattr(blackboard, 'drain_later', lambda *a, **k: None)
    with mock.patch.object(terminal, 'Term'), mock.patch.dict(terminal.SESSIONS, {}, clear=True): ingest._auto_code(s, t)   # never raises into the poller
    said = ' '.join(c['Body'] for c in s.list_comments(t))
    assert 'no built-in reviewer' in said and 'no automatic retry' in said

def test_release_all_wakes_a_held_permit_with_a_deny():
    s = MemoryStore(); t = _stranger(s); out = []
    th = threading.Thread(target=lambda: out.append(hooks.permit({'tool_name': 'Bash', 'tool_input': {'command': 'ls'}, 'session_id': 's1'}, t, store=s)))
    th.daemon = True; th.start()
    try:
        for _ in range(200):
            if ws.held_for(t): break
            threading.Event().wait(0.01)
        assert ws.release_all() and (th.join(5) or not th.is_alive())
    finally: ws.release(t)      # a failing assertion must not leave the run waiting on the hold
    assert out[0]['hookSpecificOutput']['decision']['behavior'] == 'deny'

def test_closing_the_app_releases_its_permits_and_leaves_a_fresh_pool():
    from taskuary import server
    old = server._PERMIT_POOL; ws.hold(5, 's', 'grp-close', ['grp-close:1'])
    try:
        server._close_permits()
        assert ws.HELD['grp-close']['released'] and ws.HELD['grp-close']['event'].is_set()
        assert server._PERMIT_POOL is not old and old._shutdown and server._PERMIT_POOL.submit(lambda: 1).result(5) == 1
    finally: ws.HELD.pop('grp-close', None)
