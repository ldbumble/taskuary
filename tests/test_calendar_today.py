"""Today's meetings: who is in them and what they are about, for the digest and the panel."""
import json, unittest
from datetime import datetime
from unittest import mock
from taskuary import calendar as cal, digest, reports
from taskuary.store import MemoryStore


class R:
    def __init__(self, code, body): self.status_code, self._b, self.text = code, body, json.dumps(body)
    def json(self): return self._b


class AboutTests(unittest.TestCase):
    def test_the_invite_boilerplate_is_dropped_and_the_purpose_kept(self):
        body = ('Quick sync on the Elkton refund backlog before Friday.\n\n________________________________\n'
                'Microsoft Teams meeting\nJoin on your computer, mobile app or room device\nClick here to join the meeting\n'
                'Meeting ID: 123 456 789\nPasscode: abc\nDial in by phone\n')
        self.assertEqual(cal.about_text(body), 'Quick sync on the Elkton refund backlog before Friday.')
        self.assertEqual(cal.about_text('Microsoft Teams meeting\nJoin on your computer'), '')
        # the newer Teams layout: plumbing on one line, pipes between - and a real sentence above it
        body2 = 'Target numbers for Q4, bring the census sheet.\nDownload Teams | Join on the web\nJoin with a video conferencing device\nVideo ID: 112 233\nMore info\n+1 555-010-0100,,123#'
        self.assertEqual(cal.about_text(body2), 'Target numbers for Q4, bring the census sheet.')
        self.assertEqual(cal.about_text('Download Teams | Join on the web\nMeeting options'), '')
        self.assertTrue(cal.about_text('x' * 300).endswith('…'))

    def test_graph_events_carry_who_about_and_join(self):
        ev = {'subject': 'Refund sync', 'start': {'dateTime': '2026-08-28T14:00:00'}, 'end': {'dateTime': '2026-08-28T14:30:00'},
              'isAllDay': False, 'showAs': 'busy', 'location': {'displayName': 'Teams'},
              'organizer': {'emailAddress': {'name': 'Mary Michalski', 'address': 'mary@elkton.example'}},
              'attendees': [{'type': 'required', 'emailAddress': {'name': 'Uri Nussbaum', 'address': 'uri@mfaheritage.net'}},
                            {'type': 'required', 'emailAddress': {'name': 'Mary Michalski', 'address': 'mary@elkton.example'}},
                            {'type': 'resource', 'emailAddress': {'name': 'Room 4', 'address': 'room4@x'}}],
              'bodyPreview': 'Go over the Barnes deposit.\nMicrosoft Teams meeting\nMeeting ID: 1', 'isOnlineMeeting': True,
              'onlineMeeting': {'joinUrl': 'https://teams.microsoft.com/l/x'}, 'webLink': 'https://outlook.office.com/x'}
        with mock.patch('taskuary.channels.graph_token', return_value='T'), mock.patch.object(cal.requests, 'get', return_value=R(200, {'value': [ev]})) as g:
            out = cal.outlook_events({}, 'S', ['uri@mfaheritage.net'], datetime(2026, 8, 28), datetime(2026, 8, 29), cal.tz_of(MemoryStore()))
        e = out[0]
        self.assertEqual(e['who'], ['Mary Michalski'])                                   # not the owner, not the room
        self.assertEqual((e['organizer'], e['about'], e['join']), ('Mary Michalski', 'Go over the Barnes deposit.', 'https://teams.microsoft.com/l/x'))
        self.assertIn('attendees', g.call_args[1]['params']['$select']); self.assertIn('body-content-type="text"', g.call_args[1]['headers']['Prefer'])


class TodayTests(unittest.TestCase):
    def test_today_keeps_only_today_and_the_digest_leads_with_it(self):
        s = MemoryStore()
        d = datetime.now().strftime('%Y-%m-%d')
        evs = [{'start': f'{d} 09:00', 'end': f'{d} 09:30', 'subject': 'Standup', 'all_day': False, 'status': 'busy', 'where': '', 'who': ['Gabi', 'Mindy'], 'about': '', 'join': 'https://t'},
               {'start': '2031-01-01 09:00', 'end': '2031-01-01 10:00', 'subject': 'Far away', 'all_day': False, 'status': 'busy', 'where': '', 'who': [], 'about': '', 'join': ''}]
        cal._TODAY.update(at=0.0, day='', data=None)
        with mock.patch.object(cal, 'agenda', return_value={'events': evs, 'tz': 'X', 'errors': [], 'sources': ['x'], 'start': '', 'end': ''}) as ag:
            t = cal.today(s)
            self.assertEqual([e['subject'] for e in t['events']], ['Standup'])            # a 09:00 meeting is on the list at 17:00 too
            self.assertEqual(ag.call_args[1]['start'].hour, 0)                             # read from midnight, not from now
            lines = cal.render_today(t)
            self.assertEqual(lines, ['  9:00-9:30 AM · Standup · with Gabi, Mindy · online'])       # the owner's clock, not the server's
            text = digest.gather(s, 1)
        self.assertTrue(text.startswith('MEETINGS TODAY')); self.assertIn('Standup · with Gabi, Mindy', text)
        self.assertIn("Today's meetings", digest.PROMPT); self.assertIn('MEETINGS TODAY', digest.PROMPT)
        self.assertTrue(any('under 400 words' in p and 'By the tags' in p for p in digest.OLD_PROMPTS))   # the previous stock prompt upgrades itself

    def test_a_calendar_that_cannot_be_read_says_so_in_the_digest(self):
        s = MemoryStore()
        cal._TODAY.update(at=0.0, day='', data=None)
        with mock.patch.object(cal, 'agenda', side_effect=RuntimeError('Graph refused (403)')):
            self.assertIn('COULD NOT READ: Graph refused (403)', digest.gather(s, 1))


class StartupTests(unittest.TestCase):
    def test_on_startup_beside_a_schedule_means_both(self):
        self.assertTrue(reports.is_due({'on_startup': True, 'every_minutes': 180}, None, startup=True))
        self.assertTrue(reports.is_due({'on_startup': True, 'every_minutes': 180}, '2026-08-21 09:00:00', startup=True))
        self.assertTrue(reports.is_due({'on_startup': True, 'every_minutes': 180}, '2026-08-21 09:00:00'))      # long overdue on the clock
        self.assertFalse(reports.is_due({'on_startup': True, 'every_minutes': 180}, datetime.now().isoformat(sep=' ')))   # just ran, not startup
        self.assertFalse(reports.is_due({'on_startup': True}, '2026-08-21 09:00:00'))                           # startup-only stays startup-only
        self.assertTrue(reports.is_due({'on_startup': True}, None, startup=True))
