"""Importing somebody else's expertise as a profile.

A skill says HOW a job is done. A playbook is the owner's own workflow against the owner's own
systems, drafted from work that happened - so nothing here ever writes one.
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from starlette.testclient import TestClient

from taskuary import server, skillimport
from taskuary.store import MemoryStore

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

    def test_only_a_file_called_SKILL_md_is_ever_read(self):
        """Any absolute path used to come back as a proposed worker's body, which made the endpoint
        in front of read_path an arbitrary local-file read."""
        with TemporaryDirectory() as td:
            secret = Path(td) / 'config.toml'
            secret.write_text('[server]\ntoken = "hunter2"\n', encoding='utf-8')
            self.assertEqual(skillimport.read_path(str(secret)), [])
            good = Path(td) / 'SKILL.md'
            good.write_text(SKILL, encoding='utf-8')
            self.assertEqual(len(skillimport.read_path(str(good))), 1)

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

    def test_a_folded_description_joins_its_lines_with_spaces(self):
        text = ('---\nname: nda-triage\ndescription: >\n  a counterparty sends an NDA\n'
                 '  and somebody must decide\n---\n\nbody\n')
        got = skillimport.parse(text)
        self.assertEqual(got['description'], 'a counterparty sends an NDA and somebody must decide')

    def test_a_literal_description_keeps_its_newlines(self):
        text = ('---\nname: nda-triage\ndescription: |\n  first line\n  second line\n---\n\nbody\n')
        got = skillimport.parse(text)
        self.assertEqual(got['description'], 'first line\nsecond line')

    def test_a_single_line_description_still_works(self):
        got = skillimport.parse(SKILL)
        self.assertEqual(got['description'],
                          'Use when a counterparty sends an NDA and somebody has to decide '
                          'whether it can be signed as-is.')

    def test_a_bare_block_indicator_with_no_continuation_is_empty_not_the_symbol(self):
        # the failure this closes: a bad/truncated frontmatter parsing to the literal word '>'
        text = '---\nname: nda-triage\ndescription: >\n---\n\nbody\n'
        got = skillimport.parse(text)
        self.assertEqual(got['description'], '')


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

    def test_a_cached_plugin_skill_carries_its_plugin_description(self):
        with TemporaryDirectory() as td:
            home = Path(td)
            pdir = home / '.claude' / 'plugins' / 'cache' / 'some-marketplace' / 'legal' / '1.0.0'
            d = pdir / 'skills' / 'nda-triage'
            d.mkdir(parents=True)
            (d / 'SKILL.md').write_text(SKILL, encoding='utf-8')
            (pdir / '.claude-plugin').mkdir()
            (pdir / '.claude-plugin' / 'plugin.json').write_text(
                '{"name": "legal", "description": "contract work"}', encoding='utf-8')
            got = skillimport.found(home=home)
        self.assertEqual(got[0]['plugin'], 'legal')
        self.assertEqual(got[0]['plugin_desc'], 'contract work')

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


class ConvertingTests(unittest.TestCase):
    def test_the_description_becomes_the_purpose(self):
        got = skillimport.convert(skillimport.parse(SKILL), llm=None)
        self.assertEqual(got['name'], 'nda-triage')
        self.assertIn('NDA', got['purpose'])
        self.assertIn('indemnity clause', got['body'])

    def test_a_model_may_sharpen_it_and_the_body_still_arrives_whole(self):
        """The model rewrites a description written for a harness into a purpose written for a
        roster. It must not summarise the BODY - that is the expertise being imported."""
        said = '{"name": "nda-triage", "purpose": "decides whether an NDA can be signed as-is", "kind": "analysis"}'
        got = skillimport.convert(skillimport.parse(SKILL), llm=lambda *a, **k: said)
        self.assertEqual(got['purpose'], 'decides whether an NDA can be signed as-is')
        self.assertIn('indemnity clause', got['body'])
        self.assertEqual(got['kind'], 'analysis')

    def test_a_model_that_answers_nonsense_falls_back_to_the_file(self):
        got = skillimport.convert(skillimport.parse(SKILL), llm=lambda *a, **k: 'sorry, what?')
        self.assertIn('counterparty sends an NDA', got['purpose'])

    def test_the_kind_is_never_coding(self):
        """A coding profile is chosen by routed_role, not by triage, and CODER.md's repository rules
        apply to it. An imported skill must never land there by accident."""
        said = '{"name": "x", "purpose": "p", "kind": "coding"}'
        got = skillimport.convert(skillimport.parse(SKILL), llm=lambda *a, **k: said)
        self.assertNotEqual(got['kind'], 'coding')


class CollisionTests(unittest.TestCase):
    """A wizard hands out arbitrary names, and the shipped roles (researcher, analyst, coordinator,
    marketer, trader) plus every hand-written profile all slugify into ordinary names - so a name
    collision is not a corner case. `save` must never destroy a profile it did not create."""
    def _got(self, **kw):
        return {'name': 'researcher', 'purpose': 'overwritten by an import', 'kind': 'analysis',
                'body': '# Overwritten\n\nThis should never land.', **kw}

    def _hand_made(self, s):
        """A profile that exists but carries no `imported` flag - the shape of both a shipped role
        and anything the owner wrote by hand through Docs -> Add profile."""
        from taskuary import agents
        s.upsert_agent('researcher', 'research', 'cli', '{"purpose": "outside information"}')
        doc = agents.profile_document(s, 'researcher')
        s.save_doc(doc, '# Researcher\n\nOriginal, hand-written rules.\n', 'owner')
        return doc

    def test_it_refuses_to_overwrite_a_profile_it_did_not_create(self):
        s = MemoryStore()
        doc = self._hand_made(s)
        with self.assertRaises(skillimport.ProfileCollision):
            skillimport.save(s, self._got(), enabled=True)
        row = s.get_agent('researcher')
        self.assertEqual(row['Kind'], 'research')                              # untouched
        self.assertEqual(s.get_doc(doc), '# Researcher\n\nOriginal, hand-written rules.\n')

    def test_replace_true_goes_through(self):
        s = MemoryStore()
        doc = self._hand_made(s)
        skillimport.save(s, self._got(), enabled=True, replace=True)
        self.assertEqual(s.get_agent('researcher')['Kind'], 'analysis')
        self.assertIn('should never land', s.get_doc(doc))

    def test_reimporting_your_own_import_needs_no_flag(self):
        """The idempotent case already covered elsewhere: a profile carrying `imported: True`
        updates in place with no `replace` needed."""
        s = MemoryStore()
        skillimport.save(s, self._got(), enabled=True)
        skillimport.save(s, self._got(purpose='changed'), enabled=True)   # no replace=True
        self.assertEqual(s.get_agent('researcher')['Kind'], 'analysis')

    def test_a_fresh_name_is_unaffected(self):
        s = MemoryStore()
        skillimport.save(s, self._got(name='nda-triage'), enabled=True)
        self.assertTrue(s.get_agent('nda-triage'))

    def test_the_endpoint_reports_a_clash_without_discarding_the_rest(self):
        s = MemoryStore()
        self._hand_made(s)
        with mock.patch.object(server, 'store', s):
            resp = TestClient(server.app).post('/api/skills/import', json={'skills': [
                self._got(),                                    # clashes with the hand-made researcher
                {'name': 'nda-triage', 'purpose': 'decides whether an NDA can be signed as-is',
                 'body': 'Read the indemnity clause.', 'kind': 'analysis', 'enabled': True},
            ]})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['imported'], ['nda-triage'])
        self.assertEqual(body['clashed'], [{'name': 'researcher', 'kind': 'research'}])
        self.assertEqual(s.get_agent('researcher')['Kind'], 'research')        # untouched


class SavingTests(unittest.TestCase):
    def _got(self, **kw):
        return {'name': 'nda-triage', 'purpose': 'decides whether an NDA can be signed as-is',
                'body': '# NDA triage\n\nRead the indemnity clause first.', 'kind': 'analysis', **kw}

    def test_it_writes_an_ordinary_profile(self):
        from taskuary import agents
        s = MemoryStore()
        skillimport.save(s, self._got(), enabled=True)
        row = s.get_agent('nda-triage')
        self.assertTrue(row)
        self.assertEqual(row['Kind'], 'analysis')
        self.assertIn('indemnity clause', s.get_doc(agents.profile_document(s, 'nda-triage')) or '')

    def test_ticked_reaches_the_roster_as_ONE_line(self):
        from taskuary import agents
        s = MemoryStore()
        skillimport.save(s, self._got(), enabled=True)
        roster = agents.roster(s)
        self.assertIn('nda-triage', roster)
        self.assertEqual(len([l for l in roster.splitlines() if 'nda-triage' in l]), 1)
        self.assertIn('signed as-is', roster)

    def test_unticked_is_saved_and_never_offered_to_triage(self):
        from taskuary import agents
        s = MemoryStore()
        skillimport.save(s, self._got(), enabled=False)
        self.assertTrue(s.get_agent('nda-triage'))          # imported
        self.assertNotIn('nda-triage', agents.roster(s))    # not offered

    def test_importing_twice_does_not_make_two(self):
        s = MemoryStore()
        skillimport.save(s, self._got(), enabled=True)
        skillimport.save(s, self._got(purpose='changed'), enabled=True)
        self.assertEqual(len([a for a in s.list_agents() if a['Name'] == 'nda-triage']), 1)

    def test_no_import_ever_creates_a_playbook(self):
        """The load-bearing rule: a playbook is the owner's own workflow against the owner's own
        systems, drafted from work that happened."""
        from taskuary import playbooks
        before = len(playbooks.list_all())
        skillimport.save(MemoryStore(), self._got(), enabled=True)
        self.assertEqual(len(playbooks.list_all()), before)

    def test_a_verbose_purpose_does_not_eat_half_the_roster(self):
        """A carry-forward from Task 3's review: with no model, `purpose` is the skill's raw
        `description`, which can be a multi-sentence folded block. The 2000-char roster cap
        (triage.py) is a budget shared by every worker, so one import must not crowd the rest
        out - bounded at roster-ASSEMBLY time (agents.roster), not at save, since save has no
        idea how many other workers are competing for that budget."""
        from taskuary import agents
        s = MemoryStore()
        skillimport.save(s, self._got(purpose='x' * 900), enabled=True)
        s.upsert_agent('another-worker', 'general', 'cli', '{"purpose": "handles the mail", "triage_enabled": true}')
        roster = agents.roster(s)
        self.assertLess(len(roster), 1000)
        self.assertIn('another-worker', roster)             # still visible, not crowded off the end
        # the full purpose is not lost - only the roster line is bounded - so a profile editor or
        # the starter doc can still show it whole
        row = s.get_agent('nda-triage')
        prof = __import__('json').loads(row['Config'])
        self.assertEqual(len(prof['purpose']), 900)


if __name__ == '__main__':
    unittest.main()
