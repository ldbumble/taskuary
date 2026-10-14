"""Wave B, B4: a keyed launch address never sits on a browser's command line, where any local process - a restricted
session's shell among them - can read it out of the process list; and a page whose stored token went stale says how to
get in, not "reload" (a reload no longer re-seeds it, R29)."""
import os, sys, time, pytest
from pathlib import Path
from urllib.parse import urlsplit, unquote
from urllib.request import url2pathname
from fastapi.testclient import TestClient
from taskuary import cli, config, launchkey, server

@pytest.fixture(autouse=True)
def _keys(): launchkey._KEYS.clear()

def _file(opened: str) -> Path:
    assert opened.startswith('file:') and '?k=' not in opened and 'k=' not in opened
    return Path(url2pathname(unquote(urlsplit(opened).path)))

def test_the_cli_opens_its_own_server_through_a_private_file(monkeypatch):
    opened = []
    monkeypatch.setattr(cli.webbrowser, 'open', opened.append)
    cli.open_when_ready('http://127.0.0.1:9', lambda u: True, open_it=cli._open_keyed)
    f = _file(opened[0]); html = f.read_text(encoding='utf-8')
    assert f.is_relative_to(config.home())                         # where the floor already keeps a stranger out
    key = html.split('?k=')[1].split('"')[0]
    assert 'http://127.0.0.1:9/?k=' in html and launchkey.redeem(key)
    if os.name != 'nt': assert (f.stat().st_mode & 0o777) == 0o600

def test_a_running_instance_is_opened_the_same_way(monkeypatch):
    opened = []
    monkeypatch.setattr(cli.webbrowser, 'open', opened.append)
    monkeypatch.setattr(cli, '_busy', lambda h, p: True); monkeypatch.setattr(cli, '_is_taskuary', lambda u: True)
    monkeypatch.setattr(launchkey, 'remote_link', lambda url, tok: f'{url}/?k=fromserver')
    monkeypatch.setattr(sys, 'argv', ['taskuary'])
    cli.main()
    assert '/?k=fromserver' in _file(opened[0]).read_text(encoding='utf-8')

def test_an_unkeyed_address_opens_as_it_is(monkeypatch):
    "An old server that hands out no key: there is nothing to hide, so no file."
    opened = []
    monkeypatch.setattr(cli.webbrowser, 'open', opened.append)
    cli._open_private('http://127.0.0.1:9')
    assert opened == ['http://127.0.0.1:9']

def test_old_launch_files_are_cleared(monkeypatch):
    monkeypatch.setattr(cli.webbrowser, 'open', lambda u: None)
    d = config.home() / 'launch'; d.mkdir(exist_ok=True)
    old = d / 'old.html'; old.write_text('x'); t = time.time() - launchkey.TTL - 5; os.utime(old, (t, t))
    cli._open_private('http://127.0.0.1:9/?k=abc')
    assert not old.exists() and list(d.glob('*.html'))            # the new one, and any still within their TTL

def test_a_stale_token_is_told_how_to_get_in_not_to_reload():
    r = TestClient(server.app).get('/api/settings', headers={'X-Taskuary-Token': 'a-token-from-before'})
    assert r.status_code == 401 and r.json()['code'] == 'unauthorized'
    assert 'taskuary --link' in r.json()['detail'] and 'reload' not in r.json()['detail']
