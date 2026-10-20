"""HIPAA AI: the AI an organisation runs for its people (Vertex behind its own gateway), switched on with an access code -
the person's own gateway key, so usage is metered and billed per person and one code is revoked without touching anyone
else's (the owner, 2026-10-16: "it will be card called hipaa ai - access code"). The code is the only secret; the app ships
no key."""
import json, unittest
import pytest
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


class _Gateway:
    """A gateway on this computer that answers /v1/models and /v1/chat/completions - or turns every code away (`status`)."""
    def __init__(self, allow, status=200):
        import http.server, threading
        me = self
        class H(http.server.BaseHTTPRequestHandler):
            def _send(self, body):
                code = me.status if self.path.startswith('/v1/') else 404
                self.send_response(code); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(json.dumps(body if code == 200 else {'error': 'no'}).encode())
            def do_GET(self): self._send({'data': [{'id': 'hipaa-ai'}]})
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length') or 0)); self._send({'choices': [{'message': {'content': 'ok'}}]})
            def log_message(self, *a): pass
        self.status, self.srv = status, http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.url = f'http://127.0.0.1:{allow(self.srv.server_address[1])}'
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def __enter__(self): return self
    def __exit__(self, *a): self.srv.shutdown(); self.srv.server_close()


def _closed_port():
    import socket
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    return port


class GatewayAddressTests(unittest.TestCase):
    """The card asks for the gateway address, since this build ships none: with only the code it could never connect, and said
    "That key didn't work ... copy all of it again" about an address nobody had been asked for (the owner, 2026-10-20)."""
    CODE = 'hai-code-1234567890'

    @pytest.fixture(autouse=True)
    def _loopback(self, allow_test_port): self.allow = allow_test_port

    def setUp(self):
        self.s = MemoryStore(); self.cid = self.s.get_connector_by_type('hipaa_ai')['ConnectorId']

    def choose(self, address):
        from taskuary import firstrun
        return firstrun.choose_key(self.s, 'hipaa_ai', self.CODE, cid=self.cid, config={'base_url': address})

    def saved(self): return json.loads(self.s.get_connector(self.cid).get('ConfigJson') or '{}').get('base_url')

    def test_the_build_ships_no_address(self):
        self.assertEqual(llm.HIPAA_AI_URL, '')

    def test_an_address_is_taken_as_pasted_and_saved_ending_v1(self):
        for raw in ('https://ai.northwind.example', 'https://ai.northwind.example/', 'https://ai.northwind.example/v1/',
                    'ai.northwind.example', ' https://ai.northwind.example/v1/models '):
            self.assertEqual(llm.gateway_url(raw), 'https://ai.northwind.example/v1', raw)
        self.assertEqual(llm.gateway_url('https://ai.northwind.example/llm'), 'https://ai.northwind.example/llm/v1')
        self.assertEqual(llm.gateway_url('http://localhost:4000'), 'http://localhost:4000/v1')
        self.assertEqual(llm.gateway_url(''), '')

    def test_plain_http_is_refused_anywhere_but_this_computer(self):
        for raw in ('http://ai.northwind.example', 'ftp://ai.northwind.example'):
            with self.assertRaises(ValueError) as e: llm.gateway_url(raw)
            self.assertEqual(str(e.exception), llm.GATEWAY_NOT_HTTPS)
        self.assertEqual(self.choose('http://ai.northwind.example')['why'], llm.GATEWAY_NOT_HTTPS)

    def test_no_address_says_add_it_not_that_the_key_failed(self):
        out = self.choose('')
        self.assertEqual((out['ok'], out['why']), (False, llm.GATEWAY_MISSING))
        self.assertNotIn("key didn't work", out['why'])
        self.assertEqual(llm.gateway_problem({}, self.CODE), llm.GATEWAY_MISSING)

    def test_an_address_that_does_not_answer_says_so(self):
        out = self.choose(f'http://127.0.0.1:{self.allow(_closed_port())}')
        self.assertEqual((out['ok'], out['why']), (False, llm.GATEWAY_SILENT))
        self.assertTrue(self.saved().endswith('/v1'), 'the address stays on the card for the next try')

    def test_a_page_that_is_no_gateway_did_not_answer_either(self):
        with _Gateway(self.allow) as g: self.assertEqual(llm.gateway_problem({'base_url': f'{g.url}/elsewhere'}, self.CODE), llm.GATEWAY_SILENT)

    def test_only_a_gateway_that_turned_the_code_away_blames_the_code(self):
        for status in (401, 403):
            with _Gateway(self.allow, status) as g: out = self.choose(g.url)
            self.assertEqual((out['ok'], out['why']), (False, llm.GATEWAY_CODE))
            self.assertNotRegex(out['why'], r'\d{3}')
        with _Gateway(self.allow, 500) as g: self.assertEqual(llm.gateway_problem({'base_url': g.url}, self.CODE), llm.GATEWAY_FAULT)

    def test_the_saved_address_is_what_test_and_the_model_list_use(self):
        with _Gateway(self.allow) as g:
            self.s.save_connector({'ConnectorId': self.cid, 'Secret': self.CODE, 'ConfigJson': json.dumps({'base_url': g.url})}, 'owner')
            self.assertIn('model responded: ok', llm.test_ai(self.s, self.cid))
            self.assertEqual(llm.list_models('hipaa_ai', {'base_url': g.url}, self.CODE), ['hipaa-ai'])

    def test_the_connections_card_saves_it_normalised_and_says_when_it_is_built_in(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        with mock.patch.object(server, 'store', self.s):
            c = TestClient(server.app)
            r = c.post('/api/connectors', json={'ConnectorId': self.cid, 'ConfigJson': json.dumps({'base_url': 'ai.northwind.example/'})})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(self.saved(), 'https://ai.northwind.example/v1')
            r = c.post('/api/connectors', json={'ConnectorId': self.cid, 'ConfigJson': json.dumps({'base_url': 'http://ai.northwind.example'})})
            self.assertEqual((r.status_code, r.json()['detail']), (422, llm.GATEWAY_NOT_HTTPS))
            row = next(x for x in c.get('/api/connectors').json()['data'] if x['Type'] == 'hipaa_ai')
            self.assertIs(row['GatewayBuiltIn'], False)
