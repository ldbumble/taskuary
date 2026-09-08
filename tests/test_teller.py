"""Teller: the bank and card feed. Mocked at the HTTP edge; what is under test is the shape - the
token as Basic auth, the certificate outside sandbox, account picking that refuses ambiguity, the
spend/inflow direction that saves everyone decoding the bank's sign, and the ladder (reads only)."""
import json
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import scopes, server, teller
from taskuary.store import MemoryStore

c = TestClient(server.app)
ACCTS = [{'id': 'acc_1', 'name': 'Platinum Card', 'type': 'credit', 'subtype': 'credit_card', 'last_four': '1234', 'institution': {'name': 'Amex'}},
         {'id': 'acc_2', 'name': 'Operating', 'type': 'depository', 'subtype': 'checking', 'last_four': '9876', 'institution': {'name': 'Amex'}}]


def _resp(status, body):
    r = mock.Mock(); r.status_code = status; r.text = json.dumps(body); r.json = lambda: body
    return r


def _card(store, env='sandbox', **conf):
    card = store.get_connector_by_type('teller')
    store.save_connector({'ConnectorId': card['ConnectorId'], 'Active': 1, 'Secret': 'test_token_abc',
                          'ConfigJson': json.dumps({'application_id': 'app_x', 'environment': env, **conf})}, 'owner')
    return card['ConnectorId']


class TheCard(unittest.TestCase):
    def test_seeded_read_only_report_and_tool(self):
        s = MemoryStore(); card = s.get_connector_by_type('teller')
        self.assertEqual(sorted(card['Roles'].split(',')), ['report', 'tool'])
        self.assertTrue(scopes.allows(card, 'teller_transactions'))
        self.assertEqual(scopes.needs('teller_transactions'), 'read')

    def test_the_token_rides_as_basic_auth_and_the_certificate_only_outside_sandbox(self):
        s = MemoryStore(); _card(s)
        with mock.patch.object(teller.requests, 'get', return_value=_resp(200, ACCTS)) as g:
            teller.accounts(teller.connection(s))
        self.assertEqual(g.call_args.kwargs['auth'], ('test_token_abc', ''))
        self.assertNotIn('cert', g.call_args.kwargs)
        _card(s, env='development')
        with self.assertRaisesRegex(teller.TellerError, 'certificate'): teller.accounts(teller.connection(s))
        _card(s, env='development', cert_path='c.pem', key_path='k.pem')
        with mock.patch.object(teller.requests, 'get', return_value=_resp(200, ACCTS)) as g:
            teller.accounts(teller.connection(s))
        self.assertEqual(g.call_args.kwargs['cert'], ('c.pem', 'k.pem'))

    def test_not_connected_says_press_connect(self):
        s = MemoryStore(); card = s.get_connector_by_type('teller')
        s.save_connector({'ConnectorId': card['ConnectorId'], 'ConfigJson': json.dumps({'application_id': 'app_x'})}, 'owner')
        with self.assertRaisesRegex(teller.TellerError, 'Connect a bank'): teller.accounts(teller.connection(s))

    def test_spend_is_a_read_on_the_teller_card_and_resolves_its_token(self):
        from taskuary import reports
        s = MemoryStore(); _card(s)
        self.assertEqual(reports.card_of('teller_spend'), 'teller')
        self.assertEqual(scopes.needs('teller_spend'), 'read')       # a rollup of a feed still moves nothing
        self.assertTrue(scopes.allows(s.get_connector_by_type('teller'), 'teller_spend'))
        self.assertIs(reports.executor_for('teller_spend'), reports.REGISTRY['teller_spend'])
        cfg = reports.resolve_cfg(s, {'type': 'teller_spend', 'days': 0})
        self.assertEqual(cfg['access_token'], 'test_token_abc')      # the card's secret, not the report's
        self.assertEqual(cfg['days'], 0)

    def test_the_agent_type_list_names_spend(self):
        from taskuary import docsync
        self.assertIn('teller_spend', ''.join(docsync.SYSTEMS_HINT) if hasattr(docsync, 'SYSTEMS_HINT') else open('taskuary/docsync.py', encoding='utf-8').read())


class TheRows(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); _card(self.s); self.cfg = teller.connection(self.s)

    def _get(self, url, **kw):
        if url.endswith('/accounts'): return _resp(200, ACCTS)
        if 'acc_1/transactions' in url:
            return _resp(200, [{'id': 't1', 'date': '2026-08-30', 'description': 'DELTA AIR', 'amount': '318.20', 'status': 'posted', 'details': {'category': 'travel', 'counterparty': {'name': 'Delta'}}},
                               {'id': 't0', 'date': '2026-01-01', 'description': 'old', 'amount': '5.00', 'status': 'posted', 'details': {}},
                               {'id': 't2', 'date': '2026-08-31', 'description': 'PAYMENT', 'amount': '-500.00', 'status': 'posted', 'details': {}}])
        if 'acc_2/transactions' in url:
            return _resp(200, [{'id': 't3', 'date': '2026-08-29', 'description': 'ACH DEBIT', 'amount': '-1200.00', 'status': 'posted', 'details': {}}])
        raise AssertionError(url)

    def test_spend_is_spend_on_a_card_and_on_a_checking_account(self):
        with mock.patch.object(teller, 'date') as d:
            d.today.return_value = __import__('datetime').date(2026, 9, 1)
            with mock.patch.object(teller.requests, 'get', side_effect=lambda url, **kw: self._get(url, **kw)):
                rows = teller.transactions(self.cfg, '', days=60)
        by = {r['id']: r for r in rows}
        self.assertEqual([r['id'] for r in rows], ['t2', 't1', 't3'])            # newest first, the old one cut
        self.assertEqual(by['t1']['direction'], 'spend'); self.assertEqual(by['t2']['direction'], 'inflow')   # a card: + is a purchase
        self.assertEqual(by['t3']['direction'], 'spend')                                                     # checking: - left the account
        self.assertEqual((by['t1']['counterparty'], by['t1']['account_last_four']), ('Delta', '1234'))

    def test_picking_an_account_by_digits_name_or_id_and_refusing_ambiguity(self):
        with mock.patch.object(teller.requests, 'get', side_effect=lambda url, **kw: self._get(url, **kw)):
            self.assertEqual(teller.pick_account(self.cfg, '1234')[0]['id'], 'acc_1')
            self.assertEqual(teller.pick_account(self.cfg, 'operating')[0]['id'], 'acc_2')
            self.assertEqual(teller.pick_account(self.cfg, 'acc_1')[0]['id'], 'acc_1')
            with self.assertRaisesRegex(teller.TellerError, 'matches 2'): teller.pick_account(self.cfg, 'amex')
            with self.assertRaisesRegex(teller.TellerError, 'this login has'): teller.pick_account(self.cfg, 'nope')


class TheRoutes(unittest.TestCase):
    def test_enroll_saves_the_token_write_only_and_names_the_bank(self):
        s = server.store; card = s.get_connector_by_type('teller')
        s.save_connector({'ConnectorId': card['ConnectorId'], 'Secret': None, 'ConfigJson': json.dumps({'application_id': 'app_x'})}, 'owner')
        r = c.get(f"/api/connectors/{card['ConnectorId']}/teller/status")
        self.assertEqual((r.json()['has_app'], r.json()['connected']), (True, False))
        r = c.post(f"/api/connectors/{card['ConnectorId']}/teller/enroll", json={'access_token': 'test_token_new', 'enrollment_id': 'enr_1', 'institution': 'Amex'})
        self.assertEqual(r.status_code, 200, r.text)
        row = s.get_connector(card['ConnectorId'], with_secret=True)
        self.assertEqual(row['Secret'], 'test_token_new')
        self.assertEqual(json.loads(row['ConfigJson'])['institution'], 'Amex')
        self.assertTrue(c.get(f"/api/connectors/{card['ConnectorId']}/teller/status").json()['connected'])
        self.assertNotIn('test_token_new', c.get('/api/connectors').text)      # write-only means write-only


class TheSpendRollup(TheRows):
    """The one question the rows could not answer: how much, across which cards. Summed here,
    because a total added up by a language model is a total nobody can check."""

    def _spend(self, days=3):
        with mock.patch.object(teller, 'date') as d:
            d.today.return_value = __import__('datetime').date(2026, 9, 1)
            with mock.patch.object(teller.requests, 'get', side_effect=lambda url, **kw: self._get(url, **kw)):
                return teller.spend(self.cfg, '', days)

    def test_spend_is_per_account_biggest_first_with_a_total_and_inflow_kept_apart(self):
        rows = self._spend()
        self.assertEqual([r['account'] for r in rows], ['Operating', 'Platinum Card', 'TOTAL'])  # biggest spender first
        op, card, tot = rows
        self.assertEqual((op['charges'], op['spend'], op['largest']), (1, 1200.0, 1200.0))
        self.assertEqual((card['charges'], card['spend'], card['largest']), (1, 318.2, 318.2))
        self.assertEqual(card['inflow'], 500.0)              # the payment is not negative spend
        self.assertEqual((tot['charges'], tot['spend'], tot['largest'], tot['inflow']), (2, 1518.2, 1200.0, 500.0))

    def test_the_window_is_inclusive_and_the_old_row_is_out(self):
        self.assertEqual(self._spend(days=0)[-1]['spend'], 0.0)     # nothing posted on 2026-09-01 itself
        self.assertEqual(self._spend(days=3)[-1]['charges'], 2)     # 08-29 .. 09-01, and the 01-01 row cut

    def test_the_headline_leads_with_the_total_so_a_dollar_threshold_works(self):
        from taskuary.reports import alert_fires, result_count
        with mock.patch.object(teller, 'date') as d:
            d.today.return_value = __import__('datetime').date(2026, 9, 1)
            with mock.patch.object(teller.requests, 'get', side_effect=lambda url, **kw: self._get(url, **kw)):
                head, body = teller.run_teller_spend({**self.cfg, 'days': 3})
        self.assertTrue(head.startswith('1,518.20 spent '), head)
        self.assertEqual(result_count(head, body), 1518)            # dollars, not rows - commas stripped
        cfg = {'alert': {'when': 'more_than', 'count': 500, 'to': 'me@example.com'}}
        self.assertIn('more than the 500', alert_fires(cfg, head, body))
        self.assertEqual(alert_fires({'alert': {'when': 'more_than', 'count': 5000, 'to': 'me@example.com'}}, head, body), '')

    def test_every_account_row_is_json_on_its_own_line(self):
        with mock.patch.object(teller, 'date') as d:
            d.today.return_value = __import__('datetime').date(2026, 9, 1)
            with mock.patch.object(teller.requests, 'get', side_effect=lambda url, **kw: self._get(url, **kw)):
                _, body = teller.run_teller_spend({**self.cfg, 'days': 3})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual(rows[-1]['account'], 'TOTAL')
        self.assertEqual(len(rows), 3)


class TheSpendReport(unittest.TestCase):
    """The pipeline, not the function: a saved report config, resolved credentials, and the alert
    rule the owner would actually write."""

    def setUp(self):
        self.s = MemoryStore(); _card(self.s)

    def _run(self, cfg):
        from taskuary import reports
        rows = TheRows(); rows.s = self.s; rows.cfg = teller.connection(self.s)
        with mock.patch.object(teller, 'date') as d:
            d.today.return_value = __import__('datetime').date(2026, 9, 1)
            with mock.patch.object(teller.requests, 'get', side_effect=lambda url, **kw: rows._get(url, **kw)):
                return reports.render_report(self.s, reports.resolve_cfg(self.s, cfg))

    def test_a_saved_report_needs_only_the_window_and_gets_the_token_from_the_card(self):
        head, body = self._run({'type': 'teller_spend', 'title': 'Card spend today', 'days': 3})
        self.assertTrue(head.startswith('1,518.20 spent '), head)
        self.assertIn('"account": "TOTAL"', body.replace("'", '"')) if '"account"' in body else self.assertIn('TOTAL', body)

    def test_the_owners_threshold_fires_on_dollars_and_stays_quiet_under_it(self):
        from taskuary.reports import alert_fires
        head, body = self._run({'type': 'teller_spend', 'days': 3})
        over = {'alert': {'when': 'more_than', 'count': 1000, 'to': '+15550000000', 'channel': 'whatsapp'}}
        under = {'alert': {'when': 'more_than', 'count': 2000, 'to': '+15550000000', 'channel': 'whatsapp'}}
        self.assertIn('more than the 1000', alert_fires(over, head, body))
        self.assertEqual(alert_fires(under, head, body), '')

    def test_a_failed_run_says_so_rather_than_reporting_zero_spend(self):
        from taskuary import reports
        s = MemoryStore()                      # no card connected: no token
        with self.assertRaisesRegex(teller.TellerError, 'Connect a bank'):
            reports.render_report(s, reports.resolve_cfg(s, {'type': 'teller_spend', 'days': 0}))
