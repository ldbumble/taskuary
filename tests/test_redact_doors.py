"""The three doors a prompt can leave this machine by, each shut on credentials.

Every model call in the app goes out through one of these:

* ``llm.build_llm``      - the hosted brains (triage, assistant, concierge, drafter, digest).
                           Its own docstring says "everything in the app asks for its brain here".
* ``agents.run_cli``     - a headless CLI run. This is the one the owner asked about: the coding agent
                           prompt is built by ``agents.task_context``, which writes each message's
                           ``BodyText`` in verbatim.
* ``terminal.open_session`` - the first prompt of an interactive pane, by either road: handed to
                           the CLI in argv (claude, codex, gemini, copilot, devin) or typed in.

A door test is worth more than a pattern test: patterns can be right while a call site forgets
to use them, which is exactly how this leaked in the first place.
"""
import json
import unittest
from unittest import mock

from taskuary import agents, llm, redact, terminal
from taskuary.store import MemoryStore

KEY = 'AKIA' + 'IOSFODNN7EXAMPLE'
MAIL = f'Hi - the deploy box needs {KEY} to reach S3. Can you wire it up?'


def _coder(s):
    s.upsert_agent('claude', 'coding', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p']}))


class TheHostedBrainDoorTests(unittest.TestCase):
    def test_a_credential_never_reaches_the_model(self):
        s = MemoryStore()
        row = [c for c in s.list_connectors() if c['Type'] == 'anthropic'][0]
        s.save_connector({'ConnectorId': row['ConnectorId'], 'Secret': 'k', 'Active': 1, 'ConfigJson': '{}'}, 'o')
        s.set_setting('triage_ai', 'connector:anthropic', 't')
        seen = {}
        def recorder(system, user, **kw): seen.update(system=system, user=user); return 'ok'
        with mock.patch.object(llm, 'make_llm', return_value=recorder):
            brain = llm.build_llm(s)
            self.assertEqual(brain(f'You sort mail. {KEY}', MAIL), 'ok')
        self.assertNotIn(KEY, seen['user']); self.assertNotIn(KEY, seen['system'])
        self.assertIn('[redacted:aws-key]', seen['user'])
        self.assertIn('wire it up', seen['user'])                      # the ask still reads

    def test_the_wrapper_keeps_the_attributes_callers_read_off_it(self):
        """`llm.build_llm(...).session_id` is how a resumed CLI thread is carried; a wrapper that
        swallows it would silently break session continuity rather than fail loudly."""
        s = MemoryStore()
        row = [c for c in s.list_connectors() if c['Type'] == 'anthropic'][0]
        s.save_connector({'ConnectorId': row['ConnectorId'], 'Secret': 'k', 'Active': 1, 'ConfigJson': '{}'}, 'o')
        s.set_setting('triage_ai', 'connector:anthropic', 't')
        def recorder(system, user, **kw): return 'ok'
        recorder.session_id = 'thread-7'
        with mock.patch.object(llm, 'make_llm', return_value=recorder):
            brain = llm.build_llm(s)
            brain('sys', 'user')
            self.assertEqual(getattr(brain, 'session_id', None), 'thread-7')


class ACliBuiltOutsideTheOneDoorTests(unittest.TestCase):
    """Round 5: the Assistant's CLI and a report's agent run are built by llm.make_cli_llm directly, past build_llm's wrapper - and a
    CLI's instructions go by a road of their own (a system file), so what was in them left as it was. Both come back scrubbed now."""
    SYSTEM = 'You are the Assistant. MEMORY: Erin Blake, SSN 078-05-1120, portal password: chirp-pass9'

    def _seen(self, build):
        seen = {}
        def cli(system, user, **kw): seen.update(system=str(system), user=user); return 'ok'
        with mock.patch.object(llm, 'make_cli_llm', return_value=cli): build(seen)
        self.assertNotIn('078-05-1120', seen['system']); self.assertNotIn('chirp-pass9', seen['system'])
        self.assertIn('[redacted:ssn]', seen['system'])

    def test_the_assistants_cli(self):
        from taskuary import concierge
        s = MemoryStore()
        with mock.patch.object(concierge, 'pick', return_value='cli:claude'):
            self._seen(lambda seen: concierge.brain(s)(self.SYSTEM, 'next'))

    def test_a_reports_agent_run(self):
        from taskuary import agents, reports
        s = MemoryStore()
        with mock.patch.object(agents, 'connection_brains', return_value=[('claude', 'Claude')]), mock.patch.object(reports, 'AGENT_SYSTEM', self.SYSTEM):
            self._seen(lambda seen: reports.run_agent({'store': s, 'agent': 'claude', 'prompt': 'Weekly ledger review'}))


class _FakeProc:
    """Enough of a Popen for run_cli to finish one turn, recording what was fed to stdin."""
    def __init__(self, fed): self.fed, self.returncode = fed, 0
    class _In:
        def __init__(self, fed): self.fed = fed
        def write(self, s): self.fed.append(s)
        def close(self): pass
    @property
    def stdin(self): return self._In(self.fed)
    @property
    def stdout(self): return iter(['{"type": "result", "result": "done"}'])
    @property
    def stderr(self):
        class _E:
            def read(self): return ''
        return _E()
    def poll(self): return 0
    def wait(self, timeout=None): return 0
    def kill(self): pass


class TheHeadlessCliDoorTests(unittest.TestCase):
    def test_a_credential_never_reaches_the_subprocess(self):
        fed = []
        with mock.patch.object(agents, '_resolve_cmd', return_value=['claude']), \
             mock.patch.object(agents.spawn, 'popen', side_effect=lambda *a, **k: _FakeProc(fed)):
            agents.run_cli({'cmd': 'claude', 'args': ['-p']}, f'Work this task:\n{MAIL}', lambda *a: None)
        self.assertTrue(fed)
        self.assertNotIn(KEY, fed[0]); self.assertIn('[redacted:aws-key]', fed[0])

    def test_the_stored_trace_of_the_prompt_is_scrubbed_too(self):
        """`run_cli` traces the prompt it sent, and that trace is saved on the run."""
        traced, fed = [], []
        with mock.patch.object(agents, '_resolve_cmd', return_value=['claude']), \
             mock.patch.object(agents.spawn, 'popen', side_effect=lambda *a, **k: _FakeProc(fed)):
            agents.run_cli({'cmd': 'claude', 'args': ['-p']}, MAIL,
                           lambda kind, name, text='': traced.append(str(text)))
        self.assertNotIn(KEY, ' '.join(traced))


class TheInteractivePaneDoorTests(unittest.TestCase):
    def _open(self, cmd, seed, tmp):
        s = MemoryStore()
        s.upsert_agent(cmd, 'coding', 'cli', json.dumps({'cmd': cmd, 'args': ['-p']}))
        tid = s.create_task({'Title': 'wire up S3', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
        with mock.patch.object(agents, '_resolve_cmd', return_value=[cmd]), \
             mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(terminal, 'Term') as Term:
            Term.return_value.sid, Term.return_value.task_id, Term.return_value.store = 'p1', tid, s
            Term.return_value.agent, Term.return_value.cwd, Term.return_value.ext_id = cmd, str(tmp), ''
            terminal.open_session(s, cmd, tid, None, str(tmp), actor='owner', seed_fn=lambda here: seed)
        return Term

    def test_a_prompt_handed_over_in_argv_is_scrubbed(self):
        import tempfile
        Term = self._open('claude', MAIL, tempfile.gettempdir())
        argv = ' '.join(str(a) for a in Term.call_args.args[0])
        self.assertNotIn(KEY, argv); self.assertIn('[redacted:aws-key]', argv)

    def test_a_prompt_that_has_to_be_typed_in_is_scrubbed(self):
        import tempfile
        Term = self._open('cursor-agent', MAIL, tempfile.gettempdir())
        typed = ' '.join(str(a) for a in (Term.return_value.seed.call_args.args or ()))
        self.assertNotIn(KEY, typed); self.assertIn('[redacted:aws-key]', typed)


class NothingLeavesCarryingAPlaceholderTests(unittest.TestCase):
    def test_a_draft_still_holding_a_placeholder_is_not_sent(self):
        """A placeholder in outbound text means the scrub ran on something the owner meant to
        send. That is a bug to catch, not a message to deliver."""
        self.assertTrue(redact.holds_placeholder('I rotated [redacted:aws-key] for you'))
        self.assertFalse(redact.holds_placeholder('I rotated the key for you'))



class APlaceholderNeverGoesOutTests(unittest.TestCase):
    """The scrub runs on prompts, never on the owner's mail - so a placeholder appearing in
    something ADDRESSED TO A PERSON means a prompt's text was reused as a reply. Refuse it: the
    recipient would read `[redacted:aws-key]` where a sentence should be, and neither they nor
    the owner would know why."""

    def test_an_outbound_report_carrying_a_placeholder_is_refused(self):
        from taskuary import outbound
        s = MemoryStore()
        with self.assertRaises(RuntimeError) as e:
            outbound.send_out(s, 'email', 'dana@example.com', 'Keys', 'I rotated [redacted:aws-key] today')
        self.assertIn('redacted', str(e.exception).lower())

    def test_a_reply_carrying_a_placeholder_is_refused(self):
        from taskuary import outbound
        s = MemoryStore()
        msg = {'Channel': 'email', 'ExternalId': 'x1', 'FromEmail': 'dana@example.com'}
        with self.assertRaises(RuntimeError) as e:
            outbound.reply_to_message(s, msg, 'Sure - the key is [redacted:aws-key]')
        self.assertIn('redacted', str(e.exception).lower())

    def test_an_ordinary_reply_is_not_blocked_by_the_guard(self):
        """The guard must not become a reason a normal reply cannot be sent - it fails LATER,
        on the missing mailbox, which is a different complaint entirely."""
        from taskuary import outbound
        s = MemoryStore()
        msg = {'Channel': 'email', 'ExternalId': 'x1', 'FromEmail': 'dana@example.com'}
        with self.assertRaises(RuntimeError) as e:
            outbound.reply_to_message(s, msg, 'Sure - I rotated it this morning.')
        self.assertNotIn('redacted', str(e.exception).lower())


# ── SSNs AND DATES OF BIRTH, through every door Taskuary itself sends by (the owner, 2026-11-25: "never sent to endpoints, even HIPAA AI")
# A front-desk mail of the shape a clinic gets: invented numbers from the never-issued ranges, an invented date, and a bare date that stays.
SSN, DOB = '666-12-3456', '04/05/1961'
INTAKE = (f'From Erin Blake: new resident intake. SSN {SSN}, DOB: {DOB}. Please book the first visit for 12/01/2026.')


def _hipaa_card(s):
    row = [c for c in s.list_connectors() if c['Type'] == 'anthropic'][0]
    s.save_connector({'ConnectorId': row['ConnectorId'], 'Secret': 'k', 'Active': 1, 'ConfigJson': '{}'}, 'o')
    s.set_setting('triage_ai', 'connector:anthropic', 't')


class NoSsnOrBirthDateLeavesTests(unittest.TestCase):
    def assertMasked(self, out):
        out = json.dumps(out, default=str) if not isinstance(out, str) else out
        self.assertNotIn(SSN, out); self.assertNotIn(DOB, out)
        self.assertIn('[redacted:ssn]', out); self.assertIn('[redacted:date-of-birth]', out)
        self.assertIn('12/01/2026', out, 'a bare date is not a birthday')

    def test_a_hosted_call(self):
        s, seen = MemoryStore(), {}
        _hipaa_card(s)
        def recorder(system, user, **kw): seen.update(system=system, user=user); return 'ok'
        with mock.patch.object(llm, 'make_llm', return_value=recorder): llm.build_llm(s)('You sort mail.', INTAKE)
        self.assertMasked(seen['user'])

    def test_every_step_of_an_api_agent_and_its_search(self):
        """apiagent.turn calls `brain.chat` - the HIPAA AI card's agent with hands - and that went past the wrapper's __call__ untouched:
        its prompt, his mail and every tool answer (a page it read) reached the gateway as they were."""
        from taskuary import apiagent
        s, seen = MemoryStore(), {}
        _hipaa_card(s)
        def recorder(system, user, **kw): return 'ok'
        def chat(messages, tools, max_tokens=100, **kw): seen['chat'] = messages; return {'role': 'assistant', 'content': 'done'}
        def search(q, max_tokens=100): seen['search'] = q; return 'hits'
        recorder.chat, recorder.search = chat, search
        with mock.patch.object(llm, 'make_llm', return_value=recorder):
            brain = llm.build_llm(s)
            self.assertTrue(apiagent.can(brain))
            got = apiagent.turn(brain, s, 1, 's1', 'You work tasks.', INTAKE, 100, tools=[])
        self.assertEqual(got, 'done')
        self.assertMasked(seen['chat'])
        brain.search(f'who has SSN {SSN}'); self.assertNotIn(SSN, seen['search'])
        bare = lambda system, user, **kw: 'ok'
        with mock.patch.object(llm, 'make_llm', return_value=bare): self.assertFalse(apiagent.can(llm.build_llm(s)), 'no chat is still no chat')

    def test_a_headless_cli_run(self):
        fed = []
        with mock.patch.object(agents, '_resolve_cmd', return_value=['claude']), \
             mock.patch.object(agents.spawn, 'popen', side_effect=lambda *a, **k: _FakeProc(fed)):
            agents.run_cli({'cmd': 'claude', 'args': ['-p']}, f'Work this task:\n{INTAKE}', lambda *a: None)
        self.assertMasked(fed[0])

    def test_a_kept_cli_conversation_and_an_acp_prompt(self):
        from taskuary import acp, clipool
        lv, wrote = object.__new__(clipool.Live), []
        lv.p = mock.Mock(); lv.p.stdin.write.side_effect = wrote.append
        lv._send(INTAKE)
        self.assertMasked(json.loads(wrote[0])['message']['content'])
        self.assertMasked(acp.blocks(INTAKE)[0]['text'])
        # ...a turn with a picture dropped on the box goes as parts: its words scrubbed, the picture and the parts' shape as they were
        pic = {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': 'iVBORw0KGgo'}}
        lv._send([pic, {'type': 'text', 'text': INTAKE}])
        sent = json.loads(wrote[1])['message']['content']
        self.assertEqual(sent[0], pic); self.assertMasked(sent[1]['text'])

    def test_a_line_typed_into_a_live_session(self):
        import threading
        got, done = [], threading.Event()
        class Chat:
            def send_prompt(self, text, brief=False): got.append(text)
        terminal.type_into(Chat(), INTAKE, done=lambda ok: done.set())
        self.assertTrue(done.wait(5)); self.assertMasked(got[0])

    def test_a_tool_answer(self):
        from taskuary import agenttools
        out = agenttools.rpc({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'read_message', 'arguments': {}}},
                             lambda name, args: INTAKE)
        self.assertMasked(out['result']['content'][0]['text'])

    def test_a_tool_answer_that_is_rows(self):
        """Round 5: an answer that is JSON - rows, each value under its key, a note whose lines are serialized - left with the SSN its key
        named and the one at a line's start."""
        from taskuary import agenttools
        rows = json.dumps({'rows': [{'name': 'Erin Blake', 'ssn': '078051120', 'dob': '010590', 'note': 'Erin Blake\n666-12-3456\nvisit 12/01/2026'}]}, indent=1)
        out = agenttools.rpc({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'run_system', 'arguments': {}}},
                             lambda name, args: rows)['result']['content'][0]['text']
        for raw in ('078051120', '010590', '666-12-3456'): self.assertNotIn(raw, out)
        self.assertEqual(json.loads(out)['rows'][0]['note'], 'Erin Blake\n[redacted:ssn]\nvisit 12/01/2026')

    def test_the_context_file_an_agent_reads_off_disk(self):
        from pathlib import Path
        from taskuary import context
        s = MemoryStore(); tid = s.create_task({'Title': 'intake', 'Kind': 'general', 'Status': 'open'}, 'owner')
        with mock.patch.object(context, 'build', return_value=f'## Messages\n{INTAKE}'): p = context.write(s, tid)
        self.assertMasked(Path(p).read_text(encoding='utf-8'))

    def test_what_a_session_reads_over_the_api_and_the_owner_still_sees_it_whole(self):
        from fastapi.testclient import TestClient
        from taskuary import config, guard, server
        srv = config.load()['server']
        s = MemoryStore(); tid = s.create_task({'Title': 'intake', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        mid = s.add_message({'TaskId': tid, 'ExternalId': 'x1', 'ConversationId': 'c1', 'Channel': 'email', 'FromName': 'Erin Blake',
                             'FromEmail': 'erin@northwind.example', 'Subject': 'Intake', 'BodyText': f'{INTAKE} Wifi password=bluefish17',
                             'Status': 'routed'})
        s._exec('UPDATE task SET TrustedThrough=? WHERE TaskId=?', (mid, tid))          # the owner vouched for her (agenttools.unvouched)
        with mock.patch.object(server, 'store', s):
            c = TestClient(server.app)
            agent = c.get(f'/api/agent/messages/{mid}', params={'task_id': tid},
                          headers={'X-Taskuary-Token': srv['agent_token'], guard.TASK_HDR: guard.task_proof(srv, tid)})
            owner = c.get(f'/api/messages/{mid}', headers={'X-Taskuary-Token': srv.get('token') or ''})
        # ...and still JSON: `password=` scrubbed over the answer's text took its closing quote with it
        self.assertEqual(agent.status_code, 200); self.assertMasked(agent.json()['body']); self.assertTrue(agent.json()['body'].endswith('password=[redacted:secret]'))
        self.assertEqual(owner.status_code, 200); self.assertIn(SSN, owner.text); self.assertIn(DOB, owner.text)
        self.assertIn(SSN, s.get_message(mid)['BodyText'], 'the store keeps his mail as it came')


# ── EVERY PART OF WHAT AN API CARD'S AGENT SENDS (the owner, 2026-11-26): a file the agent opens by itself, and the calls it made ─────────
def _card(s, t):
    row = [c for c in s.list_connectors() if c['Type'] == t][0]
    s.save_connector({'ConnectorId': row['ConnectorId'], 'Secret': 'k', 'Active': 1, 'ConfigJson': '{}'}, 'o')
    return f"connector:{row['ConnectorId']}"


def _call(i, name, **a): return {'id': f'c{i}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(a)}}


class EveryPartOfAnAgentsStepTests(unittest.TestCase):
    def _turn(self, card):
        """Its own loop on `card`: it opens the intake sheet in its task's folder, writes a note with the number in it, and answers.
        Returns (every list of messages a step sent, the sheet, the note)."""
        from pathlib import Path
        from taskuary import apiagent
        s, sent = MemoryStore(), []
        pick = _card(s, card)
        tid = s.create_task({'Title': 'intake', 'Kind': 'general', 'Status': 'open'}, 'owner')
        sheet = Path(apiagent.workdir(s, tid)) / 'intake.txt'; sheet.write_text(INTAKE, encoding='utf-8')
        steps = iter([[_call(1, 'file_read', path='intake.txt')], [_call(2, 'file_write', path='note.txt', text=f'Erin Blake, SSN {SSN}, born {DOB}')], None])
        def recorder(system, user, **kw): return 'ok'
        def chat(messages, tools, max_tokens=100, **kw):
            sent.append(json.loads(json.dumps(messages)))
            return {'role': 'assistant', 'content': None, 'tool_calls': c} if (c := next(steps)) else {'role': 'assistant', 'content': 'done'}
        recorder.chat = chat
        with mock.patch.object(llm, 'make_llm', return_value=recorder):
            brain = llm.build_llm(s, pick=pick, job='general', task_id=tid)
            self.assertEqual(apiagent.turn(brain, s, tid, 's1', 'You work tasks.', 'Read the intake sheet.', 100, tools=list(apiagent.FILES)), 'done')
        return sent, sheet, sheet.with_name('note.txt')

    def _masked_whole(self, card):
        sent, sheet, note = self._turn(card)
        self.assertEqual(len(sent), 3)
        read = [m for m in sent[1] if m.get('role') == 'tool'][0]['content']
        self.assertIn('[redacted:ssn]', read); self.assertIn('[redacted:date-of-birth]', read); self.assertIn('12/01/2026', read)
        wrote = json.loads([m for m in sent[2] if m.get('tool_calls')][-1]['tool_calls'][0]['function']['arguments'])     # ...still JSON, its path kept
        self.assertEqual(wrote['path'], 'note.txt'); self.assertIn('[redacted:ssn]', wrote['text'])
        for msgs in sent: self.assertNotIn(SSN, json.dumps(msgs)); self.assertNotIn(DOB, json.dumps(msgs))
        # ...and his files are as they were: the sheet it read, and the note written with what the agent gave, not with what was sent
        self.assertEqual(sheet.read_text(encoding='utf-8'), INTAKE)
        self.assertIn(SSN, note.read_text(encoding='utf-8')); self.assertIn(DOB, note.read_text(encoding='utf-8'))

    def test_on_the_hipaa_ai_card(self): self._masked_whole('hipaa_ai')
    def test_and_on_any_other_card_the_same(self): self._masked_whole('anthropic')          # one rule for every endpoint (2026-11-25)

    def test_a_tools_answer_held_inside_a_part_and_a_picture_beside_it(self):
        pic = {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': 'iVBORw0KGgo'}}
        held = {'type': 'tool_result', 'tool_use_id': 'c1', 'content': [{'type': 'text', 'text': INTAKE}]}
        out = redact.scrub_parts([pic, held, {'type': 'text', 'text': 'Booked.'}])
        self.assertEqual(out[0], pic); self.assertEqual(out[2], {'type': 'text', 'text': 'Booked.'})
        self.assertEqual(out[1]['tool_use_id'], 'c1'); self.assertNotIn(SSN, json.dumps(out)); self.assertNotIn(DOB, json.dumps(out))

    def test_what_a_backup_card_is_handed_when_the_first_brain_is_out(self):
        s, seen = MemoryStore(), {}
        first, backup = _card(s, 'anthropic'), _card(s, 'hipaa_ai')
        class Out(RuntimeError): unavailable = True
        def down(system, user, **kw): raise Out('resting')
        def up(system, user, **kw): seen['user'] = user; return 'ok'
        with mock.patch.object(llm, 'make_llm', side_effect=lambda t, *a, **k: up if t == 'hipaa_ai' else down):
            brain = llm._build_llm(s, first, backups=[backup], fallback_user=INTAKE)
            self.assertEqual(brain('You work tasks.', 'go on'), 'ok')
        self.assertNotIn(SSN, seen['user']); self.assertNotIn(DOB, seen['user']); self.assertIn('[redacted:ssn]', seen['user'])

    def test_the_search_a_card_runs_for_its_agent_on_a_cli(self):
        from taskuary import harness
        s, seen = MemoryStore(), {}
        def card(system, user, **kw): return 'ok'
        card.search = lambda q, max_tokens=100: seen.update(q=q) or 'hits'
        with mock.patch.object(harness, '_task_card', return_value={'ConnectorId': 1}), mock.patch.object(harness, '_cfg', return_value=('hipaa_ai', {}, 'k')), \
             mock.patch.object(llm, 'make_llm', return_value=card):
            self.assertEqual(harness.searcher(s, 1).search(f'who has SSN {SSN}'), 'hits')
        self.assertNotIn(SSN, seen['q'])


# ── WHAT A CARD'S HARNESS CLI SENDS (the owner, 2026-11-26): Codex or OpenCode reads a file with its own shell, and its next request carries it ──
CODE = 'gw-access-code-0001'
PICTURE = {'type': 'input_image', 'image_url': 'data:image/png;base64,iVBORw0KGgo'}


class _Answer:
    "The card's endpoint answering, in the pieces it sends."
    def __init__(self, chunks, status=200): self.chunks, self.status_code, self.closed = chunks, status, False
    headers = {'Content-Type': 'text/event-stream', 'Content-Length': '999', 'Set-Cookie': 'gw=1'}
    def iter_content(self, chunk_size=None): return iter(self.chunks)
    def close(self): self.closed = True


class TheCardHarnessRelayTests(unittest.TestCase):
    def _ask(self, body, path='responses', client=('127.0.0.1', 50000), auth=None, chunks=(b'ok',), headers=None, at='http://testserver'):
        "(the relay's answer, what the card's endpoint was sent - {} when nothing was, the card's id)"
        from fastapi.testclient import TestClient
        from taskuary import relay, server
        s, seen = MemoryStore(), {}
        cid = s.save_connector({'Type': 'hipaa_ai', 'Name': 'HIPAA AI', 'Secret': CODE, 'Active': 1,
                                'ConfigJson': json.dumps({'base_url': 'https://gateway.example/v1', 'model': 'hydrogen'})}, 't')
        def endpoint(method, url, **kw): seen.update(method=method, url=url, **kw); return _Answer(chunks)
        with mock.patch.object(server, 'store', s), mock.patch('requests.request', endpoint):
            r = TestClient(server.app, client=client, base_url=at).post(
                f'/relay/card-{cid}/{path}', content=body if isinstance(body, bytes) else json.dumps(body),
                headers={'Authorization': auth or f'Bearer {relay.token(server.cfg["server"], cid)}', 'Content-Type': 'application/json', **(headers or {})})
        return r, seen, cid

    def test_a_file_codex_opened_itself_goes_on_masked_and_its_calls_are_still_json(self):
        args = json.dumps({'command': ['cat', 'intake.txt'], 'why': f'Erin Blake, SSN {SSN}, password=chirp-pass'})
        body = {'model': 'hydrogen', 'stream': True, 'instructions': 'You are hydrogen.', 'input': [
            {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': 'Book her first visit.'}, PICTURE]},
            {'type': 'function_call', 'call_id': 'c1', 'name': 'shell', 'arguments': args},
            {'type': 'function_call_output', 'call_id': 'c1', 'output': INTAKE}]}
        r, seen, _ = self._ask(body)
        self.assertEqual(r.status_code, 200)
        self.assertEqual((seen['method'], seen['url']), ('POST', 'https://gateway.example/v1/responses'))       # the card's own address, nowhere else
        sent = seen['data'].decode('utf-8')
        self.assertNotIn(SSN, sent); self.assertNotIn(DOB, sent)
        went = json.loads(sent)['input']
        self.assertIn('[redacted:ssn]', went[2]['output']); self.assertIn('12/01/2026', went[2]['output'])       # ...a bare date is a visit, and stays
        self.assertEqual(json.loads(went[1]['arguments'])['command'], ['cat', 'intake.txt'])                    # still the JSON its call was
        self.assertEqual(went[0]['content'], body['input'][0]['content'])                                       # his words and the picture as they were
        # ...signed in to the endpoint with the card's own code, which the CLI never held - and none of the caller's own sign-ins ride on
        h = {k.lower(): v for k, v in seen['headers'].items()}
        self.assertEqual(h['authorization'], f'Bearer {CODE}'); self.assertNotIn('x-taskuary-token', h)
        self.assertIs(seen['allow_redirects'], False)

    def test_rows_a_cli_read_itself_leave_masked_by_their_keys_and_at_a_lines_start(self):
        """Round 5: a call's output that is JSON rode on as one string - "ssn": "078051120" by a rule for text, but a line-start SSN inside
        it (the letter n of its serialized newline before it) and a run-together date of birth left whole."""
        rows = json.dumps([{'name': 'Erin Blake', 'ssn': '078051120', 'dob': '010590', 'note': 'intake\n666-12-3456\nDOB\n01/05/1990'}])
        body = {'model': 'hydrogen', 'input': [{'type': 'function_call_output', 'call_id': 'c1', 'output': rows},
                                               {'type': 'function_call_output', 'call_id': 'c2', 'output': json.dumps(rows)}],
                'metadata': {'ssn': '666123456'}}
        _, seen, _ = self._ask(body)
        sent = seen['data'].decode('utf-8')
        for raw in ('078051120', '010590', '666-12-3456', '01/05/1990', '666123456'): self.assertNotIn(raw, sent)
        self.assertEqual(json.loads(json.loads(sent)['input'][0]['output'])[0]['name'], 'Erin Blake')            # ...still the JSON it was

    def test_and_what_opencode_sends_the_same(self):
        body = {'model': 'hydrogen', 'messages': [
            {'role': 'user', 'content': 'Book her first visit.'},
            {'role': 'assistant', 'content': None, 'tool_calls': [_call(1, 'read', filePath='intake.txt', note=f'born {DOB}')]},
            {'role': 'tool', 'tool_call_id': 'c1', 'content': INTAKE}]}
        _, seen, _ = self._ask(body, path='chat/completions')
        sent = seen['data'].decode('utf-8')
        self.assertEqual(seen['url'], 'https://gateway.example/v1/chat/completions')
        self.assertNotIn(SSN, sent); self.assertNotIn(DOB, sent)
        self.assertEqual(json.loads(json.loads(sent)['messages'][1]['tool_calls'][0]['function']['arguments'])['filePath'], 'intake.txt')

    def test_a_request_with_nothing_to_take_out_goes_as_the_bytes_it_came(self):
        raw = b'{"model": "hydrogen",  "input": "Book the visit for 12/01/2026."}'
        _, seen, _ = self._ask(raw)
        self.assertEqual(seen['data'], raw)

    def test_the_answer_streams_back_byte_for_byte(self):
        # ...split mid-character and mid-event, and saying a number of its own: the answer is the model's, handed on as it came
        chunks = (b'event: response.output_text.delta\ndata: {"delta":"Erin \xc3', b'\xa9 - ' + SSN.encode() + b'"}\n\n', b'event: response.completed\ndata: {}\n\n')
        r, _, _ = self._ask({'model': 'hydrogen', 'input': 'hello', 'stream': True}, chunks=chunks)
        self.assertEqual(r.content, b''.join(chunks))
        self.assertTrue(r.headers['content-type'].startswith('text/event-stream')); self.assertNotIn('gw=1', str(r.headers))

    def test_only_this_computer_and_only_the_cards_own_agent(self):
        from taskuary import relay, server
        body = {'model': 'hydrogen', 'input': INTAKE}
        for why, kw in (('another computer, with the right token', {'client': ('203.0.113.9', 50000)}),
                        ('no token of ours', {'auth': 'Bearer sk-guessed-0001'}),
                        ("the card's own code is not the relay's token", {'auth': f'Bearer {CODE}'}),
                        ("another card's token", {'auth': f'Bearer {relay.token(server.cfg["server"], 999)}'})):
            r, seen, _ = self._ask(body, **kw)
            self.assertEqual(r.status_code, 403, why); self.assertEqual(seen, {}, why)
        r, seen, cid = self._ask(body)
        self.assertEqual(r.status_code, 200); self.assertNotIn(relay.token(server.cfg['server'], cid), json.dumps(seen['headers']))

    def test_a_server_bound_to_one_address_and_no_loopback_still_answers_its_own_computer(self):
        # ...the harness is then pointed at that address (relay.base), and its call arrives FROM it - another computer on that network does not
        body = {'model': 'hydrogen', 'input': INTAKE}
        r, seen, _ = self._ask(body, client=('192.0.2.10', 50000), at='http://192.0.2.10:7787')
        self.assertEqual(r.status_code, 200); self.assertNotIn(SSN, seen['data'].decode('utf-8'))
        r, seen, _ = self._ask(body, client=('192.0.2.11', 50000), at='http://192.0.2.10:7787')
        self.assertEqual(r.status_code, 403); self.assertEqual(seen, {})

    def test_agents_streaming_at_once_never_hold_the_apps_own_threads(self):
        """A stream is held while its model thinks. More of them than the server's shared pool has threads (40), each on an endpoint that
        says nothing yet - and a plain read of the app still answers at once."""
        import threading, time
        from fastapi.testclient import TestClient
        from taskuary import relay, server
        N, s, go, lock, open_ = 45, MemoryStore(), threading.Event(), threading.Lock(), []
        cid = s.save_connector({'Type': 'hipaa_ai', 'Name': 'HIPAA AI', 'Secret': CODE, 'Active': 1,
                                'ConfigJson': json.dumps({'base_url': 'https://gateway.example/v1', 'model': 'hydrogen'})}, 't')
        class Thinking(_Answer):
            def iter_content(self, chunk_size=None):
                with lock: open_.append(1)
                go.wait(60); yield b'data: done\n\n'
        got, health = [], []
        with mock.patch.object(server, 'store', s), mock.patch('requests.request', lambda *a, **k: Thinking(())), \
             TestClient(server.app, client=('127.0.0.1', 50000)) as c:
            h = {'Authorization': f'Bearer {relay.token(server.cfg["server"], cid)}', 'Content-Type': 'application/json'}
            asks = [threading.Thread(target=lambda: got.append(c.post(f'/relay/card-{cid}/responses', content=b'{"input":"hello"}', headers=h).content), daemon=True)
                    for _ in range(N)]
            try:
                for t in asks: t.start()
                end = time.monotonic() + 20
                while len(open_) < N and time.monotonic() < end: time.sleep(0.05)
                t = threading.Thread(target=lambda: health.append(c.get('/api/health').status_code), daemon=True); t.start(); t.join(5)
                self.assertEqual(health, [200], f'the app waited on {len(open_)} streams')
                self.assertEqual(len(open_), N)
            finally:
                go.set()
                for t in asks: t.join(30)
        self.assertEqual(got, [b'data: done\n\n'] * N)

    def test_a_body_it_cannot_read_is_not_sent(self):
        r, seen, _ = self._ask(b'\x28\xb5\x2f\xfd packed', headers={'Content-Encoding': 'zstd'})
        self.assertEqual(r.status_code, 415); self.assertEqual(seen, {})
        r, seen, _ = self._ask({'input': INTAKE}, path='../admin/keys')
        self.assertNotEqual(r.status_code, 200); self.assertEqual(seen, {})


if __name__ == '__main__':
    unittest.main()
