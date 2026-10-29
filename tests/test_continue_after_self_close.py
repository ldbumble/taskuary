"""CONTINUE ON AN AGENT THAT CLOSED ITSELF MAY FINISH AGAIN (the email walk, 2026-10-29).

An agent answered, said [[TASKUARY-DONE]], and its task closed. The owner pressed Continue with new information; the agent
reconsidered, updated the reply and said it was done again - and the task sat "agent waiting on you" for minutes. The in-process
mark a self-close leaves (selfclose._DONE, there so two hooks for one turn do not both wrap) outlived its turn: the second
finish was refused "a self-close already ran". A new turn, or a new session, is a new run and clears it.
"""
import unittest
from unittest import mock

from taskuary import general, selfclose, terminal
from taskuary.store import MemoryStore
from tests.test_general_turn_ends_short import a_claude, researcher, turn


class ANewTurnMayCloseAgainTests(unittest.TestCase):
    def setUp(self): selfclose._DONE.clear(); self.addCleanup(selfclose._DONE.clear)

    def test_a_general_agents_next_turn_clears_the_last_self_close(self):
        s = MemoryStore(); a_claude(self); tid = researcher(s)
        self.assertTrue(selfclose._mark(tid))                            # the first turn closed it
        self.assertEqual(selfclose.blocked(s, tid), 'a self-close already ran for this task')
        turn(s, tid, 'Updated: renew, and use the import offer as leverage.')
        self.assertNotIn(tid, selfclose._DONE)
        self.assertEqual(selfclose.blocked(s, tid), '')

    def test_a_new_coding_session_clears_it_too(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the portal export', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        selfclose._mark(tid)
        with mock.patch.object(terminal, 'for_task', return_value=None), \
             mock.patch('taskuary.workflows.brain_of_task', side_effect=RuntimeError('stop here')):
            with self.assertRaises(RuntimeError): terminal.start_on_task(s, tid, 'coding', actor='router')
        self.assertNotIn(tid, selfclose._DONE)

    def test_a_live_session_keeps_its_mark(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the portal export', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
        selfclose._mark(tid)
        with mock.patch.object(terminal, 'for_task', return_value={'sid': 'run1'}):
            terminal.start_on_task(s, tid, 'coding', actor='router')
        self.assertIn(tid, selfclose._DONE)                              # the same run's second hook still cannot wrap twice


if __name__ == '__main__': unittest.main()
