"""The two round-trip features: verdicts landed from the phone (phone.py + verdicts.py) and
inbound answers typed into a live agent session (terminal.say_to_task + the ingest attach
hook) - plus the automation-ideas report. All faked; no network, no pty.
"""
import json, time, unittest
from unittest import mock

from taskuary import ingest, outbound, phone, terminal, verdicts
from taskuary.store import MemoryStore


def seed_review(s, draft='Hi Sarah - rerunning tonight.'):
    tid = s.create_task({'Title': 't', 'Kind': 'reply', 'Status': 'open'}, 't')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'x1', 'Channel': 'email', 'Subject': 'q',
                         'FromEmail': 'sarah@x.com', 'SentAt': '2026-08-23 10:00:00', 'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': draft})
    return tid, mid, rid


class VerdictTests(unittest.TestCase):
    def test_approve_sends_and_closes(self):
        s = MemoryStore(); tid, _, rid = seed_review(s)
        with mock.patch.object(outbound, 'reply_to_message', return_value={'channel': 'email', 'to': ['sarah@x.com']}) as send:
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertEqual((out['status'], out['send_error']), ('approved', None))
        self.assertEqual(send.call_args[0][2], 'Hi Sarah - rerunning tonight.')
        self.assertEqual(s.get_task(tid)['Status'], 'done')

    def test_edited_text_wins_and_teaches(self):
        s = MemoryStore(); _, _, rid = seed_review(s)
        lessons = []
        with mock.patch.object(outbound, 'reply_to_message', return_value={'channel': 'email', 'to': []}):
            out = verdicts.decide(s, s.get_review(rid), 'approve', 'Different words.',
                                  learn_async=lambda fn, *a: lessons.append(a))
        self.assertEqual(out['status'], 'edited')
        self.assertIn('SENT INSTEAD', lessons[0][1])

    def test_failed_send_returns_to_queue(self):
        s = MemoryStore(); tid, _, rid = seed_review(s)
        with mock.patch.object(outbound, 'reply_to_message', side_effect=RuntimeError('smtp down')):
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertEqual(out['status'], 'pending'); self.assertIn('smtp down', out['send_error'])
        self.assertEqual(s.get_review(rid)['Status'], 'pending')      # back in the queue
        self.assertNotEqual(s.get_task(tid)['Status'], 'done')


def arm_phone(s):
    s.set_setting('phone_approvals', '1', 't')
    cid = s.get_connector_by_type('telegram')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1,
                      'ConfigJson': json.dumps({'notify_chat': '777'})}, 't')


class PhoneTests(unittest.TestCase):
    def test_approve_by_reply(self):
        s = MemoryStore(); arm_phone(s)
        _, _, rid = seed_review(s)
        self.assertIn(f'[rv{rid}]', phone.ping_tail(s, rid, 'the draft'))    # ping carries the tag + draft
        acks = []
        with mock.patch.object(outbound, 'reply_to_message', return_value={'channel': 'email', 'to': ['sarah@x.com']}), \
             mock.patch('taskuary.messengers.tg_send', side_effect=lambda st, chat, text: acks.append(text)):
            self.assertTrue(phone.intercept(s, 'telegram', '777', 'approve'))
        self.assertEqual(s.get_review(rid)['Status'], 'approved')
        self.assertIn('sent by email', acks[0])

    def test_own_text_becomes_the_reply(self):
        s = MemoryStore(); arm_phone(s)
        _, _, rid = seed_review(s)
        phone.ping_tail(s, rid)
        sent = {}
        with mock.patch.object(outbound, 'reply_to_message', side_effect=lambda st, m, t: sent.update(t=t) or {'channel': 'email', 'to': []}), \
             mock.patch('taskuary.messengers.tg_send'):
            self.assertTrue(phone.intercept(s, 'telegram', '777', 'Tell her Thursday works.'))
        self.assertEqual(sent['t'], 'Tell her Thursday works.')
        self.assertEqual(s.get_review(rid)['Status'], 'edited')

    def test_wrong_chat_and_off_flow_to_triage(self):
        s = MemoryStore(); arm_phone(s)
        _, _, rid = seed_review(s); phone.ping_tail(s, rid)
        self.assertFalse(phone.intercept(s, 'telegram', '999', 'approve'))   # not the notify chat
        s.set_setting('phone_approvals', '0', 't')
        self.assertFalse(phone.intercept(s, 'telegram', '777', 'approve'))   # feature off

    def test_own_ping_echo_is_swallowed(self):
        s = MemoryStore(); arm_phone(s)
        _, _, rid = seed_review(s)
        ping = 'TQ-0001 is done.' + phone.ping_tail(s, rid, 'the draft')
        with mock.patch('taskuary.messengers.tg_send'):
            self.assertTrue(phone.intercept(s, 'telegram', '777', ping))     # swallowed, no verdict
        self.assertEqual(s.get_review(rid)['Status'], 'pending')

    def test_no_draft_yet(self):
        s = MemoryStore(); arm_phone(s)
        _, _, rid = seed_review(s, draft='')
        phone.ping_tail(s, rid)
        acks = []
        with mock.patch('taskuary.messengers.tg_send', side_effect=lambda st, chat, text: acks.append(text)):
            self.assertTrue(phone.intercept(s, 'telegram', '777', 'approve'))
        self.assertEqual(s.get_review(rid)['Status'], 'pending')
        self.assertIn('no draft yet', acks[0])

    def test_quoted_task_ping_routes_answer_to_that_live_agent(self):
        s = MemoryStore(); arm_phone(s)
        tid = s.create_task({'Title': 'choose a repo', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        fake = FakeSession(tid); acks = []
        quoted = f'{tid} is waiting.' + phone.task_ping_tail(s, tid)
        with mock.patch.dict(terminal.SESSIONS, {'sid1': fake}, clear=True), \
             mock.patch('taskuary.messengers.tg_send', side_effect=lambda st, chat, text: acks.append(text)):
            self.assertTrue(phone.intercept(s, 'telegram', '777', 'Yes, use taskhub.', quoted))
            time.sleep(0.4)
        self.assertIn('Yes, use taskhub.', ''.join(fake.writes))
        self.assertIn('sent to the live agent', acks[0])

    def test_task_tag_wins_over_a_bare_review_approve(self):
        s = MemoryStore(); arm_phone(s)
        _, _, rid = seed_review(s); phone.ping_tail(s, rid)
        tid = s.create_task({'Title': 'permission', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        fake = FakeSession(tid)
        with mock.patch.dict(terminal.SESSIONS, {'sid1': fake}, clear=True), \
             mock.patch('taskuary.messengers.tg_send'):
            self.assertTrue(phone.intercept(s, 'telegram', '777', 'approve', phone.task_ping_tail(s, tid)))
            time.sleep(0.4)
        self.assertEqual(s.get_review(rid)['Status'], 'pending')
        self.assertIn('approve', ''.join(fake.writes))

    def test_stale_task_ping_is_acknowledged_without_becoming_work(self):
        s = MemoryStore(); arm_phone(s)
        tid = s.create_task({'Title': 'old question', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        acks = []
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch('taskuary.messengers.tg_send', side_effect=lambda st, chat, text: acks.append(text)):
            self.assertTrue(phone.intercept(s, 'telegram', '777', f'[tq{tid:04d}] yes'))
        self.assertIn('no live agent', acks[0])


class FakeSession:
    def __init__(self, task_id): self.task_id, self.alive, self.n, self.writes = task_id, True, 0, []
    def write(self, x): self.writes.append(x); self.n += 1


class SayToTaskTests(unittest.TestCase):
    def test_types_into_the_live_session(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 't', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        fake = FakeSession(tid)
        with mock.patch.dict(terminal.SESSIONS, {'sid1': fake}, clear=True):
            ok = terminal.say_to_task(s, tid, {'FromName': 'Sarah', 'Channel': 'email',
                                               'BodyText': 'Use the 8/17 file, not 8/16.'})
            self.assertTrue(ok)
            time.sleep(0.4)
        typed = ''.join(w for w in fake.writes if w not in ('\r', '\n'))
        self.assertIn('Sarah answered', typed); self.assertIn('8/17 file', typed)
        self.assertTrue(any('typed into the live session' in c['Body'] for c in s.list_comments(tid)))

    def test_no_session_is_false(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 't', 'Kind': 'coding', 'Status': 'open'}, 't')
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            self.assertFalse(terminal.say_to_task(s, tid, {'BodyText': 'hi'}))


class AttachHookTests(unittest.TestCase):
    def _attachable(self, s):
        tid = s.create_task({'Title': 'PTO import', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        s.add_message({'TaskId': tid, 'ExternalId': 'orig', 'ConversationId': 'c1', 'Channel': 'email',
                       'Subject': 'PTO import', 'SentAt': '2026-08-23 09:00:00', 'Status': 'routed'})
        return tid

    def test_auto_hands_the_answer_over(self):
        s = MemoryStore(); s.set_setting('answer_to_agent', 'auto', 't')
        tid = self._attachable(s)
        with mock.patch.object(terminal, 'say_to_task', return_value=True) as say:
            out = ingest.ingest_message(s, {'external_id': 'ans1', 'channel': 'email', 'subject': 'RE: PTO import',
                                            'body': 'Use the 8/17 file.', 'from_email': 'sarah@x.com',
                                            'conversation_id': 'c1', 'sent_at': '2026-08-23 10:00:00'})
        self.assertEqual((out['status'], out['task_id']), ('attached', tid))
        self.assertEqual(say.call_args[0][1], tid)

    def test_ask_mode_stays_hands_off(self):
        s = MemoryStore()                                   # default answer_to_agent=ask
        tid = self._attachable(s)
        with mock.patch.object(terminal, 'say_to_task') as say:
            out = ingest.ingest_message(s, {'external_id': 'ans2', 'channel': 'email', 'subject': 'RE: PTO import',
                                            'body': 'Use the 8/17 file.', 'conversation_id': 'c1',
                                            'sent_at': '2026-08-23 10:00:00'})
        self.assertEqual(out['status'], 'attached'); say.assert_not_called()


if __name__ == '__main__':
    unittest.main()
