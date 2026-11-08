"""ONE OAUTH ROAD (oauth.py) and the vendors that only push (pushin.py). Vendors are faked with answers shaped as their docs show - no
network. The road: a one-time state and PKCE out, the code redeemed once, the tokens sealed as the card's Secret and renewed before they
lapse (a rotated refresh token kept); the routes: only the owner starts a sign-in, the return answers only its own state. The pushes:
a signature that does not match keeps nothing; one that does is queued and filed once by the next sync, as a stranger's words."""
import base64, hashlib, hmac, json, time, unittest
from urllib.parse import parse_qs, urlsplit
from unittest import mock

from taskuary import inboxes, oauth, pushin, senders
from taskuary.store import MemoryStore

SERVER = {'port': 7787}


class R:
    def __init__(self, j, code=200): self._j, self.status_code, self.text = j, code, json.dumps(j)
    def json(self): return self._j
    def raise_for_status(self): pass


def card(s, t, secret=None, **cfg):
    c = s.get_connector_by_type(t)
    s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'ConfigJson': json.dumps(cfg), **({'Secret': secret} if secret else {})}, 't')
    return c['ConnectorId']


def q(url): return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


class TheRoad(unittest.TestCase):
    def test_a_sign_in_goes_out_with_state_and_pkce_and_comes_back_once(self):
        s = MemoryStore(); cid = card(s, 'zoom', client_id='zc', client_secret='zs')
        url = oauth.start(s, cid, SERVER)
        a = q(url)
        self.assertTrue(url.startswith('https://zoom.us/oauth/authorize?'))
        self.assertEqual((a['client_id'], a['redirect_uri'], a['code_challenge_method']), ('zc', 'http://127.0.0.1:7787/api/oauth/callback', 'S256'))
        tok = {'access_token': 'at-1', 'refresh_token': 'rt-1', 'expires_in': 3600}
        with mock.patch.object(oauth.requests, 'post', return_value=R(tok)) as p:
            ok, msg = oauth.finish(s, 'code-1', a['state'])
        self.assertTrue(ok, msg)
        d, kw = p.call_args.kwargs['data'], p.call_args.kwargs
        self.assertEqual((d['grant_type'], d['code'], kw['auth']), ('authorization_code', 'code-1', ('zc', 'zs')))      # Zoom: the secret as Basic
        self.assertEqual(base64.urlsafe_b64encode(hashlib.sha256(d['code_verifier'].encode()).digest()).rstrip(b'=').decode(), a['code_challenge'])
        c = s.get_connector(cid, with_secret=True)
        self.assertEqual(oauth.bundle(c)['refresh_token'], 'rt-1'); self.assertTrue(c['Active'])
        self.assertEqual(oauth.access(s, c), 'at-1')
        self.assertFalse(oauth.finish(s, 'code-1', a['state'])[0])                       # a state answers once
        self.assertFalse(oauth.finish(s, 'code-2', 'made-up')[0])

    def test_an_expired_token_renews_once_and_keeps_the_rotated_refresh_token(self):
        s = MemoryStore()
        cid = card(s, 'box', json.dumps({'access_token': 'old', 'refresh_token': 'rt-1', 'expires_at': time.time() - 5}), client_id='b', client_secret='bs')
        with mock.patch.object(oauth.requests, 'post', return_value=R({'access_token': 'new', 'refresh_token': 'rt-2', 'expires_in': 3600})) as p:
            self.assertEqual(oauth.access(s, s.get_connector(cid, with_secret=True)), 'new')
            self.assertEqual(oauth.access(s, s.get_connector(cid, with_secret=True)), 'new')
        self.assertEqual(p.call_count, 1)
        self.assertEqual((p.call_args.kwargs['data']['grant_type'], p.call_args.kwargs['data']['refresh_token']), ('refresh_token', 'rt-1'))
        self.assertEqual(oauth.bundle(s.get_connector(cid, with_secret=True))['refresh_token'], 'rt-2')
        s.save_connector({'ConnectorId': cid, 'Secret': json.dumps({'access_token': 'x', 'refresh_token': 'rt-2', 'expires_at': 1})}, 't')
        with mock.patch.object(oauth.requests, 'post', return_value=R({'error': 'invalid_grant'}, 400)), \
                self.assertRaisesRegex(oauth.OAuthError, 'press Sign in on the card again'):
            oauth.access(s, s.get_connector(cid, with_secret=True))

    def test_threads_swaps_for_a_long_lived_token_and_renews_it_by_get(self):
        s = MemoryStore(); cid = card(s, 'threads', client_id='t', client_secret='ts', redirect_base='https://tunnel.northwind.example')
        url = oauth.start(s, cid, SERVER)
        self.assertEqual(q(url)['redirect_uri'], 'https://tunnel.northwind.example/api/oauth/callback')
        self.assertNotIn('code_challenge', q(url))
        with mock.patch.object(oauth.requests, 'post', return_value=R({'access_token': 'short', 'user_id': 1})), \
                mock.patch.object(oauth.requests, 'get', return_value=R({'access_token': 'long', 'expires_in': 5184000})) as g:
            self.assertTrue(oauth.finish(s, 'c', q(url)['state'])[0])
        self.assertEqual(g.call_args.kwargs['params'], {'grant_type': 'th_exchange_token', 'client_secret': 'ts', 'access_token': 'short'})
        self.assertEqual(oauth.status(s, cid, SERVER)['days_left'], 59)               # no refresh token: the card counts the days
        s.save_connector({'ConnectorId': cid, 'Secret': json.dumps({'access_token': 'long', 'expires_at': 1})}, 't')
        with mock.patch.object(oauth.requests, 'get', return_value=R({'access_token': 'longer', 'expires_in': 5184000})) as g:
            self.assertEqual(oauth.access(s, s.get_connector(cid, with_secret=True)), 'longer')
        self.assertEqual(g.call_args.kwargs['params']['grant_type'], 'th_refresh_token')

    def test_the_cards_own_host_is_the_vendors_and_salesforce_keeps_its_instance(self):
        s = MemoryStore(); cid = card(s, 'salesforce', client_id='sf', client_secret='ss', login_host='northwind.my.salesforce.com')
        url = oauth.start(s, cid, SERVER)
        self.assertTrue(url.startswith('https://northwind.my.salesforce.com/services/oauth2/authorize?'))
        with mock.patch.object(oauth.requests, 'post', return_value=R({'access_token': 'a', 'refresh_token': 'r', 'instance_url': 'https://northwind.my.salesforce.com'})) as p:
            self.assertTrue(oauth.finish(s, 'c', q(url)['state'])[0])
        self.assertEqual(p.call_args.args[0], 'https://northwind.my.salesforce.com/services/oauth2/token')
        self.assertEqual(json.loads(s.get_connector(cid)['ConfigJson'])['host'], 'https://northwind.my.salesforce.com')
        for bad in ('evil.example', 'login.salesforce.com.evil.example', 'x/y.salesforce.com'):
            s.merge_connector_config(cid, {'login_host': bad})
            with self.subTest(bad=bad), self.assertRaises(oauth.OAuthError): oauth.start(s, cid, SERVER)

    def test_no_app_no_sign_in_and_a_redirect_must_be_https(self):
        s = MemoryStore()
        with self.assertRaisesRegex(oauth.OAuthError, 'Client ID and Client Secret'): oauth.start(s, card(s, 'webex'), SERVER)
        with self.assertRaises(oauth.OAuthError): oauth.redirect_uri(SERVER, {'redirect_base': 'http://tunnel.northwind.example'})
        with self.assertRaisesRegex(oauth.OAuthError, 'not signed in'): oauth.access(s, s.get_connector_by_type('webex', with_secret=True))


class TheRoutes(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        self.server, self.s = server, MemoryStore()
        self.p = mock.patch.object(server, 'store', self.s); self.p.start(); self.addCleanup(self.p.stop)
        tok = server.cfg['server'].get('token') or ''
        self.owner = TestClient(server.app, base_url='http://127.0.0.1', headers={'X-Taskuary-Token': tok})
        self.agent = TestClient(server.app, base_url='http://127.0.0.1', headers={'X-Taskuary-Token': server.cfg['server'].get('agent_token') or ''})
        self.bare = TestClient(server.app, base_url='http://tunnel.northwind.example')

    def test_only_the_owner_starts_a_sign_in_and_the_return_needs_its_own_state(self):
        cid = card(self.s, 'hubspot', client_id='h', client_secret='hs')
        st = self.owner.get(f'/api/connectors/{cid}/oauth/status').json()
        self.assertEqual((st['has_app'], st['connected'], st['redirect_uri']), (True, False, 'http://127.0.0.1:%s/api/oauth/callback' % (self.server.cfg['server'].get('port') or 7787)))
        self.assertEqual(self.agent.post(f'/api/connectors/{cid}/oauth/start').status_code, 403)
        url = self.owner.post(f'/api/connectors/{cid}/oauth/start').json()['url']
        self.assertTrue(url.startswith('https://app.hubspot.com/oauth/authorize?'))
        with mock.patch.object(self.server, '_is_loopback', return_value=True):
            self.assertIn('was not started here', self.bare.get('/api/oauth/callback', params={'code': 'c', 'state': 'nope'}).text)
            with mock.patch.object(oauth.requests, 'post', return_value=R({'access_token': 'a', 'refresh_token': 'r', 'expires_in': 1800})):
                page = self.bare.get('/api/oauth/callback', params={'code': 'c', 'state': q(url)['state']}).text
        self.assertIn('HubSpot is signed in', page); self.assertNotIn('"a"', page)
        self.assertTrue(self.owner.get(f'/api/connectors/{cid}/oauth/status').json()['connected'])

    def test_a_push_through_a_tunnel_reaches_only_its_own_door(self):
        cid = card(self.s, 'line', 'line-token', channel_secret='cs')
        self.assertEqual(self.bare.get('/').status_code, 403)                           # the page under the tunnel's name: no
        body = json.dumps({'events': []}).encode()
        sig = base64.b64encode(hmac.new(b'cs', body, hashlib.sha256).digest()).decode()
        self.assertEqual(self.bare.post(f'/api/inbound/line/{cid}', content=body, headers={'X-Line-Signature': sig}).json(), {'taken': 0})
        self.assertEqual(self.bare.post(f'/api/inbound/line/{cid}', content=body, headers={'X-Line-Signature': 'bad'}).status_code, 403)
        self.assertEqual(self.agent.post(f'/api/inbound/line/{cid}', content=body, headers={'X-Line-Signature': sig}).status_code, 403)
        self.assertEqual(self.agent.get(f'/api/connectors/{cid}/inbound').status_code, 403)
        self.assertEqual(self.owner.get(f'/api/connectors/{cid}/inbound').json()['path'], f'/api/inbound/line/{cid}')


class ThePushes(unittest.TestCase):
    def test_line_files_a_signed_message_once_as_a_stranger(self):
        s = MemoryStore(); cid = card(s, 'line', 'line-token', channel_secret='cs')
        ev = {'destination': 'U0', 'events': [{'type': 'message', 'mode': 'active', 'webhookEventId': 'W1', 'timestamp': 1787300000000,
              'source': {'type': 'user', 'userId': 'U9'}, 'replyToken': 'r', 'message': {'type': 'text', 'id': 'M1', 'text': 'is the order ready?'}},
              {'type': 'follow', 'source': {'type': 'user', 'userId': 'U9'}, 'timestamp': 1787300000000}]}
        body = json.dumps(ev).encode()
        with self.assertRaises(pushin.Refused): pushin.take(s, 'line', cid, '', {'X-Line-Signature': 'x'}, body)
        sig = base64.b64encode(hmac.new(b'cs', body, hashlib.sha256).digest()).decode()
        self.assertEqual(pushin.take(s, 'line', cid, '', {'X-Line-Signature': sig}, body), 1)
        inboxes._MEMO.clear()
        with mock.patch.object(inboxes.requests, 'request', return_value=R({'displayName': 'Pat Buyer', 'userId': 'U9'})):
            from datetime import datetime
            c = s.get_connector(cid, with_secret=True)
            self.assertEqual(inboxes.poll(s, c, datetime(2030, 1, 1)), 1)              # drained: no time floor drops it
            self.assertEqual(inboxes.poll(s, c, datetime(2030, 1, 1)), 0)              # ...and it is handed over once
        r = dict(s.cx.execute("SELECT * FROM message WHERE Channel='line'").fetchone())
        self.assertEqual((r['FromName'], r['ConversationId']), ('Pat Buyer', 'line:U9'))
        self.assertFalse(senders.known(s, {'channel': 'line', 'from_name': r['FromName'], 'source_name': r['SourceName'],
                                           'mail_meta': json.loads(r['MailMetaJson'] or '{}')})[0])

    def test_sendgrid_needs_the_cards_key_and_files_the_mail(self):
        s = MemoryStore(); cid = card(s, 'sendgrid', 'SG.key')
        path = pushin.path(s, s.get_connector(cid, with_secret=True))
        key = path.rsplit('/', 1)[-1]
        form = {'from': 'Erin Blake <erin@vendor.example>', 'to': 'tasks@inbound.northwind.example', 'subject': 'Invoice 42',
                'text': 'Attached is March.', 'headers': 'Message-ID: <m42@vendor.example>\nSubject: Invoice 42'}
        with self.assertRaises(pushin.Refused): pushin.take(s, 'sendgrid', cid, 'wrong', {}, b'', form)
        self.assertEqual(pushin.take(s, 'sendgrid', cid, key, {}, b'', form), 1)
        from datetime import datetime
        self.assertEqual(inboxes.poll(s, s.get_connector(cid, with_secret=True), datetime(2030, 1, 1)), 1)
        r = dict(s.cx.execute("SELECT * FROM message WHERE Channel='sendgrid'").fetchone())
        self.assertEqual((r['Subject'], r['FromEmail']), ('Invoice 42', 'erin@vendor.example'))


if __name__ == '__main__':
    unittest.main()
