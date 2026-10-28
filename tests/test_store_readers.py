"""READERS OFF THE WRITER'S LOCK (2026-10-28): the console showed 6-8 requests at a time waiting 1-3 s on store.lock behind the
membership census - a setting, the connector list, the owner's name, a pile's ~500 small reads. What this pins:
  - a plain read runs on a reader connection: it sees every committed write, never another thread's open transaction, and
    never waits for the writer; the thread holding the writer reads its own transaction; writers still go one at a time
  - the census reads and groups off the writer, and applies under the lock only when nothing it read has moved since -
    its answer the same as a census under the lock, write for write
  - the worker runs at most one census per CENSUS_EVERY while mail lands, and a new message still settles within it
  - a slow wait is logged once a minute per call site, with the rest counted
  - a pile built on a big store does not wait for a held writer
"""
import itertools, sqlite3, threading, time
from datetime import datetime, timedelta
from unittest import mock

import pytest
from loguru import logger

from taskuary import funnel, processing_all, processing_membership as pm, store as store_mod, terminal
from taskuary.store import SQLiteStore


@pytest.fixture
def s(tmp_path):
    st = SQLiteStore(str(tmp_path / 'readers.db'))
    yield st
    st.close()


def hold(st, most=5.0):
    "Another thread on the writer's lock, inside an open write transaction, until released."
    held, release = threading.Event(), threading.Event()
    def run():
        with st.lock:
            st.cx.execute('BEGIN IMMEDIATE'); st.cx.execute("INSERT INTO setting(Name, Value) VALUES ('uncommitted', 'x')")
            held.set(); release.wait(most); st.cx.rollback()
    t = threading.Thread(target=run, daemon=True); t.start(); held.wait(2)
    return release, t


def mail(st, n, tid=None, status='new'):
    return st.add_message({'ExternalId': f'r:{n}', 'ConversationId': f'thread:{n}', 'TaskId': tid, 'Channel': 'email',
                           'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'Subject': f'Subject {n}',
                           'BodyText': 'x', 'Status': status, 'SentAt': '2026-10-28 08:00:00'})


class Logs:
    def __enter__(self): self.lines = []; self.id = logger.add(lambda m: self.lines.append(m.record['message']), level='DEBUG'); return self
    def __exit__(self, *a): logger.remove(self.id)
    def having(self, x): return [l for l in self.lines if x in l]


# ── readers see committed state, and only that ──────────────────────────────────────────────────────────

def test_a_read_waits_for_no_writer_and_sees_only_what_is_committed(s):
    s.set_setting('k', 'committed', 't')
    release, t = hold(s)
    try:
        t0 = time.perf_counter(); v, open_one = s.get_setting('k'), s.get_setting('uncommitted'); took = time.perf_counter() - t0
    finally: release.set(); t.join()
    assert (v, open_one) == ('committed', None), 'another thread\'s open transaction is not visible'
    assert took < 1.0, 'it read on a reader connection, not behind the writer'


def test_a_committed_write_is_read_back_at_once_from_any_thread(s):
    got = []
    for i in range(20):
        s.set_setting('n', str(i), 't')
        th = threading.Thread(target=lambda: got.append(s.get_setting('n'))); th.start(); th.join()
    assert got == [str(i) for i in range(20)]


def test_a_write_from_another_connection_is_seen(s, tmp_path):
    peer = sqlite3.connect(str(tmp_path / 'readers.db')); peer.execute("INSERT INTO setting(Name, Value) VALUES ('peer', 'p')"); peer.commit()
    try: assert s.get_setting('peer') == 'p'
    finally: peer.close()


def test_the_lock_holder_reads_its_own_open_transaction(s):
    with s.lock:
        s.cx.execute('BEGIN IMMEDIATE'); s.cx.execute("INSERT INTO setting(Name, Value) VALUES ('mine', 'm')")
        assert s.get_setting('mine') == 'm'
        s.cx.rollback()
    assert s.get_setting('mine') is None


def test_a_transaction_left_open_on_the_writer_is_read_through_it(s):
    "A failed write that left BEGIN open with nobody holding the lock: the reads go where the old code read (see _undone)."
    s.cx.execute("INSERT INTO setting(Name, Value) VALUES ('leak', 'l')")        # sqlite3 opens a transaction and leaves it
    assert s.cx.in_transaction and not s._off_writer()
    assert s.get_setting('leak') == 'l'
    s.cx.rollback()
    assert s._off_writer()


def test_writers_still_go_one_at_a_time(s):
    s._exec("INSERT INTO setting(Name, Value) VALUES ('count', '0')")
    def bump():
        for _ in range(50):
            with s.lock:
                n = int(s._one("SELECT Value FROM setting WHERE Name='count'")['Value'])
                s.cx.execute("UPDATE setting SET Value=? WHERE Name='count'", (str(n + 1),)); s.cx.commit()
    ts = [threading.Thread(target=bump) for _ in range(6)]
    for t in ts: t.start()
    for t in ts: t.join()
    assert s.get_setting('count') == '300'


def test_a_processing_read_is_one_snapshot_off_the_writer(s, tmp_path):
    s.set_setting('k', 'before', 't')
    release, t = hold(s)
    try:
        with s._processing_read() as cur:
            first = cur.execute("SELECT Value FROM setting WHERE Name='k'").fetchone()[0]
            peer = sqlite3.connect(str(tmp_path / 'readers.db'), timeout=0.1)
            # the writer is held, so the peer cannot write either: the snapshot is what matters, and that it did not wait
            peer.close()
            again = cur.execute("SELECT Value FROM setting WHERE Name='k'").fetchone()[0]
    finally: release.set(); t.join()
    assert first == again == 'before'


def test_many_threads_reading_at_once_each_get_their_own_answer(s):
    for i in range(30): s.set_setting(f'k{i}', str(i), 't')
    bad = []
    def read(i):
        for _ in range(40):
            if s.get_setting(f'k{i}') != str(i): bad.append(i)
    ts = [threading.Thread(target=read, args=(i,)) for i in range(30)]
    for t in ts: t.start()
    for t in ts: t.join()
    assert bad == []
    assert len(s._readers) <= store_mod.READERS_KEPT


# ── the census off the writer: the same answer, write for write ──────────────────────────────────────────

def _graph(st):
    return {t: [tuple(r) for r in st.cx.execute(f'SELECT * FROM {t} ORDER BY 1')]
            for t in ('processing_item', 'processing_member', 'processing_alias', 'processing_relation')} | \
           {'state': [tuple(r) for r in st.cx.execute('SELECT DirtyGeneration, AttemptedGeneration, ReconciledGeneration, '
                                                     'MembershipGeneration, CensusGeneration, ConflictsJson, DiagnosticsJson FROM processing_reconcile_state')]}


def _story(st, *, locked_only):
    "The same writes, a reconcile after each - with the census off the writer, or (the old road) only under the lock."
    n, k = itertools.count(), itertools.count()
    st._processing_item_id = lambda: f'pi_{next(n):05d}'
    if locked_only: st._census_off_writer = lambda stamp: None
    rec = lambda: st.reconcile_processing_membership(fixed_now=f'2026-10-28 08:00:{next(k):02d}')
    out = []
    tasks = [st.create_task({'Title': f'Task {i}', 'Kind': 'reply', 'Status': 'open'}, 'fixture') for i in range(5)]
    mids = [mail(st, i, tid=tasks[i % 5] if i % 3 else None) for i in range(30)]
    out.append(rec())
    st._exec("UPDATE message SET Status='fyi' WHERE MessageId=?", (mids[0],)); out.append(rec())         # moves nothing
    st._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (tasks[1], mids[3])); out.append(rec())      # moves a member
    st._exec("INSERT INTO idea(Text, ActionJson, MessageId) VALUES ('an idea', ?, ?)", (f'{{"tid": {tasks[2]}}}', mids[4])); out.append(rec())
    st._exec("UPDATE task SET Status='done' WHERE TaskId=?", (tasks[0],)); out.append(rec())               # not read: skipped
    st._exec('DELETE FROM task WHERE TaskId=?', (tasks[4],)); out.append(rec())
    st._exec("UPDATE message SET Status='skipped', TaskId=NULL WHERE MessageId=?", (mids[5],)); out.append(rec())
    return [{k: v for k, v in r.items() if k != 'last_attempt_at'} for r in out], _graph(st)


def test_the_census_off_the_writer_gives_the_census_under_it(tmp_path):
    a, b = SQLiteStore(str(tmp_path / 'a.db')), SQLiteStore(str(tmp_path / 'b.db'))
    try: assert _story(a, locked_only=False) == _story(b, locked_only=True)
    finally: a.close(); b.close()


def test_a_census_that_moves_nothing_reads_nothing_under_the_lock(s):
    tid = s.create_task({'Title': 'T', 'Kind': 'reply', 'Status': 'open'}, 'fixture'); mid = mail(s, 1, tid=tid)
    s.reconcile_processing_membership()
    s._exec("UPDATE message SET Status='fyi' WHERE MessageId=?", (mid,))
    under, real = [], pm.census_inputs
    def spy(cur): under.append(s.lock._is_owned()); return real(cur)
    with mock.patch.object(pm, 'census_inputs', spy):
        r = s.reconcile_processing_membership()
    assert r['status'] == 'complete' and not s.processing_reconcile_status()['pending']
    assert under == [False], 'read once, on a reader'


def test_a_write_landing_mid_census_is_counted_under_the_lock(s):
    """The inputs were read; then a message moved task before the census took the lock. MembershipGeneration moved, so the
    census under the lock reads again - and puts the message where it now is."""
    a, b = (s.create_task({'Title': t, 'Kind': 'reply', 'Status': 'open'}, 'fixture') for t in 'AB')
    mid = mail(s, 1, tid=a); s.reconcile_processing_membership()
    real = s._census_off_writer
    def raced(stamp):
        pre = real(stamp); s._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (b, mid)); return pre
    s._exec("UPDATE message SET Status='fyi' WHERE MessageId=?", (mid,))
    with mock.patch.object(s, '_census_off_writer', raced): s.reconcile_processing_membership()
    item = lambda kind, local: s.cx.execute('SELECT ItemId FROM processing_member WHERE EntityKind=? AND LocalId=? AND RetiredAt IS NULL',
                                            (kind, str(local))).fetchone()[0]
    assert item('message', mid) == item('task', b) != item('task', a)
    assert not s.processing_reconcile_status()['pending']


def test_a_dry_census_stops_at_its_first_write():
    "No member, no item: the census would allocate one - so a dry pass answers None, not a guess."
    inputs = {'generation': 1, 'tasks': {'1': {'TaskId': 1, 'SourceRef': None, 'CreatedAt': 'x'}}, 'messages': {}, 'reviews': {},
              'ideas': {}, 'attachments': {}, 'runs': {}, 'item_rows': {}, 'current_rows': [], 'aliases': {}, 'relations': []}
    assert pm.dry_census(inputs, stamp='2026-10-28 08:00:00') is None
    assert inputs['item_rows'] == {} and inputs['aliases'] == {}, 'and leaves what it was handed as it was'


# ── the worker: one census per CENSUS_EVERY while mail lands ─────────────────────────────────────────────

def test_a_burst_of_mail_is_one_census_and_the_last_one_still_settles(s):
    s.reconcile_processing_membership()
    calls, real = [], s.reconcile_processing_membership
    s.reconcile_processing_membership = lambda **k: calls.append(s.processing_census_due()) or real(**k)
    w = processing_all.MembershipWorker(s, interval=0.02, census_every=0.6)
    w.start()
    try:
        t0 = time.monotonic(); last = None
        while time.monotonic() - t0 < 1.2:                         # a mail every 50 ms for 1.2 s
            last = mail(s, int((time.monotonic() - t0) * 1000) + 10); time.sleep(0.05)
        end = time.monotonic()
        while s.processing_reconcile_status()['pending'] and time.monotonic() - end < 3: time.sleep(0.02)
        settled = time.monotonic() - end
    finally: w.close()
    censuses = [c for c in calls if c is not None]
    assert 1 <= len(censuses) <= 4, f'{len(censuses)} censuses for ~24 mails in 1.2 s at one per 0.6 s'
    assert settled < 0.6 + 1.0, 'the last mail reached the rail within one census interval (and its census)'
    assert s.cx.execute("SELECT 1 FROM processing_member WHERE EntityKind='message' AND LocalId=? AND RetiredAt IS NULL",
                        (str(last),)).fetchone()


def test_a_write_no_census_reads_settles_on_the_next_tick(s):
    s.set_setting('processing_membership_rules', processing_all.MEMBERSHIP_RULES, 'system')      # the worker's own first write
    tid = s.create_task({'Title': 'T', 'Kind': 'reply', 'Status': 'open'}, 'fixture'); s.reconcile_processing_membership()
    w = processing_all.MembershipWorker(s, interval=0.02, census_every=30)
    w.census_at = time.monotonic()                                   # a census just ran: the next would wait 30 s
    w.start()
    try:
        s._exec("UPDATE task SET Status='in_progress' WHERE TaskId=?", (tid,))
        t0 = time.monotonic()
        while s.processing_reconcile_status()['pending'] and time.monotonic() - t0 < 2: time.sleep(0.01)
        assert not s.processing_reconcile_status()['pending'], 'not held back: there was no census to coalesce'
    finally: w.close()


# ── the log: once a minute per call site ─────────────────────────────────────────────────────────────────

def test_a_slow_wait_is_logged_once_a_minute_per_site_with_the_rest_counted():
    from taskuary.store import MemoryStore
    st = MemoryStore()
    def waits(n):
        for _ in range(n):
            release, t = hold(st); threading.Timer(0.08, release.set).start(); st.get_setting('x'); t.join()
    with mock.patch.object(store_mod, 'LOCK_SLOW_WAIT', 0.03), mock.patch.dict(store_mod._LOGGED, clear=True), Logs() as log:
        waits(3)
        assert len(log.having('waited')) == 1, log.lines
        with mock.patch.object(store_mod, 'LOCK_LOG_EVERY', 0.0): waits(1)
    lines = log.having('waited')
    assert len(lines) == 2 and '+2 more' in lines[1], lines
    assert 'test_store_readers.py' in lines[0] and 'contextlib' not in lines[0], 'the caller is named, not a with-block'


def test_a_wait_under_two_seconds_is_not_news():
    assert store_mod.LOCK_SLOW_WAIT == 2.0 and store_mod.LOCK_LOG_EVERY == 60.0


# ── the pile on a big store, beside a held writer ────────────────────────────────────────────────────────

@pytest.fixture
def big(tmp_path, monkeypatch):
    st = SQLiteStore(str(tmp_path / 'big.db'))
    st.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    now = datetime.now()
    with st.lock:
        cur = st.cx.cursor(); cur.execute('BEGIN')
        for i in range(150):
            cur.execute("INSERT INTO task(Title, Kind, Status, Source, CreatedAt, UpdatedAt) VALUES (?, 'reply', 'open', 'email', ?, ?)",
                        (f'Task {i}', now.strftime('%Y-%m-%d %H:%M:%S'), now.strftime('%Y-%m-%d %H:%M:%S')))
        for i in range(1500):
            at = (now - timedelta(minutes=7 * i)).strftime('%Y-%m-%d %H:%M:%S')
            cur.execute("INSERT INTO message(ExternalId, ConversationId, TaskId, Channel, FromName, FromEmail, Subject, BodyText, Status, SentAt, CreatedAt) "
                        "VALUES (?, ?, ?, 'email', 'Gail Moreno', 'gail@northwind.example', ?, 'body', ?, ?, ?)",
                        (f'b:{i}', f'thread:{i % 500}', (i % 150) + 1 if i % 4 == 0 else None, f'Subject {i}',
                         'routed' if i % 4 == 0 else 'filed', at, at))
        for i in range(800): cur.execute("INSERT INTO funnel_state(Key, Status, At) VALUES (?, 'surfaced', ?)", (f'msg:{i}', now.isoformat()))
        st.cx.commit()
    st.reconcile_processing_membership()
    st.activate_processing_reads(fixed_now=now.isoformat(), live_state=[])
    funnel.invalidate()
    yield st
    funnel.invalidate(); st.close()


def test_a_pile_on_a_big_store_builds_beside_a_held_writer(big):
    funnel.pile(big, force=True, observed=[], quiet=True)                   # the cold rail build is its own matter
    t0 = time.perf_counter(); funnel.pile(big, force=True, observed=[], quiet=True); free = time.perf_counter() - t0
    release, t = hold(big, most=60)
    try:
        t0 = time.perf_counter(); p = funnel.pile(big, force=True, observed=[], quiet=True); held = time.perf_counter() - t0
    finally: release.set(); t.join()
    assert p['items'], 'a pile came back'
    assert held < 3 * free + 5 < 60, f'{held:.1f}s beside a writer held for a minute, {free:.1f}s without: it did not wait for it'


def test_the_funnel_states_are_read_again_only_after_a_write(s, tmp_path):
    big = s
    for i in range(3): big._exec("INSERT INTO funnel_state(Key, Status) VALUES (?, 'surfaced')", (f'msg:{i}',))
    first = big.funnel_states()
    assert big.funnel_states() == first and big._states_cache[1] is not first, 'a copy each time: callers may keep and edit it'
    first['msg:0']['Status'] = 'edited by a caller'
    assert big.funnel_states()['msg:0']['Status'] == 'surfaced'
    big._exec("UPDATE funnel_state SET Status='done' WHERE Key='msg:1'")
    assert big.funnel_states()['msg:1']['Status'] == 'done'
    peer = sqlite3.connect(str(tmp_path / 'readers.db')); peer.execute("DELETE FROM funnel_state WHERE Key='msg:2'"); peer.commit(); peer.close()
    assert 'msg:2' not in big.funnel_states(), 'another process\'s write moves it too'
