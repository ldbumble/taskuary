"""A helpdesk's "your ticket was submitted" answers a colleague's request the owner is copied on - on a NEW thread, from a sender the
task never heard from, in other words. The owner watched the request; the confirmation opened a second Watching row beside it (the
owner: "This is literally the same thing. why is it 2 rows??"). With no embedder nothing put the watched request in front of triage:
not the thread, not the sender, no shared number. What ties them is structure - the two mails are written between the same people,
the vendor answering the colleague who wrote to it - and that is now shown; the model still says same_as."""
import json, re, unittest
from unittest import mock

from taskuary import context, ingest
from taskuary.store import MemoryStore
from tests import fake_embed

ALEX, GAIL, DESK = 'alex@northwind.example', 'gail@northwind.example', 'support@vendor.example'


def brain(seen):
    "Watches both; names the watched request as the one this is only when the prompt showed it - nothing scripted about the join."
    def llm(system, user, **k):
        seen.append(user)
        tids = re.findall(r'"tid": (\d+)', user)
        out = {'intent': 'watch', 'why': 'the vendor handles it', 'title': 'Vendor access for Gail', 'summary': 'Gail asked the vendor for access.'}
        if tids: out['same_as'] = int(tids[0])
        return json.dumps(out)
    return llm


def arrive(s, llm, ext, conv, frm, name, to, cc, subject, body):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': frm, 'from_name': name, 'to': to, 'cc': cc,
                                         'conversation_id': conv, 'subject': subject, 'body': body, 'sent_at': '2026-11-04 10:28:00'}, llm=llm)


def request(s, seen): return arrive(s, brain(seen), 'r', 'thread-A', GAIL, 'Gail Moreno', [DESK], [ALEX], 'Give Gail full access to the budget app',
                                    'Hi, please change my role in the budget app so I can see budgets, not only AR. Thanks, Gail')


class ConfirmationJoinsWatchTests(unittest.TestCase):
    def setUp(self):
        cm = fake_embed.no_embedder(); cm.__enter__(); self.addCleanup(cm.__exit__, None, None, None)
        self.s = MemoryStore(); self.s.set_setting('owner_email', ALEX, 't')

    def test_the_vendors_ticket_confirmation_joins_the_watched_request(self):
        seen = []; tid = request(self.s, seen)['task_id']
        self.assertTrue(tid)
        r = arrive(self.s, brain(seen), 'c', 'thread-B', DESK, 'Vendor Helpdesk', [GAIL, ALEX], [],
                   'Ticket #4400123 - Give Gail full access to the budget app / Has been submitted',
                   'Hey Gail, we have received your new support request. Our technicians will be working on this shortly.')
        self.assertIn(f'"tid": {tid}', seen[-1], 'the watched request is put in front of triage')
        self.assertIn('the same people', seen[-1])
        self.assertEqual(r['task_id'], tid)
        self.assertEqual(len(self.s.list_tasks()), 1, 'one row, its thread carrying both')

    def test_the_vendor_writing_to_someone_else_is_not_shown_it(self):
        tid = request(self.s, [])['task_id']
        shown = context.recent_open(self.s, {'conversation_id': 'thread-C', 'from_email': DESK, 'channel': 'email', 'to': ['ray@northwind.example'],
                                             'cc': [ALEX], 'subject': 'Your ticket', 'body': 'Hey Ray, we received your request.'})
        self.assertNotIn(tid, [w['tid'] for w in shown])

    def test_the_owner_alone_on_both_ties_nothing(self):
        tid = request(self.s, [])['task_id']
        shown = context.recent_open(self.s, {'conversation_id': 'thread-D', 'from_email': 'omar@northwind.example', 'channel': 'email',
                                             'to': [ALEX], 'cc': [], 'subject': 'Lunch', 'body': 'Lunch on Friday?'})
        self.assertNotIn(tid, [w['tid'] for w in shown])


if __name__ == '__main__': unittest.main()
