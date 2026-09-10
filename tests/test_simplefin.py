"""SimpleFIN: the bank and card feed anyone can sign up for. Mocked at the HTTP edge; what is under
test is the shape - the one-shot claim, credentials that ride as auth rather than in a logged URL,
ONE cached call behind four tools, the daily budget that keeps the owner's token alive, the
protocol's sign convention, and the ladder (reads only, because the protocol has no writes)."""
import base64
import json
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import scopes, server, simplefin
from taskuary.store import MemoryStore

c = TestClient(server.app)
ACCESS = 'https://user1:pass1@bridge.simplefin.org/simplefin'
TOKEN = base64.b64encode(b'https://bridge.simplefin.org/simplefin/claim/abc123').decode()

# what the Bridge actually answers with (version 1.0): accounts carry their balance AND their
# transactions, `org` names the bank, and there is no account type or last four anywhere
PAYLOAD = {'errors': [], 'accounts': [
    {'id': 'ACT-1', 'name': 'Platinum Card', 'org': {'name': 'Amex', 'domain': 'americanexpress.com'},
     'currency': 'USD', 'balance': '-1240.55', 'available-balance': '8759.45', 'balance-date': 1789000000,
     'transactions': [{'id': 'T1', 'posted': 1788950000, 'amount': '-120.00', 'description': 'HARDWARE STORE'},
                      {'id': 'T2', 'posted': 1788940000, 'amount': '-40.50', 'description': 'COFFEE', 'pending': True},
                      {'id': 'T3', 'posted': 1788930000, 'amount': '500.00', 'description': 'PAYMENT THANK YOU'}]},
    {'id': 'ACT-2', 'name': 'Operating', 'org': {'name': 'CFG Bank'}, 'currency': 'USD',
     'balance': '42000.00', 'available-balance': '41500.00', 'balance-date': 1789000000,
     'transactions': [{'id': 'T4', 'posted': 1788900000, 'amount': '-9.99', 'description': 'SAAS'}]}]}


def _resp(status, body, text=None):
    r = mock.Mock(); r.status_code = status
    r.text = text if text is not None else json.dumps(body)
    r.json = lambda: (body if body is not None else (_ for _ in ()).throw(ValueError('no json')))
    return r


def _card(store, **conf):
    card = store.get_connector_by_type('simplefin')
    store.save_connector({'ConnectorId': card['ConnectorId'], 'Active': 1, 'Secret': ACCESS,
                          'ConfigJson': json.dumps(conf)}, 'owner')
    return card['ConnectorId']


class Setup(unittest.TestCase):
    def setUp(self): simplefin.reset_budget()

    def test_the_card_is_seeded_read_only_as_a_report_and_a_tool(self):
        s = MemoryStore(); card = s.get_connector_by_type('simplefin')
        self.assertEqual(sorted(card['Roles'].split(',')), ['report', 'tool'])
        for t in ('simplefin_accounts', 'simplefin_transactions', 'simplefin_balances', 'simplefin_spend'):
            self.assertEqual(scopes.needs(t), 'read', t)
            self.assertTrue(scopes.allows(card, t), t)

    def test_every_tool_resolves_the_access_url_off_the_card(self):
        from taskuary import reports
        s = MemoryStore(); _card(s)
        for t in ('simplefin_accounts', 'simplefin_transactions', 'simplefin_balances', 'simplefin_spend'):
            self.assertEqual(reports.card_of(t), 'simplefin', t)
        self.assertEqual(simplefin.connection(s)['access_url'], ACCESS)

    def test_not_connected_says_paste_a_token(self):
        s = MemoryStore()
        with self.assertRaisesRegex(simplefin.SimpleFinError, 'setup token'):
            simplefin.accounts(simplefin.connection(s))

    def test_a_setup_token_is_base64_and_a_bad_one_fails_before_it_is_spent(self):
        self.assertEqual(simplefin.claim_url(TOKEN), 'https://bridge.simplefin.org/simplefin/claim/abc123')
        for bad in ('', '   ', 'not base64 at all!!', base64.b64encode(b'sftp://nope').decode()):
            with self.assertRaises(ValueError): simplefin.claim_url(bad)

    def test_claiming_posts_the_decoded_url_and_keeps_only_the_access_url(self):
        with mock.patch.object(simplefin.requests, 'post', return_value=_resp(200, None, text=ACCESS + '\n')) as p:
            self.assertEqual(simplefin.claim(TOKEN), ACCESS)
        self.assertEqual(p.call_args.args[0], 'https://bridge.simplefin.org/simplefin/claim/abc123')

    def test_a_spent_token_says_so_in_those_words(self):
        for r in (_resp(403, None, text='Forbidden (was it already claimed?)'),
                  _resp(200, None, text='Forbidden (was it already claimed?)')):
            with mock.patch.object(simplefin.requests, 'post', return_value=r):
                with self.assertRaisesRegex(simplefin.SimpleFinError, 'already claimed'): simplefin.claim(TOKEN)

    def test_the_credentials_ride_as_auth_and_never_in_the_url(self):
        s = MemoryStore(); _card(s)
        with mock.patch.object(simplefin.requests, 'get', return_value=_resp(200, PAYLOAD)) as g:
            simplefin.accounts(simplefin.connection(s))
        self.assertEqual(g.call_args.kwargs['auth'], ('user1', 'pass1'))
        self.assertEqual(g.call_args.args[0], 'https://bridge.simplefin.org/simplefin/accounts')
        self.assertNotIn('pass1', g.call_args.args[0])


class OneCall(unittest.TestCase):
    """The Bridge allows 24 reads a day and disables a token that overruns, so the four tools share
    one response and the module refuses before the Bridge does."""

    def setUp(self): simplefin.reset_budget()

    def test_four_reads_over_the_same_window_make_one_http_call(self):
        s = MemoryStore(); _card(s); cfg = simplefin.connection(s)
        with mock.patch.object(simplefin.requests, 'get', return_value=_resp(200, PAYLOAD)) as g:
            simplefin.transactions(cfg, days=30)
            simplefin.transactions(cfg, days=30)
            simplefin.spend(cfg, days=0)
        self.assertEqual(g.call_count, 2)      # the 30-day window, and spend's own 1-day one
        self.assertEqual(simplefin.budget()['used'], 2)

    def test_the_day_budget_refuses_rather_than_getting_the_token_disabled(self):
        s = MemoryStore(); _card(s); cfg = simplefin.connection(s)
        with mock.patch.object(simplefin.requests, 'get', return_value=_resp(200, PAYLOAD)):
            for i in range(simplefin.DAY_BUDGET): simplefin.fetch(cfg, days=i + 1)
            with self.assertRaisesRegex(simplefin.SimpleFinError, '24 reads a day'):
                simplefin.fetch(cfg, days=simplefin.DAY_BUDGET + 1)

    def test_the_window_is_clamped_to_the_bridges_ninety_days(self):
        s = MemoryStore(); _card(s)
        with mock.patch.object(simplefin.requests, 'get', return_value=_resp(200, PAYLOAD)) as g:
            simplefin.fetch(simplefin.connection(s), days=900)
        sent = dict(g.call_args.kwargs['params'])
        self.assertIn('start-date', sent)
        self.assertEqual(sent['pending'], '1')                 # a daily feed that hid today would be useless

    def test_a_balances_only_read_asks_for_no_transactions(self):
        s = MemoryStore(); _card(s)
        with mock.patch.object(simplefin.requests, 'get', return_value=_resp(200, PAYLOAD)) as g:
            simplefin.accounts(simplefin.connection(s))
        self.assertEqual(dict(g.call_args.kwargs['params'])['balances-only'], '1')

    def test_what_the_bridge_refuses_is_said_in_words(self):
        s = MemoryStore(); _card(s); cfg = simplefin.connection(s)
        for status, phrase in ((403, 'fresh setup token'), (402, 'subscription lapsed'), (500, 'SimpleFIN 500')):
            simplefin.reset_budget()
            with mock.patch.object(simplefin.requests, 'get', return_value=_resp(status, None, text='no')):
                with self.assertRaisesRegex(simplefin.SimpleFinError, phrase): simplefin.fetch(cfg)


class Rows(unittest.TestCase):
    def setUp(self): simplefin.reset_budget()

    def _cfg(self):
        s = MemoryStore(); _card(s); return simplefin.connection(s)

    def test_the_protocols_sign_is_read_for_you_and_pending_is_flagged(self):
        with mock.patch.object(simplefin.requests, 'get', return_value=_resp(200, PAYLOAD)):
            rows = simplefin.transactions(self._cfg(), days=30)
        by = {r['id']: r for r in rows}
        self.assertEqual(by['T1']['direction'], 'spend')       # negative is money out, whatever the account is
        self.assertEqual(by['T3']['direction'], 'inflow')      # paying the card off is not negative spending
        self.assertTrue(by['T2']['pending'])
        self.assertFalse(by['T1']['pending'])
        self.assertEqual(by['T1']['date'][:2], '20')           # an epoch became a date
        self.assertEqual(by['T1']['account'], 'Platinum Card')
        self.assertEqual(by['T1']['org'], 'Amex')
        self.assertEqual([r['id'] for r in rows][0], 'T1')     # newest first

    def test_an_account_is_picked_by_name_or_bank_and_ambiguity_is_refused(self):
        cfg = self._cfg()
        with mock.patch.object(simplefin.requests, 'get', return_value=_resp(200, PAYLOAD)):
            self.assertEqual([r['id'] for r in simplefin.transactions(cfg, 'operating')], ['T4'])
            self.assertEqual([r['id'] for r in simplefin.transactions(cfg, 'ACT-1')], ['T1', 'T2', 'T3'])
            with self.assertRaisesRegex(simplefin.SimpleFinError, 'no account matching'):
                simplefin.transactions(cfg, 'Chase')
        rows = [{'id': 'a', 'name': 'Card one', 'org': 'Amex'}, {'id': 'b', 'name': 'Card two', 'org': 'Amex'}]
        with self.assertRaisesRegex(simplefin.SimpleFinError, 'matches 2 accounts'): simplefin.pick(rows, 'card')

    def test_balances_carry_the_as_of_date_because_the_feed_is_daily(self):
        with mock.patch.object(simplefin.requests, 'get', return_value=_resp(200, PAYLOAD)):
            rows = simplefin.balances(self._cfg())
        self.assertEqual([r['account'] for r in rows], ['Platinum Card', 'Operating'])
        self.assertEqual(rows[0]['balance'], '-1240.55')
        self.assertEqual(rows[0]['available'], '8759.45')
        self.assertTrue(rows[0]['as_of'].startswith('20'))

    def test_spend_totals_per_account_and_never_nets_the_inflow(self):
        with mock.patch.object(simplefin.requests, 'get', return_value=_resp(200, PAYLOAD)):
            rows = simplefin.spend(self._cfg(), days=3650)     # everything the fixture has
        total = rows[-1]
        self.assertEqual(total['account'], 'TOTAL')
        self.assertEqual(total['spend'], 170.49)               # 120.00 + 40.50 + 9.99
        self.assertEqual(total['inflow'], 500.0)               # counted, never subtracted
        self.assertEqual(total['charges'], 3)
        self.assertEqual(rows[0]['account'], 'Platinum Card')  # biggest spender first
        self.assertEqual(rows[0]['largest'], 120.0)

    def test_the_spend_headline_leads_with_the_total_so_an_alert_compares_dollars(self):
        from taskuary import reports
        with mock.patch.object(simplefin.requests, 'get', return_value=_resp(200, PAYLOAD)):
            head, body = simplefin.run_simplefin_spend({**self._cfg(), 'days': 3650})
        self.assertTrue(head.startswith('170.49 spent '), head)
        self.assertEqual(reports.result_count(head, body), 170)   # dollars, not rows
        self.assertIn('TOTAL', body)

    def test_a_bank_that_needs_reauthorising_is_a_200_with_a_sentence_so_test_says_it(self):
        payload = {**PAYLOAD, 'errors': ['Connection to Amex may need attention']}
        with mock.patch.object(simplefin.requests, 'get', return_value=_resp(200, payload)):
            said = simplefin.probe(self._cfg())
        self.assertIn('may need attention', said)
        self.assertIn('Amex', said)
        # the v2 spec moved them to `errlist` as objects; both are read
        self.assertEqual(simplefin.errors_of({'errlist': [{'code': 'con.auth', 'msg': 'Auth failed for My Bank'}]}),
                         ['Auth failed for My Bank'])

    def test_a_token_with_no_accounts_says_link_a_bank(self):
        with mock.patch.object(simplefin.requests, 'get', return_value=_resp(200, {'errors': [], 'accounts': []})):
            self.assertIn('link a bank', simplefin.probe(self._cfg()))

    def test_something_that_is_not_an_account_set_is_refused(self):
        with mock.patch.object(simplefin.requests, 'get', return_value=_resp(200, {'hello': 'world'})):
            with self.assertRaisesRegex(simplefin.SimpleFinError, 'no account list'): simplefin.fetch(self._cfg())


class Endpoints(unittest.TestCase):
    def setUp(self):
        simplefin.reset_budget()
        server.store = MemoryStore()
        self.cid = server.store.get_connector_by_type('simplefin')['ConnectorId']

    def test_status_needs_nothing_saved_first(self):
        r = c.get(f'/api/connectors/{self.cid}/simplefin/status')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()['has_app'])                   # no application id, no certificate
        self.assertFalse(r.json()['connected'])
        self.assertEqual(r.json()['bridge'], simplefin.BRIDGE)

    def test_claiming_stores_the_access_url_write_only(self):
        with mock.patch.object(simplefin.requests, 'post', return_value=_resp(200, None, text=ACCESS)):
            r = c.post(f'/api/connectors/{self.cid}/simplefin/claim', json={'setup_token': TOKEN})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(c.get(f'/api/connectors/{self.cid}/simplefin/status').json()['connected'])
        shown = c.get('/api/connectors').json()['data']
        row = [x for x in shown if x['ConnectorId'] == self.cid][0]
        self.assertNotIn('pass1', json.dumps(row))             # the URL carries a password: it stays in
        self.assertEqual(simplefin.connection(server.store)['access_url'], ACCESS)

    def test_a_token_that_cannot_decode_is_refused_before_it_is_spent(self):
        with mock.patch.object(simplefin.requests, 'post') as p:
            r = c.post(f'/api/connectors/{self.cid}/simplefin/claim', json={'setup_token': 'nonsense!!'})
        self.assertEqual(r.status_code, 422, r.text)
        p.assert_not_called()                                  # a claim is one-shot; do not waste it

    def test_a_spent_token_is_a_422_that_says_generate_a_new_one(self):
        with mock.patch.object(simplefin.requests, 'post', return_value=_resp(403, None, text='Forbidden')):
            r = c.post(f'/api/connectors/{self.cid}/simplefin/claim', json={'setup_token': TOKEN})
        self.assertEqual(r.status_code, 422)
        self.assertIn('already claimed', r.json()['detail'])

    def test_the_endpoints_refuse_a_card_of_another_type(self):
        other = server.store.get_connector_by_type('teller')['ConnectorId']
        self.assertEqual(c.get(f'/api/connectors/{other}/simplefin/status').status_code, 404)
        self.assertEqual(c.post(f'/api/connectors/{other}/simplefin/claim', json={'setup_token': TOKEN}).status_code, 404)

    def test_an_agent_may_not_claim_a_token(self):
        from taskuary import guard
        self.assertTrue(guard.denied('POST', f'/api/connectors/{self.cid}/simplefin/claim'))
