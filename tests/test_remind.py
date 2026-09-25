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
    for k in ('calendar_enabled', 'coder_auto_enabled', 'learn_enabled'): s.set_setting(k, '0', 't')
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

    def test_none_clears_and_nonsense_or_the_past_is_refused(self):
        self.assertIsNone(remind.parse('none', self.NOW)); self.assertIsNone(remind.parse('', self.NOW))
        for bad in ('whenever', '2026-09-25', '2026-01-01'):
            with self.assertRaises(ValueError): remind.parse(bad, self.NOW)


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

    def test_the_undo_puts_it_back_now(self):
        s = store(); t = asked(s)
        out = remind.set_reminder(s, t, 'tomorrow')
        self.assertEqual(out['undo']['params'], {'until': 'none'})
        remind.set_reminder(s, t, out['undo']['params']['until'])
        self.assertFalse(remind.waiting(s.get_task(t)))

    def test_a_done_task_cannot_be_put_away(self):
        s = store(); t = asked(s); s.update_task(t, {'Status': 'done'}, 'o')
        with self.assertRaises(ValueError): remind.set_reminder(s, t, 'tomorrow')


class ToolTests(unittest.TestCase):
    def test_the_assistant_puts_a_named_task_away_at_once_and_the_receipt_says_where_it_went(self):
        s = store(); t = asked(s)
        call = {'kind': 'task.defer', 'params': {'until': '2 weeks', 'ref': task_ref(t)}}
        with mock.patch.object(server, 'store', s):
            out = concierge.say(s, 'bring TQ back in 2 weeks', llm=lambda *a, **k: 'Putting it away.\nCALL: ' + json.dumps(call))
            p = out['proposal']
            self.assertEqual((p['kind'], p['target'], p.get('auto')), ('task.defer', t, True))
            done = concierge.run_proposal(s, p)
        self.assertTrue(remind.waiting(s.get_task(t)))
        self.assertIn('Upcoming', concierge.receipt(s, done))

    def test_the_task_page_road_is_the_same_one(self):
        s = store(); t = asked(s)
        with mock.patch.object(server, 'store', s):
            r = TestClient(server.app).post(f'/api/tasks/{t}/remind', json={'until': '1 week'})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(remind.waiting(s.get_task(t)))
            self.assertEqual(TestClient(server.app).post(f'/api/tasks/{t}/remind', json={'until': 'someday'}).status_code, 422)
