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
    assert c.post('/api/launch-key', headers={'X-Taskuary-Token': 'wrong'}).status_code == 401
    k = c.post('/api/launch-key').json()['key']                 # the owner (conftest's default header)
    assert TOK() in c.get(f'/?k={k}').text

def test_link_adds_a_fresh_key():
    a, b = launchkey.link('http://127.0.0.1:7787'), launchkey.link('http://127.0.0.1:7787/')
    assert a.startswith('http://127.0.0.1:7787/?k=') and b.startswith('http://127.0.0.1:7787/?k=') and a != b

def test_remote_link_asks_the_running_server_with_the_owner_token(monkeypatch):
    seen = {}
    class Resp:
        status = 200
        def read(self): return b'{"key": "abc"}'
    class Conn:
        def __init__(self, host, port, timeout=None): seen['at'] = (host, port)
        def request(self, m, path, headers=None, body=None): seen.update(m=m, path=path, h=headers)
        def getresponse(self): return Resp()
        def close(self): pass
    monkeypatch.setattr(launchkey.http.client, 'HTTPConnection', Conn)
    assert launchkey.remote_link('http://127.0.0.1:7795', 'own') == 'http://127.0.0.1:7795/?k=abc'
    assert seen['m'] == 'POST' and seen['path'] == '/api/launch-key' and seen['h']['X-Taskuary-Token'] == 'own' and seen['at'] == ('127.0.0.1', 7795)
    class Bad(Conn):
        def getresponse(self): raise OSError('refused')
    monkeypatch.setattr(launchkey.http.client, 'HTTPConnection', Bad)
    assert launchkey.remote_link('http://127.0.0.1:7795', 'own') == 'http://127.0.0.1:7795'   # an old server: the plain address

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
    monkeypatch.setattr(desktop, 'already_serving', lambda: '')
    monkeypatch.setattr(desktop, 'start_server', lambda port=None: (types.SimpleNamespace(), 'http://127.0.0.1:7801'))
    monkeypatch.setattr(desktop, 'serving', lambda u, secs=0: True); monkeypatch.setattr(desktop, 'stop_server', lambda s: 'clean')
    monkeypatch.setattr(sys, 'argv', ['taskuary-desktop'])
    desktop.main()
    assert loaded and loaded[0].startswith('http://127.0.0.1:7801/?k=') and launchkey.redeem(loaded[0].split('k=')[1])
    assert made['maximized']        # a fixed 1280x840 hung off a laptop's screen on every launch (TQ-1251)

def test_the_desktop_view_of_a_running_instance_asks_it_for_a_key(monkeypatch):
    made = {}
    fake = types.SimpleNamespace(create_window=lambda *a, **k: made.update(k) or object(), start=lambda f=None: None)
    monkeypatch.setitem(sys.modules, 'webview', fake)
    monkeypatch.setattr(desktop, 'already_serving', lambda: 'http://127.0.0.1:7787')
    monkeypatch.setattr(launchkey, 'remote_link', lambda url, tok: f'{url}/?k=fromserver')
    monkeypatch.setattr(sys, 'argv', ['taskuary-desktop'])
    desktop.main()
    assert made['url'] == 'http://127.0.0.1:7787/?k=fromserver'
