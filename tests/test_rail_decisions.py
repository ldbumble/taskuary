"""The work rail's decision map, as the owner answered it (2026-09-25, R4/R5/R6/R14 and the meeting setting).

R4 "idea you dismissed or read of course should leave the rail" - and a draft decided on another page.
R5 "Auto-replies or withdrawn messages should be filtered out yes. Though maybe a setting?"
R6 "next should move it to passed and done should close it" - a stopped agent, which Next could not put down.
R14 "now we have your task, where task with no message belongs"
"For meeting it ends after 5 minutes make that a setting."
"""
import unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import funnel, processing_unread
from test_funnel import ago, mail, store


def settled():
    s = store()
    def settle():
        s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
    return s, settle


def rail(s, **kw):
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        return processing_unread.build(s, live_state=[], **kw)['items']


class DecidedLeavesTheRailTests(unittest.TestCase):
    def test_a_draft_decided_elsewhere_leaves_until_they_write_again(self):
        s, settle = settled()
        mid = mail(s, 'Lunch Thursday?', who='Gail Moreno', email='gail@northwind.example', hours=2)
        rid = s.add_review({'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Yes, noon works.'})
        settle()
        self.assertTrue(any(i.get('rid') == rid for i in rail(s)))
        s.decide_review(rid, 'rejected', None, 'owner')
        settle()
        self.assertFalse([i for i in rail(s) if i.get('mid') == mid], 'decided on the Review page - off the rail')
        mail(s, 'Re: Lunch Thursday?', who='Gail Moreno', email='gail@northwind.example', hours=0, conv='Lunch Thursday?')
        settle()
        self.assertTrue(rail(s), 'she wrote again - back')


class NoiseTests(unittest.TestCase):
    def test_an_auto_reply_is_off_the_rail_unless_the_setting_is_off(self):
        s, settle = settled()
        mail(s, 'Automatic reply: Invoice 42', who='Ray Colton', email='ray@vendor.example', hours=1)
        settle()
        self.assertEqual(rail(s), [])
        s.set_setting('rail_hide_noise', '0', 'owner'); funnel.invalidate()
        self.assertEqual(len(rail(s)), 1)

    def test_the_setting_is_in_the_schema(self):
        from taskuary import appfacts
        import json, os
        schema = json.load(open(os.path.join(os.path.dirname(appfacts.__file__), 'settings_schema.json'), encoding='utf-8'))
        keys = {k for g in (schema.values() if isinstance(schema, dict) else []) if isinstance(g, dict) for k in g}
        self.assertIn('rail_hide_noise', keys)
        self.assertIn('meeting_grace_minutes', keys)


class TaskWithNoMessageTests(unittest.TestCase):
    def test_it_is_your_task_and_carries_no_promoted_arrow(self):
        s, settle = settled()
        t = s.create_task({'Title': 'Renew the domain', 'Kind': 'task', 'Status': 'open'}, 'owner')
        settle()
        card = [i for i in rail(s) if i.get('tid') == t]
        self.assertEqual([(c['lane'], c['promoted']) for c in card], [('yours', False)])

    def test_a_task_waiting_on_them_says_so_on_the_rail(self):
        # the owner, 2026-09-25: the list said "waiting on them" and the rail "on you" - the rail had no lane for it
        s, settle = settled()
        t = s.create_task({'Title': 'Chase the signed contract', 'Kind': 'task', 'Status': 'waiting'}, 'owner')
        settle()
        self.assertEqual([c['lane'] for c in rail(s) if c.get('tid') == t], ['theirs'])


class MeetingGraceTests(unittest.TestCase):
    def test_how_long_a_started_meeting_stays_is_a_setting(self):
        s = store()
        start = (datetime.now() - timedelta(minutes=8)).strftime('%Y-%m-%dT%H:%M:%S')
        end = (datetime.now() + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M:%S')
        agenda = [{'start': start, 'end': end, 'subject': 'Month-end review', 'who': ['Erin Blake']}]
        with mock.patch.object(funnel, '_agenda', return_value=agenda):
            self.assertEqual(funnel.from_calendar(s, datetime.now()), [], 'five minutes by default')
            s.set_setting('meeting_grace_minutes', '15', 'owner')
            self.assertEqual(len(funnel.from_calendar(s, datetime.now())), 1)


class NextOnAMeetingHoldsItUntilItStartsTests(unittest.TestCase):
    def test_next_on_a_coming_meeting_is_quiet_until_it_starts(self):
        """The owner, 2026-09-28: "i should not have to dismiss invite a 100 times. once i click next within 15
        minutes it should not come back to actual time" - Next wrote a shown mark only mail and tasks read, so the
        meeting was back after every fyi batch."""
        from taskuary import concierge
        s, settle = settled()
        st = datetime.now() + timedelta(minutes=10)
        agenda = [{'start': st.strftime('%Y-%m-%dT%H:%M:%S'), 'end': (st + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M:%S'),
                   'subject': 'Month-end review', 'who': ['Erin Blake']}]
        mail(s, 'lunch on friday', who='Gail Moreno', email='gail@northwind.example', hours=1)
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        with mock.patch.object(funnel, '_agenda', return_value=agenda),              mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            first = concierge.surface(s, llm=lambda *a, **k: 'never')
            self.assertEqual(first['item']['kind'], 'meeting')
            concierge.surface(s, llm=lambda *a, **k: 'never', leaving=first['item']['key'])
            self.assertFalse([i for i in rail(s) if i['kind'] == 'meeting' and i['actionable']], 'not back before it starts')
            at = st + timedelta(minutes=1)
            back = [i for i in processing_unread.build(s, now=at, live_state=[])['items'] if i['kind'] == 'meeting']
            self.assertEqual([i['actionable'] for i in back], [True], 'back when it starts')


class StoppedGoesToPassedTests(unittest.TestCase):
    def test_next_puts_a_stopped_agent_in_passed_and_the_quiet_hours_bring_it_back(self):
        from taskuary import concierge
        s, settle = settled()
        s.upsert_agent('coder', 'coding', 'cli', '{}')
        t = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open', 'Assignee': 'agent:coder'}, 'o')
        mid = mail(s, 'export', who='Omar Keller', email='omar@northwind.example', hours=3, tid=t)
        s.add_route(mid, t, 'route', 1.0, 'triage: coding', [], 'triage')
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]), \
             mock.patch.object(funnel, 'agent_left', return_value=True):
            first = concierge.surface(s, llm=lambda *a, **k: 'never')
            self.assertEqual((first['item']['lane'], first['item']['tid']), ('stopped', t))
            concierge.surface(s, llm=lambda *a, **k: 'never', leaving=first['item']['key'])
            now = [(i['lane'], bool(i.get('surfaced')), i['actionable']) for i in rail(s) if i.get('tid') == t]
            self.assertEqual(now, [('stopped', True, False)], 'in Passed, not offered again')
            later = datetime.now() + timedelta(hours=4)
            back = [i['actionable'] for i in processing_unread.build(s, now=later, live_state=[])['items'] if i.get('tid') == t]
            self.assertEqual(back, [True])


class AStopAfterNextIsYoursTests(unittest.TestCase):
    def test_an_agent_that_stops_after_the_next_leaves_passed(self):
        """The owner, 2026-09-28: "If agent stopped working after a next it should shoot up to your task category" -
        a Next pressed before the agent stopped (or asked again) filed the new stop straight into Passed."""
        from taskuary import concierge
        s, settle = settled()
        s.upsert_agent('coder', 'coding', 'cli', '{}')
        t = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open', 'Assignee': 'agent:coder'}, 'o')
        mid = mail(s, 'export', who='Omar Keller', email='omar@northwind.example', hours=3, tid=t)
        s.add_route(mid, t, 'route', 1.0, 'triage: coding', [], 'triage')
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]),              mock.patch.object(funnel, 'agent_left', return_value=True):
            first = concierge.surface(s, llm=lambda *a, **k: 'never')
            concierge.surface(s, llm=lambda *a, **k: 'never', leaving=first['item']['key'])
            passed = [(i['lane'], bool(i.get('surfaced'))) for i in rail(s) if i.get('tid') == t]
            self.assertEqual(passed, [('stopped', True)], 'Next passed it')
            # the run speaks again after the pass: continued, then stopped with a question
            later = (datetime.now() + timedelta(minutes=2)).isoformat(sep=' ', timespec='seconds')
            with mock.patch('taskuary.store._now', return_value=later):
                s.add_worker_event({'TaskId': t, 'Sid': 's1', 'Kind': 'turn_end', 'Text': 'Done - one question for you.'})
            funnel.invalidate()
            now = [(i['lane'], bool(i.get('surfaced')), i['actionable']) for i in rail(s) if i.get('tid') == t]
            self.assertEqual(now, [('stopped', False, True)], 'a stop newer than the pass is in Your task')


class UrgentGoesToPassedTests(unittest.TestCase):
    def test_next_on_an_urgent_task_puts_it_in_passed(self):
        """R3: urgent open work left the rail for three hours on Next - Passed was for the other lanes only."""
        from taskuary import concierge
        s, settle = settled()
        t = s.create_task({'Title': 'Send the August financials', 'Kind': 'task', 'Status': 'open', 'Priority': 'urgent'}, 'triage')
        mid = mail(s, 'August financials', who='Paula Vance', email='paula@vendor.example', hours=1, tid=t)
        s.add_route(mid, t, 'route', 1.0, 'triage: task', [], 'triage')
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            first = concierge.surface(s, llm=lambda *a, **k: 'never')
            self.assertEqual(first['item']['tid'], t)
            concierge.surface(s, llm=lambda *a, **k: 'never', leaving=first['item']['key'])
            now = [(bool(i.get('surfaced')), i['actionable']) for i in rail(s) if i.get('tid') == t]
        self.assertEqual(now, [(True, False)], 'in Passed, not gone')


class RemindMeTests(unittest.TestCase):
    def test_remind_me_puts_away_a_live_agent_until_its_day(self):
        """R7: a working agent forced its row unread, whatever the date said."""
        from taskuary import remind
        s, settle = settled()
        t = s.create_task({'Title': 'Draft the vendor letter', 'Kind': 'general', 'Status': 'in_progress'}, 'o')
        mail(s, 'vendor letter', who='Gail Moreno', email='gail@northwind.example', hours=2, tid=t)
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        live = [{'taskId': t, 'agent': 'codex', 'label': 'codex', 'sid': 's1', 'mode': 'terminal', 'tail': []}]
        on = lambda: [i['unread'] for i in processing_unread.build(s, live_state=live, include_read=True)['items'] if i.get('tid') == t]
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            self.assertEqual(on(), [True])
            remind.set_reminder(s, t, 'monday'); settle()
            self.assertEqual(on(), [False], 'away until Monday, agent or not')

    def test_on_its_day_it_says_why_it_is_back(self):
        """R13: remind.due cleared the date as it filed the note, so the reason was never shown."""
        from taskuary import remind
        s, settle = settled()
        t = s.create_task({'Title': 'Renew the domain', 'Kind': 'task', 'Status': 'open'}, 'owner')
        s.update_task(t, {'RemindAt': ago(hours=1)}, 'owner')
        self.assertEqual(remind.due(s), 1); settle()
        self.assertEqual([i['why'] for i in rail(s) if i.get('tid') == t], ['you asked to be reminded about this today'])


class ErrorDismissTests(unittest.TestCase):
    def test_next_on_an_error_dismisses_it_and_a_different_error_comes_back(self):
        """R10: Next from the page wrote no sig, so the error after the dismissed one stayed hidden too."""
        s = store()
        c = s.get_connector_by_type('github')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Roles': 'trigger'}, 'test')
        s.touch_connector(c['ConnectorId'], 'northwind/ledger: 404 Not Found')
        key = f"conn:{c['ConnectorId']}"
        self.assertTrue([i for i in rail(s) if i['key'] == key])
        funnel.settle(s, key, 'surfaced', 'owner', read=True); funnel.invalidate()
        self.assertFalse([i for i in rail(s) if i['key'] == key], 'Next dismisses it')
        s.touch_connector(c['ConnectorId'], 'northwind/ledger: 401 Bad credentials'); funnel.invalidate()
        self.assertTrue([i for i in rail(s) if i['key'] == key], 'a different error is news again')


class NewWalkRaisesWavingAgentsTests(unittest.TestCase):
    def test_a_new_walk_clears_the_shown_mark_on_an_agent_waiting_on_you(self):
        """R11: the rail keys an agent's row processing:<item>, and reset_walk only ever cleared agent: keys."""
        s = store()
        s.set_funnel_state('processing:pi_1', 'surfaced', 'assistant')
        s.set_funnel_state('processing:pi_2', 'surfaced', 'assistant')
        pile = {'items': [{'key': 'processing:pi_1', 'lane': 'blocked'}, {'key': 'processing:pi_2', 'lane': 'fyi'}]}
        with mock.patch.object(processing_unread, 'build', return_value=pile):
            funnel.reset_walk(s)
        self.assertNotIn('processing:pi_1', s.funnel_states())
        self.assertEqual(s.funnel_states()['processing:pi_2']['Status'], 'surfaced', 'read stays read')


if __name__ == '__main__': unittest.main()


class AdvisorTaskWearsTheAdvisorMarkTests(unittest.TestCase):
    def test_a_task_the_advisor_raised_is_the_advisors_row_not_your_own_note(self):
        """The owner, 2026-09-28: "advisor should be more prominent" - its task wore the grey person of a note you wrote."""
        s, settle = settled()
        adv = s.create_task({'Title': 'Check the gateway retirement', 'Kind': 'general', 'Status': 'open',
                             'Source': 'assistant', 'SourceRef': 'assistant:idea:7'}, 'assistant')
        mine = s.create_task({'Title': 'Call the landlord', 'Kind': 'general', 'Status': 'open'}, 'owner')
        mail(s, 'lunch on friday', who='Gail Moreno', email='gail@northwind.example', hours=1)
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        by = {i.get('tid'): i.get('channel') for i in rail(s)}
        self.assertEqual((by.get(adv), by.get(mine)), ('assistant', 'own'))

    def test_a_report_run_that_joins_the_advisors_task_does_not_take_its_mark(self):
        """A later report run about the same failure joined an Advisor's task, and as the newest message it made the
        row a report (the owner, 2026-09-28: "why are these 2 advisor and report same logo on rail?")."""
        s, settle = settled()
        tid = s.create_task({'Title': 'Investigate the export failures', 'Kind': 'coding', 'Status': 'open',
                             'Source': 'assistant', 'SourceRef': 'assistant:idea:9'}, 'assistant')
        s.add_message({'TaskId': tid, 'ExternalId': 'assistant:9', 'ConversationId': 'report:140:idea:x', 'Channel': 'assistant',
                       'SourceName': 'Backend monitor', 'Subject': 'Advisor idea: investigate the export', 'FromName': 'Backend monitor',
                       'SentAt': ago(3), 'BodyText': '.', 'Status': 'routed'})
        s.add_message({'TaskId': tid, 'ExternalId': 'report:4:x', 'ConversationId': 'report:4', 'Channel': 'report',
                       'SourceName': 'Process Error Check', 'Subject': 'Process Error Check - errors found', 'FromName': 'Process Error Check',
                       'SentAt': ago(1), 'BodyText': '.', 'Status': 'filed'})
        mail(s, 'lunch on friday', who='Gail Moreno', email='gail@northwind.example', hours=1)
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        self.assertEqual([i.get('channel') for i in rail(s) if i.get('tid') == tid], ['assistant'])
