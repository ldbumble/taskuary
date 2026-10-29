"""Should be a task, on an FYI (the owner, 2026-10-29): the put-down Not a task does not apply to what triage already filed, so an FYI says
the opposite correction in its place. The press makes the FYI a task - triage's ask, its To do list, on the owner's list - and writes the
lesson the way Not a task writes its own (memorylines.teach, LEARNED.md), the other way round, so the next mail like it reaches triage with
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

    def test_an_fyi_offers_should_be_a_task_where_a_task_offers_not_a_task(self):
        self.assertEqual(self.s.get_message(self.mid)['Status'], 'filed')
        chips = concierge.chips_for(self.s, {'kind': 'fyi', 'lane': 'fyi', 'mid': self.mid, 'key': f'msg:{self.mid}'})
        mine = next(c for c in chips if c['verb'] == 'mine')
        self.assertEqual(mine['label'], 'Should be a task')
        self.assertNotIn(buttons.label('remove'), [c['label'] for c in chips])
        self.assertEqual(buttons.label('remove'), 'Not a task')
        # ...and its press, through the proposal road the row takes, wears the same words as its badge
        prop = concierge.propose_for(self.s, None, {'verb': 'mine', 'on_item': True}, {'kind': 'fyi', 'lane': 'fyi', 'mid': self.mid, 'key': f'msg:{self.mid}'}, '')
        self.assertEqual(prop['label'], 'Should be a task')

    def test_pressing_it_makes_an_open_task_and_triage_reads_the_lesson_on_the_next_one_like_it(self):
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
        self.assertIn(LINE, self.s.get_doc('learned'))
        said = self.s._one("SELECT * FROM learned_history WHERE Action='said' AND Ev=?", (f'msg{self.mid}',))
        self.assertEqual(said['Actor'], 'verdict:made_task')
        # ...and the next mail of the same shape is triaged with that line in its prompt (the model's answer is the model's)
        prompts = []
        def brain(system, user, **k): prompts.append(system); return FYI()
        ingest.ingest_message(self.s, {**MSG, 'external_id': 'web-2', 'conversation_id': 'conv-web-2',
                                       'subject': 'Reminder: your Trainly webinar on payroll audits starts in one hour'}, llm=brain)
        self.assertTrue(any(LINE in p for p in prompts), 'the learned line reached triage')


if __name__ == '__main__':
    unittest.main()
