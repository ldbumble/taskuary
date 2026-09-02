"""Update in place (update.py). The data folder is never touched - an update is only a program
swap - and nothing here may ever swap in a half-downloaded file or fire on a version it could not
parse. The exe road cannot be run here (the running exe is locked), so the pieces are tested one
by one and the batch is read like a program.
"""
import os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

from taskuary import update


class Versions(unittest.TestCase):
    def test_newer_compares_dotted_ints_of_any_depth(self):
        self.assertTrue(update.newer('0.3.2.6', '0.3.2.5'))
        self.assertTrue(update.newer('0.4', '0.3.2.5'))          # shorter but larger
        self.assertTrue(update.newer('1.0.0', '0.99.99'))
        self.assertFalse(update.newer('0.3.2.5', '0.3.2.5'))
        self.assertFalse(update.newer('0.3.2.4', '0.3.2.5'))
        self.assertFalse(update.newer('0.3.2', '0.3.2.0'))         # padding, not lexical

    def test_a_string_it_cannot_read_is_never_newer(self):
        self.assertFalse(update.newer('', '0.3.2.5'))
        self.assertFalse(update.newer('latest', '0.3.2.5'))
        self.assertFalse(update.newer('0.3.2.6', ''))


class Checking(unittest.TestCase):
    def setUp(self): update._cache.update({'at': 0.0, 'result': None})

    def _resp(self, j, code=200):
        r = mock.Mock(status_code=code)
        r.json.return_value = j
        r.raise_for_status = mock.Mock(side_effect=None if code == 200 else RuntimeError('boom'))
        return r

    def test_reads_the_release_tag_and_the_exe_asset(self):
        j = {'tag_name': 'v9.9.9', 'html_url': 'https://github.com/x/releases/tag/v9.9.9',
             'assets': [{'name': 'taskuary-9.9.9.whl', 'browser_download_url': 'w'},
                        {'name': 'Taskuary.exe', 'browser_download_url': 'https://dl/Taskuary.exe'}]}
        with mock.patch.object(update.requests, 'get', return_value=self._resp(j)):
            out = update.check(force=True)
        self.assertEqual((out['latest'], out['newer'], out['url']), ('9.9.9', True, 'https://dl/Taskuary.exe'))
        self.assertEqual(out['current'], update.__version__)
        self.assertIn(out['how'], ('exe', 'pip', 'source'))
        self.assertIsNone(out['error'])

    def test_no_exe_asset_falls_back_to_the_fixed_latest_url(self):
        j = {'tag_name': 'v9.9.9', 'assets': []}
        with mock.patch.object(update.requests, 'get', return_value=self._resp(j)):
            self.assertEqual(update.check(force=True)['url'], update.EXE_URL)

    def test_github_unreachable_is_an_answer_not_an_exception(self):
        with mock.patch.object(update.requests, 'get', side_effect=OSError('offline')):
            out = update.check(force=True)
        self.assertFalse(out['newer']); self.assertIsNone(out['latest'])
        self.assertIn('could not reach GitHub', out['error'])

    def test_the_answer_is_cached_between_pill_polls(self):
        j = {'tag_name': 'v9.9.9', 'assets': []}
        with mock.patch.object(update.requests, 'get', return_value=self._resp(j)) as get:
            update.check(force=True); update.check(); update.check()
        self.assertEqual(get.call_count, 1)


class TheSwapScript(unittest.TestCase):
    def test_it_waits_swaps_relaunches_with_the_same_arguments_and_removes_itself(self):
        s = update.swap_script(Path(r'C:\Apps\Taskuary.exe'), Path(r'C:\Apps\Taskuary.new.exe'), 4242,
                               ['--port', '7787', '--debug'])
        self.assertIn('PID eq 4242', s)                                  # waits for THIS process to go
        self.assertIn('move /Y "C:\\Apps\\Taskuary.new.exe" "C:\\Apps\\Taskuary.exe"', s)
        self.assertIn('start "" "C:\\Apps\\Taskuary.exe" "--port" "7787" "--debug"', s)   # same command line
        self.assertIn('del "%~f0"', s)                                   # leaves nothing behind
        self.assertIn('geq 30 goto giveup', s)                          # a stuck swap still relaunches something
        self.assertTrue(s.endswith('\r\n'))                              # batch wants CRLF

    def test_no_arguments_leaves_no_trailing_space(self):
        s = update.swap_script(Path('T.exe'), Path('T.new.exe'), 1, [])
        self.assertIn('start "" "T.exe"\r\n', s)


class Downloading(unittest.TestCase):
    def _stream(self, chunks, total=None):
        r = mock.MagicMock()
        r.__enter__.return_value = r
        r.raise_for_status = mock.Mock()
        r.headers = {'Content-Length': str(total if total is not None else sum(map(len, chunks)))}
        r.iter_content.return_value = iter(chunks)
        return r

    def test_a_real_exe_is_kept_and_its_size_reported(self):
        d = Path(tempfile.mkdtemp()) / 'new.exe'
        with mock.patch.object(update.requests, 'get', return_value=self._stream([b'MZ' + b'x' * 10])):
            self.assertEqual(update._download('u', d), 12)
        self.assertTrue(d.is_file())

    def test_a_short_download_is_deleted_not_swapped_in(self):
        d = Path(tempfile.mkdtemp()) / 'new.exe'
        with mock.patch.object(update.requests, 'get', return_value=self._stream([b'MZ' + b'x' * 5], total=100)):
            with self.assertRaises(RuntimeError) as e: update._download('u', d)
        self.assertIn('stopped short', str(e.exception)); self.assertFalse(d.exists())

    def test_an_html_error_page_is_not_a_program(self):
        d = Path(tempfile.mkdtemp()) / 'new.exe'
        with mock.patch.object(update.requests, 'get', return_value=self._stream([b'<html>not found</html>'])):
            with self.assertRaises(RuntimeError) as e: update._download('u', d)
        self.assertIn('not a Windows program', str(e.exception)); self.assertFalse(d.exists())


class Applying(unittest.TestCase):
    def setUp(self): update._cache.update({'at': 0.0, 'result': None})

    def test_a_source_checkout_is_told_to_pull_not_swapped(self):
        with mock.patch.object(update, 'how', return_value='source'):
            with self.assertRaises(RuntimeError) as e: update.apply()
        self.assertIn('git pull', str(e.exception))

    def test_nothing_newer_refuses(self):
        with mock.patch.object(update, 'how', return_value='exe'), \
             mock.patch.object(update, 'check', return_value={'newer': False, 'error': None}):
            with self.assertRaises(RuntimeError) as e: update.apply()
        self.assertIn('already on the latest', str(e.exception))

    def test_the_exe_road_downloads_writes_the_script_and_detaches_it(self):
        d = Path(tempfile.mkdtemp()).resolve(); fake_exe = d / 'Taskuary.exe'; fake_exe.write_bytes(b'MZold')   # resolve: Windows short names
        with mock.patch.object(update, 'how', return_value='exe'), \
             mock.patch.object(update, 'check', return_value={'newer': True, 'error': None, 'url': 'https://dl/T.exe'}), \
             mock.patch.object(update.sys, 'executable', str(fake_exe)), \
             mock.patch.object(update.sys, 'argv', ['Taskuary.exe', '--port', '7787']), \
             mock.patch.object(update, '_download', return_value=1234) as dl, \
             mock.patch('taskuary.spawn.popen') as pop:
            out = update.apply()
        self.assertEqual(out, {'how': 'exe', 'downloaded': 1234, 'restarting': True})
        self.assertEqual(dl.call_args[0][1], d / 'Taskuary.new.exe')          # beside the old one
        script = d / 'taskuary-update.cmd'
        self.assertTrue(script.is_file())
        body = script.read_text(encoding='utf-8')
        self.assertIn(f'PID eq {os.getpid()}', body); self.assertIn('"--port" "7787"', body)
        argv = pop.call_args[0][0]
        self.assertEqual(argv[:2], ['cmd', '/c']); self.assertEqual(Path(argv[2]), script)

    def test_the_pip_road_upgrades_then_relaunches_the_same_command_line(self):
        ok = mock.Mock(returncode=0, stdout='Successfully installed taskuary-9.9.9', stderr='')
        with mock.patch.object(update, 'how', return_value='pip'), \
             mock.patch.object(update, 'check', return_value={'newer': True, 'error': None}), \
             mock.patch('taskuary.spawn.run', return_value=ok) as run, \
             mock.patch('taskuary.spawn.popen') as pop:
            out = update.apply()
        self.assertTrue(out['restarting'])
        self.assertEqual(run.call_args[0][0][:5], [sys.executable, '-m', 'pip', 'install', '-U'])
        self.assertEqual(pop.call_args[0][0], [sys.executable, *sys.argv])

    def test_a_failed_pip_says_why_and_does_not_relaunch(self):
        bad = mock.Mock(returncode=1, stdout='', stderr='ERROR: No matching distribution')
        with mock.patch.object(update, 'how', return_value='pip'), \
             mock.patch.object(update, 'check', return_value={'newer': True, 'error': None}), \
             mock.patch('taskuary.spawn.run', return_value=bad), \
             mock.patch('taskuary.spawn.popen') as pop:
            with self.assertRaises(RuntimeError) as e: update.apply()
        self.assertIn('No matching distribution', str(e.exception)); pop.assert_not_called()


class OverTheApi(unittest.TestCase):
    def test_check_is_readable_and_apply_is_the_owners(self):
        from fastapi.testclient import TestClient
        from taskuary import guard, server
        c = TestClient(server.app)
        with mock.patch.object(update, 'check', return_value={'current': '1', 'latest': '2', 'newer': True, 'how': 'pip', 'error': None, 'url': None, 'notes': None}):
            self.assertTrue(c.get('/api/update').json()['newer'])
        self.assertTrue(guard.denied('POST', '/api/update'))
        self.assertFalse(guard.denied('GET', '/api/update'))
        # a refusal is a 422 with the reason, and the process is NOT told to exit
        with mock.patch.object(update, 'apply', side_effect=RuntimeError('this is a source checkout - git pull')), \
             mock.patch.object(update, 'exit_soon') as bye:
            r = c.post('/api/update', json={})
        self.assertEqual(r.status_code, 422); self.assertIn('git pull', r.json()['detail']); bye.assert_not_called()
        # a real swap answers first, then exits
        with mock.patch.object(update, 'apply', return_value={'how': 'exe', 'downloaded': 5, 'restarting': True}), \
             mock.patch.object(update, 'exit_soon') as bye:
            r = c.post('/api/update', json={})
        self.assertTrue(r.json()['restarting']); bye.assert_called_once()


if __name__ == '__main__':
    unittest.main()
