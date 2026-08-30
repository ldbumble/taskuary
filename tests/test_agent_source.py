"""The AI itself as a report source.

"In Claude I have a skill that reviews our weekly user-management changes. I want to run that
once a week." A report's source was always something the AI read; here the source IS the AI
doing work - a CLI agent runs a saved skill (a slash command) and/or a prompt on the schedule,
and what it answers is filed onto the Timeline like any other report.
"""
import json, unittest
from unittest import mock

from taskuary import compose, reports
from taskuary.store import MemoryStore


class AgentSourceTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd': 'C:/elsewhere'}))

    def _fake_cli(self, calls):
        def make(store, name, model=None, cwd=None):
            calls.append({'name': name, 'model': model, 'cwd': cwd})
            return lambda system, user, **kw: f'ASKED[{user}]\n- 3 users added\n- 1 admin role granted'
        return make

    def test_it_is_a_report_type_that_needs_no_connection(self):
        self.assertIn('agent', reports.REGISTRY)
        row = next(c for c in compose.catalog(self.s) if c['type'] == 'agent')
        self.assertTrue(row['ready']); self.assertIsNone(row['connection'])
        self.assertIn('skill', row['takes'])

    def test_the_skill_and_the_prompt_become_one_slash_command_line(self):
        calls = []
        with mock.patch('taskuary.llm.make_cli_llm', self._fake_cli(calls)):
            head, body = reports.REGISTRY['agent'](reports.resolve_cfg(self.s, {
                'type': 'agent', 'skill': '/weekly-user-review', 'prompt': 'focus on admin roles', 'cwd': 'C:/work/fanapp', 'model': 'opus'}))
        self.assertEqual(calls, [{'name': 'coder', 'model': 'opus', 'cwd': 'C:/work/fanapp'}])
        self.assertIn('ASKED[/weekly-user-review focus on admin roles]', body)
        self.assertIn('coder ran /weekly-user-review', head)
        self.assertIn('3 lines', head)

    def test_a_prompt_alone_is_enough_and_a_bare_skill_is_too(self):
        with mock.patch('taskuary.llm.make_cli_llm', self._fake_cli([])):
            _, body = reports.REGISTRY['agent'](reports.resolve_cfg(self.s, {'type': 'agent', 'prompt': 'what changed?'}))
            self.assertIn('ASKED[what changed?]', body)
            _, body = reports.REGISTRY['agent'](reports.resolve_cfg(self.s, {'type': 'agent', 'skill': 'weekly-user-review'}))
            self.assertIn('ASKED[/weekly-user-review]', body)

    def test_the_last_run_shape_rides_along_so_runs_stay_comparable(self):
        """Two runs twenty minutes apart were two different documents. The previous run's headings
        and table columns - never its content - go into the next ask; a failed run anchors nothing."""
        cfg = {'type': 'agent', 'title': 'Daily GitHub Trending Projects', 'prompt': 'trending repos today'}
        with mock.patch('taskuary.llm.make_cli_llm', self._fake_cli([])):
            _, body = reports.REGISTRY['agent'](reports.resolve_cfg(self.s, cfg))
        self.assertNotIn('STRUCTURE', body)                                                    # first run: nothing to keep
        self.s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'SourceName': 'Daily GitHub Trending Projects',
                            'Subject': 'Daily GitHub Trending Projects — coder ran a prompt - 5 lines', 'SentAt': '2026-08-28 08:16:00',
                            'BodyText': '# GitHub Trending Report\n## Headline\nAI agents everywhere\n## Fast risers\n| Repo | Lang | Stars |\n|---|---|---|\n| a/b | Go | 900 |\nsecret content line'})
        self.s.add_message({'ExternalId': 'r2', 'Channel': 'report', 'SourceName': 'Daily GitHub Trending Projects',
                            'Subject': 'Daily GitHub Trending Projects — FAILED', 'SentAt': '2026-08-28 08:40:00', 'BodyText': '# Report error'})
        with mock.patch('taskuary.llm.make_cli_llm', self._fake_cli([])):
            _, body = reports.REGISTRY['agent'](reports.resolve_cfg(self.s, cfg))
        self.assertIn('STRUCTURE: keep the sections', body)
        self.assertIn('# GitHub Trending Report / ## Headline / ## Fast risers / | Repo | Lang | Stars |', body)
        self.assertNotIn('AI agents everywhere', body); self.assertNotIn('secret content', body)      # shape, not content
        self.assertNotIn('Report error', body)                                                       # the failed run is not the anchor

    def test_nothing_to_run_is_an_error_not_a_blank_report(self):
        with self.assertRaises(RuntimeError):
            reports.REGISTRY['agent'](reports.resolve_cfg(self.s, {'type': 'agent'}))
        with mock.patch('taskuary.llm.make_cli_llm', lambda *a, **k: None), self.assertRaises(RuntimeError):
            reports.REGISTRY['agent'](reports.resolve_cfg(self.s, {'type': 'agent', 'prompt': 'x', 'agent': 'ghost'}))

    def test_the_composer_accepts_a_skill_or_a_prompt_and_refuses_neither(self):
        ok, _ = compose.validate(self.s, {'type': 'agent', 'title': 'Weekly user review', 'skill': 'weekly-user-review'})
        self.assertTrue(ok)
        ok, why = compose.validate(self.s, {'type': 'agent', 'title': 'Weekly user review'})
        self.assertFalse(ok); self.assertIn('prompt|skill', why)

    def test_the_cli_runner_takes_the_working_directory(self):
        from taskuary import llm as llm_mod
        seen = {}
        def run_cli(prof, prompt, trace, resume=None): seen.update(prof=prof, prompt=prompt); return 'ok', None, None
        with mock.patch('taskuary.agents.run_cli', run_cli):
            f = llm_mod.make_cli_llm(self.s, 'coder', cwd='C:/work/fanapp')
            f('SYS', 'USER')
        self.assertEqual(seen['prof']['cwd'], 'C:/work/fanapp')
        self.assertTrue(seen['prompt'].startswith('SYS'))


if __name__ == '__main__':
    unittest.main()
