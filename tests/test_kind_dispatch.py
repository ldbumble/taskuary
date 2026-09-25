"""`kind` routes the task, and triage is the only thing that decides it.

Owner, 2026-08-30 (TQ-0253), after a PhishGuard training reminder got a full coder run and a
drafted reply back to the mailer: the exception to everything-goes-to-the-agent is not "an
automated sender", it is "clearly not a coding job" - and it belongs in TRIAGE.md, not in a
hardcoded rule. So there is exactly one gate on the work: coding starts a session, general
lands on the Board and waits for a click. No keyword, sender or category test anywhere else
gets a second opinion.

The training reminder is still a real task - it is due, somebody has to sit the course - it is
just `general`, because no amount of typing does it.
"""
import unittest
from unittest import mock

from taskuary import general, senders
from taskuary.ingest import auto_start_ok, ingest_message
from taskuary.store import MemoryStore

NOTICE = ('Your assignment "Common Scams and How to Avoid Them" is outstanding, due 2026-09-06. '
          'Please complete it.\nYou are receiving this email because you are enrolled.')


def llm_says(kind):
    return lambda sy, u: '{"intent": "task", "kind": "%s", "why": "w"}' % kind


def mail(**kw):
    base = {'external_id': 'x1', 'channel': 'email', 'subject': 'Outstanding Assignment', 'body': NOTICE,
            'from_email': 'alerts@phishguard.example', 'from_name': 'PhishGuard', 'conversation_id': None,
            'sent_at': '2026-08-30 09:00', 'source_link': None, 'source_name': 'dana@northwind.example'}
    return {**base, **kw}


def store():
    s = MemoryStore()
    s.set_setting('coder_auto_enabled', '1', 't')
    s.set_setting('owner_email', 'dana@northwind.example', 't')
    return s


def ingested(s, m, kind):
    with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):   # an assistant is configured (PW-071)
        out = ingest_message(s, m, llm=llm_says(kind))
    return out, [getattr(c[0][0], '__name__', '') for c in spawn.call_args_list]


class DispatchTests(unittest.TestCase):
    def test_general_makes_the_task_and_opens_the_assistant_not_a_cli(self):
        """general is the ASSISTANT'S work: since PW-069 (owner, 2026-09-05) it starts its own assistant
        session by default - never a coding CLI - and the route line says where it went."""
        s = store()
        out, spawned = ingested(s, mail(), 'general')
        t = s.get_task(out['task_id'])
        self.assertEqual((t['Kind'], t['Status']), ('general', 'open'))      # a real task, on the Board
        self.assertEqual(spawned, ['_auto_general'])
        reason = s._rows('SELECT * FROM route ORDER BY RouteId DESC')[0]['Reason']
        self.assertIn('sent to the assistant', reason)
        self.assertNotIn('sent to the coding agent', reason)                 # it was not

    def test_a_plain_task_is_nobodys_but_yours(self):
        s = store()
        out, spawned = ingested(s, mail(), 'task')
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'task')
        self.assertEqual(spawned, [])
        reason = s._rows('SELECT * FROM route ORDER BY RouteId DESC')[0]['Reason']
        self.assertIn('yours to do', reason)
        self.assertNotIn('sent to the coding agent', reason)

    def test_coding_still_goes_straight_to_the_agent(self):
        """The rule that must not move: err toward the agent for anything a keyboard can do."""
        s = store()
        _out, spawned = ingested(s, mail(external_id='c1', subject='the importer is down',
                                         body='the importer throws in jobs/import.py'), 'coding')
        self.assertEqual(spawned, ['_auto_code'])

    def test_the_same_robot_dispatches_when_triage_calls_it_coding(self):
        """Nothing looks at the SENDER any more. The identical PhishGuard address gets an agent
        the moment triage says the work is keyboard work - that judgement is TRIAGE.md's alone."""
        s = store()
        _out, spawned = ingested(s, mail(external_id='r1'), 'coding')
        self.assertEqual(spawned, ['_auto_code'])

    def test_a_person_asking_for_something_no_agent_can_do_also_gets_no_cli(self):
        """And it cuts the other way: a colleague asking you to attend a meeting is general - the
        assistant, not a coder (PW-069)."""
        s = store()
        _out, spawned = ingested(s, mail(external_id='p1', from_email='teammate@northwind.example', from_name='Sam',
                                         subject='board meeting', body='Can you sit in on the board meeting Thursday?'),
                                 'general')
        self.assertEqual(spawned, ['_auto_general'])

    def test_a_general_task_that_will_not_start_skips_the_sent_items_search(self):
        """A task already staying on the Board should not pay for a mailbox round-trip: with the
        assistant's auto-start off (PW-070) the stranger gate is never asked."""
        s = store(); s.set_setting('general_auto_enabled', '0', 't')
        with mock.patch('taskuary.ingest._spawn'), mock.patch.object(senders, 'wrote_to') as wrote:
            ingest_message(s, mail(external_id='n1'), llm=llm_says('general'))
        wrote.assert_not_called()


class GateTests(unittest.TestCase):
    """auto_start_ok, the one gate that decides an unattended start: the switch, then the stranger check. (The old
    coding-only auto_code_ok was never called outside its tests and is gone - X4, 2026-09-25.)"""
    def _mid(self, s, from_email):
        return s.add_message({'ExternalId': 'x', 'Channel': 'email', 'Subject': 's', 'FromEmail': from_email,
                              'SentAt': '2026-08-30 09:00', 'BodyText': NOTICE, 'Status': 'routed'})

    def test_coding_falls_through_to_the_stranger_gate(self):
        s = store(); s.set_setting('coder_auto_enabled', '1', 't')
        with mock.patch.object(senders, 'wrote_to', return_value=False):
            ok, why = auto_start_ok(s, {'channel': 'email', 'from_email': 'stranger@evil.example'},
                                    self._mid(s, 'stranger@evil.example'), 'coding')
        self.assertEqual((ok, 'never written to them' in why), (False, True))
        with mock.patch.object(senders, 'wrote_to', return_value=True):
            ok, _why = auto_start_ok(s, {'channel': 'email', 'from_email': 'client@partner.example'},
                                     self._mid(s, 'client@partner.example'), 'coding')
        self.assertTrue(ok)


class ConsistencyTests(unittest.TestCase):
    """The two documents that state these rules must not disagree: TRIAGE.md is what the owner
    edits, INTENT_SYSTEM is what runs when they blank it."""
    def test_both_prompts_make_kind_the_routing_decision(self):
        from pathlib import Path
        import taskuary
        from taskuary.triage import INTENT_SYSTEM
        doc = (Path(taskuary.__file__).parent / 'templates' / 'triage.md').read_text(encoding='utf-8')
        for text, name in ((doc, 'triage.md'), (INTENT_SYSTEM, 'INTENT_SYSTEM')):
            low = text.lower()
            # the one test coding has to pass: the work happens INSIDE a system this install holds
            self.assertIn('holds the code or the credentials for', low, name)
            self.assertIn('say task', low, name)                          # the tie-break (2026-09-23; was general, PW-067)
            # three destinations, named in both - a kind the doc does not describe is a kind the
            # model will not answer, and the router would then route on a value nothing produced
            for k in ('coding', 'general', 'task'):
                self.assertIn(k, low, f'{name} must name {k}')
            # never coding by default (the owner, 2026-09-23: "i don't like coding by default"), and a
            # repository that only matches the topic is not a reason (TQ-0694)
            self.assertNotIn('almost every task goes to the coding agent', low, name)
            self.assertNotIn('this is the default', low, name)
            self.assertIn('never coding', low, name)
            # the two claims that used to contradict the rest of the document
            self.assertNotIn('and every task goes to the coding agent', low, name)
            self.assertNotIn('not a routing decision', low, name)

    def test_neither_prompt_keys_the_exception_on_the_sender(self):
        """The owner's correction (2026-08-30): the exception is the WORK, not who sent it.
        A sender rule here would be a second opinion nobody could argue with."""
        from pathlib import Path
        import taskuary
        from taskuary.triage import INTENT_SYSTEM
        doc = (Path(taskuary.__file__).parent / 'templates' / 'triage.md').read_text(encoding='utf-8')
        for text, name in ((doc, 'triage.md'), (INTENT_SYSTEM, 'INTENT_SYSTEM')):
            for phrase in ('from a machine', 'from a person goes to the coding agent', 'automated sender'):
                self.assertNotIn(phrase, text.lower(), f'{name}: {phrase}')

    def test_the_code_asks_triage_and_nothing_else(self):
        """auto_start_ok reads the switch and the sender's history. If a keyword or category test ever
        creeps back in beside them, the document stops being where this is decided."""
        import inspect
        from taskuary import ingest
        self.assertFalse(hasattr(ingest, 'auto_code_ok'))
        src = inspect.getsource(ingest.auto_start_ok)
        for leak in ('sender_class', 'BODY_', 'FROM_', 're.search', 'subject'):
            self.assertNotIn(leak, src, leak)


class VerdictMarksAreEvidenceTests(unittest.TestCase):
    """The owner's verdict marks - NOT A CODING TASK, NOT OURS, NOT A TASK - reach the classifier
    as dated evidence and nothing more. Two agreeing marks used to become an order ("SETTLED BY
    YOUR OWNER ... no exceptions"), which decided a new message unread; PW-025 (2026-09-06)
    replaces the order with the evidence the model already had. The marks still differ in
    meaning, and the EVIDENCE lines carry each one verbatim for the model to weigh."""
    def _system_for(self, notes):
        from taskuary.triage import classify_intent
        seen = {}
        def llm(system, user, **kw):
            seen['s'] = system
            return '{"intent": "task", "kind": "general", "why": "w"}'
        classify_intent({'subject': 's', 'body': 'b', 'from_email': 'a@b.c'}, llm=llm, notes=notes)
        return seen['s']

    def _notes(self, mark, n=2):
        return [f'2026-08-{20 + i}: "Thing {i}" from a@b.c - {mark}: because' for i in range(n)]

    def test_agreeing_marks_are_shown_verbatim_and_order_nothing(self):
        for mark in ('NOT A CODING TASK', 'NOT OURS', 'NOT A TASK'):
            s = self._system_for(self._notes(mark))
            self.assertIn('EVIDENCE', s, mark)
            for n in self._notes(mark): self.assertIn(n, s, mark)
            self.assertNotIn('SETTLED BY YOUR OWNER', s, mark)
            self.assertNotIn('no exceptions', s, mark)


if __name__ == '__main__':
    unittest.main()


class CodingIsNotTheDefaultMigrationTests(unittest.TestCase):
    """An owner's TRIAGE.md that stopped tracking the template gets the kind rules swapped once, in place."""
    def test_the_shipped_paragraphs_are_swapped_and_nothing_else(self):
        import os, tempfile
        from taskuary import store as store_mod
        from taskuary.store import SQLiteStore
        p = os.path.join(tempfile.mkdtemp(), 't.db')
        old = 'MY OWN RULE: Erin is always urgent.\n\n' + '\n\n'.join(w for w, _n in store_mod._KIND_RULES) + '\n\nMy last line.'
        s = SQLiteStore(p); s.save_doc('triage', old, 'owner')
        s.cx.execute("DELETE FROM setting WHERE Name='triage_coding_not_default'"); s.cx.commit(); s.cx.close()
        after = SQLiteStore(p).doc('triage')
        for was, now in store_mod._KIND_RULES:
            self.assertIn(now, after)
            if was not in now: self.assertNotIn(was, after)                 # the general rule only grows a sentence
        self.assertIn('MY OWN RULE: Erin is always urgent.', after); self.assertIn('My last line.', after)

    def test_an_unnamed_kind_is_the_owners_list(self):
        from taskuary.routing import draft_task_fields
        self.assertEqual(draft_task_fields({'subject': 'Valley BAI feed', 'body': 'Kevin still has not started the feed.'})['kind'], 'task')
