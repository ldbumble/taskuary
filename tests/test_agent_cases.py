"""THE GENERAL AGENT'S EVAL IN CI (Task 3.2): every case in tests/agent_cases.py, its prompt checked for what the case needs and for
what must never ride in it."""
import pytest
from taskuary import general
from taskuary.store import MemoryStore
from tests import agent_cases as C


def _prompt(setup):
    s = MemoryStore(); tid = setup(s)
    return s, '\n'.join(general._prompt(s, tid))


def _need(case, n): return n if isinstance(n, str) else f'{case}:{getattr(n, "__name__", "computed")}'


@pytest.mark.parametrize('case,need', [
    pytest.param(c[0], n, id=f'{c[0]}-{i}', marks=[pytest.mark.xfail(strict=True, reason=C.LATER[(c[0], n)])] if (c[0], n) in C.LATER else [])
    for c in C.CASES for i, n in enumerate(c[2])])
def test_the_prompt_carries_what_the_case_needs(case, need):
    s, p = _prompt(next(c[1] for c in C.CASES if c[0] == case))
    want = need(s) if callable(need) else need
    assert want in ' '.join(p.split()), f'{case}: the prompt lacks {want!r}'


@pytest.mark.parametrize('case', [c[0] for c in C.CASES if c[3]])
def test_the_prompt_carries_nothing_the_case_never_wants(case):
    _s, p = _prompt(next(c[1] for c in C.CASES if c[0] == case))
    p = ' '.join(p.split())
    assert not [n for n in next(c[3] for c in C.CASES if c[0] == case) if n in p]


def test_a_reworded_copy_is_left_alone(tmp_path):
    from taskuary import store as S
    mine = '# ASSISTANT.md\nOur own rules only. A login the thread asks for: put it in the reply you draft.\n'
    s = S.SQLiteStore(str(tmp_path / 'tq.db')); s.save_doc('assistant', mine, 'owner')
    s.cx.execute("DELETE FROM setting WHERE Name='login_rule_in_code'"); s.cx.commit()
    assert S.SQLiteStore(str(tmp_path / 'tq.db')).get_doc('assistant') == mine
