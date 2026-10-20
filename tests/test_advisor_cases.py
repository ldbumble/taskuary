"""THE ADVISOR'S EVAL IN CI (the deep dive, 2026-10-20): every case in tests/advisor_cases.py - the demo's world, the advisor matrix's,
and the states they lack - judged at item.shown by the scripted brain, each graded against the verbs that are right there and the
ones that never are, and each prompt checked for the evidence a real model needs to get it right."""
from unittest import mock
import pytest
from taskuary import assistant, faults, terminal
from tests import advisor_cases as C


@pytest.fixture(scope='module')
def results():
    sessions, agenda = dict(terminal.SESSIONS), dict(assistant._AGENDA)
    # the suite's home is its own throwaway (conftest), under its own temp folder rather than the system's
    try:
        with mock.patch.object(faults, 'scratch_home', lambda: True): got = {r['case']: r for r in C.run()}
        yield got
    finally:
        for sid, r in list(terminal.SESSIONS.items()):
            if sid not in sessions:
                try: r.alive = False
                except Exception: pass
                terminal.SESSIONS.pop(sid, None)
        assistant._AGENDA.clear(); assistant._AGENDA.update(agenda)


@pytest.mark.parametrize('case', [c[0] for c in C.CASES])
def test_the_advisor_lights_a_right_move(results, case):
    r = results[case]
    ok, never = next((c[1], c[2]) for c in C.CASES if c[0] == case)
    assert r['grade'] == 'right', f"{case}: lit {r['verb']} ({r['line']}) - right is {sorted(map(str, ok))}, never {sorted(never)}"


@pytest.mark.parametrize('case', [c[0] for c in C.CASES if c[3]])
def test_the_prompt_carries_what_the_case_needs(results, case):
    r = results[case]
    assert not r['missing'], f"{case}: the prompt lacks {r['missing']}"


def test_the_eval_is_the_whole_world(results):
    """No case silently dropped: every one found its item, and the grades add up."""
    assert not [c for c, r in results.items() if r['grade'] == 'missing']
    assert len(results) == len(C.CASES) >= 36
