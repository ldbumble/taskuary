"""SIGN IN WITH GOOGLE FOR THE CALENDAR on the Gmail card (googlecal.py; the owner, 2026-10-26: "yes" to the card offering it):
the installed-app round with PKCE comes back to this server, the refresh token is kept on the card sealed, and from then on the
calendar reads and names that Google calendar - and stops listing the card as one no read reaches. Google is mocked throughout."""
import json, unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from urllib.parse import parse_qs, urlsplit
from fastapi.testclient import TestClient

from taskuary import calendar as cal, config, googlecal, lookups, server
from taskuary.store import MemoryStore

c = TestClient(server.app)
NOBODY = {'X-Taskuary-Token': ''}
AGENT = {'X-Taskuary-Token': config.load()['server']['agent_token']}
ME = 'alex@northwind.example'


class R:
    def __init__(self, status=200, j=None, text=''): self.status_code, self._j, self.text = status, j or {}, text or json.dumps(j or {})
    def json(self): return self._j


def fake_vault():
    """A seal anyone can see through, so the test reads what the column holds on any OS."""
    seal = lambda v: v if not v or str(v).startswith('vault:') else f'vault:test:{v}'
    unseal = lambda v: v[len('vault:test:'):] if isinstance(v, str) and v.startswith('vault:test:') else v
    return mock.patch.multiple('taskuary.store.vault', seal=seal, unseal=unseal)


EVENTS = {'items': [{'summary': 'Budget review', 'start': {'dateTime': '2026-10-27T13:00:00+00:00'},
                     'end': {'dateTime': '2026-10-27T14:00:00+00:00'}, 'attendees': [{'email': 'erin@northwind.example'}]}]}


class SignIn(unittest.TestCase):
    def setUp(self):
        googlecal._FLOWS.clear(); googlecal._TOK.clear()
        self.n = getattr(SignIn, 'n', 0) + 1; SignIn.n = self.n
        self.me = f'alex+{self.n}@northwind.example'      # one card's address: the server's store is shared across the suite

    def card(self, **cfg):
        cid = server.store.save_connector({'Type': 'gmail', 'Name': f'Gmail cal {self.n}', 'Active': 1, 'Secret': 'app-password',
                                           'ConfigJson': json.dumps({'address': self.me, **cfg})}, 'test')
        self.addCleanup(server.store.save_connector, {'ConnectorId': cid, 'Active': 0}, 'test')   # no calendar left on for later tests
        return cid

    def test_no_oauth_client_says_what_is_needed(self):
        r = c.post(f'/api/connectors/{self.card()}/google/calendar')
        self.assertEqual(r.status_code, 409)
        self.assertIn('OAuth client of your own', r.json()['detail'])
        self.assertIn('client id and secret', r.json()['detail'])

    def test_an_agent_may_not_start_it(self):
        self.assertEqual(c.post(f'/api/connectors/{self.card(google_client_id="cid.apps.example", google_client_secret="sec")}/google/calendar',
                                headers=AGENT).status_code, 403)

    def test_signed_in_card_reads_the_google_calendar(self):
        cid = self.card(google_client_id='cid.apps.example', google_client_secret='sec')
        self.assertTrue(any(self.me in x for x in cal.unread_mail(server.store)))           # before: a card no read reaches
        with fake_vault():
            f = c.post(f'/api/connectors/{cid}/google/calendar').json()
            q = {k: v[0] for k, v in parse_qs(urlsplit(f['url']).query).items()}
            self.assertEqual(q['scope'], googlecal.SCOPE)
            self.assertEqual((q['code_challenge_method'], q['access_type'], q['client_id']), ('S256', 'offline', 'cid.apps.example'))
            self.assertTrue(q['redirect_uri'].startswith('http://127.0.0.1:') and q['redirect_uri'].endswith('/api/google/calendar/callback'))
            self.assertEqual(c.post(f'/api/connectors/{cid}/google/calendar/poll', json={'flow': f['flow']}).json(), {'status': 'pending'})
            self.assertIn('was not started here', c.get('/api/google/calendar/callback', params={'code': 'x', 'state': 'forged'}, headers=NOBODY).text)
            tok = R(j={'access_token': 'at1', 'refresh_token': 'rt1', 'expires_in': 3600, 'scope': googlecal.SCOPE})
            with mock.patch('taskuary.googlecal.requests.post', return_value=tok) as post:
                ok = c.get('/api/google/calendar/callback', params={'code': 'C', 'state': q['state']}, headers=NOBODY)  # outside the token gate
            self.assertIn('reads the Google calendar', ok.text)
            sent = post.call_args.kwargs['data']
            self.assertEqual((sent['code'], sent['grant_type'], sent['client_secret']), ('C', 'authorization_code', 'sec'))
            self.assertTrue(sent['code_verifier'])
            self.assertEqual(c.post(f'/api/connectors/{cid}/google/calendar/poll', json={'flow': f['flow']}).json()['status'], 'ok')
            self.assertIn('was not started here', c.get('/api/google/calendar/callback', params={'code': 'C', 'state': q['state']}, headers=NOBODY).text)
            raw = json.loads(server.store._one('SELECT ConfigJson FROM connector WHERE ConnectorId=?', (cid,))['ConfigJson'])
            self.assertEqual(raw['google_refresh_token'], 'vault:test:rt1')                  # sealed in the column
            opened = json.loads(server.store.get_connector(cid, with_secret=True)['ConfigJson'])
            self.assertEqual(opened['google_refresh_token'], 'rt1')
            shown = c.get('/api/connectors').json()
            row = next(x for x in (shown['data']) if x['ConnectorId'] == cid)
            self.assertNotIn('google_refresh_token', json.loads(row['ConfigJson']))           # never back to a page
            self.assertIn('google_refresh_token', row['ConfigSaved'])
            self.assertFalse(any(self.me in x for x in cal.unread_mail(server.store)))          # after: not listed as unread
            with mock.patch('taskuary.calendar.requests.get', return_value=R(j=EVENTS)) as get:
                ag = cal.agenda(server.store, days=3)
                said = lookups.calendar_read(server.store, {'days': 3})
            self.assertIn(f'google: {self.me}', ag['sources'])
            self.assertIn('Budget review', [e['subject'] for e in ag['events']])
            self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer at1')   # the token minted at sign-in, not another
            self.assertIn(f'google: {self.me}', said)

    def test_unticked_calendar_box_changes_nothing(self):
        cid = self.card(google_client_id='cid.apps.example', google_client_secret='sec')
        f = c.post(f'/api/connectors/{cid}/google/calendar').json()
        with mock.patch('taskuary.googlecal.requests.post', return_value=R(j={'access_token': 'a', 'refresh_token': 'r', 'scope': 'openid'})):
            out = c.get('/api/google/calendar/callback', params={'code': 'C', 'state': f['flow']}, headers=NOBODY)
        self.assertIn('did not grant calendar access', out.text)
        self.assertNotIn('google_refresh_token', json.loads(server.store.get_connector(cid, with_secret=True)['ConfigJson']))
        self.assertEqual(c.post(f'/api/connectors/{cid}/google/calendar/poll', json={'flow': f['flow']}).json()['status'], 'error')


class Refresh(unittest.TestCase):
    CFG = {'google_client_id': 'cid', 'google_client_secret': 'sec', 'google_refresh_token': 'rt-refresh', 'address': ME}
    def setUp(self): googlecal._TOK.clear()

    def test_a_token_is_reused_until_it_expires_then_minted_again(self):
        clock = [1000.0]
        with mock.patch('taskuary.googlecal.time.time', lambda: clock[0]), \
             mock.patch('taskuary.googlecal.requests.post', side_effect=[R(j={'access_token': 'a1', 'expires_in': 3600}),
                                                                         R(j={'access_token': 'a2', 'expires_in': 3600})]) as post, \
             mock.patch('taskuary.calendar.requests.get', return_value=R(j=EVENTS)) as get:
            t0 = datetime.now(timezone.utc)
            cal.google_events(self.CFG, t0, t0 + timedelta(days=1), timezone.utc)
            clock[0] += 600
            cal.google_events(self.CFG, t0, t0 + timedelta(days=1), timezone.utc)
            self.assertEqual(post.call_count, 1)                                         # cached
            clock[0] += 3600
            cal.google_events(self.CFG, t0, t0 + timedelta(days=1), timezone.utc)
        self.assertEqual(post.call_count, 2)                                             # expired: refreshed
        self.assertEqual(post.call_args.kwargs['data']['grant_type'], 'refresh_token')
        self.assertEqual([k.kwargs['headers']['Authorization'] for k in get.call_args_list], ['Bearer a1', 'Bearer a1', 'Bearer a2'])

    def test_a_revoked_sign_in_says_how_to_fix_it(self):
        with mock.patch('taskuary.googlecal.requests.post', return_value=R(400, {'error': 'invalid_grant'})):
            with self.assertRaises(RuntimeError) as e: googlecal.access_token(self.CFG)
        self.assertIn('Sign in with Google for the calendar', str(e.exception))


class Sealing(unittest.TestCase):
    def test_the_column_holds_it_sealed_and_a_save_keeps_the_seal(self):
        s = MemoryStore()
        with fake_vault():
            cid = s.save_connector({'Type': 'gmail', 'Name': 'Gmail', 'ConfigJson': json.dumps({'address': ME, 'google_refresh_token': 'rt'})}, 't')
            raw = lambda: json.loads(s._one('SELECT ConfigJson FROM connector WHERE ConnectorId=?', (cid,))['ConfigJson'])
            self.assertEqual(raw()['google_refresh_token'], 'vault:test:rt')
            opened = s.get_connector(cid, with_secret=True)
            self.assertEqual(json.loads(opened['ConfigJson'])['google_refresh_token'], 'rt')
            with mock.patch('taskuary.store.vault.forget') as forget:
                s.set_connector_config(cid, {**json.loads(opened['ConfigJson']), 'poll': 1})   # a poller writing back what it read
                forget.assert_not_called()
                self.assertEqual(raw()['google_refresh_token'], 'vault:test:rt')
                s.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps({'address': ME, 'google_refresh_token': 'rt2'})}, 't')
                forget.assert_called_once_with('vault:test:rt')                              # the replaced one goes
            self.assertEqual(raw()['google_refresh_token'], 'vault:test:rt2')


if __name__ == '__main__':
    unittest.main()
