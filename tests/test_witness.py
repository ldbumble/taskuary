"""Said and did: what an agent holds, read off Claude's hooks and Codex's rollout, in one shape."""
import json, os, tempfile, time, unittest
from types import SimpleNamespace
from fastapi.testclient import TestClient
from taskuary import hooks, server, witness
from taskuary import terminal as term

c = TestClient(server.app)
CWD = r'C:\repo'


def ev(kind, item=None, **payload):
    return {'timestamp': '2026-08-28T20:26:26.000Z', 'type': 'event_msg', 'payload': {'type': kind, **({'item': item} if item else {}), **payload}}


class ParserTests(unittest.TestCase):
    def test_codex_rollout_lines_become_tool_file_say_and_done(self):
        w = witness.Witness()
        lines = [ev('task_started'),
                 {'type': 'response_item', 'payload': {'type': 'custom_tool_call', 'name': 'exec', 'input': 'const r = await tools.exec_command({"cmd":"pytest -q"})'}},
                 ev('item_completed', {'type': 'CommandExecution', 'command': ['powershell.exe', '-Command', 'git status']}),
                 ev('item_completed', {'type': 'FileChange', 'changes': {r'C:\repo\taskuary\server.py': {'type': 'update'}}}),
                 {'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'update_plan', 'arguments': json.dumps({'plan': [{'step': 'fix server.py', 'status': 'completed'}, {'step': 'run tests', 'status': 'in_progress'}]})}},
                 ev('item_completed', {'type': 'AgentMessage', 'content': [{'type': 'Text', 'text': 'Done, tests green.'}]}),
                 ev('task_complete', last_agent_message='Done, tests green.')]
        for j in lines:
            for n in witness.codex_notes(j): w.note(n)
        s = w.snapshot([], CWD, 'last line')
        self.assertEqual(s['tool']['name'], 'Edit'); self.assertEqual(s['files'][0]['path'], 'taskuary/server.py'); self.assertEqual(s['files'][0]['n'], 1)
        self.assertEqual([t['status'] for t in s['todos']], ['done', 'now']); self.assertEqual(s['n_done'], 1)
        self.assertTrue(s['done_at']); self.assertIn('tests green', s['said']); self.assertEqual(s['source'], 'rollout')

    def test_claude_hooks_late_and_stray_are_facts_not_verdicts(self):
        w = witness.Witness()
        feed = lambda p: [w.note(n) for n in witness.claude_notes(p)]
        feed({'hook_event_name': 'UserPromptSubmit', 'prompt': 'go'})
        feed({'hook_event_name': 'PostToolUse', 'tool_name': 'TodoWrite', 'tool_input': {'todos': [
            {'content': 'wa/status in server.py: add node flag', 'status': 'completed'}, {'content': 'card auto-start', 'status': 'in_progress'}, {'content': 'tests', 'status': 'pending'}]}})
        feed({'hook_event_name': 'PostToolUse', 'tool_name': 'Edit', 'tool_input': {'file_path': r'C:\repo\taskuary\server.py', 'old_string': 'a', 'new_string': 'b'}})
        s = w.snapshot([r'C:\repo\website\src\App.jsx'], CWD, '')
        self.assertEqual(s['tool']['name'], 'Edit'); self.assertEqual(s['rung'], 'tool')
        self.assertEqual({f['path']: f['stray'] for f in s['files']}, {'taskuary/server.py': False, 'website/src/App.jsx': True})   # the list names server.py, not App
        self.assertEqual(s['flags'], [])                                                    # nothing is late while the agent still works
        feed({'hook_event_name': 'Stop', 'last_assistant_message': 'All done.'})
        time.sleep(1.1)                                                                     # a write AFTER done, a second later
        feed({'hook_event_name': 'PostToolUse', 'tool_name': 'Write', 'tool_input': {'file_path': r'C:\repo\taskuary\store.py'}})
        s = w.snapshot([], CWD, '')
        late = next(f for f in s['files'] if f['path'] == 'taskuary/store.py')
        self.assertTrue(late['late']); self.assertEqual(s['flags'][0]['level'], 'check'); self.assertIn('store.py written after the agent said done', s['flags'][0]['text'])
        # a list that never names a file cannot make anything stray - that would be noise, not a fact
        w2 = witness.Witness()
        w2.note({'k': 'todos', 'items': [{'text': 'wire the card', 'status': 'now'}]}); w2.note({'k': 'file', 'path': 'x.py'})
        self.assertFalse(w2.snapshot([], '', '')['files'][0]['stray'])

    def test_rung_says_what_the_card_stands_on(self):
        w = witness.Witness()
        self.assertEqual(w.snapshot([], '', '')['rung'], 'files')
        self.assertEqual(w.snapshot([], '', 'some screen line')['rung'], 'line')


class HookWiringTests(unittest.TestCase):
    def setUp(self): self._keep = dict(term.SESSIONS); term.SESSIONS.clear()
    def tearDown(self): term.SESSIONS.clear(); term.SESSIONS.update(self._keep)

    def test_install_is_additive_and_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, '.claude', 'settings.local.json'); os.makedirs(os.path.dirname(p))
            with open(p, 'w', encoding='utf-8') as f: json.dump({'permissions': {'allow': ['Bash(ls)']}, 'hooks': {'PostToolUse': [{'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'echo theirs'}]}]}}, f)
            self.assertTrue(hooks.install(d, 'http://127.0.0.1:7787')); self.assertFalse(hooks.install(d, 'http://127.0.0.1:7787'))
            got = json.load(open(p, encoding='utf-8'))
            self.assertEqual(got['permissions'], {'allow': ['Bash(ls)']})                    # theirs, untouched
            post = got['hooks']['PostToolUse']
            self.assertEqual(post[0]['hooks'][0]['command'], 'echo theirs')                # their hook kept, ours appended
            self.assertIn('/api/hooks/claude', post[1]['hooks'][0]['command']); self.assertIn('curl', post[1]['hooks'][0]['command'])
            self.assertTrue(all(k in got['hooks'] for k in ('Stop', 'UserPromptSubmit')))

    def _fake(self, sid, tid, cwd=CWD, argv=('claude',), last=None):
        t = SimpleNamespace(sid=sid, alive=True, task_id=tid, cwd=cwd, argv=list(argv), agent='coder', label='coder', last=last or time.time(),
                            started='2026-08-28 09:00:00', witness=witness.Witness(), ext_id='', files=lambda: [], tail=lambda n=3: ['screen'])
        t.idle = lambda: 0.0
        t.info = lambda tail=0: term.Term.info(t, tail)
        term.SESSIONS[sid] = t
        return t

    def test_a_hook_binds_to_the_claude_session_in_that_checkout(self):
        a = self._fake('a', 1, last=time.time() - 60); b = self._fake('b', 2)             # two claudes, same checkout: the active one gets it
        self._fake('x', 3, argv=['codex'])                                               # codex never takes a claude hook
        r = hooks.receive({'session_id': 'S1', 'cwd': CWD, 'hook_event_name': 'PostToolUse', 'tool_name': 'Edit', 'tool_input': {'file_path': r'C:\repo\a.py'}})
        self.assertEqual(r, {'bound': True, 'sid': 'b'}); self.assertEqual(b.ext_id, 'S1'); self.assertEqual(b.witness.tool['name'], 'Edit')
        a.last = time.time()                                                             # a wakes up - but S1 stays bound to b
        hooks.receive({'session_id': 'S1', 'cwd': CWD, 'hook_event_name': 'Stop', 'last_assistant_message': 'done'})
        self.assertTrue(b.witness.done_at); self.assertIsNone(a.witness.done_at)
        self.assertEqual(hooks.receive({'session_id': 'S9', 'cwd': r'C:\elsewhere', 'hook_event_name': 'Stop'}), {'bound': False})

    def test_the_endpoint_feeds_the_board_and_the_task_page(self):
        tid = c.post('/api/tasks', json={'Title': 'said and did'}).json()['taskId']
        self._fake('s1', tid)
        body = {'session_id': 'S1', 'cwd': CWD, 'hook_event_name': 'PostToolUse', 'tool_name': 'TodoWrite',
                'tool_input': {'todos': [{'content': 'edit server.py', 'status': 'in_progress'}]}}
        self.assertEqual(c.post('/api/hooks/claude', json=body).json()['bound'], True)
        c.post('/api/hooks/claude', json={**body, 'tool_name': 'Edit', 'tool_input': {'file_path': r'C:\repo\taskuary\server.py'}})
        live = next(r for r in c.get('/api/runs/live').json()['data'] if r['TaskId'] == tid)
        self.assertEqual(live['work']['tool']['name'], 'Edit'); self.assertEqual(live['work']['todos'][0]['status'], 'now')
        w = c.get(f'/api/tasks/{tid}/work', params={'diff': False}).json()
        self.assertEqual(w['files'][0]['path'], 'taskuary/server.py'); self.assertEqual(w['prov']['by'], 'coder'); self.assertEqual(w['session']['sid'], 's1')
        self.assertEqual(c.post('/api/hooks/claude', content=b'not json').json(), {'bound': False})   # a hook must never trouble the agent
