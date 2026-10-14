import os, pytest
from fastapi.testclient import TestClient
from taskuary import floor, config, guard, server, origin
from taskuary.config import home
from taskuary.store import MemoryStore

H = os.path.expanduser('~')
def call(tool, **inp): return floor.check({'tool_name': tool, 'tool_input': inp}, 7)
def denied(r): return r.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny'
def tilde(p): return '~/' + os.path.relpath(str(p), H).replace('\\', '/')

def test_taskuary_s_files_are_refused_however_the_path_is_written():
    ps = [str(home() / 'config.toml'), str(home() / 'x' / '..' / 'taskuary.db'), str(home() / 'config.toml').replace('\\', '/'), tilde(home() / 'config.toml')]
    if os.name == 'nt': ps.append(str(home() / 'config.toml').upper())   # case is only folded where the filesystem folds it
    for p in ps: assert denied(call('Read', file_path=p)), p

def test_a_relative_path_is_the_session_s_not_the_server_s(tmp_path):
    cwd = home() / 'work' / 'deep'; up = os.path.relpath(home() / 'config.toml', cwd)
    assert denied(floor.check({'tool_name': 'Read', 'cwd': str(cwd), 'tool_input': {'file_path': up}}, 7))
    assert floor.check({'tool_name': 'Read', 'cwd': str(tmp_path), 'tool_input': {'file_path': 'app.py'}}, 7) == {}

def test_credentials_and_keys_are_refused():
    for p in ('~/.ssh/id_ed25519', '~/.claude/.credentials.json', '~/.codex/auth.json', '~/.aws/credentials', '~/.config/gh/hosts.yml', '~/.git-credentials'):
        assert denied(call('Read', file_path=p)), p
    assert denied(call('Grep', pattern='token', path='~/.aws'))

def test_a_shell_command_naming_them_or_taskuary_s_address_is_refused():
    port = config.load()['server'].get('port') or 7787
    rel = os.path.relpath(home(), H).replace('\\', '/')
    cmds = ['type %USERPROFILE%\\.ssh\\id_rsa', 'cat $env:USERPROFILE/.aws/credentials', 'cat $HOME/.ssh/id_rsa', f'cat {home() / "config.toml"}',
            f'curl http://127.0.0.1:{port}/', f'Invoke-WebRequest http://localhost:{port}/api/feed', f'curl http://[::1]:{port}/']
    if not rel.startswith('..'): cmds.append(f'cat ~/{rel}/config.toml')   # the home-relative form only exists where Taskuary's folder is under ~
    for cmd in cmds:
        assert denied(call('Bash', command=cmd)) and denied(call('PowerShell', command=cmd)), cmd
    assert denied(call('WebFetch', url=f'http://127.0.0.1:{port}/'))

def test_this_task_s_own_files_and_ordinary_work_pass():
    assert call('Read', file_path=str(home() / 'context' / 'TQ-0007.stranger.md')) == {}
    assert call('Read', file_path=str(origin.stranger_dir(7) / 'notes.md')) == {}
    assert call('Bash', command=f'cat {origin.stranger_dir(7) / "notes.md"}') == {}
    assert call('Bash', command='python -m pytest -q') == {}
    assert call('Edit', file_path=os.path.join(os.getcwd(), 'app.py')) == {}
    assert denied(call('Read', file_path=str(home() / 'context' / 'TQ-0008.stranger.md')))   # another task's
    assert denied(call('Read', file_path=str(home() / 'attachments' / 'other-task.pdf')))    # another task's attachment
    assert denied(call('Bash', command=f'cat {origin.stranger_dir(7) / "n.md"} {home() / "config.toml"}'))   # own file does not launder a neighbour

def test_this_task_s_attachments_pass_and_another_task_s_do_not():
    s = MemoryStore(); mk = lambda: s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'email'}, 'router')
    a, b = mk(), mk();
    for t, n in ((a, 'mine.pdf'), (b, 'theirs.pdf')):
        m = s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'a@vendor.example'})
        s.add_attachment({'MessageId': m, 'Name': n, 'Path': str(home() / 'attachments' / n)})
    ok = lambda t, n: floor.check({'tool_input': {'file_path': str(home() / 'attachments' / n)}}, t, s)
    assert ok(a, 'mine.pdf') == {} and denied(ok(a, 'theirs.pdf'))

c = TestClient(server.app)
def _hdr(tid):
    srv = config.load()['server']; return {'X-Taskuary-Token': srv['agent_token'], guard.TASK_HDR: guard.task_proof(srv, tid)}
BODY = {'tool_name': 'Read', 'tool_input': {'file_path': '~/.ssh/id_rsa'}}

def test_the_door_answers_its_own_task_and_refuses_a_neighbour_s():
    r = c.post('/api/hooks/claude/floor?task=7', json=BODY, headers=_hdr(7))
    assert r.status_code == 200 and denied(r.json())
    assert c.post('/api/hooks/claude/floor?task=7', json=BODY, headers=_hdr(8)).status_code == 403
    assert c.post('/api/hooks/claude/floor?task=7', json=BODY, headers={'X-Taskuary-Token': config.load()['server']['agent_token']}).status_code == 403

def test_the_door_is_on_the_agent_allow_list_with_a_query_string_present():
    assert guard.denied('POST', '/api/hooks/claude/floor') == '' and guard.denied('POST', '/api/hooks/claude/permit') == ''

def test_the_door_fails_closed(monkeypatch):
    def boom(*a, **k): raise RuntimeError('x')
    monkeypatch.setattr(floor, 'check', boom)
    assert TestClient(server.app, raise_server_exceptions=False).post('/api/hooks/claude/floor?task=7', json=BODY, headers=_hdr(7)).status_code == 500
