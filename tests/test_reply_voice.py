"""The reply goes out over the owner's name, so it has to be written in the owner's person.

The reported draft, verbatim:

    Hi Meyy -
    I can't suggest times by email alone; Uri will need to handle scheduling directly.
    Sincerely,
    Uri J Whitfield

Third person about the sender, first person about a tool's limitations, signed by the
sender. It came straight from the prompt: "You write {owner}'s replies" cast the model as
the owner's ASSISTANT, and every injected block ("how {owner} writes", "Standing notes from
the owner", SOUL.md's own "You work for **{owner}**") kept it there. So it wrote what an
assistant would write and then signed somebody else's name to it.
"""
import unittest
from datetime import date
from unittest import mock

from taskuary import responder, triage
from taskuary.store import MemoryStore

OWNER = 'Uri J Whitfield'


def _capture(store, task_id):
    """Draft with a fake brain that records the system prompt instead of answering."""
    seen = {}
    def llm(system, user, **kw):
        seen['system'], seen['user'] = system, user
        return 'I will send times this afternoon.'
    responder.draft_reply(store, task_id, llm=llm)
    return seen


class VoiceTests(unittest.TestCase):
    def _store(self):
        s = MemoryStore()
        s.save_doc('soul', f'You work for **{OWNER}**. He runs finance systems.', 'owner')
        tid = s.create_task({'Title': 'Scheduling', 'Kind': 'reply'}, 'o')
        s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'Times?', 'FromName': 'Meyy',
                       'FromEmail': 'meyy@partner.example', 'ExternalId': 'v1',
                       'BodyText': 'Can you suggest a few times next week?'})
        return s, tid

    def test_the_model_is_told_it_IS_the_owner_not_that_it_works_for_them(self):
        s, tid = self._store()
        sys_ = _capture(s, tid)['system']
        self.assertIn(f'You ARE {OWNER}', sys_)
        self.assertNotIn(f"You write {OWNER}'s replies", sys_)

    def test_third_person_is_named_as_the_mistake_to_avoid(self):
        s, tid = self._store()
        sys_ = _capture(s, tid)['system']
        self.assertIn('FIRST PERSON', sys_)
        self.assertIn('third person', sys_)

    def test_assistant_voice_is_ruled_out_explicitly(self):
        """"I can't suggest times by email alone" is an AI reporting its own limits over a
        human's signature. Nothing in the old prompt forbade it."""
        s, tid = self._store()
        sys_ = _capture(s, tid)['system']
        self.assertIn('not an assistant', sys_)
        self.assertIn('what you can or cannot do', sys_)

    def test_the_soul_document_is_handed_over_as_the_writers_OWN(self):
        """SOUL.md says "You work for X" - correct for a coding agent, poison here. It rides in
        either way (it carries the voice), so the seam has to disarm it."""
        s, tid = self._store()
        sys_ = _capture(s, tid)['system']
        self.assertIn('YOUR OWN document', sys_)
        self.assertIn(f'you work for {OWNER}', sys_)          # named, so the model knows to discount it
        self.assertIn('describing you', sys_)
        self.assertIn('He runs finance systems', sys_)        # the document itself still arrives

    def test_standing_notes_are_the_writers_own_notes(self):
        """...and since PW-060 only WRITING instructions ride into a reply: a triage verdict about the
        sender is routing, not voice, and stays out."""
        s, tid = self._store()
        s.add_memory({'Scope': 'global', 'ScopeKey': None, 'Active': 1, 'Source': 'writing',
                      'Note': 'Keep it to two sentences for Meyy.', 'CreatedBy': 'o'})
        s.add_memory({'Scope': 'sender', 'ScopeKey': 'meyy@partner.example', 'Active': 1, 'Source': 'verdict',
                      'Note': 'Meyy schedules for the whole vendor team.', 'CreatedBy': 'o'})
        sys_ = _capture(s, tid)['system']
        self.assertIn('Your own writing instructions', sys_); self.assertIn('two sentences for Meyy', sys_)
        self.assertNotIn('Standing notes from the owner', sys_)
        self.assertNotIn('schedules for the whole vendor team', sys_)

    def test_work_that_needs_doing_is_answered_in_the_first_person(self):
        """The old line told the model "the owner will turn it into a task" - so it wrote a
        sentence about what somebody else would have to do."""
        self.assertNotIn('the owner will', responder.NOT_YET)
        self.assertIn('you will pick it up', responder.NOT_YET)

    def test_a_finished_job_is_reported_as_the_writers_own_work(self):
        self.assertIn('YOU did this', responder.DONE)



class WritingFeedbackTests(unittest.TestCase):
    """PW-062: the two documents are separate, and a payload diff is the only way to prove it. What the
    owner says about WRITING must appear in the next draft's payload; what triage learned about ROUTING
    must not appear in it at all, while triage still reads it."""
    def _store(self):
        s = MemoryStore()
        s.save_doc('soul', f'You work for **{OWNER}**. He runs finance systems.', 'owner')
        s.save_doc('style', chr(10).join(['## Reply style', '', '- Two sentences, answer first.',
                                        '- Say the number before the explanation.', '']), 'owner')
        tid = s.create_task({'Title': 'Scheduling', 'Kind': 'reply'}, 'o')
        s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'Times?', 'FromName': 'Meyy',
                       'FromEmail': 'meyy@partner.example', 'ExternalId': 'v1',
                       'BodyText': 'Can you suggest a few times next week?'})
        return s, tid

    NOTE = 'Never open with "I hope this finds you well" - answer in the first line.'

    def test_a_writing_instruction_is_in_the_next_drafts_payload_and_is_the_whole_difference(self):
        s, tid = self._store()
        before = _capture(s, tid)
        self.assertNotIn('I hope this finds you well', before['system'])
        self.assertTrue(responder.style_feedback(s, self.NOTE))
        after = _capture(s, tid)
        self.assertIn(self.NOTE, after['system'])
        self.assertEqual(before['user'], after['user'])                        # the thread it reads is untouched
        was = set(before['system'].splitlines())
        added = [ln for ln in after['system'].splitlines() if ln not in was and ln.strip()]
        self.assertEqual([ln for ln in added if not ln.startswith('## ')], [f'- {date.today()}: {self.NOTE}'])
        self.assertEqual(added[0], responder.OWNER_NOTES.strip())              # under Owner notes, outside the generated block

    def test_a_triage_lesson_reaches_triage_and_never_the_reply_voice(self):
        s, tid = self._store()
        before = _capture(s, tid)
        lesson = 'Invoices from vendor.example are always a task, never an FYI.'
        s.save_doc('learned', '## Rules' + chr(10) * 2 + f'- {lesson}' + chr(10), 'learn')
        after = _capture(s, tid)
        self.assertEqual(before['system'], after['system'])                    # the reply voice did not move
        self.assertNotIn(lesson, after['system'] + after['user'])
        seen = {}
        def llm(system, user, **kw):
            seen['system'] = system
            return '{"intent": "task", "reason": "x"}'
        triage.classify_intent({'from_email': 'meyy@partner.example', 'subject': 'Times?', 'body': 'When?'},
                               llm=llm, learned=s.doc('learned'))
        self.assertIn(lesson, seen['system'])                                  # ...and triage still has it

if __name__ == '__main__':
    unittest.main()
