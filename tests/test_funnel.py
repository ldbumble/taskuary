"""The pipe (funnel.py): one ranked pile out of what the hub already knows, lanes in the order
a sharp assistant raises them, oldest first inside a lane, and a small memory of what was shown,
done and pushed back. No model anywhere."""
import json, unittest
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


class FollowUpTests(unittest.TestCase):
    """What a reply on an open task IS is triage's verdict, not the task's kind and not a keyword here
    (the owner, 2026-09-03: "Thank you is a close should not be hard coded"). ingest files an fyi
    follow-up onto the task; the pipe then reads the row's own category, and what is left for the
    owner is the wrap-up: your reply went out, the task is still open."""

    def test_an_fyi_follow_up_on_an_open_task_is_not_asked_you(self):
        s = store()
        t = s.create_task({'Title': 'Pto', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        mail(s, 'PTO', who='Chana', email='chana@hrtgcs.com', body='Can you import pto for Aug 9 thru Aug 22?', hours=8, tid=t, conv='c:pto')
        s.add_message({'TaskId': t, 'ExternalId': 'x:own', 'ConversationId': 'c:pto', 'Channel': 'email', 'Subject': 'RE: PTO', 'FromName': 'You',
                       'FromEmail': 'owner@ours.com', 'SentAt': ago(3), 'BodyText': 'Done. All PTO batches posted.', 'Status': 'context'})
        m = mail(s, 'RE: PTO', who='Chana', email='chana@hrtgcs.com', body='Thank you!', hours=1, tid=t, conv='c:pto', status='filed')
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
        mail(s, 'RE: PTO', who='Chana', email='chana@hrtgcs.com', body='Thanks! Can you also do the M44 period?', hours=1, tid=t, conv='c:pto2')
        self.assertEqual([(i['kind'], i['lane']) for i in funnel.build(s)['items']], [('todo', 'asked')])

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


class OneLinePerThreadTests(unittest.TestCase):
    def test_the_row_says_how_much_of_the_thread_it_stands_for(self):
        """Three lines in one WhatsApp room are one row - and the Timeline showing three of them read
        as the pipe losing two (the owner, 2026-09-03: "TImeline has 2 whatsapp while on the funnel
        it's only 1?")."""
        s = store()
        for n in range(3):
            m = mail(s, '', who='Gabi', email='', body=f'line {n}', hours=0, channel='whatsapp', conv='wa:gabi', status='filed')
            s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        items = funnel.build(s)['items']
        self.assertEqual([(i['who'], i.get('more')) for i in items], [('Gabi', 2)])
        # ...and a single line says nothing extra
        s2 = store()
        m = mail(s2, '', who='Gabi', email='', body='just one', hours=0, channel='whatsapp', conv='wa:one', status='filed')
        s2.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        self.assertIsNone(funnel.build(s2)['items'][0].get('more'))


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
        s.add_report_run(sid, {'at': ago(0), 'type': 'agent', 'title': 'Nightly headcount',
                               'subject': 'Nightly headcount — FAILED', 'failed': True, 'error': 'timed out'})
        funnel._SOURCES.update(at=0.0, by={})
        m = s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'SourceName': 'Nightly headcount',
                           'Subject': 'Nightly headcount', 'FromName': 'report', 'SentAt': ago(0),
                           'BodyText': 'nothing came back', 'Status': 'feed'})
        s.add_route(m, None, 'feed', None, 'a report you set up', [], 'feed')
        item = next(i for i in funnel.build(s)['items'] if i['kind'] == 'report')
        self.assertTrue(item['bad'])                     # the subject says nothing; the run says it failed
        self.assertIn('a report failed', item['why'])


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

    def test_the_same_line_is_slipped_once_the_agent_is_no_longer_on_it(self):
        s = store()
        t = s.create_task({'Title': 'July 2026 financials', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        self._line_about(s, t, f"TQ-{t:04d} July financials hasn't moved in three hours")
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            items = funnel.build(s)['items']
        self.assertEqual([(i['lane'], i['kind'], i['ref']) for i in items], [('forgotten', 'idea', f'TQ-{t:04d}')])

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
            m = mail(s, f'MFA Financial Report - .0{n} P&L', who='Nechama Ozur', email='nozur@hrtgcs.com',
                     body='generated by Intacct', hours=n + 1, status='filed')
            s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        keep = mail(s, 'RE: PointClickCare', who='Kishan', email='kishan@vendor.com', body='please respond', hours=1, status='filed')
        s.add_route(keep, None, 'file', None, 'triage: fyi', [], 'triage')
        self.assertEqual(len(funnel.build(s)['items']), 3)
        funnel.remember_mute(s, {'sender': 'nozur@hrtgcs.com', 'words': ['mfa', 'financials'], 'why': 'part of the financials process'}, 'o')
        p = funnel.build(s)
        self.assertEqual([i['who'] for i in p['items']], ['Kishan'])
        self.assertEqual((p['muted'], p['rules']), (2, ['part of the financials process']))
        # a rule reaches only the lanes with nothing to do
        t = s.create_task({'Title': 'Re-run .02', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        mail(s, 'MFA Financial Report - can you re-run .02?', who='Nechama Ozur', email='nozur@hrtgcs.com',
             body='please re-run it', hours=0, tid=t)
        funnel.invalidate()
        self.assertIn('asked', [i['lane'] for i in funnel.build(s)['items'] if i.get('tid') == t])
        # ...and it is the owner's to take off again
        funnel.remember_mute(s, {'sender': 'nozur@hrtgcs.com', 'words': ['mfa', 'financials'], 'why': 'x'}, 'o')
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
        self.assertEqual(keys, [('approve', 'review', 'Invoice question'), ('approve', 'review', 'Export still broken'),
                                ('report', 'report', 'Process Error Check FAILED')])          # a timeline: 30h old before 5h old
        report = funnel.build(s)['items'][-1]
        self.assertTrue(report['bad']); self.assertIn('failed', report['why'])

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
            self.assertEqual(funnel.next_item(s)['key'], f'agent:{t}')                        # half an hour on, it comes round again
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
        self.assertIn("codex is working on TQ-0001 (Pto) - nothing for you there now. Let's go to the next thing.", ev[0]['text'])
        with mock.patch('taskuary.terminal.live_sessions', return_value=working):
            self.assertEqual(funnel.announce(s), [])                                  # said once
        with mock.patch('taskuary.terminal.live_sessions', return_value=parked):
            ev = funnel.announce(s)
        self.assertEqual(ev[0]['kind'], 'asking'); self.assertIn('asked you something on TQ-0001', ev[0]['text']); self.assertEqual(ev[0]['card']['kind'], 'agent')
        s.add_comment(t, 'codex', 'agent', 'CODER REPORT' + chr(10) + 'Summary: imported all 80 PTO files; results mailed.')
        s.update_task(t, {'Status': 'done'}, 'o')
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            ev = funnel.announce(s)
            self.assertEqual(ev[0]['kind'], 'done'); self.assertIn('imported all 80 PTO files', ev[0]['text']); self.assertIn('task is closed', ev[0]['text'])
            self.assertIsNone(ev[0]['card'])
            self.assertEqual(funnel.announce(s), [])                                  # a closed task is not watched again
        # Status lines remain in the transcript, but a closed task never leaves a live card behind.
        hist = concierge.history(s, general.dock_task(s)[0]['TaskId'])
        self.assertEqual([(h['role'], (h['card'] or {}).get('kind')) for h in hist], [('assistant', None), ('assistant', 'agent'), ('assistant', None)])
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            self.assertIn('events', funnel.pile(s, force=True))

    def test_a_meeting_inside_two_hours_is_time_sensitive_and_inside_fifteen_minutes_interrupts(self):
        s = store()
        m1 = mail(s, 'Export still broken', hours=5)
        s.add_route(m1, None, 'file', None, 'triage: fyi - a person told you something', [], 'triage')
        ev = [{'start': ahead(10), 'end': ahead(40), 'subject': 'Standup', 'who': ['Priya Shah', 'Marcus Lee'], 'about': 'weekly', 'all_day': False},
              {'start': ahead(90), 'end': ahead(120), 'subject': 'Budget review', 'who': [], 'all_day': False},
              {'start': ahead(600), 'end': ahead(660), 'subject': 'Far away', 'who': [], 'all_day': False}]
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
        m2 = mail(s, 'RE: T&E Portal', who='Craig Neiswanger', email='craig@mfa.com', hours=0, tid=t)
        s.add_review({'TaskId': t, 'MessageId': m2, 'Kind': 'reply', 'DraftText': 'Yes, go ahead.', 'Status': 'pending'})
        p = funnel.build(s)
        al = funnel.alerts(s, p['items'])
        self.assertEqual([(a['kind'], a['lane'], a['text']) for a in al], [('review', 'approve', "Craig Neiswanger's reply is waiting for your yes")])
        fyi = next(i for i in p['items'] if i['lane'] == 'fyi')
        self.assertEqual([i['kind'] for i in funnel.more_urgent(p['items'], fyi['key'])], ['review'])
        self.assertEqual(funnel.more_urgent(p['items'], f'review:{s.list_reviews("pending")[0]["ReviewId"]}'), [])
        line = concierge._urgent_line(p['items'], fyi)
        self.assertIn('MORE URGENT WAITING', line); self.assertIn('Craig Neiswanger - RE: T&E Portal (needs your yes)', line)
        funnel.settle(s, f'review:{s.list_reviews("pending")[0]["ReviewId"]}', 'surfaced')
        self.assertEqual(funnel.alerts(s), [])                            # once shown, it is no longer news

    def test_a_task_whose_reply_went_out_and_agent_finished_asks_to_be_closed(self):
        s = store()
        t = s.create_task({'Title': 'T&e portal', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        m = mail(s, 'RE: T&E Portal', who='Craig', email='craig@mfa.com', hours=3, tid=t, conv='te')
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

    def test_the_assistants_open_lines_are_the_forgotten_lane(self):
        s = store()
        s.upsert_idea({'key': 'followup:c9', 'kind': 'followup', 'text': 'No answer from Dana in 4 days - follow up?', 'sig': 'x',
                       'action': {'type': 'followup', 'mid': 5, 'why': 'you asked on Monday'}}, ago(1))
        items = funnel.build(s)['items']
        self.assertEqual([(i['lane'], i['kind'], i['idea_kind']) for i in items], [('forgotten', 'idea', 'followup')])
        self.assertEqual(items[0]['why'], 'you asked on Monday')
        # a line about a task that has since closed is over, and is marked so
        done = s.create_task({'Title': 'Deploy gpt-4.1', 'Kind': 'coding', 'Status': 'done'}, 'o')
        s.upsert_idea({'key': 'cold:TQ-done', 'kind': 'cold', 'text': 'Deploy gpt-4.1 has sat quiet', 'sig': 'z', 'action': {'tid': done}}, ago(1))
        self.assertEqual([i['idea_kind'] for i in funnel.build(s)['items']], ['followup'])
        self.assertEqual(s.get_idea(next(i['IdeaId'] for i in s.list_ideas() if i['Key'] == 'cold:TQ-done'))['Status'], 'done')
        # ...and a line about a thread the owner has since replied on is over too
        s.set_setting('team_domains', 'ours.com', 't')
        mm = mail(s, 'PTO', who='Chana', email='chana@ours.com', hours=20, status='filed', conv='pto')   # a filed mail, past the window
        s.upsert_idea({'key': 'asked:pto', 'kind': 'asked', 'text': 'Chana asked for the PTO import', 'sig': 'p', 'action': {'type': 'message', 'mid': mm}}, ago(hours=2))
        self.assertIn('asked', [i.get('idea_kind') for i in funnel.build(s)['items']])
        rr = s.add_review({'TaskId': None, 'MessageId': mm, 'Kind': 'reply', 'DraftText': 'Imported, all 80 files.', 'Status': 'pending'})
        s.decide_review(rr, 'approved', 'Imported, all 80 files.', 'owner')
        self.assertNotIn('asked', [i.get('idea_kind') for i in funnel.build(s)['items']])
        self.assertEqual(next(i for i in s.list_ideas() if i['Key'] == 'asked:pto')['Status'], 'done')
        # ...and it enters when SAID: a line last raised days ago is not this morning's pipe
        s.upsert_idea({'key': 'cold:TQ-0009', 'kind': 'cold', 'text': 'TQ-0009 has sat quiet', 'sig': 'y', 'action': {'tid': 9}}, ago(days=3))
        self.assertEqual([i['idea_kind'] for i in funnel.build(s)['items']], ['followup'])

    def test_a_persons_ask_comes_before_follow_up_lines_and_reports_and_fyi_is_last(self):
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
        self.assertEqual([i['kind'] for i in funnel.build(s)['items']], ['review', 'todo', 'idea', 'report', 'fyi'])   # a person's ask before the assistant's line before a report

    def test_quiet_mail_stays_off_the_pile(self):
        s = store()
        m = mail(s, 'Weekly newsletter', who='news@vendor.com', email='news@vendor.com', body='Unsubscribe here. Manage your preferences.', status='filed')
        s.add_route(m, None, 'file', None, 'marketing', [], 'triage')
        self.assertEqual(funnel.build(s)['items'], [])


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
        self.assertEqual([(i['title'], i['kind'], i['lane']) for i in items], [('Re: budget 0', 'fyi', 'fyi'), ('Import broken', 'todo', 'working')])

    def test_unknown_verbs_are_refused(self):
        with self.assertRaises(ValueError): funnel.settle(store(), 'x', 'burn')

    def test_a_message_still_being_triaged_shows_but_is_not_talked_about_yet(self):
        s = store()
        mail(s, 'Just landed', hours=0, status='triaging')
        items = funnel.build(s)['items']
        self.assertEqual([(i['kind'], i['settling']) for i in items], [('triaging', True)])
        self.assertIsNone(funnel.next_item(s))
        self.assertIn('surfaced', funnel.VERBS)

    def test_a_quiet_row_can_still_be_pulled_into_the_chat_by_hand(self):
        s = store()
        m = mail(s, 'Weekly newsletter', who='news@vendor.com', email='news@vendor.com', body='Unsubscribe here. Manage your preferences.', status='filed')
        s.add_route(m, None, 'file', None, 'marketing - skim past', [], 'triage')
        self.assertEqual(funnel.build(s)['items'], [])
        it = funnel.item_for_key(s, f'msg:{m}')
        self.assertEqual((it['kind'], it['lane'], it['mid']), ('fyi', 'fyi', m))
        self.assertEqual(it['why'], 'marketing - skim past')
        self.assertIsNone(funnel.item_for_key(s, 'msg:999')); self.assertIsNone(funnel.item_for_key(s, 'agent:1'))

    def test_summary_names_the_lanes_and_what_comes_next(self):
        s = self._two()
        text = funnel.summary(funnel.build(s)['items'])
        self.assertIn('LEFT IN THE PIPE: 2 - 2 needs your yes', text)
        self.assertIn('Coming next: Dana - one (needs your yes)', text)
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
