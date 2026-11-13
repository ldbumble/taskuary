"""An agent's job the Assistant is asked for is started at once on a task of its own (concierge._made_now). Asked "where is it?"
a moment later, the Assistant said it was still waiting in New and had not started - its tools said nothing of the task the press had
started, and its index said every change waits for the owner's press. A press made again from that card then reached the agent already
at work and stood a red "already working on this task" over it (2026-11-02). The model is given the true state; nothing writes its words."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import asks, server, toolcatalog
from taskuary.store import MemoryStore, task_ref


class Live:
    def __init__(self, tid, mode='assistant'): self.task_id, self.alive, self.agent, self.mode, self.sid = tid, True, 'assistant', mode, 's1'
    def info(self, tail=0, details=True): return {'sid': self.sid, 'taskId': self.task_id, 'alive': True}


class Base(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Draw a picture of two people studying', 'Kind': 'general', 'Status': 'open', 'AskedVia': 'desktop'}, 'owner')
        live = mock.patch.dict(server.hub_term.SESSIONS, {}); live.start(); self.addCleanup(live.stop)


class OpenAsksTests(Base):
    def test_a_job_started_seconds_ago_is_in_the_open_asks_as_worked(self):
        # nothing written by the agent yet, no Assignee, no run row - and the turn's rail built before the task existed
        self.assertEqual(asks.block(self.s, []), '')
        server.hub_term.SESSIONS['s1'] = Live(self.tid)
        said = asks.block(self.s, [])
        self.assertIn(task_ref(self.tid), said)
        self.assertIn('agent working', said)
        self.assertEqual(asks.state(self.s, self.tid, [])[0], 'working')

    def test_once_its_agent_is_gone_it_is_quiet_again(self):
        server.hub_term.SESSIONS['s1'] = Live(self.tid); server.hub_term.SESSIONS['s1'].alive = False
        self.assertEqual(asks.state(self.s, self.tid, []), ('quiet', ''))


class ToolTests(unittest.TestCase):
    def test_the_index_and_the_tool_say_an_agents_job_starts_at_once(self):
        d = toolcatalog.describe('task.create_from_text')
        self.assertIn('STARTS at once', d); self.assertIn('YOUR OPEN ASKS', d)
        self.assertNotIn('the owner presses its button', d)
        self.assertIn("Only an agent's job starts at once (YOUR OPEN ASKS)", toolcatalog.block())


class LiveAgentTests(Base):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)

    def test_a_press_on_a_live_agent_is_refused_in_plain_words(self):
        server.hub_term.SESSIONS['s1'] = Live(self.tid)
        for body in ({'kind': 'general'}, {'kind': 'coding'}):
            r = self.c.post(f'/api/tasks/{self.tid}/dispatch', json=body)
            self.assertEqual(r.status_code, 409, r.text)
            detail = r.json()['detail']
            self.assertIn('Agent is already working on this task', detail)
            for jargon in ('agent type', 'assistant is', 'session'): self.assertNotIn(jargon, detail)
        self.assertIn('stop it with the x on its turn', detail)                   # ...the coding press: the way to another agent is a button they have


if __name__ == '__main__':
    unittest.main()
