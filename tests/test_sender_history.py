"""How this sender's last asks were worked reaches the judge (the owner, 2026-10-05: TQ-0955 "should have been sent to
coding agent repo T&E ... it's from the person that asks about it and right words").

A payroll lead's last three asks - a setup issue, missing employees in an import, approved items to reopen - were all
coding tasks on the same repository. Her fourth, a facility mapping to correct, was judged general: triage named the right
repository but was shown none of that history, because recently_closed reaches back three days and her last task closed a
week before. Not a rule - evidence, the way recently_closed is: a different kind of ask from her still goes where it belongs.
"""
import json, unittest
from datetime import datetime, timedelta

from taskuary import context, triage
from taskuary.store import MemoryStore

ERIN = 'erin@northwind.example'


def ago(days): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')


def asked(s, title, days, kind='coding', repo='northwind/ledger', sender=ERIN, status='done'):
    tid = s.create_task({'Title': title, 'Kind': kind, 'Status': status, 'Tags': f'triage-repo:{repo}' if repo else ''}, 'router')
    s.add_message({'ExternalId': f'm{tid}', 'Channel': 'email', 'ConversationId': f'c{tid}', 'FromEmail': sender,
                   'Subject': title, 'SentAt': ago(days), 'TaskId': tid, 'BodyText': 'b'})
    s.cx.execute('UPDATE task SET CreatedAt=? WHERE TaskId=?', (ago(days), tid))
    return tid


class SenderHistoryTests(unittest.TestCase):
    def test_her_last_asks_arrive_with_their_kind_and_repository_newest_first(self):
        s = MemoryStore()
        asked(s, 'Investigate ledger employee setup issues', 25)
        asked(s, 'Missing employees in the import', 13)
        last = asked(s, 'Reopen approved items for payroll', 7)
        got = context.sender_history(s, {'from_email': ERIN, 'channel': 'email', 'subject': 'Reimbursements'})
        self.assertEqual([g['title'] for g in got][:1], ['Reopen approved items for payroll'])
        self.assertEqual(got[0], {'ref': f'TQ-{last:04d}', 'title': 'Reopen approved items for payroll', 'kind': 'coding',
                                  'repository': 'northwind/ledger', 'status': 'done', 'when': ago(7)[:10]})
        self.assertEqual(len(got), 3)

    def test_it_reaches_further_back_than_recently_closed_but_not_for_ever(self):
        s = MemoryStore()
        asked(s, 'Reopen approved items for payroll', 7)
        asked(s, 'An old one', context.SENDER_DAYS + 5)
        got = context.sender_history(s, {'from_email': ERIN, 'channel': 'email'})
        self.assertEqual([g['title'] for g in got], ['Reopen approved items for payroll'])

    def test_a_few_not_all(self):
        s = MemoryStore()
        for d in range(1, 8): asked(s, f'Ask {d}', d)
        self.assertEqual(len(context.sender_history(s, {'from_email': ERIN, 'channel': 'email'})), context.SENDER_PAST)

    def test_only_this_senders(self):
        s = MemoryStore()
        asked(s, 'Somebody else entirely', 3, sender='ray@northwind.example')
        self.assertEqual(context.sender_history(s, {'from_email': ERIN, 'channel': 'email'}), [])

    def test_a_dropped_ask_is_not_how_her_work_is_done(self):
        s = MemoryStore()
        asked(s, 'Not ours after all', 3, status='dropped')
        self.assertEqual(context.sender_history(s, {'from_email': ERIN, 'channel': 'email'}), [])

    def test_taskuarys_own_reports_have_no_sender_history(self):
        s = MemoryStore()
        asked(s, 'Process Error Check', 3, sender='report@taskuary')
        self.assertEqual(context.sender_history(s, {'from_email': 'report@taskuary', 'channel': 'report'}), [])


class TheJudgeIsShownItTests(unittest.TestCase):
    def test_it_rides_in_the_payload_with_its_explanation(self):
        seen = {}
        def llm(system, user, **kw):
            seen.update(sys=system, usr=json.loads(user)); return '{"intent": "task", "kind": "coding", "why": "x"}'
        hist = [{'ref': 'TQ-0766', 'title': 'Reopen approved items for payroll', 'kind': 'coding',
                 'repository': 'northwind/ledger', 'status': 'done', 'when': '2026-09-28'}]
        triage.classify_intent({'from_email': ERIN, 'subject': 'Reimbursements', 'body': 'Can we update the facility?'},
                               llm=llm, thread={'sender_history': hist})
        self.assertEqual(seen['usr']['sender_history'], hist)
        self.assertIn('sender_history', seen['sys'])
        self.assertIn('sender_history', triage.INTENT_SYSTEM)

    def test_ingest_hands_it_to_the_judge(self):
        from unittest import mock
        from taskuary import ingest
        s = MemoryStore()
        asked(s, 'Reopen approved items for payroll', 7)
        seen = {}
        def judge(msg, **kw): seen.update(kw.get('thread') or {}); return {'intent': 'fyi', 'why': 'x'}
        with mock.patch.object(ingest, 'classify_intent', side_effect=judge):
            ingest.judge(s, {'from_email': ERIN, 'channel': 'email', 'subject': 'Reimbursements', 'body': 'b',
                             'conversation_id': 'new-thread'}, llm=lambda *a, **k: '{}')
        self.assertEqual([h['title'] for h in seen.get('sender_history') or []], ['Reopen approved items for payroll'])
