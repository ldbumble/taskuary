"""A job done in the browser has to repeat in one.

The walk works: the owner asks for something behind a sign-in, the assistant opens a walk-through
with a browser beside it, the agent drives the page, stops at the credential form, the owner types
it in the pane and hands back. Then the walk is promoted to a daily job - and until now that job
went down the REPORT road, whose CLI is built read-only and with no shell (reports.run_agent), so
`agent-browser` was not there to call and the sign-in the owner had typed was not there to reuse.
The agent that tried said exactly that and refused to save a report it knew would fail (the owner,
2026-09-15: "why can't it save the workflow and browser state for tomorrow? that's the whole idea
of a workflow").

A browser job is now a workflow: dispatched to a real session, whose task carries `needs:browser`,
which is what opens the same named browser restored from the owner's own profile.
"""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import blackboard, browserview, concierge, general, ingest, llm, reports, selfclose, server, terminal, triage, workflows
from taskuary.store import MemoryStore


def store():
    s = MemoryStore()
    s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    s.set_setting('general_auto_enabled', '1', 't'); s.set_setting('coder_auto_enabled', '1', 't')
    return s


def browser_job(s, **cfg):
    base = {'type': 'agent', 'title': 'Daily time card', 'agent': 'coder', 'browser': True, 'daily_at': '08:00',
            'prompt': 'Open the portal, read today\'s message in the secure area, and report it.'}
    base.update(cfg)
    return s.save_source({'Channel': 'report', 'Address': base['title'], 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps(base)}, 'o')


def run_it(s, sid, trigger='schedule'):
    session = mock.Mock()
    with mock.patch.object(general, 'start_session', return_value=session), mock.patch.object(general, 'history', return_value=[]), \
         mock.patch.object(ingest, 'ingest_message'), mock.patch.object(triage, 'classify_intent'), \
         mock.patch.object(blackboard, 'live_count', return_value=0), mock.patch('taskuary.llm.make_cli_llm') as cli:
        out = reports.run_report_source(s, s.get_source(sid), None, trigger=trigger)
    return out, session, cli


class BrowserJobRepeatsTests(unittest.TestCase):
    def test_a_browser_job_is_a_workflow_even_though_it_only_reads(self):
        s = store(); sid = browser_job(s)
        d = workflows.definition(s, s.get_source(sid))
        self.assertTrue(workflows.is_workflow(s.get_source(sid)))
        self.assertEqual((d['browser'], d['runs_on'], d['allowed_actions']), (True, 'general', ['read']))
        self.assertFalse(workflows.is_workflow({'type': 'agent', 'prompt': 'read a database'}))     # an ordinary report is still a report

    def test_its_run_asks_for_a_browser_and_is_told_the_sign_in_is_restored(self):
        s = store(); sid = browser_job(s)
        out, session, cli = run_it(s, sid)
        t = s.get_task(out['task_id'])
        self.assertTrue(browserview.wanted(t), f"the run task must ask for a browser - Tags={t['Tags']!r}")
        text = session.send_prompt.call_args[0][0]
        self.assertIn('BROWSER:', text)
        self.assertIn('restored', text)                       # yesterday's sign-in is the point
        self.assertIn('LOOK FIRST', text)                     # a scheduled run happens when nobody is there to ask
        self.assertIn('ask them to type it in the pane', text)
        cli.assert_not_called()                               # never the read-only report CLI, which has no shell

    def test_a_job_that_never_used_a_browser_asks_for_none(self):
        s = store(); sid = browser_job(s, browser=False, access='write')
        out, session, _ = run_it(s, sid)
        self.assertFalse(browserview.wanted(s.get_task(out['task_id'])))
        self.assertNotIn('BROWSER:', session.send_prompt.call_args[0][0])


class PromotionTests(unittest.TestCase):
    """The walk that used the browser says so on the job it becomes."""

    def _promote(self, tags):
        s = store(); tid = s.create_task({'Title': 'Daily time card', 'Summary': 'Read the portal message',
                                          'Kind': 'general', 'Status': 'open', 'Tags': tags}, 'owner')
        s.upsert_agent('my-claude', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        s.add_comment(tid, 'owner', general.USER_TYPE, 'Read the message in the secure area every morning.')
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Signed in and read it; here is today\'s message.')
        made = json.dumps({'title': 'Daily time card', 'prompt': 'Open the portal and report the secure-area message.'})
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(llm, 'build_llm', return_value=lambda *a, **k: made):
            r = TestClient(server.app).post(f'/api/tasks/{tid}/assistant/report', json={'pick': 'cli:my-claude'})
        self.assertEqual(r.status_code, 200, r.text)
        return s, json.loads(s.get_source(r.json()['sourceId'])['ConfigJson'])

    def test_a_walk_with_a_browser_becomes_a_browser_workflow(self):
        s, cfg = self._promote(browserview.WANTS)
        self.assertTrue(cfg.get('browser'))
        self.assertTrue(workflows.is_workflow(cfg))

    def test_a_walk_without_one_is_an_ordinary_report(self):
        s, cfg = self._promote('')
        self.assertFalse(cfg.get('browser'))
        self.assertFalse(workflows.is_workflow(cfg))


class TheBrowserIsARoadTests(unittest.TestCase):
    """Asked for a job on a website, the sorter must not send the owner looking for a connector that
    cannot exist: the composer's answer was "connect a browser/web automation source", and there is
    no such card in Connections. Work on a website is the walk-through's, and the walk has a browser."""

    def test_the_setup_sorter_is_told_a_website_is_the_walk_throughs(self):
        p = concierge.SETUP_SORT_SYSTEM
        self.assertIn('WORK DONE ON A WEBSITE IS ALWAYS INVESTIGATE', p)
        self.assertIn('there is no browser connector', p)


class AskMarkerIsNotProseTests(unittest.TestCase):
    def test_the_marker_comes_out_of_what_the_owner_reads(self):
        said = ('The login page is open.\n\n'
                '[[TASKUARY-ASK]] Have you signed in successfully? | Signed in | Login failed')
        self.assertEqual(selfclose.without_ask(said), 'The login page is open.')
        _, question, choices = selfclose.ask_marker(said)
        self.assertEqual((question, choices), ('Have you signed in successfully?', ['Signed in', 'Login failed']))
        self.assertEqual(selfclose.without_ask('nothing to strip'), 'nothing to strip')


class ABrowserJobNeedsHandsTests(unittest.TestCase):
    """A browser is driven from a shell, and only a CLI has one. The repeat run opened its browser,
    read its brief, and answered "opening the secure area cannot be done from here" - it had been
    handed to the quick API brain the chat prefers, which cannot run a command at all (2026-09-15)."""

    def _store_with_both(self):
        s = store()
        row = s.get_connector_by_type('openai')
        s.save_connector({'ConnectorId': row['ConnectorId'], 'Active': 1, 'Secret': 'sk-test',
                          'Name': 'Work model', 'ConfigJson': '{"model":"gpt-test"}'}, 'owner')
        return s

    def test_a_task_with_a_browser_defaults_to_a_cli_not_the_api_brain(self):
        s = self._store_with_both()
        plain = s.create_task({'Title': 'Compare the options', 'Kind': 'general', 'Status': 'open'}, 'o')
        withbrowser = s.create_task({'Title': 'Daily time card', 'Kind': 'general', 'Status': 'open',
                                     'Source': 'workflow', 'SourceRef': 'workflow:5', 'Tags': browserview.WANTS}, 'o')
        self.assertFalse(general.default_pick(s, s.get_task(plain)).startswith('cli:'))       # chat keeps the quick brain
        self.assertTrue(general.default_pick(s, s.get_task(withbrowser)).startswith('cli:'))  # a browser job gets hands


class TheSignInWasAOneOffTests(unittest.TestCase):
    """What the owner typed once is not a step of every run. The first draft off a browser walk told
    the daily job to open the login page and wait for the owner - so the repeat run walked to a
    sign-in screen it did not need and stopped there (2026-09-15)."""

    def test_the_draft_off_a_browser_walk_is_written_for_a_run_nobody_is_watching(self):
        s = store(); seen = []
        def brain(system, user, **kw):
            seen.append(system)
            return json.dumps({'title': 'Daily time card', 'prompt': 'Open the secure area and report the message.'})
        for tags, browser in ((browserview.WANTS, True), ('', False)):
            tid = s.create_task({'Title': 'Daily time card', 'Kind': 'general', 'Status': 'open', 'Tags': tags}, 'o')
            s.add_comment(tid, 'owner', general.USER_TYPE, 'Read the portal message each morning.')
            s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Signed in and read it.')
            with mock.patch.object(llm, 'build_llm', return_value=brain):
                general.report_draft(s, tid)
            self.assertEqual('starts SIGNED IN' in seen[-1], browser)
            self.assertEqual('Never make waiting for the' in seen[-1], browser)


class HandingOverTheKeyboardTests(unittest.TestCase):
    """Told to let the owner type a credential, the agent asked for the User ID and then kept working
    the same tab - snapshot, get url, read, and `open` on the sign-in URL again, on top of a
    half-finished ADP sign-in. The SSO chain does not survive being re-entered: the tab ended on
    about:blank and it polled a blank page for hours (the owner, 2026-09-15: "it showed the browser,
    then turned white ... just spinning")."""

    def test_the_brief_tells_it_to_stop_and_not_touch_the_tab(self):
        b = browserview.brief()
        self.assertIn('WHEN YOU HAND THEM THE KEYBOARD, STOP', b)
        self.assertIn('run no browser command at all until they answer', b)
        for forbidden in ('re-open the page', 'reload it', 'navigate', 'poll'):
            self.assertIn(forbidden, b)
        self.assertIn('NEVER type a password', b)            # the rule it already had, still there


class TheWatchedBrowserOutlivesAPauseTests(unittest.TestCase):
    """agent-browser shuts its daemon down after an hour of inactivity by default. A walk left
    overnight on a half-finished ADP sign-in came back to a white pane: the browser had gone, and the
    next command got a fresh empty one (the owner, 2026-09-15: "it showed the browser, then turned
    white"). This browser belongs to the session and is closed by close(), not by a clock.

    AND THE CLOCK IS SET THE SAME WAY BY EVERY COMMAND. agent-browser fingerprints a command's
    launch options into <session>.config, and the idle timeout is part of the fingerprint (--restore
    and --args are not; measured 2026-09-18 with 0, 720h and raw ms alike). A launch flag that the
    agent's own flagless `agent-browser open`, the pane's viewport resize and the address bar do not
    carry is a mismatch, and on a mismatch agent-browser SHUTS THE DAEMON DOWN and starts a default
    one on about:blank - no restored profile, the idle hour back, and the pane either white (the new
    blank page) or black (still attached to the dying daemon). "It either appears but is plain white,
    or freezes and is just black" (the owner, 2026-09-18). So the timeout rides in the ENVIRONMENT
    every command shares, launch included, and never as a flag."""

    def setUp(self):
        self.seen = []
        def popen(cmd, **kw): self.seen.append((cmd, kw)); raise OSError('not really launching one')
        self.patches = [mock.patch('shutil.which', return_value='agent-browser'),
                        mock.patch.object(browserview, 'state', return_value={'open': True, 'url': '', 'port': 1}),
                        mock.patch('taskuary.spawn.popen', popen), mock.patch('taskuary.spawn.run', popen)]
        for p in self.patches: p.start()
    def tearDown(self):
        for p in self.patches: p.stop()

    def test_the_idle_timeout_is_in_the_environment_of_every_pty(self):
        self.assertEqual(browserview.env('abc123')['AGENT_BROWSER_IDLE_TIMEOUT_MS'], '0')

    def test_the_launch_carries_no_idle_flag_and_the_same_environment(self):
        with mock.patch.object(browserview, 'state', return_value={'open': False, 'url': '', 'port': 0}):
            browserview.start('abc123')
        cmd, kw = self.seen[0]
        self.assertNotIn('--idle-timeout', cmd)                                      # a flag the agent's commands would not match
        self.assertEqual(cmd[cmd.index('--restore') + 1], browserview.RESTORE_KEY)   # and still the owner's profile
        self.assertEqual(kw['env']['AGENT_BROWSER_IDLE_TIMEOUT_MS'], '0')
        self.assertEqual(kw['env']['AGENT_BROWSER_SESSION'], 'tq-abc123')

    def test_every_door_the_server_opens_matches_the_launch(self):
        """set viewport (the pane's shape), open (the address bar) and close each run agent-browser
        from the server; a single one without the environment relaunches the daemon."""
        browserview.set_viewport('abc123', 1200, 800)
        with self.assertRaises(ValueError): browserview.navigate('abc123', 'https://example.test')
        browserview.home().mkdir(parents=True, exist_ok=True); (browserview.home() / 'tq-abc123.stream').write_text('1')
        browserview.close('abc123')
        self.assertEqual(len(self.seen), 3)
        for cmd, kw in self.seen:
            self.assertEqual(kw['env']['AGENT_BROWSER_IDLE_TIMEOUT_MS'], '0', cmd)
            self.assertEqual(kw['env']['AGENT_BROWSER_SESSION'], 'tq-abc123', cmd)


if __name__ == '__main__':
    unittest.main()
