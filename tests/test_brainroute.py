"""The router's one door (brainroute.choose) gives exactly today's answer while Auto is off.

Fixed mode is what a fresh install runs (the owner, 2026-10-25: "Auto is OFF on a fresh install, and nothing changes until it is
turned on"). So the golden matrix below holds `choose` against the resolvers every caller asked before the router existed, over
the homes those resolvers were each written for. Fake CLIs only: nothing here starts a real one.
"""
import ast, json
from pathlib import Path
from unittest import mock

import pytest

from taskuary import agents, brainroute, cli_connections as clic, concierge, config, demo, general, llm
from taskuary.store import MemoryStore

ROOT = Path(__file__).resolve().parents[1] / 'taskuary'


def test_every_build_llm_in_the_app_names_its_job():
    """A call that names no job rides the triage brain without saying so - which is how the owner's replies came to be written
    by the cheapest model. The job is what the call is FOR, from the closed list, never a word from the mail."""
    bare = []
    for p in sorted(ROOT.glob('*.py')):
        for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
            if isinstance(n, ast.Call) and getattr(n.func, 'id', getattr(n.func, 'attr', '')) == 'build_llm':
                job = next((k.value for k in n.keywords if k.arg == 'job'), None)
                if not (isinstance(job, ast.Constant) and job.value in brainroute.JOBS): bare.append(f'{p.name}:{n.lineno}')
    assert not bare, f'build_llm without a job= from brainroute.JOBS: {bare}'


def test_an_unknown_job_is_a_bug_not_a_guess():
    with pytest.raises(ValueError): brainroute.choose(MemoryStore(), 'newsletter')


def _home(conns=(), tests=None, settings=None, connector=None, by='owner'):
    s = MemoryStore()
    cfg = {**config.load(), 'cli_connections': {k: clic.with_defaults({'cmd': k}) for k in conns},
           'agents': {n: {'kind': p['kind'], 'purpose': p['purpose']} for n, p in agents.DEFAULT_PROFILES.items()}}
    for k, ok in (tests or {}).items(): agents.record_cli_test(s, k, ok)
    for k, v in (settings or {}).items(): s.set_setting(k, v, by)
    cid = None
    if connector:
        cid = s.get_connector_by_type(connector)['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1}, 'owner')
    return s, cfg, cid


@pytest.fixture
def real(monkeypatch):
    "The real default brain and connection brains (conftest stubs both), with a PATH that holds only what a test installs."
    installed = set()
    def resolve(cmd):
        if Path(str(cmd)).name in installed: return [str(cmd)]
        raise FileNotFoundError(f'{cmd} not found on PATH')
    monkeypatch.setattr(agents, 'connection_brains', agents.connection_brains.real)
    monkeypatch.setattr(agents, 'default_pick', agents.default_pick.real)
    monkeypatch.setattr(agents, '_resolve_cmd', resolve)
    return installed


HOMES = {   # name: (connections, installed, tests, settings, connector, writer)
    'no AI': ((), (), {}, {}, None, 'owner'),
    'claude only': (('claude',), ('claude',), {'claude': True}, {}, None, 'owner'),
    'codex only': (('codex',), ('codex',), {'codex': True}, {}, None, 'owner'),
    'connector only': ((), (), {}, {}, 'anthropic', 'owner'),
    'mixed': (('claude', 'codex'), ('claude', 'codex'), {'claude': False, 'codex': True}, {}, 'anthropic', 'owner'),
    'owner picked': (('claude', 'codex'), ('claude', 'codex'), {}, {'triage_ai': 'cli:codex', 'assistant_ai': 'cli:claude',
                                                                     'default_brain': 'codex', 'concierge_model': 'sonnet'}, None, 'owner'),
    'migrated, not installed': (('claude',), (), {}, {'default_brain': 'claude'}, 'anthropic', 'migration'),
    'codex effort-only': (('codex',), ('codex',), {'codex': True}, {'assistant_model': 'effort:high'}, None, 'owner'),
}


def _today(s, job, task=None):
    "What each job ran on before the router - the resolver its caller asked, read straight."
    if job in brainroute.ONE_SHOT: return llm.effective_pick(s), ''
    if job == 'coding': return agents.resolve_brain(s, 'coding', cli_only=True), ''
    if job == 'assistant': return concierge.pick(s), str(s.get_setting('concierge_model') or '')
    pick = general.default_pick(s, task)
    base = general._selected(s)
    return pick, (base[2] if pick == base[0] else general._selected(s, pick=pick)[2] if pick else '')


@pytest.mark.parametrize('home', HOMES)
def test_fixed_mode_is_todays_answer_for_every_job(real, home):
    conns, inst, tests, settings, connector, by = HOMES[home]
    real.update(inst)
    s, cfg, _ = _home(conns, tests, settings, connector, by)
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        assert brainroute.mode(s) == 'fixed'
        for job in brainroute.JOBS:
            r = brainroute.choose(s, job)
            assert (r.pick, r.model) == _today(s, job), (home, job)
            assert r.tier == 'fixed' and r.rule == 'fixed'
            assert r.gear == ('main' if job in ('general', 'coding') else 'light')
            # the reason names what runs, or says nothing does - never a vendor the home does not have
            assert r.why and (agents.NO_AI in r.why) == (not r.pick)


def test_the_concrete_answers_behind_the_matrix(real):
    "So the matrix is not merely agreeing with itself: a few homes spelled out."
    real.update({'codex'})
    s, cfg, _ = _home(('codex',), {'codex': True})
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        assert brainroute.choose(s, 'triage').pick == 'cli:codex'
        assert brainroute.choose(s, 'draft').pick == 'cli:codex'           # drafts ride triage's brain, as they always have
        assert brainroute.choose(s, 'coding').pick == 'cli:codex'
    s, cfg, cid = _home((), connector='anthropic')
    with mock.patch.object(config, 'load', lambda: cfg):
        assert brainroute.choose(s, 'triage').pick == f'connector:{cid}'
        assert brainroute.choose(s, 'coding').pick == ''                  # coding needs a terminal, never a connector
    s, cfg, _ = _home()
    with mock.patch.object(config, 'load', lambda: cfg):
        r = brainroute.choose(s, 'triage')
        assert (r.pick, r.why) == ('', f'{agents.NO_AI}, so triage waits')


def test_an_explicit_pick_wins_with_exactly_its_own_model(real):
    s, cfg, cid = _home(('claude',), connector='anthropic', settings={'triage_ai': 'cli:claude', 'assistant_model': 'opus'})
    real.add('claude')
    with mock.patch.object(config, 'load', lambda: cfg):
        r = brainroute.choose(s, 'report', want_pick=f'connector:{cid}', want_model='claude-opus-5')
        assert (r.pick, r.model, r.rule) == (f'connector:{cid}', 'claude-opus-5', 'you chose it')
        # a session's own pick keeps the model it came with - '' is the brain's own, not the saved assistant_model
        r = brainroute.choose(s, 'general', want_pick='cli:claude')
        assert (r.pick, r.model) == ('cli:claude', '')
        # ...and an empty pick stays empty, for build_llm to read as "what blank means", exactly as before
        assert brainroute.choose(s, 'general', want_pick='').pick == ''


def test_a_browser_task_still_takes_the_brain_with_hands(real):
    s, cfg, _ = _home(('codex',), {'codex': True}, connector='anthropic')
    real.add('codex')
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        from taskuary import browserview
        t = {'TaskId': 0, 'Tags': browserview.WANTS}
        assert brainroute.choose(s, 'general', task=t).pick == general.default_pick(s, t)


def test_the_backups_ride_the_route_for_one_message_jobs():
    s = MemoryStore(); s.set_setting('triage_ai', 'cli:claude', 'owner'); s.set_setting('triage_backup_ai', 'cli:claude, cli:codex', 'owner')
    assert brainroute.choose(s, 'draft').chain == ['cli:codex']           # the primary is not its own backup


def test_build_llm_asks_the_router_and_builds_what_it_says(monkeypatch):
    s = MemoryStore()
    seen = {}
    monkeypatch.setattr(llm, '_build_llm', lambda store, pick, model, *a: seen.update(pick=pick, model=model, gear=a[-3]) or (lambda *x, **k: 'ok'))
    monkeypatch.setattr(llm, 'effective_pick', lambda store, pick=None: str(pick if pick is not None else store.get_setting('triage_ai') or '') or 'cli:claude')
    llm.build_llm(s, job='draft')
    assert seen == {'pick': 'cli:claude', 'model': None, 'gear': 'light'}
    llm.build_llm(s, pick='connector:7', model='m1', gear='main', job='general')
    assert seen == {'pick': 'connector:7', 'model': 'm1', 'gear': 'main'}


def test_the_demo_still_answers_from_its_script(monkeypatch):
    monkeypatch.setattr(demo, 'enabled', lambda: True)
    assert llm.build_llm(MemoryStore(), job='draft') is not None
