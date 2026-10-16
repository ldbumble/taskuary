"""Send to agent is not offered while an agent is already running on the task (the owner, 2026-10-01): a second hand-off
on a live session either started a second worker or quietly typed into the first. The chips leave it out, and the
dispatch door itself refuses with the reason - Continue that session instead - so no button, chip or chat word gets
round it."""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, server
from taskuary.store import MemoryStore
from test_funnel import ago


class Live:
    def __init__(self, tid): self.task_id, self.alive, self.agent, self.mode, self.sid = tid, True, 'coding', 'pty', 's1'
    def info(self, tail=0, details=True): return {'sid': self.sid, 'taskId': self.task_id, 'alive': True, 'agent': self.agent}


class Base(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd': r'C:\code\repo'}))
        self.tid = self.s.create_task({'Title': 'Fix the nightly export', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        self.mid = self.s.add_message({'TaskId': self.tid, 'ExternalId': 'x:1', 'Channel': 'email', 'SourceName': 'inbox', 'Subject': 'Export',
                                       'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': ago(1),
                                       'BodyText': 'The nightly export broke.', 'Status': 'routed'})
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        live = mock.patch.dict(server.hub_term.SESSIONS, {'s1': Live(self.tid)}); live.start(); self.addCleanup(live.stop)
        self.c = TestClient(server.app)


class DispatchDoorTests(Base):
    def test_the_task_door_refuses_a_second_agent_and_says_continue(self):
        with mock.patch.object(server.hub_term, 'start_on_task') as start:
            r = self.c.post(f'/api/tasks/{self.tid}/dispatch', json={'kind': 'coding'})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn('already working on this task', r.json()['detail'])
        self.assertIn('Continue', r.json()['detail'])
        start.assert_not_called()

    def test_the_message_door_and_the_operation_refuse_too(self):
        with mock.patch.object(server.hub_term, 'start_on_task') as start:
            r = self.c.post(f'/api/messages/{self.mid}/dispatch', json={'kind': 'general'})
            self.assertEqual(r.status_code, 409, r.text)
            with self.assertRaises(Exception) as e:
                server._run_operation({'kind': 'dispatch.prepare', 'target': self.tid, 'params': {'kind': 'coding'}}, None)
            self.assertIn('already working', str(getattr(e.exception, 'detail', e.exception)))
        start.assert_not_called()


class ChipTests(Base):
    def test_no_send_to_agent_chip_on_a_task_an_agent_is_working(self):
        item = {'kind': 'message', 'tid': self.tid, 'mid': self.mid, 'ref': 'TQ-0001', 'lane': 'asked'}
        for verb in ('coding_agent', 'regular_agent'):
            self.assertIn('already being worked on', concierge.cannot(item, verb, self.s))

    def test_it_is_offered_again_once_the_session_is_gone(self):
        item = {'kind': 'message', 'tid': self.tid, 'mid': self.mid, 'ref': 'TQ-0001', 'lane': 'asked'}
        server.hub_term.SESSIONS['s1'].alive = False
        self.assertEqual(concierge.cannot(item, 'regular_agent', self.s), '')


class TwoStartsAtOnceTests(unittest.TestCase):
    """Two dispatches half a second apart both passed the live check - the first session did not exist yet - and one task
    got two coding sessions in one checkout (2026-10-13). The second now waits for the first and answers with its start."""
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Review the pull requests', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        live = mock.patch.dict(server.hub_term.SESSIONS, {}); live.start(); self.addCleanup(live.stop)

    def test_a_second_dispatch_during_a_start_reuses_it_and_starts_nothing(self):
        import threading, time
        starts = []
        def slow(tid, body, background):
            starts.append(tid); time.sleep(0.3)
            server.hub_term.SESSIONS['s9'] = Live(tid)
            return {'dispatch': 'coding', 'started': True, 'existing': False, 'taskId': tid, 'session': {'sid': 's9'}}
        out = []
        with mock.patch.object(server, '_dispatch_one', side_effect=slow):
            ts = [threading.Thread(target=lambda: out.append(server._dispatch_task_to_its_agent(self.tid, server.DispatchBody(kind='coding'), None)))
                  for _ in range(2)]
            for t in ts: t.start(); time.sleep(0.05)
            for t in ts: t.join()
        self.assertEqual(starts, [self.tid])                                     # one session, not two
        self.assertEqual(sorted((o['started'], o['existing']) for o in out), [(False, True), (True, False)])
        self.assertTrue(all(o['session']['sid'] == 's9' for o in out))

    def test_a_later_dispatch_is_not_answered_from_an_old_start(self):
        with mock.patch.object(server, '_dispatch_one', return_value={'dispatch': 'coding', 'started': True, 'existing': False}) as one:
            server._dispatch_task_to_its_agent(self.tid, server.DispatchBody(kind='coding'), None)
            server._dispatch_task_to_its_agent(self.tid, server.DispatchBody(kind='coding'), None)
        self.assertEqual(one.call_count, 2)                                      # one after another: each is its own start
