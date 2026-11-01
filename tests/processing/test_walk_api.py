"""THE WALK'S ROUTES (railwalk, 2026-10-30) - what the selection token and its reservation used to guarantee, kept by `from_key` and the
press id: a press acts on the row the page showed, a write landing mid-press never refuses it ("i hate the next list changed", the owner,
2026-10-26), a repeated press is one answer and one line, and the row the rail says is below (walk.below) is the row the press brings.
Replaces the PW-050/PW-118 reservation tests (processing_navigation.reserve, funnel_selection) with the machinery they guarded gone."""
from datetime import datetime
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from taskuary import concierge, funnel, general, server, terminal
from taskuary.store import SQLiteStore


def task(db, n):
    tid = db.create_task({'Title': f'Synthetic walk {n}', 'Status': 'open'}, 'fixture')
    mid = db.add_message({'TaskId': tid, 'Channel': 'email', 'Status': 'filed', 'Subject': f'Synthetic source {n}', 'BodyText': f'Body {n}',
                          'ExternalId': f'walk-api:{n}', 'ConversationId': f'walk-api-thread:{n}', 'SentAt': datetime.now().isoformat(sep=' ')})
    rid = db.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'reply', 'Status': 'pending', 'DraftText': f'Draft {n}'})
    return tid, rid


@pytest.fixture
def api(tmp_path, monkeypatch):
    db = SQLiteStore(str(tmp_path / 'walk.db'))
    monkeypatch.setattr(server, 'store', db)
    monkeypatch.setattr(terminal, 'live_sessions', lambda **kwargs: [])
    monkeypatch.setattr(funnel, 'announce', lambda store: [])
    monkeypatch.setattr(funnel, 'alerts', lambda *args: [])
    monkeypatch.setattr(concierge, 'INTRO_AI', False)
    monkeypatch.setattr(server, '_refresh_after', lambda out: None)       # no provider is asked after an answer here
    funnel.invalidate()
    for n in (1, 2, 3): task(db, n)
    client = TestClient(server.app)
    before = set(threading.enumerate())
    try:
        yield db, client
    finally:
        client.close()
        deadline = time.monotonic() + 20                                  # every thread the routes started ends before the close
        while time.monotonic() < deadline:
            left = [t for t in threading.enumerate() if t not in before and t.daemon and t.is_alive()]
            if not left: break
            for t in left:
                try: t.join(timeout=max(0.1, deadline - time.monotonic()))
                except RuntimeError: time.sleep(.01)
        funnel.invalidate()
        db.close()


def lines(db): return len(concierge.history(db, general.dock_task(db)[0]['TaskId']))


def post(client, path, **body):
    r = client.post(path, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_rail_carries_the_walk_and_the_row_below_is_the_row_the_press_brings(api):
    db, client = api
    first = post(client, '/api/walk/start')
    walk = client.get('/api/funnel/pile', params={'force': True}).json()['walk']
    assert walk['on'] == first['item']['key'] and walk['above'] is None
    done = post(client, '/api/walk/next', from_key=first['item']['key'])
    assert done['item']['key'] == walk['below'], 'the key the rail carried is the row Next brought'
    assert done['pile']['walk']['above'] == first['item']['key'], 'the rail rides along with the walk as the move left it'


def test_a_write_landing_mid_press_never_refuses_it(api):
    db, client = api
    first = post(client, '/api/walk/start')
    below = client.get('/api/funnel/pile', params={'force': True}).json()['walk']['below']
    task(db, 4)                                                           # mail lands while the press is on its way
    db.save_review_draft(db.list_reviews('pending')[0]['ReviewId'], 'A draft rewritten under the press')
    done = post(client, '/api/walk/next', from_key=first['item']['key'])
    assert done['item']['key'] == below, 'the row below the one the page showed, whatever moved'


def test_a_repeated_press_is_one_answer_and_one_line(api):
    db, client = api
    first = post(client, '/api/walk/start')
    n = lines(db)
    one = post(client, '/api/walk/next', from_key=first['item']['key'], press='walk-api-repeat')
    two = post(client, '/api/walk/next', from_key=first['item']['key'], press='walk-api-repeat')
    assert one['item']['key'] == two['item']['key'] and one['answer_hash'] == two['answer_hash']
    assert lines(db) == n + 1, 'a retry wrote a second line'


def test_back_at_the_top_moves_nothing_and_back_writes_no_read(api):
    db, client = api
    first = post(client, '/api/walk/start')
    top = post(client, '/api/walk/back', from_key=first['item']['key'])
    assert top['item'] is None and top['top'] and top['walk']['on'] == first['item']['key']
    second = post(client, '/api/walk/next', from_key=first['item']['key'])
    states = db.funnel_states()
    back = post(client, '/api/walk/back', from_key=second['item']['key'])
    assert back['item']['key'] == first['item']['key'] and db.funnel_states() == states


def test_the_concierge_routes_are_wrappers_of_the_walk(api):
    """/api/concierge/next and the stream's next/back/start delegate to railwalk during the migration (spec 4)."""
    db, client = api
    first = post(client, '/api/concierge/next', from_key=None)
    assert first['item'] and first['walk']['on'] == first['item']['key']
    text = client.post('/api/concierge/stream', json={'mode': 'next', 'from_key': first['item']['key']}).text
    done = next(json.loads(l) for l in text.splitlines() if l.strip() and json.loads(l)['type'] == 'done')
    assert done['walk']['above'] == first['item']['key']
    text = client.post('/api/concierge/stream', json={'mode': 'back', 'from_key': done['item']['key']}).text
    back = next(json.loads(l) for l in text.splitlines() if l.strip() and json.loads(l)['type'] == 'done')
    assert back['item']['key'] == first['item']['key']


def test_leave_closes_and_brings_the_row_that_was_below(api):
    db, client = api
    first = post(client, '/api/walk/start')
    below = client.get('/api/funnel/pile', params={'force': True}).json()['walk']['below']
    out = post(client, '/api/walk/leave', key=first['item']['key'], how='done')
    assert out['item']['key'] == below
    assert db.get_task(first['item']['tid'])['Status'] == 'done'
    assert client.post('/api/walk/leave', json={'key': first['item']['key']}).status_code == 422
