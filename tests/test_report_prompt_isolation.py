"""A scheduled report's prompt is the report's own: instruction, data scope, output contract. Editing the
chat's COUNSEL must not move it (PW-242, PW-244)."""
import unittest

from taskuary import assistant
from taskuary.store import MemoryStore


class Spy:
    def __init__(self): self.calls = []
    def __call__(self, system, user, **kw): self.calls.append((system, user)); return '1. nothing new today'


class ReportPromptIsolation(unittest.TestCase):
    def prompt(self, store, instruction):
        llm = Spy(); assistant.think(store, [], llm, instruction=instruction); return llm.calls[-1][0]

    def test_editing_chat_counsel_does_not_change_the_report_prompt(self):
        st = MemoryStore()
        before = self.prompt(st, 'List anything about invoices.')
        st.save_doc('counsel', '# Mine\n\n## Voice\n- Shout everything in capitals.\n', 'owner')
        after = self.prompt(st, 'List anything about invoices.')
        self.assertEqual(before, after)
        self.assertNotIn('Shout everything', after)
        self.assertNotIn('I SURFACE', after)

    def test_the_report_keeps_its_instruction_and_contract(self):
        st = MemoryStore()
        system = self.prompt(st, 'List anything about invoices.')
        self.assertIn("YOUR INSTRUCTION (the owner's, from the Reports tab):\nList anything about invoices.", system)
        self.assertIn('writing your POST', system)

    def test_a_systems_monitor_keeps_its_own_prompt_and_rule(self):
        st = MemoryStore(); llm = Spy()
        assistant.think(st, [], llm, instruction='Only failed nightly jobs.', systems_only=True)
        system = llm.calls[-1][0]
        self.assertIn("THE OWNER'S RULE FOR THIS MONITOR:\nOnly failed nightly jobs.", system)
        self.assertIn(assistant.SYSTEMS_PROMPT[:40], system)
        self.assertNotIn('I am Taskuary', system)


class GeneralCheckPromptTests(unittest.TestCase):
    def test_a_line_about_one_mail_must_add_what_the_mail_does_not(self):
        """The general check raised "Hindy forwarded X with nothing but her signature ... I'd ask her
        what she wants" about a mail already on the Timeline as an fyi (the owner, 2026-09-07: "Why
        did assistant triagger on bare email meaning saying the same thing?").

        The rule lives in the CONTRACT, not in the prompt: the prompt is the owner's half - stored on
        the Assistant report and edited in the app, and this owner's copy is personalised - so a rule
        put there reaches nobody who has ever touched theirs.
        """
        st = MemoryStore(); llm = Spy()
        assistant.think(st, [], llm)
        system = llm.calls[-1][0]
        self.assertIn('A line about ONE message must tell the owner something the message does not', system)
        self.assertIn('a second copy of the mail and not a line', system)
        self.assertNotIn('A line about ONE message', assistant.PROMPT)      # never the editable half

    def test_the_rule_holds_whatever_prompt_the_owner_wrote(self):
        st = MemoryStore(); llm = Spy()
        assistant.think(st, [], llm, instruction='Only tell me about invoices, in my own words.')
        system = llm.calls[-1][0]
        self.assertIn('Only tell me about invoices', system)                # their half, as written
        self.assertIn('A line about ONE message must tell the owner', system)   # ...and the rule still rides

    def test_a_systems_monitor_is_not_given_the_mail_rule_at_all(self):
        st = MemoryStore(); llm = Spy()
        assistant.think(st, [], llm, instruction='Only failed nightly jobs.', systems_only=True)
        self.assertNotIn('A line about ONE message', llm.calls[-1][0])      # it reads its own sources


if __name__ == '__main__': unittest.main()
