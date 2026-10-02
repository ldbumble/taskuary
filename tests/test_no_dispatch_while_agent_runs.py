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
    def __init__(self, tid): self.task_id, self.alive, self.agent, self.mode, self.sid = tid, True, 'coder', 'pty', 's1'
    def info(self, tail=0, details=True): return {'sid': self.sid, 'taskId': self.task_id, 'alive': True, 'agent': self.agent}


class Base(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd': r'C:\code\repo'}))
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
        for verb in ('coder', 'regular_agent'):
            self.assertIn('already working', concierge.cannot(item, verb, self.s))

    def test_it_is_offered_again_once_the_session_is_gone(self):
        item = {'kind': 'message', 'tid': self.tid, 'mid': self.mid, 'ref': 'TQ-0001', 'lane': 'asked'}
        server.hub_term.SESSIONS['s1'].alive = False
        self.assertEqual(concierge.cannot(item, 'regular_agent', self.s), '')
