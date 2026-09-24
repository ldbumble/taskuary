"""The pipe (funnel.py): one ranked pile out of what the hub already knows, lanes in the order
a sharp assistant raises them, oldest first inside a lane, and a small memory of what was shown,
done and pushed back. No model anywhere."""
import json, threading, time, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import funnel
from taskuary.store import MemoryStore


def ago(hours=0, days=0, minutes=0):
    return (datetime.now() - timedelta(hours=hours, days=days, minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


def ahead(minutes=0):
    return (datetime.now() + timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coder_auto_enabled', 'learn_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._CACHE.update(cands_at=0.0, cands=[])
    return s


def mail(s, subject, who='Dana', email='dana@vendor.com', body='Can you send the corrected file?', hours=2, tid=None, status='routed', channel='email', conv=None):
    return s.add_message({'TaskId': tid, 'ExternalId': f'x:{subject}:{hours}', 'ConversationId': conv, 'Channel': channel, 'SourceName': 'inbox',
                          'Subject': subject, 'FromName': who, 'FromEmail': email, 'SentAt': ago(hours), 'BodyText': body, 'Status': status})


class CacheTests(unittest.TestCase):
    def test_two_forced_reads_in_one_windows_clock_tick_both_refresh(self):
        """Equal wall-clock timestamps do not mean another caller rebuilt while this one waited."""
        s = store()
        with mock.patch.object(funnel.time, 'time', return_value=1000.0):
            self.assertEqual(funnel.pile(s, force=True)['items'], [])
            t = s.create_task({'Title': 'new work', 'Kind': 'coding', 'Status': 'open'}, 'o')
            mail(s, 'new work', tid=t)
            self.assertEqual([i['title'] for i in funnel.pile(s, force=True)['items']], ['new work'])

    def test_concurrent_forced_reads_share_the_rebuild_that_finished_while_they_waited(self):
        s = store()
        started, release, calls, answers = threading.Event(), threading.Event(), [], []

        def slow_build(_store):
            calls.append(1); started.set(); release.wait(2)
            return {'rev': 'fresh', 'items': []}

        def read(): answers.append(funnel.pile(s, force=True)['rev'])

        with mock.patch.object(funnel, 'announce', return_value=[]), \
             mock.patch.object(funnel, 'build', side_effect=slow_build), \
             mock.patch.object(funnel, 'alerts', return_value=[]):
            first = threading.Thread(target=read); first.start(); self.assertTrue(started.wait(1))
            second = threading.Thread(target=read); second.start(); time.sleep(.03); release.set()
            first.join(2); second.join(2)
        self.assertEqual(calls, [1])
        self.assertEqual(answers, ['fresh', 'fresh'])


class PausedConversationTests(unittest.TestCase):
    def test_saved_general_work_is_a_paused_agent_with_its_last_answer(self):
        s = store()
        tid = s.create_task({'Title': 'Set up ADP', 'Summary': 'Clock in at 9', 'Kind': 'general',
                             'Status': 'open', 'SourceRef': 'assistant:setup'}, 'owner')
        s.add_comment(tid, 'assistant', 'assistant_agent', 'The sign-in page is open. Enter your user ID.')
        s.save_session(tid, 'cli:codex', '', 'native-1', 'context-1')
        item = funnel.paused_conversation(s, {'key': 'msg:1', 'kind': 'todo', 'lane': 'asked',
                                               'tid': tid, 'title': 'Set up ADP'})
        self.assertEqual((item['key'], item['kind'], item['lane'], item['paused'], item['mode']),
                         (f'agent:{tid}', 'agent', 'blocked', True, 'assistant'))
        self.assertIn('sign-in page is open', item['tail'][0])

    def test_a_task_with_no_saved_conversation_stays_an_ordinary_task(self):
        s = store()
        tid = s.create_task({'Title': 'Call Dana', 'Kind': 'general', 'Status': 'open'}, 'owner')
        item = {'key': 'msg:1', 'kind': 'todo', 'lane': 'asked', 'tid': tid}
        self.assertEqual(funnel.paused_conversation(s, item), item)


class FollowUpTests(unittest.TestCase):
    """What a reply on an open task IS is triage's verdict, not the task's kind and not a keyword here
    (the owner, 2026-09-03: "Thank you is a close should not be hard coded"). ingest files an fyi
    follow-up onto the task; the pipe then reads the row's own category, and what is left for the
    owner is the wrap-up: your reply went out, the task is still open."""

    def test_an_fyi_follow_up_on_an_open_task_is_not_asked_you(self):
        s = store()
        t = s.create_task({'Title': 'Pto', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        mail(s, 'PTO', who='Erin', email='erin@vendor.example', body='Can you import pto for Aug 9 thru Aug 22?', hours=8, tid=t, conv='c:pto')
        s.add_message({'TaskId': t, 'ExternalId': 'x:own', 'ConversationId': 'c:pto', 'Channel': 'email', 'Subject': 'RE: PTO', 'FromName': 'You',
                       'FromEmail': 'owner@ours.com', 'SentAt': ago(3), 'BodyText': 'Done. All PTO batches posted.', 'Status': 'context'})
        m = mail(s, 'RE: PTO', who='Erin', email='erin@vendor.example', body='Thank you!', hours=1, tid=t, conv='c:pto', status='filed')
        s.add_route(m, t, 'attach', 1.0, 'triage: fyi - only says thanks · kept on TQ-0322 for the chain', [], 'triage')
        items = funnel.build(s)['items']
        self.assertEqual([(i['kind'], i['lane'], i['key']) for i in items], [('wrapup', 'report', f'wrap:{t}')])
        self.assertIn('the reply went out', items[0]['why']); self.assertIn('still open', items[0]['why'])
        self.assertIn('All PTO batches posted', items[0]['sent'])          # your own reply is what went out

    def test_a_follow_up_triage_kept_as_work_still_asks_you(self):
        s = store()
        t = s.create_task({'Title': 'Pto', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        s.add_message({'TaskId': t, 'ExternalId': 'x:own3', 'ConversationId': 'c:pto2', 'Channel': 'email', 'Subject': 'RE: PTO', 'FromName': 'You',
                       'FromEmail': 'owner@ours.com', 'SentAt': ago(3), 'BodyText': 'Done.', 'Status': 'context'})
        mail(s, 'RE: PTO', who='Erin', email='erin@vendor.example', body='Thanks! Can you also do the M44 period?', hours=1, tid=t, conv='c:pto2')
        self.assertEqual([(i['kind'], i['lane']) for i in funnel.build(s)['items']], [('todo', 'yours')])

    def test_the_wrap_up_counts_a_reply_typed_in_your_own_mail_client(self):
        s = store()
        t = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        s.add_message({'TaskId': t, 'ExternalId': 'x:own4', 'ConversationId': 'c:exp', 'Channel': 'email', 'Subject': 'RE: Export', 'FromName': 'You',
                       'FromEmail': 'owner@ours.com', 'SentAt': ago(2), 'BodyText': 'Fixed and deployed.', 'Status': 'context'})
        wrapped = funnel.from_wrapped(s, datetime.now(), set())
        self.assertEqual([(w['kind'], w['tid']) for w in wrapped], [('wrapup', t)])
        self.assertIn('Fixed and deployed', wrapped[0]['sent'])


class FlapTests(unittest.TestCase):
    """A CLI between two chunks of output can read parked for a moment. Narrating that moment - and
    then its opposite - is the "it stopped… no, it's working" the owner saw: "THe stopped coding and
    waiting for users is very buggy" (2026-09-03). A state is news only once it has HELD."""

    def _task(self, s):
        t = s.create_task({'Title': 'Run the Intacct connector', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        mail(s, 'Intacct', hours=1, tid=t)
        return t

    def _live(self, tid, **kw):
        return [{'taskId': tid, 'agent': 'coder', 'label': 'coder', 'started': ago(hours=1), 'tail': ['…'], **kw}]

    def test_a_moment_of_quiet_is_not_announced(self):
        s = store(); t = self._task(s)
        with mock.patch('taskuary.terminal.live_sessions', return_value=self._live(t, idle=2, waiting=False)):
            self.assertEqual(funnel.announce(s), [])                       # the first look only remembers
        with mock.patch('taskuary.terminal.live_sessions', return_value=self._live(t, idle=50, waiting=True, tail=['import now? (y/n)'])):
            self.assertEqual(funnel.announce(s), [])                       # parked for a beat: not news
        with mock.patch('taskuary.terminal.live_sessions', return_value=self._live(t, idle=2, waiting=False)):
            self.assertEqual(funnel.announce(s), [])                       # ...and back to work, so nothing was said

    def _held(self, tid, state):
        funnel._SEEN[tid] = (state, funnel.time.time() - funnel.DWELL - 1)   # as if it had been this way all along

    def test_a_stop_that_holds_is_announced(self):
        s = store(); t = self._task(s)
        # every state has to hold before Taskuary even believes it - so working is believed first…
        with mock.patch('taskuary.terminal.live_sessions', return_value=self._live(t, idle=2, waiting=False)):
            funnel.announce(s); self._held(t, 'working'); funnel.announce(s)
        self.assertEqual(funnel._STATE[t][0], 'working')
        parked = self._live(t, idle=200, waiting=True, tail=['import now? (y/n)'])
        with mock.patch('taskuary.terminal.live_sessions', return_value=parked):
            self.assertEqual(funnel.announce(s), [])                         # …and the stop is not news yet
            state = funnel.agent_states(s)[t][0]                             # 'asking' - it is a question
            self._held(t, state)
            ev = funnel.announce(s)
        self.assertEqual([(e['kind'], e['tid']) for e in ev], [(state, t)])
        self.assertIn('waiting on you' if state == 'parked' else 'asked you something', ev[0]['text'])

    def test_the_screen_says_working_even_when_its_footer_offers_a_prompt(self):
        """Claude Code's footer carries both readings on one line - and the parked half used to win."""
        from taskuary import terminal
        foot = 'bypass permissions on (shift+tab to cycle) \u00b7 esc to interrupt \u00b7 for agents'
        self.assertEqual(terminal.phase_of([foot]), 'working')
        self.assertEqual(terminal.phase_of(['bypass permissions on (shift+tab to cycle)']), 'parked')
        self.assertEqual(terminal.phase_of(['Reading tools/gl_export.py', foot, '']), 'working')
        # ...and a stale frame ABOVE a newer prompt line still loses: newest line first, always
        self.assertEqual(terminal.phase_of(['Running tests (esc to interrupt)', '? for shortcuts']), 'parked')


class ChatHasNoSubjectTests(unittest.TestCase):
    def test_a_chat_row_is_titled_by_what_was_said(self):
        """WhatsApp and Slack carry no subject, so every chat row in the pipe and the work list read
        "(no subject)" beside a message you had to open to see (the owner, 2026-09-07)."""
        s = store()
        said = 'Budgeting'
        m = mail(s, '', who='Tess', email='', body=said, hours=0, channel='whatsapp', conv='wa:tess', status='filed')
        s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        self.assertEqual(funnel.build(s)['items'][0]['title'], 'Budgeting')
        # ...and a long one fits the pill: one line, cut on a word, never mid-word
        s2 = store()
        long_said = ("So what's their moves if it's free? So it's a cool thing, but I mean, something like "
                     "someone you built this a month and a half ago. So now what?")
        m2 = mail(s2, '', who='Tess', email='', body=long_said, hours=0, channel='whatsapp', conv='wa:g2', status='filed')
        s2.add_route(m2, None, 'file', None, 'triage: fyi', [], 'triage')
        title = funnel.build(s2)['items'][0]['title']
        self.assertLessEqual(len(title), 91)
        self.assertTrue(title.endswith('…') and not title.endswith(' …'), repr(title))
        self.assertTrue(long_said.startswith(title[:-1].rstrip()), f'not what she said: {title!r}')

    def test_a_synthesized_chat_title_gives_way_to_the_message(self):
        """Teams titles a chat after the people already named in the row."""
        s = store()
        m = mail(s, 'Teams chat with Gail Moreno', who='Gail Moreno', email='h@northwind.test',
                 body='can you add Nathan to the call he wants to join', hours=0, channel='teams', conv='t:h', status='filed')
        s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        self.assertEqual(funnel.build(s)['items'][0]['title'], 'can you add Nathan to the call he wants to join')

    def test_a_real_subject_is_still_the_title(self):
        s = store()
        m = mail(s, 'AI Agents', who='Nathan', email='n@northwind.test', body='Nathan invited Fireflies here',
                 hours=0, channel='teams', conv='t:ai', status='filed')
        s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        self.assertEqual(funnel.build(s)['items'][0]['title'], 'AI Agents')


class OneLinePerThreadTests(unittest.TestCase):
    def test_the_row_says_how_much_of_the_thread_it_stands_for(self):
        """Three lines in one WhatsApp room are one row - and the Timeline showing three of them read
        as the pipe losing two (the owner, 2026-09-03: "TImeline has 2 whatsapp while on the funnel
        it's only 1?")."""
        s = store()
        for n in range(3):
            m = mail(s, '', who='Tess', email='', body=f'line {n}', hours=0, channel='whatsapp', conv='wa:tess', status='filed')
            s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        items = funnel.build(s)['items']
        self.assertEqual([(i['who'], i.get('more')) for i in items], [('Tess', 2)])
        # ...and a single line says nothing extra
        s2 = store()
        m = mail(s2, '', who='Tess', email='', body='just one', hours=0, channel='whatsapp', conv='wa:one', status='filed')
        s2.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        self.assertIsNone(funnel.build(s2)['items'][0].get('more'))

    def test_a_triaged_task_is_one_row_and_does_not_swallow_other_tasks_in_the_same_chat(self):
        """The task, not a long-lived WhatsApp room, is the grouping boundary after triage."""
        s = store()
        first = s.create_task({'Title': 'Reorder the intake', 'Kind': 'general', 'Status': 'open'}, 'o')
        second = s.create_task({'Title': 'Fix the login', 'Kind': 'coding', 'Status': 'open'}, 'o')
        for n in range(7):
            mid = mail(s, 'Reorder the intake', who='Tess', email='', body=f'intake line {n}', hours=n / 100,
                       tid=first, channel='whatsapp', conv='wa:long-room')
            s.add_route(mid, first, 'attach', 1.0, 'triage: same task', [], 'triage')
        for n in range(2):
            mid = mail(s, 'Fix the login', who='Tess', email='', body=f'login line {n}', hours=1 + n / 100,
                       tid=second, channel='whatsapp', conv='wa:long-room')
            s.add_route(mid, second, 'attach', 1.0, 'triage: different task', [], 'triage')

        items = funnel.build(s)['items']
        by_task = {i['tid']: i for i in items}
        self.assertEqual(set(by_task), {first, second})
        self.assertEqual(by_task[first].get('more'), 6)
        self.assertEqual(by_task[second].get('more'), 1)


class ReportFailedTests(unittest.TestCase):
    def test_a_report_failed_when_its_run_failed_not_when_its_name_says_error(self):
        """'Process Error Check - 0 rows' was read as a failure because its own title carries the word
        (the owner, 2026-09-03: "that's not a fail, it says all clear?")."""
        s = store()
        ok = mail(s, 'Process Error Check — 0 rows', who='report', email='', body='All clear', hours=1,
                  channel='report', status='feed')
        s.add_route(ok, None, 'feed', None, 'a report you set up', [], 'feed')
        bad = mail(s, 'GitHub Trending Top 15 Morning Report — FAILED', who='report', email='', body='error: timed out',
                   hours=2, channel='report', status='feed')
        s.add_route(bad, None, 'feed', None, 'a report you set up', [], 'feed')
        by_title = {i['title']: i for i in funnel.build(s)['items']}
        self.assertFalse(by_title['Process Error Check — 0 rows']['bad'])
        self.assertIn('a report you set up landed', by_title['Process Error Check — 0 rows']['why'])
        self.assertTrue(by_title['GitHub Trending Top 15 Morning Report — FAILED']['bad'])

    def test_the_run_record_outranks_the_subject(self):
        s = store()
        sid = s.save_source({'Channel': 'report', 'Address': 'Nightly headcount', 'Owner': 'o', 'Active': 1,
                             'ConfigJson': '{"title": "Nightly headcount"}'}, 'o')
        funnel._SOURCES.update(at=0.0, by={}, digest=set())
        m = s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'SourceName': 'Nightly headcount',
                           'Subject': 'Nightly headcount', 'FromName': 'report', 'SentAt': ago(0),
                           'BodyText': 'nothing came back', 'Status': 'feed'})
        s.add_route(m, None, 'feed', None, 'a report you set up', [], 'feed')
        # the run carries the message it produced, as reports.run_report_source records it (`message_id`).
        # This used to be written with no message_id and relied on the row picking up the source's newest
        # run - the very coupling that made an old failure inherit a later success (2026-09-10).
        s.add_report_run(sid, {'at': ago(0), 'type': 'agent', 'title': 'Nightly headcount', 'message_id': m,
                               'subject': 'Nightly headcount — FAILED', 'failed': True, 'error': 'timed out'})
        item = next(i for i in funnel.build(s)['items'] if i['kind'] == 'report')
        self.assertTrue(item['bad'])                     # the subject says nothing; the run says it failed
        self.assertIn('the check failed', item['why'])
        self.assertEqual(item['lane'], 'broken')         # ...and a check that cannot run is promoted, not filed

    def test_each_run_is_judged_by_its_own_record_not_the_reports_latest(self):
        """An older FAILED run kept being re-judged by the newest run of the same report, so every
        historical row inherited the latest verdict (the owner, 2026-09-10: a pipe holding two
        "Process Error Check - FAILED" rows filed as landed results because the newest run said
        "0 rows"). It cuts both ways: one fresh failure would flip every older good row to broken."""
        s = store()
        sid = s.save_source({'Channel': 'report', 'Address': 'Process Error Check', 'Owner': 'o', 'Active': 1,
                             'ConfigJson': '{"title": "Process Error Check"}'}, 'o')
        funnel._SOURCES.update(at=0.0, by={}, digest=set())
        def run_row(subject, body, hours, failed):
            # SourceName is what ties the row to its report - without it the lookup never happens
            # and the stale-verdict path is not even reached (this test passed vacuously without it)
            mid = s.add_message({'ExternalId': f'r:{subject}', 'Channel': 'report', 'SourceName': 'Process Error Check',
                                 'Subject': subject, 'FromName': 'report', 'SentAt': ago(hours),
                                 'BodyText': body, 'Status': 'feed'})
            s.add_route(mid, None, 'feed', None, 'a report you set up', [], 'feed')
            s.add_report_run(sid, {'at': ago(hours), 'type': 'sql', 'title': 'Process Error Check',
                                   'subject': subject, 'message_id': mid, 'failed': failed,
                                   'error': 'no such host' if failed else None})
            return mid
        run_row('Process Error Check - FAILED', 'Named Pipes: no such host', 6, True)
        run_row('Process Error Check - 0 rows', 'All clear', 1, False)
        by_title = {i['title']: i for i in funnel.build(s)['items']}
        older = by_title['Process Error Check - FAILED']
        newer = by_title['Process Error Check - 0 rows']
        self.assertTrue(older['bad'], 'the failed run was re-judged by the newest run of the same report')
        self.assertEqual(older['lane'], 'broken')        # band 2: a check that failed is work
        self.assertFalse(newer['bad'])
        self.assertEqual(newer['lane'], 'report')


class InHandTests(unittest.TestCase):
    """A task whose status says in_progress is being worked: it rides above the funnel as "agent
    working", not in 'slipped' (the owner, 2026-09-03: "It should not in slipped group it's in middle
    of working... so it's not in funnel. If it's actually done, waiting for you it will jump ahead")."""

    def _line_about(self, s, tid, text):
        """The assistant's own follow-up line - as it writes them: a bare note that NAMES the task."""
        return s.upsert_idea({'key': f'loose:{tid}', 'kind': 'loose', 'text': text, 'sig': text[:40],
                              'action': {'type': 'note', 'section': 'loose',
                                         'why': f'OPEN WORK: TQ-{tid:04d} in_progress, 3h since anything happened'}}, ago(1))

    def test_a_line_about_a_task_an_agent_has_rides_on_the_shelf(self):
        s = store()
        t = s.create_task({'Title': 'July 2026 financials', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        self._line_about(s, t, f"TQ-{t:04d} July financials hasn't moved in three hours")
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            items = funnel.build(s)['items']
        self.assertEqual([(i['lane'], i['key'], i['ref']) for i in items], [('working', f'agent:{t}', f'TQ-{t:04d}')])
        self.assertIn('nothing for you until it stops or asks', items[0]['why'])

    def test_the_same_line_is_an_fyi_once_the_agent_is_no_longer_on_it(self):
        s = store()
        t = s.create_task({'Title': 'July 2026 financials', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        self._line_about(s, t, f"TQ-{t:04d} July financials hasn't moved in three hours")
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            items = funnel.build(s)['items']
        # the assistant's own line about a task nobody is on is an fyi until TRIAGE calls it work
        # (the owner, 2026-09-07: "assistant ideas and slipped stuff should be fyi unless triage
        # turns it into task") - it used to open in a lane of its own inside the actionable band
        self.assertEqual([(i['lane'], i['kind'], i['ref']) for i in items], [('fyi', 'idea', f'TQ-{t:04d}')])

    def test_no_wrap_up_is_asked_for_while_an_agent_still_has_the_task(self):
        s = store()
        t, m, r = None, None, None
        t = s.create_task({'Title': 'Pto', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        s.add_message({'TaskId': t, 'ExternalId': 'x:own', 'ConversationId': 'c:pto', 'Channel': 'email', 'Subject': 'RE: PTO',
                       'FromName': 'You', 'FromEmail': 'owner@ours.com', 'SentAt': ago(2), 'BodyText': 'Done.', 'Status': 'context'})
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            self.assertEqual(funnel.build(s)['items'], [])
        s.update_task(t, {'Status': 'waiting'}, 'o')
        funnel.invalidate()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            self.assertEqual([(i['kind'], i['lane']) for i in funnel.build(s)['items']], [('wrapup', 'report')])


class MutedTests(unittest.TestCase):
    def test_a_standing_rule_keeps_a_kind_of_mail_out_of_the_pipe_but_not_a_real_ask(self):
        s = store()
        s.set_setting('team_domains', 'ours.com', 't')
        for n in range(2):
            m = mail(s, f'Northwind Financial Report - .0{n} P&L', who='Paula Vance', email='pvance@vendor.example',
                     body='generated by Intacct', hours=n + 1, status='filed')
            s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        keep = mail(s, 'RE: Careview', who='Ravi', email='ravi@vendor.com', body='please respond', hours=1, status='filed')
        s.add_route(keep, None, 'file', None, 'triage: fyi', [], 'triage')
        self.assertEqual(len(funnel.build(s)['items']), 3)
        funnel.remember_mute(s, {'sender': 'pvance@vendor.example', 'words': ['northwind', 'financials'], 'why': 'part of the financials process'}, 'o')
        p = funnel.build(s)
        self.assertEqual([i['who'] for i in p['items']], ['Ravi'])
        self.assertEqual((p['muted'], p['rules']), (2, ['part of the financials process']))
        # a rule reaches only the lanes with nothing to do
        t = s.create_task({'Title': 'Re-run .02', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        mail(s, 'Northwind Financial Report - can you re-run .02?', who='Paula Vance', email='pvance@vendor.example',
             body='please re-run it', hours=0, tid=t)
        funnel.invalidate()
        self.assertIn('yours', [i['lane'] for i in funnel.build(s)['items'] if i.get('tid') == t])
        # ...and it is the owner's to take off again
        funnel.remember_mute(s, {'sender': 'pvance@vendor.example', 'words': ['northwind', 'financials'], 'why': 'x'}, 'o')
        self.assertEqual(len(funnel.mutes(s)), 1)              # rewritten, not stacked


class LanesTests(unittest.TestCase):
    def test_a_drafted_reply_outranks_a_report_and_the_oldest_in_a_lane_comes_first(self):
        s = store()
        t1 = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        m1 = mail(s, 'Export still broken', hours=5, tid=t1)
        s.add_review({'TaskId': t1, 'MessageId': m1, 'Kind': 'reply', 'DraftText': 'Attached.', 'Status': 'pending'})
        t2 = s.create_task({'Title': 'Invoice question', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        m2 = mail(s, 'Invoice question', who='Sam', email='sam@vendor.com', hours=30, tid=t2)
        s.add_review({'TaskId': t2, 'MessageId': m2, 'Kind': 'reply', 'DraftText': '', 'Status': 'pending'})
        s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'SourceName': 'Process Error Check', 'Subject': 'Process Error Check FAILED',
                       'FromName': 'Process Error Check', 'SentAt': ago(1), 'BodyText': 'Could not open db', 'Status': 'feed'})
        keys = [(i['lane'], i['kind'], i['title']) for i in funnel.build(s)['items']]
        # the failed run wears the 'broken' lane now (promoted from 'report', which sat behind
        # everything) - but still UNDER both drafted replies, which is what this test is about
        self.assertEqual(keys, [('approve', 'review', 'Invoice question'), ('approve', 'review', 'Export still broken'),
                                ('broken', 'report', 'Process Error Check FAILED')])          # a timeline: 30h old before 5h old
        report = funnel.build(s)['items'][-1]
        self.assertTrue(report['bad']); self.assertIn('failed', report['why'])

    def test_a_failed_check_is_promoted_and_does_not_expire_while_it_is_still_failing(self):
        """"Could not open a connection to SQL Server" needs no classifier - it says what it is. It
        used to file in the 'report' lane, behind even a slipped thread, and then leave the pipe
        entirely after twelve hours with the host still down (the owner, 2026-09-04: "pipe should
        move it up as it's important if it says your sql server is down")."""
        s = store()
        s.add_message({'ExternalId': 'ok1', 'Channel': 'report', 'SourceName': 'Headcount', 'Subject': 'Headcount - 5 rows',
                       'FromName': 'Headcount', 'SentAt': ago(1), 'BodyText': '5 rows', 'Status': 'feed'})
        s.add_message({'ExternalId': 'bad1', 'Channel': 'report', 'SourceName': 'Process Error Check',
                       'Subject': 'Process Error Check FAILED', 'FromName': 'Process Error Check',
                       'SentAt': ago(hours=30), 'BodyText': 'Could not open a connection to SQL Server [53]', 'Status': 'feed'})
        items = funnel.build(s)['items']
        by = {i['title']: i for i in items}
        self.assertEqual(by['Process Error Check FAILED']['lane'], 'broken')
        self.assertEqual(by['Headcount - 5 rows']['lane'], 'report')            # a run that worked is still just news
        # 30 hours old and still in the pipe, while the ordinary report beside it obeys the window
        # a check that could not run is the owner's task; the run that worked is a result below it
        self.assertLess(funnel._band(by['Process Error Check FAILED']), funnel._band(by['Headcount - 5 rows']))
        # a drafted reply and a failed check are both the owner's task now - one level, oldest first
        self.assertEqual(funnel._band({'lane': 'approve'}), funnel._band(by['Process Error Check FAILED']))
        self.assertFalse(funnel._aged_out(by['Process Error Check FAILED'], datetime.now(), 12))
        self.assertNotIn('broken', funnel.MUTED_LANES)   # a rule that quiets a report cannot quiet it FAILING

    def test_an_assistant_line_waits_a_day_to_be_seen_not_twelve_hours(self):
        """A mail going quiet after twelve hours is fine. The assistant's standing note that
        something is LOOSE is the opposite - still true tomorrow - and expiring it is how "TQ-0329
        hasn't moved, Paula asked for that file today" left the pipe unseen."""
        now = datetime.now()
        idea = {'kind': 'idea', 'lane': 'forgotten', 'when': (now - timedelta(hours=18)).strftime('%Y-%m-%d %H:%M:%S')}
        mail = {'kind': 'fyi', 'lane': 'fyi', 'when': (now - timedelta(hours=18)).strftime('%Y-%m-%d %H:%M:%S')}
        self.assertFalse(funnel._aged_out(idea, now, 12))    # the same age, a day's grace
        self.assertTrue(funnel._aged_out(mail, now, 12))     # ...and the mail beside it goes
        old = {'kind': 'idea', 'lane': 'forgotten', 'when': (now - timedelta(hours=30)).strftime('%Y-%m-%d %H:%M:%S')}
        self.assertTrue(funnel._aged_out(old, now, 12))      # a day, not for ever - 64 open ideas is a flood
        # a window the owner widened himself is never narrowed by this
        wide = {'kind': 'idea', 'lane': 'forgotten', 'when': (now - timedelta(hours=40)).strftime('%Y-%m-%d %H:%M:%S')}
        self.assertFalse(funnel._aged_out(wide, now, 48))

    def test_an_agent_waiting_on_you_comes_out_first_and_a_working_agent_is_not_on_you(self):
        s = store()
        t1 = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        mail(s, 'Export still broken', hours=1, tid=t1)
        t2 = s.create_task({'Title': 'Rename the flag', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        mail(s, 'Rename the flag please', hours=3, tid=t2)
        live = [{'taskId': t1, 'agent': 'claude', 'label': 'claude', 'started': ago(hours=1), 'idle': 120, 'waiting': True,
                 'tail': ['Edited export.py', 'Should I also update the tests? (y/n)']},
                {'taskId': t2, 'agent': 'codex', 'label': 'codex', 'started': ago(minutes=5), 'idle': 2, 'waiting': False, 'tail': ['working…']}]
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            items = funnel.build(s)['items']
            self.assertEqual(funnel.next_item(s)['tid'], t1)                            # the worked one is never pulled
        # the worked task rides at the TOP of the pipe, in hand, and is never what comes out next
        self.assertEqual([(i['lane'], i['kind'], i['tid']) for i in items], [('blocked', 'agent', t1), ('working', 'todo', t2)])
        self.assertTrue(items[0]['asking']); self.assertIn('asked you something', items[0]['why']); self.assertIn('codex has it', items[1]['why'])
        self.assertEqual((items[0].get('sid'), items[0]['mode']), (None, 'terminal'))           # the card embeds the screen when a sid is known
        # the mail that started t1 is not a second line: answering the agent answers the mail
        self.assertEqual(items[0]['mid'], s.list_messages(t1)[0]['MessageId'])

    def test_a_waiting_agent_stays_in_the_pipe_after_it_was_shown_and_comes_round_again(self):
        s = store()
        t = s.create_task({'Title': 'Pto', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        mail(s, 'PTO', hours=3, tid=t)
        live = [{'taskId': t, 'agent': 'codex', 'label': 'codex', 'started': ago(hours=1), 'idle': 200, 'waiting': True, 'tail': ['import now? (y/n)']}]
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            self.assertEqual(funnel.next_item(s)['key'], f'agent:{t}')
            funnel.settle(s, f'agent:{t}', 'surfaced')
            items = funnel.build(s)['items']
            self.assertEqual([(i['key'], i['surfaced']) for i in items], [(f'agent:{t}', True)])   # still in the pipe, marked
            self.assertIsNone(funnel.next_item(s))                                             # but not straight back on the table
            s.set_funnel_state(f'agent:{t}', 'surfaced', 'owner'); s._exec("UPDATE funnel_state SET At=? WHERE Key=?", (ago(minutes=45), f'agent:{t}'))
            funnel.invalidate()
            self.assertIsNone(funnel.next_item(s))                                             # passed: not back within the hour (2026-09-23)
            s._exec("UPDATE funnel_state SET At=? WHERE Key=?", (ago(minutes=75), f'agent:{t}'))
            funnel.invalidate()
            self.assertEqual(funnel.next_item(s)['key'], f'agent:{t}')                        # an hour on, it comes round again
            self.assertIn('shown already, still waiting', funnel.summary(funnel.build(s)['items']))
        # ...and when the agent picks the work back up, the shown item rides up to the shelf instead of vanishing
        busy = [dict(live[0], idle=2, waiting=False)]
        with mock.patch('taskuary.terminal.live_sessions', return_value=busy):
            items = funnel.build(s)['items']
            self.assertEqual([(i['lane'], i.get('surfaced')) for i in items], [('working', True)])
            self.assertIsNone(funnel.next_item(s))
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            funnel.settle(s, f'agent:{t}', 'done')
            self.assertEqual(funnel.build(s)['items'], [])

    def test_the_watcher_turns_agent_transitions_into_lines_in_the_chat(self):
        from taskuary import concierge, general
        patch = mock.patch.object(funnel, 'DWELL', 0)                # this test is about the words, not the wait
        patch.start(); self.addCleanup(patch.stop)
        s = store()
        t = s.create_task({'Title': 'Pto', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        mail(s, 'PTO', hours=3, tid=t)
        parked = [{'taskId': t, 'agent': 'codex', 'label': 'codex', 'started': ago(hours=1), 'idle': 200, 'waiting': True, 'tail': ['import now? (y/n)']}]
        working = [dict(parked[0], idle=2, waiting=False, tail=['editing…'])]
        with mock.patch('taskuary.terminal.live_sessions', return_value=parked):
            self.assertEqual(funnel.announce(s), [])                                  # the first look only remembers
        with mock.patch('taskuary.terminal.live_sessions', return_value=working):
            ev = funnel.announce(s)
        self.assertEqual([(e['kind'], e['tid']) for e in ev], [('working', t)])
        self.assertIn("codex is working on TQ-0001 (Pto) - nothing for you there now.", ev[0]['text'])
        self.assertNotIn('next thing', ev[0]['text'])                                    # a worker starting is not a nudge to advance (PW-168)
        with mock.patch('taskuary.terminal.live_sessions', return_value=working):
            self.assertEqual(funnel.announce(s), [])                                  # said once
        with mock.patch('taskuary.terminal.live_sessions', return_value=parked):
            ev = funnel.announce(s)
        self.assertEqual(ev[0]['kind'], 'asking'); self.assertIn('asked you something on TQ-0001', ev[0]['text']); self.assertIsNone(ev[0]['card'])
        s.add_comment(t, 'codex', 'agent', 'CODER REPORT' + chr(10) + 'Summary: imported all 80 PTO files; results mailed.')
        s.update_task(t, {'Status': 'done'}, 'o')
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            ev = funnel.announce(s)
            self.assertEqual(ev[0]['kind'], 'done'); self.assertIn('imported all 80 PTO files', ev[0]['text']); self.assertIn('task is closed', ev[0]['text'])
            self.assertIsNone(ev[0]['card'])
            self.assertEqual(funnel.announce(s), [])                                  # a closed task is not watched again
        # The watcher writes nothing into the chat (PW-165): its word is a notice on the strip, kept until Open or Later
        self.assertEqual(concierge.history(s, general.dock_task(s)[0]['TaskId']), [])
        self.assertEqual(funnel.notices(s), [], 'and a closed task is not even that: it waits on nobody')
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            self.assertIn('events', funnel.pile(s, force=True))

    def test_a_working_notice_is_dropped_once_the_agent_is_gone(self):
        """The phone walk, 2026-09-10: four "coder is working on TQ-xxxx" notices, the newest two days
        old, replayed on every handoff - their tasks closed and their sessions ended long before."""
        s = store()
        t = s.create_task({'Title': 'Pto', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        funnel.notify(s, {'tid': t, 'ref': 'TQ-0001', 'kind': 'working', 'agent': 'codex',
                          'text': 'codex is working on TQ-0001 (Pto) - nothing for you there now.'})
        live = [{'taskId': t, 'agent': 'codex', 'label': 'codex', 'started': ago(hours=1), 'idle': 2, 'waiting': False, 'tail': ['editing']}]
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            self.assertEqual([a['kind'] for a in funnel.notices(s)], ['working'], 'the agent really is on it')
        s.update_task(t, {'Status': 'done'}, 'o')
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            self.assertEqual(funnel.notices(s), [], 'the session ended and the task closed: the claim is dead')
        self.assertNotIn(f'notice:{t}', s.funnel_states(), 'and the row is cleared, not re-checked for ever')

    def test_a_finished_task_leaves_no_notice_but_one_waiting_on_you_does(self):
        """The owner, 2026-09-14: "why is this showing up if it's closed?" - a done row had sat on the
        strip for three days. The strip is what is waiting on him, and a closed task waits on nobody."""
        s = store()
        t = s.create_task({'Title': 'Pto', 'Kind': 'coding', 'Status': 'done'}, 'o')
        funnel.notify(s, {'tid': t, 'ref': 'TQ-0001', 'kind': 'done', 'agent': 'codex',      # written by an older build
                          'text': 'codex finished TQ-0001 (Pto). The task is closed.'})
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            self.assertEqual(funnel.notices(s), [], 'the leftover row goes without waiting for a click')
        self.assertNotIn(f'notice:{t}', s.funnel_states(), 'and it is cleared, not re-read for ever')
        # ...while an agent that stopped to ask is exactly what the strip is for - raised by the pile itself
        t2 = s.create_task({'Title': 'Import', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        mail(s, 'Import', hours=3, tid=t2)
        parked = [{'taskId': t2, 'agent': 'codex', 'label': 'codex', 'started': ago(hours=1), 'idle': 200,
                   'waiting': True, 'tail': ['import now? (y/n)']}]
        with mock.patch('taskuary.terminal.live_sessions', return_value=parked):
            self.assertEqual([a['kind'] for a in funnel.alerts(s)], ['agent'])

    def test_a_meeting_inside_two_hours_is_time_sensitive_and_inside_fifteen_minutes_interrupts(self):
        s = store()
        m1 = mail(s, 'Export still broken', hours=5)
        s.add_route(m1, None, 'file', None, 'triage: fyi - a person told you something', [], 'triage')
        ev = [{'start': ahead(10), 'end': ahead(40), 'subject': 'Standup', 'who': ['Priya Shah', 'Marcus Lee'], 'about': 'weekly', 'all_day': False},
              {'start': ahead(90), 'end': ahead(120), 'subject': 'Budget review', 'who': [], 'all_day': False},
              {'start': ahead(60 * 26), 'end': ahead(60 * 27), 'subject': 'Far away', 'who': [], 'all_day': False}]   # tomorrow: today's are all visible (2026-09-07)
        with mock.patch.object(funnel, '_agenda', return_value=ev):
            p = funnel.build(s)
            al = funnel.alerts(s, p['items'])
        meetings = [i for i in p['items'] if i['kind'] == 'meeting']
        self.assertEqual([m['title'] for m in meetings], ['Standup', 'Budget review'])
        self.assertEqual(meetings[0]['lane'], 'time'); self.assertIn('with Priya, Marcus', meetings[0]['why'])
        self.assertEqual([a['kind'] for a in al], ['meeting']); self.assertIn('Standup starts in', al[0]['text'])
        funnel.settle(s, al[0]['key'], 'ack')
        with mock.patch.object(funnel, '_agenda', return_value=ev):
            self.assertEqual(funnel.alerts(s), [])

    def test_a_meeting_waits_for_its_fifteen_minutes_before_the_walk_offers_it(self):
        """It is on the timeline two hours out so the day is visible, and its lane is 'time' - which
        put it at the very FRONT of the walk, so the assistant opened with a meeting 90 minutes away
        ahead of mail that wanted answering now. Same shape as an agent mid-run: real, on the board,
        nothing for the owner to do about it yet (the owner, 2026-09-04: "meetings should not go down
        into the chat until 15 minutes before like a agent in middel of working")."""
        s = store()
        far = [{'start': ahead(90), 'end': ahead(120), 'subject': 'Budget review', 'who': [], 'all_day': False}]
        near = [{'start': ahead(10), 'end': ahead(40), 'subject': 'Standup', 'who': [], 'all_day': False}]
        with mock.patch.object(funnel, '_agenda', return_value=far):
            funnel.invalidate()
            self.assertEqual([i['title'] for i in funnel.build(s)['items']], ['Budget review'])   # on the timeline
            funnel.invalidate()
            self.assertIsNone(funnel.next_item(s))               # ...and the walk has nothing to open with
        with mock.patch.object(funnel, '_agenda', return_value=near):
            funnel.invalidate()
            nxt = funnel.next_item(s)
        self.assertEqual((nxt['kind'], nxt['title']), ('meeting', 'Standup'))    # inside fifteen it goes first

    def test_a_far_off_meeting_does_not_interrupt_a_mail_only_walk_either(self):
        """INTERRUPTS lets a meeting stop a 'just what came in' walk. That is for one about to
        start, not one two hours out."""
        s = store()
        far = [{'start': ahead(95), 'end': ahead(125), 'subject': 'Budget review', 'who': [], 'all_day': False}]
        with mock.patch.object(funnel, '_agenda', return_value=far):
            funnel.invalidate()
            self.assertNotEqual((funnel.next_item(s, only='mail') or {}).get('kind'), 'meeting')

    def test_the_gate_only_ever_holds_back_meetings(self):
        for kind in ('agent', 'todo', 'asked', 'fyi', 'review', 'wrapup', 'idea', 'report'):
            self.assertFalse(funnel._not_yet({'kind': kind, 'mins': 999}), kind)
        self.assertFalse(funnel._not_yet({'kind': 'meeting', 'mins': funnel.ALERT_MIN}))
        self.assertTrue(funnel._not_yet({'kind': 'meeting', 'mins': funnel.ALERT_MIN + 1}))
        self.assertFalse(funnel._not_yet({'kind': 'meeting'}))          # no clock on it: never held

    def test_a_review_carries_what_the_agent_found(self):
        s = store()
        t = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        m = mail(s, 'Export still broken', hours=2, tid=t)
        s.add_comment(t, 'claude', 'agent', 'CODER REPORT\nSummary: the export dropped rows with commas; fixed the escaping.')
        s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': 'Fixed - the corrected file is attached.', 'Status': 'pending'})
        it = funnel.build(s)['items'][0]
        self.assertEqual(it['kind'], 'review'); self.assertIn('fixed the escaping', it['summary'])
        self.assertEqual(funnel.next_item(s, only='mail')['key'], it['key'])

    def test_something_important_waiting_is_an_alert_and_the_assistant_is_told(self):
        from taskuary import concierge
        s = store()
        s.set_setting('team_domains', 'ours.com', 't')
        m = mail(s, 'Team note', who='Lee', email='lee@ours.com', body='FYI.', hours=1, status='filed', conv='n1')
        s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        t = s.create_task({'Title': 'T&E portal', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        m2 = mail(s, 'RE: T&E Portal', who='Craig Palmer', email='craig@northwind.example', hours=0, tid=t)
        s.add_review({'TaskId': t, 'MessageId': m2, 'Kind': 'reply', 'DraftText': 'Yes, go ahead.', 'Status': 'pending'})
        p = funnel.build(s)
        al = funnel.alerts(s, p['items'])
        self.assertEqual([(a['kind'], a['lane'], a['text']) for a in al], [('review', 'approve', "Craig Palmer's reply is waiting for your yes")])
        fyi = next(i for i in p['items'] if i['lane'] == 'fyi')
        self.assertEqual([i['kind'] for i in funnel.more_urgent(p['items'], fyi['key'])], ['review'])
        self.assertEqual(funnel.more_urgent(p['items'], f'review:{s.list_reviews("pending")[0]["ReviewId"]}'), [])
        line = concierge._urgent_line(p['items'], fyi)
        self.assertIn('MORE URGENT WAITING', line); self.assertIn('Craig Palmer - RE: T&E Portal (reply ready)', line)
        funnel.settle(s, f'review:{s.list_reviews("pending")[0]["ReviewId"]}', 'surfaced')
        self.assertEqual(funnel.alerts(s), [])                            # once shown, it is no longer news

    def test_a_task_whose_reply_went_out_and_agent_finished_asks_to_be_closed(self):
        s = store()
        t = s.create_task({'Title': 'T&e portal', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        m = mail(s, 'RE: T&E Portal', who='Craig', email='craig@northwind.example', hours=3, tid=t, conv='te')
        s.add_comment(t, 'coder', 'agent', 'CODER REPORT' + chr(10) + 'Summary: Bulk Approve removed and deployed.')
        r = s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': 'Done - it is off now.', 'Status': 'pending'})
        self.assertEqual([i['kind'] for i in funnel.build(s)['items']], ['review'])
        s.decide_review(r, 'approved', 'Done - it is off now.', 'owner')
        items = funnel.build(s)['items']
        self.assertEqual([(i['kind'], i['lane'], i['tid']) for i in items], [('wrapup', 'report', t)])
        self.assertIn('Bulk Approve removed', items[0]['summary']); self.assertEqual(items[0]['sent'], 'Done - it is off now.')
        s.update_task(t, {'Status': 'done'}, 'o')
        self.assertEqual(funnel.build(s)['items'], [])                                    # closed means out of the funnel

    def test_a_closed_agent_job_never_reenters_the_funnel(self):
        s = store()
        t = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'done'}, 'o')
        s.add_comment(t, 'claude', 'agent', 'CODER REPORT\nSummary: corrected the CSV escaping and added a test.')
        self.assertEqual(funnel.build(s)['items'], [])
        self.assertIsNone(funnel.next_item(s, f'done:{t}'))

    def test_the_assistants_open_lines_are_fyi_until_triage_calls_them_work(self):
        s = store()
        s.upsert_idea({'key': 'followup:c9', 'kind': 'followup', 'text': 'No answer from Dana in 4 days - follow up?', 'sig': 'x',
                       'action': {'type': 'followup', 'mid': 5, 'why': 'you asked on Monday'}}, ago(1))
        items = funnel.build(s)['items']
        self.assertEqual([(i['lane'], i['kind'], i['idea_kind']) for i in items], [('fyi', 'idea', 'followup')])
        self.assertEqual(items[0]['why'], 'you asked on Monday')
        # Being spoken in the Assistant marks an ordinary follow-up read and removes it.
        funnel.settle(s, items[0]['key'], 'surfaced')
        self.assertEqual(funnel.build(s)['items'], [])
        # Closing the underlying task does not mean the owner read the Assistant's line. It stays
        # in Unread until it is explicitly surfaced there; task completion and reading are
        # deliberately separate state machines.
        done = s.create_task({'Title': 'Deploy gpt-4.1', 'Kind': 'coding', 'Status': 'done'}, 'o')
        s.upsert_idea({'key': 'cold:TQ-done', 'kind': 'cold', 'text': 'Deploy gpt-4.1 has sat quiet', 'sig': 'z', 'action': {'tid': done}}, ago(1))
        task_line = funnel.build(s)['items'][0]
        self.assertEqual((task_line['kind'], task_line['tid']), ('idea', done))
        self.assertEqual(s.get_idea(next(i['IdeaId'] for i in s.list_ideas() if i['Key'] == 'cold:TQ-done'))['Status'], 'open')
        funnel.settle(s, task_line['key'], 'surfaced')
        self.assertEqual(funnel.build(s)['items'], [])
        # ...and a line about a thread the owner has since replied on is over too
        s.set_setting('team_domains', 'ours.com', 't')
        mm = mail(s, 'PTO', who='Erin', email='erin@ours.com', hours=20, status='filed', conv='pto')   # a filed mail, past the window
        s.upsert_idea({'key': 'asked:pto', 'kind': 'asked', 'text': 'Erin asked for the PTO import', 'sig': 'p', 'action': {'type': 'message', 'mid': mm}}, ago(hours=2))
        self.assertIn('asked', [i.get('idea_kind') for i in funnel.build(s)['items']])
        rr = s.add_review({'TaskId': None, 'MessageId': mm, 'Kind': 'reply', 'DraftText': 'Imported, all 80 files.', 'Status': 'pending'})
        s.decide_review(rr, 'approved', 'Imported, all 80 files.', 'owner')
        self.assertNotIn('asked', [i.get('idea_kind') for i in funnel.build(s)['items']])
        self.assertEqual(next(i for i in s.list_ideas() if i['Key'] == 'asked:pto')['Status'], 'done')
        # ...and it enters when SAID: a line last raised days ago is not this morning's pipe
        s.upsert_idea({'key': 'cold:TQ-0009', 'kind': 'cold', 'text': 'TQ-0009 has sat quiet', 'sig': 'y', 'action': {'tid': 9}}, ago(days=3))
        self.assertEqual(funnel.build(s)['items'], [])

    def test_one_level_for_the_owners_work_oldest_first_then_results_then_fyi(self):
        s = store()
        s.set_setting('team_domains', 'ours.com', 't')
        m = mail(s, 'Team note', who='Lee', email='lee@ours.com', body='FYI all good.', hours=9, status='filed', conv='n1')
        s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')                    # oldest of all, but fyi: last
        s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'SourceName': 'Nightly', 'Subject': 'Nightly report', 'FromName': 'Nightly',
                       'SentAt': ago(6), 'BodyText': '5 rows', 'Status': 'feed'})
        s.upsert_idea({'key': 'followup:c9', 'kind': 'followup', 'text': 'No answer from Dana', 'sig': 'x', 'action': {'type': 'followup', 'mid': 99}}, ago(4))
        t = s.create_task({'Title': 'Ask', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        mail(s, 'Can you look?', hours=2, tid=t)
        t2 = s.create_task({'Title': 'Draft', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        m2 = mail(s, 'Newest ask', hours=1, tid=t2)
        s.add_review({'TaskId': t2, 'MessageId': m2, 'Kind': 'reply', 'DraftText': 'ok', 'Status': 'pending'})   # newest, but promoted
        # The five levels are triage's verdict, and inside one the oldest leads - so the ask from two
        # hours ago comes out before the draft from one (the owner, 2026-09-07: "no reason why open
        # task is before a reply drafted"), the landed report is a result below both, and the fyi and
        # the unjudged idea share the last level oldest-first.
        self.assertEqual([i['kind'] for i in funnel.build(s)['items']], ['todo', 'review', 'report', 'fyi', 'idea'])

    def test_marketing_mail_is_still_unread_until_the_owner_handles_it(self):
        s = store()
        m = mail(s, 'Weekly newsletter', who='news@vendor.com', email='news@vendor.com', body='Unsubscribe here. Manage your preferences.', status='filed')
        s.add_route(m, None, 'file', None, 'marketing', [], 'triage')
        self.assertEqual([(i['kind'], i['lane']) for i in funnel.build(s)['items']], [('fyi', 'fyi')])

    def test_an_unread_assistant_idea_survives_its_source_task_closing(self):
        s = store()
        task = s.create_task({'Title': 'One login case', 'Kind': 'general', 'Status': 'open'}, 'o')
        source = mail(s, 'Blank login', tid=task, conv='login')
        idea = s.upsert_idea({'key': 'blank-logins-pattern', 'kind': 'idea',
                              'text': 'Blank logins happened twice; add an import check.', 'sig': 'new',
                              'action': {'type': 'task', 'mid': source, 'tid': task}}, ago(1))
        s.update_task(task, {'Status': 'done'}, 'owner')
        items = funnel.build(s)['items']
        self.assertIn(f"idea:{idea['IdeaId']}", [i['key'] for i in items])
        self.assertEqual(s.get_idea(idea['IdeaId'])['Status'], 'open')

    def test_a_read_source_row_does_not_hide_a_later_unread_assistant_idea(self):
        s = store()
        source = mail(s, 'Connector issue', conv='connector')
        idea = s.upsert_idea({'key': 'connector-followup', 'kind': 'idea',
                              'text': 'The connector report suggests a separate follow-up.', 'sig': 'new',
                              'action': {'type': 'task', 'mid': source}}, ago(1))
        funnel.settle(s, f'msg:{source}', 'surfaced')
        items = funnel.build(s)['items']
        self.assertIn(f"idea:{idea['IdeaId']}", [i['key'] for i in items])
        self.assertNotIn(f'msg:{source}', [i['key'] for i in items])


class FeedUnreadTests(unittest.TestCase):
    def test_all_and_unread_share_the_same_rows_until_the_owner_handles_one(self):
        """The Claude product email regression: All showed a filed/automated row while Unread used
        funnel.build() and silently filtered it.  Feed rows now carry the one durable distinction."""
        s = store()
        mid = mail(s, 'New ways to manage skills and messaging', who='Claude Team',
                   email='team@claude.com', body='Product update', status='filed')
        s.add_route(mid, None, 'file', None, 'triage: fyi product update', [], 'triage')
        row = next(r for r in s.feed() if r['MessageId'] == mid)
        self.assertEqual(row['Unread'], 1)
        self.assertEqual(row['FunnelKey'], f'msg:{mid}')
        funnel.settle(s, f'msg:{mid}', 'done')
        self.assertEqual(next(r for r in s.feed() if r['MessageId'] == mid)['Unread'], 0)

    def test_showing_a_row_marks_it_read_and_defer_temporarily_hides_it(self):
        s = store(); mid = mail(s, 'FYI', status='filed')
        funnel.settle(s, f'msg:{mid}', 'surfaced')
        self.assertEqual(s.feed()[0]['Unread'], 0)
        funnel.settle(s, f'msg:{mid}', 'later', hours=2)
        self.assertEqual(s.feed()[0]['Unread'], 0)

    def test_an_explicit_ignore_and_historical_rows_do_not_resurrect_as_unread(self):
        s = store()
        ignored = mail(s, 'Daily balance notice', status='ignored')
        old = mail(s, 'Already read yesterday', status='filed')
        s._exec("UPDATE message SET CreatedAt=datetime('now','localtime','-2 days') WHERE MessageId=?", (old,))
        by_id = {r['MessageId']: r for r in s.feed()}
        self.assertEqual((by_id[ignored]['Unread'], by_id[old]['Unread']), (0, 0))

    def test_unread_priority_uses_the_saved_triage_fields_without_reclassifying(self):
        s = store()
        fyi = mail(s, 'Claude product update', status='filed')
        task = s.create_task({'Title': 'Production is down', 'Kind': 'general', 'Status': 'open', 'Priority': 'urgent'}, 'o')
        urgent = mail(s, 'Production is down', tid=task)
        by_id = {r['MessageId']: r for r in s.feed()}
        self.assertEqual(by_id[urgent]['UnreadRank'], 1)
        self.assertEqual(by_id[fyi]['UnreadRank'], 4)

    def test_repeated_assistant_posts_follow_the_latest_idea_and_read_state(self):
        s = store()
        old = s.add_message({'ExternalId': 'a1', 'Channel': 'assistant', 'Subject': 'Gail still needs a sample',
                             'FromName': 'Assistant', 'SentAt': ago(2), 'BodyText': 'send it', 'Status': 'feed',
                             'Brief': json.dumps({'ideas': [{'id': 1}]})})
        s.set_brief(old, json.dumps({'ideas': [{'id': 1}]}))
        idea = s.upsert_idea({'key': 'gail-sample', 'kind': 'idea', 'text': 'Gail still needs a sample',
                              'sig': 'one', 'action': {'mid': 9}}, ago(2))
        new = s.add_message({'ExternalId': 'a2', 'Channel': 'assistant', 'Subject': 'Gail still needs a sample',
                             'FromName': 'Assistant', 'SentAt': ago(1), 'BodyText': 'send it', 'Status': 'feed',
                             'Brief': json.dumps({'ideas': [{'id': idea['IdeaId']}]})})
        s.set_brief(new, json.dumps({'ideas': [{'id': idea['IdeaId']}]}))
        s.set_ideas_message([idea['IdeaId']], new)
        by_id = {r['MessageId']: r for r in s.feed()}
        self.assertEqual((by_id[old]['Unread'], by_id[new]['Unread'], by_id[new]['FunnelKey']),
                         (0, 1, f"idea:{idea['IdeaId']}"))
        funnel.settle(s, f"idea:{idea['IdeaId']}", 'surfaced')
        self.assertEqual(next(r for r in s.feed() if r['MessageId'] == new)['Unread'], 0)

    def test_work_an_agent_has_stays_in_unread_but_never_becomes_the_next_chat_item(self):
        s = store()
        task = s.create_task({'Title': 'Import the files', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        mid = mail(s, 'Import the files', tid=task)
        live = [{'taskId': task, 'agent': 'codex', 'label': 'codex', 'started': ago(minutes=5),
                 'idle': 2, 'waiting': False, 'tail': ['working']}]
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            row = next(r for r in s.feed() if r['MessageId'] == mid)
            self.assertEqual((row['Unread'], row['UnreadRank'], row['Working']), (1, 5, 'codex'))
            self.assertEqual(row['FunnelKey'], f'agent:{task}')
            self.assertIsNone(funnel.next_item(s))
        waving = [dict(live[0], idle=200, waiting=True, tail=['Which region should I use?'])]
        with mock.patch('taskuary.terminal.live_sessions', return_value=waving):
            row = next(r for r in s.feed() if r['MessageId'] == mid)
            self.assertEqual((row['Unread'], row['UnreadRank']), (1, 2))
            self.assertEqual(funnel.next_item(s)['key'], f'agent:{task}')


class MemoryTests(unittest.TestCase):
    def _two(self):
        s = store()
        for n, h in (('one', 9), ('two', 4)):
            t = s.create_task({'Title': n, 'Kind': 'coding', 'Status': 'waiting'}, 'o')
            m = mail(s, n, hours=h, tid=t)
            s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': 'ok', 'Status': 'pending'})
        return s

    def test_read_is_gone_later_hides_until_its_time_and_done_removes(self):
        s = self._two()
        one, two = [i['key'] for i in funnel.build(s)['items']]
        funnel.settle(s, one, 'surfaced')
        items = funnel.build(s)['items']
        self.assertEqual([(i['key'], bool(i.get('surfaced'))) for i in items], [(one, True), (two, False)])   # a reply for your yes stays, marked
        self.assertEqual(funnel.next_item(s)['key'], two)
        self.assertEqual(funnel.next_item(s, one)['key'], one)          # but the named one is always reachable
        self.assertTrue(funnel.next_item(s, one)['surfaced'])
        out = funnel.settle(s, two, 'later', hours=2)
        self.assertTrue(out['until'] > ago(0))
        self.assertEqual([i['key'] for i in funnel.build(s)['items']], [one])
        funnel.settle(s, one, 'done')
        self.assertEqual(funnel.build(s, keep_surfaced=True)['items'], [])
        self.assertIsNone(funnel.next_item(s))

    def test_a_reply_shown_once_stays_and_a_rewritten_draft_is_new_again(self):
        s = self._two()
        one, two = [i['key'] for i in funnel.build(s)['items']]
        it = funnel.next_item(s, one)
        funnel.settle(s, one, 'surfaced', note=it['sig'])
        items = funnel.build(s)['items']
        self.assertEqual([(i['key'], bool(i.get('surfaced'))) for i in items], [(one, True), (two, False)])   # still in the pipe, marked
        self.assertEqual(funnel.next_item(s)['key'], two)                                              # not straight back on the table
        s.save_review_draft(int(one.split(':')[1]), 'The agent rewrote this after finishing the job.')
        items = funnel.build(s)['items']
        self.assertEqual([(i['key'], bool(i.get('surfaced'))) for i in items], [(one, False), (two, False)])  # changed: new again
        self.assertEqual(funnel.next_item(s)['key'], one)

    def test_a_new_chat_does_not_make_read_mail_new_again(self):
        s = self._two()
        one, two = [i['key'] for i in funnel.build(s)['items']]
        funnel.settle(s, one, 'surfaced'); funnel.settle(s, 'alert:x', 'ack')
        funnel.reset_walk(s)
        self.assertEqual([(i['key'], bool(i.get('surfaced'))) for i in funnel.build(s)['items']], [(one, True), (two, False)])
        self.assertNotIn('alert:x', s.funnel_states())

    def test_the_owners_knobs_bound_the_pile(self):
        s = store()
        for n in range(6):
            m = mail(s, f'note {n}', who=f'Person {n}', email=f'p{n}@ours.com', body='FYI, done.', hours=n * 5, status='filed', conv=f'c{n}')
            s.add_route(m, None, 'file', None, 'triage: fyi - a person told you something', [], 'triage')
        s.set_setting('team_domains', 'ours.com', 't')
        # the default window is twelve hours: notes 0, 1 and 2 are inside it, 3 to 5 are yesterday's
        self.assertEqual([i['title'] for i in funnel.build(s)['items']], ['note 2', 'note 1', 'note 0'])   # oldest first
        s.set_setting('funnel_hours', '48', 't')
        self.assertEqual(len(funnel.build(s)['items']), 6)
        s.set_setting('funnel_max', '2', 't')
        p = funnel.build(s)
        self.assertEqual(([i['title'] for i in p['items']], p['hidden']), (['note 5', 'note 4'], 4))
        # ...and what an agent has rides above the cap: the shelf is not the queue
        w = s.create_task({'Title': 'In hand', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        mail(s, 'In hand', hours=1, tid=w)
        live = [{'taskId': w, 'agent': 'codex', 'label': 'codex', 'started': ago(minutes=5), 'idle': 2, 'waiting': False, 'tail': []}]
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            p = funnel.build(s)
        self.assertEqual(([(i['title'], i['lane']) for i in p['items']], p['hidden']), ([('note 5', 'fyi'), ('note 4', 'fyi'), ('In hand', 'working')], 4))
        self.assertTrue(p['rev'].endswith(':4:0'), p['rev'])          # hidden by the cap, none held by a rule
        # a draft waiting for a yes ignores the window
        s.set_setting('funnel_hours', '1', 't'); s.set_setting('funnel_max', '25', 't')
        t = s.create_task({'Title': 'old ask', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        m = mail(s, 'old ask', hours=90, tid=t)
        s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': 'ok', 'Status': 'pending'})
        # note 0 is from just now; 'In hand' is on the shelf whether or not a session is alive - a task
        # whose status says in_progress is being worked (the owner, 2026-09-03)
        self.assertEqual([(i['title'], i['lane']) for i in funnel.build(s)['items']],
                         [('old ask', 'approve'), ('note 0', 'fyi'), ('In hand', 'working')])

    def test_one_line_per_thread_no_auto_replies_and_nothing_an_agent_is_working(self):
        s = store()
        s.set_setting('team_domains', 'ours.com', 't')
        for n in range(3):
            m = mail(s, f'Re: budget {n}', who='Lee', email='lee@ours.com', body='thoughts below', hours=n, status='filed', conv='budget')
            s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        m = mail(s, 'Automatic reply: out of office', who='Sam', email='sam@ours.com', body='Back Monday.', hours=1, status='filed', conv='ooo')
        s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        t = s.create_task({'Title': 'Fix the import', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        mail(s, 'Import broken', hours=1, tid=t)
        live = [{'taskId': t, 'agent': 'claude', 'label': 'claude', 'started': ago(minutes=5), 'idle': 3, 'waiting': False, 'tail': ['editing…']}]
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            items = funnel.build(s)['items']
        # the row reads triage's own title ("Fix the import") rather than the mail header it arrived
        # under ("Import broken") - funnel.says prefers Title now (the owner, 2026-09-16)
        self.assertEqual([(i['title'], i['kind'], i['lane']) for i in items], [('Re: budget 0', 'fyi', 'fyi'), ('Fix the import', 'todo', 'working')])

    def test_an_open_task_is_on_you_whatever_the_last_message_said(self):
        """TQ-0626 (the owner, 2026-09-18): a Teams ask became a task, the owner answered "done",
        the sender said "thanks" - and the chain sat in fyi with the task still open. The last line
        was triaged fyi, and the rule that keeps open work on the rail only fired when THAT line's own
        category was work. A thank-you is not work; the open task behind it is. The task being open
        is the fact, not what the newest message happened to be."""
        s = store()
        t = s.create_task({'Title': 'Change her clock-out time to 4:40', 'Kind': 'task', 'Status': 'open'}, 'o')
        ask = mail(s, 'clock-out', who='Robin', email='robin@ours.com', body='Can you change this to 4:40? Thanks!',
                   hours=10, tid=t, channel='teams', conv='room')
        s.add_route(ask, t, 'create', None, 'triage: task', [], 'router')
        s.add_message({'TaskId': t, 'ExternalId': 'x:mine', 'ConversationId': 'room', 'Channel': 'teams', 'SourceName': 'inbox',
                       'Subject': 'clock-out', 'FromName': 'You', 'FromEmail': 'me@ours.com', 'Direction': 'in',
                       'SentAt': ago(9.5), 'BodyText': 'done', 'Status': 'context'})
        thanks = mail(s, 'clock-out', who='Robin', email='robin@ours.com', body='thanks', hours=9, tid=t, status='filed',
                      channel='teams', conv='room')
        s.add_route(thanks, t, 'attach', 1.0, 'triage: fyi - a thank-you, nothing asked', [], 'triage')
        # the legacy pile has the wrap-up ("the reply went out - the task is still open"), which says
        # more than "on you" and still outranks the row (FollowUpTests)...
        self.assertEqual([(i['kind'], i['lane']) for i in funnel.build(s)['items']], [('wrapup', 'report')])
        # ...and the processing pile, the one the live rail reads and where TQ-0626 sat, has no wrap-up:
        # there the open task is the row, as the owner's own work
        settle = lambda: (s.reconcile_processing_membership(fixed_now=ago(0)), funnel.invalidate())
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        self.assertEqual([(i['title'], i['kind'], i['lane']) for i in funnel.build(s)['items'] if i.get('tid') == t],
                         [('Change her clock-out time to 4:40', 'todo', 'yours')])
        s.update_task(t, {'Status': 'done'}, 'o'); settle()             # ...and closing it is what takes the row away
        self.assertEqual([i['title'] for i in funnel.build(s)['items'] if i.get('tid') == t], [])

    def test_a_task_waiting_to_start_comes_round_again_once_the_hour_brings_it_back(self):
        """The owner, 2026-09-18: "it's not feeding the waiting to start task into assistant. It skipped
        it but then saw it at the end and hitting next just confuses it." Next put the queued row down
        as shown and read; the quiet hour brought it back unread (why_open) - but the shown mark stayed,
        since a new chat clears only agent: keys, so the walk never offered it again and stranded it at
        the end as "1 unread thing still waits. Say next", for as long as Next was pressed. The mark
        holds for the same hour the receipt does, and the row comes round with it."""
        from taskuary import concierge, funnel_selection, processing_unread
        s = store()
        s.upsert_agent('coder', 'coding', 'cli', '{}')
        t = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open', 'Assignee': 'agent:coder'}, 'o')
        mid = mail(s, 'export', who='Dana', email='dana@ours.com', hours=3, tid=t)
        s.add_route(mid, t, 'route', 1.0, 'triage: coding', [], 'triage')
        settle = lambda: (s.reconcile_processing_membership(fixed_now=ago(0)), funnel.invalidate())
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            first = concierge.surface(s, llm=lambda *a, **k: 'never')
            self.assertEqual((first['item']['lane'], first['item']['tid']), ('queued', t))
            again = concierge.surface(s, llm=lambda *a, **k: 'never', leaving=first['item']['key'])
            self.assertIsNone(again['item']); self.assertIn('already seen still waits', again['say'])   # put down: read, waiting in Passed (2026-09-23)
            later = datetime.now() + timedelta(hours=2)
            on_rail = [(i['lane'], bool(i.get('why_open')), bool(i.get('surfaced'))) for i in processing_unread.build(s, now=later, live_state=[])['items'] if i.get('tid') == t]
            self.assertEqual(on_rail, [('queued', True, False)])                                # the hour brought it back, and the mark went with it
            self.assertEqual(funnel_selection.capture_selection(s, now=later).selected['tid'], t)   # ...so the walk offers it again

    def _canonical(self):
        from taskuary import funnel as f
        s = store()
        settle = lambda: (s.reconcile_processing_membership(fixed_now=ago(0)), f.invalidate())
        return s, settle

    def test_next_on_your_own_task_leaves_it_in_passed_not_gone(self):
        """The owner, 2026-09-23: "i thought if you hit next it goes to passed section?" - Next read an open
        task and the rail dropped it for the hour. It is still theirs: on the rail, marked shown (Passed),
        not offered again by the walk, and not counted as waiting on a decision."""
        from taskuary import concierge, processing_unread
        s, settle = self._canonical()
        t = s.create_task({'Title': 'Month-end close is short', 'Kind': 'general', 'Status': 'open'}, 'o')
        mid = mail(s, 'Month-end close is short', who='Erin', email='erin@northwind.example', hours=3, tid=t)
        s.add_route(mid, t, 'route', 1.0, 'triage: task', [], 'triage')
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            first = concierge.surface(s, llm=lambda *a, **k: 'never')
            self.assertEqual(first['item']['tid'], t)
            again = concierge.surface(s, llm=lambda *a, **k: 'never', leaving=first['item']['key'])
            self.assertIsNone(again['item'])                                                  # the walk does not bring it straight back
            rail = [i for i in processing_unread.build(s, live_state=[])['items'] if i.get('tid') == t]
        self.assertEqual([(bool(i.get('surfaced')), i['actionable']) for i in rail], [(True, False)])   # ...but it is on the rail, in Passed
        self.assertEqual(s.get_task(t)['Status'], 'open')

    def test_a_task_its_agent_finished_shows_once_as_a_result(self):
        """"same for finished agent task?" - an agent that closed its task left nothing on the rail: the result
        the owner asked for was only on the Tasks tab. It is a result now, with Reports, until it is read."""
        from taskuary import processing_unread
        s, settle = self._canonical()
        t = s.create_task({'Title': 'AP clerk checklist', 'Kind': 'general', 'Status': 'open'}, 'o')
        s.add_message({'TaskId': t, 'ExternalId': 'own-1', 'Channel': 'own', 'Subject': 'AP clerk checklist',
                       'FromName': 'You', 'SentAt': ago(1), 'BodyText': 'write a checklist', 'Status': 'routed'})
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        s.add_comment(t, 'assistant', 'agent', 'The agent closed this itself: a ten-line checklist, on the task.')
        s.update_task(t, {'Status': 'done'}, 'assistant'); settle()
        card = [i for i in processing_unread.build(s, live_state=[])['items'] if i.get('tid') == t]
        self.assertEqual([(i['kind'], i['lane'], i['unread'], i.get('mid')) for i in card], [('agentdone', 'report', True, None)])
        self.assertIn('ten-line checklist', card[0]['summary'])
        self.assertEqual(card[0]['order_band'], 2)      # Your task - a task is never a report, and done is not 'working' (2026-09-24)
        # ...and put on the table (which reads it) it is STILL the agent's result, in Reports, until Next moves on
        # (the owner, 2026-09-24: "when bringing into assistant it disappears instead of staying on sidebar until
        # next") - the read flipped it to a closed fyi row, and the rail dropped the card the chat was showing
        from taskuary import concierge, funnel
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            key = concierge.surface(s, llm=lambda *a, **k: 'never')['item']['key']
        settle()
        # ...and the table says so: Current is what the page draws on the rail, and "its task is done" wiped it
        # the moment it went up - a finished agent's task is ALWAYS done (the owner, 2026-09-24, twice)
        from taskuary import general
        home = general.dock_task(s, 'owner')[0]['TaskId']
        self.assertEqual((concierge.restore_current(s, home) or {}).get('key'), key)
        self.assertEqual(concierge.current_key(s, home), key)
        here = funnel.next_item(s, key)
        self.assertEqual((here['kind'], here['lane']), ('agentdone', 'report'))
        self.assertFalse([i for i in processing_unread.build(s, live_state=[])['items'] if i.get('tid') == t])  # read: not waiting
        self.assertIn(t, s.worked_today_task_ids())      # ...but handled on the rail today: the Tasks tab and Board keep it
        # what the rail shows the Tasks tab shows, however long ago it closed ("regardless of when it was")
        s._exec('UPDATE task SET ClosedAt=?, UpdatedAt=? WHERE TaskId=?', (ago(days=2), ago(days=2), t))
        self.assertNotIn(t, [x['TaskId'] for x in s.list_tasks(active_only=True)])
        self.assertIn(t, [x['TaskId'] for x in s.list_tasks(active_only=True, also={t})])
        from taskuary import server
        with mock.patch.object(server, 'store', s), mock.patch.object(funnel, 'cached_pile', return_value={'items': [{'tid': t}]}):
            self.assertEqual(server._rail_tids(), {t})
        # ...and the card on the table counts, although showing it read it and the rail's own list lost it
        funnel.pile(s, force=True)
        with mock.patch.object(server, 'store', s), mock.patch.object(funnel, 'cached_pile', return_value={'items': []}):
            self.assertEqual(server._rail_tids(), {t})
        # ...closed by the OWNER it is simply gone
        u = s.create_task({'Title': 'Old thing', 'Kind': 'general', 'Status': 'open'}, 'o')
        s.update_task(u, {'Status': 'done'}, 'owner'); settle()
        self.assertFalse([i for i in processing_unread.build(s, live_state=[])['items'] if i.get('tid') == u])

    def test_a_finished_result_read_once_is_not_offered_again(self):
        """"make the Next button skip reports that have already been read" (2026-09-24): the task unit's read
        fingerprint carries its comments, so a note filed on the closed task after Next read the result put the
        same result back on Next. A reply from the sender after the close is still news and still returns."""
        from taskuary import concierge
        s, settle = self._canonical()
        t = s.create_task({'Title': 'Research the CLI tool', 'Kind': 'general', 'Status': 'open'}, 'o')
        mail(s, 'Research the CLI tool', who='Erin', email='erin@northwind.example', hours=2, tid=t)
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        s.add_comment(t, 'assistant', 'agent', 'The agent closed this itself: it wraps any CLI as an agent tool.')
        s.update_task(t, {'Status': 'done'}, 'assistant'); settle()
        def walk():
            with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
                got = concierge.surface(s, llm=lambda *a, **k: 'never')['item']
            settle(); return got and (got['kind'], got['tid'])
        self.assertEqual(walk(), ('agentdone', t))
        self.assertIsNone(walk())
        s.add_comment(t, 'owner', 'human', 'Thanks - noted.'); settle()
        self.assertIsNone(walk())                                   # a note on the closed task is not a new result
        s.add_message({'TaskId': t, 'ExternalId': 'out:reply', 'Channel': 'email', 'SourceName': 'inbox', 'Subject': 'Re: Research the CLI tool',
                       'FromName': 'Alex Doyle', 'FromEmail': 'alex@northwind.example', 'SentAt': ago(0), 'BodyText': 'Here is what it does.',
                       'Direction': 'out', 'Status': 'sent'}); settle()
        self.assertIsNone(walk())                                   # ...nor is the owner's own reply going out
        mail(s, 'Re: Research the CLI tool', who='Erin', email='erin@northwind.example', hours=0, tid=t); settle()
        self.assertEqual(walk(), ('agentdone', t))                  # ...their new mail is

    def test_a_pty_worker_that_ran_and_left_leaves_a_transcript_not_a_run(self):
        """A coder started from the terminal writes a TRANSCRIPT on its way out and no run row at
        all - the same row the task card reads to offer "Continue previous work". not_started_why
        only consulted runs, so a task an agent had actually worked and walked away from reported
        "it was handed to coder and nothing has started it" (TQ-0588/0589, 2026-09-16: six hours of
        it, with transcripts from copilot and from coder sitting right there)."""
        s = store()
        tid = s.create_task({'Title': 'Run the August audit', 'Kind': 'coding', 'Assignee': 'agent:coder'}, 'o')
        before = funnel.not_started_why(s, tid)
        self.assertNotIn('ran on this', before)                    # nothing has run yet, whatever the reason
        s.add_transcript(tid, 'sess-1', 'the agent said things', agent='coder')
        # ...and a transcript outranks every softer reason below it: "auto-start is off" is not why
        # this one is sitting there, because it plainly did start
        self.assertIn('ran on this and left without finishing it', funnel.not_started_why(s, tid))

    def test_answering_the_thread_does_not_finish_the_work(self):
        """NeedsYou is zeroed once the owner has answered or the ball is in the sender's court, which
        is right for a message waiting on a reply and wrong for an open task with work in it. TQ-0588
        was an open coding task assigned to the coder, nothing ticked off, and it left the rail the
        moment the owner replied to the mail that started it - filed into fyi behind seventy rows
        (2026-09-16). A reply is not the work."""
        s = store()
        tid = s.create_task({'Title': 'Run the August audit', 'Kind': 'coding',
                             'Assignee': 'agent:coder', 'Status': 'open'}, 'o')
        mid = mail(s, 'August audit', who='Dana', email='dana@vendor.com', hours=2, tid=tid)
        s.add_route(mid, tid, 'route', 1.0, 'triage: coding', [], 'triage')
        on_rail = lambda: [(i['lane'], i['tid']) for i in funnel.build(s)['items'] if i.get('tid') == tid]
        self.assertTrue(on_rail(), 'the task is on the rail before anyone replies')
        # the owner answers the thread from their own mailbox: the conversation is settled...
        s.add_message({'TaskId': tid, 'ExternalId': 'reply', 'ConversationId': 'August audit',
                       'Channel': 'email', 'FromEmail': 'owner@ours.com', 'Direction': 'out',
                       'SentAt': ago(hours=1), 'BodyText': 'looking at it', 'Status': 'context'})
        funnel.invalidate()
        # ...and the WORK is not. It stays where the owner can see it.
        self.assertTrue(on_rail(), 'an open coding task must not leave the rail because a reply went out')

    def test_unknown_verbs_are_refused(self):
        with self.assertRaises(ValueError): funnel.settle(store(), 'x', 'burn')

    def test_a_message_still_being_triaged_shows_but_is_not_talked_about_yet(self):
        s = store()
        mail(s, 'Just landed', hours=0, status='triaging')
        items = funnel.build(s)['items']
        self.assertEqual([(i['kind'], i['settling']) for i in items], [('triaging', True)])
        self.assertIsNone(funnel.next_item(s))
        self.assertIn('surfaced', funnel.VERBS)

    def test_a_low_priority_row_is_unread_and_can_be_pulled_into_the_chat_by_hand(self):
        s = store()
        m = mail(s, 'Weekly newsletter', who='news@vendor.com', email='news@vendor.com', body='Unsubscribe here. Manage your preferences.', status='filed')
        s.add_route(m, None, 'file', None, 'marketing - skim past', [], 'triage')
        self.assertEqual([(i['kind'], i['lane']) for i in funnel.build(s)['items']], [('fyi', 'fyi')])
        it = funnel.item_for_key(s, f'msg:{m}')
        self.assertEqual((it['kind'], it['lane'], it['mid']), ('fyi', 'fyi', m))
        self.assertEqual(it['why'], 'marketing - skim past')
        self.assertIsNone(funnel.item_for_key(s, 'msg:999')); self.assertIsNone(funnel.item_for_key(s, 'agent:1'))

    def test_summary_names_the_lanes_and_what_comes_next(self):
        s = self._two()
        text = funnel.summary(funnel.build(s)['items'])
        self.assertIn('LEFT IN THE PIPE: 2 - 2 reply ready', text)
        self.assertIn('Coming next: Dana - one (reply ready)', text)
        self.assertEqual(funnel.summary([]), 'THE PIPE IS EMPTY - nothing else needs the owner right now.')

    def test_the_pile_is_cached_briefly_and_carries_a_revision(self):
        s = self._two()
        p1 = funnel.pile(s)
        s.create_task({'Title': 'three', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        self.assertEqual(funnel.pile(s)['rev'], p1['rev'])              # within the cache window
        self.assertEqual(len(funnel.pile(s, force=True)['items']), 2)    # a task with no mail is not on the pile
        self.assertIn('alerts', p1); self.assertEqual(len(p1['rev'].split(':')[0]), 12)


if __name__ == '__main__':
    unittest.main()


class ABrokenConnectionSaysSoTests(unittest.TestCase):
    """A dead connection only ever landed in connector.LastError, on a page you have to go and open.
    The `broken` lane existed and was produced by exactly one thing: a failing REPORT. So a repo
    that 404s for a fortnight said nothing anywhere you look (the owner, 2026-09-18: "we should have
    notification for the github issue in the notification place")."""

    def setUp(self):
        self.s = MemoryStore()
        funnel.invalidate()

    def _broken(self, ctype, err):
        c = self.s.get_connector_by_type(ctype)
        self.s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Roles': 'trigger'}, 't')
        self.s.touch_connector(c['ConnectorId'], err)
        return c['ConnectorId']

    def test_a_connection_that_stopped_answering_is_on_the_rail(self):
        self._broken('github', 'northwind/ledger: no such repository - it was renamed or deleted')
        rows = funnel.broken_connections(self.s)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['lane'], 'broken')
        self.assertIn('github', rows[0]['title'].lower())
        self.assertIn('no such repository', rows[0]['why'])
        self.assertTrue(rows[0]['key'].startswith('conn:'))

    def test_a_healthy_connection_says_nothing(self):
        c = self.s.get_connector_by_type('github')
        self.s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Roles': 'trigger'}, 't')
        self.s.touch_connector(c['ConnectorId'], None)
        self.assertEqual(funnel.broken_connections(self.s), [])

    def test_a_connection_nobody_turned_on_is_not_broken(self):
        c = self.s.get_connector_by_type('github')
        self.s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 0}, 't')
        self.s.touch_connector(c['ConnectorId'], 'boom')
        self.assertEqual(funnel.broken_connections(self.s), [])

    def test_it_reaches_the_pile_the_rail_actually_draws(self):
        self._broken('github', 'northwind/ledger: no such repository')
        funnel.invalidate()
        keys = [i['key'] for i in funnel.pile(self.s, force=True)['items']]
        self.assertTrue(any(k.startswith('conn:') for k in keys), keys[:8])

    def test_next_walks_past_a_broken_connection_once_it_was_shown(self):
        """A broken connection is a condition with no receipt of its own - so Next put the same one back
        on the table on every press (the owner, 2026-09-23: "when I hit next it takes me back to linkedin
        failed"). Shown, it is walked past; a NEW error makes it news again."""
        cid = self._broken('github', 'northwind/ledger: no such repository')
        funnel.invalidate()
        first = funnel.next_item(self.s)
        self.assertEqual(first['key'], f'conn:{cid}')
        self.s.set_funnel_state(first['key'], 'surfaced', note=first.get('sig'))
        funnel.invalidate()
        again = funnel.next_item(self.s)
        self.assertNotEqual((again or {}).get('key'), first['key'])
        self.s.touch_connector(cid, 'a different failure: 401 unauthorised')
        funnel.invalidate()
        self.assertEqual((funnel.next_item(self.s) or {}).get('key'), first['key'], 'a new error is news again')

    def test_handled_puts_a_broken_connection_down_until_the_error_changes(self):
        """No task to close (the owner, 2026-09-23): Handled hides the row; a DIFFERENT failure is news."""
        cid = self._broken('github', 'northwind/ledger: no such repository')
        funnel.invalidate()
        funnel.settle(self.s, f'conn:{cid}', 'done')
        self.assertTrue(self.s.funnel_states()[f'conn:{cid}']['Note'])                  # it remembers which error
        funnel.invalidate()
        self.assertNotEqual((funnel.next_item(self.s) or {}).get('key'), f'conn:{cid}')
        self.s.touch_connector(cid, 'a different failure: 401 unauthorised')
        funnel.invalidate()
        self.assertEqual((funnel.next_item(self.s) or {}).get('key'), f'conn:{cid}', 'a new error comes back')

    def test_a_walked_past_error_is_not_kept_in_passed(self):
        """The rail reads the pile WITH what was read, and filed the walked-past error under Passed - so
        Next never made it go (the owner, 2026-09-23: "still see linkedin error. can't get rid of it")."""
        from taskuary import processing_unread
        cid = self._broken('linkedin', 'LinkedIn needs an access token')
        funnel.invalidate()
        key = f'conn:{cid}'
        sig = next(c['sig'] for c in funnel.broken_connections(self.s) if c['key'] == key)
        self.s.set_funnel_state(key, 'surfaced', note=sig)
        for inc in (False, True):
            keys = [i['key'] for i in processing_unread.build(self.s, include_read=inc)['items']]
            self.assertNotIn(key, keys, f'include_read={inc}')
        self.s.touch_connector(cid, 'LinkedIn: 401 unauthorised')
        self.assertIn(key, [i['key'] for i in processing_unread.build(self.s, include_read=True)['items']], 'a new error is news')

    def test_next_dismisses_an_error_until_it_changes(self):
        """An error is not work that comes back in an hour (the owner, 2026-09-23: "next on error should
        dismiss it no?"): walked past, it is not offered again - until the error itself changes."""
        cid = self._broken('github', 'northwind/ledger: no such repository')
        funnel.invalidate()
        first = funnel.next_item(self.s)
        self.s.set_funnel_state(first['key'], 'surfaced', note=first.get('sig'))
        self.s._exec("UPDATE funnel_state SET At=datetime('now', '-3 hours') WHERE Key=?", (first['key'],))
        funnel.invalidate()
        self.assertNotEqual((funnel.next_item(self.s) or {}).get('key'), first['key'], 'three hours on, still dismissed')
        self.s.touch_connector(cid, 'a different failure: 401 unauthorised')
        funnel.invalidate()
        self.assertEqual((funnel.next_item(self.s) or {}).get('key'), first['key'], 'a new error is news again')
