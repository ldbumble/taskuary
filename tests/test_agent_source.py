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
        def make(store, name, model=None, cwd=None, **_kwargs):
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
                'type': 'agent', 'skill': '/weekly-user-review', 'prompt': 'focus on admin roles', 'cwd': 'C:/work/census', 'model': 'opus'}))
        self.assertEqual(calls, [{'name': 'coder', 'model': 'opus', 'cwd': 'C:/work/census'}])
        self.assertIn('ASKED[/weekly-user-review focus on admin roles]', body)
        self.assertIn('coder ran /weekly-user-review', head)
        self.assertIn('3 lines', head)

    def test_a_prompt_alone_is_enough_and_a_bare_skill_is_too(self):
        with mock.patch('taskuary.llm.make_cli_llm', self._fake_cli([])):
            _, body = reports.REGISTRY['agent'](reports.resolve_cfg(self.s, {'type': 'agent', 'prompt': 'what changed?'}))
            self.assertIn('ASKED[what changed?]', body)
            _, body = reports.REGISTRY['agent'](reports.resolve_cfg(self.s, {'type': 'agent', 'skill': 'weekly-user-review'}))
            self.assertIn('ASKED[/weekly-user-review]', body)

    def test_a_taskuary_owned_skill_is_expanded_for_any_cli_provider(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        calls = []
        with TemporaryDirectory() as tmp, mock.patch('taskuary.config.home', return_value=Path(tmp)):
            skill = Path(tmp) / 'skills' / 'daily-watch'; skill.mkdir(parents=True)
            (skill / 'SKILL.md').write_text('# Daily watch\nCheck every current source and cite it.', encoding='utf-8')
            with mock.patch('taskuary.llm.make_cli_llm', self._fake_cli(calls)):
                _, body = reports.REGISTRY['agent'](reports.resolve_cfg(self.s, {
                    'type': 'agent', 'skill': 'daily-watch', 'prompt': "Produce today's report."}))
        self.assertIn('TASKUARY SKILL /daily-watch', body)
        self.assertIn('Check every current source', body)
        self.assertIn("RUN INPUT\nProduce today's report.", body)

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

    def test_an_agent_that_could_not_reach_its_source_is_a_failed_run(self):
        """The morning trending report, 2026-09-03: the web tool was refused, the agent narrated the
        refusal in 14 lines, and the apology filed as news - triage then read it as a defect and opened
        a bug task on an unrelated repo. A run that never reached its source fails like the timeout does."""
        blocked = ("I'll fetch the trending page now.\n\n**Tool Use: WebFetch**\n\n**Tool Result:**\n"
                   'Web search is not available on this Claude account. Please try again later.\n\n'
                   'I could not fetch the page, so there is no report today.')
        with mock.patch('taskuary.llm.make_cli_llm', lambda *a, **k: (lambda s, u, **kw: blocked)):
            with self.assertRaises(RuntimeError) as e:
                reports.REGISTRY['agent'](reports.resolve_cfg(self.s, {'type': 'agent', 'prompt': 'top 15 trending'}))
        self.assertIn('could not run this report', str(e.exception))
        self.assertIn('Web search is not available', str(e.exception))              # the excuse is kept, visibly

    def test_a_real_report_that_mentions_a_failure_is_still_a_report(self):
        """The guard is short AND shapeless. One unlucky sentence inside a document proves nothing."""
        real = ('# Trending\n\n| Repo | Lang | Stars today |\n|---|---|---|\n| a/b | Go | 900 |\n'
                '| c/d | Rust | 400 |\n\nNote: total stars were unable to fetch for one row.')
        with mock.patch('taskuary.llm.make_cli_llm', lambda *a, **k: (lambda s, u, **kw: real)):
            head, body = reports.REGISTRY['agent'](reports.resolve_cfg(self.s, {'type': 'agent', 'prompt': 'top 15 trending'}))
        self.assertIn('| a/b | Go | 900 |', body); self.assertIn('coder ran a prompt', head)

    def test_a_scheduled_agent_keeps_its_timeout_and_the_classifier_keeps_the_short_leash(self):
        """Two of that report's four runs died at exactly "timed out after 300s": the 300s cap belongs
        to the classifier reading one message, not to an agent the owner scheduled into a repo to research."""
        from taskuary import llm as llm_mod
        self.s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'timeout': 1500}))
        seen = {}
        def run_cli(prof, prompt, trace, resume=None): seen['timeout'] = prof.get('timeout'); return 'ok', None, None
        with mock.patch('taskuary.agents.run_cli', run_cli):
            llm_mod.make_cli_llm(self.s, 'coder', cwd='C:/work/census')('SYS', 'USER')
            self.assertEqual(seen['timeout'], 1500)
            llm_mod.make_cli_llm(self.s, 'coder')('SYS', 'USER')
            self.assertEqual(seen['timeout'], 300)
            llm_mod.make_cli_llm(self.s, 'coder', read_only=True, research=True)('SYS', 'USER')
            self.assertEqual(seen['timeout'], 1500)

    def test_the_cli_runner_takes_the_working_directory(self):
        from taskuary import llm as llm_mod
        seen = {}
        def run_cli(prof, prompt, trace, resume=None): seen.update(prof=prof, prompt=prompt); return 'ok', None, None
        with mock.patch('taskuary.agents.run_cli', run_cli):
            f = llm_mod.make_cli_llm(self.s, 'coder', cwd='C:/work/census')
            f('SYS', 'USER')
        self.assertEqual(seen['prof']['cwd'], 'C:/work/census')
        self.assertTrue(seen['prompt'].startswith('SYS'))

    def test_agent_reports_are_read_only_and_only_workflows_receive_write_access(self):
        calls = []
        def make(store, name, model=None, cwd=None, **kwargs):
            calls.append({'cwd': cwd, **kwargs})
            return lambda *_args, **_kwargs: '# Result\nread complete'
        with mock.patch('taskuary.llm.make_cli_llm', make):
            reports.REGISTRY['agent'](reports.resolve_cfg(self.s, {
                'type': 'agent', 'prompt': 'Fetch GitHub Trending'}))
            reports.REGISTRY['agent'](reports.resolve_cfg(self.s, {
                'type': 'agent', 'access': 'write', 'prompt': 'Update the records'}))
        self.assertEqual(calls[0]['read_only'], True)
        self.assertEqual(calls[0]['research'], True)
        self.assertEqual(calls[0]['cli_tools'], False)
        self.assertEqual(calls[1]['read_only'], False)
        self.assertEqual(calls[1]['research'], False)
        self.assertEqual(calls[1]['cli_tools'], True)

    def test_read_only_claude_reports_can_retrieve_but_cannot_write_or_run_commands(self):
        from taskuary import clis
        args = clis.report_read_args('claude', [
            '-p', '--dangerously-skip-permissions', '--output-format', 'stream-json', '--verbose'])
        self.assertNotIn('--dangerously-skip-permissions', args)
        tools = args[args.index('--tools') + 1].split(',')
        self.assertEqual(tools, ['Read', 'Glob', 'Grep', 'WebFetch', 'WebSearch'])
        self.assertNotIn('Bash', tools); self.assertNotIn('Edit', tools); self.assertNotIn('Write', tools)
        self.assertEqual(args[args.index('--disallowedTools') + 1], 'mcp__*')

    def test_the_report_run_is_granted_the_tools_it_is_given(self):
        """--tools only says the tool EXISTS. Without --allowedTools, headless WebFetch/WebSearch
        prompted an operator who was asleep, so the trending report came back as a refusal notice
        four runs in a row (2026-09-04). Every tool the run may see, it may also use."""
        from taskuary import clis
        args = clis.report_read_args('claude', ['-p', '--dangerously-skip-permissions'])
        self.assertEqual(args[args.index('--tools') + 1], args[args.index('--allowedTools') + 1])
        for t in ('WebFetch', 'WebSearch'): self.assertIn(t, args[args.index('--allowedTools') + 1].split(','))
        for t in ('Bash', 'Edit', 'Write'): self.assertNotIn(t, args[args.index('--allowedTools') + 1].split(','))

    def test_the_report_composer_may_choose_a_read_only_agent(self):
        out = compose.compose(self.s, 'Fetch GitHub Trending every morning', lambda *_a, **_k: json.dumps({
            'config': {'type': 'agent', 'title': 'GitHub Trending', 'agent': 'coder',
                       'prompt': 'Fetch and summarize the top repositories', 'daily_at': '08:00'},
            'explain': 'Reads GitHub and files the summary.', 'confidence': 'high'}),
            exclude_types=('zoho_monthly_invoices',))
        self.assertEqual(out['config']['type'], 'agent')
        self.assertNotIn('access', out['config'])


if __name__ == '__main__':
    unittest.main()
