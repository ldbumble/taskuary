"""One brain resolver behind triage, the setup checklist and the startup migration.

The bug: a fresh install pinned `default_brain` to claude whether or not Claude Code was installed, so an
install given an Anthropic key per the docs read "running on Anthropic" on the checklist while every message
landed "AI triage failed ('claude' not found on PATH)" - and a working CLI with no key never got the tick.

These tests run the REAL agents.default_pick: conftest stubs it to '' for every test (no_connection_brains),
which is exactly why the suite never saw this.
"""
import json
from unittest import mock

import pytest

from taskuary import agents, llm, setup
from taskuary.store import MemoryStore


@pytest.fixture
def real_pick():
    """...and the real brains: the `claude` connection a fresh install's config.toml carries (conftest empties them too)."""
    from taskuary import config
    real = config.load
    with mock.patch.object(agents, 'default_pick', agents.default_pick.real), \
         mock.patch.object(agents, 'connection_brains', agents.connection_brains.real), \
         mock.patch.object(config, 'load', side_effect=lambda: {**real(), 'cli_connections': {'claude': {'cmd': 'claude'}}}): yield


def _fresh():
    """What server start leaves on a fresh install: the claude connection, the shipped coding profile (instructions, no
    command of its own), nothing chosen."""
    s = MemoryStore()
    s.upsert_agent('coding', 'coding', 'cli', json.dumps({'kind': 'coding'}))
    return s


def _key(s, typ='anthropic'):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test', 'Active': 1}, 't')
    return cid


def _cli(installed):
    """Whether a CLI resolves on PATH - the one probe every readiness check goes through."""
    if installed: return mock.patch.object(agents, '_resolve_cmd', return_value=['claude'])
    return mock.patch.object(agents, '_resolve_cmd', side_effect=FileNotFoundError("'claude' not found on PATH"))


def _ai_step(s):
    return next(x for x in setup.state(s)['steps'] if x['key'] == 'ai')


def test_no_cli_and_a_key_runs_on_the_key_everywhere(real_pick):
    s = _fresh(); cid = _key(s)
    with _cli(False), mock.patch.object(llm, 'make_llm', side_effect=lambda typ, conf, secret: ('api', typ)) as made:
        assert not agents.adopt_brain_setting(s)                   # a missing CLI is never persisted
        assert not s.get_setting('default_brain')
        assert llm.effective_pick(s) == f'connector:{cid}'
        step = _ai_step(s)
        brain = llm.build_llm(s)                                   # the door triage asks
    # the brain that runs, by name; the row itself ticks once it is picked (firstrun.rail, test_setup_state)
    assert step['detail'] == 'running on Anthropic API'
    assert brain is not None and made.call_args[0][0] == 'anthropic'


def test_a_migrated_claude_that_is_not_installed_gives_way_to_the_key(real_pick):
    """An install the old migration already pinned heals without anyone touching the setting."""
    s = _fresh(); cid = _key(s)
    s.set_setting('default_brain', 'claude', 'migration')
    with _cli(False):
        assert llm.effective_pick(s) == f'connector:{cid}'
        assert _ai_step(s)['detail'] == 'running on Anthropic API'


def test_a_working_cli_and_no_key_runs_on_the_cli_and_ticks(real_pick):
    s = _fresh()
    with _cli(True):
        assert agents.adopt_brain_setting(s)
        assert s.get_setting('default_brain') == 'claude'
        assert llm.effective_pick(s) == 'cli:claude'
        step = _ai_step(s)
    assert step['detail'] == 'running on Claude'                  # by the name the setup canvas gives it


def test_a_working_cli_wins_over_a_key_when_nothing_is_chosen(real_pick):
    """'First connected should not matter' (the owner, 2026-09-24): blank is the default brain when it runs."""
    s = _fresh(); _key(s)
    with _cli(True): assert llm.effective_pick(s) == 'cli:claude'


def test_neither_is_not_done_and_says_why(real_pick):
    s = _fresh()
    with _cli(False):
        assert llm.effective_pick(s) == ''
        step = _ai_step(s)
        assert llm.build_llm(s) is None                            # untriaged, not "claude not found" per message
    assert not step['done'] and 'no AI connector' in step['detail']
    assert step['goto']['hash'] == 'cli-agents'


def test_a_chosen_brain_that_does_not_start_is_kept_and_flagged(real_pick):
    """The owner's choice is not swapped behind their back - but the checklist stops claiming it works."""
    s = _fresh(); _key(s)
    s.set_setting('triage_ai', 'cli:claude', 'owner')
    with _cli(False):
        assert llm.effective_pick(s) == 'cli:claude'
        step = _ai_step(s)
    assert not step['done'] and 'not installed' in step['detail']
    s.set_setting('triage_ai', '', 'owner'); s.set_setting('default_brain', 'claude', 'owner')
    with _cli(False): assert llm.effective_pick(s) == 'cli:claude'   # an owner-chosen default brain too


def test_a_chosen_connector_with_no_key_is_not_done():
    s = MemoryStore(); cid = s.get_connector_by_type('openai')['ConnectorId']
    s.set_setting('triage_ai', f'connector:{cid}', 'owner')
    step = _ai_step(s)
    assert not step['done'] and 'no key' in step['detail']
