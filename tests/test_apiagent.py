"""An API brain gets hands: Taskuary's browser and `show`, through its card's own function calling (apiagent.py).

A client on an API card alone - no CLI on the machine - asked its agent to sign in to a scheduling portal and read the denials, and was
told "logging in cannot be done from here - paste the claim information" (2026-11-09). The browser road was there; the API brain had
no way onto it.
"""
import json, unittest
from unittest import mock

from taskuary import apiagent, browserview as bv, llm
from taskuary.store import MemoryStore


class _R:
    def __init__(self, body, status=200): self.status_code, self._b, self.text = status, body, json.dumps(body)
    def json(self): return self._b


class TheCardTakesToolsTests(unittest.TestCase):
    def test_an_openai_compatible_card_sends_the_tools_and_hands_back_the_call(self):
        sent = []
        msg = {'role': 'assistant', 'content': None,
               'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {'name': 'browser_look', 'arguments': '{}'}}]}
        def post(url, headers, body, timeout): sent.append(body); return _R({'choices': [{'message': msg}]})
        brain = llm.make_llm('hipaa_ai', {'base_url': 'https://gateway.example', 'model': 'hipaa-ai'}, 'k')
        self.assertTrue(apiagent.can(brain))
        with mock.patch.object(llm, 'post_retrying', side_effect=post), mock.patch.object(llm.aiusage, 'openai'):
            got = brain.chat([{'role': 'user', 'content': 'look'}], apiagent.BROWSER)
        self.assertEqual(got['tool_calls'][0]['function']['name'], 'browser_look')
        self.assertEqual([t['function']['name'] for t in sent[0]['tools']][:2], ['browser_open', 'browser_look'])

    def test_a_brain_with_no_chat_step_is_not_offered_tools(self):
        self.assertFalse(apiagent.can(lambda system, user, **kw: 'hi'))


class OneRoundTripTests(unittest.TestCase):
    def test_the_model_calls_a_tool_hears_its_answer_and_answers_in_words(self):
        steps = iter([
            {'role': 'assistant', 'content': None,
             'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {'name': 'browser_open', 'arguments': '{"url": "portal.example"}'}}]},
            {'role': 'assistant', 'content': 'Three claims were denied.'}])
        heard = []
        class Brain:
            def __call__(self, *a, **kw): raise AssertionError('a looped turn never asks the plain way')
            def chat(self, msgs, tools, max_tokens, **kw): heard.append([dict(m) for m in msgs]); return next(steps)
        trace = []
        with mock.patch.object(apiagent, 'run_tool', return_value='PAGE https://portal.example/\n- button "Denials" [ref=e3]') as ran:
            said = apiagent.turn(Brain(), MemoryStore(), 1, 'sid-1', 'sys', 'go', 500, trace=lambda *e: trace.append(e))
        self.assertEqual(said, 'Three claims were denied.')
        ran.assert_called_once_with(mock.ANY, 1, 'sid-1', 'browser_open', {'url': 'portal.example'})
        self.assertEqual(heard[1][-1], {'role': 'tool', 'tool_call_id': 'c1', 'content': 'PAGE https://portal.example/\n- button "Denials" [ref=e3]'})
        self.assertEqual([e[0] for e in trace], ['tool_call', 'tool_result'])

    def test_a_failed_tool_is_told_to_the_model_not_raised(self):
        steps = iter([{'tool_calls': [{'id': 'c1', 'function': {'name': 'browser_click', 'arguments': '{"ref": "@e9"}'}}]},
                      {'content': 'The button was gone.'}])
        heard = []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): heard.append(list(msgs)); return next(steps)
        with mock.patch.object(apiagent, 'run_tool', side_effect=ValueError('no element @e9')):
            self.assertEqual(apiagent.turn(Brain(), MemoryStore(), 1, 's', 'sys', 'go', 500), 'The button was gone.')
        self.assertIn('no element @e9', heard[1][-1]['content'])

    def test_it_stops_at_its_step_bound_and_says_where_it_got(self):
        call = {'tool_calls': [{'id': 'c', 'function': {'name': 'browser_look', 'arguments': '{}'}}]}
        asked = []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): asked.append(kw); return {'content': 'Got to the list.'} if kw else call
        with mock.patch.object(apiagent, 'run_tool', return_value='PAGE'):
            self.assertEqual(apiagent.turn(Brain(), MemoryStore(), 1, 's', 'sys', 'go', 500, steps=3), 'Got to the list.')
        self.assertEqual(len(asked), 4)
        self.assertEqual(asked[-1], {'tool_choice': 'none'})

    def test_an_act_that_cannot_be_undone_is_held_not_run(self):
        held = {'hookSpecificOutput': {'permissionDecisionReason': 'Taskuary held this for the owner: submit the appeal'}}
        with mock.patch.object(bv, 'installed', return_value=True), \
             mock.patch('taskuary.browsergate.check', return_value=held), mock.patch('taskuary.browsergate._run') as ran:
            said = apiagent.run_tool(MemoryStore(), 1, 's', 'browser_click', {'ref': '@e4'})
        self.assertIn('held this for the owner', said)
        ran.assert_not_called()


class TheSessionTests(unittest.TestCase):
    """The general agent's turn on an API card: hands where it can call tools, the next real step as a question where it cannot."""

    def _turn(self, brain, installed=True, toolbox=()):
        from taskuary import general, llm as llm_mod
        s = MemoryStore()
        tid = s.create_task({'Title': 'Read the denials on the scheduling portal', 'Summary': 'go', 'Kind': 'general', 'Status': 'open'}, 'owner')
        session = general.GeneralSession(s, tid)
        session.pick, session.provider, session.model = 'connector:1', 'HIPAA AI', ''
        with mock.patch.object(llm_mod, 'build_llm', return_value=brain), mock.patch.object(bv, 'installed', return_value=installed), \
             mock.patch.object(bv, 'state', return_value={'open': False}), \
             mock.patch.object(apiagent, 'taskuary_tools', return_value=[apiagent._fn(n, n, apiagent._S({})) for n in toolbox]):
            session.send_prompt('log into the scheduling portal and read the denials', echo=False)
        return s, tid

    def test_a_card_that_takes_tools_runs_the_loop_with_the_browser_brief(self):
        seen = []
        class Brain:
            def __call__(self, *a, **kw): raise AssertionError('not the plain road')
            def chat(self, msgs, tools, max_tokens, **kw): seen.append((msgs[0]['content'], tools)); return {'content': 'Opened it.'}
        self._turn(Brain())
        system, tools = seen[0]
        self.assertIn(apiagent.BRIEF, system)
        self.assertIn('browser_open', [t['function']['name'] for t in tools])

    def test_a_sign_in_the_looped_agent_asks_for_goes_to_the_vault_road(self):
        # the agent never types a password: its marker raises signin.needs, which fills a saved vault login or asks the owner to
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): return {'content': 'The sign-in page is open.\n[[TASKUARY-SIGNIN: portal.example]]'}
        with mock.patch('taskuary.signin.needs') as needs: self._turn(Brain())
        self.assertEqual(needs.call_args[0][3], 'portal.example')

    def test_a_model_that_refuses_tools_is_asked_the_plain_way(self):
        seen = []
        class Brain:
            def __call__(self, system, user, **kw): seen.append(system); return 'Here is what I can do without a browser.'
            def chat(self, *a, **kw): raise RuntimeError('hipaa_ai error 400 at https://gateway.example: tools are not supported')
        self._turn(Brain())
        self.assertIn('THIS AI CANNOT DRIVE A BROWSER', seen[0])
        self.assertNotIn(apiagent.BRIEF, seen[0])

    def test_the_clis_toolbox_rides_with_the_browser(self):
        seen = []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): seen.append((msgs[0]['content'], [t['function']['name'] for t in tools])); return {'content': 'ok'}
        self._turn(Brain(), toolbox=('search_messages', 'propose_reply', 'show'))
        system, names = seen[0]
        self.assertIn(apiagent.TOOLS_BRIEF, system)
        self.assertEqual(names.count('show'), 1, "the server's show, never a second")
        self.assertTrue({'search_messages', 'propose_reply', 'browser_open'} <= set(names))

    def test_no_browser_but_a_toolbox_still_loops_and_says_set_the_browser_up(self):
        seen = []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): seen.append((msgs[0]['content'], [t['function']['name'] for t in tools])); return {'content': 'ok'}
        self._turn(Brain(), installed=False, toolbox=('search_messages',))
        system, names = seen[0]
        self.assertIn('NO BROWSER FOR AGENTS YET', system)
        self.assertNotIn('browser_open', names)

    def test_a_card_that_takes_no_tools_asks_for_the_next_real_step(self):
        seen = []
        def brain(system, user, **kw): seen.append(system); return 'I need a browser.\n[[TASKUARY-ASK]] Connect an agent with a browser?'
        s, tid = self._turn(brain)
        self.assertIn('THIS AI CANNOT DRIVE A BROWSER', seen[0])
        self.assertNotIn(apiagent.BRIEF, seen[0])

    def test_no_agent_browser_on_the_computer_says_set_it_up(self):
        seen = []
        class Brain:
            def __call__(self, system, user, **kw): seen.append(system); return 'The browser is not set up.'
            def chat(self, *a, **kw): raise AssertionError('no browser: no loop')
        self._turn(Brain(), installed=False)
        self.assertIn('NO BROWSER FOR AGENTS YET', seen[0])


class TheToolboxTests(unittest.TestCase):
    """Taskuary's own tools reach an API brain through the SAME server a CLI session's MCP does - its token and task proof, its gates."""

    def test_the_listing_is_the_servers_with_the_sessions_headers_and_a_gateway_safe_schema(self):
        sent = []
        def post(url, json, headers, timeout):
            sent.append((url, json, headers))
            return _R({'jsonrpc': '2.0', 'id': 1, 'result': {'tools': [{'name': 'search_messages', 'description': 'Search saved mail.',
                       'inputSchema': {'type': 'object', 'additionalProperties': False, 'properties': {'words': {'type': 'string', 'default': ''}}}}]}})
        got = apiagent.taskuary_tools(7, 'sid-7', post=post)
        url, body, h = sent[0]
        self.assertIn('/api/mcp?task=7', url); self.assertEqual(body['method'], 'tools/list')
        from taskuary import guard
        self.assertIn('X-Taskuary-Token', h); self.assertIn(guard.TASK_HDR, h)
        self.assertEqual(got[0]['function']['parameters'], {'type': 'object', 'properties': {'words': {'type': 'string'}}})

    def test_a_property_named_like_a_dropped_key_is_kept(self):
        # a gateway's Gemini refused the whole turn: "required fields ['title'] are not defined" once `title` the FIELD was cut (2026-11-09)
        got = apiagent._clean({'type': 'object', 'title': 'x', 'properties': {'title': {'type': 'string', 'title': 'T'}}, 'required': ['title']})
        self.assertEqual(got, {'type': 'object', 'properties': {'title': {'type': 'string'}}, 'required': ['title']})

    def test_a_refusal_from_the_server_is_the_models_to_read(self):
        def post(url, json, headers, timeout):
            return _R({'jsonrpc': '2.0', 'id': 1, 'result': {'content': [{'type': 'text', 'text': 'only proposed - the owner presses Send'}], 'isError': True}})
        with self.assertRaises(ValueError) as e: apiagent.call_taskuary(7, 's', 'propose_reply', {'text': 'hi'}, post=post)
        self.assertIn('owner presses Send', str(e.exception))

    def test_a_tool_the_turn_was_not_offered_is_not_run(self):
        apiagent.TOOLBOX[(9, 's')] = {'search_messages'}
        try:
            with mock.patch.object(apiagent, 'call_taskuary') as called:
                with self.assertRaises(ValueError): apiagent.run_tool(MemoryStore(), 9, 's', 'merge_pr', {})
                apiagent.run_tool(MemoryStore(), 9, 's', 'search_messages', {'words': 'x'})
            called.assert_called_once()
        finally: apiagent.TOOLBOX.pop((9, 's'), None)

    def test_a_strangers_task_gets_its_tools_and_no_browser(self):
        with mock.patch.object(apiagent, 'taskuary_tools', return_value=[apiagent._fn('remind', 'r', apiagent._S({}))]) as listed:
            names = [t['function']['name'] for t in apiagent.tools_for(11, 's', browser=True, stranger=True)]
        self.assertEqual(listed.call_args.kwargs['stranger'], True)
        self.assertNotIn('browser_open', names)
        with self.assertRaises(ValueError): apiagent.run_tool(MemoryStore(), 11, 's', 'browser_open', {'url': 'portal.example'})
        apiagent.STRANGERS.discard((11, 's')); apiagent.TOOLBOX.pop((11, 's'), None)


if __name__ == '__main__': unittest.main()
