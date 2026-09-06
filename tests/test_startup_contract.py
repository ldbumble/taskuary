"""One startup contract for both worker kinds: a session that exists is not work that was accepted,
a repository decision is not a start, and a failure is never a success (PW-209, PW-210, PW-212).

Dispatch used to answer with whatever the path it took happened to return, and one screen read a
`needs_repo` decision as a live start. Every dispatch answer - from the task page, a timeline row
or a chat card - now says the same four things: `dispatch` (session | assistant | needs_repo),
`started` (a worker session was created for this request), `existing` (a live session was reused,
nothing new started) and, for a coding session, `accepted` (the prompt was actually submitted, not
merely typed into a booting TUI). Make task creates or reuses an owner task and launches nothing.
"""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient
from fastapi import HTTPException

from taskuary import general, ingest, server
from taskuary.store import MemoryStore

MSG = {'external_id': 'e1', 'channel': 'email', 'from_email': 'dana@vendor.example', 'from_name': 'Dana', 'conversation_id': 'AAQk-x',
       'subject': 'August export', 'sent_at': '2026-09-06 09:00:00', 'body': 'Please fix the nightly export.'}


def arrive(s, kind='coding', intent='task'):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, dict(MSG), llm=lambda *a, **k: json.dumps({'intent': intent, 'kind': kind, 'why': 'w'}))


class Base(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd': r'C:\code\repo'}))
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)


class TaskDispatchTests(Base):
    def test_a_new_coding_session_is_started_and_says_whether_the_prompt_was_accepted(self):
        out = arrive(self.s, 'coding')
        with mock.patch.object(server.hub_term, 'start_on_task', return_value={'sid': 's1', 'taskId': out['task_id'], 'alive': True, 'accepted': True}):
            r = self.c.post(f"/api/tasks/{out['task_id']}/dispatch", json={'kind': 'coding'}).json()
        self.assertEqual((r['dispatch'], r['started'], r['existing'], r['accepted']), ('session', True, False, True))

    def test_a_live_session_is_reused_and_reported_as_existing_not_started(self):
        out = arrive(self.s, 'coding')
        with mock.patch.object(server.hub_term, 'start_on_task', return_value={'sid': 's1', 'taskId': out['task_id'], 'alive': True, 'existing': True}):
            r = self.c.post(f"/api/tasks/{out['task_id']}/dispatch", json={'kind': 'coding'}).json()
        self.assertEqual((r['dispatch'], r['started'], r['existing']), ('session', False, True))

    def test_a_repository_decision_is_not_a_start(self):
        out = arrive(self.s, 'coding')
        with mock.patch.object(server.hub_term, 'start_on_task', side_effect=ValueError('could not tell which checkout this belongs in - choose one')):
            r = self.c.post(f"/api/tasks/{out['task_id']}/dispatch", json={'kind': 'coding'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()['dispatch'], r.json()['started'], r.json()['existing']), ('needs_repo', False, False))
        self.assertNotIn('session', r.json())

    def test_a_failed_launch_is_an_error_never_a_success(self):
        out = arrive(self.s, 'coding')
        with mock.patch.object(server.hub_term, 'start_on_task', side_effect=RuntimeError('pty spawn failed')):
            r = self.c.post(f"/api/tasks/{out['task_id']}/dispatch", json={'kind': 'coding'})
        self.assertEqual(r.status_code, 422); self.assertIn('pty spawn failed', r.json()['detail'])

    def test_the_assistant_path_uses_the_same_words(self):
        out = arrive(self.s, 'general')
        session = mock.Mock(provider='cli:claude', model='m'); session.info.return_value = {'sid': 'g1', 'alive': True}
        with mock.patch.object(general, 'start_session', return_value=session), mock.patch.object(general, 'history', return_value=[]):
            r = self.c.post(f"/api/tasks/{out['task_id']}/dispatch", json={'kind': 'general'}).json()
        self.assertEqual((r['dispatch'], r['started'], r['existing']), ('assistant', True, False))
        with mock.patch.object(general, 'session_for', return_value=session), mock.patch.object(general, 'start_session', return_value=session), \
             mock.patch.object(general, 'history', return_value=[{'role': 'owner'}]):
            r2 = self.c.post(f"/api/tasks/{out['task_id']}/dispatch", json={'kind': 'general'}).json()
        self.assertEqual((r2['started'], r2['existing']), (False, True))


class MessageDispatchTests(Base):
    def test_a_timeline_row_gets_the_same_contract(self):
        out = arrive(self.s, 'general', intent='fyi')
        with mock.patch.object(server.hub_term, 'start_on_task', side_effect=ValueError('no local path for org/x - choose one')):
            r = self.c.post(f"/api/messages/{out['message_id']}/dispatch", json={'kind': 'coding'}).json()
        self.assertEqual((r['dispatch'], r['started']), ('needs_repo', False)); self.assertTrue(r['taskId'])
        with mock.patch.object(server.hub_term, 'start_on_task', return_value={'sid': 's1', 'alive': True, 'accepted': False}):
            r2 = self.c.post(f"/api/messages/{out['message_id']}/dispatch", json={'kind': 'coding'}).json()
        self.assertEqual((r2['dispatch'], r2['started'], r2['accepted']), ('session', True, False))

    def test_make_task_creates_or_reuses_an_owner_task_and_launches_nothing(self):
        out = arrive(self.s, 'general', intent='fyi')
        with mock.patch.object(server.hub_term, 'start_on_task') as start, mock.patch.object(general, 'start_session') as gstart:
            a = self.c.post(f"/api/messages/{out['message_id']}/mine", json={'kind': 'task'}).json()
            b = self.c.post(f"/api/messages/{out['message_id']}/mine", json={'kind': 'task'}).json()
        start.assert_not_called(); gstart.assert_not_called()
        self.assertEqual(a['taskId'], b['taskId']); self.assertEqual(len(self.s.list_tasks()), 1)
        self.assertEqual(self.s.get_task(a['taskId'])['Assignee'], 'owner')


if __name__ == '__main__':
    unittest.main()
