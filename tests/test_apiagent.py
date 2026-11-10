"""An API brain gets hands: Taskuary's browser and `show`, through its card's own function calling (apiagent.py).

A client on an API card alone - no CLI on the machine - asked its agent to sign in to a scheduling portal and read the denials, and was
told "logging in cannot be done from here - paste the claim information" (2026-11-09). The browser road was there; the API brain had
no way onto it.
"""
import json, unittest
from pathlib import Path
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

    def test_the_next_turn_is_a_turn_of_the_same_conversation(self):
        "What it called and what came back is still in front of it: every turn was one system and one user message."
        steps = iter([{'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {'name': 'browser_look', 'arguments': '{}'}}]},
                      {'role': 'assistant', 'content': 'Three claims were denied.'}, {'role': 'assistant', 'content': "The second is Gail's."}])
        heard, kept = [], []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): heard.append([dict(m) for m in msgs]); return next(steps)
        with mock.patch.object(apiagent, 'run_tool', return_value='PAGE denials: 3') as ran, mock.patch.object(llm, 'vision_safe', lambda ct, b: b):
            apiagent.turn(Brain(), MemoryStore(), 1, 's', 'sys one', 'the whole task', 500, history=kept, images=[('image/png', 'AAAA')])
            said = apiagent.turn(Brain(), MemoryStore(), 1, 's', 'sys two', "which is Gail's?", 500, history=kept)
        self.assertEqual(said, "The second is Gail's."); ran.assert_called_once()
        self.assertEqual([m['role'] for m in heard[2]], ['system', 'user', 'assistant', 'tool', 'assistant', 'user'])
        self.assertEqual([heard[2][i]['content'] for i in (0, 1, 3, 4, 5)],
                         ['sys two', 'the whole task', 'PAGE denials: 3', 'Three claims were denied.', "which is Gail's?"])
        self.assertIsInstance(heard[0][1]['content'], list, 'the picture went with the turn it was sent on - and is not carried')
        self.assertEqual([m['role'] for m in kept], ['user', 'assistant', 'tool', 'assistant', 'user', 'assistant'])

    def test_a_carried_conversation_turned_down_on_the_first_call_is_lost_not_tools_refused(self):
        kept = [{'role': 'user', 'content': 'the whole task'}, {'role': 'assistant', 'content': 'Done.'}]
        class Brain:
            def chat(self, *a, **kw): raise RuntimeError('gateway error 400 at https://gateway.example: too many tokens')
        with self.assertRaises(apiagent.Lost): apiagent.turn(Brain(), MemoryStore(), 1, 's', 'sys', 'and now?', 500, history=kept)
        self.assertEqual(len(kept), 2)
        with self.assertRaises(apiagent.ToolsRefused): apiagent.turn(Brain(), MemoryStore(), 1, 's', 'sys', 'go', 500, history=[])
        stop = __import__('threading').Event(); stop.set()
        with self.assertRaisesRegex(RuntimeError, 'stopped'): apiagent.turn(Brain(), MemoryStore(), 1, 's', 'sys', 'no - the July one', 500, history=kept, cancel=stop)
        self.assertEqual(kept[-1], {'role': 'user', 'content': 'no - the July one'}, 'stopped before an answer, the line was still said')

    def test_a_turn_that_ends_part_way_keeps_what_it_did_with_every_call_answered(self):
        two = {'tool_calls': [{'id': k, 'function': {'name': 'browser_look', 'arguments': '{}'}} for k in 'ab']}
        kept, n = [], iter(range(9))
        class Brain:
            def chat(self, *a, **kw): return two
        def trace(kind, name, detail):
            if kind == 'tool_result' and next(n): raise RuntimeError('stopped')
        with mock.patch.object(apiagent, 'run_tool', return_value='PAGE'), self.assertRaises(RuntimeError):
            apiagent.turn(Brain(), MemoryStore(), 1, 's', 'sys', 'go', 500, history=kept, trace=trace)
        self.assertEqual([(m['role'], m.get('tool_call_id'), m.get('content')) for m in kept[2:]],
                         [('tool', 'a', 'PAGE'), ('tool', 'b', 'no answer - the turn ended first')])

    def test_nothing_counts_its_steps_and_only_going_in_circles_ends_it(self):
        "It stopped at 24 tool calls and said where it got - an agent at work is never ended for running long."
        look = {'tool_calls': [{'id': 'c', 'function': {'name': 'browser_look', 'arguments': '{}'}}]}
        asked, n = [], iter(range(999))
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): asked.append(kw); return {'content': 'Read all sixty.'} if len(asked) > 60 else look
        with mock.patch.object(apiagent, 'run_tool', side_effect=lambda *a: f'PAGE {next(n)}') as ran:
            self.assertEqual(apiagent.turn(Brain(), MemoryStore(), 1, 's', 'sys', 'go', 500), 'Read all sixty.')
        self.assertEqual(ran.call_count, 60)
        asked.clear()
        class Circling:
            def chat(self, msgs, tools, max_tokens, **kw): asked.append((kw, msgs[-1]['content'])); return {'content': 'Stuck on the list.'} if kw else look
        with mock.patch.object(apiagent, 'run_tool', return_value='PAGE') as ran, mock.patch.object(apiagent, 'STUCK', 5):
            self.assertEqual(apiagent.turn(Circling(), MemoryStore(), 1, 's', 'sys', 'go', 500), 'Stuck on the list.')
        self.assertEqual(ran.call_count, 5)
        self.assertEqual(asked[-1][0], {'tool_choice': 'none'}); self.assertIn('the same call 5 times in a row', asked[-1][1])

    def test_stop_ends_the_turn_at_once_under_a_model_call_or_a_tool(self):
        "Stop was read between steps: it waited out the model's answer, the page, the command."
        import threading, time
        stop, hold = threading.Event(), threading.Event()
        class Thinking:
            def chat(self, *a, **kw): hold.wait(20); return {'content': 'late'}
        threading.Timer(0.2, stop.set).start(); t0 = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, 'stopped'): apiagent.turn(Thinking(), MemoryStore(), 1, 's', 'sys', 'go', 500, cancel=stop)
        self.assertLess(time.monotonic() - t0, 5)
        stop, kept = threading.Event(), []
        class Brain:
            def chat(self, *a, **kw): return {'tool_calls': [{'id': 'c', 'function': {'name': 'browser_look', 'arguments': '{}'}}]}
        threading.Timer(0.2, stop.set).start(); t0 = time.monotonic()
        with mock.patch.object(apiagent, 'run_tool', side_effect=lambda *a: hold.wait(20)), self.assertRaisesRegex(RuntimeError, 'stopped'):
            apiagent.turn(Brain(), MemoryStore(), 1, 's', 'sys', 'go', 500, cancel=stop, history=kept)
        hold.set()
        self.assertLess(time.monotonic() - t0, 5)
        self.assertEqual([m['role'] for m in kept], ['user', 'assistant', 'tool'], 'what it had done is kept, its open call answered')

    def test_a_long_conversation_drops_its_oldest_tool_answers_then_its_oldest_turns(self):
        call = lambda k: {'role': 'assistant', 'tool_calls': [{'id': k, 'function': {'name': 'file_read', 'arguments': '{}'}}]}
        def talk(): return [{'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': 'the whole task'},
                            call('a'), {'role': 'tool', 'tool_call_id': 'a', 'content': 'x' * 600}, {'role': 'assistant', 'content': 'one'},
                            {'role': 'user', 'content': 'two'}, call('b'), {'role': 'tool', 'tool_call_id': 'b', 'content': 'y' * 600},
                            {'role': 'assistant', 'content': 'done'}, {'role': 'user', 'content': 'three'}]
        msgs = talk()
        with mock.patch.object(apiagent, 'BUDGET', 1000): apiagent._fit(msgs, keep=2)
        self.assertEqual([m['content'] for m in msgs if m['role'] == 'tool'], [apiagent.DROPPED, 'y' * 600])
        self.assertEqual(len(msgs), 10, 'its calls stay: it still sees what it did')
        msgs = talk()
        with mock.patch.object(apiagent, 'BUDGET', 60): apiagent._fit(msgs, keep=2)
        self.assertEqual([m.get('content') for m in msgs], ['sys', 'the whole task', 'two', None, apiagent.DROPPED, 'done', 'three'])

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

    def test_a_card_with_the_toolbox_is_never_told_it_lacks_what_the_toolbox_holds(self):
        from taskuary import general, selfclose
        seen = []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): seen.append(msgs[0]['content']); return {'content': 'Read them.'}
        self._turn(Brain(), toolbox=('search_messages', 'tick'))
        self.assertIn(general._SEARCHED[1], seen[0]); self.assertNotIn('NO SEARCH OF ITS OWN', seen[0])
        self.assertEqual(general.for_toolbox(f'a\n\n{selfclose.TICK_CHAT_LINE}', ('tick',)), f'a\n\n{selfclose.TICK_TOOL_LINE}')
        self.assertEqual(general.for_toolbox(general.SEARCHED_LINE, ('show',)), general.SEARCHED_LINE)      # ...and without them, as before
        seen.clear(); self._turn(Brain())
        self.assertIn('NO SEARCH OF ITS OWN', seen[0])

    def test_a_sign_in_the_looped_agent_asks_for_goes_to_the_vault_road(self):
        # the agent never types a password: its marker raises signin.needs, which fills a saved vault login or asks the owner to
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): return {'content': 'The sign-in page is open.\n[[TASKUARY-SIGNIN: portal.example]]'}
        with mock.patch('taskuary.signin.needs') as needs: self._turn(Brain())
        self.assertEqual(needs.call_args[0][3], 'portal.example')

    def test_its_second_turn_is_the_turn_alone_on_the_conversation_it_kept(self):
        from taskuary import general, llm as llm_mod
        heard = []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): heard.append([dict(m) for m in msgs]); return {'content': f'answer {len(heard)}'}
        s = MemoryStore()
        tid = s.create_task({'Title': 'Read the denials on the scheduling portal', 'Summary': 'the August period', 'Kind': 'general', 'Status': 'open'}, 'owner')
        session = general.GeneralSession(s, tid)
        session.pick, session.provider, session.model = 'connector:1', 'HIPAA AI', ''
        with mock.patch.object(llm_mod, 'build_llm', return_value=Brain()), mock.patch.object(bv, 'installed', return_value=True), \
             mock.patch.object(bv, 'state', return_value={'open': False}), mock.patch.object(apiagent, 'taskuary_tools', return_value=[]):
            session.send_prompt('read the denials', echo=False)
            session.send_prompt('and which is the oldest?', echo=False)
            self.assertEqual([m['role'] for m in heard[1]], ['system', 'user', 'assistant', 'user'])
            self.assertEqual(heard[1][1], heard[0][1], 'the task, said in full once')
            self.assertIn('the August period', heard[1][1]['content']); self.assertNotIn('the August period', heard[1][3]['content'])
            self.assertIn('and which is the oldest?', heard[1][3]['content'])
            # ...and turned down on a later first call (too long for the model now), it is said again whole - once, on a fresh one
            class Full(Brain):
                def chat(self, msgs, *a, **kw):
                    if len(msgs) > 2: raise RuntimeError('hipaa_ai error 400 at https://gateway.example: too many tokens')
                    return super().chat(msgs, *a, **kw)
            with mock.patch.object(llm_mod, 'build_llm', return_value=Full()): session.send_prompt('go on', echo=False)
        self.assertEqual([m['role'] for m in heard[2]], ['system', 'user'])
        self.assertIn('the August period', heard[2][1]['content']); self.assertIn('and which is the oldest?', heard[2][1]['content'])
        self.assertEqual([m['role'] for m in session.card_msgs], ['user', 'assistant'])
        # ...and with nothing answering at all, what it had is still its own - with the line it was just told
        class Down(Brain):
            def chat(self, *a, **kw): raise RuntimeError('hipaa_ai could not be reached')
        with mock.patch.object(llm_mod, 'build_llm', return_value=Down()), mock.patch.object(bv, 'installed', return_value=True), \
             mock.patch.object(bv, 'state', return_value={'open': False}), mock.patch.object(apiagent, 'taskuary_tools', return_value=[]):
            try: session.send_prompt('and the newest?', echo=False)
            except Exception: pass
        self.assertEqual([m['role'] for m in session.card_msgs], ['user', 'assistant', 'user'])
        self.assertIn('and the newest?', session.card_msgs[-1]['content'])

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

    def test_a_card_with_the_email_tool_hears_the_tool_and_one_that_refuses_tools_the_block(self):
        # the agent walk, 2026-11-10: one road for an email by what the session has - and a model that would not take tools is asked the
        # plain way with the plain way's road, where it used to be left with the name of a tool it had just refused
        from taskuary import selfclose
        seen = []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): seen.append(msgs[0]['content']); return {'content': 'ok'}
        self._turn(Brain(), toolbox=('search_messages', 'propose_email', 'show'))
        self.assertIn('propose_reply / propose_email', seen[0]); self.assertNotIn(selfclose.DRAFT_OPEN, seen[0])
        class Refuses:
            def __call__(self, system, user, **kw): seen.append(system); return 'Here is what I can do.'
            def chat(self, *a, **kw): raise RuntimeError('hipaa_ai error 400 at https://gateway.example: tools are not supported')
        self._turn(Refuses(), toolbox=('search_messages', 'propose_email', 'show'))
        self.assertIn(selfclose.DRAFT_LINE, seen[1]); self.assertNotIn('propose_email', seen[1])

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


class TheHandsTests(unittest.TestCase):
    """Parity with a Claude Code session (the owner, 2026-11-09: "it should be the same as claude cli permission wise"): its folder, its
    files, its commands under the ONE gate a CLI's commands pass (hooks.command_gate), and the model's own web search."""

    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Compare two quotes', 'Summary': 'go', 'Kind': 'general', 'Status': 'open'}, 'owner')

    def run_(self, tool, **a): return apiagent.run_tool(self.s, self.tid, 'sid-h', tool, a)

    def test_a_general_task_works_in_the_folder_a_general_cli_does(self):
        from taskuary import config
        self.assertEqual(Path(apiagent.workdir(self.s, self.tid)), config.home() / 'scratch')

    def test_a_coding_task_works_in_its_checkout(self):
        tid = self.s.create_task({'Title': 'Fix the build', 'Summary': 'go', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        with mock.patch('taskuary.agentchannels.cwd_of', return_value=str(config_home() / 'ledger')):
            self.assertEqual(Path(apiagent.workdir(self.s, tid)), config_home() / 'ledger')

    def test_files_are_written_edited_listed_and_read_where_named(self):
        self.assertIn('Wrote', self.run_('file_write', path='notes/quotes.csv', text='vendor,price\nPayworth,4200\n'))
        self.run_('file_edit', path='notes/quotes.csv', old='4200', new='4100')
        self.assertIn('quotes.csv', self.run_('files_list', path='notes'))
        self.assertIn('Payworth,4100', self.run_('file_read', path='notes/quotes.csv'))
        with self.assertRaises(ValueError): self.run_('file_edit', path='notes/quotes.csv', old='nowhere', new='x')

    def test_a_command_the_cli_would_run_runs_now_in_the_working_folder(self):
        class Done:
            pid, returncode = 4242, 0
            def communicate(self, timeout=None): return b'3 files', b''
        with mock.patch('taskuary.hooks.command_gate', return_value={}) as gate, mock.patch('taskuary.spawn.popen', return_value=Done()) as ran:
            said = self.run_('run_command', command='git status', why='see what changed')
        self.assertIn('exit 0', said); self.assertIn('3 files', said)
        self.assertEqual(gate.call_args.args[3], 'git status')
        self.assertEqual(ran.call_args.kwargs['cwd'], apiagent.workdir(self.s, self.tid))

    def test_stop_ends_a_command_under_way_and_what_it_started(self):
        import subprocess, threading
        class Building:
            pid, returncode = 4242, None
            def communicate(self, timeout=None): raise subprocess.TimeoutExpired('build', timeout)
        stop = threading.Event(); stop.set()
        with mock.patch('taskuary.hooks.command_gate', return_value={}), mock.patch('taskuary.spawn.popen', return_value=Building()), \
             mock.patch.dict(apiagent.STOPS, {(self.tid, 'sid-h'): stop}), mock.patch.object(apiagent, '_kill') as killed:
            with self.assertRaisesRegex(RuntimeError, 'stopped'): self.run_('run_command', command='npm run build', why='build it')
        killed.assert_called_once()

    def test_a_command_the_cli_would_hold_is_held_by_the_same_gate_and_never_run(self):
        with mock.patch('taskuary.spawn.popen') as ran:
            said = self.run_('run_command', command='git push origin main', why='publish the fix')
        ran.assert_not_called()
        self.assertIn('held this for the owner', said)
        held = self.s._rows("SELECT DraftText FROM review WHERE TaskId=? AND Kind='action'", (self.tid,))
        self.assertEqual(json.loads(held[0]['DraftText'])['command'], 'git push origin main')

    def test_the_cli_hook_and_the_api_agent_share_one_decision(self):
        from taskuary import hooks
        payload = {'tool_name': 'Bash', 'tool_input': {'command': 'git push'}, 'cwd': ''}
        class T: store, task_id, sid, cwd = self.s, self.tid, 'sid-c', ''
        with mock.patch.object(hooks, '_pane', return_value=T()), mock.patch.object(hooks, 'command_gate', return_value={'x': 1}) as gate:
            self.assertEqual(hooks.browser(payload), {'x': 1})
        gate.assert_called_once()

    def test_web_search_is_the_models_own(self):
        class Brain:
            def search(self, q): return f'Answer to {q}\n\nSOURCES\nhttps://docs.example/rates'
        apiagent.BRAINS[(self.tid, 'sid-h')] = Brain()
        try: self.assertIn('docs.example/rates', self.run_('web_search', query='current rates'))
        finally: apiagent.BRAINS.pop((self.tid, 'sid-h'), None)

    def test_a_gateway_that_refuses_search_falls_back_to_a_search_card(self):
        class Brain:
            def search(self, q): raise RuntimeError('hipaa_ai error 400: web_search_options not supported')
        apiagent.BRAINS[(self.tid, 'sid-h')] = Brain()
        cards = [{'Type': 'brave_search', 'Active': 1, 'HasSecret': 1, 'ConnectorId': 4}]
        try:
            with mock.patch.object(self.s, 'list_connectors', return_value=cards), \
                 mock.patch.object(apiagent, 'call_taskuary', return_value='[1] Payworth') as ran:
                self.assertEqual(self.run_('web_search', query='payroll vendors'), '[1] Payworth')
            self.assertEqual(ran.call_args[0][2], 'run_system')
        finally: apiagent.BRAINS.pop((self.tid, 'sid-h'), None)

    def test_the_card_asks_its_own_search_with_web_search_options_and_no_function_tools(self):
        sent = []
        def post(url, headers, body, timeout):
            sent.append(body)
            return _R({'choices': [{'message': {'content': 'Python 3.15.2', 'annotations': [{'type': 'url_citation', 'url_citation': {'url': 'https://python.example/'}}]}}]})
        brain = llm.make_llm('hipaa_ai', {'base_url': 'https://gateway.example', 'model': 'gemini-x'}, 'k')
        with mock.patch.object(llm, 'post_retrying', side_effect=post), mock.patch.object(llm.aiusage, 'openai'):
            said = brain.search('latest python')
        self.assertIn('web_search_options', sent[0]); self.assertNotIn('tools', sent[0])
        self.assertIn('https://python.example/', said)

    def test_look_only_offers_reads_and_search_but_no_write_and_no_command(self):
        with mock.patch.object(apiagent, 'taskuary_tools', return_value=[]):
            names = {t['function']['name'] for t in apiagent.tools_for(self.tid, 'sid-h', browser=False, hands=False)}
        try:
            self.assertTrue({'files_list', 'file_read', 'web_fetch', 'web_search'} <= names)
            self.assertFalse({'file_write', 'file_edit', 'run_command', 'browser_open'} & names)
            with self.assertRaises(ValueError): self.run_('run_command', command='dir', why='list')
        finally: apiagent.OFFERED.pop((self.tid, 'sid-h'), None); apiagent.TOOLBOX.pop((self.tid, 'sid-h'), None)


class EveryCardTests(unittest.TestCase):
    """Every AI card runs the same agent (the owner, 2026-11-09: "check all APIs like Azure work the same way as Claude CLI and HIPAA"): the
    one tool loop, the one gate, and each provider's OWN web search - recorded request and answer shapes for the cards not proven live."""
    LOOP = [{'role': 'system', 'content': 'You are an agent.'}, {'role': 'user', 'content': 'Compare the two quotes.'},
            {'role': 'assistant', 'content': 'Reading both.', 'tool_calls': [
                {'id': 't1', 'type': 'function', 'function': {'name': 'file_read', 'arguments': '{"path": "a.csv"}'}},
                {'id': 't2', 'type': 'function', 'function': {'name': 'file_read', 'arguments': '{"path": "b.csv"}'}}]},
            {'role': 'tool', 'tool_call_id': 't1', 'content': 'Payworth,4200'}, {'role': 'tool', 'tool_call_id': 't2', 'content': 'Trainly,3900'},
            {'role': 'user', 'content': 'You are out of steps for this turn.'}]
    CFG = {'azure_openai': {'endpoint': 'https://res.example', 'deployment': 'gpt-x'}, 'vertex_ai': {'project': 'p1'},
           'ollama': {'model': 'llama3'}, 'hipaa_ai': {'base_url': 'https://gateway.example'}}

    def test_every_card_type_gets_the_tool_loop(self):
        import types
        fake = types.SimpleNamespace(Anthropic=lambda **k: None, BadRequestError=Exception)
        with mock.patch.dict('sys.modules', {'anthropic': fake}):
            for t in llm.AI_TYPES:
                with self.subTest(t): self.assertTrue(apiagent.can(llm.make_llm(t, self.CFG.get(t, {}), 'k')))

    def test_only_a_card_with_its_own_search_says_it_searches(self):
        for t in ('groq', 'mistral', 'ollama', 'deepseek', 'cerebras'):
            with self.subTest(t): self.assertFalse(hasattr(llm.make_llm(t, self.CFG.get(t, {}), 'k'), 'search'))
        for t in ('openai', 'azure_openai', 'gemini', 'hipaa_ai', 'openrouter', 'perplexity'):
            with self.subTest(t): self.assertTrue(callable(llm.make_llm(t, self.CFG.get(t, {}), 'k').search))

    def test_the_loop_reads_as_the_messages_api_takes_it(self):
        system, msgs, fns = llm.to_anthropic(self.LOOP, apiagent.FILES)
        self.assertEqual(system, 'You are an agent.')
        self.assertEqual([m['role'] for m in msgs], ['user', 'assistant', 'user'])
        self.assertEqual([b['type'] for b in msgs[1]['content']], ['text', 'tool_use', 'tool_use'])
        self.assertEqual(msgs[1]['content'][1]['input'], {'path': 'a.csv'})
        self.assertEqual([b['type'] for b in msgs[2]['content']], ['tool_result', 'tool_result', 'text'])     # results first, as the API wants
        self.assertEqual(fns[1]['name'], 'file_read'); self.assertIn('properties', fns[1]['input_schema'])

    def test_an_anthropic_card_runs_the_loop_on_the_messages_api(self):
        import types
        sent = []
        class Msgs:
            def create(self, **kw):
                sent.append(kw)
                return types.SimpleNamespace(stop_reason='tool_use', usage=None, content=[
                    types.SimpleNamespace(type='text', text='Writing it.'),
                    types.SimpleNamespace(type='tool_use', id='tu1', name='file_write', input={'path': 'x.txt', 'text': 'hi'})])
        fake = types.SimpleNamespace(Anthropic=lambda **k: types.SimpleNamespace(messages=Msgs()), BadRequestError=type('B', (Exception,), {}))
        with mock.patch.dict('sys.modules', {'anthropic': fake}), mock.patch.object(llm.aiusage, 'anthropic'):
            brain = llm.make_llm('anthropic', {'model': 'claude-x'}, 'k')
            got = brain.chat(self.LOOP, apiagent.WRITE)
            brain.chat(self.LOOP, apiagent.WRITE, tool_choice='none')
        self.assertEqual(got['content'], 'Writing it.')
        self.assertEqual(got['tool_calls'][0]['function'], {'name': 'file_write', 'arguments': '{"path": "x.txt", "text": "hi"}'})
        self.assertEqual(sent[0]['system'], 'You are an agent.'); self.assertEqual(sent[0]['tools'][0]['name'], 'file_write')
        self.assertEqual(sent[1]['tool_choice'], {'type': 'none'})

    def test_an_anthropic_card_searches_with_its_own_server_tool(self):
        with mock.patch.object(llm, '_anthropic_web', return_value='Python 3.15.2 - https://python.example/') as web, \
             mock.patch.dict('sys.modules', {'anthropic': mock.MagicMock()}):
            self.assertIn('python.example', llm.make_llm('anthropic', {}, 'k').search('latest python'))
        self.assertEqual(web.call_args.args[1], llm.PROVIDER_DEFAULT['anthropic'])

    def test_openai_and_azure_search_through_the_responses_api(self):
        for t, cfg, where in (('openai', {}, 'https://api.openai.com/v1/responses'),
                              ('azure_openai', self.CFG['azure_openai'], 'https://res.example/openai/v1/responses')):
            sent = []
            def post(url, headers, body, timeout):
                sent.append((url, body))
                return _R({'output': [{'type': 'web_search_call', 'id': 'ws1', 'status': 'completed', 'action': {'type': 'search', 'query': 'python'}},
                                      {'type': 'message', 'content': [{'type': 'output_text', 'text': 'Python 3.15.2 (python.example)'}]}]})
            with self.subTest(t), mock.patch.object(llm, 'post_retrying', side_effect=post), mock.patch.object(llm.aiusage, 'openai'):
                self.assertIn('3.15.2', llm.make_llm(t, cfg, 'k').search('latest python'))
                self.assertEqual(sent[0][0], where); self.assertEqual(sent[0][1]['tools'], [{'type': 'web_search'}])

    def test_gemini_on_googles_api_searches_with_google_search_grounding(self):
        sent = []
        def post(url, headers, body, timeout):
            sent.append((url, headers, body))
            return _R({'candidates': [{'content': {'parts': [{'text': 'Python 3.15.2'}]},
                                       'groundingMetadata': {'groundingChunks': [{'web': {'uri': 'https://python.example/'}}]}}]})
        with mock.patch.object(llm, 'post_retrying', side_effect=post):
            said = llm.make_llm('gemini', {'model': 'gemini-x'}, 'k').search('latest python')
        self.assertTrue(sent[0][0].endswith('/models/gemini-x:generateContent'))
        self.assertEqual(sent[0][1], {'x-goog-api-key': 'k'}); self.assertEqual(sent[0][2]['tools'], [{'google_search': {}}])
        self.assertIn('SOURCES\nhttps://python.example/', said)

    def test_a_vertex_gemini_searches_on_its_publisher_model(self):
        url = llm._google_url('vertex_ai', {'project': 'p1', 'location': 'us-central1'}, 'google/gemini-x')
        self.assertEqual(url, 'https://us-central1-aiplatform.googleapis.com/v1/projects/p1/locations/us-central1/publishers/google/models/gemini-x:generateContent')
        self.assertEqual(llm._google_url('vertex_ai', {'project': 'p1'}, 'meta/llama'), '')

    def test_a_card_with_no_search_of_its_own_goes_to_a_search_card(self):
        s = MemoryStore(); apiagent.BRAINS[(1, 'g')] = llm.make_llm('groq', {}, 'k')
        cards = [{'Type': 'tavily', 'Active': 1, 'HasSecret': 1, 'ConnectorId': 5}]
        try:
            with mock.patch.object(s, 'list_connectors', return_value=cards), mock.patch.object(apiagent, 'call_taskuary', return_value='[1] Payworth'):
                self.assertEqual(apiagent.run_tool(s, 1, 'g', 'web_search', {'query': 'payroll'}), '[1] Payworth')
            with self.assertRaisesRegex(ValueError, 'no search service is connected'): apiagent.run_tool(s, 1, 'g', 'web_search', {'query': 'payroll'})
        finally: apiagent.BRAINS.pop((1, 'g'), None)

    def test_the_chatgpt_plan_runs_the_loop_on_its_responses_api(self):
        from taskuary import chatgptauth as ca
        out = [{'type': 'function_call', 'call_id': 'fc1', 'name': 'run_command', 'arguments': '{"command": "git status", "why": "see"}'}]
        with mock.patch.object(ca, 'access_token', return_value='tok'), mock.patch.object(ca, 'respond', return_value=out) as asked:
            got = llm.make_llm('chatgpt', {'model': 'gpt-x'}, 'rt').chat(self.LOOP, apiagent.SHELL)
        self.assertEqual(got['tool_calls'][0]['id'], 'fc1')
        tok, model, instructions, items, fns = asked.call_args.args
        self.assertEqual((model, instructions), ('gpt-x', 'You are an agent.'))
        self.assertEqual([i.get('type') or i['role'] for i in items], ['user', 'assistant', 'function_call', 'function_call',
                                                                     'function_call_output', 'function_call_output', 'user'])
        self.assertEqual(fns[0]['name'], 'run_command'); self.assertEqual(fns[0]['type'], 'function')

    def test_the_plan_stream_hands_back_its_function_calls(self):
        from taskuary import chatgptauth as ca
        ev = [{'type': 'response.output_item.done', 'item': {'type': 'function_call', 'call_id': 'fc1', 'name': 'file_read', 'arguments': '{}'}},
              {'type': 'response.completed', 'response': {'usage': {}}}]
        class Resp:
            status_code, encoding = 200, 'utf-8'
            def iter_lines(self, decode_unicode=True): return [f'data: {json.dumps(e)}' for e in ev]
            def __enter__(self): return self
            def __exit__(self, *a): pass
        with mock.patch.object(ca.requests, 'post', return_value=Resp()), mock.patch('taskuary.aiusage.openai'):
            self.assertEqual(ca.respond('tok', 'gpt-x', 'sys', [], [])[0]['name'], 'file_read')

    def test_one_gate_whatever_the_card(self):
        "The tools a turn is offered and the gate its commands pass never ask which card runs it."
        import inspect
        self.assertNotIn('brain', inspect.signature(apiagent.tools_for).parameters)
        self.assertIn('hooks.command_gate', inspect.getsource(apiagent._hands))


class CodingOnACardTests(unittest.TestCase):
    """A coding task runs on an AI card the way a general task does (the owner, 2026-11-09: "coding tasks should run on hipaa, why not"):
    when the owner chose that card for coding, picked it on the task, or it is the only AI here. A CLI chosen for coding still runs it."""

    def setUp(self):
        from taskuary import general
        self.g, self.s = general, MemoryStore()
        self.cid = self.s._exec("INSERT INTO connector (Type,Name,ConfigJson,Secret,Active) VALUES ('hipaa_ai','Org AI','{}','k',1)")
        self.tid = self.s.create_task({'Title': 'add() subtracts', 'Summary': 'fix it', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        self.task = self.s.get_task(self.tid)

    def tearDown(self): self.g.ON_CARD.discard(self.tid)

    def test_the_card_chosen_for_coding_runs_it(self):
        self.s.set_setting('default_brain', f'connector:{self.cid}', 'owner')
        self.assertEqual(self.g.on_card(self.s, self.task), f'connector:{self.cid}')
        self.assertTrue(self.g.handles(self.task))

    def test_a_cli_chosen_for_coding_keeps_it_in_a_terminal(self):
        with mock.patch('taskuary.agents.resolve_brain', return_value='cli:claude'):
            self.assertEqual(self.g.on_card(self.s, self.task), '')
        self.assertFalse(self.g.handles(self.task))
        self.assertEqual(self.g.on_card(self.s, self.task, brain='claude'), '')       # the owner's CLI pick at the picker

    def test_a_pick_on_the_task_and_a_home_with_no_cli(self):
        self.assertEqual(self.g.on_card(self.s, self.task, pick=f'connector:{self.cid}'), f'connector:{self.cid}')
        with mock.patch('taskuary.agents.resolve_brain', return_value=f'connector:{self.cid}'):
            self.assertEqual(self.g.on_card(self.s, self.task), f'connector:{self.cid}')

    def test_a_general_task_is_never_on_card(self):
        t = self.s.get_task(self.s.create_task({'Title': 'q', 'Summary': 'q', 'Kind': 'general', 'Status': 'open'}, 'owner'))
        self.assertEqual(self.g.on_card(self.s, t, pick=f'connector:{self.cid}'), '')

    def test_a_restart_knows_it_again_before_any_page_looks(self):
        self.s.save_session(self.tid, f'connector:{self.cid}', '', '', 'k')
        self.g.ON_CARD.discard(self.tid)                           # the restart: the mark was this process's own
        self.assertFalse(self.g.handles(self.task))
        self.assertIn(self.tid, self.g.recall_cards(self.s))
        self.assertTrue(self.g.handles(self.task))

    def test_a_restart_with_developer_mode_off_recalls_only_what_its_card_worked(self):
        self.s.set_setting('default_brain', f'connector:{self.cid}', 'owner')
        with mock.patch('taskuary.agents.developer_mode', return_value=False):
            self.assertNotIn(self.tid, self.g.recall_cards(self.s))
            self.s.add_comment(self.tid, 'owner', self.g.USER_TYPE, 'fix it')
            self.assertIn(self.tid, self.g.recall_cards(self.s))

    def test_a_cli_named_for_it_takes_it_off_its_card(self):
        self.g.on_card(self.s, self.task, pick=f'connector:{self.cid}')
        self.assertTrue(self.g.handles(self.task))
        self.assertEqual(self.g.on_card(self.s, self.task, brain='claude'), '')
        self.assertFalse(self.g.handles(self.task))

    def test_every_road_that_starts_it_starts_it_on_its_card(self):
        "New mail's carry-on, a queue drain, the waiting room: terminal.start_on_task - it opened a CLI's pane, or made the task general work."
        from taskuary import terminal
        self.s.set_setting('default_brain', f'connector:{self.cid}', 'owner')
        self.s.set_setting('developer_mode', '1', 'owner')
        ses = mock.Mock(); ses.info.return_value = {'sid': 's1'}
        with mock.patch.object(self.g, 'place_coding') as placed, mock.patch.object(self.g, 'start_session', return_value=ses) as started, \
             mock.patch.object(terminal, '_ask_quietly') as asked, mock.patch.object(terminal, 'open_session') as pane, \
             mock.patch.object(terminal, '_as_general') as general_work, mock.patch('taskuary.agents.developer_mode', return_value=True):
            out = terminal.start_on_task(self.s, self.tid, instruction='Gail wrote again: also fix sub()', actor='router')
            for th in __import__('threading').enumerate():
                if th.name == f'general-{self.tid}': th.join(5)
        placed.assert_called_once(); pane.assert_not_called(); general_work.assert_not_called()
        self.assertEqual(started.call_args.kwargs['pick'], f'connector:{self.cid}')
        self.assertEqual(asked.call_args.args[1], 'Gail wrote again: also fix sub()')
        self.assertTrue(out['general']); self.assertEqual(self.s.get_task(self.tid)['Kind'], 'coding')

    def test_developer_mode_off_only_a_task_its_card_already_worked(self):
        from taskuary import terminal
        self.s.set_setting('default_brain', f'connector:{self.cid}', 'owner')
        with mock.patch('taskuary.agents.developer_mode', return_value=False), mock.patch.object(terminal, '_on_card') as card, \
             mock.patch.object(terminal, '_as_general', return_value={'general': True}) as general_work:
            terminal.start_on_task(self.s, self.tid, actor='router')
            card.assert_not_called(); general_work.assert_called_once()
            self.s.add_comment(self.tid, 'owner', self.g.USER_TYPE, 'fix it')
            self.s.update_task(self.tid, {'Kind': 'coding'}, 'owner')
            terminal.start_on_task(self.s, self.tid, actor='router')
            card.assert_called_once()

    def test_it_works_in_the_checkout_its_cli_would(self):
        import tempfile
        repo = tempfile.mkdtemp()
        self.s.update_task(self.tid, {'Tags': 'repo:northwind/ledger'}, 'owner')
        self.s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cwd_map': {'northwind/ledger': repo}}))
        with mock.patch('taskuary.landing.sha', return_value='abc123'), mock.patch('taskuary.landing.head_branch', return_value='main'):
            self.assertEqual(self.g.place_coding(self.s, self.tid), repo)
        self.assertEqual(Path(apiagent.workdir(self.s, self.tid)).resolve(), Path(repo).resolve())

    def test_it_is_told_this_is_coding_and_where_it_works_as_its_cli_is(self):
        import tempfile
        self.s.add_comment(self.tid, 'owner', self.g.USER_TYPE, 'fix it')
        self.assertIn('non-coding work', self.g._prompt(self.s, self.tid)[0])              # ...general work still is
        self.g.ON_CARD.add(self.tid)
        system, user = self.g._prompt(self.s, self.tid)
        self.assertIn(self.g.CODING_WHO, system)
        self.assertNotIn('non-coding', system); self.assertNotIn('Do not turn this into a coding task', system)
        self.assertIn('REPOSITORIES - no checkout is chosen for this task yet', user)      # nothing placed it: the ones to pick from
        repo = tempfile.mkdtemp()
        self.s.update_task(self.tid, {'Tags': 'repo:northwind/ledger'}, 'owner')
        self.s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cwd_map': {'northwind/ledger': repo}}))
        with mock.patch('taskuary.landing.sha', return_value='abc123'), mock.patch('taskuary.landing.head_branch', return_value='main'):
            self.g.place_coding(self.s, self.tid)
        peer = [{'tid': 99, 'ref': 'TQ-0099', 'title': 'sub() adds', 'agent': 'claude', 'files': ['ledger.py'], 'started': ''}]
        with mock.patch('taskuary.blackboard.peers', return_value=peer), mock.patch('taskuary.blackboard.likely_overlap', return_value=(None, '')) as read:
            user = self.g._prompt(self.s, self.tid)[1]
            self.assertIn(f'REPO: {apiagent.workdir(self.s, self.tid)} - you are already in it', user)
            self.assertIn('OTHER AGENTS are working in this same checkout', user); self.assertIn('ledger.py', user)
            read.assert_called_once()
            self.s.add_comment(self.tid, 'assistant', self.g.ASSISTANT_TYPE, 'Fixed add().')
            self.g._prompt(self.s, self.tid)
            read.assert_called_once()                                                      # the overlap read is the opening's, not every turn's

    def test_it_is_a_peer_in_its_checkout_as_a_pane_is(self):
        import tempfile
        from taskuary import blackboard, landing, peers, terminal
        repo, other = tempfile.mkdtemp(), self.s.create_task({'Title': 'sub() adds', 'Summary': 'fix it', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        self.s.update_task(self.tid, {'Tags': 'repo:northwind/ledger'}, 'owner')
        self.s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cwd_map': {'northwind/ledger': repo}}))
        session = self.g.GeneralSession(self.s, self.tid)
        terminal.SESSIONS[session.sid] = session
        try:
            self.assertEqual(session.cwd, '')                                           # general work is in nobody's checkout
            self.assertNotIn(session, peers.working())
            self.g.ON_CARD.add(self.tid)
            with mock.patch('taskuary.landing.sha', return_value='abc123'), mock.patch('taskuary.landing.head_branch', return_value='main'):
                self.g.place_coding(self.s, self.tid)
            self.assertEqual(session.cwd, repo)
            self.assertEqual([p['tid'] for p in blackboard.peers(self.s, repo, exclude_tid=other)], [self.tid])
            self.assertFalse(landing._alone(other, repo)); self.assertTrue(landing._alone(self.tid, repo))
            self.assertEqual(peers.targets(self.s, other, 'all')[1], [self.tid])
            self.assertEqual(peers.targets(self.s, self.tid, 'repo')[0], 'repo')        # its own note to 'repo' has a checkout to read
            self.assertNotIn(session, peers.working(at_rest=False))                     # ...between its turns it holds nothing
            session.busy = True
            self.assertIn(session, peers.working(at_rest=False))
            with mock.patch('taskuary.blackboard.dirty', return_value={'ledger.py'}):
                self.assertEqual(session.files(), [])                                   # before its first turn nothing is counted as its own
                session.dirty0 = set()
                self.assertEqual(session.files(), ['ledger.py'])
            session.cwd = 'elsewhere'                                                   # use_repo moved it (repochoice.use)
            self.assertEqual(session.cwd, 'elsewhere')
        finally: terminal.SESSIONS.pop(session.sid, None)

    def test_a_session_that_is_gone_leaves_nothing_behind_it(self):
        from taskuary import llm as llm_mod
        seen = []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): seen.append(dict(apiagent.BRAINS)); return {'content': 'Done.'}
        session = self.g.GeneralSession(self.s, self.tid)
        session.pick, session.provider, session.model = f'connector:{self.cid}', 'Org AI', ''
        k = (self.tid, session.sid)
        with mock.patch.object(llm_mod, 'build_llm', return_value=Brain()), mock.patch.object(bv, 'installed', return_value=True),              mock.patch.object(bv, 'state', return_value={'open': False}), mock.patch.object(bv, 'close'), mock.patch.object(bv, 'keep_page'),              mock.patch.object(apiagent, 'taskuary_tools', return_value=[]):
            session.send_prompt('fix add()', echo=False)
            self.assertIn(k, seen[0])                                                   # the turn had its brain while it ran...
            for d in (apiagent.BRAINS, apiagent.STOPS, apiagent.SAY): self.assertNotIn(k, d)       # ...and none of it once it ended
            self.assertIn(k, apiagent.OFFERED)                                          # what it may call stays while the session lives
            session.close(learn=False, report=False)
        for d in (apiagent.OFFERED, apiagent.TOOLBOX, apiagent.STRANGERS): self.assertNotIn(k, d)

    def test_a_note_another_agent_sent_it_is_heard_on_its_next_turn(self):
        from taskuary import llm as llm_mod
        other = self.s.create_task({'Title': 'sub() adds', 'Summary': 'fix it', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        self.s.add_peer_note(other, self.tid, 'task', '', 'I am changing ledger.py - hold off until I push')
        self.g.ON_CARD.add(self.tid)
        heard = []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): heard.append(msgs[-1]['content']); return {'content': 'Waiting for it.'}
        session = self.g.GeneralSession(self.s, self.tid)
        session.pick, session.provider, session.model = f'connector:{self.cid}', 'Org AI', ''
        with mock.patch.object(llm_mod, 'build_llm', return_value=Brain()), mock.patch.object(bv, 'installed', return_value=True), \
             mock.patch.object(bv, 'state', return_value={'open': False}), mock.patch.object(apiagent, 'taskuary_tools', return_value=[]):
            session.send_prompt('fix add()', echo=False)
        self.assertIn('hold off until I push', heard[0])
        self.assertEqual(self.s.peer_notes(self.tid), [], 'read once: the next turn does not hear it again')

    def test_a_named_repo_with_no_checkout_refuses_as_the_cli_does(self):
        self.s.update_task(self.tid, {'Tags': 'repo:northwind/portal'}, 'owner')
        with mock.patch('taskuary.terminal.find_checkout', return_value=None), self.assertRaisesRegex(ValueError, 'no local path'):
            self.g.place_coding(self.s, self.tid)


def config_home():
    from taskuary import config
    return config.home()


if __name__ == '__main__': unittest.main()
