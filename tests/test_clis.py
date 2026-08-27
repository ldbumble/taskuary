"""The setup wizard's CLI rows (clis.detect): a configured profile is shown as the CLI it runs,
and says whether that CLI is even on this machine."""
import json, unittest
from unittest import mock

from taskuary import clis
from taskuary.store import MemoryStore


class DetectTests(unittest.TestCase):
    def test_a_profile_named_coder_running_claude_is_claude_code(self):
        s = MemoryStore()
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p']}))
        with mock.patch('shutil.which', return_value=None):
            rows = {r['name']: r for r in clis.detect(s)}
        r = rows['coder']
        self.assertEqual((r['label'], r['profile'], r['cmd'], r['installed'], r['path']), ('Claude Code', 'coder', 'claude', False, ''))

    def test_an_installed_profile_shows_its_path(self):
        s = MemoryStore()
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        with mock.patch('shutil.which', side_effect=lambda c, **k: r'C:\\Users\\me\\AppData\\Roaming\\npm\\claude.cmd' if c == 'claude' else None):
            r = next(x for x in clis.detect(s) if x['name'] == 'coder')
        self.assertTrue(r['installed']); self.assertIn('claude.cmd', r['path'])


class StoreAppTests(unittest.TestCase):
    def test_a_windowsapps_package_path_is_not_run_directly(self):
        from taskuary import agents
        import os
        pkg = r'C:\\Program Files\\WindowsApps\\OpenAI.Codex_1.0_x64__abc\\app\\resources\\codex.EXE'
        with mock.patch('shutil.which', return_value=pkg), mock.patch.object(os, 'name', 'nt'), mock.patch('os.path.exists', return_value=False):
            self.assertEqual(agents._resolve_cmd('codex'), ['cmd', '/c', 'codex'])
        alias = os.path.join(os.environ.get('LOCALAPPDATA', 'X'), 'Microsoft', 'WindowsApps', 'codex.EXE')
        with mock.patch('shutil.which', return_value=pkg), mock.patch.object(os, 'name', 'nt'), mock.patch('os.path.exists', side_effect=lambda p: p == alias):
            self.assertEqual(agents._resolve_cmd('codex'), [alias])


if __name__ == '__main__': unittest.main()
