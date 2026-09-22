""""Someone else on the chain was already responding, so it should not be on me."

A request lands, a colleague answers it an hour later, and the owner still gets a task with a
drafted reply - because triage read the message and nothing around it. Whether a thread is
already in hand is never IN the message; it is in the messages beside it, and nothing was
looking there.

These cover the signal: who counts as somebody else, who does not, that it survives a channel
with no conversation id, and that it actually reaches the prompt.
"""
import unittest

from taskuary import ingest
from taskuary.store import MemoryStore
from taskuary.triage import classify_intent

OWNER, ASKER, PEER = 'alex@ours.example', 'moshe@vendor.example', 'priya@ours.example'


def _thread(*rows):
    """rows are (from_email, from_name, when) on one email thread."""
    s = MemoryStore()
    for i, (frm, name, when) in enumerate(rows):
        s.add_message({'ExternalId': f'th{i}', 'ConversationId': 'thread-1', 'Channel': 'email',
                       'Subject': 'Re: PCC - WHT', 'FromEmail': frm, 'FromName': name,
                       'SentAt': when, 'BodyText': 'body', 'Status': 'filed'})
    return s


ARRIVING = {'external_id': 'new', 'channel': 'email', 'conversation_id': 'thread-1',
            'from_email': ASKER, 'subject': 'Re: PCC - WHT',
            'body': 'Can you add column with Facility address? Otherwise, this is perfect.'}


class WhoCountsTests(unittest.TestCase):
    def test_a_colleague_who_replied_is_the_signal(self):
        s = _thread((ASKER, 'Moshe Benjamin', '2026-08-26 10:00:00'),
                    (PEER, 'Priya Raman', '2026-08-26 10:40:00'))
        got = ingest.others_on_thread(s, ARRIVING, mine=[OWNER])
        self.assertEqual(got['others_replied'], ['Priya Raman'])
        self.assertEqual(got['last_on_thread'], 'Priya Raman')
        self.assertFalse(got['last_on_thread_is_you'])

    def test_the_asker_following_up_is_still_the_asker(self):
        """Two messages from the person doing the asking is not somebody else handling it."""
        s = _thread((ASKER, 'Moshe Benjamin', '2026-08-26 10:00:00'),
                    (ASKER, 'Moshe Benjamin', '2026-08-26 10:30:00'))
        self.assertEqual(ingest.others_on_thread(s, ARRIVING, mine=[OWNER]), {})

    def test_your_own_replies_are_not_somebody_else(self):
        """The owner having answered already is a different fact, and not this one."""
        s = _thread((ASKER, 'Moshe Benjamin', '2026-08-26 10:00:00'),
                    (OWNER, 'Alex', '2026-08-26 10:20:00'))
        self.assertEqual(ingest.others_on_thread(s, ARRIVING, mine=[OWNER]), {})

    def test_being_cc_d_is_not_answering(self):
        """Only people who SENT something count - a seventeen-person thread where nobody has
        replied is exactly the case that must still reach the owner."""
        s = _thread((ASKER, 'Moshe Benjamin', '2026-08-26 10:00:00'))
        self.assertEqual(ingest.others_on_thread(s, {**ARRIVING, 'cc': [PEER, 'someone@ours.example']},
                                                 mine=[OWNER]), {})

    def test_an_empty_thread_says_nothing_either_way(self):
        self.assertEqual(ingest.others_on_thread(MemoryStore(), ARRIVING, mine=[OWNER]), {})


class NoConversationIdTests(unittest.TestCase):
    """Teams, Slack and half the mail in the world arrive with no thread id, so the subject is
    the only handle - normalised, so "Re:" and "RE:" are the same thread."""
    def test_the_subject_is_the_fallback(self):
        s = MemoryStore()
        for i, (frm, name) in enumerate([(ASKER, 'Moshe Benjamin'), (PEER, 'Priya Raman')]):
            s.add_message({'ExternalId': f'n{i}', 'Channel': 'email', 'Subject': 'RE: PCC - WHT',
                           'FromEmail': frm, 'FromName': name, 'SentAt': f'2026-08-26 1{i}:00:00',
                           'BodyText': 'b', 'Status': 'filed'})
        got = ingest.others_on_thread(s, {**ARRIVING, 'conversation_id': None}, mine=[OWNER])
        self.assertEqual(got['others_replied'], ['Priya Raman'])

    def test_a_different_subject_is_a_different_thread(self):
        s = MemoryStore()
        s.add_message({'ExternalId': 'x', 'Channel': 'email', 'Subject': 'Something else entirely',
                       'FromEmail': PEER, 'FromName': 'Priya Raman', 'SentAt': '2026-08-26 10:00:00',
                       'BodyText': 'b', 'Status': 'filed'})
        self.assertEqual(ingest.others_on_thread(s, {**ARRIVING, 'conversation_id': None}, mine=[OWNER]), {})


class ItReachesThePromptTests(unittest.TestCase):
    def test_the_classifier_is_told_and_the_guidance_travels_with_it(self):
        seen = {}
        def llm(system, user, images=None):
            seen['system'], seen['user'] = system, user
            return '{"intent": "fyi", "why": "Priya is handling it"}'
        out = classify_intent({'from_email': ASKER, 'subject': 'Re: PCC - WHT', 'body': 'can you add a column?'},
                              llm=llm, thread={'others_replied': ['Priya Raman'],
                                               'last_on_thread': 'Priya Raman',
                                               'last_on_thread_is_you': False})
        self.assertEqual(out['intent'], 'fyi')
        self.assertIn('Priya Raman', seen['user'])          # the fact
        self.assertIn('others_replied', seen['system'])        # and how to weigh it

    def test_nothing_is_added_when_nobody_else_has_spoken(self):
        seen = {}
        def llm(system, user, images=None):
            seen['user'] = user
            return '{"intent": "task", "why": "real work"}'
        classify_intent({'from_email': ASKER, 'subject': 's', 'body': 'please add a column'}, llm=llm, thread={})
        self.assertNotIn('others_replied', seen['user'])


class EndToEndTests(unittest.TestCase):
    def test_a_thread_a_colleague_is_answering_does_not_open_a_task(self):
        """The whole point, through ingest: same message, and the only difference is whether a
        colleague has spoken on the thread."""
        seen = []
        def llm(system, user, images=None):
            seen.append(user)
            return ('{"intent": "fyi", "why": "a colleague is answering"}' if 'others_replied' in user
                    else '{"intent": "task", "why": "a concrete change was requested"}')
        quiet = _thread((ASKER, 'Moshe Benjamin', '2026-08-26 10:00:00'))
        self.assertEqual(ingest.ingest_message(quiet, dict(ARRIVING), llm=llm)['status'], 'created')

        busy = _thread((ASKER, 'Moshe Benjamin', '2026-08-26 10:00:00'),
                       (PEER, 'Priya Raman', '2026-08-26 10:40:00'))
        out = ingest.ingest_message(busy, {**ARRIVING, 'external_id': 'new2'}, llm=llm)
        self.assertEqual((out['status'], out['task_id']), ('filed', None))
        row = next(r for r in busy.feed(limit=10) if r['MessageId'] == out['message_id'])
        self.assertEqual(row['NeedsYou'], 0)
        self.assertIn('colleague is answering', row['RouteReason'])


if __name__ == '__main__':
    unittest.main()


class ChatIdentityTests(unittest.TestCase):
    """Teams lines carry no address for most participants, and the owner's own lines are 'You'.
    Keyed on addresses, a twenty-message group chat read as a thread nobody had spoken on."""
    def _chat(self, *rows):
        s = MemoryStore()
        for i, (name, when) in enumerate(rows):
            s.add_message({'ExternalId': f'tm{i}', 'ConversationId': 'teams:19:grp', 'Channel': 'teams', 'Subject': 'VPN Helpdesk',
                           'FromEmail': None, 'FromName': name, 'SentAt': when, 'BodyText': 'body', 'Status': 'filed'})
        return s
    ARRIVING = {'external_id': 'tnew', 'channel': 'teams', 'conversation_id': 'teams:19:grp', 'from_name': 'Sam Okafor',
                'subject': 'VPN Helpdesk', 'body': 'Anyone able to reset my VPN token?'}

    def test_a_participant_with_no_address_still_counts(self):
        out = ingest.others_on_thread(self._chat(('Lee Tan', '2026-08-21 14:00:00')), self.ARRIVING, (OWNER,))
        self.assertEqual(out['others_replied'], ['Lee Tan'])

    def test_the_owners_own_chat_lines_are_you(self):
        out = ingest.others_on_thread(self._chat(('Lee Tan', '2026-08-21 14:00:00'), ('You', '2026-08-21 14:05:00')), self.ARRIVING, (OWNER,))
        self.assertEqual((out['others_replied'], out['last_on_thread_is_you']), (['Lee Tan'], True))
        alone = ingest.others_on_thread(self._chat(('You', '2026-08-21 14:05:00')), self.ARRIVING, (OWNER,))
        self.assertEqual(alone, {})

    def test_the_asker_by_name_is_still_the_asker(self):
        out = ingest.others_on_thread(self._chat(('Sam Okafor', '2026-08-21 13:00:00')), self.ARRIVING, (OWNER,))
        self.assertEqual(out, {})


class RepoWorkTests(unittest.TestCase):
    """A github item is the CLASSIFIER's call - every one of them.

    It used not to be. Five of five contributor PRs came back `fyi`, so a regex gate in
    decided_intent answered "work by construction" before the model was asked. The gate named no
    `kind`, an unnamed kind is `general`, and so the rescue routed every PR to the ASSISTANT
    instead of the coder - #36 through #47, twelve in a row, until 2026-09-16. The rule the gate
    was overriding was in TRIAGE.md all along ("a stranger's pull request or issue is fyi - never
    task"): the document and the code said opposite things and the code won by running first.

    TRIAGE.md now says what a pull request IS, the gate is gone, and the model reaches `coding`
    itself. That is the only road on which the verdict is visible, correctable and learned from -
    so what these tests pin is that nothing answers for the model any more."""
    def _gh(self, head):
        return {'external_id': f'gh-{head[:22]}', 'channel': 'github', 'conversation_id': 'gh:o/r#7', 'no_auto': True,
                'from_email': 'who@users.noreply.github.com', 'subject': 'o/r#7 Crash on startup',
                'body': head + chr(10) + 'Traceback ... KeyError'}

    HEADS = ('[pull request by priya-dev - association: CONTRIBUTOR]',
             '[pull request by new - association: FIRST_TIME_CONTRIBUTOR]',
             '[issue by ldbumble - association: OWNER]')

    def test_no_gate_answers_for_the_classifier(self):
        for head in self.HEADS:
            self.assertIsNone(ingest.decided_intent(self._gh(head)), head)

    def test_a_pull_request_the_model_calls_coding_reaches_the_coder(self):
        """The verdict travels: kind -> Kind on the task -> the coder's own role."""
        for head in self.HEADS:
            store = MemoryStore()
            out = ingest.ingest_message(
                store, self._gh(head),
                llm=lambda *a, **k: '{"intent": "task", "kind": "coding", "why": "a pull request asks for review"}')
            self.assertEqual(out['status'], 'created', head)
            t = store.get_task(out['task_id'])
            self.assertEqual((t['Kind'], t['Assignee']), ('coding', 'agent:coder'), head)

    def test_the_shipped_rule_tells_the_model_a_pr_is_coding(self):
        """The gate is gone, so TRIAGE.md is the only thing left saying this - if the wording is
        ever softened again, every PR silently goes back to the assistant."""
        from pathlib import Path
        import taskuary
        doc = (Path(taskuary.__file__).parent / 'templates' / 'triage.md').read_text(encoding='utf-8')
        self.assertIn('A PULL REQUEST is a task, and its kind is coding', doc)
        self.assertNotIn("A stranger's pull request or issue is fyi", doc)

    def test_somebody_elses_issue_is_still_the_models_call(self):
        for head in ('[issue by kai - association: NONE]', '[issue by pat - association: MEMBER]'):
            self.assertIsNone(ingest.decided_intent(self._gh(head)), head)

    def test_mail_is_still_the_models_call(self):
        self.assertIsNone(ingest.decided_intent({'channel': 'email', 'subject': 'Ledger', 'body': 'Can you check the ledger?'}))
        self.assertEqual(ingest.decided_intent({'channel': 'email', 'subject': 'Statement ready',
                                                'body': 'This is an automated message, do not reply.'})['intent'], 'fyi')
