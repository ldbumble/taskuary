"""Close-out and playbook are TWO things (the owner, 2026-10-01): a task closes only when both are settled - its close-out
(the reply sent, the pull request merged or closed, the issue closed) AND any playbook proposal its agent left (approved or
dismissed). A sent reply used to close the task and throw the undecided playbook away as "no reply"; deciding the playbook
after a sent reply then closed nothing. Either order now ends the same way, and neither half alone closes it."""
import json, unittest
from unittest import mock

from taskuary import outbound, playbooks, proposals, verdicts
from taskuary.store import MemoryStore

SENT = {'channel': 'email', 'to': ['erin@northwind.example'], 'cc': []}
BOOK = '# Monthly export fix\n\nWhen: the nightly export comes back empty.\n\n1. Re-run the view.\n'


def finished():
    """An agent finished: a reply to send and a playbook to decide, both waiting on the owner."""
    s = MemoryStore()
    s.set_setting('playbooks_enabled', '1', 't')
    tid = s.create_task({'Title': 'Fix the nightly export', 'Kind': 'reply', 'Status': 'waiting'}, 'router')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'm1', 'ConversationId': 'c1', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                         'Subject': 'Export broken', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                         'SentAt': '2026-09-30 09:00:00', 'BodyText': 'The nightly export is empty.', 'Status': 'routed'})
    reply = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Fixed - it runs tonight.'})
    book = proposals.queue(s, tid, {'action': 'write_playbook', 'slug': 'monthly-export-fix', 'text': BOOK, 'why': 'it recurs'}, 'coder')
    assert book, 'the playbook proposal was refused'
    return s, tid, reply, book['reviewId']


def send(s, rid):
    with mock.patch.object(outbound, 'reply_to_message', return_value=SENT):
        return verdicts.decide(s, s.get_review(rid), 'approve')


def decide_book(s, rid, verb):
    with mock.patch.object(playbooks, 'write', return_value='monthly-export-fix'):
        return verdicts.decide(s, s.get_review(rid), verb)


class PlaybookAndCloseOutTests(unittest.TestCase):
    def test_a_sent_reply_leaves_the_task_open_while_its_playbook_waits(self):
        s, tid, reply, book = finished()
        self.assertTrue(send(s, reply)['ok'])
        self.assertNotIn(s.get_task(tid)['Status'], ('done', 'dropped'))
        self.assertEqual(s.get_review(book)['Status'], 'pending', 'the playbook is still the owner\'s to decide')

    def test_then_approving_the_playbook_closes_it(self):
        s, tid, reply, book = finished()
        send(s, reply)
        self.assertTrue(decide_book(s, book, 'approve')['ok'])
        self.assertEqual(s.get_task(tid)['Status'], 'done')

    def test_then_dismissing_the_playbook_closes_it_too(self):
        s, tid, reply, book = finished()
        send(s, reply)
        decide_book(s, book, 'reject')
        self.assertEqual(s.get_task(tid)['Status'], 'done')

    def test_a_decided_playbook_leaves_the_task_open_while_the_reply_waits(self):
        s, tid, reply, book = finished()
        decide_book(s, book, 'approve')
        self.assertNotIn(s.get_task(tid)['Status'], ('done', 'dropped'))
        self.assertEqual(s.get_review(reply)['Status'], 'pending')
        send(s, reply)                                   # ...and the reply then is the last half
        self.assertEqual(s.get_task(tid)['Status'], 'done')

    def test_a_decided_playbook_alone_closes_nothing(self):
        s, tid, reply, book = finished()
        s.decide_review(reply, 'no_reply', None, 'owner', 'set aside for the test')     # no reply went out
        s.update_task(tid, {'Status': 'waiting'}, 'owner')
        decide_book(s, book, 'reject')
        self.assertNotIn(s.get_task(tid)['Status'], ('done', 'dropped'), 'nothing was closed out, so the task stays open')
