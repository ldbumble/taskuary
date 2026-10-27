"""Remind me (the owner, 2026-09-25): an open task put away until a day is Upcoming and off the work rail
until that morning, then back saying why - one road for the task page's picker and the Assistant's tool."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, funnel, processing_unread, remind, server
from taskuary.store import MemoryStore, task_ref


def ago(hours=0): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled', 'learn_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._CACHE.update(cands_at=0.0, cands=[])
    return s


def asked(s):
    t = s.create_task({'Title': 'Renew the vendor contract', 'Kind': 'task', 'Status': 'open', 'Assignee': 'owner'}, 'o')
    s.add_message({'TaskId': t, 'ExternalId': 'x:renew', 'Channel': 'email', 'SourceName': 'inbox', 'Subject': 'Contract renewal',
                   'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': ago(3),
                   'BodyText': 'Can you renew it before it lapses?', 'Status': 'routed'})
    return t


class ParseTests(unittest.TestCase):
    NOW = datetime(2026, 9, 25, 9, 30)

    def test_a_day_is_read_the_ways_people_say_it_and_lands_at_seven(self):
        for said, day in (('2026-10-09', '2026-10-09'), ('2 weeks', '2026-10-09'), ('in 3 days', '2026-09-28'),
                          ('tomorrow', '2026-09-26'), ('a month', '2026-10-25'), ('monday', '2026-09-28'), ('friday', '2026-10-02')):
            self.assertEqual(remind.parse(said, self.NOW), f'{day} 07:00:00', said)

    def test_a_time_on_the_end_keeps_its_hour(self):
        # "remind me tomorrow at 9am" reached the parser as "tomorrow 9am" and was refused whole (2026-10-06)
        for said, at in (('tomorrow 9am', '2026-09-26 09:00:00'), ('tomorrow at 9:30', '2026-09-26 09:30:00'),
                         ('monday 2pm', '2026-09-28 14:00:00'), ('friday at 4 pm', '2026-10-02 16:00:00'),
                         ('tomorrow morning', '2026-09-26 07:00:00'), ('2026-10-09 15:00', '2026-10-09 15:00:00')):
            self.assertEqual(remind.parse(said, self.NOW), at, said)
        for bad in ('tomorrow 25pm', 'tomorrow 13pm', 'tomorrow 9:75'):
            with self.assertRaisesRegex(ValueError, 'is not a day I can read'): remind.parse(bad, self.NOW)

    def test_none_clears_and_nonsense_or_the_past_is_refused(self):
        self.assertIsNone(remind.parse('none', self.NOW)); self.assertIsNone(remind.parse('', self.NOW))
        for bad in ('whenever', '2026-09-25', '2026-01-01', '2026-02-30'):
            with self.assertRaises(ValueError): remind.parse(bad, self.NOW)
        for bad in ('whenever', '2026-02-30', '2026-13-45'):
            with self.assertRaisesRegex(ValueError, 'is not a day I can read'): remind.parse(bad, self.NOW)


class RailTests(unittest.TestCase):
    def rail(self, s, t, now):
        return [i for i in processing_unread.build(s, now=now, live_state=[])['items'] if i.get('tid') == t]

    def test_put_away_it_leaves_the_rail_and_comes_back_that_morning_saying_why(self):
        s = store(); t = asked(s)
        settle = lambda: (s.reconcile_processing_membership(fixed_now=ago(0)), funnel.invalidate())
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        self.assertTrue(any(i['actionable'] for i in self.rail(s, t, datetime.now())))
        out = remind.set_reminder(s, t, '2 weeks')
        self.assertTrue(remind.waiting(s.get_task(t))); settle()
        self.assertFalse(any(i['actionable'] for i in self.rail(s, t, datetime.now())), 'still on the rail while put away')
        day = datetime.strptime(out['remindAt'], '%Y-%m-%d %H:%M:%S') + timedelta(hours=1)
        # two weeks on, the mail is past the rail's look-back: the morning's note is what brings it back
        self.assertEqual(remind.due(s, day), 1)
        self.assertEqual(s.list_comments(t)[-1]['Body'], remind.DUE_NOTE)
        self.assertFalse(s.get_task(t).get('RemindAt'), 'a reminder speaks once')
        settle()
        self.assertTrue([i for i in self.rail(s, t, datetime.now()) if i['actionable']], 'not back on its day')
        self.assertEqual(remind.due(s, day), 0)

    def test_none_brings_it_back_now_and_nothing_carries_an_undo(self):
        s = store(); t = asked(s)
        self.assertNotIn('undo', remind.set_reminder(s, t, 'tomorrow'))     # no Take it back (the owner, 2026-10-19)
        remind.set_reminder(s, t, 'none')
        self.assertFalse(remind.waiting(s.get_task(t)))

    def test_a_done_task_cannot_be_put_away(self):
        s = store(); t = asked(s); s.update_task(t, {'Status': 'done'}, 'o')
        with self.assertRaises(ValueError): remind.set_reminder(s, t, 'tomorrow')


class ToolTests(unittest.TestCase):
    def test_the_assistant_brings_a_named_task_up_with_remind_me_lit_and_the_receipt_says_where_it_went(self):
        s = store(); t = asked(s)
        call = {'kind': 'task.defer', 'params': {'until': '2 weeks', 'ref': task_ref(t)}}
        llm = lambda *a, **k: 'Putting it away.\nCALL: ' + json.dumps(call)
        with mock.patch.object(server, 'store', s):
            # the desk: the task up, its Remind me lit - nothing put away on the words (the owner, 2026-10-19)
            out = concierge.say(s, 'bring TQ back in 2 weeks', llm=llm)
            self.assertEqual((out['light']['verb'], out['light']['tid']), ('defer', t)); self.assertFalse(remind.waiting(s.get_task(t)))
            # the phone: a yes or no, and the yes puts it away
            with concierge.delivering(concierge.PHONE): p = concierge.say(s, 'bring TQ back in 2 weeks', llm=llm)['proposal']
            self.assertEqual((p['kind'], p['target']), ('task.defer', t))
            done = concierge.run_proposal(s, p)
        self.assertTrue(remind.waiting(s.get_task(t)))
        self.assertIn('under For later on your rail', concierge.receipt(s, done))

    def test_the_said_day_rides_the_lit_remind_me_and_the_picker_road_takes_it(self):
        """"remind me Monday" lit Remind me and its picker had no Monday, while the phone kept the day (the owner, 2026-10-27): the light
        carries the day - its date and its words - and the picker's road reads that date back as the same day."""
        s = store(); t = asked(s)
        call = {'kind': 'task.defer', 'params': {'until': 'monday', 'ref': task_ref(t)}}
        llm = lambda *a, **k: 'Putting it away.\nCALL: ' + json.dumps(call)
        with mock.patch.object(server, 'store', s):
            light = concierge.say(s, 'remind me Monday', llm=llm)['light']
            at = remind.parse('monday')
            self.assertEqual((light['verb'], light['day']), ('defer', {'until': at[:16], 'day': remind.when(at)}))
            self.assertTrue(light['day']['day'].startswith('Mon '), light['day'])
            self.assertFalse(remind.waiting(s.get_task(t)), 'lit, never put away on the words')
            self.assertEqual(TestClient(server.app).post(f'/api/tasks/{t}/remind', json={'until': light['day']['until']}).status_code, 200)
        self.assertEqual(str(s.get_task(t)['RemindAt'])[:16], at[:16])
        # a time said with the day keeps it; no day, an unreadable one, or "none" adds no button
        self.assertEqual(concierge.said_day('friday 2pm')['until'][11:], '14:00')
        for none in ('', 'none', 'someday', None): self.assertEqual(concierge.said_day(none), {}, none)

    def test_the_task_page_road_is_the_same_one(self):
        s = store(); t = asked(s)
        with mock.patch.object(server, 'store', s):
            r = TestClient(server.app).post(f'/api/tasks/{t}/remind', json={'until': '1 week'})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(remind.waiting(s.get_task(t)))
            self.assertEqual(TestClient(server.app).post(f'/api/tasks/{t}/remind', json={'until': 'someday'}).status_code, 422)


class LiveAgentTests(unittest.TestCase):
    """Remind me on a task whose agent session is still open put it away anyway, and the row sat on under "agent waiting
    on you" (press audit, 2026-10-01). The owner: warn that the agent is open and has to be saved and ended first - and
    do not defer it. Every door refuses the same way; bringing it back stays allowed."""
    LIVE = {'sid': 'abc', 'alive': True}

    def test_set_reminder_refuses_while_the_agent_is_open_and_leaves_the_task_as_it_was(self):
        s = store(); t = asked(s)
        with mock.patch('taskuary.terminal.for_task', return_value=self.LIVE):
            with self.assertRaisesRegex(remind.AgentOpen, 'Stop and save'): remind.set_reminder(s, t, '2 weeks')
            self.assertFalse(remind.waiting(s.get_task(t)))
            self.assertIsNone(remind.set_reminder(s, t, 'none')['remindAt'], 'bringing it back is never refused')

    def test_the_task_page_door_answers_409_with_the_reason(self):
        s = store(); t = asked(s)
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.terminal.for_task', return_value=self.LIVE):
            r = TestClient(server.app).post(f'/api/tasks/{t}/remind', json={'until': '1 week'})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn('Stop and save', r.json()['detail'])
        self.assertFalse(remind.waiting(s.get_task(t)))

    def test_the_operation_door_refuses_the_same_way(self):
        s = store(); t = asked(s)
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.terminal.for_task', return_value=self.LIVE):
            with self.assertRaises(server.HTTPException) as e:
                server._run_operation({'kind': 'task.defer', 'target': t, 'params': {'until': '2 weeks'}}, None)
        self.assertEqual(e.exception.status_code, 409)
        self.assertIn('Stop and save', e.exception.detail)
        self.assertFalse(remind.waiting(s.get_task(t)))


class WhatOutranksTheDayTests(unittest.TestCase):
    """Remind me holds a QUIET task (B2, the owner, 2026-10-11): it sat under For later past its own due day, and past
    the sender writing again, until the remind day - the walk said "at the top of your list" while the row stayed put away."""
    def rail(self, s, t):
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            return [i for i in processing_unread.build(s, live_state=[])['items'] if i.get('tid') == t]

    def setUp(self):
        from taskuary.ingest import ingest_message
        self.ingest, self.s = ingest_message, store()
        self.t = self.mail('m1', 'Budget', 'Can you send the budget next month?', 'task', hours=5)['task_id']
        self.settle(); self.s.activate_processing_reads(fixed_now=ago(0), live_state=[]); self.settle()
        remind.set_reminder(self.s, self.t, '2 weeks'); self.settle()
        self.assertTrue(all(i['deferred'] and not i['actionable'] for i in self.rail(self.s, self.t)), 'not put away to begin with')

    def settle(self): self.s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()

    def mail(self, xid, subject, body, intent, hours=0):
        brain = lambda *a, **k: json.dumps({'intent': intent, 'kind': 'task', 'why': 'invented for the test', 'title': subject})
        return self.ingest(self.s, {'external_id': xid, 'channel': 'email', 'from_email': 'erin@northwind.example', 'from_name': 'Erin Blake',
                                    'conversation_id': 'conv-b2', 'subject': subject, 'body': body, 'sent_at': ago(hours)}, llm=brain)

    def back(self):
        self.settle(); rows = self.rail(self.s, self.t)
        return bool(rows) and all(not i['deferred'] and i['actionable'] and i['unread'] for i in rows)

    def test_its_due_day_coming_near_brings_it_back(self):
        remind.set_due(self.s, self.t, (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'))
        self.assertEqual(remind.deadlines(self.s), 1)
        self.assertFalse(self.s.get_task(self.t).get('RemindAt'), 'the due day left the reminder standing')
        self.assertTrue(self.back(), 'due tomorrow and still under For later')

    def test_the_sender_writing_again_brings_it_back(self):
        self.assertEqual(self.mail('m2', 'RE: Budget', 'Change of plan - the board needs it tomorrow.', 'task')['status'], 'attached')
        self.assertFalse(self.s.get_task(self.t).get('RemindAt'), 'a new ask left the reminder standing')
        self.assertTrue(self.back(), 'the sender wrote again and it stayed under For later')

    def test_a_thanks_on_the_thread_leaves_it_away(self):
        self.assertEqual(self.mail('m2', 'RE: Budget', 'Thanks!', 'fyi')['status'], 'filed')
        self.assertTrue(remind.waiting(self.s.get_task(self.t)), 'an fyi lifted the reminder')


class AfterTheDueDayTests(unittest.TestCase):
    def test_a_reminder_past_the_due_day_is_set_and_says_so(self):
        s = store(); t = asked(s)
        remind.set_due(s, t, (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d'))
        out = remind.set_reminder(s, t, '2 weeks')
        self.assertTrue(remind.waiting(s.get_task(t)), 'warn, never refuse')
        self.assertIn('due', out.get('warn') or '')
        self.assertFalse(remind.set_reminder(s, t, 'tomorrow').get('warn'), 'warned for a day before it is due')
