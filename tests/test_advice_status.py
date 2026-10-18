"""WHY THE STRIP IS EMPTY (general fix 4, 2026-10-18): "Thinking about this one..." ran 20 s and then showed nothing, as much over
an item the Advisor keeps out of as over one it was judging. /api/advice says which: a line, {"pending": true} while a judgement
of this item is in flight, or {"none": why}."""
import json
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import advisor, server
from taskuary.store import MemoryStore
from tests.test_advisor import _Rail, brain_saying


class StatusTests(_Rail):
    def test_a_line_is_the_line(self):
        s = MemoryStore(); t = self._stopped_task(s)
        advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=brain_saying({'verb': 'continue', 'line': 'Pick it up.', 'evidence': []}))
        with mock.patch.object(advisor, 'notice'): self.assertEqual(advisor.status(s, f'task:{t}')['verb'], 'continue')

    def test_in_flight_is_pending_and_nothing_else_is(self):
        s = MemoryStore(); t = self._stopped_task(s)
        rev = advisor.revision(s, 'task', t)
        with mock.patch.object(advisor, 'notice'), mock.patch.object(advisor, '_INFLIGHT', {('task', t, rev, 2, None)}):
            self.assertEqual(advisor.status(s, f'task:{t}'), {'pending': True})
        with mock.patch.object(advisor, 'notice'):
            self.assertEqual(advisor.status(s, f'task:{t}'), {'none': 'nothing'}, 'nothing judged and nothing judging: no spinner')

    def test_left_alone_says_why(self):
        s = MemoryStore(); t = self._stopped_task(s)
        rev = advisor.revision(s, 'task', t)
        for dropped, why in (('left to the item', 'quiet'), ('no actions', 'no_actions'), ('cap', 'cap'), ('nothing to say', 'nothing')):
            s._exec('DELETE FROM advice')
            advisor._write(s, target_kind='task', target_id=t, key=f'task:{t}', event=advisor.SHOWN, revision=rev, dropped=dropped)
            with mock.patch.object(advisor, 'notice'): self.assertEqual(advisor.status(s, f'task:{t}'), {'none': why}, dropped)

    def test_an_agent_at_work_and_a_switched_off_advisor_are_said(self):
        from taskuary import workerstate as ws
        s = MemoryStore(); t = self._stopped_task(s)
        with mock.patch.object(advisor, 'notice'), mock.patch.object(ws, 'status', return_value={'state': 'working'}):
            self.assertEqual(advisor.status(s, f'task:{t}'), {'none': 'working'})
        s.set_setting(advisor.ON_KEY, '0', 'test')
        with mock.patch.object(advisor, 'notice'): self.assertEqual(advisor.status(s, f'task:{t}'), {'none': 'off'})

    def test_nothing_to_advise_on_is_said(self):
        with mock.patch.object(advisor, 'notice'): self.assertEqual(advisor.status(MemoryStore(), 'meeting:3'), {'none': 'nothing'})

    def test_the_endpoint_answers_with_the_status(self):
        s = MemoryStore(); t = self._stopped_task(s)
        with mock.patch.object(server, 'store', s), mock.patch.object(advisor, 'notice'):
            self.assertEqual(TestClient(server.app).get('/api/advice', params={'key': f'task:{t}'}).json(), {'none': 'nothing'})
