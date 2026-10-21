"""Connecting LinkedIn from its card, end to end, against a fake LinkedIn.

The owner pasted the app's keys, saw only "Get AI to set it up" do anything, and said "LinkedIn is not
working" (2026-10-21). The road a person takes is three presses - Save the app's keys, Sign in with
LinkedIn, Test - and each has to say plainly what happened. Nothing here reaches linkedin.com: the
token endpoint and the userinfo endpoint are stood in for at `linkedin.requests`.
"""
import json
import time
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from taskuary import linkedin


class _Resp:
    def __init__(self, payload=None, status=200):
        self._payload, self.status_code, self.text = payload, status, json.dumps(payload or {})
        self.ok, self.headers = status < 400, {}
    def json(self): return self._payload


class FakeLinkedIn:
    """The two endpoints a sign-in and a Test touch, keyed by the token each member holds."""
    def __init__(self, members):
        self.members, self.codes, self.seen = members, {'code-1': 'AQ-one', 'code-2': 'AQ-two'}, []
    def post(self, url, data=None, **kw):
        self.seen.append(('POST', url))
        assert url == linkedin.AUTH + '/accessToken', url
        tok = self.codes.get(data.get('code'))
        if not tok or data.get('client_secret') != 'app-secret':
            return _Resp({'error': 'invalid_request', 'error_description': 'Unable to retrieve access token'}, 400)
        return _Resp({'access_token': tok, 'expires_in': 5184000})
    def get(self, url, headers=None, **kw):
        self.seen.append(('GET', url))
        assert url == linkedin.API + '/v2/userinfo', url
        me = self.members.get(headers['Authorization'].removeprefix('Bearer '))
        return _Resp(me) if me else _Resp({'message': 'Invalid access token'}, 401)


class ConnectingFromTheCard(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        self.server, self.client = server, TestClient(server.app)
        self.cid = server.store.get_connector_by_type('linkedin')['ConnectorId']
        server.store.save_connector({'ConnectorId': self.cid, 'ConfigJson': '{}', 'Secret': ''}, 'test')
        self.fake = FakeLinkedIn({'AQ-one': {'sub': 'abc123', 'name': 'Alex Doyle', 'email': 'alex@northwind.example'},
                                  'AQ-two': {'sub': 'def456', 'name': 'Erin Blake', 'email': 'erin@northwind.example'}})
        p = mock.patch.multiple(linkedin.requests, post=self.fake.post, get=self.fake.get)
        p.start(); self.addCleanup(p.stop)

    def save_keys(self, cid):
        r = self.client.post('/api/connectors', json={'ConnectorId': cid, 'Active': True,
                             'ConfigJson': json.dumps({'client_id': 'app-id', 'client_secret': 'app-secret'})})
        self.assertEqual(r.status_code, 200, r.text)

    def sign_in(self, cid, code):
        url = self.client.get(f'/api/connectors/{cid}/linkedin/authorize').json()['url']
        q = parse_qs(urlsplit(url).query)
        self.assertEqual(q['client_id'], ['app-id'])
        return self.client.get('/api/linkedin/callback', params={'code': code, 'state': q['state'][0]})

    def test_save_sign_in_test_is_the_whole_road(self):
        st = self.client.get(f'/api/connectors/{self.cid}/linkedin/status').json()
        self.assertEqual((st['has_app'], st['connected']), (False, False))
        self.save_keys(self.cid)
        self.assertTrue(self.client.get(f'/api/connectors/{self.cid}/linkedin/status').json()['has_app'])
        page = self.sign_in(self.cid, 'code-1')
        self.assertIn('Alex Doyle is connected', page.text)
        st = self.client.get(f'/api/connectors/{self.cid}/linkedin/status').json()
        self.assertTrue(st['connected'])
        self.assertEqual(st['member'], 'Alex Doyle')
        self.assertIn(st['days_left'], (59, 60))
        out = self.client.post(f'/api/connectors/{self.cid}/test').json()
        self.assertTrue(out['ok'], out)
        # the member, said - not "LinkedIn answered: rows", which is what unpacking the result dict printed
        self.assertIn('signed in as Alex Doyle (alex@northwind.example)', out['detail'])
        self.assertIn('more days', out['detail'])
        self.assertNotIn('rows', out['detail'])

    def test_a_card_never_signed_in_says_to_press_sign_in(self):
        self.save_keys(self.cid)
        out = self.client.post(f'/api/connectors/{self.cid}/test').json()
        self.assertFalse(out['ok'])
        self.assertIn('Sign in with LinkedIn', out['detail'])
        self.assertFalse([s for s in self.fake.seen if s[0] == 'GET'], 'no call goes out without a token')

    def test_a_token_linkedin_refuses_is_said_with_its_fix(self):
        self.server.store.save_connector({'ConnectorId': self.cid, 'Secret': 'AQ-stale'}, 'test')
        out = self.client.post(f'/api/connectors/{self.cid}/test').json()
        self.assertFalse(out['ok'])
        self.assertIn('Invalid access token', out['detail'])

    def test_the_wrong_secret_is_refused_on_the_sign_in_page_and_nothing_is_stored(self):
        self.client.post('/api/connectors', json={'ConnectorId': self.cid,
                         'ConfigJson': json.dumps({'client_id': 'app-id', 'client_secret': 'typo'})})
        page = self.sign_in(self.cid, 'code-1')
        self.assertIn('Not connected', page.text)
        self.assertIn('Unable to retrieve access token', page.text)
        self.assertFalse(self.client.get(f'/api/connectors/{self.cid}/linkedin/status').json()['connected'])

    def test_a_second_card_tests_its_own_member(self):
        """Test resolved the first LinkedIn card whichever one it was pressed on."""
        self.save_keys(self.cid); self.sign_in(self.cid, 'code-1')
        two = self.client.post('/api/connectors', json={'Type': 'linkedin', 'Name': 'LinkedIn - second'}).json()['connectorId']
        self.save_keys(two); self.sign_in(two, 'code-2')
        self.assertIn('Erin Blake', self.client.post(f'/api/connectors/{two}/test').json()['detail'])
        self.assertIn('Alex Doyle', self.client.post(f'/api/connectors/{self.cid}/test').json()['detail'])



class SecretsAreWriteOnly(unittest.TestCase):
    """The owner, 2026-10-21: an app's client secret is typed like any field, then never sent back -
    replaceable, not readable - and the server goes on spending the stored one."""
    def setUp(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        self.server, self.client = server, TestClient(server.app)

    def row(self, cid):
        return next(c for c in self.client.get('/api/connectors').json()['data'] if c['ConnectorId'] == cid)

    def test_each_app_card_holds_its_secret_back_and_keeps_it_across_a_save(self):
        for typ in ('linkedin', 'quickbooks', 'zoho_invoice'):
            with self.subTest(typ):
                cid = self.server.store.get_connector_by_type(typ)['ConnectorId']
                self.client.post('/api/connectors', json={'ConnectorId': cid,
                                 'ConfigJson': json.dumps({'client_id': 'app-id', 'client_secret': 'app-secret'})})
                r = self.row(cid)
                self.assertNotIn('app-secret', json.dumps(r))
                self.assertEqual(json.loads(r['ConfigJson'])['client_id'], 'app-id')
                self.assertIn('client_secret', r['WriteOnlyKeys'])
                self.assertIn('client_secret', r['ConfigSaved'])
                # the card saves what it was sent - no secret - and the stored one stays
                self.client.post('/api/connectors', json={'ConnectorId': cid, 'ConfigJson': json.dumps({'client_id': 'app-id-2'})})
                stored = json.loads(self.server.store.get_connector(cid)['ConfigJson'])
                self.assertEqual((stored['client_id'], stored['client_secret']), ('app-id-2', 'app-secret'))
                # typed, it replaces
                self.client.post('/api/connectors', json={'ConnectorId': cid,
                                 'ConfigJson': json.dumps({'client_id': 'app-id-2', 'client_secret': 'new-secret'})})
                self.assertEqual(json.loads(self.server.store.get_connector(cid)['ConfigJson'])['client_secret'], 'new-secret')

    def test_linkedins_refresh_token_is_held_back_too_and_the_status_still_sees_the_app(self):
        cid = self.server.store.get_connector_by_type('linkedin')['ConnectorId']
        self.server.store.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps(
            {'client_id': 'a', 'client_secret': 'b', 'refresh_token': 'r-1', 'member_name': 'Alex Doyle'})}, 'test')
        r = self.row(cid)
        self.assertNotIn('r-1', r['ConfigJson'])
        self.assertEqual(json.loads(r['ConfigJson'])['member_name'], 'Alex Doyle')
        self.assertTrue(self.client.get(f'/api/connectors/{cid}/linkedin/status').json()['has_app'])

    def test_other_cards_are_unchanged(self):
        r = self.row(self.server.store.get_connector_by_type('exa')['ConnectorId'])
        self.assertNotIn('WriteOnlyKeys', r)

if __name__ == '__main__':
    unittest.main()
