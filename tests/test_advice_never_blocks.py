"""NOTHING THE OWNER PRESSES WAITS ON A RAIL BUILD (the owner, 2026-11-09: "it says closing task but it still has Mark done? it's probably
frozen"). With a coding agent busy beside the walk, every hook write emptied the pile's cache (funnel.invalidate), and the Advisor read
the rail through funnel.pile: GET /api/advice took 84 s, its press 72 s, and a Mark done 67 s - each queued behind the others' builds.
Pinned here by counting builds and lock waits, never by a timer: a press and the Advisor answer with the cache emptied and the pile's
lock held by a build in progress; readers queued behind one build share it; a coding agent's landing note keeps the cache; a poll's
heartbeat never waits out SQLite's busy timeout while holding the store's lock."""
import json, sqlite3, threading, time
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


def run_with_build_running(f):
    """f() while another thread holds the pile's lock (a build in progress) and the cache stands emptied by a hook's write, with
    funnel.pile and funnel.build refused: returns f's answer, or fails if f waited on the lock or built the rail."""
    from taskuary import funnel, railwalk
    railwalk._HAND.clear()                                      # the first press in a while: no line held from a move before it
    funnel.invalidate()                                         # ...a hook just wrote
    out, held, release = {}, threading.Event(), threading.Event()
    def builder():
        with funnel._LOCK: held.set(); release.wait(10)
    b = threading.Thread(target=builder, daemon=True); b.start(); assert held.wait(2)
    def go():
        try: out['v'] = f()
        except BaseException as e: out['e'] = e
    try:
        with mock.patch.object(funnel, 'pile', side_effect=AssertionError('waited on the rail build')):
            t = threading.Thread(target=go, daemon=True); t.start(); t.join(10)
            assert not t.is_alive(), 'it waited on the build in progress'
    finally: release.set(); b.join(2)
    if 'e' in out: raise out['e']
    return out['v']


def test_mark_done_with_the_cache_emptied_and_a_build_running(world):
    from taskuary import funnel, railwalk
    s, src = world
    funnel.pile(s)                                              # the rail as the page last read it
    t1 = walkworld.key_of(s, src, 'T1')
    railwalk.open(s, t1)
    below = railwalk.peek(s)['below']
    s.audit('task', 0, 'poke', 'sync')
    out = run_with_build_running(lambda: railwalk.leave(s, t1, 'done'))
    assert out['item']['key'] == below
    assert s.get_task(src['T1']['tid'])['Status'] == 'done'


def test_all_read_next_with_the_cache_emptied_and_a_build_running(world):
    from taskuary import funnel, railwalk
    s, src = world
    rows = funnel.pile(s)['items']
    t1 = walkworld.key_of(s, src, 'T1')
    railwalk.open(s, t1)
    below = railwalk.peek(s)['below']
    assert rows and below
    out = run_with_build_running(lambda: railwalk.leave(s, t1, 'next'))
    assert out['item']['key'] == below


def test_the_advisor_never_reads_the_rail_through_its_lock(world):
    from taskuary import advisor, funnel
    s, src = world
    funnel.pile(s)
    key = walkworld.key_of(s, src, 'T1')
    with mock.patch.object(advisor, 'notice', return_value=None):
        d = run_with_build_running(lambda: advisor.status(s, key))
        rid = run_with_build_running(lambda: advisor.press(s, key, None, 'next', surface='desk'))
    assert d.get('key') == key or d.get('none'), d
    assert rid, 'the press is kept'


def test_the_advisor_read_ahead_never_builds(world):
    from taskuary import advisor, funnel
    s, src = world
    funnel.pile(s)
    seen = []
    with mock.patch.object(advisor, 'BACKGROUND', True), mock.patch.object(advisor, 'notice', side_effect=lambda *a, **k: seen.append(k.get('key'))), \
         mock.patch.object(funnel, 'pile', side_effect=AssertionError('the read ahead built the rail')), \
         mock.patch.object(advisor.threading, 'Thread', side_effect=lambda target, **k: mock.Mock(start=target)):
        advisor._preread(s, funnel.known(s)['items'][0]['key'])
    assert seen, 'the next rows were read ahead off the known rail'


def test_readers_queued_behind_one_build_share_the_next_one():
    """A tab, the Advisor and a press queued behind a build while an agent kept writing each rebuilt in turn. A read that waited out a
    build BEGUN after it asked has every write made before its ask: it takes that build."""
    from taskuary import funnel
    from taskuary.store import MemoryStore
    s, top, calls = MemoryStore(), [1], []
    funnel.invalidate()
    first_in, release = threading.Event(), threading.Event()
    def slow_build(_store, **kw):
        n = len(calls); calls.append(n)
        top[0] += 1                                             # the agent writes during every build
        if n == 0: first_in.set(); release.wait(5)
        elif n == 1: time.sleep(.3)                             # the second build runs while the last two ask
        return {'rev': f'b{n}', 'items': [], 'lanes': [], 'counts': {}}
    answers = []
    read = lambda: answers.append(funnel.pile(s, observed=[], quiet=True)['rev'])
    with mock.patch.object(funnel, 'announce', return_value=[]), mock.patch.object(funnel, 'build', side_effect=slow_build),          mock.patch.object(funnel, 'alerts', return_value=[]), mock.patch.object(funnel, '_rail_top', side_effect=lambda _s: top[0]):
        a = threading.Thread(target=read); a.start(); assert first_in.wait(2)
        b = threading.Thread(target=read); b.start(); time.sleep(.05)
        release.set(); time.sleep(.1)                           # b now builds again, with the write made during a's
        c, d = threading.Thread(target=read), threading.Thread(target=read)
        c.start(); d.start()
        for t in (a, b, c, d): t.join(5)
    # a and b need their own builds, and c the next (b's began before it asked); d asked before c's began: it shares it, never one more
    assert len(calls) == 3, (calls, answers, top)
    assert sorted(answers) == ['b0', 'b1', 'b2', 'b2']


def test_a_coding_agents_landing_note_keeps_the_rail_cached():
    """landing.saw writes landing:<tid> on every Edit and commit the agent makes; no rail card reads it."""
    from taskuary import funnel
    from taskuary.store import MemoryStore
    s = MemoryStore(); funnel.invalidate()
    funnel.pile(s, observed=[])
    s.set_setting('landing:7', json.dumps({'cwd': 'x', 'paths': {'a.py': 1}}), 'system')
    with mock.patch.object(funnel, 'build', side_effect=AssertionError('rebuilt for a landing note')):
        funnel.pile(s, observed=[])
    s.set_setting('funnel_mutes', '["someone@vendor.example"]', 'owner')        # ...while one the rail reads still rebuilds it
    assert funnel.cached_pile(s) is None


def test_a_poll_heartbeat_never_waits_on_a_busy_database(tmp_path):
    """The WhatsApp poll's touch_source waited SQLite's 5 s busy timeout while another process wrote - holding store.lock 6 s."""
    from taskuary.store import SQLiteStore
    s = SQLiteStore(str(tmp_path / 't.db'))
    sid = s.save_source({'Channel': 'whatsapp', 'Address': 'chat-1', 'Active': 1}, 'o')
    other = sqlite3.connect(str(tmp_path / 't.db'), timeout=0)
    other.execute('BEGIN IMMEDIATE')                            # another process holds the write lock
    waits = []
    real = s.cx.execute
    with mock.patch.object(s, 'cx', wraps=s.cx) as cx:
        cx.execute.side_effect = lambda q, *a: (waits.append(q) if str(q).startswith('PRAGMA busy_timeout') else None) or real(q, *a)
        t0 = time.monotonic(); s.touch_source(sid); took = time.monotonic() - t0
    other.rollback(); other.close()
    assert waits[0] == f'PRAGMA busy_timeout={s.TOUCH_WAIT_MS}' and waits[-1] == 'PRAGMA busy_timeout=5000'
    assert took < 2.5, f'the heartbeat waited {took:.1f}s'
    assert not s.cx.in_transaction
    s.touch_source(sid)                                         # free again: stamped
    assert s.get_source(sid)['LastPolledAt']
