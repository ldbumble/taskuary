"""Every new message is evaluated afresh, in its conversation's context (PW-020 to PW-025).

Two mechanisms used to decide a new reply without reading it. `ruled_on_thread()` filed any
later mail on an email thread the owner had once dismissed, on both the attach and the create
path - so a thread that came back asking the owner something new never reached triage at all.
And `classify_intent()` turned two agreeing past verdicts into "SETTLED BY YOUR OWNER ... no
exceptions", an order the model was not allowed to weigh. Both are history now: the owner's
earlier ruling on the conversation and the past verdicts reach the model as dated EVIDENCE,
and the verdict on the new message is the model's. The explicit bypasses that need no model -
a feed connection, a saved policy, a duplicate fetch - are untouched, and re-evaluating new
activity changes nothing about the messages already judged.
"""
import unittest
from unittest import mock

from taskuary import ingest, triage
from taskuary.store import MemoryStore

CONV = 'AAQk-collection-thread'


def arrive(s, ext, llm, frm='dwhitfield@client.example', conv=CONV, subject='Re: Collection %',
           body='Why does the percentage stay the same if I exclude those payers?', sent_at='2026-09-06 10:00:00'):
    return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': frm, 'from_name': 'D. Whitfield',
                                     'conversation_id': conv, 'subject': subject, 'body': body, 'sent_at': sent_at}, llm=llm)


def brain(intent, why='x', seen=None):
    def llm(sys_, usr_, **k):
        if seen is not None: seen.append({'sys': sys_, 'usr': usr_})
        return '{"intent": "%s", "why": "%s"}' % (intent, why)
    return llm


def ruled_thread(s):
    """The first mail opened a task; the owner pressed Not our task: an owner 'ignore' route on the
    message, the task gone - exactly what the API writes."""
    first = arrive(s, 'c1', brain('reply_only'), subject='Collection %', sent_at='2026-09-06 09:00:00')
    assert first['status'] == 'created'
    s.delete_task(first['task_id'])
    s.set_message_status(first['message_id'], 'ignored')
    s.add_route(first['message_id'], None, 'ignore', None,
                'not ours - Priya will take care of this one. She is responsible for AR stuff.', [], 'owner')
    return s, first['message_id']


class RulingIsEvidenceTests(unittest.TestCase):
    def test_a_follow_up_on_a_ruled_thread_is_read_not_filed_on_sight(self):
        s, _ = ruled_thread(MemoryStore()); seen = []
        out = arrive(s, 'c2', brain('reply_only', 'this time she asks the owner directly', seen))
        self.assertEqual(out['status'], 'created')                         # the model's call, and it may open work
        self.assertEqual(len(seen), 1, 'the new message must reach the model')

    def test_the_owners_ruling_reaches_the_model_as_dated_evidence(self):
        s, _ = ruled_thread(MemoryStore()); seen = []
        arrive(s, 'c2', brain('fyi', 'same settled thread', seen))
        sys_ = seen[0]['sys']
        self.assertIn('EVIDENCE', sys_)
        self.assertIn('Priya will take care of this one', sys_)
        self.assertIn('on this very conversation', sys_.lower())
        self.assertNotIn('SETTLED BY YOUR OWNER', sys_); self.assertNotIn('no exceptions', sys_)

    def test_a_non_actionable_follow_up_is_filed_by_the_model_with_the_reason_it_gave(self):
        s, _ = ruled_thread(MemoryStore())
        out = arrive(s, 'c2', brain('fyi', 'an acknowledgement on a thread the owner handed off'), body='Thanks, Priya has it.')
        self.assertEqual((out['status'], out['task_id']), ('filed', None))
        row = next(r for r in s.feed(limit=10) if r['MessageId'] == out['message_id'])
        self.assertEqual(row['NeedsYou'], 0)
        self.assertIn('triage: fyi', row['RouteReason']); self.assertNotIn('already ruled', row['RouteReason'])

    def test_the_colleagues_answer_is_read_too(self):
        s, _ = ruled_thread(MemoryStore()); seen = []
        out = arrive(s, 'c3', brain('fyi', 'Priya answering', seen), frm='priya@corp.example')
        self.assertEqual(out['status'], 'filed'); self.assertEqual(len(seen), 1)

    def test_nothing_to_do_said_by_the_owner_is_evidence_as_well(self):
        s = MemoryStore(); seen = []
        first = arrive(s, 'c5', brain('reply_only'), subject='Collection %')
        s.delete_task(first['task_id'])
        s.add_route(first['message_id'], None, 'ignore', None, 'nothing to do - filed by the owner, nothing learned', [], 'owner')
        out = arrive(s, 'c6', brain('task', 'now they ask for the export to be fixed', seen), body='Can you fix the export?')
        self.assertEqual(out['status'], 'created')
        self.assertIn('nothing to do - filed by the owner', seen[0]['sys'])

    def test_a_ruled_thread_with_an_open_task_joins_it_and_is_judged(self):
        """The attach path had the same veto: a reply on a ruled thread was filed instead of joining
        the thread's task. It joins, and triage says what it is."""
        s = MemoryStore(); seen = []
        tid = s.create_task({'Title': 'Resident refund request', 'Kind': 'general', 'Source': 'email'}, 'test')
        s.add_message({'TaskId': tid, 'ExternalId': 'e0', 'ConversationId': 'thread-1', 'Channel': 'email',
                       'Subject': 'Re: Resident Refund Request', 'FromEmail': 'hudson@regencyhealthrehab.com',
                       'BodyText': 'the refund paperwork', 'Status': 'routed'})
        ruled = arrive(s, 'e0b', brain('fyi'), frm='lynch@regencyhealthrehab.com', conv='thread-1', subject='Re: Resident Refund Request')
        s.set_message_status(ruled['message_id'], 'ignored')
        s.add_route(ruled['message_id'], None, 'ignore', None, 'not ours - resident refunds are not our task', [], 'owner')
        out = arrive(s, 'e2', brain('task', 'asks the owner to approve', seen), frm='another@regencyhealthrehab.com',
                     conv='thread-1', subject='Re: Resident Refund Request', body='Uri, can you approve this one?')
        self.assertEqual((out['status'], out['task_id']), ('attached', tid))
        self.assertIn('resident refunds are not our task', seen[0]['sys'])


class BypassesStayTests(unittest.TestCase):
    def test_a_saved_policy_still_decides_without_a_model(self):
        s = MemoryStore(); seen = []
        s.save_policy({'Name': 'newsletters', 'Kind': 'sender', 'Pattern': 'news@vendor.example', 'Action': 'skip', 'Reason': 'a flood sender', 'Active': 1}, 't')
        out = arrive(s, 'p1', brain('task', 'x', seen), frm='news@vendor.example', conv='nl-1', subject='Weekly', body='Read all about it')
        self.assertEqual(out['status'], 'skipped'); self.assertEqual(seen, [])

    def test_a_feed_connection_still_shows_and_never_judges(self):
        s = MemoryStore(); seen = []
        out = ingest.ingest_message(s, {'external_id': 'f1', 'channel': 'email', 'from_email': 'a@b.example', 'subject': 's',
                                        'body': 'please do x', 'conversation_id': 'f'}, llm=brain('task', 'x', seen), file_only=True)
        self.assertEqual(out['status'], 'feed'); self.assertEqual(seen, [])

    def test_a_duplicate_fetch_of_the_same_message_is_not_evaluated_again(self):
        s, _ = ruled_thread(MemoryStore()); seen = []
        arrive(s, 'c2', brain('fyi', 'x', seen))
        again = arrive(s, 'c2', brain('task', 'y', seen))
        self.assertEqual(again['status'], 'duplicate'); self.assertEqual(len(seen), 1)

    def test_a_per_message_dismissal_teaches_no_standing_policy(self):
        s, _ = ruled_thread(MemoryStore())
        self.assertEqual(s.list_policies(), [])
        self.assertEqual([m for m in s.list_memories() if m.get('Active')], [])


class HistoryIsPreservedTests(unittest.TestCase):
    def test_re_evaluating_new_activity_leaves_the_judged_messages_alone(self):
        s, first_mid = ruled_thread(MemoryStore())
        before = (s.get_message(first_mid)['Status'], s.get_message(first_mid)['TaskId'], s.message_routes(first_mid)[-1]['Reason'])
        arrive(s, 'c2', brain('task', 'asks the owner'))
        after = (s.get_message(first_mid)['Status'], s.get_message(first_mid)['TaskId'], s.message_routes(first_mid)[-1]['Reason'])
        self.assertEqual(before, after)
        self.assertEqual(before[0], 'ignored')

    def test_a_reply_on_a_closed_tasks_thread_does_not_reopen_it(self):
        s = MemoryStore()
        first = arrive(s, 'd1', brain('reply_only'), conv='done-1', subject='Budget upload failing', body='The upload fails, can you look?')
        tid = first['task_id']
        s.update_task(tid, {'Status': 'done'}, 'owner')
        out = arrive(s, 'd2', brain('fyi', 'thanks'), conv='done-1', subject='Re: Budget upload failing', body='Thanks, works now!')
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        self.assertEqual(out['status'], 'filed')
        out2 = arrive(s, 'd3', brain('task', 'a new problem on the same thread'), conv='done-1', subject='Re: Budget upload failing',
                      body='It broke again after the update, please fix.')
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        self.assertEqual(out2['status'], 'created'); self.assertNotEqual(out2['task_id'], tid)


class NoForcedVerdictTests(unittest.TestCase):
    NOTES = ['2026-08-25: "resident refund request" - NOT OURS: other people\'s work',
             '2026-08-26: "resident refund request approved" - NOT OURS: other people\'s work']

    def test_unanimous_past_verdicts_are_evidence_not_an_order(self):
        seen = {}
        def llm(sys_, usr_, **k): seen['sys'] = sys_; return '{"intent": "reply_only", "why": "asks when the check was mailed"}'
        out = triage.classify_intent({'from_email': 'r@ours.com', 'subject': 'Re: Resident Refund Request Approved - Doe',
                                      'body': 'Can you advise when the check was mailed?'}, llm=llm, notes=self.NOTES)
        self.assertEqual(out['intent'], 'reply_only')                     # the model's answer stands
        self.assertNotIn('SETTLED BY YOUR OWNER', seen['sys']); self.assertNotIn('no exceptions', seen['sys'])
        self.assertIn('EVIDENCE', seen['sys'])
        for n in self.NOTES: self.assertIn(n, seen['sys'])

    def test_not_a_coding_task_verdicts_are_evidence_too(self):
        seen = {}
        def llm(sys_, usr_, **k): seen['sys'] = sys_; return '{"intent": "task", "why": "x"}'
        triage.classify_intent({'from_email': 'hr@corp.com', 'subject': 'Badges', 'body': 'order badges'}, llm=llm,
                               notes=['2026-08-26: "Badges" - NOT A CODING TASK: yours', '2026-08-27: "Badges" - NOT A CODING TASK: yours'])
        self.assertNotIn('SETTLED', seen['sys']); self.assertIn('NOT A CODING TASK', seen['sys'])

    def test_the_settled_machinery_is_gone(self):
        self.assertFalse(hasattr(triage, '_agreement')); self.assertFalse(hasattr(triage, 'SETTLED_INTENT'))
        self.assertFalse(hasattr(ingest, 'ruled_on_thread'))


if __name__ == '__main__':
    unittest.main()
