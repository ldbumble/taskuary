"""SOUL.md, asked for rather than guessed.

STYLE.md and TRIAGE.md bootstrap from history - the owner's sent mail IS how they write, their
verdicts ARE what they count as work. SOUL.md cannot: who you answer for, what an agent may
never decide alone, which systems are yours, who outranks whom. None of that is in a mailbox,
so until somebody says it the document is about a stranger called John Smith.

What is pinned here is the part that can quietly rot: that the document keeps the headings the
rest of the app reads, that a machine with no AI still gets a usable one, and that nothing the
owner did not say is invented for them.
"""
import unittest
from unittest import mock

from taskuary import interview
from taskuary.store import MemoryStore

HEADINGS = ('## What counts as a task', '## How we respond', '## Escalate (a human decides) when',
            '## Systems and repositories', '## People')
ANSWERS = {'who': 'Dana Whitfield, IT director at a nursing-home group',
           'never': 'nothing that touches payroll or resident data, ever',
           'systems': 'Sage Intacct, our Entra tenant'}


class TheQuestionsTests(unittest.TestCase):
    def test_every_question_says_why_it_is_being_asked(self):
        """A form that explains itself gets answered; one that does not gets abandoned."""
        for q in interview.QUESTIONS:
            self.assertTrue(q['q'].endswith('?'), q['key'])
            self.assertGreater(len(q['why']), 40, q['key'])
            self.assertTrue(q['placeholder'], q['key'])

    def test_it_is_short_enough_that_somebody_finishes_it(self):
        self.assertLessEqual(len(interview.QUESTIONS), 8)
        self.assertEqual(len({q['key'] for q in interview.QUESTIONS}), len(interview.QUESTIONS))

    def test_it_asks_the_two_that_decide_everything_else(self):
        keys = {q['key'] for q in interview.QUESTIONS}
        self.assertIn('who', keys)          # who is being signed for
        self.assertIn('never', keys)        # ...and the line an agent may not cross

    def test_what_the_app_can_already_see_is_not_asked_for(self):
        s = MemoryStore()
        s.set_setting('owner', 'Uri', 'o')
        ctx = interview.context(s)
        self.assertEqual(ctx['owner'], 'Uri')
        self.assertEqual(sorted(ctx.keys()), ['channels', 'owner', 'repos', 'roles', 'writes_most'])


class WithNoAiTests(unittest.TestCase):
    """A machine with no AI connector still gets a document out of its own answers."""
    def test_the_answers_are_laid_into_the_template_shape(self):
        body = interview.draft(MemoryStore(), ANSWERS, llm=None)
        for h in HEADINGS: self.assertIn(h, body)
        self.assertIn('Dana Whitfield', body)
        self.assertIn('payroll', body)

    def test_the_standing_promise_survives_even_the_plain_one(self):
        self.assertIn('Nothing sends or ships without', interview.draft(MemoryStore(), ANSWERS, llm=None))

    def test_an_unanswered_question_falls_back_and_never_invents(self):
        body = interview.draft(MemoryStore(), {'who': 'Uri'}, llm=None)
        self.assertIn('## People', body)
        self.assertIn('(not stated)', body)

    def test_an_empty_interview_is_refused_rather_than_written(self):
        for empty in ({}, {'who': '   '}, {'nonsense': 'x'}):
            with self.assertRaises(ValueError): interview.draft(MemoryStore(), empty, llm=None)


class WithAnAiTests(unittest.TestCase):
    def test_the_model_is_given_the_answers_and_what_the_app_sees(self):
        s = MemoryStore()
        s.set_setting('owner', 'Uri', 'o')
        seen = {}
        def llm(system, user, **kw):
            seen.update(system=system, user=user)
            return '# SOUL.md - the operator\'s document\n\nWritten.'
        interview.draft(s, ANSWERS, llm=llm)
        self.assertIn('nursing-home group', seen['user'])          # their words
        self.assertIn('Owner name on file: Uri', seen['user'])     # ...and the facts
        for h in HEADINGS: self.assertIn(h, seen['system'])        # the headings it must keep
        self.assertIn('Nothing they did NOT say may appear as fact', seen['system'])

    def test_a_model_that_fences_its_answer_does_not_fence_the_document(self):
        body = interview.draft(MemoryStore(), ANSWERS, llm=lambda *a, **k: '```markdown\n# SOUL.md\n\nx\n```')
        self.assertFalse(body.startswith('`'))
        self.assertFalse(body.endswith('`'))

    def test_a_model_that_answers_with_nothing_falls_back_to_the_owners_own_words(self):
        body = interview.draft(MemoryStore(), ANSWERS, llm=lambda *a, **k: '   ')
        self.assertIn('Dana Whitfield', body)
        self.assertIn('## People', body)


class WritingItTests(unittest.TestCase):
    def test_it_saves_the_document_and_leaves_a_receipt(self):
        s = MemoryStore()
        interview.write(s, ANSWERS, 'owner', llm=None)
        self.assertIn('Dana Whitfield', s.get_doc('soul') or '')
        self.assertTrue(any(a['Action'] == 'soul_interview' for a in s.list_audit('doc', 0)))

    def test_it_replaces_the_stranger_the_template_ships_with(self):
        s = MemoryStore()
        self.assertIn('John Smith', s.get_doc('soul') or '')       # the shipped template
        interview.write(s, ANSWERS, 'owner', llm=None)
        self.assertNotIn('John Smith', s.get_doc('soul') or '')


class OverTheApiTests(unittest.TestCase):
    def test_the_questions_and_the_writing_are_one_endpoint_each(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        c = TestClient(server.app)
        q = c.get('/api/soul/interview').json()
        self.assertEqual(len(q['questions']), len(interview.QUESTIONS))
        self.assertEqual(c.post('/api/soul/interview', json={'answers': {}}).status_code, 422)
        r = c.post('/api/soul/interview', json={'answers': {'who': 'Uri, IT director'}})
        self.assertEqual(r.status_code, 200)
        self.assertIn('Uri', r.json()['doc'])


if __name__ == '__main__':
    unittest.main()
