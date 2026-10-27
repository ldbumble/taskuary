"""How an agent session ends (the owner, 2026-09-25, A1-A6 and A22 of the agent lifecycle map):
A1/A2 a session you end is `session saved` - never "left without finishing", never "open again, nobody is working it";
A3 a task waiting to start says the real reason; A5 cancelling a queued start takes the agent off;
A6 a reply held while the agent worked comes back when the session ends, unless the agent wrote a newer one."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import wrapup, concierge, funnel, server, terminal
from taskuary.store import MemoryStore


def handed(s, **over):
    return s.create_task({'Title': 'Fix the nightly export', 'Kind': 'coding', 'Status': 'in_progress',
                          'Assignee': 'agent:coding', **over}, 'triage')


class CloseIsOnPurposeTests(unittest.TestCase):
    def test_a_close_marks_the_session_so_its_end_does_not_reopen_the_task(self):
        t = mock.Mock(); terminal.SESSIONS['sid-x'] = t
        self.assertTrue(terminal.close('sid-x'))
        self.assertTrue(t.on_purpose); t.close.assert_called_once()


class SessionSavedTests(unittest.TestCase):
    def test_save_and_end_session_leaves_the_task_open_saved_and_says_so(self):
        s = MemoryStore(); tid = handed(s)
        wrapup._ended(s, tid, False, 'owner')
        self.assertEqual(s.get_task(tid)['Status'], 'open')
        self.assertTrue(funnel.session_saved(s, tid))
        self.assertTrue(funnel.agent_left(s, tid))
        self.assertIn('You stopped it', funnel.not_started_why(s, tid))
        self.assertNotIn('left without finishing', funnel.not_started_why(s, tid))

    def test_closing_the_task_is_not_a_saved_session(self):
        s = MemoryStore(); tid = handed(s)
        wrapup._ended(s, tid, True, 'owner')
        self.assertFalse(funnel.session_saved(s, tid))


class RealReasonTests(unittest.TestCase):
    def test_waiting_to_start_names_the_queue(self):
        s = MemoryStore(); tid = handed(s, Status='open')
        s.enqueue_dispatch(tid, None, 'coding', 'all slots busy')
        self.assertIn('Waiting its turn. Every agent slot is busy', funnel.not_started_why(s, tid))
        s.dispatch_failed(tid, 'coding is not installed', permanent=True)
        self.assertIn("Couldn't start: coding is not installed. This is a setup problem", funnel.not_started_why(s, tid))


class CancelTakesTheAgentOffTests(unittest.TestCase):
    def test_cancel_leaves_the_task_yours(self):
        s = MemoryStore(); tid = handed(s, Status='open')
        s.enqueue_dispatch(tid, None, 'coding', 'all slots busy')
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
        prev, wrapup.REFRESH = wrapup.REFRESH, None
        try:
            with mock.patch('taskuary.responder.write_draft', return_value='Merged, thanks.') as draft:
                out = wrapup.finish(s, tid, {'summary': 'merged', 'outcome': 'did_work'}, None, 'coding', no_reply=True)
        finally: wrapup.REFRESH = prev
        draft.assert_not_called()
        self.assertFalse(out.get('drafting'))
        self.assertEqual(s.list_reviews('pending'), [])


class ContinuedIsNoLongerSavedTests(unittest.TestCase):
    def test_a_general_session_that_starts_again_clears_saved(self):
        """Continue on a general task opened a new conversation session under `session:saved`: its turn then died mid-way and the
        Result said "You stopped it and its report is written" over the failure (the agents walk, 2026-10-26)."""
        from taskuary import general, ownwork
        s = MemoryStore(); tid = s.create_task({'Title': 'Compare payroll vendors', 'Kind': 'general', 'Status': 'in_progress'}, 'o')
        s.tag_task(tid, terminal.SAVED, True, 'owner')
        fake = mock.Mock(sid='g-saved', browser_wanted=False, pick='', started='2026-10-26 09:00:00')
        try:
            with mock.patch.object(general, 'GeneralSession', return_value=fake), mock.patch.object(ownwork, 'ensure'):
                general.start_session(s, tid, actor='owner')
        finally: terminal.SESSIONS.pop('g-saved', None)
        self.assertNotIn(terminal.SAVED, str(s.get_task(tid).get('Tags') or ''))


class SavedIsItsOwnLaneTests(unittest.TestCase):
    def test_a_session_you_ended_is_session_saved_on_the_rail(self):
        """A1 + the one vocabulary: `saved` (💾 session saved), never `stopped` (⏹ agent stopped)."""
        from test_funnel import ago
        from taskuary import processing_unread
        s = MemoryStore(); tid = handed(s, Status='open')
        s.add_message({'TaskId': tid, 'ExternalId': 'e1', 'Channel': 'email', 'Subject': 'Export', 'FromName': 'Erin Blake',
                       'FromEmail': 'erin@northwind.example', 'SentAt': ago(1), 'BodyText': 'Is it fixed?', 'Status': 'routed'})
        s.tag_task(tid, terminal.SAVED, True, 'owner')
        s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            lanes = [i['lane'] for i in processing_unread.build(s, live_state=[], include_read=True)['items'] if i.get('tid') == tid]
        self.assertEqual(lanes, ['saved'])
        self.assertEqual(funnel.LANE_WORDS['saved'][0], 'stopped and saved')
