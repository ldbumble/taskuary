"""Deleted where it came from is WITHDRAWN here - not deleted, and not still on your list.

A Timeline row can have a task, an agent session, a drafted reply and an audit trail hanging off
it. A message vanishing from a chat must not silently destroy that work, so the row stays and its
history stays; it just stops pretending to be something waiting on the owner.

Teams can tell us: its delta reports deletedDateTime, and the ingest loop was already skipping
those - which did nothing for a message we had ALREADY taken in. Mail cannot yet: it is fetched
as a plain $top list with no deletion signal, so that half needs a delta migration first.
"""
import unittest

from taskuary.store import MemoryStore


def _store():
    s = MemoryStore()
    mid = s.add_message({'ExternalId': 'teams:c1:m1', 'ConversationId': 'teams:c1', 'Channel': 'teams',
                         'SourceName': 'me@ours.com', 'Subject': 'Teams chat with Mindy',
                         'FromName': 'Mindy', 'SentAt': '2026-08-31 12:00:00',
                         'BodyText': 'ignore that, wrong person', 'Status': 'filed'})
    tid = s.create_task({'Title': 'wrong person', 'Kind': 'task', 'Status': 'open'}, 'o')
    s.attach_message(mid, tid)
    return s, mid, tid


def _row(s, mid):
    return {r['MessageId']: r for r in s.feed(limit=50)}[mid]


class WithdrawingAMessage(unittest.TestCase):
    def test_it_marks_rather_than_removes(self):
        s, mid, tid = _store()
        self.assertTrue(s.withdraw_message('teams:c1:m1'))
        r = _row(s, mid)
        self.assertEqual(r['MsgStatus'], 'withdrawn')
        self.assertIsNotNone(s.get_task(tid))            # the work survives the message

    def test_it_stops_being_something_waiting_on_you(self):
        s, mid, _ = _store()
        self.assertEqual(_row(s, mid)['NeedsYou'], 1)
        s.withdraw_message('teams:c1:m1')
        self.assertEqual(_row(s, mid)['NeedsYou'], 0)

    def test_the_task_is_told_why_it_is_suddenly_quiet(self):
        s, _, tid = _store()
        s.withdraw_message('teams:c1:m1')
        self.assertTrue(any('deleted this message' in c['Body'] for c in s.list_comments(tid)))

    def test_doing_it_twice_changes_nothing(self):
        s, _, tid = _store()
        self.assertTrue(s.withdraw_message('teams:c1:m1'))
        self.assertFalse(s.withdraw_message('teams:c1:m1'))
        self.assertEqual(len([c for c in s.list_comments(tid) if 'deleted this message' in c['Body']]), 1)

    def test_a_message_we_never_had_is_not_invented(self):
        s, _, _ = _store()
        self.assertFalse(s.withdraw_message('teams:c1:never-seen'))

    def test_it_is_written_down(self):
        """Something removing a row from the owner's day has to leave a trace."""
        s, mid, _ = _store()
        s.withdraw_message('teams:c1:m1')
        hits = [a for a in s._rows("SELECT * FROM audit WHERE EntityType='message' AND Action='withdrawn'")]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]['EntityId'], mid)


if __name__ == '__main__':
    unittest.main()
