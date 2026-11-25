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

from taskuary import config, guard, quickbooks as qb, scopes, server
from taskuary.store import MemoryStore

c = TestClient(server.app)
AGENT = {'X-Taskuary-Token': config.load()['server']['agent_token'],          # ...a session's call, proving the task it is on (guard.unproven)
         guard.TASK_HDR: guard.task_proof(config.load()['server'], 999995)}


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
        self.assertEqual(scopes.scope_of(card), scopes.FULL)  # every connection starts at full; read is the owner's narrowing (2026-10-05)
        card = {**card, 'Scope': 'read'}
        self.assertTrue(scopes.allows(card, 'quickbooks'))
        self.assertTrue(scopes.allows(card, 'quickbooks_vendors'))
        self.assertFalse(scopes.allows(card, 'quickbooks_bill'), 'posting a bill is a write; at read it is refused')

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

    def test_the_chart_of_accounts_is_not_filtered_by_its_own_tool_name(self):
        """`type` names the tool on every run (tools/run, a report): run_quickbooks_accounts read it as the AccountType too, so every call
        asked for accounts of type 'quickbooks_accounts' and came back empty. The kind is `account_type`; none is every active account."""
        from taskuary.reports import REGISTRY
        seen = []
        def fake(method, url, **kw):
            seen.append(kw['params']['query'])
            return _resp(200, {'QueryResponse': {'Account': [{'Id': '80', 'Name': 'Office Supplies', 'AccountType': 'Expense'}]}})
        with mock.patch.object(qb.requests, 'request', side_effect=fake):
            head, _ = REGISTRY['quickbooks_accounts']({**self.cfg, 'type': 'quickbooks_accounts'})
            REGISTRY['quickbooks_accounts']({**self.cfg, 'type': 'quickbooks_accounts', 'account_type': 'Expense'})
        self.assertIn('WHERE Active = true', seen[0]); self.assertNotIn('quickbooks_accounts', seen[0])
        self.assertIn("AccountType = 'Expense'", seen[1])

    def test_a_bill_posts_to_a_vendor_that_exists_and_never_invents_one(self):
        def fake(method, url, **kw):
            q = (kw.get('params') or {}).get('query', '')
            if 'FROM Vendor WHERE DisplayName = \'Acme Supply\'' in q: return _resp(200, {'QueryResponse': {'Vendor': [{'Id': '55', 'DisplayName': 'Acme Supply'}]}})
            if 'FROM Vendor WHERE DisplayName = \'Nobody\'' in q: return _resp(200, {'QueryResponse': {}})
            if 'FROM Vendor WHERE DisplayName LIKE' in q: return _resp(200, {'QueryResponse': {'Vendor': [{'Id': '9', 'DisplayName': 'Nobody Inc'}]}})
            if 'FROM Account WHERE Name = \'Office Supplies\'' in q: return _resp(200, {'QueryResponse': {'Account': [{'Id': '80', 'Name': 'Office Supplies'}]}})
            if 'FROM Bill WHERE DocNumber' in q: return _resp(200, {'QueryResponse': {}})
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

    def test_a_bills_card_names_the_vendor_and_account_and_one_the_books_do_not_have_is_never_raised(self):
        """Walk 22, 2026-11-25: the approval card for a bill read "vendor id: 58 / account id: 7 / amount: 120" - nothing he could check. A write
        is read against its system as its card is raised (reports.CHECKS): each thing it names stands by NAME, its id kept as what runs; a
        vendor the books do not have is answered to the agent with why, and no card stands. Books that cannot be reached refuse nothing."""
        from taskuary import proposals
        s = self.s; tid = s.create_task({'Title': 'Post the Payworth bill', 'Kind': 'general', 'Status': 'open'}, 'owner')
        def fake(method, url, **kw):
            q = (kw.get('params') or {}).get('query', '')
            if "FROM Vendor WHERE Id = '58'" in q: return _resp(200, {'QueryResponse': {'Vendor': [{'Id': '58', 'DisplayName': 'Payworth'}]}})
            if "FROM Vendor WHERE Id = '99'" in q: return _resp(200, {'QueryResponse': {}})
            if "FROM Account WHERE Name = 'Software subscriptions'" in q: return _resp(200, {'QueryResponse': {'Account': [{'Id': '7', 'Name': 'Software subscriptions'}]}})
            raise AssertionError(f'unexpected call {method} {url} {q}')
        bill = {'action': 'run_tool', 'type': 'quickbooks_bill', 'vendor_id': 58, 'account': 'Software subscriptions', 'amount': 120}
        with mock.patch.object(qb.requests, 'request', side_effect=fake), mock.patch.object(qb, 'token', return_value='at'):
            why = []; made = proposals.queue(s, tid, bill, refused=why); self.assertTrue(made, why)
            p = json.loads(s.get_review(made['reviewId'])['DraftText'])
            self.assertEqual((p['vendor'], p['vendor_id'], p['account'], p['account_id'], p['amount']), ('Payworth', '58', 'Software subscriptions', '7', 120.0))
            no = []
            self.assertIsNone(proposals.queue(s, tid, {**bill, 'vendor_id': 99, 'memo': 'another'}, refused=no))
            self.assertIn('no vendor with id 99', no[0])
        with mock.patch.object(qb, 'token', side_effect=qb.QuickBooksError('QuickBooks refused the token (401)')):
            self.assertTrue(proposals.queue(s, tid, {**bill, 'memo': 'while the books are away'}), 'not reached is not refused')

    def test_a_bill_already_posted_under_the_doc_number_is_not_posted_again(self):
        """A timeout after Intuit committed, then a re-approval, used to book the bill twice (audit 2026-09-02)."""
        def fake(method, url, **kw):
            q = (kw.get('params') or {}).get('query', '')
            if 'FROM Vendor WHERE DisplayName' in q: return _resp(200, {'QueryResponse': {'Vendor': [{'Id': '55', 'DisplayName': 'Acme Supply'}]}})
            if 'FROM Account WHERE Name' in q: return _resp(200, {'QueryResponse': {'Account': [{'Id': '80', 'Name': 'Office Supplies'}]}})
            if 'FROM Bill WHERE DocNumber = \'88213\'' in q:
                return _resp(200, {'QueryResponse': {'Bill': [{'Id': '301', 'DocNumber': '88213', 'TotalAmt': 412.5, 'VendorRef': {'name': 'Acme Supply'}, 'TxnDate': '2026-09-01'}]}})
            raise AssertionError(f'unexpected call {method} {url} {q}')     # in particular: no POST
        with mock.patch.object(qb.requests, 'request', side_effect=fake):
            out = qb.create_bill(self.cfg, 'Acme Supply', '412.50', 'Office Supplies', '2026-09-01', 'card txn 88213', '88213')
        self.assertEqual((out['id'], out['existing']), ('301', True))


class TheLadder(unittest.TestCase):
    """An agent reads the books through /api/tools/run and is refused the writes - which is what
    turns a bill into a proposal for Review."""

    def test_reads_pass_and_writes_are_refused_at_the_default_scope(self):
        s = server.store; _card(s); qb._TOK['123'] = ('at', 9e12)
        s.save_connector({'ConnectorId': s.get_connector_by_type('quickbooks')['ConnectorId'], 'Scope': 'read'}, 't')  # every connection starts at full; read is the owner's narrowing (2026-10-05)
        body = {'QueryResponse': {'Vendor': [{'Id': '1', 'DisplayName': 'Acme'}]}}
        with mock.patch.object(qb.requests, 'request', return_value=_resp(200, body)):
            r = c.post('/api/tools/run', json={'type': 'quickbooks_vendors', 'name': 'ac'}, headers=AGENT)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn('Acme', r.text)
        # ...and a bill past the card's Authority waits for the owner's press on a task: with none named, the refusal says how to name it
        r = c.post('/api/tools/run', json={'type': 'quickbooks_bill', 'vendor': 'Acme', 'amount': 5, 'account': 'x'}, headers=AGENT)
        self.assertEqual(r.status_code, 422, r.text)
        self.assertIn('write', r.text); self.assertIn('task_id', r.text)

    def test_the_status_route_hands_the_card_its_redirect_uri(self):
        s = server.store; card = _card(s)
        r = c.get(f"/api/connectors/{card['ConnectorId']}/quickbooks/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['redirect_uri'].endswith('/api/quickbooks/callback'))
        self.assertTrue(r.json()['connected'])
        # a callback nobody started is refused, whatever it carries
        r = c.get('/api/quickbooks/callback', params={'code': 'x', 'state': f"tq-{card['ConnectorId']}-nonce", 'realmId': '123'})
        self.assertIn('not one Taskuary issued', r.text)

    def test_an_agent_is_never_handed_a_connect_link(self):
        """Red team F6: authorize was a GET any session could read, so an agent took the state, signed in to a company of its own through its
        own browser, and the callback re-pointed the card - the owner's bills posted there. Only the owner is handed a Connect link."""
        s = server.store; card = _card(s); owner = {'X-Taskuary-Token': config.load()['server']['token']}
        for kind in ('quickbooks', 'zoho', 'linkedin'):
            cid = card['ConnectorId'] if kind == 'quickbooks' else s.get_connector_by_type('zoho_invoice' if kind == 'zoho' else kind)['ConnectorId']
            r = c.get(f'/api/connectors/{cid}/{kind}/authorize', headers=AGENT)
            self.assertEqual(r.status_code, 403, (kind, r.text)); self.assertNotIn('tq-', r.text)
        r = c.get(f"/api/connectors/{card['ConnectorId']}/quickbooks/authorize", headers=owner)
        self.assertEqual(r.status_code, 200, r.text); self.assertIn('state=tq-', r.json()['url'])
