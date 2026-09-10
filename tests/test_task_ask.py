"""A task made by hand gets the ASK, not the email.

task_from_message stored BodyText[:1000] as the task's summary, so promoting a mail put the
greeting, the signature block, the confidentiality footer and the quoted thread underneath on
the task - and no checklist at all, because only the automatic road had ever asked for one
(the owner, 2026-09-10: "shouldn't the ai triage pull out just the task and that will show as
list as todo's").
"""
import json, unittest
from unittest import mock

from taskuary import ingest, triage
from taskuary.store import MemoryStore

MAIL = """Morning! Just wanted to check back in on this. We have a meeting this afternoon with
the HRs and I wanted to give them a heads up we'll be rolling it out.

Best,
J.D. Hancock
Vice President, Workforce Enhancement
Medical Facilities of America
2917 Penn Forest Blvd, Roanoke, VA 24018
P: 540.776.7576  C: 804.776.5487

This email and any files transmitted with it are confidential and intended solely for the use
of the individual or entity to whom they are addressed.

From: Uri Nussbaum <unussbaum@mfaheritage.net>
Sent: Wednesday, September 2, 2026 17:53
To: Hancock, J. D. <jdhancock@mfa.net>
"""


class ExtractTests(unittest.TestCase):
    def test_without_a_brain_the_footer_and_the_quoted_thread_are_still_gone(self):
        """The fallback must never be worse than the raw body it replaces."""
        out = triage.extract_ask({'Subject': 'Re: Hosting', 'BodyText': MAIL}, llm=None)
        self.assertIn('check back in on this', out['summary'])
        for gone in ('Penn Forest', 'confidential', 'From: Uri', '540.776.7576', 'J.D. Hancock'):
            self.assertNotIn(gone, out['summary'], gone)
        self.assertEqual(out['checklist'], [])

    def test_the_brain_supplies_the_summary_and_the_todos(self):
        llm = mock.Mock(return_value=json.dumps({
            'summary': 'J.D. Hancock is chasing the rollout of the interview screening tool.',
            'checklist': ['Confirm the rollout date', 'Send HR a heads-up before the meeting']}))
        out = triage.extract_ask({'Subject': 'Re: Hosting', 'BodyText': MAIL}, llm=llm)
        self.assertEqual(out['checklist'], ['Confirm the rollout date', 'Send HR a heads-up before the meeting'])
        self.assertIn('chasing the rollout', out['summary'])
        # the model reads the CLEANED body - the footer is not worth paying tokens for, and the
        # quoted thread is a different message's words
        sent = llm.call_args[0][1]
        self.assertNotIn('confidential', sent); self.assertNotIn('From: Uri', sent)

    def test_a_fenced_answer_is_still_read(self):
        llm = mock.Mock(return_value='```json\n{"summary": "s", "checklist": ["a"]}\n```')
        self.assertEqual(triage.extract_ask({'BodyText': 'x'}, llm=llm)['checklist'], ['a'])

    def test_a_broken_brain_never_breaks_the_promote(self):
        """Turning a message into a task must not depend on a model answering."""
        out = triage.extract_ask({'BodyText': MAIL}, llm=mock.Mock(side_effect=RuntimeError('502')))
        self.assertIn('check back in', out['summary']); self.assertEqual(out['checklist'], [])

    def test_a_model_that_answers_with_junk_falls_back_too(self):
        out = triage.extract_ask({'BodyText': MAIL}, llm=mock.Mock(return_value='sure thing!'))
        self.assertIn('check back in', out['summary'])


class PromoteTests(unittest.TestCase):
    def _msg(self, s):
        return s.add_message({'Channel': 'email', 'FromEmail': 'jdhancock@mfa.net', 'FromName': 'J. D. Hancock',
                              'Subject': 'Re: Hosting for Interview Screening Tool', 'BodyText': MAIL,
                              'SentAt': '2026-09-10T09:00:00'})

    def test_promoting_a_message_files_the_ask_and_the_checklist(self):
        s = MemoryStore()
        mid = self._msg(s)
        brain = mock.Mock(return_value=json.dumps({'summary': 'Hancock is chasing the rollout.',
                                                   'checklist': ['Confirm the rollout date']}))
        with mock.patch('taskuary.llm.build_llm', return_value=brain):
            tid = ingest.task_from_message(s, mid, 'owner')
        t = s.get_task(tid)
        self.assertEqual(t['Summary'], 'Hancock is chasing the rollout.')
        self.assertNotIn('confidential', t['Summary'])
        self.assertEqual([i['text'] for i in s.task_checklist(tid)], ['Confirm the rollout date'])

    def test_promoting_with_no_brain_still_stores_the_sender_words_only(self):
        s = MemoryStore()
        mid = self._msg(s)
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            tid = ingest.task_from_message(s, mid, 'owner')
        summary = s.get_task(tid)['Summary']
        self.assertIn('check back in on this', summary)
        self.assertNotIn('Penn Forest', summary)          # the old code stored all of this
        self.assertNotIn('From: Uri', summary)


class ContractTests(unittest.TestCase):
    """The output SHAPE survives a TRIAGE.md that never mentions it.

    A generated document (UpdatedBy=histgen) replaces INTENT_SYSTEM wholesale. This install's
    describes how to judge at length and never says title/summary/checklist, so the model
    answered intent/kind/why only - and ingest fell back to routing.draft_task_fields, whose
    summary is the raw body sliced at 1000 characters. That is why a task's ask was the whole
    email, footer and all, with no todos (the owner, 2026-09-10).
    """

    DOC = ('Decide whether each message is a task, a reply or fyi. Weigh who sent it and '
           'whether anyone else has answered. Escalate anything from a regulator.') * 3

    def _system_for(self, doc):
        seen = {}
        def fake(system, user, **kw):
            seen['sys'] = system
            return json.dumps({'intent': 'task', 'kind': 'coding', 'why': 'asks for a change'})
        triage.classify_intent({'subject': 'Re: Hosting', 'body': 'check back in'}, llm=fake, system=doc)
        return seen['sys']

    def test_a_document_that_forgets_the_shape_gets_it_back(self):
        sys = self._system_for(self.DOC)
        self.assertIn(triage.TASK_FIELDS, sys)
        self.assertIn('checklist', sys)
        self.assertIn(self.DOC[:60], sys)              # ...without displacing the owner's judgement

    def test_a_document_that_states_the_shape_is_left_alone(self):
        """No nagging: a doc already asking for these must not get a second copy."""
        doc = self.DOC + '\nAlso answer "summary" and a "checklist" of outcomes.'
        sys = self._system_for(doc)
        self.assertNotIn('WHATEVER ELSE YOU ANSWER', sys)

    def test_the_shipped_prompt_carries_it_once(self):
        self.assertIn(triage.TASK_FIELDS, triage.INTENT_SYSTEM)
        self.assertEqual(self._system_for(None).count('one distinct requested outcome each'), 1)


class BackfillTests(unittest.TestCase):
    """Re-deriving the ask for rows already on the board. It REWRITES the owner's tasks, so the
    guards matter more than the rewrite: dry-run by default, only where the summary is literally
    a copy of the message, and never over a checklist they may have ticked."""

    def _task(self, s, summary, body=MAIL, closed=False):
        mid = s.add_message({'Channel': 'email', 'FromEmail': 'jdhancock@mfa.net', 'Subject': 'Re: Hosting',
                             'BodyText': body, 'SentAt': '2026-09-10T09:00:00'})
        tid = s.create_task({'Title': 'Hosting', 'Summary': summary, 'Kind': 'coding',
                             **({'Status': 'done'} if closed else {})}, 'owner')
        s.attach_message(mid, tid)
        return tid

    def _brain(self):
        return mock.Mock(return_value=json.dumps({'summary': 'Hancock is chasing the rollout.',
                                                  'checklist': ['Confirm the rollout date']}))

    def test_it_finds_the_raw_body_slice_and_rewrites_it(self):
        s = MemoryStore()
        tid = self._task(s, MAIL[:1000])                       # the exact fingerprint
        rows = ingest.backfill_asks(s, self._brain(), dry_run=False)
        me = next(r for r in rows if r['task_id'] == tid)
        self.assertEqual(me['action'], 'rewrote')
        self.assertEqual(s.get_task(tid)['Summary'], 'Hancock is chasing the rollout.')
        self.assertEqual([i['text'] for i in s.task_checklist(tid)], ['Confirm the rollout date'])

    def test_dry_run_is_the_default_and_writes_nothing(self):
        s = MemoryStore()
        tid = self._task(s, MAIL[:1000])
        rows = ingest.backfill_asks(s, self._brain())
        self.assertEqual(next(r for r in rows if r['task_id'] == tid)['action'], 'would rewrite')
        self.assertEqual(s.get_task(tid)['Summary'], MAIL[:1000])      # untouched
        self.assertEqual(s.task_checklist(tid), [])

    def test_a_real_summary_is_left_alone(self):
        """The one thing this must never do is overwrite a good ask."""
        s = MemoryStore()
        tid = self._task(s, 'Hancock is chasing the interview screening rollout before an HR meeting.')
        r = next(x for x in ingest.backfill_asks(s, self._brain(), dry_run=False) if x['task_id'] == tid)
        self.assertEqual(r['action'], 'skipped'); self.assertIn('not a copy', r['why'])

    def test_an_existing_checklist_is_never_replaced(self):
        """They may have ticked items off it."""
        s = MemoryStore()
        tid = self._task(s, MAIL[:1000])
        s.set_task_checklist(tid, ['something the owner kept'], 'owner')
        r = next(x for x in ingest.backfill_asks(s, self._brain(), dry_run=False) if x['task_id'] == tid)
        self.assertEqual(r['action'], 'skipped'); self.assertIn('already has a checklist', r['why'])
        self.assertEqual([i['text'] for i in s.task_checklist(tid)], ['something the owner kept'])

    def test_closed_tasks_are_left_out_unless_asked_for(self):
        s = MemoryStore()
        tid = self._task(s, MAIL[:1000], closed=True)
        self.assertNotIn(tid, [r['task_id'] for r in ingest.backfill_asks(s, self._brain())])
        self.assertIn(tid, [r['task_id'] for r in ingest.backfill_asks(s, self._brain(), include_closed=True)])

    def test_a_task_with_no_message_cannot_be_re_read(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'typed by hand', 'Summary': 'x', 'Kind': 'task'}, 'owner')
        r = next(x for x in ingest.backfill_asks(s, self._brain()) if x['task_id'] == tid)
        self.assertEqual(r['action'], 'skipped'); self.assertIn('no source message', r['why'])

    def test_with_no_brain_it_still_strips_the_footer(self):
        s = MemoryStore()
        tid = self._task(s, MAIL[:1000])
        ingest.backfill_asks(s, None, dry_run=False)
        summary = s.get_task(tid)['Summary']
        self.assertIn('check back in on this', summary)
        self.assertNotIn('Penn Forest', summary); self.assertNotIn('From: Uri', summary)

    def test_the_prefix_test_is_what_identifies_a_copy(self):
        self.assertTrue(ingest._is_raw_body(MAIL[:1000], MAIL))
        self.assertTrue(ingest._is_raw_body(MAIL, MAIL))                     # short mail copied whole
        self.assertFalse(ingest._is_raw_body('A two sentence summary of it.', MAIL))
        self.assertFalse(ingest._is_raw_body('', MAIL))
        self.assertFalse(ingest._is_raw_body(MAIL[:1000], ''))

    def test_limit_counts_dry_run_hits_too(self):
        """A limit that only counted real writes ran the whole board in a dry run - on a paid
        brain that is a bill, not just a slow command."""
        s = MemoryStore()
        for _ in range(4): self._task(s, MAIL[:1000])
        rows = ingest.backfill_asks(s, self._brain(), dry_run=True, limit=2)
        self.assertEqual(len([r for r in rows if r['action'] == 'would rewrite']), 2)


if __name__ == '__main__': unittest.main()
