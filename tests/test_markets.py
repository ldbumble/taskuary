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
