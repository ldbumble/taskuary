"""The page hands out the owner token only to a window Taskuary opened itself (R29): any local process - a restricted
session's shell, its agent browser - could fetch / and read the token out of it. A one-time launch key now gates that."""
import sys, types, pytest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import server, guard, launchkey, cli, desktop

c = TestClient(server.app)
TOK = lambda: server.cfg['server']['token']
SEED = 'localStorage.setItem("taskuary_token"'

@pytest.fixture(autouse=True)
def _index(monkeypatch, tmp_path):
    p = tmp_path / 'index.html'; p.write_text('<html><head><title>Taskuary</title></head><body><div id="root"></div></body></html>', encoding='utf-8')
    monkeypatch.setattr(server, '_web_root', tmp_path)
    launchkey._KEYS.clear()

def test_no_key_no_token():
    r = c.get('/', headers={'X-Taskuary-Token': ''})
    assert r.status_code == 200 and TOK() not in r.text and SEED not in r.text
    assert 'name="taskuary-unlinked"' in r.text                  # ...and the page knows to say how to get one
    assert TOK() not in c.get('/?k=nonsense').text

def test_a_valid_key_seeds_the_token_once():
    k = launchkey.mint()
    r = c.get(f'/?k={k}')
    assert TOK() in r.text and SEED in r.text and 'taskuary-unlinked' not in r.text
    assert 'replaceState' in r.text                              # the key leaves the address bar
    assert TOK() not in c.get(f'/?k={k}').text                   # single use

def test_an_expired_key_seeds_nothing(monkeypatch):
    k = launchkey.mint()
    monkeypatch.setattr(launchkey.time, 'monotonic', lambda: 10 ** 12)
    assert TOK() not in c.get(f'/?k={k}').text

def test_the_launch_key_door_is_the_owner_s_alone():
    t = server.store.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'email'}, 'router')
    assert c.post('/api/launch-key', headers={'X-Taskuary-Token': server.cfg['server']['agent_token']}).status_code == 403
    assert c.post('/api/launch-key', headers={'X-Taskuary-Token': guard.stranger_token(server.cfg['server'], t)}).status_code == 403
    k = c.post('/api/launch-key').json()['key']                 # the owner (conftest's default header)
    assert TOK() in c.get(f'/?k={k}').text

def test_another_process_of_his_gets_a_key_by_reading_back_the_word_written_in_his_home():
    """The owner, 2026-11-25: the token is in the server's memory alone, so Taskuary started again and `taskuary --link` hold none - the
    running server writes a one-time word into its home, and a key is handed out for it once."""
    from taskuary import config
    nobody = {'X-Taskuary-Token': 'wrong'}
    got = c.post('/api/launch-key', headers=nobody).json()
    assert 'key' not in got and set(got) == {'challenge'}
    f = config.home() / 'launch' / got['challenge']
    assert c.post('/api/launch-key', headers=nobody, json={'challenge': got['challenge'], 'word': 'guessed'}).status_code == 403
    assert not f.exists()                                        # ...spent by the wrong word: a guess is never tried twice
    got = c.post('/api/launch-key', headers=nobody).json(); word = (config.home() / 'launch' / got['challenge']).read_text(encoding='utf-8')
    k = c.post('/api/launch-key', headers=nobody, json={'challenge': got['challenge'], 'word': word}).json()['key']
    assert TOK() in c.get(f'/?k={k}').text
    assert c.post('/api/launch-key', headers=nobody, json={'challenge': got['challenge'], 'word': word}).status_code == 403    # once

def test_the_window_door_brings_the_owner_s_window_forward_and_is_hers_alone(monkeypatch):
    from taskuary import workerstate
    fronted = []
    monkeypatch.setattr(workerstate, 'SHOW', [None])
    assert c.post('/api/window').status_code == 409                   # server-only: the second start opens the browser
    workerstate.SHOW[0] = lambda: fronted.append(1)
    assert c.post('/api/window', headers={'X-Taskuary-Token': server.cfg['server']['agent_token']}).status_code == 403 and not fronted
    assert c.post('/api/window').json() == {'shown': True} and fronted == [1]
    assert c.post('/api/window', headers={'X-Taskuary-Token': ''}).json() == {'shown': True} and fronted == [1, 1]    # ...Taskuary started again holds no token

def test_link_adds_a_fresh_key():
    a, b = launchkey.link('http://127.0.0.1:7787'), launchkey.link('http://127.0.0.1:7787/')
    assert a.startswith('http://127.0.0.1:7787/?k=') and b.startswith('http://127.0.0.1:7787/?k=') and a != b

def test_remote_link_answers_the_running_servers_challenge_with_the_word_in_its_home(monkeypatch, tmp_path):
    import json
    (tmp_path / 'launch').mkdir(); (tmp_path / 'launch' / '0123456789abcdef.word').write_text('the-word', encoding='utf-8')
    seen = []
    class Conn:
        def __init__(self, host, port, timeout=None): self.at = (host, port)
        def request(self, m, path, headers=None, body=None): seen.append((self.at, m, path, headers, json.loads(body)))
        def getresponse(self):
            said = {'key': 'abc'} if seen[-1][4].get('word') == 'the-word' else {'challenge': '0123456789abcdef.word'}
            return types.SimpleNamespace(status=200, read=lambda: json.dumps(said).encode())
        def close(self): pass
    monkeypatch.setattr(launchkey.http.client, 'HTTPConnection', Conn)
    assert launchkey.remote_link('http://127.0.0.1:7795', tmp_path) == 'http://127.0.0.1:7795/?k=abc'
    assert [(at, m, p) for at, m, p, _h, _b in seen] == [(('127.0.0.1', 7795), 'POST', '/api/launch-key')] * 2
    assert not any('X-Taskuary-Token' in h for *_x, h, _b in seen)        # ...no token rides: it is in that server's memory alone
    class Bad(Conn):
        def getresponse(self): raise OSError('refused')
    monkeypatch.setattr(launchkey.http.client, 'HTTPConnection', Bad)
    assert launchkey.remote_link('http://127.0.0.1:7795', tmp_path) == 'http://127.0.0.1:7795'   # an old server: the plain address

# the CLI's browser opens, keyed - through a private file since wave B: tests/test_launch_key_private.py

def test_taskuary_link_prints_a_one_time_url(monkeypatch, capsys):
    monkeypatch.setattr(cli, '_busy', lambda h, p: True); monkeypatch.setattr(cli, '_is_taskuary', lambda u: True)
    monkeypatch.setattr(launchkey, 'remote_link', lambda url, tok: f'{url}/?k=once')
    monkeypatch.setattr(sys, 'argv', ['taskuary', '--link'])
    cli.main()
    assert '/?k=once' in capsys.readouterr().out
    monkeypatch.setattr(cli, '_busy', lambda h, p: False); cli.main()
    assert 'not running' in capsys.readouterr().out

def test_the_desktop_window_opens_on_a_keyed_url(monkeypatch):
    made, loaded = {}, []
    class Win:
        events = types.SimpleNamespace(closing=None)            # += on None fails, and the desktop carries on without a goodbye
        def load_url(self, u): loaded.append(u)
        def load_html(self, h): loaded.append('html')
    win = Win()
    fake = types.SimpleNamespace(create_window=lambda *a, **k: made.update(k) or win, start=lambda f=None: f and f())
    monkeypatch.setitem(sys.modules, 'webview', fake)
    monkeypatch.setattr(desktop, 'already_serving', lambda port=None: '')
    monkeypatch.setattr(desktop, 'start_server', lambda port=None: (types.SimpleNamespace(), 'http://127.0.0.1:7801'))
    monkeypatch.setattr(desktop, 'serving', lambda u, secs=0: True); monkeypatch.setattr(desktop, 'stop_server', lambda s: 'clean')
    monkeypatch.setattr(sys, 'argv', ['taskuary-desktop'])
    desktop.main()
    assert loaded and loaded[0].startswith('http://127.0.0.1:7801/?k=') and launchkey.redeem(loaded[0].split('k=')[1])
    assert made['maximized']        # a fixed 1280x840 hung off a laptop's screen on every launch (TQ-1251)

def _second_start(monkeypatch, status):
    """Taskuary started while one runs: what it asked of the running one, what it opened, and that it made no window (TQ-1397)."""
    made, asked, opened = [], [], []
    fake = types.SimpleNamespace(create_window=lambda *a, **k: made.append(k), start=lambda *a, **k: made.append('start'))
    monkeypatch.setitem(sys.modules, 'webview', fake)
    monkeypatch.setattr(desktop, 'already_serving', lambda port=None: 'http://127.0.0.1:7787')
    class Conn:
        def __init__(self, host, port, timeout=0): asked.append((host, port))
        def request(self, m, path, headers=None): asked.append((m, path))
        def getresponse(self): return types.SimpleNamespace(status=status)
        def close(self): pass
    monkeypatch.setattr(desktop.http.client, 'HTTPConnection', Conn)
    monkeypatch.setattr(desktop.webbrowser, 'open', opened.append)
    monkeypatch.setattr(launchkey, 'remote_link', lambda url, tok: f'{url}/?k=fromserver')
    monkeypatch.setattr(sys, 'argv', ['taskuary-desktop'])
    assert desktop.main() == 0
    return made, asked, opened

def test_taskuary_started_again_brings_the_running_window_forward_and_opens_none(monkeypatch):
    # a second Taskuary.exe window outlived its server for an Update and held the install folder: the installer aborted and the
    # old version came back on every press (TQ-1251, TQ-1397). The owner: never two open at the same time.
    made, asked, opened = _second_start(monkeypatch, 200)
    assert ('POST', '/api/window') in asked and made == [] and opened == []

def test_a_running_one_with_no_window_is_opened_in_the_browser_never_a_second_window(monkeypatch):
    made, asked, opened = _second_start(monkeypatch, 409)
    assert made == [] and opened == ['http://127.0.0.1:7787/?k=fromserver']


def test_a_start_given_its_own_port_never_asks_the_app_on_the_configured_one(monkeypatch):
    # 2026-11-16: a scratch copy started with --port asked 7787, found the owner's running app, and brought his window up
    asked = []
    monkeypatch.setattr(desktop, 'already_serving', lambda port=None: asked.append(port) or '')
    monkeypatch.setattr(desktop, 'held_elsewhere', lambda: '')
    fake = types.SimpleNamespace(create_window=lambda *a, **k: types.SimpleNamespace(events=types.SimpleNamespace(closing=None), load_url=lambda u: None,
                                 load_html=lambda h: None), start=lambda f=None: None)
    monkeypatch.setitem(sys.modules, 'webview', fake)
    monkeypatch.setattr(desktop, 'start_server', lambda port=None: (types.SimpleNamespace(), f'http://127.0.0.1:{port}'))
    monkeypatch.setattr(desktop, 'stop_server', lambda s: 'clean')
    monkeypatch.setattr(sys, 'argv', ['taskuary-desktop', '--port', '7899'])
    # ...its window never opens, so nothing boots: the 120s wait for a boot hit faulthandler's 120s and the Windows shard died with it
    monkeypatch.setattr(desktop, 'BOOT_WAIT', 0)
    desktop.main()
    assert asked == [7899]


# ── RED TEAM ROUND 5: a launch key is never handed to a process Taskuary started ──────────────────────────────────────────────────────────
# An agent's own command asked the door with no token, read the one-time word back out of the home (the same account's file), and opened the
# page that carries the owner token. Who is asking is read from the OS - the process on the other end of the socket - never from the caller.
def test_the_door_refuses_a_process_this_server_started_and_one_that_hides(monkeypatch):
    from taskuary import config, spawn
    agent = TestClient(server.app, client=('127.0.0.1', 51111), headers={'X-Taskuary-Token': ''})
    asked, words = [], lambda: set((config.home() / 'launch').glob('*.word'))
    monkeypatch.setattr(spawn, 'holders', lambda port, to: asked.append(port) or [4242])
    monkeypatch.setattr(spawn, 'ours', lambda pid, marks=(): pid == 4242)
    before = words()
    r = agent.post('/api/launch-key')
    assert r.status_code == 403 and 'never to a process Taskuary started' in r.json()['detail'] and asked == [51111]
    assert words() == before, 'no word is even written for it'
    monkeypatch.setattr(spawn, 'holders', lambda port, to: [])                 # ...the connection is here and nobody admits to holding it
    assert agent.post('/api/launch-key').status_code == 403
    # ...the owner's own other process - not one of ours - is handed the challenge, and the key for the word, as before
    monkeypatch.setattr(spawn, 'ours', lambda pid, marks=(): False); monkeypatch.setattr(spawn, 'holders', lambda port, to: [777])
    got = agent.post('/api/launch-key').json()
    word = (config.home() / 'launch' / got['challenge']).read_text(encoding='utf-8')
    k = agent.post('/api/launch-key', json={'challenge': got['challenge'], 'word': word}).json()['key']
    assert TOK() in c.get(f'/?k={k}').text
    # ...and a caller on another machine (no connection of this machine's own) is asked for the word in the home, as before
    monkeypatch.setattr(spawn, 'holders', lambda port, to: None)
    assert set(agent.post('/api/launch-key').json()) == {'challenge'}

def test_a_process_is_ours_by_its_parents_and_the_one_that_started_us_is_not():
    import os
    from taskuary import spawn
    assert spawn.ours(os.getpid()), 'this process itself'
    assert not spawn.ours(os.getppid()), 'the process that started this one is nobody we started'
    assert not spawn.ours(0) and not spawn.ours('x')

def test_an_agents_session_asks_for_no_key_and_link_is_refused_there(monkeypatch, capsys):
    """`taskuary --link` run from inside an agent's session printed an address that signs in as the owner; Taskuary started again from one
    opened his browser on a keyed page. A session - his own task's too - asks the running server for nothing."""
    called = []
    class Conn:
        def __init__(self, *a, **k): called.append(a)
    monkeypatch.setattr(launchkey.http.client, 'HTTPConnection', Conn)
    monkeypatch.setenv('TASKUARY_TASK', '7'); monkeypatch.setenv('TASKUARY_TOKEN', server.cfg['server']['agent_token'])
    assert launchkey.remote_link('http://127.0.0.1:7795', 'unused') == 'http://127.0.0.1:7795' and not called
    monkeypatch.setattr(cli, '_busy', lambda h, p: True); monkeypatch.setattr(cli, '_is_taskuary', lambda u: True)
    monkeypatch.setattr(cli, 'session', lambda: (True, None))                # ...the owner's own task's agent
    monkeypatch.setattr(sys, 'argv', ['taskuary', '--link'])
    with pytest.raises(SystemExit) as e: cli.main()
    assert '--link refused' in str(e.value) and '?k=' not in capsys.readouterr().out and not called

SERVER = r'''
import os, sys, threading, time
sys.path.insert(0, {root!r})
import uvicorn
from taskuary import launchkey, server, spawn
srv = uvicorn.Server(uvicorn.Config(server.app, host='127.0.0.1', port={port}, lifespan='off', log_level='error'))
threading.Thread(target=srv.run, daemon=True).start()
while not srv.started: time.sleep(.05)
print('UP', flush=True)
# an agent's own command, as this server starts one (spawn) - with every mark of a session taken out of its environment, as one hiding would
env = {{k: v for k, v in os.environ.items() if k not in launchkey.MARKERS and k != 'TASKUARY_TOKEN'}}
rc, out = spawn.output([sys.executable, '-I', {client!r}], timeout=60, env=env)
print('CHILD ' + ' '.join(out.split()), flush=True)
# ...and one that outlives the command that started it: its parent is gone by the time it asks
spawn.output([sys.executable, '-I', {starter!r}], timeout=60, env=env)
end = time.time() + 60
while not os.path.exists({late!r}) and time.time() < end: time.sleep(.1)
print('LATE ' + (open({late!r}).read().strip() if os.path.exists({late!r}) else 'nothing'), flush=True)
sys.stdin.readline()
srv.should_exit = True
'''
CLIENT = r'''
import sys
sys.path.insert(0, {root!r})
from taskuary import launchkey
print(launchkey.remote_link({url!r}, {home!r}))
'''
STARTER = r'''
import subprocess, sys
subprocess.Popen([sys.executable, '-I', {orphan!r}], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
'''
ORPHAN = r'''
import os, sys, time
sys.path.insert(0, {root!r})
from taskuary import launchkey
time.sleep(1.5)
got = launchkey.remote_link({url!r}, {home!r})
with open({late!r} + '.tmp', 'w') as f: f.write(got)
os.replace({late!r} + '.tmp', {late!r})
'''

def test_on_real_sockets_an_agents_command_is_refused_and_the_owners_own_start_still_signs_in(monkeypatch, tmp_path, isolated_process_env):
    """The live shape, end to end: a real server in a process of its own, a command it starts as it starts an agent's (and one that outlives
    its parent) asking for a key by the CLI's own road - refused - and this process, which that server did not start, standing in for the
    owner's own second start or `taskuary --link`: handed a key, and the page it opens carries his token."""
    import http.client, socket, subprocess
    from pathlib import Path
    for k in (*launchkey.MARKERS, 'TASKUARY_TOKEN'): monkeypatch.delenv(k, raising=False)
    with socket.socket() as so: so.bind(('127.0.0.1', 0)); port = so.getsockname()[1]
    env = isolated_process_env(port=port)
    for k in (*launchkey.MARKERS, 'TASKUARY_TOKEN', 'TASKUARY_API'): env.pop(k, None)
    env.update(TASKUARY_HOST='127.0.0.1', TASKUARY_PORT=str(port))
    home, root, url = env['TASKUARY_HOME'], str(Path(__file__).resolve().parents[1]), f'http://127.0.0.1:{port}'
    f = {n: str(tmp_path / f'{n}.py') for n in ('server', 'client', 'starter', 'orphan')}
    late = str(tmp_path / 'late.txt')
    for n, text in (('server', SERVER), ('client', CLIENT), ('starter', STARTER), ('orphan', ORPHAN)):
        Path(f[n]).write_text(text.format(root=root, port=port, url=url, home=home, late=late, client=f['client'], starter=f['starter'], orphan=f['orphan']), encoding='utf-8')
    p = subprocess.Popen([sys.executable, '-I', f['server']], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        said, seen = {}, []
        for line in p.stdout:
            seen.append(line); k, _, v = line.strip().partition(' ')
            said[k] = v
            if k == 'LATE': break
        assert 'UP' in said and 'CHILD' in said and 'LATE' in said, ''.join(seen)[-3000:]
        assert said['CHILD'] == url, f"the server's own child was handed a key: {said['CHILD']}"
        assert said['LATE'] == url, f"a command that outlived its parent was handed a key: {said['LATE']}"
        assert not list((Path(home) / 'launch').glob('*.word')), 'and no word was left in the home for it to read'
        mine = launchkey.remote_link(url, home)                    # ...the owner's own process: not one that server started
        assert mine.startswith(url + '/?k='), mine
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        try: conn.request('GET', mine[len(url):]); page = conn.getresponse().read().decode('utf-8', 'replace')
        finally: conn.close()
        assert SEED in page or 'Taskuary is updating' in page, page[:300]
    finally:
        try: p.stdin.write('\n'); p.stdin.flush()
        except OSError: pass
        try: p.wait(timeout=20)
        except subprocess.TimeoutExpired: p.kill()

def test_the_word_in_the_home_is_never_an_agents_to_read():
    from taskuary import config, readgate
    from taskuary.store import MemoryStore
    d = config.home() / 'launch'; d.mkdir(parents=True, exist_ok=True); (d / '0123456789abcdef.word').write_text('w', encoding='utf-8')
    for cmd in (f'cat "{d / "0123456789abcdef.word"}"', f'cat "{d}"/*.word', f'cd "{d}" && cat 0123456789abcdef.word'):
        assert readgate.of_command(MemoryStore(), 1, cmd, str(config.home().parent)) == ([], readgate.NEVER), cmd
    assert readgate.judge(MemoryStore(), 1, [str(d / '0123456789abcdef.word')], str(config.home().parent)) == ([], readgate.NEVER)
