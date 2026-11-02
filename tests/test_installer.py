"""TaskuarySetup.exe (installer/taskuary.iss): the one-folder build it installs, and the update road that runs the next installer."""
import os, tempfile, unittest
from pathlib import Path, PureWindowsPath as P
from unittest import mock

from taskuary import spawn, unpack, update

ROOT = Path(__file__).resolve().parent.parent


class OneFolder(unittest.TestCase):
    def test_the_installed_build_is_told_from_the_one_file_exe(self):
        app = os.path.realpath(tempfile.mkdtemp())
        with mock.patch.object(spawn.sys, 'frozen', True, create=True), mock.patch.object(spawn.sys, 'executable', os.path.join(app, 'Taskuary.exe')):
            with mock.patch.object(spawn.sys, '_MEIPASS', os.path.join(app, '_internal'), create=True): self.assertTrue(spawn.onedir())
            with mock.patch.object(spawn.sys, '_MEIPASS', os.path.join(tempfile.gettempdir(), '_MEI1234'), create=True): self.assertFalse(spawn.onedir())
        self.assertFalse(spawn.onedir(), 'not frozen')

    def test_installed_it_never_ends_a_parent_taskuary_or_sweeps_temp(self):
        """In the folder build a Taskuary.exe parent is the main app that started a view - ending it as a 'bootloader' would close the app."""
        with mock.patch.object(spawn, 'meipass', return_value=r'C:\Apps\Taskuary\_internal'), mock.patch.object(spawn, 'onedir', return_value=True), \
             mock.patch.object(unpack, '_image') as img:
            self.assertEqual(unpack.bootloader(), 0); self.assertEqual(unpack.sweep_stale(), [])
        img.assert_not_called()

    def test_the_road_is_setup(self):
        with mock.patch.object(update.sys, 'frozen', True, create=True), mock.patch.object(spawn, 'onedir', return_value=True):
            self.assertEqual(update.how(), 'setup')
        with mock.patch.object(update.sys, 'frozen', True, create=True), mock.patch.object(spawn, 'onedir', return_value=False):
            self.assertEqual(update.how(), 'exe')


class TheSetupRoad(unittest.TestCase):
    def setUp(self): update._cache.update({'at': 0.0, 'result': None})

    def test_an_installed_app_takes_the_installer_asset_not_the_exe(self):
        j = {'tag_name': 'v9.9.9', 'assets': [{'name': 'Taskuary.exe', 'browser_download_url': 'https://dl/Taskuary.exe'},
                                              {'name': 'TaskuarySetup.exe', 'browser_download_url': 'https://dl/TaskuarySetup.exe'}]}
        r = mock.Mock(); r.json.return_value = j; r.raise_for_status = mock.Mock()
        with mock.patch.object(update.requests, 'get', return_value=r), mock.patch.object(update, 'how', return_value='setup'):
            self.assertEqual(update.check(force=True)['url'], 'https://dl/TaskuarySetup.exe')
        r.json.return_value = {'tag_name': 'v9.9.9', 'assets': []}
        with mock.patch.object(update.requests, 'get', return_value=r), mock.patch.object(update, 'how', return_value='setup'):
            self.assertEqual(update.check(force=True)['url'], update.SETUP_URL)

    def test_the_script_waits_installs_quietly_then_starts_the_app_itself(self):
        s = update.setup_script(P(r'C:\h\update\TaskuarySetup.exe'), P(r'C:\Users\a\AppData\Local\Programs\Taskuary\Taskuary.exe'), 4242, ['--port', '7787'])
        wait, run, start = s.find('PID eq 4242'), s.find('/VERYSILENT'), s.find('start "" /D')
        self.assertTrue(0 < wait < run < start, 'wait for us, then install, then start')
        self.assertIn(r'start "" /wait "C:\h\update\TaskuarySetup.exe"', s)
        self.assertIn('/CURRENTUSER', s); self.assertNotIn('/ALLUSERS', s)
        self.assertIn(r'"C:\Users\a\AppData\Local\Programs\Taskuary\Taskuary.exe" "--port" "7787"', s)
        self.assertIn('PYINSTALLER_RESET_ENVIRONMENT=1', s)
        self.assertIn('/ALLUSERS', update.setup_script(P(r'C:\x\S.exe'), P(r'C:\Program Files\Taskuary\Taskuary.exe'), 1, [], all_users=True))

    def test_program_files_is_an_all_users_install(self):
        with mock.patch.dict(os.environ, {'ProgramFiles': r'C:\Program Files', 'ProgramFiles(x86)': r'C:\Program Files (x86)'}):
            if os.name == 'nt':
                self.assertTrue(update.for_all_users(r'C:\Program Files\Taskuary\Taskuary.exe'))
            self.assertFalse(update.for_all_users(os.path.join(tempfile.gettempdir(), 'Programs', 'Taskuary', 'Taskuary.exe')))

    def test_apply_downloads_the_installer_to_the_data_folder_and_hands_over(self):
        d = Path(tempfile.mkdtemp()).resolve(); exe = d / 'Taskuary.exe'; exe.write_bytes(b'MZ')
        with mock.patch.object(update, 'how', return_value='setup'), \
             mock.patch.object(update, 'check', return_value={'newer': True, 'error': None, 'url': 'https://dl/S.exe'}), \
             mock.patch.object(update.sys, 'executable', str(exe)), mock.patch.object(update.sys, 'argv', ['Taskuary.exe']), \
             mock.patch.object(update, '_download', return_value=99) as dl, mock.patch.object(update, '_launch_swap') as launch:
            out = update.apply()
        self.assertEqual(out, {'how': 'setup', 'downloaded': 99, 'restarting': True})
        stage = update.staging()
        self.assertEqual(dl.call_args[0][:2], ('https://dl/S.exe', stage / 'TaskuarySetup.exe'))
        self.assertIn('/VERYSILENT', (stage / 'taskuary-update.cmd').read_text(encoding='utf-8'))
        launch.assert_called_once_with(stage / 'taskuary-update.cmd', stage)


class TheInstallerScript(unittest.TestCase):
    s = (ROOT / 'installer' / 'taskuary.iss').read_text(encoding='utf-8')

    def test_it_installs_for_this_user_unless_asked_and_never_touches_the_data(self):
        self.assertIn('PrivilegesRequired=lowest', self.s)
        self.assertIn('PrivilegesRequiredOverridesAllowed=dialog commandline', self.s)   # the update passes /CURRENTUSER or /ALLUSERS
        self.assertNotIn('.taskuary', self.s.split('[Setup]', 1)[1])

    def test_it_packs_the_folder_the_spec_builds(self):
        self.assertIn(r'..\dist\onedir\Taskuary\*', self.s)
        self.assertIn("os.getenv('TASKUARY_ONEDIR')", (ROOT / 'taskuary.spec').read_text(encoding='utf-8'))


if __name__ == '__main__': unittest.main()
