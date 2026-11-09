"""MARK DONE ANSWERS AT ONCE, AND WHAT IT CLOSED STAYS CLOSED (the owner, 2026-11-09: "mark done on task until next one opens is still 45
seconds", and a task marked done was back on the rail after the next one was marked done too). The press built the whole rail twice inside
itself - before its close and after it - and on a busy home each build was 20-60 s. It now answers off the rail already known (railwalk._known)
with the closed row taken out, and the rail is read behind the answer. Pinned here: no build inside the press, the row below is the one the
walk said was below, and no rail read after it - nor after a second close - has the closed task, unless a later message reopened it."""
from contextlib import ExitStack
from unittest import mock

import pytest

import walkworld


@pytest.fixture
def world():
    from taskuary import assistant, demo, funnel, server, terminal
    from taskuary.processing_startup import initialize
    from taskuary.store import MemoryStore
    with ExitStack() as st:
        st.enter_context(mock.patch.object(terminal, 'live_sessions', return_value=[]))
        st.enter_context(mock.patch.dict(assistant._AGENDA))
        funnel.invalidate(); funnel.forget_states()
        s = MemoryStore()
        st.enter_context(mock.patch.object(server, 'store', s))
        demo.seed(s); initialize(s, live_state=[])
        yield s, walkworld.build(s)
        funnel.invalidate()


def on_rail(s, tid):
    from taskuary import funnel
    return any(i.get('tid') == tid for i in funnel.pile(s)['items'])


def press_done(s, key):
    """Mark done as the live home meets it: something else wrote since the rail was built (a hook, a poll), so the cache is stale."""
    from taskuary import funnel, railwalk
    s.audit('task', 0, 'poke', 'sync')
    with mock.patch.object(funnel, 'build', side_effect=AssertionError('the press built the rail')):
        return railwalk.leave(s, key, 'done')


def test_mark_done_answers_off_the_known_rail_with_the_row_below(world):
    from taskuary import railwalk
    s, src = world
    t1 = walkworld.key_of(s, src, 'T1')
    railwalk.open(s, t1)
    below = railwalk.peek(s)['below']
    out = press_done(s, t1)
    assert out['item']['key'] == below, 'the row the walk said was below'
    assert s.get_task(src['T1']['tid'])['Status'] == 'done'
    assert not on_rail(s, src['T1']['tid']), 'the next rail read has no closed task'


def test_two_closes_in_a_row_neither_comes_back(world):
    from taskuary import railwalk
    s, src = world
    t1 = walkworld.key_of(s, src, 'T1')
    railwalk.open(s, t1)
    nxt = press_done(s, t1)['item']
    press_done(s, nxt['key'])
    assert not on_rail(s, src['T1']['tid']), 'the first close is not undone by the second'
    assert nxt.get('tid') and not on_rail(s, nxt['tid'])
    # ...and the walk's own line agrees: neither is below or above the row on screen
    walk = railwalk.peek(s)
    assert {walk.get('below'), walk.get('above')}.isdisjoint({t1, nxt['key']})


def test_a_later_message_that_reopens_it_brings_it_back(world):
    from taskuary import railwalk
    s, src = world
    t1, tid = walkworld.key_of(s, src, 'T1'), src['T1']['tid']
    railwalk.open(s, t1)
    press_done(s, t1)
    assert not on_rail(s, tid)
    s.update_task(tid, {'Status': 'open'}, 'router')          # a reply owing the owner an answer reopens it, by rule
    walkworld.reconcile(s)
    assert on_rail(s, tid), 'reopened by rule: back on the rail, nothing on the server hides it'


def test_a_warm_check_never_waits_behind_a_build():
    """The walk asks "is the rail warm?" on every press: asked while a build held the lock, it waited the whole build out to hear no."""
    import threading, time
    from taskuary import funnel
    from taskuary.store import MemoryStore
    s = MemoryStore()
    with mock.patch.object(funnel, 'observe', return_value=[]):
        held = threading.Event(); free = threading.Event()
        def hold():
            with funnel._LOCK: held.set(); free.wait(5)
        th = threading.Thread(target=hold); th.start(); held.wait(5)
        t = time.perf_counter(); warm = funnel.warm(s); took = time.perf_counter() - t
        free.set(); th.join()
    assert warm is False and took < 0.5
