"""Sign in with Microsoft (msauth.py + the /ms endpoints): a regular user connects Outlook
with a code and their own account - no tenant id, no secret, no Azure portal."""
import json, unittest
from unittest import mock

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

    def test_graph_token_takes_the_signed_in_road(self):
        with mock.patch.object(msauth, 'access_token', return_value='DELEGATED') as a:
            self.assertEqual(channels.graph_token({'auth': 'user', 'client_id': 'x'}, 'RT'), 'DELEGATED')
        a.assert_called_once()


class EndpointTests(unittest.TestCase):
    def _outlook(self): return next(x for x in server.store.list_connectors() if x['Type'] == 'outlook')

    def test_sign_in_connects_the_card_as_the_person_and_adds_their_mailbox(self):
        cid = self._outlook()['ConnectorId']
        with mock.patch.object(msauth, 'device_start', return_value={'device_code': 'D', 'user_code': 'ABCD-1234', 'verification_uri': 'https://microsoft.com/devicelogin', 'expires_in': 900, 'interval': 5, 'message': ''}):
            d = c.post(f'/api/connectors/{cid}/ms/signin').json()
        self.assertEqual(d['user_code'], 'ABCD-1234'); self.assertNotIn('device_code', d)     # the device code never leaves the server
        with mock.patch.object(msauth, 'device_poll', return_value={'pending': True}):
            self.assertEqual(c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': d['flow']}).json()['status'], 'pending')
        with mock.patch.object(msauth, 'device_poll', return_value={'access_token': 'A', 'refresh_token': 'RT', 'expires_in': 3600}), \
             mock.patch.object(msauth, 'me', return_value={'account': 'leah@mfaheritage.net', 'name': 'Leah R'}):
            r = c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': d['flow']}).json()
        self.assertEqual((r['status'], r['account']), ('ok', 'leah@mfaheritage.net'))
        card = server.store.get_connector(cid, with_secret=True)
        cfg = json.loads(card['ConfigJson'])
        self.assertEqual((cfg['auth'], cfg['account'], card['Secret'], card['Active']), ('user', 'leah@mfaheritage.net', 'RT', 1))
        self.assertTrue(any(s['Channel'] == 'email' and s['Address'] == 'leah@mfaheritage.net' for s in server.store.list_sources()))
        self.assertEqual(c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': d['flow']}).status_code, 404)   # a finished flow is gone
        # and out again
        self.assertTrue(c.post(f'/api/connectors/{cid}/ms/signout').json()['ok'])
        card = server.store.get_connector(cid, with_secret=True)
        self.assertNotIn('auth', json.loads(card['ConfigJson'])); self.assertFalse(card['Secret']); self.assertEqual(card['Active'], 0)

    def test_a_declined_sign_in_is_reported_not_raised(self):
        cid = self._outlook()['ConnectorId']
        with mock.patch.object(msauth, 'device_start', return_value={'device_code': 'D', 'user_code': 'X', 'verification_uri': 'u', 'expires_in': 9, 'interval': 1, 'message': ''}):
            flow = c.post(f'/api/connectors/{cid}/ms/signin').json()['flow']
        with mock.patch.object(msauth, 'device_poll', side_effect=RuntimeError('you declined the sign-in')):
            r = c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': flow}).json()
        self.assertEqual((r['status'], r['detail']), ('error', 'you declined the sign-in'))

    def test_need_admin_approval_hands_the_user_the_link_to_forward(self):
        cid = self._outlook()['ConnectorId']
        with mock.patch.object(msauth, 'device_start', return_value={'device_code': 'D', 'user_code': 'X', 'verification_uri': 'u', 'expires_in': 9, 'interval': 1, 'message': ''}):
            flow = c.post(f'/api/connectors/{cid}/ms/signin').json()['flow']
        with mock.patch.object(msauth, 'device_poll', side_effect=msauth.AdminConsent('needs an admin')), mock.patch.object(msauth, 'PUBLIC_CLIENT_ID', 'app-1'):
            r = c.post(f'/api/connectors/{cid}/ms/poll', json={'flow': flow}).json()
        self.assertEqual(r['status'], 'error'); self.assertIn('adminconsent?client_id=app-1', r['admin_consent_url'])
        with mock.patch.object(msauth, 'PUBLIC_CLIENT_ID', 'app-1'):                       # and on request, before anyone fails
            self.assertIn('adminconsent', c.get(f'/api/connectors/{cid}/ms/adminlink').json()['url'])
        with mock.patch.object(msauth, 'PUBLIC_CLIENT_ID', ''):
            self.assertEqual(c.get(f'/api/connectors/{cid}/ms/adminlink').status_code, 409)   # no app id yet: said, not a 500

    def test_teams_cannot_ride_a_personal_sign_in(self):
        from taskuary.store import MemoryStore
        s = MemoryStore()
        o = s.get_connector_by_type('outlook'); t = s.get_connector_by_type('teams')
        s.save_connector({'ConnectorId': o['ConnectorId'], 'ConfigJson': json.dumps({'auth': 'user', 'account': 'me@x.com'}), 'Secret': 'RT', 'Active': 1}, 't')
        out = channels.test_connector(s, t['ConnectorId'])
        self.assertFalse(out['ok']); self.assertIn('tenant app', out['detail'])


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
