"""Close-out and playbook are TWO things (the owner, 2026-10-01): its close-out (the reply sent, the pull request merged or
closed, the issue closed) and any playbook proposal its agent left (approved or dismissed). A sent reply used to throw the
undecided playbook away as "no reply". Neither half closes the task, in either order - only the owner's Mark done does
(2026-10-18: "sending and closing are two steps, never automatic")."""
import json, unittest
from taskuary import card
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
    book = proposals.queue(s, tid, {'action': 'write_playbook', 'slug': 'monthly-export-fix', 'text': BOOK, 'why': 'it recurs'}, 'coding')
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

    def test_then_approving_the_playbook_still_leaves_it_open(self):
        s, tid, reply, book = finished()
        send(s, reply)
        self.assertTrue(decide_book(s, book, 'approve')['ok'])
        self.assertNotIn(s.get_task(tid)['Status'], ('done', 'dropped'))

    def test_then_dismissing_the_playbook_leaves_it_open_too(self):
        s, tid, reply, book = finished()
        send(s, reply)
        decide_book(s, book, 'reject')
        self.assertNotIn(s.get_task(tid)['Status'], ('done', 'dropped'))

    def test_a_decided_playbook_leaves_the_task_open_while_the_reply_waits(self):
        s, tid, reply, book = finished()
        decide_book(s, book, 'approve')
        self.assertNotIn(s.get_task(tid)['Status'], ('done', 'dropped'))
        self.assertEqual(s.get_review(reply)['Status'], 'pending')
        send(s, reply)                                   # ...and the reply then is the last half - still not a close
        self.assertNotIn(s.get_task(tid)['Status'], ('done', 'dropped'))

    def test_a_decided_playbook_alone_closes_nothing(self):
        s, tid, reply, book = finished()
        s.decide_review(reply, 'no_reply', None, 'owner', 'set aside for the test')     # no reply went out
        s.update_task(tid, {'Status': 'waiting'}, 'owner')
        decide_book(s, book, 'reject')
        self.assertNotIn(s.get_task(tid)['Status'], ('done', 'dropped'), 'nothing was closed out, so the task stays open')


class OneLine(unittest.TestCase):
    """EVERY CARD THAT WAITS IS IN THE ONE LINE (his live app, 2026-11-23): the playbook stood outside it, so the reply in front offered Send and
    close; the task closed, and its write-up drafted the playbook and opened the task again to ask for it."""
    def test_the_playbook_waits_behind_the_reply_and_nothing_offers_a_close_over_it(self):
        from taskuary import cardqueue, concierge
        s, tid, reply, book = finished()
        q = cardqueue.state(s, tid)
        self.assertEqual((q['live'], q['held']), ([reply], [book]))
        self.assertEqual(card.may_close(s, tid), 'the playbook')
        self.assertIn('not the last card', concierge.cannot({'tid': tid, 'kind': 'review', 'rid': reply, 'ref': 'TQ-1', 'draft': 'x'}, 'send_close', s))
        send(s, reply)
        self.assertEqual(cardqueue.state(s, tid)['live'], [book], 'the playbook stands next')
        self.assertEqual(card.may_close(s, tid), '')

    def test_a_close_out_is_one_card_with_the_reply_it_closes(self):
        from taskuary import cardqueue
        s, tid, reply, book = finished()
        s.decide_review(book, 'rejected', None, 'owner')
        co = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent',
                           'DraftText': json.dumps({'action': 'close_issue', 'repo': 'northwind/ledger', 'number': 12})})
        q = cardqueue.state(s, tid)
        self.assertEqual((q['live'], q['held']), ([reply, co], []))

    def test_his_close_asks_no_playbook_and_a_leftover_one_never_reopens_it(self):
        from taskuary import concierge, general, wrapup
        s = MemoryStore(); s.set_setting('playbooks_enabled', '1', 't')
        tid = s.create_task({'Title': 'Weekly vendor check', 'Kind': 'general', 'Status': 'open'}, 't')
        s.add_comment(tid, 'owner', general.USER_TYPE, 'Check every vendor billed this week for a W-9 and a matching remit-to. ' * 6)
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Checked Payworth, Spendly and Trainly: all on file, all matching. ' * 6)
        llm = lambda *a, **k: json.dumps({'playbook': {'slug': 'vendor-check', 'text': BOOK}})
        # ...the ending his close runs (writeup's, concierge.save_live's) - the same write-up that drafted it on his live app
        shut = wrapup.CLOSING.set(True)
        try:
            with mock.patch('taskuary.llm.build_llm', return_value=llm), mock.patch('taskuary.handbook.enabled', return_value=False):
                self.assertEqual(wrapup.wrap(s, tid, close=False, actor='owner')['proposed'], [])
        finally: wrapup.CLOSING.reset(shut)
        self.assertIsNone(card.pending(s, tid, 'playbook'))
        concierge.close_task(s, tid, 'owner')
        proposals.queue(s, tid, {'action': 'write_playbook', 'slug': 'vendor-check', 'text': BOOK, 'why': 'it recurs'}, 'assistant')
        proposals.hold_for_playbook(s, tid, 'assistant')
        self.assertEqual(s.get_task(tid)['Status'], 'done', 'his close stands')
        self.assertIsNone(card.pending(s, tid, 'playbook'))
