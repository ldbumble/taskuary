"""Similar work is a briefing, not a queue; the wall is live coordination only (PW-171 to PW-181).

A task the model judged likely to touch the same files as a running one was parked behind it,
and every agent's seed prompt quoted the newest note on the checkout's wall whoever wrote it and
however long ago their session ended. Now overlap is advisory: the new agent starts (capacity
permitting) with a factual briefing - which peers are in this checkout, who they are, what they are
doing, which files they have touched, what they have said - and the model's read of similarity
when there is one, said as a read, with "not assessed" when there is none. Wall notes belong to a
session: they are live while that session is alive and drop off every live surface when it ends,
a restart of the same task does not revive them, and no surface falls back to history. The
owner's own house notes are durable guidance and stay. Ended-run notes are kept for history and
shown as historical, never as current file ownership.
"""
import json, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import blackboard as bb, general, ingest, terminal as term
from taskuary.store import MemoryStore, task_ref
from taskuary.testing import Factory

CWD = r'C:\code\repo'


def fake_session(tid, sid='s1', cwd=CWD, alive=True, agent='coder', files=()):
    return SimpleNamespace(sid=sid, alive=alive, task_id=tid, cwd=cwd, agent=agent, label=agent, started='2026-09-06 09:00:00',
                           files=lambda: list(files), info=lambda tail=0, details=True: {'sid': sid, 'taskId': tid, 'alive': alive})


class Base(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.fx = Factory(self.s)
        self._sessions = dict(term.SESSIONS); term.SESSIONS.clear()
        self.s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd': CWD}))
    def tearDown(self): term.SESSIONS.clear(); term.SESSIONS.update(self._sessions)
    def task(self, title='Fix the cron', summary='reports cron is broken'): return self.fx.task(title=title, Summary=summary, kind='coding')


class AdvisoryOverlapTests(Base):
    def test_likely_overlap_starts_the_task_and_briefs_it_instead_of_parking_it(self):
        t1, t2 = self.task('First in'), self.task('Would collide', 'also touches reports.py')
        term.SESSIONS['a'] = fake_session(t1, 'a', files=['reports.py'])
        started = []
        with mock.patch.object(bb, 'likely_overlap', return_value=({'tid': t1, 'ref': task_ref(t1), 'title': 'First in'}, 'same files')), \
             mock.patch.object(term, 'start_on_task', side_effect=lambda s, tid, *a, **k: started.append(tid)):
            ingest._auto_code(self.s, t2)
        self.assertEqual(started, [t2]); self.assertEqual(self.s.queued_dispatches(), [])
        self.assertFalse(any('Queued behind' in c['Body'] for c in self.s.list_comments(t2)))

    def test_an_old_overlap_dependency_no_longer_blocks_the_queue(self):
        t1, t2 = self.task('Blocker'), self.task('Was parked behind it')
        term.SESSIONS['a'] = fake_session(t1, 'a')
        self.s.enqueue_dispatch(t2, t1, 'coder', 'likely to touch the same files')
        started = []
        with mock.patch.object(term, 'start_on_task', side_effect=lambda s, tid, *a, **k: started.append(tid)): bb.drain(self.s)
        self.assertEqual(started, [t2]); self.assertEqual(self.s.queued_dispatches(), [])

    def test_a_ranked_task_is_not_re_parked_on_its_way_out(self):
        t1, t2 = self.task('Running'), self.task('Ranked')
        term.SESSIONS['a'] = fake_session(t1, 'a', files=['reports.py'])
        self.s.enqueue_dispatch(t2, None, 'coder', 'ranked', value=0.7, why='asked directly')
        started = []
        with mock.patch.object(bb, 'likely_overlap', return_value=({'tid': t1, 'ref': task_ref(t1), 'title': 'Running'}, 'same files')), \
             mock.patch.object(term, 'start_on_task', side_effect=lambda s, tid, *a, **k: started.append(tid)):
            bb.drain(self.s)
        self.assertEqual(started, [t2])

    def test_capacity_still_queues(self):
        self.s.set_setting('auto_sessions', '1', 't')
        t1, t2 = self.task('Running'), self.task('Waits for a desk')
        term.SESSIONS['a'] = fake_session(t1, 'a')
        with mock.patch.object(term, 'start_on_task') as start: ingest._auto_code(self.s, t2)
        start.assert_not_called(); self.assertEqual([q['TaskId'] for q in self.s.queued_dispatches()], [t2])


class BriefingTests(Base):
    def test_the_briefing_is_the_facts_plus_the_models_read_said_as_a_read(self):
        t1, t2 = self.task('First in', 'rewrite the report scheduler'), self.task('Newcomer')
        term.SESSIONS['a'] = fake_session(t1, 'a', agent='codex', files=[r'C:\code\repo\reports.py'])
        bb.post(self.s, 'taking reports.py, do not touch until I say ready', 'working', 'codex', CWD, t1, sid='a')
        with mock.patch.object(bb, 'likely_overlap', return_value=({'tid': t1, 'ref': task_ref(t1), 'title': 'First in'}, 'both touch the scheduler')):
            text = bb.briefing(self.s, CWD, exclude_tid=t2, assess_for=t2)
        for needle in (task_ref(t1), 'codex', 'rewrite the report scheduler', 'reports.py', 'taking reports.py', 'SIMILAR WORK', 'both touch the scheduler',
                       'Coordinate', 'stage and commit ONLY files you yourself changed'):
            self.assertIn(needle, text, needle)
        self.assertNotIn('locked', text.lower()); self.assertNotIn('worktree', text.lower())

    def test_no_assessment_is_not_no_overlap(self):
        t1, t2 = self.task('First in'), self.task('Newcomer')
        term.SESSIONS['a'] = fake_session(t1, 'a', files=['reports.py'])
        with mock.patch.object(bb, 'likely_overlap', return_value=(None, '')):
            text = bb.briefing(self.s, CWD, exclude_tid=t2, assess_for=t2)
        self.assertIn(task_ref(t1), text); self.assertIn('not assessed', text.lower()); self.assertIn('reports.py', text)

    def test_a_closed_sessions_note_is_not_current_ownership(self):
        t1, t2 = self.task('Finished'), self.task('Newcomer')
        bb.post(self.s, 'I own reports.py', 'working', 'codex', CWD, t1, sid='gone')       # its session ended
        text = bb.briefing(self.s, CWD, exclude_tid=t2)
        self.assertEqual(text, '')                                                             # nobody is here: nothing to brief


class LiveWallTests(Base):
    def test_notes_belong_to_a_session_and_leave_the_live_surfaces_when_it_ends(self):
        t1 = self.task()
        bb.post(self.s, 'first run: taking auth.py', 'working', 'codex', CWD, t1, sid='run1')
        term.SESSIONS['run1'] = fake_session(t1, 'run1')
        self.assertEqual([n['Body'] for n in bb.live_notes(self.s, CWD)], ['first run: taking auth.py'])
        term.SESSIONS.clear()
        self.assertEqual(bb.live_notes(self.s, CWD), [])                                        # the run ended: gone from live
        term.SESSIONS['run2'] = fake_session(t1, 'run2')                                        # the same task restarted
        self.assertEqual(bb.live_notes(self.s, CWD), [])                                        # ...does not revive the old run's notes
        bb.post(self.s, 'second run: starting over', 'working', 'codex', CWD, t1, sid='run2')
        self.assertEqual([n['Body'] for n in bb.live_notes(self.s, CWD)], ['second run: starting over'])

    def test_a_waiting_session_is_live_and_a_legacy_note_follows_its_task(self):
        t1 = self.task()
        term.SESSIONS['w'] = fake_session(t1, 'w')                                             # alive, sitting at an approval prompt
        bb.post(self.s, 'legacy note without a session', 'note', 'codex', CWD, t1)              # written before notes knew their run
        bb.post(self.s, 'approval pending on the migration', 'blocked', 'codex', CWD, t1, sid='w')
        self.assertEqual(sorted(n['Body'] for n in bb.live_notes(self.s, CWD)), ['approval pending on the migration', 'legacy note without a session'])

    def test_the_owners_house_notes_are_guidance_and_stay_while_agent_house_notes_follow_their_run(self):
        bb.post(self.s, 'the Intacct credentials are being rotated today', 'blocked', 'you', '')
        bb.post(self.s, 'found the flaky test, see TQ-0009', 'note', 'assistant', '', None, sid='chat1')
        self.assertEqual([n['Body'] for n in bb.live_notes(self.s, CWD)], ['the Intacct credentials are being rotated today'])
        term.SESSIONS['chat1'] = fake_session(None, 'chat1', cwd='', agent='assistant')
        self.assertEqual(sorted(n['Body'] for n in bb.live_notes(self.s, CWD)),
                         ['found the flaky test, see TQ-0009', 'the Intacct credentials are being rotated today'])

    def test_every_surface_reads_the_same_live_selection(self):
        t1 = self.task()
        bb.post(self.s, 'closed run said this', 'ready', 'claude', CWD, t1, sid='old')
        bb.post(self.s, 'closed chat said this', 'note', 'assistant', '', None, sid='oldchat')
        self.assertEqual(bb.wall_text(self.s, CWD), '')                                          # the seed: no fallback to history
        self.assertEqual(bb.chat_text(self.s), '')                                               # the assistant's prompt: none either
        self.assertEqual(bb.live_wall(self.s), [])                                               # the Board's live handoff
        term.SESSIONS['new'] = fake_session(t1, 'new')
        bb.post(self.s, 'live run: auth done, suite green', 'ready', 'claude', CWD, t1, sid='new')
        self.assertIn('auth done, suite green', bb.wall_text(self.s, CWD))
        self.assertEqual([n['Body'] for n in bb.live_wall(self.s)], ['live run: auth done, suite green'])

    def test_history_keeps_ended_run_notes_and_marks_them_historical(self):
        t1 = self.task()
        bb.post(self.s, 'from the ended run', 'done', 'claude', CWD, t1, sid='old')
        term.SESSIONS['new'] = fake_session(t1, 'new')
        bb.post(self.s, 'from the live run', 'working', 'claude', CWD, t1, sid='new')
        rows = {n['Body']: n['live'] for n in bb.history(self.s, CWD)}
        self.assertEqual(rows, {'from the ended run': False, 'from the live run': True})

    def test_the_general_prompt_carries_live_house_notes_only(self):
        tid = self.fx.task(title='research', summary='x', kind='general')
        bb.post(self.s, 'closed chat left this', 'note', 'assistant', '', None, sid='oldchat')
        bb.post(self.s, 'the Intacct credentials are being rotated today', 'blocked', 'you', '')
        _system, user = general._prompt(self.s, tid)
        self.assertIn('rotated today', user); self.assertNotIn('closed chat left this', user)


class SessionIdentityTests(unittest.TestCase):
    def test_a_sessions_shell_knows_its_own_session_id_so_its_notes_can_be_owned(self):
        env = term.session_env('coder', 7, CWD, sid='abc123')
        self.assertEqual(env.get('TASKUARY_SID'), 'abc123')


if __name__ == '__main__':
    unittest.main()
