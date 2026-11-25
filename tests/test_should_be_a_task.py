"""Should be a task, on an FYI (the owner, 2026-10-29): the put-down Not a task does not apply to what triage already filed, so an FYI says
the opposite correction in its place. The press makes the FYI a task - triage's ask, its To do list, on the owner's list - and writes the
lesson the way Not a task writes its own (learning.teach, LEARNED.md), the other way round, so the next mail like it reaches triage with
that line in front of it. No triage-guide edit, no pattern in code: the model writes the line. Invented Northwind world."""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import buttons, concierge, ingest, server
from taskuary.store import MemoryStore
from tests.memlines import teaching

LINE = "A registrant's reminder that their own webinar starts soon is yours to act on - join or send apologies"
MSG = {'external_id': 'web-1', 'channel': 'email', 'from_email': 'events@trainly.example', 'from_name': 'Trainly Events',
       'conversation_id': 'conv-web-1', 'subject': 'Reminder: your Trainly webinar on ledger close starts in one hour',
       'body': 'Hi Alex, the webinar you registered for starts at 14:00. Join from the link below.', 'sent_at': '2026-10-29 13:00:00'}
FYI = lambda *a, **k: json.dumps({'intent': 'fyi', 'why': 'a vendor event notice - nothing asked of you'})


class ShouldBeATaskTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)
        self.mid = ingest.ingest_message(self.s, dict(MSG), llm=FYI)['message_id']

    def test_an_fyi_has_one_move_send_to_agent_a_phish_too(self):
        """The owner, 2026-11-25: ONE move on an FYI, everywhere - Make it a task and Not for me went from its card, a phish's as well; the row
        the Assistant may light (row_buttons) is the same one move."""
        self.assertEqual(self.s.get_message(self.mid)['Status'], 'filed')
        fyi = {'kind': 'fyi', 'lane': 'fyi', 'mid': self.mid, 'key': f'msg:{self.mid}'}
        for it in (fyi, {**fyi, 'danger': 'Wants Alex to sign in on a look-alike page.', 'danger_aim': 'owner'}):
            self.assertEqual([c['verb'] for c in concierge.chips_for(self.s, it)], ['regular_agent', 'next'])
            self.assertEqual([b['label'] for b in concierge.row_buttons(self.s, it)], [buttons.label('regular_agent')])
        # ...and asked for in words, Make it a task is the plain button's name - no FYI state of its own
        prop = concierge.propose_for(self.s, None, {'verb': 'mine', 'on_item': True}, fyi, '')
        self.assertEqual(prop['label'], 'Make it a task')

    def test_pressing_it_makes_an_open_task_and_triage_reads_the_lesson_once_three_presses_bear_it_out(self):
        seen = []
        with teaching(LINE, seen=seen):
            r = self.c.post(f'/api/messages/{self.mid}/mine', json={'kind': 'task'})
        self.assertEqual(r.status_code, 200, r.text)
        t = self.s.get_task(r.json()['taskId'])
        self.assertEqual(t['Status'], 'open')
        self.assertEqual(self.s.get_message(self.mid)['TaskId'], t['TaskId'])
        # ...the lesson the model wrote, from the item and triage's own miss - the same table Not a task writes, the other way round
        self.assertIn('Made a task - triage had filed it as nothing to do', seen[0])
        self.assertIn('a vendor event notice', seen[0], "what triage had said rides with it")
        from taskuary import memory
        self.assertEqual([l['kind'] for l in memory.lessons(self.s) if l['ev'] == f'msg{self.mid}'], ['made_task'])
        # ...ONE PRESS IS ONE PRESS (the owner, 2026-11-24): an episode, not yet a line triage reads
        self.assertNotIn(LINE, self.s.get_doc('learned'))
        prompts = []
        def brain(system, user, **k): prompts.append(system); return FYI()
        def next_one(n, llm):
            return ingest.ingest_message(self.s, {**MSG, 'external_id': f'web-{n}', 'conversation_id': f'conv-web-{n}',
                                                  'subject': f'Reminder: your Trainly webinar number {n} starts in one hour'}, llm=llm)['message_id']
        next_one(2, brain)
        self.assertFalse(any(LINE in p for p in prompts), 'one press is not yet a rule triage reads')
        # ...the same press on two more like it is the pattern: in use, and the next mail of the shape is triaged with it in front
        for n in (3, 4):
            with teaching(LINE): self.assertEqual(self.c.post(f'/api/messages/{next_one(n, FYI)}/mine', json={'kind': 'task'}).status_code, 200)
        self.assertIn(LINE, self.s.get_doc('learned'))
        prompts.clear(); next_one(5, brain)
        self.assertTrue(any(LINE in p for p in prompts), 'the learned line reached triage')

if __name__ == '__main__':
    unittest.main()
