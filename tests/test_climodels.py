"""Model picks come from the CLI's own files: codex's models_cache.json and config.toml."""
import json, tempfile, unittest
from pathlib import Path
from unittest import mock
from taskuary import climodels, llm
from taskuary.store import MemoryStore

CACHE = {'models': [
    {'slug': 'gpt-5.6-sol', 'display_name': 'GPT-5.6-Sol', 'description': 'Latest frontier agentic coding model.', 'priority': 1, 'visibility': 'list',
     'default_reasoning_level': 'low', 'supported_reasoning_levels': [{'effort': 'low'}, {'effort': 'medium'}, {'effort': 'high'}, {'effort': 'xhigh'}]},
    {'slug': 'gpt-reserve', 'display_name': 'GPT-Reserve', 'priority': 2, 'visibility': 'hide', 'supported_reasoning_levels': [{'effort': 'high'}]},
    {'slug': 'gpt-5.4-mini', 'display_name': 'GPT-5.4-Mini', 'priority': 5, 'visibility': 'list', 'default_reasoning_level': 'medium',
     'supported_reasoning_levels': [{'effort': 'low'}, {'effort': 'medium'}]}]}


class CatalogTests(unittest.TestCase):
    def test_codex_models_are_read_off_its_cache_visible_ones_by_priority(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'models_cache.json').write_text(json.dumps(CACHE), encoding='utf-8')
            Path(d, 'config.toml').write_text('model = "gpt-5.6-sol"\nmodel_reasoning_effort = "high"\n', encoding='utf-8')
            with mock.patch.dict('os.environ', {'CODEX_HOME': d}):
                cat = climodels.catalog('codex')
        self.assertEqual([m['id'] for m in cat['models']], ['gpt-5.6-sol', 'gpt-5.4-mini'])           # hidden ones stay hidden
        self.assertEqual(cat['models'][0]['efforts'], ['low', 'medium', 'high', 'xhigh']); self.assertEqual(cat['models'][0]['default_effort'], 'low')
        self.assertEqual(cat['current'], {'model': 'gpt-5.6-sol', 'effort': 'high'}); self.assertIn('models_cache', cat['source'])
        self.assertEqual(cat['choices'], ['gpt-5.6-sol', 'gpt-5.4-mini'])

    def test_no_cache_falls_back_and_claude_stays_static(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict('os.environ', {'CODEX_HOME': d}):
            cat = climodels.catalog('codex')
        self.assertEqual(cat['source'], 'built-in'); self.assertTrue(cat['models'])
        self.assertIn('sonnet', climodels.catalog('claude')['choices'])
        self.assertEqual(climodels.split_pick('gpt-5.4-mini@low'), ('gpt-5.4-mini', 'low')); self.assertEqual(climodels.split_pick('opus'), ('opus', ''))

    def test_a_model_at_effort_pick_becomes_model_plus_reasoning_flag(self):
        s = MemoryStore()
        s.upsert_agent('codex', 'coding', 'cli', json.dumps({'cmd': 'codex', 'args': ['exec'], 'light_model': 'gpt-5.4-mini@low'}))
        seen = {}
        with mock.patch('taskuary.agents.run_cli', side_effect=lambda prof, p, t, **kw: (seen.update(prof), ('{}', None, None))[1]):
            llm.make_cli_llm(s, 'codex')('sys', 'user')
        self.assertEqual(seen['model'], 'gpt-5.4-mini'); self.assertEqual(seen['args'][-2:], ['-c', 'model_reasoning_effort=low'])
        # and the main model pick on a run does the same
        from taskuary.agents import run_cli
        with mock.patch('taskuary.agents._resolve_cmd', return_value=['X']), \
             mock.patch('taskuary.spawn.popen', side_effect=RuntimeError('stop')) as pop:
            with self.assertRaises(RuntimeError): run_cli({'cmd': 'codex', 'args': ['exec'], 'model': 'gpt-5.6-sol@xhigh'}, 'hi', lambda *a: None)
        argv = pop.call_args[0][0]
        self.assertEqual(argv[argv.index('--model') + 1], 'gpt-5.6-sol'); self.assertIn('model_reasoning_effort=xhigh', argv)
