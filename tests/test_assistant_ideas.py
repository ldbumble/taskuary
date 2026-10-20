"""The REPORT proposes, the chat assistant never does (the assistant-runs-the-app design, 2026-09-18):
the app's own health, read off the tables, and a system worth connecting, which the Advisor's own pass
judges from the month's threads - one row each, declined once and remembered."""
import json, re, unittest
from datetime import datetime

from taskuary import assistant, connectorcatalog
from taskuary.store import MemoryStore
import tests.test_appfacts as A


class CatalogueTests(unittest.TestCase):
    def test_the_catalogue_is_one_file_with_every_card_grouped(self):
        cards = connectorcatalog.cards()
        self.assertGreater(len(cards), 150)
        for c in cards:
            for f in ('type', 'title', 'group', 'match'): self.assertTrue(c.get(f), f"{c.get('type')} lacks {f}")
        self.assertEqual(connectorcatalog.by_type('adp')['group'], 'Corporate systems')
        self.assertTrue(connectorcatalog.by_type('adp')['planned'])
        self.assertFalse(connectorcatalog.by_type('outlook')['planned'])
        self.assertEqual(connectorcatalog.by_type('mssql')['group'], 'Databases')      # the tab's own section, not "Everything else"


class HealthTests(unittest.TestCase):
    def test_three_failures_and_a_never_run_workflow_each_raise_one_row_and_a_connection_is_the_rails_alone(self):
        s = A.store()
        for _ in range(2):
            s.add_report_run(A.AR['sid'], {'at': '2026-09-18 07:00:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'login timed out'})
        s.add_report_run(A.AR['sid'], {'at': '2026-09-18 08:00:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'login timed out'})
        wf = s.save_source({'Channel': 'report', 'Address': 'wf2', 'Active': 1, 'ConfigJson': json.dumps({'title': 'Nightly sync', 'type': 'agent', 'access': 'write', 'cron': '0 1 * * *'})}, 't')
        cid = s.save_connector({'Type': 'teams', 'Name': 'Teams live', 'Active': 1, 'ConfigJson': '{}', 'Secret': 'x'}, 't')
        s._exec('UPDATE connector SET LastError=? WHERE ConnectorId=?', ('token expired', cid))
        # a workflow is not "never run" the minute it is saved: it waits a day from when the Advisor first saw it
        self.assertNotIn(f'health:workflow:{wf}', {i['key'] for i in assistant.health_ideas(s)})
        from datetime import timedelta
        ideas = {i['key']: i for i in assistant.health_ideas(s, datetime.now() + timedelta(days=1, minutes=1))}
        self.assertIn('failed its last three runs', ideas[f"health:report:{A.AR['sid']}"]['text'])
        self.assertEqual(ideas[f"health:report:{A.AR['sid']}"]['action']['tab'], 'Reports')
        self.assertIn('never run', ideas[f'health:workflow:{wf}']['text'])
        # the rail's "stopped answering" row says this; an idea too became a task and an agent (2026-09-30)
        self.assertNotIn(f'health:connection:{cid}', ideas)
        from taskuary import funnel
        self.assertIn('Teams stopped answering', [r['title'] for r in funnel.broken_connections(s)])
        # the ADP workflow in the fixture failed ONCE: one failure is a bad day, not a broken report
        self.assertNotIn('health:workflow:' + str([r for r in A.appfacts.reports(s) if r['title'] == 'ADP hours export'][0]['source_id']), ideas)

    def test_a_report_that_keeps_failing_the_same_way_is_one_idea_said_once(self):
        # the owner, 2026-09-28: "as long as it's not the same idea a 100 times" - the sig was the last run's time
        from datetime import datetime
        s, now, key = A.store(), datetime.now(), f"health:report:{A.AR['sid']}"
        def fail(at, err):
            s.add_report_run(A.AR['sid'], {'at': at, 'title': 'Monthly AR Report', 'failed': True, 'error': err})
            return next(i for i in assistant.health_ideas(s) if i['key'] == key)
        for h in (6, 7): s.add_report_run(A.AR['sid'], {'at': f'2026-09-18 0{h}:00:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'x'})
        s.upsert_idea(fail('2026-09-18 08:00:00', 'login timed out after 30s'), '2026-09-18 08:00:00')
        state = {i['Key']: i for i in s.list_ideas()}
        self.assertFalse(assistant.fresh(state, fail('2026-09-18 09:00:00', 'login timed out after 31s'), now))   # the same failure
        self.assertTrue(assistant.fresh(state, fail('2026-09-18 10:00:00', 'the password was changed'), now))     # a new one

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
    """A system worth connecting is the Advisor's own call (the owner, 2026-10-11: "should be ai as well"). The month's
    threads ride in its prompt numbered beside the cards nothing reads; it cites the threads really about one, and code
    only checks the citation: an offered card, threads that exist, the floor, never one raised before, one a run."""
    def _mail(self, s, n, subject, email='hr@payroll.example'):
        for i in range(n):
            s.add_message({'ExternalId': f'x:{subject}:{i}', 'Channel': 'email', 'SourceName': 'inbox', 'Subject': subject,
                           'FromName': 'Payroll', 'FromEmail': email, 'SentAt': '2026-09-17 09:00:00', 'BodyText': '.', 'Status': 'routed'})

    def _advise(self, s, say):
        """Run the Advisor with a model that answers `say(user, nums)` - nums maps each subject to its T numbers."""
        seen = {}
        def llm(system, user, **k):
            if 'SYSTEMS NOTHING HERE READS' not in user: return json.dumps({'say': []})
            seen['user'] = user
            nums = {}
            for n, subj in re.findall(r'^\[T(\d+)\] [^|]*\| (.*)$', user, re.M): nums.setdefault(subj.strip(), []).append(int(n))
            return json.dumps({'say': say(user, nums)})
        out = assistant.run(s, llm=llm, force=True)
        return {i['Key']: i for i in s.list_ideas() if i['Key'].startswith('connect:')}, seen.get('user', ''), out

    def test_a_holiday_on_a_monday_is_not_monday_com_unless_the_model_cites_it(self):
        """2026-09-25: three holiday notices became "3 threads this month were about Monday.com" off a name match."""
        s = A.store()
        self._mail(s, 3, 'Federal Holiday - Monday October 12th', 'hr@northwind.example')
        self._mail(s, 3, 'Labor Day Holiday - Monday September 7th', 'news@calendar.example')
        ideas, user, _ = self._advise(s, lambda u, nums: [{'key': 'connect:monday', 'text': 'x', 'threads': []}])
        self.assertIn('Federal Holiday - Monday October 12th', user)                     # the model read the threads
        self.assertIn('monday: ', user)                                                  # ...and the card it could raise
        self.assertEqual(ideas, {})                                                      # nothing cited: nothing posted

    def test_the_count_is_the_threads_the_model_cited(self):
        s = A.store()
        self._mail(s, 1, 'ADP payroll register ready'); self._mail(s, 1, 'ADP hours export late')
        self._mail(s, 1, 'ADP year-end forms'); self._mail(s, 1, 'Quarterly adapter recall', 'ops@parts.example')
        cite = lambda u, nums: [{'key': 'connect:adp', 'text': 'Payroll mail arrives weekly.', 'why': 'three payroll threads',
                                 'threads': nums['ADP payroll register ready'] + nums['ADP hours export late'] + nums['ADP year-end forms'] + [999]}]
        ideas, _, _ = self._advise(s, cite)
        i = ideas['connect:adp']; a = json.loads(i['ActionJson'])
        self.assertTrue(i['Text'].startswith('3 threads this month were about ADP'), i['Text'])   # 999 does not exist: not counted
        self.assertEqual(a['count'], 3); self.assertTrue(a['planned']); self.assertEqual(a['connector_type'], 'adp')

    def test_under_the_floor_is_dropped_unless_the_owners_own_setup_names_it(self):
        s = A.store()
        self._mail(s, 2, 'ADP payroll register ready')
        two = lambda u, nums: [{'key': 'connect:adp', 'text': 'x', 'threads': nums['ADP payroll register ready']}]
        self.assertEqual(self._advise(s, two)[0], {})                                    # two threads, floor three
        def named(u, nums):
            n = re.search(r'^\[N(\d+)\] report: ADP hours export$', u, re.M).group(1)   # the fixture's own workflow
            return [{'key': 'connect:adp', 'text': 'x', 'threads': nums['ADP payroll register ready'], 'named_in': [f'N{n}']}]
        ideas = self._advise(s, named)[0]
        self.assertTrue(ideas['connect:adp']['Text'].startswith('2 threads this month were about ADP'))

    def test_an_invented_or_connected_type_is_dropped_and_one_a_run_is_kept(self):
        s = A.store()
        self._mail(s, 4, 'ADP payroll register ready'); self._mail(s, 4, 'Salesforce case escalated', 'noreply@crm.example')
        ideas, user, _ = self._advise(s, lambda u, nums: [
            {'key': 'connect:frobnicator', 'text': 'x', 'threads': nums['ADP payroll register ready']},
            {'key': 'connect:outlook', 'text': 'x', 'threads': nums['ADP payroll register ready']},     # connected in the fixture
            {'key': 'connect:adp', 'text': 'x', 'threads': nums['ADP payroll register ready']},
            {'key': 'connect:salesforce', 'text': 'x', 'threads': nums['Salesforce case escalated']}])
        self.assertEqual(list(ideas), ['connect:adp'])
        self.assertNotIn('\noutlook: ', user)                                            # a connected card is never offered

    def test_one_already_raised_is_never_offered_or_posted_again(self):
        s = A.store()
        self._mail(s, 4, 'ADP payroll register ready')
        cite = lambda u, nums: [{'key': 'connect:adp', 'text': 'x', 'threads': nums['ADP payroll register ready']}]
        ideas = self._advise(s, cite)[0]
        s.set_idea_status(ideas['connect:adp']['IdeaId'], 'done', 'owner')              # "not for us"
        ideas, user, _ = self._advise(s, cite)
        self.assertNotIn('\nadp: ', user)
        self.assertEqual(ideas['connect:adp']['Status'], 'done')                         # still the one the owner put down
        self.assertFalse(assistant.fresh({i['Key']: i for i in s.list_ideas()}, {'key': 'connect:adp', 'sig': 'adp'}, datetime.now()))

    def test_no_brain_no_suggestion(self):
        s = A.store()
        self._mail(s, 5, 'ADP payroll register ready')
        assistant.run(s, llm=None, force=True)
        self.assertEqual([i['Key'] for i in s.list_ideas() if i['Key'].startswith('connect:')], [])

    def test_one_conversation_is_one_thread_and_my_own_post_is_none(self):
        """Three replies on one pull request were three threads (TQ-0651), and the Advisor's own post was read as a thread
        about the system it named."""
        s = A.store()
        for i in range(4):
            s.add_message({'ExternalId': f'pr:{i}', 'ConversationId': 'pr-1736', 'Channel': 'email', 'SourceName': 'inbox',
                           'Subject': 'Re: ADP payroll register ready', 'FromName': 'Payroll', 'FromEmail': 'hr@payroll.example',
                           'SentAt': '2026-09-17 09:00:00', 'BodyText': '.', 'Status': 'routed'})
            s.add_message({'ExternalId': f'a:{i}', 'Channel': 'assistant', 'SourceName': 'Assistant', 'FromName': 'Assistant',
                           'Subject': '6 threads this month were about ADP and nothing here reads it.',
                           'SentAt': '2026-09-17 09:00:00', 'BodyText': '.', 'Status': 'routed'})
        self.assertEqual(assistant.connect_evidence(s)['threads'], ['payroll.example | Re: ADP payroll register ready'])

    def test_the_word_matcher_is_gone(self):
        for f in ('mentions', 'words', 'GENERIC', '_patterns', '_toks'): self.assertFalse(hasattr(connectorcatalog, f), f)
        self.assertFalse(hasattr(assistant, 'connect_ideas'))


class RunTests(unittest.TestCase):
    def test_the_report_posts_them_beside_its_other_ideas_without_a_model(self):
        s = A.store()
        for at in ('06:00', '07:00', '08:00'):
            s.add_report_run(A.AR['sid'], {'at': f'2026-09-18 {at}:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'login timed out'})
        out = assistant.run(s, llm=None, force=True)
        keys = [i['Key'] for i in s.list_ideas()]
        self.assertIn(f"health:report:{A.AR['sid']}", keys)
        self.assertGreaterEqual(out.get('said', 0), 1)

    def test_the_card_reads_the_lines_before_they_post_and_a_no_puts_them_down(self):
        """2026-09-20: the routing card's Timeline line is asked BEFORE the post. It no longer holds the post back
        (the owner, 2026-09-28): the post is made, every idea is triaged, and a no puts down each idea triage made
        no task of - a task or nothing, as for any report."""
        s = A.store()
        for at in ('06:00', '07:00', '08:00'):
            s.add_report_run(A.AR['sid'], {'at': f'2026-09-18 {at}:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'login timed out'})
        seen = []
        def judge(lines, n): seen.append((lines, n)); return {'timeline': False, 'why': ''}
        out = assistant.run(s, llm=None, force=True, judge=judge)
        self.assertGreaterEqual(out['said'], 1); self.assertTrue(out.get('message_id')); self.assertNotIn('held', out)
        self.assertEqual(seen[0][1], out['said']); self.assertIn('why:', seen[0][0])
        self.assertTrue(s.list_ideas() and all(i['Status'] == 'done' for i in s.list_ideas()))

    def test_timeline_yes_posts_the_news_and_leaves_the_ideas_standing(self):
        # no idea carries a work flag of its own any more: whether it is work is triage's call (2026-09-28)
        s = A.store()
        for at in ('06:00', '07:00', '08:00'):
            s.add_report_run(A.AR['sid'], {'at': f'2026-09-18 {at}:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'login timed out'})
        out = assistant.run(s, llm=None, force=True, judge=lambda lines, n: {'timeline': True})
        self.assertGreaterEqual(out['said'], 1); self.assertTrue(out.get('message_id'))
        self.assertTrue(all(i['Status'] != 'done' and 'work' not in json.loads(i['ActionJson']) for i in s.list_ideas()))

    def test_a_judge_that_fails_leaves_the_post_reaching_you(self):
        s = A.store()
        for at in ('06:00', '07:00', '08:00'):
            s.add_report_run(A.AR['sid'], {'at': f'2026-09-18 {at}:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'login timed out'})
        def judge(lines, n): raise RuntimeError('no brain')
        out = assistant.run(s, llm=None, force=True, judge=judge)
        self.assertGreaterEqual(out['said'], 1); self.assertNotIn('decided', out)


if __name__ == '__main__':
    unittest.main()
