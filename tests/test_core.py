"""Core engine tests - everything runs on the in-memory SQLite store, no network."""
import unittest
from taskuary.store import MemoryStore, task_ref
from taskuary.ingest import ingest_message
from taskuary.routing import route
from taskuary.triage import heuristic_intent
from taskuary.agents import parse_cli_json
from taskuary.coder import parse_coder_result, RESULT_MARKER
from taskuary.reports import is_due, run_report_source, REGISTRY


TASK_LLM = lambda sys, usr: '{"intent": "task", "why": "t"}'
REPLY_LLM = lambda sys, usr: '{"intent": "reply_only", "why": "q"}'


class CoreTests(unittest.TestCase):
    def msg(self, **kw):
        base = {'external_id': kw.get('external_id', 'x1'), 'channel': 'api', 'subject': 's',
                'body': 'please add the new user to the system', 'from_email': 'a@b.com',
                'conversation_id': None, 'sent_at': '2026-08-17 09:00', 'source_link': None, 'from_name': 'A'}
        return {**base, **kw}

    def test_ingest_creates_task_and_feed(self):
        s = MemoryStore()
        out = ingest_message(s, self.msg(), llm=TASK_LLM)
        self.assertEqual(out['status'], 'created')
        self.assertEqual(task_ref(out['task_id']), 'TQ-0001')
        self.assertEqual(len(s.feed()), 1)
        self.assertEqual(ingest_message(s, self.msg(), llm=TASK_LLM)['status'], 'duplicate')

    def test_no_ai_connector_files_instead_of_task_spam(self):
        # without an active AI connector, inbound is FILED (visible, no task) - the AI
        # decides what becomes a task, not the default-to-task heuristic
        s = MemoryStore()
        out = ingest_message(s, self.msg(external_id='noai1'))
        self.assertEqual((out['status'], out['task_id']), ('filed', None))
        self.assertIn('awaiting AI triage', s.feed()[0]['RouteReason'])

    def test_thread_attach(self):
        s = MemoryStore()
        a = ingest_message(s, self.msg(external_id='m1', conversation_id='c1'), llm=TASK_LLM)
        b = ingest_message(s, self.msg(external_id='m2', conversation_id='c1', body='and one more thing'), llm=TASK_LLM)
        self.assertEqual((b['status'], b['task_id']), ('attached', a['task_id']))

    def test_fyi_files_without_task(self):
        s = MemoryStore()
        out = ingest_message(s, self.msg(external_id='f1', subject='report', body='this is an automated summary'))
        self.assertEqual((out['status'], out['task_id']), ('filed', None))

    def test_reply_only_kind(self):
        s = MemoryStore()
        out = ingest_message(s, self.msg(external_id='q1', subject='Tuesday?', body='are you available tuesday?'), llm=REPLY_LLM)
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'reply')

    def test_reply_only_enters_review_queue(self):
        s = MemoryStore()
        out = ingest_message(s, self.msg(external_id='rq1', subject='Tuesday?', body='are you available tuesday?'), llm=REPLY_LLM)
        pending = s.list_reviews('pending')
        self.assertEqual(len(pending), 1)
        self.assertEqual((pending[0]['TaskId'], pending[0]['Kind']), (out['task_id'], 'draft'))

    def test_coder_auto_dispatch_when_enabled(self):
        from unittest import mock
        import taskuary.ingest as ing

        class InlineThread:
            def __init__(self, target=None, args=(), daemon=None): self.t, self.a = target, args
            def start(self): self.t(*self.a)

        s = MemoryStore()
        s.set_setting('coder_auto_enabled', '1', 't')
        with mock.patch.object(ing, 'threading') as th,              mock.patch('taskuary.coder.run_coding_task') as run,              mock.patch('taskuary.coder.github_cfg', return_value={}):
            th.Thread = InlineThread
            out = ingest_message(s, self.msg(external_id='ac1'), llm=TASK_LLM)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[1], out['task_id'])
        self.assertTrue(any('auto-dispatched' in c['Body'] for c in s.list_comments(out['task_id'])))

    def test_no_auto_dispatch_when_disabled(self):
        from unittest import mock
        s = MemoryStore()
        with mock.patch('taskuary.coder.run_coding_task') as run:
            ingest_message(s, self.msg(external_id='ac2'), llm=TASK_LLM)
        run.assert_not_called()

    def test_skip_policy_hides_flood_senders(self):
        s = MemoryStore()
        s.save_policy({'Name': 'skip:api', 'Kind': 'sender', 'Pattern': 'noreply@vendor.example',
                       'Action': 'skip', 'Reason': 'flood', 'SortOrder': 10, 'Active': 1}, 't')
        out = ingest_message(s, self.msg(external_id='sk1', from_email='NoReply@vendor.example'), llm=TASK_LLM)
        self.assertEqual((out['status'], out['task_id']), ('skipped', None))
        self.assertEqual(s.feed(), [])   # never on the timeline, unlike 'ignored'
        self.assertEqual(ingest_message(s, self.msg(external_id='sk1'))['status'], 'duplicate')

    def test_run_cli_streams_stream_json(self):
        from unittest import mock
        from taskuary.agents import run_cli
        import sys
        script = ("import sys,json;sys.stdin.read();"
                  "print(json.dumps({'type':'assistant','message':{'content':"
                  "[{'type':'tool_use','name':'Bash','input':{'command':'ls -la'}}]}}));"
                  "print(json.dumps({'type':'result','result':'all done','session_id':'s1'}))")
        ev = []
        with mock.patch('taskuary.agents._resolve_cmd', return_value=[sys.executable]):
            out, sid, _ = run_cli({'cmd': 'python', 'args': ['-c', script], 'timeout': 60},
                                  'hi', lambda k, n, d: ev.append((k, d)))
        self.assertEqual((out, sid), ('all done', 's1'))
        self.assertTrue(any(k == 'live' and 'Bash' in d for k, d in ev))

    def test_roles_gate_what_polls_and_github_can_trigger(self):
        from unittest import mock
        from taskuary import channels
        from taskuary.store import roles_of
        s = MemoryStore()
        gh = next(c for c in s.list_connectors() if c['Type'] == 'github')
        self.assertEqual(roles_of(gh), {'tool'})                    # github is a tool by default...
        s.save_connector({'ConnectorId': gh['ConnectorId'], 'Active': 1, 'Secret': 'ghp_x'}, 'o')
        s.save_source({'Channel': 'github', 'Address': 'o/repo', 'ConnectorId': gh['ConnectorId'], 'Active': 1}, 'o')
        issues = [{'number': 7, 'title': 'Export dies on empty ledger', 'body': 'stack trace here',
                   'user': {'login': 'jsmith'}, 'updated_at': '2026-08-18T09:00:00Z', 'html_url': 'https://gh/7'},
                  {'number': 8, 'title': '[TQ-0004] coder task', 'body': 'opened by taskuary itself',
                   'user': {'login': 'bot'}, 'updated_at': '2026-08-18T09:01:00Z', 'html_url': 'https://gh/8'}]
        with mock.patch('taskuary.github.list_issues', return_value=issues) as li:
            self.assertEqual(channels.poll_channels(s), 0)          # ...so nothing polls it
            li.assert_not_called()
            s.save_connector({'ConnectorId': gh['ConnectorId'], 'Roles': 'trigger,tool'}, 'o')
            self.assertEqual(channels.poll_channels(s), 1)          # the owner made it a trigger
        feed = s.feed()
        self.assertEqual([m['Channel'] for m in feed], ['github'])
        self.assertIn('o/repo#7', feed[0]['Subject'])               # our own [TQ-] issues never come back

    def test_one_report_can_pull_from_several_sources(self):
        from taskuary.reports import REGISTRY, render_report
        s = MemoryStore()
        REGISTRY['_a'] = lambda cfg: (f"{cfg['q']} rows", f"body for {cfg['q']}")
        REGISTRY['_boom'] = lambda cfg: (_ for _ in ()).throw(RuntimeError('server unreachable'))
        try:
            seen = {}
            head, body = render_report(s, {
                'title': 'Morning check', 'ai_prompt': 'summarize',
                # the SAME connector twice with different queries, plus one that dies
                'sources': [{'type': '_a', 'label': 'cash', 'q': '3'},
                            {'type': '_a', 'label': 'ledger', 'q': '7'},
                            {'type': '_boom', 'label': 'the box'}],
            }, llm=lambda sys_, usr_, **kw: seen.update(usr=usr_) or 'all good')
            self.assertEqual(head, 'cash: 3 rows · ledger: 7 rows · the box: FAILED')
            for want in ('=== cash (3 rows) ===', 'body for 7', 'server unreachable'):
                self.assertIn(want, seen['usr'])            # every source reaches the one AI pass
            self.assertIn('all good', body)
            # a config without `sources` is still the plain single-source report
            self.assertEqual(render_report(s, {'type': '_a', 'q': '1'})[0], '1 rows')
        finally:
            REGISTRY.pop('_a'); REGISTRY.pop('_boom')

    def test_report_rows_admit_when_they_were_capped(self):
        from taskuary.reports import REGISTRY, render_report, rows_out
        s = MemoryStore()
        self.assertEqual(rows_out([{'a': 1}, {'a': 2}], 5)[0], '2 rows')
        head, body = rows_out([{'a': i} for i in range(6)], 5)      # one row past the limit = there IS more
        self.assertIn('capped at 5', head)
        self.assertEqual(len(body.splitlines()), 5)
        # the AI is told the slice may be partial, so it can't call 20 of 500 rows "all"
        seen = {}
        REGISTRY['_cap'] = lambda cfg: ('20 rows (capped at 20 — the query returned more)', 'x' * 50)
        try:
            render_report(s, {'type': '_cap', 'ai_prompt': 'summarize'},
                          llm=lambda sys_, usr_, **kw: seen.update(sys=sys_, usr=usr_) or 'ok')
        finally:
            REGISTRY.pop('_cap')
        self.assertIn('never describe a capped or truncated slice as complete', seen['sys'])
        self.assertIn('capped at 20', seen['usr'])

    def test_html_mail_keeps_its_paragraphs(self):
        from taskuary.channels import _clean
        txt = _clean('<p>The form was rejected.</p><p>Thanks,<br>Roseanna</p>'
                     '<div>From: devteam-logs@x.net<br>Sent: Tuesday<br>To: Roseanna</div>')
        # block ends are newlines now: the reply and the quoted header are separable
        self.assertEqual(txt.splitlines()[0], 'The form was rejected.')
        self.assertIn('\nFrom: devteam-logs@x.net\nSent: Tuesday', txt)
        self.assertEqual(_clean('<p>a&nbsp;b</p><style>x{}</style>'), 'a b')

    def test_feed_role_shows_on_the_timeline_without_making_work(self):
        from unittest import mock
        from taskuary import channels
        s = MemoryStore()
        gh = next(c for c in s.list_connectors() if c['Type'] == 'github')
        s.save_connector({'ConnectorId': gh['ConnectorId'], 'Active': 1, 'Secret': 'ghp_x', 'Roles': 'feed,tool'}, 'o')
        s.save_source({'Channel': 'github', 'Address': 'o/repo', 'ConnectorId': gh['ConnectorId'], 'Active': 1}, 'o')
        issues = [{'number': 9, 'title': 'Docs typo', 'body': 'small fix', 'user': {'login': 'jsmith'},
                   'updated_at': '2026-08-18T09:00:00Z', 'html_url': 'https://gh/9'}]
        boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError('a feed must never call the AI'))
        with mock.patch('taskuary.github.list_issues', return_value=issues), \
             mock.patch('taskuary.llm.build_llm', return_value=boom):
            self.assertEqual(channels.poll_channels(s), 1)
        row = s.feed()[0]
        self.assertEqual((row['Channel'], row['MsgStatus'], row['TaskId']), ('github', 'feed', None))
        self.assertEqual(s.list_tasks(), [])                     # shown, never assigned
        self.assertIn('not a task trigger', row['RouteReason'])

    def test_empty_ai_summary_says_so_instead_of_filing_a_bare_wall(self):
        from taskuary.reports import REGISTRY, render_report
        s = MemoryStore()
        REGISTRY['_e'] = lambda cfg: ('2 rows', 'a\nb')
        try:
            # a reasoning model that spends its budget thinking returns '' - the report used
            # to file starting with '--- raw data ---', which reads like the prompt never ran
            _, body = render_report(s, {'type': '_e', 'ai_prompt': 'summarize'}, llm=lambda *a, **k: '   ')
            self.assertTrue(body.startswith('(the model returned an empty summary'))
            self.assertIn('--- raw data ---', body)
            # and the summary gets a real token budget, not triage's
            seen = {}
            render_report(s, {'type': '_e', 'ai_prompt': 'summarize'},
                          llm=lambda sys_, usr_, max_tokens=None: seen.update(mt=max_tokens) or 'fine')
            self.assertGreaterEqual(seen['mt'], 1000)
        finally:
            REGISTRY.pop('_e')

    def test_triage_brain_is_configurable(self):
        from unittest import mock
        from taskuary import llm
        s = MemoryStore()
        oa = next(c for c in s.list_connectors() if c['Type'] == 'openai')
        s.save_connector({'ConnectorId': oa['ConnectorId'], 'Active': 1, 'Secret': 'sk-x'}, 'o')
        self.assertTrue(callable(llm.build_llm(s)))                 # auto: the cloud key
        s.upsert_agent('coder', 'coding', 'cli', '{"cmd": "claude", "cwd": "C:/repo", "timeout": 9000}')
        s.set_setting('triage_ai', 'cli:coder', 'o')
        with mock.patch('taskuary.agents.run_cli', return_value=('{"intent": "task", "why": "x"}', None, None)) as rc:
            self.assertEqual(llm.build_llm(s)('sys', 'usr'), '{"intent": "task", "why": "x"}')
        prof = rc.call_args[0][0]
        self.assertNotIn('cwd', prof)                               # triage is not about any checkout
        self.assertEqual(prof['timeout'], 300)                      # and never waits a coding-run timeout
        s.set_setting('triage_ai', 'cli:ghost', 'o')
        self.assertIsNone(llm.build_llm(s))                         # missing agent files instead of guessing

    def test_skip_policy_hides_the_senders_history_and_gives_it_back(self):
        from taskuary.ingest import ingest_message
        from taskuary.policy import apply_retroactively
        s = MemoryStore()
        for i in range(3):
            ingest_message(s, {'external_id': f'old{i}', 'channel': 'email', 'subject': 'Provisioning notice',
                               'body': 'automated, no action required', 'from_email': 'flood@vendor.com',
                               'sent_at': '2026-08-17 10:00'})
        ingest_message(s, {'external_id': 'keep', 'channel': 'email', 'subject': 'real mail', 'body': 'hi',
                           'from_email': 'human@client.com', 'sent_at': '2026-08-17 10:00'})
        self.assertEqual(len(s.feed()), 4)
        pol = {'Name': 'skip:flood@vendor.com', 'Kind': 'sender', 'Pattern': 'flood@vendor.com',
               'Action': 'skip', 'Reason': 'flood', 'SortOrder': 10, 'Active': 1}
        s.save_policy(pol, 'owner')
        self.assertEqual(apply_retroactively(s, pol), 3)          # the back catalogue goes too
        self.assertEqual([m['FromEmail'] for m in s.feed()], ['human@client.com'])
        # switching the rule off puts the history back on the timeline
        self.assertEqual(apply_retroactively(s, {**pol, 'Active': 0}), 3)
        self.assertEqual(len(s.feed()), 4)
        # only 'skip' rewrites history - an ignore rule leaves it alone
        self.assertEqual(apply_retroactively(s, {**pol, 'Action': 'ignore'}), 0)

    def test_model_and_prompt_reach_the_cli(self):
        from unittest import mock
        from taskuary import coder
        s = MemoryStore()
        s.upsert_agent('coder', 'coding', 'cli', '{"cmd": "claude", "args": ["-p"], "cwd_map": {"o/r": "C:/src"}}')
        tid = s.create_task({'Title': 'fix the export', 'Kind': 'coding'}, 'owner')
        with mock.patch('taskuary.agents.run_cli', return_value=('done', None, None)) as rc:
            coder.run_coding_task(s, tid, 'owner', repo='o/r', github_cfg={},
                                  model='opus', instruction='Only touch the exporter.')
        prof, prompt = rc.call_args[0][0], rc.call_args[0][1]
        self.assertEqual((prof['model'], prof['cwd']), ('opus', 'C:/src'))   # per-run model, repo's checkout
        self.assertIn('Only touch the exporter.', prompt)                    # the owner's prompt leads
        self.assertIn('RESULT JSON', prompt)                                 # report contract still rides along

    def test_run_cli_appends_the_model_flag(self):
        from unittest import mock
        import sys
        from taskuary.agents import run_cli
        script = "import sys;sys.stdin.read();print('ok')"
        with mock.patch('taskuary.agents._resolve_cmd', return_value=[sys.executable]):
            seen = []
            with mock.patch('taskuary.agents.subprocess.Popen', side_effect=RuntimeError('stop')) as pop:
                try:
                    run_cli({'cmd': 'claude', 'args': ['-c', script], 'model': 'sonnet'}, 'hi', lambda *a: None)
                except RuntimeError:
                    pass
            self.assertEqual(pop.call_args[0][0][-2:], ['--model', 'sonnet'])
            with mock.patch('taskuary.agents.subprocess.Popen', side_effect=RuntimeError('stop')) as pop2:
                try:
                    run_cli({'cmd': 'codex', 'args': ['exec'], 'model': 'gpt-5-codex', 'model_arg': '-m'}, 'hi', lambda *a: None)
                except RuntimeError:
                    pass
            self.assertEqual(pop2.call_args[0][0][-2:], ['-m', 'gpt-5-codex'])   # flag name is per-CLI

    def test_terminal_env_never_inherits_a_session(self):
        from taskuary.terminal import clean_env
        import os
        os.environ['CLAUDE_CODE_CHILD_SESSION'] = 'x'
        os.environ['CLAUDECODE'] = '1'
        try:
            env = clean_env()
            self.assertNotIn('CLAUDE_CODE_CHILD_SESSION', env)   # a terminal starts FRESH,
            self.assertNotIn('CLAUDECODE', env)                  # never resuming its parent
            self.assertIn('PATH', {k.upper(): v for k, v in env.items()})
        finally:
            os.environ.pop('CLAUDE_CODE_CHILD_SESSION', None); os.environ.pop('CLAUDECODE', None)

    def test_console_lines_show_output_not_session_spam(self):
        from taskuary.agents import _live_line
        self.assertEqual(_live_line({'type': 'system', 'subtype': 'init', 'model': 'opus'}), 'session started · model opus')
        self.assertIsNone(_live_line({'type': 'system', 'subtype': 'hook_started'}))   # was 'session started · model ?' x20
        self.assertIn('2 files changed', _live_line({'type': 'user', 'message': {'content': [
            {'type': 'tool_result', 'content': [{'type': 'text', 'text': '2 files changed\n+18 -4'}]}]}}))
        self.assertTrue(_live_line({'type': 'user', 'message': {'content': [
            {'type': 'tool_result', 'is_error': True, 'content': 'no such file'}]}}).startswith('✗'))

    def test_winrm_report_inherits_connector_host(self):
        from taskuary.reports import resolve_cfg
        self.assertIn('winrm', REGISTRY)
        s = MemoryStore()
        c = s.get_connector_by_type('winrm')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'ConfigJson': '{"host": "AZWEB01"}'}, 't')
        cfg = resolve_cfg(s, {'type': 'winrm', 'script': 'hostname'})
        self.assertEqual((cfg['host'], cfg['script']), ('AZWEB01', 'hostname'))

    def test_reset_connector_wipes_connection(self):
        s = MemoryStore()
        c = s.get_connector_by_type('slack')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Secret': 'xoxb-1', 'ConfigJson': '{"a":1}', 'Active': 1}, 't')
        s.save_source({'Channel': 'slack', 'Address': 'C1', 'ConnectorId': c['ConnectorId'], 'Active': 1}, 't')
        s.reset_connector(c['ConnectorId'])
        c2 = s.get_connector(c['ConnectorId'], with_secret=True)
        self.assertFalse(c2['Secret'] or c2['Active'] or c2['ConfigJson'])
        self.assertFalse(any(x['Active'] for x in s.list_sources(active_only=False)
                             if x['ConnectorId'] == c['ConnectorId']))

    def test_triage_heuristics(self):
        self.assertEqual(heuristic_intent({'subject': '', 'body': 'are you available tuesday?'})['intent'], 'reply_only')
        self.assertEqual(heuristic_intent({'subject': 'fyi', 'body': 'this is an automated notice'})['intent'], 'fyi')

    def test_resolve_cmd_wraps_npm_shims(self):
        from unittest import mock
        from taskuary.agents import _resolve_cmd
        shim = 'C:/Users/u/AppData/Roaming/npm/claude.CMD'
        with mock.patch('shutil.which', return_value=shim), mock.patch('taskuary.agents.os') as fake_os:
            fake_os.name = 'nt'
            self.assertEqual(_resolve_cmd('claude'), ['cmd', '/c', shim])
        with mock.patch('shutil.which', return_value='/usr/local/bin/claude'):
            self.assertEqual(len(_resolve_cmd('claude')), 1)
        with mock.patch('shutil.which', return_value=None):
            with self.assertRaises(FileNotFoundError): _resolve_cmd('claude')

    def test_failed_coder_run_escalates_not_empty_report(self):
        from unittest import mock
        from taskuary.coder import run_coding_task
        s = MemoryStore()
        tid = s.create_task({'Title': 'fix it', 'Kind': 'coding'}, 'o')
        s.upsert_agent('coder', 'coding', 'cli', '{}')
        rid = s.start_run(tid, 'coder', 'i', 'o')
        s.update_run(rid, {'Status': 'error', 'LastError': 'claude not found'}, finished=True)
        with mock.patch('taskuary.agents.dispatch', return_value={'run_id': rid, 'status': 'error', 'result': None}):
            out = run_coding_task(s, tid, 'o', None, {})
        self.assertIn('error', out)
        bodies = [c['Body'] for c in s.list_comments(tid)]
        self.assertTrue(any('Coder run FAILED' in b for b in bodies))
        self.assertFalse(any(b.startswith('CODER REPORT') for b in bodies))
        pend = s.list_reviews('pending')
        self.assertEqual((len(pend), pend[0]['Kind']), (1, 'escalation'))
        self.assertIn('run failed: claude not found', pend[0]['Reason'])
        # a second failed run UPDATES the escalation instead of stacking a new one
        with mock.patch('taskuary.agents.dispatch', return_value={'run_id': rid, 'status': 'error', 'result': None}):
            run_coding_task(s, tid, 'o', None, {})
        self.assertEqual(len(s.list_reviews('pending')), 1)

    def test_cli_json_parse(self):
        self.assertEqual(parse_cli_json('{"result": "OK", "session_id": "abc"}'), ('OK', 'abc'))
        self.assertEqual(parse_cli_json('plain'), ('plain', None))

    def test_coder_report_contract(self):
        out = 'work\n' + RESULT_MARKER + '\n{"summary": "s", "close": true, "email_reply": "r"}'
        rep = parse_coder_result(out)
        self.assertTrue(rep['close']); self.assertEqual(rep['email_reply'], 'r')
        self.assertFalse(parse_coder_result('no marker')['close'])

    def test_closing_a_task_resolves_its_pending_reviews(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 't'}, 'o')
        s.add_review({'TaskId': tid, 'Kind': 'escalation', 'Status': 'pending', 'Reason': 'r'})
        s.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'd'})
        s.update_task(tid, {'Status': 'done'}, 'owner')
        self.assertEqual(s.list_reviews('pending'), [])   # done IS the decision

    def test_orphaned_reviews_never_queue(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 't'}, 'u')
        s.add_review({'TaskId': tid, 'Kind': 'escalation', 'Status': 'pending', 'Reason': 'r'})
        s.delete_task(tid)
        s.add_review({'TaskId': tid, 'Kind': 'escalation', 'Status': 'pending', 'Reason': 'late'})
        self.assertEqual(s.list_reviews('pending'), [])

    def test_startup_heals_stacked_pending_reviews(self):
        import tempfile, os
        from taskuary.store import SQLiteStore
        path = os.path.join(tempfile.mkdtemp(), 'heal.db')
        s = SQLiteStore(path)
        tid = s.create_task({'Title': 't'}, 'o')
        for i in range(3):
            s.add_review({'TaskId': tid, 'Kind': 'escalation', 'Status': 'pending', 'Reason': f'r{i}'})
        s.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'd'})
        s2 = SQLiteStore(path)   # reopen = restart
        pend = s2.list_reviews('pending')
        self.assertEqual(len(pend), 2)   # newest escalation + the draft survive
        self.assertEqual({p['Kind'] for p in pend}, {'escalation', 'draft'})
        self.assertEqual(next(p['Reason'] for p in pend if p['Kind'] == 'escalation'), 'r2')

    def test_audit_chain_verifies(self):
        s = MemoryStore()
        s.audit('task', 1, 'create', 'u'); s.audit('task', 1, 'edit', 'u')
        self.assertTrue(s.verify_audit_chain()['ok'])

    def test_report_schedule_and_run(self):
        from datetime import datetime, timedelta
        now = datetime.now()
        self.assertTrue(is_due({'every_minutes': 30}, (now - timedelta(minutes=45)).isoformat(sep=' ')))
        self.assertFalse(is_due({'every_minutes': 30}, (now - timedelta(minutes=5)).isoformat(sep=' ')))
        s = MemoryStore()
        REGISTRY['_t'] = lambda cfg: ('3 rows', 'a\nb\nc')
        try:
            out = run_report_source(s, {'SourceId': 1, 'Address': 'Census', 'ConfigJson': '{"type": "_t"}'})
            m = s.get_message(out['message_id'])
            self.assertEqual((m['Channel'], m['Status'], m['TaskId']), ('report', 'feed', None))
        finally:
            REGISTRY.pop('_t')


if __name__ == '__main__':
    unittest.main()
