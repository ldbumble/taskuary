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

    def test_the_other_task_on_the_thread_hears_it_too(self):
        """The stress run, 2026-11-05: Ray's follow-up was a new ask, so his thread held two tasks; the owner's own answer to the first was
        filed on the newer one, and the first's agent never heard it - its draft sat waiting as if nobody had answered. The line still
        lands on the task it answers, and wakes no turn - a line in a chat is context (the owner, 2026-11-08) - while each open task's
        agent hears it on its next turn."""
        from unittest import mock
        from taskuary import general, ingest
        for t in (self.a, self.b): self.s.add_comment(t, 'assistant', general.ASSISTANT_TYPE, 'Looked at it.')
        self.s._exec("UPDATE comment SET CreatedAt='2026-10-29 11:40:00'")
        woke = []
        with mock.patch.object(ingest, 'thread_moved', lambda store, tid, *a, **k: woke.append((tid, k.get('own')))):
            self.assertEqual(_own(self.s, 'o5', '2026-10-29 11:43:00', 'interesting one..'), self.b)
        self.assertEqual(woke, [])
        self.assertIn('on WhatsApp: "interesting one.."', general.latest_block(self.s, self.b))
        # ...and the other task's agent is told which task it was filed on, to judge whether it is about its own (the night run, 2026-11-09)
        self.assertIn(f'on WhatsApp (filed on TQ-{self.b:04d}, "Portal login error" - judge whether it is about this task): "interesting one.."',
                      general.latest_block(self.s, self.a))

    def test_a_line_sent_while_a_turn_worked_reaches_the_next_turn(self):
        """The night run, 2026-11-09: the owner's phone line landed a second into the agent's turn - older than that turn's answer, so
        counted from the answer no later turn ever heard it. It is counted from when the answered turn began."""
        from taskuary import general
        s, t = self.s, self.a
        s.add_comment(t, 'taskuary', general.USER_TYPE, 'THE THREAD CHANGED ...'); s.add_comment(t, 'assistant', general.ASSISTANT_TYPE, 'Drafted.')
        s._exec("UPDATE comment SET CreatedAt=CASE ActorType WHEN ? THEN '2026-10-29 11:40:00' ELSE '2026-10-29 11:50:00' END WHERE TaskId=?",
                (general.USER_TYPE, t))
        _own(s, 'o6', '2026-10-29 11:41:00', 'yes 3pm, same room')
        s._exec("UPDATE message SET CreatedAt='2026-10-29 11:41:00' WHERE ExternalId='o6'")
        self.assertIn('yes 3pm, same room', general.latest_block(s, t))

    def test_a_room_with_one_task_keeps_it(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'Rota', 'Kind': 'task', 'Status': 'open'}, 'o')
        _in(s, t, 'x1', '2026-10-29 09:44:00', 'Rota please')
        self.assertEqual(_own(s, 'x2', '2026-10-29 08:00:00', 'early line'), t)


if __name__ == '__main__':
    unittest.main()
