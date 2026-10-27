"""Sign in with Microsoft (msauth.py + the /ms endpoints): a regular user connects Outlook
in the browser (or, as a fallback, a code) with their own account - no tenant id, no secret, no Azure portal."""
import base64, hashlib, json, unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from taskuary import msauth, server, channels

c = TestClient(server.app)


class R:
    def __init__(self, code, body): self.status_code, self._b = code, body; self.headers = {'content-type': 'application/json'}; self.text = json.dumps(body)
    def json(self): return self._b
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)


CFG = {'client_id': 'app-1'}


class DeviceFlowTests(unittest.TestCase):
    def test_start_returns_what_the_user_needs_and_what_we_poll_with(self):
        with mock.patch('requests.post', return_value=R(200, {'device_code': 'D', 'user_code': 'ABCD-1234', 'verification_uri': 'https://microsoft.com/devicelogin',
                                                              'expires_in': 900, 'interval': 5, 'message': 'go'})) as p:
            d = msauth.device_start(CFG)
        self.assertEqual((d['user_code'], d['device_code'], d['interval']), ('ABCD-1234', 'D', 5))
        self.assertIn('/common/oauth2/v2.0/devicecode', p.call_args[0][0]); self.assertIn('Mail.Send', p.call_args[1]['data']['scope'])

    def test_no_app_id_is_said_plainly(self):
        with mock.patch.object(msauth, 'PUBLIC_CLIENT_ID', ''):
            with self.assertRaises(RuntimeError) as e: msauth.device_start({})
        self.assertIn('TASKUARY_MS_CLIENT_ID', str(e.exception))

    def test_poll_is_pending_then_tokens_then_friendly_errors(self):
        with mock.patch('requests.post', return_value=R(400, {'error': 'authorization_pending'})):
            self.assertTrue(msauth.device_poll(CFG, 'D')['pending'])
        with mock.patch('requests.post', return_value=R(200, {'access_token': 'A', 'refresh_token': 'RT', 'expires_in': 3600})):
            self.assertEqual(msauth.device_poll(CFG, 'D')['refresh_token'], 'RT')
        with mock.patch('requests.post', return_value=R(400, {'error': 'expired_token'})):
            with self.assertRaises(RuntimeError) as e: msauth.device_poll(CFG, 'D')
        self.assertIn('expired', str(e.exception))
        with mock.patch('requests.post', return_value=R(400, {'error': 'invalid_grant', 'error_description': 'AADSTS65001: The user or administrator has not consented'})):
            with self.assertRaises(msauth.AdminConsent) as e: msauth.device_poll(CFG, 'D')   # its own kind: the server attaches the link
        self.assertIn('approval link', str(e.exception))

    def test_the_admin_link_is_a_consent_grant_on_our_app_id(self):
        u = msauth.admin_consent_url(CFG)
        self.assertTrue(u.startswith('https://login.microsoftonline.com/organizations/v2.0/adminconsent?client_id=app-1&'))   # common -> organizations: personal accounts have no admin
        self.assertIn('Mail.ReadWrite', u); self.assertIn('redirect_uri=https%3A%2F%2Flogin.microsoftonline.com%2Fcommon%2Foauth2%2Fnativeclient', u)
        self.assertIn('/contoso.example/v2.0/adminconsent', msauth.admin_consent_url({**CFG, 'tenant_id': 'contoso.example'}))
        with mock.patch.object(msauth, 'PUBLIC_CLIENT_ID', ''), self.assertRaises(RuntimeError): msauth.admin_consent_url({})

    def test_access_token_is_cached_and_a_rotated_refresh_token_is_persisted(self):
        msauth._CACHE.clear(); saved = []
        msauth.on_rotate = lambda cid, rt: saved.append((cid, rt))
        try:
            with mock.patch('requests.post', return_value=R(200, {'access_token': 'A1', 'refresh_token': 'RT2', 'expires_in': 3600})) as p:
                self.assertEqual(msauth.access_token({**CFG, '_cid': 7}, 'RT1'), 'A1')
                self.assertEqual(msauth.access_token({**CFG, '_cid': 7}, 'RT1'), 'A1')     # cached: one HTTP call
            self.assertEqual(p.call_count, 1); self.assertEqual(saved, [(7, 'RT2')])
        finally: msauth.on_rotate = None; msauth._CACHE.clear()

    def test_two_polls_sharing_a_refresh_token_mint_once(self):
        """Outlook and Teams can borrow the same card. A parallel poll that minted twice
        would rotate the first token out from under the second."""
        import threading, time
        msauth._CACHE.clear()
        n = []
        def post(*a, **k):
            n.append(1); time.sleep(0.05)
            return R(200, {'access_token': 'A1', 'refresh_token': 'RT1', 'expires_in': 3600})
        with mock.patch('requests.post', side_effect=post):
            got = [None, None]
            def one(i): got[i] = msauth.access_token(CFG, 'RT1')
            a = threading.Thread(target=one, args=(0,)); b = threading.Thread(target=one, args=(1,))
            a.start(); b.start(); a.join(); b.join()
        self.assertEqual(got, ['A1', 'A1'])
        self.assertEqual(len(n), 1)
        msauth._CACHE.clear()

    def test_graph_token_takes_the_signed_in_road(self):
        with mock.patch.object(msauth, 'access_token', return_value='DELEGATED') as a:
            self.assertEqual(channels.graph_token({'auth': 'user', 'client_id': 'x'}, 'RT'), 'DELEGATED')
        a.assert_called_once()


class EndpointTests(unittest.TestCase):
    def _outlook(self): return next(x for x in server.store.list_connectors() if x['Type'] == 'outlook')

    def test_sign_in_connects_the_card_as_the_person_and_adds_their_mailbox(self):
        cid = self._outlook()['ConnectorId']
        with mock.patch.object(msauth, 'device_start', return_value={'device_code': 'D', 'user_code': 'ABCD-1234', 'verification_uri': 'https://microsoft.com/devicelogin', 'expires_in': 900, 'interval': 5, 'message': ''}):
            d = c.post(f'/api/connectors/{cid}/ms/signin', json={'code': True}).json()
        self.assertEqual(d['user_code'], 'ABCD-1234'); self.assertNotIn('device_code', d)     # the device code never leaves the server
        with mock.patch.object(msauth, 'device_poll', return_value={'pending': True}):
            self.assertEqual(c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': d['flow']}).json()['status'], 'pending')
        with mock.patch.object(msauth, 'device_poll', return_value={'access_token': 'A', 'refresh_token': 'RT', 'expires_in': 3600}), \
             mock.patch.object(msauth, 'me', return_value={'account': 'teammate@northwind.example', 'name': 'Sam R'}):
            r = c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': d['flow']}).json()
        self.assertEqual((r['status'], r['account']), ('ok', 'teammate@northwind.example'))
        card = server.store.get_connector(cid, with_secret=True)
        cfg = json.loads(card['ConfigJson'])
        self.assertEqual((cfg['auth'], cfg['account'], card['Secret'], card['Active']), ('user', 'teammate@northwind.example', 'RT', 1))
        self.assertTrue(any(s['Channel'] == 'email' and s['Address'] == 'teammate@northwind.example' for s in server.store.list_sources()))
        self.assertEqual(c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': d['flow']}).status_code, 404)   # a finished flow is gone
        # and out again
        self.assertTrue(c.post(f'/api/connectors/{cid}/ms/signout').json()['ok'])
        card = server.store.get_connector(cid, with_secret=True)
        self.assertNotIn('auth', json.loads(card['ConfigJson'])); self.assertFalse(card['Secret']); self.assertEqual(card['Active'], 0)

    def test_a_declined_sign_in_is_reported_not_raised(self):
        cid = self._outlook()['ConnectorId']
        with mock.patch.object(msauth, 'device_start', return_value={'device_code': 'D', 'user_code': 'X', 'verification_uri': 'u', 'expires_in': 9, 'interval': 1, 'message': ''}):
            flow = c.post(f'/api/connectors/{cid}/ms/signin', json={'code': True}).json()['flow']
        with mock.patch.object(msauth, 'device_poll', side_effect=RuntimeError('you declined the sign-in')):
            r = c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': flow}).json()
        self.assertEqual((r['status'], r['detail']), ('error', 'you declined the sign-in'))

    def test_need_admin_approval_hands_the_user_the_link_to_forward(self):
        cid = self._outlook()['ConnectorId']
        with mock.patch.object(msauth, 'device_start', return_value={'device_code': 'D', 'user_code': 'X', 'verification_uri': 'u', 'expires_in': 9, 'interval': 1, 'message': ''}):
            flow = c.post(f'/api/connectors/{cid}/ms/signin', json={'code': True}).json()['flow']
        with mock.patch.object(msauth, 'device_poll', side_effect=msauth.AdminConsent('needs an admin')), mock.patch.object(msauth, 'PUBLIC_CLIENT_ID', 'app-1'):
            r = c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': flow}).json()
        self.assertEqual(r['status'], 'error'); self.assertIn('adminconsent?client_id=app-1', r['admin_consent_url'])
        with mock.patch.object(msauth, 'PUBLIC_CLIENT_ID', 'app-1'):                       # and on request, before anyone fails
            self.assertIn('adminconsent', c.get(f'/api/connectors/{cid}/ms/adminlink').json()['url'])
        with mock.patch.object(msauth, 'PUBLIC_CLIENT_ID', ''):
            self.assertEqual(c.get(f'/api/connectors/{cid}/ms/adminlink').status_code, 409)   # no app id yet: said, not a 500

    def test_teams_does_not_ride_another_accounts_sign_in(self):
        from taskuary.store import MemoryStore
        s = MemoryStore()
        o = s.get_connector_by_type('outlook'); t = s.get_connector_by_type('teams')
        s.save_connector({'ConnectorId': o['ConnectorId'], 'ConfigJson': json.dumps({'auth': 'user', 'account': 'me@x.com'}), 'Secret': 'RT', 'Active': 1}, 't')
        out = channels.test_connector(s, t['ConnectorId'])
        # a Teams card naming no account is not read through whichever Outlook card is first: it signs in itself
        self.assertFalse(out['ok']); self.assertIn('Sign in with Microsoft on this Teams card', out['detail'])


class BrowserSignInTests(unittest.TestCase):
    """THE DEFAULT SIGN-IN is the browser one - authorization code + PKCE, back to this server on localhost. Conditional Access in
    an enterprise tenant blocks the device-code flow (an IT department, 2026-10-27), so the code is the fallback the owner picks."""
    LOCAL = TestClient(server.app, client=('127.0.0.1', 50000))

    def setUp(self):
        server._MSFLOWS.clear(); msauth._CACHE.clear()
        BrowserSignInTests.n = getattr(BrowserSignInTests, 'n', 0) + 1
        self.n, self.who = BrowserSignInTests.n, f'erin+{BrowserSignInTests.n}@northwind.example'

    def _card(self, kind='outlook'):
        return server.store.save_connector({'Type': kind, 'Name': f'{kind} browser {self.n}', 'Active': 0}, 'test')

    def _start(self, cid, **body):
        with mock.patch.object(msauth, 'PUBLIC_CLIENT_ID', 'app-1'): d = c.post(f'/api/connectors/{cid}/ms/signin', json=body).json()
        self.assertEqual(d['mode'], 'browser'); self.assertNotIn('user_code', d)
        return d, parse_qs(urlsplit(d['url']).query)

    def _back(self, q, code='C', client=None, **extra):
        return (client or self.LOCAL).get('/api/ms/callback', params={'code': code, 'state': q['state'][0], **extra})

    def test_the_authorize_url_asks_with_pkce_s256_the_cards_scopes_and_a_loopback_return(self):
        d, q = self._start(self._card())
        self.assertTrue(d['url'].startswith('https://login.microsoftonline.com/common/oauth2/v2.0/authorize?'))
        f = server._MSFLOWS[d['flow']]
        self.assertEqual((q['client_id'][0], q['response_type'][0], q['code_challenge_method'][0], q['prompt'][0]), ('app-1', 'code', 'S256', 'select_account'))
        self.assertEqual(q['code_challenge'][0], base64.urlsafe_b64encode(hashlib.sha256(f['verifier'].encode()).digest()).rstrip(b'=').decode())
        self.assertEqual(q['scope'][0], msauth.SCOPES)
        self.assertEqual(q['redirect_uri'][0], f"http://localhost:{server.cfg['server'].get('port') or 7787}/api/ms/callback")
        self.assertNotIn(f['verifier'], d['url']); self.assertNotIn('verifier', d)         # the verifier never leaves the server
        _, q = self._start(self._card('teams'))
        self.assertEqual(q['scope'][0], msauth.TEAMS_SCOPES, 'a Teams card asks for chats, not mail')
        _, q = self._start(self._card(), files=True)
        self.assertIn('Files.ReadWrite', q['scope'][0].split())

    def test_the_callback_redeems_the_code_with_the_verifier_and_connects_the_card_like_a_device_code(self):
        cid = self._card(); d, q = self._start(cid)
        self.assertEqual(c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': d['flow']}).json()['status'], 'pending')
        verifier = server._MSFLOWS[d['flow']]['verifier']
        tok = R(200, {'access_token': 'AT-secret', 'refresh_token': 'RT-secret', 'expires_in': 3600, 'scope': msauth.SCOPES})
        with mock.patch('taskuary.msauth.requests.post', return_value=tok) as p, mock.patch.object(msauth, 'PUBLIC_CLIENT_ID', 'app-1'), \
             mock.patch.object(msauth, 'me', return_value={'account': self.who, 'name': 'Erin Blake'}), mock.patch.object(server, '_poll_reports'):
            r = self._back(q, code='THE-CODE')
        self.assertIn('/common/oauth2/v2.0/token', p.call_args[0][0])
        sent = p.call_args[1]['data']
        self.assertEqual((sent['grant_type'], sent['code'], sent['code_verifier'], sent['client_id']), ('authorization_code', 'THE-CODE', verifier, 'app-1'))
        self.assertEqual(sent['redirect_uri'], q['redirect_uri'][0]); self.assertNotIn('client_secret', sent)
        self.assertEqual(r.status_code, 200); self.assertIn('Signed in - you can close this tab', r.text)
        self.assertNotIn('AT-secret', r.text); self.assertNotIn('RT-secret', r.text); self.assertNotIn('THE-CODE', r.text)
        self.assertIn('no-store', r.headers['cache-control']); self.assertIn("default-src 'none'", r.headers['content-security-policy'])
        out = c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': d['flow']}).json()
        self.assertEqual((out['status'], out['account']), ('ok', self.who))
        card = server.store.get_connector(cid, with_secret=True); cfg = json.loads(card['ConfigJson'])
        self.assertEqual((cfg['auth'], cfg['account'], cfg['granted_scope'], card['Secret'], card['Active']), ('user', self.who, msauth.SCOPES, 'RT-secret', 1))
        self.assertTrue(any(s['Channel'] == 'email' and s['Address'] == self.who for s in server.store.list_sources()))
        self.assertEqual(c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': d['flow']}).status_code, 404)   # reported once, then gone
        # ...and the refresh is the one every sign-in had: the stored refresh token, the granted scopes, no secret
        with mock.patch('taskuary.msauth.requests.post', return_value=R(200, {'access_token': 'A2', 'refresh_token': 'RT2', 'expires_in': 3600})) as p, \
             mock.patch.object(msauth, 'PUBLIC_CLIENT_ID', 'app-1'), mock.patch.object(msauth, 'on_rotate'):
            self.assertEqual(msauth.access_token({**cfg, '_cid': cid}, card['Secret']), 'A2')
        sent = p.call_args[1]['data']
        self.assertEqual((sent['grant_type'], sent['refresh_token'], sent['scope']), ('refresh_token', 'RT-secret', msauth.refresh_scope(cfg)))

    def test_a_state_answers_once(self):
        cid = self._card(); d, q = self._start(cid)
        tok = R(200, {'access_token': 'A', 'refresh_token': 'RT', 'expires_in': 3600})
        with mock.patch('taskuary.msauth.requests.post', return_value=tok) as p, mock.patch.object(msauth, 'PUBLIC_CLIENT_ID', 'app-1'), \
             mock.patch.object(msauth, 'me', return_value={'account': self.who, 'name': 'Erin Blake'}), mock.patch.object(server, '_poll_reports'):
            self.assertIn('Signed in', self._back(q).text)
            again = self._back(q, code='C2')
        self.assertIn('already used', again.text); self.assertEqual(p.call_count, 1, 'a reused state redeems nothing')

    def test_a_wrong_or_missing_state_is_refused_and_the_real_round_still_waits(self):
        cid = self._card(); d, q = self._start(cid)
        with mock.patch('taskuary.msauth.requests.post') as p:
            for params in ({'code': 'C', 'state': 'not-the-state'}, {'code': 'C'}, {'code': 'C', 'state': ''}):
                r = self.LOCAL.get('/api/ms/callback', params=params)
                self.assertEqual(r.status_code, 200); self.assertIn('Not changed', r.text)
        p.assert_not_called()
        self.assertEqual(c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': d['flow']}).json()['status'], 'pending')

    def test_only_this_machine_finishes_a_sign_in(self):
        cid = self._card(); d, q = self._start(cid)
        with mock.patch('taskuary.msauth.requests.post') as p:
            r = self._back(q, client=TestClient(server.app, client=('192.0.2.7', 50000)))
        self.assertIn('only finishes on the computer Taskuary runs on', r.text); p.assert_not_called()
        self.assertFalse(server._MSFLOWS[d['flow']].get('claimed'), "a refused stranger does not burn the owner's round")

    def test_an_old_round_is_over(self):
        cid = self._card(); d, q = self._start(cid)
        server._MSFLOWS[d['flow']]['at'] -= server.MS_TTL + 1
        with mock.patch('taskuary.msauth.requests.post') as p: self.assertIn('too old', self._back(q).text)
        p.assert_not_called()
        self.assertEqual(c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': d['flow']}).json()['status'], 'error')

    def test_declined_and_need_admin_come_back_to_the_card(self):
        cid = self._card(); d, q = self._start(cid)
        self.LOCAL.get('/api/ms/callback', params={'state': q['state'][0], 'error': 'access_denied', 'error_description': 'The user has cancelled.'})
        self.assertEqual(c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': d['flow']}).json()['detail'], 'you declined the sign-in')
        d, q = self._start(cid)
        with mock.patch.object(msauth, 'PUBLIC_CLIENT_ID', 'app-1'):
            r = self.LOCAL.get('/api/ms/callback', params={'state': q['state'][0], 'error': 'consent_required',
                                                         'error_description': 'AADSTS90094: Admin consent is required.'})
            out = c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': d['flow']}).json()
        self.assertIn('admin', r.text); self.assertIn('adminconsent?client_id=app-1', out['admin_consent_url'])
        self.assertEqual(server.store.get_connector(cid)['Active'], 0, 'a failed sign-in changes nothing on the card')

    def test_the_code_is_still_there_when_the_owner_asks_for_it(self):
        cid = self._card()
        with mock.patch.object(msauth, 'device_start', return_value={'device_code': 'D', 'user_code': 'ABCD-1234', 'verification_uri': 'https://microsoft.com/devicelogin',
                                                                     'expires_in': 900, 'interval': 5, 'message': ''}) as ds, \
             mock.patch.object(msauth, 'browser_start', return_value={'url': 'u', 'state': 's', 'verifier': 'v'}) as bs:
            d = c.post(f'/api/connectors/{cid}/ms/signin', json={'code': True}).json()
            c.post(f'/api/connectors/{cid}/ms/signin')
        self.assertEqual((d['mode'], d['user_code']), ('code', 'ABCD-1234')); self.assertNotIn('device_code', d)
        ds.assert_called_once(); bs.assert_called_once()       # ...and only then: no body is the browser


class ImapMessagesTests(unittest.TestCase):
    def test_a_microsoft_mailbox_is_sent_to_the_outlook_card(self):
        from taskuary import imapmail
        c_ = {'Type': 'imap', 'Secret': 'pw', 'ConfigJson': json.dumps({'address': 'someone@outlook.com', 'imap_host': 'outlook.office365.com'})}
        with self.assertRaises(RuntimeError) as e: imapmail._login(c_)
        self.assertIn('Sign in with Microsoft', str(e.exception))

    def test_a_blocked_socket_is_explained(self):
        from taskuary import imapmail
        c_ = {'Type': 'imap', 'Secret': 'pw', 'ConfigJson': json.dumps({'address': 'me@partnerfirm.com', 'imap_host': 'imap.partnerfirm.com'})}
        err = OSError(10013, 'An attempt was made to access a socket in a way forbidden by its access permissions'); err.winerror = 10013
        with mock.patch('imaplib.IMAP4_SSL', side_effect=err):
            with self.assertRaises(RuntimeError) as e: imapmail._login(c_)
        self.assertIn('firewall', str(e.exception)); self.assertIn('imap.partnerfirm.com:993', str(e.exception))


if __name__ == '__main__': unittest.main()
