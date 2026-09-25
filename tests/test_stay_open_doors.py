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
            def fake_open(store, agent, task_id, repo, cwd, rows, cols, act, model, seed_fn=None, resume=None, **kw):
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

    def test_a_session_limit_hands_the_same_task_to_the_backup_brain(self):
        """The ROLE does not change because a CLI fell over - the job is the same job. What the
        chain moves through is BRAINS (the 2026-09-16 spec)."""
        s = MemoryStore(); tid = _task(s)
        s.upsert_agent('coder', 'coding', 'cli', '{}')
        s.set_setting('default_brain', 'claude', 'owner')
        s.set_setting('backup_brains', 'codex', 'owner')
        opened = []

        def fake_open(store, agent, task_id, *args, **kwargs):
            brain = kwargs.get('brain')
            term = Fake(task_id)
            term.sid, term.label, term.agent = f'{brain}-session', agent, agent
            term.failover = None
            opened.append((brain, term))
            return term

        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(terminal, 'open_session', side_effect=fake_open), \
             mock.patch.object(terminal, 'guess_repo', return_value=(None, None)), \
             mock.patch('taskuary.ownwork.ensure'):
            terminal.start_on_task(s, tid, 'coder', actor='owner')
            self.assertTrue(callable(opened[0][1].failover))
            opened[0][1].failover(opened[0][1], "You've hit your session limit")

        self.assertEqual([brain for brain, _term in opened], ['claude', 'codex'])
        self.assertTrue(all(term.agent == 'coder' for _brain, term in opened))   # one role throughout
        self.assertIn('continuing with backup codex', '\n'.join(x['Body'] for x in s.list_comments(tid)))

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

    def test_the_agents_done_ends_it_even_on_a_session_the_owner_opened(self):
        """Only the JUDGE is vetoed by the tag. The agent saying it in words is the ending
        (2026-09-17) - the road the seed prompt asks every session to take."""
        s = MemoryStore(); tid = _task(s, status='in_progress'); selfclose.claim(s, tid, 'owner')
        with mock.patch('taskuary.terminal.session_for', return_value=None), \
             mock.patch.object(selfclose, 'blocked', return_value=''), \
             mock.patch.object(selfclose, '_wrap', return_value={'closed': True}) as wrap:
            out = selfclose.declare(s, tid, 'PR 33 is not ready to merge', 'coder')
        self.assertTrue(out['closed']); wrap.assert_called_once()
        self.assertIn('The agent closed this itself: PR 33', ' '.join(c['Body'] for c in s.list_comments(tid)))


if __name__ == '__main__':
    unittest.main()
