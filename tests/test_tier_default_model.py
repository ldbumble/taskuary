"""A model is chosen only when the owner picked it (the owner's live install, 2026-11-06). Every general turn logged "Tier fixed, Rule 'you
chose it'" in Auto on quick and standard tasks alike: the session carried its CLI's DEFAULT model to the router as an explicit one, and any
model there skips the tier rules. The default is nobody's choice - a session saved before the fix carries it too - so it pins nothing."""
import json
from unittest import mock

import pytest

from taskuary import agents, brainroute, config, general, llm
from taskuary.store import MemoryStore

CFG = {'cli_connections': {'claude': {'cmd': 'claude', 'model': 'claude-opus-5-5'}}}


@pytest.fixture
def s():
    s = MemoryStore()
    for k, v in (('assistant_ai', 'cli:claude'), ('triage_ai', 'cli:claude'), ('default_brain', 'claude')): s.set_setting(k, v, 'owner')
    cfg = {**config.load(), **CFG}
    with mock.patch.object(config, 'load', lambda: cfg), mock.patch.object(agents, 'runs_here', lambda prof: bool(prof)), \
         mock.patch.object(agents, 'connection_brains', agents.connection_brains.real): yield s


def _task(s, difficulty):
    tid = s.create_task({'Title': 'Find the venue address', 'Status': 'open'}, 'owner')
    s.judge_task(tid, {'difficulty': difficulty}, 'triage')
    return tid


def _turn(s, ses):
    "One turn of the session up to its brain: the route the router chose for it, logged as the live install logs it."
    seen = []
    def built(store, pick, model, *a, **kw):
        seen.append((pick, model, a[7]))
        return lambda *a_, **k_: 'The venue is on Harbour Street.'
    with mock.patch.object(llm, '_build_llm', built): ses.send_prompt('Where is it?')
    return s.brain_routes(ses.task_id, limit=1)[0], seen[0]


def test_a_default_model_session_routes_by_tier(s):
    ses = general.GeneralSession(s, _task(s, 'quick'))
    assert (ses.pick, ses.model, ses.chosen) == ('cli:claude', 'claude-opus-5-5', '')     # the picker's "default · claude-opus-5-5"
    row, (pick, model, gear) = _turn(s, ses)
    assert (row['Tier'], row['Rule']) == ('light', 'quick-work') and gear == 'light'
    assert row['Why'] == 'General work judged quick -> light on Claude Code (rule quick-work)'
    row, _ = _turn(s, general.GeneralSession(s, _task(s, 'standard')))
    assert (row['Tier'], row['Rule']) == ('standard', 'work')


def test_an_explicit_per_task_pick_still_wins(s):
    ses = general.GeneralSession(s, _task(s, 'quick'), model='claude-sonnet-5-5')
    assert ses.chosen == 'claude-sonnet-5-5'
    row, (pick, model, gear) = _turn(s, ses)
    assert (row['Tier'], row['Rule'], model) == ('fixed', 'you chose it', 'claude-sonnet-5-5')
    # ...and kept for the task: the next session on it opens on the same pick, still the owner's
    assert general.GeneralSession(s, ses.task_id).chosen == 'claude-sonnet-5-5'


def test_a_stored_default_from_an_old_session_does_not_pin(s):
    tid = _task(s, 'quick')
    s.save_session(tid, 'cli:claude', 'claude-opus-5-5', '', '')                 # what every session saved before the fix carries
    ses = general.GeneralSession(s, tid)
    assert ses.model == 'claude-opus-5-5' and ses.chosen == ''
    row, _ = _turn(s, ses)
    assert (row['Tier'], row['Rule']) == ('light', 'quick-work')


def test_the_router_itself_takes_no_default_as_a_choice(s):
    "Any caller that carries the brain's own model back (a picker sending its default) still routes by tier - only for the agents' work."
    r = brainroute.choose(s, 'general', task=_task(s, 'quick'), want_pick='cli:claude', want_model='claude-opus-5-5')
    assert (r.tier, r.rule) == ('light', 'quick-work')
    r = brainroute.choose(s, 'general', task=_task(s, 'quick'), want_pick='cli:claude', want_model='claude-sonnet-5-5')
    assert (r.tier, r.rule, r.model) == ('fixed', 'you chose it', 'claude-sonnet-5-5')
