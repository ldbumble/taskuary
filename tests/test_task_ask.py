"""A task gets the ASK, not the email - promoted by hand or made by triage.

task_from_message stored BodyText[:1000] as the task's summary, so promoting a mail put the
greeting, the signature block, the confidentiality footer and the quoted thread underneath on
the task - and no checklist at all, because only the automatic road had ever asked for one
(the owner, 2026-09-10: "shouldn't the ai triage pull out just the task and that will show as
list as todo's").

The automatic road kept the raw body a while longer: a verdict that names no summary of its own
(reply_only names none) fell through to draft_task_fields, which stored body[:1000] - so 5,998
characters of quoted thread landed on the task whose ask was one sentence (the owner, 2026-09-14:
"why is the whole email showing up not the specific task?").
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


# The same mail without the legal footer that happened to cut the last one short: a signature, and
# under it the forwarded chain. Nothing in the fallback knew where the sender stopped writing, so
# the whole chain - every header, both signatures - went on the card as the ask (TQ-0665, 2026-09-21).
FORWARDED = """Uri,

Can you send me the link on the 2027 budgets?

Thanks,

Brad West
Medical Facilities of America
VP Marketing and Business Development
(540) 776-7588 Office
Brad.west@mfa.example
www.lifeworksrehab.example

From: Yeatts, Michael L. <Michael.Yeatts@MFA.EXAMPLE>
Sent: Thursday, September 17, 2026 2:07 PM
To: West, Brad <Brad.West@MFA.EXAMPLE>
Subject: Fw: 2027 Budgets

Mike Yeatts
Vice President
"""


class AutomaticRoadTests(unittest.TestCase):
    def test_the_triaged_summary_is_the_ask_not_the_whole_thread(self):
        from taskuary.routing import draft_task_fields
        out = draft_task_fields({'subject': 'Re: Hosting', 'body': MAIL})
        self.assertIn('check back in on this', out['summary'])
        for gone in ('Penn Forest', 'confidential', 'From: Uri', '540.776.7576'):
            self.assertNotIn(gone, out['summary'], gone)

    def test_the_forwarded_chain_under_the_ask_is_not_the_ask(self):
        from taskuary.routing import draft_task_fields
        out = draft_task_fields({'subject': 'FW: 2027 Budgets', 'body': FORWARDED})
        self.assertIn('2027 budgets', out['summary'].lower())
        for gone in ('From: Yeatts', 'Vice President', 'lifeworksrehab', '776-7588'):
            self.assertNotIn(gone, out['summary'], gone)

    def test_a_mail_that_is_only_the_senders_own_words_is_kept_whole(self):
        """The cut is for what sits UNDER the ask - it must never eat a message that has no chain."""
        from taskuary.routing import draft_task_fields
        body = 'Morning - the payroll export failed again overnight. Same KeyError as last week.'
        self.assertEqual(draft_task_fields({'subject': 'Payroll export', 'body': body})['summary'], body)

    def test_a_reply_only_verdict_carries_the_ask_too(self):
        """reply_only lands as a row of its own, so it is asked for a title and a summary like any
        other - it used to answer intent/why alone and fall through to the raw body.

        The shape is asked for on EVERY verdict now (2026-09-16), which is strictly stronger: an fyi
        and a report are rows the owner reads too, and a mail header is not a sentence."""
        self.assertIn('WHATEVER the verdict', triage.TASK_FIELDS)
        self.assertIn('"title"', triage.TASK_FIELDS)
        self.assertIn('"summary"', triage.TASK_FIELDS)
        s = MemoryStore()
        llm = mock.Mock(return_value=json.dumps({
            'intent': 'reply_only', 'why': 'Dvora asks which documentation you meant',
            'title': 'Answer Dvora on the EPR documentation',
            'summary': 'Dvora Cohen asks which documentation you were referring to; she says the PAM and Review PDFs are all that is in use.'}))
        with mock.patch.object(ingest, '_spawn'):
            r = ingest.ingest_message(s, {'external_id': 'd', 'channel': 'email', 'from_email': 'dcohen@hrtgcs.example',
                                          'conversation_id': 'c-epr', 'subject': 'RE: Mindy Gorelick Annual EPR- AUG 2026',
                                          'body': MAIL, 'sent_at': '2026-09-14 09:02:00'}, llm=llm)
        task = s.get_task(r['task_id'])
        self.assertEqual(task['Kind'], 'reply')
        self.assertEqual(task['Title'], 'Answer Dvora on the EPR documentation')
        self.assertIn('which documentation you were referring to', task['Summary'])
        for gone in ('Penn Forest', 'confidential', 'From: Uri'):
            self.assertNotIn(gone, task['Summary'], gone)

    def test_an_fyi_keeps_the_verdict_s_own_line_although_it_has_no_task(self):
        """The whole point of asking for a title on every verdict: an fyi never becomes a task, so
        there was nowhere to keep the one sentence triage had already written, and the rail fell
        back to the mail header - "MFA - PCC Report Error Check - 0 rows returned for period ending
        09/15" over a row whose job is to say what a thing is (the owner, 2026-09-16)."""
        from taskuary import funnel
        s = MemoryStore()
        llm = mock.Mock(return_value=json.dumps({
            'intent': 'fyi', 'why': 'a scheduled error report; nothing is asked',
            'title': 'Nightly PCC error check returned no rows',
            'summary': 'The scheduled PCC error check ran and returned nothing for the period ending 09/15.'}))
        with mock.patch.object(ingest, '_spawn'):
            r = ingest.ingest_message(s, {'external_id': 'pcc', 'channel': 'email', 'from_email': 'rrdbreports@mfa.example',
                                          'conversation_id': 'c-pcc', 'from_name': 'RRDB Reports',
                                          'subject': 'MFA - PCC Report Error Check - 0 rows returned for period ending 09/15',
                                          'body': 'Rows returned: 0', 'sent_at': '2026-09-15 07:10:00'}, llm=llm)
        self.assertEqual(r['status'], 'filed')
        self.assertIsNone(r['task_id'])                                     # an fyi is not work...
        row = s.get_message(r['message_id'])
        self.assertEqual(row['TriageTitle'], 'Nightly PCC error check returned no rows')   # ...and still has a line
        # ...which is what the work rail actually reads, in place of the header it arrived under
        self.assertEqual(funnel.says(dict(row) | {'Title': None}), 'Nightly PCC error check returned no rows')

    def test_a_verdict_that_names_no_title_leaves_the_row_as_it_was(self):
        """A policy ignore and a failed call name nothing, and neither may invent a line."""
        from taskuary import funnel
        s = MemoryStore()
        llm = mock.Mock(return_value=json.dumps({'intent': 'fyi', 'why': 'a newsletter'}))
        with mock.patch.object(ingest, '_spawn'):
            r = ingest.ingest_message(s, {'external_id': 'n', 'channel': 'email', 'from_email': 'news@vendor.example',
                                          'conversation_id': 'c-n', 'subject': 'Our October newsletter',
                                          'body': 'Read on.', 'sent_at': '2026-09-15 07:10:00'}, llm=llm)
        row = s.get_message(r['message_id'])
        self.assertIsNone(row['TriageTitle'])
        self.assertEqual(funnel.says(dict(row) | {'Title': None}), 'Our October newsletter')

    def test_a_task_keeps_its_own_title_over_a_follow_up_s(self):
        """The row for a task is about the JOB. A follow-up's own verdict line describes only the
        latest thing said on it, so Title outranks TriageTitle and the rail does not rename a task
        every time somebody writes to it."""
        from taskuary import funnel
        self.assertEqual(funnel.says({'Title': 'Fix the census sync', 'TriageTitle': 'Marcus adds a detail',
                                      'Subject': 'RE: RE: sync'}), 'Fix the census sync')

    def test_a_verdict_that_names_its_own_summary_still_wins(self):
        """The fallback never overrides the brain - it is only what stands in for it."""
        s = MemoryStore()
        llm = mock.Mock(return_value=json.dumps({'intent': 'task', 'kind': 'task', 'why': 'an ask',
                                                 'title': 'Roll out the screening tool',
                                                 'summary': 'J.D. is chasing the rollout.'}))
        with mock.patch.object(ingest, '_spawn'):
            r = ingest.ingest_message(s, {'external_id': 'x', 'channel': 'email', 'from_email': 'jd@mfa.net',
                                          'conversation_id': 'c1', 'subject': 'Re: Hosting', 'body': MAIL,
                                          'sent_at': '2026-09-14 09:00:00'}, llm=llm)
        self.assertEqual(s.get_task(r['task_id'])['Summary'], 'J.D. is chasing the rollout.')


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

    def test_the_shape_is_the_last_thing_the_model_reads(self):
        """Appended to the DOCUMENT, it was then buried under the soul, the evidence, the playbooks
        and the repositories, while the document's own first line named a contract without title or
        summary. On a long forwarded mail the model answered that line and dropped both - three
        times in eight replays of TQ-0665 - and the card fell back to the raw body. The shape is not
        a judgement, so it can sit after everything: it is the last thing asked for."""
        seen = {}
        def fake(system, user, **kw):
            seen['sys'] = system
            return json.dumps({'intent': 'task', 'kind': 'coding', 'why': 'asks for a change'})
        triage.classify_intent({'subject': 'Re: Hosting', 'body': 'check back in'}, llm=fake, system=self.DOC,
                               soul='The owner runs IS at a care provider.', notes=['2026-09-01 - not ours'],
                               repos=[{'repo': 'acme/app', 'about': 'the portal'}], playbooks='- pto: PTO requests')
        self.assertTrue(seen['sys'].rstrip().endswith(triage.TASK_FIELDS.rstrip()), seen['sys'][-400:])

    def test_the_shape_is_asked_for_under_the_message_too(self):
        """Moving it to the end of the instructions was not enough on a long mail - the model still
        dropped the pair in two of eight replays. Asked again under the body, where the reading
        actually ends, sixteen of sixteen carried it. The payload stays strictly JSON: it has
        readers (the scrubber, the tests, the Triage tab), so the ask is a field, not a postscript."""
        seen = {}
        def fake(system, user, **kw):
            seen['user'] = json.loads(user)
            return json.dumps({'intent': 'fyi', 'why': 'a newsletter'})
        triage.classify_intent({'subject': 'x', 'body': 'check back in'}, llm=fake, system=self.DOC)
        self.assertEqual(list(seen['user'])[-1], 'answer')                     # the last thing under the body
        self.assertIn('"summary"', seen['user']['answer'])

    def test_a_document_that_states_the_shape_is_asked_nothing_twice(self):
        seen = {}
        def fake(system, user, **kw):
            seen['user'] = json.loads(user)
            return json.dumps({'intent': 'fyi', 'why': 'a newsletter'})
        triage.classify_intent({'subject': 'x', 'body': 'check back in'}, llm=fake,
                               system=self.DOC + '\nAlso answer "summary" and a "checklist" of outcomes.')
        self.assertNotIn('answer', seen['user'])

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
