"""The AI defaults panel: one screen that says what will actually run, and writes each half
back to the screen that owns it.

The bug this exists for: Settings named a brain and never a model, so "which model triages my
mail" had a different answer on a different page for every kind of brain, and the Triage page
could not tell you any of them (the owner, 2026-09-10).
"""
import json, unittest

from fastapi.testclient import TestClient

from taskuary import aidefaults, server
from taskuary.store import MemoryStore

c = TestClient(server.app)


def _store():
    s = MemoryStore()
    s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p']}))
    return s


class ResolveTests(unittest.TestCase):
    def test_a_cli_brain_reports_its_LIGHT_gear_not_its_coding_model(self):
        """The whole point of the two gears: triage must not quietly run the coding model."""
        s, cfg = _store(), {'agents': {'coder': {'cmd': 'claude', 'model': 'opus', 'light_model': 'haiku'}}}
        s.set_setting('triage_ai', 'cli:coder', 'o')
        r = aidefaults.resolve(s, cfg, 'triage_ai')
        self.assertEqual((r['model'], r['cli']), ('haiku', 'claude'))
        self.assertIn('light model', r['owner'])
        self.assertIn('haiku', r['choices'])

    def test_a_cli_brain_with_no_light_model_says_so(self):
        s, cfg = _store(), {'agents': {'coder': {'cmd': 'claude', 'model': 'opus'}}}
        s.set_setting('triage_ai', 'cli:coder', 'o')
        r = aidefaults.resolve(s, cfg, 'triage_ai')
        self.assertEqual(r['model'], '')
        self.assertIn('coding model', r['note'])           # the cost of leaving it blank, said out loud

    def test_codex_effort_only_light_gear_round_trips(self):
        """codex on a ChatGPT plan has no smaller model - its cheap gear IS the effort."""
        s, cfg = _store(), {'agents': {'x': {'cmd': 'codex', 'light_model': 'effort:low'}}}
        s.upsert_agent('x', 'coding', 'cli', json.dumps(cfg['agents']['x']))
        s.set_setting('triage_ai', 'cli:x', 'o')
        r = aidefaults.resolve(s, cfg, 'triage_ai')
        self.assertEqual((r['model'], r['effort']), ('', 'low'))

    def test_auto_names_the_connector_it_currently_resolves_to(self):
        """'auto' told the owner nothing about which model reads their mail."""
        s = _store()
        row = s.get_connector_by_type('anthropic')
        s.save_connector({'ConnectorId': row['ConnectorId'], 'Secret': 'k', 'Active': 1,
                          'ConfigJson': json.dumps({'model': 'claude-sonnet-5'})}, 'o')
        r = aidefaults.resolve(s, {}, 'triage_ai')
        self.assertEqual(r['value'], '')                    # still auto
        self.assertEqual(r['model'], 'claude-sonnet-5')
        self.assertIn('Anthropic', r['note'])               # ...and it says which card that is
        self.assertIn('card', r['owner'])

    def test_a_blank_connector_model_reports_the_provider_default(self):
        s = _store()
        row = s.get_connector_by_type('meta')
        s.save_connector({'ConnectorId': row['ConnectorId'], 'Secret': 'k', 'Active': 1, 'ConfigJson': '{}'}, 'o')
        s.set_setting('triage_ai', f"connector:{row['ConnectorId']}", 'o')
        r = aidefaults.resolve(s, {}, 'triage_ai')
        self.assertEqual(r['model'], '')
        self.assertIn('muse-spark-1.2', r['note'])          # blank is not "unconfigured"
        self.assertIn('muse-spark-1.2-contributor', r['choices'])

    def test_no_key_anywhere_is_reported_not_guessed(self):
        r = aidefaults.resolve(_store(), {}, 'triage_ai')
        self.assertFalse(r['ready']); self.assertIn('no AI connector', r['note'])

    def test_the_coding_slot_reads_the_MAIN_model(self):
        s, cfg = _store(), {'agents': {'coder': {'cmd': 'claude', 'model': 'opus', 'light_model': 'haiku'}}}
        s.set_setting('default_agent', 'coder', 'o')
        r = aidefaults.resolve(s, cfg, 'default_agent')
        self.assertEqual(r['model'], 'opus')                # not haiku
        self.assertEqual(r['owner_link'], 'agents')


class ApplyTests(unittest.TestCase):
    def test_setting_a_cli_brains_model_writes_the_light_model_and_leaves_coding_alone(self):
        s, cfg = _store(), {'agents': {'coder': {'cmd': 'claude', 'model': 'opus'}}}
        s.set_setting('triage_ai', 'cli:coder', 'o')
        out = aidefaults.apply(s, cfg, 'triage_ai', model='haiku')
        self.assertEqual(out['model'], 'haiku')
        self.assertEqual(cfg['agents']['coder']['light_model'], 'haiku')
        self.assertEqual(cfg['agents']['coder']['model'], 'opus')      # untouched
        self.assertEqual(json.loads(s.get_agent('coder')['Config'])['light_model'], 'haiku')  # and mirrored

    def test_effort_without_a_model_is_written_as_codex_spells_it(self):
        s, cfg = _store(), {'agents': {'x': {'cmd': 'codex'}}}
        s.upsert_agent('x', 'coding', 'cli', json.dumps(cfg['agents']['x']))
        s.set_setting('triage_ai', 'cli:x', 'o')
        aidefaults.apply(s, cfg, 'triage_ai', model='', effort='low')
        self.assertEqual(cfg['agents']['x']['light_model'], 'effort:low')

    def test_setting_a_connector_brains_model_writes_the_connector_card(self):
        s = _store()
        row = s.get_connector_by_type('anthropic')
        s.save_connector({'ConnectorId': row['ConnectorId'], 'Secret': 'k', 'Active': 1, 'ConfigJson': '{}'}, 'o')
        s.set_setting('triage_ai', f"connector:{row['ConnectorId']}", 'o')
        aidefaults.apply(s, {}, 'triage_ai', model='claude-haiku-4-5')
        conf = json.loads(s.get_connector(row['ConnectorId'])['ConfigJson'])
        self.assertEqual(conf['model'], 'claude-haiku-4-5')

    def test_clearing_a_model_removes_it_rather_than_saving_an_empty_string(self):
        """'' means back to the provider default, and a saved '' is not that."""
        s, cfg = _store(), {'agents': {'coder': {'cmd': 'claude', 'light_model': 'haiku'}}}
        s.set_setting('triage_ai', 'cli:coder', 'o')
        aidefaults.apply(s, cfg, 'triage_ai', model='')
        self.assertNotIn('light_model', cfg['agents']['coder'])

    def test_the_brain_and_the_model_can_be_set_in_one_call(self):
        s, cfg = _store(), {'agents': {'coder': {'cmd': 'claude'}}}
        aidefaults.apply(s, cfg, 'triage_ai', value='cli:coder', model='haiku')
        self.assertEqual(s.get_settings()['triage_ai'], 'cli:coder')
        self.assertEqual(cfg['agents']['coder']['light_model'], 'haiku')

    def test_an_unknown_slot_is_refused(self):
        with self.assertRaises(ValueError): aidefaults.apply(_store(), {}, 'not_a_slot', model='x')


class ApiTests(unittest.TestCase):
    def test_the_endpoint_returns_every_slot_with_its_owner(self):
        j = c.get('/api/ai/defaults').json()
        self.assertEqual([s['key'] for s in j['slots']], ['triage_ai', 'default_agent', 'concierge_ai'])
        for s in j['slots']:
            self.assertTrue(s['label'] and s['desc'] and s['why'])     # every row explains itself
            for k in ('model', 'effort', 'choices', 'efforts', 'owner', 'note'): self.assertIn(k, s)

    def test_a_bad_slot_is_a_422_not_a_500(self):
        self.assertEqual(c.post('/api/ai/defaults', json={'slot': 'nope', 'model': 'x'}).status_code, 422)


if __name__ == '__main__': unittest.main()
