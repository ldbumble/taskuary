"""Importing somebody else's expertise as a profile.

A skill says HOW a job is done. A playbook is the owner's own workflow against the owner's own
systems, drafted from work that happened - so nothing here ever writes one.
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from taskuary import skillimport

SKILL = '''---
name: nda-triage
description: Use when a counterparty sends an NDA and somebody has to decide whether it can be signed as-is.
---

# NDA triage

Read the indemnity clause first. Anything uncapped goes to counsel.
'''


class ParsingTests(unittest.TestCase):
    def test_the_frontmatter_becomes_the_name_and_the_purpose(self):
        got = skillimport.parse(SKILL)
        self.assertEqual(got['name'], 'nda-triage')
        self.assertIn('counterparty sends an NDA', got['description'])
        self.assertIn('indemnity clause', got['body'])
        self.assertNotIn('---', got['body'])          # the frontmatter is not part of the rules

    def test_a_file_with_no_frontmatter_is_still_importable(self):
        got = skillimport.parse('# Just prose\n\nDo the thing carefully.')
        self.assertEqual(got['description'], '')
        self.assertIn('Do the thing', got['body'])

    def test_a_folder_of_skills_reads_every_one(self):
        with TemporaryDirectory() as td:
            for n in ('a', 'b'):
                d = Path(td) / 'skills' / n
                d.mkdir(parents=True)
                (d / 'SKILL.md').write_text(SKILL.replace('nda-triage', n), encoding='utf-8')
            (Path(td) / '.claude-plugin').mkdir()
            (Path(td) / '.claude-plugin' / 'plugin.json').write_text(
                '{"name": "legal", "description": "contract work"}', encoding='utf-8')
            got = skillimport.read_path(td)
        self.assertEqual(sorted(g['name'] for g in got), ['a', 'b'])
        self.assertEqual(got[0]['plugin'], 'legal')

    def test_a_single_file_reads_as_one(self):
        with TemporaryDirectory() as td:
            p = Path(td) / 'SKILL.md'
            p.write_text(SKILL, encoding='utf-8')
            got = skillimport.read_path(str(p))
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]['name'], 'nda-triage')

    def test_the_connector_manifest_is_never_opened(self):
        """Taskuary's connectors are tested cards behind scopes.py. Importing MCP servers would hand
        a worker a second way out of the building."""
        src = Path(skillimport.__file__).read_text(encoding='utf-8')
        self.assertNotIn('.mcp.json', src)
        self.assertNotIn('mcpServers', src)

    def test_commands_are_not_read(self):
        with TemporaryDirectory() as td:
            (Path(td) / 'commands').mkdir()
            (Path(td) / 'commands' / 'x.md').write_text('# a command', encoding='utf-8')
            (Path(td) / 'skills' / 'a').mkdir(parents=True)
            (Path(td) / 'skills' / 'a' / 'SKILL.md').write_text(SKILL, encoding='utf-8')
            got = skillimport.read_path(td)
        self.assertEqual([g['name'] for g in got], ['a'])


class FoundTests(unittest.TestCase):
    """found() walks a home directory for the two install shapes Claude Code uses. The plugin name
    must come from which glob matched, not from counting path segments back from the end - that
    breaks the moment a personal skill's path happens to be five segments deep too."""

    def test_a_personal_skill_has_no_plugin(self):
        with TemporaryDirectory() as td:
            home = Path(td)
            d = home / '.claude' / 'skills' / 'solo'
            d.mkdir(parents=True)
            (d / 'SKILL.md').write_text(SKILL.replace('nda-triage', 'solo'), encoding='utf-8')
            got = skillimport.found(home=home)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]['name'], 'solo')
        self.assertEqual(got[0]['plugin'], '')

    def test_a_cached_plugin_skill_knows_its_plugin(self):
        with TemporaryDirectory() as td:
            home = Path(td)
            d = (home / '.claude' / 'plugins' / 'cache' / 'some-marketplace' / 'legal' / '1.0.0'
                 / 'skills' / 'nda-triage')
            d.mkdir(parents=True)
            (d / 'SKILL.md').write_text(SKILL, encoding='utf-8')
            got = skillimport.found(home=home)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]['name'], 'nda-triage')
        self.assertEqual(got[0]['plugin'], 'legal')

    def test_both_shapes_found_together(self):
        with TemporaryDirectory() as td:
            home = Path(td)
            solo = home / '.claude' / 'skills' / 'solo'
            solo.mkdir(parents=True)
            (solo / 'SKILL.md').write_text(SKILL.replace('nda-triage', 'solo'), encoding='utf-8')
            cached = (home / '.claude' / 'plugins' / 'cache' / 'mkt' / 'legal' / '1.0.0'
                      / 'skills' / 'nda-triage')
            cached.mkdir(parents=True)
            (cached / 'SKILL.md').write_text(SKILL, encoding='utf-8')
            got = skillimport.found(home=home)
        by_name = {g['name']: g for g in got}
        self.assertEqual(by_name['solo']['plugin'], '')
        self.assertEqual(by_name['nda-triage']['plugin'], 'legal')


if __name__ == '__main__':
    unittest.main()
