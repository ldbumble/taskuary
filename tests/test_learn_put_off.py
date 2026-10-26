"""THE PUT-OFF DAY IS A LINE YOU CAN CORRECT (the owner, 2026-10-25: "Remind me's learned day comes from a How you work line in LEARNED.md
that the owner can see and correct"). The count of the owner's put-offs (usual.put_off_habits) writes or confirms a How you work line in
each reflection, through the same ladder and books as every other line; Remind me reads the line, never the count. Invented Northwind
senders only."""
from datetime import datetime, timedelta
from unittest import mock
import pytest
from taskuary import advisor, funnel, learn, learnedgraph as lg, terminal, usual
from tests import memory_cases as C
from tests.memory_cases import put_off, reflected

KEY = 'put off renewals@payworth.example'


@pytest.fixture
def w():
    with mock.patch.object(terminal, 'live_sessions', lambda tail=0: []), mock.patch.object(funnel, '_agenda', lambda _s, **kw: []), \
         mock.patch.object(advisor, 'notice', lambda *a, **k: None):
        s, facts = C.world(); funnel.invalidate()
        yield s, facts
        funnel.invalidate()


def line(doc, key=KEY): return next((l for l in lg.lines(doc) if l['key'] == key), None)


def test_two_put_offs_wait_in_watching_and_set_no_day(w):
    s, _ = w
    l = line(reflected(s))
    assert l and l['status'] == 'hypothesis' and l['text'] == 'You put mail from renewals@payworth.example off to Friday'
    assert l['score'] == 3 and all(e.startswith('fs') for e in l['ev']) and len(l['ev']) == 2
    assert usual.remind_day(s, put_off(s, 'payworth', 0)) is None, 'a line in Watching is read by nobody'


def test_three_held_two_weeks_go_into_how_you_work_and_pass_the_books(w):
    s, _ = w
    put_off(s, 'payworth', 13)
    l = line(reflected(s))
    assert l['status'] == 'live' and l['section'] == 'How you work' and l['score'] == 4 and len(l['ev']) == 3
    assert all(lg.resolves(s, e) for e in l['ev']), 'every put-off it cites is a real task'
    assert s._one('SELECT Status, Reader FROM learned_line WHERE Key=?', (KEY,)) == {'Status': 'in_use', 'Reader': 'work'}


def test_put_offs_younger_than_two_weeks_are_no_habit_yet(w):
    s, _ = w
    from taskuary.store import MemoryStore
    s2 = MemoryStore()
    s2.save_doc('learned', s.get_doc('learned'), 'template')
    for d in (5, 4, 3): put_off(s2, 'payworth', d)
    l = line(reflected(s2))
    assert l and l['status'] == 'hypothesis', 'three put-offs this week are a guess, not how you work'


def test_a_line_the_model_wrote_on_the_same_put_offs_is_confirmed_not_doubled(w):
    s, _ = w
    put_off(s, 'payworth', 13)
    ev = usual.put_off_habits(s)[0]['evidence']
    doc = s.get_doc('learned').replace('## How you work\n', f'## How you work\n- Vendor renewals are put off to Friday [s:4 | ev: {ev[0]}, {ev[1]} | seen: 2026-10-20 | k: vendor renewals friday]\n', 1)
    s.save_doc('learned', doc, 'reflect')
    out = reflected(s)
    assert line(out) is None and set(line(out, 'vendor renewals friday')['ev']) == set(ev), 'its evidence grew, and no second line'
    assert usual.remind_day(s, put_off(s, 'payworth', 0))['line'] == 'Vendor renewals are put off to Friday'


def test_marked_wrong_it_is_never_written_back(w):
    s, _ = w
    put_off(s, 'payworth', 13)
    reflected(s)
    from taskuary import memoryedit
    memoryedit.mark(s, KEY, 'wrong')
    for _ in range(2): assert KEY not in reflected(s)
    assert usual.remind_day(s, put_off(s, 'payworth', 0)) is None


def test_with_no_ai_nothing_is_learned(w):
    s, _ = w
    put_off(s, 'payworth', 13)
    with mock.patch('taskuary.llm.build_llm', lambda *a, **k: None): assert not learn.reflect(s)
    assert KEY not in s.get_doc('learned')


def test_the_advisor_reads_the_day_from_the_line(w):
    s, _ = w
    put_off(s, 'payworth', 13); reflected(s)
    t = put_off(s, 'payworth', 0)
    m = next(x for x in s.list_messages(t))
    got = ' '.join(usual.prompt_lines(s, m, t))
    assert 'WHEN YOU PUT THEIR MAIL OFF (a How you work line the owner can correct): "You put mail from renewals@payworth.example off to Friday"' in got
    assert 'a Friday' in got
