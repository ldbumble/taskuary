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
from tests.test_linked_documents import pdf


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

    def test_his_line_sent_while_it_works_reaches_it_at_its_next_step(self):
        """Design round 3, 2026-11-18: "sign up yourself" waited 13 minutes behind a long turn. An API card's turn hears what was steered to its
        conversation (clipool.ear) between its tool calls, as his next message - made only as it goes in - and a line steered as it answers is
        answered in the same turn; once the turn is over nothing more is taken."""
        from taskuary import clipool
        steps = iter([{'tool_calls': [{'id': 'c1', 'function': {'name': 'browser_open', 'arguments': '{"url": "vendor.example"}'}}]},
                      {'content': 'Opened it.'}, {'content': 'Signing up myself, then.'}])
        heard, made = [], []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw):
                heard.append([dict(m) for m in msgs])
                if len(heard) == 2: assert clipool.steer('general:5', lambda: made.append(1) or 'THE OWNER SAYS: sign up yourself')
                return next(steps)
        def tool(*a):
            assert clipool.steerable('general:5'); return 'PAGE vendor.example'
        with mock.patch.object(apiagent, 'run_tool', side_effect=tool):
            said = apiagent.turn(Brain(), MemoryStore(), 1, 's', 'sys', 'list the vendors', 500, ear='general:5')
        self.assertEqual(said, 'Signing up myself, then.')
        self.assertEqual(heard[2][-2:], [{'role': 'assistant', 'content': 'Opened it.'}, {'role': 'user', 'content': 'THE OWNER SAYS: sign up yourself'}])
        self.assertEqual(made, [1])
        self.assertFalse(clipool.steerable('general:5'), "over: a line is the next turn's")

    def test_a_failed_tool_is_told_to_the_model_not_raised(self):
        steps = iter([{'tool_calls': [{'id': 'c1', 'function': {'name': 'browser_click', 'arguments': '{"ref": "@e9"}'}}]},
                      {'content': 'The button was gone.'}])
        heard = []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): heard.append(list(msgs)); return next(steps)
        with mock.patch.object(apiagent, 'run_tool', side_effect=ValueError('no element @e9')):
            self.assertEqual(apiagent.turn(Brain(), MemoryStore(), 1, 's', 'sys', 'go', 500), 'The button was gone.')
        self.assertIn('no element @e9', heard[1][-1]['content'])

    # ...IN THE WORDS EVERY TASKUARY TOOL'S FAILURE TAKES (agenttools.failed), never "share failed: " before them: the owner's Why line read the
    # tool's name over what happened ("Why: share failed: there is no report 9"), and the next step stayed the agent's own line (the UI judge)
    def test_a_failed_tool_is_told_in_the_words_every_tool_failure_takes(self):
        from taskuary import agenttools
        steps = iter([{'tool_calls': [{'id': 'c1', 'function': {'name': 'share', 'arguments': '{"report": 9}'}}]}, {'content': 'No such report.'}])
        refused, seen = agenttools.refusal('there is no report 9', 'give the number search_tasks gives', door='tool'), []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): return next(steps)
        with mock.patch.object(apiagent, 'run_tool', side_effect=ValueError(refused)):
            apiagent.turn(Brain(), MemoryStore(), 1, 's', 'sys', 'go', 500, trace=lambda *e: seen.append(e))
        got = next(d for k, n, d in seen if k == 'tool_result')
        self.assertEqual((got['result'], got['is_error']), (refused, True))

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

    def test_a_carried_conversation_turned_down_on_the_first_call_is_lost_and_a_fresh_one_fails_as_it_failed(self):
        kept = [{'role': 'user', 'content': 'the whole task'}, {'role': 'assistant', 'content': 'Done.'}]
        class Brain:
            def chat(self, *a, **kw): raise RuntimeError('gateway error 400 at https://gateway.example: too many tokens')
        with self.assertRaises(apiagent.Lost): apiagent.turn(Brain(), MemoryStore(), 1, 's', 'sys', 'and now?', 500, history=kept)
        self.assertEqual(len(kept), 2)
        with self.assertRaisesRegex(RuntimeError, 'error 400'): apiagent.turn(Brain(), MemoryStore(), 1, 's', 'sys', 'go', 500, history=[])
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
        with mock.patch.object(apiagent, 'run_tool', return_value='PAGE') as ran, mock.patch.object(apiagent, 'IDLE_STEPS', 5):
            self.assertEqual(apiagent.turn(Circling(), MemoryStore(), 1, 's', 'sys', 'go', 500), 'Stuck on the list.')
        self.assertEqual(ran.call_count, 6, 'the first PAGE was news; five more of it were not')
        self.assertEqual(asked[-1][0], {'tool_choice': 'none'}); self.assertIn('last 5 steps brought nothing', asked[-1][1])

    def test_a_small_model_searching_again_in_other_words_for_the_same_hits_is_stopped(self):
        """The owner, 2026-11-10: "are we leaking tokens?" - other arguments every time never tripped "the same call", and a turn whose
        answers held nothing new ran on, each step sending more. Steps that find nothing new end it (the `agent_idle_steps` setting)."""
        n, asked = iter(range(999)), []
        class Wandering:
            def chat(self, msgs, tools, max_tokens, **kw):
                asked.append(kw)
                return {'content': 'Nothing more.'} if kw else {'tool_calls': [{'id': f'c{len(asked)}', 'function': {'name': 'search_mail', 'arguments': json.dumps({'q': f'renewal {next(n)}'})}}]}
        hits = '\n'.join(f'[m{i}] Erin Blake - Payworth renewal' for i in range(10))
        s = MemoryStore(); s.set_setting('agent_idle_steps', '4', 'owner')
        with mock.patch.object(apiagent, 'run_tool', side_effect=lambda *a: '\n'.join(reversed(hits.splitlines())) if len(asked) % 2 else hits) as ran:
            self.assertEqual(apiagent.turn(Wandering(), s, 1, 's', 'sys', 'go', 500), 'Nothing more.')
        self.assertEqual(ran.call_count, 5)

    def test_a_call_sends_old_tool_answers_as_a_line_and_keeps_them_whole(self):
        "Every step sent every earlier answer in full; the conversation kept still has them, and what is sent before them never changes."
        page = lambda k: f'PAGE {k} ' + 'x' * 5000
        seen = []
        class Reader:
            def chat(self, msgs, tools, max_tokens, **kw):
                seen.append(json.dumps(msgs)); k = len(seen)
                return {'content': 'Read all eight.'} if k > 8 else {'tool_calls': [{'id': f'c{k}', 'function': {'name': 'file_read', 'arguments': json.dumps({'path': f'f{k}.txt'})}}]}
        kept = []
        with mock.patch.object(apiagent, 'run_tool', side_effect=lambda s, t, i, n, a: page(a['path'])):
            apiagent.turn(Reader(), MemoryStore(), 1, 's', 'sys ' * 2000, 'go', 500, history=kept)
        self.assertLess(len(seen[-1]), 8000 + 5 * 5100 + 3 * 400 + 2000, 'the last call carries at most five answers whole, the rest as lines')
        self.assertTrue('the answer to file_read' in seen[-1] and 'f1.txt' in seen[-1] and 'call it again' in seen[-1])
        self.assertEqual(sum(len(m.get('content') or '') > 5000 for m in kept if m['role'] == 'tool'), 8, 'what is kept is whole')
        same = lambda a, b: next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        self.assertTrue(all(same(a, b) >= 8000 for a, b in zip(seen, seen[1:])), 'the system and the task lead every call, byte for byte')
        # ...and a call is the one before it with more at the end, but where the line moves - a block of three steps at a time (the cache
        # audit, 2026-11-14: moved on every step, each step wrote the last three answers to the cache again)
        self.assertLessEqual(sum(same(a, b) < len(a) - 2 for a, b in zip(seen, seen[1:])), 2)

    def test_the_request_bound_counts_the_tools_sent_beside_the_conversation(self):
        "The gateway's own log, 2026-11-15: calls of 35-60K tokens under a 120,000-character bound - the tools' schemas were never counted."
        page = lambda k: f'PAGE {k} ' + 'x' * 9000
        seen, tools = [], [apiagent._fn(f'tool{i}', 'd' * 700, apiagent._S({})) for i in range(20)]
        class Reader:
            def chat(self, msgs, tools, max_tokens, **kw):
                seen.append(len(json.dumps(msgs)) + len(json.dumps(tools))); k = len(seen)
                return {'content': 'Read all eight.'} if k > 8 else {'tool_calls': [{'id': f'c{k}', 'function': {'name': 'file_read', 'arguments': json.dumps({'path': f'f{k}.txt'})}}]}
        s = MemoryStore(); s.set_setting('agent_request_chars', '60000', 'owner')
        with mock.patch.object(apiagent, 'run_tool', side_effect=lambda s, t, i, n, a: page(a['path'])):
            apiagent.turn(Reader(), s, 1, 's', 'sys ' * 2000, 'go', 500, tools=tools)
        self.assertLess(max(seen), 60000 * 1.05, 'the whole request - its tools with it - under the bound')

    def test_a_read_made_again_in_one_turn_is_answered_from_the_first_until_something_else_runs(self):
        """A model that read the same file or brief twice paid for the whole answer twice and the server ran it twice. A read-only tool
        (the catalogue's mark) called again with the same arguments is answered by a pointer while the first answer still goes whole, by
        that answer again once it has gone out of what is sent - never run again - and any call that is not a read clears the record."""
        plan = [('file_read', {'path': 'a'}), ('my_task', {}), ('file_read', {'path': 'a'}), ('my_task', {}), ('file_read', {'path': 'b'}),
                ('file_read', {'path': 'c'}), ('file_read', {'path': 'd'}), ('file_read', {'path': 'a'}), ('tick', {'item': '1'}), ('file_read', {'path': 'a'})]
        class Reader:
            def chat(self, msgs, tools, max_tokens, **kw):
                k = sum(1 for m in msgs if m.get('tool_calls'))
                if k == len(plan): return {'content': 'Done.'}
                return {'tool_calls': [{'id': f'c{k}', 'function': {'name': plan[k][0], 'arguments': json.dumps(plan[k][1])}}]}
        page, kept = lambda n, a: f"{n} {a.get('path', '')} " + 'x' * 2000, []
        apiagent.READS[(1, 's')] = {'my_task'}
        try:
            with mock.patch.object(apiagent, 'run_tool', side_effect=lambda s, t, i, n, a: page(n, a)) as ran:
                apiagent.turn(Reader(), MemoryStore(), 1, 's', 'sys', 'go', 500, history=kept)
        finally: apiagent.READS.pop((1, 's'), None)
        self.assertEqual([c.args[3:] for c in ran.call_args_list], [plan[i] for i in (0, 1, 4, 5, 6, 8, 9)])
        said = [m['content'] for m in kept if m['role'] == 'tool']
        self.assertTrue(said[2].startswith('(the same as your earlier file_read') and said[3].startswith('(the same as your earlier my_task'))
        self.assertEqual(said[7], page('file_read', {'path': 'a'}), 'gone out of what is sent: said again from the record, not run')

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

    def test_every_tool_offered_has_a_schema_gemini_takes(self):
        """The gateway walk, 2026-11-19: Gemini behind the HIPAA AI gateway turned every tooled call down with a 400 - propose_email's top-level
        `anyOf` ("parameters schema should be of type OBJECT"), and an `items` object requiring fields it never declared ("required properties
        are specified but schema properties are empty"). Every schema a turn is offered, its later tools too, is one Gemini takes."""
        from taskuary import agenttools
        def post(url, json=None, headers=None, timeout=None):
            r = mock.Mock(status_code=200); r.json.return_value = agenttools.rpc(json, lambda n, a: '', ()); return r
        tools = apiagent.tools_for(1, 'g', True, post=post) + list(apiagent.DEFERRED[(1, 'g')].values())
        def walk(x, name):
            if isinstance(x, list): return [walk(v, name) for v in x]
            if not isinstance(x, dict): return
            bad = {'anyOf', 'oneOf', 'allOf'} & set(x)
            assert not [k for k in bad if not all(isinstance(b, dict) and 'type' in b for b in x[k])], (name, x)
            assert set(x.get('required') or ()) <= set(x.get('properties') or {}), (name, x)
            assert not {'additionalProperties', '$schema', 'default', 'title'} & set(x), (name, x)
            for k, v in x.items(): [walk(s, name) for s in v.values()] if k == 'properties' else walk(v, name)
        assert {'propose', 'sign_form'} <= {t['function']['name'] for t in tools}
        for t in tools:
            assert t['function']['parameters']['type'] == 'object'; walk(t['function']['parameters'], t['function']['name'])
        # ...the server still holds a call to what one card needs: the schema the model reads is not the check
        with self.assertRaisesRegex(ValueError, 'not given'): agenttools.fit('read_message', {})
        with self.assertRaisesRegex(ValueError, '`kind` was not given'): agenttools.call(MemoryStore(), 1, 'propose', {'subject': 'Q3'}, {})

    def test_tools_are_offered_as_the_work_needs_them_and_a_loaded_one_is_added_at_the_end(self):
        """The owner's rule, "model sees all, tools progressive" (2026-11-10: "the ai limits as much as possible to use ai"): every schema rode
        on every step. The core is offered, a line each; the rest are found with find_tools, which appends what it finds, so what went before is the
        same bytes - and the whole list stays under TOOL_CHARS (the owner, 2026-11-15: "MCP-style tools with simple JSON")."""
        from taskuary import agenttools
        def post(url, json=None, headers=None, timeout=None):
            r = mock.Mock(status_code=200); r.json.return_value = agenttools.rpc(json, lambda n, a: f'{n} answered', ()); return r
        whole = len(json.dumps(apiagent.tools_for(1, 'p', True, post=post) + list(apiagent.DEFERRED[(1, 'p')].values())))
        core = apiagent.tools_for(1, 'p', True, post=post)
        names = [t['function']['name'] for t in core]
        assert {'search_messages', 'read_message', 'propose', 'show', 'draw_image', 'file_write'} <= set(names) and 'calendar' not in names
        assert names[-1] == 'find_tools' and len(json.dumps(core)) < whole * 0.5
        TOOL_CHARS = 7_000                # what every call carries before a word of the job: was ~15,000 (23 tools at ~650 characters); end_turn and ask_owner ride in it since the prompt's protocols became tools, and every act that raises a card since walk 10 (2026-11-23)
        assert len(json.dumps(core, separators=(',', ':'))) < TOOL_CHARS
        said = apiagent.find(1, 'p', list(core), 'meeting calendar')
        assert 'set_up_meeting:' in said and 'calendar:' in said, 'found by words, each with its whole instructions'
        seen, steps = [], iter([{'tool_calls': [{'id': 'a', 'function': {'name': 'find_tools', 'arguments': '{"query": "calendar"}'}}]},
                                {'tool_calls': [{'id': 'b', 'function': {'name': 'set_up_meeting', 'arguments': '{}'}}]}, {'content': 'Booked.'}])
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): seen.append([t['function']['name'] for t in tools]); return next(steps)
        with mock.patch.object(apiagent, 'run_tool', return_value='done'):
            self.assertEqual(apiagent.turn(Brain(), MemoryStore(), 1, 'p', 'sys', 'book it', 500, tools=core), 'Booked.')
        assert seen[1] == names + ['calendar'] and seen[2] == names + ['calendar', 'set_up_meeting'], 'appended, never reordered'

    def test_an_invoice_job_of_25_steps_stays_under_the_bound_on_every_call(self):
        """The gateway's own per-call log for an outside client (2026-11-15): one invoice job, 139 calls at 35-60K prompt tokens, 6.4M in all.
        The bound counted the messages' text alone - not the tools' schemas, not the arguments of the agent's own calls - so every whole file
        it wrote (an invoice, a PowerShell script) rode on every call after it. The job's shape: a real-size template and timesheet read, the
        invoice written whole four times and edited between, reads in parallel, a page searched, across two turns."""
        import tempfile
        from taskuary import agenttools, officefiles
        d = Path(tempfile.mkdtemp())
        tpl, xl, out = d / 'invoice-template.docx', d / 'timesheet.xlsx', d / 'invoice-october.docx'
        officefiles.write(tpl, '\n'.join(['# INVOICE', 'Bill to: [client]', 'Date | Session | Hours | Rate | Amount', '[date] | [session] | [hours] | [rate] | [amount]',
                                          *[f'Terms {i}: payment within thirty days of the invoice date, by bank transfer.' for i in range(30)]]))
        officefiles.write(xl, '\n'.join(['Date | Person | Session | Hours | Rate', *[f'2026-10-{1 + i % 28:02d} | Erin Blake | Team coaching item {i} | {1 + i % 3} | 120'
                                                                                    for i in range(300)]]))
        full = lambda r: '\n'.join(['# INVOICE', 'Bill to: Payworth', 'Date | Session | Hours | Rate | Amount',
                                    *[f'2026-10-{1 + i % 28:02d} | Team coaching item {i} | {1 + i % 3} | {r} | {(1 + i % 3) * r}' for i in range(90)]])
        P = lambda n, **a: (n, a)
        turn1 = [[P('file_read', path=str(tpl)), P('file_read', path=str(xl))], [P('search_messages', query='invoice Payworth')],
                 [P('web_search', query='Payworth billing address')], [P('file_write', path=str(out), text=full(120))], [P('file_read', path=str(out))],
                 *[[P('file_edit', path=str(out), old=f'Team coaching item {i}', new=f'Team coaching, item {i}')] for i in (81, 82, 83)],
                 [P('file_write', path=str(out), text=full(125))], [P('file_read', path=str(out)), P('file_read', path=str(xl))], None]
        turn2 = [[P('file_write', path=str(out), text=full(130))], *[[P('file_edit', path=str(out), old=f'Team coaching item {i}', new=f'Coaching {i}')] for i in (81, 82, 83)],
                 [P('file_read', path=str(out))], [P('web_search', query='Payworth accounts payable')], [P('file_write', path=str(out), text=full(135))],
                 [P('file_read', path=str(out)), P('file_read', path=str(xl))], [P('file_read', path=str(tpl))], [P('search_messages', query='Paula rate')],
                 [P('web_search', query='Payworth tax number')], [P('show', files=[str(out)])],
                 [P('propose_email', to='billing@vendor.example', subject='October invoice', text='The October invoice is attached.', attach=[str(out)])], None]
        plan, seen = [*turn1, *turn2], []
        class Model:
            def chat(self, msgs, tools, max_tokens, **kw):
                seen.append((json.loads(json.dumps(msgs)), json.loads(json.dumps(tools))))
                step = plan.pop(0)
                if step is None: return {'content': 'Filled; the rate is the open question.' if plan else 'Filled, and the email is drafted.'}
                return {'tool_calls': [{'id': f'c{len(seen)}-{j}', 'function': {'name': n, 'arguments': json.dumps(a)}} for j, (n, a) in enumerate(step)],
                        'provider_specific_fields': {'thought_signatures': [f'sig{len(seen)}' + 'A' * 3000]}}      # Gemini's, handed back as it came
        def post(url, json=None, headers=None, timeout=None):
            r = mock.Mock(status_code=200); r.json.return_value = agenttools.rpc(json, lambda n, a: f'{n}: ' + 'a found line of mail. ' * 120, ()); return r
        real = apiagent.run_tool
        def run(s, t, i, n, a):
            if n == 'web_search': return apiagent._cut('\n'.join(f'{a["query"]} - result {k}: ' + 'what the page says ' * 6 for k in range(200)))
            if n in apiagent.LOCAL and n != 'show': return real(s, t, i, n, a)
            return f'{n} done.'
        system = 'You are the agent on this task. ' * 1_000           # a fresh install's system prompt is ~33,000 characters (measured)
        task = 'TASK TQ-0001\nTITLE: October invoice\n' + 'Paula asks for the October invoice from the timesheet. ' * 60
        tools, kept = apiagent.tools_for(1, 'inv', False, post=post), []
        try:
            with mock.patch.object(apiagent, 'run_tool', side_effect=run):
                apiagent.turn(Model(), MemoryStore(), 1, 'inv', system, task, 500, tools=tools, history=kept)
                apiagent.turn(Model(), MemoryStore(), 1, 'inv', system, 'go on - the rate is 130', 500, tools=tools, history=kept)
        finally: apiagent.forget(1, 'inv')
        # ...what a model READS: a thought signature is carried back whole (the model needs it) but is never read as tokens
        read = lambda m: [{k: v for k, v in x.items() if k != 'provider_specific_fields'} for x in m]
        size = lambda m, t: len(json.dumps({'messages': read(m), 'tools': t}, separators=(',', ':'), ensure_ascii=False))
        self.assertTrue(all(f'sig{k}A' in json.dumps(seen[-1][0]) for k in range(13, 24)), "this turn's signatures go back, every one")
        sizes = [size(m, t) for m, t in seen]
        self.assertEqual(len(seen), 25)
        # FIRST: the system, the tools and the task - nothing else rides on a call before the work begins
        self.assertLess(sizes[0], len(system) + len(task) + len(json.dumps(tools)) + 500)
        # EVERY CALL, the WHOLE of it (tools and the calls' own arguments counted), under the bound
        self.assertLessEqual(max(sizes), apiagent.REQUEST_CHARS, f'calls over the bound: {[s for s in sizes if s > apiagent.REQUEST_CHARS]}')
        # ...and a file the agent wrote whole goes once, not on every call after it
        self.assertLessEqual(max(json.dumps(m).count('Coaching 89 |') + json.dumps(m).count('item 89 | 3 | 1') for m, _ in seen[-3:]), 2)
        # THE PREFIX - system, then the tools offered first - is the same bytes on every call (the provider's cache)
        self.assertTrue(all(m[0] == seen[0][0][0] and t[:len(tools)] == seen[0][1][:len(tools)] for m, t in seen))
        # ...and the WORK, what the calls carried beyond that prefix: under WORK a call on average. This job sent ~27,000 a call before (the
        # files it wrote, again and again) and ~18,000 after; the prefix itself is the provider's cache to serve
        WORK = 22_000
        self.assertLess(sum(s - sizes[0] for s in sizes) / len(sizes), WORK)

    def test_the_line_that_stands_for_text_sent_earlier_is_never_written(self):
        """The real run on gemini-2.5-pro (2026-11-15): shown its earlier file_edit with `new` shortened to a line, the model made the call again
        with that line as `new`, and the line went into the invoice. A call carrying it is refused before it runs, and says what to do."""
        import tempfile
        f = Path(tempfile.mkdtemp()) / 'invoice.txt'; f.write_text('Rows: [rows]\n', encoding='utf-8')
        line = json.loads(apiagent._slim(json.dumps({'path': str(f), 'old': '[rows]', 'new': 'a session row. ' * 40})))['new']
        self.assertIn(apiagent.SLIMMED, line)
        with self.assertRaisesRegex(ValueError, 'send the full text itself'):
            apiagent.run_tool(MemoryStore(), 1, 'sl', 'file_edit', {'path': str(f), 'old': '[rows]', 'new': line})
        self.assertEqual(f.read_text(encoding='utf-8'), 'Rows: [rows]\n')

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
        with mock.patch.object(bv, 'installed', return_value=True), mock.patch.object(bv, 'state', return_value={'open': True}), \
             mock.patch('taskuary.browsergate.check', return_value=held), mock.patch('taskuary.browsergate._run') as ran:
            said = apiagent.run_tool(MemoryStore(), 1, 's', 'browser_click', {'ref': '@e4'})
        self.assertIn('held this for the owner', said)
        ran.assert_not_called()


class TheSessionTests(unittest.TestCase):
    """The general agent's turn on an API card: hands where it can call tools, the next real step as a question where it cannot."""

    def _turn(self, brain, installed=True, toolbox=()):
        from taskuary import general, llm as llm_mod
        self._s = s = MemoryStore()
        self._tid = tid = s.create_task({'Title': 'Read the denials on the scheduling portal', 'Summary': 'go', 'Kind': 'general', 'Status': 'open'}, 'owner')
        session = general.GeneralSession(s, tid)
        session.pick, session.provider, session.model = 'connector:1', 'HIPAA AI', ''
        with mock.patch.object(llm_mod, 'build_llm', return_value=brain), mock.patch.object(bv, 'installed', return_value=installed), \
             mock.patch.object(bv, 'state', return_value={'open': False}), \
             mock.patch.object(apiagent, 'taskuary_tools', return_value=[apiagent._fn(n, n, apiagent._S({})) for n in toolbox]):
            session.send_prompt('log into the scheduling portal and read the denials', echo=False)
        return s, tid

    def test_a_turn_stopped_while_the_card_answered_files_nothing(self):
        """The audit, 2026-11-10: Remind me (or the x) set the stop while a card's one call was out; its answer came back after it and was
        filed as the turn - a CLI is killed under it, a call cannot be. Stopped is stopped: no answer filed, the turn ends stopped."""
        from taskuary import general
        box = {}
        class Brain:
            def __call__(self, *a, **kw): box['session'].stop(); return 'The plan is drafted.'
        s = MemoryStore()
        tid = s.create_task({'Title': 'Plan the offsite', 'Summary': 'go', 'Kind': 'general', 'Status': 'open'}, 'owner')
        box['session'] = session = general.GeneralSession(s, tid)
        session.pick, session.provider, session.model = 'connector:1', 'Northwind AI', ''
        with mock.patch.object(llm, 'build_llm', return_value=Brain()), mock.patch.object(bv, 'installed', return_value=False), \
             mock.patch.object(bv, 'can_set_up', return_value=False), self.assertRaises(general.Stopped):
            session.send_prompt('draft a plan for the offsite', echo=False)
        self.assertEqual([c['Body'] for c in s.list_comments(tid) if c['ActorType'] == general.ASSISTANT_TYPE], [])

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
        self._turn(Brain(), toolbox=('search_messages', 'tick', 'propose'))
        self.assertNotIn("NONE OF TASKUARY'S TOOLS", seen[0]); self.assertNotIn(selfclose.SUMMARY_OPEN, seen[0])
        seen.clear(); self._turn(Brain())
        self.assertIn("NONE OF TASKUARY'S TOOLS", seen[0])         # ...a card without them writes its acts as marks

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
            self.assertIn('scheduling portal', heard[1][1]['content']); self.assertNotIn('scheduling portal', heard[1][3]['content'])
            self.assertIn('and which is the oldest?', heard[1][3]['content'])
            # ...and turned down on a later first call (too long for the model now), it is said again whole - once, on a fresh one
            class Full(Brain):
                def chat(self, msgs, *a, **kw):
                    if len(msgs) > 2: raise RuntimeError('hipaa_ai error 400 at https://gateway.example: too many tokens')
                    return super().chat(msgs, *a, **kw)
            with mock.patch.object(llm_mod, 'build_llm', return_value=Full()): session.send_prompt('go on', echo=False)
        self.assertEqual([m['role'] for m in heard[2]], ['system', 'user'])
        self.assertIn('scheduling portal', heard[2][1]['content']); self.assertIn('and which is the oldest?', heard[2][1]['content'])
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

    def test_a_kept_conversation_s_system_never_changes_and_what_changed_leads_the_next_turn(self):
        """A provider's prompt cache serves a prompt only up to its first changed byte: "the owner answered this themselves" landed in the
        system, and everything after it - the conversation kept too - was paid for again on the next turn (the owner, 2026-11-14: "every agent
        turn should not refresh the entire cache"). The system is the first turn's, byte for byte; his own reply is the next turn's event, once."""
        from taskuary import general, llm as llm_mod, selfclose
        heard = []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): heard.append((msgs[0]['content'], msgs[-1]['content'])); return {'content': 'Found it.'}
        s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
        tid = s.create_task({'Title': 'August export', 'Summary': 'Erin asks for the August export', 'Kind': 'general', 'Status': 'open'}, 'owner')
        mail = lambda i, who, at, body, **kw: s.add_message({'TaskId': tid, 'ExternalId': f'x-{i}', 'ConversationId': 'c1', 'Channel': 'email',
                                                             'SourceName': 'alex@northwind.example', 'Subject': 'August export', 'FromName': who[0],
                                                             'FromEmail': who[1], 'SentAt': at, 'BodyText': body, 'Status': 'routed', **kw})
        mail(1, ('Erin Blake', 'erin@northwind.example'), '2026-11-06 09:00:00', 'Could you send the August export?')
        session = general.GeneralSession(s, tid)
        session.pick, session.provider, session.model = 'connector:1', 'HIPAA AI', ''
        with mock.patch.object(llm_mod, 'build_llm', return_value=Brain()), mock.patch.object(bv, 'installed', return_value=True), \
             mock.patch.object(bv, 'state', return_value={'open': False}), mock.patch.object(apiagent, 'taskuary_tools', return_value=[]):
            session.send_prompt('find the export', echo=False)
            mail(2, ('Alex Doyle', 'alex@northwind.example'), '2026-11-06 10:00:00', 'Sent it.', Direction='out')
            session.send_prompt('and the September one?', echo=False)
            session.send_prompt('and the October one?', echo=False)
        (a, _), (b, said), (c, again) = heard
        self.assertEqual(a, b); self.assertEqual(b, c)
        self.assertNotIn('Sent it.', b)
        self.assertIn("The owner's own message on the thread", said); self.assertIn('Sent it.', said)
        self.assertNotIn('Sent it.', again, 'said once')

    def test_a_model_that_refuses_its_tools_fails_the_turn_in_the_providers_words(self):
        """The gateway walk, 2026-11-19: the gateway turned the tools down (400) and the turn was asked again with none - the agent then told him
        it had no files, browser or shell, and to install a CLI. The turn fails, and he reads the provider's reason, never a tool-less agent."""
        from taskuary import conversation
        inner = json.dumps({'error': {'code': 400, 'message': 'Duplicate function declaration found: show', 'status': 'INVALID_ARGUMENT'}}, indent=2)
        why = json.dumps({'error': {'message': f'litellm.BadRequestError: Vertex_aiException BadRequestError - {inner}', 'type': 'invalid_request_error'}})
        class Brain:
            def __call__(self, *a, **kw): raise AssertionError('never asked again without its tools')
            def chat(self, *a, **kw): raise RuntimeError(f'hipaa_ai error 400 at https://gateway.example/v1/chat/completions: {why}')
        try: s, tid = self._turn(Brain(), toolbox=('search_messages', 'show'))
        except RuntimeError: s, tid = self._s, self._tid
        [t] = [x for x in conversation.items(s, tid)['items'] if x['kind'] == 'turn']
        self.assertIn('refused the request - it said: Duplicate function declaration found: show', t['fail'])
        self.assertNotIn('litellm', t['fail']); self.assertNotIn('{', t['fail'])

    def test_the_clis_toolbox_rides_with_the_browser(self):
        seen = []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): seen.append((msgs[0]['content'], [t['function']['name'] for t in tools])); return {'content': 'ok'}
        self._turn(Brain(), toolbox=('search_messages', 'propose', 'show'))
        system, names = seen[0]
        self.assertIn(apiagent.TOOLS_BRIEF, system)
        self.assertEqual(names.count('show'), 1, "the server's show, never a second")
        self.assertTrue({'search_messages', 'propose', 'browser_open'} <= set(names))

    def test_a_card_with_tools_is_told_the_owners_systems_and_mailboxes_as_a_cli_is(self):
        # design round 2, 2026-11-18: one prompt for every road - a CLI with hands is told the owner's connections and the mailboxes it sends
        # from (docsync.agent_systems); an AI card's agent with the same tools was not, and called around for them
        from taskuary import docsync
        SYSTEMS = 'YOUR SYSTEMS - Northwind books (connector_id 4). MAILBOXES you can send FROM: alex@northwind.example (gmail)'
        seen = []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): seen.append(msgs[0]['content']); return {'content': 'ok'}
        with mock.patch.object(docsync, 'agent_systems', return_value=SYSTEMS):
            self._turn(Brain(), toolbox=('search_messages', 'run_system'))
        self.assertIn(SYSTEMS, seen[0])

    def test_a_card_with_the_email_tool_hears_the_tool(self):
        # the agent walk, 2026-11-10: one road for an email by what the session has
        from taskuary import selfclose
        seen = []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): seen.append(msgs[0]['content']); return {'content': 'ok'}
        self._turn(Brain(), toolbox=('search_messages', 'propose', 'show'))
        self.assertNotIn(selfclose.DRAFT_OPEN, seen[0])

    def test_no_browser_but_a_toolbox_still_loops_and_says_set_the_browser_up(self):
        seen = []
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): seen.append((msgs[0]['content'], [t['function']['name'] for t in tools])); return {'content': 'ok'}
        self._turn(Brain(), installed=False, toolbox=('search_messages',))
        system, names = seen[0]
        self.assertIn('NO BROWSER FOR AGENTS YET', system)
        self.assertNotIn('browser_open', names)

    def test_a_small_text_file_reaches_a_card_whole_and_a_sheet_it_writes_out_is_a_file(self):
        """The API walk, 2026-11-18: a two-line totals.py on his line reached the card as a path ("I could not open the attached totals.py from
        here"), and a spreadsheet asked of it was a CSV in its words - "no spreadsheet file anywhere". The file's text rides in the message,
        and a block it writes out under a file name is saved to the task's files."""
        from taskuary import config, general, outputs
        up = config.home() / 'attachments' / 'line' / 'totals.py'; up.parent.mkdir(parents=True, exist_ok=True)
        up.write_text('def total(xs):' + chr(10) + '    return int(sum(xs))' + chr(10), encoding='utf-8')
        heard = []
        def brain(system, user, **kw):
            heard.append(user)
            return 'Here are the quotes.' + chr(10) + '```xlsx file=quotes.xlsx' + chr(10) + 'Caterer | Per head' + chr(10) + 'Ray\'s Kitchen | 42' + chr(10) + '```'
        s = MemoryStore()
        tid = s.create_task({'Title': 'Caterers for the offsite', 'Summary': 'go', 'Kind': 'general', 'Status': 'open'}, 'owner')
        session = general.GeneralSession(s, tid)
        session.pick, session.provider, session.model = 'connector:1', 'HIPAA AI', ''
        with mock.patch.object(llm, 'build_llm', return_value=brain), mock.patch.object(bv, 'installed', return_value=False), \
             mock.patch.object(bv, 'can_set_up', return_value=False):
            session.send_prompt(general.with_files('why does this round wrong? and price three caterers as a sheet', [str(up)]), echo=False)
        self.assertIn('    return int(sum(xs))', heard[0])
        self.assertTrue((outputs.folder(tid) / 'quotes.xlsx').is_file())
        said = [c['Body'] for c in s.list_comments(tid) if c['ActorType'] == general.ASSISTANT_TYPE][-1]
        self.assertIn('quotes.xlsx', said); self.assertNotIn('```', said)

    def _down_session(self, s, tid):
        from taskuary import general
        session = general.GeneralSession(s, tid); session.pick, session.provider, session.model = 'connector:1', 'HIPAA AI', ''
        return session

    def _patched(self, brain):
        from contextlib import ExitStack
        st = ExitStack()
        for p in (mock.patch.object(llm, 'build_llm', return_value=brain), mock.patch.object(bv, 'installed', return_value=False),
                  mock.patch.object(bv, 'can_set_up', return_value=False), mock.patch.object(apiagent, 'taskuary_tools', return_value=[]),
                  mock.patch('taskuary.blackboard.drain_later')):
            st.enter_context(p)
        return st

    def test_while_the_provider_is_down_the_failure_is_one_plain_line_queued_to_try_again(self):
        """The API walk, 2026-11-18/19: during the provider's outage every line he typed added another "⚠ HIPAA AI: Gemini ... over its quota at
        the provider (it answered 429) - raise the quota there..." to the chat, and nothing tried again until he typed. One state: one plain line
        that says when it is tried again, and the turn waits in the start queue. Design round 5, I3: the line was then changed in place
        ("trying again at 5:11" read "5:24" later) - each try that fails is its own dated line under the one before, and none is rewritten."""
        from taskuary import conversation, funnel, general
        class Down:
            def chat(self, *a, **kw): raise llm.QuotaSpent(llm.QUOTA_LINE.format(name='HIPAA AI', model='Gemini 4'))
        s = MemoryStore()
        tid = s.create_task({'Title': 'Weekly spend summary', 'Summary': 'go', 'Kind': 'general', 'Status': 'open'}, 'owner')
        with self._patched(Down()):
            for line in ('set up the Monday summary', 'any luck?', 'Try again.'):
                try: self._down_session(s, tid).send_prompt(line, echo=False)
                except Exception: pass
        failed = [general.failed_line(c['Body'])[1] for c in s.list_comments(tid) if c['ActorType'] == general.ASSISTANT_TYPE and general.failed_line(c['Body'])[1]]
        self.assertEqual(len(failed), 3, failed)
        for f in failed: self.assertIn('over its quota', f); self.assertIn('trying again at', f); self.assertNotIn('429', f)
        items = [x for x in conversation.items(s, tid)['items'] if x['kind'] == 'turn']
        self.assertEqual([x['fail'] for x in items], failed, 'each try stands as its own failed turn, in the order it failed')
        q = s.get_dispatch(tid)
        self.assertEqual((q['Turn'], q['State']), (general.RETRY_TURN, 'retrying'))
        self.assertEqual(funnel.idle_state(s, tid)['line'], failed[-1])

    def test_the_queued_try_runs_by_itself_and_its_answer_ends_the_outage(self):
        "Rule 4: a start that cannot happen now is queued and retried - the try is Taskuary's, never a line in his name; answered, nothing is owed."
        from taskuary import blackboard, general
        class Down:
            def chat(self, *a, **kw): raise llm.ProviderDown('hipaa_ai error 503 at https://gateway.example after 3 tries: overloaded')
        heard = []
        class Up:
            def chat(self, msgs, tools, max_tokens, **kw): heard.append(str(msgs[-1]['content'])); return {'content': 'The Monday summary is set up.'}
        s = MemoryStore()
        tid = s.create_task({'Title': 'Weekly spend summary', 'Summary': 'go', 'Kind': 'general', 'Status': 'open'}, 'owner')
        with self._patched(Down()):
            try: self._down_session(s, tid).send_prompt('set up the Monday summary', echo=False)
            except Exception: pass
        self.assertIn("The AI didn't answer - trying again at", [c['Body'] for c in s.list_comments(tid)][-1])
        s._exec("UPDATE dispatchq SET NextAt='2000-01-01 00:00:00' WHERE TaskId=?", (tid,))
        handed = []
        with mock.patch.object(general, 'retry_turn', side_effect=lambda st, t: handed.append(t)), mock.patch('taskuary.ingest.has_room', return_value=True):
            blackboard.drain(s)
        self.assertEqual(handed, [tid])                           # the drain hands the row to the try, and keeps it
        self.assertTrue(s.get_dispatch(tid))
        import threading
        # ...and what the first try made is named to the try (the walk, 2026-11-22: a fresh conversation rebuilt a deck it had already written)
        from taskuary import outputs
        outputs.folder(tid).mkdir(parents=True, exist_ok=True); (outputs.folder(tid) / 'monday-summary.md').write_text('# Monday', encoding='utf-8')
        with self._patched(Up()), mock.patch.object(general, 'start_session', side_effect=lambda *a, **kw: self._down_session(s, tid)):
            self.assertTrue(general.retry_turn(s, tid))
            for t in [t for t in threading.enumerate() if t.name == f'retry-{tid}']: t.join(20)
        self.assertIsNone(s.get_dispatch(tid))
        bodies = [c['Body'] for c in s.list_comments(tid)]
        self.assertEqual(bodies[-1], 'The Monday summary is set up.')
        self.assertEqual(bodies.count('set up the Monday summary'), 1)       # his line once, never again in his name
        self.assertIn(general.RETRY_ASK, heard[0]); self.assertIn('monday-summary.md', heard[0])

    def test_the_turn_that_answers_after_an_outage_is_clocked_from_its_own_try(self):
        """The API walk, 2026-11-19: a short ask answered after the outage read "ran 17m 18s" - its clock counted from the first hand-over
        since the last answer, a try that failed in the outage and filed nothing new (the one failure line stands in place). Each try that
        failed ends there: the turn that answers counts from its own try."""
        import time
        from taskuary import conversation, general
        class Down:
            def chat(self, *a, **kw): raise llm.QuotaSpent(llm.QUOTA_LINE.format(name='HIPAA AI', model='Gemini 4'))
        class Up:
            def chat(self, *a, **kw): return {'content': 'The posts are drafted.'}
        s = MemoryStore()
        tid = s.create_task({'Title': 'Launch posts', 'Summary': 'go', 'Kind': 'general', 'Status': 'open'}, 'owner')
        with self._patched(Down()):
            for line in ('draft the launch posts', 'any luck?'):
                try: self._down_session(s, tid).send_prompt(line, echo=False)
                except Exception: pass
                time.sleep(0.3)
        last_try = time.time()
        with self._patched(Up()):
            self._down_session(s, tid).send_prompt(general.RETRY_ASK, as_owner=False, echo=False)
        turn = [x for x in conversation.items(s, tid)['items'] if x['kind'] == 'turn'][-1]
        self.assertEqual(turn['text'], 'The posts are drafted.')
        self.assertGreaterEqual(turn['started'], last_try - 0.05)

    def test_a_failed_turn_leaves_a_draft_that_is_still_good_live(self):
        """The API walk, 2026-11-19: Paula's reply was drafted; he asked for a PDF too, the AI failed, and the draft's Send stood greyed for 43
        minutes while turn after turn failed. A card is set aside as its agent hears the input; a turn the AI never answered read past nothing."""
        from taskuary import general, proposals
        class Down:
            def chat(self, *a, **kw): raise llm.NoAnswer('hipaa_ai: the model ran out of room before answering, even with 8000 tokens (finish_reason length)')
        s = MemoryStore()
        tid = s.create_task({'Title': 'October spend summary for Paula', 'Summary': 'go', 'Kind': 'general', 'Status': 'open'}, 'owner')
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The summary is drafted for Paula.')
        rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Paula - the total is 103,190.', 'Reason': 'reply'})
        s._exec("UPDATE review SET CreatedAt=datetime(CreatedAt,'-5 minutes') WHERE ReviewId=?", (rid,))
        s._exec("UPDATE comment SET CreatedAt=datetime(CreatedAt,'-5 minutes') WHERE TaskId=?", (tid,))
        with self._patched(Down()):
            try: self._down_session(s, tid).send_prompt('make it a one-page PDF too', echo=False)
            except Exception: pass
        self.assertEqual(s.get_review(rid)['Status'], 'pending')
        self.assertNotIn(rid, proposals.written_past(s, tid))
        self.assertIn('The AI stopped before it answered - trying again at', [c['Body'] for c in s.list_comments(tid)][-1])

    def test_a_card_that_takes_no_tools_is_offered_only_the_ways_that_are_here(self):
        """The API walk, 2026-11-18: every answer of a card that takes no tools ended "connect an AI that can use tools ... or switch this task
        to one?" - with no other AI on the computer, and on asks no browser served. It is told it has words alone, and the AIs really here."""
        from taskuary import capabilities
        seen = []
        def brain(system, user, **kw): seen.append(system); return 'Here is the plan.'
        with mock.patch.object(capabilities, 'other_ais', return_value=[]): self._turn(brain)
        self.assertIn(capabilities.HANDS['none'], seen[0]); self.assertIn('No other AI is connected here', seen[0])
        self.assertNotIn('switch this task to one?', seen[0]); self.assertNotIn(apiagent.BRIEF, seen[0])
        with mock.patch.object(capabilities, 'other_ais', return_value=['Claude Code']): self._turn(brain)
        self.assertIn('Another AI could do this task: Claude Code - he picks it in the Agent menu on this task.', seen[1])

    def test_what_it_states_can_be_checked_so_it_is_told_the_day_the_addresses_and_the_roads_here(self):
        """The API walk, 2026-11-19: an email said "Thursday, March 12" (a Friday); "I guessed Ray's address" of a man whose invite was on the
        task; "there is no button or setting you can press" with a CLI's install one page away; "I cannot schedule this" in an app that runs
        routines. The agent is told the day, the address each person on the task wrote from, and the roads that are here."""
        from datetime import datetime
        from taskuary import agents, capabilities, general
        seen = []
        def brain(system, user, **kw): seen.append(system); return 'Done.'
        s = MemoryStore()
        s.set_setting('owner_email', 'alex@northwind.example', 'owner')
        tid = s.create_task({'Title': 'Vendor review time', 'Summary': 'go', 'Kind': 'general', 'Status': 'open'}, 'owner')
        s.add_message({'TaskId': tid, 'Channel': 'email', 'ConversationId': 'c-ray', 'FromName': 'Ray Colton', 'FromEmail': 'ray@northwind.example',
                       'Subject': 'Vendor review', 'BodyText': 'Invitation: vendor review, Thursday 2-3pm', 'Status': 'routed'})
        session = general.GeneralSession(s, tid); session.pick, session.provider, session.model = 'connector:1', 'HIPAA AI', ''
        with mock.patch.object(llm, 'build_llm', return_value=brain), mock.patch.object(bv, 'installed', return_value=False), \
             mock.patch.object(bv, 'can_set_up', return_value=False), mock.patch.object(capabilities, 'other_ais', return_value=[]), \
             mock.patch.object(agents, 'cli_ready', return_value=False):
            session.send_prompt('can we move it to Friday?', echo=False)
        self.assertIn(f"TODAY: {datetime.now().strftime('%A %d %B %Y')}", seen[0])
        self.assertIn('Ray Colton <ray@northwind.example>', seen[0])
        self.assertIn('An AI CLI - a shell, files and a browser on this computer - can be installed from', seen[0])
        # ...and no hint at a tool or a setting it was not asked about (walk 9, 2026-11-23: a routine and Developer mode on every task)
        self.assertNotIn('save_routine', seen[0]); self.assertNotIn('Developer mode', seen[0])


class TheToolboxTests(unittest.TestCase):
    """Taskuary's own tools reach an API brain through the SAME server a CLI session's MCP does - its token and task proof, its gates."""

    def test_the_listing_is_the_servers_with_the_sessions_headers_and_a_gateway_safe_schema(self):
        sent = []
        def post(url, json, headers, timeout):
            sent.append((url, json, headers))
            return _R({'jsonrpc': '2.0', 'id': 1, 'result': {'tools': [{'name': 'search_messages', 'description': 'Search saved mail.',
                       'inputSchema': {'type': 'object', 'additionalProperties': False, 'properties': {'words': {'type': 'string', 'default': ''}}}}]}})
        got = [t for t in apiagent.tools_for(7, 'sid-7', False, post=post) if t['function']['name'] == 'search_messages']      # ...made safe where every tool is
        url, body, h = sent[0]
        self.assertIn('/api/mcp?task=7', url); self.assertEqual(body['method'], 'tools/list')
        from taskuary import guard
        self.assertIn('X-Taskuary-Token', h); self.assertIn(guard.TASK_HDR, h)
        self.assertEqual(got[0]['function']['parameters'], {'type': 'object', 'properties': {'words': {'type': 'string'}}})

    def test_what_may_be_answered_again_from_the_turn_is_the_catalogues_own_read_only_closed_world_marks(self):
        from taskuary import agenttools
        def post(url, json, headers, timeout): return _R({'jsonrpc': '2.0', 'id': 1, 'result': {'tools': agenttools.listing()}})
        try:
            apiagent.taskuary_tools(7, 'r', post=post)
            reads = apiagent.READS[(7, 'r')]
            self.assertTrue({'my_task', 'read_message', 'search_messages', 'person'} <= reads)
            self.assertFalse(reads & {'run_system', 'tick', 'propose', 'todos'}, 'an outside system, or anything that moves, runs every time')
        finally: apiagent.forget(7, 'r')
        self.assertNotIn((7, 'r'), apiagent.READS)

    def test_a_property_named_like_a_dropped_key_is_kept(self):
        # a gateway's Gemini refused the whole turn: "required fields ['title'] are not defined" once `title` the FIELD was cut (2026-11-09)
        got = apiagent.portable({'type': 'object', 'title': 'x', 'properties': {'title': {'type': 'string', 'title': 'T'}}, 'required': ['title', 'gone']})
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
                with self.assertRaises(ValueError) as e: apiagent.run_tool(MemoryStore(), 9, 's', 'merge_pr', {})
                self.assertIn('find_tools names the ones you have', str(e.exception))         # ...said with where its tools are
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
        from taskuary import outputs
        self.assertEqual(Path(apiagent.workdir(self.s, self.tid)), outputs.work_folder(self.tid))      # ...its own (walk 9)

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

    def test_a_word_invoice_template_is_filled_by_its_own_file_tools(self):
        """An outside user's ask (2026-11-15, "it says it took 25 min"): fill an invoice template with a month's sessions and mail it. A
        .docx was text to file_edit (a decode error) and file_write made a file Word cannot open, so the agent spliced the template's XML
        in PowerShell, a script a step. Now its line-item row, read as `a | b | c`, becomes one row per session - and the template keeps its look."""
        from taskuary import officefiles
        d = Path(apiagent.workdir(self.s, self.tid)); (d / 'Invoice template.docx').write_bytes(officefiles.docx(
            'Invoice number: {{NO}}\n| Date | Units | Amount |\n| {{DATE}} | {{UNITS}} | {{AMOUNT}} |\nTotal due: {{TOTAL}}'))
        shown = self.run_('file_read', path='Invoice template.docx')
        self.assertIn('{{DATE}} | {{UNITS}} | {{AMOUNT}}', shown)
        said = self.run_('file_edit', path='Invoice template.docx', old='{{DATE}} | {{UNITS}} | {{AMOUNT}}',
                         new='2026-10-01 | 4 | 60.00\n2026-10-02 | 6 | 90.00\n2026-10-03 | 2 | 60.00', save_as='Invoice INV-2026-10.docx')
        self.assertIn('3 rows', said)
        self.run_('file_edit', path='Invoice INV-2026-10.docx', old='{{NO}}', new='INV-2026-10')
        self.run_('file_edit', path='Invoice INV-2026-10.docx', old='{{TOTAL}}', new='$210.00')
        got = self.run_('file_read', path='Invoice INV-2026-10.docx')
        for line in ('Invoice number: INV-2026-10', 'Date | Units | Amount', '2026-10-01 | 4 | 60.00', '2026-10-03 | 2 | 60.00', 'Total due: $210.00'):
            self.assertIn(line, got)
        self.assertIn('{{DATE}}', self.run_('file_read', path='Invoice template.docx'))          # save_as left the template as it was
        with self.assertRaises(ValueError): self.run_('file_edit', path='Invoice INV-2026-10.docx', old='60.00', new='61.00')   # twice: say so

    def test_an_excel_invoice_is_written_and_its_template_row_filled_with_the_total_widened(self):
        from openpyxl import Workbook, load_workbook
        d = Path(apiagent.workdir(self.s, self.tid))
        self.assertIn('Excel workbook', self.run_('file_write', path='hours.xlsx', text='Date | Units | Rate | Amount\n2026-10-01 | 4 | 15.00 | =B2*C2'))
        ws = load_workbook(d / 'hours.xlsx').active
        self.assertEqual([ws['B2'].value, ws['C2'].value, ws['D2'].value], [4, 15.0, '=B2*C2'])
        NL = chr(10)
        # ...and each formula carries what it comes to, so a viewer that works nothing out shows the number (the 2026-11-18 walk: a caterers'
        # sheet's "Est. Total for 40" stood empty for every row)
        self.run_('file_write', path='caterers.xlsx', text='Caterer | Per head | Total for 40' + NL + 'Clover | 17.50 | =B2*40' + NL + 'Flour | 17.95 | =B3*40' + NL +
                  'All | | =SUM(C2:C3)' + NL + 'Odd | | =VLOOKUP(A2,A2:C3,2)')
        shown = load_workbook(d / 'caterers.xlsx', data_only=True).active
        self.assertEqual([shown['C2'].value, shown['C3'].value, shown['C4'].value, shown['C5'].value], [700, 718, 1418, None])
        self.assertEqual(load_workbook(d / 'caterers.xlsx').active['C4'].value, '=SUM(C2:C3)')       # the formula stays the formula
        wb = Workbook(); ws = wb.active
        ws.append(['Date', 'Units', 'Rate', 'Amount']); ws.append(['2026-10-01', 4, 15, '=B2*C2']); ws.append([None, None, 'Total', '=SUM(D2:D2)'])
        wb.save(d / 'Invoice template.xlsx')
        self.assertIn('2026-10-01 | 4 | 15 | =B2*C2', self.run_('file_read', path='Invoice template.xlsx'))    # a formula no Excel worked out, as itself
        self.run_('file_edit', path='Invoice template.xlsx', old='2026-10-01 | 4 | 15 | =B2*C2',
                  new='2026-10-01 | 4 | 15\n2026-10-02 | 6 | 15\n2026-10-03 | 2 | 30', save_as='Invoice INV-2026-10.xlsx')
        ws = load_workbook(d / 'Invoice INV-2026-10.xlsx').active
        self.assertEqual([ws['A4'].value, ws['B4'].value, ws['C4'].value, ws['D4'].value], ['2026-10-03', 2, 30, '=B4*C4'])
        self.assertEqual([ws['C5'].value, ws['D5'].value], ['Total', '=SUM(D2:D4)'])
        self.assertIn('Total | =SUM(D2:D4)', self.run_('file_read', path='Invoice INV-2026-10.xlsx'))      # the total it can check, read back

    def test_a_one_page_pdf_with_a_bar_chart_and_a_deck_are_written_by_the_road_the_workbook_takes(self):
        """The API walk, design round 5 (2026-11-19): asked for a one-page PDF with a bar chart and a five-slide deck, the card's agent made the
        .xlsx, then said PDF and PowerPoint "require file generation tools ... AI CLI agents" and drew the chart in block characters. file_write
        makes both from the same text: a heading, points, a table, `chart:` over `label | number` lines, `---` between slides."""
        from pypdf import PdfReader
        NL = chr(10)
        text = NL.join(['# October vendor spend', 'Total $103,190 across 7 vendors.', '- The top five are 93.9%', '', 'chart: Spend by vendor',
                        'Payworth | 48210', 'Trainly | 21000', '', 'Vendor | Spend', 'Payworth | $48,210', '---', '# Concentration', '- Top five: 93.9%'])
        d = Path(apiagent.workdir(self.s, self.tid))
        self.assertIn('a PDF, 1 page', self.run_('file_write', path='October spend.pdf', text=text.replace('---', '')))
        pages = PdfReader(str(d / 'October spend.pdf')).pages
        self.assertEqual(len(pages), 1)
        got = pages[0].extract_text()
        for w in ('October vendor spend', 'Payworth', '48,210', 'Spend by vendor', '$48,210'): self.assertIn(w, got)
        self.assertNotIn('chart:', got); self.assertIn(' re f', pages[0].get_contents().get_data().decode('latin-1'), 'the bars are drawn, not typed')
        self.assertIn('a PowerPoint deck, 2 slides', self.run_('file_write', path='Leadership.pptx', text=text))
        read = self.run_('file_read', path='Leadership.pptx')
        for w in ('October vendor spend', 'Concentration', '48,210', 'Top five: 93.9%'): self.assertIn(w, read)
        try: import pptx
        except ImportError: pptx = None
        if pptx: self.assertEqual(len(pptx.Presentation(str(d / 'Leadership.pptx')).slides), 2)
        with self.assertRaisesRegex(ValueError, 'file_write it whole'): self.run_('file_edit', path='Leadership.pptx', old='Concentration', new='Share')

    def test_the_file_tools_are_offered_whole_not_behind_load_tools(self):
        "A model never shown file_write said it had no way to make the file (the same ask, on a card): making one is the hands' first job."
        with mock.patch.object(apiagent, 'taskuary_tools', return_value=[]):
            names = [t['function']['name'] for t in apiagent.tools_for(self.tid, 'sid-h', browser=False)]
        self.assertTrue({'file_write', 'file_edit'} <= set(names))
        apiagent.forget(self.tid, 'sid-h')

    def test_a_command_the_cli_would_run_runs_now_in_the_working_folder(self):
        class Done:
            pid, returncode = 4242, 0
            def communicate(self, timeout=None): return b'3 files', b''
        with mock.patch('taskuary.gate.check', return_value={}) as gate, mock.patch('taskuary.spawn.popen', return_value=Done()) as ran:
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
        with mock.patch('taskuary.gate.check', return_value={}), mock.patch('taskuary.spawn.popen', return_value=Building()), \
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
        with mock.patch.object(hooks, '_pane', return_value=T()), mock.patch('taskuary.gate.check', return_value={'x': 1}) as gate:
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
            self.assertTrue({'files_list', 'file_read', 'web_fetch', 'web_search'} <= apiagent.OFFERED[(self.tid, 'sid-h')])
            self.assertFalse({'file_write', 'file_edit', 'run_command', 'browser_open'} & apiagent.OFFERED[(self.tid, 'sid-h')])
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
            # ...and with neither, it reads a search engine's results page itself - never a failure handed to the agent (2026-11-20)
            seen = []
            with mock.patch.object(apiagent, '_hands', side_effect=lambda *x: seen.append(x[4]['url']) or 'PAGE results - Payworth pricing'):
                self.assertIn('Payworth', apiagent._search(s, 1, 'g', 'payroll pricing'))
            self.assertEqual(seen, [apiagent.SEARCH_PAGE + 'payroll%20pricing'])
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
        self.g.ON_CARD.add(self.tid)
        system, user = self.g._prompt(self.s, self.tid)
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


class WebFetchReadsWhatItFetchesTests(unittest.TestCase):
    """web_fetch reads "one public web page or file" - a page or a file read by the road a linked document takes (linkdocs), not decoded
    as UTF-8 whatever it is: a spreadsheet a vendor's page links to came back as zip bytes, a page in Latin-1 as mojibake, and a page that
    asked for a sign-in as a bare status code with nothing to do next."""

    def setUp(self):
        import io, threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from openpyxl import Workbook
        wb, buf = Workbook(), io.BytesIO()
        wb.active.append(['vendor', 'price']); wb.active.append(['Payworth', 4200]); wb.save(buf)
        files = {'/rates': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buf.getvalue(), 200),
                 '/about': ('text/html; charset=iso-8859-1', '<html><title>Über</title><body><p>Gail Moreno, Müller Straße</p></body></html>'.encode('latin-1'), 200),
                 '/portal': ('text/html', b'<html><body>Sign in required</body></html>', 401),
                 '/terms': ('text/html', '<html><head><meta charset="utf-8"></head><body><p>Zoë at Northwind signs.</p></body></html>'.encode(), 200),
                 '/download?id=3': ('application/pdf', pdf('Clause 9: payment within 45 days'), 200)}
        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                ct, body, code = files[self.path]
                self.send_response(code); self.send_header('Content-Type', ct); self.send_header('Content-Length', str(len(body))); self.end_headers()
                self.wfile.write(body)
            def log_message(self, *a): pass
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.srv.server_address[1]}'
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Compare two quotes', 'Summary': 'go', 'Kind': 'general', 'Status': 'open'}, 'owner')
        from taskuary import webguard
        for p in (mock.patch.object(webguard, 'check_url'), mock.patch.dict('os.environ', {'NO_PROXY': '127.0.0.1', 'no_proxy': '127.0.0.1'})):
            p.start(); self.addCleanup(p.stop)

    def tearDown(self): self.srv.shutdown(); self.srv.server_close()

    def fetch(self, path): return apiagent.run_tool(self.s, self.tid, 'sid-w', 'web_fetch', {'url': self.base + path})

    def test_a_spreadsheet_is_read_as_its_rows(self):
        got = self.fetch('/rates')
        self.assertIn('Payworth,4200', got)
        self.assertNotIn('PK', got.split('\n', 1)[1][:4])

    def test_a_page_in_its_own_charset_reads_as_written(self):
        self.assertIn('Müller Straße', self.fetch('/about'))

    def test_a_page_whose_charset_is_only_in_its_meta_reads_as_written(self):
        self.assertIn('Zoë at Northwind', self.fetch('/terms'))

    def test_a_pdf_at_an_address_with_no_extension_is_read_as_a_pdf(self):
        self.assertIn('Clause 9', self.fetch('/download?id=3'))

    def test_a_page_that_wants_a_sign_in_says_how_to_go_on(self):
        with self.assertRaises(ValueError) as e: self.fetch('/portal')
        self.assertIn('401', str(e.exception)); self.assertIn('browser_open', str(e.exception))


class TheRestOfALongAnswerTests(unittest.TestCase):
    """A long page or file was cut at CAP with "look again for the rest" - and no reading tool took a place to start, so looking again
    gave the same first part (and the turn served it as already read): a payroll table's last runs could never be reached. The cut says
    where to start, and the tool starts there."""

    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Payroll runs summary', 'Summary': 'go', 'Kind': 'general', 'Status': 'open'}, 'owner')
        rows = ''.join(f'- row "Run {1000 + i} 2026-03-{i % 28 + 1:02d} $201,345 paid" [ref=e{i}]\n' for i in range(600))
        self.page = rows + '- row "Run 9999 scheduled - THE LAST ONE" [ref=e999]\n'
        for p in (mock.patch.object(bv, 'installed', return_value=True), mock.patch.object(bv, 'state', return_value={'open': True}),
                  mock.patch('taskuary.browsergate._run', return_value=(0, self.page)),
                  mock.patch('taskuary.browsergate.address', return_value='https://portal.example/runs')):
            p.start(); self.addCleanup(p.stop)

    def walk(self, tool, **a):
        "Follow what each cut says, as a model would, until nothing is cut. Every part read, in order."
        import re
        parts = []
        for _ in range(20):
            out = apiagent.run_tool(self.s, self.tid, 'sid-l', tool, a)
            parts.append(out)
            m = re.search(r'\bfrom=(\d+)', out.rsplit('\n', 1)[-1])
            if not m: return parts
            a = {**a, 'from': int(m.group(1))}
        self.fail('the cut never ended')

    def test_a_long_page_is_read_to_its_end_part_by_part(self):
        parts = self.walk('browser_look', full=True)
        self.assertGreater(len(parts), 1)
        self.assertIn('THE LAST ONE', parts[-1])
        self.assertTrue(all(len(p) <= apiagent.CAP + 300 for p in parts))

    def test_a_long_file_is_read_to_its_end_part_by_part(self):
        apiagent.run_tool(self.s, self.tid, "sid-l", "file_write", {"path": "runs.txt", "text": self.page})
        self.assertIn('THE LAST ONE', self.walk('file_read', path='runs.txt')[-1])

    def test_the_reading_tools_say_they_take_a_place_to_start(self):
        for t in (*apiagent.BROWSER, *apiagent.FILES, *apiagent.WEB):
            if t['function']['name'] in ('browser_look', 'file_read', 'web_fetch'):
                self.assertIn('from', t['function']['parameters']['properties'], t['function']['name'])


class AnOpenThatNeverFinishedTests(unittest.TestCase):
    """A page whose text came but whose load never finished - an image or a tracker on it still loading - made agent-browser answer
    "Timed out after 25000ms waiting for load state 'load'", and browser_open told the agent it had failed over a page it could read."""

    def setUp(self):
        self.s, self.ran = MemoryStore(), []
        self.tid = self.s.create_task({'Title': 'Payroll runs summary', 'Summary': 'go', 'Kind': 'general', 'Status': 'open'}, 'owner')
        def run(sid, args, wait, tag):
            self.ran.append(args[0])
            if args[0] == 'open': return 1, "✗ Timed out after 25000ms waiting for load state 'load'"
            return 0, '- heading "Payroll runs" [level=2, ref=e2]\n- link "Next" [ref=e9]'
        self.on = 'https://portal.example/runs?page=2'
        for p in (mock.patch.object(bv, 'installed', return_value=True), mock.patch.object(bv, 'state', return_value={'open': True}),
                  mock.patch('taskuary.browsergate._run', side_effect=run), mock.patch('taskuary.browsergate.check', return_value={}),
                  mock.patch('taskuary.browsergate.address', side_effect=lambda sid, st=None: self.on)):
            p.start(); self.addCleanup(p.stop)

    def open(self): return apiagent.run_tool(self.s, self.tid, 'sid-o', 'browser_open', {'url': 'https://portal.example/runs?page=2'})

    def test_the_page_it_reached_is_read_and_said_unfinished(self):
        got = self.open()
        self.assertIn('Payroll runs', got); self.assertIn('had not finished loading', got)
        self.assertEqual(self.ran, ['open', 'snapshot'])

    def test_a_page_it_never_reached_is_still_a_failure(self):
        self.on = 'https://portal.example/runs?page=1'
        with self.assertRaises(ValueError) as e: self.open()
        self.assertIn('Timed out', str(e.exception))


class NoPageOpenTests(unittest.TestCase):
    """A look or a click before any page was opened, or after the browser closed: a look answered with a DevTools connect error, a click
    with "Taskuary held this for the owner ... Run `agent-browser get url`" - nothing was held, and an API agent has no such command."""

    def test_every_browser_tool_but_open_says_to_open_a_page_first(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Vendor invoices', 'Summary': 'go', 'Kind': 'general', 'Status': 'open'}, 'owner')
        with mock.patch.object(bv, 'installed', return_value=True), mock.patch.object(bv, 'state', return_value={'open': False}), \
             mock.patch('taskuary.browsergate._run') as ran, mock.patch('taskuary.browsergate.check') as judged:
            for tool, a in (('browser_look', {}), ('browser_click', {'ref': '@e1'}), ('browser_fill', {'ref': '@e2', 'text': 'Northwind'}),
                            ('browser_press', {'key': 'Enter'}), ('browser_screenshot', {})):
                with self.assertRaises(ValueError, msg=tool) as e: apiagent.run_tool(s, tid, 'sid-n', tool, a)
                self.assertIn('browser_open', str(e.exception)); self.assertIn('nothing was done', str(e.exception))
        ran.assert_not_called(); judged.assert_not_called()


def test_a_search_engine_page_read_as_the_fallback_is_its_results_never_its_menu():
    """A forced fallback, 2026-11-22: half of the results page handed the agent was the engine's sixty regions and time filters, and the cut
    fell on the results. What is read starts at the first result - its title, its address, its summary."""
    from taskuary import apiagent
    menu = '\n\n'.join(['All Regions', 'Argentina', 'Australia', 'US (English)', 'Any Time', 'Past Day', 'Past Year'])
    page = (f"PAGE https://html.search.example/?q=paper - paper at Search\n{menu}\n\nNorthwind Paper Supply\n\npaper.example/prices\n\n"
            "Today's office paper prices by the case, delivered next day across the region.\n\nAnother result title\n\nother.example\n\n"
            "A second summary long enough to be a result's own description line.")
    out = apiagent._results_only(page)
    assert out.startswith('PAGE https://html.search.example') and 'Argentina' not in out and 'Past Year' not in out
    assert out.split('\n')[1] == 'Northwind Paper Supply' and 'paper.example/prices' in out
