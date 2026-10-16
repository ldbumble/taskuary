"""The Assistant's fast mode (Settings > Assistant > Fast mode, 2026-10-13): "on by default if you choose codex but not for
claude". Codex's fast service tier rides the plan; Claude's fast mode is billed as extra usage, so it waits for an explicit on."""
import json, unittest
from unittest import mock
from taskuary import concierge, llm
from taskuary.store import MemoryStore


def store(cmd, fast=None):
    s = MemoryStore()
    s.upsert_agent(cmd, 'general', 'cli', json.dumps({'cmd': cmd, 'args': ['exec'] if cmd == 'codex' else ['-p']}))
    s.set_setting('concierge_ai', f'cli:{cmd}', 't')
    if fast: s.set_setting('concierge_fast', fast, 't')
    return s


class FastModeTests(unittest.TestCase):
    def test_auto_is_on_for_codex_and_off_for_claude_and_the_owner_overrides_either(self):
        self.assertEqual(MemoryStore().get_setting('concierge_fast'), 'auto')
        cases = [('codex', None, True), ('claude', None, False), ('claude', 'on', True), ('codex', 'off', False), ('gemini', None, False)]
        for cmd, fast, want in cases: self.assertEqual(llm.fast_on(store(cmd, fast), cmd), want, (cmd, fast))

    def test_each_cli_gets_its_own_spelling(self):
        self.assertEqual(llm.fast_args('codex'), ['-c', 'service_tier=fast'])           # bare word: no quotes through a shell
        flag, path = llm.fast_args('claude')
        self.assertEqual(flag, '--settings')
        with open(path, encoding='utf-8') as f: self.assertEqual(json.load(f), {'fastMode': True})   # a file, not JSON on argv
        self.assertEqual(llm.fast_args('gemini'), [])

    def _sent(self, s):
        seen = {}
        with mock.patch('taskuary.agents.run_cli', side_effect=lambda prof, *a, **k: seen.setdefault('args', prof['args']) and ''):
            b = concierge.brain(s, fast=True)
            try: b('system', 'hi')
            except Exception: pass
        return seen.get('args') or []

    def test_the_flags_reach_the_assistants_cli(self):
        a = self._sent(store('codex'))
        self.assertEqual(a[a.index('service_tier=fast') - 1], '-c')
        self.assertNotIn('--settings', self._sent(store('claude')))
        self.assertIn('--settings', self._sent(store('claude', 'on')))
        self.assertNotIn('service_tier=fast', self._sent(store('codex', 'off')))


if __name__ == '__main__':
    unittest.main()
