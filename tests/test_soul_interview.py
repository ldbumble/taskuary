"""SOUL.md is learned through one adaptive seven-turn conversation, not a fixed IT form."""
import json
import unittest
from unittest import mock

from taskuary import interview
from taskuary.store import MemoryStore

HEADINGS = ('## What counts as a task', '## How we respond', '## Escalate (a human decides) when',
            '## Systems and repositories', '## People')
LEGACY_ANSWERS = {'who': 'Dana Whitfield, operations director at a nursing-home group',
                  'never': 'nothing that touches payroll or resident data, ever',
                  'systems': 'Sage Intacct and the scheduling records'}
TRANSCRIPT = [
    {'q': 'What should I understand about you and the world you work in?',
     'a': 'I run a community theatre with volunteers and a very small budget.'},
    {'q': 'Which parts of running the theatre most need help?',
     'a': 'Keeping rehearsals, front of house, and grant deadlines from colliding.'},
]


class TheSkillTests(unittest.TestCase):
    def test_the_behavior_lives_in_a_real_skill_file(self):
        text = interview.skill_text()
        self.assertTrue(text.startswith('---\nname: soul-interview'))
        self.assertIn('Ask exactly seven user-facing questions, one at a time', text)
        self.assertIn('Generate questions 2–7 from the full transcript', text)

    def test_it_does_not_assume_the_owner_writes_code(self):
        text = interview.skill_text()
        self.assertIn('Never ask specifically about code', text)
        self.assertIn('unless the person', text)
        self.assertEqual(interview.TOTAL_QUESTIONS, 7)

    def test_the_approval_gate_is_fixed_not_an_interview_choice(self):
        text = interview.skill_text()
        self.assertIn('approval gate is a system rule', text)
        self.assertIn('Never ask the owner which outbound actions may bypass approval', text)
        self.assertIn('SOUL.md cannot create an exception', text)

    def test_people_and_project_routing_are_two_different_kinds_of_memory(self):
        text = interview.skill_text()
        self.assertIn('who the owner answers to', text)
        self.assertIn('Message frequency is context, not proof', text)
        self.assertIn('separate structured memory maintained by Taskuary', text)
        self.assertIn("owner's explicit routing", text)

    def test_what_the_app_can_already_see_is_supplied_as_context(self):
        s = MemoryStore()
        s.set_setting('owner', 'Uri', 'o')
        ctx = interview.context(s)
        self.assertEqual(ctx['owner'], 'Uri')
        self.assertEqual(sorted(ctx.keys()), ['channels', 'owner', 'repos', 'roles', 'writes_most'])


class AdaptiveQuestionTests(unittest.TestCase):
    def test_the_first_question_is_generated_by_the_assistant(self):
        seen = {}
        def llm(system, user, **kw):
            seen.update(system=system, user=user, kw=kw)
            return json.dumps({'q': 'What should I understand about your life and work?',
                               'why': 'This gives the rest of the interview its direction.',
                               'placeholder': 'The responsibilities, people, or goals that shape your days'})
        question = interview.next_question(MemoryStore(), [], llm=llm)
        self.assertEqual(question['number'], 1)
        self.assertEqual(question['total'], 7)
        self.assertIn('QUESTION NUMBER: 1 OF 7', seen['user'])
        self.assertIn('Start broad', seen['system'])

    def test_each_next_question_receives_every_previous_answer(self):
        seen = {}
        def llm(_system, user, **_kw):
            seen['user'] = user
            return ('```json\n{"q":"When rehearsal and grant deadlines collide, which wins?",'
                    '"why":"You named that collision as the recurring pressure point.",'
                    '"placeholder":"For example, opening night may be immovable"}\n```')
        question = interview.next_question(MemoryStore(), TRANSCRIPT, llm=llm)
        self.assertEqual(question['number'], 3)
        self.assertIn('community theatre', seen['user'])
        self.assertIn('grant deadlines', seen['user'])
        self.assertIn('When rehearsal and grant deadlines collide', question['q'])

    def test_it_stops_after_exactly_seven_questions(self):
        seven = [{'q': f'Question {i}?', 'a': f'Answer {i}'} for i in range(1, 8)]
        with self.assertRaisesRegex(ValueError, 'seven'):
            interview.next_question(MemoryStore(), seven, llm=lambda *_a, **_k: '{}')

    def test_it_requires_an_assistant_instead_of_falling_back_to_fixed_questions(self):
        with mock.patch('taskuary.interview._brain', return_value=None):
            with self.assertRaisesRegex(ValueError, 'AI assistant'):
                interview.next_question(MemoryStore(), [])


class WritingTests(unittest.TestCase):
    def test_the_model_gets_the_full_conversation_and_known_context(self):
        s = MemoryStore(); s.set_setting('owner', 'Uri', 'o')
        seen = {}
        def llm(system, user, **kw):
            seen.update(system=system, user=user)
            return "# SOUL.md - the operator's document\n\nWritten."
        interview.draft(s, TRANSCRIPT, llm=llm)
        self.assertIn('community theatre', seen['user'])
        self.assertIn('grant deadlines', seen['user'])
        self.assertIn('Owner name on file: Uri', seen['user'])
        self.assertIn('MODE: WRITE_SOUL', seen['user'])
        for heading in HEADINGS: self.assertIn(heading, seen['system'])
        self.assertIn('Never add a policy', seen['system'])

    def test_a_model_that_fences_its_answer_does_not_fence_the_document(self):
        body = interview.draft(MemoryStore(), TRANSCRIPT,
                               llm=lambda *_a, **_k: '```markdown\n# SOUL.md\n\nx\n```')
        self.assertFalse(body.startswith('`')); self.assertFalse(body.endswith('`'))

    def test_an_empty_interview_is_refused(self):
        for empty in ([], {}, [{'q': 'Anything?', 'a': '   '}], {'who': '   '}):
            with self.assertRaises(ValueError): interview.draft(MemoryStore(), empty, llm=lambda *_a, **_k: '')

    def test_an_adaptive_interview_is_not_silently_flattened_without_its_assistant(self):
        with mock.patch('taskuary.interview._brain', return_value=None):
            with self.assertRaisesRegex(ValueError, 'no longer available'):
                interview.draft(MemoryStore(), TRANSCRIPT)

    def test_old_clients_keep_the_safe_plain_fallback(self):
        with mock.patch('taskuary.interview._brain', return_value=None):
            body = interview.draft(MemoryStore(), LEGACY_ANSWERS)
        for heading in HEADINGS: self.assertIn(heading, body)
        self.assertIn('Dana Whitfield', body)
        self.assertIn('payroll', body)
        self.assertIn('Nothing sends or ships without', body)

    def test_write_saves_the_document_and_leaves_a_receipt(self):
        s = MemoryStore()
        interview.write(s, TRANSCRIPT, 'owner', llm=lambda *_a, **_k: "# SOUL.md - the operator's document")
        self.assertIn('SOUL.md', s.get_doc('soul') or '')
        receipt = next(a for a in s.list_audit('doc', 0) if a['Action'] == 'soul_interview')
        self.assertIn('adaptive', receipt['Detail'])

    def test_write_cannot_erase_or_invent_managed_relationship_sections(self):
        s = MemoryStore()
        s.save_doc('soul', """# SOUL.md - the operator's document

## Connected systems
<!-- connections:start -->
- stale generated line
<!-- connections:end -->

## Project relationships
<!-- projects:start -->
- stale generated relationship
<!-- projects:end -->

## Repository map
- **noble/app**: Owner's routing note that must survive.
""", 'owner')
        pid = s.ensure_project('Noble', actor='owner')
        s.upsert_project_link(pid, 'repository', 'noble/app', 'noble/app', 1, True, 'owner')
        s.upsert_project_link(pid, 'email', 'rene@noble.example', 'Rene Gomez', .86, False, 'repo_choice')
        made_up = """# SOUL.md - the operator's document

New interview prose.

## Project relationships
- **Wrong** - invented by the model

## Repository map
- **wrong/repo**: invented by the model
"""
        interview.write(s, TRANSCRIPT, 'owner', llm=lambda *_a, **_k: made_up)
        soul = s.get_doc('soul') or ''
        self.assertIn('New interview prose.', soul)
        self.assertIn('<!-- connections:start -->', soul)
        self.assertIn("**noble/app**: Owner's routing note that must survive.", soul)
        self.assertIn('Rene Gomez (email)', soul)
        self.assertNotIn('invented by the model', soul)


class OverTheApiTests(unittest.TestCase):
    def test_context_next_question_and_writing_have_separate_contracts(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        client = TestClient(server.app)
        context = client.get('/api/soul/interview').json()
        self.assertEqual(context['total'], 7)
        self.assertNotIn('questions', context)
        made = {'number': 1, 'total': 7, 'q': 'What matters?', 'why': 'To begin.', 'placeholder': ''}
        with mock.patch('taskuary.interview.next_question', return_value=made):
            response = client.post('/api/soul/interview/next', json={'answers': []})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['question']['q'], 'What matters?')

    def test_an_empty_final_interview_is_still_refused(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        response = TestClient(server.app).post('/api/soul/interview', json={'answers': []})
        self.assertEqual(response.status_code, 422)


if __name__ == '__main__':
    unittest.main()
