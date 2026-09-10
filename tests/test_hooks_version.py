"""Claude Code hooks are installed against a known CLI version: the version is read and recorded, one below the
validated floor warns instead of pretending the status is complete (PW-223)."""
import unittest
from unittest import mock

from taskuary import hooks


class HooksVersion(unittest.TestCase):
    def test_the_installed_version_is_read_and_a_missing_cli_is_none(self):
        with mock.patch.object(hooks.subprocess, 'run', return_value=mock.Mock(stdout='2.1.3 (Claude Code)\n', returncode=0)):
            self.assertEqual(hooks.cli_version('claude'), '2.1.3')
        with mock.patch.object(hooks.subprocess, 'run', side_effect=OSError('no such file')):
            self.assertIsNone(hooks.cli_version('claude'))
        with mock.patch.object(hooks.subprocess, 'run', return_value=mock.Mock(stdout='nonsense', returncode=0)):
            self.assertIsNone(hooks.cli_version('claude'))

    def test_supported_is_the_floor_that_carries_every_event_we_install(self):
        self.assertTrue(hooks.supported('2.0.0')); self.assertTrue(hooks.supported('2.1.3')); self.assertTrue(hooks.supported('10.0.0'))
        self.assertFalse(hooks.supported('1.0.90')); self.assertFalse(hooks.supported(None)); self.assertFalse(hooks.supported(''))

    def test_install_reports_the_version_it_installed_against(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d, mock.patch.object(hooks, 'cli_version', return_value='1.0.90') as cv, \
             mock.patch.object(hooks.logger, 'warning') as warn:
            self.assertTrue(hooks.install(d, base='http://127.0.0.1:1', cmd='claude'))
            self.assertEqual(cv.call_args.args, ('claude',)); self.assertTrue(warn.called); self.assertIn('1.0.90', str(warn.call_args))
        with tempfile.TemporaryDirectory() as d, mock.patch.object(hooks, 'cli_version', return_value='2.1.3'), \
             mock.patch.object(hooks.logger, 'warning') as warn:
            self.assertTrue(hooks.install(d, base='http://127.0.0.1:1', cmd='claude')); self.assertFalse(warn.called)
        # without a named CLI nothing is executed - an install is a file write, not a process
        with tempfile.TemporaryDirectory() as d, mock.patch.object(hooks, 'cli_version') as cv:
            self.assertTrue(hooks.install(d, base='http://127.0.0.1:1')); self.assertFalse(cv.called)
