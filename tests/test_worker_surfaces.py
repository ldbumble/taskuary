"""Every surface reads the worker's own word before it reads the screen (PW-228, PW-137, PW-142 in part).

The funnel, the hand-raise and the task list decided "the agent is waiting on you" from a bare
prompt on screen. When a run has reported through explicit events, that word decides: an open
input or approval request is a hand raised - with the exact question and its choices - and a run
whose events say it is working raises no hand however quiet its screen; a finished run's result is
a result, not blocked work; the same event is never announced twice. A run that never reported
(a third-party CLI without hooks) keeps the screen heuristic as its fallback.
"""
import unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import funnel, handraise, outbound, terminal, workerstate as ws
from taskuary.store import MemoryStore


class FakeTerm:
    def __init__(self, tid, sid='run1', waiting=False, tail=()):
        self.task_id, self.alive, self.agent, self.label, self.sid = tid, True, 'codex', 'codex', sid
        self.started, self._waiting, self._tail = '2026-09-06 12:00:00', waiting, list(tail)
        self.cwd, self.files = r'C:\code\repo', (lambda: [])
    def waiting(self): return self._waiting
    def tail(self, n=3): return self._tail[-n:]
    def idle(self): return 90.0


class BlendTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); funnel.invalidate(); handraise.reset()
        self.tid = self.s.create_task({'Title': 'Fix notifications', 'Kind': 'coding', 'Status': 'in_progress'}, 't')

    def test_a_run_that_reported_decides_and_a_silent_run_falls_back_to_the_screen(self):
        reported = FakeTerm(self.tid, 'run1', waiting=True, tail=['> '])                 # parked on screen...
        with mock.patch.dict(terminal.SESSIONS, {'run1': reported}, clear=True):
            ws.record(self.s, self.tid, 'run1', 'working')                              # ...but it said it is working
            self.assertIs(ws.waiting_of(self.s, reported), False)
            ws.record(self.s, self.tid, 'run1', 'input_needed', request_id='q1', text='Which repository should I use?', choices=['a', 'b'])
            self.assertIs(ws.waiting_of(self.s, reported), True)
            self.assertEqual(ws.asking_of(self.s, reported)['text'], 'Which repository should I use?')
        silent = FakeTerm(self.tid, 'run9', waiting=True)
        with mock.patch.dict(terminal.SESSIONS, {'run9': silent}, clear=True):
            self.assertIsNone(ws.waiting_of(self.s, silent))                            # nothing reported: the screen decides
            self.assertIsNone(ws.asking_of(self.s, silent))


class HandRaiseTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); handraise.reset()
        self.tid = self.s.create_task({'Title': 'Fix notifications', 'Kind': 'coding', 'Status': 'in_progress'}, 't')

    def test_the_ping_carries_the_exact_question_and_a_working_run_raises_no_hand_however_quiet(self):
        term = FakeTerm(self.tid, 'run1', waiting=True, tail=['> '])
        pings = []
        with mock.patch.dict(terminal.SESSIONS, {'run1': term}, clear=True), \
             mock.patch.object(outbound, 'notify', side_effect=lambda st, text: pings.append(text)):
            ws.record(self.s, self.tid, 'run1', 'working')
            self.assertEqual(handraise.tick(self.s), 0)                                 # the screen says parked; the run says working
            ws.record(self.s, self.tid, 'run1', 'input_needed', request_id='q1', text='Which repository should I use?')
            self.assertEqual(handraise.tick(self.s), 1)
            self.assertEqual(handraise.tick(self.s), 0)                                 # not announced twice
            ws.record(self.s, self.tid, 'run1', 'answered', request_id='q1', text='the exports repo')
            self.assertEqual(handraise.tick(self.s), 0)
        self.assertEqual(len(pings), 1); self.assertIn('Which repository should I use?', pings[0]); self.assertIn('asked you', pings[0])

    def test_an_approval_request_is_said_as_an_approval(self):
        term = FakeTerm(self.tid, 'run1', waiting=False)
        pings = []
        with mock.patch.dict(terminal.SESSIONS, {'run1': term}, clear=True), \
             mock.patch.object(outbound, 'notify', side_effect=lambda st, text: pings.append(text)):
            ws.record(self.s, self.tid, 'run1', 'approval_needed', request_id='p1', text='Run alembic upgrade head?')
            self.assertEqual(handraise.tick(self.s), 1)
        self.assertIn('approval', pings[0].lower()); self.assertIn('alembic', pings[0])


class FunnelTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); funnel.invalidate()
        self.tid = self.s.create_task({'Title': 'Fix notifications', 'Kind': 'coding', 'Status': 'in_progress'}, 't')

    def test_the_agent_item_carries_the_request_and_its_kind(self):
        live = [{'taskId': self.tid, 'sid': 'run1', 'agent': 'codex', 'started': '2026-09-06 12:00:00', 'waiting': True,
                 'request': {'request_id': 'q1', 'kind': 'input_needed', 'text': 'Which repository should I use?', 'choices': ['a', 'b']}, 'tail': ['> ']}]
        items = funnel.from_agents(self.s, live_state=live)
        self.assertEqual(len(items), 1); it = items[0]
        self.assertTrue(it['asking']); self.assertEqual(it['request_id'], 'q1'); self.assertEqual(it['choices'], ['a', 'b'])
        self.assertIn('Which repository should I use?', it['why']); self.assertEqual(it['tail'], ['Which repository should I use?'])
        live[0]['request'] = {'request_id': 'p1', 'kind': 'approval_needed', 'text': 'Run alembic upgrade head?', 'choices': []}
        it = funnel.from_agents(self.s, live_state=live)[0]
        self.assertIn('approval', it['why'].lower()); self.assertEqual(it['request_kind'], 'approval_needed')

    def test_a_working_run_is_not_a_blocked_item(self):
        live = [{'taskId': self.tid, 'sid': 'run1', 'agent': 'codex', 'started': '2026-09-06 12:00:00', 'waiting': False, 'idle': 400, 'tail': ['> ']}]
        self.assertEqual(funnel.from_agents(self.s, live_state=live), [])           # waiting is the worker's word now, not idle time


class InfoTests(unittest.TestCase):
    def test_a_sessions_info_reports_the_open_request(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix notifications', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        term = FakeTerm(tid, 'run1', waiting=True, tail=['> ']); term.store = s
        with mock.patch.dict(terminal.SESSIONS, {'run1': term}, clear=True):
            ws.record(s, tid, 'run1', 'input_needed', request_id='q1', text='Which repository should I use?')
            info = terminal.worker_fields(s, term)
        self.assertEqual((info['waiting'], info['request']['request_id']), (True, 'q1'))
        with mock.patch.dict(terminal.SESSIONS, {'run1': term}, clear=True):
            ws.record(s, tid, 'run1', 'answered', request_id='q1', text='exports')
            info = terminal.worker_fields(s, term)
        self.assertEqual((info['waiting'], info['request']), (False, None))


if __name__ == '__main__':
    unittest.main()
