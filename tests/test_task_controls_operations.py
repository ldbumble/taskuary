"""The task-view buttons run the shared operations road (PW-215/216): the same checks and outcomes as the
assistant's confirmation card - no false success, no duplicate start, a stale click refused."""
import unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import concierge, server, terminal
from taskuary.store import MemoryStore


class Live:
    def __init__(self, sid='s1'): self.sid, self.alive, self.agent, self.label, self.mode = sid, True, 'coder', 'coder', 'terminal'


class TaskControls(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)

    def run_op(self, kind, target, params=None):
        p = self.c.post('/api/operations', json={'kind': kind, 'target': target, 'params': params or {}}).json()
        return p, self.c.post(f"/api/operations/{p['id']}/execute", json={'version': p['version']})

    def test_mark_task_done_closes_the_task_and_ends_its_live_session(self):
        tid = self.s.create_task({'Title': 'Work', 'Kind': 'coding'}, 'owner')
        live = Live()
        with mock.patch.object(terminal, 'session_for', return_value=live), mock.patch.object(terminal, 'close', return_value=True) as close:
            _, r = self.run_op('task.complete', tid)
        self.assertEqual(r.status_code, 200); self.assertEqual(r.json()['status'], 'done')
        self.assertEqual(self.s.get_task(tid)['Status'], 'done')
        close.assert_called_once_with('s1')

    def test_reopen_changes_status_only_and_starts_no_worker(self):
        tid = self.s.create_task({'Title': 'Work', 'Kind': 'coding'}, 'owner')
        self.s.update_task(tid, {'Status': 'done'}, 'owner')
        with mock.patch.object(server.hub_term, 'start_on_task') as start:
            _, r = self.run_op('task.reopen', tid)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.s.get_task(tid)['Status'], 'open')
        start.assert_not_called()

    def test_close_reply_without_sending_also_handles_an_already_finished_task(self):
        for status in ('open', 'done'):
            with self.subTest(status=status):
                mid = self.s.add_message({'ExternalId': f'close-unsent-{status}', 'Channel': 'email',
                                         'FromEmail': 'sender@example.com', 'BodyText': 'Please check this.'})
                tid = self.s.create_task({'Title': 'Reply ready', 'Tags': 'stay:open'}, 'owner')
                self.s.attach_message(mid, tid)
                self.s.update_task(tid, {'Status': status}, 'owner')
                rid = self.s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft',
                                         'Status': 'pending', 'DraftText': 'Checked.'})
                chips = concierge.chips_for(self.s, {'kind': 'review', 'tid': tid, 'mid': mid, 'rid': rid})
                self.assertTrue(any(x['verb'] == 'close' and x['label'] == 'Close without sending' for x in chips))
                with mock.patch.object(terminal, 'session_for', return_value=None), \
                     mock.patch.object(server, 'decide') as send:
                    _, response = self.run_op('task.complete', tid)
                self.assertEqual(response.json()['status'], 'done')
                self.assertEqual(self.s.get_task(tid)['Status'], 'done')
                self.assertEqual(self.s.get_review(rid)['Status'], 'no_reply')
                send.assert_not_called()

    def test_coding_start_with_an_unknown_agent_is_refused_and_the_task_is_untouched(self):
        tid = self.s.create_task({'Title': 'Work', 'Kind': 'coding'}, 'owner')
        _, r = self.run_op('dispatch.prepare', tid, {'kind': 'coding', 'agent': 'nobody-here'})
        out = r.json()
        self.assertEqual(out['status'], 'error'); self.assertIn('unknown agent', out['error'])
        self.assertEqual(self.s.get_task(tid)['Status'], 'open')

    def test_coding_start_on_a_task_with_a_live_worker_is_refused_without_a_duplicate(self):
        tid = self.s.create_task({'Title': 'Work', 'Kind': 'general'}, 'owner')
        with mock.patch.object(server.hub_term, 'session_for', return_value=Live()), \
             mock.patch.object(server.hub_term, 'start_on_task') as start:
            _, r = self.run_op('dispatch.prepare', tid, {'kind': 'coding'})
        out = r.json()
        self.assertEqual(out['status'], 'error'); self.assertIn('already working', out['error'])
        start.assert_not_called()
        self.assertEqual(self.s.get_task(tid)['Kind'], 'general')

    def test_the_same_confirmation_twice_is_one_effect(self):
        tid = self.s.create_task({'Title': 'Work', 'Kind': 'coding'}, 'owner')
        with mock.patch.object(terminal, 'session_for', return_value=None):
            p, a = self.run_op('task.complete', tid)
            b = self.c.post(f"/api/operations/{p['id']}/execute", json={'version': p['version']})
        self.assertEqual(a.json()['status'], 'done'); self.assertTrue(b.json()['duplicate'])

    def test_stop_agent_ends_only_the_worker(self):
        tid = self.s.create_task({'Title': 'Work', 'Kind': 'coding'}, 'owner')
        self.s.update_task(tid, {'Status': 'in_progress'}, 'owner')
        with mock.patch.object(server.hub_term, 'session_for', return_value=Live()), \
             mock.patch.object(server.hub_term, 'close', return_value=True), \
             mock.patch.object(server, '_refresh_chat_context', return_value={}):
            _, r = self.run_op('agent.stop', tid)
        self.assertEqual(r.json()['status'], 'done')
        self.assertEqual(self.s.get_task(tid)['Status'], 'open', 'stopping the worker reopens, never completes')


if __name__ == '__main__': unittest.main()
