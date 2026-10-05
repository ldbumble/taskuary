"""Close out with a note: work done off the app - a phone call - is closed with what came of it, written on the task."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import server, terminal
from taskuary.store import MemoryStore


def close(s, tid, **params):
    with mock.patch.object(server, 'store', s), mock.patch.object(terminal, 'live_sessions', return_value=[]):
        c = TestClient(server.app)
        op = c.post('/api/operations', json={'kind': 'task.complete', 'target': tid, 'params': params}).json()
        return c.post(f"/api/operations/{op['id']}/execute", json={'version': op['version']}).json()


class CloseWithANoteTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Call Erin about the report', 'Kind': 'task', 'Status': 'open'}, 'triage')

    def notes(self): return [c['Body'] for c in self.s.list_comments(self.tid)]

    def test_the_note_is_on_the_task_and_the_task_is_closed(self):
        got = close(self.s, self.tid, note='  Called her - the filter was off by a month; she is fixing it.  ')
        self.assertEqual(got['status'], 'done'); self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')
        self.assertIn('Closed out: Called her - the filter was off by a month; she is fixing it.', self.notes())

    def test_no_note_closes_as_before_and_writes_nothing(self):
        before = self.notes()
        close(self.s, self.tid)
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'done'); self.assertEqual(self.notes(), before)

    def test_a_note_on_a_closed_task_is_still_kept(self):
        close(self.s, self.tid)
        close(self.s, self.tid, note='She confirmed it is fixed.')
        self.assertIn('Closed out: She confirmed it is fixed.', self.notes())
