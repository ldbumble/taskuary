"""HIPAA AI: the AI an organisation runs for its people (Vertex behind its own gateway), switched on with an access code -
the person's own gateway key, so usage is metered and billed per person and one code is revoked without touching anyone
else's (the owner, 2026-10-16: "it will be card called hipaa ai - access code"). The code is the only secret; the app ships
no key."""
import json, unittest
import pytest
from pathlib import Path
from unittest import mock

from taskuary import brainroute, llm
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

    def test_switching_it_on_never_takes_a_job_a_brain_already_runs(self):
        """2026-11-09: switched on in Connections, the card took the general agent off the Claude Code the blank slot already ran on, and
        wrote it as the owner's pick - a general ask then started on a gateway nobody chose. A ready CLI, or another AI card on, keeps
        every blank job blank; with neither, the card fills them, saved for the owner, never as their choice."""
        from taskuary import firstrun
        for ready, other in ((['claude'], False), ([], True)):
            s = MemoryStore()
            if other: s.save_connector({'ConnectorId': s.get_connector_by_type('azure_openai')['ConnectorId'], 'Secret': 'az-key-123456', 'Active': 1}, 'owner')
            cid = s.get_connector_by_type('hipaa_ai')['ConnectorId']
            s.save_connector({'ConnectorId': cid, 'Secret': 'hai-code-123', 'Active': 1}, 'owner')
            with mock.patch('taskuary.llm.list_models', return_value=self.MODELS), mock.patch('taskuary.agents.ready_brains', return_value=ready):
                firstrun.models_by_job(s, {}, cid, only_blank=True)
            self.assertEqual([s.get_setting(k) or '' for k in ('triage_ai', 'concierge_ai', 'assistant_ai')], ['', '', ''], (ready, other))
        s = MemoryStore(); cid = s.get_connector_by_type('hipaa_ai')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'hai-code-123', 'Active': 1}, 'owner')
        with mock.patch('taskuary.llm.list_models', return_value=self.MODELS), mock.patch('taskuary.agents.ready_brains', return_value=[]):
            firstrun.models_by_job(s, {}, cid, only_blank=True)
        self.assertEqual((s.get_setting('assistant_ai'), s.setting_writer('assistant_ai')), (f'connector:{cid}', 'migration'))


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

    def test_a_page_that_is_no_gateway_is_the_wrong_address(self):
        with _Gateway(self.allow) as g: self.assertEqual(llm.gateway_problem({'base_url': f'{g.url}/elsewhere'}, self.CODE), llm.GATEWAY_NOT_GATEWAY)

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


class _Site:
    """Anything at an address that answers every GET the same way: status, content type, body and any extra headers."""
    def __init__(self, allow, status, ctype, body, headers=()):
        import http.server, threading
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(status); self.send_header('Content-Type', ctype)
                for k, v in headers: self.send_header(k, v)
                self.end_headers(); self.wfile.write(body.encode())
            def log_message(self, *a): pass
        self.srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.url = f'http://127.0.0.1:{allow(self.srv.server_address[1])}'
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def __enter__(self): return self
    def __exit__(self, *a): self.srv.shutdown(); self.srv.server_close()


class WrongAddressTests(unittest.TestCase):
    """An admin site pasted as the gateway address answered with its own page or a sign-in redirect, and the card said the access
    code didn't work - the code was fine, the address was not. Only the gateway itself, in its own JSON, can turn a code away."""
    CODE = 'hai-code-1234567890'
    HTML = '<!doctype html><html><body>Sign in</body></html>'

    @pytest.fixture(autouse=True)
    def _loopback(self, allow_test_port): self.allow = allow_test_port

    def problem(self, *site):
        with _Site(self.allow, *site) as s: return llm.gateway_problem({'base_url': s.url}, self.CODE)

    def test_a_web_page_is_the_wrong_address(self):
        self.assertEqual(self.problem(200, 'text/html', self.HTML), llm.GATEWAY_NOT_GATEWAY)

    def test_a_sign_in_redirect_is_the_wrong_address(self):
        self.assertEqual(self.problem(302, 'text/html', '', [('Location', 'https://admin.example/login?next=/v1/models')]), llm.GATEWAY_NOT_GATEWAY)

    def test_a_sign_in_wall_that_is_not_the_gateway_does_not_blame_the_code(self):
        for status in (401, 403): self.assertEqual(self.problem(status, 'text/html', self.HTML), llm.GATEWAY_NOT_GATEWAY)

    def test_json_that_is_not_a_model_list_is_the_wrong_address(self):
        self.assertEqual(self.problem(200, 'application/json', '{"ok": true}'), llm.GATEWAY_NOT_GATEWAY)
        self.assertEqual(self.problem(404, 'application/json', '{"detail": "Not Found"}'), llm.GATEWAY_NOT_GATEWAY)

    def test_the_gateway_turning_the_code_away_blames_the_code(self):
        for status in (401, 403):
            self.assertEqual(self.problem(status, 'application/json', '{"error": {"message": "Authentication Error"}}'), llm.GATEWAY_CODE)

    def test_a_model_list_is_a_working_gateway(self):
        self.assertEqual(self.problem(200, 'application/json', '{"data": [{"id": "hipaa-ai"}]}'), '')

    def test_nothing_listening_says_it_could_not_reach_the_address(self):
        self.assertEqual(llm.gateway_problem({'base_url': f'http://127.0.0.1:{self.allow(_closed_port())}'}, self.CODE), llm.GATEWAY_SILENT)
        self.assertIn("Couldn't reach", llm.GATEWAY_SILENT)

    def test_the_wrong_address_message_names_the_address_not_the_code(self):
        self.assertIn('web page', llm.GATEWAY_NOT_GATEWAY); self.assertIn('admin site', llm.GATEWAY_NOT_GATEWAY)
        self.assertNotIn("code didn't work", llm.GATEWAY_NOT_GATEWAY)

    def test_the_card_says_it_through_connect(self):
        from taskuary import firstrun
        s = MemoryStore(); cid = s.get_connector_by_type('hipaa_ai')['ConnectorId']
        with _Site(self.allow, 302, 'text/html', '', [('Location', 'https://admin.example/login')]) as site:
            out = firstrun.choose_key(s, 'hipaa_ai', self.CODE, cid=cid, config={'base_url': site.url})
        self.assertEqual((out['ok'], out['why']), (False, llm.GATEWAY_NOT_GATEWAY))


# the effort setting, as the OpenAI and Azure cards take it (2026-11-06)
def _posted(body, status=200):
    r = mock.Mock(); r.status_code, r.text = status, json.dumps(body); r.json.return_value = body; return r


def test_hipaa_ai_takes_effort_and_drops_it_quietly_when_its_gateway_refuses():
    sent = []
    def post(url, headers=None, json=None, timeout=None):
        sent.append(dict(json))
        if 'reasoning_effort' in json: return _posted({'error': {'message': 'reasoning_effort is not supported for this model'}}, 422)
        return _posted({'choices': [{'message': {'content': 'ok'}}]})
    llm._NO_EFFORT.clear()
    fn = llm.make_llm('hipaa_ai', {'base_url': 'https://ai.northwind.example/v1', 'model': 'hipaa-ai@high'}, 'hai-code-123')
    with mock.patch('taskuary.llm.requests.post', side_effect=post): assert fn('s', 'u') == 'ok'
    assert sent[0]['reasoning_effort'] == 'high' and 'reasoning_effort' not in sent[1] and sent[0]['model'] == 'hipaa-ai'
    s = MemoryStore(); cid = s.get_connector_by_type('hipaa_ai')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'hai-code-123', 'Active': 1, 'ConfigJson': json.dumps({'model': 'hipaa-ai'})}, 'owner')
    assert brainroute.lift(s, f'connector:{cid}', 'strong', cfg={}) == 'hipaa-ai@high'


def _jpeg(channels: int, adobe: bool) -> bytes:
    "A JPEG's header as a decoder walks it: Adobe's APP14 when asked, a frame of `channels`, a scan."
    seg = lambda m, body: bytes([0xFF, m]) + (len(body) + 2).to_bytes(2, 'big') + body
    sof = seg(0xC0, b'\x08\x00\x10\x00\x10' + bytes([channels]) + b''.join(bytes([i + 1, 0x11, 0]) for i in range(channels)))
    return b'\xff\xd8' + (seg(0xEE, b'Adobe\x00\x64\x00\x00\x00\x00\x00') if adobe else b'') + sof + seg(0xDA, b'\x01\x01\x00\x00\x3f\x00') + b'\x12\x34\xff\xd9'


def test_a_grayscale_jpeg_goes_without_the_adobe_marker_google_refuses():
    """2026-11-09: a signature logo - a one-channel JPEG saved from Photoshop - on every mail of a thread made Vertex answer "The provided
    file is malformed or corrupted and could not be decoded" (400), so a HIPAA AI agent could never start on it. APP14 means nothing on one
    channel and is dropped; a colour JPEG, which needs it, and any other picture go as they came."""
    import base64
    b64 = lambda b: base64.b64encode(b).decode()
    got = base64.b64decode(llm.vision_safe('image/jpeg', b64(_jpeg(1, True))))
    assert got == _jpeg(1, False) and b'Adobe' not in got
    for ct, b in (('image/jpeg', _jpeg(3, True)), ('image/jpeg', _jpeg(1, False)), ('image/png', _jpeg(1, True)), ('image/jpeg', b'not a jpeg')):
        assert llm.vision_safe(ct, b64(b)) == b64(b)
    assert llm.vision_safe('image/jpeg', '%%%') == '%%%'


def _refusing_pictures(sent):
    "A gateway that cannot decode any picture it is sent - and answers the same question without one."
    def post(url, headers=None, json=None, timeout=None):
        sent.append(json); r = mock.Mock()
        if any(isinstance(m['content'], list) for m in json['messages']):
            r.status_code, r.text = 400, ('{"error":{"message":"litellm.BadRequestError: Vertex_aiException - The provided file is malformed '
                                          'or corrupted and could not be decoded."}}')
        else: r.status_code, r.text = 200, ''; r.json.return_value = {'choices': [{'message': {'content': 'done'}}]}
        return r
    return post


def test_a_picture_the_model_cannot_open_costs_the_picture_never_the_turn():
    "Any picture the gateway still cannot decode is asked about again without it, saying so - the agent's turn goes on."
    sent, fn = [], llm.make_llm('hipaa_ai', {'base_url': 'https://gateway.example/v1'}, 'hai-code-123')
    with mock.patch('taskuary.llm.requests.post', side_effect=_refusing_pictures(sent)):
        assert fn('s', 'what is in it?', images=[('image/jpeg', 'AAAA')]) == 'done'
    assert sent[-1]['messages'][-1]['content'].startswith('what is in it?\n\n(1 attached image(s) could not be opened')


def test_a_refused_turn_is_said_in_words_with_no_address_and_no_json():
    """The agent's line was "hipaa_ai error 400 at https://<gateway>/v1/chat/completions: {"error":{"message":"litellm.BadRequestError: ..."
    (2026-11-09). It names the AI and its reason; the address and the JSON stay in the log."""
    from taskuary import failures, general
    e = RuntimeError('hipaa_ai error 400 at https://gateway.example/v1/chat/completions: {"error":{"message":"litellm.BadRequestError: '
                     'Vertex_aiException BadRequestError - {\\n  \\"error\\": {\\n    \\"code\\": 400,\\n    \\"message\\": \\"The provided file is '
                     'malformed or corrupted and could not be decoded.\\",\\n')
    assert general.refused_line(e, 'HIPAA AI (API)') == ('HIPAA AI refused the request - it said: The provided file is malformed or corrupted '
                                                         'and could not be decoded. Type to try again, or pick another AI in Settings.')
    said = failures.classify(e)['sentence']
    assert said.startswith('HIPAA AI refused the request') and 'gateway.example' not in said and '{' not in said
    assert general.refused_line(RuntimeError('openai error 400 at https://api.example.com/v1/chat/completions: nope')) == \
        'openai refused the request. Type to try again, or pick another AI in Settings.'
    assert general.refused_line(RuntimeError('something else broke')) == ''


def test_a_blank_job_never_falls_to_hipaa_ai_only_a_job_set_to_it_runs_there():
    # the owner, 2026-11-09: "it should not be used unless set in settings" - no CLI ready and nothing picked is no brain, not the gateway
    from taskuary import agents
    s = MemoryStore(); cid = s.get_connector_by_type('hipaa_ai')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'hai-code-123', 'Active': 1,
                      'ConfigJson': json.dumps({'base_url': 'https://ai.northwind.example/v1'})}, 'owner')
    assert agents.ready_connector(s) is None and llm.brain_status(s, '')['ready'] is False
    s.set_setting('assistant_ai', f'connector:{cid}', 'owner')
    assert llm.brain_status(s, f'connector:{cid}')['ready'] is True
