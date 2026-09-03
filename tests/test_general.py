"""General work: assistant-ui and xterm are two renderers of one persistent session."""
import json
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import browserview, general, handbook, llm, server, terminal, waitroom
from taskuary.store import MemoryStore


def general_task(store, kind='general'):
    return store.create_task({'Title': 'Plan the customer launch', 'Summary': 'Compare the three options',
                              'Kind': kind, 'Status': 'open'}, 'owner')


def connect_openai(store):
    row = store.get_connector_by_type('openai')
    store.save_connector({'ConnectorId': row['ConnectorId'], 'Active': 1, 'Secret': 'sk-test',
                          'Name': 'Work model', 'ConfigJson': '{"model":"gpt-test"}'}, 'owner')
    return row['ConnectorId']


class SharedSessionTests(unittest.TestCase):
    def test_setup_walkthrough_uses_a_tool_cli_and_starts_its_own_browser(self):
        store = MemoryStore()
        store.upsert_agent('my-claude', 'coding', 'cli', json.dumps({
            'cmd': 'claude', 'args': ['-p', '--dangerously-skip-permissions']}))
        cid = connect_openai(store)
        store.set_setting('assistant_ai', f'connector:{cid}', 'owner')
        tid = store.create_task({'Title': 'Connect Zoho', 'Summary': 'Walk me through Zoho Invoice',
                                 'Kind': 'general', 'Status': 'open', 'Source': 'assistant',
                                 'SourceRef': 'assistant:setup', 'Tags': browserview.WANTS}, 'owner')
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(general.threading, 'Thread') as thread:
            session = general.start_session(store, tid)
        self.assertEqual(session.pick, 'cli:my-claude')     # the saved API chat cannot drive a browser
        self.assertIs(thread.call_args.kwargs['target'], browserview.start)
        self.assertEqual(thread.call_args.kwargs['args'], (session.sid,))

    def test_setup_cli_gets_the_same_visible_browser_without_a_checkout(self):
        store = MemoryStore()
        store.upsert_agent('my-claude', 'coding', 'cli', json.dumps({
            'cmd': 'claude', 'args': ['-p', '--dangerously-skip-permissions']}))
        tid = store.create_task({'Title': 'Connect Zoho', 'Summary': 'Walk me through Zoho Invoice',
                                 'Kind': 'general', 'Status': 'open', 'SourceRef': 'assistant:setup',
                                 'Tags': browserview.WANTS}, 'owner')
        seen = {}
        def answer(system, user, **kwargs):
            seen.update(system=system, user=user, kwargs=kwargs); return 'Zoho is open beside us.'
        session = general.GeneralSession(store, tid, pick='cli:my-claude')
        with mock.patch.object(browserview, 'start', return_value=True), \
             mock.patch.object(llm, 'build_llm', return_value=answer) as build:
            session.send_prompt('Open Zoho', pick='cli:my-claude')
        self.assertTrue(build.call_args.kwargs['cli_tools'])
        env = build.call_args.kwargs['extra_env']
        self.assertEqual(env['AGENT_BROWSER_SESSION'], browserview.session_name(session.sid))
        self.assertEqual(env['TASKUARY_TASK'], str(tid))
        self.assertIn('TASKUARY_URL', env)
        self.assertIn('NEVER use --session, --headed', seen['system'])

    def test_browser_walkthrough_cli_keeps_tools_in_scratch_and_receives_session_env(self):
        store = MemoryStore()
        store.upsert_agent('my-claude', 'coding', 'cli', json.dumps({
            'cmd': 'claude', 'args': ['-p', '--dangerously-skip-permissions']}))
        seen = {}
        def run_cli(profile, prompt, trace, resume=None, **kwargs):
            seen.update(profile=profile, kwargs=kwargs); return 'done', None, None
        with mock.patch('taskuary.agents.run_cli', side_effect=run_cli):
            brain = llm.make_cli_llm(store, 'my-claude', cli_tools=True,
                                     extra_env={'AGENT_BROWSER_SESSION': 'tq-one'})
            brain('system', 'user')
        self.assertIn('--dangerously-skip-permissions', seen['profile']['args'])
        self.assertNotIn('--tools', seen['profile']['args'])
        self.assertTrue(str(seen['profile']['cwd']).endswith('scratch'))
        self.assertEqual(seen['kwargs']['extra_env']['AGENT_BROWSER_SESSION'], 'tq-one')

    def test_closing_the_walkthrough_closes_its_browser_once(self):
        store = MemoryStore(); tid = general_task(store)
        session = general.GeneralSession(store, tid)
        with mock.patch.object(handbook, 'enabled', return_value=False), \
             mock.patch.object(browserview, 'close') as close:
            session.close(); session.close()
        close.assert_called_once_with(session.sid)

    def test_native_api_is_the_fast_default_when_assistant_choice_is_blank(self):
        store = MemoryStore()
        store.upsert_agent('my-codex', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
        cid = connect_openai(store)
        store.set_setting('assistant_ai', '', 'owner')
        pick, _label, model = general._selected(store)
        self.assertEqual((pick, model), (f'connector:{cid}', 'gpt-test'))

    def test_assistant_reads_relevant_company_knowledge_from_hub(self):
        store = MemoryStore(); tid = general_task(store)
        handbook.post(store, 'Customer launches need operations approval',
                      'Ask the operations owner before fixing the date.', 'customer-launch',
                      'decision', 'coder')
        _system, user = general._prompt(store, tid)
        self.assertIn('FROM HUB', user)
        self.assertIn('Customer launches need operations approval', user)
        self.assertNotIn('taskuary --upvote', user)  # an API assistant has no shell for this

    def test_cli_assistant_is_told_to_file_nontechnical_company_knowledge(self):
        store = MemoryStore(); tid = general_task(store)
        store.upsert_agent('my-codex', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
        seen = {}
        def answer(system, user, **kwargs):
            seen['system'] = system
            return 'The launch plan is ready.'
        # start_session REGISTERS the session in terminal.SESSIONS (process-wide) - left there, a live
        # fake on task 1 made every later test that looks a session up by task id find this one
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=answer):
            session = general.start_session(store, tid, pick='cli:my-codex')
            session.send_prompt('Plan the launch')
        self.assertIn('Hub is a high-signal commons', seen['system'])
        self.assertIn('substantial investigation', seen['system'])
        self.assertIn('taskuary --learned', seen['system'])

    def test_ending_an_assistant_session_mines_the_conversation_for_hub_once(self):
        store = MemoryStore(); tid = general_task(store)
        store.add_comment(tid, 'owner', general.USER_TYPE, 'Who approves customer launches?')
        store.add_comment(tid, 'assistant', general.ASSISTANT_TYPE,
                          'Operations approves every customer launch before a date is promised.')
        session = general.GeneralSession(store, tid)
        brain = mock.Mock(return_value=json.dumps({'entries': [{
            'earned': True,
            'why_earned': 'The conversation compared launch ownership and worked through the commitment risk.',
            'title': 'Operations approves customer launch dates',
            'topic': 'customer-launch', 'kind': 'people',
            'body': 'Ask operations before promising a date.',
        }]}))
        with mock.patch.object(llm, 'build_llm', return_value=brain) as build:
            session.close()
            session.close()
        build.assert_called_once()
        self.assertEqual(brain.call_count, 1)
        prompt = brain.call_args.args[1]
        self.assertIn('OWNER: Who approves customer launches?', prompt)
        self.assertIn('ASSISTANT: Operations approves every customer launch', prompt)
        posts = store.lore_posts()
        self.assertEqual([(p['Title'], p['Author'], p['TaskId']) for p in posts],
                         [('Operations approves customer launch dates', 'assistant', tid)])

    def test_api_assistant_can_publish_a_hub_idea_without_showing_the_marker(self):
        store = MemoryStore(); tid = general_task(store)
        cid = connect_openai(store)
        payload = {'earned': True,
                   'why_earned': 'We compared the customer failure modes and developed a concrete operating model.',
                   'topic': 'customer-launch', 'kind': 'new_idea',
                   'title': 'Give every launch a reversible dry-run',
                   'body': 'A dry-run catches ownership gaps before a customer date is committed.'}
        answer = mock.Mock(return_value='I saved the developed idea to the Hub.\n<TASKUARY-HUB>'
                                       + json.dumps(payload) + '</TASKUARY-HUB>')
        with mock.patch.object(llm, 'build_llm', return_value=answer):
            session = general.GeneralSession(store, tid, connector_id=cid)
            visible = session.send_prompt('Put that idea in the Hub')
        self.assertEqual(visible, 'I saved the developed idea to the Hub.')
        self.assertEqual([(p['Title'], p['Kind'], p['Author']) for p in store.lore_posts()],
                         [('Give every launch a reversible dry-run', 'new_idea', 'assistant')])

    def test_ending_an_assistant_session_respects_social_being_off(self):
        store = MemoryStore(); tid = general_task(store)
        store.add_comment(tid, 'owner', general.USER_TYPE, 'Remember this company fact.')
        store.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The fact.')
        session = general.GeneralSession(store, tid)
        with mock.patch.object(handbook, 'enabled', return_value=False), \
             mock.patch.object(handbook, 'learn_from_session') as learn:
            session.close()
        learn.assert_not_called()

    def test_configured_cli_login_is_a_first_class_assistant_provider(self):
        store = MemoryStore(); tid = general_task(store)
        store.upsert_agent('my-codex', 'coding', 'cli', json.dumps({'cmd': 'codex', 'model': 'gpt-test'}))
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(llm, 'build_llm', return_value=lambda *a, **k: 'Done through the CLI.') as build:
            session = general.start_session(store, tid, pick='cli:my-codex')
            reply = session.send_prompt('Research this', pick='cli:my-codex')
        self.assertEqual(reply, 'Done through the CLI.')
        self.assertEqual((session.pick, session.model), ('cli:my-codex', 'gpt-test'))
        self.assertIn('your CLI', session.provider)
        self.assertEqual(build.call_args.kwargs['pick'], 'cli:my-codex')

    def test_one_session_persists_chat_and_exposes_the_terminal_contract(self):
        store = MemoryStore(); tid = general_task(store); cid = connect_openai(store)
        seen = {}
        def fake_brain(system, user, **kwargs):
            seen.update(system=system, user=user, kwargs=kwargs)
            return 'Here is the launch plan.'
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=fake_brain):
            session = general.start_session(store, tid, cid)
            reply = session.send_prompt('Make a concise plan')
            same = general.start_session(store, tid, cid)
            self.assertIs(terminal.SESSIONS[session.sid], session)
        self.assertIs(session, same)
        self.assertEqual(reply, 'Here is the launch plan.')
        self.assertIn('Make a concise plan', seen['user'])
        self.assertEqual([m['role'] for m in general.history(store, tid)], ['user', 'assistant'])
        info = session.info()
        self.assertEqual((info['mode'], info['connector_id'], info['model']), ('assistant', cid, 'gpt-test'))
        self.assertTrue(all(hasattr(session, name) for name in ('write', 'scrollback', 'waiting', 'subscribe', 'files')))

    def test_source_message_and_its_attachment_ride_into_the_general_agent(self):
        store = MemoryStore(); tid = general_task(store)
        mid = store.add_message({'ExternalId': 'attached-email', 'Channel': 'email',
                                 'Subject': 'Complete the form', 'FromName': 'Mindy',
                                 'BodyText': 'Please fill out the attached PAM form.'})
        store.attach_message(mid, tid)
        store.upsert_agent('my-codex', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
        seen = {}
        with TemporaryDirectory() as tmp:
            image = Path(tmp) / 'pam.png'; image.write_bytes(b'\x89PNG\r\n\x1a\nproof')
            store.add_attachment({'MessageId': mid, 'Name': 'pam.png', 'Path': str(image),
                                  'ContentType': 'image/png', 'Size': image.stat().st_size})
            def answer(system, user, **kwargs):
                seen.update(user=user, kwargs=kwargs)
                return 'I have the email and its form.'
            with mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
                 mock.patch.object(llm, 'build_llm', return_value=answer):
                session = general.start_session(store, tid, pick='cli:my-codex')
                session.send_prompt('Take this task', pick='cli:my-codex')
        self.assertIn('Please fill out the attached PAM form.', seen['user'])
        self.assertIn('pam.png', seen['user'])
        self.assertIn(str(image.resolve()), seen['user'])
        self.assertEqual(len(seen['kwargs']['images']), 1)

    def test_terminal_input_adds_to_the_same_conversation(self):
        store = MemoryStore(); tid = general_task(store); connect_openai(store)
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(llm, 'build_llm', return_value=lambda *a, **k: 'Done from terminal.'):
            session = general.start_session(store, tid)
            session.write('Do this from xterm\r')
            limit = time.time() + 2
            while len(general.history(store, tid)) < 2 and time.time() < limit: time.sleep(.02)
        self.assertEqual([m['role'] for m in general.history(store, tid)], ['user', 'assistant'])
        self.assertIn('Done from terminal.', session.scrollback())

    def test_session_state_keeps_busy_and_the_live_tool_trace_for_a_returning_view(self):
        store = MemoryStore(); tid = general_task(store)
        store.upsert_agent('my-claude', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        entered, release = threading.Event(), threading.Event()

        def fake_build(*args, trace=None, **kwargs):
            def brain(system, user, **brain_kwargs):
                trace('tool_call', 'WebSearch', {'tool_call_id': 'search-1', 'args': {'query': 'competitors'}})
                entered.set(); release.wait(5)
                trace('tool_result', 'search-1', {'result': 'three sources', 'is_error': False})
                return 'Here is the comparison.'
            return brain

        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(llm, 'build_llm', side_effect=fake_build):
            session = general.start_session(store, tid, pick='cli:my-claude')
            worker = threading.Thread(target=lambda: session.send_prompt('Compare them'), daemon=True)
            worker.start(); self.assertTrue(entered.wait(2))
            live = session.info()
            self.assertTrue(live['busy'])
            self.assertEqual([e['type'] for e in live['trace']], ['start', 'tool_call'])
            release.set(); worker.join(5)
        finished = session.info()
        self.assertFalse(finished['busy'])
        self.assertEqual([e['type'] for e in finished['trace']], ['start', 'tool_call', 'tool_result'])
        self.assertGreater(finished['trace_revision'], live['trace_revision'])

    def test_an_owner_started_conversation_does_not_close_itself_after_answering(self):
        store = MemoryStore(); tid = general_task(store)
        session = general.GeneralSession(store, tid)
        session.pick, session.provider = 'cli:coder', 'coder'
        answer = 'Here is the comparison.\n[[TASKUARY-DONE]] Finished the comparison.'
        with mock.patch.object(llm, 'build_llm', return_value=lambda *a, **k: answer), \
             mock.patch.object(session, '_close_out') as close:
            self.assertEqual(session.send_prompt('Compare them'), 'Here is the comparison.')
        close.assert_not_called()
        self.assertNotEqual(store.get_task(tid)['Status'], 'done')

    def test_source_backed_work_can_still_close_after_answering(self):
        store = MemoryStore(); tid = general_task(store)
        mid = store.add_message({'ExternalId': 'source-backed', 'Channel': 'email',
                                 'Subject': 'Please compare these', 'BodyText': 'Compare them'})
        store.attach_message(mid, tid)
        session = general.GeneralSession(store, tid)
        session.pick, session.provider = 'cli:coder', 'coder'
        answer = 'Here is the comparison.\n[[TASKUARY-DONE]] Finished the comparison.'
        timer = mock.Mock()
        with mock.patch.object(llm, 'build_llm', return_value=lambda *a, **k: answer), \
             mock.patch.object(general.threading, 'Timer', return_value=timer) as make_timer:
            session.send_prompt('Compare them')
        make_timer.assert_called_once()
        timer.start.assert_called_once()


class GeneralApiTests(unittest.TestCase):
    def test_switching_agent_modes_closes_the_existing_general_session(self):
        store = MemoryStore(); tid = general_task(store)
        session = general.GeneralSession(store, tid)
        with mock.patch.object(server, 'store', store), \
             mock.patch.dict(terminal.SESSIONS, {session.sid: session}, clear=True), \
             mock.patch.object(handbook, 'enabled', return_value=False):
            response = TestClient(server.app).patch(f'/api/tasks/{tid}', json={'Kind': 'coding'})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(session.alive)
            self.assertNotIn(session.sid, terminal.SESSIONS)
        self.assertEqual(store.get_task(tid)['Kind'], 'coding')

    def test_one_click_turns_the_discussion_into_a_daily_agent_prompt(self):
        store = MemoryStore(); tid = general_task(store)
        store.upsert_agent('my-claude', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        store.add_comment(tid, 'owner', general.USER_TYPE, 'Research the facilities and cite every source.')
        store.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'I compared the current sources and listed the gaps.')
        made = json.dumps({'title': 'Facility ownership watch',
                           'prompt': 'Research current facility ownership changes; cite sources and flag gaps.'})
        with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(llm, 'build_llm', return_value=lambda *a, **k: made):
            response = TestClient(server.app).post(f'/api/tasks/{tid}/assistant/report',
                                                   json={'pick': 'cli:my-claude'})
        self.assertEqual(response.status_code, 200)
        src = store.get_source(response.json()['sourceId'])
        cfg = json.loads(src['ConfigJson'])
        self.assertEqual((src['Channel'], src['Active'], cfg['type']), ('report', 1, 'agent'))
        self.assertEqual((cfg['agent'], cfg['daily_at'], cfg['origin_task_id']), ('my-claude', '08:00', tid))
        self.assertIn('current facility ownership', cfg['prompt'])
        self.assertEqual(response.json()['mode'], 'prompt')
        self.assertTrue(any('Created daily recurring report' in c['Body'] for c in store.list_comments(tid)))

    def test_a_long_reusable_workflow_is_saved_as_a_provider_neutral_skill(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        store = MemoryStore(); tid = general_task(store)
        store.upsert_agent('my-claude', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        store.add_comment(tid, 'owner', general.USER_TYPE, 'Build the full recurring review.')
        store.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Done, with sources and a stable structure.')
        made = json.dumps({'title': 'Deep operations review', 'prompt': 'Check the current systems.\n' + ('Detailed step. ' * 250)})
        with TemporaryDirectory() as tmp, mock.patch('taskuary.config.home', return_value=Path(tmp)), \
             mock.patch.object(server, 'store', store), mock.patch.object(llm, 'build_llm', return_value=lambda *a, **k: made):
            response = TestClient(server.app).post(f'/api/tasks/{tid}/assistant/report', json={'pick': 'cli:my-claude'})
            cfg = response.json()['config']
            skill = Path(tmp) / 'skills' / cfg['skill'] / 'SKILL.md'
            self.assertTrue(skill.is_file())
            self.assertIn('Detailed step.', skill.read_text(encoding='utf-8'))
        self.assertEqual(response.json()['mode'], 'skill')
        self.assertEqual(cfg['prompt'], "Run this workflow with current information and produce today's report.")

    def test_report_still_gets_an_editable_prompt_when_model_selection_fails(self):
        store = MemoryStore(); tid = general_task(store)
        store.upsert_agent('my-claude', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        store.add_comment(tid, 'owner', general.USER_TYPE, 'Check this every weekday.')
        store.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'I checked it and cited the result.')
        with mock.patch.object(server, 'store', store), \
             mock.patch.object(llm, 'build_llm', side_effect=RuntimeError('provider unavailable')):
            response = TestClient(server.app).post(f'/api/tasks/{tid}/assistant/report',
                                                   json={'pick': 'cli:my-claude'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('original requests to preserve', response.json()['config']['prompt'].lower())

    def test_stream_exposes_cli_work_before_the_final_answer(self):
        store = MemoryStore(); tid = general_task(store)
        store.upsert_agent('my-claude', 'coding', 'cli', json.dumps({'cmd': 'claude'}))

        def fake_build(*args, trace=None, cancel=None, **kwargs):
            def brain(system, user, **brain_kwargs):
                trace('tool_call', 'WebSearch', {'tool_call_id': 'tool-1', 'args': {'query': 'medical facilities'}})
                trace('tool_result', 'tool-1', {'result': 'three sources', 'is_error': False})
                trace('progress', 'text', 'Comparing the sources')
                return 'Here is the researched answer.'
            return brain

        with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(llm, 'build_llm', side_effect=fake_build):
            response = TestClient(server.app).post(f'/api/tasks/{tid}/assistant/stream',
                json={'text': 'Research this', 'pick': 'cli:my-claude'})
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual(response.headers['content-type'].split(';')[0], 'application/x-ndjson')
        self.assertEqual([e['type'] for e in events],
                         ['start', 'tool_call', 'tool_result', 'progress', 'done'])
        self.assertEqual(events[-1]['reply'], 'Here is the researched answer.')
        self.assertEqual([m['role'] for m in events[-1]['payload']['messages']], ['user', 'assistant'])

    def test_api_accepts_the_existing_cli_agent_connection(self):
        store = MemoryStore(); tid = general_task(store)
        store.upsert_agent('my-claude', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(llm, 'build_llm', return_value=lambda *a, **k: 'CLI answer'):
            out = TestClient(server.app).post(f'/api/tasks/{tid}/assistant/messages',
                                               json={'text': 'Plan it', 'pick': 'cli:my-claude'}).json()
        self.assertEqual(out['reply'], 'CLI answer')
        self.assertEqual(out['session']['pick'], 'cli:my-claude')

    def test_api_starts_and_resumes_the_same_session(self):
        store = MemoryStore(); tid = general_task(store, 'research'); cid = connect_openai(store)
        with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(llm, 'build_llm', return_value=lambda *a, **k: 'Research result'):
            client = TestClient(server.app)
            first = client.post(f'/api/tasks/{tid}/assistant/session', json={'connector_id': cid}).json()
            sent = client.post(f'/api/tasks/{tid}/assistant/messages', json={'text': 'Research this', 'connector_id': cid}).json()
            resumed = client.get(f'/api/tasks/{tid}/assistant').json()
        self.assertEqual(first['session']['sid'], sent['session']['sid'])
        self.assertEqual(sent['session']['sid'], resumed['session']['sid'])
        self.assertEqual(sent['reply'], 'Research result')
        self.assertEqual(len(resumed['messages']), 2)

    def test_coding_task_cannot_accidentally_start_the_general_assistant(self):
        store = MemoryStore(); tid = general_task(store, 'coding')
        with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            self.assertEqual(TestClient(server.app).post(f'/api/tasks/{tid}/assistant/session', json={}).status_code, 422)

    def test_wall_wrap_closes_general_work_without_a_coder_report(self):
        store = MemoryStore(); tid = general_task(store); connect_openai(store)
        with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(llm, 'build_llm', return_value=lambda *a, **k: 'The finished plan'):
            session = general.start_session(store, tid); session.send_prompt('Finish the plan')
            result = TestClient(server.app).post(f'/api/tasks/{tid}/wrap', json={'close': True}).json()
        self.assertEqual((result['wrap'], result['report']), ('done', 'The finished plan'))
        self.assertEqual(store.get_task(tid)['Status'], 'done')
        self.assertFalse(any(str(c['Body']).startswith('CODER REPORT') for c in store.list_comments(tid)))


class GeneralWaitroomTests(unittest.TestCase):
    def test_a_general_note_reopens_the_assistant_not_a_coding_cli(self):
        store = MemoryStore(); tid = general_task(store); connect_openai(store)
        fake = mock.Mock(); fake.send_prompt = mock.Mock()
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(general, 'start_session', return_value=fake) as start, \
             mock.patch.object(terminal, 'start_on_task') as coding:
            out = waitroom.add(store, tid, 'Compare the competitors')
            time.sleep(.05)
        self.assertEqual((out['state'], out['delivered']), ('restarted', 1))
        start.assert_called_once(); coding.assert_not_called(); fake.send_prompt.assert_called_once()


if __name__ == '__main__': unittest.main()
