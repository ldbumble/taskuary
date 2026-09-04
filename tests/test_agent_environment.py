"""What a CLI needs from us before it can run at all.

Two failures from one owner's machine (2026-08-31), both of which read as somebody else's bug:

* `codex exit 1: ... Error finding codex home: Could not find home directory` - Taskuary handed
  the CLI an environment with no home in it. codex keeps its settings and its sign-in there and
  will not start without one, and the message points at codex.
* Every dispatch aimed at `claude`, which that machine has never had, because `coder` = claude
  is what Taskuary ships. The Board showed it as the agent failing.

Neither is the CLI's fault, so neither is left to the CLI to explain.
"""
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from taskuary import agents
from taskuary.store import MemoryStore


def _agent(s, name, cmd, **extra):
    s.upsert_agent(name, 'cli', 'cli', json.dumps({'cmd': cmd, **extra}))


class TheEnvironmentAChildGetsTests(unittest.TestCase):
    def test_a_home_is_always_handed_down(self):
        env = agents.child_env()
        self.assertTrue(env['HOME'])
        self.assertEqual(env['CODEX_HOME'], os.path.join(str(Path.home()), '.codex'))

    def test_an_environment_that_already_says_where_home_is_keeps_its_answer(self):
        with mock.patch.dict(os.environ, {'HOME': '/somewhere/else', 'CODEX_HOME': '/opt/codex'}):
            env = agents.child_env()
        self.assertEqual((env['HOME'], env['CODEX_HOME']), ('/somewhere/else', '/opt/codex'))

    def test_windows_gets_the_variables_windows_tools_read(self):
        """Asked for AS Windows rather than pretending to BE Windows: patching os.name out
        from under the interpreter is how the first version of this failed on Linux CI."""
        env = agents.child_env({}, r'C:\Users\rabbi', windows=True)
        self.assertEqual(env['USERPROFILE'], r'C:\Users\rabbi')
        self.assertEqual((env['HOMEDRIVE'], env['HOMEPATH']), ('C:', r'\Users\rabbi'))
        self.assertEqual(env['CODEX_HOME'], r'C:\Users\rabbi\.codex')

    def test_a_posix_box_gets_posix_variables_and_no_windows_ones(self):
        env = agents.child_env({}, '/home/rabbi', windows=False)
        self.assertEqual(env['HOME'], '/home/rabbi')
        self.assertNotIn('USERPROFILE', env)
        self.assertTrue(env['CODEX_HOME'].endswith('.codex'))

    def test_an_environment_handed_in_is_the_one_that_comes_back(self):
        env = agents.child_env({'PATH': '/usr/bin'}, '/home/rabbi', windows=False)
        self.assertEqual(env['PATH'], '/usr/bin')

    def test_a_machine_with_no_home_at_all_is_not_a_crash(self):
        with mock.patch.object(agents.Path, 'home', staticmethod(mock.Mock(side_effect=RuntimeError))):
            self.assertIsInstance(agents.child_env(), dict)

    def test_the_message_names_the_account_and_not_the_cli(self):
        said = agents.no_home_msg('codex')
        self.assertIn('CODEX_HOME', said)
        self.assertIn('service', said)
        self.assertIn('codex login', said)

    def test_a_home_complaint_is_recognised_however_it_is_worded(self):
        for line in ('Error finding codex home: Could not find home directory',
                     'could not find home directory', 'HOME is not set'):
            self.assertTrue(agents._NO_HOME.search(line), line)
        self.assertFalse(agents._NO_HOME.search('no such file or directory'))


class WhichAgentWorkTests(unittest.TestCase):
    def test_default_backup_chain_uses_every_other_configured_agent(self):
        s = MemoryStore()
        _agent(s, 'coder', 'claude')
        _agent(s, 'codex', 'codex')
        _agent(s, 'gemini', 'gemini')
        s.set_setting('default_agent', 'coder', 'o')
        self.assertEqual(agents.agent_chain(s), ['coder', 'codex', 'gemini'])

    def test_explicit_backup_chain_keeps_the_owners_order(self):
        s = MemoryStore()
        for name in ('coder', 'codex', 'gemini'): _agent(s, name, name)
        s.set_setting('backup_agents', 'gemini,codex', 'o')
        self.assertEqual(agents.agent_chain(s, 'coder'), ['coder', 'gemini', 'codex'])

    def test_session_and_usage_limits_are_availability_failures(self):
        self.assertTrue(agents.availability_failure(RuntimeError("You've hit your session limit; resets 11:50am")))
        self.assertTrue(agents.availability_failure(RuntimeError('rate limit exceeded')))
        self.assertFalse(agents.availability_failure(RuntimeError('tests failed after editing three files')))

    def test_the_owners_default_wins_when_its_cli_is_here(self):
        s = MemoryStore()
        _agent(s, 'coder', 'claude')
        s.set_setting('default_agent', 'coder', 'o')
        with mock.patch.object(agents, 'runs_here', return_value=True):
            self.assertEqual(agents.default_agent(s), 'coder')

    def test_a_default_that_cannot_run_here_hands_over_to_one_that_can(self):
        s = MemoryStore()
        _agent(s, 'coder', 'claude')
        _agent(s, 'codex', 'codex')
        s.set_setting('default_agent', 'coder', 'o')
        with mock.patch.object(agents, 'runs_here', side_effect=lambda p: p.get('cmd') == 'codex'):
            self.assertEqual(agents.default_agent(s), 'codex')

    def test_with_nothing_installed_the_owners_choice_is_still_reported(self):
        """Silently renaming their default would be worse than failing where they can see it."""
        s = MemoryStore()
        _agent(s, 'coder', 'claude')
        s.set_setting('default_agent', 'coder', 'o')
        with mock.patch.object(agents, 'runs_here', return_value=False):
            self.assertEqual(agents.default_agent(s), 'coder')

    def test_an_unknown_default_is_left_alone(self):
        s = MemoryStore()
        s.set_setting('default_agent', 'somebody-elses-agent', 'o')
        self.assertEqual(agents.default_agent(s), 'somebody-elses-agent')

    def test_runs_here_answers_no_rather_than_raising_for_a_missing_cli(self):
        self.assertFalse(agents.runs_here({'cmd': 'no-such-cli-anywhere-9z'}))


class APinnedPathThatMovedTests(unittest.TestCase):
    """codex installs into ...\\Codex\\bin\\<version hash>\\codex.exe, so a profile pinned to one
    of those breaks on the next update - and read as "the CLI is gone"."""
    def test_the_name_is_asked_for_again_when_the_saved_path_has_gone(self):
        real = '/usr/local/bin/codex'
        with mock.patch.object(agents.shutil, 'which', side_effect=lambda n, path=None: real if n == 'codex.exe' else None):
            self.assertEqual(agents._resolve_cmd(r'C:\gone\Codex\bin\8fffe694\codex.exe'), [real])

    def test_a_bare_name_that_is_not_installed_still_says_so(self):
        with mock.patch.object(agents.shutil, 'which', return_value=None):
            with self.assertRaises(FileNotFoundError):
                agents._resolve_cmd('codex')


class ARunOutsideACheckoutTests(unittest.TestCase):
    """Most of what this app asks a CLI is not about a repo - the classifier, the drafter,
    STYLE.md generation all run in ~/.taskuary/scratch on purpose. codex refuses to start there
    ("Not inside a trusted directory and --skip-git-repo-check was not specified") and headlessly
    there is nobody to answer its trust prompt, so the whole setup step died before the model was
    reached (issue #34)."""
    def _argv(self, profile):
        with mock.patch.object(agents, '_resolve_cmd', return_value=['X']), \
             mock.patch('taskuary.spawn.popen', side_effect=RuntimeError('stop')) as pop:
            with self.assertRaises(RuntimeError): agents.run_cli(profile, 'hi', lambda *a: None)
        return pop.call_args[0][0]

    def test_codex_exec_is_allowed_to_run_where_there_is_no_git_repo(self):
        argv = self._argv({'cmd': 'codex', 'args': ['exec', '--sandbox', 'read-only'], 'cwd': None})
        self.assertIn('--skip-git-repo-check', argv)

    def test_the_flag_is_not_repeated_when_the_profile_already_says_it(self):
        argv = self._argv({'cmd': 'codex', 'args': ['exec', '--skip-git-repo-check']})
        self.assertEqual(argv.count('--skip-git-repo-check'), 1)

    def test_it_is_an_exec_flag_so_no_other_cli_and_no_tui_gets_it(self):
        self.assertNotIn('--skip-git-repo-check', self._argv({'cmd': 'claude', 'args': ['-p']}))
        # bare `codex` is the interactive TUI, which asks about trust itself
        self.assertNotIn('--skip-git-repo-check', self._argv({'cmd': 'codex', 'args': ['--full-auto']}))
        from taskuary import terminal
        self.assertNotIn('--skip-git-repo-check', terminal.interactive_args(['exec', '--json']))


if __name__ == '__main__':
    unittest.main()
