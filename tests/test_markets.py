"""Market data: plain REST with a key on a card, mocked at the HTTP edge. What is under test is
the SHAPE - the row keys a report and a chart consume, the headline that leads with its number so
a threshold compares the number and not the row count, and the refusal when no key is saved."""
import json
import unittest
from unittest import mock

from taskuary import markets

# captured live 2026-09-08 from api.coingecko.com/api/v3/simple/price
CG = {'bitcoin': {'usd': 78624, 'usd_24h_change': -0.6056038333762712}}


def _resp(status, body, text=None):
    r = mock.Mock(); r.status_code = status; r.text = text if text is not None else json.dumps(body)
    r.json = lambda: body
    return r


class TheHelpers(unittest.TestCase):
    def test_a_numeric_headline_leads_with_the_number_so_a_threshold_reads_dollars(self):
        from taskuary.reports import alert_fires, result_count
        head, body = markets._num({}, 1518.2, 'spent across 2 accounts', [{'a': 1}])
        self.assertTrue(head.startswith('1,518.20 '), head)
        self.assertEqual(result_count(head, body), 1518)
        self.assertIn('more than the 500', alert_fires({'alert': {'when': 'more_than', 'count': 500, 'to': 'x'}}, head, body))

    def test_a_missing_key_names_the_card_rather_than_failing_at_the_provider(self):
        with self.assertRaisesRegex(markets.MarketError, 'Finnhub'):
            markets.run_finnhub_quotes({'symbols': 'AAPL'})


class TheCrypto(unittest.TestCase):
    def test_prices_carry_the_symbol_price_and_day_change(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, CG)) as g:
            head, body = markets.run_coingecko_prices({'ids': 'bitcoin', 'vs': 'usd'})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual(rows, [{'id': 'bitcoin', 'currency': 'usd', 'price': 78624, 'change_pct': -0.61}])
        self.assertEqual(head, '1 prices')   # rows_out substitutes the unit word; it does not singularise
        self.assertNotIn('x-cg-demo-api-key', g.call_args.kwargs.get('headers') or {})

    def test_a_demo_key_rides_as_a_header_when_one_is_saved(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, CG)) as g:
            markets.run_coingecko_prices({'ids': 'bitcoin', 'api_key': 'demo_abc'})
        self.assertEqual(g.call_args.kwargs['headers']['x-cg-demo-api-key'], 'demo_abc')

    def test_the_providers_own_error_reaches_the_owner(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(429, {'status': {'error_message': 'rate limited'}})):
            with self.assertRaisesRegex(markets.MarketError, 'rate limited'):
                markets.run_coingecko_prices({'ids': 'bitcoin'})


class TheErrorExtraction(unittest.TestCase):
    """_get's error message is a seam every keyed provider will copy, so it is pinned on its own,
    independent of any one provider's shape."""
    def test_a_nested_error_envelope_is_read_one_level_down(self):
        body = {'wrapper': {'error': {'description': 'nested boom'}}}
        with mock.patch.object(markets.requests, 'get', return_value=_resp(400, body)):
            with self.assertRaises(markets.MarketError) as ctx:
                markets._get('https://example.test/x')
        self.assertTrue(str(ctx.exception).endswith('nested boom'), str(ctx.exception))
        self.assertNotIn('wrapper', str(ctx.exception))     # the raw envelope must not leak into the message

    def test_a_flat_error_still_wins_over_a_nested_one(self):
        body = {'message': 'flat boom', 'wrapper': {'error': {'description': 'should not be seen'}}}
        with mock.patch.object(markets.requests, 'get', return_value=_resp(400, body)):
            with self.assertRaises(markets.MarketError) as ctx:
                markets._get('https://example.test/x')
        self.assertTrue(str(ctx.exception).endswith('flat boom'), str(ctx.exception))


# captured live 2026-09-08 from api.frankfurter.dev/v1/latest
FX = {'amount': 1.0, 'base': 'USD', 'date': '2026-09-08', 'rates': {'EUR': 0.86103, 'GBP': 0.73825}}


class TheFx(unittest.TestCase):
    def test_one_row_per_currency_with_the_base_and_the_date(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, FX)) as g:
            head, body = markets.run_fx_rates({'base': 'USD', 'symbols': 'EUR,GBP'})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual(rows, [{'base': 'USD', 'currency': 'EUR', 'rate': 0.86103, 'date': '2026-09-08'},
                                {'base': 'USD', 'currency': 'GBP', 'rate': 0.73825, 'date': '2026-09-08'}])
        self.assertEqual(g.call_args.args[0], 'https://api.frankfurter.dev/v1/latest')


# captured live 2026-09-08 from query1.finance.yahoo.com/v8/finance/chart/AAPL (meta trimmed)
YQ = {'chart': {'result': [{'meta': {'currency': 'USD', 'symbol': 'AAPL', 'fullExchangeName': 'NasdaqGS',
                                     'instrumentType': 'EQUITY', 'regularMarketPrice': 316.195,
                                     'regularMarketChangePercent': -1.18, 'regularMarketTime': 1788889085,
                                     'regularMarketDayHigh': 319.4, 'regularMarketDayLow': 314.0,
                                     'previousClose': 319.97, 'exchangeTimezoneName': 'America/New_York'},
                            'timestamp': [1788800000, 1788886400],
                            'indicators': {'quote': [{'close': [318.1, 316.195], 'volume': [41000000, 38000000]}]}}],
                'error': None}}


class TheYahoo(unittest.TestCase):
    def test_a_quote_row_carries_last_change_and_the_day_range(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, YQ)) as g:
            head, body = markets.run_yahoo_quotes({'symbols': 'AAPL'})
        row = json.loads(body.splitlines()[0])
        self.assertEqual(row['symbol'], 'AAPL')
        self.assertEqual((row['price'], row['change_pct'], row['currency']), (316.195, -1.18, 'USD'))
        self.assertEqual((row['day_low'], row['day_high'], row['previous_close']), (314.0, 319.4, 319.97))
        self.assertEqual(row['exchange'], 'NasdaqGS')
        self.assertIn('/v8/finance/chart/AAPL', g.call_args.args[0])
        self.assertNotIn('crumb', json.dumps(g.call_args.kwargs))

    def test_several_symbols_are_several_calls_and_one_table(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, YQ)) as g:
            head, body = markets.run_yahoo_quotes({'symbols': 'AAPL, MSFT'})
        self.assertEqual(g.call_count, 2)
        self.assertEqual(len([l for l in body.splitlines() if l.strip()]), 2)

    def test_a_symbol_yahoo_does_not_know_is_named_and_the_rest_still_come_back(self):
        def side(url, **kw):
            return _resp(200, YQ) if '/AAPL' in url else _resp(404, {'chart': {'error': {'description': 'No data found, symbol may be delisted'}}})
        with mock.patch.object(markets.requests, 'get', side_effect=side):
            head, body = markets.run_yahoo_quotes({'symbols': 'AAPL,NOPE'})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['symbol'], 'NOPE')
        self.assertTrue(rows[1]['error'].endswith('No data found, symbol may be delisted'), rows[1]['error'])
        self.assertNotIn('chart', rows[1]['error'])    # the raw {"chart": {"error": ...}} envelope, not just its message

    def test_history_is_one_row_per_bar_newest_last(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, YQ)):
            head, body = markets.run_yahoo_history({'symbol': 'AAPL', 'range': '5d', 'interval': '1d'})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual([r['close'] for r in rows], [318.1, 316.195])
        self.assertEqual(rows[0]['date'], '2026-09-07')


# captured live 2026-09-08 from data.sec.gov/submissions/CIK0000320193.json (trimmed)
EDGAR = {'cik': '0000320193', 'entityType': 'operating', 'sic': '3571', 'sicDescription': 'Electronic Computers',
         'name': 'Apple Inc.', 'tickers': ['AAPL'],
         'filings': {'recent': {'accessionNumber': ['0000320193-26-000081', '0000320193-26-000075'],
                                'filingDate': ['2026-08-01', '2026-07-15'], 'form': ['10-Q', '8-K'],
                                'primaryDocument': ['aapl-20260627.htm', 'ex991.htm'],
                                'primaryDocDescription': ['10-Q', 'EX-99.1']}}}


class TheEdgar(unittest.TestCase):
    def test_filings_are_rows_newest_first_with_a_link_to_the_document(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, EDGAR)) as g:
            head, body = markets.run_edgar_filings({'cik': '320193'})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual(rows[0]['form'], '10-Q')
        self.assertEqual(rows[0]['filed'], '2026-08-01')
        self.assertEqual(rows[0]['company'], 'Apple Inc.')
        self.assertIn('320193/000032019326000081/aapl-20260627.htm', rows[0]['url'])
        self.assertIn('CIK0000320193.json', g.call_args.args[0])          # zero-padded to ten
        self.assertIn('Taskuary', g.call_args.kwargs['headers']['User-Agent'])

    def test_only_the_forms_asked_for_come_back(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, EDGAR)):
            _, body = markets.run_edgar_filings({'cik': '320193', 'forms': '8-K'})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual([r['form'] for r in rows], ['8-K'])


# shape of data.sec.gov/api/xbrl/companyfacts/CIK...json - trimmed to the parts run_edgar_facts reads
def _facts(us_gaap=None, ifrs_full=None, name='Test Co'):
    facts = {}
    if us_gaap is not None: facts['us-gaap'] = {'Revenues': us_gaap}
    if ifrs_full is not None: facts['ifrs-full'] = {'Revenues': ifrs_full}
    return {'entityName': name, 'facts': facts}


class TheEdgarFacts(unittest.TestCase):
    def test_an_empty_units_tag_in_one_taxonomy_does_not_shadow_a_populated_one_below_it(self):
        # us-gaap carries the tag but with no observations at all - it must not win the fallback
        # just because a truthy dict exists there, which is what let a company's ifrs-full series
        # go dark behind an empty us-gaap entry
        body = _facts(us_gaap={'label': 'Revenues', 'units': {}},
                      ifrs_full={'label': 'Revenues', 'units': {'USD': [
                          {'end': '2026-06-30', 'val': 100, 'fy': 2026, 'fp': 'Q2', 'form': '10-Q'},
                          {'end': '2025-06-30', 'val': 90, 'fy': 2025, 'fp': 'Q2', 'form': '10-Q'}]}})
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, body)):
            head, out = markets.run_edgar_facts({'cik': '1'})
        rows = [json.loads(l) for l in out.splitlines() if l.strip()]
        self.assertEqual([r['end'] for r in rows], ['2026-06-30', '2025-06-30'])   # newest first
        self.assertEqual(rows[0]['value'], 100)

    def test_usd_is_preferred_over_a_unit_with_more_observations(self):
        # EUR is listed first in the dict AND has more observations - dict order and observation
        # count must both lose to USD when USD is one of the units this company reports
        body = _facts(us_gaap={'label': 'Revenues', 'units': {
            'EUR': [{'end': '2026-06-30', 'val': 1}, {'end': '2025-06-30', 'val': 2}, {'end': '2024-06-30', 'val': 3}],
            'USD': [{'end': '2026-06-30', 'val': 111}]}})
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, body)):
            head, out = markets.run_edgar_facts({'cik': '1'})
        rows = [json.loads(l) for l in out.splitlines() if l.strip()]
        self.assertEqual(rows, [{'company': 'Test Co', 'tag': 'Revenues', 'unit': 'USD',
                                'end': '2026-06-30', 'value': 111, 'fy': None, 'fp': None, 'form': None}])

    def test_no_usd_picks_the_unit_with_the_most_observations_not_whichever_sorts_first(self):
        body = _facts(us_gaap={'label': 'Revenues', 'units': {
            'EUR': [{'end': '2026-06-30', 'val': 1}],
            'GBP': [{'end': '2026-06-30', 'val': 2}, {'end': '2025-06-30', 'val': 3}]}})
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, body)):
            head, out = markets.run_edgar_facts({'cik': '1'})
        rows = [json.loads(l) for l in out.splitlines() if l.strip()]
        self.assertTrue(all(r['unit'] == 'GBP' for r in rows), rows)

    def test_a_unit_asked_for_that_the_tag_does_not_carry_is_refused_and_names_what_it_does_carry(self):
        body = _facts(us_gaap={'label': 'Revenues', 'units': {'USD': [{'end': '2026-06-30', 'val': 1}]}})
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, body)):
            with self.assertRaises(markets.MarketError) as ctx:
                markets.run_edgar_facts({'cik': '1', 'unit': 'GBP'})
        self.assertIn('GBP', str(ctx.exception))
        self.assertIn('USD', str(ctx.exception))


class TheWiring(unittest.TestCase):
    KEYLESS = ('coingecko_prices', 'fx_rates', 'yahoo_quotes', 'yahoo_history', 'edgar_filings', 'edgar_facts')

    def test_every_type_is_registered_a_read_and_owned_by_a_card(self):
        from taskuary import reports, scopes
        for t in self.KEYLESS:
            self.assertIn(t, reports.REGISTRY, t)
            self.assertIs(reports.executor_for(t), reports.REGISTRY[t], t)
            self.assertEqual(scopes.needs(t), 'read', t)
            self.assertIn(reports.card_of(t), ('coingecko', 'frankfurter', 'yahoo', 'sec_edgar'), t)

    def test_a_keyless_card_needs_no_connection_entry_and_resolve_cfg_passes_the_config_through(self):
        from taskuary import reports
        from taskuary.store import MemoryStore
        cfg = reports.resolve_cfg(MemoryStore(), {'type': 'yahoo_quotes', 'symbols': 'AAPL'})
        self.assertEqual(cfg['symbols'], 'AAPL')

    def test_stooq_is_planned_and_fails_loudly_rather_than_being_absent(self):
        from taskuary import reports
        self.assertIn('stooq', reports.PLANNED)
        with self.assertRaisesRegex(NotImplementedError, 'roadmap'):
            reports.REGISTRY['stooq']({})

    def test_the_cards_are_in_the_catalog_so_they_can_be_configured(self):
        from taskuary.store import MemoryStore
        types = {c['Type'] for c in MemoryStore().list_connectors()}
        for card in ('coingecko', 'frankfurter', 'yahoo', 'sec_edgar'): self.assertIn(card, types, card)


class TheScreen(unittest.TestCase):
    def test_only_the_rows_where_every_condition_holds_come_back(self):
        with mock.patch.object(markets, 'run_yahoo_quotes', return_value=('2 quotes', '\n'.join([
                json.dumps({'symbol': 'AAPL', 'price': 316.19, 'change_pct': -1.18}),
                json.dumps({'symbol': 'NVDA', 'price': 118.0, 'change_pct': -6.4})]))):
            head, body = markets.run_markets_screen({'provider': 'yahoo_quotes', 'symbols': 'AAPL,NVDA',
                                                     'conditions': [['change_pct', '<=', -5]]})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual([r['symbol'] for r in rows], ['NVDA'])
        self.assertIn('1 match', head)

    def test_nothing_matching_is_quiet_and_an_alert_stays_silent(self):
        from taskuary.reports import alert_fires
        with mock.patch.object(markets, 'run_yahoo_quotes', return_value=('1 quotes', json.dumps({'symbol': 'AAPL', 'change_pct': -1.0}))):
            head, body = markets.run_markets_screen({'provider': 'yahoo_quotes', 'conditions': [['change_pct', '<=', -5]]})
        self.assertEqual(alert_fires({'alert': {'when': 'something_came_back', 'to': 'x'}}, head, body), '')

    def test_an_unknown_provider_or_operator_is_refused_before_any_call(self):
        with self.assertRaisesRegex(markets.MarketError, 'not a market source'):
            markets.run_markets_screen({'provider': 'sqlite', 'conditions': []})
        with self.assertRaisesRegex(markets.MarketError, 'operator'):
            markets.run_markets_screen({'provider': 'yahoo_quotes', 'conditions': [['price', 'DROP TABLE', 1]]})

    def test_a_condition_on_a_field_the_provider_does_not_return_says_so(self):
        with mock.patch.object(markets, 'run_yahoo_quotes', return_value=('1 quotes', json.dumps({'symbol': 'AAPL'}))):
            with self.assertRaisesRegex(markets.MarketError, 'rsi'):
                markets.run_markets_screen({'provider': 'yahoo_quotes', 'conditions': [['rsi', '<', 30]]})

    def test_a_degraded_row_missing_the_field_does_not_abort_a_screen_the_other_rows_can_still_answer(self):
        # run_yahoo_quotes degrades an unresolvable symbol to {symbol, price, error} - no change_pct.
        # That row must be skipped as a non-match, not treated as "the provider has no such field".
        with mock.patch.object(markets, 'run_yahoo_quotes', return_value=('2 quotes', '\n'.join([
                json.dumps({'symbol': 'AAPL', 'price': 316.19, 'change_pct': -6.0}),
                json.dumps({'symbol': 'NOPE', 'price': None, 'error': 'No data found'})]))):
            head, body = markets.run_markets_screen({'provider': 'yahoo_quotes', 'symbols': 'AAPL,NOPE',
                                                     'conditions': [['change_pct', '<=', -5]]})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual([r['symbol'] for r in rows], ['AAPL'])

    def test_a_malformed_condition_is_refused_not_silently_dropped(self):
        # a 2-element condition used to vanish from the filter, which LOOSENS it - a typo must not
        # make the alert fire every run instead of never.
        with self.assertRaisesRegex(markets.MarketError, 'condition'):
            markets.run_markets_screen({'provider': 'yahoo_quotes', 'conditions': [['price', '<']]})

    def test_zero_conditions_is_refused_not_treated_as_match_everything(self):
        with self.assertRaisesRegex(markets.MarketError, 'at least one condition'):
            markets.run_markets_screen({'provider': 'yahoo_quotes', 'conditions': []})

    def test_comparing_a_string_field_with_an_ordering_operator_names_what_to_fix(self):
        with mock.patch.object(markets, 'run_yahoo_quotes', return_value=('1 quotes', json.dumps({'symbol': 'AAPL', 'currency': 'USD'}))):
            with self.assertRaisesRegex(markets.MarketError, 'currency'):
                markets.run_markets_screen({'provider': 'yahoo_quotes', 'conditions': [['currency', '<', 100]]})

    def test_the_screen_refuses_to_borrow_a_card_of_the_wrong_type(self):
        # a wrong connector_id must not hand an unrelated card's secret to whichever provider the
        # screen calls - reports._connector refuses this same way for every other borrow.
        from taskuary.store import MemoryStore
        store = MemoryStore()
        aws_id = store.connectors_by_type('aws')[0]['ConnectorId']
        store.save_connector({'ConnectorId': aws_id, 'Secret': 'AKIA_fake'}, 'owner')
        with self.assertRaisesRegex(markets.MarketError, 'aws'):
            markets.screen_connection(store, aws_id)

    def test_the_screen_borrows_the_named_providers_card(self):
        # behaviour, not identity: CONNECTION_OF['markets_screen'] must actually resolve the card
        # connector_id names and hand back its saved key.
        from taskuary import reports
        from taskuary.store import MemoryStore
        store = MemoryStore()
        cg_id = store.connectors_by_type('coingecko')[0]['ConnectorId']
        store.save_connector({'ConnectorId': cg_id, 'Secret': 'demo_xyz'}, 'owner')
        cfg = reports.CONNECTION_OF['markets_screen'](store, cg_id)
        self.assertEqual(cfg['api_key'], 'demo_xyz')


# captured live 2026-09-08 from api.twelvedata.com/quote?symbol=AAPL&apikey=demo
TD_QUOTE = {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "mic_code": "XNGS", "currency": "USD",
            "datetime": "2026-09-08", "timestamp": 1788874200, "last_quote_at": 1788893340, "open": "317.18",
            "high": "320.71", "low": "314.98", "close": "315.02", "volume": "886145", "previous_close": "319.97000",
            "change": "-4.95000", "percent_change": "-1.54702", "average_volume": "33681314", "is_market_open": True,
            "fifty_two_week": {"low": "225.95000", "high": "344.57001", "low_change": "89.070003",
                               "high_change": "-29.55001", "low_change_percent": "39.42023",
                               "high_change_percent": "-8.57591", "range": "225.949997 - 344.570007"}}

# captured live 2026-09-08 from api.twelvedata.com/rsi?symbol=AAPL&apikey=demo (trimmed to 3 values)
TD_RSI = {"meta": {"symbol": "AAPL", "interval": "1day", "indicator": {"name": "RSI - Relative Strength Index"}},
          "values": [{"datetime": "2026-09-08", "rsi": "49.12401"}, {"datetime": "2026-09-04", "rsi": "53.88621"},
                     {"datetime": "2026-09-03", "rsi": "63.38419"}], "status": "ok"}

# captured live 2026-09-08 from api.twelvedata.com - the demo key's error shape, HTTP 200 with status=error
TD_ERROR = {"code": 401, "message": "The 'demo' API key is only used for initial familiarity. To become a full "
            "user, you can request your own API key at https://twelvedata.com/pricing. It is absolutely free, "
            "and it’s yours for a lifetime. It only takes 10 seconds to obtain your own API key!",
            "status": "error"}


class TheTwelveData(unittest.TestCase):
    def test_a_quote_row_is_coerced_off_the_providers_all_string_values(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, TD_QUOTE)) as g:
            head, body = markets.run_td_quotes({'symbol': 'AAPL', 'api_key': 'demo'})
        row = json.loads(body.splitlines()[0])
        self.assertEqual(row, {'symbol': 'AAPL', 'name': 'Apple Inc.', 'exchange': 'NASDAQ', 'currency': 'USD',
                              'price': 315.02, 'change_pct': -1.54702, 'open': 317.18, 'high': 320.71, 'low': 314.98,
                              'previous_close': 319.97, 'volume': 886145})
        self.assertIsInstance(row['price'], float); self.assertIsInstance(row['volume'], int)
        self.assertEqual(g.call_args.kwargs['params']['apikey'], 'demo')

    def test_a_missing_key_names_the_card(self):
        with self.assertRaisesRegex(markets.MarketError, 'Twelve Data'):
            markets.run_td_quotes({'symbol': 'AAPL'})

    def test_the_200_with_status_error_shape_is_raised_not_returned_as_a_row(self):
        # a 200 that reports zero rows because of an error is a report that lies
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, TD_ERROR)):
            with self.assertRaises(markets.MarketError) as ctx:
                markets.run_td_quotes({'symbol': 'AAPL', 'api_key': 'demo'})
        self.assertIn('own API key', str(ctx.exception))

    def test_an_indicator_with_one_value_key_comes_back_newest_first(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, TD_RSI)):
            head, body = markets.run_td_indicator({'symbol': 'AAPL', 'indicator': 'rsi', 'api_key': 'demo'})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual(rows[0], {'symbol': 'AAPL', 'indicator': 'rsi', 'date': '2026-09-08', 'rsi': 49.12401})
        self.assertEqual([r['date'] for r in rows], ['2026-09-08', '2026-09-04', '2026-09-03'])

    def test_an_indicator_with_several_value_keys_carries_every_one(self):
        # not captured (the demo key blocks MACD too) - synthesized from the documented shape to
        # prove the code unpacks ANY non-datetime keys, not just a hardcoded "rsi"
        macd = {"values": [{"datetime": "2026-09-08", "macd": "1.234", "macd_signal": "0.987", "macd_hist": "0.247"}]}
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, macd)):
            head, body = markets.run_td_indicator({'symbol': 'AAPL', 'indicator': 'macd', 'api_key': 'demo'})
        row = json.loads(body.splitlines()[0])
        self.assertEqual(row, {'symbol': 'AAPL', 'indicator': 'macd', 'date': '2026-09-08',
                              'macd': 1.234, 'macd_signal': 0.987, 'macd_hist': 0.247})

    def test_an_indicator_this_card_does_not_know_is_refused_before_any_call(self):
        with self.assertRaisesRegex(markets.MarketError, 'stoch'):
            markets.run_td_indicator({'symbol': 'AAPL', 'indicator': 'stoch', 'api_key': 'demo'})


# captured live 2026-09-08 from alphavantage.co/query?function=GLOBAL_QUOTE&symbol=IBM&apikey=demo
AV_QUOTE = {"Global Quote": {"01. symbol": "IBM", "02. open": "233.3300", "03. high": "236.1700",
                            "04. low": "231.6800", "05. price": "234.8900", "06. volume": "3722860",
                            "07. latest trading day": "2026-09-04", "08. previous close": "234.7100",
                            "09. change": "0.1800", "10. change percent": "0.0767%"}}

# captured live 2026-09-08 from alphavantage.co/query?function=RSI&apikey=demo - a 200 with NO data
AV_BLOCKED = {"Information": "The **demo** API key is for demo purposes only. Please claim your free API key at "
              "(https://www.alphavantage.co/support/#api-key) to explore our full API offerings. It takes fewer "
              "than 20 seconds."}


class TheAlphaVantage(unittest.TestCase):
    def test_a_quote_row_strips_the_percent_sign_off_change_percent(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, AV_QUOTE)):
            head, body = markets.run_av_quotes({'symbol': 'IBM', 'api_key': 'demo'})
        row = json.loads(body.splitlines()[0])
        self.assertEqual(row, {'symbol': 'IBM', 'price': 234.89, 'change_pct': 0.0767, 'volume': 3722860,
                              'previous_close': 234.71, 'open': 233.33, 'high': 236.17, 'low': 231.68,
                              'latest_day': '2026-09-04'})
        self.assertIsInstance(row['change_pct'], float)

    def test_a_missing_key_names_the_card(self):
        with self.assertRaisesRegex(markets.MarketError, 'Alpha Vantage'):
            markets.run_av_quotes({'symbol': 'IBM'})

    def test_a_200_carrying_information_and_no_data_is_the_real_demo_key_trap(self):
        # this is the exact captured response a demo key gets back from a blocked endpoint - a
        # rate limit or a refusal answered at HTTP 200, with no Global Quote key at all
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, AV_BLOCKED)):
            with self.assertRaises(markets.MarketError) as ctx:
                markets.run_av_quotes({'symbol': 'IBM', 'api_key': 'demo'})
        self.assertIn('for demo purposes only', str(ctx.exception))

    def test_av_indicator_is_not_built(self):
        self.assertFalse(hasattr(markets, 'run_av_indicator'))
