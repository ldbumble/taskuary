"""Which brain you PICKED is which brain runs, on every road that starts a session.

`agent` is the role and `brain` is the CLI that runs it - two questions the API has taken as two
arguments since the brain layer landed. The doors in between were still built with one: the task
page sent `brain: devin` to dispatch.prepare, the operation handler rebuilt the body without it,
and the dispatch door called start_session without it either, so the work started on whatever
default_brain names - claude (the owner, 2026-09-22: "chose devin from start coding agent screen
but it started claude code").

And a start that cannot happen is not a start: /api/tasks/{id}/dispatch answers `needs_repo` with
`started: false` when no checkout can be told, which the New sheet announced as "a live session".
"""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import server, terminal as hub_term


class BrainReachesTheSessionTests(unittest.TestCase):
    def setUp(self):
        self.c, self.s = TestClient(server.app), server.store
        self.tid = self.s.create_task({'Title': 'fix the importer', 'Kind': 'coding', 'Status': 'open',
                                       'Tags': 'triage-repo:org/app'}, 'router')

    def _started(self):
        """Start a session for real up to the point a CLI would be launched, and report the call."""
        seen = {}
        def fake(store_, tid, agent=None, model=None, instruction=None, actor=None, brain=None, **kw):
            seen.update(tid=tid, agent=agent, model=model, brain=brain)
            return {'sid': 'x', 'agent': agent, 'cli': brain or 'claude', 'alive': True, 'existing': False}
        return seen, mock.patch.object(hub_term, 'start_on_task', side_effect=fake)

    def test_the_dispatch_door_carries_the_brain_it_was_given(self):
        seen, patched = self._started()
        with patched:
            r = self.c.post(f'/api/tasks/{self.tid}/dispatch', json={'kind': 'coding', 'agent': 'coder', 'brain': 'devin'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(seen.get('brain'), 'devin', 'the picked brain reached the session')

    def test_the_operation_the_task_page_runs_carries_it_too(self):
        """The task page's Start goes through operations (dispatch.prepare), which rebuilds the body."""
        seen, patched = self._started()
        with patched:
            op = self.c.post('/api/operations', json={'kind': 'dispatch.prepare', 'target': self.tid,
                                                      'params': {'kind': 'coding', 'agent': 'coder', 'brain': 'devin'}}).json()
            r = self.c.post(f"/api/operations/{op['id']}/execute", json={'version': op['version']})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(seen.get('brain'), 'devin')

    def test_a_message_promoted_to_coding_carries_it(self):
        mid = self.s.add_message({'ExternalId': 'q1', 'Channel': 'email', 'Subject': 'the importer drops rows',
                                  'FromEmail': 'dana@vendor.example', 'SentAt': '2026-09-22 09:00:00',
                                  'BodyText': 'it drops the last row', 'Status': 'routed'})
        seen, patched = self._started()
        with patched:
            r = self.c.post(f'/api/messages/{mid}/dispatch', json={'kind': 'coding', 'agent': 'coder', 'brain': 'devin'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(seen.get('brain'), 'devin')


class ANonStartIsNotAStartTests(unittest.TestCase):
    def test_a_task_with_no_checkout_answers_needs_repo_and_says_nothing_started(self):
        c, s = TestClient(server.app), server.store
        tid = s.create_task({'Title': 'no repo anywhere', 'Kind': 'coding', 'Status': 'open'}, 'router')
        with mock.patch.object(hub_term, 'start_on_task',
                               side_effect=ValueError('I could not tell which checkout this belongs in')):
            out = c.post(f'/api/tasks/{tid}/dispatch', json={'kind': 'coding', 'agent': 'coder'}).json()
        self.assertEqual(out['dispatch'], 'needs_repo')
        self.assertFalse(out['started'], 'a caller that reads `started` is told the truth')


if __name__ == '__main__':
    unittest.main()
