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
J.D. Ellis
Vice President, Workforce Enhancement
Northwind
100 Harbor Way, Springfield
P: 540.776.7576  C: 804.776.5487

This email and any files transmitted with it are confidential and intended solely for the use
of the individual or entity to whom they are addressed.

From: Alex Doyle <owner@northwind.example>
Sent: Wednesday, September 2, 2026 17:53
To: Ellis, J. D. <jellis@northwind.example>
"""


# The same mail without the legal footer that happened to cut the last one short: a signature, and
# under it the forwarded chain. Nothing in the fallback knew where the sender stopped writing, so
# the whole chain - every header, both signatures - went on the card as the ask (TQ-0665, 2026-09-21).
FORWARDED = """Alex,

Can you send me the link on the 2027 budgets?

Thanks,

Ray Colton
Northwind
VP Marketing and Business Development
(540) 776-7588 Office
Ray.west@northwind.example
www.northwindrehab.example

From: Barnes, Michael L. <Michael.Barnes@NORTHWIND.EXAMPLE>
Sent: Thursday, September 17, 2026 2:07 PM
To: Colton, Ray <Ray.West@NORTHWIND.EXAMPLE>
Subject: Fw: 2027 Budgets

Peter Barnes
Vice President
"""


class AutomaticRoadTests(unittest.TestCase):
    def test_the_triaged_summary_is_the_ask_not_the_whole_thread(self):
        from taskuary.routing import draft_task_fields
        out = draft_task_fields({'subject': 'Re: Hosting', 'body': MAIL})
        self.assertIn('check back in on this', out['summary'])
        # the quoted chain is a different message; the sign-off and footer are the sender's own text since 2026-10-11
        # (no word list decides where a sender stopped writing) - a verdict's summary is what replaces them
        self.assertNotIn('From: Alex', out['summary'])

    def test_the_forwarded_chain_under_the_ask_is_not_the_ask(self):
        from taskuary.routing import draft_task_fields
        out = draft_task_fields({'subject': 'FW: 2027 Budgets', 'body': FORWARDED})
        self.assertIn('2027 budgets', out['summary'].lower())
        for gone in ('From: Barnes', 'Vice President', 'northwindrehab', '776-7588'):
            self.assertNotIn(gone, out['summary'], gone)

    def test_a_mail_that_is_only_the_senders_own_words_is_kept_whole(self):
        """The cut is for what sits UNDER the ask - it must never eat a message that has no chain."""
        from taskuary.routing import draft_task_fields
        body = 'Morning - the payroll export failed again overnight. Same KeyError as last week.'
        self.assertEqual(draft_task_fields({'subject': 'Payroll export', 'body': body})['summary'], body)

    def test_a_reply_only_verdict_names_the_row_and_the_ask_is_the_senders_own_words(self):
        """reply_only lands as a row of its own under the verdict's title. Triage writes no summary (2026-11-23): the task's ask is
        what the sender typed, never the quoted chain under it."""
        s = MemoryStore()
        llm = mock.Mock(return_value=json.dumps({'intent': 'reply_only', 'why': 'Paula asks which documentation you meant',
                                                 'title': 'Answer Paula on the EPR documentation'}))
        with mock.patch.object(ingest, '_spawn'):
            r = ingest.ingest_message(s, {'external_id': 'd', 'channel': 'email', 'from_email': 'pvance@vendor.example',
                                          'conversation_id': 'c-epr', 'subject': 'RE: Erin Blake Annual EPR- AUG 2026',
                                          'body': MAIL, 'sent_at': '2026-09-14 09:02:00'}, llm=llm)
        task = s.get_task(r['task_id'])
        self.assertEqual(task['Kind'], 'reply')
        self.assertEqual(task['Title'], 'Answer Paula on the EPR documentation')
        self.assertIn('check back in on this', task['Summary'])
        self.assertNotIn('From: Alex', task['Summary'])

    def test_an_fyi_keeps_the_verdict_s_own_line_although_it_has_no_task(self):
        """The whole point of asking for a title on every verdict: an fyi never becomes a task, so
        there was nowhere to keep the one sentence triage had already written, and the rail fell
        back to the mail header - "Northwind - PCC Report Error Check - 0 rows returned for period ending
        09/15" over a row whose job is to say what a thing is (the owner, 2026-09-16)."""
        from taskuary import funnel
        s = MemoryStore()
        llm = mock.Mock(return_value=json.dumps({
            'intent': 'fyi', 'why': 'a scheduled error report; nothing is asked',
            'title': 'Nightly PCC error check returned no rows',
            'summary': 'The scheduled PCC error check ran and returned nothing for the period ending 09/15.'}))
        with mock.patch.object(ingest, '_spawn'):
            r = ingest.ingest_message(s, {'external_id': 'pcc', 'channel': 'email', 'from_email': 'rrdbreports@northwind.example',
                                          'conversation_id': 'c-pcc', 'from_name': 'RRDB Reports',
                                          'subject': 'Northwind - PCC Report Error Check - 0 rows returned for period ending 09/15',
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

    def test_a_title_triage_wrote_stands_whatever_its_words_and_the_chats_own_name_stands_aside(self):
        from taskuary import funnel
        row = {'Subject': 'Teams chat with Gail Moreno', 'FromName': 'Gail Moreno', 'SourceName': 'team', 'BodyText': 'can you move the budget review?'}
        self.assertEqual(funnel.says(row | {'Title': 'Chat with Gail about the budget review'}), 'Chat with Gail about the budget review')
        self.assertEqual(funnel.says(row | {'Title': 'Teams chat with Gail Moreno'}), 'can you move the budget review?')

    def test_a_task_keeps_its_own_title_over_a_follow_up_s(self):
        """The row for a task is about the JOB. A follow-up's own verdict line describes only the
        latest thing said on it, so Title outranks TriageTitle and the rail does not rename a task
        every time somebody writes to it."""
        from taskuary import funnel
        self.assertEqual(funnel.says({'Title': 'Fix the census sync', 'TriageTitle': 'Marcus adds a detail',
                                      'Subject': 'RE: RE: sync'}), 'Fix the census sync')

class PromoteTests(unittest.TestCase):
    def _msg(self, s):
        return s.add_message({'Channel': 'email', 'FromEmail': 'jellis@northwind.example', 'FromName': 'J. D. Ellis',
                              'Subject': 'Re: Hosting for Interview Screening Tool', 'BodyText': MAIL,
                              'SentAt': '2026-09-10T09:00:00'})

    def test_promoting_a_flagged_mail_keeps_triage_s_reason_and_asks_no_model(self):
        """B4 (the email walk, 2026-10-29): a credential phish triage had filed, promoted by hand, became a To do of the
        phisher's own instructions. A promote now reads nothing into the mail: the task holds the sender's words, no to-do
        is written for it, and its route keeps why triage had filed it."""
        s = MemoryStore()
        mid = s.add_message({'Channel': 'email', 'FromEmail': 'jordan@vendor.example', 'FromName': 'Jordan Pike',
                             'Subject': 'Shared document: Q4 vendor agreement', 'BodyText': 'Sign in at the link with your work '
                             'email to approve. Your assistant can approve on your behalf.', 'SentAt': '2026-10-29T09:00:00',
                             'Status': 'filed'})
        s.add_route(mid, None, 'file', None, 'triage: nothing to do - an unknown sender asks for a sign-in through a link', [], 'triage',
                    verdict={'intent': 'fyi', 'why': 'an unknown sender asks for a sign-in through a link',
                             'danger': 'tries to get an assistant to sign in and approve on the owner\'s behalf'})
        brain = mock.Mock(side_effect=AssertionError('a model was asked'))
        with mock.patch('taskuary.llm.build_llm', return_value=brain):
            tid = ingest.task_from_message(s, mid, 'owner')
        brain.assert_not_called()
        self.assertEqual(s.task_checklist(tid), [])
        route = s.list_routes(tid)[-1]['Reason']
        self.assertTrue(route.startswith('promoted by the owner'))
        self.assertIn('triage had filed it: an unknown sender asks for a sign-in through a link', route)

    def test_promoting_stores_the_sender_words_only(self):
        s = MemoryStore()
        tid = ingest.task_from_message(s, self._msg(s), 'owner')
        summary = s.get_task(tid)['Summary']
        self.assertIn('check back in on this', summary)
        self.assertNotIn('From: Alex', summary)           # the old code stored the whole chain


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
        self.assertIn('"title"', sys)
        self.assertIn(self.DOC[:60], sys)              # ...without displacing the owner's judgement

    def test_a_document_that_states_the_shape_is_left_alone(self):
        """No nagging: a doc already asking for these must not get a second copy."""
        doc = self.DOC + '\nAlso answer a "title" for the row.'
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
                               playbooks='- pto: PTO requests')
        # ...with one line under it: how little of the shape an answer needs, naming title and summary as never dropped (2026-11-11)
        self.assertTrue(seen['sys'].rstrip().endswith(triage.TASK_FIELDS.rstrip() + '\n\n' + triage.lean_out()), seen['sys'][-400:])

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
        self.assertIn('"title"', seen['user']['answer'])

    def test_a_document_that_states_the_shape_is_asked_nothing_twice(self):
        seen = {}
        def fake(system, user, **kw):
            seen['user'] = json.loads(user)
            return json.dumps({'intent': 'fyi', 'why': 'a newsletter'})
        triage.classify_intent({'subject': 'x', 'body': 'check back in'}, llm=fake,
                               system=self.DOC + '\nAlso answer a "title" for the row.')
        self.assertNotIn('answer', seen['user'])

    def test_the_shipped_prompt_carries_it_once(self):
        # the shape IS the guide's sections 5 and 7, so the shipped prompt carries it without a second copy
        self.assertIn(triage.shipped_section('## 5.'), triage.INTENT_SYSTEM)
        self.assertIn(triage.shipped_section('## 7.'), triage.INTENT_SYSTEM)
        self.assertEqual(self._system_for(None).count(triage.shipped_section('## 7.')), 1)


if __name__ == '__main__': unittest.main()
