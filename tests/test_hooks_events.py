"""Hooks tell us what an agent is doing - every state the owner asked about, as an EVENT, not a guess.

Until 2026-09-20 we installed four Claude Code events and read a permission out of a notification by
the word "permission". Claude has a hook for the very things the screen could never tell apart: a
turn that died on a rate limit or a token ceiling (StopFailure, with the error type), the agent
asking inside its own TUI (Notification agent_needs_input), the permission decision itself
(PermissionRequest) and the session ending (SessionEnd). Codex has hooks too now, the same schema.
These tests hold what each event becomes on the record, that the hooks are installed once at user
scope for both CLIs (so setup can do it before any checkout exists), and that the setup flow does so.
"""
import json, os, tempfile, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import cliinstall, hooks, terminal as term, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

CWD = r'C:\code\repo'


def live(tid, sid='run1', cwd=CWD, agent='coder', argv=('claude',), ext_id=''):
    return SimpleNamespace(sid=sid, alive=True, task_id=tid, cwd=cwd, agent=agent, label=agent, argv=list(argv), last=1.0,
                           ext_id=ext_id, started='2026-09-20 09:00:00', typed=[], files=lambda: [], tail=lambda n=3: [],
                           idle=lambda: 0.0, witness=SimpleNamespace(note=lambda n: None), store=None)


class Base(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.fx = Factory(self.s)
        self._sessions = dict(term.SESSIONS); term.SESSIONS.clear()
        self.tid = self.fx.task(title='Fix the cron', kind='coding')
        self._bind = mock.patch.object(term, 'bind_ext', lambda t, sid: setattr(t, 'ext_id', sid)); self._bind.start()

    def tearDown(self):
        self._bind.stop(); term.SESSIONS.clear(); term.SESSIONS.update(self._sessions)

    def session(self, argv=('claude',), ext_id='c-sess'):
        t = live(self.tid, argv=argv, ext_id=ext_id); t.store = self.s
        term.SESSIONS['run1'] = t
        return t

    def fire(self, event, cli='claude', sid='c-sess', **fields):
        return hooks.receive({'hook_event_name': event, 'session_id': sid, 'cwd': CWD, **fields}, cli=cli)

    def state(self): return ws.status(self.s, self.tid)


class StopFailureTests(Base):
    def test_a_rate_limit_is_a_stall_the_owner_can_see(self):
        """The screen showed a prompt and we said "waiting on you". It was a wall, not a question."""
        self.session()
        self.fire('StopFailure', error_type='rate_limit', error_message='You have hit your usage limit until 3pm.')
        st = self.state()
        self.assertEqual(st['state'], 'stalled')
        req = st['requests'][-1]
        self.assertEqual(req['kind'], 'stalled')
        self.assertIn('rate limit', req['text']); self.assertIn('3pm', req['text'])
        self.assertIn('rate limit', ws.request_line('coder', req))

    def test_a_stall_outranks_an_older_question(self):
        """A question cannot be answered through a wall; what is actually blocking leads."""
        self.session()
        self.fire('Notification', notification_type='agent_needs_input', message='Which branch?')
        self.fire('StopFailure', error_type='max_output_tokens', error_message='Output too long.')
        self.assertEqual(self.state()['state'], 'stalled')

    def test_a_stall_clears_when_the_run_speaks_again(self):
        self.session()
        self.fire('StopFailure', error_type='overloaded', error_message='Overloaded.')
        self.assertEqual(self.state()['state'], 'stalled')
        self.fire('Stop', last_assistant_message='Resumed and finished the search.')
        self.assertNotEqual(self.state()['state'], 'stalled'); self.assertEqual(self.state()['requests'], [])

    def test_a_quota_auto_resume_clears_the_stall_too(self):
        self.session()
        self.fire('StopFailure', error_type='rate_limit', error_message='Limit.')
        self.fire('Notification', notification_type='quota_auto_resume_fired', message='Resuming.')
        self.assertEqual(self.state()['requests'], [])


class QuestionAndPermissionTests(Base):
    def test_claude_asking_inside_its_tui_is_a_question_event(self):
        """A chooser drawn in the TUI emits no tool hook; the typed notification is the only witness."""
        self.session()
        self.fire('Notification', notification_type='agent_needs_input', message='Pick a database: staging or prod?')
        st = self.state()
        self.assertEqual(st['state'], 'input_needed'); self.assertIn('staging or prod', st['requests'][0]['text'])

    def test_an_idle_prompt_is_a_question_with_a_default_sentence(self):
        self.session()
        self.fire('Notification', notification_type='idle_prompt')
        self.assertEqual(self.state()['state'], 'input_needed'); self.assertTrue(self.state()['requests'][0]['text'])

    def test_a_permission_request_names_the_tool_and_its_arguments(self):
        self.session()
        self.fire('PermissionRequest', tool_name='Bash', tool_input={'command': 'rm -rf build'}, tool_use_id='tu1')
        st = self.state()
        self.assertEqual(st['state'], 'approval_needed')
        self.assertIn('Bash', st['requests'][0]['text']); self.assertIn('rm -rf build', st['requests'][0]['text'])
        # ...and the tool then RUNNING is the permission having been granted in the pane
        self.fire('PostToolUse', tool_name='Bash', tool_input={'command': 'rm -rf build'}, tool_response={})
        self.assertEqual(self.state()['requests'], [])

    def test_the_typed_permission_notification_still_works(self):
        self.session()
        self.fire('Notification', notification_type='permission_prompt', message='Claude needs your permission to use Bash')
        self.assertEqual(self.state()['state'], 'approval_needed')

    def test_asking_the_owner_is_a_question_not_a_permission(self):
        """Claude asks leave to run AskUserQuestion, so the PermissionRequest CARRIES the question: the record
        says asked, with the choices - never "needs your approval: AskUserQuestion {json}" (2026-09-20)."""
        self.session()
        q = {'questions': [{'question': 'alpha or beta?', 'header': 'Name', 'options': [{'label': 'alpha'}, {'label': 'beta'}]}]}
        self.fire('PermissionRequest', tool_name='AskUserQuestion', tool_input=q, tool_use_id='tu2')
        st = self.state()
        self.assertEqual(st['state'], 'input_needed')
        self.assertEqual((st['requests'][0]['text'], st['requests'][0]['choices']), ('alpha or beta?', ['alpha', 'beta']))
        self.assertEqual(ws.request_line('coder', st['requests'][0]), 'coder asked you: alpha or beta?')
        # the generic notification that follows a few seconds later is the same stop, not a second one
        self.fire('Notification', notification_type='permission_prompt', message='Claude needs your permission')
        self.assertEqual(len(self.state()['requests']), 1)
        # ...and the owner picking in the pane completes the tool: asked and answered, nothing left open
        self.fire('PostToolUse', tool_name='AskUserQuestion', tool_input=q, tool_response={'answers': {'alpha or beta?': 'alpha'}})
        self.assertEqual(self.state()['requests'], [])

    def test_the_generic_permission_sentence_never_replaces_the_specific_one(self):
        self.session()
        self.fire('PermissionRequest', tool_name='Edit', tool_input={'file_path': 'server.py'}, tool_use_id='tu3')
        self.fire('Notification', notification_type='permission_prompt', message='Claude needs your permission')
        st = self.state()
        self.assertEqual(len(st['requests']), 1); self.assertIn('Edit', st['requests'][0]['text'])

    def test_an_mcp_elicitation_is_a_question_until_answered(self):
        self.session()
        self.fire('Elicitation', server_name='jira', tool_name='create_issue', prompt='Which project key?', input_type='text')
        self.assertEqual(self.state()['state'], 'input_needed'); self.assertIn('Which project key', self.state()['requests'][0]['text'])
        self.fire('ElicitationResult', server_name='jira', tool_name='create_issue', prompt='Which project key?', response='OPS')
        self.assertEqual(self.state()['requests'], [])


class SessionLifeTests(Base):
    def test_session_end_ends_the_run_on_the_record(self):
        self.session()
        self.fire('UserPromptSubmit', prompt='go')
        self.fire('SessionEnd', reason='other')
        self.assertEqual(self.state()['state'], 'disconnected')

    def test_clearing_the_conversation_is_not_the_run_ending(self):
        """/clear fires SessionEnd(reason=clear) while the process very much lives on."""
        self.session()
        self.fire('UserPromptSubmit', prompt='go')
        self.fire('SessionEnd', reason='clear')
        self.assertNotEqual(self.state()['state'], 'disconnected')

    def test_session_start_binds_the_session_before_it_says_anything(self):
        t = self.session(ext_id='')
        self.fire('SessionStart', sid='fresh-id', source='startup')
        self.assertEqual(t.ext_id, 'fresh-id')

    def test_a_pty_that_dies_writes_its_own_ending(self):
        """The one idempotent place that already knows a run ended (release_task) now says so on the
        worker record too - so a question left open by a dead run stops reading as open for ever."""
        self.s.update_task(self.tid, {'Status': 'in_progress'}, 'test')
        self.s.start_run(self.tid, 'coder', 'fix the cron', 'owner')          # a running row, as a live pty leaves one
        ws.record(self.s, self.tid, 'run1', 'input_needed', request_id='q1', text='Staging or prod?', source='hook')
        self.assertEqual(self.state()['state'], 'input_needed')
        term.release_task(self.s, self.tid)
        self.assertEqual(self.state()['state'], 'disconnected')


class CodexTests(Base):
    def test_a_codex_hook_binds_to_the_codex_session_in_that_checkout(self):
        t = self.session(argv=('codex',), ext_id='')
        out = self.fire('Stop', cli='codex', sid='thr-1', last_assistant_message='done the search')
        self.assertTrue(out['bound']); self.assertEqual(t.ext_id, 'thr-1')
        self.assertEqual(ws.events(self.s, self.tid, 'run1')[-1]['Kind'], 'turn_end')

    def test_a_claude_payload_never_binds_to_a_codex_session(self):
        self.session(argv=('codex',), ext_id='')
        self.assertFalse(self.fire('Stop', cli='claude', sid='c-1', last_assistant_message='x')['bound'])

    def test_codex_events_become_the_same_record(self):
        self.session(argv=('codex',), ext_id='thr-1')
        self.fire('UserPromptSubmit', cli='codex', sid='thr-1', prompt='go')
        self.assertEqual(self.state()['state'], 'working')
        self.fire('PermissionRequest', cli='codex', sid='thr-1', tool_name='shell', tool_input={'command': 'git push'})
        self.assertEqual(self.state()['state'], 'approval_needed')
        self.fire('PostToolUse', cli='codex', sid='thr-1', tool_name='shell', tool_input={'command': 'git push'}, tool_response={})
        self.fire('Interrupt', cli='codex', sid='thr-1')
        self.assertEqual(ws.events(self.s, self.tid, 'run1')[-1]['Kind'], 'turn_end')
        self.fire('SessionEnd', cli='codex', sid='thr-1', reason='other')
        self.assertEqual(self.state()['state'], 'disconnected')


class CodexSpoolTests(Base):
    """Codex's hook cannot reach the network on this box, sandbox on or off (measured 2026-09-20), while a
    file write from a hook succeeds every time. So the hook appends its stdin to a spool and we tail it."""

    def test_the_spool_is_decoded_however_cmd_wrote_it(self):
        utf16 = b'\xff\xfe' + json.dumps({'a': 1}).encode('utf-16-le') + '\r\n'.encode('utf-16-le')
        utf8 = (json.dumps({'b': 2}) + '\n').encode('utf-8')
        self.assertEqual([json.loads(l) for l in hooks.decode_spool(utf8 + utf16 + utf16)], [{'b': 2}, {'a': 1}, {'a': 1}])

    def test_spooled_payloads_reach_the_codex_session(self):
        t = self.session(argv=('codex',), ext_id='')
        raw = b'\xff\xfe' + (json.dumps({'hook_event_name': 'Stop', 'session_id': 'thr-9', 'cwd': CWD, 'last_assistant_message': 'ok'})
                             + '\r\n').encode('utf-16-le')
        self.assertEqual(hooks.CodexSpool('unused').feed(raw), 1)
        self.assertEqual(t.ext_id, 'thr-9')
        self.assertEqual(ws.events(self.s, self.tid, 'run1')[-1]['Kind'], 'turn_end')

    def test_the_codex_hook_command_appends_stdin_to_the_spool(self):
        cmd = hooks.codex_command(r'C:\Users\me\.taskuary\hooks\codex.jsonl')
        self.assertIn('codex.jsonl', cmd); self.assertNotIn('curl', cmd); self.assertNotIn('http', cmd)


class InstallTests(unittest.TestCase):
    def test_claude_hooks_install_once_at_user_scope_with_every_event(self):
        with tempfile.TemporaryDirectory() as home:
            p = os.path.join(home, '.claude', 'settings.json')
            os.makedirs(os.path.dirname(p)); json.dump({'theme': 'dark', 'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'say done'}]}]}}, open(p, 'w'))
            self.assertTrue(hooks.install_user('claude', base='http://127.0.0.1:1', token='t', home=home))
            cur = json.load(open(p, encoding='utf-8'))
            self.assertEqual(cur['theme'], 'dark')                                           # nothing else touched
            for ev in hooks.EVENTS: self.assertTrue(any(hooks.MARK in h['command'] for g in cur['hooks'][ev] for h in g['hooks']), ev)
            for ev in ('StopFailure', 'PermissionRequest', 'SessionEnd', 'SessionStart', 'Elicitation'): self.assertIn(ev, hooks.EVENTS)
            self.assertTrue(any(h['command'] == 'say done' for g in cur['hooks']['Stop'] for h in g['hooks']))   # theirs kept
            self.assertFalse(hooks.install_user('claude', base='http://127.0.0.1:1', token='t', home=home))     # idempotent

    def test_a_project_install_retires_our_old_entries_so_nothing_fires_twice(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(hooks.install(d, base='http://127.0.0.1:1'))                     # the legacy per-checkout file
            self.assertTrue(hooks.retire_project(d))
            cur = json.load(open(os.path.join(d, '.claude', 'settings.local.json'), encoding='utf-8'))
            self.assertFalse(any(hooks.MARK in h.get('command', '') for lst in cur.get('hooks', {}).values() for g in lst for h in g.get('hooks', [])))
            self.assertFalse(hooks.retire_project(d))                                        # nothing left to retire

    def test_codex_hooks_install_at_user_scope_within_its_three_second_clamp(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertTrue(hooks.install_user('codex', base='http://127.0.0.1:1', token='t', home=home))
            cur = json.load(open(os.path.join(home, '.codex', 'hooks.json'), encoding='utf-8'))
            for ev in hooks.CODEX_EVENTS:
                for g in cur['hooks'][ev]:
                    for h in g['hooks']:
                        self.assertIn(hooks.CODEX_MARK, h['command']); self.assertLessEqual(h['timeout'], 3)
                        self.assertNotIn('NUL', h['command'])          # not a device under Codex's shell: an illegal file name

    def test_setup_installs_the_hooks_right_after_the_cli(self):
        with mock.patch.object(cliinstall, 'plan', return_value=[{'how': 'script', 'cmd': ['x'], 'timeout': 1}]), \
             mock.patch.object(cliinstall, '_run', return_value=(0, 'ok')), \
             mock.patch.object(cliinstall, 'find', return_value=r'C:\bin\claude.cmd'), \
             mock.patch.object(cliinstall, 'ensure_on_path'), \
             mock.patch.object(cliinstall, 'broken', return_value=''), \
             mock.patch.object(hooks, 'install_user') as inst:
            self.assertEqual(cliinstall.install('claude')['phase'], 'done')
        self.assertEqual(inst.call_args.args[0], 'claude')
