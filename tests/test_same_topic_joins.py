"""One job is one task, however many people, threads and channels it arrives on (the owner, 2026-10-26: "if someone sends a email
to us, then another person sends us about same topic will they get joined on one task ... also if there is teams message then email
about same task will it join it? We should join them as it's about same thing"). Triage was shown an open task only for the same
thread, the same sender or two of its title's words in the SUBJECT - so a second colleague's differently-worded mail, or a Teams line,
never put the task in front of it. Now the arrival's body is read for the task's topic; the model still says same_as."""
import json, unittest
from unittest import mock

from taskuary import context, ingest, sentjudge
from taskuary.routing import tokens
from taskuary.store import MemoryStore

TITLE, SUMMARY = 'Reconcile the Payworth Q3 invoice', 'Gail needs the Payworth Q3 invoice reconciled against the ledger export before the Friday close.'


def brain(seen=None, same_as=None, title=TITLE):
    def llm(system, user, **k):
        if seen is not None: seen.append(user)
        out = {'intent': 'task', 'kind': 'task', 'why': 'scripted', 'title': title, 'summary': SUMMARY}
        if same_as is not None: out['same_as'] = same_as
        return json.dumps(out)
    return llm


def arrive(s, ext, llm, conv, frm, name, subject, body, channel='email'):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': channel, 'from_email': frm, 'from_name': name,
                                         'conversation_id': conv, 'subject': subject, 'body': body, 'sent_at': '2026-10-26 09:00:00'}, llm=llm)


def gails(s): return arrive(s, 'g', brain(), 'thread-A', 'gail@northwind.example', 'Gail Moreno', 'Payworth Q3 invoice',
                            'Alex, can you reconcile the Payworth Q3 invoice against the ledger export before Friday close?')

PAULA = dict(conv='thread-B', frm='paula@northwind.example', name='Paula Vance', subject='Quick question before close',
             body='Hi Alex, finance is still waiting on the Payworth invoice for Q3 - has it been reconciled with the ledger yet?')


class SameTopicTests(unittest.TestCase):
    def test_another_person_on_another_thread_is_shown_the_task_and_joins_it(self):
        s = MemoryStore(); tid = gails(s)['task_id']; seen = []
        # the subject shares no word with the title: by the subject alone it was never shown
        self.assertFalse(set(tokens(PAULA['subject'])) & set(tokens(TITLE)))
        b = arrive(s, 'p', brain(seen, same_as=tid), **PAULA)
        self.assertIn(f'"tid": {tid}', seen[-1])
        self.assertIn('the same topic (', seen[-1])
        self.assertIn('"about": "Gail needs the Payworth Q3 invoice', seen[-1])
        self.assertEqual((b['status'], b['task_id']), ('routed', tid))
        self.assertEqual(len(s.list_tasks()), 1)

    def test_its_null_still_opens_a_task_of_its_own(self):
        s = MemoryStore(); tid = gails(s)['task_id']
        b = arrive(s, 'p', brain(title='Answer finance on the Q3 close'), **PAULA)
        self.assertEqual(b['status'], 'created'); self.assertNotEqual(b['task_id'], tid)

    def test_a_teams_line_about_the_same_job_is_shown_the_emailed_task(self):
        s = MemoryStore(); tid = gails(s)['task_id']; seen = []
        r = arrive(s, 't', brain(seen, same_as=tid), 'teams:finance-room', 'paula@northwind.example', 'Paula Vance', '',
                   'did the Payworth Q3 invoice get reconciled yet? the ledger is locked tonight', channel='teams')
        self.assertTrue(seen, 'a chat line goes through triage')
        self.assertIn(f'"tid": {tid}', seen[-1])
        self.assertIn('the same topic (', seen[-1])
        self.assertEqual((r['status'], r['task_id']), ('routed', tid))

    def test_an_email_is_shown_the_task_a_teams_line_opened(self):
        s = MemoryStore(); seen = []
        tid = arrive(s, 't', brain(), 'teams:finance-room', 'paula@northwind.example', 'Paula Vance', '',
                     'can you reconcile the Payworth Q3 invoice against the ledger before Friday close?', channel='teams')['task_id']
        self.assertTrue(tid)
        arrive(s, 'g', brain(seen), 'thread-A', 'gail@northwind.example', 'Gail Moreno', 'Month end',
               'Alex - where are we on the Payworth invoice for Q3? The ledger needs it reconciled.')
        self.assertIn(f'"tid": {tid}', seen[-1])

    def test_an_unrelated_mail_is_not_shown_it(self):
        s = MemoryStore(); tid = gails(s)['task_id']
        shown = context.recent_open(s, {'conversation_id': 'thread-C', 'from_email': 'omar@northwind.example', 'channel': 'email',
                                        'subject': 'Printer on floor 3', 'body': 'Hi Alex, the printer is jammed again - can someone call '
                                        'the vendor before Friday close?'})
        self.assertNotIn(tid, [w['tid'] for w in shown])

    def test_the_owners_own_mail_on_another_thread_is_shown_it(self):
        s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't'); tid = gails(s)['task_id']
        mid = s.add_message({'ExternalId': 'sent-1', 'ConversationId': 'thread-R', 'Channel': 'email', 'Subject': 'Numbers',
                             'FromName': 'Alex Doyle', 'FromEmail': 'alex@northwind.example', 'SentAt': '2026-10-26 10:00:00',
                             'Status': 'context', 'BodyText': 'Ray - I am reconciling the Payworth Q3 invoice against the ledger today.'})
        self.assertIn(tid, [w['tid'] for w in sentjudge.open_work(s, s.get_message(mid))])

    def test_a_report_keeps_its_own_ranking(self):
        s = MemoryStore(); tid = gails(s)['task_id']
        shown = context.recent_open(s, {'conversation_id': 'rep-1', 'channel': 'report', 'subject': 'Daily check',
                                        'body': 'All clear. Nothing about any invoice or ledger today, Payworth quiet.'})
        self.assertFalse([w for w in shown if w['why'].startswith('the same topic')])


if __name__ == '__main__': unittest.main()
