"""Starting a new outbound email: arbitrary/multiple recipients and durable CC."""
import json
import unittest
from unittest import mock

from taskuary import outbox
from taskuary.store import MemoryStore


def compose(s, *a, **k):
    "New -> Send something, its agent stood in: (what compose answered, [(task, his line)]) - no side model may write it."
    told = []
    with mock.patch('taskuary.general.to_agent', side_effect=lambda st, tid, said, *x, **y: told.append((tid, said, y.get('frm'))) or 'started'),          mock.patch('taskuary.outbox.draft_message', side_effect=AssertionError('a side model wrote it')),          mock.patch('taskuary.outbox.subject_for', side_effect=AssertionError('a side model wrote its subject')):
        return outbox.compose(s, *a, **k), told


class OutboxEmailTests(unittest.TestCase):
    """New -> Send something is his ask to a task's agent (the owner, 2026-11-27: "side model should never work in agent canvas"): the task
    holds his ask, and his line - whom, and what about - starts its agent, which writes the message and raises its card."""
    def setUp(self):
        self.s = MemoryStore()

    def test_his_ask_is_his_line_to_its_agent_and_nothing_is_drafted_in_his_name(self):
        made, told = compose(self.s, 'email', ['a@example.com', 'b@example.com'], 'share the report', subject='Monthly report', cc=['copy@example.com'])
        self.assertEqual(told, [(made['taskId'], 'Email a@example.com, b@example.com, cc copy@example.com, subject "Monthly report": share the report', 'owner')])
        self.assertTrue(made['asked'])
        self.assertIsNone(self.s.pending_review(made['taskId']), 'no card in his name - the agent raises its own')
        self.assertEqual(self.s.get_task(made['taskId'])['Kind'], 'general')

    def test_a_new_address_is_allowed_and_bad_or_missing_addresses_are_refused(self):
        made, _ = compose(self.s, 'email', 'never-seen@example.com', 'say hello', subject='Hello')
        self.assertTrue(made['taskId'])
        with self.assertRaisesRegex(ValueError, 'valid email'): compose(self.s, 'email', ['not-an-address'], 'say hello', subject='Hello')
        with self.assertRaisesRegex(ValueError, 'at least one'): compose(self.s, 'email', [], 'say hello', subject='Hello')

    def test_comma_pasted_addresses_are_split_and_to_cc_duplicates_are_removed(self):
        made, _ = compose(self.s, 'email', 'One@example.com, two@example.com', 'say hello', subject='Hello', cc=['one@example.com', 'three@example.com'])
        r = json.loads(self.s.get_message(made['messageId'])['RecipientsJson'])
        self.assertEqual((r['to'], r['cc']), (['One@example.com', 'two@example.com'], ['three@example.com']))


class OwnersAskTests(unittest.TestCase):
    """THE NEW BOX'S ASK IS HIS INSTRUCTION, NOT MAIL HE SENT (2026-11-17): it was stored outbound, addressed to nobody - the page drew it as
    "Sent by you · gail@...", and the agent's brief read "FROM You" with no recipient, called it his own reply on the thread, and the draft
    waiting "to You". Asked to make the email shorter, it asked him whom it was for."""
    def setUp(self):
        self.s = MemoryStore()
        made, _ = compose(self.s, 'email', 'gail@northwind.example', 'ask her for the March census numbers', subject='Census')
        self.tid, self.mid = made['taskId'], made['messageId']

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
