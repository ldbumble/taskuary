"""Devin for Terminal (Cognition) as a coding CLI.

Three things are not like the others, and each one is a way the row could look installed and
then do nothing: the approval bypass is a MODE rather than a flag, `--print` refuses to start
in a folder nobody has trusted, and the vendor's installer ends by launching the CLI's own
interactive wizard - which, spawned from a server with no terminal, may never come back.

Nothing here installs anything or runs devin: the runner and the lookup are both faked.
"""
import os, subprocess, tempfile, unittest
from pathlib import Path
from unittest import mock

from taskuary import agents, cliinstall, clis, clisetup

ARGS = ['--permission-mode', 'dangerous', '--respect-workspace-trust=false', '-p']


class RegistrationTests(unittest.TestCase):
    def test_a_headless_turn_carries_the_bypass_and_the_trust_answer(self):
        """-p is the headless turn; without the mode it parks on an approval nobody can click,
        and without the trust answer it refuses to start in ~/.taskuary/scratch at all."""
        k = next(k for k in clis.KNOWN if k['name'] == 'devin')
        self.assertEqual((k['cmd'], k['args']), ('devin', ARGS))
        self.assertEqual(clis.preset_args('devin'), ARGS)
        # a profile saved as the absolute path the Windows installer writes is still a devin
        self.assertEqual(clis.preset_args(r'C:\Users\u\AppData\Local\devin\cli\bin\devin.exe'), ARGS)

    def test_the_trust_answer_is_one_token_not_two(self):
        """--respect-workspace-trust takes an OPTIONAL value. Spelled with a space, `false` is
        read as the start of the prompt and the check stays on - the `=` makes both readings agree."""
        self.assertIn('--respect-workspace-trust=false', clis.preset_args('devin'))
        self.assertNotIn('false', clis.preset_args('devin'))

    def test_the_classifier_loses_its_hands(self):
        """Triage reads untrusted mail: the message IS the prompt, so a sentence in it saying
        'run this' must find nothing to run. The mode is swapped, not dropped - `normal` asks
        before every write and shell command, and headlessly there is nobody to ask."""
        ro = clis.readonly_args('devin', ARGS)
        self.assertNotIn('dangerous', ro)
        self.assertEqual(ro, ['--respect-workspace-trust=false', '-p', '--permission-mode', 'normal'])
        self.assertEqual(clis.report_read_args('devin', ARGS), ro)

    def test_a_signed_out_devin_is_told_which_login_to_run(self):
        """The name that arrives is the PROFILE's - every install ships one called `coder` - so
        the CLI is read off the command it runs."""
        self.assertIn('devin auth login', agents.signed_out_msg('coder', '401 Unauthorized', 'devin'))


class InstallRoadTests(unittest.TestCase):
    def setUp(self):
        cliinstall.reset(); self.addCleanup(cliinstall.reset)

    def test_every_operating_system_gets_the_vendors_own_script(self):
        """No npm package and no triple-named archive, so the script is the only road - but
        unlike cursor and muse there IS a Windows one, which is the machine most owners arrive with."""
        for system, host in (('Windows', 'static.devin.ai/cli/setup.ps1'),
                             ('Darwin', 'cli.devin.ai/install.sh'), ('Linux', 'cli.devin.ai/install.sh')):
            roads = cliinstall.plan('devin', has_npm=False, system=system)
            self.assertEqual([r['how'] for r in roads], ['script'], system)
            self.assertIn(host, roads[0]['cmd'][-1], system)
            self.assertEqual(cliinstall.why_not('devin', has_npm=False, system=system), '', system)

    def test_the_binary_is_named_and_the_first_run_is_ours_to_open(self):
        self.assertEqual(cliinstall.BINARY['devin'], 'devin')
        self.assertEqual(cliinstall.recipe_for('devin'), 'devin')
        self.assertEqual(cliinstall.recipe_for(r'C:\Users\u\AppData\Local\devin\cli\bin\devin.exe'), 'devin')
        self.assertIn('devin', clisetup.SETUP)            # the sign-in is a browser round trip
        with mock.patch('taskuary.cliinstall.find', return_value=''):
            with self.assertRaises(ValueError): clisetup.argv('devin')

    def test_windows_is_looked_for_where_devins_installer_actually_puts_it(self):
        """It writes the USER path, which this long-running process will not see until it is
        restarted. Looking only at PATH is the difference between "installed" and "the installer
        said yes and left nothing to run"."""
        d = Path(tempfile.mkdtemp()) / 'devin' / 'cli' / 'bin'
        d.mkdir(parents=True)
        (d / 'devin.exe').write_text('', encoding='utf-8')
        with mock.patch.object(cliinstall, 'WINDOWS', True), \
                mock.patch.object(cliinstall.shutil, 'which', return_value=None), \
                mock.patch.dict(os.environ, {'LOCALAPPDATA': str(d.parent.parent.parent)}):
            self.assertEqual(cliinstall.find('devin'), str(d / 'devin.exe'))

    def test_a_setup_wizard_that_never_returns_is_not_a_failed_install(self):
        """Both scripts end by running `devin setup`. The binary is on the disk by then, so
        reporting failure would send the owner off to reinstall what is already installed."""
        exe = Path(tempfile.mkdtemp()) / ('devin.exe' if os.name == 'nt' else 'devin')
        exe.write_text('', encoding='utf-8')
        with mock.patch.object(cliinstall, '_run', side_effect=subprocess.TimeoutExpired('devin', 300)), \
                mock.patch.object(cliinstall, 'find', return_value=str(exe)), \
                mock.patch.object(cliinstall, 'ensure_on_path'):
            out = cliinstall.install('devin')
        self.assertEqual(out['phase'], 'done')
        self.assertEqual(out['path'], str(exe))

    def test_a_timeout_with_nothing_on_disk_is_still_a_failure(self):
        """The second look is for a binary that landed, never a way to call a dead install done."""
        with mock.patch.object(cliinstall, '_run', side_effect=subprocess.TimeoutExpired('devin', 300)), \
                mock.patch.object(cliinstall, 'find', return_value=''):
            out = cliinstall.install('devin')
        self.assertEqual(out['phase'], 'failed')

    def test_the_wizard_is_not_waited_on_for_a_quarter_of_an_hour(self):
        """900s is the right wait for an npm install on a slow line and the wrong one for a
        prompt that will never be answered."""
        seen = {}
        with mock.patch.object(cliinstall, '_run', side_effect=lambda cmd, **kw: (seen.update(kw), (0, 'ok'))[1]), \
                mock.patch.object(cliinstall, 'find', return_value='/tmp/devin'), \
                mock.patch.object(cliinstall, 'ensure_on_path'):
            cliinstall.install('devin')
        self.assertEqual(seen.get('timeout'), 300)


if __name__ == '__main__': unittest.main()
