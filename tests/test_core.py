"""Core engine tests - everything runs on the in-memory SQLite store, no network."""
import json, tempfile, time, unittest
from pathlib import Path
from taskuary import store as store_mod
from taskuary.store import MemoryStore, task_ref
from taskuary.testing import inbound
from taskuary import artifacts, reshape
from taskuary.ingest import ingest_message
from taskuary.routing import route
from taskuary.triage import heuristic_intent
from taskuary.agents import parse_cli_json
from taskuary.reports import is_due, run_report_source, REGISTRY


TASK_LLM = lambda sys, usr: '{"intent": "task", "why": "t"}'
REPLY_LLM = lambda sys, usr: '{"intent": "reply_only", "why": "q"}'


class CoreTests(unittest.TestCase):
    def msg(self, **kw):
        kw.setdefault('external_id', 'x1')
        return inbound(**kw)

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
        """Auto-dispatch is for CODING tasks: _auto_code opens a CLI session in a repository,
        so it only makes sense where there is a repository to work in. The body here carries a
        real code signal; see test_non_code_work_waits_for_you for the other half."""
        from unittest import mock
        import taskuary.ingest as ing

        class InlineThread:
            def __init__(self, target=None, args=(), daemon=None): self.t, self.a = target, args
            def start(self): self.t(*self.a)

        s = MemoryStore()
        s.set_setting('coder_auto_enabled', '1', 't')
        # auto-dispatch starts a live session, like every other way work starts here
        with mock.patch.object(ing, 'threading') as th,              mock.patch('taskuary.terminal.start_on_task') as start:
            th.Thread = InlineThread
            out = ingest_message(s, self.msg(external_id='ac1', body='the importer throws an exception, see jobs/import.py'), llm=TASK_LLM)
        start.assert_called_once()
        self.assertEqual(start.call_args.args[1], out['task_id'])
        self.assertTrue(any('auto-started a live coder session' in c['Body'] for c in s.list_comments(out['task_id'])))

    def test_work_the_brain_calls_general_goes_on_your_list(self):
        """`kind` routes the task and triage alone decides it (owner, 2026-08-30): general means
        it looked and saw nothing a keyboard does, so the task lands on the Board and waits for
        a click rather than buying a session that can only say "nothing to do here"."""
        from unittest import mock
        s = MemoryStore()
        s.set_setting('coder_auto_enabled', '1', 't')
        general = lambda *a, **k: '{"intent": "task", "kind": "general", "why": "nobody can type this"}'
        with mock.patch('taskuary.ingest._spawn') as spawn:
            out = ingest_message(s, self.msg(external_id='ac3'), llm=general)
        spawn.assert_not_called()
        t = s.get_task(out['task_id'])
        self.assertEqual((t['Kind'], t['Status']), ('general', 'open'))     # a real task, just yours

    def test_a_task_the_brain_did_not_call_general_goes_to_the_coder(self):
        """The owner's call (2026-08-27): err toward the coding agent. A task the brain did not
        label general - even with no code word in the body - is dispatched; an agent on a
        non-coding task says "nothing to do here" and stops, a job left on a list does not."""
        from unittest import mock
        s = MemoryStore()
        s.set_setting('coder_auto_enabled', '1', 't')
        with mock.patch('taskuary.ingest._spawn') as spawn:
            out = ingest_message(s, self.msg(external_id='ac4'), llm=TASK_LLM)
        self.assertTrue(any(getattr(c[0][0], '__name__', '') == '_auto_code' for c in spawn.call_args_list))
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'coding')
        self.assertIn('sent to the coding agent', s._rows('SELECT * FROM route ORDER BY RouteId DESC')[0]['Reason'])

    def test_a_first_time_email_sender_never_starts_the_coder_by_itself(self):
        """The one road from a stranger's text to an agent on this machine with nobody in between
        was the auto-start. Email now gates it on the SENDER (senders.py): known = your own
        domain, has written before, or your mailbox has written to them (Sent Items, asked of the
        server - Taskuary's table starts the day it was connected, the correspondence did not).
        The task still lands; only the automatic session waits for the owner."""
        from unittest import mock
        from taskuary import senders
        s = MemoryStore()
        s.set_setting('coder_auto_enabled', '1', 't')
        s.set_setting('owner_email', 'dana@northwind.example', 't')
        # distinct subjects and bodies: a look-alike would ATTACH to the first task and never reach the create path
        texts = {'e1': ('importer crash', 'the importer throws an exception in jobs/import.py'),
                 'e2': ('invoice portal login', 'customers cannot log into the invoice portal since friday'),
                 'e3': ('nightly scheduler', 'the report scheduler silently skipped tuesday night'),
                 'e4': ('ios signing', 'the mobile build fails at the code signing step on ci'),
                 'e2b': ('vendor portal timeout', 'the vendor portal times out uploading invoices over five megabytes')}
        mail = lambda **kw: self.msg(channel='email', source_name='dana@northwind.example', conversation_id=kw['external_id'],
                                     subject=texts[kw['external_id']][0], body=texts[kw['external_id']][1], **kw)
        with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=False) as wt:
            out = ingest_message(s, mail(external_id='e1', from_email='stranger@evil.example'), llm=TASK_LLM)
        spawn.assert_not_called(); wt.assert_called_once()
        t = s.get_task(out['task_id'])
        self.assertEqual((t['Kind'], t['Status']), ('coding', 'open'))                      # a task, on the Board, not worked
        self.assertTrue(any('not auto-started' in c['Body'] for c in s.list_comments(out['task_id'])))
        self.assertIn('this mailbox has never written to them', s._rows('SELECT * FROM route ORDER BY RouteId DESC')[0]['Reason'])
        # the same stranger writes again: still a stranger. Their own first mail, held for the owner,
        # used to make the second one 'known' and start the agent the hold exists to stop (audit 2026-09-02)
        with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=False):
            self.assertEqual(ingest_message(s, mail(external_id='e2', from_email='Stranger@evil.example'), llm=TASK_LLM)['status'], 'created')
        spawn.assert_not_called()
        # ...until the owner has dealt with them: their own words on one of the stranger's threads
        s.add_message({'ExternalId': 'own-e2', 'Channel': 'email', 'ConversationId': 'e2', 'FromEmail': 'dana@northwind.example',
                       'Status': 'context', 'BodyText': 'thanks - looking into it'})
        with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to') as wt:
            self.assertEqual(ingest_message(s, mail(external_id='e2b', from_email='Stranger@evil.example'), llm=TASK_LLM)['status'], 'created')
        spawn.assert_called_once(); wt.assert_not_called()
        # your own domain: never a stranger
        with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to') as wt:
            self.assertEqual(ingest_message(s, mail(external_id='e3', from_email='teammate@northwind.example'), llm=TASK_LLM)['status'], 'created')
        spawn.assert_called_once(); wt.assert_not_called()
        # someone you have written to for years, whom Taskuary has never seen: Sent Items says so
        with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True):
            self.assertEqual(ingest_message(s, mail(external_id='e4', from_email='old.client@partner.example'), llm=TASK_LLM)['status'], 'created')
        spawn.assert_called_once()
        # chat senders are already inside a workspace you control: no gate at all
        with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to') as wt:
            self.assertEqual(ingest_message(s, self.msg(external_id='e5', channel='teams', from_email='new.colleague@elsewhere.example',
                                                        conversation_id='c5', subject='teams: the exporter', body='e5: exporter fails in jobs/export.py'), llm=TASK_LLM)['status'], 'created')
        spawn.assert_called_once(); wt.assert_not_called()

    def test_the_digest_window_starts_at_midnight_so_a_one_day_digest_is_all_of_yesterday(self):
        from datetime import datetime, timedelta
        from taskuary.digest import gather
        from taskuary.reports import run_digest
        s = MemoryStore()
        tid = s.create_task({'Title': 'fixed at dawn yesterday', 'Kind': 'coding', 'Status': 'done'}, 't')
        dawn = (datetime.now() - timedelta(days=1)).replace(hour=6, minute=0, second=0).isoformat(sep=' ', timespec='seconds')
        s._exec('UPDATE task SET UpdatedAt=? WHERE TaskId=?', (dawn, tid))
        self.assertIn('fixed at dawn yesterday', gather(s, 1))                  # 24h back from 07:26 would have missed it
        self.assertEqual(run_digest({'store': s, 'days': 1})[0], 'yesterday and today so far, distilled')

    def test_no_auto_dispatch_when_disabled(self):
        """Dispatching is ON by default now, so this asserts the SWITCH works - turned off,
        a real task is filed and waits for the owner to start it."""
        from unittest import mock
        s = MemoryStore()
        s.set_setting('coder_auto_enabled', '0', 'owner')
        with mock.patch('taskuary.terminal.start_on_task') as start:
            out = ingest_message(s, self.msg(external_id='ac2'), llm=TASK_LLM)
        start.assert_not_called()
        self.assertEqual(s.get_task(out['task_id'])['Status'], 'open')

    def test_out_of_the_box_a_job_goes_to_the_agent_and_a_question_gets_a_draft(self):
        """Both switches used to ship OFF, so a fresh install watched the mail arrive and did
        nothing with it. Neither one sends anything: a draft waits for approval, and a session
        is one you are watching."""
        d = store_mod.DEFAULT_SETTINGS
        self.assertEqual((d['coder_auto_enabled'], d['auto_draft_enabled']), ('1', '1'))
        self.assertEqual(MemoryStore().get_settings()['coder_auto_enabled'], '1')

    def test_out_of_the_box_timeline_fade_is_normal(self):
        self.assertEqual(store_mod.DEFAULT_SETTINGS['timeline_fade'], 'normal')
        self.assertEqual(MemoryStore().get_settings()['timeline_fade'], 'normal')

    def test_reply_only_is_drafted_by_the_main_ai_not_a_coding_agent(self):
        """A question needs an answer, not an agent. Drafting used to require a CLI agent
        named 'responder' - nobody has one, so reply mail sat undrafted, and the fallback
        was the CODING agent opening a repo to write two sentences."""
        from unittest import mock
        import taskuary.ingest as ing

        class InlineThread:
            def __init__(self, target=None, args=(), daemon=None): self.t, self.a = target, args
            def start(self): self.t(*self.a)

        s = MemoryStore()
        s.set_setting('auto_draft_enabled', '1', 't')
        s.upsert_agent('coder', 'coding', 'cli', '{"cmd": "claude"}')     # the only agent, and NOT for this
        seen = {}
        def fake_llm(system, user, **kw):
            seen['system'], seen['user'] = system, user
            return 'Yes - Monday is covered. I will confirm the cover with Dana.'
        with mock.patch.object(ing, 'threading') as th, \
             mock.patch('taskuary.llm.build_llm', return_value=fake_llm), \
             mock.patch('taskuary.terminal.start_on_task') as sess:
            th.Thread = InlineThread
            out = ingest_message(s, self.msg(external_id='r1', subject='Tuesday?',
                                             body='are you available tuesday?'), llm=REPLY_LLM)
        sess.assert_not_called()                                           # no agent was opened at it
        rv = s.list_reviews('pending')[0]
        self.assertEqual(rv['TaskId'], out['task_id'])
        self.assertIn('Monday is covered', rv['DraftText'])
        self.assertIn('are you available tuesday?', seen['user'])          # the thread went in
        self.assertIn('Output ONLY the message body', seen['system'])

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
                  "[{'type':'tool_use','id':'tool-1','name':'Bash','input':{'command':'ls -la'}}]}}));"
                  "print(json.dumps({'type':'user','message':{'content':"
                  "[{'type':'tool_result','tool_use_id':'tool-1','content':'three files'}]}}));"
                  "print(json.dumps({'type':'result','result':'all done','session_id':'s1'}))")
        ev = []
        with mock.patch('taskuary.agents._resolve_cmd', return_value=[sys.executable]):
            out, sid, _ = run_cli({'cmd': 'python', 'args': ['-c', script], 'timeout': 60},
                                  'hi', lambda k, n, d: ev.append((k, d)))
        self.assertEqual((out, sid), ('all done', 's1'))
        self.assertTrue(any(k == 'live' and 'Bash' in d for k, d in ev))
        self.assertTrue(any(k == 'tool_call' and d['tool_call_id'] == 'tool-1' for k, d in ev))
        self.assertTrue(any(k == 'tool_result' and d['result'] == 'three files' for k, d in ev))

    def test_run_cli_normalizes_codex_jsonl_tools(self):
        from unittest import mock
        from taskuary.agents import run_cli
        import sys
        script = ("import sys,json;sys.stdin.read();"
                  "print(json.dumps({'type':'thread.started','thread_id':'cx1'}));"
                  "print(json.dumps({'type':'item.started','item':{'id':'i1','type':'command_execution','command':'dir','status':'in_progress'}}));"
                  "print(json.dumps({'type':'item.completed','item':{'id':'i1','type':'command_execution','command':'dir','aggregated_output':'ok','exit_code':0,'status':'completed'}}));"
                  "print(json.dumps({'type':'item.completed','item':{'id':'i2','type':'agent_message','text':'finished'}}))")
        ev = []
        with mock.patch('taskuary.agents._resolve_cmd', return_value=[sys.executable, '-c', script]):
            out, sid, _ = run_cli({'cmd': 'codex', 'args': ['exec'], 'timeout': 60},
                                  'hi', lambda k, n, d: ev.append((k, n, d)))
        self.assertEqual((out, sid), ('finished', 'cx1'))
        self.assertTrue(any(k == 'tool_call' and n == 'shell' for k, n, d in ev))
        self.assertTrue(any(k == 'tool_result' and d['result'] == 'ok' for k, n, d in ev))

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
        with mock.patch('taskuary.github.list_items', return_value=issues) as li:
            self.assertEqual(channels.poll_channels(s), 0)          # ...so nothing polls it
            li.assert_not_called()
            s.save_connector({'ConnectorId': gh['ConnectorId'], 'Roles': 'trigger,tool'}, 'o')
            self.assertEqual(channels.poll_channels(s), 1)          # the owner made it a trigger
        feed = s.feed()
        self.assertEqual([m['Channel'] for m in feed], ['github'])
        self.assertIn('o/repo#7', feed[0]['Subject'])               # our own [TQ-] issues never come back

    def test_teams_chats_reach_the_timeline(self):
        """The whole channel was silently missing from poll_channels: the connector card was
        green, the source stamped LastPolledAt, and not one chat message ever landed."""
        from unittest import mock
        from taskuary import channels
        s = MemoryStore()
        tm = next(c for c in s.list_connectors() if c['Type'] == 'teams')
        s.save_connector({'ConnectorId': tm['ConnectorId'], 'Active': 1, 'Roles': 'trigger,tool',
                          'ConfigJson': '{"client_id": "c", "tenant_id": "t"}', 'Secret': 'x'}, 'o')
        s.save_source({'Channel': 'teams', 'Address': 'me@corp.com', 'Active': 1, 'Owner': 'o'}, 'o')
        # the delta feed hands them back NEWEST first, mixed across chats
        msgs = [
            {'id': 'm4', 'chatId': '19:aa', 'messageType': 'message', 'createdDateTime': '2026-08-18T10:03:00Z',
             'from': {'user': {'id': 'me', 'displayName': 'You'}}, 'body': {'content': '<p>I sent it to her in this chat.</p>'}},
            {'id': 'm3', 'chatId': '19:aa', 'messageType': 'message', 'createdDateTime': '2026-08-18T10:02:00Z',
             'from': {'application': {'id': 'bot'}, 'user': None}, 'body': {'content': '<attachment id="x"></attachment>'}},
            {'id': 'm2', 'chatId': '19:aa', 'messageType': 'systemEventMessage', 'createdDateTime': '2026-08-18T10:01:00Z',
             'from': None, 'body': {'content': '<systemEventMessage/>'}},           # call started
            {'id': 'm1', 'chatId': '19:aa', 'messageType': 'message', 'createdDateTime': '2026-08-18T10:00:00Z',
             'from': {'user': {'id': 'u2', 'displayName': 'Priya'}}, 'body': {'content': '<p>can you look at the export?</p>'}},
        ]
        with mock.patch.object(channels, 'graph_token', return_value='tok'), \
             mock.patch.object(channels, '_teams_delta', return_value=msgs), \
             mock.patch.object(channels, '_chat_meta', return_value=('', 'oneOnOne')), \
             mock.patch.object(channels, '_graph_user', return_value=('Priya', 'priya@corp.com')), \
             mock.patch.object(channels.requests, 'get', return_value=mock.Mock(status_code=200,
                                                                               json=lambda: {'id': 'me'})):
            self.assertEqual(channels.poll_channels(s), 2)
        feed = [m for m in s.feed() if m['Channel'] == 'teams']
        self.assertEqual(len(feed), 1)                                 # only the human line, bot + system dropped
        self.assertEqual((feed[0]['FromName'], feed[0]['FromEmail']), ('Priya', 'priya@corp.com'))
        row = s._one('SELECT ConversationId FROM message WHERE MessageId=?', (feed[0]['MessageId'],))
        self.assertEqual(row['ConversationId'], 'teams:19:aa')          # a chat is one thread, like a mail chain
        chain = s.thread_messages(conversation_id='teams:19:aa')
        self.assertEqual([(m['Status'], m['BodyText']) for m in chain],
                         [('filed', 'can you look at the export?'), ('context', 'I sent it to her in this chat.')])

    def test_needs_you_is_anything_no_agent_is_moving(self):
        """The old rule was 'a review is pending', so a task whose agent finished without
        closing it sat in_progress, looking busy, telling nobody."""
        s = MemoryStore()
        out = ingest_message(s, self.msg(external_id='ny1'), llm=TASK_LLM)
        tid = out['task_id']
        row = lambda: next(m for m in s.feed() if m['MessageId'] == out['message_id'])
        self.assertEqual(row()['NeedsYou'], 1)                       # nobody has touched it yet
        rid = s.start_run(tid, 'coder', 'work it', 'o')
        self.assertEqual(row()['NeedsYou'], 0)                       # an agent IS working it
        s.update_run(rid, {'Status': 'done'}, finished=True)
        self.assertEqual(row()['NeedsYou'], 1)                       # it stopped and left it open - yours
        self.assertEqual(len(s.feed(pending_only=True)), 1)
        s.update_task(tid, {'Status': 'done'}, 'o')
        self.assertEqual((row()['NeedsYou'], len(s.feed(pending_only=True))), (0, 0))

    def test_splitting_a_second_ask_off_a_thread(self):
        from taskuary.ingest import split_message
        s = MemoryStore()
        a = ingest_message(s, self.msg(external_id='s1', conversation_id='c9', subject='Chat'), llm=TASK_LLM)
        b = ingest_message(s, self.msg(external_id='s2', conversation_id='c9', subject='Chat',
                                       body='unrelated: should job code 325 have a license?'), llm=TASK_LLM)
        self.assertEqual(b['task_id'], a['task_id'])                 # same thread, one task
        tid = split_message(s, b['message_id'], 'owner')
        self.assertNotEqual(tid, a['task_id'])
        self.assertEqual(s.get_message(b['message_id'])['TaskId'], tid)
        self.assertEqual(len(s.list_messages(a['task_id'])), 1)      # the parent keeps only its own
        # the title comes from the ask, not the chat's name, which every message shares
        self.assertIn('job code 325', s.get_task(tid)['Title'])
        self.assertTrue(any('Split' in c['Body'] for c in s.list_comments(a['task_id'])))

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
        with mock.patch('taskuary.github.list_items', return_value=issues), \
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
        self.assertNotIn('repo', prof['cwd'])                       # triage is not about any checkout: a scratch cwd,
        self.assertNotIn('--dangerously-skip-permissions', prof['args'])   # and no hands (audit 2026-09-02)
        self.assertEqual(prof['timeout'], 300)                      # and never waits a coding-run timeout
        s.set_setting('triage_ai', 'cli:ghost', 'o')
        self.assertIsNone(llm.build_llm(s))                         # missing agent files instead of guessing

    def test_background_ai_falls_back_in_order_when_the_primary_hits_its_session_limit(self):
        from unittest import mock
        from taskuary import llm
        s = MemoryStore()
        s.upsert_agent('claude', 'coding', 'cli', '{"cmd":"claude"}')
        s.upsert_agent('codex', 'coding', 'cli', '{"cmd":"codex"}')
        s.set_setting('triage_ai', 'cli:claude', 'o')
        s.set_setting('triage_backup_ai', 'cli:codex', 'o')
        called = []
        def made(store, name, *args, **kwargs):
            def answer(system, user, **call_kwargs):
                called.append(name)
                if name == 'claude': raise RuntimeError("You've hit your session limit; resets at noon")
                return '{"intent":"fyi","why":"backup answered"}'
            return answer
        with mock.patch.object(llm, 'make_cli_llm', side_effect=made):
            out = llm.build_llm(s)('system', 'message')
        self.assertIn('backup answered', out)
        self.assertEqual(called, ['claude', 'codex'])

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

    def test_run_cli_appends_the_model_flag(self):
        from unittest import mock
        import sys
        from taskuary.agents import run_cli
        script = "import sys;sys.stdin.read();print('ok')"
        with mock.patch('taskuary.agents._resolve_cmd', return_value=[sys.executable]):
            seen = []
            with mock.patch('taskuary.spawn.popen', side_effect=RuntimeError('stop')) as pop:
                try:
                    run_cli({'cmd': 'claude', 'args': ['-c', script], 'model': 'sonnet'}, 'hi', lambda *a: None)
                except RuntimeError:
                    pass
            self.assertEqual(pop.call_args[0][0][-2:], ['--model', 'sonnet'])
            with mock.patch('taskuary.spawn.popen', side_effect=RuntimeError('stop')) as pop2:
                try:
                    run_cli({'cmd': 'codex', 'args': ['exec'], 'model': 'gpt-5-codex', 'model_arg': '-m'}, 'hi', lambda *a: None)
                except RuntimeError:
                    pass
            self.assertEqual(pop2.call_args[0][0][-2:], ['-m', 'gpt-5-codex'])   # flag name is per-CLI

    def test_a_profile_with_only_a_cmd_gets_the_known_headless_flags(self):
        from unittest import mock
        from taskuary.agents import run_cli
        from taskuary.clis import preset_args
        from taskuary.terminal import agent_argv
        # config.toml said [agents.coder] cmd = "claude" and nothing else -> bare `claude -p`, and a
        # non-interactive claude with no permission flag denied every tool call of a scheduled report
        for cmd in ('claude', r'C:\Users\me\AppData\Roaming\npm\claude.cmd', '/usr/local/bin/claude'):
            with mock.patch('taskuary.agents._resolve_cmd', return_value=['X']), \
                 mock.patch('taskuary.spawn.popen', side_effect=RuntimeError('stop')) as pop:
                with self.assertRaises(RuntimeError): run_cli({'cmd': cmd}, 'hi', lambda *a: None)
            self.assertIn('--dangerously-skip-permissions', pop.call_args[0][0]); self.assertIn('-p', pop.call_args[0][0])
        self.assertEqual(preset_args('codex.exe')[0], 'exec'); self.assertEqual(preset_args('mycli'), [])
        with mock.patch('taskuary.spawn.popen', side_effect=RuntimeError('stop')) as pop:
            with mock.patch('taskuary.agents._resolve_cmd', return_value=['X']), self.assertRaises(RuntimeError):
                run_cli({'cmd': 'mycli'}, 'hi', lambda *a: None)
        self.assertEqual(pop.call_args[0][0], ['X', '-p'])                       # an unknown CLI keeps the old bare pipe
        with mock.patch('taskuary.agents._resolve_cmd', side_effect=lambda n: ['X']):   # and the watched session gets the same trust, minus the pipe flags
            self.assertEqual(agent_argv({'cmd': 'claude'}), ['X', '--dangerously-skip-permissions', '--verbose'])
            self.assertEqual(agent_argv({'cmd': 'claude', 'args': ['-p', '--foo']}), ['X', '--foo'])   # args the owner wrote stay theirs

    def test_run_cli_names_a_lapsed_login_and_says_how_to_fix_it(self):
        from unittest import mock
        import sys
        from taskuary.agents import run_cli
        # the exact stderr claude prints when its OAuth session has lapsed - the raw line told the user nothing they could act on
        script = "import sys;sys.stdin.read();sys.stderr.write('Failed to authenticate: OAuth session expired and could not be refreshed');sys.exit(1)"
        with mock.patch('taskuary.agents._resolve_cmd', return_value=[sys.executable]):
            with self.assertRaises(RuntimeError) as e:
                run_cli({'cmd': 'claude', 'args': ['-c', script]}, 'hi', lambda *a: None)
        msg = str(e.exception)
        self.assertIn('signed out', msg); self.assertIn('/login', msg); self.assertIn('come back here', msg)
        self.assertIn('OAuth session expired', msg)                      # the original reason still travels with it
        with mock.patch('taskuary.agents._resolve_cmd', return_value=[sys.executable]):   # any other failure keeps the plain exit line
            with self.assertRaises(RuntimeError) as e2:
                run_cli({'cmd': 'claude', 'args': ['-c', "import sys;sys.stdin.read();sys.stderr.write('boom');sys.exit(2)"]}, 'hi', lambda *a: None)
        self.assertEqual(str(e2.exception), 'claude exit 2: boom')

    def test_the_pane_says_it_is_a_real_terminal(self):
        """codex read TERM=dumb (or none) off a service environment and stopped at 'Continue anyway?
        [y/N]' before its first prompt - the pane is xterm.js, so the env says so."""
        from unittest import mock
        from taskuary.terminal import clean_env
        with mock.patch.dict('os.environ', {'TERM': 'dumb'}): self.assertEqual(clean_env()['TERM'], 'xterm-256color')
        with mock.patch.dict('os.environ', {}, clear=True): self.assertEqual((clean_env()['TERM'], clean_env()['COLORTERM']), ('xterm-256color', 'truecolor'))
        with mock.patch.dict('os.environ', {'TERM': 'screen-256color', 'COLORTERM': 'x'}):
            self.assertEqual((clean_env()['TERM'], clean_env()['COLORTERM']), ('screen-256color', 'x'))   # a real value is left alone

    def test_a_full_path_to_the_cli_still_finds_its_model_list(self):
        from taskuary.server import cli_base, CLI_MODELS
        for cmd in (r'C:\Users\rabbi\AppData\Local\OpenAI\Codex\bin\codex.exe', '/usr/local/bin/codex', 'codex', 'CODEX.CMD'):
            self.assertEqual(cli_base(cmd), 'codex'); self.assertEqual(CLI_MODELS[cli_base(cmd)], CLI_MODELS['codex'])
        self.assertEqual(cli_base(r'C:\npm\claude.cmd'), 'claude'); self.assertEqual(cli_base(''), '')

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

    def test_row_cap_admits_when_the_number_is_just_the_default(self):
        from taskuary.reports import row_limit, rows_out
        self.assertEqual((row_limit({}), row_limit({'max_rows': 50})), ((200, False), (50, True)))
        rows = [{'a': i} for i in range(7)]
        self.assertIn('capped at the default 5', rows_out(rows, 5, mine=False)[0])   # nobody set this
        self.assertIn('capped at 5 ', rows_out(rows, 5, mine=True)[0])               # you did

    def test_interactive_argv_carries_the_model_but_not_the_headless_flags(self):
        from unittest import mock
        from taskuary.terminal import agent_argv
        with mock.patch('taskuary.agents._resolve_cmd', side_effect=lambda n: [n]):
            self.assertEqual(agent_argv({'cmd': 'claude', 'args': ['-p', '--output-format', 'json']}, 'opus'),
                             ['claude', '--model', 'opus'])
            # no args at all -> the known preset stands in (minus its `exec` pipe subcommand), so a
            # cmd-only profile is as unattended in a session as it is headless
            # the two TUI flags come from _codex_browser_tui: inline mode and no decorative
            # animations, so the composer stays responsive over ConPTY -> websocket -> xterm
            self.assertEqual(agent_argv({'cmd': 'codex', 'model_arg': '-m', 'model': 'gpt-5-codex'}),
                             ['codex', '--dangerously-bypass-approvals-and-sandbox', '-m', 'gpt-5-codex',
                              '--no-alt-screen', '-c', 'tui.animations=false'])
            self.assertEqual(agent_argv({'cmd': 'gemini', 'interactive_args': ['chat']}), ['gemini', 'chat'])

    def test_wrap_up_reads_the_screen_and_asks_the_agent_nothing(self):
        """Closing a session used to TYPE a summary request into the pty and wait for an answer.
        The transcript is already there: harvest it, and let the main AI write the report."""
        from taskuary import terminal as term

        class FakeTerm:
            def __init__(self, s): self.buf, self.typed = [s], []
            def scrollback(self): return ''.join(self.buf)
            def write(self, s): self.typed.append(s)

        esc, bar = chr(27), chr(0x2502)                              # a TUI paints colour and gutters
        t = FakeTerm(f'{esc}[35m{bar} {esc}[0mRan the importer.' + chr(13) + chr(10) + f'{bar} Fixed the date parse.' + chr(13) + chr(10))
        self.assertEqual(term.harvest(t), 'Ran the importer.' + chr(10) + 'Fixed the date parse.')
        self.assertEqual(t.typed, [])                                # nothing was asked of the agent
        self.assertFalse(hasattr(term, 'WRAP_PROMPT'))               # and there is no prompt left to send

    def test_report_comes_from_the_transcript_and_survives_a_missing_ai(self):
        from unittest import mock
        from taskuary.coder import report_from_transcript
        s = MemoryStore()
        tid = s.create_task({'Title': 'importer', 'Kind': 'coding'}, 'o')
        seen = {}
        def fake_llm(system, user, **kw):
            seen['user'] = user
            return '{"determination": "bad date", "actions": "fixed run_pto.py", "summary": "runs again"}'
        with mock.patch('taskuary.llm.build_llm', return_value=fake_llm):
            rep = report_from_transcript(s, tid, 'Ran the importer. Fixed the date parse.')
        self.assertEqual((rep['determination'], rep['actions'], rep['summary']), ('bad date', 'fixed run_pto.py', 'runs again'))
        self.assertIn('Fixed the date parse', seen['user'])
        # no AI (or a bad answer) must never lose the record - the transcript itself is filed
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertIn('Fixed the date parse', report_from_transcript(s, tid, 'Ran it. Fixed the date parse.')['summary'])
        self.assertIn('nothing on screen', report_from_transcript(s, tid, '   ')['summary'])

    def test_plain_resolves_repaints_and_keeps_the_gaps(self):
        """A TUI animates by rewriting the line and moves the cursor instead of printing spaces.
        Splitting on the carriage return turned one spinner into a hundred lines of debris, and
        deleting cursor-forward ran "112 active" together into "112active" in real wrap-ups."""
        from taskuary.terminal import plain
        esc, cr = chr(27), chr(13)
        self.assertEqual(plain(esc + '[35m' + chr(0x2502) + ' ' + esc + '[0mhi ' + cr + chr(10) + chr(0x2502) + ' there' + cr + chr(10)),
                         'hi' + chr(10) + 'there' + chr(10))
        self.assertEqual(plain('112' + esc + '[1Cactive employees'), '112 active employees')
        self.assertEqual(plain('112' + esc + '[4Cactive'), '112    active')
        # a frame that clears to end-of-line leaves nothing of the old one behind
        self.assertEqual(plain('Levitating... (0s)' + cr + esc + '[KBaking... (11s)'), 'Baking... (11s)')

    def test_declutter_drops_the_chrome_and_keeps_the_words(self):
        """What the agent SAID is a handful of lines; the rest is spinner frames, a hint bar and a
        token counter, painted hundreds of times. All of it used to land in the wrap-up."""
        from taskuary.terminal import declutter
        junk = [chr(0x273b), '*', chr(0x2722) + chr(0x2026) + '2', chr(0x2736) + '103 tokens)', '85516 tokens',
                chr(0x273b) + 'an8', 'e69', 'va6',                         # a frame painted mid-line
                chr(0x2500) * 90,                                          # a full-width rule
                chr(0x23bf) + ' Tip: Use /statusline to set up a custom status line that will display beneath the input box',
                chr(0x2500) * 90, chr(0x276f), chr(0x00b7) + ' esc to interrupt ' + chr(0x00b7) + ' ' + chr(0x2190) + ' for agents',
                chr(0x273b) + ' Baked for 13s ' + chr(0x00b7) + ' 1 shell still running']
        real = ['Changed: one UPDATE against UserDb.dbo.lookJobCode where JobCode=325.',
                'Left for next time: 112 active employees on code 325.']
        out = declutter(chr(10).join([real[0]] + junk + [real[1]]))
        self.assertEqual(out.splitlines(), real)
        # a real sentence is never chrome, however it reads
        long_line = 'The operator can hit esc to interrupt the agent at any point, which is the whole point of a live session.'
        self.assertIn(long_line, declutter(long_line))
        self.assertEqual(declutter('same' + chr(10) + 'same' + chr(10) + 'same'), 'same')   # repaints collapse

    def test_cli_json_parse(self):
        self.assertEqual(parse_cli_json('{"result": "OK", "session_id": "abc"}'), ('OK', 'abc'))
        self.assertEqual(parse_cli_json('plain'), ('plain', None))

    def test_finishing_hands_the_reply_to_the_responder(self):
        """A finished session does not write email. It reports; the SAME responder that answers
        reply-only mail turns that report into the draft you approve - and the draft has to
        survive the close, which used to supersede it on the spot."""
        from unittest import mock
        from taskuary.coder import finish
        s = MemoryStore()
        tid = s.create_task({'Title': 'importer is down', 'Kind': 'coding'}, 'o')
        # a real ingest always stamps the channel (the push API defaults it to 'api'), and the
        # reply road now asks which channel it is - a channel-less row cannot be answered at all
        s.add_message({'TaskId': tid, 'ExternalId': 'm1', 'Channel': 'email', 'Subject': 'importer is down',
                       'FromEmail': 'ap@client.com', 'SentAt': '2026-08-18 09:00', 'BodyText': 'nothing imported'})
        rep = {'determination': 'a bad date killed the batch', 'actions': 'fixed the date parse', 'summary': 'ran the import'}
        seen = {}
        def fake_llm(system, user, **kw):
            seen['system'], seen['user'] = system, user
            return 'The import is running again - a bad date had stopped the batch.'
        with mock.patch('taskuary.llm.build_llm', return_value=fake_llm):
            finish(s, tid, rep)
        pend = s.list_reviews('pending')
        self.assertEqual((len(pend), pend[0]['Kind'], s.get_task(tid)['Status']), (1, 'draft_reply', 'waiting'))
        self.assertIn('import is running again', pend[0]['DraftText'])
        self.assertIn('fixed the date parse', seen['user'])            # the report is the source of truth
        self.assertIn('FINISHED', seen['system'])                      # ...and it reports, never promises

    def test_finishing_with_nobody_to_reply_to_just_closes(self):
        from taskuary.coder import finish
        s = MemoryStore()
        tid = s.create_task({'Title': 'my own note', 'Kind': 'coding'}, 'o')
        self.assertEqual(finish(s, tid, {'summary': 'did it'})['drafting'], False)
        self.assertEqual((s.get_task(tid)['Status'], s.list_reviews('pending')), ('done', []))

    def test_a_responder_agent_no_longer_takes_the_reply_headless(self):
        """There is no headless road left. A `responder` agent used to hijack this and run a CLI
        open->close where nobody could watch it, interrupt it or answer it - the one thing this
        app exists to replace. Configuring one now changes nothing: the main AI writes the reply,
        in front of you, and it lands on the review for approval like every other draft."""
        from unittest import mock
        from taskuary import agents, responder
        s = MemoryStore()
        tid = s.create_task({'Title': 't'}, 'o')
        s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'Payroll', 'ExternalId': 'rd1',
                       'FromName': 'Dana', 'FromEmail': 'd@n.example', 'BodyText': 'is it fixed?'})
        s.upsert_agent('responder', 'reply', 'cli', '{"cmd": "claude"}')
        rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'Reason': 'r'})
        self.assertFalse(hasattr(agents, 'dispatch'))            # deleted, not left dormant
        with mock.patch('taskuary.llm.build_llm', return_value=lambda sys_, usr, **kw: 'Fixed - it posts to August now.'):
            out = responder.write_draft(s, tid, rid, 'Actions: fixed it')
        self.assertIn('August', out)
        self.assertEqual(s.get_review(rid)['DraftText'], out)

    def test_closing_a_task_resolves_its_pending_reviews(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 't'}, 'o')
        s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'Reason': 'r'})
        s.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'd'})
        s.update_task(tid, {'Status': 'done'}, 'owner')
        self.assertEqual(s.list_reviews('pending'), [])   # done IS the decision

    def test_orphaned_reviews_never_queue(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 't'}, 'u')
        s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'Reason': 'r'})
        s.delete_task(tid)
        s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'Reason': 'late'})
        self.assertEqual(s.list_reviews('pending'), [])

    def test_startup_heals_stacked_pending_reviews(self):
        import tempfile, os
        from taskuary.store import SQLiteStore
        path = os.path.join(tempfile.mkdtemp(), 'heal.db')
        s = SQLiteStore(path)
        tid = s.create_task({'Title': 't'}, 'o')
        for i in range(3):
            s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'Reason': f'r{i}'})
        s.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'd'})
        s2 = SQLiteStore(path)   # reopen = restart
        pend = s2.list_reviews('pending')
        self.assertEqual(len(pend), 2)   # newest of each kind survives
        self.assertEqual({p['Kind'] for p in pend}, {'draft_reply', 'draft'})
        self.assertEqual(next(p['Reason'] for p in pend if p['Kind'] == 'draft_reply'), 'r2')

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

    # ── the AI got the SHAPE wrong: one task holding two jobs, or two holding one ──
    def _two_job_task(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'PTO import failing', 'Summary': 'Please fix the PTO import mapping.\n'
                             'Also we need the 112 active employees added to the roster.', 'Kind': 'coding',
                             'Priority': 'high', 'Source': 'email', 'Tags': 'repo:northwind/Census'}, 'owner')
        mid = s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'PTO import failing',
                             'FromEmail': 'rita@example.com', 'SentAt': '2026-08-19 09:00',
                             'BodyText': 'Please fix the PTO import mapping.\nAlso add the 112 active employees.'})
        return s, tid, mid

    def test_split_keeps_the_history_here_and_carries_the_ticked_mail_over(self):
        s, tid, mid = self._two_job_task()
        new = reshape.split_task(s, tid, {'title': 'Add the 112 active employees', 'summary': 'roster'},
                                 {'title': 'Fix the PTO import mapping'}, [mid])
        self.assertEqual(s.get_task(tid)['Title'], 'Fix the PTO import mapping')      # the ref stays put
        t2 = s.get_task(new)
        self.assertEqual((t2['Kind'], t2['Priority'], t2['Tags']), ('coding', 'high', 'repo:northwind/Census'))
        self.assertEqual(s.get_message(mid)['TaskId'], new)                            # moved, with a route
        self.assertEqual([r['Decision'] for r in s.list_routes(new)], ['split'])
        self.assertIn(task_ref(new), s.list_comments(tid)[-1]['Body'])                 # each side says where
        self.assertIn(task_ref(tid), s.list_comments(new)[-1]['Body'])

    def test_split_never_hands_the_new_task_an_agent_but_keeps_your_own_name_on_it(self):
        s, tid, _mid = self._two_job_task()
        s.update_task(tid, {'Assignee': 'agent:coder'}, 'owner')
        self.assertIsNone(s.get_task(reshape.split_task(s, tid, {'title': 'the other job'}))['Assignee'])
        s.update_task(tid, {'Assignee': 'owner'}, 'owner')
        self.assertEqual(s.get_task(reshape.split_task(s, tid, {'title': 'mine too'}))['Assignee'], 'owner')

    def test_split_needs_a_title_and_ignores_mail_that_is_not_on_the_task(self):
        s, tid, _mid = self._two_job_task()
        with self.assertRaises(ValueError): reshape.split_task(s, tid, {'title': '  '})
        new = reshape.split_task(s, tid, {'title': 'second job'}, None, [9999])
        self.assertEqual(s.list_messages(new), [])

    def test_propose_split_reads_the_ai_and_falls_back_to_the_ask_lines(self):
        s, tid, _mid = self._two_job_task()
        out = reshape.propose_split(s, tid, lambda sys, user, mt=None: '{"two": true, "why": "two asks",'
                                    ' "first": {"title": "Fix the import", "summary": "a"},'
                                    ' "second": {"title": "Add the employees", "summary": "b"}}')
        self.assertEqual((out['ai'], out['two'], out['second']['title']), (True, True, 'Add the employees'))
        # no brain, or a brain that falls over: never claims a split, just offers the pieces
        for llm in (None, lambda *a, **k: 'not json at all'):
            out = reshape.propose_split(s, tid, llm)
            self.assertFalse(out['two'])
            self.assertTrue(out['first']['summary'])
            self.assertIn('112 active employees', out['second']['title'])
        self.assertEqual(len(reshape.propose_split(s, tid)['messages']), 1)

    # ── a report hands back the spreadsheet and the chart, not just prose about them ──
    def _report_rows(self):
        return [{'Employee': 'Tabita C Vaughan', 'Debit': 242.25, 'Period': 'Jun.28 thru Jul.11'},
                {'Employee': 'Avis M Rodgers', 'Debit': 1536.0},
                {'Employee': 'Donna T Eanes', 'Debit': 2611.2, 'Period': 'Jul.12 thru Jul.25', 'Memo': None}]

    def test_report_rows_become_a_real_xlsx_with_numbers_as_numbers(self):
        import openpyxl                      # the reader, not the writer - the writer is ours
        rows = self._report_rows()
        p = Path(tempfile.mkdtemp()) / 'r.xlsx'
        self.assertTrue(artifacts.to_xlsx(rows, p, 'Payroll Journal'))
        ws = openpyxl.load_workbook(p).active
        got = [[c.value for c in r] for r in ws.iter_rows()]
        self.assertEqual(ws.title, 'Payroll Journal')
        self.assertEqual(got[0], ['Employee', 'Debit', 'Period', 'Memo'])   # a ragged row must not shift columns
        self.assertEqual(got[2], ['Avis M Rodgers', 1536.0, None, None])
        self.assertIsInstance(got[1][1], float)                             # Excel can sum it
        self.assertFalse(artifacts.to_xlsx([], p))

    def test_the_chart_needs_a_measure_and_says_what_it_plotted(self):
        rows = self._report_rows()
        self.assertEqual(artifacts.chart_columns(rows), ('Employee', 'Debit'))
        p = Path(tempfile.mkdtemp()) / 'c.svg'
        self.assertEqual(artifacts.to_svg_chart(rows, p, 'Payroll'), 'Debit by Employee')
        svg = p.read_text(encoding='utf-8')
        self.assertIn('Tabita C Vaughan', svg)
        self.assertIn('<rect', svg)
        self.assertNotIn('<script', svg)
        # a table of names and ids is not a chart just because we can draw axes
        self.assertEqual(artifacts.chart_columns([{'a': 'x', 'b': 'y'}]), ('a', None))
        self.assertEqual(artifacts.to_svg_chart([{'a': 'x'}], p), '')

    def test_a_series_over_dates_draws_a_line_not_a_stack_of_bars(self):
        rows = [{'day': f'2026-08-{d:02d}', 'tickets': n} for d, n in zip(range(18, 32), range(38, 52))]
        svg = artifacts.to_svg_chart(rows, None, 'Tickets by day')
        self.assertIn('<polyline', svg)                       # the line
        self.assertNotIn('<rect x=', svg)                     # ...and not fourteen bars
        self.assertIn('51', svg)                              # the last value, labelled
        self.assertNotIn('<script', svg)
        # four rows is a comparison, not a trend, and still reads better as bars
        self.assertIn('<rect x=', artifacts.to_svg_chart(rows[:4], None, 'Tickets by day'))
        # and a label column that is not dates never becomes a timeline
        sites = [{'site': f'Site {i}', 'headcount': 90 + i} for i in range(6)]
        self.assertNotIn('<polyline', artifacts.to_svg_chart(sites, None, 'Headcount'))

    def test_prose_reports_produce_no_files_and_row_reports_produce_both(self):
        s = MemoryStore()
        body = '\n'.join(json.dumps(r) for r in self._report_rows())
        mid = s.add_message({'Channel': 'report', 'Subject': 'Payroll Journal', 'BodyText': body, 'Status': 'feed'})
        self.assertEqual(len(artifacts.attach_report_output(s, mid, 'Payroll Journal', body)), 2)
        names = [a['Name'] for a in s.list_attachments(mid)]
        self.assertTrue(any(n.endswith('.xlsx') for n in names) and any(n.endswith('.svg') for n in names))
        self.assertEqual([a['Inline'] for a in s.list_attachments(mid) if a['Name'].endswith('.svg')], [1])
        prose = s.add_message({'Channel': 'report', 'Subject': 'Digest', 'BodyText': 'Everything looks fine today.'})
        self.assertEqual(artifacts.attach_report_output(s, prose, 'Digest', 'Everything looks fine today.'), [])
        # a body that mixes an AI summary with the rows still yields the rows
        mixed = 'Three employees posted to the wrong period.\n' + body
        self.assertEqual(len(artifacts.rows_from_body(mixed)), 3)

    def test_ask_lines_finds_two_asks_whether_they_are_two_lines_or_one(self):
        two = 'Please fix the PTO import mapping.\nAlso add the 112 active employees.'
        one = 'Hi Dana,\nPlease fix the PTO import mapping. Also add the 112 active employees.\nThanks'
        for body in (two, one):
            self.assertEqual(len(reshape.ask_lines(body)), 2, body)
        # one job described in two sentences is still one piece per line, and greetings never count
        self.assertEqual(reshape.ask_lines('Hello there\nPlease fix the import mapping'), ['Please fix the import mapping'])

    def test_merge_moves_the_mail_appends_the_ask_and_drops_the_duplicate(self):
        s = MemoryStore()
        keep = s.create_task({'Title': 'Add the employees', 'Summary': 'roster work'}, 'owner')
        dupe = s.create_task({'Title': 'Employee roster', 'Summary': 'the 112 active employees'}, 'owner')
        mid = s.add_message({'TaskId': dupe, 'Channel': 'email', 'Subject': 'roster', 'SentAt': '2026-08-19 10:00'})
        s.add_review({'TaskId': dupe, 'Kind': 'draft', 'Status': 'pending'})
        out = reshape.merge_tasks(s, dupe, keep)
        self.assertEqual((out['task_id'], out['moved']), (keep, 1))
        self.assertEqual(s.get_message(mid)['TaskId'], keep)
        self.assertIn('the 112 active employees', s.get_task(keep)['Summary'])
        self.assertEqual(s.get_task(dupe)['Status'], 'dropped')                        # dropped, never deleted
        self.assertIn(task_ref(keep), s.list_comments(dupe)[-1]['Body'])
        self.assertEqual([r['Status'] for r in s.list_reviews()], ['superseded'])       # its draft goes with it

    def test_merge_refuses_itself_a_stranger_and_a_task_an_agent_is_working(self):
        s = MemoryStore()
        a = s.create_task({'Title': 'a'}, 'owner'); b = s.create_task({'Title': 'b'}, 'owner')
        for src, dst in ((a, a), (a, 9999), (9999, b)):
            with self.assertRaises(ValueError): reshape.merge_tasks(s, src, dst)
        s.start_run(a, 'coder', 'go', 'owner')
        with self.assertRaises(ValueError): reshape.merge_tasks(s, a, b)

    def test_merge_candidates_rank_the_task_it_is_really_a_copy_of(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'PTO import mapping is wrong', 'Summary': 'the PTO import maps the wrong column'}, 'owner')
        twin = s.create_task({'Title': 'PTO import maps the wrong column', 'Summary': 'PTO import mapping is wrong'}, 'owner')
        s.create_task({'Title': 'Order new laptops for the studio'}, 'owner')
        cands = reshape.merge_candidates(s, tid)
        self.assertEqual(cands[0]['task_id'], twin)
        self.assertEqual(cands[0]['ref'], task_ref(twin))
        self.assertGreater(cands[0]['score'], cands[-1]['score'])
        self.assertNotIn(tid, [c['task_id'] for c in cands])
        # a hand-typed task keeps its whole ask in Summary - scoring that reads only titles and
        # message bodies (store.snapshots) called two obvious duplicates 0.00 alike
        s2 = MemoryStore()
        a = s2.create_task({'Title': 'Roster work', 'Summary': 'add the 112 active employees to the roster'}, 'owner')
        b = s2.create_task({'Title': 'Headcount', 'Summary': 'the roster needs the 112 active employees'}, 'owner')
        self.assertGreater(reshape.merge_candidates(s2, b)[0]['score'], 0.1)
        self.assertEqual(reshape.merge_candidates(s2, b)[0]['task_id'], a)
        # a task already closed is nothing to fold into
        s2.update_task(a, {'Status': 'done'}, 'owner')
        self.assertEqual(reshape.merge_candidates(s2, b), [])


if __name__ == '__main__':
    unittest.main()


class StampTests(unittest.TestCase):
    """One clock for the timeline. A row that sorts above its own future is not a display
    nit: list_messages orders by SentAt, so the LAST row is what seed_text hands an agent as
    "the ask" - and a three-day-old message sorting last is a wrong instruction, delivered
    with total confidence."""

    def test_graphs_two_digit_fraction_normalizes(self):
        """py3.10's fromisoformat accepts exactly 3 or 6 fractional digits. Graph sends TWO
        ('...:37.94Z'), so this raised, the value was handed back untouched, and the heal that
        exists to fix these rows did nothing at all from the day it was written."""
        self.assertEqual(store_mod.norm_stamp('2026-08-21T18:44:37.94Z')[:10], '2026-08-21')
        self.assertNotIn('T', store_mod.norm_stamp('2026-08-21T18:44:37.94Z'))

    def test_every_fraction_width_and_none_at_all(self):
        for v in ('2026-08-21T18:44:37Z', '2026-08-21T18:44:37.9Z', '2026-08-21T18:44:37.94Z',
                  '2026-08-21T18:44:37.943Z', '2026-08-21T18:44:37.943512Z'):
            self.assertNotIn('T', store_mod.norm_stamp(v), v)

    def test_a_local_stamp_is_left_exactly_as_it_is(self):
        self.assertEqual(store_mod.norm_stamp('2026-08-24 15:29:11'), '2026-08-24 15:29:11')

    def test_something_unparseable_passes_through_rather_than_becoming_now(self):
        self.assertEqual(store_mod.norm_stamp('garbage'), 'garbage')

    def test_a_raw_iso_stamp_can_never_be_STORED_again(self):
        s = MemoryStore()
        mid = s.add_message({'Channel': 'teams', 'ExternalId': 'st1', 'SentAt': '2026-08-21T18:44:37.94Z'})
        self.assertNotIn('T', s.get_message(mid)['SentAt'])

    def test_the_newest_message_really_is_last(self):
        """The failure in one line: the older message sorted last, so it was the one handed
        over as the ask."""
        s = MemoryStore()
        tid = s.create_task({'Title': 't'}, 'o')
        s.add_message({'TaskId': tid, 'ExternalId': 'a', 'SentAt': '2026-08-21T18:44:37.94Z',
                       'BodyText': 'three days ago'})
        s.add_message({'TaskId': tid, 'ExternalId': 'b', 'SentAt': '2026-08-24 15:29:11',
                       'BodyText': 'the actual ask'})
        self.assertEqual(s.list_messages(tid)[-1]['BodyText'], 'the actual ask')
