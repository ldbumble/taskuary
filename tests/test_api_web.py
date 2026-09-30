"""An API brain looks things up with its provider's own web search when the job is research (the general agent), and
answers plainly when the provider, model or account refuses the tool. Nothing here reaches a provider."""
import json, unittest
from types import SimpleNamespace as NS
from unittest import mock

from taskuary import chatgptauth as ca, general, llm


class _R:
    def __init__(self, status, body): self.status_code, self._b, self.text = status, body, json.dumps(body)
    def json(self): return self._b


def _chat(text): return _R(200, {'choices': [{'message': {'content': text}}]})


class OpenAIFamilyTests(unittest.TestCase):
    def test_openai_asks_the_responses_api_with_web_search_and_reads_its_text(self):
        seen = []
        def post(url, headers, body, timeout):
            seen.append((url, body)); return _R(200, {'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'found it'}]}]})
        with mock.patch.object(llm, 'post_retrying', side_effect=post):
            out = llm.make_llm('openai', {'model': 'gpt-x'}, 'k')('sys', 'research the vendor', web=True)
        self.assertEqual(out, 'found it')
        self.assertEqual(seen[0][0], 'https://api.openai.com/v1/responses')
        self.assertEqual(seen[0][1]['tools'], [{'type': 'web_search'}])

    def test_azure_uses_its_own_v1_responses_and_falls_back_when_the_deployment_has_no_search(self):
        seen = []
        def post(url, headers, body, timeout):
            seen.append(url)
            return _R(400, {'error': {'message': 'tool web_search not supported'}}) if url.endswith('/responses') else _chat('from memory')
        cfg = {'endpoint': 'https://res.example.openai.azure.com', 'deployment': 'gpt-dep'}
        with mock.patch.object(llm, 'post_retrying', side_effect=post):
            out = llm.make_llm('azure_openai', cfg, 'k')('sys', 'research', web=True)
        self.assertEqual(out, 'from memory')
        self.assertEqual(seen[0], 'https://res.example.openai.azure.com/openai/v1/responses')
        self.assertIn('/chat/completions', seen[1])

    def test_no_search_without_asking_and_none_for_a_schema(self):
        with mock.patch.object(llm, 'post_retrying', return_value=_chat('{}')) as post:
            brain = llm.make_llm('openai', {'model': 'gpt-x'}, 'k')
            brain('sys', 'one message')                                   # triage: never a search
            brain('sys', 'x', want={'name': 'v', 'schema': {'type': 'object'}}, web=True)
        self.assertTrue(all(c.args[0].endswith('/chat/completions') for c in post.call_args_list))

    def test_only_openai_and_azure_of_the_compatible_surfaces_claim_search(self):
        self.assertTrue(llm.make_llm('openai', {}, 'k').takes_web)
        self.assertFalse(llm.make_llm('groq', {}, 'k').takes_web)


class AnthropicTests(unittest.TestCase):
    def _client(self, *responses):
        cli = mock.MagicMock()
        cli.messages.create.side_effect = list(responses)
        return cli

    def test_the_server_tools_ride_along_and_a_paused_turn_is_continued(self):
        text = lambda t: NS(type='text', text=t)
        cli = self._client(NS(stop_reason='pause_turn', content=[text('searching')]),
                           NS(stop_reason='end_turn', content=[text('Answer with sources')]))
        with mock.patch('anthropic.Anthropic', return_value=cli):
            out = llm.make_llm('anthropic', {'model': 'claude-opus-5-5'}, 'k')('sys', 'research', web=True)
        self.assertEqual(out, 'Answer with sources')
        first = cli.messages.create.call_args_list[0].kwargs
        self.assertEqual([t['name'] for t in first['tools']], ['web_search', 'web_fetch'])
        self.assertEqual(first['tools'][0]['type'], 'web_search_20260209')
        self.assertEqual(len(cli.messages.create.call_args_list[1].kwargs['messages']), 2)   # the paused turn went back in

    def test_an_older_model_gets_the_basic_tools_and_a_refusal_of_both_answers_plainly(self):
        import anthropic, httpx
        bad = anthropic.BadRequestError('tool type not supported', response=httpx.Response(400, request=httpx.Request('POST', 'https://api.example')), body=None)
        plain = NS(stop_reason='end_turn', content=[NS(type='text', text='plain')])
        cli = self._client(bad, bad, plain)
        with mock.patch('anthropic.Anthropic', return_value=cli):
            out = llm.make_llm('anthropic', {'model': 'claude-3-x'}, 'k')('sys', 'research', web=True)
        self.assertEqual(out, 'plain')
        calls = cli.messages.create.call_args_list
        self.assertEqual(calls[1].kwargs['tools'][0]['type'], 'web_search_20250305')
        self.assertNotIn('tools', calls[2].kwargs)


class ChatGptPlanTests(unittest.TestCase):
    def test_search_and_images_go_along_and_each_is_dropped_only_when_refused(self):
        calls = []
        def complete(tok, model, system, user, max_tokens, want=None, images=None, web=False):
            calls.append((bool(web), bool(images), user[:6]))
            if web: raise ca.Unsupported('no web here')
            return 'ok'
        with mock.patch.object(ca, 'access_token', return_value='at'), mock.patch.object(ca, 'complete', side_effect=complete):
            out = llm.make_llm('chatgpt', {'model': 'gpt-plan'}, 'rt')('s', 'look it up', images=[('image/png', 'AAAA')], web=True)
        self.assertEqual(out, 'ok')
        self.assertEqual(calls, [(True, True, 'look i'), (False, True, 'look i')])   # web dropped, the picture kept

    def test_a_model_that_cannot_see_says_so_instead_of_dropping_the_picture_silently(self):
        def complete(tok, model, system, user, max_tokens, want=None, images=None, web=False):
            if images: raise ca.Unsupported('no images')
            return user
        with mock.patch.object(ca, 'access_token', return_value='at'), mock.patch.object(ca, 'complete', side_effect=complete):
            out = llm.make_llm('chatgpt', {'model': 'gpt-plan'}, 'rt')('s', 'see below', images=[('image/png', 'AAAA')])
        self.assertIn('1 attached image(s) not shown', out)


class ChainAndAgentTests(unittest.TestCase):
    def test_the_general_agent_asks_only_a_brain_that_can_search(self):
        api, cli = mock.Mock(takes_web=True), mock.Mock(spec=['__call__'])
        self.assertEqual(general._web(api), {'web': True})
        self.assertEqual(general._web(cli), {})

    def test_the_failover_chain_hands_web_only_to_the_brains_that_take_it(self):
        got = {}
        def cli_brain(system, user, **kw): got['cli'] = kw; raise RuntimeError('usage limit reached')
        def api_brain(system, user, **kw): got['api'] = kw; return 'ok'
        api_brain.takes_web = True
        store = mock.Mock()
        store.get_settings.return_value = {'triage_ai': 'cli:coder', 'triage_backup_ai': 'connector:2'}
        with mock.patch.object(llm, 'make_cli_llm', return_value=cli_brain), \
             mock.patch('taskuary.agents.agent_row', return_value=None), mock.patch('taskuary.agents.cli_of', return_value='claude'), \
             mock.patch('taskuary.agents.availability_failure', return_value=True):
            store.list_connectors.return_value = [{'ConnectorId': 2, 'Type': 'openai', 'Active': 1, 'HasSecret': 1}]
            store.get_connector.return_value = {'ConnectorId': 2, 'Type': 'openai', 'ConfigJson': '{}', 'Secret': 'k'}
            with mock.patch.object(llm, 'make_llm', return_value=api_brain):
                brain = llm._build_llm(store)
                self.assertTrue(brain.takes_web)
                self.assertEqual(brain('s', 'u', web=True), 'ok')
        self.assertNotIn('web', got['cli'])
        self.assertEqual(got['api'], {'web': True})


if __name__ == '__main__': unittest.main()
