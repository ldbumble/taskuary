"""A brain is a thing of its own: which CLI runs the work, and on which gear.

Spec: docs/superpowers/specs/2026-09-16-profile-brain-separation-design.md
"""
import json, unittest

from taskuary import agents as hub_agents, cli_connections as clic, terminal
from taskuary.store import MemoryStore


class CliNameTests(unittest.TestCase):
    def test_a_wrapper_is_not_the_cli(self):
        """copilot resolves to `cmd /c ...copilot.BAT` and qwen is launched through node.EXE, so
        argv[0] names the LAUNCHER. The card said `cmd` and `node`, and the task page's `by:` chip
        named the wrong product outright - `by: claude` over a Copilot session."""
        seen = 0
        for cmd in ('copilot', 'qwen', 'claude', 'codex'):
            # agent_argv RESOLVES the launcher, so it needs the CLI on PATH. A machine that has none
            # of them is not evidence of anything - CI installs no agents and failed every run on a
            # FileNotFoundError for 'copilot' (2026-09-16). Assert on the ones that are here, and
            # say so if none were, rather than reporting a green run over nothing tested.
            try:
                argv = terminal.agent_argv({'cmd': cmd})
            except FileNotFoundError:
                continue
            seen += 1
            self.assertEqual(terminal.cli_named({'cmd': cmd}, argv), cmd,
                             f'{cmd} is what runs; argv[0] is {argv[0]!r}')
        if not seen: self.skipTest('no agent CLI on PATH - nothing to resolve a launcher for')

    def test_cli_of_still_reads_a_plain_argv(self):
        """The fallback for a bare shell, which has no profile to ask."""
        self.assertEqual(terminal.cli_of(['/usr/bin/claude', '-p']), 'claude')

    def test_no_profile_falls_back_to_argv(self):
        self.assertEqual(terminal.cli_named({}, ['/usr/bin/codex', 'exec']), 'codex')


class DefaultBrainTests(unittest.TestCase):
    def store(self):
        s = MemoryStore()
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        s.upsert_agent('analyst', 'analysis', 'cli', json.dumps({'cmd': 'claude'}))
        return s

    def test_one_brain_serves_coding_and_general_alike(self):
        """The owner's rule: general agents use the same brain as coding by default."""
        s = self.store()
        s.set_setting('default_brain', 'claude', 'owner')
        self.assertEqual(hub_agents.brain_for(s, 'coder'), 'claude')
        self.assertEqual(hub_agents.brain_for(s, 'analyst'), 'claude')

    def test_a_role_may_be_overridden_in_settings(self):
        """Configurable - but it is a SETTING keyed by a profile, never a field on the profile,
        and what it names is a brain, never a model."""
        s = self.store()
        s.set_setting('default_brain', 'claude', 'owner')
        s.set_setting('profile_brains', json.dumps({'analyst': 'codex'}), 'owner')
        self.assertEqual(hub_agents.brain_for(s, 'analyst'), 'codex')
        self.assertEqual(hub_agents.brain_for(s, 'coder'), 'claude')

    def test_a_broken_override_falls_back_rather_than_failing(self):
        s = self.store()
        s.set_setting('default_brain', 'claude', 'owner')
        s.set_setting('profile_brains', 'not json', 'owner')
        self.assertEqual(hub_agents.brain_for(s, 'analyst'), 'claude')

    def test_an_unset_default_falls_back_to_the_legacy_profile_setting(self):
        """Nothing regresses on upgrade: blank means "whatever default_agent was already running"."""
        s = self.store()
        s.set_setting('default_agent', 'coder', 'owner')
        self.assertEqual(hub_agents.default_brain(s), 'claude')


class SessionBrainTests(unittest.TestCase):
    def setup(self, brain: str):
        s = MemoryStore()
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'provider': 'cli:claude'}))
        s.set_setting('default_brain', brain, 'owner')
        cfg = {'cli_connections': {'claude': {'cmd': 'claude'}, 'codex': {'cmd': 'codex', 'args': ['exec']}}}
        return s, cfg

    def test_the_command_comes_from_the_brain_settings_name(self):
        """The profile still says claude; settings say codex, and settings win. A profile has
        nothing to do with which brain runs it."""
        s, cfg = self.setup('codex')
        self.assertEqual(hub_agents.brain_command(s, 'coder', cfg).get('cmd'), 'codex')

    def test_an_unconfigured_brain_leaves_the_profile_alone(self):
        """A half-migrated install must still be able to start an agent at all."""
        s, cfg = self.setup('nobody-has-this')
        self.assertEqual(hub_agents.brain_command(s, 'coder', cfg), {})

    def test_no_brain_chosen_leaves_the_profile_alone(self):
        """Blank means the owner has not moved to the brain layer, and brain_for would be GUESSING
        from the legacy default_agent. Overriding an explicit profile command with a guess is how
        "start a session with codex" would quietly have run claude."""
        s, cfg = self.setup('')
        s.upsert_agent('codex', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
        self.assertEqual(hub_agents.brain_command(s, 'codex', cfg), {})

    def test_the_owners_own_pick_outranks_the_setting(self):
        """What the picker chooses is a BRAIN now, and it beats both the role override and the
        default - otherwise "start a session with codex" would resolve the default and run claude."""
        s, cfg = self.setup('claude')
        s.set_setting('profile_brains', json.dumps({'coder': 'claude'}), 'owner')
        self.assertEqual(hub_agents.brain_command(s, 'coder', cfg, want='codex').get('cmd'), 'codex')

    def test_a_role_override_alone_is_enough_to_choose(self):
        s, cfg = self.setup('')
        s.set_setting('profile_brains', json.dumps({'coder': 'codex'}), 'owner')
        self.assertEqual(hub_agents.brain_command(s, 'coder', cfg).get('cmd'), 'codex')

    def test_the_brain_brings_its_own_headless_flags(self):
        s, cfg = self.setup('codex')
        self.assertIn('exec', hub_agents.brain_command(s, 'coder', cfg).get('args') or [])

    def test_the_transcript_records_which_brain_ran(self):
        """Which brain ran is a fact of the SESSION - the task is never stamped with one."""
        s = MemoryStore()
        tid = s.create_task({'Title': 'x', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        s.add_transcript(tid, 'sid1', 'some output', agent='coder', cwd='C:/repo', brain='copilot')
        row = s.resumable_session(tid) or s._one('SELECT * FROM transcript WHERE Sid=?', ('sid1',))
        self.assertEqual((row['Agent'], row['Brain']), ('coder', 'copilot'))


class WhatRanItTests(unittest.TestCase):
    """The card names the brain that RAN the session, not the one the role would run on today.

    A researcher session ran on the owner's Azure OpenAI connector, closed, and an hour later its
    card read "brain claude" - the default for a role with no override, read off the coding roster
    because a closed session said nothing about itself (the owner, 2026-09-22: "claude did not open
    but azure openai did"). Both records existed: the pick a general session resumes from, and the
    transcript a pty session leaves."""

    def client(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        return TestClient(server.app), server.store

    def test_a_general_session_is_named_by_the_connector_it_reached_for(self):
        c, s = self.client()
        tid = s.create_task({'Title': 'Vendor asks for SAML SSO', 'Kind': 'general', 'Status': 'open'}, 'router')
        cid = s.save_connector({'Type': 'azure_openai', 'Name': 'Azure OpenAI', 'Active': 1, 'ConfigJson': '{}'}, 'owner')
        s.save_session(tid, f'connector:{cid}', 'gpt-5.4', '', 'ctx')
        self.assertEqual(c.get(f'/api/tasks/{tid}').json()['ranOn'], {'brain': 'Azure OpenAI', 'model': 'gpt-5.4'})

    def test_a_coding_session_is_named_by_the_brain_its_transcript_recorded(self):
        c, s = self.client()
        tid = s.create_task({'Title': 'fix the importer', 'Kind': 'coding', 'Status': 'open'}, 'router')
        s.add_transcript(tid, 'sid9', 'output', agent='coder', cwd='C:/repo', brain='claude')
        d = c.get(f'/api/tasks/{tid}').json()
        self.assertEqual(d['ranOn'], {'brain': 'claude', 'model': ''})
        self.assertEqual(d['transcript']['brain'], 'claude')

    def test_the_later_session_is_the_one_that_ran_it(self):
        """The task in the report had both: yesterday's coder on claude, this morning's researcher
        on Azure. The card must name the one that just closed."""
        c, s = self.client()
        tid = s.create_task({'Title': 'Vendor asks for SAML SSO', 'Kind': 'general', 'Status': 'open'}, 'router')
        s.add_transcript(tid, 'sidA', 'output', agent='coder', cwd='C:/repo', brain='claude')
        cid = s.save_connector({'Type': 'azure_openai', 'Name': 'Azure OpenAI', 'Active': 1, 'ConfigJson': '{}'}, 'owner')
        s.save_session(tid, f'connector:{cid}', 'gpt-5.4', '', 'ctx')
        self.assertEqual(c.get(f'/api/tasks/{tid}').json()['ranOn']['brain'], 'Azure OpenAI')

    def test_a_task_nothing_ever_ran_claims_nothing(self):
        c, s = self.client()
        tid = s.create_task({'Title': 'nobody has touched this', 'Kind': 'general', 'Status': 'open'}, 'router')
        self.assertIsNone(c.get(f'/api/tasks/{tid}').json()['ranOn'])


class GearByJobTests(unittest.TestCase):
    """Session work - coding and general alike - takes the MAIN model. The light gear is for the
    one-message jobs: triage, drafts, summaries, the digest."""

    def store(self):
        s = MemoryStore()
        s.upsert_agent('analyst', 'analysis', 'cli', json.dumps({'cmd': 'claude', 'light_model': 'haiku'}))
        return s

    def ran_with(self, **kw):
        """The profile make_cli_llm actually hands to run_cli."""
        from unittest import mock
        from taskuary import llm as llm_mod
        seen = {}

        def fake_run_cli(prof, prompt, trace, **_):
            seen.update(prof); return 'ok', None, None

        brain = llm_mod.make_cli_llm(self.store(), 'analyst', **kw)
        with mock.patch('taskuary.agents.run_cli', fake_run_cli): brain('sys', 'user')
        return seen

    def test_a_one_message_job_takes_the_light_gear(self):
        self.assertEqual(self.ran_with().get('model'), 'haiku')

    def test_session_work_does_not_fall_through_to_the_light_gear(self):
        """The analyst was answering on the classifier's cheap model whenever no main model was
        set - the whole point of naming the gear rather than inferring it."""
        self.assertNotEqual(self.ran_with(gear='main').get('model'), 'haiku')

    def test_an_explicit_model_still_outranks_everything(self):
        self.assertEqual(self.ran_with(model='opus').get('model'), 'opus')


class SwitchTests(unittest.TestCase):
    """Step 2 left the brain layer opt-in - brain_command acts only on a brain the owner chose, so
    nothing regressed. This is the line that moves an install onto it, naming exactly what it was
    already running."""

    def store(self):
        s = MemoryStore()
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        s.set_setting('default_agent', 'coder', 'owner')
        return s

    def test_an_upgrade_writes_the_brain_it_was_already_running(self):
        s = self.store()
        self.assertTrue(hub_agents.adopt_brain_setting(s))
        self.assertEqual(s.get_settings()['default_brain'], 'claude')

    def test_it_does_not_overwrite_a_brain_the_owner_chose(self):
        s = self.store()
        s.set_setting('default_brain', 'codex', 'owner')
        self.assertFalse(hub_agents.adopt_brain_setting(s))
        self.assertEqual(s.get_settings()['default_brain'], 'codex')

    def test_it_is_idempotent(self):
        s = self.store()
        self.assertTrue(hub_agents.adopt_brain_setting(s))
        self.assertFalse(hub_agents.adopt_brain_setting(s))


class GearTests(unittest.TestCase):
    """`model_arg` (the FLAG) already lived on the connection; `model` and `light_model` (the
    VALUES) were stranded on the profile behind a patch that scrubbed them whenever the provider
    changed - whose own comment said "Model names belong to their provider"."""

    def cfg(self):
        return {'cli_connections': {'claude': {'cmd': 'claude', 'model': 'opus', 'light_model': 'haiku'}},
                'agents': {'coder': {'kind': 'coding', 'provider': 'cli:claude'}}}

    def test_gears_belong_to_the_connection(self):
        self.assertEqual(clic.gears(self.cfg(), 'claude'), {'model': 'opus', 'light_model': 'haiku'})

    def test_resolving_a_profile_takes_the_connection_gears(self):
        c = self.cfg()
        got = clic.resolve(c, c['agents']['coder'])
        self.assertEqual((got['model'], got['light_model']), ('opus', 'haiku'))

    def test_one_brain_two_gears_is_still_one_brain(self):
        """The owner's rule: triage runs the main brain on a quicker model, and a CLI session
        always takes the main one. Not two providers."""
        c = self.cfg()
        self.assertEqual(clic.gears(c, 'claude'), {'model': 'opus', 'light_model': 'haiku'})

    def test_an_unknown_brain_has_no_gears_rather_than_raising(self):
        self.assertEqual(clic.gears(self.cfg(), 'nobody'), {'model': '', 'light_model': ''})

    def test_gears_already_on_a_profile_are_lifted_onto_its_connection(self):
        """Adding them to COMMAND_FIELDS makes resolve() DROP whatever the profile holds, so an
        install that already has a provider would silently lose the models the owner chose."""
        c = {'cli_connections': {'claude': {'cmd': 'claude'}},
             'agents': {'coder': {'kind': 'coding', 'provider': 'cli:claude', 'model': 'opus', 'light_model': 'haiku'}}}
        clic.migrate(c)
        self.assertEqual(clic.gears(c, 'claude'), {'model': 'opus', 'light_model': 'haiku'})
        self.assertNotIn('model', c['agents']['coder'])

    def test_a_connection_that_already_has_gears_is_not_overwritten(self):
        c = {'cli_connections': {'claude': {'cmd': 'claude', 'model': 'mine'}},
             'agents': {'coder': {'kind': 'coding', 'provider': 'cli:claude', 'model': 'theirs'}}}
        clic.migrate(c)
        self.assertEqual(clic.gears(c, 'claude')['model'], 'mine')
