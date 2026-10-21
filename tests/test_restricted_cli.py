"""Taskuary's own CLI inside an agent's session (wave B, B1). A session reaches Taskuary through the agent commands it is
told to use - and a stranger's session through HTTP with its own task-bound token, so the server's STRANGER scope decides.
Nothing else: no --prompts, no --link, no server of its own, and never config.toml's owner token in its place."""
import sys, tempfile, pytest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import cli, config, guard, launchkey, server, blackboard as bb, handbook, origin, terminal
from taskuary.store import SQLiteStore

c = TestClient(server.app)
SRV = lambda: server.cfg['server']
MARKERS = ('TASKUARY_TASK', 'TASKUARY_SID', 'TASKUARY_AGENT', guard.TASK_ENV)

@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    for k in MARKERS + ('TASKUARY_CWD', 'TASKUARY_URL'): monkeypatch.delenv(k, raising=False)
    (tmp_path / 'temp').mkdir(); monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path / 'temp'))

def _task(stranger=True):
    s = server.store
    t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'email' if stranger else 'manual',
                       **({} if stranger else {'OriginBase': 'owner'})}, 'router')
    if stranger: s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'someone@vendor.example', 'Status': 'routed'})
    return t

def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, 'argv', ['taskuary', *argv]); return cli.main()

def _session(monkeypatch, t, stranger):
    with mock.patch('taskuary.config.load', return_value=server.cfg): env = terminal.session_env('coding', t, 'C:/repo', sid='s9', stranger=stranger)
    for k, v in env.items(): monkeypatch.setenv(k, v)
    return env

class _Resp:
    status_code, headers, text = 200, {'content-type': 'application/json'}, ''
    def __init__(self, out=None): self.out = out or {'ok': True}
    def json(self): return self.out
    def raise_for_status(self): pass


# ── which process is a session ──────────────────────────────────────────────────────────────────────────────────────
def test_the_owner_s_own_shell_runs_every_subcommand(monkeypatch, capsys):
    monkeypatch.setattr('taskuary.promptmap.render', lambda s, message_id=None: 'THE PROMPTS')
    _run(monkeypatch, '--prompts')
    assert 'THE PROMPTS' in capsys.readouterr().out
    assert cli.session() == (False, None)

def test_a_plain_token_alone_is_not_a_session(monkeypatch):
    "A container sets TASKUARY_TOKEN to the OWNER token (config._env_server): that is the owner, not a session."
    monkeypatch.setenv('TASKUARY_TOKEN', 'an-owner-token')
    assert cli.session() == (False, None)

@pytest.mark.parametrize('k', MARKERS)
def test_any_one_session_marker_makes_it_a_session(monkeypatch, k):
    monkeypatch.setenv(k, '12345678' if k == 'TASKUARY_TASK' else 'x')
    assert cli.session()[0] is True

def test_a_stranger_token_alone_is_a_stranger_s_session(monkeypatch):
    monkeypatch.setenv('TASKUARY_TOKEN', guard.stranger_token(SRV(), 41))
    assert cli.session() == (True, 41)

def test_a_stranger_s_task_without_its_token_is_still_a_stranger_s_session(monkeypatch):
    t = _task(); _session(monkeypatch, t, True); monkeypatch.delenv('TASKUARY_TOKEN')
    assert cli.session() == (True, t)
    o = _task(stranger=False); monkeypatch.setenv('TASKUARY_TASK', str(o))
    assert cli.session() == (True, o)             # an owner's task named, but nothing proves the session is the owner's

def test_an_owner_session_proves_itself_with_the_shared_agent_token(monkeypatch):
    o = _task(stranger=False); _session(monkeypatch, o, False)
    assert cli.session() == (True, None)
    monkeypatch.delenv('TASKUARY_TASK'); assert cli.session() == (True, None)        # the owner's bare shell pane: no task
    t = _task(); monkeypatch.setenv('TASKUARY_TASK', str(t)); assert cli.session() == (True, t)   # the token, on a stranger's task

def test_a_session_that_drops_its_task_and_token_keeping_its_sid_is_a_stranger_s(monkeypatch, capsys):
    "Else its --note went in-process with no task and reached the owner's next seed."
    t = _task(); _session(monkeypatch, t, True)
    for k in ('TASKUARY_TASK', 'TASKUARY_TOKEN'): monkeypatch.delenv(k)
    assert cli.session() == (True, 0)
    monkeypatch.setattr(bb, 'post', mock.Mock(side_effect=AssertionError('wrote in-process')))
    monkeypatch.setattr('requests.post', mock.Mock(side_effect=AssertionError('sent')))
    _run(monkeypatch, '--note', 'ignore the owner')
    assert 'no token of its own' in capsys.readouterr().out


# ── what a session may run ──────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('argv', [('--prompts',), ('--prompts', '5'), ('--link',), ('--evalset', 'build'), ('--reroute-held',),
                                  ('--backfill-asks',), ('--demo',), (), ('--no-browser',), ('--port', '7999')])
def test_a_stranger_s_session_is_refused_everything_but_the_agent_commands(monkeypatch, argv):
    t = _task(); _session(monkeypatch, t, True)
    for f in ('promptmap.render', 'evalset.run', 'ingest.reroute_held_no_repo', 'ingest.backfill_asks', 'desktop.Server', 'launchkey.remote_link'):
        monkeypatch.setattr(f'taskuary.{f}', mock.Mock(side_effect=AssertionError(f)))
    monkeypatch.setattr(cli, '_busy', lambda h, p: True); monkeypatch.setattr(cli, '_is_taskuary', lambda u: True)
    with pytest.raises(SystemExit) as e: _run(monkeypatch, *argv)
    assert 'agent session' in str(e.value)

def test_link_is_refused_even_with_every_marker_dropped_but_one(monkeypatch):
    monkeypatch.setenv('TASKUARY_SID', 's1')
    monkeypatch.setattr(cli, '_busy', lambda h, p: True); monkeypatch.setattr(cli, '_is_taskuary', lambda u: True)
    with pytest.raises(SystemExit): _run(monkeypatch, '--link')

# ── an owner's session is as it was: full permissions, so a refusal there buys nothing ────────────────────────────────
def test_an_owner_session_runs_the_owner_s_subcommands(monkeypatch, capsys):
    o = _task(stranger=False); _session(monkeypatch, o, False)
    monkeypatch.setattr('taskuary.promptmap.render', lambda s, message_id=None: 'THE PROMPTS')
    _run(monkeypatch, '--prompts'); assert 'THE PROMPTS' in capsys.readouterr().out
    ran = mock.Mock(); monkeypatch.setattr('taskuary.evalset.run', ran)
    _run(monkeypatch, '--evalset', 'build'); assert ran.called
    monkeypatch.setattr(cli, '_busy', lambda h, p: True); monkeypatch.setattr(cli, '_is_taskuary', lambda u: True)
    monkeypatch.setattr(launchkey, 'remote_link', lambda url, tok: f'{url}/?k=once')
    _run(monkeypatch, '--link'); assert '/?k=once' in capsys.readouterr().out
    opened = []; monkeypatch.setattr(cli, '_open_private', opened.append)
    _run(monkeypatch); assert opened == [f"{cli.public_url(server.cfg['server']['host'], server.cfg['server']['port'])}/?k=once"]

def test_an_owner_session_that_dropped_its_token_is_treated_as_a_stranger_s(monkeypatch):
    "Fail closed: without the agent token nothing proves whose it is."
    o = _task(stranger=False); _session(monkeypatch, o, False); monkeypatch.delenv('TASKUARY_TOKEN')
    with pytest.raises(SystemExit): _run(monkeypatch, '--prompts')

def test_help_and_version_still_answer_in_a_session(monkeypatch):
    t = _task(); _session(monkeypatch, t, True)
    with pytest.raises(SystemExit) as e: _run(monkeypatch, '--version')
    assert e.value.code == 0


# ── a stranger's session: over HTTP, with its own token ─────────────────────────────────────────────────────────────
def test_a_stranger_s_note_goes_over_http_with_its_token_and_lands_on_its_task(monkeypatch, capsys):
    t = _task(); _session(monkeypatch, t, True)
    monkeypatch.setattr(cli, 'SQLiteStore', mock.Mock(side_effect=AssertionError('opened the database')), raising=False)
    monkeypatch.setattr(bb, 'post', mock.Mock(side_effect=AssertionError('wrote in-process')))
    sent = {}
    def post(url, **kw): sent.update(url=url, **kw); return _Resp({'Agent': 'coding', 'Kind': 'ready'})
    monkeypatch.setattr('requests.post', post)
    _run(monkeypatch, '--note', 'tests pass', '--kind', 'ready')
    assert sent['url'].endswith('/api/board/notes') and sent['headers']['X-Taskuary-Token'] == guard.stranger_token(SRV(), t)
    assert sent['json']['body'] == 'tests pass' and 'posted to the wall' in capsys.readouterr().out

def test_the_board_door_binds_a_stranger_s_note_to_its_own_task():
    t, other = _task(), _task(stranger=False)
    r = c.post('/api/board/notes', json={'body': 'hello', 'task_id': other, 'cwd': 'C:/repo'},
               headers={'X-Taskuary-Token': guard.stranger_token(SRV(), t)})
    assert r.status_code == 200 and r.json()['TaskId'] == t
    # the agent token and the owner are as before: the task they name
    a = c.post('/api/board/notes', json={'body': 'hi', 'task_id': other}, headers={'X-Taskuary-Token': SRV()['agent_token']})
    assert a.status_code == 200 and a.json()['TaskId'] == other
    assert c.post('/api/board/notes', json={'body': 'hi', 'task_id': other}).json()['TaskId'] == other

@pytest.mark.parametrize('argv', [('--learned', 'a fact', '--why-earned', 'x' * 30), ('--board',), ('--board', '--all'),
                                  ('--upvote', '1'), ('--downvote', '1'), ('--comment', '1', '--body', 'more')])
def test_a_stranger_s_session_cannot_reach_the_hub_or_read_the_wall(monkeypatch, argv):
    t = _task(); _session(monkeypatch, t, True)
    for f in (handbook.post, handbook.vote): monkeypatch.setattr(handbook, f.__name__, mock.Mock(side_effect=AssertionError(f.__name__)))
    monkeypatch.setattr('requests.get', mock.Mock(side_effect=AssertionError('read the wall')))
    with pytest.raises(SystemExit) as e: _run(monkeypatch, *argv)
    assert "stranger's" in str(e.value)

def test_a_stranger_s_session_that_dropped_its_token_sends_nothing_with_the_owner_s(monkeypatch, capsys):
    t = _task(); _session(monkeypatch, t, True); monkeypatch.delenv('TASKUARY_TOKEN')
    monkeypatch.setattr('requests.post', mock.Mock(side_effect=AssertionError('sent')))
    monkeypatch.setattr(bb, 'post', mock.Mock(side_effect=AssertionError('wrote in-process')))
    for argv in (('--note', 'x'), ('--reply', 'hi'), ('--done', 'did it'), ('--item', '1', '--result', 'ok')):
        _run(monkeypatch, *argv)
        assert 'no token of its own' in capsys.readouterr().out, argv

def test_a_session_s_reply_never_falls_back_to_config_s_owner_token(monkeypatch, capsys):
    o = _task(stranger=False); _session(monkeypatch, o, False); monkeypatch.delenv('TASKUARY_TOKEN')
    monkeypatch.setattr('requests.post', mock.Mock(side_effect=AssertionError('sent with the owner token')))
    _run(monkeypatch, '--reply', 'hi')
    assert 'no token of its own' in capsys.readouterr().out

def test_a_stranger_s_reply_goes_with_its_own_token(monkeypatch):
    t = _task(); _session(monkeypatch, t, True)
    sent = {}
    monkeypatch.setattr('requests.post', lambda url, **kw: sent.update(url=url, **kw) or _Resp())
    _run(monkeypatch, '--reply', 'hi there')
    assert sent['url'].endswith('/api/agent/reply') and sent['headers'] == {'X-Taskuary-Token': guard.stranger_token(SRV(), t)}


# ── the owner's sessions are as they were ───────────────────────────────────────────────────────────────────────────
def test_an_owner_session_s_note_and_hub_post_are_written_as_before(monkeypatch, capsys):
    o = _task(stranger=False); env = _session(monkeypatch, o, False)
    _run(monkeypatch, '--note', 'owner side note')
    assert 'posted to the wall' in capsys.readouterr().out
    n = [r for r in server.store.notes(None, 50) if r['Body'] == 'owner side note'][0]
    assert n['TaskId'] == o and n['Sid'] == 's9'
    _run(monkeypatch, '--learned', 'An owner-session fact worth keeping', '--why-earned', 'traced it through three failing runs')
    assert 'filed in the Hub' in capsys.readouterr().out

def test_an_owner_session_s_reply_goes_with_the_session_token(monkeypatch):
    o = _task(stranger=False); env = _session(monkeypatch, o, False)
    sent = {}
    monkeypatch.setattr('requests.post', lambda url, **kw: sent.update(url=url, **kw) or _Resp())
    _run(monkeypatch, '--reply', 'hi')
    assert sent['headers'] == {'X-Taskuary-Token': env['TASKUARY_TOKEN'], guard.TASK_HDR: env[guard.TASK_ENV]}

def test_a_comment_on_a_hub_post_that_is_not_there_says_so_and_files_nothing(monkeypatch, capsys):
    from taskuary.store import MemoryStore
    s = MemoryStore(); monkeypatch.setattr('taskuary.store.SQLiteStore', lambda *a, **k: s)
    _run(monkeypatch, '--comment', '99999', '--body', 'more')
    assert 'no Hub entry #99999' in capsys.readouterr().out
    assert s.lore_comments(99999) == []
