"""The coding agent's context file (context.py): what the hub knows about a task, written to Taskuary's
home and pointed at from the seed - history, past work, the thread. Offline; the
calendar is off and TASKUARY_HOME is the temp home conftest forces.
"""
import json, os, unittest
from datetime import datetime, timedelta
from pathlib import Path

from taskuary import context, terminal, wrapup
from taskuary.store import MemoryStore
from tests import fake_embed

ME, DANA = 'owner@ours.com', 'dana@vendor.com'
def _ago(days=0): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')


def _store():
    s = MemoryStore()
    s.set_setting('calendar_enabled', '0', 't'); s.set_setting('coding_auto_enabled', '0', 't')
    return s


def _mail(s, frm, subject, body, days=3, tid=None, conv=None, status='routed'):
    return s.add_message({'TaskId': tid, 'ExternalId': f'x:{frm}:{subject}:{days}', 'ConversationId': conv, 'Channel': 'email', 'SourceName': ME,
                          'Subject': subject, 'FromName': frm.split('@')[0].title(), 'FromEmail': frm, 'SentAt': _ago(days), 'BodyText': body, 'Status': status})


def _closed(s, title, frm, report, days=20):
    tid = s.create_task({'Title': title, 'Kind': 'coding', 'Status': 'done'}, 't')
    _mail(s, frm, title, 'the original ask', days=days, tid=tid)
    s.add_comment(tid, 'agent', 'agent', f'{wrapup.REPORT}\n{report}')
    s._exec('UPDATE task SET ClosedAt=? WHERE TaskId=?', (_ago(days - 1), tid))
    return tid


class PastWorkTests(unittest.TestCase):
    def test_closed_tasks_from_the_same_sender_or_subject_come_back_with_their_reports(self):
        s = _store()
        a = _closed(s, 'Payroll import month wrong', DANA, 'Determination: the import used file date. Actions: routing.py now reads the payroll date.')
        b = _closed(s, 'Ledger export duplicates rows', 'lee@ours.com', 'Actions: dedupe on (id, period) in export.py')
        _closed(s, 'Printer on floor 3', 'sam@ours.com', 'Actions: nothing to do here')
        tid = s.create_task({'Title': 'Ledger export still duplicating', 'Kind': 'coding'}, 't')
        mid = _mail(s, DANA, 'Ledger export still duplicating', 'Same rows twice again.', days=0, tid=tid)
        # ...the same subject is the same MEANING (embeddings), never shared title words
        with fake_embed.meaning({'ledger rows': ['ledger export']}):
            rows = context.past_work(s, s.list_messages(tid), 'Ledger export still duplicating')
        self.assertEqual({r['tid']: r['why'] for r in rows}, {a: 'the same sender', b: 'the same subject'})
        self.assertIn('payroll date', next(r for r in rows if r['tid'] == a)['report'])
        text = context.render_past(rows)
        self.assertIn('TQ-%04d' % b, text); self.assertIn('dedupe on (id, period)', text)
        # ...and with no embedder, structure alone: the sender
        with fake_embed.no_embedder():
            self.assertEqual({r['tid']: r['why'] for r in context.past_work(s, s.list_messages(tid), 'Ledger export still duplicating')},
                             {a: 'the same sender'})

    def test_no_history_means_no_section_and_no_file(self):
        s = _store()
        tid = s.create_task({'Title': 'Brand new thing', 'Kind': 'coding'}, 't')
        self.assertEqual(context.past_work(s, [], 'Brand new thing'), [])
        # ...but who the owner is always rides (SOUL.md + JOB.md, the owner 2026-10-14), so the file is the background alone
        text = context.build(s, tid)
        self.assertNotIn('## Past work', text); self.assertIn('## About the owner', text)
        for name in ('soul', 'job'): s.save_doc(name, '', 't')
        self.assertEqual(context.build(s, tid), '')                      # nothing worth a file
        self.assertIsNone(context.write(s, tid))


class FileTests(unittest.TestCase):
    def test_the_file_carries_history_past_work_and_thread_and_the_seed_points_at_it(self):
        s = _store(); s.set_setting('owner_email', 'owner@vendor.com', 't')
        # a colleague's mail is the owner's own domain; an unvouched sender would be a stranger's, whose words ride in a file (tests/test_origin_seed.py)
        a = _closed(s, 'Payroll import month wrong', DANA, 'Actions: routing.py now reads the payroll date.')
        tid = s.create_task({'Title': 'Payroll import wrong again', 'Kind': 'coding'}, 't')
        _mail(s, DANA, 'Payroll imports', 'March file landed in April.', days=9, conv='c1', status='filed')
        m1 = _mail(s, DANA, 'Payroll import wrong again', 'It is doing it again for May.', days=1, tid=tid, conv='c2')
        s.add_message({'TaskId': tid, 'ExternalId': 'mine', 'ConversationId': 'c2', 'Channel': 'email', 'SourceName': ME, 'Subject': 'Re: Payroll import wrong again',
                       'FromName': 'You', 'FromEmail': ME, 'SentAt': _ago(0), 'BodyText': 'Looking now.', 'Status': 'context'})
        path = context.write(s, tid, repo='northwind/Census')
        self.assertTrue(path and Path(path).exists())
        self.assertEqual(Path(path).parent.name, 'context')
        self.assertTrue(Path(path).is_relative_to(Path(os.environ['TASKUARY_HOME'])))     # Taskuary's home, never a checkout
        text = Path(path).read_text(encoding='utf-8')
        for want in ('## What the hub knows', 'March file landed in April',
                     '## Past work', 'reads the payroll date', '## The whole thread', 'THE OWNER', 'Looking now.'):
            self.assertIn(want, text)
        seed = terminal.seed_text(s, tid, None, 'northwind/Census', 'C:/src/Census')
        self.assertIn(f'CONTEXT FILE: {path}', seed)
        self.assertIn('and in the context file', seed)
        # in PARAGRAPHS on the command line - a blank line between blocks, none inside one (2026-09-30: "(0 lines hidden)")
        self.assertIn('\n\n', seed); self.assertNotIn('\n', seed.replace('\n\n', ''))

    def test_the_switch_turns_the_file_off_and_the_seed_stays_as_it_was(self):
        s = _store()
        _closed(s, 'Payroll import month wrong', DANA, 'Actions: fixed.')
        tid = s.create_task({'Title': 'Payroll import wrong again', 'Kind': 'coding'}, 't')
        _mail(s, DANA, 'Payroll import wrong again', 'Again.', days=1, tid=tid)
        s.set_setting('agent_context_file', '0', 't')
        self.assertIsNone(context.write(s, tid))
        seed = terminal.seed_text(s, tid)
        self.assertNotIn('CONTEXT FILE', seed); self.assertIn('everything known about it is above. ', seed)


class NewestFirstTests(unittest.TestCase):
    """A reopened coding task's context file kept the thread's FIRST mails and cut the ones after them - the very ones it was
    reopened for - while the resume seed said "3 new messages, read them in this file" (the owner, 2026-10-14)."""
    def test_a_long_thread_keeps_what_came_after_the_last_run_and_marks_it(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Budget tab still missing', 'Kind': 'coding'}, 't')
        def mail(n, sent, reached):
            mid = s.add_message({'TaskId': tid, 'ExternalId': f'b{n}', 'ConversationId': 'cb', 'Channel': 'email', 'Subject': 'Budget tab',
                                 'FromName': f'Sender {n}', 'FromEmail': f's{n}@northwind.example', 'SentAt': sent,
                                 'BodyText': f'Mail {n}. ' + 'detail ' * 200, 'Status': 'routed'})
            s.cx.execute('UPDATE message SET CreatedAt=? WHERE MessageId=?', (reached, mid))
        for n in range(1, 13): mail(n, f'2026-10-{n:02d} 09:00:00', f'2026-10-{n:02d} 09:05:00')
        s.add_transcript(tid, 'sid-1', 'worked it', agent='coding', ext_id='ext-1')
        s.cx.execute("UPDATE transcript SET CreatedAt='2026-10-10 12:00:00' WHERE TaskId=?", (tid,))
        mail(13, '2026-10-09 18:00:00', '2026-10-13 08:00:00')                 # sent before the run, read in after it: still news
        s.cx.commit()
        text = context.build(s, tid)
        self.assertIn('newest first;', text); self.assertIn('older not shown', text)
        order = [int(n) for n in __import__('re').findall(r'^--- (?:\[NEW since your last run\] )?Sender (\d+) ·', text, __import__('re').M)]
        self.assertEqual(order[:4], [13, 12, 11, 10], 'newest first, by when it reached the thread')
        self.assertNotIn(1, order, 'the oldest are what the cap drops')
        for n in (11, 12, 13): self.assertIn(f'--- [NEW since your last run] Sender {n} ·', text)
        self.assertNotIn('[NEW since your last run] Sender 10 ·', text)
        self.assertIn('NEW SINCE YOUR LAST RUN: 3 messages', terminal.resume_seed('', s, tid), 'the seed counts the ones the file marks')


class SameRunTests(unittest.TestCase):
    """Two monitors reported one failed run an hour apart; the second opened a task "after the prior one was closed" because the
    closed one - made from the first monitor's idea, on another thread - was never shown to triage (TQ-1088/1089, 2026-10-14)."""
    def test_a_closed_task_carrying_the_same_run_id_is_shown_first(self):
        s = MemoryStore()
        first = s.create_task({'Title': 'Investigate ledger sync auth failures', 'Kind': 'coding'}, 't')
        s.add_message({'TaskId': first, 'ExternalId': 'i1', 'ConversationId': 'report:9:idea:ledger', 'Channel': 'assistant',
                       'Subject': 'Advisor idea', 'BodyText': 'Ledger Sync runId 4400917 failed with HTTP 401.', 'Status': 'routed'})
        for n in range(3):                                     # the report's own older tasks, which used to take every seat
            t = s.create_task({'Title': f'Ledger sync timeout {n}', 'Kind': 'coding'}, 't')
            s.add_message({'TaskId': t, 'ExternalId': f'r{n}', 'ConversationId': 'report:4', 'Channel': 'report',
                           'Subject': 'Process Error Check', 'BodyText': 'Ledger Sync timed out.', 'Status': 'routed'})
            s.update_task(t, {'Status': 'done'}, 't')
        s.update_task(first, {'Status': 'done'}, 't')
        body = 'Error summary:\n' + 'Ledger Sync timed out. ' * 60 + '\nLedger Sync failed: runId 4400917 - 3 company failures, HTTP 401'
        msg = {'channel': 'report', 'conversation_id': 'report:4', 'subject': 'Process Error Check - Error summary:', 'body': body}
        rows = context.recent_closures(s, msg)
        self.assertEqual(rows[0]['tid'], first)
        self.assertEqual(rows[0]['why'], 'the same run or record (4400917)')

    def test_no_shared_id_changes_nothing(self):
        self.assertEqual(context.ids_of('a run at 2026-10-14 16:18:39, 7 failures, code 401'), set())
        self.assertEqual(context.ids_of('runId 1001769 and ticket #3856864'), {'1001769', '3856864'})
