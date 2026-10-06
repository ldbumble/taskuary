"""An installed CLI is not a connected one, and Remove removes (the owner, 2026-10-06: "can't remove the claude cli install",
"don't assume if cli installed to be used.. don't automatically connect them")."""
import copy, json, unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import cli_connections, config, server
from taskuary.store import MemoryStore

CLAUDE = {'cmd': 'claude', 'args': ['-p'], 'timeout': 60}


class RemoveRemovesTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.cfg = {**copy.deepcopy(server.cfg), 'cli_connections': {'claude': dict(CLAUDE)},
                    'agents': {'coder': {'provider': 'cli:claude', 'kind': 'coding'}, 'analyst': {'provider': 'cli:claude', 'kind': 'general'}}}
        for p in (mock.patch.object(server, 'store', self.s), mock.patch.object(server, 'cfg', self.cfg), mock.patch.object(config, 'save')):
            p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)

    def test_profiles_on_it_are_named_first_then_detached_never_moved(self):
        rows = self.c.get('/api/cli/connections').json()['data']
        self.assertEqual(next(r for r in rows if r['name'] == 'claude')['used_by'], ['coder', 'analyst'])
        self.assertEqual(self.c.delete('/api/cli/connections/claude').status_code, 409)
        r = self.c.delete('/api/cli/connections/claude?detach=1')
        self.assertEqual((r.status_code, r.json()['detached']), (200, ['coder', 'analyst']), r.text)
        self.assertNotIn('claude', self.cfg['cli_connections'])
        self.assertNotIn('provider', self.cfg['agents']['coder'])

    def test_a_profile_on_a_cli_that_is_gone_never_stops_the_app(self):
        cfg = {'cli_connections': {}, 'agents': {'coder': {'provider': 'cli:claude', 'kind': 'coding'}}}
        cli_connections.sync(cfg, self.s)                       # "CLI connection 'claude' is not configured" stopped every start


class NothingConnectsItselfTests(unittest.TestCase):
    def test_startup_connects_no_installed_cli(self):
        src = (Path(server.__file__)).read_text(encoding='utf-8')
        self.assertNotIn('cli_connections.adopt_installed(', src)


if __name__ == '__main__':
    unittest.main()
