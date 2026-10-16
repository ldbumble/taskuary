"""A bug report's facts are gathered by code, not by a model: where it happened, the error, the
versions, and the log lines around it. What the person did is reported as action names only."""
import hashlib, json, platform, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

import taskuary
from taskuary import bugreport
from taskuary.store import MemoryStore


def _client(**kw):
    return {'screen': 'Work', 'route': '/api/tasks/123/code', 'error': 'TypeError: x is undefined',
            'stack': 'TypeError: x is undefined\n    at openTask (assets/index-abc.js:10:5)\n    at click (assets/index-abc.js:99:1)',
            'actions': ['opened Work', 'pressed Start', 'opened a task', 'pressed Next', 'pressed Code', 'pressed Send'],
            'at': '2026-10-14T10:00:50', **kw}


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.s, self.home = MemoryStore(), Path(tempfile.mkdtemp())
        p = mock.patch('taskuary.config.home', return_value=self.home); p.start(); self.addCleanup(p.stop)

    def test_the_environment_names_version_install_os_python_brains_and_connectors(self):
        self.s.save_connector({'Type': 'imap', 'Name': 'alex@northwind.example', 'Active': 1}, 'test')
        self.s.save_connector({'Type': 'github', 'Name': 'off one', 'Active': 0}, 'test')
        st = {'pick': 'connector:9', 'Name': 'alex@northwind.example', 'Type': 'anthropic', 'ready': True, 'why': ''}
        with mock.patch('taskuary.llm.brain_status', return_value=st):
            env = bugreport.collect(self.s, _client())['env']
        self.assertIn(f'Taskuary {taskuary.__version__}', env)
        self.assertIn(platform.system(), env)
        self.assertIn(f'Python {sys.version_info.major}.{sys.version_info.minor}', env)
        self.assertIn('anthropic', env); self.assertIn('imap', env)
        self.assertNotIn('github', env)                               # switched off
        self.assertNotIn('northwind', env)                            # a Name can be an account: never reported

    def test_install_kind(self):
        def kind(frozen=False, docker=False, home='', source=False):
            with mock.patch('taskuary.deps.frozen', return_value=frozen), \
                 mock.patch.object(bugreport, '_dockerenv', return_value=docker), \
                 mock.patch.dict('os.environ', {'TASKUARY_HOME': home or str(self.home)}), \
                 mock.patch.object(bugreport, '_source', return_value=source):
                return bugreport.install_kind()
        self.assertEqual('exe', kind(frozen=True, source=True))
        self.assertEqual('docker', kind(docker=True, source=True))
        self.assertEqual('docker', kind(home='/data'))
        self.assertEqual('source', kind(source=True))
        self.assertEqual('pip', kind())
        self.assertEqual('source', bugreport.install_kind())          # this checkout has pyproject.toml beside the package

    def test_a_cli_brain_is_reported_by_its_cli_name(self):
        self.s.upsert_agent('coding', 'cli', 'cli', json.dumps({'cmd': 'claude'}))
        st = {'pick': 'cli:claude', 'Name': 'coding (CLI)', 'Type': 'cli', 'ready': True, 'why': ''}
        with mock.patch('taskuary.llm.brain_status', return_value=st):
            self.assertIn('claude (cli)', bugreport.collect(self.s, _client())['env'])

    def test_where_actions_and_error(self):
        f = bugreport.collect(self.s, _client())
        self.assertIn('Work', f['where']); self.assertIn('/api/tasks/123/code', f['where'])
        self.assertEqual(['pressed Start', 'opened a task', 'pressed Next', 'pressed Code', 'pressed Send'], f['actions'])
        self.assertTrue(f['error'].startswith('TypeError: x is undefined'))

    def test_the_fingerprint_ignores_ids_and_later_frames(self):
        a = bugreport.collect(self.s, _client())['fingerprint']
        self.assertRegex(a, r'^[0-9a-f]{10}$')
        self.assertEqual(a, bugreport.collect(self.s, _client(route='/api/tasks/77/code'))['fingerprint'])
        self.assertEqual(a, bugreport.collect(self.s, _client(route='/api/tasks/' + 'ab' * 16 + '/code'))['fingerprint'])
        self.assertEqual(a, bugreport.collect(self.s, _client(stack=_client()['stack'].replace('99:1', '5:5')))['fingerprint'])
        self.assertNotEqual(a, bugreport.collect(self.s, _client(error='RangeError: no'))['fingerprint'])
        self.assertNotEqual(a, bugreport.collect(self.s, _client(route='/api/feed'))['fingerprint'])
        want = hashlib.sha1('TypeError|/api/tasks/:id/code|at openTask (assets/index-abc.js:10:5)'.encode()).hexdigest()[:10]
        self.assertEqual(want, a)

    def test_route_normalising(self):
        self.assertEqual('/api/tasks/:id/code', bugreport.norm_route('/api/tasks/123/code'))
        self.assertEqual('/api/x/:id', bugreport.norm_route('/api/x/' + '0f' * 16))
        self.assertEqual('/api/v2/feed', bugreport.norm_route('/api/v2/feed'))

    def test_the_log_is_the_thirty_lines_nearest_the_error(self):
        lines = [f'2026-10-14 10:{i // 60:02d}:{i % 60:02d} INFO    taskuary.server:1 line {i}' for i in range(100)]
        lines.insert(51, 'Traceback (most recent call last):')     # belongs to line 50's record
        (self.home / 'taskuary.log').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        log = bugreport.collect(self.s, _client())['log'].splitlines()
        self.assertEqual(30, len(log))
        self.assertEqual('Traceback (most recent call last):', log[-1]); self.assertTrue(log[-2].endswith('line 50'))
        self.assertNotIn('line 51', '\n'.join(log))
        self.assertTrue(bugreport.collect(self.s, _client(at=''))['log'].endswith('line 99'))   # no time: the newest

    def test_a_missing_log_is_empty_not_an_error(self):
        self.assertEqual('', bugreport.collect(self.s, _client())['log'])

    def test_a_bare_client_still_collects(self):
        f = bugreport.collect(self.s, {})
        self.assertEqual([], f['actions']); self.assertEqual('', f['error']); self.assertRegex(f['fingerprint'], r'^[0-9a-f]{10}$')
        self.assertEqual({'where', 'error', 'env', 'log', 'actions', 'fingerprint'}, set(f))


if __name__ == '__main__':
    unittest.main()
