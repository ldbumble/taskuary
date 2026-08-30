"""The assistant's private brief (counsel.py): an info mail or an invite used to be filed and
forgotten, and a reply was drafted with no memory of what the same person asked last week.
These cover the dossier (what the hub already knows), the brief itself, the invite road through
ingest, the notify ping, the feed column and the responder's history block - all offline.
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


class BriefTests(unittest.TestCase):
    def test_brief_is_written_from_counsel_doc_and_stored_as_json(self):
        s = _store()
        s.set_setting('owner_name', 'Uri Nussbaum', 't')
        mid = _mail(s, DANA, 'Q3 ledger reconciliation', 'Ledger attached; auditors want sign-off by the 15th.', days=0)
        seen = {}
        def llm(system, user, max_tokens=None, **k):
            seen.update(system=system, user=user, max_tokens=max_tokens)
            return ('```json\n{"read": "Dana needs your sign-off; I would clear it this week.", "do": "Reply with a date.", '
                    '"ahead": ["Auditor deadline on the 15th"], "prep": [], "suggest": {"title": "Sign off Q3 ledger before the 15th", "why": "auditors are waiting"}, "nothing": false}\n```')
        b = counsel.brief(s, counsel.msg_of(s.get_message(mid)), mid, 'fyi', llm=llm)
        self.assertIn("I have Uri's back", seen['system'])                    # COUNSEL.md, owner tokens filled
        self.assertIn('Answer JSON only', seen['system']); self.assertNotIn('<!--', seen['system'])
        self.assertIn('nothing on file about this sender', seen['user'])      # thin history is said, not hidden
        self.assertEqual(b['suggest']['title'], 'Sign off Q3 ledger before the 15th'); self.assertFalse(b['history'])
        stored = json.loads(s.get_message(mid)['Brief'])
        self.assertEqual(stored['read'], b['read']); self.assertEqual(stored['ahead'], ['Auditor deadline on the 15th'])
        self.assertIn('Sign off Q3 ledger', counsel.render(b)); self.assertIn('⏳ Auditor deadline', counsel.render(b))
        self.assertIn('Brief', s.feed(limit=5)[0])                            # the panel gets it with the row

    def test_an_unreadable_answer_stores_nothing(self):
        s = _store()
        mid = _mail(s, DANA, 'hi', 'hello', days=0)
        self.assertIsNone(counsel.brief(s, counsel.msg_of(s.get_message(mid)), mid, 'fyi', llm=lambda *a, **k: 'Sure! Here is my read: ...'))
        self.assertIsNone(counsel.brief(s, counsel.msg_of(s.get_message(mid)), mid, 'fyi', llm=lambda *a, **k: '{"do": "x"}'))   # no read = no brief
        self.assertIsNone(s.get_message(mid)['Brief'])
        self.assertIsNone(counsel.parse('{"read": "ok", "suggest": {"why": "no title"}, "ahead": "not a list"}')['suggest'])

    def test_invite_asks_for_a_prep_note(self):
        s = _store()
        mid = _mail(s, LEE, 'Invitation: Vendor review @ Thu 2pm', 'Agenda: Q3 ledger', days=0)
        seen = {}
        def llm(system, user, **k): seen['system'] = system; return '{"read": "Lee wants the ledger settled.", "prep": ["Dana still owes the reconciliation"], "nothing": false}'
        b = counsel.brief(s, counsel.msg_of(s.get_message(mid)), mid, 'fyi', llm=llm, invite=True)
        self.assertIn('CALENDAR INVITE', seen['system']); self.assertEqual(b['prep'], ['Dana still owes the reconciliation'])


class IngestRoadTests(unittest.TestCase):
    def test_an_invite_files_as_fyi_without_asking_the_model(self):
        s = _store()
        calls = []
        def llm(system, user, **k): calls.append(1); return '{"intent": "task", "kind": "coding", "why": "x"}'
        with mock.patch.object(counsel, 'later') as spawn:
            out = ingest.ingest_message(s, {'external_id': 'g:1', 'channel': 'email', 'subject': 'Invitation: Budget sync @ Mon 10am', 'body': 'Teams link',
                                            'from_email': LEE, 'from_name': 'Lee', 'source_name': ME, 'sent_at': _ago(), 'invite': True}, llm=llm)
        self.assertEqual(out['status'], 'filed'); self.assertEqual(calls, [])                 # no verdict to ask for
        self.assertIn('calendar invite', s.feed(limit=3)[0]['RouteReason'])
        fn, *args = spawn.call_args[0]
        self.assertIs(fn, counsel.after_triage); self.assertTrue(args[-1])                    # the prep note is on its way, in invite mode

    def test_a_model_judged_fyi_gets_a_brief_and_keyword_noise_does_not(self):
        s = _store()
        llm = lambda system, user, **k: '{"intent": "fyi", "why": "a status note"}'
        with mock.patch.object(counsel, 'later') as spawn:
            ingest.ingest_message(s, {'external_id': 'g:2', 'channel': 'email', 'subject': 'Ledger status', 'body': 'Reconciliation is done; auditors sign next week.',
                                      'from_email': DANA, 'source_name': ME, 'sent_at': _ago()}, llm=llm)
            self.assertEqual(spawn.call_args[0][0], counsel.after_triage)
            spawn.reset_mock()
            ingest.ingest_message(s, {'external_id': 'g:3', 'channel': 'email', 'subject': 'Nightly report', 'body': 'This is an automated message. Do not reply.',
                                      'from_email': 'noreply@robot.com', 'source_name': ME, 'sent_at': _ago()}, llm=llm)
            self.assertFalse(spawn.called)                                                     # the keyword pass filed it: not worth a call

    def test_after_triage_pings_only_when_there_is_something_to_get_ahead_of(self):
        s = _store()
        mid = _mail(s, DANA, 'Ledger status', 'Auditors sign on the 15th.', days=0)
        msg = counsel.msg_of(s.get_message(mid))
        quiet = lambda *a, **k: '{"read": "Routine status.", "nothing": false}'
        loud = lambda *a, **k: '{"read": "The 15th is a hard date.", "do": "Book the sign-off.", "ahead": ["Auditor deadline 15th"], "nothing": false}'
        with mock.patch('taskuary.outbound.notify') as ping:
            counsel.after_triage(s, msg, mid, None, 'fyi', llm=quiet); self.assertFalse(ping.called)
            counsel.after_triage(s, msg, mid, None, 'fyi', llm=loud)
            self.assertTrue(ping.called); self.assertIn('Heads-up', ping.call_args[0][1]); self.assertIn('Auditor deadline', ping.call_args[0][1])
            s.set_setting('counsel_enabled', '0', 't'); ping.reset_mock(); s.set_brief(mid, None)
            counsel.after_triage(s, msg, mid, None, 'fyi', llm=loud)
            self.assertFalse(ping.called); self.assertIsNone(s.get_message(mid)['Brief'])      # the switch is a switch

    def test_a_brief_on_a_task_lands_on_the_task_too(self):
        s = _store()
        tid = s.create_task({'Title': 'Ledger', 'Kind': 'reply', 'Status': 'open'}, 't')
        mid = _mail(s, DANA, 'Ledger', 'When can you sign?', days=0, tid=tid, status='routed')
        counsel.after_triage(s, counsel.msg_of(s.get_message(mid)), mid, tid, 'reply_only',
                             llm=lambda *a, **k: '{"read": "She has asked twice; answer with a date.", "nothing": false}')
        self.assertTrue(any(c['Body'].startswith('ASSISTANT BRIEF') for c in s.list_comments(tid)))


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
