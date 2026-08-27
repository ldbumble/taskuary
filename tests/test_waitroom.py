"""The waiting room (waitroom.py): notes the owner queues on a task while its agent works, typed
in as one batch when the agent parks - held while it is working, held while it is ASKING, and
reopening a session when the old one ended. All faked: no pty, no CLI.
"""
import time, unittest
from unittest import mock

from taskuary import terminal, waitroom
from taskuary.store import MemoryStore


class FakeTerm:
    """Just enough of terminal.Term: a task, a pulse, a screen."""
    def __init__(self, tid, idle=0.0, tail=()): self.task_id, self.alive, self._idle, self._tail, self.n, self.writes = tid, True, idle, list(tail), 0, []
    def idle(self): return self._idle
    def tail(self, n=3): return self._tail[-n:]
    def write(self, x): self.writes.append(x); self.n += 1
    def info(self, tail=0): return {'sid': 'fake', 'taskId': self.task_id, 'alive': True, 'idle': self._idle, 'files': []}
    def typed(self): return ''.join(w for w in self.writes if w not in ('\r', '\n'))


def task(s, status='in_progress'): return s.create_task({'Title': 'PTO import', 'Kind': 'coding', 'Status': status}, 't')


class QuestionTests(unittest.TestCase):
    def test_a_question_on_the_tail_is_a_question(self):
        for tail in (['Should I also update the tests?'], ['Do you want to proceed?', '❯ 1. Yes', '  2. No'],
                     ['Which of these files is the right one?'], ['Overwrite config.toml (y/n)']):
            self.assertTrue(waitroom.looks_like_question(tail), tail)

    def test_a_finished_report_is_not(self):
        for tail in (['Done. Tests pass (12 passed).', 'Committed as 3f1a2c.'], ['I wondered whether x? No - it is y.', 'Finished.'], []):
            self.assertFalse(waitroom.looks_like_question(tail), tail)


class DeliveryTests(unittest.TestCase):
    def test_held_while_the_agent_works_then_typed_as_one_batch_in_order(self):
        s = MemoryStore(); tid = task(s)
        t = FakeTerm(tid, idle=2)
        with mock.patch.dict(terminal.SESSIONS, {'a': t}, clear=True):
            r1 = waitroom.add(s, tid, 'also handle the null case', 'owner')
            r2 = waitroom.add(s, tid, 'rename the flag to --dry-run')
            self.assertEqual((r1['delivered'], r1['state'], r2['state']), (0, 'working', 'working'))
            self.assertEqual(len(s.waiting_notes(tid)), 2); self.assertEqual(t.writes, [])
            t._idle = terminal.IDLE_WAITING + 1                      # it parked at its prompt
            out = waitroom.tick(s)
            time.sleep(0.5)
        self.assertEqual(out, 2)
        typed = t.typed()
        self.assertIn('(1) also handle the null case', typed); self.assertIn('(2) rename the flag', typed)
        self.assertLess(typed.index('(1)'), typed.index('(2)'))
        self.assertIn('after finishing the step you are on', typed)
        self.assertEqual(s.waiting_notes(tid), [])
        self.assertEqual({w['How'] for w in s.waitroom(tid)}, {'typed'})
        self.assertTrue(any('waiting-room' in c['Body'] for c in s.list_comments(tid)))

    def test_a_parked_agent_gets_the_note_at_once(self):
        s = MemoryStore(); tid = task(s)
        t = FakeTerm(tid, idle=terminal.IDLE_WAITING + 5, tail=['Done - all tests pass.'])
        with mock.patch.dict(terminal.SESSIONS, {'a': t}, clear=True):
            out = waitroom.add(s, tid, 'now do the same for the export path')
            time.sleep(0.5)
        self.assertEqual((out['delivered'], out['state']), (1, 'parked'))
        self.assertIn('export path', t.typed())

    def test_held_behind_a_question_for_the_owner(self):
        s = MemoryStore(); tid = task(s)
        t = FakeTerm(tid, idle=terminal.IDLE_WAITING + 5, tail=['Two repos match. Which one should I use?'])
        with mock.patch.dict(terminal.SESSIONS, {'a': t}, clear=True):
            out = waitroom.add(s, tid, 'use the 8/17 file')
            self.assertEqual((out['delivered'], out['state']), (0, 'asking'))
            self.assertEqual(t.writes, [])
            t._tail = ['Using FanApp. Done.']                          # the owner answered, it finished
            self.assertEqual(waitroom.tick(s), 1)
            time.sleep(0.5)
        self.assertIn('8/17 file', t.typed())

    def test_no_session_reopens_one_with_the_notes_as_the_ask(self):
        s = MemoryStore(); tid = task(s)
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(terminal, 'start_on_task', return_value={'sid': 'new'}) as start:
            out = waitroom.add(s, tid, 'also fix the header row')
        self.assertEqual((out['delivered'], out['state']), (1, 'restarted'))
        self.assertEqual(start.call_args[0][1], tid)
        self.assertIn('(1) also fix the header row', start.call_args[1]['instruction'])
        self.assertIn('after the last session ended', start.call_args[1]['instruction'])
        self.assertEqual({w['How'] for w in s.waitroom(tid)}, {'seeded'})

    def test_a_closed_task_holds_and_a_full_house_waits(self):
        s = MemoryStore(); done = task(s, 'done'); open_ = task(s, 'open')
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(terminal, 'start_on_task') as start:
            self.assertEqual(waitroom.add(s, done, 'x')['state'], 'closed')
            s.set_setting('auto_sessions', '1', 't')
            with mock.patch.dict(terminal.SESSIONS, {'b': FakeTerm(999, idle=1)}, clear=True):
                self.assertEqual(waitroom.add(s, open_, 'y')['state'], 'full')
            start.assert_not_called()
        self.assertEqual(len(s.waiting_notes(open_)), 1)                # still waiting - the clock retries

    def test_withdraw_before_delivery_only(self):
        s = MemoryStore(); tid = task(s)
        with mock.patch.dict(terminal.SESSIONS, {'a': FakeTerm(tid, idle=1)}, clear=True):
            wid = waitroom.add(s, tid, 'scratch that')['wid']
        s.drop_waiting(wid, tid); self.assertEqual(s.waiting_notes(tid), [])
        wid2 = s.add_waiting(tid, 'kept', 'owner'); s.deliver_waiting([wid2], 'typed')
        s.drop_waiting(wid2, tid); self.assertEqual(len(s.waitroom(tid)), 1)

    def test_empty_note_and_unknown_task_are_refused(self):
        s = MemoryStore(); tid = task(s)
        with self.assertRaises(ValueError): waitroom.add(s, tid, '   ')
        with self.assertRaises(ValueError): waitroom.add(s, 9999, 'x')


class ApiTests(unittest.TestCase):
    def test_round_trip(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore(); tid = task(s)
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {'a': FakeTerm(tid, idle=1)}, clear=True):
            c = TestClient(server.app)
            self.assertEqual(c.post(f'/api/tasks/{tid}/waitroom', json={'text': ''}).status_code, 422)
            r = c.post(f'/api/tasks/{tid}/waitroom', json={'text': 'check the other repo too'}).json()
            self.assertEqual(r['state'], 'working')
            got = c.get(f'/api/tasks/{tid}/waitroom').json()
            self.assertEqual((len(got['data']), got['state']), (1, 'working'))
            self.assertEqual(c.get('/api/tasks').json()['data'][0]['Waiting'], 1)
            c.delete(f"/api/tasks/{tid}/waitroom/{r['wid']}")
            self.assertEqual(c.get('/api/tasks').json()['data'][0]['Waiting'], 0)
            self.assertEqual(c.get('/api/tasks/9999/waitroom').status_code, 404)

    def test_live_runs_say_when_a_parked_agent_is_asking(self):
        """The hand-raise notification reads this: a session quiet past IDLE_WAITING whose last
        lines are a question is 'asking'; one still printing is neither."""
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore(); tid = task(s)
        asking = FakeTerm(tid, idle=terminal.IDLE_WAITING + 3, tail=['Which repo should I use?'])
        asking.cwd, asking.agent, asking.label, asking.started = 'x', 'coder', 'coder', ''
        def info(tail=0): return {'sid': 'a', 'taskId': tid, 'alive': True, 'idle': asking._idle, 'files': [], 'agent': 'coder', 'label': 'coder',
                                  'started': '', 'tail': asking.tail(tail)}
        asking.info = info
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {'a': asking}, clear=True):
            rows = TestClient(server.app).get('/api/runs/live').json()['data']
            self.assertEqual((rows[0]['asking'], rows[0]['Title']), (True, 'PTO import'))
            asking._idle = 2
            self.assertFalse(TestClient(server.app).get('/api/runs/live').json()['data'][0]['asking'])


if __name__ == '__main__': unittest.main()
