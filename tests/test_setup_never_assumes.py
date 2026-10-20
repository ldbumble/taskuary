"""SETUP NEVER ASSUMES AN AI (the owner, 2026-10-20: "every time someone is installing a fresh install of the .exe, the advisor says
claude is installed, set it up?? first of all it was not, and stop assuming that. I hate that. It should let them choose the AIs").

The default coding profile named `claude`; the first start split that into a `claude` CLI connection, and setup read the saved
connection as "Connected - pick it to make it your AI" and lit it, on a machine with no Claude Code at all. Each case here is a
machine as a fresh install finds it - an empty PATH, folders other apps leave behind, a remembered PATH answer gone stale, the
frozen exe - and asserts that nothing is said to be installed or connected that detection did not find, and that the line names
no vendor. The last case puts one fake CLI on PATH, so the honest positive is proved too."""
import json, os, re, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import agents, cli_connections, clis, config, firstrun, pathcache, server
from taskuary.store import MemoryStore

# every AI a setup line could name - none may appear in what it says before the person picks
VENDORS = re.compile(r'claude|codex|gemini|chatgpt|openai|anthropic|copilot|qwen|cursor|devin|kimi|opencode|muse', re.I)
CLAIMS = re.compile(r'\binstalled\b|\bconnected\b|\bon this computer\b|set it up', re.I)
FAKE = 'claude.cmd' if os.name == 'nt' else 'claude'


class FreshMachine(unittest.TestCase):
    """A scratch home, user profile and PATH: nothing of this machine's own CLIs can be seen."""
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='nw-fresh-'))
        self.home, self.tq, self.path = self.root / 'user', self.root / 'taskuary', self.root / 'bin'
        for d in (self.home, self.tq, self.path, self.home / 'AppData' / 'Roaming', self.home / 'AppData' / 'Local'): d.mkdir(parents=True)
        env = {'PATH': str(self.path), 'HOME': str(self.home), 'USERPROFILE': str(self.home), 'TASKUARY_HOME': str(self.tq),
               'APPDATA': str(self.home / 'AppData' / 'Roaming'), 'LOCALAPPDATA': str(self.home / 'AppData' / 'Local'),
               'CLAUDE_CONFIG_DIR': str(self.home / '.claude'), 'CODEX_HOME': str(self.home / '.codex')}
        ps = [mock.patch.dict(os.environ, env),
              # the registry's PATH is the dev box's, never a fresh machine's
              mock.patch.object(agents, '_fresh_path', lambda: os.environ.get('PATH', '')),
              mock.patch.object(Path, 'home', classmethod(lambda cls: self.home))]
        for p in ps: p.start(); self.addCleanup(p.stop)
        pathcache.forget(); self.addCleanup(pathcache.forget)
        self.s = MemoryStore()

    def leftovers(self):
        """What other apps - or an uninstalled CLI - leave in a profile: config folders, never a program that runs."""
        for d in ('.claude', '.codex', '.gemini', '.claude/local', 'AppData/Roaming/Claude', 'AppData/Local/AnthropicClaude',
                  'AppData/Roaming/npm/node_modules/@anthropic-ai/claude-code'):
            (self.home / d).mkdir(parents=True, exist_ok=True)
        (self.home / '.claude.json').write_text('{"numStartups": 3}')
        (self.home / '.claude' / 'settings.json').write_text('{}')

    def fake(self, d=None):
        f = Path(d or self.path) / FAKE
        f.write_text('@echo ok\r\n' if os.name == 'nt' else '#!/bin/sh\necho ok\n'); f.chmod(0o755)
        return f

    def state(self):
        cfg = config.load()                                    # the fresh home's own config.toml, as the first start writes it
        cli_connections.migrate(cfg); config.save(cfg)
        return firstrun.state(self.s)

    def says_nothing_assumed(self, st):
        self.assertEqual([a['name'] for a in st['ais'] if a['installed']], [], 'nothing is on PATH')
        self.assertEqual([a['name'] for a in st['ais'] if a['connected']], [], 'nothing was connected')
        self.assertFalse(st['brain']['ready']); self.assertEqual(st['brain']['name'], '')
        self.assertEqual(st['step'], 'ai')
        self.assertIsNone(VENDORS.search(st['next']), st['next']); self.assertIsNone(CLAIMS.search(st['next']), st['next'])
        self.assertIn('pick', st['next'].lower(), 'it asks the person to choose')


class NothingIsAssumedTests(FreshMachine):
    def test_a_fresh_home_saves_no_ai_connection(self):
        cfg = config.load()
        cli_connections.migrate(cfg)                           # what the first start runs on it (server.py)
        self.assertEqual(cfg.get('cli_connections') or {}, {}, 'a fresh install names no CLI')
        self.assertNotIn('cmd', cfg['agents']['coding'], 'the coding profile is instructions, not a vendor')
        self.assertIsNone(VENDORS.search(json.dumps(cfg['agents'])), cfg['agents'])

    def test_an_empty_path_offers_the_choice_and_claims_nothing(self):
        self.says_nothing_assumed(self.state())

    def test_folders_other_apps_leave_are_not_an_install(self):
        self.leftovers()
        self.says_nothing_assumed(self.state())
        self.assertFalse(any(r['installed'] for r in clis.detect(self.s)), 'a config folder is not a program')

    def test_the_frozen_exe_finds_nothing_either(self):
        self.leftovers()
        with mock.patch.object(sys, 'frozen', True, create=True):
            self.says_nothing_assumed(self.state())

    def test_a_connection_saved_for_a_cli_that_is_not_here_is_not_connected(self):
        """A home made by 0.3.9.11 or before already carries the `claude` connection the old default split off."""
        cfg = config.load()
        cfg['cli_connections'] = {'claude': cli_connections.with_defaults({'cmd': 'claude'})}; config.save(cfg)
        self.says_nothing_assumed(firstrun.state(self.s))

    def test_a_remembered_answer_for_a_cli_since_removed_is_not_trusted(self):
        f = self.fake()
        self.assertTrue(clis.which('claude'), 'the lookup is remembered')
        f.unlink()
        self.says_nothing_assumed(self.state())

    def test_the_api_the_page_reads_claims_nothing(self):
        self.leftovers()
        cfg = config.load(); cli_connections.migrate(cfg); config.save(cfg)
        cfg = {**server.cfg, 'agents': cfg['agents'], 'cli_connections': cfg.get('cli_connections') or {}}   # the server's own [server]
        with mock.patch.object(server, 'store', self.s), mock.patch.object(server, 'cfg', cfg):
            c = TestClient(server.app)
            self.says_nothing_assumed(c.get('/api/setup/first-run').json())
            self.says_nothing_assumed(c.get('/api/setup').json())
            rows = c.get('/api/cli/detect').json()['data']
            self.assertEqual([r['name'] for r in rows if r['installed'] or r['configured']], [])
            rows = c.get('/api/cli/connections').json()['data']
            self.assertEqual([r['name'] for r in rows if r['installed'] or r['configured']], [])


class TheHonestPositiveTests(FreshMachine):
    def test_one_cli_on_path_is_found_and_still_only_offered(self):
        self.fake()
        st = self.state()
        self.assertEqual([a['name'] for a in st['ais'] if a['installed']], ['claude'], 'the one that is here is found')
        self.assertEqual([a['name'] for a in st['ais'] if a['connected']], [], 'found is not connected: nothing was picked')
        self.assertFalse(st['brain']['ready']); self.assertEqual(st['step'], 'ai')
        self.assertIsNone(VENDORS.search(st['next']), 'the server line still names no vendor - the screen says it found one')
        row = next(r for r in clis.detect(self.s) if r['name'] == 'claude')
        self.assertEqual(Path(row['path']).resolve(), (self.path / FAKE).resolve())

    def test_one_the_person_connected_and_that_is_here_reads_connected(self):
        self.fake()
        cfg = config.load()
        cfg['cli_connections'] = {'claude': cli_connections.with_defaults({'cmd': 'claude'})}; config.save(cfg)
        st = firstrun.state(self.s)
        self.assertEqual([a['name'] for a in st['ais'] if a['connected']], ['claude'])


class TheScreenNamesOnlyWhatWasFoundTests(unittest.TestCase):
    """The setup line and the lit card are drawn on the page (FirstRun.jsx, setupSteps.cardOf); website/test pins the rule and
    website/browser/fresh-setup.test.mjs the rendered page. Here: the source still carries the rule, so neither can quietly drift."""
    def test_no_ai_card_is_lit_by_default(self):
        src = (Path(__file__).resolve().parents[1] / 'website' / 'src' / 'setupSteps.js').read_text(encoding='utf-8')
        self.assertIn('(view === "mail" ? can[0] : null)', src)


if __name__ == '__main__':
    unittest.main()
