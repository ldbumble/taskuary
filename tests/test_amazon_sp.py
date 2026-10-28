"""Amazon SP-API: a seller's reports, mocked at the HTTP edge (no network). Under test is the shape: the LWA
exchange and its hour-long cache, Test reading the marketplaces, the createReport -> getReport -> document ->
gzip -> rows road, a 429 waited out at the operation's own rate, and the read-only guarantee - nothing but a
GET leaves this card except the token exchange and createReport. The seller and their goods are invented."""
import gzip, json, unittest
from unittest import mock

from taskuary import amazon_sp as amz, reports, scopes
from taskuary.store import MemoryStore

CFG = {'client_id': 'amzn1.application-oa2-client.test', 'client_secret': 'cs-test', 'refresh_token': 'Atzr|test', 'region': 'na',
       'marketplace_ids': 'ATVPDKIKX0DER'}
TSV = 'amazon-order-id\tsku\tquantity\titem-price\n111-0000001-0000001\tNW-MUG-01\t2\t25.98\n111-0000002-0000002\tNW-TEE-02\t1\t19.00\n'
SALES = {'reportSpecification': {'reportType': 'GET_SALES_AND_TRAFFIC_REPORT'},
         'salesAndTrafficByDate': [{'date': '2026-10-01', 'salesByDate': {'orderedProductSales': {'amount': 120.5, 'currencyCode': 'USD'}, 'unitsOrdered': 6},
                                    'trafficByDate': {'sessions': 80}},
                                   {'date': '2026-10-02', 'salesByDate': {'orderedProductSales': {'amount': 44.0, 'currencyCode': 'USD'}, 'unitsOrdered': 2},
                                    'trafficByDate': {'sessions': 31}}],
         'salesAndTrafficByAsin': [{'parentAsin': 'B0TEST0001', 'salesByAsin': {'unitsOrdered': 8}}]}


def _resp(status, body=None, content=b'', headers=None):
    r = mock.Mock(); r.status_code, r.headers, r.content = status, headers or {}, content
    r.text = json.dumps(body) if body is not None else content.decode('latin-1')
    r.json = lambda: body
    return r


class FakeAmazon:
    """Answers the calls the card makes, records every one, and can throttle or delay on request."""
    def __init__(self, doc=TSV.encode(), gz=True, statuses=('IN_QUEUE', 'IN_PROGRESS', 'DONE'), throttle=0):
        self.calls, self.tokens, self.doc, self.gz, self.statuses, self.throttle = [], 0, doc, gz, list(statuses), throttle
        self.created = []

    def post(self, url, **kw):
        self.calls.append(('POST', url)); self.tokens += 1
        assert url == amz.TOKEN_URL and kw['data']['grant_type'] == 'refresh_token'
        return _resp(200, {'access_token': f'Atza|tok{self.tokens}', 'token_type': 'bearer', 'expires_in': 3600})

    def request(self, method, url, **kw):
        self.calls.append((method, url)); path = url.split('.amazon.com', 1)[1]
        assert kw['headers']['x-amz-access-token'].startswith('Atza|')
        if self.throttle: self.throttle -= 1; return _resp(429, {'errors': [{'code': 'QuotaExceeded', 'message': 'You exceeded your quota'}]})
        if path == amz.PARTICIPATIONS:
            return _resp(200, {'payload': [
                {'marketplace': {'id': 'ATVPDKIKX0DER', 'name': 'Amazon.com', 'countryCode': 'US', 'defaultCurrencyCode': 'USD'},
                 'storeName': 'Northwind Goods', 'participation': {'isParticipating': True, 'hasSuspendedListings': False}},
                {'marketplace': {'id': 'A2EUQ1WTGCTBG2', 'name': 'Amazon.ca', 'countryCode': 'CA', 'defaultCurrencyCode': 'CAD'},
                 'storeName': 'Northwind Goods', 'participation': {'isParticipating': False, 'hasSuspendedListings': False}}]})
        if method == 'POST' and path == '/reports/2021-06-30/reports':
            self.created.append(json.loads(kw['data'])); return _resp(202, {'reportId': 'R1'})
        if path == '/reports/2021-06-30/reports/R1':
            st = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return _resp(200, {'reportId': 'R1', 'processingStatus': st, **({'reportDocumentId': 'D1'} if st == 'DONE' else {})})
        if path == '/reports/2021-06-30/reports' and method == 'GET':
            self.listed = kw['params']
            return _resp(200, {'reports': [{'reportId': 'S1', 'createdTime': '2026-10-01T00:00:00Z', 'reportDocumentId': 'D1'},
                                           {'reportId': 'S2', 'createdTime': '2026-10-15T00:00:00Z', 'reportDocumentId': 'D2'}]})
        if path.startswith('/reports/2021-06-30/documents/'):
            return _resp(200, {'reportDocumentId': path.rsplit('/', 1)[1], 'url': 'https://tortuga-prod.s3.example/doc?sig=x',
                               **({'compressionAlgorithm': 'GZIP'} if self.gz else {})})
        raise AssertionError(f'unexpected call {method} {path}')

    def get(self, url, **kw):
        self.calls.append(('DOWNLOAD', url)); assert 'headers' not in kw     # a presigned link never gets the access token
        return _resp(200, content=gzip.compress(self.doc) if self.gz else self.doc)

    def patch(self):
        return mock.patch.multiple(amz.requests, post=self.post, request=self.request, get=self.get)


class Base(unittest.TestCase):
    def setUp(self):
        amz._TOK.clear(); amz._DOCS.clear()
        p = mock.patch.object(amz, '_sleep', lambda s: self.slept.append(s)); p.start(); self.addCleanup(p.stop)
        self.slept = []


class Token(Base):
    def test_the_refresh_token_is_exchanged_once_and_cached_for_the_hour(self):
        f = FakeAmazon()
        with f.patch():
            self.assertEqual(amz.token(CFG), 'Atza|tok1')
            self.assertEqual(amz.token(CFG), 'Atza|tok1')
        self.assertEqual(f.tokens, 1)

    def test_an_expired_token_is_bought_again(self):
        f = FakeAmazon()
        with f.patch():
            amz.token(CFG); amz._TOK[amz._key(CFG)] = ('old', 0)
            self.assertEqual(amz.token(CFG), 'Atza|tok2')

    def test_a_refused_refresh_token_says_what_to_do(self):
        bad = _resp(400, {'error': 'invalid_grant', 'error_description': 'The request has an invalid grant parameter'})
        with mock.patch.object(amz.requests, 'post', return_value=bad), self.assertRaises(amz.AmazonError) as e: amz.token(CFG)
        self.assertIn('invalid_grant', str(e.exception)); self.assertIn('authorize the app again', str(e.exception))

    def test_missing_credentials_are_named_before_any_call(self):
        with mock.patch.object(amz.requests, 'post') as p:
            for k in ('client_id', 'client_secret', 'refresh_token'):
                with self.assertRaises(amz.AmazonError): amz.token({**CFG, k: ''})
        p.assert_not_called()


class TestConnection(Base):
    def test_test_names_the_store_and_the_marketplaces_it_sells_in(self):
        f = FakeAmazon()
        with f.patch(): out = amz.probe(CFG)
        self.assertIn('Northwind Goods', out); self.assertIn('Amazon.com (ATVPDKIKX0DER)', out); self.assertNotIn('Amazon.ca', out)
        self.assertEqual(f.calls[-1], ('GET', 'https://sellingpartnerapi-na.amazon.com/sellers/v1/marketplaceParticipations'))

    def test_a_marketplace_the_account_does_not_have_is_flagged(self):
        with FakeAmazon().patch(): out = amz.probe({**CFG, 'marketplace_ids': 'ATVPDKIKX0DER, A1PA6795UKMFR9'})
        self.assertIn("not this account's in this region: A1PA6795UKMFR9", out)

    def test_the_region_picks_the_host(self):
        self.assertEqual(amz.region({'region': 'Europe'}), 'eu')
        self.assertEqual(amz.region({'marketplace_ids': 'A1VC38T7YXB528'}), 'fe')
        with self.assertRaises(amz.AmazonError): amz.region({'region': 'mars'})

    def test_the_card_test_branch_reaches_the_probe(self):
        from taskuary import channels
        s = MemoryStore(); c = s.get_connector_by_type('amazon_sp')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Secret': 'Atzr|test',
                          'ConfigJson': json.dumps({k: v for k, v in CFG.items() if k != 'refresh_token'})}, 'owner')
        with FakeAmazon().patch(): r = channels.test_connector(s, c['ConnectorId'])
        self.assertTrue(r.get('ok'), r); self.assertIn('Northwind Goods', json.dumps(r))


class ReportFlow(Base):
    def test_orders_are_requested_polled_downloaded_unzipped_and_parsed(self):
        f = FakeAmazon()
        with f.patch(): head, body = amz.run_amazon_orders({**CFG, 'days': 7})
        rows = [json.loads(l) for l in body.splitlines()]
        self.assertEqual([r['sku'] for r in rows], ['NW-MUG-01', 'NW-TEE-02'])
        self.assertTrue(head.startswith('2 rows'), head)
        body = f.created[0]
        self.assertEqual(body['reportType'], 'GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL')
        self.assertEqual(body['marketplaceIds'], ['ATVPDKIKX0DER'])
        self.assertTrue(body['dataStartTime'].endswith('T00:00:00Z') and body['dataEndTime'].endswith('Z'))
        self.assertEqual(len(self.slept), 2)          # IN_QUEUE, IN_PROGRESS, then DONE
        self.assertIn(('DOWNLOAD', 'https://tortuga-prod.s3.example/doc?sig=x'), f.calls)

    def test_sales_and_traffic_json_becomes_one_row_a_day_or_one_an_asin(self):
        f = FakeAmazon(doc=json.dumps(SALES).encode())
        with f.patch():
            _, body = amz.run_amazon_sales_traffic({**CFG, 'days': 30})
            _, by_asin = amz.run_amazon_sales_traffic({**CFG, 'days': 30, 'by': 'asin'})
        rows = [json.loads(l) for l in body.splitlines()]
        self.assertEqual(rows[0]['salesByDate.orderedProductSales.amount'], 120.5)
        self.assertEqual(rows[1]['trafficByDate.sessions'], 31)
        self.assertEqual(json.loads(by_asin.splitlines()[0])['parentAsin'], 'B0TEST0001')
        self.assertEqual(f.created[0]['reportOptions'], {'dateGranularity': 'DAY', 'asinGranularity': 'PARENT'})

    def test_a_finished_report_is_kept_so_a_second_read_asks_amazon_once(self):
        f = FakeAmazon()
        with f.patch(): amz.run_amazon_inventory(CFG); amz.run_amazon_inventory(CFG)
        self.assertEqual(len(f.created), 1)
        self.assertNotIn('dataStartTime', f.created[0])     # inventory is as it stands, no window

    def test_an_uncompressed_csv_document_parses_too(self):
        f = FakeAmazon(doc=b'sku,qty\nNW-MUG-01,4\n', gz=False)
        with f.patch(): _, body = amz.run_amazon_report({**CFG, 'report_type': 'GET_MERCHANT_LISTINGS_ALL_DATA'})
        self.assertEqual(json.loads(body), {'sku': 'NW-MUG-01', 'qty': '4'})

    def test_a_cancelled_report_is_no_data_not_a_failure(self):
        f = FakeAmazon(statuses=('CANCELLED',))
        with f.patch(): head, body = amz.run_amazon_orders(CFG)
        self.assertIn('no data', head); self.assertEqual(body, '')

    def test_a_fatal_report_fails_loudly(self):
        with FakeAmazon(statuses=('FATAL',)).patch(), self.assertRaises(amz.AmazonError) as e: amz.run_amazon_orders(CFG)
        self.assertIn('FATAL', str(e.exception))

    def test_settlements_are_listed_never_requested_and_the_newest_is_read(self):
        f = FakeAmazon()
        with f.patch(): head, _ = amz.run_amazon_settlement({**CFG, 'days': 60})
        self.assertEqual(f.created, [])
        self.assertEqual(f.listed['reportTypes'], 'GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2')
        self.assertEqual(f.listed['processingStatuses'], 'DONE')
        self.assertIn('/documents/D2', ' '.join(u for _, u in f.calls))        # 2026-10-15 is the newer one
        self.assertNotIn('/documents/D1', ' '.join(u for _, u in f.calls))
        self.assertIn('newest 2026-10-15', head)

    def test_no_marketplace_on_the_card_means_every_one_the_account_sells_in(self):
        f = FakeAmazon()
        with f.patch(): amz.run_amazon_orders({**CFG, 'marketplace_ids': ''})
        self.assertEqual(f.created[0]['marketplaceIds'], ['ATVPDKIKX0DER'])

    def test_bad_options_are_refused_in_words(self):
        with self.assertRaises(amz.AmazonError): amz.run_amazon_report({**CFG, 'report_type': 'GET_X', 'options': '{nope'})


class Throttling(Base):
    def test_a_429_is_waited_out_at_the_operations_own_restore_rate(self):
        f = FakeAmazon(throttle=2)
        with f.patch(): amz.run_amazon_marketplaces(CFG)
        base = 1 / amz.RATE['getMarketplaceParticipations']
        self.assertEqual([round(s, 1) for s in self.slept], [round(base, 1), round(base * 1.5, 1)])

    def test_waits_are_capped_and_give_up_in_words(self):
        f = FakeAmazon(throttle=99)
        with f.patch(), self.assertRaises(amz.AmazonError) as e: amz.participations(CFG)
        self.assertIn('throttling', str(e.exception))
        self.assertTrue(all(s <= amz.MAX_BACKOFF for s in self.slept))
        self.assertEqual(len(self.slept), amz.TRIES - 1)

    def test_retry_after_wins_when_amazon_sends_one(self):
        self.assertEqual(amz._wait('createReport', _resp(429, headers={'Retry-After': '3'}), 0), 3.0)


class ReadOnly(Base):
    def test_nothing_but_a_get_leaves_except_the_token_and_create_report(self):
        f = FakeAmazon(doc=json.dumps(SALES).encode())
        with f.patch():
            amz.probe(CFG); amz.run_amazon_sales_traffic(CFG); amz.run_amazon_orders(CFG); amz.run_amazon_inventory(CFG)
            amz.run_amazon_settlement(CFG); amz.run_amazon_marketplaces(CFG); amz.run_amazon_report({**CFG, 'report_type': 'GET_X'})
        writes = {(m, u) for m, u in f.calls if m not in ('GET', 'DOWNLOAD')}
        self.assertEqual(writes, {('POST', amz.TOKEN_URL), ('POST', 'https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/reports')})

    def test_any_other_verb_is_refused_before_it_is_sent(self):
        with mock.patch.object(amz.requests, 'request') as r:
            for m, p in (('DELETE', '/reports/2021-06-30/reports/R1'), ('PUT', '/listings/2021-08-01/items/X/SKU'),
                         ('PATCH', '/listings/2021-08-01/items/X/SKU'), ('POST', '/feeds/2021-06-30/feeds')):
                with self.assertRaises(amz.AmazonError): amz._call(CFG, 'x', m, p)
        r.assert_not_called()

    def test_every_tool_is_a_read_on_a_report_and_tool_card(self):
        s = MemoryStore(); card = s.get_connector_by_type('amazon_sp')
        self.assertEqual(sorted(card['Roles'].split(',')), ['report', 'tool'])     # never a trigger: no work on the rail
        for t in (k for k in reports.REGISTRY if k.startswith('amazon_')):
            self.assertEqual(scopes.needs(t), 'read', t)
            self.assertEqual(reports.card_of(t), 'amazon_sp', t)
            self.assertTrue(scopes.allows({**card, 'Scope': 'read'}, t), t)

    def test_the_card_resolves_its_secret_as_the_refresh_token_and_hides_the_client_secret(self):
        from taskuary import guard
        s = MemoryStore(); c = s.get_connector_by_type('amazon_sp')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Secret': 'Atzr|abc',
                          'ConfigJson': json.dumps({'client_id': 'cid', 'client_secret': 'shh', 'region': 'eu'})}, 'owner')
        cfg = reports.resolve_cfg(s, {'type': 'amazon_orders', 'days': 3})
        self.assertEqual((cfg['refresh_token'], cfg['client_secret'], cfg['region'], cfg['days']), ('Atzr|abc', 'shh', 'eu', 3))
        shown = guard.masked_config(s.get_connector(c['ConnectorId']))
        self.assertNotIn('shh', shown['ConfigJson']); self.assertEqual(shown['ConfigSaved'], ['client_secret'])


class Parse(unittest.TestCase):
    def test_a_bom_and_a_windows_1252_byte_do_not_break_a_flat_file(self):
        want = [{'sku': 'NW-1', 'name': 'Caf\xe9 mug'}]
        self.assertEqual(amz.parse('﻿sku\tname\nNW-1\tCaf\xe9 mug\n'.encode('utf-8')), want)
        self.assertEqual(amz.parse('sku\tname\nNW-1\tCaf\xe9 mug\n'.encode('cp1252')), want)

    def test_a_japanese_flat_file_reads_as_shift_jis(self):
        self.assertEqual(amz.parse('sku\tname\nNW-1\t日本\n'.encode('cp932'), fallback='cp932'), [{'sku': 'NW-1', 'name': '日本'}])

    def test_an_empty_document_is_no_rows(self):
        self.assertEqual(amz.parse(gzip.compress(b'')), [])


if __name__ == '__main__':
    unittest.main()
