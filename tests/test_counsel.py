"""The dossier (counsel.py): what the hub already knows about a sender and a topic, read by the reply
drafter, the assistant's post and the coder's context file. These cover the dossier, the invite road
through ingest (an invite files as fyi, no model asked) and the responder's history block - all offline.
"""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import counsel, ingest, responder
from taskuary.store import MemoryStore

ME, DANA, LEE = 'owner@ours.com', 'dana@vendor.com', 'lee@ours.com'
def _ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def _store():
    s = MemoryStore()
    s.set_setting('calendar_enabled', '0', 't')           # no Graph in tests
    s.set_setting('coder_auto_enabled', '0', 't')
    return s


def _mail(s, frm, subject, body, days=3, conv=None, status='filed', tid=None, name=None):
    return s.add_message({'TaskId': tid, 'ExternalId': f'x:{frm}:{subject}:{days}', 'ConversationId': conv, 'Channel': 'email',
                          'SourceName': ME, 'Subject': subject, 'FromName': name or frm.split('@')[0].title(), 'FromEmail': frm,
                          'SentAt': _ago(days), 'BodyText': body, 'Status': status})


class InviteDetectionTests(unittest.TestCase):
    def test_graph_marks_meeting_mail_and_subjects_cover_imap(self):
        self.assertTrue(counsel.is_invite({'@odata.type': '#microsoft.graph.eventMessage', 'subject': 'Budget sync'}))
        self.assertTrue(counsel.is_invite({'meetingMessageType': 'meetingRequest', 'subject': 'x'}))
        for subj in ('Invitation: Q3 review @ Tue', 'Updated invitation: standup', 'Accepted: lunch', 'Canceled: 1:1', 'Tentative: demo'):
            self.assertTrue(counsel.is_invite({'subject': subj}), subj)
        self.assertFalse(counsel.is_invite({'subject': 'Re: invoice 4471', 'body': {'content': 'see attached'}}))
        self.assertFalse(counsel.is_invite({'Subject': 'Your invitation to the vendor portal'}))     # a word, not a prefix


class DossierTests(unittest.TestCase):
    def test_reads_sender_history_own_replies_topic_and_open_tasks(self):
        s = _store()
        _mail(s, DANA, 'Q3 ledger reconciliation', 'Attaching the reconciled ledger for Q3.', days=6, conv='c1')
        s.add_message({'TaskId': None, 'ExternalId': 'mine1', 'ConversationId': 'c1', 'Channel': 'email', 'SourceName': ME, 'Subject': 'Re: Q3 ledger reconciliation',
                       'FromName': 'You', 'FromEmail': ME, 'SentAt': _ago(5), 'BodyText': 'Thanks Dana - I will review by Friday.', 'Status': 'context'})
        _mail(s, LEE, 'ledger reconciliation - questions', 'Lee here, two open items on the ledger.', days=2, conv='c9')
        _mail(s, 'noise@else.com', 'Weekly newsletter', 'Unrelated.', days=1)
        tid = s.create_task({'Title': 'Review Q3 ledger reconciliation figures', 'Kind': 'general', 'Status': 'open'}, 't')
        new = _mail(s, DANA, 'Re: Q3 ledger reconciliation', 'Any word on the review?', days=0, conv='c1')
        d = counsel.dossier(s, {'from_email': DANA, 'from_name': 'Dana', 'subject': 'Re: Q3 ledger reconciliation', 'conversation_id': 'c1'}, exclude_mid=new)
        self.assertIn('FROM THIS SENDER', d); self.assertIn('Attaching the reconciled ledger', d)
        self.assertIn('WHAT YOU LAST WROTE TO THEM', d); self.assertIn('review by Friday', d)
        self.assertIn('SAME TOPIC ELSEWHERE', d); self.assertIn('two open items', d)
        self.assertNotIn('newsletter', d.lower())                                             # one shared word is not a topic
        self.assertIn('OPEN TASKS THAT TOUCH IT', d); self.assertIn(f'TQ-{tid:04d}', d)
        self.assertNotIn('Any word on the review', d)                                          # the message itself is not its own history

    def test_skip_conv_leaves_the_thread_to_the_responder(self):
        s = _store()
        _mail(s, DANA, 'Q3 ledger reconciliation', 'Attaching the ledger.', days=6, conv='c1')
        _mail(s, DANA, 'Vendor portal access', 'Can someone reset my portal login?', days=4, conv='c2')
        d = counsel.dossier(s, {'from_email': DANA, 'subject': 'Re: Q3 ledger reconciliation', 'conversation_id': 'c1'}, skip_conv=True)
        self.assertNotIn('Attaching the ledger', d); self.assertIn('portal login', d)

    def test_nothing_known_is_an_empty_string(self):
        self.assertEqual(counsel.dossier(_store(), {'from_email': 'new@nowhere.com', 'subject': 'Hello'}), '')


class IngestRoadTests(unittest.TestCase):
    def test_an_invite_files_as_fyi_without_asking_the_model(self):
        s = _store()
        calls = []
        def llm(system, user, **k): calls.append(1); return '{"intent": "task", "kind": "coding", "why": "x"}'
        out = ingest.ingest_message(s, {'external_id': 'g:1', 'channel': 'email', 'subject': 'Invitation: Budget sync @ Mon 10am', 'body': 'Teams link',
                                    'from_email': LEE, 'from_name': 'Lee', 'source_name': ME, 'sent_at': _ago(), 'invite': True}, llm=llm)
        self.assertEqual(out['status'], 'filed'); self.assertEqual(calls, [])                 # no verdict to ask for
        self.assertIn('calendar invite', s.feed(limit=3)[0]['RouteReason'])

class ResponderHistoryTests(unittest.TestCase):
    def test_a_reply_draft_knows_what_the_sender_asked_last_week(self):
        s = _store()
        s.save_doc('soul', 'You work for **Uri Nussbaum** (owner@ours.com).', 't')
        _mail(s, DANA, 'Vendor portal access', 'Can someone reset my portal login?', days=6, conv='c2')
        tid = s.create_task({'Title': 'Ledger question', 'Kind': 'reply', 'Status': 'open'}, 't')
        _mail(s, DANA, 'Q3 ledger', 'When can you sign the ledger?', days=0, conv='c1', tid=tid, status='routed')
        seen = {}
        def llm(system, user, max_tokens=None, **k): seen['system'] = system; return 'Friday works - I will send it then.'
        responder.draft_reply(s, tid, llm=llm)
        self.assertIn('WHAT YOU ALREADY KNOW', seen['system']); self.assertIn('portal login', seen['system'])
        self.assertNotIn('When can you sign the ledger', seen['system'].split('WHAT YOU ALREADY KNOW')[1])   # the thread itself is not repeated as history


if __name__ == '__main__': unittest.main()
