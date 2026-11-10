"""A reply an EARLIER agent session drafted is not the task's reply once a newer session is on it.

The owner (2026-11-03): "when you continue on general agent it shows the prior reply on bottom that the agent generated. Don't show
that reply if it was based off another general session not the latest one". A draft remembers the session that wrote it (DraftSid);
a newer session holds it out of sight while it works, takes its place when it drafts, and closes it as superseded when it ends - kept,
never overwritten, so it can still be read and brought back. A draft the owner edited or readdressed is theirs and stays. Invented people only.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import server, terminal, wrapup
from taskuary.store import MemoryStore

OLD = 'Hi Gail - the October invoices are reconciled; two vendor credits are still open.'
NEW = 'Hi Gail - all October invoices are reconciled now, the vendor credits included.'


def task_with(s):
    tid = s.create_task({'Title': 'October invoices', 'Kind': 'general', 'Status': 'in_progress'}, 't')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'g-1', 'ConversationId': 'conv-g', 'Channel': 'email',
                         'SourceName': 'alex@northwind.example', 'Subject': 'October invoices', 'FromName': 'Gail Moreno',
                         'FromEmail': 'gail@northwind.example', 'SentAt': '2026-11-03 09:00:00',
                         'BodyText': 'Are the October invoices reconciled?', 'Status': 'routed'})
    return tid, mid


def reply_rows(s, tid): return [r for r in s._rows('SELECT * FROM review WHERE TaskId=? ORDER BY ReviewId', (tid,)) if r['Kind'] != 'slot']


class Base(unittest.TestCase):
    def setUp(self): self._prev, wrapup.REFRESH = wrapup.REFRESH, None
    def tearDown(self): wrapup.REFRESH = self._prev


class StaleSessionDraftTests(Base):
    def test_a_draft_remembers_the_session_that_wrote_it(self):
        s = MemoryStore(); tid, _ = task_with(s)
        rid = wrapup.agent_reply(s, tid, OLD, 'assistant', sid='s-old')['review_id']
        self.assertEqual(s.get_review(rid)['DraftSid'], 's-old')

    def test_a_newer_session_holds_the_earlier_sessions_draft(self):
        s = MemoryStore(); tid, _ = task_with(s)
        rid = wrapup.agent_reply(s, tid, OLD, 'assistant', sid='s-old')['review_id']
        self.assertEqual(wrapup.hold_stale(s, tid, 's-new'), 1)
        self.assertEqual(s.get_review(rid)['Status'], 'held')
        self.assertIsNone(s.pending_review(tid), 'nothing pending: Close out and Send have no stale draft to show or send')
        # ...and its own session's draft is never held by it
        rid2 = wrapup.agent_reply(s, tid, NEW, 'assistant', sid='s-new')['review_id']
        self.assertEqual(wrapup.hold_stale(s, tid, 's-new'), 0)
        self.assertEqual(s.get_review(rid2)['Status'], 'pending')

    def test_a_draft_the_owner_edited_stays(self):
        s = MemoryStore(); tid, _ = task_with(s)
        rid = wrapup.agent_reply(s, tid, OLD, 'assistant', sid='s-old')['review_id']
        with mock.patch.object(server, 'store', s):
            TestClient(server.app).patch(f'/api/reviews/{rid}', json={'body': OLD + ' Thanks.'})
        self.assertEqual(s.get_review(rid)['DraftSid'], wrapup.OWNER_SID)
        self.assertEqual(wrapup.hold_stale(s, tid, 's-new'), 0)
        self.assertEqual(s.get_review(rid)['Status'], 'pending')

    def test_taskuarys_own_draft_is_not_an_agent_sessions(self):
        s = MemoryStore(); tid, mid = task_with(s)
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'Reason': 'r'})
        s.update_review_draft(rid, 'Yes, done.', None)
        self.assertEqual(wrapup.hold_stale(s, tid, 's-new'), 0)

    def test_the_new_sessions_draft_takes_its_place_and_the_old_one_is_kept(self):
        s = MemoryStore(); tid, _ = task_with(s)
        old = wrapup.agent_reply(s, tid, OLD, 'assistant', sid='s-old')['review_id']
        wrapup.hold_stale(s, tid, 's-new')
        new = wrapup.agent_reply(s, tid, NEW, 'assistant', sid='s-new')['review_id']
        self.assertNotEqual(old, new, 'a new review - the earlier words are never written over')
        o, n = s.get_review(old), s.get_review(new)
        self.assertEqual((o['Status'], o['DraftText']), ('closed_unsent', OLD))
        self.assertIn('superseded', o['DecideNote'])
        self.assertEqual((n['Status'], n['DraftText'], n['DraftSid']), ('pending', NEW, 's-new'))
        self.assertEqual(s.pending_review(tid)['ReviewId'], new)

    def test_a_held_stale_draft_left_over_is_closed_when_the_session_ends(self):
        s = MemoryStore(); tid, _ = task_with(s)
        old = wrapup.agent_reply(s, tid, OLD, 'assistant', sid='s-old')['review_id']
        wrapup.hold_stale(s, tid, 's-new')
        with mock.patch('taskuary.workerstate.current_sid', return_value='s-new'): terminal.release_held(s, tid, 'owner')
        self.assertEqual(s.get_review(old)['Status'], 'closed_unsent')
        # ...and it can still be brought back to send (T11)
        with mock.patch.object(server, 'store', s):
            self.assertEqual(TestClient(server.app).post(f'/api/reviews/{old}/reopen').status_code, 200)
        self.assertEqual(s.get_review(old)['Status'], 'pending')

    def test_a_triage_draft_held_by_a_session_still_comes_back(self):
        s = MemoryStore(); tid, mid = task_with(s)
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'Reason': 'r'})
        s.update_review_draft(rid, 'Looking into it.', None)
        s.hold_reviews(tid, 'held while an agent works the task')
        with mock.patch('taskuary.workerstate.current_sid', return_value='s-new'): terminal.release_held(s, tid, 'owner')
        self.assertEqual(s.get_review(rid)['Status'], 'pending', 'A6 stands for drafts no agent session wrote')

    def test_the_wrap_up_raises_a_fresh_reply_instead_of_bringing_the_stale_draft_back(self):
        s = MemoryStore(); tid, mid = task_with(s)
        old = wrapup.agent_reply(s, tid, OLD, 'assistant', sid='s-old')['review_id']
        wrapup.hold_stale(s, tid, 's-new')
        with mock.patch('taskuary.workerstate.current_sid', return_value='s-new'), \
             mock.patch('taskuary.responder.write_draft', return_value=NEW) as redraft:
            owed = wrapup.raise_reply(s, tid, mid, None)
        redraft.assert_not_called()                          # ...the reply owed, the new session's agent's to write (2026-11-10)
        self.assertEqual(s.get_review(old)['Status'], 'closed_unsent')
        self.assertEqual(s.pending_review(tid)['ReviewId'], owed); self.assertNotEqual(owed, old)

    def test_send_refuses_a_held_stale_draft(self):
        s = MemoryStore(); tid, _ = task_with(s)
        old = wrapup.agent_reply(s, tid, OLD, 'assistant', sid='s-old')['review_id']
        wrapup.hold_stale(s, tid, 's-new')
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_refresh_chat_context', return_value=None), \
             mock.patch('taskuary.outbound.send_out') as send:
            r = TestClient(server.app).post(f'/api/reviews/{old}/decide', json={'verb': 'approve', 'final_text': OLD})
        self.assertEqual(r.status_code, 409, r.text)
        send.assert_not_called()
        self.assertEqual(s.get_review(old)['Status'], 'held')

    def test_continue_holds_the_earlier_draft_before_it_answers(self):
        s = MemoryStore(); tid, _ = task_with(s)
        old = wrapup.agent_reply(s, tid, OLD, 'assistant', sid='s-old')['review_id']
        s.update_task(tid, {'Status': 'waiting'}, 't')
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=True), \
             mock.patch('taskuary.general.provider_options', return_value=['x']), mock.patch('taskuary.general.session_for', return_value=None), \
             mock.patch('threading.Thread', side_effect=lambda target, **k: mock.Mock(start=lambda: None)):
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={})
        self.assertEqual(s.get_review(old)['Status'], 'held')

    def test_continuing_a_live_session_keeps_its_own_draft(self):
        s = MemoryStore(); tid, _ = task_with(s)
        old = wrapup.agent_reply(s, tid, OLD, 'assistant', sid='s-old')['review_id']
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=True), \
             mock.patch('taskuary.general.provider_options', return_value=['x']), \
             mock.patch('taskuary.general.session_for', return_value=mock.Mock(sid='s-old', alive=True)), \
             mock.patch('threading.Thread', side_effect=lambda target, **k: mock.Mock(start=lambda: None)):
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={})
        self.assertEqual(s.get_review(old)['Status'], 'pending', 'the same session, a new turn: its draft is the latest')


if __name__ == '__main__': unittest.main()
