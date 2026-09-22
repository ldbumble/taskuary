"""LinkedIn is a sign-in, not a token you fetch by hand.

The card shipped asking for an access token pasted out of LinkedIn's own portal, because LinkedIn
has no device-code flow. That was the wrong read of the choice: Taskuary already serves a local
port, so it can take the redirect, which is the road QuickBooks and Zoho Invoice already take.
The owner puts in the app's client id and secret, presses a button, and the token comes back on
its own (2026-09-22).

What has to hold for that button to be safe, and each of these is a line of code somebody could
delete without a test noticing:

  - the callback is exempt from the Origin and token checks, because a redirect from linkedin.com
    carries neither. It proves itself with the one-time state instead.
  - a state that was never issued, is stale, or belongs to another card is refused.
  - a token is only stored when LinkedIn actually returned one - it answers 200 with an `error`
    field for some failures, and trusting the status alone stores '' and calls the card connected.
"""
import json
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from taskuary import linkedin
from taskuary.store import MemoryStore


class _Resp:
    def __init__(self, payload=None, status=200, text=''):
        self._payload, self.status_code, self.text = payload, status, text
        self.ok = status < 400
        self.headers = {}

    def json(self):
        if self._payload is None: raise ValueError('no json')
        return self._payload


class TheAuthorizeUrl(unittest.TestCase):
    def test_it_asks_only_for_the_scopes_the_self_serve_product_grants(self):
        """Asking for more is what sends an app into Community Management review, where a
        rejection is terminal for that app."""
        self.assertEqual(linkedin.SCOPES, 'openid profile email w_member_social')
        url = linkedin.authorize_url({'client_id': 'abc'}, 'http://localhost:7999/api/linkedin/callback', 'tq-1-n')
        self.assertIn('scope=openid+profile+email+w_member_social', url)
        self.assertNotIn('w_organization', url)

    def test_it_carries_the_state_and_the_redirect(self):
        url = linkedin.authorize_url({'client_id': 'abc'}, 'http://localhost:7999/api/linkedin/callback', 'tq-4-nonce')
        self.assertTrue(url.startswith('https://www.linkedin.com/oauth/v2/authorization?'))
        self.assertIn('state=tq-4-nonce', url)
        self.assertIn('redirect_uri=http%3A%2F%2Flocalhost%3A7999%2Fapi%2Flinkedin%2Fcallback', url)
        self.assertIn('response_type=code', url)

    def test_with_no_client_id_it_says_where_to_get_one(self):
        with self.assertRaises(linkedin.LinkedInError) as e:
            linkedin.authorize_url({}, 'http://localhost/cb', 's')
        self.assertIn('developer.linkedin.com', str(e.exception))

    def test_the_redirect_url_follows_the_port_the_app_is_actually_on(self):
        """It has to be registered on the app's Auth tab character for character, so a card that
        prints a different port than the one serving it is a dead end."""
        self.assertEqual(linkedin.redirect_uri({'port': 7999}),
                         'http://localhost:7999/api/linkedin/callback')


class ExchangingTheCode(unittest.TestCase):
    def _cfg(self):
        s = MemoryStore()
        cid = s.get_connector_by_type('linkedin')['ConnectorId']
        s.save_connector({'ConnectorId': cid,
                          'ConfigJson': json.dumps({'client_id': 'abc', 'client_secret': 'shh'})}, 'test')
        return s, cid, linkedin.connection(s, cid)

    def test_the_token_lands_on_the_card_as_its_secret(self):
        s, cid, cfg = self._cfg()
        with mock.patch.object(linkedin.requests, 'post',
                               return_value=_Resp({'access_token': 'AQ-token', 'expires_in': 5184000})):
            linkedin.exchange_code(cfg, 'the-code', 'http://localhost:7999/api/linkedin/callback')
        self.assertEqual(s.get_connector(cid, with_secret=True)['Secret'], 'AQ-token')

    def test_the_expiry_is_kept_so_the_card_can_say_how_long_is_left(self):
        s, cid, cfg = self._cfg()
        with mock.patch.object(linkedin.requests, 'post',
                               return_value=_Resp({'access_token': 't', 'expires_in': 5184000})):
            linkedin.exchange_code(cfg, 'c', 'http://localhost/cb')
        conf = json.loads(s.get_connector(cid)['ConfigJson'])
        self.assertIn(linkedin.days_left(conf), (59, 60))

    def test_a_200_carrying_an_error_is_still_a_failure(self):
        """LinkedIn answers 200 with an `error` field for some failures. Trusting the status alone
        stores an empty token and the card then reports itself connected."""
        s, cid, cfg = self._cfg()
        with mock.patch.object(linkedin.requests, 'post',
                               return_value=_Resp({'error': 'invalid_request',
                                                   'error_description': 'the redirect_uri does not match'})):
            with self.assertRaises(linkedin.LinkedInError) as e:
                linkedin.exchange_code(cfg, 'c', 'http://localhost/cb')
        self.assertIn('does not match', str(e.exception))
        self.assertFalse(s.get_connector(cid, with_secret=True).get('Secret'))

    def test_a_body_that_is_not_json_still_fails_readably(self):
        s, cid, cfg = self._cfg()
        with mock.patch.object(linkedin.requests, 'post', return_value=_Resp(None, 502, 'Bad Gateway')):
            with self.assertRaises(linkedin.LinkedInError) as e:
                linkedin.exchange_code(cfg, 'c', 'http://localhost/cb')
        self.assertIn('502', str(e.exception))

    def test_the_apps_own_credentials_are_what_spend_the_code(self):
        s, cid, cfg = self._cfg()
        with mock.patch.object(linkedin.requests, 'post',
                               return_value=_Resp({'access_token': 't'})) as post:
            linkedin.exchange_code(cfg, 'the-code', 'http://localhost/cb')
        sent = post.call_args.kwargs['data']
        self.assertEqual(sent['grant_type'], 'authorization_code')
        self.assertEqual((sent['client_id'], sent['client_secret']), ('abc', 'shh'))
        self.assertEqual(sent['code'], 'the-code')

    def test_a_refresh_token_is_kept_when_linkedin_grants_one(self):
        """Only approved apps get one. When it arrives it is worth keeping; when it does not,
        reconnecting is a button rather than a trip back to the portal."""
        s, cid, cfg = self._cfg()
        with mock.patch.object(linkedin.requests, 'post',
                               return_value=_Resp({'access_token': 't', 'refresh_token': 'r-1'})):
            linkedin.exchange_code(cfg, 'c', 'http://localhost/cb')
        self.assertEqual(json.loads(s.get_connector(cid)['ConfigJson'])['refresh_token'], 'r-1')


class DaysLeft(unittest.TestCase):
    def test_nothing_recorded_is_not_zero_days(self):
        """None means "unknown", and the card says nothing. Zero would say "expired today"."""
        self.assertIsNone(linkedin.days_left({}))
        self.assertIsNone(linkedin.days_left({'expires_at': 'not a date'}))

    def test_an_expired_token_floors_at_zero_rather_than_going_negative(self):
        past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        self.assertEqual(linkedin.days_left({'expires_at': past}), 0)


class TheCallbackOverTheApi(unittest.TestCase):
    """The state is the whole of the callback's proof, so it is tested through the real route."""

    def _client(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        return TestClient(server.app), server

    def test_a_state_nobody_issued_is_refused(self):
        client, server = self._client()
        server._LI_STATES.clear()
        r = client.get('/api/linkedin/callback', params={'code': 'c', 'state': 'tq-1-made-up'})
        self.assertEqual(r.status_code, 200)            # it is a page for a human, not an API error
        self.assertIn('Not connected', r.text)
        self.assertIn('expired', r.text)

    def test_a_stale_state_is_refused(self):
        client, server = self._client()
        cid = server.store.get_connector_by_type('linkedin')['ConnectorId']
        server._LI_STATES[cid] = ('nonce', time.time() - 1000)      # issued over 15 minutes ago
        r = client.get('/api/linkedin/callback', params={'code': 'c', 'state': f'tq-{cid}-nonce'})
        self.assertIn('expired', r.text)

    def test_a_state_is_spent_once(self):
        """Replaying a callback must not re-run the exchange - the code is single-use at
        LinkedIn's end too, but the state is the half we control."""
        client, server = self._client()
        cid = server.store.get_connector_by_type('linkedin')['ConnectorId']
        server.store.save_connector({'ConnectorId': cid,
                                     'ConfigJson': json.dumps({'client_id': 'a', 'client_secret': 'b'})}, 'test')
        server._LI_STATES[cid] = ('nonce', time.time())
        with mock.patch.object(linkedin, 'exchange_code', return_value={'access_token': 't'}), \
             mock.patch.object(linkedin, 'whoami', return_value={'name': 'Alex Doyle', 'author': 'urn:li:person:x'}):
            first = client.get('/api/linkedin/callback', params={'code': 'c', 'state': f'tq-{cid}-nonce'})
        self.assertIn('Connected', first.text)
        self.assertIn('Alex Doyle', first.text)
        again = client.get('/api/linkedin/callback', params={'code': 'c', 'state': f'tq-{cid}-nonce'})
        self.assertIn('Not connected', again.text)

    def test_linkedins_own_refusal_is_shown_rather_than_a_blank_page(self):
        client, _server = self._client()
        r = client.get('/api/linkedin/callback',
                       params={'error': 'user_cancelled_login',
                               'error_description': 'The user cancelled the sign-in'})
        self.assertIn('Not connected', r.text)
        self.assertIn('cancelled the sign-in', r.text)

    def test_the_callback_needs_no_token_header_because_a_redirect_cannot_carry_one(self):
        """It is one of three paths exempt from the Origin and token checks. Remove it from either
        list and the button works right up to the moment LinkedIn sends the owner back."""
        import inspect
        from taskuary import server
        src = inspect.getsource(server)
        self.assertEqual(src.count("'/api/quickbooks/callback', '/api/zoho/callback', '/api/linkedin/callback'"), 2)


class TheStatusEndpoint(unittest.TestCase):
    def test_it_reports_the_app_missing_so_the_button_stays_disabled(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        client = TestClient(server.app)
        cid = server.store.get_connector_by_type('linkedin')['ConnectorId']
        server.store.save_connector({'ConnectorId': cid, 'ConfigJson': '{}', 'Secret': ''}, 'test')
        d = client.get(f'/api/connectors/{cid}/linkedin/status').json()
        self.assertFalse(d['has_app'])
        self.assertFalse(d['connected'])
        self.assertTrue(d['redirect_uri'].endswith('/api/linkedin/callback'))

    def test_with_the_keys_saved_the_button_unlocks(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        client = TestClient(server.app)
        cid = server.store.get_connector_by_type('linkedin')['ConnectorId']
        server.store.save_connector({'ConnectorId': cid,
                                     'ConfigJson': json.dumps({'client_id': 'a', 'client_secret': 'b'})}, 'test')
        self.assertTrue(client.get(f'/api/connectors/{cid}/linkedin/status').json()['has_app'])

    def test_another_cards_id_is_not_a_linkedin_card(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        client = TestClient(server.app)
        other = server.store.get_connector_by_type('exa')['ConnectorId']
        self.assertEqual(client.get(f'/api/connectors/{other}/linkedin/status').status_code, 404)
        self.assertEqual(client.get(f'/api/connectors/{other}/linkedin/authorize').status_code, 404)


class TheCardOnThePage(unittest.TestCase):
    def test_it_asks_for_the_app_keys_and_offers_the_button(self):
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1] / 'website' / 'src' / 'ConnectorsView.jsx').read_text(encoding='utf-8')
        card = src[src.index('  linkedin: { title: "LinkedIn"'):src.index('  treg: { title:')]
        self.assertIn('"client_id"', card)
        self.assertIn('"client_secret"', card)
        self.assertIn('linkedin/authorize', card)
        self.assertIn('linkedin/status', card)
        self.assertIn('Sign in with LinkedIn', card)


if __name__ == '__main__':
    unittest.main()
