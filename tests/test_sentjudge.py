"""The owner's sent words, read by the model (sentjudge.py): which asked the other side for something, which promised
something - and a promise stays open until a LATER word of the owner's delivers it, never because the other side wrote
back. Replaces the _ASKS/_PROMISE regexes that picked what the Advisor could see (the owner, 2026-10-11: "remove step 1.
Everything should be ai"). The model is a stub that answers per phrase (tests/sentjudge_fixture.py)."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import assistant, sentjudge
from taskuary.store import MemoryStore
from tests.sentjudge_fixture import brain, judged

ME, RAY = 'alex@northwind.example', 'ray@vendor.example'
def _ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
def _day(days=0): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')


def _store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled'): s.set_setting(k, '0', 't')
    s.set_setting('owner_email', ME, 't')
    return s


N = [0]
def _theirs(s, body, days, conv, hours=0):
    N[0] += 1
    return s.add_message({'ExternalId': f't{N[0]}', 'ConversationId': conv, 'Channel': 'email', 'SourceName': ME, 'Subject': 'Budget',
                          'FromName': 'Ray Colton', 'FromEmail': RAY, 'SentAt': _ago(days, hours), 'BodyText': body, 'Status': 'filed'})


def _mine(s, body, days, conv, hours=0):
    N[0] += 1
    return s.add_message({'ExternalId': f'm{N[0]}', 'ConversationId': conv, 'Channel': 'email', 'SourceName': ME, 'Subject': 'Re: Budget',
                          'FromName': 'Alex Doyle', 'FromEmail': ME, 'SentAt': _ago(days, hours), 'BodyText': body, 'Status': 'context'})


PROMISE = {"I'll send the budget Friday": {'promise': True, 'what': 'send the budget', 'due': _day(-1)},
           'On it, by EOD': {'promise': True, 'what': 'send the deck', 'due': _day(3)},
           'Can you confirm the PO': {'asks_them': True}}


class PromiseTests(unittest.TestCase):
    # A JUDGED PROMISE IS A TASK on the owner, with its day (spec 2026-10-12, goals as tasks): a row on the rail, so the
    # Advisor raises no line for it. The other side's thanks closes neither.
    def test_a_promise_survives_their_thanks(self):
        s = _store()
        _theirs(s, 'Can we get the revised budget?', 4, 'c1'); mid = _mine(s, "I'll send the budget Friday.", 3, 'c1')
        self.assertEqual(judged(s, PROMISE), 1)
        t = s.promise_task(mid)
        self.assertEqual((t['Title'], t['Status'], t['Assignee'], t['DueAt']), ('Send the budget', 'open', 'owner', PROMISE["I'll send the budget Friday"]['due']))
        self.assertEqual(assistant.followups(s, 24), [])
        _theirs(s, 'Great, thanks!', 2, 'c1')                                    # their word is not the budget
        self.assertEqual(s.promise_task(mid)['Status'], 'open')
        self.assertEqual(assistant.followups(s, 24), [])

    def test_on_it_by_eod_is_a_promise_not_a_chase_on_them(self):
        s = _store()
        _theirs(s, 'Can we get the deck?', 4, 'c2'); mid = _mine(s, 'On it, by EOD.', 3, 'c2')
        judged(s, PROMISE)
        self.assertEqual((s.promise_task(mid)['Title'], s.promise_task(mid)['DueAt']), ('Send the deck', PROMISE['On it, by EOD']['due']))   # the model's day - read from the fixture, so a run across midnight cannot split it (2026-10-25)
        self.assertEqual(assistant.followups(s, 24, ('followup',)), [])

    def test_an_ask_of_them_is_a_followup_chosen_by_the_judge(self):
        s = _store()
        _theirs(s, 'Invoice attached.', 4, 'c3'); _mine(s, 'Can you confirm the PO number?', 3, 'c3')
        judged(s, PROMISE)
        self.assertEqual([c['kind'] for c in assistant.followups(s, 24)], ['followup'])
        _theirs(s, 'PO is 4471.', 2, 'c3')                                       # they answered: no longer the owner's last word
        self.assertEqual(assistant.followups(s, 24), [])

    def test_a_later_owner_message_judged_as_delivering_closes_it(self):
        s = _store(); calls = []
        _theirs(s, 'Can we get the revised budget?', 5, 'c1'); p = _mine(s, "I'll send the budget Friday.", 4, 'c1')
        judged(s, PROMISE)
        d = _mine(s, 'Attached is the revised budget.', 1, 'c1')
        judged(s, {'Attached is the revised budget': {'delivers': [f'm{p}']}}, calls)
        self.assertIn(f'OPEN PROMISES on this thread: [m{p}] "send the budget"', calls[0])    # the judge was shown it
        self.assertEqual(s.sent_verdict(p)['DeliveredBy'], d)
        self.assertEqual(assistant.followups(s, 0), [])

    def test_a_promise_judged_after_its_delivery_sees_the_later_words(self):
        s = _store(); calls = []
        _theirs(s, 'Budget?', 5, 'c1'); p = _mine(s, "I'll send the budget Friday.", 4, 'c1'); d = _mine(s, 'Here it is, attached.', 1, 'c1')
        judged(s, {"I'll send the budget": lambda item: {'promise': True, 'what': 'send the budget', 'delivered': 'Here it is' in item}}, calls)
        self.assertIn('YOUR LATER WORDS on this thread', calls[0])
        self.assertEqual(s.sent_verdict(p)['DeliveredBy'], d)
        self.assertEqual(assistant.followups(s, 0), [])

    def test_a_delivery_it_was_not_shown_is_ignored(self):
        s = _store()
        _theirs(s, 'Budget?', 5, 'c1'); p = _mine(s, "I'll send the budget Friday.", 4, 'c1')
        _theirs(s, 'Deck?', 5, 'c9'); _mine(s, 'Done.', 1, 'c9')
        judged(s, PROMISE); judged(s, {'Done.': {'delivers': [f'm{p}']}})      # another thread's message cannot close it
        self.assertIsNone(s.sent_verdict(p)['DeliveredBy'])

    def test_the_owner_closing_the_task_closes_it(self):
        s = _store()
        _theirs(s, 'Budget?', 5, 'c1'); mid = _mine(s, "I'll send the budget Friday.", 4, 'c1')
        judged(s, PROMISE)
        s.update_task(s.promise_task(mid)['TaskId'], {'Status': 'done'}, 'owner')
        self.assertEqual(assistant.followups(s, 24), [])
        self.assertEqual(judged(s, PROMISE), 0)                                 # judged once: no second task, no second line

    def test_promises_due_reads_the_judged_day(self):
        s = _store()
        _theirs(s, 'Budget?', 3, 'c1'); _mine(s, 'You will have it Monday.', 2, 'c1')
        judged(s, {'You will have it': {'promise': True, 'what': 'send the budget', 'due': _day()}})
        self.assertEqual(assistant.promises_due(s), [{'who': 'Ray Colton', 'what': 'send the budget', 'mid': s._one(
            "SELECT MessageId FROM message WHERE BodyText LIKE 'You will%'")['MessageId']}])
        s._exec('UPDATE sent_verdict SET Due=?', (_day(-2),))
        self.assertEqual(assistant.promises_due(s), [])


class JudgeTests(unittest.TestCase):
    def test_each_message_is_judged_once(self):
        s = _store(); calls = []
        _theirs(s, 'Budget?', 3, 'c1'); _mine(s, "I'll send the budget Friday.", 2, 'c1')
        self.assertEqual(judged(s, PROMISE, calls), 1)
        self.assertEqual(judged(s, PROMISE, calls), 0)
        self.assertEqual(len(calls), 1, 'a judged message is never sent to the model again')

    def test_one_call_judges_the_batch(self):
        s = _store(); calls = []
        for i in range(5): _theirs(s, 'Hi', 4, f'c{i}'); _mine(s, f'Line {i}', 3, f'c{i}')
        self.assertEqual(judged(s, {}, calls), 5)
        self.assertEqual(len(calls), 1)

    def test_an_answer_it_could_not_read_judges_nothing(self):
        s = _store()
        _mine(s, "I'll send the budget Friday.", 2, 'c1')
        self.assertEqual(sentjudge.judge(s, lambda *a, **k: 'not json'), 0)
        self.assertEqual(len(s.sent_unjudged(_ago(30))), 1)                    # tried again on the next run

    def test_no_model_guesses_nothing_and_says_so(self):
        s = _store()
        _theirs(s, 'Budget?', 3, 'c1'); _mine(s, "I'll send the budget Friday.", 2, 'c1')
        with mock.patch('taskuary.llm.build_llm', return_value=None): self.assertEqual(sentjudge.judge(s), 0)
        self.assertEqual(assistant.followups(s, 0), [])
        with mock.patch.object(sentjudge, 'ready', return_value=False): self.assertIn("can't keep track", sentjudge.blind(s))
        with mock.patch.object(sentjudge, 'ready', return_value=True): self.assertIn("haven't read 1 of your sent message", sentjudge.blind(s))
        with mock.patch.object(sentjudge, 'ready', return_value=False):
            from taskuary import digest
            self.assertIn("NOT TRACKED: Nothing reads your sent mail", digest.gather(s, 3))

    def test_the_advisor_run_judges_before_it_finds_candidates(self):
        s = _store(); seen = []
        _theirs(s, 'Can we get the revised budget?', 4, 'c1'); _mine(s, "I'll send the budget Friday.", 3, 'c1')
        judge = brain(PROMISE)
        def llm(system, user, **kw):
            if system == sentjudge.SYSTEM: return judge(system, user)
            seen.append(user); return json.dumps({'say': [], 'notes': ''})
        assistant.run(s, llm=llm, force=True)
        mid = s._one("SELECT MessageId FROM message WHERE Status='context'")['MessageId']
        self.assertTrue(s.sent_verdict(mid))
        # ...and the promise it found is a task by the time the candidates are read, so it is not among them
        self.assertEqual(s.promise_task(mid)['Title'], 'Send the budget')
        self.assertNotIn('[promise:c1]', seen[0])


class AdvisorLineTests(unittest.TestCase):
    def test_a_nobody_replied_line_is_held_by_the_models_own_premise_flag(self):
        s = _store()
        tid = s.create_task({'Title': 'Give access', 'Kind': 'coding', 'Status': 'done'}, 't')
        mid = _theirs(s, 'Am I missing a permission?', 0, 'a1')
        s._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (tid, mid))
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'DraftText': 'Fixed.', 'Status': 'pending'})
        s.decide_review(rid, 'approved', 'Fixed.', 'owner')
        line = {'text': 'Ray is still stuck on access.', 'action': {'type': 'message', 'mid': mid}}
        self.assertFalse(assistant.contradicts_sent_reply(s, line))              # no word list reads the text
        self.assertTrue(assistant.contradicts_sent_reply(s, line | {'action': line['action'] | {'unanswered': True}}))

    def test_a_job_list_is_read_whatever_the_subject_says(self):
        r = {'Subject': 'ci - master (abc1234)', 'BodyText': 'ci / test (ubuntu, 3.12) Failed in 49 seconds\n'}
        self.assertEqual(assistant._cause(r), ' -> failed: test (ubuntu, 3.12)')
        self.assertEqual(assistant._cause({'Subject': 'Nightly - FAILED', 'BodyText': 'Login timeout'}), '')


if __name__ == '__main__': unittest.main()
