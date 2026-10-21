"""EVERY BACKEND REACHES THE CANVAS IN ONE SHAPE (the owner, 2026-10-21: "make the output on the general agent canvas more readable,
not some greps and gets"). One invented research turn - Alex Doyle's agent looking into a budget review - recorded as each backend
speaks it: claude's stream-json, codex's JSONL, opencode's JSON, gemini over ACP, and two API connectors' own web searches. Each is
read by the parser that reads the real one, and must come out as the trace in `<backend>.trace.json`; website/test/agentSteps.test.mjs
then renders those same files and asserts they read as the same plain steps. TASKUARY_REGEN_FIXTURES=1 rewrites the traces."""
import json, os, sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from taskuary import agents, llm

D = Path(__file__).parent / 'fixtures' / 'agent_steps'
KEEP = ('tool_call', 'tool_result', 'progress', 'live', 'error')


def recorder():
    ev = []
    return ev, lambda kind, name, detail: ev.append({'type': kind, 'name': name, 'detail': detail}) if kind in KEEP else None


def same(case, backend, ev):
    path = D / f'{backend}.trace.json'
    if os.environ.get('TASKUARY_REGEN_FIXTURES') == '1':
        path.write_text(json.dumps(ev, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    case.assertEqual(ev, json.loads(path.read_text(encoding='utf-8')))


def cli_run(backend, cmd, args):
    fake = [sys.executable, str(Path(__file__).parent / 'fake_recorded_cli.py'), f'{backend}.jsonl']
    ev, trace = recorder()
    with mock.patch.object(agents, '_resolve_cmd', return_value=fake):
        out, _sid, _ = agents.run_cli({'cmd': cmd, 'args': args, 'timeout': 60}, 'look into the budget review', trace)
    return out, ev


class EachBackendTracesTheTurn(unittest.TestCase):
    def test_claude_stream_json(self):
        out, ev = cli_run('claude', 'claude', ['-p', '--output-format', 'stream-json', '--verbose'])
        self.assertIn('Gail Moreno', out); same(self, 'claude', ev)

    def test_codex_jsonl(self):
        out, ev = cli_run('codex', 'codex', ['exec'])
        self.assertIn('Gail Moreno', out); same(self, 'codex', ev)

    def test_opencode_json(self):
        out, ev = cli_run('opencode', 'opencode', ['run', '--format', 'json'])
        self.assertIn('Gail Moreno', out); same(self, 'opencode', ev)

    def test_gemini_over_acp_is_structured_like_the_argv_road(self):
        """ACP traced a `live` line per tool ("ReadFile (completed)") and nothing the canvas could summarise."""
        ev, trace = recorder()
        show = agents.acp_tracer(trace, 'gemini')
        for u in json.loads((D / 'gemini_acp.json').read_text(encoding='utf-8')): show(u)
        self.assertEqual(sum(e['type'] == 'tool_call' for e in ev), 7)
        same(self, 'gemini_acp', ev)

    def test_an_openai_connector_reports_its_own_web_searches(self):
        ev, trace = recorder()
        fixture = json.loads((D / 'openai_responses.json').read_text(encoding='utf-8'))
        r = SimpleNamespace(status_code=200, json=lambda: fixture, text='')
        with mock.patch.object(llm, 'post_retrying', return_value=r), llm.watching(trace):
            out = llm._responses_web('openai', {}, {}, 'gpt-x', 'sys', 'user', None, 100)
        self.assertIn('Gail Moreno', out); same(self, 'openai_responses', ev)

    def test_an_anthropic_connector_reports_its_server_tool_searches(self):
        ev, trace = recorder()
        fixture = json.loads((D / 'anthropic_api.json').read_text(encoding='utf-8'))
        ns = lambda o: SimpleNamespace(**{k: [ns(x) if isinstance(x, dict) else x for x in v] if isinstance(v, list) and k != 'input'
                                          else v for k, v in o.items()})
        resp = SimpleNamespace(stop_reason=fixture['stop_reason'], content=[ns(b) for b in fixture['content']])
        cli = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: resp))
        with llm.watching(trace):
            out = llm._anthropic_web(cli, 'claude-x', 'sys', 'user', 100)
        self.assertIn('Gail Moreno', out); same(self, 'anthropic_api', ev)

    def test_nobody_watching_costs_nothing(self):
        fixture = json.loads((D / 'openai_responses.json').read_text(encoding='utf-8'))
        r = SimpleNamespace(status_code=200, json=lambda: fixture, text='')
        with mock.patch.object(llm, 'post_retrying', return_value=r):
            self.assertIn('Gail Moreno', llm._responses_web('openai', {}, {}, 'gpt-x', 'sys', 'user', None, 100))


if __name__ == '__main__':
    unittest.main()
