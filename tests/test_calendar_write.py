"""Answering the calendar (calwrite.py): an invite accepted, declined or met with another time, a meeting booked from a thread -
each DRAFTED for the owner's Send, and only that Send reaching Graph or Google. Both providers are faked; no network."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import calwrite, concierge, ingest, msauth, triage, verdicts
from taskuary.store import MemoryStore

ME, ERIN = 'alex@northwind.example', 'erin@northwind.example'
DAY = (datetime.now() + timedelta(days=1))
while DAY.weekday() >= 5: DAY += timedelta(days=1)
D = DAY.strftime('%Y-%m-%d')
BUSY = [{'start': f'{D} 09:00', 'end': f'{D} 12:00', 'subject': 'Quarter-end planning', 'all_day': False},
        {'start': f'{D} 14:00', 'end': f'{D} 15:00', 'subject': 'Budget review', 'all_day': False}]
INVITE = {'kind': 'request', 'provider': 'outlook', 'mailbox': ME, 'event_id': 'ev-1', 'ical_uid': 'uid-1', 'update': False, 'answered': False,
          'asks': True, 'subject': 'Budget sync', 'start': f'{D} 14:30', 'end': f'{D} 15:00', 'all_day': False,
          'organizer': 'Erin Blake', 'organizer_email': ERIN, 'attendees': [ERIN, ME]}


class R:
    def __init__(self, status=200, body=None): self.status_code, self._b, self.text = status, body or {}, json.dumps(body or {})
    def json(self): return self._b


class Fake:
    """Graph and Google, as calwrite calls them: every call kept, each answered from `answers` (url fragment -> R)."""
    def __init__(self, answers=None): self.calls, self.answers = [], answers or {}
    def _go(self, method, url, **kw):
        self.calls.append((method, url, kw))
        return next((r for k, r in self.answers.items() if k in url), R())
    def get(self, url, **kw): return self._go('GET', url, **kw)
    def post(self, url, **kw): return self._go('POST', url, **kw)
    def patch(self, url, **kw): return self._go('PATCH', url, **kw)


def outlook_store(granted='offline_access User.Read Mail.ReadWrite Mail.Send Calendars.ReadWrite'):
    s = MemoryStore(); s.set_setting('calendar_enabled', '0', 't')
    ol = s.get_connector_by_type('outlook')
    s.save_connector({'ConnectorId': ol['ConnectorId'], 'Active': 1, 'Secret': 'rt',
                      'ConfigJson': json.dumps({'auth': 'user', 'account': ME, **({'granted_scope': granted} if granted else {})})}, 't')
    s.save_source({'Channel': 'email', 'Address': ME, 'Owner': 'me', 'Active': 1, 'ConnectorId': ol['ConnectorId']}, 't')
    s.set_setting('owner_email', ME, 't')
    return s


def arrive(s, cal=INVITE, **more):
    with mock.patch.object(calwrite, 'busy', return_value=BUSY):
        return ingest.ingest_message(s, {'external_id': f"graph:{cal.get('event_id')}-{cal.get('kind')}", 'channel': 'email',
                                         'subject': f"Invitation: {cal['subject']}", 'body': 'Join us', 'from_name': 'Erin Blake', 'from_email': ERIN,
                                         'to': [ME], 'source_name': ME, 'sent_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                         'invite': True, 'cal': cal, 'mail_meta': {'invite': True, 'cal': cal}, **more}, llm=None)


def send(s, rid, text=None):
    """The owner's Send, through the one door every Send takes."""
    with mock.patch('taskuary.channels.graph_token', return_value='tok'):
        return verdicts.decide(s, s.get_review(rid), 'approve', text)


class WhatAnInviteIs(unittest.TestCase):
    def test_graph_types_say_request_answer_and_cancellation(self):
        req = {'@odata.type': '#microsoft.graph.eventMessageRequest', 'subject': 'Budget sync',
               'event': {'id': 'ev-1', 'responseStatus': {'response': 'notResponded'}, 'start': {'dateTime': f'{D}T14:30:00', 'timeZone': 'UTC'},
                         'end': {'dateTime': f'{D}T15:00:00', 'timeZone': 'UTC'}, 'organizer': {'emailAddress': {'name': 'Erin Blake', 'address': ERIN}}}}
        c = calwrite.from_graph(req, ME)
        self.assertEqual((c['kind'], c['event_id'], c['organizer_email']), ('request', 'ev-1', ERIN))
        self.assertTrue(calwrite.needs_answer(c))
        self.assertEqual(calwrite.from_graph({'@odata.type': '#microsoft.graph.eventMessageResponse'}, ME)['kind'], 'response')
        self.assertEqual(calwrite.from_graph({'@odata.type': '#microsoft.graph.eventMessage', 'meetingMessageType': 'meetingCancelled'}, ME)['kind'], 'cancel')
        answered = calwrite.from_graph({**req, 'event': {**req['event'], 'responseStatus': {'response': 'accepted'}}}, ME)
        self.assertFalse(calwrite.needs_answer(answered))
        moved = calwrite.from_graph({**req, 'previousStartDateTime': {'dateTime': f'{D}T10:00:00'}}, ME)
        self.assertFalse(calwrite.needs_answer(moved), 'an update is fyi')

    def test_an_icalendar_part_says_the_same(self):
        ics = ('BEGIN:VCALENDAR\r\nMETHOD:REQUEST\r\nBEGIN:VEVENT\r\nUID:uid-9\r\nSEQUENCE:0\r\nSUMMARY:Budget sync\r\n'
               f'DTSTART:{DAY.strftime("%Y%m%d")}T143000\r\nDTEND:{DAY.strftime("%Y%m%d")}T150000\r\n'
               f'ORGANIZER;CN=Erin Blake:mailto:{ERIN}\r\nATTENDEE;PARTSTAT=NEEDS-ACTION;CN=Alex:mailto:{ME}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')
        c = calwrite.from_ics(ics, me=(ME,))
        self.assertEqual((c['kind'], c['ical_uid'], c['subject'], c['start'], c['organizer_email']), ('request', 'uid-9', 'Budget sync', f'{D} 14:30', ERIN))
        self.assertTrue(calwrite.needs_answer(c))
        self.assertFalse(calwrite.needs_answer(calwrite.from_ics(ics.replace('NEEDS-ACTION', 'ACCEPTED'), me=(ME,))))
        self.assertFalse(calwrite.needs_answer(calwrite.from_ics(ics.replace('SEQUENCE:0', 'SEQUENCE:2'), me=(ME,))), 'an update is fyi')
        self.assertEqual(calwrite.from_ics(ics.replace('METHOD:REQUEST', 'METHOD:CANCEL'), me=(ME,))['kind'], 'cancel')

    def test_utc_times_read_without_a_tz_database(self):
        """Windows has no IANA database without tzdata: ZoneInfo('UTC') raised, ingest crashed and the invite was lost."""
        from zoneinfo import ZoneInfoNotFoundError
        from datetime import timezone, timedelta
        ics = ('BEGIN:VCALENDAR\r\nMETHOD:REQUEST\r\nBEGIN:VEVENT\r\nUID:uid-utc\r\nSUMMARY:Budget sync\r\n'
               'DTSTART:20261102T140000Z\r\nDTEND;TZID=Nowhere/Unknown:20261102T150000\r\n'
               f'ORGANIZER;CN=Erin Blake:mailto:{ERIN}\r\nATTENDEE;PARTSTAT=NEEDS-ACTION;CN=Alex:mailto:{ME}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')
        def no_db(key): raise ZoneInfoNotFoundError(key)
        with mock.patch.object(calwrite, 'ZoneInfo', side_effect=no_db):
            c = calwrite.from_ics(ics, me=(ME,), tz=timezone(timedelta(hours=-5)))
            self.assertEqual((c['start'], c['end']), ('2026-11-02 09:00', '2026-11-02 15:00'))
            self.assertEqual(calwrite._local({'dateTime': '2026-11-02T14:00:00', 'timeZone': 'UTC'}, timezone(timedelta(hours=-5))), '2026-11-02 09:00')


class TheOwnersMove(unittest.TestCase):
    def test_an_unanswered_invite_is_a_task_that_says_its_clash(self):
        s = outlook_store()
        out = arrive(s)
        self.assertEqual(out['status'], 'created')
        t = s.get_task(out['task_id'])
        self.assertEqual(t['Kind'], 'reply'); self.assertIn('Budget sync', t['Title'])
        self.assertIn('clashes with Budget review', t['Summary'])
        self.assertEqual(s.reviews_for_message(out['message_id']), [], 'no email is drafted to answer an invite')

    def test_a_cancellation_an_answer_and_an_update_stay_fyi(self):
        for c in ({**INVITE, 'kind': 'cancel', 'event_id': 'c1'}, {**INVITE, 'kind': 'response', 'event_id': 'c2'},
                  {**INVITE, 'update': True, 'event_id': 'c3'}, {**INVITE, 'answered': True, 'event_id': 'c4'}):
            s = outlook_store()
            out = arrive(s, c)
            self.assertEqual(out['status'], 'filed', c); self.assertIsNone(out.get('task_id'))

    def test_the_row_offers_the_three_answers(self):
        s = outlook_store(); out = arrive(s)
        item = {'kind': 'asked', 'key': f"msg:{out['message_id']}", 'mid': out['message_id'], 'tid': out['task_id'], 'title': 'Invite: Budget sync'}
        verbs = [c['verb'] for c in concierge.chips_for(s, item)]
        self.assertEqual(verbs[:3], ['accept_invite', 'decline_invite', 'propose_time'])
        self.assertNotIn('reply', verbs)
        # ...and once an answer is drafted all three stay, its Send first: another press REPLACES the drafted answer
        with mock.patch.object(calwrite, 'busy', return_value=BUSY): first = calwrite.draft(s, out['message_id'], 'accept')
        rv_item = {**item, 'kind': 'review', 'rid': first['reviewId'], 'draft': True}
        verbs = [c['verb'] for c in concierge.chips_for(s, rv_item)]
        self.assertEqual(verbs[:4], ['approve', 'accept_invite', 'decline_invite', 'propose_time']); self.assertNotIn('redraft', verbs)
        with mock.patch.object(calwrite, 'busy', return_value=BUSY): second = calwrite.draft(s, out['message_id'], 'decline')
        self.assertEqual(s.get_review(first['reviewId'])['Status'], 'rejected')
        pending = [r for r in s.reviews_for_message(out['message_id']) if r['Status'] == 'pending']
        self.assertEqual([json.loads(r['Deliver'])['act'] for r in pending], ['decline'])
        self.assertTrue(calwrite.of_task(s, out['task_id'])['invite'])
        # ...and the answer the calendar took ends them
        with mock.patch.object(calwrite, 'requests', Fake()): send(s, second['reviewId'], '')
        self.assertNotIn('accept_invite', [c['verb'] for c in concierge.chips_for(s, item)])
        self.assertIsNone(calwrite.of_task(s, out['task_id']))


class DraftedThenSent(unittest.TestCase):
    def setUp(self):
        self.s = outlook_store(); self.out = arrive(self.s); self.mid = self.out['message_id']

    def draft(self, act, **kw):
        with mock.patch.object(calwrite, 'busy', return_value=BUSY): return calwrite.draft(self.s, self.mid, act, **kw)

    def test_accept_is_a_draft_until_send_then_graph_accepts_with_the_note(self):
        g = Fake()
        with mock.patch.object(calwrite, 'requests', g):
            d = self.draft('accept')
            self.assertEqual(g.calls, [], 'drafting writes nothing')
            rv = self.s.get_review(d['reviewId'])
            env = json.loads(rv['Deliver'])
            self.assertEqual((env['kind'], env['act'], env['to']), ('calendar', 'accept', [ERIN]))
            self.assertIn('clashes with Budget review', env['clash'])
            self.assertEqual(env['when'], calwrite.when(INVITE['start'], INVITE['end']))
            self.assertEqual(rv['TaskId'], self.out['task_id'])
            res = send(self.s, d['reviewId'], 'See you there.')
        self.assertTrue(res['ok'], res)
        (m, url, kw), = g.calls
        self.assertEqual(m, 'POST'); self.assertTrue(url.endswith(f'/users/{ME}/events/ev-1/accept'))
        self.assertEqual(json.loads(kw['data']), {'comment': 'See you there.', 'sendResponse': True})
        self.assertEqual(self.s.get_review(d['reviewId'])['DeliveryState'], 'sent')
        self.assertTrue(any('Accepted Budget sync' in str(c.get('Body')) for c in self.s.list_comments(self.out['task_id'])))

    def test_decline_with_the_note_emptied_sends_no_note(self):
        g = Fake()
        with mock.patch.object(calwrite, 'requests', g):
            d = self.draft('decline')
            res = send(self.s, d['reviewId'], '')
        self.assertTrue(res['ok'], res)
        self.assertTrue(g.calls[0][1].endswith('/events/ev-1/decline'))
        self.assertEqual(json.loads(g.calls[0][2]['data'])['comment'], '')

    def test_propose_is_a_tentative_answer_with_the_new_time(self):
        g = Fake()
        with mock.patch.object(calwrite, 'requests', g):
            with mock.patch.object(calwrite, 'busy', return_value=BUSY):
                slots = calwrite.slots_for(self.s, self.s.get_message(self.mid), 'propose')['slots']
            self.assertTrue(2 <= len(slots) <= 3, slots)
            for x in slots: self.assertEqual(calwrite.clashes(self.s, x['start'], x['end'], events=BUSY), [], x)
            d = self.draft('propose', start=slots[0]['start'], end=slots[0]['end'])
            res = send(self.s, d['reviewId'])
        self.assertTrue(res['ok'], res)
        url, body = g.calls[0][1], json.loads(g.calls[0][2]['data'])
        self.assertTrue(url.endswith('/events/ev-1/tentativelyAccept'))
        self.assertEqual(body['proposedNewTime']['start']['dateTime'][:16], slots[0]['start'].replace(' ', 'T'))
        self.assertIn('would', body['comment'])

    def test_a_refused_send_stays_a_draft_with_the_sign_in_as_its_fix(self):
        g = Fake({'/accept': R(403, {'error': 'Forbidden'})})
        with mock.patch.object(calwrite, 'requests', g):
            d = self.draft('accept')
            res = send(self.s, d['reviewId'])
        self.assertFalse(res.get('sent')); self.assertEqual(res['status'], 'pending')
        self.assertEqual((res.get('send_fix') or {}).get('label'), 'Sign in again')


class ScheduleFromAThread(unittest.TestCase):
    def test_find_a_time_offers_free_slots_in_the_asked_window_and_books_on_send(self):
        s = outlook_store()
        t = s.create_task({'Title': 'Audit list', 'Kind': 'reply'}, 'owner')
        mid = s.add_message({'TaskId': t, 'ExternalId': 'graph:m2', 'Channel': 'email', 'Subject': 'Re: Audit list - 30 minutes?', 'FromEmail': ERIN,
                             'FromName': 'Erin Blake', 'SourceName': ME, 'BodyText': 'Can we find 30 minutes?', 'Status': 'routed',
                             'RecipientsJson': json.dumps({'to': [ME], 'cc': ['gail@northwind.example']}),
                             'MeetJson': json.dumps({'minutes': 30, 'from': D, 'to': D})})
        item = {'kind': 'asked', 'key': f'msg:{mid}', 'mid': mid, 'tid': t, 'title': 'Audit list'}
        self.assertIn('find_time', [c['verb'] for c in concierge.chips_for(s, item)])
        with mock.patch.object(calwrite, 'busy', return_value=BUSY):
            slots = calwrite.slots_for(s, s.get_message(mid), 'schedule')['slots']
        self.assertTrue(slots and all(x['start'][:10] == D for x in slots), slots)
        self.assertTrue(all(not calwrite.clashes(s, x['start'], x['end'], events=BUSY) for x in slots))
        g = Fake({'/events': R(201, {'id': 'new-1'})})
        with mock.patch.object(calwrite, 'requests', g), mock.patch.object(calwrite, 'busy', return_value=BUSY):
            d = calwrite.draft(s, mid, 'schedule', slots[0]['start'], slots[0]['end'])
            self.assertEqual(g.calls, [])
            res = send(s, d['reviewId'])
        self.assertTrue(res['ok'], res)
        (m, url, kw), = g.calls
        body = json.loads(kw['data'])
        self.assertTrue(url.endswith(f'/users/{ME}/events'))
        self.assertEqual(body['subject'], 'Audit list - 30 minutes?')
        self.assertEqual(sorted(a['emailAddress']['address'] for a in body['attendees']), [ERIN, 'gail@northwind.example'])

    def test_triage_reads_the_ask_and_keeps_only_real_days(self):
        def llm(meet): return lambda system, user, **k: json.dumps({'intent': 'reply_only', 'why': 'x', 'title': 't', 'summary': 's', 'meet': meet})
        sent = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        got = triage.classify_intent({'subject': 'x', 'body': 'can we find 30 minutes?', 'sent_at': sent}, llm=llm({'minutes': 30, 'from': D, 'to': D}))
        self.assertEqual(got['meet'], {'minutes': 30, 'from': D, 'to': D})
        got = triage.classify_intent({'subject': 'x', 'body': 'y', 'sent_at': sent}, llm=llm({'minutes': 9999, 'from': '1999-01-01', 'to': 'Thursday'}))
        self.assertEqual(got['meet'], {'minutes': None, 'from': None, 'to': None})
        self.assertNotIn('meet', triage.classify_intent({'subject': 'x', 'body': 'y'}, llm=llm(None)))
        self.assertIn('meet', triage.verdict_schema()['schema']['properties'])


class TheWriteScope(unittest.TestCase):
    def test_a_sign_in_without_the_write_scope_keeps_the_buttons_and_says_why(self):
        for granted in ('offline_access User.Read Mail.Send Calendars.Read', None):
            s = outlook_store(granted)
            out = arrive(s)
            item = {'kind': 'asked', 'key': f"msg:{out['message_id']}", 'mid': out['message_id'], 'tid': out['task_id'], 'title': 'x'}
            self.assertIn('accept_invite', [c['verb'] for c in concierge.chips_for(s, item)], 'the buttons stay')
            with self.assertRaises(calwrite.NoAccess) as e: calwrite.draft(s, out['message_id'], 'accept')
            self.assertIn('Calendar access needs to be granted', str(e.exception))
            self.assertEqual(e.exception.fix, {'label': 'Sign in again', 'href': '#connector=outlook'})
            self.assertEqual(s.reviews_for_message(out['message_id']), [], 'nothing drafted')

    def test_with_no_calendar_connected_accept_and_find_a_time_say_so_with_the_connect_step(self):
        """B15 (the email walk, 2026-10-29): no mailbox card at all, an invite read off IMAP (provider google) - Accept talked about a
        Google refresh token and offered "Open the Gmail card", Find a time "Sign in again"; nothing had ever been signed in."""
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore(); s.set_setting('calendar_enabled', '0', 't')
        out = arrive(s, {**INVITE, 'provider': 'google', 'event_id': 'ev-g'})
        with self.assertRaises(calwrite.NoAccess) as e: calwrite.draft(s, out['message_id'], 'accept')
        self.assertEqual(str(e.exception), calwrite.NO_CALENDAR)
        self.assertNotIn('refresh token', str(e.exception))
        self.assertEqual(e.exception.fix, {'label': 'Connect a calendar', 'href': '#connector=outlook'})
        with mock.patch.object(server, 'store', s):
            r = TestClient(server.app).get(f"/api/messages/{out['message_id']}/calendar/slots", params={'act': 'propose'}).json()
        self.assertFalse(r['ok']); self.assertIn('No calendar is connected', r['say'])
        self.assertNotEqual((r.get('fix') or {}).get('label'), 'Sign in again')
        # ...and a Gmail card that IS there, with no Google calendar on it yet, is still told how to add one - on that card
        gm = s.get_connector_by_type('gmail'); s.save_connector({'ConnectorId': gm['ConnectorId'], 'Active': 1}, 't')
        with self.assertRaises(calwrite.NoAccess) as e: calwrite.draft(s, out['message_id'], 'accept')
        self.assertEqual(e.exception.fix['href'], '#connector=gmail')

    def test_the_endpoint_answers_with_one_line_and_the_fix(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = outlook_store('offline_access Calendars.Read'); out = arrive(s)
        with mock.patch.object(server, 'store', s):
            c = TestClient(server.app)
            r = c.post(f"/api/messages/{out['message_id']}/calendar", json={'act': 'accept'}).json()
            self.assertEqual((r['ok'], r['fix']['label']), (False, 'Sign in again'))
            r = c.get(f"/api/messages/{out['message_id']}/calendar/slots", params={'act': 'propose'}).json()
            self.assertFalse(r['ok']); self.assertIn('Calendar access', r['say'])

    def test_new_sign_ins_ask_for_write_and_old_ones_refresh_as_they_were(self):
        self.assertIn('Calendars.ReadWrite', msauth.SCOPES.split())
        self.assertEqual(msauth.refresh_scope({}), msauth.LEGACY_SCOPES)
        self.assertNotIn('Calendars.ReadWrite', msauth.refresh_scope({'granted_scope': 'User.Read Mail.Send Calendars.Read openid profile'}))
        self.assertIn('Calendars.ReadWrite', msauth.refresh_scope({'granted_scope': 'User.Read Calendars.ReadWrite'}))
        self.assertTrue(calwrite.ms_can_write({'auth': 'user', 'granted_scope': 'User.Read Calendars.ReadWrite'}))
        self.assertFalse(calwrite.ms_can_write({'auth': 'user', 'granted_scope': 'User.Read Calendars.Read'}))


class Google(unittest.TestCase):
    def store(self, scope):
        s = MemoryStore(); s.set_setting('calendar_enabled', '0', 't')
        gm = s.get_connector_by_type('gmail')
        s.save_connector({'ConnectorId': gm['ConnectorId'], 'Active': 1,
                          'ConfigJson': json.dumps({'address': ME, 'google_client_id': 'id', 'google_client_secret': 'sec', 'google_refresh_token': 'rt'})}, 't')
        self.tok = R(200, {'access_token': 'g', 'scope': scope})
        return s

    def test_accept_patches_the_owners_own_attendee_row(self):
        s = self.store('https://www.googleapis.com/auth/calendar.events')
        out = arrive(s, {**INVITE, 'provider': 'google', 'event_id': ''})
        ev = {'items': [{'id': 'g-ev', 'attendees': [{'email': ERIN, 'responseStatus': 'accepted'}, {'email': ME, 'self': True, 'responseStatus': 'needsAction'}]}]}
        g = Fake({'oauth2.googleapis.com/token': self.tok, 'events?': R(200, ev), '/events': R(200, ev)})
        with mock.patch.object(calwrite, 'requests', g), mock.patch.object(calwrite, 'busy', return_value=BUSY):
            d = calwrite.draft(s, out['message_id'], 'accept')
            res = verdicts.decide(s, s.get_review(d['reviewId']), 'approve', 'Will be there.')
        self.assertTrue(res['ok'], res)
        m, url, kw = next(c for c in g.calls if c[0] == 'PATCH')
        self.assertTrue(url.endswith('/events/g-ev')); self.assertEqual(kw['params'], {'sendUpdates': 'all'})
        me = next(a for a in json.loads(kw['data'])['attendees'] if a.get('self'))
        self.assertEqual((me['responseStatus'], me['comment']), ('accepted', 'Will be there.'))
        self.assertEqual(next(a for a in json.loads(kw['data'])['attendees'] if a['email'] == ERIN)['responseStatus'], 'accepted')

    def test_a_read_only_google_token_is_refused_with_the_card_as_its_fix(self):
        s = self.store('https://www.googleapis.com/auth/calendar.readonly')
        out = arrive(s, {**INVITE, 'provider': 'google'})
        with mock.patch.object(calwrite, 'requests', Fake({'oauth2.googleapis.com/token': self.tok})):
            with self.assertRaises(calwrite.NoAccess) as e: calwrite.draft(s, out['message_id'], 'accept')
        self.assertEqual(e.exception.fix['href'], '#connector=gmail')


class TheDemo(unittest.TestCase):
    def test_the_demo_world_has_an_invite_that_clashes_and_an_ask_for_a_time(self):
        from taskuary import demo
        s = MemoryStore()
        with mock.patch.object(demo, 'enabled', return_value=True):
            demo.seed(s)
            inv = next(m for m in s._rows("SELECT * FROM message") if calwrite.needs_answer(calwrite.invite_of(m)))
            ask = next(m for m in s._rows("SELECT * FROM message") if calwrite.meet_of(m))
            self.assertIn('clashes with', calwrite.of_task(s, inv['TaskId'])['clash'])
            self.assertTrue(calwrite.of_task(s, ask['TaskId'])['meet'])
            d = calwrite.draft(s, inv['MessageId'], 'accept')          # no card behind the demo: drafted all the same
            self.assertEqual(json.loads(s.get_review(d['reviewId'])['Deliver'])['act'], 'accept')
            self.assertEqual(len(calwrite.slots_for(s, ask, 'schedule')['slots']), 3)
            self.assertEqual(demo.refuse('POST', f"/api/messages/{inv['MessageId']}/calendar", s), '', 'drafting is the demo')
            self.assertEqual(demo.refuse('POST', f"/api/reviews/{d['reviewId']}/decide", s), demo.SENDS, 'Send stays refused')


class MovedMeeting(unittest.TestCase):
    """An update that moves a meeting the owner had accepted is theirs to answer again; any other update stays fyi."""
    def moved(self, s, start, had=''):
        end = INVITE['end'] if start == INVITE['start'] else start[:11] + '17:00'
        return arrive(s, {**INVITE, 'update': True, 'start': start, 'end': end, 'had': had}, external_id=f'graph:upd-{start}-{had}')

    def test_moved_after_you_accepted_here_is_yours_again_on_the_same_task(self):
        s = outlook_store(); out = arrive(s, conversation_id='conv-1')
        with mock.patch.object(calwrite, 'requests', Fake()), mock.patch.object(calwrite, 'busy', return_value=BUSY):
            send(s, calwrite.draft(s, out['message_id'], 'accept')['reviewId'])
        s.update_task(out['task_id'], {'Status': 'done'}, 'owner')
        up = arrive(s, {**INVITE, 'update': True, 'start': f'{D} 16:00', 'end': f'{D} 17:00'}, external_id='graph:upd-1', conversation_id='conv-1')
        self.assertEqual(up.get('task_id'), out['task_id'], up)
        self.assertNotIn(s.get_task(out['task_id'])['Status'], ('done', 'dropped'), 'the moved meeting reopens its task')
        item = {'kind': 'asked', 'key': f"msg:{up['message_id']}", 'mid': up['message_id'], 'tid': out['task_id'], 'title': 'x'}
        self.assertIn('accept_invite', [c['verb'] for c in concierge.chips_for(s, item)])
        said = ' '.join(str(r.get('Reason')) for r in s._rows('SELECT * FROM route WHERE MessageId=?', (up['message_id'],)))
        self.assertIn('you had accepted it', said)
        self.assertEqual(s.reviews_for_message(up['message_id']), [], 'no email drafted for it')

    def test_an_update_that_keeps_the_time_or_that_you_never_accepted_stays_fyi(self):
        s = outlook_store(); arrive(s)
        same = self.moved(s, INVITE['start'], had='accepted')                    # a new room, the same time
        self.assertEqual(same['status'], 'filed')
        s2 = outlook_store(); arrive(s2)
        never = self.moved(s2, f'{D} 16:00')                                      # moved, and nobody had said yes
        self.assertEqual(never['status'], 'filed')
        s3 = outlook_store(); arrive(s3)
        self.assertEqual(self.moved(s3, f'{D} 16:00', had='accepted')['status'], 'created', 'moved after a yes given in Outlook')

    def test_graph_says_moved_and_what_you_had_said(self):
        c = calwrite.from_graph({'@odata.type': '#microsoft.graph.eventMessageRequest', 'previousStartDateTime': {'dateTime': f'{D}T10:00:00'},
                                 'event': {'id': 'ev-1', 'responseStatus': {'response': 'tentativelyAccepted'}}}, ME)
        self.assertEqual((c['update'], c['moved'], c['had']), (True, True, 'tentative'))
        self.assertTrue(calwrite.needs_answer(c))
        self.assertFalse(calwrite.needs_answer({**c, 'moved': False}), 'a new room is fyi')


class AssistantTools(unittest.TestCase):
    """"accept it" lights the row's real Accept; words never send - by a phone's words they draft, as the press does."""
    def test_the_row_buttons_the_assistant_may_light(self):
        from taskuary import toolcatalog
        s = outlook_store(); out = arrive(s)
        item = {'kind': 'asked', 'key': f"msg:{out['message_id']}", 'mid': out['message_id'], 'tid': out['task_id'], 'title': 'x'}
        have = {b['verb'] for b in concierge.row_buttons(s, item)}
        self.assertTrue({'accept_invite', 'decline_invite', 'propose_time'} <= have, have)
        self.assertNotIn('find_time', have, 'no ask for a time on an invite')
        self.assertTrue(all(v in toolcatalog.DECISIONS and v in concierge.PROPOSALS for v in concierge.CAL_ACT))
        self.assertTrue(concierge.cannot({'kind': 'asked', 'mid': 999, 'title': 'x'}, 'accept_invite', s))

    def test_the_operation_drafts_and_never_sends(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = outlook_store(); out = arrive(s)
        g = Fake()
        with mock.patch.object(server, 'store', s), mock.patch.object(calwrite, 'requests', g), mock.patch.object(calwrite, 'busy', return_value=BUSY):
            c = TestClient(server.app)
            for act in ('accept', 'propose'):
                op = c.post('/api/operations', json={'kind': 'calendar.answer', 'target': out['message_id'], 'params': {'act': act}}).json()
                r = c.post(f"/api/operations/{op['id']}/execute", json={'version': op['version']})
                self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(g.calls, [], 'nothing reached a calendar')
        pending = [json.loads(r['Deliver']) for r in s.reviews_for_message(out['message_id']) if r['Status'] == 'pending']
        self.assertEqual([e['act'] for e in pending], ['propose'])
        self.assertFalse(calwrite.clashes(s, pending[0]['new_start'], pending[0]['new_end'], events=BUSY))


class Clash(unittest.TestCase):
    def test_overlap_names_the_meeting_and_its_time(self):
        s = MemoryStore()
        self.assertEqual(calwrite.clash_line(s, f'{D} 14:30', f'{D} 15:30', events=BUSY), 'clashes with Budget review 2:00-3:00 PM')
        self.assertEqual(calwrite.clash_line(s, f'{D} 12:00', f'{D} 13:00', events=BUSY), '')
        self.assertEqual(calwrite.clash_line(s, f'{D} 14:00', f'{D} 15:00', skip='Budget review', events=BUSY), '', 'never itself')


if __name__ == '__main__':
    unittest.main()
