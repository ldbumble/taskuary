"""A CLOSED TASK THAT NEW MAIL REOPENS ARRIVES NOW (an owner screenshot, 2026-10-28). A task made two months before came back on a
chat this morning and sat on the table, and the rail's age column read "68d": its arrival was still the task's creation. The rail
orders and ages rows by arrival (2026-10-23) - a reopened task's arrival is the line that brought it back. An old task nothing
reopened keeps its age, and a reply on an open one is +N, never a move."""
import unittest
from unittest import mock
from taskuary import funnel, ingest, processing_unread, timewords
from test_funnel import ago, ahead, mail, store


def rail(s):
    s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        return processing_unread.build(s, live_state=[], include_read=True)['items']


def old_task(s, title, days, who='Erin Blake', email='erin@vendor.example'):
    tid = s.create_task({'Title': title, 'Kind': 'task', 'Status': 'open'}, 'owner')
    s.cx.execute('UPDATE task SET CreatedAt=? WHERE TaskId=?', (ago(days=days), tid)); s.cx.commit()
    mail(s, title, who=who, email=email, hours=days * 24, tid=tid, conv=f'chat:{tid}', channel='teams')
    return tid


class ReopenedArrivesNow(unittest.TestCase):
    def setUp(self):
        self.s = s = store()
        self.quiet = old_task(s, 'Send the vendor the Q3 export', 3, who='Gail Moreno', email='gail@vendor.example')
        self.back = old_task(s, 'Will the connector work with the ledger?', 68)
        s.update_task(self.back, {'Status': 'done'}, 'owner')
        m = mail(s, 'Will the connector work with the ledger?', body='One more: will it connect with the portal too?', hours=0.1,
                 tid=self.back, conv=f'chat:{self.back}', channel='teams')
        ingest._reopen(s, self.back, {'from_name': 'Erin Blake', 'subject': 'Will it connect with the portal too?'}, 'router',
                       {'intent': 'reply_only'})
        self.sent = s.get_message(m)['SentAt'] if hasattr(s, 'get_message') else ago(0.1)
        self.rows = {i['tid']: i for i in rail(s) if i.get('tid') in (self.quiet, self.back)}

    def test_the_reopened_task_arrives_with_the_line_that_reopened_it(self):
        at = self.rows[self.back]['arrived_at']
        self.assertEqual(str(at)[:16], str(self.sent)[:16])
        self.assertLess(timewords.mins(at), 30)          # the age column's "< 30m" (timeWords.band), not "68d"

    def test_an_old_task_nothing_reopened_keeps_its_age(self):
        self.assertGreater(timewords.mins(self.rows[self.quiet]['arrived_at']), 3 * 24 * 60 - 5)

    def test_the_rail_and_the_walk_order_follow_the_new_arrival(self):
        rows = sorted(self.rows.values(), key=funnel.order_key)       # one key for the rail, desktop Next and phone Next
        self.assertEqual([r['tid'] for r in rows], [self.quiet, self.back])

    def test_a_reply_after_the_reopen_does_not_move_it(self):
        before = self.rows[self.back]['arrived_at']
        m = mail(self.s, 'Will the connector work with the ledger?', body='Also the census?', hours=0.01, tid=self.back,
                 conv=f'chat:{self.back}', channel='teams')
        self.s.cx.execute('UPDATE message SET CreatedAt=? WHERE MessageId=?', (ahead(1), m)); self.s.cx.commit()   # a later poll
        self.assertEqual(next(i for i in rail(self.s) if i.get('tid') == self.back)['arrived_at'], before)

    def test_funnel_stamps_the_same_arrival_for_a_row_without_one(self):
        self.assertEqual(processing_unread.came_back(self.s, self.back, self.s.list_messages(self.back)), self.rows[self.back]['arrived_at'])
        self.assertIsNone(processing_unread.came_back(self.s, self.quiet, self.s.list_messages(self.quiet)))


if __name__ == '__main__': unittest.main()
