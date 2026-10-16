"""HIPAA AI: the AI an organisation runs for its people (Vertex behind its own gateway), switched on with an access code -
the person's own gateway key, so usage is metered and billed per person and one code is revoked without touching anyone
else's (the owner, 2026-10-16: "it will be card called hipaa ai - access code"). The code is the only secret; the app ships
no key."""
import json, unittest
from pathlib import Path
from unittest import mock

from taskuary import llm
from taskuary.store import MemoryStore


class HipaaAiTests(unittest.TestCase):
    def test_it_is_an_ai_card_in_the_catalogue_and_on_every_install(self):
        self.assertIn('hipaa_ai', llm.AI_TYPES)
        cards = json.loads((Path(llm.__file__).parent / 'connectorcatalog.json').read_text(encoding='utf-8'))['cards']
        card = next(c for c in cards if c['type'] == 'hipaa_ai')
        self.assertEqual((card['title'], card['group']), ('HIPAA AI - access code', 'AI — agents & models'))
        self.assertTrue(MemoryStore().get_connector_by_type('hipaa_ai'))

    def test_the_access_code_is_the_bearer_key_to_the_gateway_and_the_model_is_its_alias(self):
        seen = {}
        def post(url, headers=None, json=None, timeout=None):
            seen.update(url=url, auth=headers.get('Authorization'), model=json.get('model'))
            r = mock.Mock(); r.status_code = 200; r.json.return_value = {'choices': [{'message': {'content': 'ok'}}]}
            return r
        fn = llm.make_llm('hipaa_ai', {'base_url': 'https://ai.northwind.example/v1/'}, 'hai-code-123')
        with mock.patch('taskuary.llm.requests.post', side_effect=post): self.assertEqual(fn('s', 'u'), 'ok')
        self.assertEqual(seen, {'url': 'https://ai.northwind.example/v1/chat/completions', 'auth': 'Bearer hai-code-123', 'model': 'hipaa-ai'})

    def test_with_no_gateway_address_it_says_whom_to_ask(self):
        with mock.patch.dict(llm.OPENAI_COMPATIBLE, {'hipaa_ai': ('', 'hipaa-ai')}), self.assertRaises(RuntimeError) as e:
            llm.make_llm('hipaa_ai', {}, 'hai-code-123')
        self.assertIn('gateway address', str(e.exception))


class ModelsByJobTests(unittest.TestCase):
    """Turning the card on fills each job's model from the gateway's own list (the owner, 2026-10-16: "pull the models available,
    then use lowest quickest for triage/assistant/advisor, and then ... sonnet default for agent work")."""
    MODELS = ['hipaa-ai', 'claude-opus-5-5', 'gemini-2.5-pro', 'claude-sonnet-5-5', 'gemini-3.8-flash']

    def test_the_fastest_model_for_triage_and_the_assistant_and_sonnet_for_the_agent(self):
        from taskuary import firstrun
        self.assertEqual(firstrun.pick_models(self.MODELS), ('gemini-3.8-flash', 'claude-sonnet-5-5'))
        self.assertEqual(firstrun.pick_models(['x-pro', 'x-flash-lite', 'x-flash']), ('x-flash-lite', 'x-pro'))
        self.assertEqual(firstrun.pick_models([]), ('', ''))

    def test_turning_it_on_sets_each_job_and_only_blank_ones_when_asked(self):
        from taskuary import firstrun, aidefaults
        s = MemoryStore()
        cid = s.get_connector_by_type('hipaa_ai')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'hai-code-123', 'Active': 1,
                          'ConfigJson': json.dumps({'base_url': 'https://ai.northwind.example/v1'})}, 'owner')
        with mock.patch('taskuary.llm.list_models', return_value=self.MODELS), mock.patch('taskuary.config.load', return_value={}):
            out = firstrun.models_by_job(s, {}, cid)
        self.assertEqual(out, {'fast': 'gemini-3.8-flash', 'agent': 'claude-sonnet-5-5'})
        for slot in ('triage_ai', 'concierge_ai', 'assistant_ai'): self.assertEqual(s.get_setting(slot), f'connector:{cid}')
        self.assertEqual(s.get_setting('assistant_model'), 'claude-sonnet-5-5')
        self.assertEqual(s.get_setting('concierge_model'), 'gemini-3.8-flash')
        t = MemoryStore(); t.set_setting('triage_ai', 'cli:claude', 'owner')
        tid = t.get_connector_by_type('hipaa_ai')['ConnectorId']
        t.save_connector({'ConnectorId': tid, 'Secret': 'hai-code-123', 'Active': 1}, 'owner')
        with mock.patch('taskuary.llm.list_models', return_value=self.MODELS):
            firstrun.models_by_job(t, {}, tid, only_blank=True)
        self.assertEqual(t.get_setting('triage_ai'), 'cli:claude', "the owner's own pick stays")
        self.assertEqual(t.get_setting('assistant_ai'), f'connector:{tid}')

    def test_switching_it_on_from_connections_fills_only_the_unpointed_jobs(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore(); s.set_setting('triage_ai', 'cli:claude', 'owner')
        cid = s.get_connector_by_type('hipaa_ai')['ConnectorId']
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.llm.list_models', return_value=self.MODELS):
            r = TestClient(server.app).post('/api/connectors', json={'ConnectorId': cid, 'Secret': 'hai-code-123', 'Active': 1}).json()
        self.assertEqual(r['discovery'], {'fast': 'gemini-3.8-flash', 'agent': 'claude-sonnet-5-5'})
        self.assertEqual((s.get_setting('triage_ai'), s.get_setting('assistant_ai')), ('cli:claude', f'connector:{cid}'))
