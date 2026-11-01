"""Stripe: a business's payments, mocked at the HTTP edge (no network). Under test is the shape: the key checked before any
call, Test reading the balance and naming the mode, starting_after paging to the cap, minor units turned into money, a 429
waited out, and the read-only guarantee - nothing but a GET to api.stripe.com ever leaves this card. The business and its
customers are invented."""
import json, pathlib, unittest
from unittest import mock

from taskuary import reports, scopes, stripe as st
from taskuary.store import MemoryStore

ROOT = pathlib.Path(__file__).resolve().parents[1]
CFG = {'api_key': 'rk_test_northwind'}


def _resp(status, body=None, headers=None):
    r = mock.Mock(); r.status_code, r.headers = status, headers or {}
    r.text = json.dumps(body) if body is not None else ''
    r.json = lambda: body
    return r


def _ch(i, amount=1999, currency='usd', status='succeeded', created=1761955200):
    return {'id': f'ch_{i:04d}', 'object': 'charge', 'amount': amount, 'amount_captured': amount, 'amount_refunded': 0, 'currency': currency,
            'status': status, 'paid': status == 'succeeded', 'refunded': False, 'disputed': False, 'customer': 'cus_erin', 'created': created,
            'billing_details': {'email': 'erin@northwind.example'}, 'description': 'Northwind mug', 'payment_intent': f'pi_{i:04d}'}


SUB = {'id': 'sub_1', 'object': 'subscription', 'status': 'active', 'customer': 'cus_gail', 'currency': 'usd', 'created': 1759276800,
       'current_period_end': 1764547200, 'cancel_at_period_end': False,
       'items': {'data': [{'quantity': 3, 'price': {'unit_amount': 1500, 'currency': 'usd', 'nickname': 'Team', 'product': 'prod_team',
                                                     'recurring': {'interval': 'month', 'interval_count': 1, 'usage_type': 'licensed'}}},
                          {'quantity': 1, 'price': {'unit_amount': 24000, 'currency': 'usd', 'nickname': 'Support', 'product': 'prod_sup',
                                                     'recurring': {'interval': 'year', 'interval_count': 1, 'usage_type': 'licensed'}}},
                          {'quantity': 1, 'price': {'unit_amount': None, 'currency': 'usd', 'product': 'prod_api',
                                                     'recurring': {'interval': 'month', 'usage_type': 'metered'}}}]}}


class FakeStripe:
    """Answers the GETs the card makes, records every one, and can throttle, refuse or page on request."""
    def __init__(self, charges=(), throttle=0, retry_after=None, account=True, status=200):
        self.calls, self.charges, self.throttle, self.retry_after, self.account, self.status = [], list(charges), throttle, retry_after, account, status

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(('GET', url, dict(params or {}), dict(headers or {})))
        assert headers['Authorization'] == f"Bearer {CFG['api_key']}" or headers['Authorization'].startswith('Bearer sk_')
        if self.throttle:
            self.throttle -= 1
            return _resp(429, {'error': {'message': 'Too many requests'}}, {'Retry-After': self.retry_after} if self.retry_after else {})
        if self.status != 200: return _resp(self.status, {'error': {'type': 'invalid_request_error', 'message': 'Invalid API Key provided: rk_test_****wind'}})
        path = url.split('api.stripe.com', 1)[1]
        if path == '/v1/balance':
            return _resp(200, {'object': 'balance', 'livemode': False, 'available': [{'amount': 123456, 'currency': 'usd'}, {'amount': 5000, 'currency': 'jpy'}],
                               'pending': [{'amount': 2500, 'currency': 'usd'}]})
        if path == '/v1/account':
            if not self.account: return _resp(403, {'error': {'message': 'The provided key does not have the required permissions'}})
            return _resp(200, {'id': 'acct_northwind', 'business_profile': {'name': 'Northwind'}})
        if path == '/v1/charges':
            after, lim = params.get('starting_after'), params['limit']
            i = next((n + 1 for n, c in enumerate(self.charges) if c['id'] == after), 0) if after else 0
            page = self.charges[i:i + lim]
            return _resp(200, {'object': 'list', 'data': page, 'has_more': i + lim < len(self.charges)})
        if path == '/v1/subscriptions': return _resp(200, {'object': 'list', 'data': [SUB], 'has_more': False})
        if path.startswith('/v1/'): return _resp(200, {'object': 'list', 'data': [], 'has_more': False})
        raise AssertionError(f'unexpected call {url}')

    def refuse(self, *a, **kw): raise AssertionError(f'a non-GET reached the network: {a}')

    def patch(self):
        return mock.patch.multiple(st.requests, get=self.get, post=self.refuse, put=self.refuse, delete=self.refuse, patch=self.refuse, request=self.refuse)


class Base(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(st, '_sleep', lambda s: self.slept.append(s)); p.start(); self.addCleanup(p.stop)
        self.slept = []


class Key(Base):
    def test_a_missing_publishable_or_strange_key_is_refused_before_any_call(self):
        with mock.patch.object(st.requests, 'get') as g:
            for k, said in (('', 'no Stripe key'), ('pk_live_abc', 'publishable'), ('whsec_abc', 'starts rk_live_')):
                with self.assertRaises(st.StripeError) as e: st.probe({'api_key': k})
                self.assertIn(said, str(e.exception))
        g.assert_not_called()

    def test_restricted_and_full_keys_are_both_accepted_and_the_mode_read_off_them(self):
        self.assertEqual([st.mode({'api_key': k}) for k in ('rk_test_x', 'rk_live_x', 'sk_test_x', 'sk_live_x')], ['test', 'live', 'test', 'live'])


class TestConnection(Base):
    def test_test_reads_the_balance_and_names_the_account_and_mode(self):
        f = FakeStripe()
        with f.patch(): out = st.probe(CFG)
        self.assertIn('Northwind (acct_northwind)', out); self.assertIn('TEST mode', out); self.assertIn('restricted key', out)
        self.assertIn('1,234.56 USD', out); self.assertIn('5,000 JPY', out)
        self.assertEqual(f.calls[0][1], 'https://api.stripe.com/v1/balance')

    def test_a_key_that_may_not_read_the_account_still_passes_on_the_balance(self):
        with FakeStripe(account=False).patch(): out = st.probe(CFG)
        self.assertIn('connected to the account in TEST mode', out)

    def test_a_full_secret_key_is_told_a_restricted_one_is_safer(self):
        with FakeStripe().patch(): out = st.probe({'api_key': 'sk_live_northwind'})
        self.assertIn('LIVE mode', out); self.assertIn('restricted read-only key is safer', out)

    def test_a_refused_key_is_a_plain_error(self):
        with FakeStripe(status=401).patch(), self.assertRaises(st.StripeError) as e: st.probe(CFG)
        self.assertIn('refused the key (401)', str(e.exception)); self.assertIn('Invalid API Key', str(e.exception))

    def test_a_403_names_the_missing_permission(self):
        with FakeStripe(status=403).patch(), self.assertRaises(st.StripeError) as e: st.run_stripe_payouts(CFG)
        self.assertIn('/v1/payouts (403)', str(e.exception)); self.assertIn('needs Read', str(e.exception))

    def test_the_card_test_branch_reaches_the_probe(self):
        from taskuary import channels
        s = MemoryStore(); c = s.get_connector_by_type('stripe')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Secret': CFG['api_key']}, 'owner')
        with FakeStripe().patch(): r = channels.test_connector(s, c['ConnectorId'])
        self.assertTrue(r.get('ok'), r); self.assertIn('acct_northwind', json.dumps(r))


class Paging(Base):
    def test_lists_page_with_starting_after_until_has_more_is_false(self):
        f = FakeStripe(charges=[_ch(i) for i in range(250)])
        with f.patch(): got = st.items(CFG, '/v1/charges')
        self.assertEqual(len(got), 250)
        self.assertEqual([c[2].get('starting_after') for c in f.calls], [None, 'ch_0099', 'ch_0199'])
        self.assertTrue(all(c[2]['limit'] == 100 for c in f.calls))

    def test_the_cap_stops_paging_and_the_headline_says_it_was_cut(self):
        f = FakeStripe(charges=[_ch(i) for i in range(400)])
        with f.patch(): head, body = st.run_stripe_charges({**CFG, 'max_rows': 150})
        self.assertEqual(len(f.calls), 2)                   # 151 wanted: two pages, never the third or fourth
        self.assertIn('150 rows (capped at 150', head)

    def test_the_window_is_created_gte_and_lte(self):
        f = FakeStripe()
        with f.patch(): st.run_stripe_refunds({**CFG, 'start': '2026-10-01', 'end': '2026-10-31'})
        p = f.calls[0][2]
        self.assertEqual((p['created[gte]'], p['created[lte]']), (1790812800, 1793491199))     # 2026-10-01 00:00 and 2026-10-31 23:59:59 UTC

    def test_customers_and_subscriptions_are_whole_unless_a_window_is_asked_for(self):
        f = FakeStripe()
        with f.patch(): st.run_stripe_customers(CFG); st.run_stripe_subscriptions(CFG); st.run_stripe_customers({**CFG, 'days': 7})
        self.assertNotIn('created[gte]', f.calls[0][2]); self.assertNotIn('created[gte]', f.calls[1][2]); self.assertIn('created[gte]', f.calls[2][2])
        self.assertEqual(f.calls[1][2]['status'], 'active')

    def test_a_balance_transaction_kind_is_stripes_type_filter(self):
        f = FakeStripe()
        with f.patch(): st.run_stripe_balance_transactions({**CFG, 'type': 'stripe_balance_transactions', 'kind': 'payout'})
        self.assertEqual(f.calls[0][2]['type'], 'payout')

    def test_a_bad_date_is_refused_in_words(self):
        with self.assertRaises(st.StripeError) as e: st.window({'start': 'last tuesday'})
        self.assertIn('2026-10-01', str(e.exception))


class Money(Base):
    def test_minor_units_become_money_by_currency(self):
        self.assertEqual(st.minor(1999, 'usd'), 19.99)
        self.assertEqual(st.minor(500, 'JPY'), 500)
        self.assertEqual(st.minor(1500, 'kwd'), 1.5)
        self.assertEqual(st.minor(-250, 'eur'), -2.5)
        self.assertIsNone(st.minor(None, 'usd'))

    def test_rows_carry_money_and_the_headline_a_total_per_currency(self):
        f = FakeStripe(charges=[_ch(1, 1999), _ch(2, 1001), _ch(3, 500, 'jpy')])
        with f.patch(): head, body = st.run_stripe_charges(CFG)
        rows = [json.loads(x) for x in body.splitlines()]
        self.assertEqual([r['amount'] for r in rows], [19.99, 10.01, 500])
        self.assertIn('total 500 JPY · 30.0 USD', head)

    def test_a_status_stripe_cannot_filter_on_is_filtered_here(self):
        f = FakeStripe(charges=[_ch(1), _ch(2, status='failed'), _ch(3)])
        with f.patch(): head, body = st.run_stripe_charges({**CFG, 'status': 'failed'})
        self.assertEqual([json.loads(x)['id'] for x in body.splitlines()], ['ch_0002']); self.assertIn('failed charges', head)
        self.assertNotIn('status', f.calls[0][2])          # /v1/charges takes no status - never sent

    def test_mrr_normalises_each_interval_and_skips_metered_prices(self):
        self.assertEqual(st.mrr(SUB), 65.0)               # 3 x 15.00 a month + 240.00 a year / 12; the metered item adds 0
        with FakeStripe().patch(): head, body = st.run_stripe_subscriptions(CFG)
        self.assertIn('MRR 65.0 USD', head); self.assertEqual(json.loads(body)['items'], 'Team, Support, prod_api')

    def test_the_balance_is_one_row_per_state_and_currency(self):
        with FakeStripe().patch(): head, body = st.run_stripe_balance(CFG)
        self.assertEqual([json.loads(x) for x in body.splitlines()],
                         [{'state': 'available', 'currency': 'usd', 'amount': 1234.56}, {'state': 'available', 'currency': 'jpy', 'amount': 5000},
                          {'state': 'pending', 'currency': 'usd', 'amount': 25.0}])


class Throttling(Base):
    def test_a_429_is_waited_out_doubling_then_answered(self):
        f = FakeStripe(throttle=3)
        with f.patch(): st.run_stripe_balance(CFG)
        self.assertEqual(self.slept, [1.0, 2.0, 4.0]); self.assertEqual(len(f.calls), 4)

    def test_retry_after_wins_when_stripe_sends_one(self):
        with FakeStripe(throttle=1, retry_after='7').patch(): st.run_stripe_balance(CFG)
        self.assertEqual(self.slept, [7.0])

    def test_it_gives_up_in_words_with_every_wait_capped(self):
        with FakeStripe(throttle=99, retry_after='600').patch(), self.assertRaises(st.StripeError) as e: st.run_stripe_balance(CFG)
        self.assertIn('rate-limiting', str(e.exception))
        self.assertEqual(len(self.slept), st.TRIES - 1); self.assertTrue(all(s <= st.MAX_BACKOFF for s in self.slept))


class ReadOnly(Base):
    def test_every_read_sends_only_gets_to_api_stripe_com(self):
        f = FakeStripe(charges=[_ch(1)])
        with f.patch():
            st.probe(CFG)
            for t in reports.STRIPE_TYPES: getattr(st, f'run_{t}')({**CFG, 'type': t})      # a report's cfg carries its own type
        self.assertTrue(f.calls)
        self.assertFalse([c for c in f.calls if str(c[2].get('type', '')).startswith('stripe_')], "the report's type reached Stripe")
        self.assertEqual({(m, u.split('/v1/')[0]) for m, u, *_ in f.calls}, {('GET', 'https://api.stripe.com')})

    def test_any_other_verb_or_host_is_refused_before_it_is_sent(self):
        with FakeStripe().patch():
            for m, p in (('POST', '/v1/refunds'), ('POST', '/v1/payouts'), ('DELETE', '/v1/subscriptions/sub_1'), ('PUT', '/v1/customers/cus_1'),
                         ('PATCH', '/v1/charges/ch_1'), ('GET', '@evil.example/v1/balance'), ('GET', '/v2/core/events')):
                with self.assertRaises(st.StripeError): st._call(CFG, m, p)

    def test_the_module_has_no_other_road_out(self):
        src = (ROOT / 'taskuary' / 'stripe.py').read_text(encoding='utf-8')
        self.assertEqual(src.count('requests.'), 1, 'stripe.py must reach the network through _call alone')
        self.assertIn('requests.get(', src)

    def test_every_tool_is_a_read_on_a_report_and_tool_card_never_on_the_rail(self):
        s = MemoryStore(); card = s.get_connector_by_type('stripe')
        self.assertEqual(sorted(card['Roles'].split(',')), ['report', 'tool'])     # never a trigger: no tasks, no FYIs
        self.assertEqual(sorted(k for k in reports.REGISTRY if k.startswith('stripe_')), sorted(reports.STRIPE_TYPES))
        for t in reports.STRIPE_TYPES:
            self.assertEqual(scopes.needs(t), 'read', t)
            self.assertEqual(reports.card_of(t), 'stripe', t)
            self.assertTrue(scopes.allows({**card, 'Scope': 'read'}, t), t)

    def test_the_key_reaches_the_executor_and_never_the_page(self):
        s = MemoryStore(); c = s.get_connector_by_type('stripe')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Secret': 'rk_live_shh'}, 'owner')
        cfg = reports.resolve_cfg(s, {'type': 'stripe_payouts', 'days': 7})
        self.assertEqual((cfg['api_key'], cfg['days']), ('rk_live_shh', 7))
        self.assertNotIn('rk_live_shh', json.dumps(s.get_connector(c['ConnectorId']), default=str))
        self.assertNotIn('rk_live_shh', json.dumps(s.list_connectors(), default=str))


class Wiring(unittest.TestCase):
    def test_the_catalogue_card_is_working_and_a_corporate_system(self):
        from taskuary import connectorcatalog
        c = connectorcatalog.by_type('stripe')
        self.assertEqual((c['planned'], c['group'], c['title']), (False, 'Corporate systems', 'Stripe'))
        self.assertIn('read-only', c['desc'])

    def test_the_page_lists_describes_and_draws_the_card(self):
        cv = (ROOT / 'website' / 'src' / 'ConnectorsView.jsx').read_text(encoding='utf-8')
        self.assertIn('dataCards(["intacct", "quickbooks", "zoho_invoice", "amazon_sp", "stripe"])', cv)
        self.assertIn('  stripe: { title: "Stripe",', cv)
        self.assertIn('stripe: (p) =>', (ROOT / 'website' / 'src' / 'logos.jsx').read_text(encoding='utf-8'))
        rv = (ROOT / 'website' / 'src' / 'ReportsView.jsx').read_text(encoding='utf-8')
        for t in reports.STRIPE_TYPES: self.assertIn(f'  {t}: [', rv)
        self.assertIn('**Taking payments with Stripe**', (ROOT / 'docs' / 'site' / 'connections.md').read_text(encoding='utf-8'))

    def test_the_report_builder_reads_what_each_source_is_for(self):
        from taskuary import compose
        cat = {r['type']: r for r in compose.catalog(MemoryStore())}
        for t, word in (('stripe_payouts', 'payouts'), ('stripe_disputes', 'chargebacks'), ('stripe_refunds', 'refunds'),
                        ('stripe_subscriptions', 'MRR'), ('stripe_charges', 'revenue'), ('stripe_balance_transactions', 'fees')):
            self.assertIn(word, cat[t]['takes'], t); self.assertEqual(cat[t]['connection'], 'stripe')

    def test_agents_are_told_the_tool_names(self):
        src = (ROOT / 'taskuary' / 'docsync.py').read_text(encoding='utf-8')
        for t in reports.STRIPE_TYPES: self.assertIn(f'|{t}|' if t != 'stripe_invoices' else f'|{t}', src.replace("'\n                     '", ''))


if __name__ == '__main__':
    unittest.main()
