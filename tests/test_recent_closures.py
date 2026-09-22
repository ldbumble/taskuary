"""What was already answered reaches the judge that decides whether to answer it again.

A scheduled check reported the same two Pex export failures every run. Yesterday's agent found the
cause (two facilities divested, PEX closed their accounts, nothing to fix) and the task closed. The
next run opened a fresh coding task and started a fresh agent - which read that determination in its
own context file and reported that the previous day had already handled it (TQ-0668 -> TQ-0672,
2026-09-22). The block existed; only the coder was ever shown it. Now the judge is shown it first.
"""
import json, unittest
from datetime import datetime, timedelta

from taskuary import context, ingest, triage
from taskuary.store import MemoryStore


def ago(days, hours=0):
    return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


DETERMINATION = ('CODER REPORT\nDetermination: The export failures are PEX-side business closures for divested '
                 'facilities Westport (66) and Hopewell (67), not token expiry. No code fix was needed.')


def _closed_task(s, title, when, conv=None, sender=None, status='done', report=DETERMINATION):
    tid = s.create_task({'Title': title, 'Summary': 'the ask', 'Kind': 'coding'}, 'router')
    if conv or sender:
        s.add_message({'ExternalId': f'x{tid}', 'Channel': 'report', 'ConversationId': conv,
                       'FromEmail': sender, 'Subject': title, 'SentAt': when, 'TaskId': tid, 'BodyText': 'b'})
    if report: s.add_comment(tid, 'coder', 'agent', report)
    s.update_task(tid, {'Status': status}, 'owner')
    s.cx.execute('UPDATE task SET ClosedAt=? WHERE TaskId=?', (when, tid))
    return tid


class RecentClosureTests(unittest.TestCase):
    def test_a_closure_on_this_thread_arrives_with_what_it_found(self):
        s = MemoryStore()
        tid = _closed_task(s, 'Pex exports failing for two facilities', ago(0, 8), conv='report:4')
        [hit] = context.recent_closures(s, {'conversation_id': 'report:4', 'subject': 'Process Error Check - 2 rows'})
        self.assertEqual(hit['ref'], f'TQ-{tid:04d}')
        self.assertEqual((hit['why'], hit['how']), ('the same thread', 'done'))
        self.assertIn('divested', hit['ended'])
        self.assertNotIn('CODER REPORT', hit['ended'], 'the label is not the finding')

    def test_the_window_closes(self):
        s = MemoryStore()
        _closed_task(s, 'Pex exports failing for two facilities', ago(40), conv='report:4')
        self.assertEqual(context.recent_closures(s, {'conversation_id': 'report:4', 'subject': 'x'}), [])

    def test_an_open_task_is_not_a_closure(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Pex exports failing', 'Kind': 'coding'}, 'router')
        s.add_message({'ExternalId': 'o1', 'Channel': 'report', 'ConversationId': 'report:4', 'TaskId': tid,
                       'Subject': 'Pex exports failing', 'SentAt': ago(0, 2), 'BodyText': 'b'})
        self.assertEqual(context.recent_closures(s, {'conversation_id': 'report:4', 'subject': 'x'}), [])

    def test_a_dropped_task_counts_and_says_it_was_dropped(self):
        """"We looked and it was nothing" is evidence too - and it is not the same as "done"."""
        s = MemoryStore()
        _closed_task(s, 'Pex exports failing', ago(1), conv='report:4', status='dropped', report='')
        [hit] = context.recent_closures(s, {'conversation_id': 'report:4', 'subject': 'x'})
        self.assertEqual(hit['how'], 'dropped')
        self.assertIn('the ask', hit['ended'], 'with no agent report, the ask it was closed on')

    def test_the_thread_outranks_the_subject_and_the_sender_and_the_list_is_capped(self):
        s = MemoryStore()
        for i in range(3): _closed_task(s, f'Pex export failures {i}', ago(2), sender='ops@x.com')
        _closed_task(s, 'Pex exports failing for two facilities', ago(3))
        want = _closed_task(s, 'Nothing alike at all', ago(4), conv='report:4')
        hits = context.recent_closures(s, {'conversation_id': 'report:4', 'subject': 'Pex export failures 1',
                                           'from_email': 'ops@x.com'})
        self.assertEqual(len(hits), context.RECENT)
        self.assertEqual(hits[0]['ref'], f'TQ-{want:04d}')
        self.assertEqual(hits[0]['why'], 'the same thread')

    def test_one_shared_word_is_not_a_match(self):
        s = MemoryStore()
        _closed_task(s, 'Invoice approval for the Roanoke lease', ago(1))
        self.assertEqual(context.recent_closures(s, {'subject': 'Roanoke plumbing quote'}), [])


class JudgeSeesItTests(unittest.TestCase):
    def test_the_arrival_carries_the_closure_and_the_field_is_explained(self):
        s = MemoryStore()
        _closed_task(s, 'Pex exports failing for two facilities', ago(0, 8), conv='report:4')
        seen = {}
        def llm(sys_, usr_, **k):
            seen['sys'], seen['usr'] = sys_, json.loads(usr_)
            return '{"intent": "fyi", "why": "TQ-0001 already answered this", "title": "t", "summary": "s"}'
        s.save_doc('triage', 'Judge it. Answer intent and why.', 'owner')      # a document that names no signals
        ingest.ingest_message(s, {'external_id': 'r1', 'channel': 'report', 'source_name': 'Process Error Check',
                                  'conversation_id': 'report:4', 'subject': 'Process Error Check - 2 rows',
                                  'sent_at': ago(0), 'body': 'Pex User Export failed: 67 and 66 - 403 Business is not open'},
                              llm=llm)
        closed = seen['usr'].get('recently_closed')
        self.assertTrue(closed, 'the judge was handed what was already answered')
        self.assertIn('divested', closed[0]['ended'])
        self.assertIn('recently_closed is work on this thread', seen['sys'],
                      'a document that never names the field still gets it explained (triage.FIELDS)')

    def test_the_shipped_instructions_name_it_themselves(self):
        self.assertIn('recently_closed', triage.INTENT_SYSTEM)


if __name__ == '__main__':
    unittest.main()
