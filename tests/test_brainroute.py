"""The router's one door (brainroute.choose) gives exactly today's answer while Auto is off.

Fixed mode is what a fresh install runs (the owner, 2026-10-25: "Auto is OFF on a fresh install, and nothing changes until it is
turned on"). So the golden matrix below holds `choose` against the resolvers every caller asked before the router existed, over
the homes those resolvers were each written for. Fake CLIs only: nothing here starts a real one.
"""
import ast, json
from datetime import datetime, timedelta
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
           'agents': {'coding': {'kind': 'coding'}}}
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
    if job == 'assistant': return concierge.pick(s), concierge.model_of(s)      # its saved model, on the brain it was saved for
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
        assert brainroute.mode(s) == 'auto'                     # the default since 2026-11-06; Fixed is the owner's choice
        s.set_setting('ai_route_mode', 'fixed', 'owner')
        for job in brainroute.JOBS:
            r = brainroute.choose(s, job)
            assert (r.pick, r.model) == _today(s, job), (home, job)
            assert r.tier == 'fixed' and r.rule == 'fixed'
            assert r.gear == ('main' if job in ('general', 'coding', 'quick_work', 'advisor') else 'light')
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
        # a session's own pick keeps the model it came with - none is the brain's own normal gear (climodels.gears: the owner's ruling,
        # 2026-11-20), never the saved assistant_model
        r = brainroute.choose(s, 'general', want_pick='cli:claude')
        assert (r.pick, r.model) == ('cli:claude', 'sonnet@medium')
        # ...and an empty pick is what blank means - the reading build_llm always made of it, now said on the route
        assert brainroute.choose(s, 'general', want_pick='').pick == llm.effective_pick(s, '')


def test_a_saved_model_follows_the_brain_it_was_saved_for(real):
    """The live shape: the general card's model was picked while its brain was Claude, the default brain became Codex, and
    Codex was started with a Claude model name - it answered nothing. A model applies to the brain it was saved for."""
    from taskuary import aidefaults, climodels
    real.update({'claude', 'codex'})
    lists = {'claude': ['claude-sonnet-5-5'], 'codex': ['gpt-5.5']}
    for stamped in (True, False):                               # saved with its brain beside it; and a row from before that
        s, cfg, _ = _home(('claude', 'codex'), {'claude': True, 'codex': True}, {'default_brain': 'claude'})
        with mock.patch.object(config, 'load', lambda: cfg), \
             mock.patch.object(climodels, 'catalog', lambda cli: {'choices': lists.get(cli, [])}):
            clic.sync(cfg, s)
            if stamped: aidefaults.keep_model(s, 'assistant_model', 'claude-sonnet-5-5', 'owner')
            else: s.set_setting('assistant_model', 'claude-sonnet-5-5', 'owner')
            r = brainroute.choose(s, 'general')
            assert (r.pick, r.model) == ('cli:claude', 'claude-sonnet-5-5'), stamped
            s.set_setting('default_brain', 'codex', 'owner')
            r = brainroute.choose(s, 'general')
            assert r.pick == 'cli:codex' and r.model != 'claude-sonnet-5-5', (stamped, r.model)
            assert s.get_setting('assistant_model') == 'claude-sonnet-5-5', 'the setting itself is never rewritten'
            s.set_setting('default_brain', 'claude', 'owner')
            assert brainroute.choose(s, 'general').model == 'claude-sonnet-5-5', 'and it is back with its brain'


def test_a_saved_session_on_one_brain_with_anothers_model_shows_and_runs_that_brains_own(real, monkeypatch):
    """The owner's live app, 2026-11-23 ("why does this say both claude and codex????"): a task's saved conversation was Codex with a Claude
    model - its chip read "OpenAI Codex CLI · claude-sonnet", its menu ticked Codex's default, and every turn started Codex with the Claude
    name ("not supported when using Codex with a ChatGPT account"). A pair that does not belong together is the brain's own default - in the
    run, in what the task says ran it, and so on its chip; a model the brain offers is kept."""
    from taskuary import climodels, server
    real.update({'claude', 'codex'})
    lists = {'claude': ['claude-sonnet-5-5'], 'codex': ['gpt-5.5']}
    s, cfg, _ = _home(('claude', 'codex'), {'claude': True, 'codex': True}, {'default_brain': 'codex'})
    with mock.patch.object(config, 'load', lambda: cfg), mock.patch.object(climodels, 'catalog', lambda cli: {'choices': lists.get(cli, [])}):
        clic.sync(cfg, s)
        monkeypatch.setattr(server, 'store', s)
        tid = s.create_task({'Title': 'Quarterly close checklist', 'Kind': 'general', 'Status': 'open'}, 'router')
        s.save_session(tid, 'cli:codex', 'claude-sonnet-5-5', '', 'ctx')
        assert general.opening(s, s.get_task(tid))[:2] == ('cli:codex', 'claude-sonnet-5-5'), 'the live shape: the stored pair'
        pick, _, model = general._selected(s, model='claude-sonnet-5-5', pick='cli:codex')
        assert pick == 'cli:codex' and 'claude' not in model, model
        assert server._ran_on(tid)['model'] == '', 'the chip: Codex at its default, as the menu ticks it'
        sess = general.GeneralSession(s, tid)
        assert sess.pick == 'cli:codex' and 'claude' not in sess.model, sess.model
        assert s.saved_session(tid)['Model'] == sess.model, 'and the conversation is saved as it runs'
        assert general._selected(s, model='gpt-5.5', pick='cli:codex')[2] == 'gpt-5.5', 'a model the brain offers is kept'
        assert general._selected(s, model='claude-sonnet-5-5', pick='cli:claude')[2] == 'claude-sonnet-5-5'


def test_a_task_no_ai_has_worked_names_the_one_that_will(real, monkeypatch):
    """Walk 11 (2026-11-23): a stranger's task, held before any agent ran, wore a bare "AI" chip at its head - nothing had run, so nothing was
    named. The task says which AI WILL take it - the router's own answer, the one Settings says - and nothing where none would."""
    from taskuary import climodels, server
    real.update({'codex'})
    s, cfg, _ = _home(('codex',), {'codex': True}, {'default_brain': 'codex'})
    with mock.patch.object(config, 'load', lambda: cfg), mock.patch.object(climodels, 'catalog', lambda cli: {'choices': ['gpt-5.5']}):
        clic.sync(cfg, s)
        monkeypatch.setattr(server, 'store', s)
        tid = s.create_task({'Title': 'Seat pricing for next year', 'Kind': 'general', 'Status': 'open'}, 'router')
        assert server._ran_on(tid) is None, 'the live shape: nothing has run it'
        will = server._will_run(s.get_task(tid))
        assert will and will['pick'] == 'cli:codex' and will['brain'], will
        assert will == {k: v for k, v in brainroute.runs(s, 'general', cfg).items() if k in ('pick', 'brain', 'model')}, 'the router says it, once'
    bare, cfg2, _ = _home()
    with mock.patch.object(config, 'load', lambda: cfg2):
        monkeypatch.setattr(server, 'store', bare)
        tid = bare.create_task({'Title': 'Seat pricing for next year', 'Kind': 'general', 'Status': 'open'}, 'router')
        assert server._will_run(bare.get_task(tid)) is None, 'no AI connected: no chip'


def test_a_cli_is_never_handed_a_model_it_does_not_run(real):
    """The live shape, 2026-11-13: "Quick general work -> standard on codex (CLI), claude-sonnet-5-5 (rule work)" - Codex exited 1, "not
    supported when using Codex with a ChatGPT account", on every quick call. The general card's model came along whatever it was saved for,
    and Claude's own list (its built-in aliases, no catalogue cached) did not name it, so nothing called it Claude's. Whatever road a model
    comes by, the router hands a CLI only a model that CLI runs - else its own, at the tier's effort."""
    from taskuary import aidefaults, climodels
    real.update({'claude', 'codex'})
    lists = {'codex': {'choices': ['gpt-5.5'], 'source': 'codex models_cache.json'}, 'claude': {'choices': ['opus', 'sonnet', 'haiku'], 'source': 'built-in'}}
    for conns in (('codex',), ('claude', 'codex')):
        s, cfg, _ = _home(conns, {k: True for k in conns}, {'default_brain': 'codex'})
        with mock.patch.object(config, 'load', lambda: cfg), mock.patch.object(climodels, 'catalog', lambda cli: lists.get(cli, {'choices': []})):
            clic.sync(cfg, s)
            aidefaults.keep_model(s, 'assistant_model', 'claude-sonnet-5-5', 'owner', 'cli:codex')     # stamped for the wrong brain
            for job in ('quick_work', 'general'):
                r = brainroute.choose(s, job)
                assert r.pick == 'cli:codex' and 'claude-sonnet-5-5' not in r.model and r.model in ('', '@low', '@high'), (conns, job, r.model, r.why)
            assert brainroute.choose(s, 'general', want_pick='cli:codex', want_model='gpt-5.5').model == 'gpt-5.5'     # its own model is kept
            assert aidefaults.fits(s, 'sonnet', 'cli:claude') if 'claude' in conns else True                    # ...and an alias of its own


def test_the_default_ai_is_asked_once_and_a_choice_is_never_written_over(real):
    """The live shape: two CLIs connected, a start named the first one ready as the default, and a day of work ran on a tool
    nobody picked. With several, the one question is owed - on the bell and on the Settings card - until answered or put down."""
    from taskuary import aidefaults, problems
    real.update({'claude', 'codex'})
    s, cfg, _ = _home(('claude', 'codex'), {'claude': True, 'codex': True})
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        assert agents.adopt_brain_setting(s) and s.setting_writer('default_brain') == 'migration'
        ask, bell = agents.default_ask(s), lambda: [p for p in problems.collect(s) if p['key'] == 'default_ai']
        assert sorted(ask['options']) == ['claude', 'codex'] and ask['runs'] == s.get_setting('default_brain')
        assert len(bell()) == 1 and bell()[0]['where'] == 'Settings'
        card = aidefaults.resolve(s, cfg, 'default_brain')
        assert card.get('ask') and card['note'] == ask['note'] and ask['detail'] == bell()[0]['detail'], 'one set of facts, each ending with its own move'
        problems.dismiss(s, 'default_ai')                              # put down: it was asked, once
        assert not bell() and not aidefaults.resolve(s, cfg, 'default_brain').get('ask')
        assert s.setting_writer('default_brain') == 'migration', 'putting it down chose nothing for them'
        s.set_setting(problems.DISMISSED, '{}', 't')
        s.set_setting('default_brain', 'claude', 'owner')              # answered: theirs from here on
        assert agents.default_ask(s) == {} and not bell() and not agents.adopt_brain_setting(s)
        assert s.get_setting('default_brain') == 'claude' and not problems.news(s), 'no "working again" for an answered question'
    real.clear(); real.add('codex')


def test_the_default_question_lists_every_cli_that_can_take_work_and_ends_with_the_move(real):
    """The owner, 2026-11-11: "it says codex not claude why?" - five names read "are both connected", a CLI that worked all day was
    not among them because one test of it had failed (nothing but another Test cleared the mark), and the sentence ended on a place
    instead of the pick. The list is what can take work now: one resting says until when, one left out says why and its way back,
    and choosing the one already running counts as choosing."""
    from taskuary import aidefaults, llm
    real.update({'claude', 'codex', 'gemini'})
    s, cfg, _ = _home(('codex', 'claude', 'gemini'), {'codex': True, 'gemini': True, 'claude': False})
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        assert agents.adopt_brain_setting(s) and s.get_setting('default_brain') == 'codex'
        ask = agents.default_ask(s)
        assert ask['note'].startswith('OpenAI Codex CLI and Gemini CLI are both connected and you have not chosen between them, so work runs on OpenAI Codex CLI')
        assert 'Claude Code is left out: its last test failed - press Test on it under Connections.' in ask['note']
        assert ask['note'].endswith('Choose one in the list above - choosing OpenAI Codex CLI again counts.')
        assert ask['detail'].endswith('Choose one in Settings, on the Coding agent card.')
        # ...IT ANSWERS WORK: the failed mark is over, by the call itself - and three names are "all", never "both"
        with mock.patch.object(llm, 'make_cli_llm', lambda *a, **k: (lambda *a, **k: 'ok')):
            assert llm.build_llm(s, 'cli:claude', job='summary')('s', 'u') == 'ok'
        assert agents.cli_tests(s)['claude'] is True and 'claude' in agents.ready_brains(s)
        brainroute.cool(s, 'cli:claude', datetime.now() + timedelta(hours=2))
        note = agents.default_ask(s)['note']
        assert ' are all connected ' in note and 'left out' not in note
        from taskuary.timewords import clock
        assert f"Claude Code (resting until {clock(brainroute.cooldowns(s)['cli:claude'])})" in note
        # ...THE ONE IT TOOK, RESTING (rendered 2026-11-11): the card's RUNS line named the CLI that had the work meanwhile and the question
        # under it still said "work runs on" the resting one - it does once it is back; and a card whose AI rests with nothing to
        # take its work says until when, as the "right now" rows do
        assert 'once it is back' not in note
        brainroute.cool(s, 'cli:codex', datetime.now() + timedelta(hours=2))
        till = clock(brainroute.cooldowns(s)['cli:codex'])
        assert f'so work runs on OpenAI Codex CLI, the first one ready, once it is back.' in agents.default_ask(s)['note']
        s.set_setting('triage_backup_ai', '', 'owner')
        gen, rows = aidefaults.resolve(s, cfg, 'assistant_ai'), brainroute.now(s, cfg)
        # ...and with both resting, whatever else is connected takes the work meanwhile (the owner, 2026-11-24), and says why
        assert gen['runs']['brain'] == 'Gemini CLI' and gen['runs']['why'] == f'Running on Gemini CLI - OpenAI Codex CLI is limited until {till}'
        assert {r['why'] for r in rows} == {f'Running on Gemini CLI - OpenAI Codex CLI is limited until {till}'} and brainroute.resting(s, 'cli:gemini') == ''
        s.set_setting(brainroute.COOL_KEY, json.dumps({'cli:claude': brainroute.cooldowns(s)['cli:claude'].isoformat(sep=' ', timespec='minutes')}), 'router')
        # ...and THE CURRENT ONE, CHOSEN, IS A CHOICE: the same value, now the owner's - the question is over and nothing else moved
        card = aidefaults.apply(s, cfg, 'default_brain', value=aidefaults.resolve(s, cfg, 'default_brain')['value'])
        assert s.get_setting('default_brain') == 'codex' and s.setting_writer('default_brain') == 'owner'
        assert agents.default_ask(s) == {} and not card.get('ask') and card['chosen'] and not card['set_by']
    real.clear(); real.add('codex')


def test_a_card_says_what_runs_and_whose_choice_it_was(real):
    """The owner, 2026-11-11: "where is general agent??" and "never change from what's in settings" - each card's RUNS line is the
    router's own answer for its job (the "right now" rows' function), and a value nobody chose says so beside the pick."""
    from taskuary import aidefaults
    real.update({'claude', 'codex'})
    s, cfg, _ = _home(('codex', 'claude'), {'codex': True, 'claude': True})
    cfg['cli_connections']['claude']['model'] = 'opus'
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        s.set_setting('default_brain', 'claude', 'migration')
        gen, code = aidefaults.resolve(s, cfg, 'assistant_ai'), aidefaults.resolve(s, cfg, 'default_brain')
        assert (code['chosen'], code['set_by']) == (False, aidefaults.SAVED_FOR) and gen['set_by'] == aidefaults.FOLLOWS
        s.set_setting('ai_route_mode', 'fixed', 'owner')
        gen, row = aidefaults.resolve(s, cfg, 'assistant_ai'), brainroute.now(s, cfg)[1]
        assert (gen['runs']['brain'], gen['runs']['model']) == (row['brain'], row['model']) == ('Claude Code', 'opus')
        # the general agent's model box is the general agent's (assistant_model, for this AI) - never the light gear triage rides
        with mock.patch.object(config, 'save'), mock.patch.object(clic, 'sync'):
            aidefaults.apply(s, cfg, 'assistant_ai', model='sonnet')
        assert 'light_model' not in cfg['cli_connections']['claude'] and s.get_setting('assistant_model') == 'sonnet'
        gen, row = aidefaults.resolve(s, cfg, 'assistant_ai'), brainroute.now(s, cfg)[1]
        assert gen['model'] == 'sonnet' and gen['runs']['model'] == row['model'] == 'sonnet'
        aidefaults.apply(s, cfg, 'assistant_ai', value='cli:codex')
        gen = aidefaults.resolve(s, cfg, 'assistant_ai')
        assert gen['chosen'] and not gen['set_by'] and gen['runs']['brain'] == brainroute.now(s, cfg)[1]['brain'] == 'OpenAI Codex CLI'
    real.clear(); real.add('codex')
    s, cfg, _ = _home(('codex',), {'codex': True})
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        assert agents.adopt_brain_setting(s) and agents.default_ask(s) == {}, 'one CLI is no choice: it is used, and shown'
        assert aidefaults.resolve(s, cfg, 'default_brain')['value'] == 'cli:codex'


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
    s = MemoryStore(); s.set_setting('ai_route_mode', 'fixed', 'owner')          # the cards, as before the router
    seen = {}
    monkeypatch.setattr(llm, '_build_llm', lambda store, pick, model, *a, **kw: seen.update(pick=pick, model=model, gear=a[-3]) or (lambda *x, **k: 'ok'))
    monkeypatch.setattr(llm, 'effective_pick', lambda store, pick=None: str(pick if pick is not None else store.get_setting('triage_ai') or '') or 'cli:claude')
    llm.build_llm(s, job='draft')
    assert seen == {'pick': 'cli:claude', 'model': None, 'gear': 'light'}
    llm.build_llm(s, pick='connector:7', model='m1', gear='main', job='general')
    assert seen == {'pick': 'connector:7', 'model': 'm1', 'gear': 'main'}


def test_the_demo_still_answers_from_its_script(monkeypatch):
    monkeypatch.setattr(demo, 'enabled', lambda: True)
    assert llm.build_llm(MemoryStore(), job='draft') is not None


# ── slice 2: one fallback path ─────────────────────────────────────────────────────────────────────────────────────────────

def _cli_rows(s, **rows):
    for name, cmd in rows.items(): s.upsert_agent(name, 'coding', 'cli', json.dumps({'cmd': cmd}))


def _calls(s, fail=('claude',)):
    called = []
    def made(store, name, *args, **kwargs):
        def answer(system, user, **kw):
            called.append(name)
            if name in fail: raise RuntimeError("You've hit your session limit; resets at noon")
            return f'{name} answered'
        return answer
    return called, mock.patch.object(llm, 'make_cli_llm', side_effect=made)


def test_a_failover_walks_the_route_s_chain():
    s = MemoryStore(); _cli_rows(s, claude='claude', codex='codex')
    s.set_setting('triage_ai', 'cli:claude', 'owner'); s.set_setting('triage_backup_ai', 'cli:codex', 'owner')
    called, made = _calls(s)
    with made, mock.patch.object(brainroute, '_backups', return_value=['cli:codex']) as chain:
        assert llm.build_llm(s, job='draft')('sys', 'user') == 'codex answered'
    assert called == ['claude', 'codex'] and chain.called       # the backups came from the route, not a second reading


def test_two_settings_naming_one_cli_do_not_try_it_twice():
    "Two profiles over one executable: trying claude again is not failover, it is the same paid failure twice."
    s = MemoryStore(); _cli_rows(s, writer='claude', reader='claude', codex='codex')
    s.set_setting('triage_ai', 'cli:writer', 'owner'); s.set_setting('triage_backup_ai', 'cli:reader, cli:codex', 'owner')
    called, made = _calls(s, fail=('writer', 'reader'))
    with made: assert llm.build_llm(s, job='summary')('sys', 'user') == 'codex answered'
    assert called == ['writer', 'codex']


def test_a_general_session_keeps_the_backups_it_always_had():
    s = MemoryStore(); s.set_setting('triage_backup_ai', 'cli:codex', 'owner')
    assert brainroute.choose(s, 'general', want_pick='cli:claude').chain == ['cli:codex']
    assert brainroute.choose(s, 'assistant', want_pick='cli:claude').chain == ['cli:codex']


def test_a_coding_pane_walks_backup_brains(monkeypatch):
    s = MemoryStore(); s.set_setting('backup_brains', 'codex', 'owner')
    monkeypatch.setattr(config, 'load', lambda: {'cli_connections': {'claude': {'cmd': 'claude'}, 'codex': {'cmd': 'codex'}}})
    assert brainroute.session_chain(s, 'claude') == agents.brain_chain(s, 'claude') == ['claude', 'codex']
    assert brainroute.choose(s, 'coding', want_pick='cli:claude').chain == ['cli:codex']


def test_a_blank_anthropic_card_reads_mail_on_its_light_model_and_keeps_its_own_for_the_rest(real):
    """A blank model box on an Anthropic card read every mail on Opus, thinking less (the readiness review, 2026-11-14). Its quick jobs
    run on the provider's light model as a CLI's do; a model the owner typed is his, and agent work stays on the card's own."""
    s, cfg, cid = _home((), connector='anthropic', settings={'ai_route_mode': 'auto'})
    with mock.patch.object(config, 'load', lambda: cfg):
        r = brainroute.choose(s, 'triage')
        assert (r.pick, r.tier, r.model) == (f'connector:{cid}', 'light', llm.PROVIDER_LIGHT['anthropic'])
        assert brainroute.choose(s, 'general').model != llm.PROVIDER_LIGHT['anthropic']
        assert brainroute._words(s, f'connector:{cid}', cfg)['quick'] == llm.PROVIDER_LIGHT['anthropic']
        c = s.get_connector(cid); s.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps({**json.loads(c.get('ConfigJson') or '{}'), 'model': 'claude-sonnet-5'})}, 'owner')
        assert llm.PROVIDER_LIGHT['anthropic'] not in brainroute.choose(s, 'triage').model, 'a model he typed is his'


def test_an_ai_cards_quick_agent_work_is_its_own_model_thinking_less_and_its_light_model_only_the_one_shot_jobs(real):
    """A gateway card set up with a light model (firstrun.tier_models: a Flash) ran every agent task triage judged quick on it, and the agent
    did the work badly (the owner, 2026-11-20). Its light box is for the one-shot jobs; an agent's quick gear is the card's own model at low
    effort, normal its model, hard its strong one."""
    s, cfg, cid = _home((), connector='hipaa_ai', settings={'ai_route_mode': 'auto'})
    c = s.get_connector(cid)
    s.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps({**json.loads(c.get('ConfigJson') or '{}'), 'base_url': 'https://gw.example',
                      'model': 'gem-hydrogen', 'light_model': 'gem-flash', 'strong_model': 'gem-neon'})}, 'owner')
    p = f'connector:{cid}'
    for k in ('assistant_ai', 'triage_ai'): s.set_setting(k, p, 'owner')
    with mock.patch.object(config, 'load', lambda: cfg):
        assert brainroute.choose(s, 'triage').model in ('', 'gem-flash')       # ...the card's light box, swapped in by its gear
        assert brainroute.choose(s, 'triage').gear == 'light'
        q = brainroute.choose(s, 'general', difficulty='quick')
        assert (q.pick, q.model) == (p, 'gem-hydrogen@low'), q.why
        assert brainroute.choose(s, 'general', difficulty='standard').model in ('', 'gem-hydrogen')
        assert 'gem-neon' in brainroute.choose(s, 'general', difficulty='hard').model or brainroute.choose(s, 'general', difficulty='hard').gear == 'strong'
        assert brainroute._words(s, p, cfg)['quick'] == 'gem-hydrogen, low effort'


def test_a_level_model_saved_as_the_pickers_whole_object_reads_and_saves_as_its_id():
    # the live setting, 2026-11-23: the quick level's model held "{'id': 'gpt-6.2-sol', 'label': ...}" - the check refused it and quick work
    # ran on Codex's default, not the model he picked
    import json
    from taskuary.store import MemoryStore
    s = MemoryStore()
    s.set_setting(brainroute.LEVEL_KEY, json.dumps({'quick': {'pick': 'cli:codex', 'model': "{'id': 'gpt-6.2-sol', 'label': 'GPT-6.2-Sol'}"}}), 'owner')
    assert brainroute.by_level(s)['quick']['model'] == 'gpt-6.2-sol'
    brainroute.save_by_level(s, {'quick': {'pick': 'cli:codex', 'model': {'id': 'gpt-6.2-astra', 'label': 'GPT-6.2-Astra'}}})
    assert brainroute.by_level(s)['quick']['model'] == 'gpt-6.2-astra'


def test_the_advisor_thinks_on_the_normal_model_never_triages_quick_one(real):
    """The owner, 2026-11-24: the twice-a-day Advisor look ran on triage's card at its light gear - the sorting model. It runs where general
    work does: the general agent's AI on its normal gear, and in Auto the AI he set for normal work."""
    real.add('claude')
    s, cfg, cid = _home(('claude',), {'claude': True}, connector='anthropic')
    p = f'connector:{cid}'
    s.set_setting('triage_ai', p, 'owner'); s.set_setting('assistant_ai', 'cli:claude', 'owner')
    with mock.patch.object(config, 'load', lambda: cfg):
        clic.sync(cfg, s)
        s.set_setting('ai_route_mode', 'fixed', 'owner')
        r, g = brainroute.choose(s, 'advisor', gear='light'), brainroute.choose(s, 'general')
        assert (r.pick, r.gear) == (g.pick, 'main') and r.pick != brainroute.choose(s, 'triage').pick, r.why
        s.set_setting('ai_route_mode', 'auto', 'owner')
        r = brainroute.choose(s, 'advisor', gear='light')
        assert (r.tier, r.gear) == ('standard', 'main') and r.pick == brainroute.choose(s, 'general').pick, r.why
        brainroute.save_by_level(s, {'normal': {'pick': p, 'model': 'claude-sonnet-5'}})
        r = brainroute.choose(s, 'advisor')
        assert (r.pick, r.model, r.level) == (p, 'claude-sonnet-5', 'normal'), r.why
