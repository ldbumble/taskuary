"""THE RAIL ADVISOR'S EVAL IN CI (2026-10-20): every kind of idea the clock Advisor puts on the rail, in the worlds where it should
fire and the ones where it should not (tests/rail_advisor_cases.py), through the real run with the scripted brain. A case that
should fire is a hit, one that should not is quiet - a miss or a line that is not useful (noise) fails, with its reason. The demo +
faults world is checked twice with every line put down between, and no line of it may be noise."""
from unittest import mock
import pytest
from taskuary import assistant, faults, terminal
from tests import rail_advisor_cases as C

# what still fails, and why - strict, so a fix that lands without crossing it off fails too
KNOWN = {
    'twelve mails put down, none taken up': "the automation card's skip-rule idea beside the rule question",
}
WORLD_KNOWN = {
}


@pytest.fixture(scope='module')
def results():
    sessions, agenda = dict(terminal.SESSIONS), dict(assistant._AGENDA)
    try:
        with mock.patch.object(faults, 'scratch_home', lambda: True):
            got = C.run_all()
        yield {r['case']: r for r in got}
    finally:
        for sid, r in list(terminal.SESSIONS.items()):
            if sid not in sessions:
                try: r.alive = False
                except Exception: pass
                terminal.SESSIONS.pop(sid, None)
        assistant._AGENDA.clear(); assistant._AGENDA.update(agenda)


def _case(results, name):
    r = results[name]
    if name in KNOWN or name in WORLD_KNOWN:
        if r['out'] in ('noise', 'miss'): pytest.xfail(KNOWN.get(name) or WORLD_KNOWN[name])
        pytest.fail(f'{name} is fixed now ({r["out"]}) - cross it off KNOWN')
    return r


@pytest.mark.parametrize('name', [c[1] for c in C.CASES])
def test_each_case_fires_where_it_should_and_nowhere_else(results, name):
    r = _case(results, name)
    want = 'hit' if r['should'] else 'quiet'
    assert r['out'] == want, f"{r['kind']} / {name}: {r['out']} - {r['why']} (lines: {r['lines']})"


def test_the_world_raises_no_noise(results):
    bad = {k: r['why'] for k, r in results.items() if k.startswith('world') and r['out'] == 'noise' and k not in WORLD_KNOWN}
    assert not bad, bad
    for k in WORLD_KNOWN:
        if k in results and results[k]['out'] != 'noise': pytest.fail(f'{k} is fixed now - cross it off WORLD_KNOWN')


def test_every_kind_the_rail_advisor_raises_has_a_case_both_ways():
    kinds = {c[0] for c in C.CASES}
    assert kinds >= {'followup', 'promise', 'cold', 'health', 'connect', 'idea', 'rule'}
    for k in kinds:
        assert {c[2] for c in C.CASES if c[0] == k} == {True, False}, f'{k} needs a should-fire and a should-not case'
