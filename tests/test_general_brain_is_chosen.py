"""A general agent runs on the AI the person set up - never on claude because nobody chose anything.

A fresh install where the person had set up only Codex: a researcher task started on a claude that was signed out (a claude
connection left behind, first in the list, was the fallback), and a playbook the person created themselves was refused on Codex
as "a stranger's task - start it with claude". The rule: the brain the owner chose; else only an AI that is connected, starts
here and did not fail its test; else "No AI is connected". Fake CLIs only - nothing here starts a real one."""
import json
from pathlib import Path
from unittest import mock

import pytest

from taskuary import agents, cli_connections as clic, config, general, llm, origin, playbooks
from taskuary.store import MemoryStore


def _home(conns=(), tests=None, settings=None, connector=None):
    """A home with these CLI connections (and their last Test), the shipped profiles synced before any brain was chosen - as a
    fresh start leaves them - and optionally one API connector holding a key."""
    s = MemoryStore()
    cfg = {**config.load(), 'cli_connections': {k: clic.with_defaults({'cmd': k}) for k in conns},
           'agents': {n: {'kind': p['kind'], 'purpose': p['purpose']} for n, p in agents.DEFAULT_PROFILES.items()}}
    for k, ok in (tests or {}).items(): agents.record_cli_test(s, k, ok)
    for k, v in (settings or {}).items(): s.set_setting(k, v, 'owner')
    if connector:
        cid = s.get_connector_by_type(connector)['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1}, 'owner')
    return s, cfg


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Patches the doors a run goes through: which CLIs are on this machine (`installed`), what a CLI run was asked to start
    (`ran`, by command), and what an API brain was built for (`api`)."""
    w = {'installed': set(), 'ran': [], 'api': [], 'signed_out': set()}
    def resolve(cmd):
        if Path(str(cmd)).name in w['installed']: return [str(cmd)]
        raise FileNotFoundError(f'{cmd} not found on PATH')
    def run_cli(prof, prompt, trace, resume=None, cancel=None, extra_env=None):
        w['ran'].append({'cmd': prof.get('cmd'), 'args': list(prof.get('args') or [])})
        if prof.get('cmd') in w['signed_out']: raise RuntimeError(agents.signed_out_msg('assistant', 'Not logged in', prof['cmd']))
        return 'Here is what I found.', 'sid-1', ''
    def make_llm(typ, conf, secret):
        w['api'].append(typ)
        return lambda system, user, **kw: 'Here is what I found.'
    monkeypatch.setattr(agents, 'connection_brains', agents.connection_brains.real)
    monkeypatch.setattr(agents, 'default_pick', agents.default_pick.real)
    monkeypatch.setattr(agents, '_resolve_cmd', resolve)
    monkeypatch.setattr(agents, 'run_cli', run_cli)
    monkeypatch.setattr(llm, 'make_llm', make_llm)
    monkeypatch.setattr(config, 'home', lambda: tmp_path)
    monkeypatch.setattr(origin, '_claude_version', lambda cmd='claude': (2, 1, 300))
    (tmp_path / 'scratch').mkdir()
    return w


def _run(s, cfg, tid):
    """Start the task's general agent and send one turn, as Start does; what it said, or the error it failed with."""
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        sess = _run.sess = general.GeneralSession(s, tid)
        try: return sess.send_prompt('Go ahead.', echo=False)
        except Exception as e: return f'error: {e}'


def _researcher(s):
    return s.create_task({'Title': 'Compare payroll vendors', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner',
                          'Assignee': 'agent:researcher'}, 'owner')


def _playbook(s, example=None):
    return playbooks.setup_task(s, 'Every month, check the Payworth invoice against the purchase order', message_id=example)['taskId']


def _stranger_mail(s):
    return s.add_message({'ExternalId': 'x1', 'Channel': 'email', 'Direction': 'in', 'Subject': 'Invoice 4471',
                          'FromEmail': 'billing@vendor.example', 'FromName': 'Vendor billing', 'BodyText': 'Please pay.',
                          'SentAt': '2026-10-01 09:00:00', 'Status': 'filed'})


# ── Codex only ────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('chose', [True, False], ids=['picked-at-setup', 'connected-on-its-card'])
def test_a_codex_only_home_runs_the_researcher_on_codex(world, chose):
    """Even beside a claude left connected on this machine that never passed its test (a sign-in that was never finished)."""
    world['installed'] |= {'codex', 'claude'}
    s, cfg = _home(('claude', 'codex'), tests={'claude': False, 'codex': True},
                   settings={'default_brain': 'codex', 'assistant_ai': 'cli:codex'} if chose else {})
    _run(s, cfg, _researcher(s))
    assert [r['cmd'] for r in world['ran']] == ['codex']


def test_an_untested_claude_does_not_outrank_the_codex_that_passed(world):
    world['installed'] |= {'codex', 'claude'}
    s, cfg = _home(('claude', 'codex'), tests={'codex': True})
    _run(s, cfg, _researcher(s))
    assert [r['cmd'] for r in world['ran']] == ['codex']


def test_the_owner_s_own_playbook_is_not_a_stranger_s_task_and_runs_on_codex_with_its_tools(world):
    world['installed'] |= {'codex'}
    s, cfg = _home(('codex',), tests={'codex': True}, settings={'default_brain': 'codex', 'assistant_ai': 'cli:codex'})
    tid = _playbook(s)
    assert origin.of_task(s, tid)[0] == 'owner'
    said = _run(s, cfg, tid)
    assert not said.startswith('error'), said
    assert [r['cmd'] for r in world['ran']] == ['codex']
    assert '--dangerously-bypass-approvals-and-sandbox' in world['ran'][0]['args']      # the owner's work launches as it always did


def test_a_playbook_from_a_stranger_s_mail_runs_on_codex_in_its_read_only_sandbox(world):
    """A real stranger's words, on a CLI with no reviewer: Codex's own read-only sandbox - never a refusal naming claude."""
    world['installed'] |= {'codex'}
    s, cfg = _home(('codex',), tests={'codex': True}, settings={'default_brain': 'codex', 'assistant_ai': 'cli:codex'})
    tid = _playbook(s, _stranger_mail(s))
    assert origin.of_task(s, tid)[0] == 'stranger'
    said = _run(s, cfg, tid)
    assert 'claude' not in said.lower(), said
    assert [r['cmd'] for r in world['ran']] == ['codex']
    args = world['ran'][0]['args']
    assert '--dangerously-bypass-approvals-and-sandbox' not in args and args[args.index('--sandbox') + 1] == 'read-only'


def test_a_refusal_offers_only_an_ai_that_is_connected(world):
    world['installed'] |= {'gemini'}
    s, _ = _home(('gemini',), tests={'gemini': True})
    with mock.patch.object(config, 'load', lambda: {'cli_connections': {'gemini': clic.with_defaults({'cmd': 'gemini'})}}):
        assert 'claude' not in origin.no_reviewer(s)
        world['installed'] |= {'claude'}
        cfg = {**config.load(), 'cli_connections': {k: clic.with_defaults({'cmd': k}) for k in ('gemini', 'claude')}}
        agents.record_cli_test(s, 'claude', True)
        with mock.patch.object(config, 'load', lambda: cfg): assert origin.no_reviewer(s).endswith('start it with claude')


# ── Claude only ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_claude_only_home_runs_the_researcher_and_a_playbook_on_claude(world):
    world['installed'] |= {'claude'}
    s, cfg = _home(('claude',), tests={'claude': True}, settings={'default_brain': 'claude', 'assistant_ai': 'cli:claude'})
    _run(s, cfg, _researcher(s)); _run(s, cfg, _playbook(s))
    assert [r['cmd'] for r in world['ran']] == ['claude', 'claude']


# ── An API connector only ─────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('typ', ['hipaa_ai', 'openai'])
def test_an_api_only_home_runs_the_researcher_and_a_playbook_on_the_connector(world, typ):
    s, cfg = _home(connector=typ)
    for tid in (_researcher(s), _playbook(s), _playbook(s, _stranger_mail(s))):
        said = _run(s, cfg, tid)
        assert 'claude' not in said.lower() and not said.startswith('error'), said
    assert world['ran'] == [] and world['api'] == [typ] * 3


# ── No AI at all ──────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('leftover', [(), ('claude',)], ids=['nothing', 'a-claude-whose-test-failed'])
def test_a_home_with_no_ai_fails_saying_so(world, leftover):
    world['installed'] |= set(leftover)
    s, cfg = _home(leftover, tests={k: False for k in leftover})
    for tid in (_researcher(s), _playbook(s)):
        said = _run(s, cfg, tid)
        assert said.startswith('error: No AI is connected'), said
    assert world['ran'] == []


def test_a_role_row_that_names_no_cli_is_never_read_as_claude(world):
    world['installed'] |= {'claude'}
    assert not agents.runs_here({'kind': 'research'})
    s, cfg = _home(())
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        assert 'cmd' not in json.loads(s.get_agent('researcher')['Config'])
        assert llm.make_cli_llm(s, 'researcher') is None


# ── A machine an older start already pinned to claude heals on upgrade ───────────────────────────────────────────────
def _pinned(writer='migration'):
    """claude saved as the default and the general brain by a start before this fix - not by the person - beside a Codex that
    passed its test; claude is on the machine but not signed in, and nothing has tested it."""
    s, cfg = _home(('claude', 'codex'), tests={'codex': True})
    for k, v in (('default_brain', 'claude'), ('assistant_ai', 'cli:claude'), ('triage_ai', 'cli:claude')): s.set_setting(k, v, writer)
    return s, cfg


@pytest.mark.parametrize('writer', ['migration', ''], ids=['adopted', 'unmarked'])
def test_startup_clears_a_saved_claude_that_is_not_signed_in_and_the_researcher_runs_on_codex(world, writer):
    world['installed'] |= {'codex', 'claude'}; world['signed_out'] |= {'claude'}
    s, cfg = _pinned(writer)
    asked = []
    with mock.patch.object(config, 'load', lambda: cfg),          mock.patch('taskuary.clisetup.signed_in', side_effect=lambda name: asked.append(name) or name != 'claude'):
        assert set(agents.heal_brains(s)) == {'default_brain', 'assistant_ai', 'triage_ai'}       # what startup runs
    assert asked == ['claude'] and agents.cli_tests(s)['claude'] is False                       # asked once, and remembered
    _run(s, cfg, _researcher(s))
    assert [r['cmd'] for r in world['ran']] == ['codex']


def test_a_launch_that_finds_a_saved_claude_signed_out_moves_to_codex_for_the_next_try(world):
    """No probe at startup (it could not tell): the first start fails on claude, says so - and Try again runs on codex."""
    world['installed'] |= {'codex', 'claude'}; world['signed_out'] |= {'claude'}
    s, cfg = _pinned()
    tid = _researcher(s)
    first = _run(s, cfg, tid)
    assert "claude isn't signed in" in first
    with mock.patch.object(config, 'load', lambda: cfg): again = _run.sess.send_prompt('Try again.', echo=False)
    assert not again.startswith('error') and [r['cmd'] for r in world['ran']] == ['claude', 'codex']
    assert not s.get_setting('default_brain') and not s.get_setting('assistant_ai')


def test_a_claude_the_person_picked_stays_and_says_it_is_not_signed_in(world):
    world['installed'] |= {'codex', 'claude'}; world['signed_out'] |= {'claude'}
    s, cfg = _pinned('owner')
    with mock.patch.object(config, 'load', lambda: cfg), mock.patch('taskuary.clisetup.signed_in', return_value=False) as probe:
        assert agents.heal_brains(s) == [] and not probe.called
    tid = _researcher(s)
    said = _run(s, cfg, tid)
    assert "claude isn't signed in" in said and 'Set it up' in said, said
    with mock.patch.object(config, 'load', lambda: cfg), pytest.raises(RuntimeError, match="claude isn't signed in"):
        _run.sess.send_prompt('Try again.', echo=False)
    assert [r['cmd'] for r in world['ran']] == ['claude', 'claude']          # never quietly another AI
    assert s.get_setting('assistant_ai') == 'cli:claude'
