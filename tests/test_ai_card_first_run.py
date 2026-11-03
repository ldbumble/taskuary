"""An OpenAI-compatible AI card connected in first-run setup (2026-11-03): its Test passed, then the mail came back "wrong format",
and setup's last page said "One thing left: your AI" over a card that was connected. The card is a generic OpenAI-compatible endpoint here,
at a .example address on this computer; the people are invented."""
import json, unittest
import pytest
from unittest import mock

from taskuary import brainroute, capabilities, firstrun, llm
from taskuary.store import MemoryStore

VERDICT = {'intent': 'task', 'why': 'asks for approval', 'title': 'Approve the Q3 invoice', 'summary': 'Erin asks Alex to approve it.',
           'checklist': ['Approve the invoice'], 'kind': 'task'}
CODE = 'code-1234567890abcdef'


class _Proxy:
    """An OpenAI-compatible proxy on this computer: /v1/models lists `models`, and each chat call is answered by `answer(body)` ->
    (status, json). Every body it was sent is kept."""
    def __init__(self, allow, answer, models=('card-default',)):
        import http.server, threading
        me, self.bodies = self, []
        class H(http.server.BaseHTTPRequestHandler):
            def _send(self, code, body):
                self.send_response(code); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(json.dumps(body).encode())
            def do_GET(self): self._send(200, {'data': [{'id': m} for m in models]})
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
                me.bodies.append(body); self._send(*answer(body))
            def log_message(self, *a): pass
        self.srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.url = f'http://127.0.0.1:{allow(self.srv.server_address[1])}'
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def __enter__(self): return self
    def __exit__(self, *a): self.srv.shutdown(); self.srv.server_close()


def said(content): return 200, {'choices': [{'message': {'role': 'assistant', 'content': content}, 'finish_reason': 'stop'}]}


class AiCardFirstRunTests(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def _loopback(self, allow_test_port): self.allow = allow_test_port

    def setUp(self):
        llm._FORMAT_FROM.clear()
        self.s = MemoryStore(); self.cid = self.s.get_connector_by_type('hipaa_ai')['ConnectorId']
        self.p = [mock.patch('taskuary.config.load', return_value={}), mock.patch('taskuary.llm.sleep')]
        for p in self.p: p.start()

    def tearDown(self):
        for p in reversed(self.p): p.stop()

    def choose(self, proxy): return firstrun.choose_key(self.s, 'hipaa_ai', CODE, cid=self.cid, config={'base_url': proxy.url})
    def card_model(self): return json.loads(self.s.get_connector(self.cid).get('ConfigJson') or '{}').get('model')

    def test_a_proxy_that_refuses_the_schema_and_answers_in_parts_passes_the_test_email(self):
        fenced = f'```json\n{json.dumps(VERDICT)}\n```'
        def answer(b):
            if (b.get('response_format') or {}).get('type') == 'json_schema':
                return 500, {'error': {'message': 'upstream error: response_format json_schema is not supported for this model'}}
            return said([{'type': 'text', 'text': fenced}])
        with _Proxy(self.allow, answer) as p: out = self.choose(p)
        self.assertTrue(out['ok'], out)
        st = firstrun.state(self.s)
        self.assertEqual((st['step'], st['brain']['ready'], st['brain']['pick']), ('email', True, f'connector:{self.cid}'))
        self.assertTrue(next(r for r in st['rail'] if r['key'] == 'ai')['done'])

    def test_a_test_email_that_still_fails_says_what_came_back(self):
        with _Proxy(self.allow, lambda b: said('Sure! Happy to help Alex with that invoice.')) as p: out = self.choose(p)
        self.assertFalse(out['ok'])
        self.assertIn('plain words instead of the JSON', out['detail'])
        self.assertIn('Happy to help Alex', out['detail'])

    def test_the_test_email_is_sorted_on_the_model_triage_will_run(self):
        """Switching triage to the gateway's quickest model came AFTER the test email, so the mail was sorted on a model nobody
        had tried. Tried first now - and one that cannot sort it leaves the card's own model doing the job."""
        good = lambda b: said(json.dumps(VERDICT))
        with _Proxy(self.allow, good, models=('card-default', 'x-flash', 'x-sonnet')) as p: out = self.choose(p)
        self.assertTrue(out['ok'], out)
        self.assertEqual(p.bodies[-1]['model'], 'x-flash')
        self.assertEqual(self.card_model(), 'x-flash')
        llm._FORMAT_FROM.clear(); self.s = MemoryStore(); self.cid = self.s.get_connector_by_type('hipaa_ai')['ConnectorId']
        flaky = lambda b: said('I cannot help with that.') if b.get('model') == 'x-flash' else good(b)
        with _Proxy(self.allow, flaky, models=('card-default', 'x-flash', 'x-sonnet')) as p: out = self.choose(p)
        self.assertTrue(out['ok'], out)
        self.assertIn('x-flash', [b.get('model') for b in p.bodies])
        self.assertNotEqual(self.card_model(), 'x-flash')
        self.assertEqual(self.s.get_setting('triage_ai'), f'connector:{self.cid}')

    def test_with_only_the_card_every_job_that_needs_an_ai_has_one_and_coding_has_none(self):
        with _Proxy(self.allow, lambda b: said(json.dumps(VERDICT))) as p: self.assertTrue(self.choose(p)['ok'])
        self.assertTrue(capabilities.has_ai(self.s))
        for job in ('triage', 'draft', 'advisor', 'summary', 'assistant', 'general'):
            self.assertEqual(brainroute.choose(self.s, job).pick, f'connector:{self.cid}', job)
        self.assertEqual(brainroute.choose(self.s, 'coding').pick, '')          # a coding agent still needs a CLI

    def test_the_finish_page_says_what_came_back_when_the_mail_still_cannot_be_read(self):
        """Setup's last page read "One thing left: your AI ... its answers came back in a form Taskuary can't read" and nothing more."""
        from taskuary import ingest
        with _Proxy(self.allow, lambda b: said(json.dumps(VERDICT))) as p: self.assertTrue(self.choose(p)['ok'])
        msg = {'external_id': 'm1', 'channel': 'email', 'from_email': 'erin.blake@northwind.example', 'subject': 'Q3 invoice',
               'body': 'Hi Alex, can you approve the Payworth invoice by Friday?'}
        ingest.ingest_message(self.s, msg, llm=lambda *a, **k: 'Happy to help - this looks like a task for Alex.')
        said_now = firstrun._ai_error(self.s)
        self.assertIn("can't read", said_now)
        self.assertIn('plain words instead of the JSON', said_now)
        self.assertIn('Happy to help', said_now)


if __name__ == '__main__':
    unittest.main()
