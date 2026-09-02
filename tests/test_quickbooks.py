"""QuickBooks Online: the first Corporate system that writes - and the reasons it may not.

Intuit is mocked at the HTTP edge (requests.post / requests.request), so what is under test is the
shape that matters: the refresh token ROTATES and must be written back to the card, a bill posts to
a vendor that exists and refuses one that does not, and the scope ladder keeps quickbooks_bill off
an agent's direct road while letting the reads through.
"""
import json
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import config, quickbooks as qb, scopes, server
from taskuary.store import MemoryStore

c = TestClient(server.app)
AGENT = {'X-Taskuary-Token': config.load()['server']['agent_token']}


def _resp(status, body):
    r = mock.Mock(); r.status_code = status; r.text = json.dumps(body); r.json = lambda: body
    return r


def _card(store, **conf):
    card = store.get_connector_by_type('quickbooks')
    store.save_connector({'ConnectorId': card['ConnectorId'], 'Active': 1, 'Secret': 'rt-1',
                          'ConfigJson': json.dumps({'client_id': 'id', 'client_secret': 'sec', 'realm_id': '123', 'env': 'sandbox', **conf})}, 'owner')
    return store.get_connector(card['ConnectorId'], with_secret=True)


class TheCard(unittest.TestCase):
    def test_it_is_seeded_as_a_report_and_tool_card_at_scope_read(self):
        s = MemoryStore()
        card = s.get_connector_by_type('quickbooks')
        self.assertEqual(card['Name'], 'QuickBooks Online')
        self.assertEqual(sorted(card['Roles'].split(',')), ['report', 'tool'])
        self.assertEqual(scopes.scope_of(card), 'read')
        self.assertTrue(scopes.allows(card, 'quickbooks'))
        self.assertTrue(scopes.allows(card, 'quickbooks_vendors'))
        self.assertFalse(scopes.allows(card, 'quickbooks_bill'), 'posting a bill is a write; the card ships at read')

    def test_the_rotated_refresh_token_goes_back_on_the_card(self):
        """Intuit hands out a NEW refresh token on every refresh and kills the old one. A connector
        that kept the first would work for one hour."""
        s = MemoryStore(); _card(s)
        qb._TOK.clear()
        cfg = qb.connection(s)
        with mock.patch.object(qb.requests, 'post', return_value=_resp(200, {'access_token': 'at-1', 'refresh_token': 'rt-2', 'expires_in': 3600})) as post:
            self.assertEqual(qb.token(cfg), 'at-1')
        self.assertEqual(post.call_args.kwargs['data']['refresh_token'], 'rt-1')
        self.assertEqual(s.get_connector(cfg['_cid'], with_secret=True)['Secret'], 'rt-2')
        # the hour is not up: the second call reuses the access token, no refresh
        with mock.patch.object(qb.requests, 'post') as post2:
            self.assertEqual(qb.token(cfg), 'at-1'); post2.assert_not_called()

    def test_not_connected_says_so_instead_of_calling_intuit(self):
        s = MemoryStore(); card = s.get_connector_by_type('quickbooks')
        s.save_connector({'ConnectorId': card['ConnectorId'], 'ConfigJson': json.dumps({'client_id': 'id', 'client_secret': 'sec'})}, 'owner')
        with self.assertRaisesRegex(qb.QuickBooksError, 'Connect to QuickBooks'): qb.token(qb.connection(s))


class ReadsAndWrites(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); _card(self.s); qb._TOK['123'] = ('at', 9e12)
        self.cfg = qb.connection(self.s)

    def test_a_query_flattens_refs_into_name_and_id(self):
        body = {'QueryResponse': {'Bill': [{'Id': '7', 'TotalAmt': 412.5, 'VendorRef': {'value': '55', 'name': 'Acme'}, 'Line': [{}, {}]}]}}
        with mock.patch.object(qb.requests, 'request', return_value=_resp(200, body)) as req:
            rows = qb.query(self.cfg, 'SELECT * FROM Bill')
        self.assertEqual(rows, [{'Id': '7', 'TotalAmt': 412.5, 'VendorRef': 'Acme', 'VendorRef.id': '55', 'Line': '2 lines'}])
        self.assertIn('MAXRESULTS', req.call_args.kwargs['params']['query'])
        self.assertIn('sandbox-quickbooks', req.call_args.args[1])

    def test_a_bill_posts_to_a_vendor_that_exists_and_never_invents_one(self):
        def fake(method, url, **kw):
            q = (kw.get('params') or {}).get('query', '')
            if 'FROM Vendor WHERE DisplayName = \'Acme Supply\'' in q: return _resp(200, {'QueryResponse': {'Vendor': [{'Id': '55', 'DisplayName': 'Acme Supply'}]}})
            if 'FROM Vendor WHERE DisplayName = \'Nobody\'' in q: return _resp(200, {'QueryResponse': {}})
            if 'FROM Vendor WHERE DisplayName LIKE' in q: return _resp(200, {'QueryResponse': {'Vendor': [{'Id': '9', 'DisplayName': 'Nobody Inc'}]}})
            if 'FROM Account WHERE Name = \'Office Supplies\'' in q: return _resp(200, {'QueryResponse': {'Account': [{'Id': '80', 'Name': 'Office Supplies'}]}})
            if method == 'POST' and url.endswith('/bill'):
                sent = json.loads(kw['data'])
                self.assertEqual(sent['VendorRef']['value'], '55'); self.assertEqual(sent['Line'][0]['Amount'], 412.5)
                self.assertEqual(sent['DocNumber'], '88213')
                return _resp(200, {'Bill': {'Id': '301', 'DocNumber': '88213', 'TotalAmt': 412.5, 'VendorRef': {'name': 'Acme Supply'}, 'TxnDate': '2026-09-01'}})
            raise AssertionError(f'unexpected call {method} {url} {q}')
        with mock.patch.object(qb.requests, 'request', side_effect=fake):
            out = qb.create_bill(self.cfg, 'Acme Supply', '412.50', 'Office Supplies', '2026-09-01', 'card txn 88213', '88213')
            self.assertEqual((out['id'], out['doc_number'], out['vendor']), ('301', '88213', 'Acme Supply'))
            with self.assertRaisesRegex(qb.QuickBooksError, 'not created for you.*Nobody Inc'):
                qb.create_bill(self.cfg, 'Nobody', 10, 'Office Supplies')
        with self.assertRaisesRegex(qb.QuickBooksError, 'positive'): qb._money('-3')


class TheLadder(unittest.TestCase):
    """An agent reads the books through /api/tools/run and is refused the writes - which is what
    turns a bill into a proposal for Review."""

    def test_reads_pass_and_writes_are_refused_at_the_default_scope(self):
        s = server.store; _card(s); qb._TOK['123'] = ('at', 9e12)
        body = {'QueryResponse': {'Vendor': [{'Id': '1', 'DisplayName': 'Acme'}]}}
        with mock.patch.object(qb.requests, 'request', return_value=_resp(200, body)):
            r = c.post('/api/tools/run', json={'type': 'quickbooks_vendors', 'name': 'ac'}, headers=AGENT)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn('Acme', r.text)
        r = c.post('/api/tools/run', json={'type': 'quickbooks_bill', 'vendor': 'Acme', 'amount': 5, 'account': 'x'}, headers=AGENT)
        self.assertEqual(r.status_code, 403, r.text)
        self.assertIn('write', r.text)

    def test_the_status_route_hands_the_card_its_redirect_uri(self):
        s = server.store; card = _card(s)
        r = c.get(f"/api/connectors/{card['ConnectorId']}/quickbooks/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['redirect_uri'].endswith('/api/quickbooks/callback'))
        self.assertTrue(r.json()['connected'])
        # a callback nobody started is refused, whatever it carries
        r = c.get('/api/quickbooks/callback', params={'code': 'x', 'state': f"tq-{card['ConnectorId']}-nonce", 'realmId': '123'})
        self.assertIn('not one Taskuary issued', r.text)
