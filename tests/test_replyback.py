"""REPLYING BACK on the sources that file work (inboxes.REPLY - the owner, 2026-11-08: "do replying back new source as well we will need
that"): a pressed Send goes to the vendor's own thread, through the card the item came in on. HTTP is faked by URL with answers shaped
like each vendor's API reference - no network. Per source: the right endpoint, the text, and the threading id; the card's Replies
switch (off for a public post until the owner opts in) refuses with the way to the card; a card not connected, or a key that may not
write, is Not sent with Reconnect - never "delivery unknown"; a 5xx stays unknown, and nothing is sent twice."""
import json, unittest
from datetime import datetime
from unittest import mock
import requests as real_requests

from taskuary import apireads, inboxes, outbound, verdicts
from taskuary.store import MemoryStore

TEXT = 'Thanks - the export is fixed now.'
REV = '@0123456789ab'                                  # ingest.rev_id's suffix: the item at one revision


class R:
    def __init__(self, j, status=200): self._j, self.status_code, self.text = j, status, json.dumps(j)
    def json(self): return self._j
    def raise_for_status(self):
        if self.status_code >= 400: raise real_requests.HTTPError(str(self.status_code), response=self)


class FakeHTTP:
    """Route by URL substring, longest first; a list answers in turn. An unexpected call fails instead of reaching the network."""
    RequestException, HTTPError = real_requests.RequestException, real_requests.HTTPError
    def __init__(self, routes): self.routes, self.calls = routes, []
    def request(self, method, url, **kw):
        self.calls.append((method.lower(), url, kw))
        for k in sorted(self.routes, key=len, reverse=True):
            if k in url:
                v = self.routes[k]
                v = v.pop(0) if isinstance(v, list) else v
                return v if isinstance(v, R) else R(v)
        raise AssertionError(f'unexpected url: {url}')
    get = lambda self, url, **kw: self.request('get', url, **kw)
    post = lambda self, url, **kw: self.request('post', url, **kw)


def card(s, t, cfg=None, **kw):
    cid = s.get_connector_by_type(t)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1, 'ConfigJson': json.dumps(cfg or {}), **kw}, 't')
    return s.get_connector(cid, with_secret=True)


def msg(t, id, conv=None, link='', author=None, head='an item', email='pat@vendor.example', at=None, subject='The export'):
    return {'Channel': t, 'ExternalId': f'{t}:{id}{REV}', 'ConversationId': f'{t}:{conv or id}', 'SourceLink': link, 'FromName': 'Pat Vendor',
            'FromEmail': email, 'Subject': subject, 'BodyText': f'[{head}]\nIt broke again.', 'SentAt': at or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'MailMetaJson': json.dumps({'author': f'{t}:{author}'} if author else {}), 'SourceName': ''}


def send(s, m, routes, reads=None):
    """reply_to_message on the fake: (receipt, every call made). OAuth cards spend a token the test hands them."""
    http, rd = FakeHTTP(routes), FakeHTTP(reads or {})
    inboxes._MEMO.clear()
    with mock.patch.object(inboxes, 'requests', http), mock.patch.object(apireads, 'requests', rd), \
            mock.patch('taskuary.oauth.access', return_value='oauth-tok'):
        return outbound.reply_to_message(s, m, TEXT), http.calls


AC = 'AC' + '0' * 32
SYS = 'a' * 32
# type, card config, message, routes, (method, url of the write), what the write must carry
CASES = [
    ('zendesk', {'subdomain': 'northwind', 'email': 'alex@northwind.example'}, msg('zendesk', 42), {'/tickets/42.json': {'audit': {'id': 9}}},
     ('put', 'https://northwind.zendesk.com/api/v2/tickets/42.json'), ['"public": true']),
    ('freshdesk', {'domain': 'northwind'}, msg('freshdesk', 42), {'/tickets/42/reply': {'id': 3}},
     ('post', 'https://northwind.freshdesk.com/api/v2/tickets/42/reply'), []),
    ('intercom', {'me_id': '99'}, msg('intercom', '1234'), {'/conversations/1234/reply': {'id': 'p1'}},
     ('post', 'https://api.intercom.io/conversations/1234/reply'), ['"admin_id": "99"', '"message_type": "comment"']),
    ('servicenow', {'instance': 'northwind', 'username': 'alex'}, msg('servicenow', f'incident:{SYS}'), {f'/incident/{SYS}': {'result': {'number': 'INC1'}}},
     ('patch', f'https://northwind.service-now.com/api/now/table/incident/{SYS}'), ['"comments"']),
    ('shortcut', {}, msg('shortcut', 77), {'/stories/77/comments': {'id': 1}}, ('post', 'https://api.app.shortcut.com/api/v3/stories/77/comments'), []),
    ('wrike', {}, msg('wrike', 'IEAAAAAA'), {'/tasks/IEAAAAAA/comments': {'data': [{'id': 'c1'}]}},
     ('post', 'https://www.wrike.com/api/v4/tasks/IEAAAAAA/comments'), []),
    ('smartsheet', {}, msg('smartsheet', '111:222'), {'/rows/222/discussions': {'result': {'id': 5}}},
     ('post', 'https://api.smartsheet.com/2.0/sheets/111/rows/222/discussions'), []),
    ('airtable', {'base_id': 'appX', 'table': 'Requests'}, msg('airtable', 'recABC'), {'/recABC/comments': {'id': 'com1'}},
     ('post', 'https://api.airtable.com/v0/appX/Requests/recABC/comments'), []),
    ('github_projects', {'replies': True}, msg('github_projects', 'PVTI_1'),
     {'graphql': [{'data': {'node': {'content': {'__typename': 'Issue', 'id': 'I_issue1', 'url': 'u'}}}},
                  {'data': {'addComment': {'commentEdge': {'node': {'url': 'c'}}}}}]},
     ('post', 'https://api.github.com/graphql'), ['addComment', 'I_issue1']),
    ('bitbucket', {'workspace': 'northwind', 'username': 'alex'}, msg('bitbucket', 'ledger:p12'), {'/pullrequests/12/comments': {'id': 1}},
     ('post', 'https://api.bitbucket.org/2.0/repositories/northwind/ledger/pullrequests/12/comments'), ['"raw"']),
    ('zulip', {'site': 'northwind', 'email': 'alex@northwind.example'}, msg('zulip', 501, conv='5:deploys'), {'/messages': {'id': 502}},
     ('post', 'https://northwind.zulipchat.com/api/v1/messages'), ['"topic": "deploys"', '"to": "5"', '"type": "stream"']),
    ('zulip', {'site': 'northwind', 'email': 'alex@northwind.example'}, msg('zulip', 503, conv='dm:31'), {'/messages': {'id': 504}},
     ('post', 'https://northwind.zulipchat.com/api/v1/messages'), ['"type": "direct"', '[31]']),
    ('signal', {'number': '+15550001111'}, msg('signal', 'uuid-1:17', conv='g:abc'), {'/v2/send': {'timestamp': 1}},
     ('post', 'http://127.0.0.1:8080/v2/send'), ['group.YWJj', '+15550001111']),
    ('twilio', {'account_sid': AC, 'number': '+15550001111'}, msg('twilio', 'SM1', conv='from:+15552223333'), {'/Messages.json': {'sid': 'SM2'}},
     ('post', f'https://api.twilio.com/2010-04-01/Accounts/{AC}/Messages.json'), ['"To": "+15552223333"', '"From": "+15550001111"']),
    ('discourse', {'base_url': 'https://forum.northwind.example', 'username': 'alex', 'replies': True},
     msg('discourse', 9, conv='t88', link='https://forum.northwind.example/t/the-export/88/4'), {'/posts.json': {'id': 1, 'post_number': 5}},
     ('post', 'https://forum.northwind.example/posts.json'), ['"topic_id": 88', '"reply_to_post_number": 4']),
    ('reddit', {'client_id': 'i', 'client_secret': 's', 'username': 'alexd', 'replies': True}, msg('reddit', 't1_abc'),
     {'access_token': {'access_token': 'rt', 'expires_in': 3600}, '/api/comment': {'json': {'errors': [], 'data': {'things': [{'data': {'name': 't1_new'}}]}}}},
     ('post', 'https://oauth.reddit.com/api/comment'), ['"thing_id": "t1_abc"']),
    ('webex', {}, msg('webex', 'msg1', conv='room1', head='Webex - you were mentioned in Ops'), {'/messages': {'id': 'm2'}},
     ('post', 'https://webexapis.com/v1/messages'), ['"parentId": "msg1"', '"roomId": "room1"']),
    ('zoom_chat', {}, msg('zoom_chat', 'zm1', conv='ch1'), {'/chat/users/me/messages': {'id': 'zm2'}},
     ('post', 'https://api.zoom.us/v2/chat/users/me/messages'), ['"to_channel": "ch1"', '"reply_main_message_id": "zm1"']),
    ('zoom_chat', {}, msg('zoom_chat', 'zm3', conv='pat@vendor.example'), {'/chat/users/me/messages': {'id': 'zm4'}},
     ('post', 'https://api.zoom.us/v2/chat/users/me/messages'), ['"to_contact": "pat@vendor.example"']),
    ('threads', {'me_id': '55', 'replies': True}, msg('threads', '9001', conv='800'), {'/55/threads_publish': {'id': 'p1'}, '/55/threads': {'id': 'box1'}},
     ('post', 'https://graph.threads.net/v1.0/55/threads'), ['"reply_to_id": "9001"']),
    ('hubspot', {}, msg('hubspot', '321', link='https://app.hubspot.com/contacts/1/record/0-5/321'), {'/crm/v3/objects/notes': {'id': 'n1'}},
     ('post', 'https://api.hubapi.com/crm/v3/objects/notes'), ['"id": "321"', '"associationTypeId": 228']),
    ('salesforce', {'host': 'https://northwind.my.salesforce.com'}, msg('salesforce', '500xx000000AbCdAAA'), {'/CaseComment': {'id': 'cc1', 'success': True}},
     ('post', 'https://northwind.my.salesforce.com/services/data/v62.0/sobjects/CaseComment'), ['"ParentId": "500xx000000AbCdAAA"', '"IsPublished": true']),
    ('salesforce', {'host': 'https://northwind.my.salesforce.com'}, msg('salesforce', '00Txx000000AbCdAAA'), {'/FeedItem': {'id': 'f1', 'success': True}},
     ('post', 'https://northwind.my.salesforce.com/services/data/v62.0/sobjects/FeedItem'), ['"ParentId": "00Txx000000AbCdAAA"']),
    ('basecamp_todos', {'host': 'https://3.basecampapi.com/999'}, msg('basecamp_todos', 34, link='https://3.basecamp.com/999/buckets/12/todos/34'),
     {'/comments.json': {'id': 1}}, ('post', 'https://3.basecampapi.com/999/buckets/12/recordings/34/comments.json'), []),
    ('basecamp_todos', {'host': 'https://3.basecampapi.com/999'}, msg('basecamp_todos', 'r7', link='https://3.basecamp.com/999/buckets/12/chats/56'),
     {'/lines.json': {'id': 1}}, ('post', 'https://3.basecampapi.com/999/buckets/12/chats/56/lines.json'), []),
    ('line', {}, msg('line', 'l1', conv='U123'), {'/v2/bot/message/push': {}}, ('post', 'https://api.line.me/v2/bot/message/push'), ['"to": "U123"']),
    ('instagram', {'ig_user_id': '1784', 'replies': True}, msg('instagram', '17900'), {'/17900/replies': {'id': 'r1'}},
     ('post', 'https://graph.facebook.com/v24.0/17900/replies'), ['"message"']),
    ('facebook_pages', {'page_id': '1010', 'replies': True}, msg('facebook_pages', '1010_5_77'), {'/1010_5_77/comments': {'id': 'c1'}},
     ('post', 'https://graph.facebook.com/v24.0/1010_5_77/comments'), []),
    ('facebook_pages', {'page_id': '1010', 'replies': True}, msg('facebook_pages', 'm_1', conv='t_9', author='fb:4242'), {'/1010/messages': {'message_id': 'm2'}},
     ('post', 'https://graph.facebook.com/v24.0/1010/messages'), ['"id": "4242"', '"messaging_type": "RESPONSE"']),
    ('front', {'me_id': 'tea_1'}, msg('front', 'cnv_1'), {'/conversations/cnv_1/messages': {'id': 'msg_2'}},
     ('post', 'https://api2.frontapp.com/conversations/cnv_1/messages'), ['"author_id": "tea_1"']),
    ('helpscout', {'app_id': 'app', 'me_id': '5'}, msg('helpscout', 123, author='c:77'),
     {'/oauth2/token': {'access_token': 'hs', 'expires_in': 3600}, '/conversations/123/reply': {}},
     ('post', 'https://api.helpscout.net/v2/conversations/123/reply'), ['"customer": {"id": 77}', '"user": 5']),
    ('gorgias', {'domain': 'northwind', 'email': 'alex@northwind.example'}, msg('gorgias', 42),
     {'/api/tickets/42/messages': {'id': 8}, '/api/tickets/42': {'channel': 'email', 'subject': 'Order', 'customer': {'email': 'pat@vendor.example'},
                                                               'messages': [{'from_agent': False, 'source': {'to': [{'address': 'help@northwind.example'}]}}]}},
     ('post', 'https://northwind.gorgias.com/api/tickets/42/messages'), ['help@northwind.example', '"receiver": {"email": "pat@vendor.example"}']),
    ('ringcentral', {'client_id': 'cid', 'client_secret': 'cs'}, msg('ringcentral', 'vm1', author='tel:+15552223333'),
     {'/restapi/oauth/token': {'access_token': 'rc', 'expires_in': 3600}, '/phone-number': {'records': [{'phoneNumber': '+15550009999', 'features': ['SmsSender']}]},
      '/extension/~/sms': {'id': 5}},
     ('post', 'https://platform.ringcentral.com/restapi/v1.0/account/~/extension/~/sms'), ['+15550009999', '+15552223333']),
    ('aircall', {'api_id': 'aid'}, msg('aircall', 88, author='tel:+15552223333'), {'/v1/calls/88': {'call': {'number': {'id': 4}}}, '/messages/native/send': {'id': 1}},
     ('post', 'https://api.aircall.io/v1/numbers/4/messages/native/send'), ['"to": "+15552223333"']),
    ('dialpad', {'me_id': '321'}, msg('dialpad', 'call1', author='tel:+15552223333'), {'/api/v2/sms': {'id': 1}},
     ('post', 'https://dialpad.com/api/v2/sms'), ['"target_id": 321', '+15552223333']),
]


class EverySourceAnswersOnItsOwnThread(unittest.TestCase):
    def test_a_pressed_send_calls_the_right_endpoint_with_the_text_and_the_thread(self):
        for t, cfg, m, routes, (verb, url), carries in CASES:
            with self.subTest(t=t, id=m['ExternalId']):
                s = MemoryStore(); card(s, t, cfg)
                got, calls = send(s, m, routes)
                hit = next((c for c in reversed(calls) if c[0] == verb and c[1] == url), None)
                self.assertIsNotNone(hit, f'{t}: no {verb.upper()} {url} in {[c[:2] for c in calls]}')
                said = json.dumps(hit[2])
                for x in [TEXT, *carries]: self.assertIn(x, said, t)
                self.assertNotIn(REV[1:], said, t)                                  # the revision mark is ours, never the vendor's id
                self.assertEqual(got['channel'], t)

    def test_an_internal_note_where_the_card_says_so(self):
        for t, cfg, m, routes, url, carries in [
                ('zendesk', {'subdomain': 'northwind', 'email': 'a'}, msg('zendesk', 42), {'/tickets/42.json': {}}, '/tickets/42.json', '"public": false'),
                ('freshdesk', {'domain': 'northwind'}, msg('freshdesk', 42), {'/tickets/42/notes': {}}, '/tickets/42/notes', '"private": true'),
                ('servicenow', {'instance': 'northwind', 'username': 'a'}, msg('servicenow', f'incident:{SYS}'), {SYS: {}}, SYS, '"work_notes"'),
                ('front', {'me_id': 'tea_1'}, msg('front', 'cnv_1'), {'/comments': {}}, '/conversations/cnv_1/comments', 'tea_1'),
                ('gorgias', {'domain': 'northwind', 'email': 'a'}, msg('gorgias', 42), {'/messages': {}}, '/tickets/42/messages', 'internal-note')]:
            with self.subTest(t=t):
                s = MemoryStore(); card(s, t, {**cfg, 'reply_note': True})
                _, calls = send(s, m, routes)
                hit = next(c for c in calls if url in c[1] and c[0] != 'get')
                self.assertIn(carries, json.dumps(hit[2]))

    def test_mail_through_a_relay_goes_back_from_the_owners_mailbox(self):
        for t in ('mailgun', 'sendgrid'):
            s = MemoryStore(); card(s, t, {'domain': 'in.northwind.example'})
            with mock.patch.object(outbound, 'send_out', return_value={'channel': 'email', 'to': ['pat@vendor.example']}) as out:
                got = outbound.reply_to_message(s, msg(t, '<a1@vendor.example>'), TEXT)
            out.assert_called_once_with(s, 'email', ['pat@vendor.example'], 'Re: The export', TEXT)
            self.assertEqual((got['channel'], got['by']), (t, 'email'))

    def test_a_messenger_reply_past_its_24_hours_is_refused_before_anything_goes(self):
        s = MemoryStore(); card(s, 'facebook_pages', {'page_id': '1010', 'replies': True})
        with self.assertRaisesRegex(RuntimeError, '24 hours'):
            send(s, msg('facebook_pages', 'm_1', conv='t_9', author='fb:4242', at='2026-01-01 09:00:00'), {})

    def test_a_reddit_refusal_inside_a_200_is_not_sent(self):
        s = MemoryStore(); card(s, 'reddit', {'client_id': 'i', 'client_secret': 's', 'username': 'alexd', 'replies': True})
        with self.assertRaisesRegex(RuntimeError, 'THREAD_LOCKED'):
            send(s, msg('reddit', 't1_abc'), {'access_token': {'access_token': 'rt'}, '/api/comment': {'json': {'errors': [['THREAD_LOCKED', 'locked', '']]}}})

    def test_the_ones_that_cannot_reply_say_so_and_stay_read_only(self):
        for t in ('youtube', 'x', 'ms_planner', 'docusign', 'shopify', 'calendly', 'typeform', 'lever'):
            self.assertNotIn(t, inboxes.REPLY); self.assertIn(t, outbound.NEVER)
            s = MemoryStore(); self.assertFalse(outbound.can_reply(s, t))


class TheCardsRepliesSwitch(unittest.TestCase):
    def test_on_for_helpdesks_and_chats_off_for_a_public_post(self):
        s = MemoryStore()
        for t in ('zendesk', 'zulip', 'twilio', 'front'): card(s, t); self.assertTrue(outbound.can_reply(s, t), t)
        for t in ('reddit', 'instagram', 'facebook_pages', 'wordpress', 'threads', 'discourse'):
            card(s, t); self.assertFalse(outbound.can_reply(s, t), t)
            card(s, t, {'replies': True}); self.assertTrue(outbound.can_reply(s, t), t)

    def test_every_reply_source_has_its_catalogue_words_and_no_other_does(self):
        from taskuary import connectorcatalog
        said = {c['type'] for c in connectorcatalog.cards() if c.get('replies')}
        self.assertEqual(said, set(inboxes.REPLY))
        for t in said: self.assertTrue(connectorcatalog.by_type(t)['replies']['says'], t)

    def test_replies_off_is_refused_with_the_way_to_the_card(self):
        s = MemoryStore(); card(s, 'zendesk', {'subdomain': 'northwind', 'email': 'a', 'replies': False})
        self.assertFalse(outbound.can_reply(s, 'zendesk'))
        self.assertIn('Replies switch', outbound.send_block(s, 'zendesk'))
        self.assertEqual(outbound.block_fix(s, 'zendesk'), {'label': 'Open the Zendesk card', 'href': '#connector=zendesk'})
        with self.assertRaises(outbound.Fixable) as e: send(s, msg('zendesk', 42), {})
        self.assertEqual(e.exception.fix['href'], '#connector=zendesk')

    def test_replies_off_on_the_road_the_owner_presses(self):
        s = MemoryStore(); card(s, 'zendesk', {'subdomain': 'northwind', 'email': 'a', 'replies': False})
        rid = _review(s, msg('zendesk', 42))
        with mock.patch.object(inboxes, 'requests', FakeHTTP({})) as h:
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertEqual((out['ok'], out['delivery']), (False, 'failed'))
        self.assertEqual(out['send_fix']['href'], '#connector=zendesk')
        self.assertEqual(h.calls, [])


def _review(s, m):
    tid = s.create_task({'Title': 'The export', 'Kind': 'reply', 'Status': 'open', 'Source': m['Channel']}, 'router')
    mid = s.add_message({**{k: v for k, v in m.items()}, 'TaskId': tid, 'Status': 'routed', 'Direction': 'in'})
    return s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': TEXT,
                         'Deliver': json.dumps({'kind': 'reply'})})


class DeliverySafety(unittest.TestCase):
    """The owner's press, through verdicts.decide: confirmed, failed (Not sent + Reconnect) or unknown - never a second send."""
    def press(self, s, m, routes):
        http = FakeHTTP(routes)
        with mock.patch.object(inboxes, 'requests', http), mock.patch('taskuary.oauth.access', return_value='oauth-tok'):
            rid = _review(s, m)
            return verdicts.decide(s, s.get_review(rid), 'approve'), http.calls, rid

    def test_a_pressed_send_is_confirmed_and_said_on_the_task(self):
        s = MemoryStore(); card(s, 'zendesk', {'subdomain': 'northwind', 'email': 'a'})
        out, calls, rid = self.press(s, msg('zendesk', 42), {'/tickets/42.json': {'audit': {'id': 9}}})
        self.assertTrue(out['ok']); self.assertEqual(out['delivery'], 'sent'); self.assertEqual(len(calls), 1)
        self.assertEqual(s.get_review(rid)['DeliveryState'], 'sent')

    def test_a_card_not_connected_is_not_sent_with_reconnect(self):
        s = MemoryStore(); card(s, 'zulip', {'site': 'northwind'}, Active=0)
        out, calls, _ = self.press(s, msg('zulip', 501, conv='5:deploys'), {})
        self.assertEqual(out['delivery'], 'failed'); self.assertIsNone(out['sent'])
        self.assertIn('not connected', out['send_error'])
        self.assertEqual(out['send_fix'], {'label': 'Reconnect Zulip', 'href': '#connector=zulip'})
        self.assertEqual(calls, [])

    def test_a_key_that_may_not_write_is_not_sent_with_reconnect(self):
        s = MemoryStore(); card(s, 'zendesk', {'subdomain': 'northwind', 'email': 'a'})
        out, _, _ = self.press(s, msg('zendesk', 42), {'/tickets/42.json': R({'error': 'Forbidden'}, 403)})
        self.assertEqual(out['delivery'], 'failed'); self.assertIsNone(out['sent'])
        self.assertEqual(out['send_fix']['label'], 'Reconnect Zendesk')

    def test_a_5xx_is_unknown_and_never_sent_again(self):
        s = MemoryStore(); card(s, 'zendesk', {'subdomain': 'northwind', 'email': 'a'})
        out, calls, rid = self.press(s, msg('zendesk', 42), {'/tickets/42.json': R({}, 502)})
        self.assertEqual(out['delivery'], 'unknown'); self.assertEqual(len(calls), 1)
        with mock.patch.object(inboxes, 'requests', FakeHTTP({})) as h:
            again = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertFalse(again['ok']); self.assertEqual(h.calls, [])


class AgentsDraftOnTheSameRoad(unittest.TestCase):
    def test_propose_reply_on_a_source_task_waits_with_send_lit(self):
        from taskuary import wrapup
        s = MemoryStore(); card(s, 'zendesk', {'subdomain': 'northwind', 'email': 'a'})
        rid = _review(s, msg('zendesk', 42))
        tid = s.get_review(rid)['TaskId']
        out = wrapup.agent_reply(s, tid, 'The fix is live - try the export again.', 'agent')
        self.assertTrue(out.get('ok'), out)
        self.assertTrue(outbound.can_reply(s, 'zendesk'))


if __name__ == '__main__': unittest.main()
