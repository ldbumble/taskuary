"""Different tasks from different sources can be joined (the owner, 2026-11-04: "I thought we went through this already"). A follow-up
from a THIRD party - another thread, another sender, no shared number - was never put in front of triage beside the task it belongs to:
only structure tied an arrival to open work, and matching by meaning needs an embedder the install may not have. Now every arrival is
shown a compact list of the owner's open tasks and Watching items (context.open_items) and the model joins by meaning, or does not."""
import json, re, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import context, ingest
from taskuary.store import MemoryStore
from tests import fake_embed

ALEX, GAIL, PORTAL, ONBOARD = 'alex@northwind.example', 'gail@northwind.example', 'support@vendor.example', 'welcome@payworth.example'


def brain(seen, topic):
    "Stands in for the model: names a task about `topic` - only one the prompt listed, so a join needs the list to have shown it."
    def llm(system, user, **k):
        seen.append(user)
        j, out = json.loads(user), {'intent': 'watch', 'why': 'someone else handles it', 'title': 'Vendor portal', 'summary': 'About the portal.'}
        hit = [int(m) for l in j.get('open_items') or [] if topic in l.lower() for m in re.findall(r'\(tid (\d+)\)', l)]
        if hit: out['same_as'] = hit[0]
        return json.dumps(out)
    return llm


def arrive(s, llm, ext, conv, frm, name, to, subject, body):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': frm, 'from_name': name, 'to': to, 'cc': [],
                                         'conversation_id': conv, 'subject': subject, 'body': body, 'sent_at': '2026-11-04 10:28:00'}, llm=llm)


class OpenItemsJoinTests(unittest.TestCase):
    def setUp(self):
        cm = fake_embed.no_embedder(); cm.__enter__(); self.addCleanup(cm.__exit__, None, None, None)
        self.s = MemoryStore(); self.s.set_setting('owner_email', ALEX, 't')
        self.tid = arrive(self.s, brain([], 'portal'), 'r', 'thread-A', GAIL, 'Gail Moreno', [PORTAL, ALEX], 'Access to the vendor portal',
                          'Hi, could you set me up with a login to the vendor portal so I can download the invoices? Thanks, Gail')['task_id']
        self.assertTrue(self.tid)

    def test_a_third_partys_follow_up_on_a_new_thread_joins_the_watched_item(self):
        seen = []
        r = arrive(self.s, brain(seen, 'portal'), 'c', 'thread-B', ONBOARD, 'Payworth Onboarding', [ALEX], 'Welcome aboard',
                   'Good news: the portal account you requested for your team is now active. Sign in from the welcome page.')
        items = json.loads(seen[-1]).get('open_items') or []
        self.assertTrue(any(f'(tid {self.tid})' in l for l in items), 'the watched item is in front of triage')
        self.assertNotIn('open_work', json.loads(seen[-1]), 'nothing structural tied them - the list is the only evidence')
        self.assertEqual(r['task_id'], self.tid)
        self.assertEqual(len(self.s.list_tasks()), 1)

    def test_a_different_matter_is_shown_the_list_and_still_not_joined(self):
        seen = []
        r = arrive(self.s, brain(seen, 'lunch'), 'l', 'thread-C', 'ray@northwind.example', 'Ray Colton', [ALEX], 'Friday',
                   'Lunch on Friday with the auditors? Ray')
        self.assertTrue(any(f'(tid {self.tid})' in l for l in json.loads(seen[-1]).get('open_items') or []))
        self.assertNotEqual(r['task_id'], self.tid)
        self.assertEqual(len(self.s.list_tasks()), 2)


class OpenItemsBoundTests(unittest.TestCase):
    def test_bounded_newest_first_and_no_closed_work(self):
        s = MemoryStore()
        tids = [s.create_task({'Title': f'Task number {i} about something', 'Summary': f'what task {i} asks'}, 'owner') for i in range(context.OPEN_ITEMS + 10)]
        for t, st in zip(tids[-2:], ('done', 'dropped')): s._exec('UPDATE task SET Status=? WHERE TaskId=?', (st, t))
        got = context.open_items(s, skip={tids[-3]})
        shown = [int(re.search(r'\(tid (\d+)\)', l)[1]) for l in got]
        self.assertEqual(len(got), context.OPEN_ITEMS)
        self.assertFalse({*tids[-3:]} & {*shown}, 'skipped, done and dropped are left out')
        self.assertTrue(all(len(l) <= context.OPEN_ITEM_CHARS for l in got))



def finder(seen, topic, intent='task'):
    "Stands in for the model: names a task about `topic` only from what the owner's search found and showed it."
    def llm(system, user, **k):
        seen.append(user)
        j, out = json.loads(user), {'intent': intent, 'why': 'new work on it', 'title': 'Trainly licence seats', 'summary': 'About the Trainly seats.', 'kind': 'task'}
        hit = [int(m) for l in j.get('found_by_search') or [] if topic in l.lower() for m in re.findall(r'\(tid (\d+)\)', l)]
        if hit: out['same_as'] = hit[0]
        return json.dumps(out)
    return llm


class ClosedTaskFoundTests(unittest.TestCase):
    "A task closed last week is past recent_closures' days and shares no thread, sender or number with the follow-up: search finds it."
    def setUp(self):
        cm = fake_embed.no_embedder(); cm.__enter__(); self.addCleanup(cm.__exit__, None, None, None)
        self.s = MemoryStore(); self.s.set_setting('owner_email', ALEX, 't')
        self.tid = arrive(self.s, finder([], 'trainly'), 'q', 'thread-T', GAIL, 'Gail Moreno', [ALEX], 'Trainly licence seats for finance',
                          'Can we add three Trainly licence seats for the finance team before the quarter starts?')['task_id']
        self.s.update_task(self.tid, {'Status': 'done'}, 'owner')
        ago = lambda d: (datetime.now() - timedelta(days=d, hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        self.s._exec('UPDATE task SET ClosedAt=?, UpdatedAt=?, CreatedAt=? WHERE TaskId=?', (ago(7), ago(7), ago(9), self.tid))

    def test_a_follow_up_from_a_new_sender_finds_joins_and_reopens_it(self):
        seen = []
        r = arrive(self.s, finder(seen, 'trainly'), 'f', 'thread-U', 'billing@trainly.example', 'Trainly Billing', [ALEX], 'Your Trainly renewal',
                   'The renewal for your Trainly licence seats is due. Please confirm the seat count so we can issue the invoice.')
        found = json.loads(seen[-1]).get('found_by_search') or []
        self.assertTrue(any(f'(tid {self.tid})' in l and 'closed 7d ago' in l for l in found), found)
        self.assertNotIn('recently_closed', json.loads(seen[-1]), 'nothing but the search put it in front of triage')
        self.assertEqual(r['task_id'], self.tid)
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'open', 'new work owed on it brings it back')

    def test_nothing_owed_keeps_it_closed(self):
        r = arrive(self.s, finder([], 'trainly', 'fyi'), 'g', 'thread-V', 'billing@trainly.example', 'Trainly Billing', [ALEX], 'Trainly receipt',
                   'Receipt for your Trainly licence seats - nothing to do.')
        self.assertEqual(r['task_id'], self.tid)
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')

    def test_an_unrelated_mail_is_not_joined(self):
        seen = []
        r = arrive(self.s, finder(seen, 'trainly'), 'h', 'thread-W', 'ray@northwind.example', 'Ray Colton', [ALEX], 'Parking',
                   'The garage is closed on Monday for repairs, park on the street.')
        self.assertFalse(any(f'(tid {self.tid})' in l for l in json.loads(seen[-1]).get('found_by_search') or []))
        self.assertNotEqual(r['task_id'], self.tid)
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')


if __name__ == '__main__': unittest.main()
