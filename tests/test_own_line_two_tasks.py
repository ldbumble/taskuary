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
        from taskuary import events
        self.assertIn("The owner's own message on the thread", events.take(self.s, self.b)[0]); self.assertIn('interesting one..', events.take(self.s, self.b)[0])
        # ...and the other task's agent is told which task it was filed on (the night run, 2026-11-09)
        self.assertIn(f'filed on TQ-{self.b:04d}:\ninteresting one..', events.take(self.s, self.a)[0])

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
        from taskuary import events
        self.assertIn('yes 3pm, same room', events.take(s, t)[0])      # ...an event past the cursor, whenever its turn began

    def test_a_room_with_one_task_keeps_it(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'Rota', 'Kind': 'task', 'Status': 'open'}, 'o')
        _in(s, t, 'x1', '2026-10-29 09:44:00', 'Rota please')
        self.assertEqual(_own(s, 'x2', '2026-10-29 08:00:00', 'early line'), t)


class AnOlderTaskInTheRoom(unittest.TestCase):
    """The live shape, 2026-11-19: a one-to-one chat holds months of lines. A coding task begun two days before took its first line from that
    chat at 11:11; its chat then drew, at its top, the owner's own lines to the same person from yesterday and from 11:08 - each filed on
    another task in the room - as if they had just arrived. A line on the room is this task's only from when the task joined the room."""
    def test_lines_filed_on_another_task_before_this_one_joined_the_room_are_not_drawn(self):
        from taskuary import conversation
        s = MemoryStore()
        old = s.create_task({'Title': 'Rota', 'Kind': 'task', 'Status': 'open'}, 'o')
        new = s.create_task({'Title': 'Build the export', 'Kind': 'coding', 'Status': 'open'}, 'o')
        s._exec("UPDATE task SET CreatedAt='2026-10-27 14:33:00' WHERE TaskId=?", (new,))
        _in(s, old, 'e1', '2026-10-28 14:53:00', 'Can you look at the rota?')
        self.assertEqual(_own(s, 'o1', '2026-10-28 15:16:00', 'on it'), old)
        self.assertEqual(_own(s, 'o2', '2026-10-29 11:08:00', 'done'), old)
        _in(s, new, 'e2', '2026-10-29 11:11:00', 'About the export: the dates come out wrong')
        s._exec("UPDATE message SET CreatedAt=SentAt")
        drawn = [m['ExternalId'] for m in conversation._mail(s, new)]
        self.assertEqual(drawn, ['e2'])
        # ...a line of his on the room after the task joined it is still drawn here, wherever it was filed
        mid = s.add_message({'ExternalId': 'o3', 'ConversationId': CONV, 'Channel': 'whatsapp', 'FromName': 'Alex Doyle', 'Direction': 'out',
                             'SentAt': '2026-10-29 11:15:00', 'BodyText': 'looking at it', 'Status': 'context'})
        s.attach_message(mid, old)
        self.assertEqual([m['ExternalId'] for m in conversation._mail(s, new)], ['e2', 'o3'])

    def test_his_lines_on_the_room_are_read_from_its_threads_not_the_whole_mailbox(self):
        """The owner, 2026-11-25: "hitting Next is still a bit slow". Every open and chat read asked, of every line he ever sent, whether this
        task held an earlier line of its thread - ~140 ms a read on a real store. Its work now follows the task's threads, not the mailbox."""
        from taskuary import general
        s = MemoryStore()
        new = s.create_task({'Title': 'Build the export', 'Kind': 'coding', 'Status': 'open'}, 'o')
        old = s.create_task({'Title': 'Rota', 'Kind': 'task', 'Status': 'done'}, 'o')
        s._exec("UPDATE task SET CreatedAt='2026-09-01 00:00:00' WHERE TaskId=?", (new,))
        # ...a mailbox of 20,000 lines on 2,000 threads, a third of them his own, all filed on another task
        s._exec("WITH RECURSIVE n(j) AS (SELECT 0 UNION ALL SELECT j+1 FROM n WHERE j<19999) INSERT INTO message (ExternalId, ConversationId, Channel, "
                "Direction, Status, TaskId, SentAt, CreatedAt, BodyText) SELECT 'x'||j, 'thread-'||(j%2000), 'email', CASE WHEN j%3=0 THEN 'out' ELSE 'in' END, "
                "CASE WHEN j%3=0 THEN 'context' ELSE 'filed' END, ?, datetime('2026-10-01','+'||(j/100)||' minutes'), "
                "datetime('2026-10-01','+'||(j/100)||' minutes'), 'an older line' FROM n", (old,))
        s.add_message({'ExternalId': 'e1', 'ConversationId': 'thread-5', 'Channel': 'email', 'SentAt': '2026-10-01 00:00:30', 'BodyText': 'x',
                       'Status': 'filed', 'TaskId': new})
        steps = [0]; s.cx.set_progress_handler(lambda: steps.__setitem__(0, steps[0] + 1), 100)
        got = [m['ExternalId'] for m in general.room_own(s, new)]
        s.cx.set_progress_handler(None, 0)
        # ...his lines on thread-5 no earlier than the task's own first line on it, as before
        self.assertEqual(got, ['x4005', 'x10005', 'x16005'])
        self.assertLess(steps[0], 50, f'{steps[0] * 100} database steps for one task on a 20,000-line mailbox')


if __name__ == '__main__':
    unittest.main()
