"""Looping somebody in: a cc on the answer, from the Review card to the wire.

The copy list is passed at the moment of approval and stored nowhere - what the owner can SEE on
the card is what sends. Two senders have to honour it (Graph and SMTP) and one has to refuse it
(a chat has members, not recipients).
"""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import imapmail, outbound, server, verdicts
from taskuary.store import MemoryStore

c = TestClient(server.app)


class AddressTests(unittest.TestCase):
    def test_only_addresses_survive_and_only_once(self):
        self.assertEqual(outbound.addrs(['a@x.com', ' b@x.com ', 'A@X.com', 'not-an-address', '', None]),
                         ['a@x.com', 'b@x.com'])
        self.assertEqual(outbound.addrs(None), [])


class GraphTests(unittest.TestCase):
    def _store(self):
        s = MemoryStore()
        oc = s.get_connector_by_type('outlook')
        s.save_connector({'ConnectorId': oc['ConnectorId'], 'Active': 1, 'Secret': 'x',
                          'ConfigJson': json.dumps({'address': 'me@corp.example', 'auth': 'user'})}, 'o')
        return s

    def _post(self, sent):
        r = mock.Mock(status_code=202, text='')
        return mock.patch.object(outbound.requests, 'post',
                                 side_effect=lambda url, **kw: (sent.update(url=url, body=json.loads(kw['data'])), r)[1])

    def test_a_threaded_reply_carries_the_cc_and_keeps_the_recipient(self):
        """Graph replaces its own recipients the moment a message object is sent, so `to` has to
        go back in alongside the cc - otherwise looping someone in drops the person you answered."""
        sent = {}
        with mock.patch.object(outbound, '_graph_token', return_value='t'), self._post(sent):
            out = outbound.send_email(self._store(), ['them@partner.example'], 'Re: x', 'body',
                                      reply_to_graph_id='AAA', mailbox='me@corp.example',
                                      cc=['mindy@corp.example'])
        m = sent['body']['message']
        self.assertEqual([a['emailAddress']['address'] for a in m['toRecipients']], ['them@partner.example'])
        self.assertEqual([a['emailAddress']['address'] for a in m['ccRecipients']], ['mindy@corp.example'])
        self.assertEqual(out['cc'], ['mindy@corp.example'])

    def test_no_cc_leaves_the_reply_exactly_as_it_was(self):
        sent = {}
        with mock.patch.object(outbound, '_graph_token', return_value='t'), self._post(sent):
            outbound.send_email(self._store(), [], 'Re: x', 'body', reply_to_graph_id='AAA', mailbox='me@corp.example')
        self.assertEqual(sent['body']['message'], {})       # Graph keeps its own recipients

    def test_a_new_mail_carries_it_too(self):
        sent = {}
        with mock.patch.object(outbound, '_graph_token', return_value='t'), self._post(sent):
            outbound.send_email(self._store(), ['them@partner.example'], 'Hello', 'body',
                                mailbox='me@corp.example', cc=['mindy@corp.example', 'mindy@corp.example'])
        m = sent['body']['message']
        self.assertEqual([a['emailAddress']['address'] for a in m['ccRecipients']], ['mindy@corp.example'])


class SmtpTests(unittest.TestCase):
    def test_the_cc_is_on_the_header_and_in_the_envelope(self):
        """The header alone is only text: a server delivers to the envelope, so a Cc: line without
        the address in sendmail() looks copied to everyone and reaches nobody."""
        sent = {}
        cfg = {'address': 'me@mine.example', 'imap_host': 'imap.mine.example'}
        conn = {'Type': 'imap', 'Secret': 'pw', 'ConfigJson': json.dumps(cfg)}
        S = mock.MagicMock(); S.__enter__.return_value = S
        S.sock = mock.Mock(getpeercert=mock.Mock(return_value=b'cert'))
        S.sendmail.side_effect = lambda frm, to, data: sent.update(frm=frm, to=to, data=data)
        with mock.patch.object(imapmail.smtplib, 'SMTP', return_value=S):
            out = imapmail.send_smtp(MemoryStore(), conn, ['them@partner.example'], 'Re: x', 'body',
                                     cc=['mindy@mine.example'])
        self.assertEqual(sent['to'], ['them@partner.example', 'mindy@mine.example'])
        self.assertIn('Cc: mindy@mine.example', sent['data'])
        self.assertEqual(out['cc'], ['mindy@mine.example'])


class ChannelTests(unittest.TestCase):
    def test_a_chat_refuses_rather_than_dropping_the_person(self):
        for ch in ('teams', 'whatsapp', 'telegram'):
            with self.assertRaisesRegex(RuntimeError, 'no cc'):
                outbound.reply_to_message(MemoryStore(), {'Channel': ch, 'ConversationId': f'{ch}:1'},
                                          'body', cc=['mindy@corp.example'])
        with self.assertRaisesRegex(RuntimeError, 'no cc'):
            outbound.send_out(MemoryStore(), 'teams', ['19:chat'], 'subject', 'body', cc=['mindy@corp.example'])


class VerdictTests(unittest.TestCase):
    def test_approving_sends_the_copy_list_and_the_task_says_who_got_it(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'answer them', 'Kind': 'general', 'Status': 'open'}, 'o')
        mid = s.add_message({'TaskId': tid, 'ExternalId': 'graph:AAA', 'Channel': 'email',
                             'SourceName': 'me@corp.example', 'FromEmail': 'them@partner.example',
                             'Subject': 'a question', 'BodyText': '?', 'Status': 'routed'})
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply',
                            'Status': 'pending', 'DraftText': 'here is the answer'})
        seen = {}
        def fake(store, msg, body, to=None, cc=None):
            seen['cc'] = cc
            return {'channel': 'email', 'to': ['them@partner.example'], 'cc': cc or []}
        with mock.patch.object(outbound, 'reply_to_message', side_effect=fake):
            out = verdicts.decide(s, s.get_review(rid), 'approve', 'here is the answer',
                                  cc=['mindy@corp.example'])
        self.assertTrue(out['ok'])
        self.assertEqual(seen['cc'], ['mindy@corp.example'])
        said = ' '.join(x['Body'] for x in s.list_comments(tid))
        self.assertIn('copied mindy@corp.example', said)

    def test_the_door_passes_it_through(self):
        """POST /api/reviews/{id}/decide carries cc; rejecting copies nobody on nothing."""
        s = server.store
        tid = s.create_task({'Title': 'answer them', 'Kind': 'general', 'Status': 'open'}, 'o')
        mid = s.add_message({'TaskId': tid, 'ExternalId': 'graph:BBB', 'Channel': 'email',
                             'SourceName': 'me@corp.example', 'FromEmail': 'them@partner.example',
                             'Subject': 'q', 'BodyText': '?', 'Status': 'routed'})
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply',
                            'Status': 'pending', 'DraftText': 'the answer'})
        seen = {}
        with mock.patch.object(server.outbound, 'reply_to_message',
                               side_effect=lambda st, m, b, to=None, cc=None: (seen.update(cc=cc),
                                   {'channel': 'email', 'to': ['them@partner.example'], 'cc': cc or []})[1]):
            r = c.post(f'/api/reviews/{rid}/decide',
                       json={'verb': 'approve', 'final_text': 'the answer', 'cc': ['mindy@corp.example']})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(seen['cc'], ['mindy@corp.example'])



class AddressBookTests(unittest.TestCase):
    """Every place a person is picked reads one list (ui.ContactPicker): looping somebody in on a
    reply, handing a task over."""

    def test_it_returns_a_book_worth_searching_and_will_not_be_talked_into_more(self):
        r = c.get('/api/people')
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json()['data'], list)
        # 60 was enough for a recency list you scroll; a box you SEARCH wants the whole book
        with mock.patch.object(server.store, 'people', return_value=[]) as book:
            c.get('/api/people')
            self.assertEqual(book.call_args[0][0], 300)
            c.get('/api/people', params={'limit': 5000})
            self.assertEqual(book.call_args[0][0], 1000)      # clamped: not an invitation to read the table
            c.get('/api/people', params={'limit': 0})
            self.assertEqual(book.call_args[0][0], 1)

    def test_a_name_and_an_address_come_back_for_each(self):
        """The picker searches the NAME as well as the address - nobody remembers how a
        colleague's mailbox is spelled."""
        s = server.store
        s.add_message({'ExternalId': 'ab1', 'Channel': 'email', 'SourceName': 'me@corp.example',
                       'FromEmail': 'nechama@hrtgcs.example', 'FromName': 'Nechama Ozur, CPA',
                       'Subject': 'monthly close', 'BodyText': '?', 'Status': 'filed',
                       'SentAt': '2026-09-02 15:00:00'})
        got = c.get('/api/people').json()['data']
        row = next((p for p in got if p['Email'] == 'nechama@hrtgcs.example'), None)
        self.assertIsNotNone(row)
        self.assertEqual(row['Name'], 'Nechama Ozur, CPA')

if __name__ == '__main__':
    unittest.main()
