"""A CLI the agent runner can start is INSTALLED, whichever PATH found it.

A long-running app keeps the environment it was launched with, so a CLI installed after the app
started - or installed by a vendor that writes the USER path - resolves on the registry PATH and
not on this process's. `agents._resolve_cmd` has always known that and falls back to
`_fresh_path()`; `clis.detect` and `cliinstall.find` did not, and detect's comment asserted the two
agreed.

They did not. On the owner's machine, 2026-09-11: codex at
%LOCALAPPDATA%\\Programs\\OpenAI\\Codex\\bin ran every agent session while Connections > AI CLI
agents said it was not installed - offering to Install a CLI that was already there, and hiding the
Update button, which is drawn only over a CLI that is actually here.
"""
import os
import unittest
from pathlib import Path
from unittest import mock

from taskuary import agents, cliinstall, clis


class FreshPathTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()
        self.exe = Path(self.dir) / ('codex.exe' if os.name == 'nt' else 'codex')
        self.exe.write_text('#!/bin/sh\ntrue\n')
        self.exe.chmod(0o755)
        # the app's own PATH does NOT have it - that is the whole point
        env = mock.patch.dict(os.environ, {'PATH': os.path.dirname(os.__file__)})
        env.start(); self.addCleanup(env.stop)
        fresh = mock.patch.object(agents, '_fresh_path', return_value=self.dir)
        fresh.start(); self.addCleanup(fresh.stop)

    def test_the_process_path_alone_does_not_find_it(self):
        """The precondition. Without this the test would pass for the wrong reason."""
        import shutil
        self.assertIsNone(shutil.which('codex'))

    def test_the_page_says_installed_when_the_runner_can_start_it(self):
        row = next(r for r in clis.detect() if r['name'] == 'codex')
        self.assertTrue(row['installed'], 'the runner starts it, so the page must not offer Install')
        self.assertEqual(Path(row['path']).resolve(), self.exe.resolve())
        self.assertTrue(row['updatable'], 'and the Update button has something to update')

    def test_the_installer_finds_it_too_so_update_has_a_binary(self):
        """cliinstall.update refuses with "not on this machine" when find() comes back empty."""
        self.assertEqual(Path(cliinstall.find('codex')).resolve(), self.exe.resolve())

    def test_a_cli_that_is_nowhere_is_still_not_installed(self):
        """The fallback must not make everything look present."""
        row = next(r for r in clis.detect() if r['name'] == 'gemini')
        self.assertFalse(row['installed'])
        self.assertFalse(row['updatable'])
        self.assertEqual(cliinstall.find('gemini'), '')
