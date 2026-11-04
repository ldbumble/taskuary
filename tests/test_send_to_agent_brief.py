"""Send to agent pressed with nothing typed starts a general agent on the task's Summary - Taskuary's brief, never the owner's words.
The overnight run (2026-11-03): the pane drew "Marcus Reed wants Alex to choose between..." under YOU, a sentence the owner never wrote."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import general, server
from taskuary.store import MemoryStore


class Ses:
    "The session start_session hands back: what it was sent, and how."
    def __init__(self): self.sent, self.provider, self.model = [], 'Claude Code', ''
    def send_prompt(self, text, **kw): self.sent.append((text, kw))
    def info(self, tail=0): return {'sid': 's1'}


class SendToAgentTests(unittest.TestCase):
    def setUp(self):
        self.s, self.ses = MemoryStore(), Ses()
        self.tid = self.s.create_task({'Title': 'PhishGuard renewal', 'Summary': 'Marcus wants a 1 or 3 year renewal picked.', 'Kind': 'general',
                                       'Status': 'open'}, 'router')
        for p in [mock.patch.object(server, 'store', self.s), mock.patch.dict(server.hub_term.SESSIONS, {}, clear=True),
                  mock.patch.object(general, 'start_session', return_value=self.ses),
                  mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}])]:
            p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)

    def test_nothing_typed_sends_the_summary_as_taskuarys_brief(self):
        r = self.c.post(f'/api/tasks/{self.tid}/dispatch', json={'kind': 'general'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.ses.sent, [('Marcus wants a 1 or 3 year renewal picked.', {'brief': True})])

    def test_words_the_owner_typed_stay_theirs(self):
        r = self.c.post(f'/api/tasks/{self.tid}/dispatch', json={'kind': 'general', 'instruction': 'Go with three years.'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.ses.sent, [('Go with three years.', {'brief': False})])

    def test_a_task_triage_left_to_the_owner_is_the_agents_once_sent(self):
        "Its Summary said the owner does it by hand, and the agent it was sent to read that as its orders and did nothing."
        self.s.update_task(self.tid, {'Kind': 'task', 'Summary': 'Omar wants a file deleted - Alex does it by hand.'}, 't')
        r = self.c.post(f'/api/tasks/{self.tid}/dispatch', json={'kind': 'general'})
        self.assertEqual(r.status_code, 200, r.text)
        [(text, kw)] = self.ses.sent
        self.assertTrue(text.startswith('Omar wants a file deleted') and text.endswith(server.HANDED_OVER), text)
        self.assertEqual(kw, {'brief': True})
