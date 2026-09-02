"""A session that OWNS its browser.

The coupling used to be one environment variable and two files on disk: every pty carries
AGENT_BROWSER_SESSION=tq-<sid>, and if the agent happened to run `agent-browser`, Taskuary
noticed the state files it left and showed the page. Nothing started a browser, nothing told
the agent one was wanted, and a task that plainly needs one - a portal with no API, a page
behind a login - began with nothing on screen and an owner watching text scroll (the owner,
2026-08-31: "the terminal doesn't know how to manage it, it has to be a custom session").

So the owner marks the task, and the SESSION owns the browser: started with it, bound to it by
name, restored from the owner's own saved cookies, named in the agent's seed, closed with it.
"""
import subprocess
import unittest
from unittest import mock

from taskuary import browserview as bv, terminal
from taskuary.store import MemoryStore


class AskingForOneTests(unittest.TestCase):
    def test_the_tag_is_read_exactly(self):
        self.assertTrue(bv.wanted({'Tags': bv.WANTS}))
        self.assertTrue(bv.wanted({'Tags': f'repo:acme/census,{bv.WANTS}'}))
        self.assertFalse(bv.wanted({'Tags': 'needs:browsers'}))       # not a prefix match
        self.assertFalse(bv.wanted({'Tags': 'repo:acme/census'}))
        self.assertFalse(bv.wanted({}))
        self.assertFalse(bv.wanted(None))

    def test_the_agent_is_told_only_when_there_is_one(self):
        s = MemoryStore()
        asked = s.create_task({'Title': 'portal', 'Kind': 'coding', 'Tags': bv.WANTS}, 'o')
        plain = s.create_task({'Title': 'code', 'Kind': 'coding'}, 'o')
        with mock.patch.object(terminal.shutil, 'which', return_value='/usr/bin/agent-browser'):
            self.assertIn('A BROWSER IS OPEN', terminal.seed_text(s, asked, repo=None, cwd=''))
            self.assertNotIn('A BROWSER IS OPEN', terminal.seed_text(s, plain, repo=None, cwd=''))

    def test_nothing_is_promised_when_the_tool_is_not_installed(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'portal', 'Kind': 'coding', 'Tags': bv.WANTS}, 'o')
        with mock.patch.object(terminal.shutil, 'which', return_value=None):
            self.assertNotIn('A BROWSER IS OPEN', terminal.seed_text(s, tid, repo=None, cwd=''))

    def test_what_the_agent_is_told_covers_driving_it_and_the_line_it_must_not_cross(self):
        said = bv.brief()
        self.assertIn('agent-browser', said)
        self.assertIn('skills get core', said)          # the CLI documents its own commands
        self.assertIn('NEVER type a password', said)    # ...and the owner types those, in the pane


class StartingItTests(unittest.TestCase):
    def test_it_is_bound_to_the_session_and_restored_from_the_owners_own_cookies(self):
        seen = {}
        with mock.patch.object(bv.shutil, 'which', return_value='ab'), \
             mock.patch.object(bv, 'state', side_effect=[{'open': False}, {'open': True}]), \
             mock.patch.object(bv.subprocess, 'Popen', side_effect=lambda cmd, **kw: seen.update(cmd=cmd)):
            self.assertTrue(bv.start('abc123', 'https://portal.example'))
        self.assertEqual(seen['cmd'][:6], ['ab', '--session', 'tq-abc123', '--restore', bv.RESTORE_KEY, 'open'])
        self.assertEqual(seen['cmd'][6], 'https://portal.example')

    def test_a_browser_the_agent_already_opened_is_not_opened_twice(self):
        with mock.patch.object(bv.shutil, 'which', return_value='ab'), \
             mock.patch.object(bv, 'state', return_value={'open': True}), \
             mock.patch.object(bv.subprocess, 'Popen') as popen:
            self.assertTrue(bv.start('abc123'))
        popen.assert_not_called()

    def test_without_the_tool_it_says_no_rather_than_raising(self):
        with mock.patch.object(bv.shutil, 'which', return_value=None):
            self.assertFalse(bv.start('abc123'))

    def test_a_browser_that_will_not_launch_is_a_warning_not_a_dead_session(self):
        with mock.patch.object(bv.shutil, 'which', return_value='ab'), \
             mock.patch.object(bv, 'state', return_value={'open': False}), \
             mock.patch.object(bv.subprocess, 'Popen', side_effect=OSError('no chrome')):
            self.assertFalse(bv.start('abc123'))

    def test_it_goes_with_the_session(self):
        """Term._pump calls this when the pty ends - one Chrome per finished task, idling, is
        what the close is for."""
        with mock.patch.object(bv.shutil, 'which', return_value='ab'), \
             mock.patch.object(bv, '_read', return_value='9222'), \
             mock.patch.object(bv.subprocess, 'run') as run:
            bv.close('abc123')
        self.assertEqual(run.call_args[0][0], ['ab', '--session', 'tq-abc123', 'close'])


if __name__ == '__main__':
    unittest.main()
