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
