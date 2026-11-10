"""Agent profiles: CODING.md is one profile, not the ground.

Asked for 2026-09-10. Every worker session was seeded `CODING RULES (CODING.md)` unconditionally
(terminal.py), so a meeting-prep task and a research task were both told "work only in the repository
the task names" - and the system compensated with prose ("NO REPOSITORY", "THIS IS NOT A CODE
CHANGE") rather than by not sending the wrong document. On the owner's own store: 123 general tasks
against 98 coding ones, and 27 agent sessions on general work against 10 on coding.

The model, minimal: a profile IS an agent row, and its rules document is the `doc` row of the same
name. `coding` already was exactly that. Triage names none for a task (the owner, 2026-11-04): a routine or
workflow names the profile it runs on.
"""
import json, re, unittest
from unittest import mock

from taskuary import agents as hub_agents, terminal, triage
from taskuary.store import MemoryStore


def store():
    s = MemoryStore()
    s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    return s


def seeded(s):
    """What server.py's boot does: seed the config, then copy it into the store."""
    cfg = {'agents': {'coding': {'cmd': 'claude', 'kind': 'coding'}}}
    hub_agents.seed_profiles(cfg)
    for name, prof in cfg['agents'].items():
        s.upsert_agent(name, prof.get('kind', 'coding'), 'cli', json.dumps(prof))
    return s


class TheRosterTests(unittest.TestCase):
    def test_database_seeds_all_shipped_profile_documents(self):
        s = store()
        for name in hub_agents.DEFAULT_PROFILES:
            self.assertGreater(len(s.get_doc(name) or ''), 200, name)

    def test_the_shipped_profiles_are_the_ones_the_owner_chose(self):
        # ...and the general assistant's own, like CODING.md for coding (the owner, 2026-10-14)
        self.assertEqual(set(hub_agents.DEFAULT_PROFILES),
                         {'researcher', 'analyst', 'coordinator', 'marketer', 'trader', 'assistant'})
        for name, prof in hub_agents.DEFAULT_PROFILES.items():
            self.assertNotEqual(prof['kind'], 'coding', f'{name} must not be a coding profile')
            self.assertTrue(prof['purpose'].strip(), f'{name} needs a purpose for the roster')

    def test_every_shipped_profile_has_a_document_to_edit(self):
        """A profile with no document is a worker with no rules - the whole point is the stock prompt."""
        from pathlib import Path
        import taskuary
        tpl = Path(taskuary.__file__).parent / 'templates'
        for name in hub_agents.DEFAULT_PROFILES:
            doc = tpl / f'{name}.md'
            self.assertTrue(doc.exists(), f'{name}.md is not shipped')
            self.assertGreater(len(doc.read_text(encoding='utf-8').strip()), 200, f'{name}.md is a stub')

    def test_researcher_and_analyst_are_split_on_whose_information_it_is(self):
        """The first pair of purpose lines both read as "find out something", so "look into last
        month's spend" could land on either (the owner, 2026-09-10: "sharpen analyst vs
        researcher"). The line is OUTSIDE vs OUR OWN, and each document says it too, so a session
        that starts on the wrong side of it hands the job back instead of guessing."""
        from pathlib import Path
        import taskuary
        res, ana = hub_agents.DEFAULT_PROFILES['researcher']['purpose'], hub_agents.DEFAULT_PROFILES['analyst']['purpose']
        self.assertIn('OUTSIDE', res)
        self.assertIn('OUR OWN', ana)
        self.assertNotIn('OUTSIDE', ana)
        tpl = Path(taskuary.__file__).parent / 'templates'
        self.assertIn('analyst', tpl.joinpath('researcher.md').read_text(encoding='utf-8'))
        self.assertIn('researcher', tpl.joinpath('analyst.md').read_text(encoding='utf-8'))

    def test_seeding_never_clobbers_a_profile_the_owner_changed(self):
        """It goes in config.toml, which is what the Agents page reads and writes."""
        cfg = {'agents': {'coding': {'cmd': 'claude', 'args': ['-p'], 'kind': 'coding'}}}
        self.assertIn('researcher', hub_agents.seed_profiles(cfg))
        cfg['agents']['researcher'] = {'purpose': 'mine', 'kind': 'research', 'rules_doc': 'mine'}
        self.assertEqual(hub_agents.seed_profiles(cfg), [])          # nothing left to add
        self.assertEqual(cfg['agents']['researcher']['rules_doc'], 'mine')
        self.assertEqual(cfg['agents']['researcher']['purpose'], 'mine')

    def test_a_shipped_profile_carries_instructions_and_no_cli(self):
        """A profile is instructions layered on whichever brain runs its work (the owner, 2026-10-15): it
        inherits no command, flags or timeout - its row takes the brain's command at sync."""
        cfg = {'agents': {'coding': {'cmd': 'claude', 'args': ['-p', '--dangerously-skip-permissions'],
                                    'timeout': 1500, 'kind': 'coding'}}}
        hub_agents.seed_profiles(cfg)
        got = cfg['agents']['marketer']
        self.assertEqual(got, {'kind': 'marketing', 'purpose': hub_agents.DEFAULT_PROFILES['marketer']['purpose']})
        for k in ('cmd', 'args', 'timeout', 'provider'): self.assertNotIn(k, got)

    def test_profiles_are_seeded_even_before_any_cli_is_configured(self):
        """With no CLI to inherit from there is nothing to wait for: a profile names no command."""
        cfg = {}
        self.assertEqual(set(hub_agents.seed_profiles(cfg)), set(hub_agents.DEFAULT_PROFILES))
        self.assertFalse(any('cmd' in p for p in cfg['agents'].values()))


class ProfileEditingTests(unittest.TestCase):
    def setUp(self):
        from taskuary import server
        from fastapi.testclient import TestClient
        self.server = server
        self.s = seeded(store())
        cfg = {**server.cfg, 'agents': hub_agents.profiles(self.s)}
        for patch in (mock.patch.object(server, 'store', self.s), mock.patch.object(server, 'cfg', cfg),
                      mock.patch.object(server.config, 'save')):
            patch.start(); self.addCleanup(patch.stop)
        self.client = TestClient(server.app)

    def test_opening_a_missing_or_blank_role_restores_its_own_template(self):
        self.s.cx.execute("DELETE FROM doc WHERE Name='trader'")
        self.s.save_doc('analyst', '', 'owner')
        for name in ('trader', 'analyst'):
            result = self.client.get(f'/api/doc/{name}')
            self.assertEqual(result.status_code, 200)
            self.assertGreater(len(result.json()['content']), 200)
            self.assertEqual(self.s.get_doc(name), result.json()['content'])
        self.s.save_doc('trader', 'The owner wrote this.', 'owner')
        self.assertEqual(self.client.get('/api/doc/trader').json()['content'], 'The owner wrote this.')

    def test_learned_is_edited_with_the_name_and_saved_with_the_token(self):
        """The setup sweep, 2026-10-28: LEARNED.md's editor showed {{owner_first}} raw."""
        self.s.set_setting('owner_name', 'Alex Doyle', 'owner')
        self.s.save_doc('learned', '## Your people\n- {{owner_first}} answers Erin Blake the same day', 'owner')
        got = self.client.get('/api/doc/learned').json()['content']
        self.assertIn('- Alex answers Erin Blake', got); self.assertNotIn('{{', got)
        self.client.put('/api/doc/learned', json={'content': got + '\n- Alex reads the digest first'})
        self.assertEqual(self.s.get_doc('learned').count('{{owner_first}}'), 2, self.s.get_doc('learned'))
        self.assertNotIn('Alex', self.s.get_doc('learned'))
        # ...another document keeps its tokens as written
        self.s.save_doc('trader', 'Ask {{owner_first}} first.', 'owner')
        self.assertEqual(self.client.get('/api/doc/trader').json()['content'], 'Ask {{owner_first}} first.')

    def test_codex_and_coding_edit_and_run_the_same_document(self):
        self.s.upsert_agent('codex', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
        self.s.save_doc('coding', 'Shared coding rules: test every changed behavior.', 'owner')
        result = self.client.get('/api/doc/codex').json()
        self.assertEqual(result['name'], 'coding')
        self.assertEqual(result['content'], self.s.get_doc('coding'))
        self.client.put('/api/doc/codex', json={'content': 'Shared coding rules: preserve user changes.'})
        self.assertIn('preserve user changes', terminal.rules_text(self.s, profile='codex'))
        self.assertEqual(terminal.rules_text(self.s, profile='codex'), terminal.rules_text(self.s, profile='coding'))
        self.assertFalse(self.s.get_doc('codex'))

    def test_new_profile_gets_starter_rules_and_triage_still_names_no_worker(self):
        result = self.client.put('/api/agents/procurement', json={
            'cmd': 'claude', 'args': ['-p'], 'kind': 'general', 'purpose': 'Compare vendor quotes and explain costs.',
            'rules_doc': 'procurement', 'triage_enabled': True})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['rules_doc'], 'procurement')
        doc = self.client.get('/api/doc/procurement').json()['content']
        self.assertIn('Compare vendor quotes', doc)
        self.assertIn('AGENT.md', doc)
        # a profile is for routines (the owner, 2026-11-04): a task's verdict never carries one, even when the brain names it
        decision = triage.classify_intent({'Subject': 'Compare these vendors', 'Body': 'Find the best quote'},
            lambda *args, **kwargs: json.dumps({'intent': 'task', 'kind': 'general', 'profile': 'procurement'}))
        self.assertNotIn('profile', decision)

    def test_a_profile_is_a_name_and_instructions_and_saves_with_no_ai_connected(self):
        """The owner, 2026-10-22: no provider or model on a profile. "Choose a configured CLI provider" refused every save on a box with
        no CLI connected; one saved before with those keys still loads, and a CLI the body NAMES that is not there is still refused."""
        with mock.patch.dict(self.server.cfg, {'cli_connections': {}}):
            result = self.client.put('/api/agents/scout', json={'kind': 'research', 'purpose': 'Compare vendors and cite public sources.',
                                                                 'rules_doc': 'scout', 'triage_enabled': True})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertNotIn('provider', self.server.cfg['agents']['scout'])
            self.assertEqual(self.client.put('/api/agents/bad', json={'provider': 'cli:not-connected', 'purpose': 'x'}).status_code, 422)
        self.server.cfg['agents']['legacy'] = {'provider': 'cli:claude', 'model': 'sonnet', 'kind': 'research', 'purpose': 'Old one'}
        self.assertEqual(self.client.get('/api/agents').json()['config']['legacy']['model'], 'sonnet')

    def test_changing_the_cli_keeps_routing_metadata(self):
        original = hub_agents.profiles(self.s)['researcher']
        self.s.save_doc('researcher', 'Custom research instructions.', 'owner')
        result = self.client.put('/api/agents/researcher', json={'cmd': 'codex'})
        self.assertEqual(result.status_code, 200, result.text)
        updated = hub_agents.profiles(self.s)['researcher']
        self.assertEqual(updated['kind'], original['kind'])
        self.assertEqual(updated['purpose'], original['purpose'])
        self.assertEqual(self.s.get_doc('researcher'), 'Custom research instructions.')
        self.assertIsNotNone(self.s.get_agent('researcher'))

    def test_a_routed_general_task_uses_the_named_workers_instructions(self):
        """The role owns the INSTRUCTIONS - which is what stops it being "only a label on the
        task" - and no longer owns the CLI. It used to answer both, so naming a worker named a
        brain; that fusion is what routed TQ-0588's coding work to Copilot (the 2026-09-16 spec)."""
        from taskuary import general
        self.s.save_doc('researcher', 'Research rule: compare independent public sources.', 'owner')
        self.s.save_doc('coding', 'CODE-ONLY SENTINEL: edit repository files.', 'owner')
        task_id = self.s.create_task({'Title': 'Compare vendors', 'Kind': 'general', 'Status': 'open',
                                     'Assignee': 'agent:researcher'}, 'owner')
        task = self.s.get_task(task_id)
        self.assertEqual(general.assigned_role(self.s, task), 'researcher')
        self.assertNotEqual(general.default_pick(self.s, task), 'cli:researcher')
        system, _ = general._prompt(self.s, task_id)
        self.assertIn('RESEARCHER.md', system)
        self.assertIn('compare independent public sources', system)
        self.assertNotIn('CODE-ONLY SENTINEL', system)


class TriageNamesNoProfileTests(unittest.TestCase):
    """A general agent working a TASK has one goal, to walk the owner through their work (the owner, 2026-11-04):
    triage stops choosing a worker, and every general task runs on the assistant. Routines keep theirs."""
    def test_the_contract_neither_asks_for_a_profile_nor_explains_one(self):
        self.assertNotIn('**Which worker.**', triage.INTENT_SYSTEM)
        self.assertNotIn('`profile`', triage.INTENT_SYSTEM)

    def _classify(self, answer):
        msg = {'Subject': 'Look into the vendor', 'BodyText': 'Can you find out who they are?',
               'FromEmail': 'a@b.test', 'FromName': 'A'}
        return triage.classify_intent(msg, llm=lambda *a, **k: json.dumps(answer))

    def test_a_profile_the_brain_names_never_rides_on_the_verdict(self):
        out = self._classify({'intent': 'task', 'kind': 'general', 'profile': 'researcher', 'why': 'a look-up'})
        self.assertNotIn('profile', out)
        self.assertEqual(out['kind'], 'general')

    def test_a_reply_only_message_gets_no_profile(self):
        out = self._classify({'intent': 'reply_only', 'profile': 'researcher', 'why': 'just answer them'})
        self.assertNotIn('profile', out)

    def test_a_workflow_still_names_its_worker(self):
        """Profiles are for routines and workflows: one whose definition names `analyst` is stamped with it
        (workflows.run) and its session is seeded ANALYST.md (general._prompt)."""
        from taskuary import general, ingest, workflows
        s = seeded(store())
        s.save_doc('analyst', 'ANALYST RULES: our own figures only.', 'test')
        sid = s.save_source({'Channel': 'report', 'Address': 'Spend', 'Owner': 'o', 'Active': 1,
                             'ConfigJson': json.dumps({'type': 'agent', 'title': 'Spend', 'agent': 'analyst', 'prompt': 'sum the month'})}, 'o')
        with mock.patch.object(ingest, '_auto_general'), mock.patch.object(ingest, '_auto_code'):
            tid = workflows.run(s, s.get_source(sid))['task_id']
        self.assertEqual(s.get_task(tid)['Assignee'], 'agent:analyst')
        system, _ = general._prompt(s, tid)
        self.assertIn('PROFILE RULES (the file ANALYST.md)', system)
        self.assertIn('our own figures only', system)


class TheSessionGetsItsOwnRulesTests(unittest.TestCase):
    def test_a_profile_task_is_seeded_its_own_document_and_not_coding_md(self):
        s = store()
        seeded(s)
        s.save_doc('coding', 'CODING RULES: work only in the repository the task names.', 'test')
        s.save_doc('researcher', 'RESEARCH RULES: cite every source; change nothing.', 'test')
        tid = s.create_task({'Title': 'Who are Acme?', 'Kind': 'coding', 'Status': 'open',
                             'Assignee': 'agent:researcher'}, 'o')
        seed = terminal.seed_text(s, tid)
        self.assertIn('cite every source', seed)
        self.assertNotIn('work only in the repository', seed)
        self.assertIn('RESEARCHER.md', seed)

    def test_a_coding_task_still_gets_coding_md(self):
        """The regression that matters: coding work must be untouched by this."""
        s = store()
        s.save_doc('coding', 'CODING RULES: work only in the repository the task names.', 'test')
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open',
                             'Assignee': 'agent:coding'}, 'o')
        seed = terminal.seed_text(s, tid)
        self.assertIn('work only in the repository', seed)
        self.assertIn('CODING.md', seed)

    def test_a_task_with_no_assignee_falls_back_to_the_default_profile(self):
        s = store()
        s.save_doc('coding', 'CODING RULES: work only in the repository the task names.', 'test')
        tid = s.create_task({'Title': 'Something', 'Kind': 'coding', 'Status': 'open'}, 'o')
        seed = terminal.seed_text(s, tid)
        self.assertIn('work only in the repository', seed)

    def test_a_profile_with_an_empty_document_seeds_no_rules_block_rather_than_coding_md(self):
        """Falling back to CODING.md here is the bug, not a safety net."""
        s = store()
        seeded(s)
        s.save_doc('coding', 'CODING RULES: work only in the repository the task names.', 'test')
        s.save_doc('marketer', '', 'test')
        tid = s.create_task({'Title': 'Write the launch note', 'Kind': 'coding', 'Status': 'open',
                             'Assignee': 'agent:marketer'}, 'o')
        seed = terminal.seed_text(s, tid)
        self.assertNotIn('work only in the repository', seed)


if __name__ == '__main__':
    unittest.main()


class WorkflowsAreNotCodeTests(unittest.TestCase):
    """A workflow is not code, so it must not always go to the coding agent (the owner, 2026-09-10).

    run_agent fell back to the coding profile, and - because that road never loaded an operator
    document at all - a workflow pointed at `researcher` got the researcher's CLI and none of the
    researcher's rules."""

    def test_an_unnamed_workflow_goes_to_the_default_brain_not_the_coding_profile(self):
        from taskuary import reports
        s = seeded(store())
        s.set_setting('default_brain', 'codex', 'owner')     # the person's pick: a brain saved for them that does not run is not one (agents.stale)
        seen = {}
        def fake_cli(store_, name, model=None, **kw):
            seen['name'] = name
            return lambda system, user, **k: seen.update(ask=user) or 'done'
        with mock.patch.object(reports, 'make_cli_llm', fake_cli, create=True), \
             mock.patch('taskuary.llm.make_cli_llm', fake_cli):
            reports.run_agent({'store': s, 'prompt': 'summarise the week'})
        self.assertEqual(seen['name'], 'codex')

    def test_a_named_workflow_runs_under_that_profiles_rules(self):
        from taskuary import reports
        s = seeded(store())
        s.save_doc('researcher', 'RESEARCH RULES: cite every source.', 'test')
        seen = {}
        def fake_cli(store_, name, model=None, **kw):
            seen['name'] = name
            return lambda system, user, **k: seen.update(ask=user) or 'done'
        with mock.patch('taskuary.llm.make_cli_llm', fake_cli):
            reports.run_agent({'store': s, 'agent': 'researcher', 'prompt': 'who are Acme?'})
        self.assertEqual(seen['name'], 'researcher')
        self.assertIn('cite every source', seen['ask'])
        self.assertIn('RESEARCHER.md', seen['ask'])

    def test_an_unnamed_workflow_gets_no_rules_block_so_nothing_existing_changes(self):
        from taskuary import reports
        s = seeded(store())
        s.save_doc('coding', 'CODING RULES: work only in the repository.', 'test')
        s.set_setting('default_brain', 'codex', 'owner')      # a brain to run on: with none, a report says "No AI is connected"
        seen = {}
        def fake_cli(store_, name, model=None, **kw):
            return lambda system, user, **k: seen.update(ask=user) or 'done'
        with mock.patch('taskuary.llm.make_cli_llm', fake_cli):
            reports.run_agent({'store': s, 'prompt': 'the weekly numbers'})
        self.assertNotIn('work only in the repository', seen['ask'])
