"""The first task list after a restart: a cold rail build on a home of thousands of items.

A restart throws the rail's cache away, so the first pile projects every root again. That build ran ~17 queries per
root under the writer's lock - 71 s on the owner's home after a restart (2026-10-21), and opening a task, the agents
and the problems list queued behind it for up to 28 s. Here: a synthetic home of the same shape (tasks with threads,
reviews, comments, runs, transcripts, attachments, ideas, reads and deferrals, and a long tail of FYI mail), built once.
"""
import os, sqlite3, threading, time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from taskuary import funnel, server, terminal
from taskuary.funnel_presentation import forget_stamps
from taskuary.store import SQLiteStore

CI = bool(os.environ.get('CI'))
# Speed guards against per-root queries and a held lock (many seconds), not against a busy machine: a shared CI runner
# is several times slower and noisier than a desk (tests/test_floor_wave_b.py's FAST).
FAST = 1.5 if CI else 0.5
# ...and a desk running browser tests beside it took 2.6-3.4 s (2026-10-31): the per-root regression is caught exactly by the
# statement count above, so the clock here only has to catch a held lock
RAIL = 6.0 if CI else 4.0         # the rail alone, on a desk: 2.6-7.7 s before the bulk build, 0.8-1.9 s after (2026-10-21)
BUILD = 30.0 if CI else 15.0      # the whole first pile: a held lock, not a busy machine - its work is STATEMENTS
STATEMENTS = 60_000               # ...the first pile's statements: 167k with every hold judged afresh, ~38k with the stored hold
TASKS, FYI = 600, 3000


def _seed(s):
    now = datetime.now()
    ago = lambda h: (now - timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S')
    who = [(f'Person {i}', f'p{i}@vendor.example') for i in range(60)]
    tids = []
    for i in range(TASKS):
        status = ('open', 'done', 'in_progress', 'open', 'dropped', 'done')[i % 6]
        tid = s.create_task({'Title': f'Synthetic task {i}', 'Status': status, 'Kind': ('general', 'reply', 'task')[i % 3],
                             'Source': 'email'}, 'fixture')
        tids.append(tid)
        name, email = who[i % len(who)]
        for j in range(3):
            mid = s.add_message({'TaskId': tid, 'Status': 'routed', 'Channel': 'email', 'ExternalId': f'syn-{i}-{j}',
                                 'Subject': f'Synthetic task {i}', 'FromName': name, 'FromEmail': email,
                                 'BodyText': f'thread {i} line {j} ' * 20, 'SentAt': ago((i * 7 + j) % (24 * 30)),
                                 'ConversationId': f'syn-thread-{i}', 'Direction': 'in'})
            if j == 0: s.add_route(mid, tid, 'create', None, 'real work', [], 'triage')
        if i % 5 == 0: s.add_review({'TaskId': tid, 'MessageId': mid, 'Status': 'pending' if status == 'open' else 'sent',
                                     'Kind': 'draft', 'Reason': 'drafted', 'DraftText': 'a draft'})
        if i % 4 == 0: s.add_comment(tid, 'agent', 'agent', f'a note on {i}')
        if i % 9 == 0: s.add_attachment({'MessageId': mid, 'Name': f'sheet{i}.csv', 'ContentType': 'text/csv'})
        if i % 11 == 0:
            rid = s.start_run(tid, 'general', 'go', 'fixture')
            if status != 'in_progress': s.update_run(rid, {'Status': 'done'}, finished=True)
            s.add_transcript(tid, f'sid-{i}', 'a session', agent='general')
    fyi = []
    for k in range(FYI):
        name, email = who[k % len(who)]
        fyi.append(s.add_message({'Status': 'filed', 'Channel': ('email', 'teams', 'whatsapp', 'email')[k % 4], 'ExternalId': f'fyi-{k}',
                                  'Subject': f'FYI {k // 3}', 'FromName': name, 'FromEmail': email, 'BodyText': f'for your information {k} ' * 15,
                                  'SentAt': ago(k % (24 * 30)), 'ConversationId': f'fyi-thread-{k // 3}', 'Direction': 'in'}))
    for k in range(0, 60, 3):
        idea = s.upsert_idea({'key': f'followup:syn-{k}', 'kind': 'followup', 'text': f'Chase reply {k}', 'sig': f's{k}',
                              'action': {'mid': fyi[k]}}, ago(k))
        s.set_ideas_message([idea['IdeaId']], fyi[k])
    from taskuary.processing_startup import initialize
    initialize(s, live_state=[])
    # ...and what an owner's reads leave behind: receipts, a Later and a Done
    for k in range(0, 300, 7): s.set_funnel_state(f'msg:{fyi[k]}', 'surfaced', 'owner', read=True)
    for k in range(1, 300, 13): s.set_funnel_state(f'msg:{fyi[k]}', 'later', 'owner', until=ago(-48))
    for k in range(2, 300, 17): s.set_funnel_state(f'msg:{fyi[k]}', 'done', 'owner')
    s.reconcile_processing_membership()
    # ...and what the run before the restart judged and kept: each open task's hold (origin_hold), stored facts a restart does not lose
    from taskuary import origin
    for tid in tids: origin.hold(s, tid)
    return tids


@pytest.fixture(scope='module')
def home(tmp_path_factory):
    path = str(tmp_path_factory.mktemp('cold-rail') / 'home.db')
    s = SQLiteStore(path)
    s.set_setting('calendar_enabled', '0', 'fixture')
    tids = _seed(s)
    s.close()
    return path, tids


@pytest.fixture
def restarted(home, tmp_path, monkeypatch):
    """The home as a new process opens it: its own copy, nothing cached, no live worker."""
    path = str(tmp_path / 'restarted.db')
    with sqlite3.connect(home[0]) as src, sqlite3.connect(path) as dst: src.backup(dst)
    s = SQLiteStore(path)
    monkeypatch.setattr(server, 'store', s)
    monkeypatch.setattr(terminal, 'live_sessions', lambda **kw: [])
    funnel.invalidate(); forget_stamps()
    yield s, home[1]
    funnel.invalidate(); forget_stamps()
    s.close()


def test_the_bulk_projection_is_the_per_root_one(restarted):
    """Prefetch is a faster road to the SAME projection: every root, every field, every order."""
    from taskuary.processing_projection import Prefetch, processing_projection
    s, _ = restarted
    with s._processing_read() as cur:
        rail = {}; s._rail_roots(cur, rail)
        roots = sorted(rail['roots'])
        pre = Prefetch(cur, {r: rail['lineage'][r] for r in roots})
        bulk = [processing_projection(cur, r, live_state=[], pre=pre) for r in roots]
        assert bulk == [processing_projection(cur, r, live_state=[]) for r in roots]
    views = [p['view'] for p in bulk]
    # the home exercises what a projection reads, so equal means something
    for part in ('reviews', 'comments', 'runs', 'transcripts', 'attachments', 'ideas', 'relations', 'legacy_states'):
        assert any(v[part] for v in views), part
    assert any(u.get('read') for v in views for u in v['processing_read']['units'])
    assert any(v['processing_read']['deferrals'] for v in views)


def test_a_cold_rail_build_makes_no_query_per_root(restarted, monkeypatch):
    s, _ = restarted
    counts, build = [], SQLiteStore._rail_build

    def counted(self, cur, *a, **kw):
        n = [0]
        cur.connection.set_trace_callback(lambda sql: n.__setitem__(0, n[0] + 1))
        try: return build(self, cur, *a, **kw)
        finally: cur.connection.set_trace_callback(None); counts.append((n[0], len(self._processing_display_cache) or 1))

    monkeypatch.setattr(SQLiteStore, '_rail_build', counted)
    snap = s.processing_inventory_snapshot(fixed_now=datetime.now().isoformat(), live_state=[], display_only=True, history_days=60)
    assert len(snap['items']) > 3000 and counts
    assert counts[0][0] < len(snap['items']) / 10, f'{counts[0][0]} statements for {len(snap["items"])} roots'


def test_the_first_pile_after_a_restart_is_built_in_seconds(restarted, monkeypatch):
    s, _ = restarted
    took = time.perf_counter()
    snap = s.processing_inventory_snapshot(fixed_now=datetime.now().isoformat(), live_state=[], display_only=True, history_days=60)
    rail = time.perf_counter() - took
    assert len(snap['items']) > 3000 and rail < RAIL, f'the cold rail took {rail:.1f}s'
    s._processing_display_cache = {}
    # ...the pile's WORK is counted, not timed (2026-11-24): its clock failed on a loaded macOS runner at 11.7 s while the work had
    # fallen to a quarter - every task's Trust hold judged afresh was 167k statements, the stored hold (origin_hold) ~38k
    n, connect = [0], sqlite3.connect
    tick = lambda _sql: n.__setitem__(0, n[0] + 1)
    for cx in (s.cx, s._rail_cx, *s._readers):
        if cx is not None: cx.set_trace_callback(tick)
    def counted(*a, **k):
        cx = connect(*a, **k); cx.set_trace_callback(tick); return cx
    monkeypatch.setattr(sqlite3, 'connect', counted)
    took = time.perf_counter()
    pile = server._pile_payload(force=True, fyi=50)
    took = time.perf_counter() - took
    assert pile['items'] and n[0] < STATEMENTS, f'the first pile ran {n[0]} statements'
    assert took < BUILD, f'the first pile took {took:.1f}s'      # ...the clock only catches a held lock


def test_opening_a_task_never_waits_for_a_cold_pile(restarted, monkeypatch):
    """A cold build still running (held here until the task has answered) leaves the task's own read free."""
    s, tids = restarted
    entered, release, build = threading.Event(), threading.Event(), SQLiteStore._rail_build

    def slow(self, *a, **kw):
        entered.set(); release.wait(15)
        return build(self, *a, **kw)

    monkeypatch.setattr(SQLiteStore, '_rail_build', slow)
    out = {}
    pile = threading.Thread(target=lambda: out.update(pile=server._pile_payload(force=True, fyi=50)))
    pile.start()
    try:
        assert entered.wait(15), 'the pile never began its build'
        c = TestClient(server.app)
        took = time.perf_counter()
        task = c.get(f'/api/tasks/{tids[0]}')
        took = time.perf_counter() - took
        record = c.get(f'/api/tasks/{tids[0]}/record')
        # ...and the Assistant's own look-up of the task it was asked to open answers from the task's rows
        looked = time.perf_counter()
        item = funnel.next_item(s, f'task:{tids[0]}', include_surfaced=True)
        looked = time.perf_counter() - looked
        still = pile.is_alive()
    finally:
        release.set(); pile.join(60)
    assert task.status_code == 200 and task.json()['task']['TaskId'] == tids[0]
    assert record.status_code == 200
    assert still, 'the build finished before the task was opened: nothing was shown'
    assert took < FAST, f'opening a task waited {took:.1f}s on the rail'
    assert item and item['tid'] == tids[0] and looked < FAST, f'the Assistant waited {looked:.1f}s on the rail for the task'
    assert out['pile']['items']
    # ...and once it is built, the same look-up is the rail's own row again
    assert funnel.next_item(s, f'task:{tids[0]}', include_surfaced=True)['tid'] == tids[0]


def _two_profiles(s):
    """What made the walk slow on 0.4.6.11 (the owner: "all read, next is slower now"): his own address set, two profiles, a mailbox each, and
    the mail read by them."""
    import json
    from taskuary import workstreams as W
    s.set_setting('owner_email', 'alex@northwind.example', 'fixture')
    W.save(s, [{'name': 'Northwind'}, {'name': 'Harbor Bakery'}])
    for slug, typ, box in (('northwind', 'outlook', 'alex@northwind.example'), ('harbor-bakery', 'gmail', 'shop@harbor.example')):
        cid = s.save_connector({'Type': typ, 'Name': box, 'Active': 1, 'ConfigJson': json.dumps({'address': box})}, 'fixture')
        s.save_source({'Name': box, 'Address': box, 'Channel': 'email', 'ConnectorId': cid, 'Active': 1}, 'fixture')
        W.tag_account(s, slug, connector_id=cid)
    s._exec("UPDATE message SET SourceName=CASE WHEN MessageId % 2 THEN 'alex@northwind.example' ELSE 'shop@harbor.example' END WHERE Channel='email'")


def _traced(s, monkeypatch) -> list:
    "Every statement run from here on, on any of the store's connections."
    reads, connect = [], sqlite3.connect
    for cx in (s.cx, s._rail_cx, *s._readers):
        if cx is not None: cx.set_trace_callback(reads.append)
    def counted(*a, **k):
        cx = connect(*a, **k); cx.set_trace_callback(reads.append); return cx
    monkeypatch.setattr(sqlite3, 'connect', counted)
    return reads


def test_a_walk_move_rebuilds_the_rail_without_a_read_per_row(restarted, monkeypatch):
    """Every Next or All read rebuilds the rail behind the move, and on 0.4.6.11 the rebuild asked per row what is the same for every row: the
    owner's own addresses copied every connection card (ingest.own_addresses) - 2.2x the statements of 0.4.6.5."""
    import json, re
    s, _ = restarted
    _two_profiles(s)
    first = json.loads(server.walk_start(server.RailWalkBody(light=True, press='w0')).body)['item']['key']
    server._pile_payload(force=False, fyi=50)
    server.walk_next(server.RailWalkBody(light=True, from_key=first, press='w1', read=[first]))
    # ...a closed task's Trust hold, judged afresh when it is read, is counted by the first pile's own guard above: it stands still here
    from taskuary import origin
    monkeypatch.setattr(origin, '_now_judged', lambda store, tid: {})
    reads = _traced(s, monkeypatch)
    pile = server._pile_payload(force=False, fyi=50)            # ...the rail the page reads behind the move
    of = lambda pat: sum(bool(re.search(pat, q)) for q in reads)
    cards, rows = of(r"change_gen WHERE Tbl='connector'"), pile['counts']['unread']
    assert reads and rows > 1000 and any(i.get('kind') == 'review' for i in pile['items'])
    # ...a fact the same for every row is read a bounded number of times, never once a row (0.4.6.11: a read of the cards a row). A waiting
    # card's own channel checks (outbound.connect_fix, send_probe) read them a few times a card, as 0.4.6.5 did
    assert cards < rows / 5, f'the connection cards read {cards} times for {rows} rows'


def test_a_waiting_letter_asks_the_wall_without_reading_its_thread(restarted, monkeypatch):
    """The rail asks each waiting letter whether its task has a mailbox to leave from (outbound.no_from, read for its Connect), on every
    rebuild. A task that may use one cannot be refused, and that is one read; on 0.4.6.11 the whole road ran for it - the task's every message
    read for the mailbox its mail came in on, and the wall asked of every mailbox three times over."""
    import json, re
    from taskuary import outbound, workstreams as W
    s, tids = restarted
    _two_profiles(s)
    tid = next(t for t in tids if s.get_task(t)['Status'] == 'open')
    W.set_task(s, tid, 'northwind', 'fixture')
    rid = s.add_review({'TaskId': tid, 'Status': 'pending', 'Kind': 'draft', 'Reason': 'a new letter', 'DraftText': 'The figures, as promised.',
                        'Deliver': json.dumps({'channel': 'email', 'to': ['erin@vendor.example'], 'subject': 'Figures'})})
    rv = s.get_review(rid)
    reads = _traced(s, monkeypatch)
    assert outbound.no_from(s, rv) is None and outbound.leaves_from(s, rv) == 'alex@northwind.example'
    reads.clear()
    assert outbound.no_from(s, rv) is None
    assert not [q for q in reads if re.search(r'FROM message\b', q)], 'the letter read its thread to say it has a mailbox'
