"""Starting a new outbound email: arbitrary/multiple recipients and durable CC."""
import json
import unittest
from unittest import mock

from taskuary import outbox, verdicts
from taskuary.store import MemoryStore


class OutboxEmailTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()

    def test_multiple_to_and_cc_are_saved_on_the_review_and_shown_to_the_drafter(self):
        self.s.save_doc('style', '### Greeting & sign-off\n- Always end with:\n  Best,\n  Alex\n  Northwind Trading\n'
                                    '### Tone & length\n- concise but complete\n', 'test')
        seen = {}
        def llm(system, user, max_tokens=0):
            seen['system'], seen['user'] = system, user
            return 'Hi all,\n\nThe report is ready.\n\nBest,\nAlex'
        result = outbox.compose(self.s, 'email', ['a@example.com', 'b@example.com'], 'share the report',
                                subject='Monthly report', cc=['copy@example.com'], llm=llm)
        review = self.s.get_review(result['reviewId'])
        deliver = json.loads(review['Deliver'])
        self.assertEqual(deliver['to'], ['a@example.com', 'b@example.com'])
        self.assertEqual(deliver['cc'], ['copy@example.com'])
        self.assertIn('TO: a@example.com, b@example.com', seen['user'])
        self.assertIn('CC: copy@example.com', seen['user'])
        self.assertIn('Do NOT write a sign-off', seen['system'])         # the signature layer signs, never the writer (signatures.py)
        self.assertIn('Northwind Trading', seen['system'])

    def test_a_new_address_is_allowed_and_bad_or_missing_addresses_are_refused(self):
        made = outbox.compose(self.s, 'email', 'never-seen@example.com', 'say hello',
                              subject='Hello', llm=lambda *_a, **_k: 'Hello')
        self.assertTrue(made['reviewId'])
        with self.assertRaisesRegex(ValueError, 'valid email'):
            outbox.compose(self.s, 'email', ['not-an-address'], 'say hello', subject='Hello',
                           llm=lambda *_a, **_k: 'Hello')
        with self.assertRaisesRegex(ValueError, 'at least one'):
            outbox.compose(self.s, 'email', [], 'say hello', subject='Hello',
                           llm=lambda *_a, **_k: 'Hello')

    def test_comma_pasted_addresses_are_split_and_to_cc_duplicates_are_removed(self):
        made = outbox.compose(self.s, 'email', 'One@example.com, two@example.com', 'say hello',
                              subject='Hello', cc=['one@example.com', 'three@example.com'],
                              llm=lambda *_a, **_k: 'Hello')
        deliver = json.loads(self.s.get_review(made['reviewId'])['Deliver'])
        self.assertEqual(deliver['to'], ['One@example.com', 'two@example.com'])
        self.assertEqual(deliver['cc'], ['three@example.com'])

    def test_saved_cc_is_used_when_an_approval_client_does_not_override_it(self):
        made = outbox.compose(self.s, 'email', ['to@example.com'], 'say hello', subject='Hello',
                              cc=['copy@example.com'], llm=lambda *_a, **_k: 'Hello')
        sent = {}
        def send(_store, channel, to, subject, body, cc=None, attachments=None, mailbox=None):
            sent.update(channel=channel, to=to, subject=subject, body=body, cc=cc)
            return {'channel': channel, 'to': to, 'cc': cc}
        with mock.patch('taskuary.outbound.send_out', side_effect=send):
            verdicts.decide(self.s, self.s.get_review(made['reviewId']), 'approve', 'Hello')
        self.assertEqual(sent['to'], ['to@example.com'])
        self.assertEqual(sent['cc'], ['copy@example.com'])

    def test_redraft_uses_the_saved_recipient_envelope(self):
        made = outbox.compose(self.s, 'email', ['one@example.com', 'two@example.com'], 'send the result',
                              subject='Result', cc=['copy@example.com'], llm=lambda *_a, **_k: 'First')
        seen = {}
        def llm(_system, user, max_tokens=0): seen['user'] = user; return 'Rewritten'
        draft = outbox.redraft_review(self.s, self.s.get_review(made['reviewId']),
                                      resolution='The result is 42.', llm=llm)
        self.assertEqual(draft, 'Rewritten')
        self.assertIn('TO: one@example.com, two@example.com', seen['user'])
        self.assertIn('CC: copy@example.com', seen['user'])
        self.assertIn('The result is 42.', seen['user'])


class OwnersAskTests(unittest.TestCase):
    """THE NEW BOX'S ASK IS HIS INSTRUCTION, NOT MAIL HE SENT (2026-11-17): it was stored outbound, addressed to nobody - the page drew it as
    "Sent by you · gail@...", and the agent's brief read "FROM You" with no recipient, called it his own reply on the thread, and the draft
    waiting "to You". Asked to make the email shorter, it asked him whom it was for."""
    def setUp(self):
        self.s = MemoryStore()
        made = outbox.compose(self.s, 'email', 'gail@northwind.example', 'ask her for the March census numbers', subject='Census',
                              llm=lambda *_a, **_k: 'Hi Gail,\n\nCould you send the March census numbers?')
        self.tid, self.mid, self.rid = made['taskId'], made['messageId'], made['reviewId']

    def test_the_ask_is_his_words_and_the_brief_says_whom_it_is_for(self):
        from taskuary import context, general, wrapup
        m = self.s.get_message(self.mid)
        self.assertNotEqual(m.get('Direction'), 'out', 'nothing was sent')
        self.assertEqual(m['BodyText'], 'ask her for the March census numbers', 'his words as typed')
        self.assertFalse([x for x in self.s.list_messages(self.tid) if x.get('Direction') == 'out'])
        self.assertIn('gail@northwind.example', context.came_in(self.s, self.tid))
        self.assertTrue(wrapup.from_owner(self.s, m), 'he wrote it - nobody to reply to')
        self.assertTrue(general.owner_spoke(self.s, self.tid))
        self.assertEqual(general.own_replies(self.s, self.tid, since='2000-01-01'), [])
        said = general.prompt_parts(self.s, self.tid)[2]
        self.assertIn('gail@northwind.example', said)
        self.assertNotIn('to You', said)
        self.assertNotIn("The owner's own message on the thread", said, 'his ask is no reply of his on a thread')
        self.assertIn('The owner started a message to gail@northwind.example', said)

    def test_a_first_turn_hears_the_card_his_line_moved_past_with_whom_and_what(self):
        import time
        from taskuary import general, proposals
        self.assertTrue(proposals.set_aside_drafts(self.s, self.tid, time.time() + 5))
        said = general.prompt_parts(self.s, self.tid)[2]       # no turn has answered yet: this is the agent's first
        self.assertIn(f'rv{self.rid}', said)
        self.assertIn('gail@northwind.example', said)
        self.assertIn('Could you send the March census numbers?', said)

    def test_an_ask_filed_by_an_earlier_build_is_read_as_his_ask(self):
        import os, tempfile
        from taskuary.store import SQLiteStore
        p = os.path.join(tempfile.mkdtemp(), 't.db')
        s = SQLiteStore(p)
        tid = s.create_task({'Title': 'Census', 'Kind': 'reply', 'Status': 'open', 'Source': 'outbox'}, 'owner')
        mid = s.add_message({'TaskId': tid, 'ExternalId': f'outbox:{tid}', 'ConversationId': f'outbox:{tid}', 'Channel': 'email',
                             'SourceName': 'gail@northwind.example', 'FromName': 'You', 'Direction': 'out', 'BodyText': 'ask her', 'Status': 'routed'})
        s.close()
        m = SQLiteStore(p).get_message(mid)
        self.assertNotEqual(m.get('Direction'), 'out')
        self.assertFalse(m.get('SourceName'))
        self.assertEqual(json.loads(m['RecipientsJson'])['to'], ['gail@northwind.example'])


if __name__ == '__main__':
    unittest.main()


def test_his_ask_from_new_is_his_own_words_so_what_he_asks_to_remember_is_kept():
    """The walk, 2026-11-22: "Two things to remember from now on: I sign 'Best, Alex'; Gail handles payroll now" typed in New - the memory tool
    refused both, "the owner has said nothing in this chat": the task's own row New files for his words (own:) read as a sender's mail. One
    answer to "are these his own words" (wrapup.from_owner) reads it as his."""
    from taskuary import general, ownwork, wrapup
    s = MemoryStore(); tid = s.create_task({'Title': 'Remember how I sign and who does payroll', 'Kind': 'general', 'Status': 'in_progress',
                                            'Summary': "I sign my emails 'Best, Alex'. Gail Moreno handles payroll now."}, 'owner')
    mid = ownwork.ensure(s, tid)
    assert mid and wrapup.from_owner(s, s.get_message(mid)) and general.owner_spoke(s, tid)
    s.add_message({'TaskId': tid, 'ExternalId': 'm9', 'Channel': 'email', 'FromEmail': 'ray@northwind.example', 'BodyText': 'Payroll is mine.', 'Status': 'routed'})
    assert not general.owner_spoke(s, tid), "a sender's mail on it is still not his"
