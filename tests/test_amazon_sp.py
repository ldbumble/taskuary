"""Amazon SP-API: a seller's reports, mocked at the HTTP edge (no network). Under test is the shape: the LWA
exchange and its hour-long cache, Test reading the marketplaces, the createReport -> getReport -> document ->
gzip -> rows road, a 429 waited out at the operation's own rate, and the read-only guarantee - nothing but a
GET leaves this card except the token exchange and createReport. The seller and their goods are invented."""
import gzip, io, json, shutil, unittest, zipfile
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
        # a seller app holds no Amazon Business role: the reconciliation API refuses it, as Amazon does
        if 'business-api' in url: return _resp(403, {'errors': [{'code': 'Unauthorized', 'message': 'Access to requested resource is denied.'}]})
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
        self.assertIn(('GET', 'https://sellingpartnerapi-na.amazon.com/sellers/v1/marketplaceParticipations'), f.calls)

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


KEY = {'orderId': '113-0000001-0000001', 'orderLineItemId': 'L1', 'shipmentId': 'S1'}
LINE = {**KEY, 'asin': 'B0TEST0001', 'productTitle': 'Northwind mug', 'itemQuantity': 2, 'unitPrice': {'amount': 12.99, 'currencyCode': 'USD'},
        'totalAmount': {'amount': 25.98, 'currencyCode': 'USD'}, 'tax': {'amount': 2.08, 'currencyCode': 'USD'}, 'purchaseOrderNumber': 'PO-1001'}
CHARGE = {'transactionId': 'T1', 'transactionDate': '2026-10-20T10:00:00Z', 'transactionType': 'CHARGE',
          'amount': {'amount': 28.06, 'currencyCode': 'USD'}, 'legalEntityName': 'Northwind', 'transactionLineItems': [LINE]}
REFUND = {'transactionId': 'T2', 'transactionDate': '2026-10-25T09:00:00Z', 'transactionType': 'REFUND',
          'amount': {'amount': -14.03, 'currencyCode': 'USD'}, 'legalEntityName': 'Northwind', 'transactionLineItems': [{**LINE, 'itemQuantity': 1}]}
# one order line, invoiced once and credited twice: a refund belongs to the credit memo nearest its own date
DETAILS = [{'invoiceNumber': 'INV-1', 'invoiceDate': '2026-10-20T00:00:00Z', 'invoiceType': 'STANDARD'},
           {'invoiceNumber': 'CM-1', 'invoiceDate': '2026-10-21T00:00:00Z', 'invoiceType': 'CREDIT_MEMO'},
           {'invoiceNumber': 'CM-2', 'invoiceDate': '2026-10-25T00:00:00Z', 'invoiceType': 'CREDIT_MEMO'}]


class FakeBusiness:
    """An Amazon Business buyer's app: reconciliation answers in pages, and the Selling Partner API refuses it (sp=403) - or not."""
    def __init__(self, pages=([CHARGE], [REFUND]), sp=403, business=200):
        self.pages, self.sp, self.business, self.calls, self.params, self.bodies = [list(p) for p in pages], sp, business, [], [], []

    def post(self, url, **kw): return _resp(200, {'access_token': 'Atza|tok', 'expires_in': 3600})

    def request(self, method, url, **kw):
        self.calls.append((method, url)); path = url.split('.amazon.com', 1)[1]
        if 'business-api' not in url:
            if self.sp == 403: return _resp(403, {'errors': [{'code': 'Unauthorized', 'message': 'Access to requested resource is denied.'}]})
            return FakeAmazon().request(method, url, **kw)
        if self.business != 200: return _resp(self.business, {'errors': [{'code': 'Unauthorized', 'message': 'denied'}]})
        if method == 'GET' and path == f'{amz.RECON}/transactions':
            self.params.append(dict(kw['params']))
            i = int(kw['params'].get('nextPageToken', 'p0')[1:])
            return _resp(200, {'transactions': self.pages[i] if i < len(self.pages) else [],
                               **({'nextPageToken': f'p{i + 1}'} if i + 1 < len(self.pages) else {})})
        if method == 'POST' and path == f'{amz.RECON}/invoices':
            body = json.loads(kw['data']); self.bodies.append(body)
            return _resp(200, {'invoiceDetailsByOrderLineItems': [{'orderLineItem': li, 'invoiceDetails': DETAILS if li == KEY else
                                                                   [{'invoiceNumber': f"INV-{li['orderLineItemId']}", 'invoiceDate': '2026-10-20T00:00:00Z',
                                                                     'invoiceType': 'STANDARD'}]} for li in body['orderLineItems']]})
        raise AssertionError(f'unexpected call {method} {path}')

    def patch(self): return mock.patch.multiple(amz.requests, post=self.post, request=self.request)


class Business(Base):
    NOW = amz.datetime(2026, 10, 30, 15, 0, tzinfo=amz.timezone.utc)

    def test_the_feed_window_follows_the_date_rules(self):
        w = lambda **c: amz.feed_window(c, now=self.NOW)
        self.assertEqual(w(), ('2026-10-23T00:00:00Z', '2026-10-30T14:58:00Z'))              # 7 days, ending two minutes ago
        self.assertEqual(w(days=1), ('2026-10-29T00:00:00Z', '2026-10-30T14:58:00Z'))
        self.assertEqual(w(start='2026-10-01'), ('2026-10-01T00:00:00Z', '2026-10-08T23:59:59Z'))   # a past end is that day's last second
        self.assertEqual(w(end='2026-10-10'), ('2026-10-03T00:00:00Z', '2026-10-10T23:59:59Z'))
        self.assertEqual(w(start='2026-10-28'), ('2026-10-28T00:00:00Z', '2026-10-30T14:58:00Z'))   # never past now
        self.assertEqual(w(start='2026-10-01', end='2026-10-30'), ('2026-10-01T00:00:00Z', '2026-10-30T14:58:00Z'))
        with self.assertRaises(amz.AmazonError): w(start='2026-10-20', end='2026-10-10')
        with self.assertRaises(amz.AmazonError): w(start='last tuesday')

    def test_transactions_page_on_the_token_alone_to_the_last_page(self):
        f = FakeBusiness(pages=([CHARGE], [REFUND], [{**CHARGE, 'transactionId': 'T3'}]))
        with f.patch(): txs = amz.transactions(CFG, '2026-10-01T00:00:00Z', '2026-10-08T23:59:59Z')
        self.assertEqual([t['transactionId'] for t in txs], ['T1', 'T2', 'T3'])
        self.assertEqual(f.params, [{'feedStartDate': '2026-10-01T00:00:00Z', 'feedEndDate': '2026-10-08T23:59:59Z', 'pageSize': 100},
                                    {'nextPageToken': 'p1'}, {'nextPageToken': 'p2'}])
        self.assertTrue(all(u.startswith('https://na.business-api.amazon.com/') for _, u in f.calls))

    def test_the_region_picks_the_business_host(self):
        f = FakeBusiness(pages=([],))
        with f.patch(): amz.transactions({**CFG, 'region': 'fe'}, 'a', 'b')
        self.assertTrue(f.calls[0][1].startswith('https://jp.business-api.amazon.com/reconciliation/2021-01-08/transactions'))

    def test_an_errors_list_in_a_200_is_a_refusal(self):
        with mock.patch.multiple(amz.requests, post=FakeBusiness().post,
                                 request=lambda *a, **k: _resp(200, {'errors': [{'code': 'InvalidInput', 'message': 'bad feedEndDate'}]})):
            with self.assertRaises(amz.AmazonError) as e: amz.transactions(CFG, 'a', 'b')
        self.assertIn('bad feedEndDate', str(e.exception))

    def test_a_charge_takes_its_invoice_and_a_refund_the_nearest_credit_memo(self):
        self.assertEqual(amz.pick_invoice('CHARGE', DETAILS, '2026-10-20T10:00:00Z'), {'invoiceNumber': 'INV-1', 'invoiceDate': '2026-10-20T00:00:00Z'})
        self.assertEqual(amz.pick_invoice('REFUND', DETAILS, '2026-10-25T09:00:00Z'),
                         {'invoiceNumber': 'CM-2', 'invoiceDate': '2026-10-25T00:00:00Z', 'originalInvoiceNumber': 'INV-1'})
        self.assertEqual(amz.pick_invoice('OVERREFUND', DETAILS, '2026-10-21T12:00:00Z')['invoiceNumber'], 'CM-1')
        self.assertEqual(amz.pick_invoice('REFUND', DETAILS[:1], '2026-10-25'), {'originalInvoiceNumber': 'INV-1'})    # no memo yet
        self.assertEqual(amz.pick_invoice('CHARGE', []), {})

    def test_invoices_are_asked_25_lines_at_a_time_and_only_for_whole_lines(self):
        lines = [{**KEY, 'orderLineItemId': f'L{i}'} for i in range(30)] + [{**KEY, 'shipmentId': ''}, {**KEY, 'orderLineItemId': 'L0'}]
        f = FakeBusiness()
        with f.patch(): got = amz.invoices(CFG, lines)
        self.assertEqual([len(b['orderLineItems']) for b in f.bodies], [25, 5])       # the duplicate and the line with no shipment are not asked
        self.assertEqual(got[('113-0000001-0000001', 'L7', 'S1')][0]['invoiceNumber'], 'INV-L7')

    def test_the_report_flattens_lines_and_names_their_invoices(self):
        f = FakeBusiness()
        with f.patch(): head, body = amz.run_amazon_business_transactions({**CFG, 'days': 14})
        rows = [json.loads(l) for l in body.splitlines()]
        self.assertTrue(head.startswith('2 rows') and '2 transaction(s)' in head and 'Amazon Business transactions' in head, head)
        c, r = rows
        self.assertEqual((c['transactionType'], c['amount'], c['currency'], c['legalEntityName'], c['asin'], c['itemQuantity'], c['unitPrice'],
                          c['totalAmount'], c['tax'], c['orderId'], c['purchaseOrderNumber'], c['invoiceNumber']),
                         ('CHARGE', 28.06, 'USD', 'Northwind', 'B0TEST0001', 2, 12.99, 25.98, 2.08, '113-0000001-0000001', 'PO-1001', 'INV-1'))
        self.assertEqual((r['transactionType'], r['invoiceNumber'], r['originalInvoiceNumber']), ('REFUND', 'CM-2', 'INV-1'))
        self.assertEqual(len(f.bodies), 1)

    def test_invoices_off_asks_no_invoice_and_no_transactions_asks_nothing_more(self):
        f = FakeBusiness()
        with f.patch(): _, body = amz.run_amazon_business_transactions({**CFG, 'invoices': 'no'})
        self.assertEqual(f.bodies, []); self.assertNotIn('INV-1', body)
        f = FakeBusiness(pages=([],))
        with f.patch(): head, body = amz.run_amazon_business_transactions(CFG)
        self.assertEqual((f.bodies, body), ([], '')); self.assertIn('0 transaction(s)', head)

    def test_the_kind_is_a_read_on_the_amazon_card(self):
        self.assertIn('amazon_business_transactions', reports.REGISTRY)
        self.assertEqual((scopes.needs('amazon_business_transactions'), reports.card_of('amazon_business_transactions')), ('read', 'amazon_sp'))
        f = FakeBusiness()
        with f.patch(): amz.run_amazon_business_transactions(CFG)
        self.assertEqual({(m, u.split('.amazon.com')[1].split('?')[0]) for m, u in f.calls if m != 'GET'}, {('POST', f'{amz.RECON}/invoices')})


class ApiDots(Base):
    def test_a_business_only_app_passes_test_naming_the_api_that_answered(self):
        with FakeBusiness(sp=403).patch(): detail, apis = amz.probe_apis(CFG)
        self.assertEqual(apis, ['business'])
        self.assertIn('Amazon Business reconciliation ✓', detail); self.assertIn('Seller reports (SP-API) ✗', detail)
        self.assertIn('(403)', detail)

    def test_a_seller_only_app_passes_naming_sp(self):
        with FakeAmazon().patch(): detail, apis = amz.probe_apis(CFG)
        self.assertEqual(apis, ['sp']); self.assertIn('Seller reports (SP-API) ✓', detail)
        self.assertIn('Business Purchase Reconciliation role', detail)

    def test_both_answering_fills_both_dots(self):
        with FakeBusiness(sp=200).patch(): _, apis = amz.probe_apis(CFG)
        self.assertEqual(apis, ['sp', 'business'])

    def test_neither_answering_fails_and_says_why_for_each(self):
        with FakeBusiness(sp=403, business=403).patch(), self.assertRaises(amz.AmazonError) as e: amz.probe_apis(CFG)
        self.assertIn('Seller reports (SP-API):', str(e.exception)); self.assertIn('Amazon Business reconciliation:', str(e.exception))

    def test_the_card_test_saves_the_dots_that_answered(self):
        from taskuary import channels
        s = MemoryStore(); c = s.get_connector_by_type('amazon_sp')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Secret': 'Atzr|test',
                          'ConfigJson': json.dumps({k: v for k, v in CFG.items() if k != 'refresh_token'} | {'apis': ['sp']})}, 'owner')
        with FakeBusiness(sp=403).patch(): r = channels.test_connector(s, c['ConnectorId'])
        self.assertTrue(r['ok'], r); self.assertEqual(r['apis'], ['business'])
        saved = json.loads(s.get_connector(c['ConnectorId'], with_secret=True)['ConfigJson'])
        self.assertEqual((saved['apis'], saved['client_secret'], saved['region']), (['business'], 'cs-test', 'na'))


def _pdf(tag): return b'%PDF-1.4\n% ' + tag.encode() + b'\n%%EOF\n'


def _zip(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        for n, d in files: z.writestr(n, d)
    return b.getvalue()


class FakeInvoicePdf(FakeBusiness):
    """FakeBusiness that also builds invoice PDFs: createReport -> getReport (statuses) -> document -> a presigned download that is,
    as Amazon's guide says, a zip of PDFs gzipped on top - or whatever `doc` says."""
    def __init__(self, doc=None, gz=True, statuses=('IN_QUEUE', 'DONE'), **kw):
        super().__init__(**kw); self.doc, self.gz, self.statuses, self.created, self.downloads = doc, gz, list(statuses), [], 0

    def request(self, method, url, **kw):
        path = url.split('.amazon.com', 1)[1]
        if not path.startswith(amz.BREPORTS): return super().request(method, url, **kw)
        self.calls.append((method, url))
        if method == 'POST' and path == f'{amz.BREPORTS}/reports': self.created.append(json.loads(kw['data'])); return _resp(202, {'reportId': 'P1'})
        if path == f'{amz.BREPORTS}/reports/P1':
            st = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return _resp(200, {'reportId': 'P1', 'processingStatus': st, **({'reportDocumentId': 'PD1'} if st == 'DONE' else {})})
        if path == f'{amz.BREPORTS}/documents/PD1':
            return _resp(200, {'reportDocumentId': 'PD1', 'url': 'https://tortuga-prod.s3.example/pdf?sig=x', **({'compressionAlgorithm': 'GZIP'} if self.gz else {})})
        raise AssertionError(f'unexpected call {method} {path}')

    def get(self, url, **kw):
        self.calls.append(('DOWNLOAD', url)); self.downloads += 1; assert 'headers' not in kw
        n = self.created[-1]['reportOptions']['invoiceId']
        doc = self.doc if self.doc is not None else _zip([('summary.pdf', _pdf('summary')), (f'Invoice_{n.replace("-", "")}.pdf', _pdf(n)),
                                                          ('Invoice_OTHER-9.pdf', _pdf('other'))])
        return _resp(200, content=gzip.compress(doc) if self.gz else doc)

    def patch(self): return mock.patch.multiple(amz.requests, post=self.post, request=self.request, get=self.get)


class PdfBase(Base):
    """No PDF left on disk from another test, and a clock that moves only when the code sleeps - 120s of polling in no time."""
    def setUp(self):
        super().setUp(); shutil.rmtree(amz.pdf_dir(), ignore_errors=True)
        self.t = [0.0]
        p = mock.patch.multiple(amz, _sleep=lambda s: (self.slept.append(s), self.t.__setitem__(0, self.t[0] + s)), _clock=lambda: self.t[0])
        p.start(); self.addCleanup(p.stop)


class InvoicePdf(PdfBase):
    def test_an_invoice_is_asked_for_polled_every_15s_and_picked_out_of_the_zip_by_its_number(self):
        f = FakeInvoicePdf()
        with f.patch(): name, data = amz.invoice_pdf(CFG, '1111-2222-3333')
        self.assertEqual((name, data), ('Invoice_111122223333.pdf', _pdf('1111-2222-3333')))      # punctuation in the number is ignored
        self.assertEqual(f.created, [{'reportType': 'GET_AB_INVOICE_PDF', 'reportOptions': {'invoiceId': '1111-2222-3333', 'documentType': 'Invoice'},
                                      'marketplaceIds': ['ATVPDKIKX0DER']}])
        self.assertEqual(self.slept, [15])
        self.assertTrue(all(u.startswith('https://na.business-api.amazon.com/reports/2021-09-30/') for m, u in f.calls if m != 'DOWNLOAD'))

    def test_a_credit_memo_is_asked_for_as_credits(self):
        f = FakeInvoicePdf()
        with f.patch(): amz.invoice_pdf({**CFG, 'region': 'eu', 'marketplace_ids': 'A1PA6795UKMFR9'}, 'CM-2', credit=True)
        self.assertEqual(f.created[0]['reportOptions'], {'invoiceId': 'CM-2', 'documentType': 'Credits'})
        self.assertEqual(f.created[0]['marketplaceIds'], ['A1PA6795UKMFR9'])
        self.assertTrue(f.calls[0][1].startswith('https://eu.business-api.amazon.com/'))

    def test_a_plain_uncompressed_pdf_comes_back_as_it_is(self):
        with FakeInvoicePdf(doc=_pdf('only'), gz=False).patch(): self.assertEqual(amz.invoice_pdf(CFG, 'INV-1'), ('INV-1.pdf', _pdf('only')))

    def test_a_cancelled_or_fatal_pdf_is_a_failure_in_words(self):
        for st in ('CANCELLED', 'FATAL'):
            with FakeInvoicePdf(statuses=('IN_PROGRESS', st)).patch(), self.assertRaises(amz.AmazonError) as e: amz.invoice_pdf(CFG, 'INV-1')
            self.assertIn(f'invoice INV-1 ({st})', str(e.exception))

    def test_a_pdf_still_building_after_120s_gives_up(self):
        f = FakeInvoicePdf(statuses=('IN_PROGRESS',))
        with f.patch(), self.assertRaises(amz.AmazonError) as e: amz.invoice_pdf(CFG, 'INV-1')
        self.assertIn('still IN_PROGRESS after 120s', str(e.exception))
        self.assertEqual(sum(self.slept), 120); self.assertEqual(f.downloads, 0)

    def test_outside_north_america_a_marketplace_must_be_named(self):
        with mock.patch.object(amz.requests, 'request') as r, self.assertRaises(amz.AmazonError): amz.invoice_pdf({**CFG, 'region': 'eu', 'marketplace_ids': ''}, 'X')
        r.assert_not_called()

    def test_the_pdf_is_the_only_new_post_and_it_stays_read_only(self):
        f = FakeInvoicePdf()
        with f.patch(): amz.invoice_pdf(CFG, 'INV-1')
        self.assertEqual({(m, u.split('.amazon.com')[1]) for m, u in f.calls if m not in ('GET', 'DOWNLOAD')}, {('POST', '/reports/2021-09-30/reports')})
        self.assertEqual((scopes.needs('amazon_invoice_pdf'), reports.card_of('amazon_invoice_pdf')), ('read', 'amazon_sp'))

    def test_the_tool_stages_the_pdf_once_and_answers_with_its_path(self):
        f = FakeInvoicePdf()
        with f.patch():
            head, path = amz.run_amazon_invoice_pdf({**CFG, 'invoice': 'CM-2', 'credit': 'true'})
            head2, path2 = amz.run_amazon_invoice_pdf({**CFG, 'invoice': 'CM-2', 'credit': True})
        self.assertEqual(path, path2); self.assertTrue(path.endswith('Amazon credit memo CM-2.pdf'))
        self.assertEqual(open(path, 'rb').read(), _pdf('CM-2')); self.assertIn('already fetched', head2); self.assertEqual(len(f.created), 1)
        with self.assertRaises(amz.AmazonError): amz.run_amazon_invoice_pdf(CFG)


class PickPdf(unittest.TestCase):
    def test_a_zip_without_the_number_in_a_filename_is_read_for_it_or_refused(self):
        z = _zip([('a.pdf', _pdf('a')), ('b.pdf', _pdf('b'))])
        with mock.patch.object(amz, '_pdf_text', side_effect=lambda d: 'Invoice # INV-77' if d == _pdf('b') else 'nothing'):
            self.assertEqual(amz.pick_pdf(z, 'inv77'), ('b.pdf', _pdf('b')))
            with self.assertRaises(amz.AmazonError): amz.pick_pdf(z, 'INV-78')

    def test_a_zip_of_one_pdf_is_that_pdf_and_a_non_pdf_is_refused(self):
        self.assertEqual(amz.pick_pdf(gzip.compress(_zip([('doc/x.pdf', _pdf('x'))])), 'INV-1'), ('x.pdf', _pdf('x')))
        with self.assertRaises(amz.AmazonError): amz.pick_pdf(b'<html>', 'INV-1')
        with self.assertRaises(amz.AmazonError): amz.pick_pdf(_zip([('readme.txt', b'hi')]), 'INV-1')


class ReportPdfs(PdfBase):
    def test_a_run_attaches_each_invoice_and_credit_memo_once(self):
        f, sink = FakeInvoicePdf(), []
        with f.patch(): head, body = amz.run_amazon_business_transactions({**CFG, 'pdfs': 'yes', '_files': sink})
        rows = [json.loads(l) for l in body.splitlines()]
        self.assertEqual([(c['reportOptions']['invoiceId'], c['reportOptions']['documentType']) for c in f.created], [('INV-1', 'Invoice'), ('CM-2', 'Credits')])
        self.assertEqual([r['invoicePdf'] for r in rows], ['Amazon invoice INV-1.pdf', 'Amazon credit memo CM-2.pdf'])
        self.assertEqual([x['name'] for x in sink], ['Amazon invoice INV-1.pdf', 'Amazon credit memo CM-2.pdf']); self.assertIn('2 invoice PDF(s) attached', head)
        f2, sink2 = FakeInvoicePdf(), []
        with f2.patch(): amz.run_amazon_business_transactions({**CFG, 'pdfs': 'yes', '_files': sink2})
        self.assertEqual((f2.created, len(sink2)), ([], 2))         # already on disk: attached again, not asked for again

    def test_the_cap_holds_the_rest_for_the_next_run(self):
        f, sink = FakeInvoicePdf(), []
        with f.patch(): head, _ = amz.run_amazon_business_transactions({**CFG, 'pdfs': 'yes', 'pdf_cap': 1, '_files': sink})
        self.assertEqual((len(f.created), len(sink)), (1, 1)); self.assertIn('1 more next run', head)

    def test_off_by_default_and_a_preview_fetches_none(self):
        f = FakeInvoicePdf()
        with f.patch():
            head, _ = amz.run_amazon_business_transactions({**CFG, '_files': []})
            head2, _ = amz.run_amazon_business_transactions({**CFG, 'pdfs': 'yes'})
        self.assertEqual(f.created, []); self.assertNotIn('PDF', head); self.assertIn('not on a preview', head2)

    def test_a_report_run_puts_the_pdfs_on_its_message(self):
        s = MemoryStore(); c = s.get_connector_by_type('amazon_sp')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Secret': CFG['refresh_token'],
                          'ConfigJson': json.dumps({k: CFG[k] for k in ('client_id', 'client_secret', 'region')})}, 'owner')
        files = []
        with FakeInvoicePdf().patch(): reports.render_report(s, {'type': 'amazon_business_transactions', 'pdfs': 'yes'}, notes=[], files=files)
        mid = s.add_message({'TaskId': None, 'ExternalId': 'report:t', 'ConversationId': 'report:t', 'Channel': 'report', 'Subject': 'r', 'Status': 'feed'})
        from taskuary.artifacts import attach_files
        attach_files(s, mid, files)
        got = s.list_attachments(mid)
        self.assertEqual([(a['Name'], a['ContentType']) for a in got], [('Amazon invoice INV-1.pdf', 'application/pdf'), ('Amazon credit memo CM-2.pdf', 'application/pdf')])
        self.assertEqual(open(got[1]['Path'], 'rb').read(), _pdf('CM-2'))
        # one source among several hands its files to the run the same way
        more = []
        with FakeInvoicePdf().patch():
            reports.render_report(s, {'sources': [{'type': 'amazon_business_transactions', 'pdfs': 'yes'}]}, notes=[], files=more)
        self.assertEqual([f['name'] for f in more], ['Amazon invoice INV-1.pdf', 'Amazon credit memo CM-2.pdf'])


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
