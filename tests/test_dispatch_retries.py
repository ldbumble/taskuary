"""Capacity counts every live session, and a start that fails is retried a bounded number of times (PW-084 to PW-089).

A queued start that failed was retried whenever some unrelated session ended, forever, with the
same error each time; a direct auto-start that failed wrote one line and was never tried again.
Now every live coding or general session counts toward the shared capacity - idle at a prompt or
stopped at an approval too - and a startup failure is a recorded attempt: at most two automatic
retries after the first try (three attempts), with bounded backoff, the attempt count, last error
and next-attempt time persisted so a restart cannot reset the budget. Configuration failures (an
unknown agent, a missing repository or worker, a permission problem) become "needs you" at once
instead of burning blind retries; a capacity wait is not an attempt. After exhaustion the task and
its error stay visible, automatic attempts stop, and the owner has Retry (a new bounded cycle) and
Cancel queued start (the pending dispatch goes, the task stays). Other queued tasks keep moving.
"""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import blackboard as bb, general, ingest, server, terminal as term
from taskuary.store import MemoryStore
from taskuary.testing import Factory


def fake_session(tid, alive=True, phase='working', agent='coder'):
    return SimpleNamespace(alive=alive, task_id=tid, cwd=r'C:\code\repo', agent=agent, label=agent, started='2026-09-06 09:00:00',
                           files=lambda: [], info=lambda tail=0: {'sid': 'fake', 'taskId': tid}, phase=lambda: phase, waiting=lambda: phase == 'parked')


def past(): return (datetime.now() - timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S')


class Base(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.fx = Factory(self.s)
        self._sessions = dict(term.SESSIONS); term.SESSIONS.clear()
        p = mock.patch.object(bb.threading, 'Timer'); self.timer = p.start(); self.addCleanup(p.stop)   # retries are scheduled, not slept for
    def tearDown(self): term.SESSIONS.clear(); term.SESSIONS.update(self._sessions)
    def task(self, title='Fix the cron', kind='coding'): return self.fx.task(title=title, summary='reports cron is broken', kind=kind)
    def row(self, tid): return self.s.get_dispatch(tid)
    def comments(self, tid): return [c['Body'] for c in self.s.list_comments(tid)]
    def due(self, tid): self.s._exec('UPDATE dispatchq SET NextAt=? WHERE TaskId=?', (past(), tid))


class CapacityTests(Base):
    def test_every_live_session_counts_whatever_it_is_doing(self):
        t1, t2, t3, t4 = self.task('a'), self.task('b'), self.task('c', 'general'), self.task('d')
        term.SESSIONS['w'] = fake_session(t1, phase='working')
        term.SESSIONS['p'] = fake_session(t2, phase='parked')                      # idle at its prompt: still a desk taken
        term.SESSIONS['g'] = fake_session(t3, agent='assistant')                    # a general session counts the same
        term.SESSIONS['x'] = fake_session(t4, alive=False)                          # ended: not counted
        self.assertEqual(bb.live_count(), 3)
        self.s.set_setting('auto_sessions', '3', 't')
        t5 = self.task('e'); self.s.enqueue_dispatch(t5, None, 'coder', 'slot')
        with mock.patch.object(term, 'start_on_task') as start: bb.drain(self.s)
        start.assert_not_called()
        self.assertEqual((self.row(t5)['Attempts'] or 0, self.row(t5).get('State') or 'waiting'), (0, 'waiting'))   # a capacity wait is not an attempt


class RetryTests(Base):
    def test_a_transient_failure_is_retried_with_backoff_and_stops_after_three_attempts(self):
        tid = self.task(); self.s.enqueue_dispatch(tid, None, 'coder', 'slot')
        with mock.patch.object(term, 'start_on_task', side_effect=RuntimeError('pty spawn failed')) as start:
            bb.drain(self.s)
            row = self.row(tid)
            self.assertEqual((row['Attempts'], row['State']), (1, 'retrying')); self.assertIn('pty spawn failed', row['LastError'])
            self.assertGreater(row['NextAt'], datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.assertTrue(any('attempt 1 of 3' in c and 'retrying in' in c for c in self.comments(tid)))
            bb.drain(self.s)                                                     # not due yet: nothing happens
            self.assertEqual(start.call_count, 1)
            self.due(tid); bb.drain(self.s)
            self.assertEqual((start.call_count, self.row(tid)['Attempts']), (2, 2))
            self.due(tid); bb.drain(self.s)
            row = self.row(tid)
            self.assertEqual((start.call_count, row['Attempts'], row['State']), (3, 3, 'failed'))
            self.assertIsNone(row['NextAt'])
            self.assertTrue(any('could not start - needs you' in c for c in self.comments(tid)))
            self.due(tid); bb.drain(self.s); bb.drain(self.s)
            self.assertEqual(start.call_count, 3)                                 # exhausted: automatic attempts stop
        self.assertEqual(self.s.get_task(tid)['Status'], 'open')                   # the task is kept, with its error
        self.assertTrue(self.timer.called)                                         # the retry was scheduled, not left to luck

    def test_a_transient_failure_that_recovers_clears_the_queue(self):
        tid = self.task(); self.s.enqueue_dispatch(tid, None, 'coder', 'slot')
        with mock.patch.object(term, 'start_on_task', side_effect=RuntimeError('busy')): bb.drain(self.s)
        self.due(tid)
        with mock.patch.object(term, 'start_on_task', return_value={'sid': 's1'}): bb.drain(self.s)
        self.assertIsNone(self.row(tid)); self.assertTrue(any('Started from the dispatch queue' in c for c in self.comments(tid)))

    def test_a_configuration_failure_needs_you_at_once(self):
        for err in ('unknown agent: codex', 'no repository for this task - pick one', 'permission denied for the checkout'):
            tid = self.task(err[:10]); self.s.enqueue_dispatch(tid, None, 'coder', 'slot')
            with mock.patch.object(term, 'start_on_task', side_effect=ValueError(err)) as start: bb.drain(self.s)
            row = self.row(tid)
            self.assertEqual((row['Attempts'], row['State']), (1, 'failed'), err)
            self.assertTrue(any('needs you' in c and 'no automatic retry' in c for c in self.comments(tid)), err)
            self.due(tid)
            with mock.patch.object(term, 'start_on_task') as start: bb.drain(self.s)
            start.assert_not_called()

    def test_the_budget_and_backoff_are_persisted_and_a_restart_only_rearms_the_timer(self):
        tid = self.task(); self.s.enqueue_dispatch(tid, None, 'coder', 'slot')
        with mock.patch.object(term, 'start_on_task', side_effect=RuntimeError('boom')): bb.drain(self.s)
        row = dict(self.row(tid))
        self.timer.reset_mock()
        delay = bb.schedule_due(self.s)                                           # what the lifespan does on restart
        self.assertTrue(0 < delay <= bb.BACKOFF[0] + 1); self.timer.assert_called_once()
        self.assertEqual(dict(self.row(tid)), row)                                 # nothing reset

    def test_other_queued_tasks_proceed_while_one_backs_off(self):
        t1, t2 = self.task('failing'), self.task('fine')
        self.s.enqueue_dispatch(t1, None, 'coder', 'slot'); self.s.enqueue_dispatch(t2, None, 'coder', 'slot')
        def first(s, tid, *a, **k):
            if tid == t1: raise RuntimeError('boom')
        started = []
        with mock.patch.object(term, 'start_on_task', side_effect=first): bb.drain(self.s)
        self.assertEqual(self.row(t1)['State'], 'retrying'); self.assertIsNone(self.row(t2))   # t2 started in the same pass
        self.s.enqueue_dispatch(t2, None, 'coder', 'slot')                                # queued again while t1 backs off
        with mock.patch.object(term, 'start_on_task', side_effect=lambda s, tid, *a, **k: started.append(tid)): bb.drain(self.s)
        self.assertEqual(started, [t2]); self.assertIsNone(self.row(t2)); self.assertEqual(self.row(t1)['State'], 'retrying')

    def test_a_bookkeeping_failure_after_the_session_started_is_not_a_failed_start_and_never_duplicates_it(self):
        tid = self.task(); self.s.enqueue_dispatch(tid, None, 'coder', 'slot')
        live = fake_session(tid)
        def start(store, task_id, *a, **k):
            term.SESSIONS['live'] = live
            raise RuntimeError('comment write failed after start')                 # the launch happened; what came after did not
        with mock.patch.object(term, 'start_on_task', side_effect=start) as launch: bb.drain(self.s)
        self.assertIsNone(self.row(tid))                                            # reconciled: the session exists, the row goes
        self.assertTrue(any('bookkeeping' in c.lower() for c in self.comments(tid)))
        with mock.patch.object(term, 'start_on_task') as launch2: bb.drain(self.s)
        launch2.assert_not_called()

    def test_a_direct_auto_start_that_fails_enters_the_same_bounded_cycle(self):
        tid = self.task()
        with mock.patch.object(term, 'start_on_task', side_effect=RuntimeError('pty spawn failed')), \
             mock.patch.object(bb, 'target_cwd', return_value=None):
            ingest._auto_code(self.s, tid)
        row = self.row(tid)
        self.assertEqual((row['Attempts'], row['State']), (1, 'retrying'))
        self.assertTrue(any('Auto-start failed: pty spawn failed' in c and 'attempt 1 of 3' in c for c in self.comments(tid)))
        gid = self.task('general one', 'general')
        with mock.patch.object(general, 'start_session', side_effect=RuntimeError('no CLI login')):
            ingest._auto_general(self.s, gid)
        self.assertEqual((self.row(gid)['Attempts'], self.row(gid)['State']), (1, 'retrying'))
        self.assertTrue(any('Assistant start failed: no CLI login' in c for c in self.comments(gid)))


class OwnerControlsTests(Base):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)

    def exhausted(self):
        tid = self.task(); self.s.enqueue_dispatch(tid, None, 'coder', 'slot')
        with mock.patch.object(term, 'start_on_task', side_effect=ValueError('unknown agent: x')): bb.drain(self.s)
        self.assertEqual(self.row(tid)['State'], 'failed'); return tid

    def test_retry_is_a_new_bounded_cycle(self):
        tid = self.exhausted()
        with mock.patch.object(term, 'start_on_task', return_value={'sid': 's1'}) as start:
            r = self.c.post(f'/api/tasks/{tid}/dispatch/retry')
        self.assertEqual(r.status_code, 200); start.assert_called_once(); self.assertIsNone(self.row(tid))
        tid2 = self.exhausted()
        with mock.patch.object(term, 'start_on_task', side_effect=RuntimeError('still down')):
            self.c.post(f'/api/tasks/{tid2}/dispatch/retry')
        self.assertEqual((self.row(tid2)['Attempts'], self.row(tid2)['State']), (1, 'retrying'))   # budget reset, counted afresh

    def test_cancel_removes_the_pending_start_and_keeps_the_task(self):
        tid = self.exhausted()
        r = self.c.delete(f'/api/tasks/{tid}/dispatch')
        self.assertEqual(r.status_code, 200); self.assertIsNone(self.row(tid))
        self.assertEqual(self.s.get_task(tid)['Status'], 'open')
        self.assertTrue(any('Cancelled the queued start' in c for c in self.comments(tid)))
        self.assertEqual(self.c.delete(f'/api/tasks/{tid}/dispatch').status_code, 404)

    def test_the_task_list_shows_the_failure_state(self):
        tid = self.exhausted()
        rows = self.c.get('/api/tasks').json()['data']
        q = next(t for t in rows if t['TaskId'] == tid)['Queued']
        self.assertEqual((q['state'], q['attempts']), ('failed', 1)); self.assertIn('unknown agent', q['lastError'])


if __name__ == '__main__':
    unittest.main()
