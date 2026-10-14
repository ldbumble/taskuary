"""Wave B, B4: a keyed launch address never sits on a browser's command line, where any local process - a restricted
session's shell among them - can read it out of the process list; and a page whose stored token went stale says how to
get in, not "reload" (a reload no longer re-seeds it, R29)."""
import os, sys, time, types, pytest
from pathlib import Path
from fastapi.testclient import TestClient
from taskuary import cli, config, launchkey, server

BROWSER = '"C:\\Browsers\\web.exe" --single-argument %1'

@pytest.fixture(autouse=True)
def _keys(): launchkey._KEYS.clear()

@pytest.fixture
def launched(monkeypatch):
    "The registered http browser, faked: what it was started with. webbrowser.open must not be used for a keyed address."
    out = []
    monkeypatch.setattr(cli, '_http_browser', lambda: BROWSER)
    monkeypatch.setattr(cli.subprocess, 'Popen', lambda cmd, **kw: out.append(cmd))
    monkeypatch.setattr(cli.webbrowser, 'open', lambda u: pytest.fail(f'opened {u} on a command line'))
    return out

def _file(cmd: str) -> Path:
    assert cmd.startswith('"C:\\Browsers\\web.exe" --single-argument ') and 'k=' not in cmd
    return Path(cmd.split('--single-argument ', 1)[1])

def test_the_cli_opens_its_own_server_through_a_private_file(launched):
    cli.open_when_ready('http://127.0.0.1:9', lambda u: True, open_it=cli._open_keyed)
    f = _file(launched[0]); html = f.read_text(encoding='utf-8')
    assert f.is_relative_to(config.home())                         # where the floor already keeps a stranger out
    key = html.split('?k=')[1].split('"')[0]
    assert 'http://127.0.0.1:9/?k=' in html and launchkey.redeem(key)
    if os.name != 'nt': assert (f.stat().st_mode & 0o777) == 0o600

def test_a_running_instance_is_opened_the_same_way(monkeypatch, launched):
    monkeypatch.setattr(cli, '_busy', lambda h, p: True); monkeypatch.setattr(cli, '_is_taskuary', lambda u: True)
    monkeypatch.setattr(launchkey, 'remote_link', lambda url, tok: f'{url}/?k=fromserver')
    monkeypatch.setattr(sys, 'argv', ['taskuary'])
    cli.main()
    assert '/?k=fromserver' in _file(launched[0]).read_text(encoding='utf-8')

def test_with_no_browser_to_name_it_falls_back_to_the_keyed_address(monkeypatch):
    "The .html association may be an editor, which would show the file instead of the app: never trusted for it."
    opened, spawned = [], []
    monkeypatch.setattr(cli, '_http_browser', lambda: None)
    monkeypatch.setattr(cli.subprocess, 'Popen', lambda cmd, **kw: spawned.append(cmd))
    monkeypatch.setattr(cli.webbrowser, 'open', opened.append)
    cli._open_private('http://127.0.0.1:9/?k=abc')
    assert opened == ['http://127.0.0.1:9/?k=abc'] and not spawned

def test_an_unkeyed_address_opens_as_it_is(monkeypatch):
    "An old server that hands out no key: there is nothing to hide, so no file."
    opened = []
    monkeypatch.setattr(cli.webbrowser, 'open', opened.append)
    cli._open_private('http://127.0.0.1:9')
    assert opened == ['http://127.0.0.1:9']

def test_old_launch_files_are_cleared(launched):
    d = config.home() / 'launch'; d.mkdir(exist_ok=True)
    old = d / 'old.html'; old.write_text('x'); t = time.time() - launchkey.TTL - 5; os.utime(old, (t, t))
    cli._open_private('http://127.0.0.1:9/?k=abc')
    assert not old.exists() and list(d.glob('*.html'))            # the new one, and any still within their TTL


# ── the registered browser ──────────────────────────────────────────────────────────────────────────────────────────
class _Reg:
    "winreg, faked: {(root, path): {value name: data}}."
    HKEY_CURRENT_USER, HKEY_CLASSES_ROOT = 'HKCU', 'HKCR'
    def __init__(self, keys): self.keys = keys
    def OpenKey(self, root, path):
        if (root, path) not in self.keys: raise OSError(path)
        return _Key(self.keys[(root, path)])
    def QueryValueEx(self, k, name):
        if name not in k.v: raise OSError(name)
        return k.v[name], 1

class _Key:
    def __init__(self, v): self.v = v
    def __enter__(self): return self
    def __exit__(self, *a): pass

UC = r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice'

def test_the_browser_is_read_from_the_http_user_choice(monkeypatch):
    monkeypatch.setattr(cli, 'os', types.SimpleNamespace(name='nt'), raising=False)
    monkeypatch.setattr(cli, '_winreg', _Reg({('HKCU', UC): {'ProgId': 'WebHTML'}, ('HKCR', r'WebHTML\shell\open\command'): {'': BROWSER}}))
    assert cli._http_browser() == BROWSER

@pytest.mark.parametrize('keys', [{}, {('HKCU', UC): {'ProgId': 'WebHTML'}}, {('HKCU', UC): {}},
                                  {('HKCU', UC): {'ProgId': 'X'}, ('HKCR', r'X\shell\open\command'): {'': 'notepad.exe'}}])
def test_no_usable_browser_is_none(monkeypatch, keys):
    "No choice, no command, or a command with no place for the address."
    monkeypatch.setattr(cli, 'os', types.SimpleNamespace(name='nt'), raising=False)
    monkeypatch.setattr(cli, '_winreg', _Reg(keys))
    assert cli._http_browser() is None

def test_off_windows_there_is_no_registry_to_ask(monkeypatch):
    monkeypatch.setattr(cli, 'os', types.SimpleNamespace(name='posix'), raising=False)
    assert cli._http_browser() is None

def test_a_command_with_a_quoted_placeholder_gets_the_path_quoted(monkeypatch):
    assert cli._with_target('"C:\\b.exe" "%1"', 'C:\\x y\\f.html') == '"C:\\b.exe" "C:\\x y\\f.html"'
    assert cli._with_target('"C:\\b.exe" --single-argument %1', 'C:\\x y\\f.html') == '"C:\\b.exe" --single-argument C:\\x y\\f.html'
    assert cli._with_target('"C:\\b.exe" -url %1', 'C:\\x y\\f.html') == '"C:\\b.exe" -url "C:\\x y\\f.html"'


def test_a_stale_token_is_told_how_to_get_in_not_to_reload():
    r = TestClient(server.app).get('/api/settings', headers={'X-Taskuary-Token': 'a-token-from-before'})
    assert r.status_code == 401 and r.json()['code'] == 'unauthorized'
    assert 'taskuary --link' in r.json()['detail'] and 'reload' not in r.json()['detail']
