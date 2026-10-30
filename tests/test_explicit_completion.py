"""Explicit completion: save the agent's own result, then close its run (PW-230 to PW-234).

An agent that said it was finished had its result rebuilt by a second AI from terminal scrollback;
a session the owner had opened stayed open after `taskuary --done` because a veto meant for the
judge also stopped the explicit word; the terminal was closed before the report was written, so a
failed save lost the session and still read as finished. Now the final answer is captured
directly - the `--done` sentence and the Stop hook's last message, matched to the run - and
persisted with the report BEFORE the run closes (no checklist box is ticked from its prose - 2026-10-11);
an explicit finish ends a task only when the task allows it -
on a session the owner opened (stay:open) it is refused and the owner completes it (2026-09-25); a save that
fails neither closes the session nor claims finalisation, and a second finish for the same run
does nothing twice.
"""
import unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import wrapup, selfclose, session_artifacts, terminal as term, workerstate as ws
from taskuary.store import MemoryStore


def live(tid, sid='run1'):
    return SimpleNamespace(sid=sid, alive=True, task_id=tid, cwd=r'C:\code\repo', agent='coding', label='coding', argv=['claude'],
                           started='2026-09-06 09:00:00', started_ts=1.0, n=5000, tail=lambda k=3: ['done'], files=lambda: [],
                           witness=SimpleNamespace(said='I fixed the cron user and re-ran it.', note=lambda n: None), store=None, last=1.0)


class Base(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self._sessions = dict(term.SESSIONS); term.SESSIONS.clear(); selfclose._DONE.clear()
        self.tid = self.s.create_task({'Title': 'Fix the cron', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
        self.s.set_task_checklist(self.tid, ['Find why the cron fails', 'Fix it', 'Re-run tonight'], 'triage')
        self.closed = []
        self.patches = [mock.patch.object(term, 'transcript_for', return_value=('the transcript\n- [x] Find why the cron fails\n- [x] Fix it', 'coding', 'run1')),
                        mock.patch.object(term, 'close', side_effect=lambda sid: self.closed.append(sid) or True),
                        mock.patch.object(wrapup, 'report_from_transcript', return_value={'summary': 'Fixed the cron user.', 'changed': [], 'left': ''}),
                        mock.patch.object(wrapup, 'resolution_text', return_value='Fixed the cron user.'),
                        mock.patch.object(wrapup, 'finish', return_value={'drafting': False}),
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
            wrapup.wrap(self.s, self.tid, close=True, actor='agent', final_message='Fixed: the cron ran as the wrong user.')
        self.assertEqual(order, ['saved', 'closed'])
        # no box is ticked from a `- [x] ...` line in the prose (2026-10-11): nothing gives the agent an item id to report,
        # and a substring match ticked items it never named; closing the TASK ticks every box (done-ticks-every-box)
        items = {i['text']: i['done'] for i in self.s.task_checklist(self.tid)}
        self.assertEqual(items, {'Find why the cron fails': False, 'Fix it': False, 'Re-run tonight': False})
        self.assertFalse(hasattr(wrapup, 'tick_reported_checklist'))

    def test_the_final_answer_is_the_agents_own_and_matched_to_the_run(self):
        term.SESSIONS['run1'] = live(self.tid)
        ws.record(self.s, self.tid, 'run1', 'finished', text='Done: cleared the stuck job and re-ran it.', source='cli')
        wrapup.wrap(self.s, self.tid, close=True, actor='agent')
        self.assertIn('cleared the stuck job', self.artifact_text())                       # the --done sentence, not a reconstruction
        term.SESSIONS['run1'].alive = False                                              # the first run is over
        term.SESSIONS['run2'] = live(self.tid, 'run2')
        ws.record(self.s, self.tid, 'run2', 'finished', text='Second run: nothing left to do.', source='cli')
        with mock.patch.object(term, 'transcript_for', return_value=('the second transcript', 'coding', 'run2')):   # run1 is wrapped once only
            wrapup.wrap(self.s, self.tid, close=True, actor='agent')
        self.assertIn('Second run', self.artifact_text()); self.assertNotIn('cleared the stuck job', self.artifact_text())

    def test_a_save_that_fails_keeps_the_session_and_claims_nothing(self):
        term.SESSIONS['run1'] = live(self.tid)
        with mock.patch.object(session_artifacts, 'coding', side_effect=OSError('disk full')):
            with self.assertRaises(ValueError): wrapup.wrap(self.s, self.tid, close=True, actor='agent', final_message='x')
        self.assertEqual(self.closed, []); self.assertEqual(self.s.get_task(self.tid)['Status'], 'in_progress')
        self.assertFalse(any(str(c['Body']).startswith(wrapup.REPORTS) for c in self.s.list_comments(self.tid)))


class ExplicitFinishTests(Base):
    def test_an_owner_opened_session_keeps_completion_with_the_owner(self):
        """ONE rule (the owner, 2026-09-25): an agent may close its own task only when the task allows it.
        On a session the owner opened (stay:open) `--done` is refused, as its seed says - the run is not
        closed, nothing is wrapped, and the agent's sentence is filed for the owner."""
        sess = live(self.tid); term.SESSIONS['run1'] = sess
        selfclose.claim(self.s, self.tid, 'owner')                                           # the owner opened it to sit in
        out = selfclose.declare(self.s, self.tid, 'cleared the stuck job', 'agent')
        self.assertFalse(out.get('closed')); self.assertEqual(out['why'], selfclose.OWNER_ENDS)
        self.assertEqual(self.closed, []); self.assertFalse(self.artifacts())
        self.assertIn('The agent says it is finished: cleared the stuck job', ' '.join(c['Body'] for c in self.s.list_comments(self.tid)))
        # ...and once the owner takes the mark off, the same word is the ending
        selfclose.unclaim(self.s, self.tid)
        self.assertTrue(selfclose.declare(self.s, self.tid, 'cleared the stuck job', 'agent').get('closed'))
        self.assertEqual(self.closed, ['run1']); self.assertEqual(ws.status(self.s, self.tid)['state'], 'finished')

    def test_a_second_finish_for_the_same_run_does_nothing_twice(self):
        term.SESSIONS['run1'] = live(self.tid)
        a = selfclose.declare(self.s, self.tid, 'done', 'agent')
        b = selfclose.declare(self.s, self.tid, 'done again', 'agent')
        self.assertTrue(a.get('closed') or a.get('closed_run')); self.assertFalse(b.get('closed') or b.get('closed_run'))
        self.assertEqual(len(self.artifacts()), 1)

    def test_a_finish_whose_save_fails_can_be_retried(self):
        term.SESSIONS['run1'] = live(self.tid)
        with mock.patch.object(session_artifacts, 'coding', side_effect=OSError('disk full')):
            a = selfclose.declare(self.s, self.tid, 'done', 'agent')
        self.assertFalse(a.get('closed')); self.assertTrue(any('could not' in c['Body'] for c in self.s.list_comments(self.tid)))
        b = selfclose.declare(self.s, self.tid, 'done', 'agent')
        self.assertTrue(b.get('closed') or b.get('closed_run')); self.assertEqual(len(self.artifacts()), 1)



class QuestionGateTests(Base):
    """`--done` is refused for a question the RUN raised and nobody answered - a held ask, or one asked through the CLI's
    question tool or a [[TASKUARY-ASK]] marker - never for the words on its screen (2026-10-11, "everything should be ai")."""
    def test_a_question_mark_on_the_screen_does_not_refuse_done(self):
        sess = live(self.tid); sess.tail = lambda k=3: ['Fixed the cron. Why did it fail? It ran as the wrong user.', 'Should I also tidy the logs?']
        term.SESSIONS['run1'] = sess
        self.assertEqual(selfclose.blocked(self.s, self.tid, sess), '')
        self.assertTrue(selfclose.declare(self.s, self.tid, 'fixed the cron', 'agent').get('closed'))

    def test_an_open_marker_question_refuses_done(self):
        sess = live(self.tid); term.SESSIONS['run1'] = sess
        ws.record(self.s, self.tid, 'run1', 'input_needed', text='Which account should the refund go to?', choices=['Card', 'Bank'], source='api')
        self.assertIn('Which account should the refund go to?', selfclose.blocked(self.s, self.tid, sess))
        self.assertFalse(selfclose.declare(self.s, self.tid, 'done', 'agent').get('closed'))

    def test_a_hook_question_the_agent_is_past_does_not_refuse_done(self):
        # a hook's question blocks the CLI that asked it: an agent running --done is past it (the owner, 2026-10-30)
        sess = live(self.tid); term.SESSIONS['run1'] = sess
        ws.record(self.s, self.tid, 'run1', 'input_needed', text='Which account should the refund go to?', choices=['Card', 'Bank'], source='hook')
        self.assertEqual(selfclose.blocked(self.s, self.tid, sess), '')

    def test_the_models_read_of_a_turn_does_not_refuse_done(self):
        sess = live(self.tid); term.SESSIONS['run1'] = sess
        ws.record(self.s, self.tid, 'run1', 'input_needed', text='Want me to tidy the logs too?', source='judge')
        self.assertEqual(selfclose.blocked(self.s, self.tid, sess), '')

    def test_a_held_ask_left_behind_is_let_go_and_does_not_refuse_done(self):
        # the leftover hold refused every --done after the agent had moved on (the owner, 2026-10-30: "it should be able to close task")
        sess = live(self.tid); term.SESSIONS['run1'] = sess
        h = ws.hold(self.tid, 'run1', 'g1', ['q1'])
        try:
            self.assertEqual(selfclose.blocked(self.s, self.tid, sess), '')
            self.assertTrue(h['released'] and h['event'].is_set(), 'the hook holding it lets go')
        finally:
            with ws._HELD_LOCK: ws.HELD.pop('g1', None)


if __name__ == '__main__':
    unittest.main()


class NoReplyTests(Base):
    """`taskuary --done --no-reply` (the owner, 2026-10-08: "allow done with no reply"): told "not ours, don't answer", the agent
    could only finish with --done, which drafted the reply anyway. Saying none is owed is the agent's call; it is carried out."""
    def test_done_with_no_reply_drafts_none_and_puts_a_waiting_draft_down(self):
        term.SESSIONS['run1'] = live(self.tid)
        rid = self.s.add_review({'TaskId': self.tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Erin, on it.'})
        out = selfclose.declare(self.s, self.tid, 'not ours - the owner chose no reply', 'agent', no_reply=True)
        self.assertTrue(out.get('closed'))
        self.assertTrue(wrapup.finish.call_args.kwargs.get('no_reply'), 'finish is told no reply is owed')
        self.assertEqual(self.s.get_review(rid)['Status'], 'no_reply')
        self.assertIn('no reply is owed', ' '.join(c['Body'] for c in self.s.list_comments(self.tid)))

    def test_plain_done_still_drafts_as_before(self):
        term.SESSIONS['run1'] = live(self.tid)
        selfclose.declare(self.s, self.tid, 'fixed the cron', 'agent')
        self.assertFalse(wrapup.finish.call_args.kwargs.get('no_reply'))

    def test_the_agent_is_told_the_flag_exists(self):
        self.assertIn('--no-reply', selfclose.SEED_LINE)
