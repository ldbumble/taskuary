"""What a poll is allowed to SPEND on mail nobody will ever read.

A 3-day catch-up on a shared log mailbox read 630 messages and cost thirteen minutes,
of which triage was 45 seconds. The rest was two kinds of round trip bought for mail a
skip policy threw away on arrival: the full body, downloaded inside the folder page, and
a thread-history call per conversation - 634 of them, every one returning nothing.
"""
import json, unittest
from unittest import mock
from taskuary import channels, chains
from taskuary.store import MemoryStore

FLOOD = 'noreply-logs@vendor.example'


def _mailbox(s, folders=('inbox',)):
    o = s.get_connector_by_type('outlook')
    s.save_connector({'ConnectorId': o['ConnectorId'], 'Active': 1, 'Secret': 'S',
                      'ConfigJson': json.dumps({'tenant_id': 'T', 'client_id': 'C'})}, 't')
    s.save_source({'Channel': 'email', 'Address': 'me@x.com', 'ConnectorId': o['ConnectorId'],
                   'Active': 1, 'ConfigJson': json.dumps({'folders': list(folders)})}, 't')
    s.save_policy({'Name': 'log flood', 'Kind': 'sender', 'Pattern': FLOOD, 'Action': 'skip',
                   'Reason': 'automated log mail', 'Active': 1, 'SortOrder': 1}, 't')


def _msg(i, addr=FLOOD):
    return {'id': f'm{i}', 'subject': f'Vendor Create {i}', 'receivedDateTime': f'2026-09-12T10:0{i}:00Z',
            'from': {'emailAddress': {'name': 'logs', 'address': addr}},
            'conversationId': f'conv-{i}', 'body': {'content': 'x' * 2000}, 'isRead': True}


class HistoryForSkippedMailTests(unittest.TestCase):
    """A message the policy threw away must not buy a thread-history round trip."""

    def _poll(self, addrs):
        s = MemoryStore(); _mailbox(s)
        batch = [_msg(i, a) for i, a in enumerate(addrs)]
        def msgs(tok, upn, since, folder='inbox', **kw):
            out = [] if folder == 'sentitems' else batch
            return (out, None) if kw.get('with_continuation') else out
        completed = []
        by_id = {m['id']: m for m in batch}
        with mock.patch.object(channels, 'graph_token', return_value='T'), \
             mock.patch.object(channels, '_mail_msgs', side_effect=msgs), \
             mock.patch.object(channels, '_mail_bodies',
                               side_effect=lambda tok, upn, ids: [by_id[x] for x in ids]), \
             mock.patch.object(chains, 'needs_history', return_value=True), \
             mock.patch.object(chains, 'refresh_outlook',
                               side_effect=lambda st, tok, mb, conv, before=None: completed.append(conv)):
            channels.poll_channels(s)
        return s, completed

    def test_a_skipped_sender_buys_no_history_call(self):
        s, completed = self._poll([FLOOD] * 5)
        self.assertEqual([m['Status'] for m in s.scan_messages()], ['skipped'] * 5)
        self.assertEqual(completed, [], 'nothing on the timeline, nothing worth completing')

    def test_a_real_message_still_gets_its_history(self):
        s, completed = self._poll([FLOOD, 'a.person@vendor.example'])
        self.assertEqual(completed, ['conv-1'], 'only the message that stayed')


class BodyDownloadTests(unittest.TestCase):
    """The folder page lists; bodies are fetched for the mail that survives the policy."""

    def test_the_listing_does_not_ask_for_bodies(self):
        self.assertNotIn('body', [f.strip() for f in channels.MAIL_LIST_SELECT.split(',')])

    def test_only_surviving_mail_costs_a_body(self):
        s = MemoryStore(); _mailbox(s)
        batch = [_msg(0, FLOOD), _msg(1, 'a.person@vendor.example')]
        light = [{k: v for k, v in m.items() if k != 'body'} for m in batch]
        def msgs(tok, upn, since, folder='inbox', **kw):
            out = [] if folder == 'sentitems' else light
            return (out, None) if kw.get('with_continuation') else out
        asked = []
        def bodies(tok, upn, ids):
            asked.extend(ids)
            return [m for m in batch if m['id'] in set(ids)]
        with mock.patch.object(channels, 'graph_token', return_value='T'), \
             mock.patch.object(channels, '_mail_msgs', side_effect=msgs), \
             mock.patch.object(channels, '_mail_bodies', side_effect=bodies), \
             mock.patch.object(chains, 'needs_history', return_value=False):
            channels.poll_channels(s)
        self.assertEqual(asked, ['m1'], 'the flood sender never costs a body')
        kept = {m['Subject']: m for m in s.scan_messages()}
        self.assertEqual(kept['Vendor Create 0']['Status'], 'skipped')
        self.assertEqual(kept['Vendor Create 1']['BodyText'], 'x' * 2000)


    def test_a_body_graph_throttles_inside_the_batch_is_asked_again_never_kept_as_its_preview(self):
        """Graph answers a $batch 200 and throttles single requests inside it (429 - a mailbox takes only a few at once). Those mails
        were kept with the listing's 255-character preview as their whole body, for good: the agent read a cut mail as the mail."""
        def batch(answers):
            r = mock.Mock(status_code=200); r.raise_for_status = lambda: None
            r.json.return_value = {'responses': answers}
            return r
        full = lambda k, x: {'id': str(k), 'status': 200, 'body': {'id': x, 'body': {'content': f'all of {x}'}}}
        busy = lambda k: {'id': str(k), 'status': 429, 'headers': {'Retry-After': '1'}, 'body': {'error': {'code': 'ApplicationThrottled'}}}
        sent = []
        def post(url, json=None, **kw):
            ids = [q['url'].split('/messages/')[1].split('?')[0] for q in json['requests']]; sent.append(ids)
            return batch([full(0, ids[0]), busy(1)] if len(sent) == 1 else [full(k, x) for k, x in enumerate(ids)])
        with mock.patch.object(channels.requests, 'post', side_effect=post), mock.patch.object(channels.time, 'sleep') as slept:
            got = channels._mail_bodies('T', 'me@x.com', ['m0', 'm1'])
        self.assertEqual(sorted(b['body']['content'] for b in got), ['all of m0', 'all of m1'])
        self.assertEqual(sent, [['m0', 'm1'], ['m1']]); slept.assert_called()
        # ...and one Graph will not give at all holds the folder for the next poll, as a failed page does
        with mock.patch.object(channels.requests, 'post', side_effect=lambda url, json=None, **kw: batch([busy(k) for k, _ in enumerate(json['requests'])])), \
             mock.patch.object(channels.time, 'sleep'):
            with self.assertRaises(RuntimeError): channels._mail_bodies('T', 'me@x.com', ['m2'])
        # ...while a mail deleted since it was listed (404) has no body to wait for
        with mock.patch.object(channels.requests, 'post', side_effect=lambda url, json=None, **kw: batch([{'id': '0', 'status': 404}])):
            self.assertEqual(channels._mail_bodies('T', 'me@x.com', ['m3']), [])

if __name__ == '__main__':
    unittest.main()
