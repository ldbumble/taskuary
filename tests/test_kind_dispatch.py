"""`kind` routes the task, and triage is the only thing that decides it.

Owner, 2026-08-30 (TQ-0253), after a CyberHoot training reminder got a full coder run and a
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

from taskuary import senders
from taskuary.ingest import auto_code_ok, ingest_message
from taskuary.store import MemoryStore

NOTICE = ('Your assignment "Common Scams and How to Avoid Them" is outstanding, due 2026-09-06. '
          'Please complete it.\nYou are receiving this email because you are enrolled.')


def llm_says(kind):
    return lambda sy, u: '{"intent": "task", "kind": "%s", "why": "w"}' % kind


def mail(**kw):
    base = {'external_id': 'x1', 'channel': 'email', 'subject': 'Outstanding Assignment', 'body': NOTICE,
            'from_email': 'hoots@cyberhoot.com', 'from_name': 'CyberHoot', 'conversation_id': None,
            'sent_at': '2026-08-30 09:00', 'source_link': None, 'source_name': 'dana@northwind.example'}
    return {**base, **kw}


def store():
    s = MemoryStore()
    s.set_setting('coder_auto_enabled', '1', 't')
    s.set_setting('owner_email', 'dana@northwind.example', 't')
    return s


def ingested(s, m, kind):
    with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True):
        out = ingest_message(s, m, llm=llm_says(kind))
    return out, [getattr(c[0][0], '__name__', '') for c in spawn.call_args_list]


class DispatchTests(unittest.TestCase):
    def test_general_makes_the_task_and_opens_no_session(self):
        """general is the ASSISTANT'S CHAT now, not "only you can do it" - so nothing is spawned
        and the route line says where it went, instead of apologising for an agent that was never
        going to start."""
        s = store()
        out, spawned = ingested(s, mail(), 'general')
        t = s.get_task(out['task_id'])
        self.assertEqual((t['Kind'], t['Status']), ('general', 'open'))      # a real task, on the Board
        self.assertEqual(spawned, [])
        reason = s._rows('SELECT * FROM route ORDER BY RouteId DESC')[0]['Reason']
        self.assertIn('talk it through with the assistant', reason)
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
        """Nothing looks at the SENDER any more. The identical CyberHoot address gets an agent
        the moment triage says the work is keyboard work - that judgement is TRIAGE.md's alone."""
        s = store()
        _out, spawned = ingested(s, mail(external_id='r1'), 'coding')
        self.assertEqual(spawned, ['_auto_code'])

    def test_a_person_asking_for_something_no_agent_can_do_also_waits(self):
        """And it cuts the other way: a colleague asking you to attend a meeting is general."""
        s = store()
        _out, spawned = ingested(s, mail(external_id='p1', from_email='teammate@northwind.example', from_name='Sam',
                                         subject='board meeting', body='Can you sit in on the board meeting Thursday?'),
                                 'general')
        self.assertEqual(spawned, [])

    def test_general_skips_the_sent_items_search(self):
        """A task already staying on the Board should not pay for a mailbox round-trip."""
        s = store()
        with mock.patch('taskuary.ingest._spawn'), mock.patch.object(senders, 'wrote_to') as wrote:
            ingest_message(s, mail(external_id='n1'), llm=llm_says('general'))
        wrote.assert_not_called()


class GateTests(unittest.TestCase):
    """auto_code_ok on its own: one question about the work, then the stranger check."""
    def _mid(self, s, from_email):
        return s.add_message({'ExternalId': 'x', 'Channel': 'email', 'Subject': 's', 'FromEmail': from_email,
                              'SentAt': '2026-08-30 09:00', 'BodyText': NOTICE, 'Status': 'routed'})

    def test_general_is_refused_without_asking_anything_else(self):
        s = store()
        with mock.patch.object(senders, 'known') as known:
            ok, why = auto_code_ok(s, {'channel': 'email', 'from_email': 'a@b.c'}, self._mid(s, 'a@b.c'), 'general')
        known.assert_not_called()
        self.assertEqual((ok, 'talk it through with the assistant' in why), (False, True))

    def test_coding_falls_through_to_the_stranger_gate(self):
        s = store()
        with mock.patch.object(senders, 'wrote_to', return_value=False):
            ok, why = auto_code_ok(s, {'channel': 'email', 'from_email': 'stranger@evil.example'},
                                   self._mid(s, 'stranger@evil.example'), 'coding')
        self.assertEqual((ok, 'never written to them' in why), (False, True))
        with mock.patch.object(senders, 'wrote_to', return_value=True):
            ok, _why = auto_code_ok(s, {'channel': 'email', 'from_email': 'client@partner.example'},
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
            self.assertIn('from a keyboard', low, name)                   # the one test coding has to pass
            self.assertIn('say coding', low, name)                        # the tie-break, both ways
            # three destinations, named in both - a kind the doc does not describe is a kind the
            # model will not answer, and the router would then route on a value nothing produced
            for k in ('coding', 'general', 'task'):
                self.assertIn(k, low, f'{name} must name {k}')
            self.assertIn('almost every task goes to the coding agent', low, name)
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
        """auto_code_ok reads `kind` and the sender's history. If a keyword or category test ever
        creeps back in beside them, the document stops being where this is decided."""
        import inspect
        from taskuary import ingest
        src = inspect.getsource(ingest.auto_code_ok)
        self.assertIn("kind != 'coding'", src)
        for leak in ('sender_class', 'BODY_', 'FROM_', 're.search', 'subject'):
            self.assertNotIn(leak, src, leak)


class SettledVerdictTests(unittest.TestCase):
    """The owner's three verdict marks do not mean the same thing.

    "Not a coding task" is the button for real work they are KEEPING - server.not_coding writes
    NOT A CODING TASK and takes the agent off. Two of those on a topic used to settle it as fyi
    along with NOT OURS and NOT A TASK, which drops a job the owner had just claimed. It is also
    the mark most likely to pile up now, since general is the exception this all exists for.
    """
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

    def test_not_a_coding_task_settles_as_work_you_keep(self):
        s = self._system_for(self._notes('NOT A CODING TASK'))
        self.assertIn('Answer task with kind task', s)
        self.assertIn('never fyi', s)

    def test_the_other_two_still_settle_as_fyi(self):
        for mark in ('NOT OURS', 'NOT A TASK'):
            s = self._system_for(self._notes(mark))
            self.assertIn('Answer fyi - no exceptions', s, mark)
            self.assertNotIn('kind general', s, mark)

    def test_marks_that_disagree_settle_nothing(self):
        from taskuary.triage import _agreement
        self.assertEqual(_agreement(['x - NOT OURS: a', 'y - NOT A CODING TASK: b']), ())
        self.assertEqual(_agreement(['x - NOT OURS: a']), ())              # one is not agreement
        self.assertEqual(_agreement(['just a note the owner typed', 'another one']), ())

    def test_the_longer_mark_wins_the_match(self):
        """NOT A CODING TASK must not be read as a NOT A TASK with words around it."""
        from taskuary.triage import _agreement
        self.assertEqual(_agreement(self._notes('NOT A CODING TASK'))[0], 'NOT A CODING TASK')


if __name__ == '__main__':
    unittest.main()
