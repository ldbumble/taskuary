"""One group chat, two open tasks: the owner's own line lands on the one it answers.

Erin asks something at 09:44 and 10:17 (task A); the owner answers at 11:36. At 11:38 and 11:39 she sends a screenshot and a
voice note about a different problem, which triage gives a task of its own (B). The owner's 11:43 line answers the voice note
- and was filed on A, because ingest_own_message took the FIRST open task whose conversations held the room."""
import unittest

from taskuary.channels import ingest_own_message
from taskuary.store import MemoryStore

CONV = 'whatsapp:ops-room@g.us'


def _in(s, tid, ext, at, body):
    mid = s.add_message({'ExternalId': ext, 'ConversationId': CONV, 'Channel': 'whatsapp', 'SourceName': 'Ops room',
                         'FromName': 'Erin Blake', 'SentAt': at, 'BodyText': body, 'Status': 'filed'})
    s.attach_message(mid, tid)


def _own(s, ext, at, body, quoted=None):
    ingest_own_message(s, {'external_id': ext, 'channel': 'whatsapp', 'conversation_id': CONV, 'source_name': 'Ops room',
                           'sent_at': at, 'body': body, 'quoted': quoted}, 'your line in this chat - kept for context')
    return s._one('SELECT TaskId FROM message WHERE ExternalId=?', (ext,))['TaskId']


class TwoTasksOneRoom(unittest.TestCase):
    def setUp(self):
        s = self.s = MemoryStore()
        self.a = s.create_task({'Title': 'Rota for next week', 'Kind': 'task', 'Status': 'open'}, 'o')
        _in(s, self.a, 'e1', '2026-10-29 09:44:00', 'Can you look at the rota for next week?')
        _in(s, self.a, 'e2', '2026-10-29 10:17:00', 'The Tuesday shift has nobody on it')
        self.assertEqual(_own(s, 'o1', '2026-10-29 11:36:00', 'I will move Gail to Tuesday'), self.a)
        self.b = s.create_task({'Title': 'Portal login error', 'Kind': 'task', 'Status': 'open'}, 'o')
        _in(s, self.b, 'e3', '2026-10-29 11:38:00', '[image] the portal shows an error')
        _in(s, self.b, 'e4', '2026-10-29 11:39:00', 'Voice note (0:20): it happens every time I sign in')

    def test_a_line_after_Bs_message_lands_on_B(self):
        self.assertEqual(_own(self.s, 'o2', '2026-10-29 11:43:00', 'interesting one..'), self.b)

    def test_a_line_after_As_message_lands_on_A(self):
        "Read back late, a line sent before B's first message answers what was last said before it - A's."
        self.assertEqual(_own(self.s, 'o3', '2026-10-29 10:20:00', 'checking now'), self.a)

    def test_a_quote_wins_over_the_newest_message(self):
        q = 'The Tuesday shift has nobody on it'
        self.assertEqual(_own(self.s, 'o4', '2026-10-29 11:45:00', 'Paula can take it', quoted=q), self.a)

    def test_a_room_with_one_task_keeps_it(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'Rota', 'Kind': 'task', 'Status': 'open'}, 'o')
        _in(s, t, 'x1', '2026-10-29 09:44:00', 'Rota please')
        self.assertEqual(_own(s, 'x2', '2026-10-29 08:00:00', 'early line'), t)


if __name__ == '__main__':
    unittest.main()
