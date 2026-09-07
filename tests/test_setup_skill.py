"""The setup walkthrough gets its procedure from a shipped skill, not from branching in the code (PW-190).

A task opened as `assistant:setup` carries the skill into the worker's prompt in the same slot a
playbook rides in; every other general task is untouched by it. The skill is a document the worker
READS and adapts - there is no wizard route behind this, and no keyword dispatch.
"""
import unittest

from taskuary import general
from taskuary.store import MemoryStore


def task(store, ref=None):
    return store.create_task({'Title': 'Connect Zoho', 'Summary': 'Walk me through Zoho Invoice', 'Kind': 'general',
                              'Status': 'open', 'Source': 'assistant', **({'SourceRef': ref} if ref else {})}, 'owner')


class ShippedSkillTests(unittest.TestCase):
    def test_the_skill_ships_with_the_package_and_says_what_a_walkthrough_must_know(self):
        text = general.setup_skill()
        self.assertIn('name: taskuary-setup', text)
        for needed in ('/api/setup',                                   # inspect what is already configured
                       'Prerequisites',                                # owner name, one AI brain, one inbound source
                       'GET /api/cli/detect',
                       'Secrets never pass through this chat',
                       'never rerun it',                               # resume without redoing a done step
                       'Never create a second connector'):
            self.assertIn(needed, text, needed)

    def test_a_setup_task_carries_the_skill_as_its_procedure_and_other_work_does_not(self):
        s = MemoryStore()
        walk, _ = general._prompt(s, task(s, general.SETUP_REF))
        plain, _ = general._prompt(s, task(s))
        self.assertIn('# Taskuary setup walkthrough', walk)
        self.assertIn('PROCEDURE FOR THIS JOB', walk)
        self.assertNotIn('# Taskuary setup walkthrough', plain)

    def test_the_procedure_is_read_not_hardcoded(self):
        # PW-190: the branching lives in the document. If the code grew a second setup script the
        # prompt would stop tracking the skill file, so the prompt must quote it verbatim.
        s = MemoryStore()
        walk, _ = general._prompt(s, task(s, general.SETUP_REF))
        self.assertIn(general.setup_skill()[:2_000], walk)


if __name__ == '__main__':
    unittest.main()
