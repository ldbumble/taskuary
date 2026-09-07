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


if __name__ == '__main__': unittest.main()
