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
import threading
import time
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
        self.assertIn('$TASKUARY_URL', said)             # reuse this server; never start another port
        self.assertIn('NEVER use --session, --headed', said)
        # ...and it is told to LOOK with the accessibility tree, which is what the browser already
        # knows about its own page - an order of magnitude cheaper than the same page as pixels.
        self.assertIn('snapshot -i -c', said)
        self.assertIn('@ref', said)
        self.assertIn('screenshot only when', said)


class TheChatIsNamedTooTests(unittest.TestCase):
    """A browser the CHAT opens is one the pane can find.

    Every pty has carried AGENT_BROWSER_SESSION since TQ-0255, so a coding agent's browser appears
    beside its terminal on its own. The Assistant's own sessions were named only when the task
    carried needs:browser - so in the general agent tab a browser could never show up at all, and
    the owner asked why (2026-09-14). Naming costs one environment variable and starts nothing;
    LAUNCHING Chrome and granting a shell still belong to a task that asked for a browser.
    """

    def _turn(self, tags=''):
        """One assistant turn on a CLI brain, with everything outside this decision held still."""
        from taskuary import general, llm as llm_mod
        s = MemoryStore()
        tid = s.create_task({'Title': 'Look something up', 'Summary': 'go', 'Kind': 'general',
                             'Status': 'open', 'Tags': tags}, 'owner')
        session = general.GeneralSession(s, tid)
        session.pick, session.provider, session.model = 'cli:coder', 'Claude Code (your CLI)', ''
        seen = {}
        def build(store, **kw): seen.update(kw); return None                  # no brain: the turn stops here
        with mock.patch.object(llm_mod, 'build_llm', side_effect=build), \
             mock.patch.object(bv, 'start', return_value=True) as started:
            with self.assertRaises(RuntimeError):                             # "the selected AI connector is unavailable"
                session.send_prompt('go', echo=False)
        return seen, started

    def test_a_plain_chat_is_bound_without_a_browser_being_started(self):
        seen, started = self._turn()
        self.assertIn('AGENT_BROWSER_SESSION', seen.get('extra_env') or {})
        self.assertFalse(seen.get('cli_tools'), 'a chat that did not ask for a browser gets no shell')
        started.assert_not_called()

    def test_a_task_that_asked_for_one_gets_the_browser_and_the_brief(self):
        seen, started = self._turn(tags=bv.WANTS)
        self.assertIn('AGENT_BROWSER_SESSION', seen.get('extra_env') or {})
        self.assertTrue(seen.get('cli_tools'), 'it has to be able to RUN agent-browser')
        started.assert_called_once()


class AskingForOneLaterTests(unittest.TestCase):
    """The agent tab's own button. Before it, needs:browser could only be set when the task was
    made, so a conversation that turned out to need a page never got one."""

    def _client(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        return TestClient(server.app), server

    def test_pressing_it_marks_the_task_and_starts_the_browser_on_the_live_session(self):
        from taskuary import general
        s = MemoryStore()
        tid = s.create_task({'Title': 'Look at the portal', 'Kind': 'general', 'Status': 'open'}, 'owner')
        client, server = self._client()
        class Live:                                    # a real object: a Mock's info() is not JSON
            sid, browser_wanted = 'sid-1', False
            def info(self, tail=0): return {'sid': 'sid-1', 'alive': True, 'busy': False}
        live = Live()
        with mock.patch.object(server, 'store', s), \
             mock.patch.object(bv, 'installed', return_value=True), \
             mock.patch.object(general, 'session_for', return_value=live), \
             mock.patch.object(bv, 'start') as start, \
             mock.patch.object(server.threading, 'Thread') as thread:
            r = client.post(f'/api/tasks/{tid}/assistant/browser')
            launched = thread.call_args.kwargs                 # while bv.start is still the patched one
            start.assert_not_called()                          # it is launched on the thread, not inline
        self.assertEqual(r.status_code, 200)
        self.assertTrue(bv.wanted(s.get_task(tid)), 'the press IS the mark on the task')
        self.assertTrue(live.browser_wanted, 'and the running session hands its next turn the brief')
        self.assertIs(launched['target'], start)
        self.assertEqual(launched['args'], ('sid-1',))

    def test_with_no_session_yet_it_still_marks_the_task(self):
        from taskuary import general
        s = MemoryStore()
        tid = s.create_task({'Title': 'Look at the portal', 'Kind': 'general', 'Status': 'open'}, 'owner')
        client, server = self._client()
        with mock.patch.object(server, 'store', s), \
             mock.patch.object(bv, 'installed', return_value=True), \
             mock.patch.object(general, 'session_for', return_value=None), \
             mock.patch.object(general, 'provider_options', return_value=[]):
            self.assertEqual(client.post(f'/api/tasks/{tid}/assistant/browser').status_code, 200)
        self.assertTrue(bv.wanted(s.get_task(tid)))

    def test_it_says_so_rather_than_promising_a_browser_that_is_not_installed(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Look at the portal', 'Kind': 'general', 'Status': 'open'}, 'owner')
        client, server = self._client()
        with mock.patch.object(server, 'store', s), mock.patch.object(bv, 'installed', return_value=False):
            r = client.post(f'/api/tasks/{tid}/assistant/browser')
        self.assertEqual(r.status_code, 422)
        self.assertIn('agent-browser', r.json()['detail'])
        self.assertFalse(bv.wanted(s.get_task(tid)), 'and the task is not marked for a browser it cannot have')


class TheShapeOfThePageTests(unittest.TestCase):
    """The pane says what shape it is; the page renders that shape, so there is nothing to letterbox."""

    def test_the_viewport_is_set_on_the_session_and_never_waited_on(self):
        with mock.patch.object(bv.shutil, 'which', return_value='ab'), \
             mock.patch.object(bv.spawn, 'popen') as popen:
            self.assertTrue(bv.set_viewport('abc123', 1200, 1480))
        self.assertEqual(popen.call_args.args[0],
                         ['ab', '--session', 'tq-abc123', 'set', 'viewport', '1200', '1480'])
        # a piped agent-browser call blocks until the DAEMON exits, which is a hang, not a resize
        self.assertEqual(popen.call_args.kwargs.get('stdout'), subprocess.DEVNULL)

    def test_a_nonsense_shape_is_refused_rather_than_handed_to_chrome(self):
        with mock.patch.object(bv.shutil, 'which', return_value='ab'), \
             mock.patch.object(bv.spawn, 'popen') as popen:
            self.assertFalse(bv.set_viewport('abc123', 0, 800))
            self.assertFalse(bv.set_viewport('abc123', 1200, 99_000))
        popen.assert_not_called()

    def test_with_no_tool_installed_it_simply_says_no(self):
        with mock.patch.object(bv.shutil, 'which', return_value=None):
            self.assertFalse(bv.set_viewport('abc123', 1200, 1480))

    def test_the_endpoint_hands_the_pane_shape_through(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        with mock.patch.object(bv, 'set_viewport', return_value=True) as sv:
            r = TestClient(server.app).post('/api/terminals/sid-9/browser/viewport', json={'w': 1200, 'h': 1480})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'set': True})
        self.assertEqual(sv.call_args.args, ('sid-9', 1200, 1480))


class StartingItTests(unittest.TestCase):
    def test_it_is_bound_to_the_session_and_restored_from_the_owners_own_cookies(self):
        seen = {}
        with mock.patch.object(bv.shutil, 'which', return_value='ab'), \
             mock.patch.object(bv, 'state', side_effect=[{'open': False}, {'open': True}]), \
             mock.patch.object(bv.spawn, 'popen', side_effect=lambda cmd, **kw: seen.update(cmd=cmd)):
            self.assertTrue(bv.start('abc123', 'https://portal.example'))
        self.assertEqual(seen['cmd'][:5], ['ab', '--session', 'tq-abc123', '--restore', bv.RESTORE_KEY])
        self.assertEqual(seen['cmd'][-2:], ['open', 'https://portal.example'])
        # ...and it does not announce itself. agent-browser leaves navigator.webdriver true by
        # default (measured 2026-09-14); a login page reads that before anything subtler.
        self.assertIn('--args', seen['cmd'])
        self.assertIn('AutomationControlled', seen['cmd'][seen['cmd'].index('--args') + 1])
        # HEADED is not how this browser is hidden - the pane is. A headed Chrome on Windows is a
        # window across the owner's own work (the owner, 2026-09-14: "it should not show up in
        # random. but in the browser").
        self.assertNotIn('--headed', seen['cmd'])

    def test_a_browser_the_agent_already_opened_is_not_opened_twice(self):
        with mock.patch.object(bv.shutil, 'which', return_value='ab'), \
             mock.patch.object(bv, 'state', return_value={'open': True}), \
             mock.patch.object(bv.spawn, 'popen') as popen:
            self.assertTrue(bv.start('abc123'))
        popen.assert_not_called()

    def test_two_simultaneous_starts_launch_one_browser_for_the_session(self):
        opened, calls = threading.Event(), []
        def launch(cmd, **kwargs):
            calls.append(cmd); time.sleep(.05); opened.set()
        with mock.patch.object(bv.shutil, 'which', return_value='ab'), \
             mock.patch.object(bv, 'state', side_effect=lambda *a, **k: {'open': opened.is_set()}), \
             mock.patch.object(bv.spawn, 'popen', side_effect=launch):
            threads = [threading.Thread(target=bv.start, args=('one-session',)) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(2)
        self.assertEqual(len(calls), 1)

    def test_without_the_tool_it_says_no_rather_than_raising(self):
        with mock.patch.object(bv.shutil, 'which', return_value=None):
            self.assertFalse(bv.start('abc123'))

    def test_a_browser_that_will_not_launch_is_a_warning_not_a_dead_session(self):
        with mock.patch.object(bv.shutil, 'which', return_value='ab'), \
             mock.patch.object(bv, 'state', return_value={'open': False}), \
             mock.patch.object(bv.spawn, 'popen', side_effect=OSError('no chrome')):
            self.assertFalse(bv.start('abc123'))

    def test_it_goes_with_the_session(self):
        """Term._pump calls this when the pty ends - one Chrome per finished task, idling, is
        what the close is for."""
        with mock.patch.object(bv.shutil, 'which', return_value='ab'), \
             mock.patch.object(bv, '_read', return_value='9222'), \
             mock.patch.object(bv.spawn, 'run') as run:
            bv.close('abc123')
        self.assertEqual(run.call_args[0][0], ['ab', '--session', 'tq-abc123', 'close'])


if __name__ == '__main__':
    unittest.main()
