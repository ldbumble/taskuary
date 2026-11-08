"""SOURCES THAT ARE ALSO KEYED READS (inboxes.py over apireads.get): one card's key brings work in and serves reports and agents. HTTP
faked by URL with payloads shaped like each vendor's own API reference - no network. Customers, commenters and posters from outside
are strangers until the owner trusts them (senders._item_known, H2); an order carries no author at all."""
import json, unittest
from unittest import mock

from taskuary import apireads, channels, inboxes, reports, store as store_mod
from taskuary.store import MemoryStore
from tests.test_inboxes import FakeHTTP, SINCE, rows, trusted


class Fake(FakeHTTP):
    post = lambda self, url, **kw: self.request('post', url, **kw)


def wired(routes):
    inboxes._MEMO.clear()
    return mock.patch.object(apireads, 'requests', Fake(routes))


def conn(s, typ, cfg, key='tok'):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': key, 'Active': 1, 'ConfigJson': json.dumps(cfg)}, 't')
    return s.get_connector(cid, with_secret=True)


class OneCardTwoRoles(unittest.TestCase):
    def test_each_source_is_a_read_too_and_tests_as_a_source(self):
        both = set(inboxes.TYPES) & set(apireads.types())
        self.assertTrue({'woocommerce', 'bigcommerce'} <= both)
        for t in both:
            self.assertEqual(store_mod.DEFAULT_ROLES[t], 'trigger,report,tool', t)
            self.assertEqual(reports.card_of(f'{t}_read'), t)


class CommerceTests(unittest.TestCase):
    def test_woocommerce_processing_orders_carry_no_author(self):
        s = MemoryStore(); c = conn(s, 'woocommerce', {'host': 'https://shop.northwind.example', 'consumer_key': 'ck_1'})
        o = {'id': 727, 'number': '727', 'status': 'processing', 'currency': 'USD', 'total': '29.35', 'date_modified_gmt': '2026-08-20T14:00:00',
             'billing': {'first_name': 'Pat', 'last_name': 'Buyer', 'email': 'pat@vendor.example'}, 'customer_note': 'gift wrap please',
             'line_items': [{'name': 'Mug', 'quantity': 2}]}
        with wired({'/wp-json/wc/v3/orders': [o]}) as h:
            self.assertIn('processing', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, c, SINCE), 1)
        self.assertEqual((h.calls[-1][2]['params']['status'], h.calls[-1][2]['allow_redirects']), ('processing', False))
        self.assertTrue(h.calls[-1][2]['headers']['Authorization'].startswith('Basic '))
        r = rows(s, 'woocommerce')[0]
        self.assertEqual((r['Subject'], r['FromName'], r['SourceLink']),
                         ('Order #727 to ship', 'Pat Buyer', 'https://shop.northwind.example/wp-admin/post.php?post=727&action=edit'))
        self.assertIn('2 × Mug', r['BodyText']); self.assertFalse(trusted(s, r))

    def test_bigcommerce_awaiting_fulfillment_and_an_empty_answer(self):
        s = MemoryStore(); c = conn(s, 'bigcommerce', {'store_hash': 'abc123'})
        o = {'id': 100, 'status': 'Awaiting Fulfillment', 'status_id': 11, 'total_inc_tax': '45.0000', 'currency_code': 'USD', 'items_total': 3,
             'date_modified': 'Thu, 20 Aug 2026 14:00:00 +0000', 'customer_message': 'leave at the door',
             'billing_address': {'first_name': 'Pat', 'last_name': 'Buyer', 'email': 'pat@vendor.example'}}
        with wired({'/stores/abc123/v2/store': {'id': 'abc123', 'name': 'Northwind Goods'}, '/stores/abc123/v2/orders': [o]}) as h:
            self.assertIn('Northwind Goods', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, c, SINCE), 1)
        self.assertEqual((h.calls[-1][2]['headers']['X-Auth-Token'], h.calls[-1][2]['params']['status_id']), ('tok', 11))
        r = rows(s, 'bigcommerce')[0]
        self.assertEqual((r['Subject'], r['SourceLink']), ('Order 100 to fulfil', 'https://store-abc123.mybigcommerce.com/manage/orders/100'))
        self.assertFalse(trusted(s, r))
        with wired({'/stores/abc123/v2/orders': ''}): self.assertEqual(inboxes.poll(s, c, SINCE), 0)
        with wired({'/stores/abc123/v2/store': {'name': 'Northwind Goods'}}):
            self.assertTrue(channels.test_connector(s, c['ConnectorId'])['ok'])


if __name__ == '__main__':
    unittest.main()
