"""THE AGENT CONNECTOR INSTALLED BESIDE ITS CLI (the owner, 2026-11-06: "will the adapters get installed when you set up claude code cli
tool in the card section. we need to do that. it does not have to be built in no?"). npm is a fake throughout: `npm ls -g` answers from
a dict, and `npm install -g` writes into it - nothing here installs anything on this machine."""
import json, os
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import acpadapter, agents, cliinstall, clis, guard, server, troubleshoot
from taskuary.store import MemoryStore

pytestmark = pytest.mark.acp                     # keeps clis.ADAPTERS (conftest.no_real_acp_adapters)
PKG, WANT = acpadapter.split(clis.ADAPTERS['claude']['pkg'])


class FakeNpm:
    "npm ls -g answers from `pkgs`; npm install -g <pkg@v> puts it there. Every command it saw, in `ran`."
    def __init__(self, pkgs=None, fails=False): self.pkgs, self.fails, self.ran, self.said = dict(pkgs or {}), fails, [], []
    def ls(self, _exe): self.ran.append('ls'); return dict(self.pkgs)
    def __call__(self, cmd, timeout=900):          # the installer's runner: the CLI's own recipe, and the connector's npm
        self.ran.append(cmd)
        if cmd[1:3] == ['install', '-g'] and not self.fails:
            n, v = acpadapter.split(cmd[-1]); self.pkgs[n] = v
        return (1, 'npm ERR! network') if self.fails and cmd[1:3] == ['install', '-g'] else (0, 'ok')
    def message(self, t): self.said.append(t)     # the visible terminal's own words (cli_install_terminal.ShellRunner)


@pytest.fixture
def npm(monkeypatch, tmp_path):
    cliinstall.reset(); acpadapter.forget(); acpadapter._BUSY.clear()
    f = FakeNpm()
    exe = tmp_path / ('claude.exe' if os.name == 'nt' else 'claude'); exe.write_text('', encoding='utf-8')
    monkeypatch.setattr(acpadapter, '_read', f.ls)
    monkeypatch.setattr(cliinstall, 'npm', lambda: 'npm')
    monkeypatch.setattr(cliinstall, 'plan', lambda *a, **k: [{'how': 'script', 'cmd': ['claude-installer']}])
    monkeypatch.setattr(cliinstall, 'find', lambda n: str(exe))
    monkeypatch.setattr(cliinstall, 'broken', lambda *a: '')
    monkeypatch.setattr(cliinstall, 'ensure_on_path', lambda *a, **k: False)    # no PATH, registry or rc file written
    from taskuary import hooks
    monkeypatch.setattr(hooks, 'install_user', lambda *a, **k: None)
    yield f
    cliinstall.reset(); acpadapter.forget()


def npm_installs(f): return [c for c in f.ran if c != 'ls' and c[1:3] == ['install', '-g']]


# ── 1. the CLI's install takes one more visible step ──────────────────────────────────────────────────────────────────────
def test_installing_claude_also_installs_its_pinned_connector_as_a_visible_step(npm):
    out = cliinstall.install('claude', runner=npm)
    assert out['phase'] == 'done' and 'Agent connector' in out['detail']
    assert npm.ran[0] == ['claude-installer']                                         # the CLI first
    assert npm_installs(npm) == [cliinstall.npm_install(f'{PKG}@{WANT}')]                # then the pinned connector, once
    assert acpadapter.STEP in npm.said and npm.pkgs[PKG] == WANT


def test_a_connector_already_installed_is_skipped(npm):
    npm.pkgs[PKG] = WANT
    out = cliinstall.install('claude', runner=npm)
    assert out['phase'] == 'done' and not npm_installs(npm)
    assert any('already installed' in t for t in npm.said)


def test_no_npm_still_finishes_the_cli_install_and_says_so(npm, monkeypatch):
    monkeypatch.setattr(cliinstall, 'npm', lambda: '')
    out = cliinstall.install('claude', runner=npm)
    assert out['phase'] == 'done' and out['path']                                     # the CLI is installed all the same
    assert npm.ran == [['claude-installer']]
    assert 'npm is not on this machine' in out['detail'] and 'still work' in out['detail']


def test_a_connector_that_fails_to_install_never_fails_the_cli(npm):
    npm.fails = True
    out = cliinstall.install('claude', runner=npm)
    assert out['phase'] == 'done' and 'did not install' in out['detail']


def test_an_update_brings_the_connector_up_to_the_pin_too(npm, monkeypatch):
    npm.pkgs[PKG] = '0.1.0'
    monkeypatch.setattr(cliinstall, 'update_plan', lambda n: [{'how': 'self', 'args': ['update']}])
    assert cliinstall.update('claude', runner=npm)['phase'] == 'done' and npm.pkgs[PKG] == WANT


def test_the_card_s_own_press_installs_the_connector_alone(npm):
    out = cliinstall.connector('claude', runner=npm)
    assert out['phase'] == 'done' and out['verb'] == 'connector'
    assert ['claude-installer'] not in npm.ran and npm.pkgs[PKG] == WANT
    assert cliinstall.connector('gemini')['phase'] == 'failed'                       # no connector to install for one that needs none


def test_set_it_up_installs_the_connector_in_the_background(npm, monkeypatch):
    monkeypatch.setattr(cliinstall, '_run', npm)
    started = []
    monkeypatch.setattr(acpadapter.threading, 'Thread', lambda target, **k: mock.Mock(start=lambda: started.append(target)))
    assert acpadapter.start('claude') and acpadapter.state('claude')['status'] == 'installing'
    started[0]()
    assert npm.pkgs[PKG] == WANT and acpadapter.state('claude')['status'] == 'installed'
    assert not acpadapter.start('claude')                                             # here already: nothing to do


# ── 2. the card's line ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_state_reads_npm_once_and_says_each_case(npm, monkeypatch):
    assert acpadapter.state('claude')['status'] == 'missing'
    for have, st in ((WANT, 'installed'), ('0.1.0', 'update'), ('99.0.0', 'other')):
        npm.pkgs[PKG] = have
        assert acpadapter.state('claude', refresh=True) == {'pkg': PKG, 'want': WANT, 'have': have, 'status': st}
    n = npm.ran.count('ls')
    for _ in range(5): acpadapter.state('claude')                                     # a page draw is never an npm spawn
    assert npm.ran.count('ls') == n
    monkeypatch.setattr(cliinstall, 'npm', lambda: '')
    assert acpadapter.state('claude')['status'] == 'no_npm'
    assert acpadapter.state('gemini') == {}


def test_a_stale_answer_is_served_while_a_fresh_one_is_read_behind_it(npm, monkeypatch):
    acpadapter.state('claude'); acpadapter._LS['at'] = 0.1                           # long past TTL
    npm.pkgs[PKG] = WANT
    later = []
    monkeypatch.setattr(acpadapter.threading, 'Thread', lambda target, **k: mock.Mock(start=lambda: later.append(target)))
    assert acpadapter.state('claude')['status'] == 'missing' and later                 # the old answer, at once
    later[0]()
    assert acpadapter.state('claude')['status'] == 'installed'


def test_the_cli_card_carries_the_connector_line(npm, monkeypatch):
    rows = [{'name': 'claude', 'cmd': 'claude', 'label': 'Claude Code', 'installed': True, 'install': 'claude'},
            {'name': 'gemini', 'cmd': 'gemini', 'label': 'Gemini CLI', 'installed': True, 'install': 'gemini'}]
    monkeypatch.setattr(clis, 'detect', lambda store=None: rows)
    for k in ('cli_connections', 'agents'): monkeypatch.setitem(server.cfg, k, {})
    data = {r['name']: r for r in TestClient(server.app).get('/api/cli/connections').json()['data']}
    assert data['claude']['connector'] == {'pkg': PKG, 'want': WANT, 'have': '', 'status': 'missing'}
    assert 'connector' not in data['gemini']


def test_the_connector_press_is_the_owner_s_alone():
    assert guard.denied('POST', '/api/cli/connector') and guard.denied('POST', '/api/cli/connector/terminal')
    assert TestClient(server.app).post('/api/cli/connector', json={'name': 'gemini'}).status_code == 422


# ── 3. only the pinned version runs ───────────────────────────────────────────────────────────────────────────────────────
def shim(tmp_path, version):
    "npm's global layout on Windows: the launcher beside node_modules/<pkg>/package.json."
    d = tmp_path / 'npm'; (d / 'node_modules' / PKG).mkdir(parents=True, exist_ok=True)
    (d / 'node_modules' / PKG / 'package.json').write_text(json.dumps({'name': PKG, 'version': version}), encoding='utf-8')
    exe = d / 'claude-agent-acp.cmd'; exe.write_text('', encoding='utf-8')
    return str(exe)


@pytest.mark.parametrize('version,runs', [(WANT, 'own'), ('0.1.0', 'npx'), ('99.0.0', 'npx')])
def test_the_global_adapter_runs_only_at_the_pinned_version(tmp_path, version, runs):
    exe = shim(tmp_path, version)
    with mock.patch.object(agents.pathcache, 'which', return_value=exe), \
         mock.patch.object(agents, '_resolve_cmd', side_effect=lambda c: ['npx'] if c == 'npx' else ['/opt/bin/claude']), \
         mock.patch.object(acpadapter, '_read', side_effect=AssertionError('read beside the launcher, never an npm spawn')):
        cmd = agents.acp_launch({'cmd': 'claude', 'args': []})['cmd']
    assert cmd == ([exe] if runs == 'own' else ['npx', '-y', f'{PKG}@{WANT}'])


def test_a_launcher_whose_package_cannot_be_found_asks_npm(tmp_path, npm):
    exe = tmp_path / 'claude-agent-acp'; exe.write_text('', encoding='utf-8')
    ad = clis.ADAPTERS['claude']
    assert not acpadapter.runs_pinned(ad, str(exe))
    npm.pkgs[PKG] = WANT; acpadapter.forget()
    assert acpadapter.runs_pinned(ad, str(exe))


# ── 4. the troubleshooter knows it ────────────────────────────────────────────────────────────────────────────────────────
def test_a_slow_agent_start_is_answered_with_the_connector_install(npm):
    s = MemoryStore()
    for asked in ('claude', 'Claude Code', 'the agent connector'):
        h = troubleshoot.health(s, asked)
        assert not h['ok'] and 'npx' in h['why'] and h['fix'] == {'label': 'Install the connector', 'href': '#cli-agents'}, asked
    assert troubleshoot.chips(h) == [{'verb': 'go', 'href': '#cli-agents', 'label': 'Install the connector'}]
    assert 'Install the connector' in troubleshoot.words(h)
    npm.pkgs[PKG] = '0.1.0'; acpadapter.forget()
    assert troubleshoot.health(s, 'claude')['fix']['label'] == 'Update the connector'
    npm.pkgs[PKG] = WANT; acpadapter.forget()
    assert troubleshoot.health(s, 'claude')['ok']
