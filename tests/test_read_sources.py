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
        self.assertEqual(both, {'woocommerce', 'bigcommerce', 'instagram', 'facebook_pages', 'x', 'wordpress',
                                # ...and the ones that sign in by OAuth or push (tests/test_oauth_sources.py)
                                'webex', 'zoom_chat', 'threads', 'hubspot', 'salesforce', 'docusign', 'basecamp_todos', 'mailgun', 'line', 'sendgrid'})
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


class SocialTests(unittest.TestCase):
    "Everyone who comments, writes to a Page or mentions you is an outsider: a stranger until the owner trusts them."
    def test_instagram_comments_but_not_your_own_replies(self):
        s = MemoryStore(); c = conn(s, 'instagram', {'ig_user_id': '17841400000000001'})
        media = {'data': [{'id': 'm1', 'caption': 'New mugs are in', 'permalink': 'https://www.instagram.com/p/abc/', 'timestamp': '2026-08-20T10:00:00+0000',
                           'comments': {'data': [{'id': 'k1', 'text': 'Do you ship to Canada?', 'username': 'pat_buys', 'timestamp': '2026-08-20T11:00:00+0000'},
                                                 {'id': 'k2', 'text': 'We do!', 'username': 'northwind', 'timestamp': '2026-08-20T11:05:00+0000'}]}}]}
        with wired({'/17841400000000001/media': media, '/17841400000000001': {'username': 'northwind', 'id': '17841400000000001'}}) as h:
            self.assertIn('@northwind', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, s.get_connector(c['ConnectorId'], with_secret=True), SINCE), 1)
        self.assertEqual(h.calls[-1][2]['headers']['Authorization'], 'Bearer tok')
        r = rows(s, 'instagram')[0]
        self.assertEqual((r['Subject'], r['SourceLink']), ('@pat_buys commented on your post', 'https://www.instagram.com/p/abc/'))
        self.assertFalse(trusted(s, r))

    def test_facebook_page_comments_and_messages_whose_last_word_is_not_the_pages(self):
        s = MemoryStore(); c = conn(s, 'facebook_pages', {'page_id': '1001'})
        feed = {'data': [{'id': '1001_5', 'message': 'Open late on Friday', 'permalink_url': 'https://www.facebook.com/1001/posts/5',
                          'comments': {'data': [{'id': 'c1', 'message': 'Until when?', 'from': {'id': '77', 'name': 'Pat Buyer'}, 'created_time': '2026-08-20T10:00:00+0000'},
                                                {'id': 'c2', 'message': 'Until 10.', 'from': {'id': '1001', 'name': 'Northwind'}, 'created_time': '2026-08-20T10:05:00+0000'}]}}]}
        convs = {'data': [{'id': 't_1', 'link': '/northwind/inbox/1', 'updated_time': '2026-08-20T12:00:00+0000',
                           'messages': {'data': [{'id': 'mid.1', 'message': 'Is the order ready?', 'from': {'id': '78', 'name': 'Sam Shopper'},
                                                  'created_time': '2026-08-20T12:00:00+0000'}]}},
                          {'id': 't_2', 'updated_time': '2026-08-20T12:00:00+0000',
                           'messages': {'data': [{'id': 'mid.2', 'message': 'Thanks!', 'from': {'id': '1001'}, 'created_time': '2026-08-20T12:00:00+0000'}]}}]}
        with wired({'/1001/feed': feed, '/1001/conversations': convs, '/1001': {'name': 'Northwind', 'id': '1001'}}):
            self.assertIn('Northwind', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, c, SINCE), 2)
        got = {r['Subject']: r for r in rows(s, 'facebook_pages')}
        self.assertEqual(set(got), {"Pat Buyer commented on your Page's post", 'Message from Sam Shopper to your Page'})
        self.assertEqual(got['Message from Sam Shopper to your Page']['SourceLink'], 'https://www.facebook.com/northwind/inbox/1')
        self.assertFalse(any(trusted(s, r) for r in got.values()))

    def test_x_mentions_with_their_authors(self):
        s = MemoryStore(); c = conn(s, 'x', {'username': 'northwind'})
        with wired({'/users/by/username/northwind': {'data': {'id': '42', 'name': 'Northwind', 'username': 'northwind'}},
                    '/users/42/mentions': {'data': [{'id': '9001', 'text': '@northwind is the shop open Sunday?', 'author_id': '7', 'conversation_id': '9001',
                                                     'created_at': '2026-08-20T10:00:00.000Z'}],
                                           'includes': {'users': [{'id': '7', 'name': 'Pat Buyer', 'username': 'patbuys'}]}, 'meta': {'result_count': 1}}}) as h:
            inboxes.test(s, c)
            self.assertEqual(inboxes.poll(s, s.get_connector(c['ConnectorId'], with_secret=True), SINCE), 1)
        self.assertGreaterEqual(h.calls[-1][2]['params']['max_results'], 5)
        r = rows(s, 'x')[0]
        self.assertEqual((r['FromName'], r['SourceLink']), ('Pat Buyer (@patbuys)', 'https://x.com/patbuys/status/9001'))
        self.assertFalse(trusted(s, r))

    def test_wordpress_held_comments_and_a_user_who_may_not_moderate(self):
        s = MemoryStore(); c = conn(s, 'wordpress', {'host': 'blog.northwind.example', 'user': 'alex'})
        held = [{'id': 31, 'post': 12, 'author': 0, 'author_name': 'Pat Buyer', 'author_email': 'pat@vendor.example', 'status': 'hold',
                 'date_gmt': '2026-08-20T10:00:00', 'content': {'rendered': '<p>Great post - is there a part two?</p>'}}]
        me = {'id': 1, 'name': 'Alex Doyle', 'capabilities': {'moderate_comments': True}}
        with wired({'/wp-json/wp/v2/users/me': me, '/wp-json/wp/v2/comments': held}) as h:
            self.assertIn('Alex Doyle', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, c, SINCE), 1)
        self.assertEqual((h.calls[-1][2]['params']['status'], h.calls[-1][1]), ('hold', 'https://blog.northwind.example/wp-json/wp/v2/comments'))
        r = rows(s, 'wordpress')[0]
        self.assertEqual(r['SourceLink'], 'https://blog.northwind.example/wp-admin/comment.php?action=editcomment&c=31')
        self.assertIn('part two', r['BodyText']); self.assertNotIn('<p>', r['BodyText']); self.assertFalse(trusted(s, r))
        with wired({'/wp-json/wp/v2/users/me': {'id': 2, 'name': 'Gail Moreno', 'capabilities': {'read': True}}}), \
                self.assertRaisesRegex(RuntimeError, 'may not moderate'):
            inboxes.test(s, c)
if __name__ == '__main__':
    unittest.main()
