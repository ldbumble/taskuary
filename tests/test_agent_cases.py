"""THE GENERAL AGENT'S EVAL IN CI (Task 3.2): every case in tests/agent_cases.py, its prompt checked for what the case needs and for
what must never ride in it."""
from pathlib import Path
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


# THE LOGIN RULE LIVES IN CODE (general.GOAL_LINE, the owner's own tasks only - Task 3.4 review): AGENT.md and ASSISTANT.md ride on a
# stranger's task too, so neither carries it. An owner-edited copy stops tracking its template (store.py): the login lines an earlier
# wording put there come out where they still read word for word - the rest of the document stays as its owner left it
@pytest.mark.parametrize('name,i', [('agent', 0), ('assistant', 0), ('assistant', 1)])
@pytest.mark.parametrize('nl', ['\n', '\r\n'])
def test_an_edited_copy_loses_the_login_rule(tmp_path, name, i, nl):
    from taskuary import store as S
    froms, to = S._LOGIN_RULES[name]
    shipped = (Path(S.__file__).parent / 'templates' / f'{name}.md').read_text(encoding='utf-8').replace('\r\n', '\n')
    assert shipped.count(to) == 1 and not [f for f in froms if f in shipped]
    old = (shipped.replace(to, froms[i]) + '- Our own line.\n').replace('\n', nl)
    s = S.SQLiteStore(str(tmp_path / 'tq.db')); s.save_doc(name, old, 'owner')
    s.cx.execute("DELETE FROM setting WHERE Name='login_rule_in_code'"); s.cx.commit()
    got = S.SQLiteStore(str(tmp_path / 'tq.db')).get_doc(name)
    assert got == (shipped + '- Our own line.\n').replace('\n', nl)
    for gone in ('put it in the', 'or a draft', '.env'): assert gone not in got, gone
    assert S.SQLiteStore(str(tmp_path / 'tq.db')).get_doc(name) == got


def test_a_reworded_copy_is_left_alone(tmp_path):
    from taskuary import store as S
    mine = '# ASSISTANT.md\nOur own rules only. A login the thread asks for: put it in the reply you draft.\n'
    s = S.SQLiteStore(str(tmp_path / 'tq.db')); s.save_doc('assistant', mine, 'owner')
    s.cx.execute("DELETE FROM setting WHERE Name='login_rule_in_code'"); s.cx.commit()
    assert S.SQLiteStore(str(tmp_path / 'tq.db')).get_doc('assistant') == mine
