"""Unsubscribe on an FYI (the owner, 2026-10-22): the list's own headers say how to leave it (RFC 2369 List-Unsubscribe, RFC 8058
one-click); ingest keeps that, the FYI item carries it to its card, and the owner's press - never an agent's - leaves the list."""
import email, json, time, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import funnel, guard, ingest, server, unsubscribe
from taskuary.channels import _header_marks
from taskuary.imapmail import protocol_marks
from taskuary.store import MemoryStore

c = TestClient(server.app)
AGENT = {'X-Taskuary-Token': server.cfg['server']['agent_token']}
HTTPS, MAILTO = 'https://lists.vendor.example/u/abc', 'mailto:leave@vendor.example?subject=unsubscribe'
FYI = lambda system, user, **k: json.dumps({'intent': 'fyi', 'why': 'a newsletter', 'title': 'September deals', 'summary': 's', 'sender_class': 'bulk'})


def raw(head): return email.message_from_string(f'{head}\n\nDeals.')


def _ingest(s, unsub, ext='g:news'):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'subject': 'September deals', 'from_email': 'news@vendor.example',
                                         'from_name': 'Vendor news', 'body': 'Deals.', 'source_name': 'alex@northwind.example',
                                         'sender_class': 'bulk', **({'unsub': unsub} if unsub else {})}, llm=FYI)['message_id']


class ParseTests(unittest.TestCase):
    def test_one_click_needs_https_and_the_post_header(self):
        both = f'List-Unsubscribe: <{MAILTO}>,\n <{HTTPS}>'
        self.assertEqual(unsubscribe.parse(raw(both + '\nList-Unsubscribe-Post: List-Unsubscribe=One-Click')),
                         {'via': 'post', 'url': HTTPS, 'mailto': MAILTO})
        self.assertEqual(unsubscribe.parse(raw(both))['via'], 'url')                         # no Post header: a page to finish on
        self.assertEqual(unsubscribe.parse(raw('List-Unsubscribe: <http://lists.vendor.example/u>\nList-Unsubscribe-Post: List-Unsubscribe=One-Click'))['via'],
                         'url')                                                               # RFC 8058 is https only
        self.assertEqual(unsubscribe.parse(raw(f'List-Unsubscribe: <{MAILTO}>')), {'via': 'mailto', 'mailto': MAILTO})

    def test_no_header_or_no_usable_link_offers_nothing(self):
        for h in ('Subject: Unsubscribe me please', 'List-Unsubscribe: please write to us', 'List-Unsubscribe: <javascript:alert(1)>'):
            with self.subTest(h=h): self.assertIsNone(unsubscribe.parse(raw(h)))

    def test_both_connectors_read_it(self):
        self.assertEqual(protocol_marks(raw(f'List-Unsubscribe: <{HTTPS}>'))['unsub'], {'via': 'url', 'url': HTTPS})
        g = {'internetMessageHeaders': [{'name': 'List-Unsubscribe', 'value': f'<{HTTPS}>'},
                                        {'name': 'List-Unsubscribe-Post', 'value': 'List-Unsubscribe=One-Click'}]}
        self.assertEqual(_header_marks(g)['unsub'], {'via': 'post', 'url': HTTPS})


class ItemTests(unittest.TestCase):
    def test_ingest_keeps_it_and_the_fyi_item_carries_it(self):
        s = MemoryStore(); mid = _ingest(s, {'via': 'post', 'url': HTTPS})
        self.assertEqual(unsubscribe.of(s.get_message(mid)), {'via': 'post', 'url': HTTPS})
        item = next(i for i in funnel.from_feed(s, s.feed(limit=10)) if i['mid'] == mid)
        self.assertEqual((item['lane'], item['unsub']), ('fyi', 'post'))
        from taskuary.concierge import card_for
        self.assertEqual(card_for(item)['unsub'], 'post')

    def test_a_mail_with_no_list_header_offers_nothing(self):
        s = MemoryStore(); mid = _ingest(s, None)
        item = next(i for i in funnel.from_feed(s, s.feed(limit=10)) if i['mid'] == mid)
        self.assertNotIn('unsub', item)


class RunTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.p = mock.patch.object(server, 'store', self.s); self.p.start(); self.addCleanup(self.p.stop)

    def test_one_click_posts_rfc_8058_and_the_item_stops_offering_it(self):
        mid = _ingest(self.s, {'via': 'post', 'url': HTTPS})
        with mock.patch.object(unsubscribe, '_post', return_value=mock.Mock(status_code=200)) as p:
            r = c.post(f'/api/messages/{mid}/unsubscribe', json={})
        self.assertEqual((r.status_code, r.json()), (200, {'via': 'post'}))
        p.assert_called_once_with(HTTPS)
        self.assertNotIn('unsub', next(i for i in funnel.from_feed(self.s, self.s.feed(limit=10)) if i['mid'] == mid))

    def test_the_post_itself_is_rfc_8058s_and_follows_no_redirect(self):
        with mock.patch('taskuary.webguard.check_url') as g, mock.patch('requests.post', return_value=mock.Mock(status_code=200)) as p:
            unsubscribe._post(HTTPS)
        g.assert_called_once_with(HTTPS)
        p.assert_called_once_with(HTTPS, data={'List-Unsubscribe': 'One-Click'}, timeout=20, allow_redirects=False)

    def test_a_list_pointing_at_this_machine_is_refused_and_nothing_is_marked(self):
        mid = _ingest(self.s, {'via': 'post', 'url': 'https://127.0.0.1/u'})
        with mock.patch('requests.post') as p:
            r = c.post(f'/api/messages/{mid}/unsubscribe', json={})
        self.assertEqual(r.status_code, 502); p.assert_not_called()
        self.assertNotIn('done', unsubscribe.of(self.s.get_message(mid)))

    def test_a_refused_post_says_so_and_stays_offered(self):
        mid = _ingest(self.s, {'via': 'post', 'url': HTTPS})
        with mock.patch.object(unsubscribe, '_post', return_value=mock.Mock(status_code=500)):
            r = c.post(f'/api/messages/{mid}/unsubscribe', json={})
        self.assertEqual(r.status_code, 502); self.assertIn('500', r.json()['detail'])
        self.assertEqual(next(i for i in funnel.from_feed(self.s, self.s.feed(limit=10)) if i['mid'] == mid)['unsub'], 'post')

    def test_no_one_click_hands_back_the_link_and_opens_it_in_the_app(self):
        mid = _ingest(self.s, {'via': 'mailto', 'mailto': MAILTO})
        r = c.post(f'/api/messages/{mid}/unsubscribe', json={})
        self.assertEqual(r.json(), {'via': 'mailto', 'link': MAILTO})
        mid2 = _ingest(self.s, {'via': 'url', 'url': HTTPS}, ext='g:news2')
        with mock.patch('webbrowser.open') as o:
            r = c.post(f'/api/messages/{mid2}/unsubscribe', json={'open': True})
            for _ in range(100):
                if o.called: break
                time.sleep(.02)
        self.assertEqual(r.json(), {'via': 'url', 'link': HTTPS, 'opened': True}); o.assert_called_once_with(HTTPS)

    def test_only_the_owner_presses_it(self):
        mid = _ingest(self.s, {'via': 'post', 'url': HTTPS})
        stranger = {'X-Taskuary-Token': guard.stranger_token(server.cfg['server'], 7)}
        with mock.patch.object(unsubscribe, '_post') as p:
            for h in (AGENT, stranger): self.assertEqual(c.post(f'/api/messages/{mid}/unsubscribe', json={}, headers=h).status_code, 403)
        p.assert_not_called()

    def test_a_message_with_no_way_off_is_422(self):
        self.assertEqual(c.post(f'/api/messages/{_ingest(self.s, None)}/unsubscribe', json={}).status_code, 422)


if __name__ == '__main__': unittest.main()
