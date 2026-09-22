"""A review that needs a task asks for one, by naming it.

Three callers file a decision nothing else owns - a setting proposed in chat, a Zoho invoice,
an outbound report - and with the Review tab gone they would have no page to be answered on.
They ask for a task here.

It is opt-IN. A blanket rule was tried first and is wrong: answering filed chatter is a reply,
not a project, and minting a task to hold that review puts a TQ badge on "it was just his
demo" (tests/test_api.py::test_replying_to_a_filed_message_creates_no_task). Nothing is
stranded either way - the funnel gives a task-less review the `approve` lane and the assistant
decides it by rid.
"""
import os, tempfile, unittest
from taskuary.store import SQLiteStore
from taskuary.testing import Factory, main


class AReviewThatNeedsATaskAsksForOne(unittest.TestCase):
    def setUp(self):
        self.fx = Factory()
        self.s = self.fx.s

    def test_a_review_with_no_task_gets_one(self):
        rid = self.s.add_review({'Kind': 'action', 'Status': 'pending', 'DraftText': '{"action": "settings"}',
                                 'Reason': 'you asked for this setting: where general work runs',
                                 '_task_title': 'Setting · where general work runs'})
        rv = self.s.get_review(rid)
        self.assertTrue(rv['TaskId'], 'a review with nowhere to be decided is one nobody can answer')
        self.assertEqual(self.s.get_task(rv['TaskId'])['Title'], 'Setting · where general work runs')

    def test_a_review_that_asks_for_no_task_keeps_none(self):
        """Answering filed chatter is a reply, not a project. It rides task-less and is decided
        in the assistant, which needs only the rid."""
        rid = self.s.add_review({'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Got it.',
                                 'Reason': 'you opened a reply on this message'})
        self.assertIsNone(self.s.get_review(rid)['TaskId'])

    def test_a_review_that_names_its_task_is_left_alone(self):
        tid = self.s.create_task({'Title': 'already mine', 'Status': 'open'}, 'test')
        rid = self.s.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'hi'})
        self.assertEqual(self.s.get_review(rid)['TaskId'], tid)

    def test_the_marker_fields_never_reach_the_review_row(self):
        rid = self.s.add_review({'Kind': 'action', 'Status': 'pending', 'DraftText': '{}',
                                 '_task_title': 'Invoice · Acme · September', '_task_kind': 'task'})
        rv = dict(self.s.get_review(rid))
        self.assertNotIn('_task_title', rv)
        self.assertNotIn('_task_kind', rv)
        self.assertEqual(self.s.get_task(rv['TaskId'])['Kind'], 'task')

    def test_the_three_callers_that_ask_all_get_one(self):
        for title in ('Setting · where general work runs', 'Invoice · Acme · September',
                      'Report · Morning brief → you'):
            rid = self.s.add_review({'Kind': 'outbound', 'Status': 'pending', 'DraftText': 'b',
                                     'Reason': 'r', '_task_title': title, '_task_kind': 'task'})
            self.assertEqual(self.s.get_task(self.s.get_review(rid)['TaskId'])['Title'], title)


class StrandedRowsAreBackfilled(unittest.TestCase):
    """Rows filed before add_review issued a task are still in live stores, and the tab that was
    their only surface is gone. Opening the store gives each one the task it should have had."""

    def test_reopening_gives_a_stranded_review_its_task(self):
        path = os.path.join(tempfile.mkdtemp(), 't.db')
        s = SQLiteStore(path)
        s.cx.execute("INSERT INTO review (TaskId, Kind, Status, DraftText, Reason, CreatedAt) "
                     "VALUES (NULL,'outbound','pending','body','Morning brief → you. Approve to send it.','2026-09-21 08:00:00')")
        # the guard was stamped on the first open, when there was nothing to find
        s.cx.execute("DELETE FROM setting WHERE Name='review_task_backfilled'")
        s.cx.commit()
        highest = s.cx.execute('SELECT MAX(TaskId) m FROM task').fetchone()['m'] or 0
        s.cx.close()

        s2 = SQLiteStore(path)
        rv = s2.cx.execute('SELECT TaskId FROM review').fetchone()
        self.assertTrue(rv['TaskId'], 'a stranded decision is one nobody can answer')
        self.assertGreater(rv['TaskId'], highest, 'a backfilled ref must never name existing work')
        task = s2.get_task(rv['TaskId'])
        self.assertEqual(task['Title'], 'Morning brief → you. Approve to send it.')
        self.assertEqual(task['Source'], 'review')
        self.assertEqual(s2.cx.execute('SELECT COUNT(*) c FROM review WHERE TaskId IS NULL').fetchone()['c'], 0)

    def test_the_backfill_runs_once(self):
        path = os.path.join(tempfile.mkdtemp(), 't.db')
        s = SQLiteStore(path)
        s.cx.execute("INSERT INTO review (TaskId, Kind, Status, DraftText, Reason, CreatedAt) "
                     "VALUES (NULL,'action','pending','{}','a setting waits for your yes','2026-09-21 08:00:00')")
        s.cx.execute("DELETE FROM setting WHERE Name='review_task_backfilled'")
        s.cx.commit(); s.cx.close()
        SQLiteStore(path).cx.close()
        s3 = SQLiteStore(path)
        self.assertEqual(s3.cx.execute("SELECT COUNT(*) c FROM task WHERE Source='review'").fetchone()['c'], 1,
                         'a second open must not mint a second task for the same review')


if __name__ == '__main__':
    main()
