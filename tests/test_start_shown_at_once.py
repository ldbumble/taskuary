"""A start on the task the owner has open is on the page at once (the owner, 2026-11-04: "the agent tab did not say 'agent starting' right
away. Until 10 seconds later it just opened"). A quick call, a Continue or a carried-on turn holds the task in general.OPENING for seconds
before any session exists; the mark wakes the page, the task's read says so, and a queued start says it waits. Invented task only."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import general, handraise, server
from taskuary.store import MemoryStore


class OpeningTests(unittest.TestCase):
    def tearDown(self): general.OPENING.clear()

    def test_marking_and_clearing_wake_the_task_once_each(self):
        with mock.patch.object(handraise, 'moved') as moved:
            general.OPENING.add(41); general.OPENING.add(41)
            self.assertEqual(moved.call_args_list, [mock.call(41)], 'marked: the open page reads the task now, and once')
            general.OPENING.discard(41); general.OPENING.discard(41)
        self.assertEqual(moved.call_count, 2, 'cleared: once more, and a clear of nothing is quiet')
        self.assertNotIn(41, general.OPENING)

    def test_the_tasks_read_carries_a_start_under_way_and_a_queued_one(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Compare payroll vendors', 'Kind': 'general', 'Status': 'open'}, 'o')
        with mock.patch.object(server, 'store', s):
            c = TestClient(server.app)
            d = c.get(f'/api/tasks/{tid}').json()
            self.assertEqual((d['starting'], d['queued']), (False, None))
            general.OPENING.add(tid)
            self.assertTrue(c.get(f'/api/tasks/{tid}').json()['starting'])
            general.OPENING.discard(tid)
            s.enqueue_dispatch(tid, None, 'assistant', '2 agents are already running')
            q = c.get(f'/api/tasks/{tid}').json()['queued']
        self.assertEqual((q['state'], q['reason']), ('waiting', '2 agents are already running'))

    def test_send_to_agent_is_opening_until_its_first_turn_has_run(self):
        """Answered before the turn took the session, the page read an idle session that had said nothing - no Starting…, no poll."""
        s = MemoryStore()
        tid = s.create_task({'Title': 'Compare payroll vendors', 'Summary': 'Compare three payroll vendors', 'Kind': 'general', 'Status': 'open'}, 'o')
        seen = []
        ses = mock.Mock(provider='Claude', model='', send_prompt=lambda *a, **k: seen.append(tid in general.OPENING))
        ses.info.return_value = {'sid': 's1', 'alive': True}
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.start_session', return_value=ses), \
             mock.patch.object(server, '_no_brain', return_value=''):
            out = TestClient(server.app).post(f'/api/tasks/{tid}/dispatch', json={'kind': 'general'}).json()
        self.assertTrue(out['started'])
        self.assertEqual(seen, [True], 'the turn runs marked opening')
        self.assertNotIn(tid, general.OPENING, 'and the mark goes with it')


if __name__ == '__main__': unittest.main()
