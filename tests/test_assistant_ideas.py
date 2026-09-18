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
        hits = connectorcatalog.mentions(['ADP hours export is late', 'adp again', 'the adapter broke', 'Viventium ESS link'])
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


class RunTests(unittest.TestCase):
    def test_the_report_posts_them_beside_its_other_ideas_without_a_model(self):
        s = A.store()
        for at in ('06:00', '07:00', '08:00'):
            s.add_report_run(A.AR['sid'], {'at': f'2026-09-18 {at}:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'login timed out'})
        out = assistant.run(s, llm=None, force=True)
        keys = [i['Key'] for i in s.list_ideas()]
        self.assertIn(f"health:report:{A.AR['sid']}", keys)
        self.assertGreaterEqual(out.get('said', 0), 1)


if __name__ == '__main__':
    unittest.main()
