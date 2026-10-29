"""A vendor's invitation is fyi unless the owner actually needs to respond (the owner, 2026-10-29).

Every unanswered webinar or demo invite from a vendor's rep came back as a reply the owner owed: triage read "let me know if you can
make it" as a question put to them, and the morning brief kept the silence as an ask that slipped. What the invitation IS stays the
model's call - the guide says how to read one (section 2, "An invitation from a vendor or a list") - and the brief reads triage's own
asks_owner, never the invitation's words.
"""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import assistant, ingest, triage
from taskuary.store import MemoryStore

ME = 'alex@northwind.example'
REP = 'sam@vendor.example'
INVITE = 'Hi Alex - we are running a live demo of our new scheduling module on Thursday. Save your seat, and let me know if you can make it!'


def ago(hours): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def arrive(s, llm, ext='v1', body=INVITE, hours=30):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': REP, 'from_name': 'Sam Ortiz',
                                         'to': [ME], 'conversation_id': f'conv-{ext}', 'subject': 'Live demo Thursday', 'body': body,
                                         'sent_at': ago(hours)}, llm=llm)


def verdict(**v):
    seen = []
    def llm(system, user, **k):
        seen.append(system)
        return json.dumps({'why': 'scripted', 'title': 'Vendor demo invite', 'summary': 's', 'sender_class': 'person', **v})
    llm.seen = seen
    return llm


class TheGuideSaysHowToReadOne(unittest.TestCase):
    def test_the_model_is_told_an_invitation_is_fyi_unless_the_owner_must_answer(self):
        s = MemoryStore(); s.set_setting('owner_email', ME, 't')
        llm = verdict(intent='fyi', asks_owner=False)
        out = arrive(s, llm)
        self.assertEqual((out['status'], out['task_id']), ('filed', None))
        said = llm.seen[0]
        self.assertIn('An invitation from a vendor or a list', said)
        self.assertIn('stays fyi unanswered', said)
        self.assertIn('actually need to respond', said)
        self.assertIn('An invitation from a vendor or a list', triage.SHIPPED)


class TheBriefReadsAsksOwner(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.s.set_setting('owner_email', ME, 't'); self.s.set_setting('calendar_enabled', '0', 't')

    def test_a_reply_only_that_waits_on_nobody_is_not_an_ask_that_slipped(self):
        arrive(self.s, verdict(intent='reply_only', asks_owner=False))
        self.assertEqual(assistant.unanswered(self.s, days=3), [])

    def test_one_that_still_waits_on_the_owner_still_slips(self):
        arrive(self.s, verdict(intent='reply_only', asks_owner=True), body='Alex, you signed up for Thursday - which of your sites should we demo?')
        self.assertEqual([c['kind'] for c in assistant.unanswered(self.s, days=3)], ['asked'])


if __name__ == '__main__':
    unittest.main()
