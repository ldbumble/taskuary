"""NOTHING CLOSES A TASK AUTOMATICALLY WHILE ANYTHING ON IT IS STILL WORKING (the owner, 2026-11-01: "if agent screen is still open and
you hit send message it should not close the tasks ... If anything still working never close the task automatically"). The shape: a coding
task's agent sat at its prompt waiting on the owner, the owner pressed Send on the drafted reply in Close out, and the row left the rail
with the agent still drawn on the canvas. Every automatic close asks one check (workerstate.live_work); the owner's own Mark done does not.
Invented Northwind people only."""
import unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import channels, concierge, proposals, selfclose, terminal as term, workerstate as ws
from taskuary.store import MemoryStore
from tests.test_explicit_completion import Base, live


class LiveWork(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = self.s.create_task({'Title': 'Fix the ledger export for Erin', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        self._sessions = dict(term.SESSIONS); term.SESSIONS.clear()
    def tearDown(self): term.SESSIONS.clear(); term.SESSIONS.update(self._sessions)

    def test_nothing_live_is_nothing(self): self.assertEqual(ws.live_work(self.s, self.tid), [])

    def test_an_agent_waiting_on_the_owner_is_live(self):
        term.SESSIONS['run1'] = SimpleNamespace(sid='run1', task_id=self.tid, alive=True)
        ws.record(self.s, self.tid, 'run1', 'input_needed', text='Which export format should Erin get?', source='hook')
        self.assertEqual(ws.live_work(self.s, self.tid), [ws.LIVE_SESSION])
        self.assertEqual(ws.live_work(self.s, self.tid, but='run1'), [], 'the asking session is never counted against itself')

    def test_a_quick_call_a_routine_and_a_queued_start_are_live(self):
        from taskuary import quickwork, workflows
        with mock.patch.object(quickwork, 'RUNNING', {self.tid}), mock.patch.object(workflows, '_STARTING', {self.tid}):
            self.s.enqueue_dispatch(self.tid, None, 'claude', 'every slot is busy')
            got = ws.live_work(self.s, self.tid)
            self.assertIn('its routine is still running', got); self.assertIn('an agent is queued to start on it', got)
            self.assertTrue(any('quick answer' in x for x in got))
            self.assertNotIn('its routine is still running', ws.live_work(self.s, self.tid, skip=('routine',)))

    def test_send_with_a_live_waiting_agent_keeps_it_open_and_says_why(self):
        term.SESSIONS['run1'] = SimpleNamespace(sid='run1', task_id=self.tid, alive=True)
        out = concierge.close_after_send(self.s, self.tid)
        self.assertFalse(out['closed']); self.assertEqual(out['kept_open'], [ws.LIVE_SESSION])
        self.assertNotEqual(self.s.get_task(self.tid)['Status'], 'done')
        self.assertIn('Sent. Kept open: The agent session on it is still open.', [c['Body'] for c in self.s.list_comments(self.tid)])

    def test_send_with_nothing_live_still_closes(self):
        self.assertTrue(concierge.close_after_send(self.s, self.tid)['closed'])
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')

    def test_a_playbook_answer_does_not_close_under_a_live_agent(self):
        self.s.update_task(self.tid, {'Status': 'waiting', 'Tags': proposals.HELD}, 'owner')
        term.SESSIONS['run1'] = SimpleNamespace(sid='run1', task_id=self.tid, alive=True)
        with mock.patch.object(proposals, 'owed', return_value=False):
            proposals.playbook_answered(self.s, self.tid, 'owner')
        t = self.s.get_task(self.tid)
        self.assertNotEqual(t['Status'], 'done'); self.assertNotIn(proposals.HELD, str(t.get('Tags') or ''))

    def test_an_item_ended_upstream_does_not_close_under_a_live_agent(self):
        term.SESSIONS['run1'] = SimpleNamespace(sid='run1', task_id=self.tid, alive=True)
        said = 'The pull request this task came from was merged on GitHub (northwind/ledger#12), so there is nothing left to do here.'
        self.assertIs(channels.close_upstream_ended(self.s, self.tid, said), False)
        self.assertNotEqual(self.s.get_task(self.tid)['Status'], 'done')
        self.assertIn(said, [c['Body'] for c in self.s.list_comments(self.tid)], 'the cause is still said, once')


class SelfCloseUnderAnotherSession(Base):
    def test_done_while_another_session_on_the_task_is_live_does_not_close(self):
        term.SESSIONS['run1'] = live(self.tid); term.SESSIONS['run2'] = live(self.tid, 'run2')
        out = selfclose.declare(self.s, self.tid, 'fixed the cron', 'agent', sid='run2')
        self.assertFalse(out.get('closed')); self.assertIn(ws.OTHER_SESSION, out['why'])
        self.assertEqual(self.closed, []); self.assertNotEqual(self.s.get_task(self.tid)['Status'], 'done')
        self.assertIn('The agent says it is finished: fixed the cron', ' '.join(c['Body'] for c in self.s.list_comments(self.tid)))

    def test_done_from_the_only_live_session_still_ends_its_run(self):
        term.SESSIONS['run1'] = live(self.tid)
        self.assertTrue(selfclose.declare(self.s, self.tid, 'fixed the cron', 'agent', sid='run1').get('ended'))

    def test_done_while_a_routine_runs_on_the_task_does_not_close(self):
        from taskuary import workflows
        term.SESSIONS['run1'] = live(self.tid)
        with mock.patch.object(workflows, '_STARTING', {self.tid}):
            out = selfclose.declare(self.s, self.tid, 'fixed the cron', 'agent', sid='run1')
        self.assertFalse(out.get('closed')); self.assertIn('routine', out['why'])


if __name__ == '__main__': unittest.main()
