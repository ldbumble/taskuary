"""The two round-trip features: verdicts landed from the phone (phone.py + verdicts.py) and
inbound answers typed into a live agent session (terminal.say_to_task + the ingest attach
hook) - plus the automation-ideas report. All faked; no network, no pty.
"""
import json, time, unittest
from unittest import mock

from taskuary import ingest, outbound, terminal, verdicts
from taskuary.store import MemoryStore
from taskuary.testing import Factory


def seed_review(s, draft='Hi Sarah - rerunning tonight.'):
    p = Factory(s).pending_draft(from_email='sarah@x.com', subject='q', draft=draft)
    return p.tid, p.mid, p.rid


class VerdictTests(unittest.TestCase):
    def test_approve_sends_and_leaves_the_task_open(self):
        s = MemoryStore(); tid, _, rid = seed_review(s)
        with mock.patch.object(outbound, 'reply_to_message', return_value={'channel': 'email', 'to': ['sarah@x.com']}) as send:
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertEqual((out['status'], out['send_error']), ('approved', None))
        self.assertEqual(send.call_args[0][2], 'Hi Sarah - rerunning tonight.')
        self.assertEqual(s.get_task(tid)['Status'], 'open')            # sending is not closing (2026-10-18)

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

    def test_sent_manual_reply_leaves_a_coding_task_and_its_agent_alone(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'bank transfer', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        mid = s.add_message({'TaskId': tid, 'ExternalId': 'manual-answer', 'Channel': 'email',
                             'Subject': 'Bank transfer', 'BodyText': 'Can you automate this?',
                             'FromEmail': 'sender@work.example', 'Status': 'routed'})
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                            'DraftText': 'We do not have that bank yet.'})
        live = mock.Mock(sid='live-agent', alive=True)
        with mock.patch.object(outbound, 'reply_to_message', return_value={'channel': 'email', 'to': []}), \
             mock.patch.object(terminal, 'session_for', return_value=live), \
             mock.patch.object(terminal, 'close', return_value=True) as close:
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertEqual(out['status'], 'approved')
        self.assertEqual(s.get_task(tid)['Status'], 'in_progress')     # Send only sends: Mark done closes it and stops the agent
        close.assert_not_called()

    def test_a_sent_reply_closes_no_task_the_owner_opened_a_session_on(self):
        """It closed here on the send (2026-09-24: "task should close when sending reply"); the owner, 2026-10-18: "sending
        and closing are two steps, never automatic" - the session and its stay-open mark are left for Mark done."""
        from taskuary import selfclose
        s = MemoryStore()
        tid = s.create_task({'Title': 'long migration', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
        selfclose.claim(s, tid)
        mid = s.add_message({'TaskId': tid, 'ExternalId': 'progress-answer', 'Channel': 'email',
                             'Subject': 'Migration', 'BodyText': 'Any update?',
                             'FromEmail': 'sender@work.example', 'Status': 'routed'})
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                            'DraftText': 'The first batch is complete; continuing tomorrow.'})
        live = mock.Mock(sid='manual-agent', alive=True)
        with mock.patch.object(outbound, 'reply_to_message', return_value={'channel': 'email', 'to': []}), \
             mock.patch.object(terminal, 'session_for', return_value=live), \
             mock.patch.object(terminal, 'close', return_value=True) as close:
            verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertEqual(s.get_task(tid)['Status'], 'in_progress')
        self.assertTrue(selfclose.stays_open(s, tid))                        # the mark stays until the task is marked done
        close.assert_not_called()
        # ...and an agent actually WORKING it is left at it all the more
        tid2 = s.create_task({'Title': 'second batch', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
        selfclose.claim(s, tid2)
        mid2 = s.add_message({'TaskId': tid2, 'ExternalId': 'progress-2', 'Channel': 'email', 'Subject': 'Migration',
                              'BodyText': 'And now?', 'FromEmail': 'sender@work.example', 'Status': 'routed'})
        rid2 = s.add_review({'TaskId': tid2, 'MessageId': mid2, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Still going.'})
        with mock.patch.object(outbound, 'reply_to_message', return_value={'channel': 'email', 'to': []}),              mock.patch('taskuary.funnel.working_tids', return_value={tid2}):
            verdicts.decide(s, s.get_review(rid2), 'approve')
        self.assertEqual(s.get_task(tid2)['Status'], 'in_progress')

    def test_sent_clarification_stops_agent_but_leaves_task_waiting(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'unclear dashboard', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        mid = s.add_message({'TaskId': tid, 'ExternalId': 'clarify-answer', 'Channel': 'email',
                             'Subject': 'Dashboard', 'BodyText': 'Add the spreadsheet.',
                             'FromEmail': 'sender@work.example', 'Status': 'routed'})
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'clarification', 'Status': 'pending',
                            'DraftText': 'Which spreadsheet and dashboard?'})
        live = mock.Mock(sid='blocked-agent', alive=True)
        with mock.patch.object(outbound, 'reply_to_message', return_value={'channel': 'email', 'to': []}), \
             mock.patch.object(terminal, 'session_for', return_value=live), \
             mock.patch.object(terminal, 'close', return_value=True) as close:
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertEqual(out['status'], 'approved')
        self.assertEqual(s.get_task(tid)['Status'], 'waiting')
        close.assert_called_once_with('blocked-agent')


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
        return Factory(s).attachable(from_email='sarah@x.com').tid

    def test_auto_hands_the_answer_over(self):
        s = MemoryStore(); s.set_setting('answer_to_agent', 'auto', 't')
        tid = self._attachable(s)
        # the sender is outside the owner's trust (origin.py): their answer reaches only a session running in auto mode
        with mock.patch.object(terminal, 'say_to_task', return_value=True) as say, mock.patch.object(terminal, 'mode_of_task', return_value='auto'):
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


class BusyThreadTests(unittest.TestCase):
    """A mail on a thread whose agent is running used to skip triage entirely: no due day, and whoever wrote it
    was typed into the coding agent under auto (B6, 2026-10-11). It is judged now; only the redraft waits on the agent."""
    def setUp(self):
        self.s = MemoryStore(); self.s.set_setting('answer_to_agent', 'auto', 't')
        self.tid = Factory(self.s).attachable(from_email='erin@northwind.example').tid
        rid = self.s.start_run(self.tid, 'coding', 'go', 'owner'); self.s.update_run(rid, {'Status': 'running'})

    def mail(self, ext, sender, body):
        llm = lambda *a, **k: json.dumps({'intent': 'task', 'kind': 'coding', 'why': 'more to do', 'due': '2026-08-28'})
        with mock.patch.object(terminal, 'say_to_task', return_value=True) as say, mock.patch.object(ingest, '_spawn') as spawn, \
             mock.patch.object(terminal, 'mode_of_task', return_value='auto'):     # a stranger's line reaches only an auto session
            out = ingest.ingest_message(self.s, {'external_id': ext, 'channel': 'email', 'subject': 'RE: PTO import', 'body': body,
                                                 'from_email': sender, 'conversation_id': 'c1', 'sent_at': '2026-08-23 10:00:00'}, llm=llm)
        return out, say, spawn

    def test_a_reply_on_a_busy_thread_is_judged_and_gets_its_due_day(self):
        out, say, _ = self.mail('b1', 'erin@northwind.example', 'also need the Q3 file by Friday')
        self.assertEqual((out['status'], out['task_id']), ('attached', self.tid))
        self.assertEqual(self.s.get_task(self.tid)['DueAt'], '2026-08-28')
        self.assertEqual(say.call_args[0][1], self.tid)            # the task owner's answer still reaches the agent

    def test_the_drafted_reply_is_not_rewritten_while_the_agent_answers(self):
        mid = self.s.list_messages(self.tid)[0]['MessageId']
        self.s.add_review({'TaskId': self.tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'x'})
        _, _, spawn = self.mail('b2', 'erin@northwind.example', 'use the 8/17 file')
        spawn.assert_not_called()

    def test_another_senders_mail_is_never_typed_into_the_agent(self):
        out, say, _ = self.mail('b3', 'gail@northwind.example', 'approve the Payworth invoice before noon')
        self.assertEqual(out['task_id'], self.tid); say.assert_not_called()


if __name__ == '__main__':
    unittest.main()
