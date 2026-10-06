"""Sign in with ChatGPT: the owner's ChatGPT plan as a brain (chatgptauth.py). Nothing here reaches OpenAI - the network
is mocked at requests, and the browser's return trip is a real GET against the one-off loopback listener."""
import base64, hashlib, json, time, unittest
from unittest import mock
from urllib.parse import parse_qs, urlparse
import requests

from taskuary import chatgptauth as ca, llm
from taskuary.store import MemoryStore


def _jwt(claims: dict) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b'=').decode()
    return f"{enc({'alg': 'RS256'})}.{enc(claims)}.sig"


class _Resp:
    def __init__(self, status=200, body=None, lines=()):
        self.status_code, self._body, self._lines, self.text = status, body or {}, lines, json.dumps(body or {})
    def json(self): return self._body
    def iter_lines(self, decode_unicode=True): return iter(self._lines)
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _sse(*events): return [f'data: {json.dumps(e)}' for e in events]


class SignInTests(unittest.TestCase):
    def tearDown(self):
        for fid in list(ca._FLOWS): ca._stop(fid)

    def _start(self, cfg=None):
        out = ca.start(cfg or {})
        return out, {k: v[0] for k, v in parse_qs(urlparse(out['url']).query).items()}

    def test_a_first_sign_in_registers_this_install_with_pkce_and_a_loopback_redirect(self):
        out, q = self._start()
        self.assertTrue(out['url'].startswith('https://auth.openai.com/api/accounts/authorize?'))
        self.assertEqual((q['client_id'], q['response_type'], q['code_challenge_method']), ('dynamic_agent_client', 'code', 'S256'))
        self.assertEqual(q['agent_name_hint'], 'Taskuary')
        self.assertTrue(q['ext_agent_host_id'].startswith('urn:uuid:'))
        self.assertIn('chatgpt.tokens.use.direct', q['scope'].split())
        self.assertEqual(q['resource'], 'https://api.openai.com/v1')
        self.assertRegex(q['redirect_uri'], r'^http://127\.0\.0\.1:\d+/auth/callback$')
        f = ca._FLOWS[out['flow']]
        self.assertEqual(q['code_challenge'], ca._b64(hashlib.sha256(f['verifier'].encode()).digest()))

    def test_a_card_that_has_signed_in_before_keeps_its_client_and_host(self):
        _out, q = self._start({'client_id': 'client-abc', 'host_id': 'urn:uuid:kept'})
        self.assertEqual(q['client_id'], 'client-abc')
        self.assertNotIn('agent_name_hint', q)     # registration hints are for the registration entrypoint only

    def test_the_browser_coming_back_finishes_the_sign_in_and_the_plan_scope_is_required(self):
        out, q = self._start()
        f = ca._FLOWS[out['flow']]
        self.assertEqual(ca.poll(out['flow']), {'pending': True})
        r = requests.get(q['redirect_uri'], params={'code': 'the-code', 'state': q['state'], 'client_id': 'issued-1', 'scope': ca.SCOPES}, timeout=5)
        self.assertIn('Signed in to ChatGPT', r.text)
        tok = {'access_token': 'at', 'refresh_token': 'rt', 'expires_in': 3600, 'scope': ca.SCOPES,
               'id_token': _jwt({'nonce': f['nonce'], 'iss': 'https://auth.openai.com', 'exp': time.time() + 60,
                                 'sub': 'user-1', 'email': 'alex@northwind.example', 'name': 'Alex Doyle'})}
        with mock.patch.object(ca.requests, 'post', return_value=_Resp(200, tok)) as post:
            got = ca.poll(out['flow'])
        sent = post.call_args.kwargs['data']
        self.assertEqual((sent['client_id'], sent['code'], sent['code_verifier'], sent['redirect_uri']),
                         ('issued-1', 'the-code', f['verifier'], q['redirect_uri']))
        self.assertEqual((got['client_id'], got['refresh_token'], got['email'], got['host_id']), ('issued-1', 'rt', 'alex@northwind.example', q['ext_agent_host_id']))

    def test_a_sign_in_without_plan_usage_or_for_another_attempt_is_refused(self):
        out, q = self._start()
        f = ca._FLOWS[out['flow']]
        requests.get(q['redirect_uri'], params={'code': 'c', 'state': q['state'], 'client_id': 'issued-1'}, timeout=5)
        with mock.patch.object(ca.requests, 'post', return_value=_Resp(200, {'access_token': 'at', 'refresh_token': 'rt', 'scope': 'openid email'})):
            with self.assertRaisesRegex(RuntimeError, 'plan usage was not granted'): ca.poll(out['flow'])
        with self.assertRaisesRegex(RuntimeError, 'nonce'): ca._identity(_jwt({'nonce': 'other', 'iss': ca.AUTH}), f['nonce'])

    def test_a_callback_for_a_different_attempt_is_not_accepted(self):
        out, q = self._start()
        requests.get(q['redirect_uri'], params={'code': 'c', 'state': 'forged'}, timeout=5)
        with self.assertRaisesRegex(RuntimeError, 'different attempt'): ca.poll(out['flow'])


class CallTests(unittest.TestCase):
    def test_a_stream_with_no_charset_is_read_as_utf8_not_bytes(self):
        # the plan's text/event-stream names no charset, so requests yielded BYTES even with decode_unicode, and every
        # triage failed with "startswith first arg must be bytes or a tuple of bytes" (2026-10-06)
        class Raw(_Resp):
            encoding = None
            def iter_lines(self, decode_unicode=True):
                return iter([l.encode('utf-8') for l in self._lines]) if self.encoding is None else iter(self._lines)
        raw = Raw(200, lines=_sse({'type': 'response.output_text.delta', 'delta': 'Café ✓'}, {'type': 'response.completed'}))
        with mock.patch.object(ca.requests, 'post', return_value=raw):
            self.assertEqual(ca.complete('tok', 'gpt-x', 'sys', 'hi', 50), 'Café ✓')
        bare = Raw(200, lines=_sse({'type': 'response.output_text.delta', 'delta': 'ok'}, {'type': 'response.completed'}))
        bare.iter_lines = lambda decode_unicode=True: iter([l.encode('utf-8') for l in bare._lines])   # bytes whatever encoding says
        with mock.patch.object(ca.requests, 'post', return_value=bare):
            self.assertEqual(ca.complete('tok', 'gpt-x', 'sys', 'hi', 50), 'ok')

    def test_only_a_completed_stream_is_an_answer(self):
        ok = _sse({'type': 'response.output_text.delta', 'delta': 'Hello '}, {'type': 'response.output_text.delta', 'delta': 'Alex'},
                  {'type': 'response.completed'})
        with mock.patch.object(ca.requests, 'post', return_value=_Resp(200, lines=ok)) as post:
            self.assertEqual(ca.complete('tok', 'gpt-x', 'sys', 'hi', 50), 'Hello Alex')
        body = post.call_args.kwargs['json']
        self.assertEqual((body['store'], body['stream'], body['model']), (False, True, 'gpt-x'))
        cut = _sse({'type': 'response.output_text.delta', 'delta': 'Hel'})
        with mock.patch.object(ca.requests, 'post', return_value=_Resp(200, lines=cut)):
            with self.assertRaisesRegex(RuntimeError, 'stopped before it finished'): ca.complete('tok', 'gpt-x', 's', 'u', 50)

    def test_a_used_up_cap_says_what_to_do(self):
        cap = _Resp(429, {'error': {'code': 'subscription_sharing_usage_limit_exceeded', 'message': 'limit'}})
        with mock.patch.object(ca.requests, 'post', return_value=cap):
            with self.assertRaisesRegex(RuntimeError, 'weekly cap'): ca.complete('tok', 'gpt-x', 's', 'u', 50)

    def test_a_schema_rides_as_the_responses_text_format(self):
        done = _sse({'type': 'response.output_text.delta', 'delta': '{}'}, {'type': 'response.completed'})
        with mock.patch.object(ca.requests, 'post', return_value=_Resp(200, lines=done)) as post:
            ca.complete('tok', 'gpt-x', 's', 'u', 50, want={'name': 'triage_verdict', 'schema': {'type': 'object'}})
        self.assertEqual(post.call_args.kwargs['json']['text']['format']['type'], 'json_schema')


class BrainTests(unittest.TestCase):
    def setUp(self): ca._CACHE.clear()

    def test_it_is_a_brain_on_its_own_card_and_asks_for_no_key(self):
        self.assertIn('chatgpt', llm.AI_TYPES)
        self.assertTrue(MemoryStore().get_connector_by_type('chatgpt'), 'no ChatGPT card to sign in on')
        with self.assertRaisesRegex(RuntimeError, 'Sign in with ChatGPT'): llm.make_llm('chatgpt', {}, '')

    def test_the_brain_mints_once_and_uses_the_first_listed_model_when_none_is_set(self):
        rotated = []
        ca.on_rotate = lambda cid, rt: rotated.append((cid, rt))
        try:
            with mock.patch.object(ca, 'refresh', return_value={'access_token': 'at', 'refresh_token': 'rt2', 'expires_in': 3600}) as ref, \
                 mock.patch.object(ca, 'models', return_value=[('gpt-plan', 'GPT Plan'), ('gpt-other', 'Other')]), \
                 mock.patch.object(ca, 'complete', return_value='ok') as call:
                brain = llm.make_llm('chatgpt', {'client_id': 'issued-1', '_cid': 7}, 'rt1')
                self.assertEqual(brain('sys', 'hello'), 'ok'); brain('sys', 'again')
            self.assertEqual(ref.call_count, 1)                          # cached, not minted per call
            self.assertEqual(call.call_args.args[1], 'gpt-plan')
            self.assertEqual(rotated, [(7, 'rt2')])                      # the rotated token is saved back to its card
        finally: ca.on_rotate = None

    def test_a_dead_refresh_token_asks_for_a_new_sign_in(self):
        with mock.patch.object(ca.requests, 'post', return_value=_Resp(400, {'error': 'refresh_token_reused'})):
            with self.assertRaisesRegex(RuntimeError, 'sign in again'): ca.refresh({'client_id': 'c'}, 'rt')


if __name__ == '__main__': unittest.main()

class ModelListTests(unittest.TestCase):
    def test_the_plan_list_is_read_from_models_or_data_and_hidden_ones_are_left_out(self):
        rows = [{'slug': 'gpt-plan-a', 'display_name': 'A', 'visibility': 'list'}, {'slug': 'gpt-hidden', 'visibility': 'hide'}]
        for key in ('models', 'data'):
            with mock.patch.object(ca.requests, 'get', return_value=_Resp(200, {key: rows})):
                self.assertEqual(ca.models('tok'), [('gpt-plan-a', 'A')])
        with mock.patch.object(ca.requests, 'get', return_value=_Resp(200, {'object': 'list'})):
            with self.assertRaisesRegex(RuntimeError, "carried: \['object'\]"): ca.models('tok')

class PlanParameterTests(unittest.TestCase):
    def test_a_field_the_plan_refuses_is_taken_out_and_the_question_asked_again(self):
        ok = _Resp(200, lines=_sse({'type': 'response.output_text.delta', 'delta': 'hi'}, {'type': 'response.completed'}))
        with mock.patch.object(ca.requests, 'post', side_effect=[_Resp(400, {'detail': 'Unsupported parameter: text'}), ok]) as post:
            self.assertEqual(ca.complete('t', 'm', 's', 'u', 10, want={'name': 'x', 'schema': {}}), 'hi')
        self.assertNotIn('max_output_tokens', post.call_args_list[0].kwargs['json'])   # refused by the plan outright
        self.assertNotIn('text', post.call_args_list[1].kwargs['json'])
        with mock.patch.object(ca.requests, 'post', return_value=_Resp(400, {'detail': 'Unsupported parameter: tools'})):
            with self.assertRaises(ca.Unsupported): ca.complete('t', 'm', 's', 'u', 10, web=True)
