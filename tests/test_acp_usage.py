"""WHAT AN ACP TURN USED, AND THE MODEL IT RUNS ON (the owner's live install, 2026-11-06). A general turn over ACP logged its model and its
time but no tokens: the argv road reads claude's `result` and codex's `turn.completed`, and the ACP road read nothing. Both adapters answer
session/prompt with the turn's `usage` and name its model in _meta.quota; a turn whose answer has none is read from the CLI's own log by
its session id, from the turn's start. And our model ids are matched to the agent's own spelling quietly - "claude offers no model
'claude-opus-5-5' over ACP - it runs on opus" was an agent step in the owner's chat. The agent is tests/fake_acp_server.py."""
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

from taskuary import acp, agents, aiusage, brainroute, sessionrecord
from taskuary.store import MemoryStore

pytestmark = pytest.mark.acp
FAKE = [sys.executable, str(Path(__file__).parent / 'fake_acp_server.py')]
HERE = str(Path(__file__).parent)


def _metered_turn(s, tid, prof, env=None):
    "One general turn through the meter build_llm puts round every brain (aiusage.Metered), onto a route row of its own."
    r = brainroute.choose(s, 'general', task=tid)
    rid = brainroute.log(s, r, tid)
    brain = aiusage.Metered(s, rid, lambda *a, **k: agents.run_cli(prof, 'find the venue', lambda *a: None, extra_env=env)[0])
    with mock.patch.object(agents, '_resolve_cmd', return_value=[FAKE[0]]), agents.run_context(s, tid): out = brain()
    return out, s.brain_routes(tid, limit=1)[0]


def _task(s): return s.create_task({'Title': 'Find the venue address', 'Status': 'open'}, 'owner')


def test_the_adapters_own_count_lands_on_the_route_row():
    s = MemoryStore(); tid = _task(s)
    prof = {'cmd': FAKE[0], 'args': [], 'acp': FAKE[1:], 'acp_ok': True, 'cwd': HERE}
    out, row = _metered_turn(s, tid, prof, {'FAKE_ACP_USAGE': '1'})
    assert out.startswith('granted')
    # inputTokens leave the cache out (as Anthropic's do): in = 12 + 400 written + 3000 read
    assert (row['Ran'], row['TokensIn'], row['Cached'], row['TokensOut'], row['Calls']) == ('claude-opus-5-5', 3412, 3000, 250, 1)
    assert row['Ms'] is not None


def test_the_shape_of_both_adapters_prompt_response():
    claude = {'stopReason': 'end_turn', 'usage': {'inputTokens': 5, 'cachedReadTokens': 100, 'cachedWriteTokens': 20, 'outputTokens': 7, 'totalTokens': 132},
              '_meta': {'quota': {'model_usage': [{'model': 'claude-haiku-5', 'token_count': {'outputTokens': 1}},
                                                  {'model': 'claude-opus-5-5', 'token_count': {'outputTokens': 6}}]}}}
    assert aiusage.acp(claude) == {'model': 'claude-opus-5-5', 'in': 125, 'cached': 100, 'out': 7}       # the model that did the most
    assert aiusage.acp({'stopReason': 'end_turn', 'usage': None, '_meta': {'quota': {'token_count': None, 'model_usage': []}}}) == {}
    assert aiusage.acp({'stopReason': 'end_turn'}) == {}


def test_a_turn_with_no_count_is_read_from_the_cli_s_own_log_from_the_turn_s_start(tmp_path):
    s = MemoryStore(); tid = _task(s)
    log = tmp_path / '.claude' / 'projects' / 'venue'; log.mkdir(parents=True)
    utc = lambda d: (datetime.now(timezone.utc) + d).isoformat().replace('+00:00', 'Z')
    line = lambda mid, at, n: json.dumps({'type': 'assistant', 'timestamp': at, 'message': {'id': mid, 'model': 'claude-sonnet-5-5',
                                          'usage': {'input_tokens': n, 'cache_read_input_tokens': 50, 'output_tokens': 9}}})
    def prompt_and_log(real):
        def go(self, text):
            out = real(self, text)
            # the CLI writes this turn's line as it answers; the line before it is an earlier turn of the same conversation
            (log / 'sess_fake_1.jsonl').write_text(line('old', utc(timedelta(hours=-1)), 999) + '\n' + line('new', utc(timedelta(seconds=1)), 11) + '\n',
                                                   encoding='utf-8')
            return out
        return go
    prof = {'cmd': 'claude', 'args': [], 'acp': FAKE[1:], 'acp_ok': True, 'cwd': HERE}
    with mock.patch.object(sessionrecord, '_home', lambda: tmp_path), mock.patch.object(acp.ACPClient, 'prompt', prompt_and_log(acp.ACPClient.prompt)):
        out, row = _metered_turn(s, tid, prof)
    assert (row['TokensIn'], row['Cached'], row['TokensOut']) == (61, 50, 9)                              # only this turn's line


def test_a_coding_turn_over_acp_adds_onto_its_session_s_row(tmp_path, monkeypatch):
    from taskuary import acpcoding
    s = MemoryStore(); tid = s.create_task({'Title': 'Comment the ledger totals', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
    t = acpcoding.ACPCoding.__new__(acpcoding.ACPCoding)
    t.store, t.task_id, t.sid, t.cli, t.started = s, tid, 'pane1', 'claude', datetime.now().isoformat(sep=' ', timespec='seconds')
    t.client = mock.Mock(session_id='sess_fake_1', last_turn={'usage': {'inputTokens': 10, 'cachedReadTokens': 0, 'cachedWriteTokens': 0, 'outputTokens': 4},
                                                              '_meta': {'quota': {'model_usage': [{'model': 'claude-opus-5-5'}]}}})
    rid = brainroute.log(s, brainroute.choose(s, 'coding', task=tid), tid)        # the route the router logged as the pane opened
    t._used(t.started, 1200); t._used(t.started, 800)
    row = s.brain_routes(tid, limit=1)[0]
    assert (row['Id'], row['Sid'], row['Ran'], row['TokensIn'], row['TokensOut'], row['Calls'], row['Ms']) == (rid, 'pane1', 'claude-opus-5-5', 20, 8, 2, 2000)


# ── our model id, the agent's spelling ─────────────────────────────────────────────────────────────────────────────────────
CLAUDE = ['default', 'opus', 'opus[1m]', 'sonnet', 'sonnet[1m]', 'haiku']


@pytest.mark.parametrize('want,offered,to', [
    ('claude-opus-5-5', CLAUDE, 'opus'), ('claude-sonnet-5-5', CLAUDE, 'sonnet'), ('claude-haiku-5', CLAUDE, 'haiku'), ('opus', CLAUDE, 'opus'),
    ('claude-opus-5-5', ['claude-opus-5-5-20261001', 'claude-sonnet-5-5-20261001'], 'claude-opus-5-5-20261001'),
    ('claude-opus-5-5', ['claude-opus-5-5[1m]', 'claude-opus-5-5'], 'claude-opus-5-5'),
    ('gpt-5.5-codex', ['gpt-5.5', 'gpt-5.5-codex', 'gpt-5.4-codex'], 'gpt-5.5-codex'), ('GPT-5.5', ['gpt-5.5', 'gpt-5.5-codex'], 'gpt-5.5'),
    ('gpt-5.5-codex', ['gpt-5.5', 'gpt-5.4'], 'gpt-5.5'), ('gpt-9', ['opus', 'sonnet'], ''), ('claude-opus-5-5', ['sonnet', 'haiku'], '')])
def test_our_model_id_is_matched_to_what_the_agent_offers(want, offered, to):
    assert agents.offered_model(want, offered) == to


def test_effort_goes_to_the_nearest_offered():
    assert [agents.offered_effort(w, ['low', 'medium', 'high']) for w in ('max', 'xhigh', 'minimal', 'medium', 'odd')] == ['high', 'high', 'low', 'medium', '']


@pytest.mark.parametrize('pick,models,said', [('claude-opus-5-5@max', 'default,opus,sonnet,haiku', 'model=opus effort=high'),
                                              ('claude-haiku-5', 'default,opus,sonnet,haiku', 'model=haiku'),
                                              ('gpt-5.5-codex@low', 'gpt-5.5,gpt-5.5-codex', 'model=gpt-5.5-codex effort=low')])
def test_a_matched_model_is_set_quietly_and_nothing_reaches_the_chat(monkeypatch, pick, models, said):
    monkeypatch.setenv('FAKE_ACP_MODELS', models)
    ev, c = [], acp.ACPClient(FAKE[0], FAKE[1:], timeout=30)
    try:
        c.connect(); c.new_session(HERE)
        agents._acp_gears(c, {'model': pick}, 'claude', lambda k, n, d=None: ev.append((k, n, d)))
        _stop, out = c.prompt('go')
    finally: c.close()
    assert said in out and not ev


def test_a_model_this_sign_in_cannot_run_is_said_in_plain_words(monkeypatch):
    monkeypatch.setenv('FAKE_ACP_MODELS', 'sonnet,haiku')
    ev, c = [], acp.ACPClient(FAKE[0], FAKE[1:], timeout=30)
    try:
        c.connect(); c.new_session(HERE)
        agents._acp_gears(c, {'model': 'claude-opus-5-5'}, 'C:/tools/claude.exe', lambda k, n, d=None: ev.append((k, n, d)))
    finally: c.close()
    assert [d for _k, _n, d in ev] == ['claude-opus-5-5 is not available on this claude sign-in, so this ran on opus']
