""""I wrote this a bunch and the system is not learning it."

Two reasons it could not, and both are covered here. A verdict about a KIND OF WORK had
nowhere to live - the scopes were this sender, their domain, or everybody - so "resident
refunds are not our task" got filed under whichever colleague was on screen and never fired
again on a seventeen-person thread. And ATTACHING skipped every judgement: once a task existed,
each new message on the thread joined it with no triage, no notes and no AI call, so the task
stayed 'needs you' no matter what the owner had said.
"""
import unittest
from fastapi.testclient import TestClient

from taskuary import ingest, server
from taskuary.store import MemoryStore

c = TestClient(server.app)

REFUND = 'Re: Resident Refund Request - Doe, Jane'
TOPIC = 'resident refund request - doe, jane'


def _store(*notes):
    s = MemoryStore()
    for scope, key, note, src in notes:
        s.add_memory({'Scope': scope, 'ScopeKey': key, 'Note': note, 'Source': src,
                      'Active': 1, 'CreatedBy': 'test'})
    return s


VERDICT = ('subject', TOPIC, 'Resident refunds are not our task.', 'verdict')


class TopicScopeTests(unittest.TestCase):
    def test_the_changing_part_of_a_subject_is_ignored(self):
        """Every mail in the thread names a different resident. Keying on the exact subject
        would have matched exactly one of them."""
        hit = lambda subj: ingest.topic_hit(TOPIC, subj)
        self.assertTrue(hit('RE: Resident Refund Request - PAYNE, MICHAEL'))
        self.assertTrue(hit('Resident Refund Request - Blickenstaff, D'))
        self.assertTrue(hit('Re: resident refund request'))
        self.assertFalse(hit('Vendor Create'))
        self.assertFalse(hit('Directors meeting'))
        self.assertFalse(hit(''))

    def test_a_topic_verdict_applies_to_a_sender_who_was_never_named(self):
        """THE bug: the thread has seventeen people on it, and a sender-scoped note covers one.
        The next refund mail arrives from somebody else and the verdict has nothing to say."""
        s = _store(VERDICT)
        notes = ingest.notes_for(s, {'from_email': 'someone-new@elsewhere.com',
                                     'subject': 'RE: Resident Refund Request - PAYNE, MICHAEL',
                                     'body': 'Attached is a new transaction history.'})
        self.assertEqual(notes, ['Resident refunds are not our task.'])
        # and it stays out of mail that is genuinely about something else
        self.assertEqual(ingest.notes_for(s, {'from_email': 'someone-new@elsewhere.com',
                                              'subject': 'Directors meeting', 'body': 'agenda attached'}), [])

    def test_only_the_owners_own_verdicts_can_veto(self):
        """A distilled pattern is a hint for the classifier. A refusal has to be something the
        owner actually pressed a button to say."""
        msg = {'from_email': 'x@y.com', 'subject': REFUND, 'body': 'history attached'}
        self.assertIn('not our task', ingest.veto(_store(VERDICT), msg))
        learned = ('subject', TOPIC, 'Resident refunds look like they are not ours.', 'learned')
        self.assertEqual(ingest.veto(_store(learned), msg), '')


class AttachRespectsTheVerdictTests(unittest.TestCase):
    def _thread(self, s):
        """An open task with the refund thread already on it, exactly like TQ-0046."""
        tid = s.create_task({'Title': 'Resident refund request', 'Kind': 'general', 'Source': 'email'}, 'test')
        s.add_message({'TaskId': tid, 'ExternalId': 'e0', 'ConversationId': 'thread-1', 'Channel': 'email',
                       'Subject': REFUND, 'FromEmail': 'hudson@regencyhealthrehab.com',
                       'BodyText': 'the refund paperwork', 'Status': 'routed'})
        return tid

    def _arrive(self, s, ext='e1', frm='lynch@regencyhealthrehab.com'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': frm,
                                        'subject': 'Re: Resident Refund Request - PAYNE, MICHAEL',
                                        'conversation_id': 'thread-1',
                                        'body': 'Attached is a new transaction history.'})

    def test_without_a_verdict_the_thread_still_builds_one_task(self):
        s = MemoryStore(); tid = self._thread(s)
        out = self._arrive(s)
        self.assertEqual((out['status'], out['task_id']), ('attached', tid))

    def test_a_standing_verdict_stops_the_message_joining_the_task(self):
        """This is what "not learning" looked like: a thread match is worth 1.0, it attached on
        sight, and no note was ever consulted on the way in."""
        s = _store(VERDICT); tid = self._thread(s)
        out = self._arrive(s)
        self.assertEqual((out['status'], out['task_id']), ('filed', None))
        row = next(r for r in s.feed(limit=10) if r['MessageId'] == out['message_id'])
        self.assertEqual(row['NeedsYou'], 0)                      # the point of the whole exercise
        self.assertIn('Resident refunds are not our task', row['RouteReason'])
        self.assertIn(f'TQ-{tid:04d}', row['RouteReason'])         # and which task it did not join

    def test_a_live_agent_session_still_gets_its_answer(self):
        """The agent asked a question on this thread and the reply is arriving. A standing
        verdict about the topic must not eat the answer to a question we asked."""
        s = _store(VERDICT); tid = self._thread(s)
        s.start_run(tid, 'coder', 'go', 'test')
        out = self._arrive(s)
        self.assertEqual((out['status'], out['task_id']), ('attached', tid))


class TheDialogTests(unittest.TestCase):
    """The panel offered this sender / their domain / everybody, and defaulted to the sender -
    so the failing choice was also the easy one."""
    def _msg(self, subject=REFUND, frm='dlynch1@regencyhealthrehab.com'):
        return server.store.add_message({'ExternalId': f'ui-{subject}-{frm}', 'Channel': 'email',
                                         'Subject': subject, 'FromEmail': frm,
                                         'BodyText': 'Attached is a new transaction history.',
                                         'Status': 'filed'})

    def test_the_topic_is_suggested_and_the_wording_follows_the_scope(self):
        mid = self._msg()
        d = c.get(f'/api/messages/{mid}/not-mine/suggest').json()
        self.assertEqual((d['scope'], d['topic']), ('subject', TOPIC))
        self.assertIn('Mail about', d['note'])
        # ask for a different scope and the sentence changes with it
        self.assertIn('from dlynch1@regencyhealthrehab.com',
                      c.get(f'/api/messages/{mid}/not-mine/suggest?scope=sender').json()['note'])
        self.assertEqual(c.get(f'/api/messages/{mid}/not-mine/suggest?scope=nonsense').status_code, 422)

    def test_a_subject_with_nothing_to_key_on_falls_back_to_the_sender(self):
        """A verdict keyed on nothing would be a note that can never match - saved, and silent."""
        mid = self._msg(subject='Hi')
        self.assertEqual(c.get(f'/api/messages/{mid}/not-mine/suggest').json()['scope'], 'sender')
        d = c.post(f'/api/messages/{mid}/not-mine', json={'scope': 'subject'}).json()
        self.assertEqual(d['scope'], 'sender')

    def test_the_verdict_is_saved_on_the_topic_and_older_tasks_are_reported(self):
        mid = self._msg(subject='Re: Resident Refund Request - Juergens, Larry')
        # an open task on the same topic, opened BEFORE the verdict: it does not vanish, and
        # staying silent about it is what makes a working fix look broken
        tid = server.store.create_task({'Title': 'Resident refund request - PAYNE', 'Kind': 'general',
                                        'Source': 'email'}, 'test')
        server.store.add_message({'TaskId': tid, 'ExternalId': 'older-1', 'Channel': 'email',
                                  'Subject': 'RE: Resident Refund Request - PAYNE, MICHAEL',
                                  'FromEmail': 'hudson@regencyhealthrehab.com', 'Status': 'routed'})
        d = c.post(f'/api/messages/{mid}/not-mine',
                   json={'scope': 'subject', 'note': 'resident refunds are not our task'}).json()
        self.assertEqual(d['scope'], 'subject')
        self.assertEqual(d['scopeKey'], 'resident refund request - juergens, larry')
        self.assertIn(tid, [t['taskId'] for t in d['alsoCovered']])
        self.assertTrue(server.store.get_task(tid))                # reported, never deleted
        # and the verdict now covers mail from anyone about refunds
        self.assertIn('resident refunds are not our task',
                      ingest.notes_for(server.store, {'from_email': 'brand-new@vendor.com',
                                                      'subject': 'Resident Refund Request - Smith, J',
                                                      'body': 'see attached'}))


if __name__ == '__main__':
    unittest.main()
