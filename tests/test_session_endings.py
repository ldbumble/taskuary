"""How an agent session ends (the owner, 2026-09-25, A1-A6 and A22 of the agent lifecycle map):
A1/A2 a session you end is `session saved` - never "left without finishing", never "open again, nobody is working it";
A3 a task waiting to start says the real reason; A5 cancelling a queued start takes the agent off;
A6 a reply held while the agent worked comes back when the session ends, unless the agent wrote a newer one."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import coder, concierge, funnel, server, terminal
from taskuary.store import MemoryStore


def handed(s, **over):
    return s.create_task({'Title': 'Fix the nightly export', 'Kind': 'coding', 'Status': 'in_progress',
                          'Assignee': 'agent:coder', **over}, 'triage')


class CloseIsOnPurposeTests(unittest.TestCase):
    def test_a_close_marks_the_session_so_its_end_does_not_reopen_the_task(self):
        t = mock.Mock(); terminal.SESSIONS['sid-x'] = t
        self.assertTrue(terminal.close('sid-x'))
        self.assertTrue(t.on_purpose); t.close.assert_called_once()


class SessionSavedTests(unittest.TestCase):
    def test_save_and_end_session_leaves_the_task_open_saved_and_says_so(self):
        s = MemoryStore(); tid = handed(s)
        coder._ended(s, tid, False, 'owner')
        self.assertEqual(s.get_task(tid)['Status'], 'open')
        self.assertTrue(funnel.session_saved(s, tid))
        self.assertTrue(funnel.agent_left(s, tid))
        self.assertIn('You ended the session', funnel.not_started_why(s, tid))
        self.assertNotIn('left without finishing', funnel.not_started_why(s, tid))

    def test_closing_the_task_is_not_a_saved_session(self):
        s = MemoryStore(); tid = handed(s)
        coder._ended(s, tid, True, 'owner')
        self.assertFalse(funnel.session_saved(s, tid))


class RealReasonTests(unittest.TestCase):
    def test_waiting_to_start_names_the_queue(self):
        s = MemoryStore(); tid = handed(s, Status='open')
        s.enqueue_dispatch(tid, None, 'coder', 'all slots busy')
        self.assertIn('next in line', funnel.not_started_why(s, tid))
        s.dispatch_failed(tid, 'coder is not installed', permanent=True)
        self.assertIn('could not start: coder is not installed', funnel.not_started_why(s, tid))


class CancelTakesTheAgentOffTests(unittest.TestCase):
    def test_cancel_leaves_the_task_yours(self):
        s = MemoryStore(); tid = handed(s, Status='open')
        s.enqueue_dispatch(tid, None, 'coder', 'all slots busy')
        with mock.patch.object(server, 'store', s):
            self.assertEqual(TestClient(server.app).delete(f'/api/tasks/{tid}/dispatch').status_code, 200)
        self.assertFalse(s.get_task(tid).get('Assignee'))


class HeldReplyComesBackTests(unittest.TestCase):
    def _draft(self, s, tid, status='pending'):
        mid = s.add_message({'TaskId': tid, 'ExternalId': f'x{status}', 'Channel': 'email', 'Subject': 'Export', 'FromName': 'Erin Blake',
                             'FromEmail': 'erin@northwind.example', 'BodyText': 'Is it fixed?', 'Status': 'routed'})
        return s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': status, 'DraftText': 'Looking at it now.'})

    def test_a_held_reply_is_back_when_the_session_ends(self):
        s = MemoryStore(); tid = handed(s)
        rid = self._draft(s, tid); s.hold_reviews(tid)
        self.assertEqual(s.get_review(rid)['Status'], 'held')
        terminal.release_task(s, tid)
        self.assertEqual(s.get_review(rid)['Status'], 'pending')

    def test_unless_the_agent_wrote_a_newer_reply(self):
        s = MemoryStore(); tid = handed(s)
        old = self._draft(s, tid); s.hold_reviews(tid)
        new = self._draft(s, tid, 'pending')
        terminal.release_held(s, tid)
        self.assertEqual((s.get_review(old)['Status'], s.get_review(new)['Status']), ('closed_unsent', 'pending'))

    def test_mark_done_decides_a_held_reply_too(self):
        s = MemoryStore(); tid = handed(s)
        rid = self._draft(s, tid); s.hold_reviews(tid)
        concierge.close_task(s, tid)
        self.assertEqual(s.get_review(rid)['Status'], 'no_reply')


if __name__ == '__main__': unittest.main()


class MergedPullRequestOwesNoReplyTests(unittest.TestCase):
    def test_no_reply_is_drafted_when_the_pull_request_ended_it(self):
        """A21: close_upstream_ended passes no_reply - nobody is owed an answer on a merged or closed PR."""
        s = MemoryStore()
        tid = s.create_task({'Title': 'Export fix', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        s.add_message({'TaskId': tid, 'ExternalId': 'gh-1', 'Channel': 'github', 'Subject': 'Fix the export', 'FromName': 'Erin Blake',
                       'FromEmail': 'erin@northwind.example', 'BodyText': 'PR opened', 'Status': 'routed'})
        prev, coder.REFRESH = coder.REFRESH, None
        try:
            with mock.patch('taskuary.responder.write_draft', return_value='Merged, thanks.') as draft:
                out = coder.finish(s, tid, {'summary': 'merged', 'outcome': 'did_work'}, None, 'coder', no_reply=True)
        finally: coder.REFRESH = prev
        draft.assert_not_called()
        self.assertFalse(out.get('drafting'))
        self.assertEqual(s.list_reviews('pending'), [])
