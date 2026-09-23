"""A folded agent card shows what the agent said last (2026-09-23): workerstate.status carries it."""
import unittest

from taskuary import workerstate as ws
from taskuary.store import MemoryStore


class SaidTests(unittest.TestCase):
    def test_status_carries_the_runs_last_words(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'SAML settings', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        ws.record(s, tid, 'sid1', 'working', source='hook')
        ws.record(s, tid, 'sid1', 'turn_end', text='Short answer: we do not need a new ID. Should I draft the reply?', source='hook')
        self.assertEqual(ws.status(s, tid)['said'], 'Short answer: we do not need a new ID. Should I draft the reply?')

    def test_nothing_said_is_empty(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'x', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        self.assertEqual(ws.status(s, tid).get('said', ''), '')
