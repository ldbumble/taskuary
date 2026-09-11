import tempfile
import unittest
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import cliinstall, cli_install_terminal as visible, server, terminal, guard
from taskuary.store import MemoryStore


class VisibleInstallerTests(unittest.TestCase):
    def setUp(self):
        cliinstall.reset()
        self.addCleanup(cliinstall.reset)
        self.store = MemoryStore()

    def test_opening_terminal_does_not_run_a_second_installer_on_repeated_click(self):
        term = mock.Mock(sid='installer-test', alive=True)
        with mock.patch.object(terminal, 'Term', return_value=term), \
             mock.patch.object(visible.threading, 'Thread') as thread, \
             mock.patch.object(cliinstall, 'plan', return_value=[{'how': 'script'}]):
            first = visible.start(self.store, 'devin')
            again = visible.start(self.store, 'devin')
        self.addCleanup(lambda: terminal.SESSIONS.pop('installer-test', None))
        self.assertEqual(first['sid'], 'installer-test')
        self.assertEqual(again['taskId'], first['taskId'])
        self.assertEqual(thread.call_count, 1)
        self.assertFalse(term.keep_transcript)
        self.assertEqual(self.store.get_task(first['taskId'])['Kind'], 'setup')

    def test_closed_terminal_does_not_report_success(self):
        term = mock.Mock(alive=False, n=1)
        with tempfile.TemporaryDirectory() as folder:
            run = visible.ShellRunner(term, Path(folder), True)
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                run(['anything'])
        term.write.assert_not_called()

    def test_return_code_comes_from_completion_file_not_printed_success_text(self):
        term = mock.Mock(alive=True, n=1)
        term.scrollback.side_effect = ['', 'The installer says success but exited with failure']
        with tempfile.TemporaryDirectory() as folder:
            def command(cmd, result, windows):
                result.write_text('1', encoding='utf-8')
                return 'installer command'
            with mock.patch.object(visible, 'command_line', side_effect=command):
                code, output = visible.ShellRunner(term, Path(folder), True)(['installer'])
            self.assertEqual(code, 1)
            self.assertIn('failure', output)
            self.assertFalse(list(Path(folder).iterdir()))

    def test_arguments_are_quoted_without_reinterpreting_shell_syntax(self):
        script = visible.command_line(['installer', "a'b", '$(do-not-run)', 'a; b'], Path('result.exit'), True)
        self.assertIn("& 'installer' 'a''b' '$(do-not-run)' 'a; b'", script)
        self.assertIn('WriteAllText', script)

    def test_terminal_control_codes_are_not_written_back_into_powershell(self):
        term = mock.Mock(alive=True, n=1)
        visible.ShellRunner(term, Path('.'), True).message('\x1b[31mFailure\x1b[0m\r\nDetails')
        term.write.assert_called_once_with("Write-Host 'Failure Details'\r")

    def test_visible_failure_has_a_clean_summary_instead_of_raw_terminal_output(self):
        run = mock.Mock(return_value=(1, '\x1b[31mParserError\x1b[0m\r\nPS C:\\>'))
        result = cliinstall.install('devin', runner=run, system='Windows')
        self.assertEqual(result['phase'], 'failed')
        self.assertIn('exited 1', result['detail'])
        self.assertIn('terminal', result['detail'])
        self.assertNotIn('\x1b', result['detail'])

    def test_api_passes_terminal_request_and_agent_tokens_cannot_start_it(self):
        c = TestClient(server.app)
        with mock.patch.object(visible, 'start', return_value={'sid': 'test', 'taskId': 42, 'phase': 'installing'}) as start:
            r = c.post('/api/cli/install/terminal', json={'name': 'devin', 'terminal': True})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()['sid'], 'test')
            self.assertEqual(start.call_args.args[1], 'devin')
        self.assertTrue(guard.denied('POST', '/api/cli/install/terminal'))
        self.assertTrue(guard.denied('POST', '/api/cli/update/terminal'))
