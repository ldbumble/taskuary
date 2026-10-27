"""Remove - not a task acts at once and its Undo puts the task back (the owner, 2026-10-21: no "are you sure", Undo instead): the
task card had no Undo at all - the task, its draft, its notes and the thread's verdict were gone for good (2026-10-22)."""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import demo, recentlydeleted, server
from taskuary.store import MemoryStore
from tests.memlines import teaching


class NotATaskUndoTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)
        self.tid = self.s.create_task({'Title': 'Fuel card statement', 'Kind': 'general', 'Status': 'open'}, 'owner')
        self.mid = self.s.add_message({'TaskId': self.tid, 'ExternalId': 'undo-1', 'Channel': 'email', 'Subject': 'The fuel card statement',
                                       'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'BodyText': 'Can you send the fuel card statement?'})
        self.rid = self.s.add_review({'TaskId': self.tid, 'MessageId': self.mid, 'Kind': 'reply', 'DraftText': 'Attached.', 'Status': 'pending'})
        self.s.add_comment(self.tid, 'owner', 'human', 'asked accounting')

    def remove(self):
        with teaching('Fuel card statements are accounting\'s, never a task for you'):
            r = self.c.post(f'/api/tasks/{self.tid}/not-a-task')
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_remove_answers_with_what_the_undo_names(self):
        out = self.remove()
        self.assertEqual((out['kind'], out['title']), ('task', 'Fuel card statement'))
        self.assertIsNone(self.s.get_task(self.tid))
        self.assertNotIn('task', recentlydeleted.LISTED, 'an Undo line only - not listed under Recently deleted')

    def test_undo_puts_the_task_back_with_its_draft_notes_and_mail_and_lifts_the_verdict(self):
        out = self.remove()
        ignore = self.s._one("SELECT RouteId FROM route WHERE MessageId=? AND Decision='ignore'", (self.mid,))
        self.assertTrue(ignore, 'the thread was ruled on')
        self.assertIn("Fuel card statements are accounting's", self.s.get_doc('learned'))
        r = self.c.post(f"/api/deleted/{out['deleted']}/restore")
        self.assertEqual(r.status_code, 200, r.text)
        tid = r.json()['task_id']
        self.assertEqual(self.s.get_task(tid)['Title'], 'Fuel card statement')
        self.assertEqual(self.s.get_review(self.rid)['TaskId'], tid)
        self.assertEqual(self.s.get_review(self.rid)['DraftText'], 'Attached.')
        self.assertEqual([c['Body'] for c in self.s.list_comments(tid)], ['asked accounting'])
        self.assertEqual(self.s.get_message(self.mid)['TaskId'], tid)
        self.assertNotEqual(self.s.get_message(self.mid)['Status'], 'filed')
        self.assertIsNone(self.s._one('SELECT 1 FROM route WHERE RouteId=?', (ignore['RouteId'],)), 'the thread may open work again')
        self.assertNotIn("Fuel card statements are accounting's", self.s.get_doc('learned'), 'the line it taught is taken back')
        # ...once: a second Undo finds nothing
        self.assertEqual(self.c.post(f"/api/deleted/{out['deleted']}/restore").status_code, 404)

    def test_a_task_id_taken_since_gives_the_task_a_new_one_and_its_rows_follow(self):
        out = self.remove()
        snap = json.loads(self.s.get_deleted(out['deleted'])['DataJson'])
        self.s.put_back('task', {**snap['task'], 'Title': 'someone else'}, 'TaskId')       # the id is taken again
        r = self.c.post(f"/api/deleted/{out['deleted']}/restore").json()
        self.assertNotEqual(r['task_id'], self.tid)
        self.assertEqual(self.s.get_review(self.rid)['TaskId'], r['task_id'])
        self.assertEqual(self.s.get_task(self.tid)['Title'], 'someone else')

    def test_the_demo_lets_its_undo_through(self):
        with mock.patch.object(demo, 'enabled', return_value=True):
            self.assertEqual(demo.refuse('POST', '/api/deleted/7/restore'), '')


if __name__ == '__main__':
    unittest.main()
