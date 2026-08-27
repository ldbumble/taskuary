"""The blackboard: agents aware of each other, and the affinity dispatch queue."""
import json, os, unittest
from types import SimpleNamespace

from taskuary import blackboard as bb, terminal as term
from taskuary.ingest import _auto_code, AUTO_SESSIONS
from taskuary.store import MemoryStore, task_ref
from taskuary.testing import Factory


def fake_session(tid, cwd, agent='coder', alive=True, files=()):
    return SimpleNamespace(alive=alive, task_id=tid, cwd=cwd, agent=agent, label=agent,
                           started='2026-08-23 09:00:00', files=lambda: list(files),
                           info=lambda tail=0: {'sid': 'fake', 'taskId': tid})


class BlackboardTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.fx = Factory(self.s)
        self._sessions = dict(term.SESSIONS)
        term.SESSIONS.clear()

    def tearDown(self):
        term.SESSIONS.clear(); term.SESSIONS.update(self._sessions)

    def task(self, title='Fix the cron', summary='reports cron is broken'):
        return self.fx.task(title=title, summary=summary, kind='coding')

    # ── the queue itself ──────────────────────────────────────────────────────
    def test_enqueue_is_deduped_and_clearable(self):
        t1, t2 = self.task(), self.task('Second')
        self.assertTrue(self.s.enqueue_dispatch(t2, t1, 'coder', 'overlap'))
        self.assertIsNone(self.s.enqueue_dispatch(t2, None, 'coder', 'again'))   # one row per task
        q = self.s.queued_dispatches()
        self.assertEqual([(q[0]['TaskId'], q[0]['BehindTaskId'])], [(t2, t1)])
        self.s.clear_dispatch(t2)
        self.assertEqual(self.s.queued_dispatches(), [])

    # ── who is a peer, and what the newcomer is told ──────────────────────────
    def test_peers_and_briefing_are_same_checkout_only(self):
        import os
        t1, t2, t3 = self.task('One'), self.task('Two'), self.task('Elsewhere')
        term.SESSIONS['a'] = fake_session(t1, r'C:\code\repo', files=['taskuary/reports.py'])
        term.SESSIONS['b'] = fake_session(t3, r'C:\code\other')
        # case-folding is normcase's call, which is per-PLATFORM: Windows folds, POSIX must not
        probe = r'C:\code\REPO' if os.name == 'nt' else r'C:\code\repo'
        ps = bb.peers(self.s, probe)
        self.assertEqual([p['tid'] for p in ps], [t1])
        text = bb.briefing(self.s, r'C:\code\repo', exclude_tid=t2)
        self.assertIn(task_ref(t1), text)
        self.assertIn('reports.py', text)
        self.assertIn('commit ONLY files you yourself changed', text)
        self.assertNotIn(task_ref(t3), text)                   # another repo is none of its business
        self.assertEqual(bb.briefing(self.s, r'C:\code\repo', exclude_tid=t1), '')   # alone = silence

    def test_headless_runs_are_peers_too(self):
        t1, t2 = self.task('Headless'), self.task('New')
        self.s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd': r'C:\code\repo'}))
        rid = self.s.start_run(t1, 'coder', 'work', 'owner')
        self.s.update_run(rid, {'TraceJson': json.dumps([
            {'kind': 'live', 'name': 'claude', 'detail': '→ Edit: C:\\code\\repo\\taskuary\\llm.py'}])})
        ps = bb.peers(self.s, r'C:\code\repo', exclude_tid=t2)
        self.assertEqual([(p['tid'], p['files']) for p in ps], [(t1, ['C:\\code\\repo\\taskuary\\llm.py'])])

    def test_trace_files_reads_edits_off_the_live_trace(self):
        tj = json.dumps([{'kind': 'live', 'detail': '→ Edit: a/b.py'},
                         {'kind': 'live', 'detail': '→ Bash: pytest -q'},
                         {'kind': 'live', 'detail': '→ Write: c.md\nsome text'},
                         {'kind': 'live', 'detail': '→ Edit: a/b.py'}])
        self.assertEqual(bb.trace_files(tj), ['a/b.py', 'c.md'])
        self.assertEqual(bb.trace_files('not json'), [])

    def test_seed_text_carries_the_briefing(self):
        t1, t2 = self.task('First in'), self.task('Second in')
        term.SESSIONS['a'] = fake_session(t1, r'C:\code\repo', files=['x.py'])
        seed = term.seed_text(self.s, t2, 'do it', 'org/repo', r'C:\code\repo')
        self.assertIn('OTHER AGENTS', seed)
        self.assertIn(task_ref(t1), seed)

    # ── affinity routing at auto-dispatch ─────────────────────────────────────
    def test_full_house_queues_for_a_slot(self):
        tids = [self.task(f'T{i}') for i in range(AUTO_SESSIONS)]
        for i, tid in enumerate(tids): term.SESSIONS[f's{i}'] = fake_session(tid, r'C:\code\repo')
        new = self.task('Waits for a slot')
        _auto_code(self.s, new)
        q = self.s.queued_dispatches()
        self.assertEqual([(q[0]['TaskId'], q[0]['BehindTaskId'])], [(new, None)])

    def test_likely_overlap_queues_behind_the_peer(self):
        t1, t2 = self.task('First in'), self.task('Would collide')
        self.s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd': r'C:\code\repo'}))
        term.SESSIONS['a'] = fake_session(t1, r'C:\code\repo', files=['reports.py'])
        real, bb.likely_overlap = bb.likely_overlap, lambda s, tid, ps: (ps[0], 'same files')
        try: _auto_code(self.s, t2)
        finally: bb.likely_overlap = real
        q = self.s.queued_dispatches()
        self.assertEqual([(q[0]['TaskId'], q[0]['BehindTaskId'])], [(t2, t1)])
        self.assertIn(task_ref(t1), self.s.list_comments(t2)[-1]['Body'])

    def test_no_overlap_starts_with_awareness(self):
        t1, t2 = self.task('First in'), self.task('Disjoint')
        self.s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd': r'C:\code\repo'}))
        term.SESSIONS['a'] = fake_session(t1, r'C:\code\repo')
        started = []
        real_o, bb.likely_overlap = bb.likely_overlap, lambda s, tid, ps: (None, '')
        real_s, term.start_on_task = term.start_on_task, lambda *a, **k: started.append(a[1])
        try: _auto_code(self.s, t2)
        finally: bb.likely_overlap, term.start_on_task = real_o, real_s
        self.assertEqual(started, [t2])
        self.assertEqual(self.s.queued_dispatches(), [])

    # ── the queue drains as agents finish ─────────────────────────────────────
    def test_drain_starts_what_was_blocked_and_skips_what_still_is(self):
        t1, t2, t3, t4 = self.task('Done'), self.task('Freed'), self.task('Still blocked'), self.task('Blocker')
        term.SESSIONS['b'] = fake_session(t4, r'C:\code\repo')          # t4 still working
        self.s.enqueue_dispatch(t2, t1, 'coder', 'overlap')             # t1 has no session: freed
        self.s.enqueue_dispatch(t3, t4, 'coder', 'overlap')             # t4 live: stays put
        started = []
        real, term.start_on_task = term.start_on_task, lambda s, tid, *a, **k: started.append(tid)
        try: bb.drain(self.s)
        finally: term.start_on_task = real
        self.assertEqual(started, [t2])
        self.assertEqual([q['TaskId'] for q in self.s.queued_dispatches()], [t3])

    def test_drain_clears_a_task_that_moved_on(self):
        t1 = self.task('Closed while queued')
        self.s.enqueue_dispatch(t1, None, 'coder', 'slot')
        self.s.update_task(t1, {'Status': 'done'}, 't')
        bb.drain(self.s)
        self.assertEqual(self.s.queued_dispatches(), [])


if __name__ == '__main__':
    unittest.main()
