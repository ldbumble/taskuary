"""Setup asks a few short questions for SOUL.md and JOB.md, filled from the mail where it can, and ends in a finish the owner
presses (the owner, 2026-10-15: "we need survey like a few short question on setup screen to fill out soul.md and job.md (though you
can generate as much as possible from history) ... we only have repo's in the soul.md not what other corporate system connectors
they have for non technical people ... forgot to ask for their name ... we should be able to dismiss the walk through and then the
morning digest screen will show up")."""
import json, unittest
from unittest import mock

from taskuary import firstrun
from taskuary.store import MemoryStore

ANSWERS = {'name': 'Alex Doyle', 'org': 'Northwind', 'role': 'Finance systems lead', 'systems': ['Workday', 'Salesforce', 'Payworth']}
LEARNED = ('### What my job is\n- I run the finance systems the month-end close depends on.\n'
           '### Who I work with\n- Erin Blake writes most about the close.')
STYLE_GUIDE = ('### Greeting & sign-off\n- I open with "Hi" and the first name, and sign off "Best, {{owner_first}}".\n'
               '### Tone & length\n- Two or three sentences, the answer first.')


def learned(s, body=LEARNED):
    """JOB.md as Generate from history leaves it - the marked block after the template's own section."""
    from taskuary import histgen
    s.save_doc('job', histgen._splice(s.get_doc('job') or '## The job\n', f'_generated 2026-10-16 08:00 — 9 messages_\n\n{body}',
                                      histgen.TITLES['job']), 'histgen')


def mailboxes(s, *boxes):
    """Mailboxes connected the way setup connects them: the card switched on, its address a source on that card."""
    for typ, addr in boxes:
        cid = s.get_connector_by_type(typ)['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1}, 't')
        s.save_source({'Channel': 'email', 'Address': addr, 'Active': 1, 'ConnectorId': cid}, 't')
    return s


class AboutTests(unittest.TestCase):
    """ONE QUESTION A SCREEN, AND THE JOB READ OUT OF THE MAIL (the owner, 2026-10-16: "about your work is too much on one screen ...
    wait for email to read through all of them then let them fill out name/org/name of role/ then what they are responsible or job
    description should be prefilled using ai from their email and ask them if it's good description")."""
    def test_the_answers_land_where_they_are_read_and_the_name_everywhere(self):
        s = MemoryStore(); learned(s)
        firstrun.save_about(s, ANSWERS)
        soul, job = s.get_doc('soul'), s.get_doc('job')
        self.assertIn('## Systems I work in', soul)
        for x in ('Workday', 'Salesforce', 'Payworth'): self.assertIn(f'- {x}', soul)
        self.assertLess(soul.index('## Systems I work in'), soul.index('## Connected systems'))
        self.assertIn('Finance systems lead', job); self.assertIn('Northwind', job)
        self.assertIn('I run the finance systems', job)                             # the learned job, kept as it was
        self.assertEqual(s.owner()['owner'], 'Alex Doyle')
        self.assertEqual((s.get_setting('owner_company'), s.get_setting('owner_title')), ('Northwind', 'Finance systems lead'))
        self.assertTrue(firstrun.state(s)['about_done'])

    def test_the_job_as_the_owner_corrected_it_replaces_the_learned_one(self):
        s = MemoryStore(); learned(s)
        firstrun.save_about(s, {**ANSWERS, 'job': '### What my job is\n- I own payroll and vendor payments, end to end.'})
        job = s.get_doc('job')
        self.assertIn('I own payroll and vendor payments', job); self.assertNotIn('month-end close depends on', job)
        self.assertEqual(job.count('<!-- fromhistory:start -->'), 1)
        self.assertEqual(firstrun.about(s)['job'], '### What my job is\n- I own payroll and vendor payments, end to end.')

    def test_the_signature_checked_at_setup_is_the_one_saved(self):
        s = MemoryStore()
        sig = 'Best,\nAlex Doyle\nNorthwind'
        firstrun.save_about(s, {**ANSWERS, 'signature': sig})
        self.assertEqual(s.get_setting('email_signature'), sig)
        self.assertEqual(firstrun.about(s)['signature'], sig)
        firstrun.save_about(s, ANSWERS)                                                   # not asked: left as it was
        self.assertEqual(s.get_setting('email_signature'), sig)

    def test_saving_again_replaces_the_answers_and_keeps_the_owners_own_lines(self):
        s = MemoryStore()
        firstrun.save_about(s, ANSWERS)
        s.save_doc('soul', s.get_doc('soul') + '\n## My notes\n- Never wire money on a Friday.\n', 'owner')
        firstrun.save_about(s, {**ANSWERS, 'systems': ['ADP']})
        soul = s.get_doc('soul')
        self.assertIn('- ADP', soul); self.assertNotIn('- Workday', soul); self.assertEqual(soul.count('## Systems I work in'), 1)
        self.assertIn('Never wire money on a Friday.', soul)
        self.assertEqual(firstrun.about(s)['systems'], ['ADP'])

    def test_the_prefill_reads_signatures_names_and_bodies_not_only_subjects(self):
        """Read off counts and subject lines alone, the role came back "exact job title not shown in the mail" and the people as
        bare addresses, while every signature said the title (a fresh-install walk, 2026-10-16)."""
        s = MemoryStore()
        s.set_setting('owner_email', 'alex@northwind.example', 'owner')
        msgs = [{'FromEmail': 'erin@northwind.example', 'FromName': 'Erin Blake', 'Subject': 'Month-end close', 'Status': 'routed',
                 'BodyText': 'Can you sign off the AP accruals in Workday by Thursday?', 'SentAt': '2026-10-15 09:00:00'}]
        sent = [{'subject': 'Re: close', 'receivedDateTime': '2026-10-14T10:00:00Z',
                 'body': {'content': 'Hi Erin,\n\nSigned off.\n\nBest,\nAlex Doyle\nFinance Systems Lead | Northwind'}}]
        def brain(system, user, **kw):
            brain.user = user
            return json.dumps({'name': 'Alex Doyle', 'org': 'Northwind', 'role': 'Finance Systems Lead', 'systems': ['Workday']})
        with mock.patch('taskuary.histgen.sent_mail', return_value=(sent, [], 1, 'IMAP')), \
             mock.patch('taskuary.histgen._db_window', return_value=msgs), mock.patch('taskuary.llm.build_llm', return_value=brain):
            out = firstrun.suggest_about(s)
        self.assertEqual(out, {'name': 'Alex Doyle', 'org': 'Northwind', 'role': 'Finance Systems Lead', 'systems': ['Workday'],
                               'signature': ''})                     # one sent mail is no shared ending (test_signature_learn)
        for seen in ('alex@northwind.example', 'Finance Systems Lead | Northwind', 'Erin Blake', 'sign off the AP accruals'):
            self.assertIn(seen, brain.user)

    def test_the_systems_are_read_off_three_months_of_who_writes_not_the_last_few_mails(self):
        """On a real mailbox the forty newest mails were alerts and the systems came back as "SFTP" and "SharePoint" (the owner,
        2026-10-16: "the softwares mentioned in my emails were not accurate"). The model is shown which vendors write in and how
        often, across the whole window, and told a protocol or a file share is not a system."""
        s = MemoryStore()
        s.set_setting('owner_email', 'alex@northwind.example', 'owner')
        msgs = [{'FromEmail': f'noreply@payworth.example', 'FromName': 'Payworth', 'Subject': f'Payroll import {i} failed', 'Status': 'routed',
                 'BodyText': 'The import failed.', 'SentAt': '2026-09-01 09:00:00'} for i in range(12)]
        msgs += [{'FromEmail': 'erin@northwind.example', 'FromName': 'Erin Blake', 'Subject': 'SFTP folder for the bank file', 'Status': 'routed',
                  'BodyText': 'Can you open the SFTP folder?', 'SentAt': '2026-10-15 09:00:00'}]
        def brain(system, user, **kw):
            brain.system, brain.user = system, user
            return json.dumps({'name': '', 'org': '', 'role': '', 'systems': ['Payworth']})
        with mock.patch('taskuary.histgen.sent_mail', return_value=([], [], 0, 'IMAP')), \
             mock.patch('taskuary.histgen._db_window', return_value=msgs), mock.patch('taskuary.llm.build_llm', return_value=brain):
            out = firstrun.suggest_about(s)
        self.assertEqual(out['systems'], ['Payworth'])
        self.assertIn('payworth.example: 12 mails', brain.user)                       # who writes in, counted over the window
        self.assertNotIn('northwind.example: ', brain.user.split('WHO WRITES IN')[1].split('\n\n')[0])   # the owner's own domain is not a vendor
        self.assertIn('SFTP', brain.system); self.assertIn('Never a protocol', brain.system)

    def test_long_sent_mail_never_pushes_the_vendors_out_of_what_the_model_reads(self):
        """A real mailbox's sent-mail endings ran to 39K characters and the one 16K cut came after them: the model never saw who
        writes in, and named the one product the owner's own mail complained about (2026-10-16)."""
        s = MemoryStore()
        s.set_setting('owner_email', 'alex@northwind.example', 'owner')
        sent = [{'subject': 'Re: x', 'body': {'content': ('x' * 1500 + '\n') * 8 + 'Best,\nAlex Doyle'}} for _ in range(12)]
        msgs = [{'FromEmail': 'noreply@payworth.example', 'FromName': 'Payworth', 'Subject': 'Payroll import failed', 'Status': 'routed',
                 'BodyText': 'y' * 3000, 'SentAt': '2026-09-01 09:00:00'} for _ in range(60)]
        def brain(system, user, **kw):
            brain.user = user
            return json.dumps({'name': 'Alex Doyle', 'org': '', 'role': '', 'systems': []})
        with mock.patch('taskuary.histgen.sent_mail', return_value=(sent, [], 1, 'IMAP')), \
             mock.patch('taskuary.histgen._db_window', return_value=msgs), mock.patch('taskuary.llm.build_llm', return_value=brain):
            firstrun.suggest_about(s)
        self.assertIn('payworth.example: 60 mails', brain.user)
        self.assertIn('Alex Doyle', brain.user)                                       # the signature itself survives the cut
        self.assertLess(len(brain.user), 20000)

    def test_a_suggestion_that_fails_says_why_and_the_form_still_works(self):
        s = MemoryStore()
        with mock.patch('taskuary.histgen.sent_mail', side_effect=RuntimeError('no mail history yet')):
            out = firstrun.suggest_about(s)
        self.assertIn('no mail history yet', out['error'])

    def test_the_job_is_written_from_the_mail_once_the_role_is_known_and_its_state_is_said(self):
        s = MemoryStore()
        self.assertEqual(firstrun.job_state(s)['state'], 'none')
        names = []
        def gen(store, name, days=90):
            names.append(name)
            if name == 'job': learned(store)
        with mock.patch('taskuary.histgen.generate', side_effect=gen):
            firstrun.learn(s, {'name': 'Alex Doyle', 'org': 'Northwind', 'role': 'Finance systems lead'}, wait=True)
        self.assertEqual(names, ['job', 'style'])
        self.assertEqual((s.owner()['owner'], s.get_setting('owner_company')), ('Alex Doyle', 'Northwind'))
        st = firstrun.job_state(s)
        self.assertEqual(st['state'], 'ready'); self.assertTrue(st['text'].startswith('### What my job is')); self.assertNotIn('_generated', st['text'])

    def test_a_job_that_cannot_be_written_says_why(self):
        s = MemoryStore()
        with mock.patch('taskuary.histgen.generate', side_effect=RuntimeError('no mail history to learn the job from')):
            firstrun.learn(s, {'name': 'Alex Doyle', 'org': '', 'role': ''}, wait=True)
        st = firstrun.job_state(s)
        self.assertEqual(st['state'], 'failed'); self.assertIn('no mail history', st['why'])

    def test_only_the_name_guessed_from_the_address_is_open_to_the_mails_suggestion(self):
        s = MemoryStore()
        s.set_setting('owner_name', 'Alex', 'owner')                         # read off alex@... when the mail connected
        self.assertEqual(firstrun.about(s)['guessed'], ['name'])
        firstrun._who(s, {'name': 'Alex Doyle'})
        self.assertEqual(firstrun.about(s)['guessed'], [])                   # answered: a reload never puts the guess back

    def test_the_mailbox_step_lists_every_mailbox_connected_and_switched_on(self):
        """EVERY MAILBOX BEFORE THE JOB (the owner, 2026-10-20): setup's mailbox step lists what is connected so far - each Gmail and
        IMAP card's own, an Outlook card's mailboxes - once each, and never a card switched off."""
        s = mailboxes(MemoryStore(), ('gmail', 'alex.doyle@mail.example'), ('imap', 'alex@northwind.example'), ('imap', 'ALEX@northwind.example'))
        off = s.get_connector_by_type('outlook')['ConnectorId']
        s.save_source({'Channel': 'email', 'Address': 'shared@northwind.example', 'Active': 1, 'ConnectorId': off}, 't')   # its card is off
        self.assertEqual(firstrun.state(s)['mailboxes'], [{'address': 'alex.doyle@mail.example', 'type': 'gmail'},
                                                          {'address': 'alex@northwind.example', 'type': 'imap'}])

    def test_the_job_is_learned_from_every_mailbox_with_a_section_per_organisation(self):
        """JOB.md FROM EVERY MAILBOX (the owner, 2026-10-20): an Outlook mailbox at one organisation and an IMAP one at another are two
        jobs - each section written from its own mailbox's mail alone, the Outlook card no longer ending the read."""
        s = mailboxes(MemoryStore(), ('outlook', 'alex@northwind.example'), ('imap', 'alex@riverside.example'))
        s.set_setting('owner_email', 'alex@northwind.example', 'owner')
        graph_sent = [{'subject': 'Re: month-end close', 'receivedDateTime': '2026-10-01T10:00:00Z', 'conversationId': 'n1',
                       'toRecipients': [{'emailAddress': {'address': 'erin@northwind.example', 'name': 'Erin Blake'}}],
                       'body': {'content': 'Signed off the accruals.'}, 'mailbox': 'alex@northwind.example'}]
        graph_in = [{'subject': 'Month-end close', 'receivedDateTime': '2026-10-01T09:00:00Z', 'conversationId': 'n1', 'mailbox': 'alex@northwind.example',
                     'from': {'emailAddress': {'address': 'erin@northwind.example', 'name': 'Erin Blake'}}}]
        imap_sent = [{'subject': 'Board minutes', 'sent_at': '2026-10-02 08:00:00', 'conversation_id': 'r1', 'from_email': 'alex@riverside.example',
                      'to': ['ray@riverside.example'], 'body': 'Minutes attached for the volunteer board.'}]
        imap_in = [{'FromEmail': 'ray@riverside.example', 'FromName': 'Ray Colton', 'Subject': 'Volunteer rota', 'Status': 'routed',
                    'BodyText': 'Can you draw up the rota?', 'SentAt': '2026-10-02 07:00:00', 'SourceName': 'alex@riverside.example',
                    'ConversationId': 'r1'}]
        asked = []
        def brain(system, user, **kw):
            if 'JOB IS' not in system: return STYLE_GUIDE
            asked.append((system, user))
            org = 'Northwind' if 'work at Northwind' in user else 'riverside'
            return f'### What my job is\n- I do the {org} work, every week, and answer the people there who depend on it being done right.'
        with mock.patch('taskuary.histgen._graph_mail', return_value=(graph_sent, graph_in, 1)), \
             mock.patch('taskuary.imapmail.sent_history', return_value=imap_sent), \
             mock.patch('taskuary.histgen._db_window', return_value=imap_in), mock.patch('taskuary.llm.build_llm', return_value=brain):
            firstrun.learn(s, {'name': 'Alex Doyle', 'org': 'Northwind', 'role': 'Finance lead'}, wait=True)
        self.assertEqual(firstrun.job_state(s)['state'], 'ready')
        job = firstrun.about(s)['job']
        self.assertEqual(job.count('\n## ') + job.startswith('## '), 2, job)
        self.assertLess(job.index('## At Northwind (alex@northwind.example)'), job.index('## At riverside.example (alex@riverside.example)'))
        self.assertIn('I do the Northwind work', job); self.assertIn('I do the riverside work', job)
        (sys1, north), (_s, river) = asked
        self.assertIn('ONE OF SEVERAL JOBS', sys1)
        # each organisation read from its own mailbox: Northwind's colleagues never in the other's evidence, and the reverse
        self.assertIn('erin@northwind.example', north); self.assertNotIn('ray@riverside.example', north)
        self.assertIn('ray@riverside.example', river); self.assertNotIn('erin@northwind.example', river)
        self.assertIn('Finance lead', north); self.assertNotIn('Finance lead', river)     # the title setup was told is the owner's own org's

    def test_one_organisation_is_one_job_as_before(self):
        s = mailboxes(MemoryStore(), ('gmail', 'alex@northwind.example'), ('imap', 'ap@northwind.example'))
        from taskuary import histgen
        self.assertEqual(histgen.org_groups(s), [('northwind.example', ['alex@northwind.example', 'ap@northwind.example'])])

    def test_the_systems_offered_are_the_catalogues_corporate_ones(self):
        offered = firstrun.about(MemoryStore())['offered']
        self.assertTrue(len(offered) >= 8); self.assertTrue(all(isinstance(x, str) and x for x in offered))


class FinishTests(unittest.TestCase):
    def test_setup_stays_until_the_owner_finishes_it(self):
        s = MemoryStore()
        self.assertFalse(firstrun.state(s)['dismissed'])
        firstrun.finish(s)
        self.assertTrue(firstrun.state(s)['dismissed'])

    def test_an_install_already_working_before_this_is_treated_as_finished(self):
        """The finish button is new: an install that set up before it must not open on setup again."""
        s = MemoryStore()
        with mock.patch.object(firstrun, 'state', return_value={'step': 'done'}):
            firstrun.settle_existing(s)
        self.assertEqual(s.get_setting('first_run_dismissed'), '1')
        t = MemoryStore()
        with mock.patch.object(firstrun, 'state', return_value={'step': 'ai'}):
            firstrun.settle_existing(t)
        self.assertEqual(t.get_setting('first_run_dismissed'), '0')
        with mock.patch.object(firstrun, 'state', return_value={'step': 'done'}):
            firstrun.settle_existing(t)                                  # once decided, never re-decided
        self.assertEqual(t.get_setting('first_run_dismissed'), '0')

    def test_a_finished_install_that_never_answered_about_your_work_opens_setup_on_it_once(self):
        """An install settled as finished before About your work existed never saw it - setup reopens once for it, and the owner's
        Finish closes it for good."""
        s = MemoryStore()
        s.set_setting('first_run_dismissed', '1', 'system')
        firstrun.offer_about(s)
        self.assertEqual(s.get_setting('first_run_dismissed'), '0')
        firstrun.finish(s); firstrun.offer_about(s)                      # offered once: Finish without answering is final
        self.assertEqual(s.get_setting('first_run_dismissed'), '1')
        t = MemoryStore()
        t.set_setting('first_run_dismissed', '1', 'system')
        firstrun.save_about(t, ANSWERS)
        firstrun.offer_about(t)                                           # answered already: nothing to reopen
        self.assertEqual(t.get_setting('first_run_dismissed'), '1')


if __name__ == '__main__': unittest.main()


class SuggestConnectionsTests(unittest.TestCase):
    """More connections is the Connections page itself, and the Advisor's line over the row says which to connect, from the survey
    and the job (the owner, 2026-10-15: "use ai to process their survey questions and then suggest what softwares they use ... advisor
    is what tells you what to do next always")."""
    def setUp(self):
        self.s = MemoryStore()
        firstrun.save_about(self.s, ANSWERS)

    def test_the_ai_reads_the_answers_and_names_the_cards_and_their_sections(self):
        def brain(system, user, **kw):
            brain.user = user
            return json.dumps({'line': 'You work in Workday and Salesforce - connect those first.', 'picks': ['workday', 'salesforce', 'nosuch']})
        with mock.patch('taskuary.llm.build_llm', return_value=brain):
            out = firstrun.suggest_connections(self.s)
        self.assertIn('Workday', brain.user); self.assertIn('Finance systems lead', brain.user)
        self.assertEqual(out['line'], 'You work in Workday and Salesforce - connect those first.')
        self.assertEqual([p['type'] for p in out['picks']], ['workday', 'salesforce'])          # an unknown card is dropped
        self.assertTrue(all(p['group'] and p['title'] for p in out['picks']))

    def test_the_ais_sentence_stands_even_when_it_picks_nothing(self):
        """Every system the owner named was planned, the AI said so and picked none - and its sentence was dropped for the plain
        "You said you work in..." line (a fresh-install walk, 2026-10-16). And it is asked for cards that CAN connect, too."""
        def brain(system, user, **kw):
            brain.system = system
            return json.dumps({'line': "Workday and Salesforce can't be connected yet - nothing else fits your work for now.", 'picks': []})
        with mock.patch('taskuary.llm.build_llm', return_value=brain):
            out = firstrun.suggest_connections(self.s)
        self.assertEqual(out, {'line': "Workday and Salesforce can't be connected yet - nothing else fits your work for now.", 'picks': []})
        self.assertIn('can be connected now', brain.system)

    def test_more_connections_counts_what_is_connected_beyond_the_ai_and_the_mail(self):
        """The rail never ticked More connections, however many were set up - it was optional, so never done (the owner, 2026-10-16:
        "i have many more connections setup, why is it still not checked")."""
        self.assertEqual(firstrun.more_connected(self.s), 0)
        for t in ('outlook', 'azure_openai', 'handbook', 'intacct', 'teams'):
            cid = self.s.get_connector_by_type(t)['ConnectorId']; self.s.save_connector({'ConnectorId': cid, 'Active': 1}, 'o')
        self.assertEqual(firstrun.more_connected(self.s), 2)                     # Sage Intacct and Teams: not the AI, the mail or the Hub

    def test_a_generic_transfer_or_storage_card_is_never_a_system_or_a_suggestion(self):
        """"SFTP is the best next connection" - SFTP is how files move, not a system one works in (the owner, 2026-10-16: "remove
        this sftp because it can be many systems")."""
        self.assertFalse({'SFTP', 'Network file share'} & set(firstrun.about(self.s)['offered']))
        with mock.patch('taskuary.llm.build_llm', return_value=lambda system, user, **kw: json.dumps(
                {'line': 'Connect SFTP and Sage Intacct.', 'picks': ['sftp', 'smb_file', 'intacct']})):
            out = firstrun.suggest_connections(self.s)
        self.assertEqual([p['type'] for p in out['picks']], ['intacct'])

    def test_with_no_ai_the_systems_ticked_are_matched_to_the_catalogue(self):
        with mock.patch('taskuary.llm.build_llm', side_effect=RuntimeError('no brain')):
            out = firstrun.suggest_connections(self.s)
        titles = [p['title'] for p in out['picks']]
        self.assertIn('Workday', titles); self.assertIn('Salesforce', titles)
        self.assertIn('Workday', out['line'])


class FirstDigestTests(unittest.TestCase):
    """Finishing setup writes the day's Morning digest once the mail is sorted, and the opener says it waits for that (the owner,
    2026-10-15: "run morning digest - say running in not yet processed")."""
    def test_finish_makes_the_report_once_and_a_deleted_one_stays_deleted(self):
        s = MemoryStore()
        sid = firstrun.ensure_digest(s)
        self.assertEqual(json.loads(s.get_source(sid)['ConfigJson'])['type'], 'digest')
        self.assertEqual(firstrun.ensure_digest(s), sid)                         # never a second one
        s.save_source({'SourceId': sid, 'Active': 0}, 'owner')                     # the owner switched it off
        self.assertIsNone(firstrun.ensure_digest(s))

    def test_it_waits_on_the_sorting_then_writes_and_says_so_meanwhile(self):
        from taskuary import since
        s, ran, gate = MemoryStore(), [], {'n': 3}
        with mock.patch.object(firstrun, '_sorting', side_effect=lambda st: gate['n']),              mock.patch('threading.Thread') as T:
            sid = firstrun.first_digest(s, ran.append, wait=60, tick=0)
            go = T.call_args.kwargs['target']
            self.assertEqual(since.digest(s)['waiting'], 3); self.assertTrue(since.digest(s)['writing'])
            with mock.patch('time.sleep', side_effect=lambda _: gate.update(n=0)): go()
        self.assertEqual([r['SourceId'] for r in ran], [sid])
        self.assertIsNone(firstrun.digest_waiting(s, sid))

    def test_one_written_today_is_not_written_again(self):
        from datetime import datetime
        s = MemoryStore(); sid = firstrun.ensure_digest(s)
        s.add_report_run(sid, {'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'message_id': 7, 'failed': False})
        with mock.patch('threading.Thread') as T:
            firstrun.first_digest(s, lambda src: None)
        T.assert_not_called()
