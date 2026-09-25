"""One state per task for the Tasks list and the Board (T1-T9, the owner, 2026-09-25): the rail's rules and words,
decided once on the server."""
import unittest

from taskuary import taskstate, terminal
from taskuary.store import MemoryStore


def task(s, **kw):
    tid = s.create_task({'Title': 'Fix the export', 'Kind': kw.pop('Kind', 'coding'), 'Status': kw.pop('Status', 'open')}, 'o')
    if kw: s.update_task(tid, kw, kw.pop('by', 'o') if 'by' in kw else 'o')
    return tid


def row(s, tid, **extra): return {**s.get_task(tid), **extra}


class StateTests(unittest.TestCase):
    def test_the_list_says_what_the_rail_says(self):
        s = MemoryStore()
        t = task(s, Assignee='agent:coder')
        self.assertEqual(taskstate.state(s, row(s, t)), 'queued')                      # handed on, nothing started
        s.tag_task(t, terminal.SAVED, True, 'owner')
        self.assertEqual(taskstate.state(s, row(s, t)), 'saved')                       # you ended its session
        s.tag_task(t, terminal.SAVED, False, 'owner'); s.tag_task(t, terminal.INTERRUPTED, True, 'shutdown')
        self.assertEqual(taskstate.state(s, row(s, t)), 'stopped')                     # it ended without finishing
        self.assertEqual(taskstate.state(s, row(s, task(s))), 'yours')                 # nobody was handed it

    def test_a_live_session_is_working_or_waiting_on_you(self):
        s = MemoryStore(); t = task(s)
        self.assertEqual(taskstate.state(s, row(s, t), {'alive': True, 'waiting': False}), 'working')
        self.assertEqual(taskstate.state(s, row(s, t), {'alive': True, 'waiting': True}), 'blocked')

    def test_a_done_task_continued_is_live_work_but_a_stale_terminal_is_not(self):
        s = MemoryStore(); t = task(s); s.update_task(t, {'Status': 'done'}, 'owner')
        closed = s.get_task(t)['ClosedAt']
        self.assertEqual(taskstate.state(s, row(s, t), {'alive': True, 'started': '2999-01-01 00:00:00'}), 'working')
        self.assertEqual(taskstate.state(s, row(s, t), {'alive': True, 'started': '2000-01-01 00:00:00'}), 'closed')
        self.assertTrue(closed)

    def test_a_reply_ready_and_a_task_waiting_on_them_are_different_things(self):
        s = MemoryStore(); t = task(s, Status='waiting')
        self.assertEqual(taskstate.state(s, row(s, t)), 'theirs')
        self.assertEqual(taskstate.state(s, row(s, t, ReviewStatus='pending')), 'approve')

    def test_a_queued_start_stays_waiting_to_start_even_when_it_failed(self):
        s = MemoryStore(); t = task(s, Assignee='agent:coder')
        self.assertEqual(taskstate.state(s, row(s, t), queued={'State': 'failed'}), 'queued')

    def test_who_closed_it_decides_agent_finished(self):
        s = MemoryStore(); t = task(s)
        s.add_comment(t, 'coder', 'agent', 'The agent closed this itself: fixed.')
        s.update_task(t, {'Status': 'done'}, 'coder')
        self.assertEqual(taskstate.state(s, row(s, t)), 'agentdone')
        s.update_task(t, {'Status': 'done'}, 'owner')                                  # you edited it last
        self.assertEqual(taskstate.state(s, row(s, t)), 'closed')

    def test_board_columns(self):
        self.assertEqual([taskstate.column(k) for k in ('queued', 'working', 'blocked', 'saved', 'stopped', 'agentdone', 'approve')],
                         ['queued', 'working', 'blocked', 'left', 'left', 'agentdone', 'agentdone'])
        self.assertIsNone(taskstate.column('yours')); self.assertIsNone(taskstate.column('theirs'))



class MakeATaskTests(unittest.TestCase):
    def test_a_message_that_is_already_a_task_is_not_offered_make_a_task(self):
        # the owner, 2026-09-25: "why am i getting make this a task?? it already is" (desktop and the phone's poll)
        from taskuary import concierge
        s = MemoryStore()
        on = lambda item: [c['verb'] for c in concierge.chips_for(s, item)]
        self.assertIn('mine', on({'key': 'msg:7', 'kind': 'asked', 'mid': 7}))
        t = s.create_task({'Title': 'Send the August reports', 'Kind': 'general', 'Status': 'open'}, 'o')
        mine = {'key': 'msg:7', 'kind': 'asked', 'mid': 7, 'tid': t, 'ref': f'TQ-{t:04d}'}
        self.assertNotIn('mine', on(mine))
        self.assertIn('already a task', concierge.cannot(mine, 'mine', s))
        # ...but on a task an agent holds it takes it back, and says so
        s.update_task(t, {'Assignee': 'agent:coder'}, 'o')
        self.assertEqual([c['label'] for c in concierge.chips_for(s, mine) if c['verb'] == 'mine'], ['Take it myself'])


if __name__ == '__main__': unittest.main()
