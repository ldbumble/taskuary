"""The owner's calendar in replies about time (calendar.py): what counts as 'about time', how
the agenda renders, what the responder is told - and that a calendar that cannot be read makes
the draft hedge rather than promise. Graph and Google are faked; no network."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import calendar as cal, responder
from taskuary.store import MemoryStore


class AboutTimeTests(unittest.TestCase):
    def test_scheduling_talk_is_recognised_and_ordinary_mail_is_not(self):
        for t in ('are you available Tuesday at 1:00pm?', 'can we meet next week', 'free tomorrow?', 'call me at 3pm', 'reschedule the 8/29'):
            self.assertTrue(cal.about_time(t), t)
        for t in ('please fix the export', 'attached is the refund paperwork', 'thanks!'):
            self.assertFalse(cal.about_time(t), t)


def fake_graph(events):
    class R:
        status_code = 200
        text = ''
        def json(self): return {'value': events}
    return lambda url, **kw: R()


class AgendaTests(unittest.TestCase):
    def _store(self):
        s = MemoryStore()
        ol = s.get_connector_by_type('outlook')
        s.save_connector({'ConnectorId': ol['ConnectorId'], 'Active': 1, 'Secret': 'sec',
                          'ConfigJson': json.dumps({'tenant_id': 't', 'client_id': 'c'})}, 't')
        s.save_source({'Channel': 'email', 'Address': 'me@corp.example', 'Owner': 'me', 'Active': 1, 'ConnectorId': ol['ConnectorId']}, 't')
        return s

    def test_busy_slots_render_by_day_and_free_days_are_named(self):
        s = self._store()
        d = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        ev = [{'subject': 'Budget review', 'start': {'dateTime': f'{d}T13:00:00.0000000'}, 'end': {'dateTime': f'{d}T14:00:00.0000000'},
               'showAs': 'busy', 'location': {'displayName': 'Room 2'}},
              {'subject': 'Lunch', 'start': {'dateTime': f'{d}T12:00:00.0000000'}, 'end': {'dateTime': f'{d}T12:30:00.0000000'}, 'showAs': 'free'}]
        with mock.patch('taskuary.channels.graph_token', return_value='tok'), mock.patch('taskuary.calendar.requests.get', fake_graph(ev)):
            ag = cal.agenda(s, days=3)
        self.assertEqual([e['subject'] for e in ag['events']], ['Budget review'])          # 'free' slots are not busy
        text = cal.render(ag)
        self.assertIn('1:00-2:00 PM · Budget review · Room 2', text)
        self.assertIn('free all day', text)
        self.assertIn('outlook: me@corp.example', text)

    def test_a_forbidden_calendar_says_which_permission(self):
        s = self._store()
        class R: status_code = 403; text = 'Forbidden'
        with mock.patch('taskuary.channels.graph_token', return_value='tok'), mock.patch('taskuary.calendar.requests.get', lambda *a, **k: R()):
            ag = cal.agenda(s, days=3)
        self.assertEqual(ag['events'], []); self.assertIn('Calendars.Read', ag['errors'][0])
        self.assertIn('COULD NOT READ', cal.render(ag))

    def test_context_only_when_the_thread_is_about_time_and_the_switch_is_on(self):
        s = self._store()
        with mock.patch('taskuary.calendar.agenda', return_value={'events': [], 'errors': [], 'sources': ['outlook: me@corp.example'],
                                                                   'start': '2026-08-28T09:00:00', 'end': '2026-08-29T09:00:00', 'tz': 'UTC'}):
            self.assertIn('YOUR CALENDAR', cal.context_for(s, 'are you free Tuesday at 1?'))
            self.assertEqual(cal.context_for(s, 'please fix the export'), '')
            s.set_setting('calendar_enabled', '0', 't')
            self.assertEqual(cal.context_for(s, 'are you free Tuesday at 1?'), '')

    def test_no_calendar_source_means_no_paragraph(self):
        self.assertEqual(cal.context_for(MemoryStore(), 'free Tuesday?'), '')

    def test_the_tool_reads_the_same_thing(self):
        s = self._store()
        with mock.patch('taskuary.calendar.agenda', return_value={'events': [{'start': '2026-08-28 13:00', 'end': '2026-08-28 14:00', 'subject': 'x', 'all_day': False, 'status': 'busy', 'where': '', 'mailbox': 'm'}],
                                                                   'errors': [], 'sources': ['outlook: m'], 'start': '2026-08-28T09:00:00', 'end': '2026-08-29T09:00:00', 'tz': 'UTC'}):
            head, body = cal.run_calendar({'store': s, 'days': 1})
        self.assertEqual(head, '1 event(s) in the next 1 days'); self.assertIn('1:00-2:00 PM · x', body)


class ResponderTests(unittest.TestCase):
    def test_the_draft_prompt_carries_the_calendar_and_the_task_says_so(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Reimbursement app', 'Kind': 'reply', 'Status': 'open'}, 't')
        mid = s.add_message({'TaskId': tid, 'ExternalId': 'c1', 'Channel': 'email', 'Subject': 'Reimbursement App',
                             'FromEmail': 'marinda@corp.example', 'FromName': 'Marinda', 'SentAt': '2026-08-27 10:00:00', 'Status': 'routed',
                             'BodyText': 'Are you available Tuesday at 1:00pm to go over it?'})
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending'})
        seen = {}
        def llm(sys_, usr_, **k): seen['sys'] = sys_; return 'Tuesday at 1 I am in the budget review - could we do 2?'
        with mock.patch('taskuary.calendar.context_for', return_value='\n\nYOUR CALENDAR - ...\n  Tue 2026-09-01:\n    13:00-14:00 · Budget review'):
            out = responder.write_draft(s, tid, rid, llm=llm)
        self.assertIn('YOUR CALENDAR', seen['sys']); self.assertIn('Budget review', seen['sys'])
        self.assertIn('could we do 2', out)
        self.assertTrue(any('Checked your calendar' in c['Body'] for c in s.list_comments(tid)))


class AgendaNeverBlocksThePileTests(unittest.TestCase):
    """The pile reads the calendar (funnel.from_calendar -> assistant._agenda -> calendar.agenda
    -> channels.graph_token), and that is a LIVE Microsoft call: a token POST plus one
    calendarView per mailbox, 20s timeout each. The 60s cache meant most /api/funnel/pile calls
    were ~5s and whichever one refreshed was 45s (2026-09-09)."""

    # "did the refresh thread run at all" is a LIVENESS check, so it gets a generous budget. The
    # one real timing assertion in this class is `waited < 2` below, and that one stays tight.
    STARTED = 30

    def setUp(self):
        self._quiesce()                      # a refresh from the previous test can still be running
        self.addCleanup(self._quiesce)

    @classmethod
    def _quiesce(cls):
        """Let any refresh thread finish BEFORE clearing the cache, then clear it.

        Clearing it from under a running refresh is what made this class flaky. _read_agenda writes
        the `at` stamp back AFTER the clear, so the next test's `block=False` read finds a cache
        that looks fresh (line 286 of assistant.py returns early), no refresh is started at all,
        and its `started.wait(...)` times out with "False is not true". It failed exactly that way
        on macos-latest/3.10 three times (7205ed5, b1b613f), always at
        test_the_refresh_lands_for_the_next_reader, and never on a box fast enough to close the
        window between the clear and the leftover thread's write.
        """
        import threading
        from taskuary import assistant
        for t in threading.enumerate():
            if t.name == 'taskuary-agenda': t.join(cls.STARTED)
        assistant._AGENDA.clear()

    @staticmethod
    def _store():
        s = MemoryStore()
        s.set_setting('calendar_enabled', '1', 'test')
        return s

    @staticmethod
    def _slow(started, release, subject='Budget review'):
        def slow_agenda(store, days=2, start=None):
            started.set()
            release.wait(10)                     # a Graph call that is taking its time
            return {'events': [{'subject': subject, 'start': '2026-09-09T13:00:00', 'all_day': False}]}
        return slow_agenda

    def test_the_pile_does_not_wait_on_a_stale_calendar(self):
        import threading, time
        from taskuary import assistant, funnel
        s, started, release = self._store(), threading.Event(), threading.Event()
        with mock.patch('taskuary.calendar.agenda', self._slow(started, release)):
            t0 = time.perf_counter()
            funnel.from_calendar(s, datetime.now())          # the pile's calendar leg
            waited = time.perf_counter() - t0
            self.assertTrue(started.wait(self.STARTED), 'the refresh never ran')
            release.set()
        self.assertLess(waited, 2, f'the pile waited {waited:.1f}s on the calendar')

    def test_the_refresh_lands_for_the_next_reader(self):
        import threading, time
        from taskuary import assistant
        s, started, release = self._store(), threading.Event(), threading.Event()
        with mock.patch('taskuary.calendar.agenda', self._slow(started, release)):
            assistant._agenda(s, block=False)
            self.assertTrue(started.wait(self.STARTED), 'the refresh never ran')
            release.set()
            for _ in range(200):
                if assistant._AGENDA.get('events'): break
                time.sleep(.05)
        self.assertEqual([e['subject'] for e in assistant._agenda(s)], ['Budget review'])

    def test_a_brief_still_gets_the_meetings_it_is_composing_about(self):
        """prep() and the CALENDAR block feed a report, not a click. An empty calendar there is a
        WRONG brief, not a slow one, so those keep the blocking read."""
        import threading
        from taskuary import assistant
        s, started, release = self._store(), threading.Event(), threading.Event()
        release.set()                                        # the read completes normally
        with mock.patch('taskuary.calendar.agenda', self._slow(started, release, 'Board meeting')):
            self.assertEqual([e['subject'] for e in assistant._agenda(s)], ['Board meeting'])

    def test_only_one_refresh_runs_however_many_readers_ask(self):
        import threading
        from taskuary import assistant
        s, started, release, calls = self._store(), threading.Event(), threading.Event(), []
        def slow_agenda(store, days=2, start=None):
            calls.append(1); started.set(); release.wait(10)
            return {'events': []}
        with mock.patch('taskuary.calendar.agenda', slow_agenda):
            for _ in range(5): assistant._agenda(s, block=False)
            self.assertTrue(started.wait(self.STARTED), 'the refresh never ran')
            release.set()
        self.assertEqual(len(calls), 1, f'{len(calls)} concurrent Graph reads')

    def test_a_calendar_nobody_enabled_is_not_read_at_all(self):
        from taskuary import assistant
        s = MemoryStore()
        s.set_setting('calendar_enabled', '0', 'test')
        with mock.patch('taskuary.calendar.agenda', side_effect=AssertionError('must not be read')):
            self.assertEqual(assistant._agenda(s), [])


if __name__ == '__main__': unittest.main()
