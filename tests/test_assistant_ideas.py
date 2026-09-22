"""The REPORT proposes, the chat assistant never does (the assistant-runs-the-app design, 2026-09-18):
the app's own health, and a system worth connecting - read off the tables, one row each, declined once
and remembered."""
import json, unittest
from datetime import datetime

from taskuary import assistant, connectorcatalog
from taskuary.store import MemoryStore
import tests.test_appfacts as A


class CatalogueTests(unittest.TestCase):
    def test_the_catalogue_is_one_file_with_every_card_grouped_and_matchable(self):
        cards = connectorcatalog.cards()
        self.assertGreater(len(cards), 150)
        for c in cards:
            for f in ('type', 'title', 'group', 'match'): self.assertTrue(c.get(f), f"{c.get('type')} lacks {f}")
        self.assertEqual(connectorcatalog.by_type('adp')['group'], 'Corporate systems')
        self.assertTrue(connectorcatalog.by_type('adp')['planned'])
        self.assertFalse(connectorcatalog.by_type('outlook')['planned'])
        self.assertEqual(connectorcatalog.by_type('mssql')['group'], 'Databases')      # the tab's own section, not "Everything else"

    def test_mentions_count_whole_words_once_per_text(self):
        hits = connectorcatalog.mentions(['ADP hours export is late', 'adp again', 'the adapter broke', 'Payworth ESS link'])
        self.assertEqual(hits.get('adp'), 2)                                            # "adapter" is not ADP
        self.assertNotIn('adp', connectorcatalog.mentions(['adp'], exclude_types={'adp'}))

    def test_a_generic_word_is_not_a_system_and_every_card_keeps_its_own_title(self):
        """"can you share the file?" counted as a thread about the SMB share until the words a title
        splits into were filtered - 26 of them, which is how this became an idea (TQ-0647)."""
        ordinary = ['please share the file', 'the network is down again', 'any update on the data?',
                    'card declined at the bank', 'search the web for it',
                    # TQ-0650: an app about messages cannot read the bare word as a Mac-only channel
                    '12 messages waiting', 'no messages from the vendor since Tuesday',
                    'Your Apple ID was used to sign in', 'Apple sent a receipt for the subscription']
        self.assertEqual(connectorcatalog.mentions(ordinary), {})
        self.assertEqual(connectorcatalog.mentions(['the network file share is full']).get('smb_file'), 1)
        self.assertEqual(connectorcatalog.mentions(['SMB share on fileserv']).get('smb_file'), 1)
        self.assertEqual(connectorcatalog.mentions(['can you read Apple Messages?']).get('imessage'), 1)
        self.assertEqual(connectorcatalog.mentions(['it came over iMessage']).get('imessage'), 1)
        for c in connectorcatalog.cards():
            self.assertTrue(connectorcatalog.words(c), f"{c['type']} has no match word left")
            self.assertIn(c['type'], connectorcatalog.mentions([c['title']]), f"{c['type']} no longer matches its own title")

    def test_a_word_split_out_of_a_title_names_the_vendor_not_the_product(self):
        """Three replies to "add Taskuary interactive demo" became "3 threads about Interactive
        Brokers"; "you have new requests" became New Relic; every mail from microsoft.com became
        Microsoft Planner AND Microsoft 365 files (TQ-0651). A blocklist could not keep up - it had
        already taken 26 words and missed these."""
        self.assertEqual(connectorcatalog.mentions([
            'Re: [org/app] feat: add Taskuary interactive demo (PR #1736)',
            'you have new requests from your team', 'microsoft Refresh succeeded with critical warnings',
            'the brokers sent the renewal quote', 'sage advice from the planner', 'amazon your order has shipped',
        ]), {})
        # and the systems themselves still answer to their own names
        for text, typ in [('Interactive Brokers margin call', 'ibkr'), ('open an IBKR account', 'ibkr'),
                          ('New Relic alert: apdex below threshold', 'new_relic'), ('Charles Schwab statement', 'schwab'),
                          ('Sage Intacct close is done', 'intacct'), ('the Intacct journal', 'intacct'),
                          ('PointClickCare census export', 'pointclickcare'), ('Microsoft Planner board', 'ms_planner'),
                          ('Replicate ran the model', 'replicate_image'), ('Elasticsearch is down', 'elastic')]:
            self.assertEqual(connectorcatalog.mentions([text]).get(typ), 1, f"{typ} lost its own name in {text!r}")


class HealthTests(unittest.TestCase):
    def test_three_failures_a_never_run_workflow_and_an_erroring_connection_each_raise_one_row(self):
        s = A.store()
        for _ in range(2):
            s.add_report_run(A.AR['sid'], {'at': '2026-09-18 07:00:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'login timed out'})
        s.add_report_run(A.AR['sid'], {'at': '2026-09-18 08:00:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'login timed out'})
        wf = s.save_source({'Channel': 'report', 'Address': 'wf2', 'Active': 1, 'ConfigJson': json.dumps({'title': 'Nightly sync', 'type': 'agent', 'access': 'write', 'cron': '0 1 * * *'})}, 't')
        cid = s.save_connector({'Type': 'teams', 'Name': 'Teams live', 'Active': 1, 'ConfigJson': '{}', 'Secret': 'x'}, 't')
        s._exec('UPDATE connector SET LastError=? WHERE ConnectorId=?', ('token expired', cid))
        ideas = {i['key']: i for i in assistant.health_ideas(s)}
        self.assertIn('failed its last three runs', ideas[f"health:report:{A.AR['sid']}"]['text'])
        self.assertEqual(ideas[f"health:report:{A.AR['sid']}"]['action']['tab'], 'Reports')
        self.assertIn('never run', ideas[f'health:workflow:{wf}']['text'])
        self.assertIn('token expired', ideas[f'health:connection:{cid}']['text'])
        self.assertEqual(ideas[f'health:connection:{cid}']['action']['hash'], 'connector=teams')
        # the ADP workflow in the fixture failed ONCE: one failure is a bad day, not a broken report
        self.assertNotIn('health:workflow:' + str([r for r in A.appfacts.reports(s) if r['title'] == 'ADP hours export'][0]['source_id']), ideas)

    def test_a_seen_failure_stays_seen_until_a_new_one(self):
        s = A.store()
        for at in ('06:00', '07:00', '08:00'):
            s.add_report_run(A.AR['sid'], {'at': f'2026-09-18 {at}:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'x'})
        idea = assistant.health_ideas(s)[0]
        row = s.upsert_idea(idea, '2026-09-18 09:00:00'); s.set_idea_status(row['IdeaId'], 'done', 'owner')
        state = {i['Key']: i for i in s.list_ideas()}
        self.assertFalse(assistant.fresh(state, idea, datetime.now()))
        s.add_report_run(A.AR['sid'], {'at': '2026-09-19 08:00:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'y'})
        self.assertTrue(assistant.fresh(state, assistant.health_ideas(s)[0], datetime.now()))


class ConnectTests(unittest.TestCase):
    def _mail(self, s, n, subject, email='hr@adp.com'):
        for i in range(n):
            s.add_message({'ExternalId': f'x:{subject}:{i}', 'Channel': 'email', 'SourceName': 'inbox', 'Subject': subject,
                           'FromName': 'ADP', 'FromEmail': email, 'SentAt': '2026-09-17 09:00:00', 'BodyText': '.', 'Status': 'routed'})

    def test_the_system_the_mail_names_most_is_suggested_once_and_not_after_a_no(self):
        s = A.store()
        self._mail(s, 4, 'ADP payroll register ready')
        self._mail(s, 2, 'Salesforce weekly pipeline', email='noreply@salesforce.com')
        ideas = assistant.connect_ideas(s)
        self.assertEqual(len(ideas), 1)
        self.assertEqual(ideas[0]['key'], 'connect:adp'); self.assertIn('ADP', ideas[0]['text'])
        self.assertTrue(ideas[0]['action']['planned']); self.assertGreaterEqual(ideas[0]['action']['count'], 4)
        row = s.upsert_idea(ideas[0], '2026-09-18 09:00:00'); s.set_idea_status(row['IdeaId'], 'done', 'owner')   # "not for us"
        self.assertEqual([i['key'] for i in assistant.connect_ideas(s)], [])                # salesforce is under the floor
        self._mail(s, 3, 'Salesforce case escalated', email='noreply@salesforce.com')
        self.assertEqual(assistant.connect_ideas(s)[0]['key'], 'connect:salesforce')       # the next one, never adp again
        state = {i['Key']: i for i in s.list_ideas()}
        self.assertFalse(assistant.fresh(state, {'key': 'connect:adp', 'sig': 'adp'}, datetime.now()))

    def test_a_connected_system_is_never_suggested(self):
        s = A.store()
        self._mail(s, 5, 'Outlook mail rules changed', email='admin@outlook.com')
        self.assertNotIn('connect:outlook', [i['key'] for i in assistant.connect_ideas(s)])

    def test_one_conversation_is_one_thread(self):
        """Three replies on one pull request were three threads, so "add Taskuary interactive demo"
        cleared a floor of three on its own (TQ-0651)."""
        s = A.store()
        for i in range(4):
            s.add_message({'ExternalId': f'pr:{i}', 'ConversationId': 'pr-1736', 'Channel': 'email', 'SourceName': 'inbox',
                           'Subject': 'Re: ADP payroll register ready', 'FromName': 'ADP', 'FromEmail': 'hr@adp.com',
                           'SentAt': '2026-09-17 09:00:00', 'BodyText': '.', 'Status': 'routed'})
        self.assertEqual([i['key'] for i in assistant.connect_ideas(s)], [])
        self._mail(s, 3, 'ADP hours export late')                                    # three separate ones do clear it
        self.assertEqual(assistant.connect_ideas(s)[0]['key'], 'connect:adp')

    def test_my_own_post_is_not_a_thread_about_anything(self):
        """The idea went onto the Timeline as a message, the next run counted it, and the count grew
        by one a day off its own words (TQ-0651)."""
        s = A.store()
        for i in range(4):
            s.add_message({'ExternalId': f'a:{i}', 'Channel': 'assistant', 'SourceName': 'Assistant', 'FromName': 'Assistant',
                           'Subject': '6 threads this month were about ADP and nothing here reads it.',
                           'SentAt': '2026-09-17 09:00:00', 'BodyText': '.', 'Status': 'routed'})
        self.assertEqual([i['key'] for i in assistant.connect_ideas(s)], [])

    def test_the_sentence_counts_threads_and_nothing_else(self):
        """Raised by a report title and SOUL.md with no mail behind it, the row said "3 threads this
        month" about threads that did not exist."""
        s = A.store()
        self._mail(s, 3, 'ADP payroll register ready')
        idea = assistant.connect_ideas(s)[0]
        self.assertTrue(idea['text'].startswith('3 threads this month'), idea['text'])


class RunTests(unittest.TestCase):
    def test_the_report_posts_them_beside_its_other_ideas_without_a_model(self):
        s = A.store()
        for at in ('06:00', '07:00', '08:00'):
            s.add_report_run(A.AR['sid'], {'at': f'2026-09-18 {at}:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'login timed out'})
        out = assistant.run(s, llm=None, force=True)
        keys = [i['Key'] for i in s.list_ideas()]
        self.assertIn(f"health:report:{A.AR['sid']}", keys)
        self.assertGreaterEqual(out.get('said', 0), 1)

    def test_the_card_reads_the_lines_before_they_post_and_a_no_holds_them(self):
        """2026-09-20: the routing card's Timeline line is asked BEFORE the post - a run held back
        posts nothing, marks no idea said, and the next check raises the same lines again."""
        s = A.store()
        for at in ('06:00', '07:00', '08:00'):
            s.add_report_run(A.AR['sid'], {'at': f'2026-09-18 {at}:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'login timed out'})
        seen = []
        def judge(lines, n): seen.append((lines, n)); return {'timeline': False, 'work': False, 'why': ''}
        out = assistant.run(s, llm=None, force=True, judge=judge)
        self.assertEqual((out['said'], 'message_id' in out), (0, False))
        self.assertGreaterEqual(out['held'], 1)
        self.assertEqual(seen[0][1], out['held']); self.assertIn('why:', seen[0][0])
        self.assertEqual(s.list_ideas(), [])
        again = assistant.run(s, llm=None, force=True, judge=lambda lines, n: {'timeline': True, 'work': True})
        self.assertGreaterEqual(again['said'], 1)

    def test_work_no_posts_the_news_and_raises_no_row_on_the_rail(self):
        from taskuary import funnel
        s = A.store()
        for at in ('06:00', '07:00', '08:00'):
            s.add_report_run(A.AR['sid'], {'at': f'2026-09-18 {at}:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'login timed out'})
        out = assistant.run(s, llm=None, force=True, judge=lambda lines, n: {'timeline': True, 'work': False})
        self.assertGreaterEqual(out['said'], 1); self.assertTrue(out.get('message_id'))
        self.assertTrue(all(json.loads(i['ActionJson']).get('work') is False for i in s.list_ideas()))
        self.assertEqual(funnel.from_forgotten(s, set(), set()), [])

    def test_a_judge_that_fails_leaves_the_post_reaching_you(self):
        s = A.store()
        for at in ('06:00', '07:00', '08:00'):
            s.add_report_run(A.AR['sid'], {'at': f'2026-09-18 {at}:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'login timed out'})
        def judge(lines, n): raise RuntimeError('no brain')
        out = assistant.run(s, llm=None, force=True, judge=judge)
        self.assertGreaterEqual(out['said'], 1); self.assertNotIn('decided', out)


if __name__ == '__main__':
    unittest.main()
