"""Interactive terminals: a real pty around a process, its bytes fanned out to sockets.
Spawns python itself (no CLI agent required), so it runs the same on every OS in CI.
"""
import json, os, sys, time, unittest
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import server, terminal

c = TestClient(server.app)
ECHO = [sys.executable, '-c', "print('hello-from-pty')"]


# ConPTY holds the pipe open for ~8s after the child exits, so "the CLI has finished" is not a
# fast condition on Windows - 8s was right on the line and made every wait here a coin flip.
def _wait(fn, secs=20):
    end = time.time() + secs
    while time.time() < end:
        if fn(): return True
        time.sleep(0.05)
    return False


class TerminalTests(unittest.TestCase):
    def test_pty_streams_into_scrollback_and_dies(self):
        t = terminal.Term(ECHO, os.getcwd(), 'test')
        terminal.SESSIONS[t.sid] = t
        try:
            self.assertTrue(_wait(lambda: 'hello-from-pty' in t.scrollback()), t.scrollback()[:200])
            self.assertTrue(_wait(lambda: not t.alive))
            self.assertIn(t.sid, [x['sid'] for x in terminal.listing()])   # kept until nobody is watching
        finally:
            terminal.close(t.sid)
        self.assertNotIn(t.sid, [x['sid'] for x in terminal.listing()])

    def test_websocket_carries_output_and_exit(self):
        t = terminal.Term(ECHO, os.getcwd(), 'test')
        terminal.SESSIONS[t.sid] = t
        try:
            with c.websocket_connect(f'/api/terminals/{t.sid}/ws') as ws:
                got, exited = '', False
                for _ in range(40):
                    m = ws.receive_json()
                    if m['type'] == 'out': got += m['data']
                    if m['type'] == 'exit': exited = True; break
                    if 'hello-from-pty' in got and exited: break
                self.assertIn('hello-from-pty', got)
        finally:
            terminal.close(t.sid)

    def test_api_validates_before_spawning_anything(self):
        self.assertEqual(c.post('/api/terminals', json={'agent': 'ghost-cli'}).status_code, 422)
        self.assertEqual(c.post('/api/terminals', json={'cwd': os.path.join(os.getcwd(), 'no-such-dir')}).status_code, 422)
        self.assertEqual(c.delete('/api/terminals/nope').status_code, 404)
        self.assertEqual(c.get('/api/terminals').json()['data'], [])

    def test_wrapping_up_reads_the_screen_then_closes_everything(self):
        """"Done - wrap it up" asks the agent NOTHING. It takes the transcript that is already on
        screen, ends the session, has the main AI write the report from it, and leaves the reply
        drafted for approval. Nothing typed at the agent, nothing left running."""
        tid = c.post('/api/tasks', json={'Title': 'lookJobCode 325', 'Kind': 'coding'}).json()['taskId']
        server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:CCC', 'Channel': 'email',
                                  'SourceName': 'me@corp.com', 'FromEmail': 'john@corp.com',
                                  'BodyText': 'all CNA should be restricted', 'Status': 'routed'})
        t = terminal.Term(ECHO, os.getcwd(), 'test')
        t.task_id, t.agent = tid, 'coder'
        terminal.SESSIONS[t.sid] = t
        self.assertTrue(_wait(lambda: 'hello-from-pty' in t.scrollback()))     # something on screen to harvest
        self.assertTrue(_wait(lambda: not t.alive))     # the CLI exited by itself - wrap-up must still work
        typed = []
        t.write = typed.append
        report = '{"determination": "325 was Y/Y", "actions": "flipped it to N/N", "summary": "no mailbox now"}'
        try:
            with mock.patch('taskuary.llm.build_llm', side_effect=[lambda s, u, **kw: report,
                                                                   lambda s, u, **kw: 'Done - 325 no longer gets a mailbox.']):
                out = c.post(f'/api/terminals/{t.sid}/wrap', json={'task_id': tid}).json()
            self.assertEqual(out['wrap'], 'done')
            self.assertIn('flipped it to N/N', out['report'])
            self.assertEqual(typed, [])                                        # the agent was never asked
            self.assertNotIn(t.sid, [x['sid'] for x in terminal.listing()])     # session gone
            pend = [r for r in server.store.list_reviews('pending') if r['TaskId'] == tid]
            self.assertEqual((len(pend), pend[0]['Kind']), (1, 'draft_reply'))
            self.assertIn('no longer gets a mailbox', pend[0]['DraftText'])
            self.assertEqual(server.store.get_task(tid)['Status'], 'waiting')  # waiting on you to send it
            self.assertTrue(any('flipped it to N/N' in cm['Body'] for cm in server.store.list_comments(tid)))
        finally:
            terminal.close(t.sid)

    def test_pausing_keeps_what_it_found_and_hands_it_to_the_next_session(self):
        """Killing a session threw away everything it had worked out. Pausing writes the handover
        note first, leaves the task OPEN (no report, no reply draft), and the next session on that
        task gets the note typed into it so it carries on instead of starting over."""
        tid = c.post('/api/tasks', json={'Title': 'importer is down', 'Kind': 'coding'}).json()['taskId']
        t = terminal.Term(ECHO, os.getcwd(), 'test')
        t.task_id, t.agent = tid, 'coder'
        terminal.SESSIONS[t.sid] = t
        self.assertTrue(_wait(lambda: 'hello-from-pty' in t.scrollback()))
        self.assertTrue(_wait(lambda: not t.alive))     # same for pausing an exited session
        note = '{"found": "a malformed date kills the batch", "did": "nothing yet", "next": "patch the date parse"}'
        try:
            with mock.patch('taskuary.llm.build_llm', return_value=lambda s, u, **kw: note):
                out = c.post(f'/api/terminals/{t.sid}/pause', json={'task_id': tid}).json()
            self.assertEqual(out['pause'], 'done')
            self.assertIn('malformed date', out['note'])
            self.assertNotIn(t.sid, [x['sid'] for x in terminal.listing()])      # session ended
            self.assertEqual(server.store.get_task(tid)['Status'], 'open')       # paused is not finished
            self.assertEqual([r for r in server.store.list_reviews('pending') if r['TaskId'] == tid], [])
            self.assertTrue(any('HANDOVER NOTE' in cm['Body'] for cm in server.store.list_comments(tid)))
            # ...and the note rides into the next session
            seed = terminal.seed_text(server.store, tid)
            self.assertIn('malformed date', seed)
            self.assertIn('do not start over', seed)
        finally:
            terminal.close(t.sid)

    def test_the_prompt_carries_everything_so_the_agent_never_calls_back(self):
        """An agent that goes back to Taskuary for the message spends a minute of tool calls
        re-fetching what it was handed. The prompt says the message IS the context - and carries
        the mail, the repo and CODER.md (which claimed to be sent every run, and never was)."""
        tid = c.post('/api/tasks', json={'Title': 'payroll import month is wrong', 'Kind': 'coding'}).json()['taskId']
        server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:PAY1', 'Channel': 'email',
                                  'FromName': 'Dana Reyes', 'FromEmail': 'dreyes@northwind.example',
                                  'Subject': 'Payroll File Imports', 'SentAt': '2026-08-19 15:03',
                                  'BodyText': 'files with adjustments import in the wrong month'})
        seed = terminal.seed_text(server.store, tid, 'use the payroll date', 'mfaVita/FanApp', 'C:/src/FanApp')
        for s in ['payroll import month is wrong', 'Dana Reyes', 'wrong month', 'use the payroll date',
                  'REPO: mfaVita/FanApp', 'Do NOT call the Taskuary API', 'fix it if it is fixable',
                  'Do NOT create GitHub issues']:
            self.assertIn(s, seed)
        self.assertIn('RULES:', seed)                                   # CODER.md rides along
        self.assertIn('Work ONLY in the repository', seed)
        self.assertNotIn('\\n', seed)                                   # one line - a newline submits

    def test_repo_is_guessed_from_the_soul_map_when_the_task_has_no_tag(self):
        prof = {'cwd_map': {'mfaVita/FanApp': 'C:/src/FanApp', 'mfaVita/Reports': 'C:/src/Reports'}}
        server.store.save_doc('soul', '## Repository map\n'
                              '- **mfaVita/FanApp**: employee portal - PTO, payroll imports, timesheets\n'
                              '- **mfaVita/Reports**: nightly financial reporting pipeline\n', 'test')
        pto = c.post('/api/tasks', json={'Title': 'PTO import maps the wrong month',
                                         'Summary': 'the payroll timesheet import is off'}).json()['taskId']
        self.assertEqual(terminal.guess_repo(server.store, pto, prof)[0], 'mfaVita/FanApp')
        named = c.post('/api/tasks', json={'Title': 'Reports is failing at 2am'}).json()['taskId']
        self.assertEqual(terminal.guess_repo(server.store, named, prof), ('mfaVita/Reports', 'named in the ask'))
        tagged = c.post('/api/tasks', json={'Title': 'anything', 'Tags': 'repo:mfaVita/Reports'}).json()['taskId']
        self.assertEqual(terminal.guess_repo(server.store, tagged, prof), ('mfaVita/Reports', 'tagged on the task'))
        # nothing to match against, or nothing that matches: the agent's own folder, not a wrong repo
        self.assertEqual(terminal.guess_repo(server.store, pto, {}), (None, None))
        blank = c.post('/api/tasks', json={'Title': 'zzz qqq'}).json()['taskId']
        self.assertIsNone(terminal.guess_repo(server.store, blank, prof)[0])

    def test_start_session_seeds_the_same_full_prompt_as_dispatch(self):
        """"Start session" in the Tasks header used to build its OWN thin prompt - title plus
        summary, no message, no rules - which is precisely why an agent started that way went
        back to the API for the mail. One prompt builder, both doors."""
        server.store.upsert_agent('coder', 'coding', 'cli', '{"cmd": "claude"}')
        tid = c.post('/api/tasks', json={'Title': 'payroll month', 'Kind': 'coding'}).json()['taskId']
        server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:PAY2', 'Channel': 'email',
                                  'FromEmail': 'dreyes@northwind.example', 'Subject': 'Payroll File Imports',
                                  'SentAt': '2026-08-19 15:03', 'BodyText': 'imports in the wrong month'})

        class Fake:
            sid, cwd, label, agent, task_id = 'fake-sid', os.getcwd(), 'coder', 'coder', tid
            seeded = None
            def seed(self, text): Fake.seeded = text
            def info(self): return {'sid': self.sid, 'cwd': self.cwd, 'alive': True}
        with mock.patch.object(terminal, 'open_session', return_value=Fake()):
            self.assertEqual(c.post('/api/terminals', json={'agent': 'coder', 'task_id': tid, 'seed': True}).status_code, 200)
        for s in ('imports in the wrong month', 'dreyes@northwind.example', 'Do NOT call the Taskuary API', 'fix it if it is fixable'):
            self.assertIn(s, Fake.seeded)

    def test_the_prompt_is_sent_not_just_typed(self):
        """Killer detail: a long paste and a carriage return in the same breath read as ONE edit
        to a TUI, so the prompt sat there typed but never submitted. Enter goes in on its own."""
        t = terminal.Term([sys.executable, '-c', 'import time; time.sleep(3)'], os.getcwd(), 'test')
        terminal.SESSIONS[t.sid] = t
        wrote = []
        # a pty ECHOES what is typed - the seed verifies that before any Enter goes in, so the
        # fake write feeds the buffer the way a real echo would
        def fake_write(x): wrote.append(x); t._append(x)
        try:
            with mock.patch.object(t, 'write', side_effect=fake_write):
                with mock.patch.object(terminal, 'SEED_QUIET', 0), mock.patch.object(terminal, 'SEED_ENTER', .05):
                    t.n = 1                                  # the TUI has printed: it is 'ready'
                    t.seed('do the thing and then do the other thing')
                    self.assertTrue(_wait(lambda: len(wrote) >= 2))
            self.assertEqual(wrote[0], 'do the thing and then do the other thing')
            self.assertEqual(wrote[1], '\r')                  # then Enter, on its own
        finally:
            terminal.close(t.sid)

    def test_an_unechoed_prompt_is_never_submitted_blind(self):
        """codex boots into "do you trust this directory?" - a dialog that eats typed text and
        treats Enter as its ANSWER. If the text never echoes, no Enter may be pressed: trusting
        a directory is the owner's security decision, not the seeder's."""
        t = terminal.Term([sys.executable, '-c', 'import time; time.sleep(3)'], os.getcwd(), 'test')
        terminal.SESSIONS[t.sid] = t
        wrote = []
        try:
            with mock.patch.object(t, 'write', side_effect=wrote.append):   # NO echo: a dialog ate it
                with mock.patch.object(terminal, 'SEED_QUIET', 0), mock.patch.object(terminal, 'SEED_ENTER', .05), \
                     mock.patch.object(terminal, 'SEED_BUDGET', 1.5):
                    t.n = 1
                    t.seed('do the thing and then do the other thing')
                    time.sleep(2.5)
            self.assertNotIn('\r', wrote)                     # nothing answered the dialog for them
            self.assertNotIn('\n', wrote)
        finally:
            terminal.close(t.sid)

    def test_the_wrap_up_reads_the_WHOLE_session_not_the_last_48k_of_escape_codes(self):
        """TQ-0013: 27 minutes of real work, and the report said "the content is heavily
        corrupted". The tail was taken off the RAW stream - and in a busy TUI the last 48k chars
        are spinner frames and cursor moves, not words. Render first, then take the tail."""
        work = ('Root-caused and fixed (FanApp master b4275ce9). ACH rows in bankFeed carry nothing in '
                'Cust. Ref, so the doc-number rules can never fire for an EFT and only amount+date is '
                'left. CFG settled Shady Grove over two deposits, which is why they show uncleared.\r\n')
        spam = ''.join(f'\r\x1b[2K\x1b[36m✻\x1b[0m Levitating… ({i}s · esc to interrupt · {i * 431} tokens)'
                       for i in range(1, 1200))          # what a TUI paints while it thinks
        t = terminal.Term(ECHO, os.getcwd(), 'test')
        terminal.SESSIONS[t.sid] = t
        try:
            t.buf.clear(); t.n = 0
            t._append(work); t._append(spam)
            self.assertGreater(len(t.scrollback()), 48000)        # the old window would see spam only
            self.assertLess(len(t.scrollback()), terminal.SCROLLBACK)
            got = terminal.harvest(t)
            self.assertIn('Root-caused and fixed', got)
            self.assertIn('Shady Grove', got)
            self.assertNotIn('Levitating', got)                   # and the chrome still goes
            self.assertGreater(terminal.letters(got), 160)
            # a session that printed nothing but chrome hands back the rendered text, not silence:
            # noise an AI can discount, emptiness it cannot
            t.buf.clear(); t.n = 0; t._append(spam)
            self.assertTrue(terminal.harvest(t).strip())
        finally:
            terminal.close(t.sid)

    def test_end_to_end_a_real_tui_gets_the_prompt_submitted_and_the_report_is_real(self):
        """The whole lifecycle against a REAL pty running a TUI that only works on a full line:
        seed it, and the work only happens if Enter actually went in. Then the wrap-up has to
        write the report from what the TUI said - not from its spinner."""
        fake = str(Path(__file__).parent / 'fake_tui.py')
        server.store.upsert_agent('faketui', 'coding', 'cli', json.dumps({'cmd': sys.executable, 'args': [fake]}))
        tid = c.post('/api/tasks', json={'Title': 'payroll adjustments post to the wrong month',
                                         'Kind': 'coding'}).json()['taskId']
        server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:E2E', 'Channel': 'email',
                                  'FromName': 'Dana Reyes', 'FromEmail': 'dreyes@northwind.example',
                                  'Subject': 'Payroll File Imports', 'SentAt': '2026-08-19 15:03',
                                  'BodyText': 'files with adjustments import in the wrong month'})
        ses = c.post('/api/terminals', json={'agent': 'faketui', 'task_id': tid, 'seed': True,
                                             'cwd': os.getcwd()}).json()
        t = terminal.get(ses['sid'])
        try:
            # the TUI echoes the ask only when a whole line arrives, so this passing IS the proof
            # that the prompt was submitted and not just typed into the box
            self.assertTrue(_wait(lambda: 'run_pto_intacct.py' in terminal.plain(t.scrollback()), 40),
                            terminal.plain(t.scrollback())[-400:])
            self.assertIn('Payroll File Imports', terminal.plain(t.scrollback()))   # the mail rode in
            got = terminal.harvest(t)
            self.assertIn('wrong month', got)
            self.assertIn('run_pto_intacct.py', got)
            self.assertNotIn('Levitating', got)                       # spinner frames stay out
            self.assertNotIn('esc to interrupt', got)
            seen = []                       # the wrap calls the AI twice: report, then reply draft
            def fake_llm(system, user, **kw):
                seen.append(user)
                return '{"determination": "adjustment rows took the first line date", "actions": "fixed the batch date", "summary": "posts to the right month now"}'
            with mock.patch('taskuary.llm.build_llm', return_value=fake_llm):
                out = c.post(f'/api/terminals/{t.sid}/wrap', json={'task_id': tid, 'close': True}).json()
            self.assertIn('fixed the batch date', out['report'])
            self.assertIn('run_pto_intacct.py', seen[0])               # the AI read the real transcript
            self.assertNotIn('Levitating', seen[0])
            self.assertNotIn('esc to interrupt', seen[0])
            # ...and not the prompt WE typed in, echoed back by the pty as if the agent said it
            self.assertNotIn('Do NOT call the Taskuary API', seen[0])
        finally:
            terminal.close(ses['sid'])


    def test_agents_open_issues_only_when_the_setting_says_so(self):
        """Off (the default): the seed forbids tracker items and the SOUL.md tool blurb scopes
        writes to the ask. On: both sides grant the licence. One switch, both documents."""
        from taskuary import docsync
        tid = c.post('/api/tasks', json={'Title': 'issue policy probe', 'Kind': 'coding'}).json()['taskId']
        server.store.set_setting('agent_issues_enabled', '0', 'test')
        self.assertIn('Do NOT create GitHub issues', terminal.seed_text(server.store, tid))
        self.assertIn('never issues or tracker items', docsync.role_text(server.store, 'tool'))
        server.store.set_setting('agent_issues_enabled', '1', 'test')
        try:
            seed = terminal.seed_text(server.store, tid)
            self.assertNotIn('Do NOT create GitHub issues', seed)
            self.assertIn('may open GitHub issues', seed)
            self.assertIn('as the work needs', docsync.role_text(server.store, 'tool'))
        finally:
            server.store.set_setting('agent_issues_enabled', '0', 'test')

    def test_agent_argv_drops_the_headless_flags(self):
        # -p / --output-format stream-json make the CLI a one-shot pipe; a TUI needs neither
        with mock.patch('taskuary.agents._resolve_cmd', return_value=['claude']):
            self.assertEqual(terminal.agent_argv({'cmd': 'claude', 'args': ['-p', '--output-format', 'stream-json']}), ['claude'])
            self.assertEqual(terminal.agent_argv({'cmd': 'codex', 'interactive_args': ['tui']}), ['claude', 'tui'])


if __name__ == '__main__':
    unittest.main()


class DurableWrapTests(unittest.TestCase):
    """Wrapping up must not depend on a pty still being around. A CLI that exits on its own is
    reaped after ten minutes, and with it went the only handle the Done/Pause buttons had - so a
    task whose agent had finished could never be closed out at all."""

    def _task(self, title='reaped session task'):
        return c.post('/api/tasks', json={'Title': title, 'Kind': 'coding'}).json()['taskId']

    def test_the_transcript_outlives_the_pty_and_the_task_can_still_be_wrapped(self):
        tid = self._task()
        t = terminal.Term(ECHO, os.getcwd(), 'coder', tid, 'coder', store=server.store)
        terminal.SESSIONS[t.sid] = t
        self.assertTrue(_wait(lambda: not t.alive))                     # it exited by itself
        self.assertTrue(_wait(lambda: server.store.last_transcript(tid) is not None))
        self.assertIn('hello-from-pty', server.store.last_transcript(tid)['Text'])
        # now the session is gone entirely, as the reaper would leave it
        terminal.SESSIONS.pop(t.sid, None)
        self.assertIsNone(terminal.session_for(tid))
        text, agent, sid = terminal.transcript_for(server.store, tid)
        self.assertIn('hello-from-pty', text)
        self.assertEqual((agent, sid), ('coder', t.sid))
        # ...and the buttons still have somewhere to point
        self.assertTrue(c.get(f'/api/tasks/{tid}').json()['transcript'])
        with mock.patch('taskuary.llm.build_llm', return_value=None):   # no AI: files the tail verbatim
            out = c.post(f'/api/tasks/{tid}/wrap', json={'close': True})
        self.assertEqual(out.status_code, 200)
        self.assertIn('hello-from-pty', out.json()['report'])

    def test_pause_works_off_a_dead_session_too(self):
        tid = self._task('paused after exit')
        t = terminal.Term(ECHO, os.getcwd(), 'coder', tid, 'coder', store=server.store)
        terminal.SESSIONS[t.sid] = t
        self.assertTrue(_wait(lambda: server.store.last_transcript(tid) is not None))
        terminal.SESSIONS.pop(t.sid, None)
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            out = c.post(f'/api/tasks/{tid}/pause', json={})
        self.assertEqual(out.status_code, 200)
        self.assertIn('hello-from-pty', out.json()['note'])
        # pausing is not finishing: the task stays open and nothing is drafted
        self.assertEqual(c.get(f'/api/tasks/{tid}').json()['task']['Status'], 'open')

    def test_a_task_that_never_had_a_session_says_so_instead_of_500ing(self):
        tid = self._task('no session ever')
        self.assertIsNone(c.get(f'/api/tasks/{tid}').json()['transcript'])
        self.assertEqual(c.post(f'/api/tasks/{tid}/wrap', json={'close': True}).status_code, 422)
        self.assertEqual(c.post('/api/tasks/999999/wrap', json={'close': True}).status_code, 422)

    def test_a_reply_drafted_from_the_mail_is_held_while_the_agent_works_and_rewritten_after(self):
        """Triage answers a question from the mail alone. Send that same task to a coding agent and
        the draft was still sitting in Review looking ready to send - promising a fix nobody had
        looked at yet. It waits, then comes back written from what the session found."""
        tid = self._task('held reply task')
        mid = server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:HELD1', 'Channel': 'email',
                                        'FromEmail': 'asker@corp.com', 'SourceName': 'me@corp.com',
                                        'BodyText': 'is the import fixed?', 'Status': 'routed'})
        rid = server.store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                                       'DraftText': 'We will look into it.', 'Reason': 'needs a reply'})
        pending = lambda: [r['ReviewId'] for r in c.get('/api/reviews', params={'status': 'pending'}).json()['data']]
        self.assertIn(rid, pending())
        t = terminal.Term(ECHO, os.getcwd(), 'coder', tid, 'coder', store=server.store)
        terminal.SESSIONS[t.sid] = t
        server.store.hold_reviews(tid, 'held while an agent works the task')   # what open_session does
        self.assertNotIn(rid, pending())                                        # out of the queue
        held = [r['ReviewId'] for r in c.get('/api/reviews', params={'status': 'held'}).json()['data']]
        self.assertIn(rid, held)                                                # but visible, not vanished
        self.assertTrue(_wait(lambda: server.store.last_transcript(tid) is not None))
        terminal.SESSIONS.pop(t.sid, None)
        with mock.patch('taskuary.responder.write_draft', return_value='The import is fixed.') as wd:
            with mock.patch('taskuary.llm.build_llm', return_value=None):
                out = c.post(f'/api/tasks/{tid}/wrap', json={'close': True}).json()
        self.assertTrue(out['drafting'])
        self.assertEqual(wd.call_args.args[2], rid)          # the SAME review, not a second one
        self.assertIn(rid, pending())                        # back in the queue, rewritten
        self.assertIn('what it found', server.store.get_review(rid)['Reason'])

    def test_a_held_reply_can_be_released_without_waiting(self):
        tid = self._task('released reply task')
        mid = server.store.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': 'graph:HELD2',
                                        'FromEmail': 'asker@corp.com', 'BodyText': 'any news?', 'Status': 'routed'})
        rid = server.store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                                       'DraftText': 'Looking now.', 'Reason': 'needs a reply'})
        server.store.hold_reviews(tid)
        self.assertEqual(c.post(f'/api/reviews/{rid}/release').status_code, 200)
        self.assertEqual(server.store.get_review(rid)['Status'], 'pending')
        self.assertEqual(c.post(f'/api/reviews/{rid}/release').status_code, 422)   # not held any more


class RepoRoutingTests(unittest.TestCase):
    """A wrong checkout means an agent editing the wrong tree in good faith. The real failure:
    SOUL.md knew about the reimbursement repo, the agent had a path for only ONE repo, and
    "the only repo this agent has a path for" won without the ask ever being read."""

    SOUL = ('## Repository map\n'
            '- **mfaVita/FanApp**: Python enterprise integration services, payroll imports, timesheets\n'
            '- **mfaVita/TopE**: a travel and expense reimbursement platform with AI receipt validation\n')

    def setUp(self):
        server.store.save_doc('soul', self.SOUL, 'test')
        server.store.upsert_agent('coder', 'coding', 'cli',
                                  json.dumps({'cmd': 'claude', 'cwd': os.getcwd(),
                                              'cwd_map': {'mfaVita/FanApp': os.getcwd()}}))

    def _task(self, title, summary=''):
        return c.post('/api/tasks', json={'Title': title, 'Summary': summary, 'Kind': 'coding'}).json()['taskId']

    def test_the_ask_beats_the_only_repo_that_happens_to_be_configured(self):
        prof = json.loads(server.store.get_agent('coder')['Config'])
        tid = self._task('Reimbursement app', 'approving reimbursements shows an error on each transaction')
        repo, why = terminal.guess_repo(server.store, tid, prof)
        self.assertEqual(repo, 'mfaVita/TopE')           # NOT the one with a path
        self.assertTrue(why)
        ranked = terminal.rank_repos(server.store, tid, prof)
        self.assertEqual(ranked[0][0], 'mfaVita/TopE')
        self.assertFalse(ranked[0][2])                   # ...and we know we have no path for it
        # a payroll task still goes to the integrations repo
        pay = self._task('payroll import posts to the wrong month', 'the timesheets import is off')
        self.assertEqual(terminal.guess_repo(server.store, pay, prof)[0], 'mfaVita/FanApp')

    def test_a_repo_with_no_path_refuses_instead_of_opening_the_wrong_folder(self):
        with self.assertRaises(ValueError) as e:
            terminal.open_session(server.store, 'coder', self._task('x'), 'mfaVita/TopE')
        self.assertIn('no local path for mfaVita/TopE', str(e.exception))
        self.assertIn('Pick the repository', str(e.exception))    # the fix is ON the task now
        self.assertIn('wrong tree', str(e.exception))

    def test_the_api_lists_every_repo_with_whether_it_can_be_opened(self):
        tid = self._task('Reimbursement app', 'approving reimbursements errors out')
        out = c.get(f'/api/tasks/{tid}/repos').json()
        self.assertEqual(out['picked'], 'mfaVita/TopE')
        by = {r['repo']: r for r in out['data']}
        self.assertFalse(by['mfaVita/TopE']['has_path'])
        self.assertTrue(by['mfaVita/FanApp']['has_path'])
        self.assertIn('reimbursement', by['mfaVita/TopE']['what'])

    def test_pinning_a_repo_overrides_the_guess_and_takes_the_path_with_it(self):
        tid = self._task('Reimbursement app', 'approving reimbursements errors out')
        here = os.getcwd()
        r = c.put(f'/api/tasks/{tid}/repo', json={'repo': 'mfaVita/TopE', 'path': here, 'agent': 'coder'})
        self.assertEqual(r.status_code, 200)
        prof = json.loads(server.store.get_agent('coder')['Config'])
        self.assertEqual(prof['cwd_map']['mfaVita/TopE'], here)          # the path stuck
        self.assertEqual(terminal.guess_repo(server.store, tid, prof), ('mfaVita/TopE', 'tagged on the task'))
        self.assertIn('repo:mfaVita/TopE', server.store.get_task(tid)['Tags'])
        # ...and the prompt now says so, which is the whole point
        self.assertIn('REPO: mfaVita/TopE', terminal.seed_text(server.store, tid, None, 'mfaVita/TopE', here))
        # a bad path is refused rather than silently stored
        self.assertEqual(c.put(f'/api/tasks/{tid}/repo',
                               json={'repo': 'mfaVita/TopE', 'path': os.path.join(here, 'nope')}).status_code, 422)
        # unpinning hands the choice back to the guess
        c.put(f'/api/tasks/{tid}/repo', json={'repo': None})
        self.assertNotIn('repo:', str(server.store.get_task(tid)['Tags'] or ''))


class FindCheckoutTests(unittest.TestCase):
    """"Why can't it find the local repo? It's there?" - it is, in a folder that is not named
    after the repo, which is why matching on the GIT REMOTE is the whole point."""

    def _tree(self):
        import tempfile
        root = Path(tempfile.mkdtemp())
        # the checkout, under a name that does not match the repo
        co = root / 'work' / 'oddname'
        (co / '.git').mkdir(parents=True)
        (co / '.git' / 'config').write_text('[remote "origin"]\n\turl = https://github.com/acme/widget.git\n')
        # a decoy with the right folder name but the wrong remote
        decoy = root / 'work' / 'widget'
        (decoy / '.git').mkdir(parents=True)
        (decoy / '.git' / 'config').write_text('[remote "origin"]\n\turl = https://github.com/other/widget-fork.git\n')
        (root / 'work' / 'node_modules' / 'widget').mkdir(parents=True)   # never descended into
        return root, co

    def test_finds_by_remote_not_by_folder_name(self):
        root, co = self._tree()
        hint = {'cwd': str(root / 'work' / 'somewhere-known')}
        (root / 'work' / 'somewhere-known').mkdir()
        found = terminal.find_checkout('acme/widget', hint)
        self.assertEqual(found, str(co))                       # oddname, because its REMOTE matches
        self.assertIsNone(terminal.find_checkout('acme/nothere', hint, seconds=1.0))

    def test_open_session_adopts_the_found_path_and_remembers_it(self):
        root, co = self._tree()
        server.store.upsert_agent('finder', 'coding', 'cli',
                                  json.dumps({'cmd': 'claude', 'cwd': str(root / 'work'),
                                              'cwd_map': {'acme/other': str(root / 'work')}}))
        with mock.patch.object(terminal, 'Term') as T:          # never spawn a real pty here
            T.return_value = mock.Mock(sid='x', cwd=str(co), info=lambda: {})
            terminal.open_session(server.store, 'finder', None, 'acme/widget')
            self.assertEqual(T.call_args.args[1], str(co))      # the session opens IN the checkout
        prof = json.loads(server.store.get_agent('finder')['Config'])
        self.assertEqual(prof['cwd_map']['acme/widget'], str(co))   # ...and it is remembered
