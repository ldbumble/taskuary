"""SIGN IN WITH GOOGLE on the Gmail card (googlecal.py; the owner, 2026-11-15: mail and calendar by Google's own sign-in, beside
the App Password): the installed-app round with PKCE comes back to this server, the refresh token is kept on the card sealed, and
from then on the calendar reads, names and answers on that Google calendar. Each install brings its own Google client (as Microsoft,
msauth.py): a card without one says how to add it. Google is mocked throughout, and the client is a stand-in."""
import json, os, unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from urllib.parse import parse_qs, urlsplit
from fastapi.testclient import TestClient

from taskuary import calendar as cal, calwrite, channels, config, googlecal, lookups, server
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


NO_ENV = {k: v for k, v in os.environ.items() if not k.startswith('TASKUARY_GOOGLE_CLIENT')}


OWN = {'google_client_id': 'own-desktop.apps.example', 'google_client_secret': 'not-a-secret'}     # the install's own Desktop client


class NoEnv(unittest.TestCase):
    """No Google client from the environment: only what the card holds."""
    def setUp(self):
        p = mock.patch.dict(os.environ, NO_ENV, clear=True); p.start(); self.addCleanup(p.stop)
        googlecal._FLOWS.clear(); googlecal._TOK.clear(); googlecal._GONE.clear()


EVENTS = {'items': [{'summary': 'Budget review', 'start': {'dateTime': '2026-10-27T13:00:00+00:00'},
                     'end': {'dateTime': '2026-10-27T14:00:00+00:00'}, 'attendees': [{'email': 'erin@northwind.example'}]}]}


class SignIn(NoEnv):
    def setUp(self):
        super().setUp()
        self.n = getattr(SignIn, 'n', 0) + 1; SignIn.n = self.n
        self.me = f'alex+{self.n}@northwind.example'      # one card's address: the server's store is shared across the suite

    def card(self, client=OWN, secret='app-password', **cfg):
        cid = server.store.save_connector({'Type': 'gmail', 'Name': f'Gmail cal {self.n}', 'Active': 1, 'Secret': secret,
                                           'ConfigJson': json.dumps({'address': self.me, **client, **cfg})}, 'test')
        self.addCleanup(server.store.save_connector, {'ConnectorId': cid, 'Active': 0}, 'test')   # no calendar left on for later tests
        return cid

    def test_a_card_without_a_client_says_how_to_add_one(self):
        cid = self.card(client={})
        st = c.get(f'/api/connectors/{cid}/google/calendar').json()
        self.assertEqual((st['available'], st['connected'], st['said']), (False, False, googlecal.NO_CLIENT))
        self.assertIn('client ID and secret on the Gmail card', st['said'])               # where it goes, and the card lists the steps
        r = c.post(f'/api/connectors/{cid}/google/calendar')
        self.assertEqual((r.status_code, r.json()['detail']), (409, googlecal.NO_CLIENT))
        self.assertNotIn("isn't available", st['said'])                                   # never "not in this build": the owner adds one
        st = c.get(f"/api/connectors/{self.card()}/google/calendar").json()               # with the install's own: offered, nothing to say
        self.assertEqual((st['available'], st['said']), (True, ''))

    def test_the_client_is_the_cards_own_or_the_environments(self):
        self.assertEqual(googlecal.client({}), ('', ''))                                  # Taskuary ships none
        self.assertEqual(googlecal.client(OWN), ('own-desktop.apps.example', 'not-a-secret'))
        self.assertEqual(googlecal.client({'google_client_id': 'half'}), ('', ''))
        with mock.patch.dict(os.environ, {'TASKUARY_GOOGLE_CLIENT_ID': 'dev.apps.example', 'TASKUARY_GOOGLE_CLIENT_SECRET': 'dev'}):
            self.assertEqual(googlecal.client({}), ('dev.apps.example', 'dev'))
            self.assertEqual(googlecal.client(OWN), ('own-desktop.apps.example', 'not-a-secret'))

    def test_an_agent_may_not_start_it(self):
        self.assertEqual(c.post(f'/api/connectors/{self.card()}/google/calendar',
                                headers=AGENT).status_code, 403)

    def test_signed_in_card_reads_the_google_calendar(self):
        # the server's store is shared across the suite and an earlier test may leave the calendar switched off: this one reads it
        was = server.store.get_setting('calendar_enabled'); server.store.set_setting('calendar_enabled', '1', 'test')
        self.addCleanup(server.store.set_setting, 'calendar_enabled', '1' if was is None else was, 'test')
        cid = self.card()
        self.assertTrue(any(self.me in x for x in cal.unread_mail(server.store)))           # before: a card no read reaches
        with fake_vault():
            f = c.post(f'/api/connectors/{cid}/google/calendar').json()
            q = {k: v[0] for k, v in parse_qs(urlsplit(f['url']).query).items()}
            # the mail (IMAP and SMTP by XOAUTH2), the calendar to read AND answer on, and the people search's contacts
            self.assertEqual(q['scope'].split(), ['https://mail.google.com/', 'https://www.googleapis.com/auth/calendar.events', *googlecal.PEOPLE])
            self.assertNotIn('calendar.readonly', q['scope'])
            self.assertEqual((q['code_challenge_method'], q['access_type'], q['client_id'], q['login_hint']), ('S256', 'offline', 'own-desktop.apps.example', self.me))
            self.assertTrue(q['redirect_uri'].startswith('http://127.0.0.1:') and q['redirect_uri'].endswith('/api/google/calendar/callback'))
            self.assertEqual(c.post(f'/api/connectors/{cid}/google/calendar/poll', json={'flow': f['flow']}).json(), {'status': 'pending'})
            self.assertIn('was not started here', c.get('/api/google/calendar/callback', params={'code': 'x', 'state': 'forged'}, headers=NOBODY).text)
            tok = R(j={'access_token': 'at1', 'refresh_token': 'rt1', 'expires_in': 3600, 'scope': googlecal.SCOPES})
            with mock.patch('taskuary.googlecal.requests.post', return_value=tok) as post:
                ok = c.get('/api/google/calendar/callback', params={'code': 'C', 'state': q['state']}, headers=NOBODY)  # outside the token gate
            self.assertIn('reads its calendar and answers invites', ok.text)
            self.assertIn('the App Password is used while one is saved', ok.text)             # which road the mail is on, said
            sent = post.call_args.kwargs['data']
            self.assertEqual((sent['code'], sent['grant_type'], sent['client_id'], sent['client_secret']),
                             ('C', 'authorization_code', 'own-desktop.apps.example', 'not-a-secret'))
            self.assertTrue(sent['code_verifier'])
            self.assertEqual(c.post(f'/api/connectors/{cid}/google/calendar/poll', json={'flow': f['flow']}).json()['status'], 'ok')
            self.assertIn('was not started here', c.get('/api/google/calendar/callback', params={'code': 'C', 'state': q['state']}, headers=NOBODY).text)
            raw = json.loads(server.store._one('SELECT ConfigJson FROM connector WHERE ConnectorId=?', (cid,))['ConfigJson'])
            self.assertEqual(raw['google_refresh_token'], 'vault:test:rt1')                  # sealed in the column
            opened = json.loads(server.store.get_connector(cid, with_secret=True)['ConfigJson'])
            self.assertEqual((opened['google_refresh_token'], opened['google_scope']), ('rt1', googlecal.SCOPES))
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
            # ACCEPT, DECLINE AND A NEW MEETING WORK ON THIS SIGN-IN: it asked for calendar.events, so the write check passes - on the
            # token the sign-in minted, with no second road to Google's token endpoint
            card = server.store.get_connector(cid, with_secret=True)
            with mock.patch('taskuary.googlecal.requests.post', side_effect=AssertionError('the sign-in\'s token is still live')), \
                 mock.patch('taskuary.demo.enabled', return_value=False):
                calwrite.require_write(server.store, {'provider': 'google', 'cfg': json.loads(card['ConfigJson'])})
            st = c.get(f'/api/connectors/{cid}/google/calendar').json()
            self.assertEqual((st['connected'], st['again']), (True, False))
            self.assertEqual(st['said'], 'Signed in with Google: mail, the calendar, contacts. Mail comes in by the App Password.')

    def test_a_card_with_no_app_password_is_told_its_mail_rides_the_sign_in(self):
        cid = self.card(secret=None)
        f = c.post(f'/api/connectors/{cid}/google/calendar').json()
        with fake_vault(), mock.patch('taskuary.googlecal.requests.post', return_value=R(j={'access_token': 'a', 'refresh_token': 'r', 'scope': googlecal.SCOPES})):
            out = c.get('/api/google/calendar/callback', params={'code': 'C', 'state': f['flow']}, headers=NOBODY)
            self.assertIn('Taskuary now reads and sends its mail, reads its calendar and answers invites', out.text)
            self.assertIn('Mail comes in through this sign-in.', c.get(f'/api/connectors/{cid}/google/calendar').json()['said'])

    def test_an_older_read_only_sign_in_is_asked_again_with_the_press_that_fixes_it(self):
        old = {'google_refresh_token': 'rt-old', 'google_scope': 'https://www.googleapis.com/auth/calendar.readonly'}
        cid = self.card(**old)
        st = c.get(f'/api/connectors/{cid}/google/calendar').json()
        self.assertEqual((st['connected'], st['again'], st['lapsed']), (True, True, False))
        self.assertIn('only reads the calendar', st['said']); self.assertIn('Sign in with Google', st['said'])
        with mock.patch('taskuary.googlecal.requests.post', return_value=R(j={'access_token': 'a', 'scope': old['google_scope']})), \
             mock.patch('taskuary.demo.enabled', return_value=False):
            with self.assertRaises(calwrite.NoAccess) as e: calwrite.require_write(server.store, {'provider': 'google', 'cfg': {**OWN, **old}})
        # the line names the press that fixes it - pressing it now asks for calendar.events - and the button opens that card
        self.assertIn('Press Sign in with Google on the Gmail card again', str(e.exception))
        self.assertNotIn('refresh token', str(e.exception))
        self.assertEqual(e.exception.fix['href'], '#connector=gmail')

    def test_unticked_mail_and_calendar_boxes_change_nothing(self):
        cid = self.card()
        f = c.post(f'/api/connectors/{cid}/google/calendar').json()
        with mock.patch('taskuary.googlecal.requests.post', return_value=R(j={'access_token': 'a', 'refresh_token': 'r', 'scope': 'openid'})):
            out = c.get('/api/google/calendar/callback', params={'code': 'C', 'state': f['flow']}, headers=NOBODY)
        self.assertIn('granted neither the mail nor the calendar', out.text)
        self.assertNotIn('google_refresh_token', json.loads(server.store.get_connector(cid, with_secret=True)['ConfigJson']))
        self.assertEqual(c.post(f'/api/connectors/{cid}/google/calendar/poll', json={'flow': f['flow']}).json()['status'], 'error')


class Refresh(NoEnv):
    CFG = {'google_refresh_token': 'rt-refresh', **OWN, 'address': ME}

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
        self.assertEqual(post.call_args.kwargs['data']['client_id'], 'own-desktop.apps.example')    # renewed on the install's own client
        self.assertEqual([k.kwargs['headers']['Authorization'] for k in get.call_args_list], ['Bearer a1', 'Bearer a1', 'Bearer a2'])

    def test_a_revoked_sign_in_says_how_to_fix_it(self):
        with mock.patch('taskuary.googlecal.requests.post', return_value=R(400, {'error': 'invalid_grant'})):
            with self.assertRaises(RuntimeError) as e: googlecal.access_token(self.CFG)
        self.assertIn('Sign in with Google on the Gmail card', str(e.exception))
        self.assertTrue(googlecal.lapsed(e.exception))
        # the card's box says it at once, without asking Google again - and stops saying it once a poll's error is gone and a token is live
        self.assertTrue(googlecal.state({}, self.CFG)['lapsed'])
        self.assertIn('Publish app', googlecal.state({}, self.CFG)['said'])                # a Testing client's weekly sign-out, and its fix
        with mock.patch('taskuary.googlecal.requests.post', return_value=R(j={'access_token': 'a3', 'expires_in': 3600})):
            googlecal.access_token(self.CFG)
        self.assertFalse(googlecal.state({'LastError': str(e.exception)}, self.CFG)['lapsed'])

    def test_a_sign_in_with_the_calendar_box_unticked_reads_no_calendar(self):
        t0 = datetime.now(timezone.utc)
        with mock.patch('taskuary.googlecal.requests.post', side_effect=AssertionError('nothing to ask Google for')),              mock.patch('taskuary.calendar.requests.get', side_effect=AssertionError('no calendar was granted')):
            self.assertEqual(cal.google_events({**self.CFG, 'google_scope': googlecal.MAIL}, t0, t0 + timedelta(days=1), timezone.utc), [])

    def test_googles_own_bad_minute_is_not_a_lapse(self):
        with mock.patch('taskuary.googlecal.requests.post', return_value=R(503, {'error': 'backend'})):
            with self.assertRaises(RuntimeError) as e: googlecal.access_token(self.CFG)
        self.assertFalse(googlecal.lapsed(e.exception)); self.assertFalse(googlecal.state({}, self.CFG)['lapsed'])

    def test_one_road_mints_every_google_token(self):
        # calwrite's own refresh, which asked Google on every Accept and never said a lapse, is gone: the calendar, the mail and Share ask token()
        self.assertFalse(hasattr(calwrite, '_google_token'))
        with mock.patch('taskuary.googlecal.requests.post', return_value=R(j={'access_token': 'a1', 'expires_in': 3600, 'scope': googlecal.SCOPES})) as post:
            self.assertEqual(googlecal.token(self.CFG), ('a1', googlecal.SCOPES))
            with mock.patch('taskuary.demo.enabled', return_value=False): calwrite.require_write(None, {'provider': 'google', 'cfg': self.CFG})
        self.assertEqual(post.call_count, 1)


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
