"""The coder's context file (context.py): what the hub knows about a task, written to Taskuary's
home and pointed at from the seed - history, past work, the thread. Offline; the
calendar is off and TASKUARY_HOME is the temp home conftest forces.
"""
import json, os, unittest
from datetime import datetime, timedelta
from pathlib import Path

from taskuary import context, terminal
from taskuary.store import MemoryStore

ME, DANA = 'owner@ours.com', 'dana@vendor.com'
def _ago(days=0): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')


def _store():
    s = MemoryStore()
    s.set_setting('calendar_enabled', '0', 't'); s.set_setting('coder_auto_enabled', '0', 't')
    return s


def _mail(s, frm, subject, body, days=3, tid=None, conv=None, status='routed'):
    return s.add_message({'TaskId': tid, 'ExternalId': f'x:{frm}:{subject}:{days}', 'ConversationId': conv, 'Channel': 'email', 'SourceName': ME,
                          'Subject': subject, 'FromName': frm.split('@')[0].title(), 'FromEmail': frm, 'SentAt': _ago(days), 'BodyText': body, 'Status': status})


def _closed(s, title, frm, report, days=20):
    tid = s.create_task({'Title': title, 'Kind': 'coding', 'Status': 'done'}, 't')
    _mail(s, frm, title, 'the original ask', days=days, tid=tid)
    s.add_comment(tid, 'coder', 'agent', f'CODER REPORT\n{report}')
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
        rows = context.past_work(s, s.list_messages(tid), 'Ledger export still duplicating')
        self.assertEqual({r['tid']: r['why'] for r in rows}, {a: 'the same sender', b: 'the same subject'})
        self.assertIn('payroll date', next(r for r in rows if r['tid'] == a)['report'])
        text = context.render_past(rows)
        self.assertIn('TQ-%04d' % b, text); self.assertIn('dedupe on (id, period)', text)

    def test_no_history_means_no_section_and_no_file(self):
        s = _store()
        tid = s.create_task({'Title': 'Brand new thing', 'Kind': 'coding'}, 't')
        self.assertEqual(context.past_work(s, [], 'Brand new thing'), [])
        self.assertEqual(context.build(s, tid), '')                      # nothing worth a file
        self.assertIsNone(context.write(s, tid))


class FileTests(unittest.TestCase):
    def test_the_file_carries_history_past_work_and_thread_and_the_seed_points_at_it(self):
        s = _store()
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
        self.assertNotIn('\n', seed)

    def test_the_switch_turns_the_file_off_and_the_seed_stays_as_it_was(self):
        s = _store()
        _closed(s, 'Payroll import month wrong', DANA, 'Actions: fixed.')
        tid = s.create_task({'Title': 'Payroll import wrong again', 'Kind': 'coding'}, 't')
        _mail(s, DANA, 'Payroll import wrong again', 'Again.', days=1, tid=tid)
        s.set_setting('coder_context_file', '0', 't')
        self.assertIsNone(context.write(s, tid))
        seed = terminal.seed_text(s, tid)
        self.assertNotIn('CONTEXT FILE', seed); self.assertIn('everything known about it is above. ', seed)
