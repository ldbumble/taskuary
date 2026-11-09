"""A TASK HELD FOR A NEW SENDER HAS ONE WAY ON (the owner, 2026-11-09): a coding task held because its sender was new showed "waiting to start"
over an empty chat with a "Run another agent" on its bar. The chat says why nothing started and offers Run anyway (website HeldStart); here,
Run another agent is never offered where no agent ever ran - an agent's task held before its start is not one. Invented people only."""
import unittest
from unittest import mock

from taskuary import concierge
from taskuary.ingest import HOLD_TAG
from taskuary.store import MemoryStore
from taskuary.testing import Factory


class RunAnotherOnlyAfterARun(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); f = Factory(self.s)
        self.tid = f.task('Fix the CSV export header order', kind='coding', Assignee='agent:coding')
        self.s.tag_task(self.tid, HOLD_TAG)
        p = mock.patch.object(concierge, '_agent_running', return_value=False); p.start(); self.addCleanup(p.stop)

    def shows(self): return concierge._shows(self.s, {'tid': self.tid}, 'run_another')

    def test_a_held_task_no_agent_ran_on_offers_no_run_another(self):
        self.assertFalse(self.shows())
        self.assertTrue(concierge._shows(self.s, {'tid': self.tid}, 'review_changes'), 'the others keep their own rule')

    def test_once_an_agent_ran_it_is_offered(self):
        self.s.start_run(self.tid, 'coding', 'fix it', 'owner')
        self.assertTrue(self.shows())
