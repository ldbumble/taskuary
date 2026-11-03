"""NO AI, NO START (the owner, 2026-11-03): an agent started with no AI connected must be refused with what is missing and where to connect
it - not a session with nothing to run it. Every road, and the task stays as it was: no session, no kind change, no new task."""
import json, unittest
from unittest import mock
from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient

from taskuary import capabilities, general, server
from taskuary.store import MemoryStore

REAL_BRAIN_GATE = True


class NoAI(unittest.TestCase):
    def setUp(self):
        self.s = s = MemoryStore()
        s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd': r'C:\code\ledger'}))
        s.set_setting('developer_mode', '1', 't')
        self.tid = s.create_task({'Title': 'Fix the nightly export for Erin Blake', 'Kind': 'coding', 'Status': 'open'}, 't')
        for p in (mock.patch.object(server, 'store', s), mock.patch.object(server.hub_agents, 'cli_ready', return_value=False),
                  mock.patch.object(capabilities, 'has_ai', return_value=False),
                  mock.patch.object(server.hub_term, 'start_on_task', side_effect=AssertionError('a session started with no AI')),
                  mock.patch.object(general, 'start_session', side_effect=AssertionError('a conversation started with no AI'))):
            p.start(); self.addCleanup(p.stop)
        self.c, self.before = TestClient(server.app), dict(s.get_task(self.tid))

    def refused(self, r, coding=True):
        self.assertEqual(r.status_code, 422, r.text)
        why = r.json()['detail']
        self.assertIn('No AI is connected', why); self.assertIn('connect', why)
        if coding: self.assertIn('coding agent', why)
        t = self.s.get_task(self.tid)
        self.assertEqual((t['Kind'], t['Status']), (self.before['Kind'], self.before['Status']))
        self.assertIsNone(server.hub_term.session_for(self.tid))

    def test_start_and_send_to_agent(self): self.refused(self.c.post(f'/api/tasks/{self.tid}/dispatch', json={'kind': 'coding'}))
    def test_run_another_agent(self): self.refused(self.c.post(f'/api/tasks/{self.tid}/dispatch', json={'kind': 'coding', 'fresh': True}))
    def test_continue(self): self.refused(self.c.post(f'/api/tasks/{self.tid}/continue-work', json={'note': 'also the weekly one'}))
    def test_continue_session(self): self.refused(self.c.post(f'/api/tasks/{self.tid}/continue-session', json={}))
    def test_continue_with_instruction(self): self.refused(self.c.post(f'/api/tasks/{self.tid}/continue', json={'instruction': 'add a test'}))

    def test_the_assistant_and_phone_start(self):
        with self.assertRaises(HTTPException) as e: server.dispatch_task(self.tid, server.DispatchBody(kind='coding'), BackgroundTasks())
        self.assertIn('No AI is connected', e.exception.detail)
        self.assertIsNone(server.hub_term.session_for(self.tid))

    def test_a_message_is_not_turned_into_a_half_started_task(self):
        mid = self.s.add_message({'external_id': 'm1', 'channel': 'email', 'from_email': 'gail@northwind.example', 'from_name': 'Gail Moreno',
                                  'subject': 'Export broke', 'body': 'The export broke again.', 'sent_at': '2026-11-03 09:00'})
        mid = mid if isinstance(mid, int) else mid['MessageId']
        r = self.c.post(f'/api/messages/{mid}/dispatch', json={'kind': 'coding'})
        self.assertEqual(r.status_code, 422, r.text); self.assertIn('No AI is connected', r.json()['detail'])
        self.assertFalse(self.s.get_message(mid).get('TaskId'))

    def test_a_general_agent_with_no_ai_is_refused_too(self):
        self.s.update_task(self.tid, {'Kind': 'general'}, 't'); self.before = dict(self.s.get_task(self.tid))
        self.refused(self.c.post(f'/api/tasks/{self.tid}/dispatch', json={'kind': 'general'}), coding=False)
