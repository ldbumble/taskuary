""""I wrote this a bunch and the system is not learning it."

Four reasons it could not, and all four are covered here. A verdict about a KIND OF WORK had
nowhere to live - the scopes were this sender, their domain, or everybody - so "resident
refunds are not our task" got filed under whichever colleague was on screen and never fired
again on a seventeen-person thread. ATTACHING skipped every judgement: once a task existed,
each new message on the thread joined it with no triage, no notes and no AI call, so the task
stayed 'needs you' no matter what the owner had said. CREATING skipped it too, and less
visibly - veto() guarded the attach branch alone, so the same topic on a thread with no task
yet went to the classifier as advice rather than as a decision. And a model that ANSWERED
UNUSABLY fell through to a keyword heuristic whose last branch assumes real work and reads no
notes at all, which is how a refused topic kept opening a fresh task every single time.
"""
import unittest
from fastapi.testclient import TestClient

from taskuary import ingest, server
from taskuary.store import MemoryStore

c = TestClient(server.app)

REFUND = 'Re: Resident Refund Request - Doe, Jane'
# what a verdict on that subject now keys on: the standing part, with the resident left out
TOPIC = 'resident refund request'


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
        self.assertEqual(d['scopeKey'], TOPIC)          # the resident is not the topic
        self.assertIn(tid, [t['taskId'] for t in d['alsoCovered']])
        self.assertTrue(server.store.get_task(tid))                # reported, never deleted
        # and the verdict now covers mail from anyone about refunds
        self.assertIn('resident refunds are not our task',
                      ingest.notes_for(server.store, {'from_email': 'brand-new@vendor.com',
                                                      'subject': 'Resident Refund Request - Smith, J',
                                                      'body': 'see attached'}))


if __name__ == '__main__':
    unittest.main()


class TheTopicIsTheStandingPartTests(unittest.TestCase):
    """A verdict keyed on "resident refund request - doe, jane" put the match on a
    knife edge: the resident is half the words, so the next mail scored exactly the 0.5 floor
    and a longer name fell under it. A rule that general work has to key on the general part."""
    def _msg(self, subject):
        return server.store.add_message({'ExternalId': f'topic-{subject}', 'Channel': 'email',
                                         'Subject': subject, 'FromEmail': 'hudson@regencyhealthrehab.com',
                                         'BodyText': 'history attached', 'Status': 'filed'})

    def test_the_per_item_tail_is_not_part_of_the_topic(self):
        from taskuary.routing import subject_topic
        for subj in ('Re: Resident Refund Request - Doe, Jane',
                     'RE: Resident Refund Request - Foote, Marie Grace',
                     'Resident Refund Request'):
            self.assertEqual(subject_topic(subj), 'resident refund request')
        self.assertEqual(subject_topic('Vendor Create'), 'vendor create')
        self.assertEqual(subject_topic('Hi'), '')            # nothing to key a topic on

    def test_the_generalised_key_matches_every_resident_outright(self):
        key = 'resident refund request'
        for subj in ('Re: Resident Refund Request - PAYNE, MICHAEL',
                     'RE: Resident Refund Request - Watson, Lisa',
                     'Resident refund request - Roe, Sam'):
            self.assertTrue(ingest.topic_hit(key, subj))
        self.assertFalse(ingest.topic_hit(key, 'Vendor Create'))

    def test_the_owner_can_say_what_the_topic_is(self):
        """Trimming is a guess at the standing part. Being told beats guessing."""
        mid = self._msg('Re: Resident Refund Request - Juergens, Larry')
        d = c.post(f'/api/messages/{mid}/not-mine',
                   json={'scope': 'subject', 'topic': 'RE: resident refunds', 'note': 'not ours'}).json()
        self.assertEqual(d['scopeKey'], 'resident refunds')       # normalised, Re: stripped
        self.assertTrue(ingest.topic_hit(d['scopeKey'], 'Resident Refunds - anyone at all'))

    def test_a_topic_too_thin_to_match_falls_back_rather_than_saving_nothing(self):
        mid = self._msg('Re: Resident Refund Request - Adams, Neil')
        d = c.post(f'/api/messages/{mid}/not-mine', json={'scope': 'subject', 'topic': 'the'}).json()
        self.assertEqual((d['scope'], d['scopeKey']), ('sender', 'hudson@regencyhealthrehab.com'))


class CreateRespectsTheVerdictTests(unittest.TestCase):
    """The half that was still missing. veto() guarded ATTACH only, so the same topic arriving
    on a thread with no task open yet reached the classifier as a NOTE - advice, which loses to
    a model having a bad day. Twenty verdicts, twenty new tasks."""
    def _arrive(self, s, llm=None, subject='Resident Refund Request - Watson, Lisa'):
        return ingest.ingest_message(s, {'external_id': f'new-{subject}', 'channel': 'email',
                                         'from_email': 'never-seen@elsewhere.com', 'subject': subject,
                                         'body': 'Attached is the transaction history.'}, llm=llm)

    def test_a_topic_verdict_stops_a_new_task_opening(self):
        s = _store(VERDICT)
        out = self._arrive(s, llm=lambda *a, **k: '{"intent": "task", "why": "real work"}')
        self.assertEqual((out['status'], out['task_id']), ('filed', None))
        row = next(r for r in s.feed(limit=10) if r['MessageId'] == out['message_id'])
        self.assertEqual(row['NeedsYou'], 0)
        self.assertIn('Resident refunds are not our task', row['RouteReason'])

    def test_a_verdict_about_a_PERSON_still_only_advises(self):
        """Someone whose last message was not yours can still send you something that is, so a
        sender-scoped verdict goes to the classifier instead of deciding for it."""
        s = _store(('sender', 'dana@vendor.com', 'Dana asking about ledgers is not ours.', 'verdict'))
        seen = {}
        def llm(sys_, usr_, **kw):
            seen['sys'] = sys_
            return '{"intent": "task", "why": "real work"}'
        out = ingest.ingest_message(s, {'external_id': 'p1', 'channel': 'email', 'from_email': 'dana@vendor.com',
                                        'subject': 'Quarterly ledger', 'body': 'please rebuild the ledger'}, llm=llm)
        self.assertEqual(out['status'], 'created')
        self.assertIn('Dana asking about ledgers', seen['sys'])

    def test_mail_about_something_else_is_untouched(self):
        s = _store(VERDICT)
        out = self._arrive(s, subject='Directors meeting agenda',
                           llm=lambda *a, **k: '{"intent": "task", "why": "real work"}')
        self.assertEqual(out['status'], 'created')


class DegradedTriageTests(unittest.TestCase):
    """The AI answered, and the answer was not a verdict. `fail` only catches a call that RAISED,
    so the old code sailed on with heuristic_intent's last branch - "assumed real work", which
    reads no standing notes at all - and opened the task anyway. The timeline said so out loud:
    "assumed real work (keyword heuristic, no AI read this)"."""
    MSG = {'external_id': 'd1', 'channel': 'email', 'from_email': 'someone@elsewhere.com',
           'subject': 'Resident Refund Request - Watson, Lisa', 'body': 'Attached is the history.'}

    def test_an_unusable_answer_files_instead_of_assuming_work(self):
        s = MemoryStore()
        out = ingest.ingest_message(s, dict(self.MSG), llm=lambda *a, **k: 'I think this is a task, honestly')
        self.assertEqual((out['status'], out['task_id']), ('filed', None))
        self.assertIn('could not read as a verdict', next(
            r for r in s.feed(limit=10) if r['MessageId'] == out['message_id'])['RouteReason'])

    def test_the_cheap_fyi_short_circuit_still_runs_without_a_model(self):
        """That branch is a keyword rule that only ever FILES, which is the safe direction -
        it is not degraded and must keep saving the AI call."""
        s, called = MemoryStore(), []
        out = ingest.ingest_message(s, {'external_id': 'd2', 'channel': 'email', 'from_email': 'x@y.com',
                                        'subject': 'Weekly digest',
                                        'body': 'This is an automated message. No action required.'},
                                    llm=lambda *a, **k: called.append(1) or '{"intent": "task", "why": "x"}')
        self.assertEqual((out['status'], called), ('filed', []))

    def test_degradation_is_marked_only_when_a_model_was_actually_asked(self):
        from taskuary.triage import classify_intent
        msg = {'from_email': 'x@y.com', 'subject': 'something', 'body': 'a body with no question'}
        self.assertTrue(classify_intent(msg, llm=lambda *a, **k: 'not json').get('degraded'))
        self.assertNotIn('degraded', classify_intent(msg))      # no model asked, nothing degraded


class ThreadVerdictTests(unittest.TestCase):
    """"Collection %" from the CFO: one usable word in the subject, so "Priya will take care of
    this one" could only be saved against the sender - advice. The very next reply on the same
    conversation opened a task, with Priya's answer already sitting in the thread. A verdict
    given on a thread decides that thread, however it happened to be filed."""
    CONV = 'AAQk-collection-thread'
    REPLY = lambda *a, **k: '{"intent": "reply_only", "why": "asks how the percentage is computed"}'

    def _arrive(self, s, ext, frm='dwhitfield@client.example', conv=None, subject='Re: Collection %'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': frm,
                                         'conversation_id': conv or self.CONV, 'subject': subject,
                                         'body': 'Why does the percentage stay the same if I exclude those payers?'},
                                     llm=self.REPLY)

    def _ruled(self):
        """The first mail arrives, opens a task, and the owner presses Not our task - which the
        API writes as a sender-scoped memory plus an owner 'ignore' route on the message."""
        s = MemoryStore()
        first = self._arrive(s, 'c1', subject='Collection %')
        self.assertEqual(first['status'], 'created')
        s.add_memory({'Scope': 'sender', 'ScopeKey': 'dwhitfield@client.example', 'Source': 'verdict', 'Active': 1,
                      'CreatedBy': 'owner', 'Note': 'Priya will take care of this one. She is responsible for AR stuff.'})
        s.delete_task(first['task_id'])
        s.set_message_status(first['message_id'], 'ignored')
        s.add_route(first['message_id'], None, 'ignore', None,
                    'not ours - Priya will take care of this one. She is responsible for AR stuff.', [], 'owner')
        return s

    def test_the_askers_follow_up_on_the_same_thread_is_filed(self):
        s = self._ruled()
        out = self._arrive(s, 'c2')
        self.assertEqual((out['status'], out['task_id']), ('filed', None))
        row = next(r for r in s.feed(limit=10) if r['MessageId'] == out['message_id'])
        self.assertEqual(row['NeedsYou'], 0)
        self.assertIn('Priya will take care of this one', row['RouteReason'])
        self.assertNotIn('not ours - not ours', row['RouteReason'])

    def test_the_colleagues_answer_on_the_thread_is_filed_too(self):
        s = self._ruled()
        out = self._arrive(s, 'c3', frm='priya@corp.example')
        self.assertEqual((out['status'], out['task_id']), ('filed', None))

    def test_a_new_thread_from_the_same_sender_is_still_the_classifiers_call(self):
        """The sender-scoped half keeps its meaning: a person ruled out on one thread can still
        send something that is yours, so a fresh conversation goes to the classifier as before."""
        s = self._ruled()
        out = self._arrive(s, 'c4', conv='AAQk-something-else', subject='Budget upload failing')
        self.assertEqual(out['status'], 'created')

    def test_nothing_to_do_said_by_the_owner_rules_the_thread_too(self):
        """"Nothing to do here" / "Not a task - just conversation" is the verdict the owner gives
        most, and it teaches nothing about the sender on purpose - but said on a thread it is
        still a ruling on THAT thread (tests/test_verdict_paths.py has the whole story)."""
        s = MemoryStore()
        first = self._arrive(s, 'c5', subject='Collection %')
        s.delete_task(first['task_id'])
        s.add_route(first['message_id'], None, 'ignore', None, 'nothing to do - filed by the owner, nothing learned', [], 'owner')
        out = self._arrive(s, 'c6')
        self.assertEqual((out['status'], out['task_id']), ('filed', None))
