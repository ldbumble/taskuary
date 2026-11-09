"""Every road a HIPAA AI card is used on, against a gateway shaped like LiteLLM in front of Vertex AI (the owner, 2026-11-06: "make
sure the hipaa thing works both for triage and agent as it was not working in the past").

The fake answers as LiteLLM does: its own error envelope, the model ids its key may call, Gemini and Claude-on-Vertex each with the
rules their provider enforces behind it (an empty system or user turn refused, Claude's thinking budget against max_tokens, a forced
tool call refused while it thinks), `usage` on every answer. Each test goes in through the app's own door - build_llm, ingest_message,
draft_reply, GeneralSession, quickwork.ask, concierge.brain - never by calling make_llm with a hand-built config."""
import json, unittest
from pathlib import Path
from unittest import mock

from taskuary import brainroute, llm
from taskuary.store import MemoryStore
from taskuary.testing import Factory

BASE, CODE = 'https://ai.northwind.example/v1', 'hai-code-1234567890'
FLASH, SONNET, OPUS, PRO = 'gemini-3.8-flash', 'claude-sonnet-5-5', 'claude-opus-5-5', 'gemini-2.5-pro'
MODELS = ['hipaa-ai', FLASH, SONNET, OPUS, PRO]
BUDGET = {'minimal': 512, 'low': 1024, 'medium': 2048, 'high': 4096}       # LiteLLM's reasoning_effort -> Claude thinking budget


class R:
    "A requests.Response as the app reads it."
    def __init__(self, status, body):
        self.status_code, self._b, self.headers = status, body, {'Content-Type': 'application/json'}
        self.text = json.dumps(body)
    def json(self): return self._b


def err(status, msg): return R(status, {'error': {'message': msg, 'type': 'None', 'param': 'None', 'code': str(status)}})


class Gateway:
    """LiteLLM over Vertex: /v1/models and /v1/chat/completions. `answer(body)` writes the model's reply text."""
    def __init__(self, answer=lambda body: 'ok', models=MODELS, served=None):
        "`served`: {asked: answered} - the gateway's own fallback, as the live one answers a Claude request on Gemini when Claude's quota is out."
        self.answer, self.models, self.calls, self.served = answer, list(models), [], dict(served or {})

    def get(self, url, headers=None, timeout=None, **kw):
        if (headers or {}).get('Authorization') != f'Bearer {CODE}': return err(401, 'Authentication Error, Invalid proxy server token passed.')
        assert url == f'{BASE}/models', url
        return R(200, {'object': 'list', 'data': [{'id': m, 'object': 'model', 'created': 1677610602, 'owned_by': 'openai'} for m in self.models]})

    def post(self, url, headers=None, json=None, timeout=None):
        b = dict(json); self.calls.append(b)
        if (headers or {}).get('Authorization') != f'Bearer {CODE}': return err(401, 'Authentication Error, Invalid proxy server token passed.')
        assert url == f'{BASE}/chat/completions', url
        m = b.get('model')
        if m not in self.models:
            return err(400, f'{{"error": "/chat/completions: Invalid model name passed in model={m}. Call `/v1/models` to view available models for your key."}}')
        real = self.served.get(m) or (FLASH if m == 'hipaa-ai' else m)
        claude = real.startswith('claude')
        for x in b['messages']:
            c = x.get('content')
            if not (c if isinstance(c, list) else str(c or '').strip()):
                return err(400, f'litellm.BadRequestError: VertexAIException BadRequestError - '
                                + ('{"type":"error","error":{"type":"invalid_request_error","message":"messages: text content blocks must be non-empty"}}'
                                   if claude else '{"error": {"code": 400, "message": "* GenerateContentRequest.contents[0].parts: contents.parts must not be empty.\\n", "status": "INVALID_ARGUMENT"}}'))
        cap = b.get('max_completion_tokens') or b.get('max_tokens') or 4096
        effort, fmt = b.get('reasoning_effort'), (b.get('response_format') or {}).get('type')
        if claude and effort and cap <= BUDGET.get(effort, 0):
            return err(400, 'litellm.BadRequestError: VertexAIException BadRequestError - {"type":"error","error":{"type":"invalid_request_error",'
                            '"message":"`max_tokens` must be greater than `thinking.budget_tokens`. Please consult our documentation at '
                            'https://docs.claude.com/en/docs/build-with-claude/extended-thinking#max-tokens-and-context-windows"}}')
        if claude and effort and fmt == 'json_schema':
            return err(400, 'litellm.BadRequestError: VertexAIException BadRequestError - {"type":"error","error":{"type":"invalid_request_error",'
                            '"message":"Thinking may not be enabled when tool_choice forces tool use."}}')
        text = self.answer(b)
        return R(200, {'id': 'chatcmpl-1', 'object': 'chat.completion', 'created': 1, 'model': real, 'system_fingerprint': None,
                       'choices': [{'index': 0, 'finish_reason': 'stop',
                                    'message': {'role': 'assistant', 'content': text, 'tool_calls': None, 'function_call': None}}],
                       'usage': {'prompt_tokens': 120, 'completion_tokens': 30, 'total_tokens': 150,
                                 'prompt_tokens_details': None, 'completion_tokens_details': {'reasoning_tokens': 10}}})

    def __enter__(self):
        self._p = [mock.patch('taskuary.llm.requests.post', side_effect=self.post), mock.patch('taskuary.llm.requests.get', side_effect=self.get)]
        for p in self._p: p.start()
        llm._FORMAT_FROM.clear(); llm._NO_EFFORT.clear(); llm._models_cache.clear()
        return self
    def __exit__(self, *a):
        for p in self._p: p.stop()

    def said(self, i=-1): return self.calls[i]


def card(s, model=FLASH, **conf) -> int:
    "The HIPAA AI card switched on with its access code, its gateway address and `model` in its model box."
    cid = s.get_connector_by_type('hipaa_ai')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': CODE, 'Active': 1,
                      'ConfigJson': json.dumps({'base_url': BASE, **({'model': model} if model else {}), **conf})}, 'owner')
    return cid


VERDICT = {'intent': 'task', 'kind': 'task', 'why': 'asks for a report', 'title': 'Send the census report', 'summary': 'Erin wants the census report by Friday.',
           'priority': 'regular', 'priority_why': 'routine', 'sender_class': 'person', 'checklist': ['Pull the numbers', 'Send it']}


def triage_answer(body):
    sys = body['messages'][0]['content'] if body['messages'][0]['role'] == 'system' else ''
    return json.dumps(VERDICT) if 'intent' in str(sys) or body.get('response_format') else 'ok'


class SetupRoad(unittest.TestCase):
    "(a) The card's Connect: the code is tried, the gateway's list fills each job's model, and the test email is sorted on them."
    def test_connect_tries_the_code_lists_the_models_and_sorts_the_test_mail(self):
        from taskuary import firstrun
        s = MemoryStore(); cid = s.get_connector_by_type('hipaa_ai')['ConnectorId']
        with Gateway(triage_answer) as g, mock.patch('taskuary.config.load', return_value={}):
            out = firstrun.choose_key(s, 'hipaa_ai', CODE, cid=cid, config={'base_url': 'ai.northwind.example'})
        self.assertTrue(out['ok'], out)
        self.assertEqual({c['model'] for c in g.calls} - {'hipaa-ai'}, {FLASH}, 'the test email went to the model that will sort the mail')
        self.assertEqual(s.get_setting('triage_ai'), f'connector:{cid}')

    def test_the_model_list_offers_the_gateways_models(self):
        s = MemoryStore(); cid = card(s)
        with Gateway(): self.assertEqual(llm.connector_models(s, cid), {'models': sorted(MODELS)})


class TriageRoad(unittest.TestCase):
    "(b) A mail in, through poll_channels' own brain and ingest_message: the task carries the gateway's judgement."
    def mail(self, s, ext='m1'):
        from taskuary import ingest
        with mock.patch.object(ingest, '_spawn', mock.Mock()):
            return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': 'erin@northwind.example', 'from_name': 'Erin Blake',
                                             'to': 'alex@northwind.example', 'subject': 'Census report', 'body': 'Can you send the census report by Friday?',
                                             'sent_at': '2026-11-06 09:00:00'}, llm=llm.build_llm(s, job='triage'))

    def check(self, s, g):
        out = self.mail(s)
        t = s.get_task(out['task_id'])
        self.assertEqual(t['Title'], VERDICT['title'], out)
        self.assertTrue(g.calls)
        return t

    def test_flash_judges_the_mail(self):
        s = MemoryStore(); s.set_setting('triage_ai', f'connector:{card(s)}', 'owner')
        with Gateway(triage_answer) as g: self.check(s, g)
        self.assertEqual(g.calls[0]['model'], FLASH)

    def test_claude_on_vertex_judges_the_mail(self):
        s = MemoryStore(); s.set_setting('triage_ai', f'connector:{card(s, SONNET)}', 'owner')
        with Gateway(triage_answer) as g: self.check(s, g)

    def test_a_blank_model_box_runs_the_gateways_alias(self):
        s = MemoryStore(); s.set_setting('triage_ai', f'connector:{card(s, "")}', 'owner')
        with Gateway(triage_answer) as g: self.check(s, g)
        self.assertEqual(g.calls[0]['model'], 'hipaa-ai')

    def test_auto_quick_tier_on_claude_takes_low_effort_and_still_judges(self):
        s = MemoryStore(); s.set_setting('triage_ai', f'connector:{card(s, SONNET)}', 'owner'); s.set_setting('ai_route_mode', 'auto', 'owner')
        with Gateway(triage_answer) as g: self.check(s, g)


def jobs_on(s, cid, *slots, mode='fixed'):
    for k in slots or ('triage_ai', 'assistant_ai', 'concierge_ai'): s.set_setting(k, f'connector:{cid}', 'owner')
    s.set_setting('ai_route_mode', mode, 'owner')


class DraftRoad(unittest.TestCase):
    "(c) The reply a task needs, written by the card the drafting job rides (blank = triage's)."
    def test_a_reply_is_drafted_on_each_model(self):
        from taskuary import responder
        for model in (FLASH, SONNET):
            s = MemoryStore(); fx = Factory(s); jobs_on(s, card(s, model), 'triage_ai')
            tid = fx.task(title='Census report', kind='task'); fx.message(task_id=tid, subject='Census report', body_text='Can you send it by Friday?')
            with Gateway(lambda b: 'Hi Erin, I will send it Friday.\n\nAlex') as g: out = responder.draft_reply(s, tid)
            self.assertIn('send it Friday', out, model)
            self.assertEqual(g.said()['model'], model)


SUMMARY = ('I compared the two vendors: Payworth is cheaper.\n[[TASKUARY-SUMMARY]]{"about": "Erin asked which payroll vendor to keep.", '
           '"did": "Payworth is 2 dollars a head cheaper than Trainly.", "on_you": ["Pick one"], "nothing_left": false, "answer_is_result": true}'
           '[[/TASKUARY-SUMMARY]]')


class GeneralAgentRoad(unittest.TestCase):
    "(d) A general agent on the card: no shell, no web search on this provider, the summary block parsed off its answer."
    def turn(self, model, answer=SUMMARY, mode='fixed', **conf):
        from taskuary import general
        s = MemoryStore(); fx = Factory(s); cid = card(s, model, **conf); jobs_on(s, cid, mode=mode)
        tid = fx.task(title='Compare payroll vendors', kind='general')
        # the PLAIN road, a card that takes no tools: nothing a gateway model may refuse rides (the tool road is test_apiagent's)
        with Gateway(lambda b: answer) as g, mock.patch('taskuary.browserview.installed', return_value=False), \
             mock.patch('taskuary.apiagent.can', return_value=False):
            sess = general.GeneralSession(s, tid)
            self.assertEqual(sess.pick, f'connector:{cid}')
            reply = sess.send_prompt('Compare Payworth and Trainly')
        return s, tid, g, reply

    def test_a_turn_answers_and_files_where_the_owner_stands(self):
        from taskuary import general
        for model in (SONNET, FLASH, OPUS, PRO):
            s, tid, g, reply = self.turn(model)
            self.assertIn('Payworth is cheaper', reply); self.assertNotIn('TASKUARY-SUMMARY', reply)
            summ = [c['Body'] for c in s.list_comments(tid, internal=True) if c['ActorType'] == general.SUMMARY_TYPE]
            self.assertTrue(summ and 'a head cheaper' in summ[-1], model)
            b = g.said()
            self.assertEqual(b['model'], model)
            self.assertFalse({'tools', 'tool_choice', 'functions', 'stream', 'web_search_options'} & set(b), 'nothing a gateway model may refuse')
            self.assertEqual([m['role'] for m in b['messages']], ['system', 'user'])

    def test_hard_work_on_auto_runs_the_cards_strong_model(self):
        s, tid, g, _ = self.turn(SONNET, mode='auto', strong_model=OPUS)
        self.assertIn(g.said()['model'], (SONNET, OPUS))


class QuickWorkRoad(unittest.TestCase):
    "(e) One call that answers a task in one go: on an API card with no web search, the schema rides the wire."
    def test_a_quick_answer_comes_back_read(self):
        from taskuary import quickwork
        for model in (FLASH, SONNET):
            s = MemoryStore(); fx = Factory(s); jobs_on(s, card(s, model))
            tid = fx.task(title='What is the PTO policy?', kind='general'); fx.message(task_id=tid, subject='PTO', body_text='How many days do I get?')
            ans = {'report': 'Fifteen days a year.', 'draft': 'Hi, you get fifteen days.', 'question': None, 'done': False, 'escalate': False, 'why': ''}
            with Gateway(lambda b: json.dumps(ans)) as g: got = quickwork.ask(s, tid, 'How many PTO days?')
            self.assertEqual(got.report, 'Fifteen days a year.', model)
            self.assertEqual(g.said()['model'], model)


class AssistantRoad(unittest.TestCase):
    "(f) The Assistant (concierge) on the card answers in-process."
    def test_the_assistant_brain_answers(self):
        from taskuary import concierge
        for model in (FLASH, SONNET):
            s = MemoryStore(); cid = card(s, model); jobs_on(s, cid)
            with Gateway(lambda b: 'You have two tasks waiting.') as g:
                b = concierge.brain(s)
                self.assertIsNotNone(b, model)
                self.assertEqual(b('You are the Assistant.', 'what is waiting?'), 'You have two tasks waiting.')
            self.assertEqual(g.said()['model'], model)


class EffortRoad(unittest.TestCase):
    "(g) Auto's tiers on one card: quick is its model at low effort, hard its strong_model or high effort; a refused effort is asked plainly."
    def test_tiers(self):
        s = MemoryStore(); pick = f'connector:{card(s, FLASH)}'
        self.assertEqual(brainroute.lift(s, pick, 'light', cfg={}), f'{FLASH}@low')
        self.assertEqual(brainroute.lift(s, pick, 'strong', cfg={}), f'{FLASH}@high')
        t = MemoryStore(); tp = f'connector:{card(t, FLASH, strong_model=OPUS)}'
        self.assertEqual(brainroute.strong_of(t, tp, cfg={}), OPUS)

    def test_quick_jobs_send_low_effort_and_the_gateway_takes_it(self):
        s = MemoryStore(); jobs_on(s, card(s, FLASH), mode='auto')
        with Gateway() as g: self.assertEqual(llm.build_llm(s, job='rank')('s', 'u', max_tokens=300), 'ok')
        self.assertEqual((g.said()['model'], g.said()['reasoning_effort']), (FLASH, 'low'))

    def test_claudes_thinking_budget_over_a_small_call_is_asked_without_effort_and_not_written_off(self):
        """A quick job on Claude behind the gateway: LiteLLM turned `low` into a 1024-token thinking budget over a 300-token call, and
        Claude's refusal never says "effort" - so it was no quiet retry but an error, and every quick job on the card failed."""
        s = MemoryStore(); jobs_on(s, card(s, SONNET), mode='auto')
        with Gateway() as g:
            self.assertEqual(llm.build_llm(s, job='rank')('s', 'u', max_tokens=300), 'ok')
            self.assertEqual([c.get('reasoning_effort') for c in g.calls], ['low', None])
            self.assertEqual(llm.build_llm(s, job='rank')('s', 'u', max_tokens=3000), 'ok')
            self.assertEqual(g.said()['reasoning_effort'], 'low', 'a call with room still thinks')
        self.assertFalse(llm._NO_EFFORT)

    def test_thinking_beside_a_schema_keeps_the_schema(self):
        s = MemoryStore(); jobs_on(s, card(s, SONNET), mode='auto')
        with Gateway(lambda b: '{"a": 1}') as g:
            got = llm.ask_json(llm.build_llm(s, job='rank'), 's', 'u', want={'name': 'x', 'schema': {'type': 'object'}}, max_tokens=3000)
        self.assertEqual(got.data, {'a': 1})
        self.assertEqual([(c.get('response_format') or {}).get('type') for c in g.calls], ['json_schema', 'json_schema'])

    def test_an_effort_refused_with_400_or_422_is_asked_plainly(self):
        for status in (400, 422):
            gw = Gateway()
            def post(url, headers=None, json=None, timeout=None, _s=status):
                return err(_s, 'litellm.UnsupportedParamsError: gemini does not support parameters: {"reasoning_effort": "low"}') \
                    if 'reasoning_effort' in json else gw.post(url, headers, json, timeout)
            fn = llm.make_llm('hipaa_ai', {'base_url': BASE, 'model': f'{FLASH}@low'}, CODE)
            llm._NO_EFFORT.clear()
            with mock.patch('taskuary.llm.requests.post', side_effect=post): self.assertEqual(fn('s', 'u'), 'ok')
            self.assertTrue(llm._NO_EFFORT, 'a model that refused effort by name is asked plainly from then on')

    def test_a_model_with_no_thinking_at_all_is_written_off(self):
        gw = Gateway()
        def post(url, headers=None, json=None, timeout=None):
            return err(400, 'litellm.BadRequestError: VertexAIException - thinking is not supported by this model') if 'reasoning_effort' in json                 else gw.post(url, headers, json, timeout)
        llm._NO_EFFORT.clear()
        with mock.patch('taskuary.llm.requests.post', side_effect=post):
            self.assertEqual(llm.make_llm('hipaa_ai', {'base_url': BASE, 'model': f'{FLASH}@low'}, CODE)('s', 'u'), 'ok')
        self.assertTrue(llm._NO_EFFORT)

    def test_a_refusal_that_says_effort_on_its_own_is_one(self):
        "The word as a word: it was spelled with backspace bytes where \\b belonged, and matched only 'reasoning_effort'."
        self.assertTrue(llm._EFFORT_REFUSED.search('Unsupported value: effort must be one of low, high'))
        self.assertNotIn('\x08', llm._EFFORT_REFUSED.pattern)


class SensitiveRoad(unittest.TestCase):
    "(h) The owner's data rule: a sensitive task reaches only a card marked for it, and the HIPAA card can be that card."
    def route(self, marked):
        s = MemoryStore(); fx = Factory(s)
        cid = card(s, FLASH, **({'sensitive_ok': '1'} if marked else {})); jobs_on(s, cid, 'triage_ai', mode='auto')
        brainroute.save_rules(s, [{**r, 'on': True} if r['id'] == 'sensitive' else r for r in brainroute.rules(s)])
        tid = fx.task(title='Resident chart question', kind='task'); s.judge_task(tid, {'data_class': 'sensitive'}, 'triage')
        return cid, brainroute.choose(s, 'draft', task=tid)

    def test_a_marked_card_reads_a_sensitive_task(self):
        cid, r = self.route(True)
        self.assertEqual((r.pick, r.tier != 'held'), (f'connector:{cid}', True))

    def test_an_unmarked_card_holds_it(self):
        _, r = self.route(False)
        self.assertEqual((r.pick, r.tier), ('', 'held'))


class ColdStartRoad(unittest.TestCase):
    "A gateway that scales to zero answers its first request once it has booted: Connect and the model list wait for it."
    def test_connect_and_the_model_list_wait_past_a_cold_start(self):
        waits = []
        gw = Gateway()
        def get(url, headers=None, timeout=None, **kw): waits.append(timeout); return gw.get(url, headers)
        with mock.patch('taskuary.llm.requests.get', side_effect=get):
            self.assertEqual(llm.gateway_problem({'base_url': BASE}, CODE), '')
            self.assertEqual(llm.list_models('hipaa_ai', {'base_url': BASE}, CODE), sorted(MODELS))
        self.assertTrue(all(isinstance(w, tuple) and w[1] >= 60 for w in waits), waits)


class EmptyTurnRoad(unittest.TestCase):
    "Gemini and Claude behind the gateway refuse an empty system or user turn, where OpenAI let one by."
    def test_a_blank_system_is_left_out_and_a_blank_ask_is_the_systems(self):
        for model in (FLASH, SONNET):
            fn = llm.make_llm('hipaa_ai', {'base_url': BASE, 'model': model}, CODE)
            with Gateway() as g:
                self.assertEqual(fn('', 'Summarise this.'), 'ok')
                self.assertEqual([m['role'] for m in g.said()['messages']], ['user'])
                self.assertEqual(fn('Reply with exactly: ok', '  '), 'ok')
                self.assertEqual(g.said()['messages'], [{'role': 'user', 'content': 'Reply with exactly: ok'}])


class AgentTicksRoad(unittest.TestCase):
    "(d) With no shell, the general agent's to-dos are ticked by a line in its answer."
    def test_a_tick_line_ticks_the_to_do(self):
        from taskuary import general, selfclose
        s = MemoryStore(); fx = Factory(s); jobs_on(s, card(s, SONNET))
        tid = fx.task(title='Census report', kind='general'); s.set_task_checklist(tid, ['Pull the numbers', 'Send it'], 'owner')
        first = s.task_checklist(tid)[0]['id']
        with Gateway(lambda b: f'Pulled the numbers.\n[[TASKUARY-TICK: {first}]]\n' + SUMMARY) as g:
            reply = general.GeneralSession(s, tid).send_prompt('Pull the numbers')
        self.assertIn(selfclose.TICK_CHAT_LINE, g.said()['messages'][0]['content'])
        self.assertNotIn('TASKUARY-TICK', reply)
        self.assertEqual([bool(i.get('done')) for i in s.task_checklist(tid)][:2], [True, False])


class AgentStartsByItselfRoad(unittest.TestCase):
    "(d) The road triage takes into an agent: a general task started by the router runs its first turn on the card."
    def test_the_router_starts_the_agent_and_its_turn_lands(self):
        from taskuary import general, ingest
        s = MemoryStore(); fx = Factory(s); cid = card(s, SONNET); jobs_on(s, cid)
        tid = fx.task(title='Compare payroll vendors', kind='general', summary='Erin wants Payworth and Trainly compared.')
        # the router's start is a process boundary the test suite guards (conftest): the session it opens is the one an owner opens
        with Gateway(lambda b: SUMMARY) as g, mock.patch.object(general, 'start_session', lambda st, t, **kw: general.GeneralSession(st, t)):
            self.assertTrue(ingest._start_general(s, tid))
        self.assertEqual(g.said()['model'], SONNET)
        self.assertTrue([c for c in s.list_comments(tid, internal=True) if c['ActorType'] == general.SUMMARY_TYPE])


class SmokeTool(unittest.TestCase):
    "tools/hipaa_smoke.py, against the same gateway: a triage and an agent call per model, and never the address or the code on screen."
    def smoke(self, answer, **kw):
        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location('hipaa_smoke', Path(__file__).resolve().parents[1] / 'tools' / 'hipaa_smoke.py')
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        s = MemoryStore(); card(s, FLASH); lines = []
        with Gateway(answer, **kw): rows = mod.run(s, say=lines.append)
        return rows, '\n'.join(lines)

    def test_every_model_answers_both_shapes(self):
        def answer(b):
            return json.dumps(VERDICT) if b.get('response_format') or 'intent' in b['messages'][0]['content'] else SUMMARY
        rows, said = self.smoke(answer)
        self.assertEqual({(r['model'], r['kind']) for r in rows}, {(m, k) for m in MODELS for k in ('triage', 'agent')})
        self.assertTrue(all(r['ok'] for r in rows), said)
        self.assertTrue(all(r['in'] == 120 and r['out'] == 30 for r in rows), said)
        self.assertIn('summary block read', said)
        self.assertNotIn(CODE, said); self.assertNotIn('ai.northwind.example', said)

    def test_an_answer_from_the_gateways_fallback_says_which_model_gave_it(self):
        def answer(b):
            return json.dumps(VERDICT) if b.get('response_format') or 'intent' in b['messages'][0]['content'] else SUMMARY
        rows, said = self.smoke(answer, served={SONNET: PRO, OPUS: PRO})
        self.assertEqual({r['ran'] for r in rows if r['model'] in (SONNET, OPUS)}, {PRO})
        self.assertIn(f'ANSWERED BY {PRO}', said)

    def test_a_spent_budget_is_said_in_its_line(self):
        rows, said = self.smoke(lambda b: 'ok', models=[FLASH])
        with mock.patch('taskuary.llm.requests.post', return_value=R(422, SPENT)):
            import importlib.util
            spec = importlib.util.spec_from_file_location('hipaa_smoke', Path(__file__).resolve().parents[1] / 'tools' / 'hipaa_smoke.py')
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            st = MemoryStore(); card(st, FLASH); lines = []
            with mock.patch('taskuary.llm.requests.get', side_effect=Gateway().get): mod.run(st, models=[FLASH], say=lines.append)
        self.assertIn('monthly budget is used up', '\n'.join(lines)); self.assertNotIn('team-0000', '\n'.join(lines))

    def test_a_refused_model_is_a_failure_with_the_secrets_taken_out(self):
        rows, said = self.smoke(lambda b: 'ok', models=[FLASH])
        rows2 = [r for r in rows if r['kind'] == 'triage']
        self.assertFalse(rows2[0]['ok'], said)
        self.assertNotIn(CODE, said); self.assertNotIn('ai.northwind.example', said)


class AnsweredByRoad(unittest.TestCase):
    "The gateway may answer on another model than the one asked (its fallback): what the task says it used is the model that answered."
    def test_the_usage_row_names_the_model_that_answered(self):
        s = MemoryStore(); jobs_on(s, card(s, SONNET), 'triage_ai')
        with Gateway(served={SONNET: PRO}) as g: self.assertEqual(llm.build_llm(s, job='summary')('s', 'u'), 'ok')
        self.assertEqual(g.said()['model'], SONNET)
        row = s.brain_routes_since('2000-01-01 00:00:00')[0]
        self.assertEqual((row['Ran'], row['TokensIn'], row['TokensOut']), (PRO, 120, 30))


FENCED = 'Here is the verdict:\n```json\n' + json.dumps(VERDICT, indent=2) + '\n```'


class FencedJsonRoad(unittest.TestCase):
    "Gemini and Claude behind the gateway often wrap their JSON in a ```json fence, prose before it: every road that reads JSON unwraps it."
    def test_triage_reads_a_fenced_verdict(self):
        s = MemoryStore(); s.set_setting('triage_ai', f'connector:{card(s)}', 'owner')
        with Gateway(lambda b: FENCED): self.assertEqual(s.get_task(TriageRoad().mail(s)['task_id'])['Title'], VERDICT['title'])

    def test_quick_work_reads_a_fenced_answer(self):
        from taskuary import quickwork
        s = MemoryStore(); fx = Factory(s); jobs_on(s, card(s, FLASH))
        tid = fx.task(title='PTO policy', kind='general'); fx.message(task_id=tid, subject='PTO', body_text='How many days?')
        ans = {'report': 'Fifteen days.', 'draft': None, 'question': None, 'done': False, 'escalate': False, 'why': ''}
        with Gateway(lambda b: f'```json\n{json.dumps(ans)}\n```'): self.assertEqual(quickwork.ask(s, tid, 'How many?').report, 'Fifteen days.')

    def test_the_agents_summary_block_is_read_inside_a_fence(self):
        from taskuary import selfclose
        text, summ = selfclose.summary_marker('Done.\n[[TASKUARY-SUMMARY]]\n```json\n{"about": "a", "did": "compared them", "on_you": []}\n```\n[[/TASKUARY-SUMMARY]]')
        self.assertEqual((text, summ and summ['did']), ('Done.', 'compared them'))

    def test_the_ranker_and_the_overlap_check_read_a_fenced_order(self):
        from taskuary import rank, blackboard
        for mod in (rank, blackboard):
            self.assertNotIn("re.sub(r'^```(json)?|```$'", Path(mod.__file__).read_text(encoding='utf-8'), 'a fence only at the very start was read')
        self.assertEqual(llm.json_of('The order:\n```json\n{"order": [{"ref": "TQ-0001"}]}\n```'), {'order': [{'ref': 'TQ-0001'}]})


SPENT = {'error': {'message': 'Budget has been exceeded! Team=team-0000 Current cost: 0.58, Max budget: 0.5', 'type': 'budget_exceeded', 'code': '422'}}


class BudgetRoad(unittest.TestCase):
    """The team's budget spent: the gateway answers 422 budget_exceeded. It is no effort refusal, it is said plainly once, the card rests
    instead of being asked every poll, and a sensitive task still waits rather than going to an AI the rule keeps out."""
    def spent_gateway(self, also=None):
        gw, sent = Gateway(triage_answer), []
        def post(url, headers=None, json=None, timeout=None):
            sent.append((url, dict(json)))
            if url.startswith(BASE): return R(422, SPENT)
            return (also or gw.post)(url, headers, json, timeout)
        return gw, sent, mock.patch('taskuary.llm.requests.post', side_effect=post)

    def test_it_is_no_effort_refusal_and_is_asked_once(self):
        s = MemoryStore(); jobs_on(s, card(s, SONNET), 'triage_ai', mode='auto')
        gw, sent, p = self.spent_gateway()
        with gw, p, self.assertRaises(llm.BudgetSpent) as e: llm.build_llm(s, job='triage')('s', 'u', want={'name': 'x', 'schema': {'type': 'object'}})
        self.assertEqual(len(sent), 1, 'neither the effort nor the format retry asked again')
        self.assertFalse(llm._NO_EFFORT, 'the model is not written off as refusing effort')
        self.assertEqual(str(e.exception), "HIPAA AI's monthly budget is used up - it answers again when the budget resets or is raised")

    def test_the_bell_says_it_plainly_once_and_the_card_rests(self):
        from taskuary import problems
        s = MemoryStore(); cid = card(s); s.set_setting('triage_ai', f'connector:{cid}', 'owner')
        gw, sent, p = self.spent_gateway()
        with gw, p:
            outs = [TriageRoad().mail(s, f'm{i}') for i in range(3)]
        self.assertEqual([o['status'] for o in outs], ['error'] * 3, 'held for the retry, never filed as nothing to do')
        self.assertEqual(len(sent), 1, 'the resting card is not asked again for every mail')
        self.assertIn(f'connector:{cid}', brainroute.cooldowns(s))
        bell = [b for b in problems.collect(s) if 'budget' in json.dumps(b)]
        self.assertEqual(len(bell), 1, bell)
        said = json.dumps(bell[0])
        self.assertEqual(bell[0]['title'], "HIPAA AI's monthly budget is used up - it answers again when the budget resets or is raised")
        for raw in ('team-0000', 'Team=', 'budget_exceeded', '0.58', '{"error'): self.assertNotIn(raw, said)

    def test_a_card_that_answers_again_stops_resting(self):
        s = MemoryStore(); pick = f'connector:{card(s)}'; jobs_on(s, int(pick[10:]), 'triage_ai')
        from datetime import datetime, timedelta
        brainroute.spend(s, pick, 'spent', datetime.now() - timedelta(seconds=1))      # the rest ran out
        with Gateway() as g: self.assertEqual(llm.build_llm(s, job='summary')('s', 'u'), 'ok')
        self.assertEqual((len(g.calls), brainroute.spent(s, pick), brainroute._spent_map(s)), (1, '', {}))

    def backup(self, s):
        cid = s.get_connector_by_type('openai')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-123456789', 'Active': 1, 'ConfigJson': json.dumps({'model': 'gpt-x'})}, 'owner')
        s.set_setting('triage_backup_ai', f'connector:{cid}', 'owner')
        return lambda url, headers, body, timeout: R(200, {'model': 'gpt-x', 'choices': [{'message': {'content': 'from the backup'}}]})

    def test_ordinary_work_goes_to_a_backup(self):
        s = MemoryStore(); jobs_on(s, card(s), 'triage_ai', mode='auto')
        gw, sent, p = self.spent_gateway(self.backup(s))
        with gw, p: self.assertEqual(llm.build_llm(s, job='summary')('s', 'u'), 'from the backup')

    def test_a_sensitive_task_waits_on_its_marked_card_and_never_goes_to_the_unmarked_backup(self):
        s = MemoryStore(); fx = Factory(s); cid = card(s, FLASH, sensitive_ok='1'); jobs_on(s, cid, 'triage_ai', mode='auto')
        brainroute.save_rules(s, [{**r, 'on': True} if r['id'] == 'sensitive' else r for r in brainroute.rules(s)])
        tid = fx.task(title='Resident chart question', kind='task'); s.judge_task(tid, {'data_class': 'sensitive'}, 'triage')
        gw, sent, p = self.spent_gateway(self.backup(s))
        with gw, p:
            for _ in range(2):
                with self.assertRaises(llm.BudgetSpent): llm.build_llm(s, job='draft', task_id=tid)('s', 'u')
        self.assertTrue(sent and all(u.startswith(BASE) for u, _ in sent), [u for u, _ in sent])
        self.assertEqual(len(sent), 1, 'and it rests')
        self.assertEqual(brainroute.choose(s, 'draft', task=tid).chain, [], 'no unmarked AI in its chain')
