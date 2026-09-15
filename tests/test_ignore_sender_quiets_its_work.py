"""Silencing a sender must not be WORSE than pressing Next.

"Ignore this sender" wrote its exclusion rule and marked the sender's mail skipped - and stopped
there. The task triage had already cut from that mail stayed open, so the pipe went on offering it:
the owner silenced Power BI and the very next thing the assistant showed was Power BI (2026-09-15:
"i put this in that ignore sender but then it showed up again?"). Pressing Next on the same item
would at least have marked it read.

So the rule now writes the same receipt Next writes - `surfaced`, read=True - on the open tasks that
sender's mail produced. READ, never closed: silencing who reported a thing is not a verdict on the
thing, so nobody's work is thrown away and a new arrival makes the task unread again.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import ingest, server
from taskuary.store import MemoryStore

NOISE = {'external_id': 'pbi-1', 'channel': 'email', 'from_email': 'no-reply-powerbi@microsoft.com',
         'from_name': 'Microsoft Power BI', 'conversation_id': 'pbi', 'subject': 'Refresh succeeded with warnings',
         'body': 'The gateway serving CashBalancesNew is on a deprecated version.'}
TASK = lambda *a, **k: '{"intent": "task", "kind": "coding", "why": "the gateway needs upgrading"}'


class IgnoreSenderTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)
        out = ingest.ingest_message(self.s, dict(NOISE), llm=TASK)
        self.mid, self.tid = out['message_id'], out['task_id']
        self.assertIsNotNone(self.tid, 'the noise made a task, which is the whole problem')

    def silence(self):
        r = self.c.post(f'/api/messages/{self.mid}/ignore-sender', json={'how': 'rule'})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_the_mail_is_hidden_and_its_task_is_marked_read(self):
        out = self.silence()
        self.assertEqual(self.s.get_message(self.mid)['Status'], 'skipped')
        self.assertEqual(out['quieted'], [self.tid])
        state = self.s.funnel_states().get(f'task:{self.tid}')
        self.assertIsNotNone(state, 'the task carries a receipt, as Next would have left')
        self.assertEqual(state['Status'], 'surfaced')

    def test_the_task_is_not_closed(self):
        """Silencing who reported a thing is not a verdict on the thing - the gateway may still
        need upgrading, and an agent's work on it is not thrown away."""
        self.silence()
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'open')

    def test_a_sender_with_no_open_work_quiets_nothing(self):
        self.s.update_task(self.tid, {'Status': 'done'}, 'owner')
        self.assertEqual(self.silence()['quieted'], [])

    def test_the_memory_route_files_the_task_outright(self):
        """The asymmetry that made this confusing, written down.

        `memory` ("not mine") FILES the task - _file_task, audited as not_mine_delete - while the
        rule, the bigger and more permanent hammer, used to leave the work untouched. The softer
        choice did more about it than the harder one. The rule still does not delete (it is
        reversible, and silencing a reporter is not a verdict on what was reported); it marks the
        work read, which is the floor: no worse than pressing Next.
        """
        r = self.c.post(f'/api/messages/{self.mid}/ignore-sender', json={'how': 'memory'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn('quieted', r.json())
        self.assertIsNone(self.s.get_task(self.tid), 'the memory route files it')

    def test_only_this_senders_work_is_quieted(self):
        other = ingest.ingest_message(self.s, {**NOISE, 'external_id': 'p2', 'conversation_id': 'p2',
                                               'from_email': 'someone@partner.example'}, llm=TASK)
        self.assertEqual(self.silence()['quieted'], [self.tid])
        self.assertIsNone(self.s.funnel_states().get(f"task:{other['task_id']}"))


class StoreTests(unittest.TestCase):
    def test_live_tasks_from_sender_finds_only_open_ones(self):
        s = MemoryStore()
        a = ingest.ingest_message(s, dict(NOISE), llm=TASK)
        b = ingest.ingest_message(s, {**NOISE, 'external_id': 'pbi-2', 'conversation_id': 'pbi2'}, llm=TASK)
        s.update_task(b['task_id'], {'Status': 'done'}, 'owner')
        got = [r['TaskId'] for r in s.live_tasks_from_sender('NO-REPLY-POWERBI@microsoft.com')]
        self.assertEqual(got, [a['task_id']], 'case-insensitive, and closed work is already quiet')
        self.assertEqual(s.live_tasks_from_sender('nobody@example.com'), [])


class CardTests(unittest.TestCase):
    def test_a_card_with_no_mail_behind_it_asks_for_nothing(self):
        """The task outlived its message, so the card had no mid and fetched /api/messages/null,
        painting FastAPI's own validation sentence into the card."""
        from pathlib import Path
        cards = (Path(__file__).resolve().parents[1] / 'website' / 'src' / 'assistantCards.jsx').read_text(encoding='utf-8')
        guard = cards.index('if (mid == null || mid === "")')
        self.assertLess(guard, cards.index('api.get(`/api/messages/${mid}`)'))


if __name__ == '__main__':
    unittest.main()
