"""Model picks come from the CLI's own files: codex's models_cache.json and config.toml."""
import json, tempfile, unittest
from pathlib import Path
from unittest import mock
from taskuary import climodels, clis, llm
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

    def test_copilot_models_come_from_the_installed_sdks_visible_choices(self):
        declaration = ('export declare const HELP_VISIBLE_MODELS: '
                       '("gpt-5.4" | "claude-sonnet-4.6" | "gpt-5.4")[];')
        got = climodels.parse_copilot_models(declaration)
        self.assertEqual([m['id'] for m in got], ['auto', 'gpt-5.4', 'claude-sonnet-4.6'])

    def test_devin_catalog_uses_model_families_not_hundreds_of_reasoning_variants(self):
        listing = """Available models (2 families)

Claude Opus 5 (claude-opus-5)
  aliases: opus
  claude-opus-5-low     Claude Opus 5 Low
GPT-5.6 Sol (gpt-5.6-sol)
  gpt-5-6-sol-medium    GPT-5.6 Sol Medium
"""
        got = climodels.parse_devin_models(listing)
        self.assertEqual([(m['id'], m['label']) for m in got],
                         [('claude-opus-5', 'Claude Opus 5'), ('gpt-5.6-sol', 'GPT-5.6 Sol')])

    def test_copilot_and_devin_are_real_model_catalogues_not_empty_placeholders(self):
        with mock.patch.object(climodels, 'copilot_models', return_value=climodels._items(['auto', 'gpt-5.4'])), \
             mock.patch.object(climodels, 'devin_models', return_value=climodels.parse_devin_models('SWE-2 (swe-2)')):
            self.assertEqual(climodels.catalog('copilot')['choices'], ['auto', 'gpt-5.4'])
            self.assertEqual(climodels.catalog('devin')['choices'], ['swe-2'])

    def test_every_shipped_cli_has_a_provider_specific_model_picker(self):
        with mock.patch.object(climodels, 'devin_models', return_value=climodels._items(['adaptive'])), \
             mock.patch.object(climodels, 'copilot_models', return_value=climodels._items(['auto'])):
            missing = [row['name'] for row in clis.KNOWN if not climodels.catalog(row['name'])['choices']]
        self.assertEqual(missing, [])

    def test_chinese_cli_fallbacks_use_their_own_identifier_formats(self):
        with mock.patch.object(climodels, '_configured_models', return_value=([], {}, '')):
            self.assertEqual(climodels.catalog('qwen')['choices'], ['coder-model'])
            self.assertIn('kimi-code/kimi-for-coding', climodels.catalog('kimi')['choices'])
        self.assertIn('deepseek/deepseek-v4-pro', climodels.catalog('opencode')['choices'])
        self.assertIn('minimax/MiniMax-M3', climodels.catalog('opencode')['choices'])
        for name in ('qwen', 'kimi', 'opencode'):
            for model in climodels.STATIC[name]:
                self.assertTrue(model['id'])
                self.assertEqual(model['efforts'], [])  # do not send Codex's -c to another CLI

    def test_qwen_picker_reads_the_active_protocols_configured_ids(self):
        data = {'security': {'auth': {'selectedType': 'openai'}},
                'model': {'name': 'local-coder'}, 'modelProviders': {
                    'openai': [{'id': 'local-coder', 'name': 'Local coder', 'apiKey': 'private-key'}],
                    'anthropic': [{'id': 'different-provider-model'}]}}
        with tempfile.TemporaryDirectory() as d, mock.patch.dict('os.environ', {'QWEN_HOME': d}):
            Path(d, 'settings.json').write_text(json.dumps(data), encoding='utf-8')
            cat = climodels.catalog('qwen')
        self.assertEqual(cat['choices'], ['local-coder'])
        self.assertEqual(cat['current'], {'model': 'local-coder'})
        self.assertEqual(cat['models'][0]['label'], 'Local coder')
        self.assertNotIn('private-key', json.dumps(cat))

    def test_qwen_oauth_does_not_offer_ids_from_an_old_api_configuration(self):
        data = {'security': {'auth': {'selectedType': 'qwen-oauth'}}, 'model': {'name': 'old-api-model'}}
        with tempfile.TemporaryDirectory() as d, mock.patch.dict('os.environ', {'QWEN_HOME': d}):
            Path(d, 'settings.json').write_text(json.dumps(data), encoding='utf-8')
            self.assertEqual(climodels.catalog('qwen')['choices'], ['coder-model'])

    def test_kimi_picker_uses_aliases_and_updates_after_login_without_restart(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict('os.environ', {'KIMI_CODE_HOME': d}):
            self.assertIn('kimi-code/k3', climodels.catalog('kimi')['choices'])
            Path(d, 'config.toml').write_text(
                'default_model = "my-coder"\n[models.my-coder]\nprovider = "local"\n'
                'model = "raw-api-id"\ndisplay_name = "My coder"\n'
                '[providers.local]\napi_key = "private-key"\n', encoding='utf-8')
            cat = climodels.catalog('kimi')
        self.assertEqual(cat['choices'], ['my-coder'])
        self.assertEqual(cat['current'], {'model': 'my-coder'})
        self.assertNotIn('raw-api-id', json.dumps(cat))
        self.assertNotIn('private-key', json.dumps(cat))

    def test_unreadable_or_malformed_cli_config_keeps_documented_fallbacks(self):
        for name, env, filename in [('qwen', 'QWEN_HOME', 'settings.json'), ('kimi', 'KIMI_CODE_HOME', 'config.toml')]:
            with tempfile.TemporaryDirectory() as d, mock.patch.dict('os.environ', {env: d}):
                Path(d, filename).write_text('invalid{', encoding='utf-8')
                cat = climodels.catalog(name)
                self.assertEqual(cat['models'], climodels.STATIC[name])

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
