"""The Install button for the coding CLIs: what it may run, where the binary lands, how it
reaches PATH, and who may press it.

Nothing here installs anything. The runner is faked in every test - a suite that shells out to
a vendor's installer is a suite that changes the machine it runs on.
"""
import os, sys, unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import cliinstall, clis, guard, server

c = TestClient(server.app)


class PlanTests(unittest.TestCase):
    """`plan` is pure: given a machine, which recipes could run on it, best first."""

    def test_the_menu_is_closed(self):
        """This runs an installer. An open field would be 'run anything on this machine'."""
        self.assertEqual(cliinstall.plan('rm -rf /'), [])
        self.assertEqual(cliinstall.plan('some-cli-nobody-vetted'), [])

    def test_claude_leads_with_the_vendor_script_not_npm(self):
        """The whole point of the button is the machine with no Node on it."""
        for system in ('Windows', 'Darwin', 'Linux'):
            first = cliinstall.plan('claude', has_npm=False, system=system)[0]
            self.assertEqual(first['how'], 'script', system)

    def test_a_machine_without_npm_is_offered_only_what_can_run_there(self):
        """gemini is npm and nothing else, so it must not claim it can install without npm."""
        self.assertEqual(cliinstall.plan('gemini', has_npm=False), [])
        self.assertEqual([r['how'] for r in cliinstall.plan('gemini', has_npm=True)], ['npm'])

    def test_codex_falls_back_to_the_release_binary_when_there_is_no_npm(self):
        self.assertEqual([r['how'] for r in cliinstall.plan('codex', has_npm=True)], ['npm', 'binary'])
        self.assertEqual([r['how'] for r in cliinstall.plan('codex', has_npm=False)], ['binary'])

    def test_cursor_says_no_on_windows_rather_than_pretending(self):
        """Its installer is a bash script and there is no Windows one. A button that cannot work
        must not be drawn - `installable` is what the UI reads."""
        self.assertEqual(cliinstall.plan('cursor', has_npm=True, system='Windows'), [])
        self.assertTrue(cliinstall.plan('cursor', has_npm=False, system='Darwin'))


class PathTests(unittest.TestCase):
    """A perfect PATH write reaches no process that is already running - including this one."""

    def setUp(self):
        self.env = mock.patch.dict(os.environ, {'PATH': os.environ.get('PATH', '')})
        self.env.start(); self.addCleanup(self.env.stop)

    def test_the_running_process_sees_it_immediately(self):
        """Without this the agent runner cannot spawn what was just installed until a restart."""
        import tempfile
        d = Path(tempfile.mkdtemp())
        cliinstall.ensure_on_path(d, persist=False)
        self.assertIn(str(d), os.environ['PATH'].split(os.pathsep))

    def test_it_does_not_add_the_same_directory_twice(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        cliinstall.ensure_on_path(d, persist=False)
        before = os.environ['PATH']
        cliinstall.ensure_on_path(d, persist=False)
        self.assertEqual(os.environ['PATH'], before)

    def test_a_shell_opened_tomorrow_gets_it_too(self):
        """The rc file is the only PATH a new terminal reads, and appending twice is a bug that
        only shows up as a rc file with forty identical lines in it."""
        import tempfile
        home, d = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        (home / '.bashrc').write_text('# existing\n', encoding='utf-8')
        cliinstall.persist_posix(d, home)
        cliinstall.persist_posix(d, home)
        rc = (home / '.bashrc').read_text(encoding='utf-8')
        self.assertEqual(rc.count(str(d)), 1)
        self.assertIn('# existing', rc)
        self.assertIn('export PATH=', rc)


class InstallTests(unittest.TestCase):
    def setUp(self):
        cliinstall.reset()
        self.env = mock.patch.dict(os.environ, {'PATH': os.environ.get('PATH', '')})
        self.env.start(); self.addCleanup(self.env.stop)

    def test_it_runs_the_first_recipe_and_reports_where_the_binary_landed(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        exe = d / ('claude.exe' if os.name == 'nt' else 'claude')
        exe.write_text('#!/bin/sh\n', encoding='utf-8')
        ran = []
        with mock.patch.object(cliinstall, '_run', side_effect=lambda cmd, **kw: (ran.append(cmd), (0, 'ok'))[1]), \
                mock.patch.object(cliinstall, 'find', side_effect=lambda name: str(exe) if name == 'claude' else ''):
            out = cliinstall.install('claude')
        self.assertEqual(len(ran), 1)
        self.assertEqual(out['path'], str(exe))
        self.assertEqual(out['phase'], 'done')

    def test_a_failing_recipe_falls_through_to_the_next(self):
        """npm is there but the registry is unreachable: the binary download is still a way in."""
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            return (1, 'npm ERR! network') if len(calls) == 1 else (0, 'ok')
        with mock.patch.object(cliinstall, '_run', side_effect=run), \
                mock.patch.object(cliinstall, '_binary', return_value='/tmp/codex'), \
                mock.patch.object(cliinstall, 'find', return_value='/tmp/codex'):
            out = cliinstall.install('codex', has_npm=True)
        self.assertEqual(out['phase'], 'done')
        self.assertEqual(out['path'], '/tmp/codex')

    def test_an_install_that_leaves_nothing_runnable_is_a_failure_not_a_success(self):
        """rc 0 and no binary is the failure that made "installed" mean nothing: the wizard would
        go straight on to Test and hand the owner a CLI error instead of an install error."""
        with mock.patch.object(cliinstall, '_run', return_value=(0, 'all good')), \
                mock.patch.object(cliinstall, 'find', return_value=''):
            out = cliinstall.install('gemini', has_npm=True)
        self.assertEqual(out['phase'], 'failed')
        self.assertIn('could not', out['detail'].lower())

    def test_nothing_installable_here_says_so_without_running_anything(self):
        with mock.patch.object(cliinstall, '_run', side_effect=AssertionError('must not run')):
            out = cliinstall.install('cursor', has_npm=True, system='Windows')
        self.assertEqual(out['phase'], 'failed')

    def test_the_phase_is_readable_while_it_runs(self):
        """A minute-long npm install cannot sit on an HTTP request, so the UI polls this."""
        seen = []
        with mock.patch.object(cliinstall, '_run', side_effect=lambda cmd, **kw: (seen.append(cliinstall.state()['phase']), (0, ''))[1]), \
                mock.patch.object(cliinstall, 'find', return_value='/tmp/claude'):
            cliinstall.install('claude')
        self.assertEqual(seen, ['installing'])
        self.assertEqual(cliinstall.state()['phase'], 'done')


class RecipeForTests(unittest.TestCase):
    """A profile is named for its JOB. Every install ships one called `coder`, so the name to
    install has to be read off the command it runs - install('coder') is a 422, and `coder` is
    the first row every install has."""

    def test_a_profiles_command_names_the_recipe_not_the_profile(self):
        self.assertEqual(cliinstall.recipe_for('claude'), 'claude')
        self.assertEqual(cliinstall.recipe_for('/usr/local/bin/claude'), 'claude')
        # both separators on either OS: a Windows profile path is read on the CI box too
        self.assertEqual(cliinstall.recipe_for(r'C:\Users\u\.local\bin\claude.exe'), 'claude')

    def test_the_binary_is_not_always_the_recipes_name(self):
        """cursor installs `cursor-agent`, so a profile pointing at that is still cursor."""
        self.assertEqual(cliinstall.recipe_for('cursor-agent'), 'cursor')
        self.assertEqual(cliinstall.recipe_for('cursor-agent.cmd'), 'cursor')

    def test_something_nobody_vetted_maps_to_nothing(self):
        for cmd in ('', 'coder', 'aider', 'my-own-wrapper', 'rm'):
            self.assertEqual(cliinstall.recipe_for(cmd), '', cmd)


class ApiTests(unittest.TestCase):
    def test_installing_software_is_the_owners_button(self):
        """An agent reads untrusted mail. An agent that can install software is an agent that can
        be talked into installing anything."""
        self.assertTrue(guard.denied('POST', '/api/cli/install'))

    def test_an_unknown_cli_is_refused_by_the_endpoint(self):
        self.assertEqual(c.post('/api/cli/install', json={'name': 'evil'}).status_code, 422)

    def test_the_state_endpoint_answers_before_anything_has_been_installed(self):
        cliinstall.reset()
        self.assertEqual(c.get('/api/cli/install/state').json()['phase'], 'idle')

    def test_a_profile_name_is_not_a_thing_that_can_be_installed(self):
        """The `coder` row wears the button; what it posts has to be `claude`."""
        self.addCleanup(cliinstall.reset)
        self.assertEqual(c.post('/api/cli/install', json={'name': 'coder'}).status_code, 422)

    def test_a_second_install_of_something_else_is_refused_while_one_runs(self):
        """The phase is global, so letting the second press through would have it poll the first
        install's state and report that success as its own."""
        self.addCleanup(cliinstall.reset)
        cliinstall._set('installing', 'claude', 'installing claude')
        r = c.post('/api/cli/install', json={'name': 'gemini'})
        self.assertEqual(r.status_code, 409)
        self.assertIn('claude', r.json()['detail'])
        self.assertEqual(cliinstall.state()['name'], 'claude')


class DetectTests(unittest.TestCase):
    def test_a_machine_with_no_cli_still_gets_a_row_to_press(self):
        """detect() used to drop everything it could not find, so the one owner who most needs the
        button - the one with nothing installed - saw an empty list and a dead end."""
        with mock.patch.object(clis.shutil, 'which', return_value=None):
            rows = clis.detect(None)
        by = {r['name']: r for r in rows}
        self.assertIn('claude', by)
        self.assertFalse(by['claude']['installed'])
        self.assertTrue(by['claude']['installable'])
        self.assertEqual(by['claude']['install'], 'claude')

    def test_a_configured_profile_offers_the_recipe_its_command_runs(self):
        """`coder` runs claude, so its row installs claude - not the nickname, which is a 422."""
        class Store:
            def list_agents(self): return [{'Name': 'coder', 'Config': '{"cmd": "claude"}'}]
        with mock.patch.object(clis.shutil, 'which', return_value=None):
            by = {r['name']: r for r in clis.detect(Store())}
        self.assertEqual(by['coder']['install'], 'claude')
        self.assertTrue(by['coder']['installable'])
        self.assertIn(by['coder']['install'], cliinstall.RECIPES)

    def test_a_profile_pointing_at_something_unknown_offers_no_button(self):
        class Store:
            def list_agents(self): return [{'Name': 'mine', 'Config': '{"cmd": "my-own-wrapper"}'}]
        with mock.patch.object(clis.shutil, 'which', return_value=None):
            by = {r['name']: r for r in clis.detect(Store())}
        self.assertEqual(by['mine']['install'], '')
        self.assertFalse(by['mine']['installable'])

    def test_what_is_installed_is_still_reported_as_installed(self):
        with mock.patch.object(clis.shutil, 'which', side_effect=lambda cmd: '/usr/bin/claude' if cmd == 'claude' else None):
            by = {r['name']: r for r in clis.detect(None)}
        self.assertTrue(by['claude']['installed'])
        self.assertEqual(by['claude']['path'], '/usr/bin/claude')


if __name__ == '__main__':
    unittest.main()
