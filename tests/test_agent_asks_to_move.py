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
        self.assertIn('elsewhere', wrapup.TRANSCRIPT_SYSTEM)
        self.assertIn('never nothing_to_do', wrapup.TRANSCRIPT_SYSTEM)
        s = MemoryStore(); tid, _ = coding_task(s)
        llm = mock.Mock(return_value=json.dumps(MOVE))
        with mock.patch('taskuary.llm.build_llm', return_value=llm):
            rep = wrapup.report_from_transcript(s, tid, 'searched for the export job: not in this repo')
        self.assertEqual((rep['outcome'], rep['elsewhere']), ('elsewhere', 'northwind/portal'))
        self.assertTrue(wrapup.moves(rep))

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

    def test_a_real_done_still_says_closed(self):
        s = MemoryStore(); tid, _ = coding_task(s)
        selfclose.forget(tid)
        def wrap(store, t, **kw):
            store.update_task(t, {'Status': 'done'}, 'coding'); return {'wrap': 'done', 'drafting': False}
        with mock.patch('taskuary.wrapup.wrap', side_effect=wrap):
            self.assertTrue(selfclose.declare(s, tid, 'fixed the export', 'coding')['closed'])
        self.assertTrue(any(c['Body'].startswith('The agent closed this itself: fixed the export') for c in s.list_comments(tid)))
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
