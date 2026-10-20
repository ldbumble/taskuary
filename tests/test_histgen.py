"""Generate-from-history: Graph mail faked, LLM faked - the splice, the fallbacks and the
guardrails are what's under test.
"""
import unittest
from unittest import mock
from taskuary import histgen
from taskuary.store import MemoryStore

GUIDE = ('### What history shows gets answered\n- payroll and import failures, same day\n'
         '### What history shows is ignorable\n- vendor newsletters\n'
         '### Senders and domains that matter\n- corp.example colleagues')
STYLE = ('### Greeting & sign-off\n- "Hi <first>", signs "Best, {{owner_first}}"\n'
         '### Tone & length\n- two sentences, answer first\n'
         '### Characteristic phrasing\n- "on it"\n'
         '### How they push back or say no\n- offers the alternative in the same breath')

JOB = ('### What the job is\n- {{owner_first}} keeps the payroll import running and answers the people who depend on it\n'
       '### Responsibilities, by how often they come up\n- PTO import failures: weekly, always answered\n'
       '### Who {{owner_first}} works with\n- corp.example colleagues write most and are answered\n'
       '### Recurring cadences\n- the import runs nightly; its failures arrive the next morning\n'
       '### Decisions {{owner_first}} makes, and what they hand up\n- fixes and reruns are theirs\n'
       '### What to protect\n- payroll going out on the right numbers')

def fake_llm(system, user, max_tokens=0):
    return JOB if 'JOB IS' in system else GUIDE if 'TRIAGE' in system else STYLE   # the job prompt names TRIAGE.md too

def graph(sent, inbox, n=1):
    return mock.patch.object(histgen, '_graph_mail', return_value=(sent, inbox, n))

SENT = [{'id': 's1', 'subject': 'RE: PTO import', 'receivedDateTime': '2026-08-01T10:00:00Z',
         'conversationId': 'c1', 'body': {'content': 'Fixed - rerunning tonight.\nFrom: Sarah\nSent: old'}}]
INBOX = [{'id': 'i1', 'subject': 'PTO import failing', 'receivedDateTime': '2026-08-01T09:00:00Z',
          'conversationId': 'c1', 'from': {'emailAddress': {'address': 'paula@corp.example'}}},
         {'id': 'i2', 'subject': 'Weekly vendor newsletter', 'receivedDateTime': '2026-08-02T09:00:00Z',
          'conversationId': 'c2', 'from': {'emailAddress': {'address': 'news@vendor.com'}}}]


class HistgenTests(unittest.TestCase):
    def test_cut_quoted(self):
        self.assertEqual(histgen.cut_quoted('Answer.\nFrom: Someone <a@b.c>\nold text'), 'Answer.')
        self.assertEqual(histgen.cut_quoted('Yes.\nOn Mon, Aug 3, Sarah wrote:\n> hi'), 'Yes.')
        self.assertEqual(histgen.cut_quoted('plain\nreply'), 'plain\nreply')

    def test_style_sample_keeps_the_signature_at_the_end_of_a_long_email(self):
        body = 'Hello,\n\n' + ('detail ' * 200) + '\n\nBest,\nAlex\nNorthwind Trading\n555-0100'
        sample = histgen.style_sample(body, 200)
        self.assertLess(len(sample), 240)
        self.assertTrue(sample.startswith('Hello,'))
        self.assertIn('Best,\nAlex\nNorthwind Trading\n555-0100', sample)

    def test_triage_generates_into_marker_block(self):
        s = MemoryStore()
        with graph(SENT, INBOX), mock.patch('taskuary.llm.build_llm', return_value=fake_llm):
            detail = histgen.generate(s, 'triage')
        doc = s.get_doc('triage')
        self.assertIn('2 inbound + 1 sent', detail)
        self.assertIn(histgen.HIST_START, doc)
        self.assertIn('vendor newsletters', doc)
        self.assertIn('# How to triage what arrives', doc)   # the shipped guide survives

    def test_regenerate_replaces_not_duplicates(self):
        s = MemoryStore()
        with graph(SENT, INBOX), mock.patch('taskuary.llm.build_llm', return_value=fake_llm):
            histgen.generate(s, 'triage'); histgen.generate(s, 'triage')
        doc = s.get_doc('triage')
        self.assertEqual(doc.count(histgen.HIST_START), 1)
        self.assertEqual(doc.count('vendor newsletters'), 1)

    def test_style_falls_back_to_taskuary_record(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 't', 'Kind': 'reply', 'Status': 'open'}, 't')
        s.add_message({'TaskId': tid, 'ExternalId': 'x1', 'Channel': 'email', 'Subject': 'q',
                       'SentAt': '2026-08-20 10:00:00', 'Status': 'context',
                       'BodyText': 'Hi Sarah - yes, rerunning tonight and will confirm before payroll.'})
        with graph([], [], 0), mock.patch('taskuary.llm.build_llm', return_value=fake_llm):
            detail = histgen.generate(s, 'style')
        self.assertIn('Taskuary itself has seen', detail)
        self.assertIn('Greeting & sign-off', s.get_doc('style'))
        self.assertEqual(s.get_doc('style').count(histgen.HIST_START), 1)   # template block reused

    def test_job_reads_both_directions_into_its_marker_block(self):
        """JOB.md is the third generated document: inbox and sent together, the people each way, the recurring
        subjects with how many weeks they were present, and the threads the owner opened. The shipped template's
        own heading survives and the placeholder line is what the block replaces."""
        s = MemoryStore()
        sent = SENT + [{'id': 's2', 'subject': 'Access review - census database', 'receivedDateTime': '2026-08-05T10:00:00Z',
                        'conversationId': 'c9', 'toRecipients': [{'emailAddress': {'address': 'gail@corp.example'}}],
                        'body': {'content': 'Starting the quarterly review.'}}]
        seen = {}
        def llm(system, user, max_tokens=0): seen.update(s=system, u=user); return JOB
        with graph(sent, INBOX), mock.patch('taskuary.llm.build_llm', return_value=llm):
            detail = histgen.generate(s, 'job')
        doc = s.get_doc('job')
        self.assertIn('2 inbound + 2 sent', detail)
        self.assertIn(histgen.HIST_START, doc)
        self.assertIn('payroll going out', doc)
        self.assertIn('## The job', doc)                          # the template's own section survives
        self.assertNotIn('not generated yet', doc)
        self.assertIn('paula@corp.example: 1 mails, 1 answered', seen['u'])    # who writes in, and whether answered
        self.assertIn('gail@corp.example: 1 mails', seen['u'])                 # who the owner writes to
        self.assertIn('THREADS THE OWNER STARTED', seen['u'])                   # a sent mail on no inbound thread
        self.assertIn('never say what is a task', seen['s'])                   # importance, not intent
        ev = histgen.STATUS['evidence']
        self.assertTrue(any(l.startswith('writes to you') for l in ev) and any(l.startswith('you write to') for l in ev))

    def test_job_doc_is_silent_until_it_says_something_real(self):
        """The untouched template must never ride into triage as noise - the rule STYLE.md already lives by."""
        from taskuary.triage import job_doc
        s = MemoryStore()
        self.assertEqual(job_doc(s), '')
        with graph(SENT, INBOX), mock.patch('taskuary.llm.build_llm', return_value=fake_llm):
            histgen.generate(s, 'job')
        self.assertIn('payroll going out', job_doc(s))
        self.assertNotIn('<!--', job_doc(s))
        self.assertEqual(len(job_doc(s, 20)), 20)

    def test_no_data_and_no_ai_are_loud(self):
        s = MemoryStore()
        with graph([], [], 0), mock.patch('taskuary.llm.build_llm', return_value=fake_llm):
            with self.assertRaises(RuntimeError): histgen.generate(s, 'style')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            with self.assertRaises(RuntimeError): histgen.generate(s, 'triage')
        with self.assertRaises(ValueError): histgen.generate(s, 'agent')     # a doc with no history generator

    def test_broken_answer_never_lands(self):
        s = MemoryStore()
        before = s.get_doc('triage')
        with graph(SENT, INBOX), mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: '<!-- evil -->'):
            with self.assertRaises(RuntimeError): histgen.generate(s, 'triage')
        self.assertEqual(s.get_doc('triage'), before)

    def test_style_doc_gate(self):
        from taskuary.responder import style_doc
        s = MemoryStore()
        self.assertEqual(style_doc(s), '')                 # untouched template: headers + placeholders only
        with graph(SENT, INBOX), mock.patch('taskuary.llm.build_llm', return_value=fake_llm):
            histgen.generate(s, 'style')
        out = style_doc(s)
        self.assertIn('Tone & length', out)
        self.assertNotIn('<!--', out)

class VocabularyFromHistoryTests(unittest.TestCase):
    """The Shared voice vocabulary page's Generate from history: names off the envelopes and subjects,
    the model picks, the owner's list is kept whole and the new terms fill the room left."""
    INBOX = [{'id': 'i1', 'subject': 'RE: Payworth export', 'receivedDateTime': '2026-08-01T09:00:00Z', 'conversationId': 'c1',
              'from': {'emailAddress': {'address': 'paula@corp.example', 'name': 'Paula Vance'}}},
             {'id': 'i2', 'subject': 'Intacct sync', 'receivedDateTime': '2026-08-02T09:00:00Z', 'conversationId': 'c2',
              'from': {'emailAddress': {'address': 'paula@corp.example', 'name': 'Paula Vance'}}}]
    SENT = [{'id': 's1', 'subject': 'RE: Payworth export', 'receivedDateTime': '2026-08-01T10:00:00Z', 'conversationId': 'c1',
             'toRecipients': [{'emailAddress': {'address': 'paula@corp.example', 'name': 'Paula Vance'}}], 'body': {'content': 'done'}}]

    def test_history_terms_join_the_owners_list_without_displacing_it(self):
        from taskuary import voice
        s = MemoryStore(); voice.save_vocabulary(s, ['Taskuary', 'Intacct'], 'o')
        seen = {}
        def llm(system, user, max_tokens=0):
            seen['user'] = user
            # numbering, quotes, a duplicate of the owner's own term and an over-long line: each handled per line
            return '1. Paula Vance\n- "Payworth"\nintacct\n' + 'x' * 60 + '\nNorthwind Group'
        with graph(self.SENT, self.INBOX), mock.patch('taskuary.llm.build_llm', return_value=llm):
            detail = histgen.generate(s, 'vocabulary')
        self.assertEqual(voice.vocabulary(s), ['Taskuary', 'Intacct', 'Paula Vance', 'Payworth', 'Northwind Group'])
        self.assertIn('kept 2, added 3', detail); self.assertIn('1 sent + 2 inbound', detail)
        self.assertIn('Paula Vance: 3', seen['user']); self.assertIn('corp.example: 2', seen['user'])
        self.assertIn('Payworth export: 2', seen['user'])           # RE: stripped, so both sides of the thread count once
        self.assertIn('CURRENT LIST: Taskuary, Intacct', seen['user'])
        self.assertEqual(histgen.STATUS['state'], 'done'); self.assertTrue(any('Paula Vance' in l for l in histgen.STATUS['evidence']))
        self.assertIsNone(s.get_doc('vocabulary'))                        # a setting, never a doc

    def test_the_list_never_overflows_and_says_what_did_not_fit(self):
        from taskuary import voice
        s = MemoryStore(); voice.save_vocabulary(s, [f'term{i}' for i in range(98)], 'o')
        with graph(self.SENT, self.INBOX), mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: 'A One\nB Two\nC Three'):
            detail = histgen.generate(s, 'vocabulary')
        self.assertEqual(len(voice.vocabulary(s)), 100); self.assertIn('added 2 (1 more did not fit)', detail)
        with graph(self.SENT, self.INBOX), mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: 'D Four'):
            with self.assertRaises(RuntimeError) as e: histgen.generate(s, 'vocabulary')
        self.assertIn('full', str(e.exception))

    def test_falls_back_to_taskuary_record_and_refuses_an_empty_history(self):
        from taskuary import voice
        s = MemoryStore()
        with graph([], [], 0), mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: 'x'):
            with self.assertRaises(RuntimeError) as e: histgen.generate(s, 'vocabulary')
        self.assertIn('no mail history', str(e.exception))
        tid = s.create_task({'Title': 't', 'Kind': 'task', 'Status': 'open'}, 't')
        s.add_message({'TaskId': tid, 'ExternalId': 'x1', 'Channel': 'email', 'Subject': 'FW: Yardi roll', 'FromName': 'Dov Blake',
                       'FromEmail': 'dov@corp.example', 'SentAt': '2026-08-20 10:00:00', 'BodyText': 'see attached'})
        seen = {}
        def llm(system, user, max_tokens=0): seen['user'] = user; return 'Dov Blake\nYardi'
        with graph([], [], 0), mock.patch('taskuary.llm.build_llm', return_value=llm):
            detail = histgen.generate(s, 'vocabulary')
        self.assertIn('no Graph mailbox history', detail); self.assertEqual(voice.vocabulary(s), ['Dov Blake', 'Yardi'])
        self.assertIn('Yardi roll: 1', seen['user']); self.assertIn('Dov Blake: 1', seen['user'])


if __name__ == '__main__':
    unittest.main()


class TopicRollUpTests(unittest.TestCase):
    """"Generate from history should see no responses on it." It already marked each mail
    ANSWERED or not - one line at a time. So a fortnight of resident-refund mail, each with a
    different resident in the subject and none of them ever answered, arrived as seventeen
    unrelated no-reply lines, and the prompt's own rule ("never a rule from a single
    conversation") forbade the model from saying the one thing the mailbox was shouting."""
    REFUNDS = [{'id': f'r{i}', 'subject': f'Re: Resident Refund Request - {name}',
                'receivedDateTime': f'2026-08-{10 + i:02d}T09:00:00Z', 'conversationId': f'rc{i}',
                'from': {'emailAddress': {'address': f'{name.split(",")[0].lower()}@riverbend.example'}}}
               for i, name in enumerate(['Doe, Jane', 'PAYNE, MICHAEL', 'Watson, Lisa',
                                         'Foote, Marie Grace', 'Smith, Rosemary'])]

    def _payload(self, sent, inbox):
        seen = {}
        def llm(system, user, max_tokens=0):
            seen['user'] = user
            return GUIDE
        s = MemoryStore()
        with graph(sent, inbox), mock.patch('taskuary.llm.build_llm', return_value=llm):
            histgen.generate(s, 'triage')
        return seen['user'], histgen.STATUS['evidence']

    def test_a_recurring_never_answered_topic_is_counted_and_named(self):
        user, ev = self._payload(SENT, self.REFUNDS + INBOX)
        self.assertIn('TOPIC ROLL-UP', user)
        # one topic, five mails, none answered - and the changing resident is not part of it
        self.assertIn('"resident refund request": 5 mails, 0 answered', user)
        self.assertIn('never answered', user)
        self.assertNotIn('Doe', user.split('INBOUND MAIL:')[0])   # not in the roll-up
        # and the receipts show the owner the same thing, so the guidance is inspectable
        self.assertTrue(any('never-answered first' in e for e in ev))

    def test_an_answered_topic_is_not_dressed_up_as_ignorable(self):
        """The signal has to cut both ways or it is not a signal."""
        answered = [{'id': 's9', 'subject': 'RE: Resident Refund Request - PAYNE, MICHAEL',
                     'receivedDateTime': '2026-08-11T10:00:00Z', 'conversationId': 'rc1',
                     'body': {'content': 'Approved, processing today.'}}]
        user, _ev = self._payload(SENT + answered, self.REFUNDS)
        self.assertIn('"resident refund request": 5 mails, 1 answered', user)
        self.assertNotIn('never answered', user)

    def test_a_one_off_subject_is_not_a_topic(self):
        """Three sightings is routine work; one is a conversation."""
        user, _ev = self._payload(SENT, INBOX)
        self.assertNotIn('TOPIC ROLL-UP', user)

class VocabularyFromHistoryTests(unittest.TestCase):
    """The Shared voice vocabulary page's Generate from history: names off the envelopes and subjects,
    the model picks, the owner's list is kept whole and the new terms fill the room left."""
    INBOX = [{'id': 'i1', 'subject': 'RE: Payworth export', 'receivedDateTime': '2026-08-01T09:00:00Z', 'conversationId': 'c1',
              'from': {'emailAddress': {'address': 'paula@corp.example', 'name': 'Paula Vance'}}},
             {'id': 'i2', 'subject': 'Intacct sync', 'receivedDateTime': '2026-08-02T09:00:00Z', 'conversationId': 'c2',
              'from': {'emailAddress': {'address': 'paula@corp.example', 'name': 'Paula Vance'}}}]
    SENT = [{'id': 's1', 'subject': 'RE: Payworth export', 'receivedDateTime': '2026-08-01T10:00:00Z', 'conversationId': 'c1',
             'toRecipients': [{'emailAddress': {'address': 'paula@corp.example', 'name': 'Paula Vance'}}], 'body': {'content': 'done'}}]

    def test_history_terms_join_the_owners_list_without_displacing_it(self):
        from taskuary import voice
        s = MemoryStore(); voice.save_vocabulary(s, ['Taskuary', 'Intacct'], 'o')
        seen = {}
        def llm(system, user, max_tokens=0):
            seen['user'] = user
            # numbering, quotes, a duplicate of the owner's own term and an over-long line: each handled per line
            return '1. Paula Vance\n- "Payworth"\nintacct\n' + 'x' * 60 + '\nNorthwind Group'
        with graph(self.SENT, self.INBOX), mock.patch('taskuary.llm.build_llm', return_value=llm):
            detail = histgen.generate(s, 'vocabulary')
        self.assertEqual(voice.vocabulary(s), ['Taskuary', 'Intacct', 'Paula Vance', 'Payworth', 'Northwind Group'])
        self.assertIn('kept 2, added 3', detail); self.assertIn('1 sent + 2 inbound', detail)
        self.assertIn('Paula Vance: 3', seen['user']); self.assertIn('corp.example: 2', seen['user'])
        self.assertIn('Payworth export: 2', seen['user'])           # RE: stripped, so both sides of the thread count once
        self.assertIn('CURRENT LIST: Taskuary, Intacct', seen['user'])
        self.assertEqual(histgen.STATUS['state'], 'done'); self.assertTrue(any('Paula Vance' in l for l in histgen.STATUS['evidence']))
        self.assertIsNone(s.get_doc('vocabulary'))                        # a setting, never a doc

    def test_the_list_never_overflows_and_says_what_did_not_fit(self):
        from taskuary import voice
        s = MemoryStore(); voice.save_vocabulary(s, [f'term{i}' for i in range(98)], 'o')
        with graph(self.SENT, self.INBOX), mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: 'A One\nB Two\nC Three'):
            detail = histgen.generate(s, 'vocabulary')
        self.assertEqual(len(voice.vocabulary(s)), 100); self.assertIn('added 2 (1 more did not fit)', detail)
        with graph(self.SENT, self.INBOX), mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: 'D Four'):
            with self.assertRaises(RuntimeError) as e: histgen.generate(s, 'vocabulary')
        self.assertIn('full', str(e.exception))

    def test_falls_back_to_taskuary_record_and_refuses_an_empty_history(self):
        from taskuary import voice
        s = MemoryStore()
        with graph([], [], 0), mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: 'x'):
            with self.assertRaises(RuntimeError) as e: histgen.generate(s, 'vocabulary')
        self.assertIn('no mail history', str(e.exception))
        tid = s.create_task({'Title': 't', 'Kind': 'task', 'Status': 'open'}, 't')
        s.add_message({'TaskId': tid, 'ExternalId': 'x1', 'Channel': 'email', 'Subject': 'FW: Yardi roll', 'FromName': 'Dov Blake',
                       'FromEmail': 'dov@corp.example', 'SentAt': '2026-08-20 10:00:00', 'BodyText': 'see attached'})
        seen = {}
        def llm(system, user, max_tokens=0): seen['user'] = user; return 'Dov Blake\nYardi'
        with graph([], [], 0), mock.patch('taskuary.llm.build_llm', return_value=llm):
            detail = histgen.generate(s, 'vocabulary')
        self.assertIn('no Graph mailbox history', detail); self.assertEqual(voice.vocabulary(s), ['Dov Blake', 'Yardi'])
        self.assertIn('Yardi roll: 1', seen['user']); self.assertIn('Dov Blake: 1', seen['user'])


class FirstPersonTests(unittest.TestCase):
    """JOB.md and STYLE.md are the owner's own documents (the owner, 2026-10-16: "it's written in 3rd party like it appears they are x,
    that's not a good job.md. it should say this is what i am responsible in 1st party") - and the job knows whose company it is:
    the owner's own colleagues were read as "one partner organisation"."""
    INBOX = [{'id': 'i1', 'subject': 'PTO import failing', 'receivedDateTime': '2026-08-01T09:00:00Z', 'conversationId': 'c1',
              'from': {'emailAddress': {'address': 'paula@corp.example', 'name': 'Paula Vance'}}}]

    def test_the_job_is_written_as_the_owner_and_knows_their_organisation(self):
        s = MemoryStore()
        for k, v in (('owner_name', 'Alex Doyle'), ('owner_email', 'alex@corp.example'), ('owner_company', 'Corp'), ('owner_title', 'Payroll lead')):
            s.set_setting(k, v, 'owner')
        seen = {}
        def llm(system, user, max_tokens=0): seen.update(s=system, u=user); return JOB
        with graph(SENT, self.INBOX), mock.patch('taskuary.llm.build_llm', return_value=llm):
            histgen.generate(s, 'job')
        self.assertIn('first person', seen['s']); self.assertIn('### Who I work with', seen['s'])
        self.assertNotIn('Refer to the owner as {{owner_first}}', seen['s'])
        self.assertIn('appears', seen['s'])                         # named as a word never to use
        self.assertIn('Alex Doyle, Payroll lead at Corp', seen['u'])
        self.assertIn('corp.example', seen['u']); self.assertIn('their own organisation', seen['u'])
        self.assertIn('paula@corp.example: 1 mails, 1 answered - Paula Vance', seen['u'])   # people by name, not address alone

    def test_the_job_reads_what_people_ask_not_only_subjects(self):
        s = MemoryStore()
        asks = [{'FromName': 'Marcus Reed', 'FromEmail': 'marcus@corp.example', 'Subject': 'Vendor payment run', 'Status': 'routed',
                 'BodyText': 'The payment run is ready - it needs your approval by EOD Wednesday.'}]
        seen = {}
        def llm(system, user, max_tokens=0): seen.update(u=user); return JOB
        with graph(SENT, self.INBOX), mock.patch.object(histgen, '_db_window', return_value=asks), mock.patch('taskuary.llm.build_llm', return_value=llm):
            histgen.generate(s, 'job')
        self.assertIn('Marcus Reed "Vendor payment run": The payment run is ready - it needs your approval', seen['u'])

    def test_the_style_is_written_as_the_owner_too(self):
        self.assertIn('first person', histgen.STYLE_SYSTEM); self.assertIn('### How I push back or say no', histgen.STYLE_SYSTEM)

SOUL = ('### How I like to work\n- I settle a question the same day and say so in one line.\n'
        '### What matters to me\n- The close going out on the right numbers.\n'
        '### What I want handled for me\n- (nothing clear from my mail yet)')


class SetupDraftTests(unittest.TestCase):
    """How you write and who you are, drafted at setup from the mail with fake brains (the owner, 2026-10-20)."""
    IMAP = [{'subject': 'Re: rota', 'sent_at': '2026-10-02 08:00:00', 'conversation_id': 'r1', 'from_email': 'alex@riverside.example',
             'to': ['ray@riverside.example'], 'body': 'Done - the rota is in the shared folder now.\n\nBest,\nAlex'}]

    def test_style_reads_every_mailbox_not_only_the_outlook_one(self):
        """An Outlook card ended the read: the IMAP mailbox's sent mail never reached the style (2026-10-20)."""
        s = MemoryStore()
        cid = s.get_connector_by_type('imap')['ConnectorId']; s.save_connector({'ConnectorId': cid, 'Active': 1}, 't')
        seen = {}
        def llm(system, user, max_tokens=0): seen['u'] = user; return STYLE
        with graph(SENT, INBOX), mock.patch('taskuary.imapmail.sent_history', return_value=self.IMAP), \
             mock.patch('taskuary.llm.build_llm', return_value=llm):
            src = histgen.generate(s, 'style')
        self.assertIn('Fixed - rerunning tonight.', seen['u']); self.assertIn('the rota is in the shared folder', seen['u'])
        self.assertIn('across 2 mailbox(es), read over Graph and IMAP', src)
        self.assertIn('two sentences, answer first', s.get_doc('style'))

    def test_who_you_are_is_drafted_from_the_sent_mail_and_the_answers_beside_the_systems_block(self):
        from taskuary import firstrun
        s = MemoryStore()
        firstrun.save_about(s, {'name': 'Alex Doyle', 'org': 'Northwind', 'role': 'Finance lead', 'systems': ['Payworth']})
        seen = {}
        def llm(system, user, max_tokens=0): seen.update(s=system, u=user); return SOUL
        with mock.patch.object(histgen, 'sent_mail', return_value=(SENT, [], 1, 'Graph')), mock.patch('taskuary.llm.build_llm', return_value=llm):
            histgen.generate(s, 'soul')
        soul = s.get_doc('soul')
        self.assertIn('I settle a question the same day', soul)
        self.assertIn('- Payworth', soul)                                             # the systems answered stay the owner's block
        self.assertLess(soul.index('## How I work'), soul.index('## Systems I work in'))
        self.assertEqual(soul.count(histgen.HIST_START), 1)
        for x in ('Payworth', 'Finance lead', 'Fixed - rerunning tonight.'): self.assertIn(x, seen['u'])
        self.assertIn('Never invent a fact', seen['s']); self.assertIn('first person', seen['s'])
        with mock.patch.object(histgen, 'sent_mail', return_value=(SENT, [], 1, 'Graph')), \
             mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: SOUL.replace('same day', 'same hour')):
            histgen.generate(s, 'soul')                                               # written again: replaced in place
        soul = s.get_doc('soul')
        self.assertIn('same hour', soul); self.assertNotIn('same day', soul); self.assertEqual(soul.count('## How I work'), 1)
        self.assertIn('- Payworth', soul)

    def test_who_you_are_with_nothing_the_owner_wrote_says_so(self):
        s = MemoryStore()
        with mock.patch.object(histgen, 'sent_mail', return_value=([], [], 0, 'IMAP')), \
             mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: SOUL):
            with self.assertRaisesRegex(RuntimeError, 'no sent mail to learn from'): histgen.generate(s, 'soul')
        self.assertEqual(histgen.STATUS['state'], 'failed')
