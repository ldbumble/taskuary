"""Explicit completion: save the agent's own result, tick what it reported, then close its run (PW-230 to PW-234).

An agent that said it was finished had its result rebuilt by a second AI from terminal scrollback;
a session the owner had opened stayed open after `taskuary --done` because a veto meant for the
judge also stopped the explicit word; the terminal was closed before the report was written, so a
failed save lost the session and still read as finished. Now the final answer is captured
directly - the `--done` sentence and the Stop hook's last message, matched to the run - and
persisted with the report and the reported checklist items BEFORE the run closes; only items the
agent said it completed are ticked; an explicit finish closes the completed run even when the
owner opened it, saving the result and leaving the task's own closure to the owner; a save that
fails neither closes the session nor claims finalisation, and a second finish for the same run
does nothing twice.
"""
import unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import coder, selfclose, session_artifacts, terminal as term, workerstate as ws
from taskuary.store import MemoryStore


def live(tid, sid='run1'):
    return SimpleNamespace(sid=sid, alive=True, task_id=tid, cwd=r'C:\code\repo', agent='coder', label='coder', argv=['claude'],
                           started='2026-09-06 09:00:00', started_ts=1.0, n=5000, tail=lambda k=3: ['done'], files=lambda: [],
                           witness=SimpleNamespace(said='I fixed the cron user and re-ran it.', note=lambda n: None), store=None, last=1.0)


class Base(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self._sessions = dict(term.SESSIONS); term.SESSIONS.clear(); selfclose._DONE.clear()
        self.tid = self.s.create_task({'Title': 'Fix the cron', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
        self.s.set_task_checklist(self.tid, ['Find why the cron fails', 'Fix it', 'Re-run tonight'], 'triage')
        self.closed = []
        self.patches = [mock.patch.object(term, 'transcript_for', return_value=('the transcript\n- [x] Find why the cron fails\n- [x] Fix it', 'coder', 'run1')),
                        mock.patch.object(term, 'close', side_effect=lambda sid: self.closed.append(sid) or True),
                        mock.patch.object(coder, 'report_from_transcript', return_value={'summary': 'Fixed the cron user.', 'changed': [], 'left': ''}),
                        mock.patch.object(coder, 'resolution_text', return_value='Fixed the cron user.'),
                        mock.patch.object(coder, 'finish', return_value={'drafting': False}),
                        mock.patch('taskuary.proposals.collect', return_value=[]),
                        mock.patch('taskuary.playbooks.draft', return_value=None),
                        mock.patch('taskuary.handbook.enabled', return_value=False)]
        for p in self.patches: p.start(); self.addCleanup(p.stop)
    def tearDown(self): term.SESSIONS.clear(); term.SESSIONS.update(self._sessions)
    def artifacts(self): return [a for a in self.s.list_task_artifacts(self.tid) if a.get('Kind') == 'coding_session']
    def artifact_text(self):
        import pathlib
        return pathlib.Path(self.artifacts()[0]['Path']).read_text(encoding='utf-8')      # newest first


class SaveBeforeCloseTests(Base):
    def test_the_result_and_the_reported_checklist_are_saved_before_the_run_closes(self):
        term.SESSIONS['run1'] = live(self.tid)
        order = []
        with mock.patch.object(session_artifacts, 'coding', side_effect=lambda *a, **k: order.append('saved') or {'ArtifactId': 1, 'Path': 'x', 'Kind': 'coding_session'}), \
             mock.patch.object(term, 'close', side_effect=lambda sid: order.append('closed') or True):
            coder.wrap(self.s, self.tid, close=True, actor='coder', final_message='Fixed: the cron ran as the wrong user.')
        self.assertEqual(order, ['saved', 'closed'])
        items = {i['text']: i['done'] for i in self.s.task_checklist(self.tid)}
        self.assertEqual(items, {'Find why the cron fails': True, 'Fix it': True, 'Re-run tonight': False})   # only what the agent said it did

    def test_the_final_answer_is_the_agents_own_and_matched_to_the_run(self):
        term.SESSIONS['run1'] = live(self.tid)
        ws.record(self.s, self.tid, 'run1', 'finished', text='Done: cleared the stuck job and re-ran it.', source='cli')
        coder.wrap(self.s, self.tid, close=True, actor='coder')
        self.assertIn('cleared the stuck job', self.artifact_text())                       # the --done sentence, not a reconstruction
        term.SESSIONS['run1'].alive = False                                              # the first run is over
        term.SESSIONS['run2'] = live(self.tid, 'run2')
        ws.record(self.s, self.tid, 'run2', 'finished', text='Second run: nothing left to do.', source='cli')
        coder.wrap(self.s, self.tid, close=True, actor='coder')
        self.assertIn('Second run', self.artifact_text()); self.assertNotIn('cleared the stuck job', self.artifact_text())

    def test_a_save_that_fails_keeps_the_session_and_claims_nothing(self):
        term.SESSIONS['run1'] = live(self.tid)
        with mock.patch.object(session_artifacts, 'coding', side_effect=OSError('disk full')):
            with self.assertRaises(ValueError): coder.wrap(self.s, self.tid, close=True, actor='coder', final_message='x')
        self.assertEqual(self.closed, []); self.assertEqual(self.s.get_task(self.tid)['Status'], 'in_progress')
        self.assertFalse(any(str(c['Body']).startswith('CODER REPORT') for c in self.s.list_comments(self.tid)))


class ExplicitFinishTests(Base):
    def test_an_owner_opened_session_still_closes_its_run_on_an_explicit_finish_and_leaves_the_task_to_the_owner(self):
        sess = live(self.tid); term.SESSIONS['run1'] = sess
        selfclose.claim(self.s, self.tid, 'owner')                                           # the owner opened it to sit in
        out = selfclose.declare(self.s, self.tid, 'cleared the stuck job', 'coder')
        self.assertTrue(out.get('closed_run')); self.assertEqual(self.closed, ['run1'])       # the run closed and the result saved...
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'in_progress')                 # ...the task is the owner's to end
        self.assertEqual(ws.status(self.s, self.tid)['state'], 'finished')
        self.assertTrue(self.artifacts())

    def test_a_second_finish_for_the_same_run_does_nothing_twice(self):
        term.SESSIONS['run1'] = live(self.tid)
        a = selfclose.declare(self.s, self.tid, 'done', 'coder')
        b = selfclose.declare(self.s, self.tid, 'done again', 'coder')
        self.assertTrue(a.get('closed') or a.get('closed_run')); self.assertFalse(b.get('closed') or b.get('closed_run'))
        self.assertEqual(len(self.artifacts()), 1)

    def test_a_finish_whose_save_fails_can_be_retried(self):
        term.SESSIONS['run1'] = live(self.tid)
        with mock.patch.object(session_artifacts, 'coding', side_effect=OSError('disk full')):
            a = selfclose.declare(self.s, self.tid, 'done', 'coder')
        self.assertFalse(a.get('closed')); self.assertTrue(any('could not' in c['Body'] for c in self.s.list_comments(self.tid)))
        b = selfclose.declare(self.s, self.tid, 'done', 'coder')
        self.assertTrue(b.get('closed') or b.get('closed_run')); self.assertEqual(len(self.artifacts()), 1)


if __name__ == '__main__':
    unittest.main()
