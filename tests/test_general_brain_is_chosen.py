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
        # a gateway answers only the jobs set to it (agents.PICKED_ONLY) - first-run setup names them all, as here
        if connector in agents.PICKED_ONLY:
            for k in ('triage_ai', 'concierge_ai', 'assistant_ai'): s.set_setting(k, f'connector:{cid}', 'owner')
    return s, cfg


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Patches the doors a run goes through: which CLIs are on this machine (`installed`), what a CLI run was asked to start
    (`ran`, by command), and what an API brain was built for (`api`)."""
    w = {'installed': set(), 'ran': [], 'api': [], 'signed_out': set()}
    w['run_cli'] = agents.run_cli                  # the real one, for the test that follows a command down it
    def resolve(cmd):
        if Path(str(cmd)).name in w['installed']: return [str(cmd)]
        raise FileNotFoundError(f'{cmd} not found on PATH')
    def run_cli(prof, prompt, trace, resume=None, cancel=None, extra_env=None):
        w['ran'].append({'cmd': prof.get('cmd'), 'args': list(prof.get('args') or []), 'held': bool(prof.get('held_only'))})
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


def _again(s, tid, text='Try again.'):
    """Try again, as its door sends it: the failed turn's session is closing (GeneralSession._end_soon), so the line goes to a fresh one."""
    _run.sess.close(learn=False, report=False); general.drop_session(tid)
    _run.sess = general.GeneralSession(s, tid)
    return _run.sess.send_prompt(text, echo=False)


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


def _job(s):
    """The owner's own general job (it was a playbook-authoring task: playbooks are built by the Assistant on their page now, build.py)."""
    return s.create_task({'Title': 'Check the Payworth invoice against the purchase order', 'Kind': 'general', 'Status': 'open',
                          'OriginBase': 'owner'}, 'owner')


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


@pytest.mark.acp                       # the adapters kept: whether codex has a held road decides how it runs
def test_the_owner_s_own_job_is_not_a_stranger_s_task_and_runs_on_codex_with_its_tools(world):
    world['installed'] |= {'codex'}
    s, cfg = _home(('codex',), tests={'codex': True}, settings={'default_brain': 'codex', 'assistant_ai': 'cli:codex'})
    tid = _job(s)
    assert origin.of_task(s, tid)[0] == 'owner'
    said = _run(s, cfg, tid)
    assert not said.startswith('error'), said
    assert [r['cmd'] for r in world['ran']] == ['codex']
    # ...on the held road, never its sandbox bypass: over ACP a read outside the task asks (the owner, 2026-11-16)
    assert world['ran'][0]['held'] and '--dangerously-bypass-approvals-and-sandbox' not in world['ran'][0]['args']


def test_a_refusal_never_names_another_tool(world):
    """2026-10-22, the owner: "never suggest another coding tool" - the way on is Trust them, whatever is connected."""
    world['installed'] |= {'gemini'}
    s, _ = _home(('gemini',), tests={'gemini': True})
    with mock.patch.object(config, 'load', lambda: {'cli_connections': {'gemini': clic.with_defaults({'cmd': 'gemini'})}}):
        assert 'claude' not in origin.no_reviewer(s)
        world['installed'] |= {'claude'}
        cfg = {**config.load(), 'cli_connections': {k: clic.with_defaults({'cmd': k}) for k in ('gemini', 'claude')}}
        agents.record_cli_test(s, 'claude', True)
        with mock.patch.object(config, 'load', lambda: cfg): assert 'claude' not in origin.no_reviewer(s) and 'Trust them' in origin.no_reviewer(s)


# ── Claude only ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_claude_only_home_runs_the_researcher_and_a_playbook_on_claude(world):
    world['installed'] |= {'claude'}
    s, cfg = _home(('claude',), tests={'claude': True}, settings={'default_brain': 'claude', 'assistant_ai': 'cli:claude'})
    _run(s, cfg, _researcher(s)); _run(s, cfg, _job(s))
    assert [r['cmd'] for r in world['ran']] == ['claude', 'claude']


# ── An API connector only ─────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('typ', ['hipaa_ai', 'openai'])
def test_an_api_only_home_runs_the_researcher_and_a_playbook_on_the_connector(world, typ):
    s, cfg = _home(connector=typ)
    for tid in (_researcher(s), _job(s)):
        said = _run(s, cfg, tid)
        assert 'claude' not in said.lower() and not said.startswith('error'), said
    assert world['ran'] == [] and world['api'] == [typ] * 2


# ── No AI at all ──────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('leftover', [(), ('claude',)], ids=['nothing', 'a-claude-whose-test-failed'])
def test_a_home_with_no_ai_fails_saying_so(world, leftover):
    world['installed'] |= set(leftover)
    s, cfg = _home(leftover, tests={k: False for k in leftover})
    for tid in (_researcher(s), _job(s)):
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
        with pytest.raises(agents.NoAI, match='No AI is connected'): llm.make_cli_llm(s, 'researcher')


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
    with mock.patch.object(config, 'load', lambda: cfg): again = _again(s, tid)
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
        _again(s, tid)
    assert [r['cmd'] for r in world['ran']] == ['claude', 'claude']          # never quietly another AI
    assert s.get_setting('assistant_ai') == 'cli:claude'


# ── One resolver behind every launch road that names no CLI ──────────────────────────────────────────────────────
def _roads(s, world):
    """What each launch road resolves a profile that names no CLI to - by the command it ends up running."""
    from taskuary import terminal
    bare, out = {'kind': 'research'}, {}
    out['with_cmd'] = agents.with_cmd(bare, s)['cmd']
    out['resume_argv'] = agents.resume_argv(bare, 'abc', s)
    for name, call in (('run_cli', lambda: world['run_cli'](bare, 'hi', lambda *a: None, store=s)),
                       ('run_acp', lambda: agents.run_acp(bare, 'hi', lambda *a: None, store=s))):
        with mock.patch.object(agents, '_resolve_cmd', side_effect=FileNotFoundError('stop here')) as r:
            try: call()
            except Exception: pass
            out[name] = Path(str(r.call_args[0][0])).name if r.called else None
    world['ran'].clear()
    llm.make_cli_llm(s, 'researcher')('sys', 'hi')
    out['make_cli_llm'] = world['ran'][-1]['cmd']
    with mock.patch.object(terminal, 'Term') as term, mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        terminal.open_session(s, 'researcher', cwd=str(Path.cwd()))
        out['open_session'] = Path(str(term.call_args[0][0][0])).name
    return out


def test_a_codex_only_home_resolves_every_launch_road_to_codex(world):
    world['installed'] |= {'codex'}
    s, cfg = _home(('codex',), tests={'codex': True})
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        got = _roads(s, world)
    assert got == {'with_cmd': 'codex', 'resume_argv': ['resume', 'abc'], 'run_cli': 'codex', 'run_acp': 'codex',
                   'make_cli_llm': 'codex', 'open_session': 'codex'}


def test_the_brain_named_in_settings_wins_over_another_ready_cli(world):
    world['installed'] |= {'codex', 'gemini'}
    s, cfg = _home(('codex', 'gemini'), tests={'codex': True, 'gemini': True}, settings={'default_brain': 'gemini'})
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        assert agents.resolve_brain(s, 'coding') == 'cli:gemini'
        got = _roads(s, world)
    assert {v for k, v in got.items() if k != 'resume_argv'} == {'gemini'}


def test_a_connector_only_home_resolves_to_the_connector_and_a_pane_says_it_needs_a_coding_tool(world):
    from taskuary import terminal
    s, cfg = _home(connector='hipaa_ai')
    cid = s.get_connector_by_type('hipaa_ai')['ConnectorId']
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        assert agents.resolve_brain(s, 'general') == agents.resolve_brain(s, 'coding') == f'connector:{cid}'
        assert agents.resolve_brain(s, 'coding', cli_only=True) == ''
        with pytest.raises(agents.NoAI) as e: terminal.open_session(s, 'researcher', cwd=str(Path.cwd()))
    assert 'needs a coding tool - connect one' in str(e.value) and 'claude' not in str(e.value).lower()


def test_a_home_with_nothing_resolves_to_nothing():
    s, cfg = _home(())
    with mock.patch.object(config, 'load', lambda: cfg):
        assert agents.resolve_brain(s, 'general') == ''
        with pytest.raises(agents.NoAI, match='No AI is connected'): agents.with_cmd({}, s)
    with pytest.raises(agents.NoAI): agents.with_cmd({})          # no store, no command: never a claude in its place
    assert origin._claude_version('') == ()


# ── A connector-only home runs every kind of work ─────────────────────────────────────────────────────────────────
class _Now:
    "A thread that runs where it is started - the test reads what the turn did."
    def __init__(self, target, args=(), **kw): self.go = lambda: target(*args)
    def start(self): self.go()


def test_a_connector_only_home_runs_a_coding_task_on_the_connector_as_the_coding_task_it_is(world):
    "By the roads that start a terminal too (a carry-on, a queue drain): its card's session, as the Send button starts it (general.on_card)."
    from taskuary import general, terminal
    s, cfg = _home(connector='hipaa_ai')
    tid = s.create_task({'Title': 'Fix the invoice export', 'Kind': 'coding', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
    with mock.patch.object(config, 'load', lambda: cfg), mock.patch.object(terminal, 'threading', mock.Mock(Thread=_Now)), \
         mock.patch.dict(terminal.SESSIONS, {}, clear=True):          # the session it opens is this test's
        clic.sync(cfg, s)
        try: out = terminal.start_on_task(s, tid)
        finally: general.ON_CARD.discard(tid)
    assert out['general'] and s.get_task(tid)['Kind'] == 'coding'
    assert world['ran'] == [] and world['api'] == ['hipaa_ai']
    assert not any('general agent works this' in str(c.get('Body') or '') for c in s.list_comments(tid))


def test_a_connector_only_home_with_developer_mode_off_runs_a_coding_task_as_the_general_agent(world):
    from taskuary import terminal
    s, cfg = _home(connector='hipaa_ai')
    tid = s.create_task({'Title': 'Fix the invoice export', 'Kind': 'coding', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
    with mock.patch.object(agents, 'developer_mode', agents.developer_mode.real): _as_the_general_agent(world, s, cfg, tid)


def _as_the_general_agent(world, s, cfg, tid):
    from taskuary import terminal
    with mock.patch.object(config, 'load', lambda: cfg), mock.patch.object(terminal, 'threading', mock.Mock(Thread=_Now)),          mock.patch.dict(terminal.SESSIONS, {}, clear=True):          # the session it opens is this test's, never the next one's
        clic.sync(cfg, s)
        out = terminal.start_on_task(s, tid)
    assert out['general'] and s.get_task(tid)['Kind'] == 'general'
    assert world['ran'] == [] and world['api'] == ['hipaa_ai']
    assert not any('claude' in str(c.get('Body') or '').lower() for c in s.list_comments(tid))


def test_a_connector_only_home_triages_answers_and_runs_reports_and_workflows_on_the_connector(world):
    from taskuary import concierge, reports, workflows
    s, cfg = _home(connector='hipaa_ai')
    cid = s.get_connector_by_type('hipaa_ai')['ConnectorId']
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        assert llm.effective_pick(s) == f'connector:{cid}' and llm.build_llm(s)       # triage
        assert concierge.pick(s) == f'connector:{cid}'                                  # the Assistant
        said, body = reports.run_agent({'store': s, 'prompt': 'Summarise the week for Alex Doyle'})
        assert 'claude' not in (said + body).lower()
        for runs in ('general', 'coding'):
            assert workflows.brain(s, {'runs_on': runs})['pick'] == f'connector:{cid}'
    assert world['ran'] == [] and world['api'][-1] == 'hipaa_ai'


# ── The invariant ────────────────────────────────────────────────────────────────────────────────────────────────
def test_no_launch_road_defaults_a_missing_cli_to_any_one_cli():
    """A run that names no CLI asks the one resolver (agents.resolve_brain); no road may put a CLI of its own choosing in the
    gap. Said as the shapes such a default takes, not as a list of places - a new road that grows one fails here."""
    import re
    shapes = [r"get\(\s*'cmd'\s*,\s*'[a-z-]+'\s*\)", r"get\('cmd'\)\s*or\s*'[a-z-]+'", r"\bcmd\s+or\s+'[a-z-]+'",
              r"\b(?:cli|cmd)\s*:\s*str\s*=\s*'[a-z-]+'"]
    bad = [f'{p.name}:{i}: {l.strip()}' for p in sorted(Path(agents.__file__).parent.glob('*.py'))
           for i, l in enumerate(p.read_text(encoding='utf-8').splitlines(), 1) if any(re.search(x, l) for x in shapes)]
    assert bad == []


# ── ONE RESOLVER: every road that asks "which AI runs this" gets the same answer ──────────────────────────────────────
def _two_ready(**settings):
    "claude and codex both connected, installed and passed - claude first in the list - and the Coding agent card set by the owner to codex."
    return _home(('claude', 'codex'), tests={'claude': True, 'codex': True}, settings={'default_brain': 'codex', **settings})


def test_a_blank_card_reads_the_default_brain_on_every_road(world):
    """The general agent's session, triage and the Assistant read a blank card as the default brain; resolve_brain - what reports, a
    coding task on no CLI and the Settings card's RUNS line read - took the first ready CLI instead: two AIs for one blank."""
    from taskuary import concierge
    world['installed'] |= {'claude', 'codex'}
    s, cfg = _two_ready()
    with mock.patch.object(config, 'load', lambda: cfg):
        assert agents.resolve_brain(s, 'general') == general._selected(s)[0] == 'cli:codex'
        assert agents.resolve_brain(s, 'triage') == llm.effective_pick(s) == 'cli:codex'
        assert agents.resolve_brain(s, 'assistant') == concierge.default_pick(s) == 'cli:codex'


def test_a_coding_pane_its_role_row_and_its_failover_head_name_one_cli(world):
    "brain_for, the pane's chain and the row sync (cli_connections.brain_of) read the settings each their own way; now the resolver's."
    world['installed'] |= {'claude', 'codex'}
    s, cfg = _two_ready()
    s.set_setting('profile_brains', json.dumps({'researcher': 'claude'}), 'owner')
    with mock.patch.object(config, 'load', lambda: cfg):
        for role, want in (('coding', 'codex'), ('researcher', 'claude')):
            assert agents.brain_for(s, role) == agents.resolve_brain(s, 'coding', cli_only=True, role=role)[4:] == want
            assert clic.brain_of(s, cfg, role, {}) == want
        assert agents.brain_chain(s)[0] == agents.resolve_brain(s, 'coding', cli_only=True)[4:] == 'codex'


def test_a_brain_an_update_saved_that_no_longer_starts_is_set_aside_by_every_road(world):
    "Triage read its card raw and brain_for read default_brain raw: a saved-for-him gemini that is gone kept both while the rest moved on."
    world['installed'] |= {'codex'}
    s, cfg = _home(('codex', 'gemini'), tests={'codex': True})
    for k, v in (('default_brain', 'gemini'), ('triage_ai', 'cli:gemini')): s.set_setting(k, v, 'migration')
    with mock.patch.object(config, 'load', lambda: cfg):
        assert llm.effective_pick(s) == agents.resolve_brain(s, 'triage') == 'cli:codex'
        assert agents.brain_for(s, 'coding') == agents.brain_chain(s)[0] == 'codex'


def test_the_task_header_names_the_ai_its_session_opens_on(world):
    """The header (server: defaultPick) kept a saved conversation on a CLI whose test failed since; the session set it aside and opened on
    the card's AI. One answer (general.opening) for both."""
    world['installed'] |= {'claude', 'codex'}
    s, cfg = _home(('claude', 'codex'), tests={'claude': False, 'codex': True})
    tid = _researcher(s)
    s.save_session(tid, 'cli:claude', '', 'sid-old', '')
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        shown = general.default_pick(s, s.get_task(tid))         # before the session saves its own pick over the old one
        sess = general.GeneralSession(s, tid)
        try: assert shown == sess.pick == 'cli:codex'
        finally: sess.close(learn=False, report=False); general.drop_session(tid)


def test_is_there_an_ai_is_asked_of_the_job_that_will_run(world):
    """The New sheet's Plan it read triage's AI; its press read the general agents' list - one sheet, two answers. Each job has its
    own answer now, from the AI that job runs on: here triage's card is his and ready while the general agent is set to a CLI not installed."""
    from taskuary import brainroute, capabilities
    world['installed'] |= {'codex'}
    s, cfg = _home(('codex', 'gemini'), tests={'codex': True}, connector='anthropic')
    cid = s.get_connector_by_type('anthropic')['ConnectorId']
    s.set_setting('triage_ai', f'connector:{cid}', 'owner'); s.set_setting('assistant_ai', 'cli:gemini', 'owner')
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        assert capabilities.has_ai(s) and capabilities.has_ai(s, 'assistant')
        assert brainroute.choose(s, 'general').pick == general._selected(s)[0] == 'cli:gemini'
        assert not capabilities.has_ai(s, 'general')
        assert capabilities.capabilities(s)['ai_for'] == {'triage': True, 'general': False, 'assistant': True}
