"""A CLOSE OUT SEND CLOSES THE TASK ONLY WHEN NOTHING ON IT STILL WAITS ON THE OWNER (concierge.close_after_send, 2026-10-29). The shape
that broke it: the agent's `git push` was held for the owner's Approve, the owner closed the session, sent the reply, and the Send closed the
task - the push never approved, the commits never pushed, the task read done. Kept open, the task says why in the held step's own words; and
a held step outlives the session it was held in, still on the task and still approvable. Invented Northwind people and repositories only."""
import json, unittest
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, server, shellgate as sg, terminal, verdicts
from taskuary.store import MemoryStore
from taskuary.testing import Factory


def send_close(s, tid):
    with mock.patch.object(server, 'store', s), mock.patch.object(terminal, 'live_sessions', return_value=[]):
        c = TestClient(server.app)
        op = c.post('/api/operations', json={'kind': 'task.complete', 'target': tid, 'params': {'after_send': True}}).json()
        return c.post(f"/api/operations/{op['id']}/execute", json={'version': op['version']}).json()


class SendThenClose(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Fix the ledger export for Erin', kind='coding')

    def hold(self): sg.check(self.s, self.tid, 'run1', 'git push origin fix-export', 'Bash', r'C:\work\ledger')
    def notes(self): return [c['Body'] for c in self.s.list_comments(self.tid)]
    def held(self): return self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))

    def test_a_held_push_keeps_the_task_open_and_says_so(self):
        self.hold()
        out = send_close(self.s, self.tid)
        self.assertEqual(out['status'], 'done', out); self.assertFalse(out['outcome']['closed'])
        self.assertNotEqual(self.s.get_task(self.tid)['Status'], 'done')
        self.assertIn("Sent. Kept open: The agent's held step still waits for your Approve - push the agent's commits out of this computer.", self.notes())
        self.assertEqual(len(self.held()), 1, 'the held push is not dismissed by the send')
        self.assertIn('kept open', out['receipt'])

    def test_nothing_waiting_closes_it(self):
        out = send_close(self.s, self.tid)
        self.assertTrue(out['outcome']['closed'], out); self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')
        self.assertFalse(any(n.startswith('Sent. Kept open') for n in self.notes()))

    def test_an_open_session_or_a_queued_start_keeps_it_open(self):
        with mock.patch('taskuary.workerstate._live', return_value=SimpleNamespace(sid='run1')):
            self.assertEqual(concierge.close_after_send(self.s, self.tid)['kept_open'], ['the agent session on it is still open'])
        self.s.enqueue_dispatch(self.tid, None, 'claude', 'every slot is busy')
        self.assertIn('an agent is queued to start on it', concierge.close_after_send(self.s, self.tid)['kept_open'])
        self.assertNotEqual(self.s.get_task(self.tid)['Status'], 'done')

    def test_a_held_step_outlives_its_closed_session_and_is_still_approvable(self):
        closed = []
        sess = SimpleNamespace(sid='run1', task_id=self.tid, alive=True, close=lambda: closed.append(1))
        with mock.patch.dict(terminal.SESSIONS, {'run1': sess}):
            self.hold()
            self.assertTrue(terminal.close('run1')); sess.alive = False
        self.assertEqual(closed, [1])
        with mock.patch.object(server, 'store', self.s):
            rvs = TestClient(server.app).get(f'/api/tasks/{self.tid}').json()['reviews']
        [rv] = [r for r in rvs if r['Kind'] == 'action' and r['Status'] == 'pending']
        self.assertEqual(json.loads(rv['DraftText'])['command'], 'git push origin fix-export')
        calls = []
        def run(argv, cwd=None, **kw): calls.append((argv[-1], cwd)); return SimpleNamespace(returncode=0, stdout='fix-export -> fix-export', stderr='')
        with mock.patch.object(sg.subprocess, 'run', run), mock.patch.object(sg.os.path, 'isdir', return_value=True):
            self.assertTrue(verdicts.decide(self.s, self.held()[0], 'approve')['ok'])
        self.assertEqual(calls, [('git push origin fix-export', r'C:\work\ledger')]); self.assertEqual(self.held(), [])
        self.assertTrue(any('No agent is running on this task to tell' in n for n in self.notes()))
        self.assertTrue(concierge.close_after_send(self.s, self.tid)['closed'], 'approved, nothing waits: the next send-close closes it')


if __name__ == '__main__': unittest.main()
