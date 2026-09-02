"""Every door the OWNER opens a session through marks the task theirs to end - not one dialog's
checkbox. TQ-0285 (2026-09-02): continued by hand from the task page, no tag, the agent ran
`taskuary --done`, and the session the owner was sitting in closed under them. Twice.
"""
import unittest
from unittest import mock

from taskuary import selfclose, terminal
from taskuary.store import MemoryStore


def _task(s, tags=None, status='open'):
    return s.create_task({'Title': 'review PR 33', 'Kind': 'coding', 'Status': status, 'Tags': tags}, 'router')


class Fake:
    """What open_session returns, as far as start_on_task and the route care."""
    def __init__(self, tid=None):
        self.sid, self.cwd, self.label, self.started, self.task_id, self.alive = 'fake1', 'C:/repo', 'coder', 0.0, tid, True
    def info(self): return {'sid': self.sid, 'taskId': self.task_id, 'alive': True}


class TheMarkIsSetByTheDoor(unittest.TestCase):
    def test_claim_is_the_owners_and_idempotent(self):
        s = MemoryStore(); tid = _task(s, 'repo:acme/widget')
        self.assertFalse(selfclose.claim(s, tid, 'router'))            # the funnel's own dispatch: unmarked
        self.assertFalse(selfclose.stays_open(s, tid))
        self.assertTrue(selfclose.claim(s, tid, 'owner'))
        self.assertTrue(selfclose.stays_open(s, tid))
        self.assertEqual(s.get_task(tid)['Tags'], f'repo:acme/widget,{selfclose.STAY_TAG}')   # the repo tag survives
        self.assertFalse(selfclose.claim(s, tid, 'owner'))              # already marked: nothing written twice
        self.assertFalse(selfclose.claim(s, 4242, 'owner'))             # no task, no error

    def test_continue_and_start_session_mark_it_and_a_router_start_does_not(self):
        for actor, marked in (('owner', True), ('router', False)):
            s = MemoryStore(); s.upsert_agent('coder', 'coding', 'cli', '{}'); tid = _task(s)
            seeds = []
            def fake_open(store, agent, task_id, repo, cwd, rows, cols, act, model, seed_fn=None):
                seeds.append(seed_fn(cwd) if seed_fn else ''); return Fake(task_id)
            with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(terminal, 'open_session', side_effect=fake_open), \
                 mock.patch.object(terminal, 'guess_repo', return_value=(None, '')), \
                 mock.patch('taskuary.ownwork.ensure'):
                terminal.start_on_task(s, tid, 'coder', actor=actor)
            self.assertEqual(selfclose.stays_open(s, tid), marked, actor)
            # ...and the seed built for that session says the right thing about ending it
            if marked:
                self.assertIn('THE OWNER OPENED THIS SESSION', seeds[0]); self.assertNotIn('WHEN FINISHED: run', seeds[0])
            else:
                self.assertIn('taskuary --done', seeds[0]); self.assertNotIn('THE OWNER OPENED', seeds[0])

    def test_the_terminals_route_marks_it_too(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        c = TestClient(server.app)
        tid = _task(server.store, status='done')
        with mock.patch.object(server.hub_term, 'open_session', return_value=Fake(tid)):
            r = c.post('/api/terminals', json={'agent': 'coder', 'task_id': tid, 'seed': True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(selfclose.stays_open(server.store, tid))
        self.assertEqual(server.store.get_task(tid)['Status'], 'in_progress')


class NeitherRoadEndsIt(unittest.TestCase):
    def setUp(self): selfclose._DONE.clear()

    def test_the_agents_done_is_filed_not_obeyed(self):
        s = MemoryStore(); tid = _task(s, status='in_progress'); selfclose.claim(s, tid, 'owner')
        with mock.patch('taskuary.terminal.session_for', return_value=None), \
             mock.patch.object(selfclose, 'blocked', return_value=''), \
             mock.patch.object(selfclose, '_wrap') as wrap:
            out = selfclose.declare(s, tid, 'PR 33 is not ready to merge', 'coder')
        self.assertTrue(out['held']); self.assertFalse(out['closed']); wrap.assert_not_called()
        self.assertEqual(s.get_task(tid)['Status'], 'in_progress')
        self.assertIn('The agent says it is finished: PR 33', s.list_comments(tid)[-1]['Body'])

    def test_the_judge_is_not_consulted(self):
        s = MemoryStore(); tid = _task(s, status='in_progress'); selfclose.claim(s, tid, 'owner')
        term = mock.Mock(task_id=tid, agent='coder')
        with mock.patch.object(selfclose, 'blocked', return_value=''), \
             mock.patch.object(selfclose, 'judge') as judge, mock.patch.object(selfclose, '_wrap') as wrap:
            out = selfclose.on_stop(s, term, 'all done')
        self.assertFalse(out['closed']); judge.assert_not_called(); wrap.assert_not_called()


if __name__ == '__main__':
    unittest.main()
