"""Every launch road asks where the task's words came from (spec 2026-10-14): a stranger's task runs in the CLI's own
auto mode with a trimmed environment, or is refused; the owner's and trusted work launch exactly as before."""
import json, os, tempfile, threading, pytest
from pathlib import Path
from unittest import mock
from taskuary import terminal, origin, llm, agents, general, floor, workerstate as ws, hooks, ingest, blackboard
from taskuary.store import MemoryStore

# CI's machines have no AI CLI on them: these tests are about what a session is ALLOWED to do, never whether claude is
# installed, so the command resolves to its own name here as it does on a machine that has it (CI, 2026-10-14)
@pytest.fixture(autouse=True)
def _cli_resolves(monkeypatch):
    from taskuary import agents
    monkeypatch.setattr(agents, '_resolve_cmd', lambda name: [str(name)])

@pytest.fixture(autouse=True)
def _claude(monkeypatch, tmp_path):
    monkeypatch.setattr(origin, '_claude_version', lambda cmd='claude': (2, 1, 299))   # nothing here may launch a real claude
    (tmp_path / 'temp').mkdir(); monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path / 'temp'))   # strangers' folders stay in the test's own

def _stranger(s):
    t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'email'}, 'router')
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'someone@vendor.example', 'Status': 'routed'}); return t

def _owner(s): return s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')

def _store(cmd='claude', name='coding'):
    s = MemoryStore(); s.upsert_agent(name, 'coding', 'cli', json.dumps({'cmd': cmd})); return s

def _pane(s, t, tmp_path, agent='coding', **kw):
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
    with pytest.raises(ValueError, match="no built-in reviewer, so it cannot run a stranger's task"):
        terminal.open_session(s, 'g', task_id=t, cwd=str(tmp_path))

def test_an_owner_task_on_that_cli_still_starts(tmp_path):
    s = _store('gemini', 'g'); t = _owner(s)
    _, kw = _pane(s, t, tmp_path, agent='g')
    assert kw.get('mode', 'full') == 'full'

def test_a_stranger_batch_runs_in_auto_mode_like_any_stranger_s_task(tmp_path):
    "A batch an item was judged dangerous in is warned, not locked (the owner, 2026-10-15): auto mode and the floor, as for every stranger."
    from taskuary import batch
    s = _store(); t = _stranger(s)
    with mock.patch.object(batch, 'is_batch', return_value=True):
        argv, kw = _pane(s, t, tmp_path)
    assert argv[argv.index('--permission-mode') + 1] == 'auto' and '--dangerously-skip-permissions' not in argv and kw['mode'] == 'auto'


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

class _Pty:
    "A pty that records how it was made and ends at once - Term's own wiring, no child process."
    made = []
    def __init__(self, argv, cwd, rows, cols, env=None, strict=False): _Pty.made.append(strict)
    def read(self): return ''
    def alive(self): return False
    def write(self, s): pass
    def resize(self, r, c): pass
    def kill(self): pass

def test_a_term_s_mode_decides_its_pty_s_env(tmp_path):
    import sys
    argv = [sys.executable, str(Path(__file__).parent / 'fake_tui.py')]   # the conftest-reviewed fake: nothing unreviewed may reach a pty
    _Pty.made.clear()
    with mock.patch.object(terminal, '_WinPty' if os.name == 'nt' else '_UnixPty', _Pty), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        terminal.Term(argv, str(tmp_path), 't', mode='auto'); terminal.Term(argv, str(tmp_path), 't')
    assert _Pty.made == [True, False]

def test_a_headless_run_trims_its_env_only_when_the_profile_says_so(monkeypatch):
    monkeypatch.setenv('GH_TOKEN', 'y'); monkeypatch.setenv('ANTHROPIC_API_KEY', 'z')
    strict = agents.spawn_env({'strict_env': True}, {'TASKUARY_TASK': '7'})
    assert 'GH_TOKEN' not in strict and strict['ANTHROPIC_API_KEY'] == 'z' and strict['TASKUARY_TASK'] == '7'
    assert agents.spawn_env({}, {'A': '1'}) == agents.child_env({**os.environ, 'A': '1'})


# ── headless and general ─────────────────────────────────────────────────────────────────────────────────────────
def _headless(s, t, **kw):
    brain = llm.make_cli_llm(s, 'coding', cli_tools=True, task_id=t, **kw)
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
    with pytest.raises(ValueError, match='no built-in reviewer'): llm.make_cli_llm(s, 'coding', cli_tools=True, task_id=t)

def test_the_classifier_road_ignores_the_task():
    s = _store('gemini'); t = _stranger(s)
    assert llm.make_cli_llm(s, 'coding', task_id=t)      # no hands: it already runs with every tool off

def test_build_llm_forwards_the_task():
    s = _store(); t = _stranger(s)
    with mock.patch.object(llm, 'make_cli_llm', return_value=lambda *a, **k: 'x') as m: llm.build_llm(s, pick='cli:coding', cli_tools=True, task_id=t)
    assert m.call_args.kwargs['task_id'] == t

def test_a_backup_brain_that_cannot_run_a_stranger_s_task_is_skipped():
    s = _store(); s.upsert_agent('g', 'coding', 'cli', json.dumps({'cmd': 'gemini'})); t = _stranger(s)
    s.set_setting('triage_backup_ai', 'cli:g', 'owner')
    assert llm.build_llm(s, pick='cli:coding', cli_tools=True, task_id=t)

def _general_build(s, t):
    # a general turn runs on a BRAIN - the connected CLI tool - never on a profile
    with mock.patch.object(agents, 'connection_brains', lambda store, cfg=None: [('claude', {'cmd': 'claude'})]),          mock.patch.object(llm, 'build_llm', return_value=lambda *a, **k: 'done') as b, mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        general.start_session(s, t, pick='cli:claude').send_prompt('go', pick='cli:claude')
    return b.call_args.kwargs

def test_a_general_agent_s_turn_names_its_task():
    s = _store(); t = s.create_task({'Title': 'x', 'Kind': 'general', 'Source': 'email'}, 'router')
    assert _general_build(s, t)['task_id'] == t

def test_the_owner_s_guide_chat_is_the_owner_s():
    s = _store(); d, _ = general.dock_task(s)
    assert origin.of_task(s, d['TaskId'])[0] == 'owner'             # assistant-sourced, but the owner's own chat (R15)
    assert _general_build(s, d['TaskId'])['task_id'] == d['TaskId']  # every road names the task; the origin answers for the dock
    s.add_message({'TaskId': d['TaskId'], 'Channel': 'email', 'FromEmail': 'someone@vendor.example', 'Status': 'routed'})
    assert origin.of_task(s, d['TaskId'])[0] == 'stranger'          # a stranger's message on it still lowers it

def _headless_research(s, t):
    brain = llm.make_cli_llm(s, 'coding', research=True, task_id=t)
    with mock.patch.object(agents, 'run_cli', return_value=('ok', 'sid', '')) as run: brain('', 'hi')
    return run.call_args.args[0]

def test_a_stranger_s_research_run_gets_no_tools_a_trimmed_env_and_its_own_folder():
    s = _store(); t = _stranger(s)
    p = _headless_research(s, t); a = p['args']
    assert a[a.index('--tools') + 1] == '' and a[a.index('--disallowedTools') + 1] == 'mcp__*' and 'WebFetch' not in ' '.join(a)
    assert p['strict_env'] is True and Path(p['cwd']) == origin.stranger_path(t)

def test_an_owner_s_research_run_is_unchanged():
    s = _store(); t = _owner(s)
    p = _headless_research(s, t)
    assert p == _headless_research(s, None) and 'WebFetch' in ' '.join(p['args']) and not p.get('strict_env')

def test_a_stranger_s_run_does_not_resume_a_conversation_from_another_folder():
    s = _store(); t = _stranger(s)
    brain = llm.make_cli_llm(s, 'coding', cli_tools=True, task_id=t, resume='owner-sid')
    with mock.patch.object(agents, 'run_cli', return_value=('ok', 'new-sid', '')) as run: brain('', 'hi')
    assert run.call_args.kwargs.get('resume') is None
    brain = llm.make_cli_llm(s, 'coding', cli_tools=True, task_id=t, resume='new-sid')      # its own, from that folder, continues
    with mock.patch.object(agents, 'run_cli', return_value=('ok', 'new-sid', '')) as run: brain('', 'hi')
    assert run.call_args.kwargs.get('resume') == 'new-sid'

def test_an_owner_s_run_resumes_as_before():
    s = _store(); t = _owner(s)
    brain = llm.make_cli_llm(s, 'coding', cli_tools=True, task_id=t, resume='owner-sid')
    with mock.patch.object(agents, 'run_cli', return_value=('ok', 'owner-sid', '')) as run: brain('', 'hi')
    assert run.call_args.kwargs.get('resume') == 'owner-sid' and not s.get_setting(f'stranger_sid:{t}')   # and nothing written for it

def test_only_the_stranger_refusal_skips_a_backup_brain():
    assert issubclass(origin.RefusedForStranger, ValueError)
    s = _store(); s.upsert_agent('g', 'coding', 'cli', json.dumps({'cmd': 'gemini'})); t = _stranger(s); s.set_setting('triage_backup_ai', 'cli:g', 'owner')
    real = llm.make_cli_llm
    def boom(store, name, *a, **k):
        if name == 'g': raise ValueError('a broken profile')
        return real(store, name, *a, **k)
    with mock.patch.object(llm, 'make_cli_llm', side_effect=boom), pytest.raises(ValueError, match='a broken profile'):
        llm.build_llm(s, pick='cli:coding', cli_tools=True, task_id=t)


# ── the stranger's folder cannot be planted ──────────────────────────────────────────────────────────────────────
def _link(src, dst):
    if os.name == 'nt': import _winapi; _winapi.CreateJunction(str(src), str(dst))   # what another account could plant, no privilege needed
    else: os.symlink(src, dst)

def test_a_planted_link_for_the_task_s_folder_refuses_the_launch(tmp_path):
    s = _store(); t = _stranger(s)
    target = tmp_path / 'secret'; target.mkdir(); origin.stranger_path(t).parent.mkdir(parents=True, exist_ok=True)
    _link(target, origin.stranger_path(t))
    with pytest.raises(ValueError, match='folder'): llm.make_cli_llm(s, 'coding', cli_tools=True, task_id=t)
    with pytest.raises(origin.Refusal): origin.stranger_dir(t)
    assert not any(o == floor._norm(target, real=True) or o.startswith(floor._norm(target, real=True) + '/') for o in floor._own(t, s))

def test_the_floor_s_own_list_creates_nothing():
    floor._own(4242)
    assert not origin.stranger_path(4242).exists()

@pytest.mark.skipif(os.name == 'nt', reason='POSIX modes')
def test_the_strangers_root_is_private():
    origin.stranger_dir(7)
    assert (origin.stranger_path(7).parent.stat().st_mode & 0o077) == 0

def test_auto_args_drop_every_bypass_spelling():
    from taskuary import clis
    for extra in (['--dangerously-skip-permissions'], ['--allow-dangerously-skip-permissions'], ['--permission-mode', 'bypassPermissions'],
                  ['--permission-mode=bypassPermissions'], ['--permission-mode', 'acceptEdits']):
        a = clis.auto_args('claude', ['-p', *extra, '--output-format', 'stream-json'])
        assert a.count('--permission-mode') == 1 and a[a.index('--permission-mode') + 1] == 'auto', extra
        assert not any('dangerously' in x or x.startswith('--permission-mode=') or x in ('bypassPermissions', 'acceptEdits') for x in a), extra
        assert a[:3] == ['-p', '--output-format', 'stream-json']

def test_the_strict_env_keeps_what_a_cli_signs_in_and_runs_with(monkeypatch):
    keep = ('ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDE_CODE_USE_BEDROCK', 'AWS_REGION', 'TMPDIR', 'PSMODULEPATH')
    for k in keep: monkeypatch.setenv(k, 'v')
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'k')
    up = lambda e: {k.upper(): v for k, v in e.items()}
    headless = up(agents.spawn_env({'strict_env': True}))
    assert all(headless.get(k) == 'v' for k in keep) and 'AWS_ACCESS_KEY_ID' not in headless
    pane, owner = up(terminal.clean_env(strict=True)), up(terminal.clean_env())
    assert 'AWS_ACCESS_KEY_ID' not in pane and all(pane.get(k) == 'v' for k in ('ANTHROPIC_AUTH_TOKEN', 'AWS_REGION', 'TMPDIR', 'PSMODULEPATH'))
    # a pane strips CLAUDE_CODE* for everyone (a fresh session, _DIRTY): the strict list never gives a stranger more than the owner gets
    assert all((k in pane) == (k in owner) for k in keep)

def test_the_pane_takes_the_theme_from_any_settings_spelling_and_keeps_one(tmp_path):
    s = _store(); t = _stranger(s)
    f = tmp_path / 'theme.json'; f.write_text('{"theme": "dark"}', encoding='utf-8'); g = tmp_path / 'other.json'; g.write_text('{}', encoding='utf-8')
    s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude', 'args': [f'--settings={g}', '--settings', str(f)]}))
    argv, _ = _pane(s, t, tmp_path)
    assert argv.count('--settings') == 1 and not any(str(x).startswith('--settings=') for x in argv)
    assert json.loads(Path(argv[argv.index('--settings') + 1]).read_text(encoding='utf-8')).get('theme') == 'dark'


# ── the floor follows the folder ─────────────────────────────────────────────────────────────────────────────────
def test_the_stranger_folder_passes_the_floor_and_another_task_s_does_not():
    mine, theirs = origin.stranger_path(7), origin.stranger_path(8)
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
    s = _store('gemini'); t = _stranger(s); s.set_setting('default_brain', 'gemini', 'owner')     # the coding brain is the CLI, not the profile
    monkeypatch.setattr(blackboard, 'drain_later', lambda *a, **k: None)
    with mock.patch.object(terminal, 'Term'), mock.patch.dict(terminal.SESSIONS, {}, clear=True): ingest._auto_code(s, t)   # never raises into the poller
    said = ' '.join(c['Body'] for c in s.list_comments(t))
    assert 'no built-in reviewer' in said and 'Start fails the same way until it is fixed' in said and 'try again' not in said

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

@pytest.mark.skipif(os.name != 'nt', reason='8.3 names')
def test_the_folder_passes_in_its_long_name_when_temp_is_a_short_one(monkeypatch, tmp_path):
    import ctypes
    long_ = tmp_path / 'temp' / 'a-long-folder-name'; long_.mkdir()
    buf = ctypes.create_unicode_buffer(600); ctypes.windll.kernel32.GetShortPathNameW(str(long_), buf, 600)
    if not buf.value or buf.value.lower() == str(long_).lower(): pytest.skip('no 8.3 names on this volume')
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: buf.value)          # TEMP as Windows often sets it
    d = origin.stranger_dir(7)
    for p in (d / 'notes.md', Path(os.path.realpath(d)) / 'notes.md'):
        assert floor.check({'tool_name': 'Read', 'tool_input': {'file_path': str(p)}}, 7) == {}, p
