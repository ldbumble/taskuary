"""A stranger's session never holds the shared agent token (R28): it carries a token bound to its own task, and the
gate lets that token read its task and use its task's doors - nothing else. Owner and agent access is untouched."""
import json, os, sys, tempfile, pytest
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import guard, server, terminal, origin, llm, agents, floor, cli, wrapup, selfclose, hooks
from taskuary.store import MemoryStore

# CI's machines have no AI CLI on them: these tests are about what a session is ALLOWED to do, never whether claude is
# installed, so the command resolves to its own name here as it does on a machine that has it (CI, 2026-10-14)
@pytest.fixture(autouse=True)
def _cli_resolves(monkeypatch):
    from taskuary import agents
    monkeypatch.setattr(agents, '_resolve_cmd', lambda name: [str(name)])

c = TestClient(server.app)
SRV = lambda: server.cfg['server']
ST = lambda tid: {'X-Taskuary-Token': guard.stranger_token(SRV(), tid)}
AGENT = lambda tid=None: {'X-Taskuary-Token': SRV()['agent_token'], **({guard.TASK_HDR: guard.task_proof(SRV(), tid)} if tid else {})}

@pytest.fixture(autouse=True)
def _claude(monkeypatch, tmp_path):
    monkeypatch.setattr(origin, '_claude_version', lambda cmd='claude': (2, 1, 300))   # nothing here may launch a real claude
    (tmp_path / 'temp').mkdir(); monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path / 'temp'))

def _task(s=None, frm='someone@vendor.example'):
    s = s or server.store
    t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'email'}, 'router')
    mid = s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': frm, 'Status': 'routed'}); return t, mid


# ── the token ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_token_names_its_task_and_only_this_server_can_mint_it():
    srv = {'agent_token': 'k1'}; tok = guard.stranger_token(srv, 7)
    assert tok.startswith('s1.7.') and guard.stranger_tid(srv, tok) == 7
    assert guard.stranger_tid({'agent_token': 'k2'}, tok) is None                       # another install's secret
    assert guard.stranger_tid(srv, tok.replace('s1.7.', 's1.8.')) is None               # the task id is in the MAC
    assert guard.stranger_tid(srv, tok[:-1] + ('0' if tok[-1] != '0' else '1')) is None
    for bad in ('', None, 'k1', 's1.7.', 's1.x.' + 'a' * 32, 's1.7.' + '\xe9' * 32): assert guard.stranger_tid(srv, bad) is None
    assert guard.stranger_token({}, 7) == '' and guard.stranger_tid({}, 's1.7.' + 'a' * 32) is None
    assert tok != guard.task_proof(srv, 7) and guard.task_proof(srv, 7) not in tok      # not the owner-agent session's proof

def test_the_scope_of_a_stranger_token_is_stranger_and_the_others_are_as_before():
    srv = {'agent_token': 'k1', 'token': 'own'}
    assert guard.scope_of(srv, {'X-Taskuary-Token': guard.stranger_token(srv, 7)}) == guard.STRANGER
    assert guard.scope_of(srv, {'X-Taskuary-Token': 'k1'}) == guard.AGENT
    assert guard.scope_of(srv, {'X-Taskuary-Token': 'own'}) == guard.OWNER
    assert guard.scope_of(srv, {'X-Taskuary-Token': 'nope'}) == guard.ANON
    assert guard.scope_of({'agent_token': 'k1'}, {'X-Taskuary-Token': guard.stranger_token(srv, 7)}) == guard.STRANGER   # even with no owner token

def test_the_stranger_table():
    d = lambda m, p, q=None, of=None: guard.stranger_denied(m, p, q or {}, 7, of or (lambda k, a: None))
    assert not d('GET', '/api/tasks/7') and not d('GET', '/api/tasks/7/work') and not d('HEAD', '/api/tasks/7/proof')
    assert d('GET', '/api/tasks/8') and d('GET', '/api/tasks/70') and d('GET', '/api/tasks') and d('GET', '/api/tasks/7/../8')
    for p in ('/api/feed', '/api/messages/3', '/api/connectors', '/api/settings', '/api/docs/soul', '/api/search', '/api/terminals',
              '/api/hub', '/api/board/notes', '/api/send-targets', '/api/funnel'):
        assert d('GET', p), p
    assert not d('POST', '/api/hooks/claude/floor', {'task': '7'}) and not d('POST', '/api/hooks/claude/permit', {'task': '7'})
    assert d('POST', '/api/hooks/claude/floor', {'task': '8'}) and d('POST', '/api/hooks/claude/permit', {})
    assert not d('POST', '/api/hooks/claude') and not d('POST', '/api/agent/reply') and not d('POST', '/api/agent/done')
    assert not d('POST', '/api/board/notes') and d('POST', '/api/board/notes/3/read')   # a note, pinned to its own task (wave B)
    for p in ('/api/hub', '/api/tools/run', '/api/reports/3/rerun', '/api/hooks/claude/ask', '/api/tasks/7/trust',
              '/api/reviews/3/decide', '/api/tasks/7/comments', '/api/terminals'):
        assert d('POST', p), p
    of = lambda k, a: {('attachment', 5): 7, ('attachment', 6): 8, ('artifact', 9): 7}.get((k, a))
    assert not d('GET', '/api/attachments/5', of=of) and d('GET', '/api/attachments/6', of=of) and d('GET', '/api/attachments/99', of=of)
    assert not d('GET', '/api/task-artifacts/9', of=of) and d('GET', '/api/task-artifacts/5', of=of)


# ── the gate ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_stranger_token_reads_its_own_task_and_nothing_else():
    t, _ = _task(); other, _ = _task()
    assert c.get(f'/api/tasks/{t}', headers=ST(t)).status_code == 200
    assert c.get(f'/api/tasks/{other}', headers=ST(t)).status_code == 403
    for p in ('/api/feed', '/api/messages', '/api/connectors', '/api/settings', '/api/docs/soul', '/api/search?q=x', '/api/terminals',
              '/api/tasks', '/api/hub', '/api/board/notes', f'/api/messages/{_}'):
        assert c.get(p, headers=ST(t)).status_code == 403, p

def test_a_stranger_token_reaches_only_its_own_task_s_attachments(tmp_path):
    t, mid = _task(); other, omid = _task()
    a = server.store.add_attachment({'MessageId': mid, 'Name': 'a.txt', 'ContentType': 'text/plain'})
    b = server.store.add_attachment({'MessageId': omid, 'Name': 'b.txt', 'ContentType': 'text/plain'})
    assert c.get(f'/api/attachments/{a}', headers=ST(t)).status_code == 404     # through the gate: never saved, so not found
    assert c.get(f'/api/attachments/{b}', headers=ST(t)).status_code == 403

def test_a_stranger_token_uses_its_own_task_s_doors(monkeypatch):
    t, _ = _task(); other, _ = _task()
    monkeypatch.setattr(floor, 'check', lambda p, tid, store=None: {})
    assert c.post(f'/api/hooks/claude/floor?task={t}', json={}, headers=ST(t)).status_code == 200
    assert c.post(f'/api/hooks/claude/floor?task={other}', json={}, headers=ST(t)).status_code == 403
    monkeypatch.setattr(wrapup, 'agent_reply', lambda s, tid, text, agent, files=(), follow_up=False: {'ok': True, 'tid': tid})
    assert c.post('/api/agent/reply', json={'task_id': t, 'text': 'hi'}, headers=ST(t)).json() == {'ok': True, 'tid': t}
    assert c.post('/api/agent/reply', json={'task_id': other, 'text': 'hi'}, headers=ST(t)).status_code == 403
    assert c.post('/api/hooks/claude', json={}, headers=ST(t)).status_code == 200
    for p in ('/api/hub', '/api/tools/run', f'/api/tasks/{t}/comments'):
        assert c.post(p, json={'body': 'x', 'title': 'x'}, headers=ST(t)).status_code == 403, p

def test_a_permit_takes_the_stranger_token_for_its_own_task(monkeypatch):
    from taskuary import hooks
    t, _ = _task(); other, _ = _task()
    monkeypatch.setattr(hooks, 'permit', lambda p, tid, wait=None, store=None: {'tid': tid})
    assert c.post(f'/api/hooks/claude/permit?task={t}', json={}, headers=ST(t)).json() == {'tid': t}
    assert c.post(f'/api/hooks/claude/permit?task={other}', json={}, headers=ST(t)).status_code == 403
    assert c.post(f'/api/hooks/claude/permit?task={t}', json={}, headers=AGENT(t)).json() == {'tid': t}   # agent + proof still

def test_a_stranger_token_opens_no_socket(monkeypatch):
    class W: headers, query_params = {'host': '127.0.0.1:7787'}, {}
    t, _ = _task(); W.query_params = {'token': guard.stranger_token(SRV(), t)}
    monkeypatch.setitem(server.cfg['server'], 'token', '')            # the open, token-less install: still not a stranger's
    assert server._ws_ok(W) is False
    W.query_params = {}; assert server._ws_ok(W) is True

def test_owner_and_agent_access_is_unchanged():
    t, mid = _task()
    for p in ('/api/settings', '/api/connectors', f'/api/messages/{mid}', '/api/tasks'):
        assert c.get(p).status_code == 200, p                          # the owner (conftest's default header)
        assert c.get(p, headers=AGENT()).status_code == 200, p         # the shared agent token, no proof: owner sessions rely on it
    assert c.post('/api/board/notes', json={'body': 'a line for the others', 'agent': 'coding'}, headers=AGENT()).status_code != 403
    assert c.post('/api/reviews/1/decide', json={'verb': 'approve'}, headers=AGENT()).status_code == 403


# ── the session's environment ───────────────────────────────────────────────────────────────────────────────────────
def test_a_stranger_session_env_carries_the_stranger_token_and_never_the_shared_one():
    shared = SRV()['agent_token']
    with mock.patch('taskuary.config.load', return_value=server.cfg):
        own, st = terminal.session_env('coding', 7, 'C:/w'), terminal.session_env('coding', 7, 'C:/w', stranger=True)
    assert own[guard.AGENT_ENV] == shared and own[guard.TASK_ENV] == guard.task_proof(SRV(), 7)     # the owner's: as before
    assert st[guard.AGENT_ENV] == guard.stranger_token(SRV(), 7) and guard.TASK_ENV not in st
    assert shared not in json.dumps(st) and st['TASKUARY_TASK'] == '7' and st['TASKUARY_URL']

class _Pty:
    made = []
    def __init__(self, argv, cwd, rows, cols, env=None, strict=False): _Pty.made.append((env or {}, strict))
    def read(self): return ''
    def alive(self): return False
    def write(self, s): pass
    def resize(self, r, c): pass
    def kill(self): pass

def test_a_term_in_auto_mode_hands_its_pty_the_stranger_token(tmp_path):
    argv = [sys.executable, str(Path(__file__).parent / 'fake_tui.py')]
    _Pty.made.clear(); shared = SRV()['agent_token']
    with mock.patch.object(terminal, '_WinPty' if os.name == 'nt' else '_UnixPty', _Pty), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
            mock.patch('taskuary.config.load', return_value=server.cfg):
        terminal.Term(argv, str(tmp_path), 't', 7, 'coding', mode='auto'); terminal.Term(argv, str(tmp_path), 't', 7, 'coding')
    (st, strict), (own, full) = _Pty.made
    assert strict and st[guard.AGENT_ENV] == guard.stranger_token(SRV(), 7) and shared not in json.dumps(st)
    assert not full and own[guard.AGENT_ENV] == shared and own[guard.TASK_ENV] == guard.task_proof(SRV(), 7)

def _store(cmd='claude'):
    s = MemoryStore(); s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': cmd})); return s

def _headless(s, t, **kw):
    brain = llm.make_cli_llm(s, 'coding', cli_tools=True, task_id=t, **kw)
    with mock.patch.object(agents, 'run_cli', return_value=('ok', 'sid', '')) as run, mock.patch('taskuary.config.load', return_value=server.cfg):
        brain('', 'hi')
    return run.call_args

def test_a_stranger_s_headless_run_gets_the_stranger_token_in_place_of_the_shared_one():
    s = _store(); t, _ = _task(s); shared = SRV()['agent_token']
    with mock.patch('taskuary.config.load', return_value=server.cfg): passed = terminal.session_env('assistant', t)
    for kw in ({}, {'extra_env': passed}):
        env = _headless(s, t, **kw).kwargs['extra_env']
        assert env[guard.AGENT_ENV] == guard.stranger_token(SRV(), t) and guard.TASK_ENV not in env and shared not in json.dumps(env), kw
        assert env['TASKUARY_TASK'] == str(t)

def test_an_owner_s_headless_run_keeps_its_env_as_passed():
    s = _store(); t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')
    passed = {guard.AGENT_ENV: 'shared', 'X': '1'}
    assert _headless(s, t, extra_env=passed).kwargs['extra_env'] == passed
    assert 'extra_env' not in _headless(s, t).kwargs

def test_the_session_settings_hooks_carry_the_stranger_token():
    s = MemoryStore(); t, _ = _task(s); shared = SRV()['agent_token']
    with mock.patch('taskuary.config.load', return_value=server.cfg): f = origin.session_settings(s, t)
    text = Path(f).read_text(encoding='utf-8')
    with mock.patch('taskuary.config.load', return_value=server.cfg): hdr = hooks.header_file(guard.stranger_token(SRV(), t))
    # by file, the stranger's own token: neither it nor the shared one is in the settings the CLI's hooks run from
    assert f'@{hdr}' in text and guard.stranger_token(SRV(), t) not in text and shared not in text and guard.TASK_HDR not in text

def test_taskuary_reply_from_a_stranger_session_authenticates_with_its_token(monkeypatch):
    t, _ = _task()
    with mock.patch('taskuary.config.load', return_value=server.cfg): env = terminal.session_env('coding', t, stranger=True)
    for k, v in env.items(): monkeypatch.setenv(k, v)
    monkeypatch.delenv(guard.TASK_ENV, raising=False)
    from taskuary import config
    hdr = cli._session_headers(config.load()['server'])
    assert hdr == {'X-Taskuary-Token': guard.stranger_token(SRV(), t)}
    monkeypatch.setattr(selfclose, 'declare', lambda s, tid, summary, agent, no_reply=False: {'closed': True, 'tid': tid})
    assert c.post('/api/agent/done', json={'task_id': t, 'summary': 'done'}, headers=hdr).json() == {'closed': True, 'tid': t}


# ── the strict env keeps where Taskuary is ──────────────────────────────────────────────────────────────────────────
def test_the_strict_env_keeps_taskuary_s_home_and_address(monkeypatch):
    monkeypatch.setenv('TASKUARY_HOME', 'C:/elsewhere'); monkeypatch.setenv('TASKUARY_PORT', '7795'); monkeypatch.setenv('GH_TOKEN', 'y')
    for env in (agents.spawn_env({'strict_env': True}), terminal.clean_env({}, strict=True)):
        assert env['TASKUARY_HOME'] == 'C:/elsewhere' and env['TASKUARY_PORT'] == '7795' and 'GH_TOKEN' not in env
        assert guard.AGENT_ENV not in env                              # the process's own token is never inherited by a stranger


# ── fix round 1: only the routes a restricted session needs, the floor on a locked batch, the socket header ─────────
def test_the_stranger_reads_only_the_named_parts_of_its_task():
    d = lambda p: guard.stranger_denied('GET', p, {}, 7, lambda k, a: None)
    for p in ('', '/history', '/worker', '/proof', '/work', '/diff', '/record', '/waitroom'):
        assert not d(f'/api/tasks/7{p}'), p
    for p in ('/merge-candidates', '/repos', '/steps', '/split/suggest', '/assistant', '/anything-new'):   # other tasks, checkouts, a model call
        assert d(f'/api/tasks/7{p}'), p

def test_the_leaky_task_routes_are_refused_over_http():
    t, _ = _task()
    for p in ('merge-candidates', 'repos', 'steps', 'split/suggest'):
        assert c.get(f'/api/tasks/{t}/{p}', headers=ST(t)).status_code == 403, p
    for p in ('history', 'worker', 'waitroom'):
        assert c.get(f'/api/tasks/{t}/{p}', headers=ST(t)).status_code == 200, p

def test_a_stranger_token_in_the_socket_header_is_refused_on_a_tokened_install(monkeypatch):
    t, _ = _task(); monkeypatch.setitem(server.cfg['server'], 'token', 'owner-tok')     # tokened, whatever an earlier test left
    class W: headers, query_params = {'host': '127.0.0.1:7787', 'x-taskuary-token': guard.stranger_token(SRV(), t)}, {}
    assert server.cfg['server'].get('token') and server._ws_ok(W) is False
    W.headers = {'host': '127.0.0.1:7787', 'x-taskuary-token': SRV()['token']}; assert server._ws_ok(W) is True

def _pane(s, t, tmp_path):
    with mock.patch.object(terminal, 'Term') as T, mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        terminal.open_session(s, 'coding', task_id=t, cwd=str(tmp_path))
    return T.call_args.args[0]

def test_a_stranger_batch_runs_in_auto_mode_under_the_floor(tmp_path):
    "No read-only lock any more (the owner, 2026-10-15): a stranger's batch is a stranger's task - auto mode, the floor, its folder."
    from taskuary import batch
    s = _store(); t, _ = _task(s)
    with mock.patch.object(batch, 'is_batch', return_value=True), mock.patch('taskuary.config.load', return_value=server.cfg):
        argv = _pane(s, t, tmp_path)
    assert argv[argv.index('--permission-mode') + 1] == 'auto' and argv.count('--settings') == 1
    hooks_ = json.loads(Path(argv[argv.index('--settings') + 1]).read_text(encoding='utf-8'))['hooks']
    assert '/api/hooks/claude/floor' in hooks_['PreToolUse'][0]['hooks'][0]['command']
    assert str(origin.stranger_dir(t)) == argv[argv.index('--add-dir') + 1]

def test_an_owner_batch_launches_as_any_owner_session(tmp_path):
    from taskuary import batch
    s = _store(); t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')
    with mock.patch.object(batch, 'is_batch', return_value=True):
        argv = _pane(s, t, tmp_path)
    assert '--permission-mode' not in argv and not any('sessions' in str(a) and str(a).endswith('.json') for a in argv)

def test_a_live_conversation_restarts_when_its_environment_s_keys_change(monkeypatch):
    from taskuary import clipool
    made = []
    class Live:
        def __init__(self, key, cmd, cwd, env, sig): self.sig, self.turns, self.sid, self.lock = sig, 0, '', __import__('threading').Lock(); made.append(sig)
        def alive(self): return True
        def close(self): pass
        def turn(self, *a, **k): self.turns += 1; return ({}, [])
    monkeypatch.setattr(clipool, 'Live', Live); monkeypatch.setattr(clipool, '_POOL', {})
    clipool.run('k', ['claude'], 'hi', None, env={'A': '1', guard.TASK_ENV: 'p'}, resume='s')
    clipool.run('k', ['claude'], 'hi', None, env={'A': '2', guard.TASK_ENV: 'q'}, resume='s')     # same keys: kept
    clipool.run('k', ['claude'], 'hi', None, env={'A': '1'}, resume='s')                          # a key gone: a new process
    assert len(made) == 2 and made[0] != made[1]
