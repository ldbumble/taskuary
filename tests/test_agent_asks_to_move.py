"""Work in another repository is a question, not "nothing to do".

A coding agent was started in the wrong repository. It searched, found the job was not there, and closed the task
"Nothing to do. It's handled" - "not a <repo> problem, it has to be diagnosed in the repo that runs that job". The work was
real; only its place was wrong (the owner, 2026-10-27: "coding agent should be able to at least ask can I change repos").

Pinned here: CODING.md tells the agent to ask, naming the repository it thinks it is; and an ending that says the work lives
elsewhere is read by the report's model as `elsewhere` - never done, never a reply - and leaves the task open, held on where
the code is, so the row's own Change where the code is moves it and starts the agent there.
"""
import json, tempfile, unittest
from pathlib import Path
from unittest import mock

import taskuary
from taskuary import funnel, selfclose, wrapup, store as store_mod
from taskuary.store import MemoryStore, SQLiteStore

CODING = (Path(taskuary.__file__).parent / 'templates' / 'coding.md').read_text(encoding='utf-8')
MOVE = {'determination': 'the nightly export job is not in this repository', 'actions': 'nothing changed',
        'summary': 'The export job lives in northwind/portal, not here.', 'outcome': 'elsewhere', 'elsewhere': 'northwind/portal'}


def coding_task(s, sender='erin@northwind.example', repo='northwind/ledger'):
    tid = s.create_task({'Title': 'Nightly export failed', 'Kind': 'coding', 'Status': 'in_progress', 'Tags': f'repo:{repo}'}, 't')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'x1', 'Channel': 'email', 'Subject': 'Nightly export failed',
                         'FromEmail': sender, 'FromName': 'Erin Blake', 'SentAt': '2026-10-27 08:00:00',
                         'BodyText': 'The nightly export failed again - can you look?', 'Status': 'routed', 'SenderClass': 'person'})
    return tid, mid


def tags(s, tid): return str(s.get_task(tid).get('Tags') or '')


class ReportReadsTheMoveTests(unittest.TestCase):
    def test_the_report_model_is_asked_for_elsewhere_and_its_answer_is_kept(self):
        """A run that ended without the agent saying how (the owner's Stop, a killed CLI): the transcript is all there is."""
        self.assertIn('elsewhere', wrapup.OUTCOME_ASK)
        s = MemoryStore(); tid, _ = coding_task(s)
        llm = mock.Mock(return_value=json.dumps(MOVE))
        with mock.patch('taskuary.llm.build_llm', return_value=llm):
            rep = wrapup.report_from_transcript(s, tid, 'searched for the export job: not in this repo')
        self.assertEqual((rep['outcome'], rep['elsewhere']), ('elsewhere', 'northwind/portal'))
        self.assertTrue(wrapup.moves(rep))
        self.assertIn(wrapup.OUTCOME_ASK, llm.call_args[0][0])

    def test_an_agent_that_said_done_is_not_second_guessed(self):
        """The owner's rule (2026-11-10, "no second voice drafts, judges or edits for it"): `taskuary --done` is the agent saying it
        finished the work here. The report's model writes the prose and is never asked how the run ended - nor heard if it says."""
        s = MemoryStore(); tid, _ = coding_task(s)
        llm = mock.Mock(return_value=json.dumps(MOVE))
        with mock.patch('taskuary.llm.build_llm', return_value=llm):
            rep = wrapup.report_from_transcript(s, tid, 'fixed the export', said=True)
        self.assertFalse(wrapup.moves(rep)); self.assertNotIn('outcome', rep)
        self.assertNotIn('did_work', llm.call_args[0][0])
        self.assertEqual(rep['summary'], MOVE['summary'])                 # ...its prose is still the report

    def test_the_wrap_reads_the_agents_done_off_its_run(self):
        """Which run said it: the Finished event its `--done` records (selfclose._finished) - a run with none was not said."""
        from types import SimpleNamespace
        from taskuary import terminal as term, workerstate as ws
        s = MemoryStore(); tid, _ = coding_task(s)
        saw = []
        def rep(*a, **k): saw.append(k.get('said')); return {'summary': 'fixed'}
        sess = SimpleNamespace(sid='run1', alive=True, task_id=tid, witness=SimpleNamespace(said='Fixed it.'))
        keep = dict(term.SESSIONS); self.addCleanup(lambda: (term.SESSIONS.clear(), term.SESSIONS.update(keep)))
        with mock.patch.object(term, 'transcript_for', return_value=('fixed the export', 'coding', 'run1')), \
             mock.patch.object(term, 'close', return_value=True), mock.patch.object(wrapup, 'report_from_transcript', side_effect=rep), \
             mock.patch.object(wrapup, 'finish', return_value={}), mock.patch('taskuary.proposals.collect', return_value=[]), \
             mock.patch('taskuary.playbooks.draft', return_value=None), mock.patch('taskuary.handbook.enabled', return_value=False):
            term.SESSIONS['run1'] = sess
            wrapup.wrap(s, tid, close=False, actor='owner')
            sess.sid = 'run2'; term.SESSIONS.clear(); term.SESSIONS['run2'] = sess
            ws.record(s, tid, 'run2', 'finished', text='Fixed it.', source='cli')
            with mock.patch.object(term, 'transcript_for', return_value=('fixed the export', 'coding', 'run2')):
                wrapup.wrap(s, tid, close=False, actor='coding')
        self.assertEqual(saw, [False, True])

    def test_other_outcomes_carry_no_move(self):
        s = MemoryStore(); tid, _ = coding_task(s)
        llm = mock.Mock(return_value=json.dumps({**MOVE, 'outcome': 'did_work', 'elsewhere': ''}))
        with mock.patch('taskuary.llm.build_llm', return_value=llm):
            self.assertFalse(wrapup.moves(wrapup.report_from_transcript(s, tid, 'fixed it')))


class FinishAsksTests(unittest.TestCase):
    def test_a_move_is_not_done_and_drafts_no_reply_even_for_a_person(self):
        s = MemoryStore(); tid, _ = coding_task(s)
        with mock.patch('taskuary.responder.write_draft') as wd:
            out = wrapup.finish(s, tid, MOVE, None, 'coding')
        wd.assert_not_called()
        self.assertEqual((out['drafting'], out['asks']), (False, 'repo'))
        self.assertEqual((s.get_task(tid)['Status'], s.list_reviews('pending')), ('open', []))
        self.assertTrue(funnel.held_for_repo(s.get_task(tid)))
        said = [c['Body'] for c in s.list_comments(tid)]
        self.assertTrue(any('not in northwind/ledger' in b and 'northwind/portal' in b and 'Move it there?' in b for b in said), said)

    def test_no_guess_asks_which_code(self):
        s = MemoryStore(); tid, _ = coding_task(s)
        self.assertIn('Which code should it move to?', wrapup.move_question(s, tid, {**MOVE, 'elsewhere': ''}))

    def test_the_owners_mark_done_still_closes(self):
        s = MemoryStore(); tid, _ = coding_task(s, sender='alerts@vendor.example')
        with mock.patch('taskuary.responder.write_draft', return_value='x'):
            wrapup.finish(s, tid, MOVE, None, 'owner', owner_done=True, no_reply=True)
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        self.assertFalse(funnel.held_for_repo(s.get_task(tid)))

    def test_choosing_the_code_answers_it(self):
        s = MemoryStore(); tid, _ = coding_task(s)
        wrapup.finish(s, tid, MOVE, None, 'coding')
        s.tag_task(tid, funnel.HELD_REPO, False, 'owner')          # what set_task_repo and a session's start do
        self.assertFalse(funnel.held_for_repo(s.get_task(tid)))

    def test_the_task_says_the_agent_asks_to_move_once_it_ran(self):
        s = MemoryStore(); tid, _ = coding_task(s)
        s.add_transcript(tid, 'sid1', 'searched: the export job is not here', agent='coding')
        wrapup.finish(s, tid, MOVE, None, 'coding')
        st = funnel.idle_state(s, tid)
        self.assertEqual(st['kind'], 'held')
        self.assertIn('asks where to move it', st['line']); self.assertNotIn('before', st['line'])


class SelfCloseTests(unittest.TestCase):
    def test_a_done_that_turns_out_to_be_a_move_does_not_say_closed(self):
        s = MemoryStore(); tid, _ = coding_task(s)
        selfclose.forget(tid)
        def wrap(store, t, **kw): return {'wrap': 'done', **wrapup.finish(store, t, MOVE, None, 'coding')}
        with mock.patch('taskuary.wrapup.wrap', side_effect=wrap):
            out = selfclose.declare(s, tid, 'Not a ledger problem - it has to be diagnosed in the repo that runs the job.', 'coding')
        self.assertFalse(out['closed']); self.assertEqual(out['asks'], 'repo')
        self.assertEqual(s.get_task(tid)['Status'], 'open')
        said = [c['Body'] for c in s.list_comments(tid)]
        self.assertFalse(any(b.startswith('The agent closed this itself') for b in said), said)
        self.assertTrue(any(b.startswith(selfclose.DONE_SAID) for b in said))
        # ...and once moved, a later --done may close it
        with selfclose._LOCK: self.assertNotIn(tid, selfclose._DONE)

    def test_a_real_done_says_finished_and_leaves_the_close_to_the_owner(self):
        s = MemoryStore(); tid, _ = coding_task(s)
        selfclose.forget(tid)
        def wrap(store, t, **kw):
            assert kw['close'] is False; return {'wrap': 'done', 'drafting': False}
        with mock.patch('taskuary.wrapup.wrap', side_effect=wrap):
            out = selfclose.declare(s, tid, 'fixed the export', 'coding')
        self.assertTrue(out['ended']); self.assertFalse(out['closed']); self.assertNotIn(s.get_task(tid)['Status'], ('done', 'dropped'))
        self.assertTrue(any(c['Body'].startswith(selfclose.DONE_SAID + 'fixed the export') for c in s.list_comments(tid)))
        selfclose.forget(tid)


class SeedTrimTests(unittest.TestCase):
    """CODING.md growing put the worst-case seed over SEED_CEILING, and the trim's ' RULES (' never matched the blank line
    paragraphs() puts there: the prompt lost its END - how to finish and reply - instead of the ask."""
    def test_an_over_ceiling_seed_cuts_the_ask_and_keeps_its_end_and_the_true_size(self):
        from taskuary import terminal
        s = MemoryStore(); s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        tid = s.create_task({'Title': 'long ask', 'Kind': 'coding'}, 'o')
        s.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': 'b1', 'FromName': 'Erin', 'FromEmail': 'erin@northwind.example',
                       'Subject': 'Importer', 'SentAt': '2026-10-27 08:00:00', 'BodyText': 'z' * 200000})
        with mock.patch('taskuary.origin.of_task', new=lambda *a, **k: ('owner', 'test')), mock.patch.object(terminal, 'SEED_CEILING', 20000):
            seed = terminal.seed_text(s, tid)
        self.assertLessEqual(len(seed), 20000)
        self.assertNotIn('prompt truncated', seed)
        self.assertIn('of 200,000 characters', seed)
        self.assertIn(selfclose.SEED_LINE, seed)                    # the end: how to finish and reply, whole
        self.assertIn('## The work is in another repository'.lstrip('# '), seed)


class CodingMdTests(unittest.TestCase):
    def test_coding_md_says_ask_and_name_the_repo(self):
        sec = CODING.split('## The work is in another repository', 1)[1].split('##', 1)[0]
        for w in ('NOT "nothing to do"', 'no `taskuary --done`', 'naming where you think it is', 'Move it there?',
                  'Change where the code is', 'and wait'):
            self.assertIn(w, sec, w)
        self.assertIn(store_mod._ELSEWHERE_AT + store_mod._ELSEWHERE_NOW, CODING)

    def test_an_edited_copy_takes_the_section_once(self):
        path = Path(tempfile.mkdtemp()) / 'taskuary.db'
        s = SQLiteStore(str(path))
        s.save_doc('coding', 'MY RULE: Erin reviews every change.\n' + store_mod._ELSEWHERE_AT + '\n## Ask first\nmine', 'owner')
        s.cx.execute("DELETE FROM setting WHERE Name='coding_asks_to_move'"); s.cx.commit()
        c = SQLiteStore(str(path)).get_doc('coding')
        self.assertIn(store_mod._ELSEWHERE_AT + store_mod._ELSEWHERE_NOW, c)
        self.assertIn('MY RULE: Erin reviews every change.', c); self.assertEqual(c.count('## The work is in another repository'), 1)
        self.assertEqual(SQLiteStore(str(path)).get_doc('coding'), c)


if __name__ == '__main__': unittest.main()
