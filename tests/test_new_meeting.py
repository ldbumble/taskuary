"""New → Meeting (calwrite.suggest / draft_new, the owner 2026-10-28: "probably new meeting screen is better"): people, a subject and a
length; free times clear on the owner's calendar AND the attendees' where the provider answers for them; a pick DRAFTED as the invite on a
task of its own, sent only by the owner's Send. Graph and Google are faked; no network."""
import json, unittest
from datetime import date, timedelta
from unittest import mock

from taskuary import calwrite, concierge
from taskuary.store import MemoryStore
from tests.test_calendar_write import BUSY, D, ERIN, ME, R, Fake, outlook_store, send
from tests.test_assistant_router import say

GAIL = 'gail@northwind.example'
# Erin is out from 15:00 on the day - a time the owner alone would have offered
THEIRS = {'value': [{'scheduleId': ERIN, 'scheduleItems': [{'status': 'busy', 'start': {'dateTime': f'{D}T15:00:00', 'timeZone': 'UTC'},
                                                             'end': {'dateTime': f'{D}T17:00:00', 'timeZone': 'UTC'}}]},
                    {'scheduleId': GAIL, 'error': {'message': 'not shared'}}]}


def slots(s, fake, **kw):
    with mock.patch.object(calwrite, 'requests', fake), mock.patch.object(calwrite, 'busy', return_value=BUSY), \
         mock.patch('taskuary.channels.graph_token', return_value='tok'), mock.patch.object(calwrite.cal, 'tz_of', return_value=None):
        return calwrite.suggest(s, [ERIN, GAIL], 30, '', D, D, **kw)


class TheDays(unittest.TestCase):
    def test_this_week_next_week_and_a_range(self):
        wed = date(2026, 10, 28)
        self.assertEqual(calwrite.within_days('this_week', today=wed), (wed, date(2026, 10, 30)))
        self.assertEqual(calwrite.within_days('next_week', today=wed), (date(2026, 11, 2), date(2026, 11, 6)))
        self.assertEqual(calwrite.within_days('this_week', today=date(2026, 10, 31)), (date(2026, 11, 2), date(2026, 11, 6)), 'a weekend looks ahead')
        self.assertEqual(calwrite.within_days('', '2026-10-01', '2026-11-03', today=wed), (wed, date(2026, 11, 3)), 'never before today')
        self.assertEqual(calwrite.within_days('', today=wed), (wed, wed + timedelta(days=6)))


class FindTimes(unittest.TestCase):
    def test_slots_are_free_on_both_calendars_in_working_hours(self):
        s = outlook_store(); g = Fake({'getSchedule': R(200, THEIRS)})
        out = slots(s, g)
        (m, url, kw), = g.calls
        self.assertEqual((m, url.endswith(f'/users/{ME}/calendar/getSchedule')), ('POST', True))
        self.assertEqual(json.loads(kw['data'])['schedules'], [ERIN, GAIL])
        self.assertEqual((out['read'], out['unread']), ([ERIN], [GAIL]), "Gail's calendar was not shared - said, not guessed")
        self.assertTrue(3 <= len(out['slots']) <= 5, out['slots'])
        for x in out['slots']:
            self.assertEqual(x['start'][:10], D)
            self.assertTrue('09:00' <= x['start'][11:] and x['end'][11:] <= '17:00', x)
            self.assertFalse(calwrite.clashes(s, x['start'], x['end'], events=BUSY), 'never over the owner')
            self.assertLessEqual(x['end'][11:], '15:00', 'never over Erin')

    def test_an_attendee_read_that_fails_leaves_the_owners_times_and_says_whose_were_not_seen(self):
        s = outlook_store()
        out = slots(s, Fake({'getSchedule': R(403, {})}))
        self.assertEqual((out['read'], out['unread']), ([], [ERIN, GAIL]))
        self.assertTrue(out['slots'])

    def test_google_reads_freebusy(self):
        s = MemoryStore(); gm = s.get_connector_by_type('gmail')
        s.save_connector({'ConnectorId': gm['ConnectorId'], 'Active': 1, 'ConfigJson': json.dumps(
            {'address': ME, 'google_client_id': 'id', 'google_client_secret': 'sec', 'google_refresh_token': 'rt'})}, 't')
        fb = {'calendars': {ERIN: {'busy': [{'start': f'{D}T15:00:00Z', 'end': f'{D}T17:00:00Z'}]}, GAIL: {'errors': [{'reason': 'notFound'}]}}}
        g = Fake({'oauth2.googleapis.com/token': R(200, {'access_token': 'g', 'scope': calwrite.G_WRITE[0]}), 'freeBusy': R(200, fb)})
        with mock.patch('taskuary.googlecal.access_token', return_value='g'):
            out = slots(s, g)
        self.assertEqual((out['provider'], out['read'], out['unread']), ('google', [ERIN], [GAIL]))
        self.assertTrue(all(x['end'][11:] <= '15:00' for x in out['slots']))

    def test_a_full_window_offers_the_next_free_times_after_it(self):
        s = outlook_store()
        full = [{'start': f'{D} 08:00', 'end': f'{D} 18:00', 'subject': 'Offsite', 'all_day': False}]
        with mock.patch.object(calwrite, 'busy', return_value=full), mock.patch.object(calwrite, 'requests', Fake({'getSchedule': R(200, {'value': []})})), \
             mock.patch('taskuary.channels.graph_token', return_value='tok'):
            out = calwrite.suggest(s, [ERIN], 30, '', D, D)
        self.assertTrue(out['later'] and out['slots'] and all(x['start'][:10] > D for x in out['slots']))

    def test_a_card_that_may_not_write_says_so_before_any_pick(self):
        s = outlook_store('offline_access Calendars.Read')
        with self.assertRaises(calwrite.NoAccess) as e: slots(s, Fake())
        self.assertEqual(e.exception.fix, {'label': 'Sign in again', 'href': '#connector=outlook'})


class APickIsADraft(unittest.TestCase):
    def test_the_pick_makes_a_task_whose_close_out_holds_the_invite_and_only_send_books_it(self):
        s = outlook_store(); s.add_message({'ExternalId': 'graph:e1', 'Channel': 'email', 'FromEmail': ERIN, 'FromName': 'Erin Blake',
                                            'SourceName': ME, 'Subject': 'hi', 'BodyText': 'x', 'Status': 'routed'})
        g = Fake({'/events': R(201, {'id': 'new-1'})})
        with mock.patch.object(calwrite, 'requests', g), mock.patch.object(calwrite, 'busy', return_value=BUSY):
            d = calwrite.draft_new(s, [ERIN], 'the Q3 budget', f'{D} 12:00', f'{D} 12:30', 'Bring the sheet.')
            self.assertEqual(g.calls, [], 'nothing reaches the calendar before Send')
            t, rv = s.get_task(d['taskId']), s.get_review(d['reviewId'])
            self.assertEqual(t['Title'], 'Meeting with Erin Blake about the Q3 budget')
            self.assertEqual((rv['TaskId'], rv['Status'], rv['DraftText']), (d['taskId'], 'pending', 'Bring the sheet.'))
            env = calwrite.env_of(rv)
            self.assertEqual((env['kind'], env['act'], env['to'], env['start']), ('calendar', 'schedule', [ERIN], f'{D} 12:00'))
            self.assertIn(rv['ReviewId'], [r['ReviewId'] for r in s.task_detail(d['taskId'])['reviews']], 'in Close out')
            res = send(s, d['reviewId'])
        self.assertTrue(res['ok'], res)
        (m, url, kw), = g.calls
        body = json.loads(kw['data'])
        self.assertEqual((m, body['subject'], body['body']['content']), ('POST', 'the Q3 budget', 'Bring the sheet.'))
        self.assertEqual([a['emailAddress']['address'] for a in body['attendees']], [ERIN])

    def test_what_is_missing_is_said_and_nothing_is_made(self):
        s = outlook_store()
        for args, why in ((([], 'x', f'{D} 12:00', f'{D} 12:30'), 'who'), (([ERIN], ' ', f'{D} 12:00', f'{D} 12:30'), 'about'),
                          (([ERIN], 'x', None, None), 'pick a time'), (([ERIN], 'x', f'{D} 12:30', f'{D} 12:00'), 'ends before')):
            with self.assertRaises(ValueError) as e: calwrite.draft_new(s, *args)
            self.assertIn(why, str(e.exception))
        self.assertEqual(s._rows('SELECT * FROM review'), [])


class TheEndpoints(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        self.server, self.client = server, TestClient(server.app)

    def test_no_calendar_is_one_line_with_connect_a_calendar(self):
        s = MemoryStore()
        with mock.patch.object(self.server, 'store', s):
            r = self.client.get('/api/meetings/slots', params={'to': [ERIN], 'minutes': 30}).json()
            p = self.client.post('/api/meetings', json={'to': [ERIN], 'subject': 'x', 'start': f'{D} 12:00', 'end': f'{D} 12:30'}).json()
        for x in (r, p): self.assertEqual((x['ok'], x['say'], x['fix']['label']), (False, calwrite.NO_CAL, 'Connect a calendar'))
        self.assertEqual(s._rows('SELECT * FROM review'), [])

    def test_slots_then_pick(self):
        s = outlook_store()
        with mock.patch.object(self.server, 'store', s), mock.patch.object(calwrite, 'busy', return_value=BUSY), \
             mock.patch.object(calwrite, 'requests', Fake({'getSchedule': R(200, THEIRS)})), mock.patch('taskuary.channels.graph_token', return_value='tok'):
            r = self.client.get('/api/meetings/slots', params={'to': [ERIN, GAIL], 'minutes': 45, 'start': D, 'end': D}).json()
            self.assertTrue(r['ok'] and r['slots'] and r['minutes'] == 45, r)
            x = r['slots'][0]
            p = self.client.post('/api/meetings', json={'to': [ERIN], 'subject': 'the audit', 'start': x['start'], 'end': x['end']}).json()
        self.assertTrue(p['ok'], p)
        self.assertEqual(s.get_review(p['reviewId'])['Status'], 'pending')
        self.assertIn('Close out', p['say'])

    def test_an_agent_may_not_book_one(self):
        from taskuary import guard
        self.assertEqual(guard.classify('POST', '/api/meetings')[0], 'owner')


class TheAssistant(unittest.TestCase):
    def test_with_no_fitting_task_it_brings_up_new_meeting_filled_in(self):
        s = outlook_store(); s.add_message({'ExternalId': 'graph:g1', 'Channel': 'email', 'FromEmail': GAIL, 'FromName': 'Gail Moreno',
                                            'SourceName': ME, 'Subject': 'hi', 'BodyText': 'x', 'Status': 'routed'})
        call = 'CALL: ' + json.dumps({'kind': 'meeting.new', 'params': {'who': 'Gail Moreno, Zed Nobody', 'about': 'the Q3 budget', 'when': 'next week', 'minutes': 45}})
        out, spawn = say(s, 'schedule 45 minutes with Gail and Zed next week about the Q3 budget', None, call)
        spawn.assert_not_called()
        n = out['new']
        self.assertEqual(n['kind'], 'meeting')
        self.assertEqual(n['meeting'], {'to': [GAIL], 'unplaced': ['Zed Nobody'], 'about': 'the Q3 budget', 'minutes': 45,
                                        'within': 'next_week', 'from': '', 'to_day': ''})
        self.assertIn('New → Meeting', out['say']); self.assertIn('Zed Nobody', out['say'])
        self.assertEqual(s._rows('SELECT * FROM review'), [], 'opened, nothing drafted')


if __name__ == '__main__': unittest.main()
