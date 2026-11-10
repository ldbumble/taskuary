"""The pipe (funnel.py): one ranked pile out of what the hub already knows, lanes in the order
a sharp assistant raises them, oldest first inside a lane, and a small memory of what was shown,
done and pushed back. No model anywhere."""
import json, threading, time, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import funnel, lanes, railwalk
from taskuary.store import MemoryStore


def ago(hours=0, days=0, minutes=0):
    return (datetime.now() - timedelta(hours=hours, days=days, minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


def ahead(minutes=0):
    return (datetime.now() + timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled'): s.set_setting(k, '0', 't')
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

        def slow_build(_store, **_kw):
            calls.append(1); started.set(); release.wait(2)
            return {'rev': 'fresh', 'items': [], 'lanes': [], 'counts': {}}

        def read(): answers.append(funnel.pile(s, force=True)['rev'])

        with mock.patch.object(funnel, 'announce', return_value=[]), \
             mock.patch.object(funnel, 'build', side_effect=slow_build), \
             mock.patch.object(funnel, 'alerts', return_value=[]):
            first = threading.Thread(target=read); first.start(); self.assertTrue(started.wait(1))
            second = threading.Thread(target=read); second.start(); time.sleep(.03); release.set()
            first.join(2); second.join(2)
        self.assertEqual(calls, [1])
        self.assertEqual(answers, ['fresh', 'fresh'])

    def test_a_rebuild_that_began_before_a_write_is_not_shared_with_a_read_after_it(self):
        # PW-118: a comment landed on the next task while the page's own pile read was building; Next's admission waited on that
        # build and took it as its selection, then its commit check built again, with the comment, and refused the press
        s, top = store(), [1]
        started, release, calls, answers = threading.Event(), threading.Event(), [], []

        def slow_build(_store, **_kw):
            calls.append(1); started.set(); release.wait(2)
            return {'rev': f'build {len(calls)}', 'items': [], 'lanes': [], 'counts': {}}

        def read(**kw): answers.append(funnel.pile(s, observed=[], **kw)['rev'])

        with mock.patch.object(funnel, 'announce', return_value=[]), mock.patch.object(funnel, 'build', side_effect=slow_build), \
             mock.patch.object(funnel, 'alerts', return_value=[]), mock.patch.object(funnel, '_rail_top', side_effect=lambda _s: top[0]):
            first = threading.Thread(target=read, kwargs={'force': True}); first.start(); self.assertTrue(started.wait(1))
            top[0] = 2                                                     # the write, while the first build runs
            second = threading.Thread(target=read, kwargs={'quiet': True}); second.start(); time.sleep(.03); release.set()
            first.join(2); second.join(2)
        self.assertEqual(answers, ['build 1', 'build 2'])


    def test_a_forced_read_after_a_write_never_takes_a_rebuild_that_began_before_it(self):
        """A Done's rail rides along forced while a page's read is still building: that build began before the Done was
        written, so handing it over gave the answer the rail from before the write - stamped as read after it."""
        s = store()
        started, release, calls, answers, top = threading.Event(), threading.Event(), [], [], [1]

        def slow_build(_store, **_kw):
            n = len(calls); calls.append(1)
            if not n: started.set(); release.wait(2)
            return {'rev': f'build{n}', 'items': [], 'lanes': [], 'counts': {}}

        def read(): answers.append(funnel.pile(s, force=True, observed=[])['rev'])

        with mock.patch.object(funnel, 'announce', return_value=[]), \
             mock.patch.object(funnel, 'build', side_effect=slow_build), \
             mock.patch.object(funnel, 'alerts', return_value=[]), \
             mock.patch.object(funnel, '_rail_top', side_effect=lambda _s: top[0]):
            first = threading.Thread(target=read); first.start(); self.assertTrue(started.wait(1))
            top[0] = 2                                             # the write, after the first build took its mark
            second = threading.Thread(target=read); second.start(); time.sleep(.03); release.set()
            first.join(2); second.join(2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(answers, ['build0', 'build1'])

    def test_a_setting_rewritten_as_it_was_keeps_the_pile_warm(self):
        """A setting written on a loop with the value it already holds changed nothing, and still emptied the pile and left a dirty
        row - each rewrite a cold rebuild (2026-11-09). A new value, or a new writer, is still a write."""
        s = store()
        mail(s, 'Invoice 12', hours=1)
        s.set_setting('pane_geometry', '120x40', 'system'); s.set_setting('feed_days', '14', 'owner')
        builds, real = [], funnel.build
        with mock.patch.object(funnel, 'build', side_effect=lambda *a, **kw: builds.append(1) or real(*a, **kw)), \
             mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            funnel.invalidate(); funnel.pile(s); n, top = len(builds), s.rail_top()
            s.set_setting('pane_geometry', '120x40', 'system'); s.set_setting('feed_days', '14', 'owner'); funnel.pile(s)
            self.assertEqual((len(builds), s.rail_top()), (n, top), 'a rewrite of the same value rebuilt the pile')
            s.set_setting('feed_days', '7', 'owner'); funnel.pile(s)
            self.assertEqual(len(builds), n + 1, 'a new value must rebuild it')
        self.assertEqual(s.get_setting('feed_days'), '7')
        s.set_setting('feed_days', '7', 'migration'); self.assertEqual(s.setting_writer('feed_days'), 'migration')

    def test_a_working_agent_printing_keeps_the_pile_warm_and_its_row_shows_the_new_lines(self):
        """A working agent prints every second; its screen is not a new pile. Every line it printed threw the cached pile away, and the
        Advisor, the walk and each tab rebuilt it in turn - a Not for me sat ~45 s (2026-11-09). A parked agent's screen IS its card."""
        s = store()
        t = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        mail(s, 'Export still broken', hours=1, tid=t)
        def live(tail, waiting=False, files=()):
            return [{'sid': 's1', 'taskId': t, 'agent': 'claude', 'label': 'claude', 'started': ago(minutes=5), 'idle': 1,
                     'waiting': waiting, 'tail': tail, 'files': list(files)}]
        builds = []
        real = funnel.build
        def counted(*a, **kw): builds.append(1); return real(*a, **kw)
        with mock.patch.object(funnel, 'build', side_effect=counted):
            with mock.patch('taskuary.terminal.live_sessions', return_value=live(['reading export.py'])):
                self.assertEqual(funnel.pile(s)['items'][0]['lane'], 'working')
            n = len(builds)
            with mock.patch('taskuary.terminal.live_sessions', return_value=live(['editing export.py'], files=['export.py'])):
                # warm() never waits on a build (2026-11-09); one a neighbouring test left running may hold the lock a moment
                deadline = time.time() + 5
                while not funnel.warm(s) and time.time() < deadline: time.sleep(0.05)
                self.assertTrue(funnel.warm(s))
                row = funnel.pile(s)['items'][0]
            self.assertEqual(len(builds), n, 'a new line on a working screen rebuilt the pile')
            self.assertEqual((row['lane'], row['tail']), ('working', ['editing export.py']))       # ...and the row shows it all the same
            with mock.patch('taskuary.terminal.live_sessions', return_value=live(['Overwrite export.py? (y/n)'], waiting=True)):
                self.assertFalse(funnel.warm(s))                                                  # parked: a different pile
                funnel.pile(s)
            n = len(builds)
            with mock.patch('taskuary.terminal.live_sessions', return_value=live(['Delete the backup too? (y/n)'], waiting=True)):
                funnel.pile(s)
            self.assertEqual(len(builds), n + 1, "a parked agent's screen is what its card says")


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
                         (f'agent:{tid}', 'agent', 'stopped', True, 'assistant'))
        self.assertIn('sign-in page is open', item['tail'][0])

    def test_a_saved_or_failed_conversation_is_never_waiting_on_you(self):
        "No session is live on it, so nothing asks: the hand ('blocked') was untrue of every one (2026-10-22 walk)."
        from taskuary import terminal, workerstate as ws
        s = store()
        tid = s.create_task({'Title': 'Compare vendors', 'Kind': 'general', 'Status': 'open'}, 'owner')
        s.add_comment(tid, 'assistant', 'assistant_agent', 'Here is the comparison.')
        s.save_session(tid, 'cli:codex', '', 'native-1', 'context-1')
        paused = lambda: funnel.paused_conversation(s, {'key': 'msg:1', 'kind': 'todo', 'lane': 'asked', 'tid': tid, 'title': 't'})
        ws.record(s, tid, 'sid1', 'failed', text='No AI is connected - connect one', source='api')
        item = paused()
        self.assertEqual((item['lane'], item.get('failed')), ('stopped', True))
        self.assertTrue(item['why'].startswith('Failed - No AI is connected'), item['why'])
        s.tag_task(tid, terminal.SAVED, actor='owner')
        self.assertEqual(paused()['lane'], 'saved')
        self.assertFalse(any(a['item'] == f'agent:{tid}' for a in funnel.alerts(s, [paused()])), 'a saved agent interrupts nobody')

    def test_a_task_with_no_saved_conversation_stays_an_ordinary_task(self):
        s = store()
        tid = s.create_task({'Title': 'Call Dana', 'Kind': 'general', 'Status': 'open'}, 'owner')
        item = {'key': 'msg:1', 'kind': 'todo', 'lane': 'asked', 'tid': tid}
        self.assertEqual(funnel.paused_conversation(s, item), item)


class FollowUpTests(unittest.TestCase):
    """What a reply on an open task IS is triage's verdict, not the task's kind and not a keyword here
    (the owner, 2026-09-03: "Thank you is a close should not be hard coded"). ingest files an fyi
    follow-up onto the task; the pipe then reads the row's own category."""

    def test_a_follow_up_triage_kept_as_work_still_asks_you(self):
        s = store()
        t = s.create_task({'Title': 'Pto', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        s.add_message({'TaskId': t, 'ExternalId': 'x:own3', 'ConversationId': 'c:pto2', 'Channel': 'email', 'Subject': 'RE: PTO', 'FromName': 'You',
                       'FromEmail': 'owner@ours.com', 'SentAt': ago(3), 'BodyText': 'Done.', 'Status': 'context'})
        mail(s, 'RE: PTO', who='Erin', email='erin@vendor.example', body='Thanks! Can you also do the M44 period?', hours=1, tid=t, conv='c:pto2')
        self.assertEqual([(i['kind'], i['lane']) for i in funnel.build(s)['items']], [('todo', 'yours')])


class FlapTests(unittest.TestCase):
    """A CLI between two chunks of output can read parked for a moment. Narrating that moment - and
    then its opposite - is the "it stopped… no, it's working" the owner saw: "THe stopped coding and
    waiting for users is very buggy" (2026-09-03). A state is news only once it has HELD."""

    def _task(self, s):
        t = s.create_task({'Title': 'Run the Intacct connector', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        mail(s, 'Intacct', hours=1, tid=t)
        return t

    def _live(self, tid, **kw):
        return [{'taskId': tid, 'agent': 'coding', 'label': 'coding', 'started': ago(hours=1), 'tail': ['…'], **kw}]

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
        """The assistant's own follow-up line - as it writes them: the task it is about carried as the action's `tid`."""
        return s.upsert_idea({'key': f'loose:{tid}', 'kind': 'loose', 'text': text, 'sig': text[:40],
                              'action': {'type': 'task', 'tid': tid, 'section': 'loose',
                                         'why': f'OPEN WORK: TQ-{tid:04d} in_progress, 3h since anything happened'}}, ago(1))

    def test_a_task_named_only_in_the_words_is_not_the_lines_task(self):
        """The line's task is the structured `tid`, never a TQ ref read out of its text (the owner, 2026-10-11): a regex here
        tied an idea to whichever task its words named first."""
        s = store()
        t = s.create_task({'Title': 'July 2026 financials', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        s.upsert_idea({'key': 'idea:loose-words', 'kind': 'idea', 'text': f"Like TQ-{t:04d}, the August close needs a look", 'sig': 'aug',
                       'action': {'type': 'note', 'section': 'ideas', 'why': f'TQ-{t:04d} was the same shape'}}, ago(1))
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            items = [i for i in funnel.build(s)['items'] if i['kind'] == 'idea']
        self.assertEqual([(i['tid'], i['action'].get('tid')) for i in items], [(None, None)])


class LanesTests(unittest.TestCase):
    def test_a_send_the_mail_server_refused_says_not_sent_and_why(self):
        """It said "ready to send" over a reply the server had turned away, its reason a grey line on the card (UI audit 2026-10-21)."""
        s = store()
        t = s.create_task({'Title': 'Lease renewal', 'Kind': 'reply', 'Status': 'waiting'}, 'o')
        m = mail(s, 'Lease renewal', who='Erin Blake', email='erin@northwind.example', tid=t)
        rid = s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': 'Signed this morning.', 'Status': 'pending',
                            'Reason': 'Not sent: the mail server refused erin@northwind.example (5.1.1 no such user).'})
        it = funnel.build(s)['items'][0]
        self.assertEqual((it['lane'], it.get('not_sent')), ('approve', None))
        s._exec("UPDATE review SET DeliveryState='failed' WHERE ReviewId=?", (rid,)); funnel.invalidate()
        it = funnel.build(s)['items'][0]
        self.assertEqual((it['lane'], it['not_sent'], it['why']), ('approve', True, 'the mail server refused erin@northwind.example (5.1.1 no such user)'))

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
        # 30 hours old and still in the pipe
        # a check that could not run is the owner's task; the run that worked is a result below it
        self.assertLess(funnel._band(by['Process Error Check FAILED']), funnel._band(by['Headcount - 5 rows']))
        # a drafted reply and a failed check are both the owner's task now - one level, oldest first
        self.assertEqual(funnel._band({'lane': 'approve'}), funnel._band(by['Process Error Check FAILED']))
        self.assertNotIn('broken', funnel.MUTED_LANES)   # a rule that quiets a report cannot quiet it FAILING

    def test_the_watcher_turns_agent_transitions_into_lines_in_the_chat(self):
        from taskuary import concierge, general
        patch = mock.patch.object(funnel, 'DWELL', 0)                # this test is about the words, not the wait
        patch.start(); self.addCleanup(patch.stop)
        s = store()
        t = s.create_task({'Title': 'Pto', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        mail(s, 'PTO', hours=3, tid=t)
        parked = [{'taskId': t, 'agent': 'codex', 'label': 'codex', 'started': ago(hours=1), 'idle': 200, 'waiting': True, 'state': 'asking', 'tail': ['import now? (y/n)']}]
        working = [dict(parked[0], idle=2, waiting=False, state=None, tail=['editing…'])]
        with mock.patch('taskuary.terminal.live_sessions', return_value=parked):
            self.assertEqual(funnel.announce(s), [])                                  # the first look only remembers
        with mock.patch('taskuary.terminal.live_sessions', return_value=working):
            ev = funnel.announce(s)
        self.assertEqual([(e['kind'], e['tid']) for e in ev], [('working', t)])
        self.assertIn("Agent is working on TQ-0001 (Pto) - nothing for you there now.", ev[0]['text'])
        self.assertNotIn('next thing', ev[0]['text'])                                    # a worker starting is not a nudge to advance (PW-168)
        with mock.patch('taskuary.terminal.live_sessions', return_value=working):
            self.assertEqual(funnel.announce(s), [])                                  # said once
        with mock.patch('taskuary.terminal.live_sessions', return_value=parked):
            ev = funnel.announce(s)
        self.assertEqual(ev[0]['kind'], 'asking'); self.assertIn('asked you something on TQ-0001', ev[0]['text']); self.assertIsNone(ev[0]['card'])
        s.add_comment(t, 'codex', 'agent', 'AGENT REPORT' + chr(10) + 'Summary: imported all 80 PTO files; results mailed.')
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
        """The phone walk, 2026-09-10: four "coding agent is working on TQ-xxxx" notices, the newest two days
        old, replayed on every handoff - their tasks closed and their sessions ended long before."""
        s = store()
        t = s.create_task({'Title': 'Pto', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        funnel.notify(s, {'tid': t, 'ref': 'TQ-0001', 'kind': 'working', 'agent': 'codex',
                          'text': 'Agent is working on TQ-0001 (Pto) - nothing for you there now.'})
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
            far_row = railwalk.top(s)                        # ...walked in its place like a task (Q3, 2026-10-30), never urgent yet
            self.assertEqual(far_row['title'], 'Budget review'); self.assertFalse(lanes.is_urgent(far_row))
        with mock.patch.object(funnel, '_agenda', return_value=near):
            funnel.invalidate()
            nxt = railwalk.top(s)
        self.assertEqual((nxt['kind'], nxt['title']), ('meeting', 'Standup'))    # inside fifteen it is shaded urgent
        self.assertTrue(lanes.is_urgent(nxt))

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
        s.add_comment(t, 'claude', 'agent', 'AGENT REPORT\nSummary: the export dropped rows with commas; fixed the escaping.')
        s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': 'Fixed - the corrected file is attached.', 'Status': 'pending'})
        it = funnel.build(s)['items'][0]
        self.assertEqual(it['kind'], 'review'); self.assertIn('fixed the escaping', it['summary'])
        self.assertEqual(railwalk.top(s)['key'], it['key'])

    def test_a_closed_agent_job_never_reenters_the_funnel(self):
        s = store()
        t = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'done'}, 'o')
        s.add_comment(t, 'claude', 'agent', 'AGENT REPORT\nSummary: corrected the CSV escaping and added a test.')
        self.assertEqual(funnel.build(s)['items'], [])
        self.assertIsNone(funnel.next_item(s, f'done:{t}'))

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
        # task is before a reply drafted"), the landed report is a result below both, and the unjudged
        # idea leads the last level - its own section above FYI since the canvas redesign (2026-09-29).
        self.assertEqual([i['kind'] for i in funnel.build(s)['items']], ['todo', 'review', 'report', 'idea', 'fyi'])

    def test_marketing_mail_is_still_unread_until_the_owner_handles_it(self):
        s = store()
        m = mail(s, 'Weekly newsletter', who='news@vendor.com', email='news@vendor.com', body='Unsubscribe here. Manage your preferences.', status='filed')
        s.add_route(m, None, 'file', None, 'marketing', [], 'triage')
        self.assertEqual([(i['kind'], i['lane']) for i in funnel.build(s)['items']], [('fyi', 'fyi')])

    def test_a_read_source_row_does_not_hide_a_later_unread_assistant_idea(self):
        s = store()
        source = mail(s, 'Connector issue', conv='connector')
        idea = s.upsert_idea({'key': 'connector-followup', 'kind': 'idea',
                              'text': 'The connector report suggests a separate follow-up.', 'sig': 'new',
                              'action': {'type': 'task', 'mid': source}}, ago(1))
        funnel.settle(s, f'msg:{source}', 'surfaced')
        names = [a for i in funnel.build(s)['items'] for a in i['aliases']]
        self.assertIn(f"idea:{idea['IdeaId']}", names)
        self.assertNotIn(f'msg:{source}', names)


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

    def test_work_an_agent_has_stays_in_unread_and_is_walked_like_any_task(self):
        s = store()
        task = s.create_task({'Title': 'Import the files', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        mid = mail(s, 'Import the files', tid=task)
        live = [{'taskId': task, 'agent': 'codex', 'label': 'codex', 'started': ago(minutes=5),
                 'idle': 2, 'waiting': False, 'tail': ['working']}]
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            row = next(r for r in s.feed() if r['MessageId'] == mid)
            # the same level as any task, and the walk's item in its place (the owner, 2026-10-21)
            self.assertEqual((row['Unread'], row['UnreadRank'], row['Working']), (1, 2, 'Agent'))
            self.assertEqual(row['FunnelKey'], f'agent:{task}')
            self.assertEqual(railwalk.top(s)['tid'], task)
        waving = [dict(live[0], idle=200, waiting=True, tail=['Which region should I use?'])]
        with mock.patch('taskuary.terminal.live_sessions', return_value=waving):
            row = next(r for r in s.feed() if r['MessageId'] == mid)
            self.assertEqual((row['Unread'], row['UnreadRank']), (1, 2))
            self.assertIn(f'agent:{task}', railwalk.top(s)['aliases'])


class MemoryTests(unittest.TestCase):
    def _two(self):
        s = store()
        for n, h in (('one', 9), ('two', 4)):
            t = s.create_task({'Title': n, 'Kind': 'coding', 'Status': 'waiting'}, 'o')
            m = mail(s, n, hours=h, tid=t)
            s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': 'ok', 'Status': 'pending'})
        return s

    def test_a_reply_shown_once_stays_and_a_rewritten_draft_stays_too(self):
        """Shown is not acted on (2026-10-13): a reply for your yes put on the table stays in its place, and so does its rewrite -
        never walked past for having been shown (rule 6, 2026-10-30)."""
        s = self._two()
        one, two = [i['key'] for i in funnel.build(s)['items']]
        it = funnel.next_item(s, one)
        funnel.settle(s, one, 'surfaced', note=it['sig'])
        self.assertEqual([i['key'] for i in funnel.build(s)['items']], [one, two])
        self.assertEqual(railwalk.top(s)['key'], one)
        s.save_review_draft(it['rid'], 'The agent rewrote this after finishing the job.')
        self.assertEqual([i['key'] for i in funnel.build(s)['items']], [one, two])
        self.assertEqual(railwalk.top(s)['key'], one)

    def test_a_new_chat_does_not_make_read_mail_new_again(self):
        s = self._two()
        one, two = [i['key'] for i in funnel.build(s)['items']]
        funnel.settle(s, one, 'surfaced'); funnel.settle(s, 'alert:x', 'ack')
        funnel.reset_walk(s)
        self.assertEqual([i['key'] for i in funnel.build(s)['items']], [one, two])
        self.assertEqual(s.funnel_states()[one]['Status'], 'surfaced', 'read stays read')
        self.assertNotIn('alert:x', s.funnel_states())

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
        # the rail has no wrap-up row: the open task is the row, as the owner's own work
        settle = lambda: (s.reconcile_processing_membership(fixed_now=ago(0)), funnel.invalidate())
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        self.assertEqual([(i['title'], i['kind'], i['lane']) for i in funnel.build(s)['items'] if i.get('tid') == t],
                         [('Change her clock-out time to 4:40', 'todo', 'yours')])
        s.update_task(t, {'Status': 'done'}, 'o'); settle()             # ...and closing it is what takes the row away
        self.assertEqual([i['title'] for i in funnel.build(s)['items'] if i.get('tid') == t], [])

    def test_a_task_waiting_to_start_is_walked_again_by_the_next_walk(self):
        """The owner, 2026-09-18: "it's not feeding the waiting to start task into assistant. It skipped it but then saw it at the end
        and hitting next just confuses it." Next on it writes nothing now (2026-10-30): it stays under Tasks, the end of the walk
        offers it, and Walk starts on it again - no hour, no mark."""
        from taskuary import concierge, processing_unread, railwalk
        s = store()
        s.upsert_agent('coding', 'coding', 'cli', '{}')
        t = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open', 'Assignee': 'agent:coding'}, 'o')
        mid = mail(s, 'export', who='Dana', email='dana@ours.com', hours=3, tid=t)
        s.add_route(mid, t, 'route', 1.0, 'triage: coding', [], 'triage')
        settle = lambda: (s.reconcile_processing_membership(fixed_now=ago(0)), funnel.invalidate())
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            first = concierge.surface(s, llm=lambda *a, **k: 'never')
            self.assertEqual((first['item']['lane'], first['item']['tid']), ('queued', t))
            again = concierge.surface(s, llm=lambda *a, **k: 'never', from_key=first['item']['key'])
            self.assertIsNone(again['item']); self.assertEqual([c.get('key') for c in again['chips']][1:], [first['item']['key']])
            on_rail = [(i['lane'], bool(i.get('surfaced'))) for i in processing_unread.build(s, live_state=[])['items'] if i.get('tid') == t]
            self.assertEqual(on_rail, [('queued', False)])
            self.assertEqual(railwalk.start(s)['item']['tid'], t)

    def _canonical(self):
        from taskuary import funnel as f
        s = store()
        settle = lambda: (s.reconcile_processing_membership(fixed_now=ago(0)), f.invalidate())
        return s, settle

    def test_next_on_your_own_task_leaves_it_in_passed_not_gone(self):
        """The owner, 2026-09-23: "i thought if you hit next it goes to passed section?" - Next read an open
        task and the rail dropped it for the hour. It is still theirs: on the rail, marked shown (Passed),
        not offered again by the walk, and not counted as waiting on a decision.

        ...for the rest of THIS walk (the owner, 2026-10-21): here it was the last thing, so the walk ran out and the next one
        starts with it again - under Tasks, offered, no mark."""
        from taskuary import concierge, general, processing_unread
        s, settle = self._canonical()
        t = s.create_task({'Title': 'Month-end close is short', 'Kind': 'general', 'Status': 'open'}, 'o')
        mid = mail(s, 'Month-end close is short', who='Erin', email='erin@northwind.example', hours=3, tid=t)
        s.add_route(mid, t, 'route', 1.0, 'triage: task', [], 'triage')
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            first = concierge.surface(s, llm=lambda *a, **k: 'never')
            self.assertEqual(first['item']['tid'], t)
            again = concierge.surface(s, llm=lambda *a, **k: 'never', from_key=first['item']['key'])
            self.assertIsNone(again['item'])                                                  # the walk does not bring it straight back
            self.assertEqual(again['say'], '')                                                  # its Open is the line (2026-10-23)
            self.assertEqual([c.get('verb') for c in again['chips']], ['walk', 'open'])
            # ...and the card it left wears Next - passed, not read: the task is still yours (2026-10-23)
            dock = general.dock_task(s)[0]['TaskId']
            worn = [json.loads(m.group(1)).get('pressed') for c in s.list_comments(dock) if (m := concierge._MARK.search(c.get('Body') or ''))]
            self.assertIn('Next', worn); self.assertNotIn('Read', worn)
            rail = [i for i in processing_unread.build(s, live_state=[])['items'] if i.get('tid') == t]
        self.assertEqual([(bool(i.get('surfaced')), i['actionable']) for i in rail], [(False, True)])   # ...on the rail, the next walk's first
        self.assertEqual(s.get_task(t)['Status'], 'open')

    def test_a_task_opened_is_still_walked_first(self):
        """The owner, 2026-10-14: "it skipped the first task again in walk through" - a task opened from the rail is read, and the walk
        took any read for a pass. Nothing is a pass now (2026-10-30): the walk starts at the top, the opened task included."""
        from taskuary import processing_unread, railwalk
        s, settle = self._canonical()
        t = s.create_task({'Title': 'Simplify the export', 'Kind': 'task', 'Status': 'open'}, 'o')
        mid = mail(s, 'Simplify the export', who='Erin', email='erin@northwind.example', hours=3, tid=t)
        s.add_route(mid, t, 'route', 1.0, 'triage: task', [], 'triage')
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            key = next(i['key'] for i in processing_unread.build(s, live_state=[])['items'] if i.get('tid') == t)
            s.set_funnel_state(key, 'surfaced', read=True); settle()                 # opened: read, shown
            card = next(i for i in processing_unread.build(s, live_state=[])['items'] if i.get('tid') == t)
            self.assertTrue(card['actionable'])
            self.assertEqual(railwalk.start(s)['item']['tid'], t)

    def test_a_task_its_agent_finished_stays_in_tasks_until_read(self):
        """"same for finished agent task?" - an agent that closed its task left nothing on the rail: the result
        the owner asked for was only on the Tasks tab. It is on the rail until it is read - in TASKS, its task lane, never under
        Reports (the owner, 2026-11-02: "when an agent closes a task on its own it should not be in reports - it stays in Tasks
        until read")."""
        from taskuary import lanes, processing_unread
        s, settle = self._canonical()
        t = s.create_task({'Title': 'AP clerk checklist', 'Kind': 'general', 'Status': 'open'}, 'o')
        s.add_message({'TaskId': t, 'ExternalId': 'own-1', 'Channel': 'own', 'Subject': 'AP clerk checklist',
                       'FromName': 'You', 'SentAt': ago(1), 'BodyText': 'write a checklist', 'Status': 'routed'})
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        s.add_comment(t, 'assistant', 'agent', 'The agent closed this itself: a ten-line checklist, on the task.')
        s.update_task(t, {'Status': 'done'}, 'assistant'); settle()
        card = [i for i in processing_unread.build(s, live_state=[])['items'] if i.get('tid') == t]
        self.assertEqual([(i['kind'], i['lane'], i['unread'], i.get('mid')) for i in card], [('agentdone', 'yours', True, None)])
        self.assertIn('ten-line checklist', card[0]['summary'])
        self.assertEqual((card[0]['order_band'], lanes.level_of(card[0])), (2, 'task'))    # under Tasks, at its arrival place
        # ...and put on the table it is STILL the agent's result, in Tasks, until Next moves on (the owner, 2026-09-24: "when
        # bringing into assistant it disappears instead of staying on sidebar until next") - opening never reads (rule 4)
        from taskuary import concierge, funnel, railwalk
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            key = concierge.surface(s, llm=lambda *a, **k: 'never')['item']['key']
        settle()
        self.assertTrue([i for i in processing_unread.build(s, live_state=[])['items'] if i.get('tid') == t], 'opened is not read')
        # ...and the table says so: Current is what the page draws on the rail, and "its task is done" wiped it
        # the moment it went up - a finished agent's task is ALWAYS done (the owner, 2026-09-24, twice)
        from taskuary import general
        home = general.dock_task(s, 'owner')[0]['TaskId']
        self.assertEqual((concierge.restore_current(s, home) or {}).get('key'), key)
        self.assertEqual(concierge.current_key(s, home), key)
        here = funnel.next_item(s, key)
        self.assertEqual((here['kind'], here['lane']), ('agentdone', 'yours'))
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            railwalk.next(s, key)                            # Next reads it
        settle()
        self.assertFalse([i for i in processing_unread.build(s, live_state=[])['items'] if i.get('tid') == t])  # read: not waiting
        self.assertIn(t, s.worked_today_task_ids())      # ...but handled on the rail today: the Tasks tab and Board keep it
        # what the rail shows the Tasks tab shows, however long ago it closed ("regardless of when it was")
        s._exec('UPDATE task SET ClosedAt=?, UpdatedAt=? WHERE TaskId=?', (ago(days=2), ago(days=2), t))
        self.assertNotIn(t, [x['TaskId'] for x in s.list_tasks(active_only=True)])
        self.assertIn(t, [x['TaskId'] for x in s.list_tasks(active_only=True, also={t})])
        from taskuary import server
        with mock.patch.object(server, 'store', s), mock.patch.object(funnel, 'cached_pile', return_value={'items': [{'tid': t}]}):
            self.assertEqual(server._rail_tids(), {t})
        # ...and the card on the table counts, although Next read it and the rail's own list lost it
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            railwalk.open(s, key)                            # back on the table, by its row
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
            """A walk from the top, and Next on what it opens with - Next is what reads a result (rule 4, 2026-10-30)."""
            from taskuary import railwalk
            with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
                got = railwalk.start(s)['item']
                if got: railwalk.next(s, got['key'])
            settle(); return got and (got['kind'], got['tid'])
        self.assertEqual(walk(), ('agentdone', t))
        self.assertIsNone(walk())
        s.add_comment(t, 'owner', 'human', 'Thanks - noted.'); settle()
        self.assertIsNone(walk())                                   # a note on the closed task is not a new result
        s.add_message({'TaskId': t, 'ExternalId': 'out:reply', 'Channel': 'email', 'SourceName': 'inbox', 'Subject': 'Re: Research the CLI tool',
                       'FromName': 'Alex Doyle', 'FromEmail': 'alex@northwind.example', 'SentAt': ago(0), 'BodyText': 'Here is what it does.',
                       'Direction': 'out', 'Status': 'sent'}); settle()
        self.assertIsNone(walk())                                   # ...nor is the owner's own reply going out
        s.add_message({'TaskId': t, 'ExternalId': 'report:again', 'Channel': 'report', 'SourceName': 'Nightly check', 'Subject': 'Nightly check - the same',
                       'FromName': 'Nightly check', 'SentAt': ago(0), 'BodyText': 'Same failure as yesterday.', 'Status': 'filed'}); settle()
        self.assertIsNone(walk())                                   # ...nor a repeat triage FILED on it as nothing new (2026-09-25)
        mail(s, 'Re: Research the CLI tool', who='Erin', email='erin@northwind.example', hours=0, tid=t); settle()
        self.assertEqual(walk(), ('agentdone', t))                  # ...their new mail is

    def test_a_finished_result_stays_read_when_the_advisor_says_its_idea_again(self):
        """"i clicked next on this text which should dismiss it but it's coming back" (2026-09-25): an Advisor idea
        about the finished task was said again overnight - same key, reworded by the model - and the rewording is
        new fingerprint, so the whole finished result was back on Next. A re-said idea read before is not news; an
        the Advisor's ideas have their own cards, so no idea brings a finished result back."""
        from taskuary import concierge
        s, settle = self._canonical()
        t = s.create_task({'Title': 'Look into the failed alert', 'Kind': 'coding', 'Status': 'open'}, 'o')
        mail(s, 'Look into the failed alert', who='Erin', email='erin@northwind.example', hours=2, tid=t)
        say = lambda text, key='idea:alert': s.upsert_idea({'key': key, 'kind': 'idea', 'text': text, 'sig': text[:40],
                                                           'action': {'type': 'task', 'tid': t, 'title': 'Check the allowlist'}}, ago(0))
        say('The alert failed because the group is refused, not a bug.')
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        s.add_comment(t, 'assistant', 'agent', 'The agent closed this itself: the group is refused on purpose.')
        s.update_task(t, {'Status': 'done'}, 'assistant'); settle()
        def walk():
            """A walk from the top, and Next on what it opens with - Next is what reads a result (rule 4, 2026-10-30)."""
            from taskuary import railwalk
            with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
                got = railwalk.start(s)['item']
                if got: railwalk.next(s, got['key'])
            settle(); return got and (got['kind'], got['tid'])
        self.assertEqual(walk(), ('agentdone', t))
        self.assertIsNone(walk())
        say('TQ-0001 found the alert was refused by configuration - check the allowlist.'); settle()
        self.assertIsNone(walk())                                   # the same idea, reworded, is not a new result
        say('A second group is refused the same way.', key='idea:alert-2'); settle()
        self.assertIsNone(walk())                                   # ...nor a new one: an idea is its own card (2026-09-25)

    def test_a_task_the_owner_closed_by_sending_the_reply_is_not_agent_finished(self):
        """The agent finished, a reply was drafted, the task waited - and the owner's send closed it minutes later.
        Inside the evidence window that close was credited to the agent, and two answered tasks came back as "agent
        finished"; an unread Advisor idea on a finished task held it there too (2026-09-25)."""
        from taskuary import processing_unread
        s, settle = self._canonical()
        t = s.create_task({'Title': 'Grant budget access', 'Kind': 'general', 'Status': 'open'}, 'o')
        mail(s, 'Grant budget access', who='Erin', email='erin@northwind.example', hours=2, tid=t)
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        s.add_comment(t, 'coding', 'agent', 'The agent closed this itself: access granted.')
        s.update_task(t, {'Status': 'done'}, 'coding'); settle()
        s.add_comment(t, 'owner', 'human', 'Closed - the reply went out.')
        s.update_task(t, {'Status': 'done'}, 'owner'); settle()                    # the send is the owner's edit (verdicts)
        self.assertFalse([i for i in processing_unread.build(s, live_state=[])['items'] if i.get('tid') == t])
        u = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 'o')
        mail(s, 'Fix the export', who='Erin', email='erin@northwind.example', hours=2, tid=u)
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        s.add_comment(u, 'coding', 'agent', 'The agent closed this itself: fixed.')
        s.update_task(u, {'Status': 'done'}, 'coding'); settle()
        from taskuary import concierge
        from taskuary import railwalk
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            railwalk.next(s, concierge.surface(s, llm=lambda *a, **k: 'never')['item']['key'])   # the result opened, and Next reads it
        settle()
        s.upsert_idea({'key': 'idea:export-again', 'kind': 'idea', 'text': 'The export fix may not hold.', 'sig': 'x',
                       'action': {'type': 'note', 'tid': u}}, ago(0)); settle()
        self.assertFalse([i for i in processing_unread.build(s, live_state=[])['items'] if i.get('tid') == u and i.get('unread')])

    def test_a_finished_result_stays_read_when_its_mail_was_read_long_before_the_close(self):
        """The same ask, TQ-0740: the read that counts is the task's own, after the close. A note filed on the closed
        task changes the task's fingerprint, and the newest read left was the mail's, from BEFORE the agent closed it
        - so the result read as unread again and Next offered it a second time. Read in the same second it closed,
        the test above could not see this."""
        from taskuary import concierge
        s, settle = self._canonical()
        t = s.create_task({'Title': 'Research the CLI tool', 'Kind': 'general', 'Status': 'open'}, 'o')
        mail(s, 'Research the CLI tool', who='Erin', email='erin@northwind.example', hours=2, tid=t)
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        def walk():
            """A walk from the top, and Next on what it opens with - Next is what reads a result (rule 4, 2026-10-30)."""
            from taskuary import railwalk
            with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
                got = railwalk.start(s)['item']
                if got: railwalk.next(s, got['key'])
            settle(); return got and (got['kind'], got['tid'])
        key = next(i['key'] for i in funnel.pile(s, force=True)['items'] if i.get('tid') == t)
        funnel.settle(s, key, 'surfaced', read=True)                # the owner read the ask while the agent worked it...
        s._exec('UPDATE processing_read_receipt SET ReadAt=?', (ago(1),))                  # ...an hour ago
        s.add_comment(t, 'assistant', 'agent', 'The agent closed this itself: it wraps any CLI as an agent tool.')
        s.update_task(t, {'Status': 'done'}, 'assistant'); settle()
        self.assertEqual(walk(), ('agentdone', t))
        self.assertIsNone(walk())
        s.add_comment(t, 'owner', 'human', 'Thanks - noted.'); settle()
        self.assertIsNone(walk())                                   # the mail's old read does not un-read the result
        mail(s, 'Re: Research the CLI tool', who='Erin', email='erin@northwind.example', hours=0, tid=t); settle()
        self.assertEqual(walk(), ('agentdone', t))                  # ...their new mail still brings it back

    def test_a_pty_worker_that_ran_and_left_leaves_a_transcript_not_a_run(self):
        """A coding agent started from the terminal writes a TRANSCRIPT on its way out and no run row at
        all - the same row the task card reads to offer "Continue previous work". not_started_why
        only consulted runs, so a task an agent had actually worked and walked away from reported
        "it was handed to coding agent and nothing has started it" (TQ-0588/0589, 2026-09-16: six hours of
        it, with transcripts from copilot and from coding agent sitting right there)."""
        s = store()
        tid = s.create_task({'Title': 'Run the August audit', 'Kind': 'coding', 'Assignee': 'agent:coding'}, 'o')
        before = funnel.not_started_why(s, tid)
        self.assertNotIn('ran on this', before)                    # nothing has run yet, whatever the reason
        s.add_transcript(tid, 'sess-1', 'the agent said things', agent='coding')
        # ...and a transcript outranks every softer reason below it: "auto-start is off" is not why
        # this one is sitting there, because it plainly did start
        self.assertIn('ran on this and left without finishing it', funnel.not_started_why(s, tid))

    def test_answering_the_thread_does_not_finish_the_work(self):
        """NeedsYou is zeroed once the owner has answered or the ball is in the sender's court, which
        is right for a message waiting on a reply and wrong for an open task with work in it. TQ-0588
        was an open coding task assigned to the coding agent, nothing ticked off, and it left the rail the
        moment the owner replied to the mail that started it - filed into fyi behind seventy rows
        (2026-09-16). A reply is not the work."""
        s = store()
        tid = s.create_task({'Title': 'Run the August audit', 'Kind': 'coding',
                             'Assignee': 'agent:coding', 'Status': 'open'}, 'o')
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
        self.assertIsNone(railwalk.top(s))
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
        self.assertIn('LEFT IN THE PIPE: 2 - 2 ready to send', text)
        self.assertIn('Coming next: Dana - one (ready to send)', text)
        self.assertEqual(funnel.summary([]), 'THE PIPE IS EMPTY - nothing else needs the owner right now.')


if __name__ == '__main__':
    unittest.main()


class AFailingConnectionIsTheBellsTests(unittest.TestCase):
    """The owner, 2026-10-26: "let's remove that row. it should be only in errors logo in corner" - a failing connection
    was a "stopped answering" row on the rail AND a line on the bell; now it is the bell's alone (problems.py)."""

    def test_a_failing_connection_is_on_the_bell_and_not_on_the_rail(self):
        s = MemoryStore(); funnel.invalidate()
        c = s.get_connector_by_type('github')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Roles': 'trigger'}, 't')
        s.touch_connector(c['ConnectorId'], 'northwind/ledger: no such repository')
        s._exec('UPDATE connector SET LastErrorAt=? WHERE ConnectorId=?',
                ((datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S'), c['ConnectorId']))
        from taskuary import problems
        self.assertIn(f"connector:{c['ConnectorId']}", {p['key'] for p in problems.collect(s)})
        self.assertFalse([i for i in funnel.pile(s, force=True)['items'] if i['key'].startswith('conn:')])
        self.assertFalse(hasattr(funnel, 'broken_connections'))


def test_a_closed_task_looked_up_by_any_road_says_it_is_closed():
    # the owner, 2026-11-08: a done task opened from Search was drawn under Tasks - the page draws none for a `closed` card (pulledRow)
    from taskuary import funnel
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = s.create_task({'Title': 'Payworth renewal', 'Kind': 'task', 'Status': 'open'}, 'owner')
    s.update_task(tid, {'Status': 'done'}, 'owner')
    assert funnel.item_for_key(s, f'task:{tid}')['closed'] is True
    assert (funnel.next_item(s, f'task:{tid}', include_surfaced=True) or {'closed': True})['closed'] is True
    assert funnel.shut(s, {'tid': s.create_task({'Title': 'Open one', 'Kind': 'task', 'Status': 'open'}, 'owner')}).get('closed') is None
