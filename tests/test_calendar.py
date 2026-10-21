"""The owner's calendar in replies about time (calendar.py): what counts as 'about time', how
the agenda renders, what the responder is told - and that a calendar that cannot be read makes
the draft hedge rather than promise. Graph and Google are faked; no network."""
import json, unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from taskuary import calendar as cal, responder
from taskuary.store import MemoryStore


class NoWordListTests(unittest.TestCase):
    """A word list decided whether a reply saw the calendar, and "the 14th", "noon" and "sync" were not on it - so
    "Are you around on the 14th for a quick sync?" was answered "the 14th works" blind. The calendar now rides along
    whenever the switch is on, and the drafting model judges whether the thread is about time (the owner, 2026-10-11)."""
    AG = {'events': [{'start': '2026-10-14 10:00', 'end': '2026-10-14 11:00', 'subject': 'Board prep', 'all_day': False, 'status': 'busy',
                      'where': '', 'mailbox': 'alex@northwind.example'}],
          'errors': [], 'sources': ['outlook: alex@northwind.example'], 'start': '2026-10-11T09:00:00', 'end': '2026-10-25T09:00:00', 'tz': 'UTC'}

    def test_there_is_no_word_list(self):
        self.assertFalse(hasattr(cal, 'SCHEDULING') or hasattr(cal, 'about_time'))

    def test_a_reply_to_one_message_sees_the_calendar_whatever_words_it_uses(self):
        for body in ('Are you around on the 14th for a quick sync?', 'Does Oct 22 at noon work?', 'Can we push to the 3rd?'):
            s = MemoryStore()
            mid = s.add_message({'ExternalId': 'n1', 'Channel': 'email', 'Subject': 'Quick one', 'FromEmail': 'erin@northwind.example',
                                 'FromName': 'Erin Blake', 'SentAt': '2026-10-11 09:30:00', 'Status': 'new', 'BodyText': body})
            rid = s.add_review({'MessageId': mid, 'Kind': 'draft', 'Status': 'pending'})
            seen = {}
            def llm(sys_, usr_, **k): seen['sys'] = sys_; return 'The 14th at 10 I am in board prep - 11 works.'
            cal._REPLY.update(at=0.0, data=None)
            with mock.patch('taskuary.calendar.agenda', return_value=self.AG):
                responder.draft_for_message(s, s.get_message(mid), rid, llm=llm)
            self.assertIn('YOUR CALENDAR', seen['sys'], body); self.assertIn('Board prep', seen['sys'], body)

    def test_drafts_share_one_calendar_read_so_attaching_it_costs_no_call_per_draft(self):
        s = MemoryStore()
        with mock.patch('taskuary.calendar.agenda', return_value=self.AG) as ag:
            for _ in range(3): self.assertIn('Board prep', cal.context_for(s))
        self.assertEqual(ag.call_count, 1)

    def test_a_read_that_raised_is_not_cached(self):
        s = MemoryStore()
        with mock.patch('taskuary.calendar.agenda', side_effect=[RuntimeError('down'), self.AG]) as ag:
            self.assertEqual(cal.context_for(s), ''); self.assertIn('Board prep', cal.context_for(s))
        self.assertEqual(ag.call_count, 2)


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

    def test_a_google_meeting_you_declined_is_not_busy(self):
        class R:
            status_code = 200
            text = ''
            def __init__(self, j): self._j = j
            def json(self): return self._j
        me = {'email': 'alex@northwind.example', 'self': True}
        items = [{'summary': 'Vendor demo', 'start': {'dateTime': '2026-09-01T10:00:00Z'}, 'end': {'dateTime': '2026-09-01T11:00:00Z'},
                  'attendees': [{**me, 'responseStatus': 'declined'}, {'email': 'erin@vendor.example'}]},
                 {'summary': 'Budget review', 'start': {'dateTime': '2026-09-01T13:00:00Z'}, 'end': {'dateTime': '2026-09-01T14:00:00Z'},
                  'attendees': [{**me, 'responseStatus': 'accepted'}]}]
        cfg = {'google_client_id': 'c', 'google_client_secret': 's', 'google_refresh_token': 'r', 'address': 'alex@northwind.example'}
        with mock.patch('taskuary.calendar.requests.post', lambda *a, **k: R({'access_token': 't'})), \
             mock.patch('taskuary.calendar.requests.get', lambda *a, **k: R({'items': items})):
            got = cal.google_events(cfg, datetime.now(), datetime.now() + timedelta(days=1), timezone.utc)
        self.assertEqual([e['subject'] for e in got], ['Budget review'])

    def test_a_forbidden_calendar_says_which_permission(self):
        s = self._store()
        class R: status_code = 403; text = 'Forbidden'
        with mock.patch('taskuary.channels.graph_token', return_value='tok'), mock.patch('taskuary.calendar.requests.get', lambda *a, **k: R()):
            ag = cal.agenda(s, days=3)
        self.assertEqual(ag['events'], []); self.assertIn('Calendars.Read', ag['errors'][0])
        self.assertIn('COULD NOT READ', cal.render(ag))

    def test_context_whenever_the_switch_is_on(self):
        s = self._store()
        with mock.patch('taskuary.calendar.agenda', return_value={'events': [], 'errors': [], 'sources': ['outlook: me@corp.example'],
                                                                   'start': '2026-08-28T09:00:00', 'end': '2026-08-29T09:00:00', 'tz': 'UTC'}):
            self.assertIn('YOUR CALENDAR', cal.context_for(s))
            s.set_setting('calendar_enabled', '0', 't')
            self.assertEqual(cal.context_for(s), '')

    def test_no_calendar_source_means_no_paragraph(self):
        self.assertEqual(cal.context_for(MemoryStore()), '')

    def test_the_tool_reads_the_same_thing(self):
        s = self._store()
        with mock.patch('taskuary.calendar.agenda', return_value={'events': [{'start': '2026-08-28 13:00', 'end': '2026-08-28 14:00', 'subject': 'x', 'all_day': False, 'status': 'busy', 'where': '', 'mailbox': 'm'}],
                                                                   'errors': [], 'sources': ['outlook: m'], 'start': '2026-08-28T09:00:00', 'end': '2026-08-29T09:00:00', 'tz': 'UTC'}):
            head, body = cal.run_calendar({'store': s, 'days': 1})
        self.assertEqual(head, '1 event(s) in the next 1 days'); self.assertIn('1:00-2:00 PM · x', body)

    def test_a_bad_days_value_falls_back_and_never_goes_below_one(self):
        s = self._store()
        empty = {'events': [], 'errors': [], 'sources': [], 'start': '', 'end': '', 'tz': 'UTC'}
        with mock.patch('taskuary.calendar.agenda', return_value=empty) as ag:
            self.assertIn(f'in the next {cal.DAYS} days', cal.run_calendar({'store': s, 'days': 'week'})[0])
            self.assertIn('in the next 1 days', cal.run_calendar({'store': s, 'days': -3})[0])
        self.assertEqual([c.args[1] for c in ag.call_args_list], [cal.DAYS, 1])


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
