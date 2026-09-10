"""PW-106: completed HTTP display snapshots include the held legacy Current."""
from datetime import datetime
import copy

import pytest
from fastapi.testclient import TestClient

from taskuary import funnel, funnel_presentation, server, terminal
from taskuary.store import SQLiteStore


@pytest.fixture
def display_api(tmp_path, monkeypatch):
    db = SQLiteStore(str(tmp_path / 'display-api.db'))
    monkeypatch.setattr(server, 'store', db)
    monkeypatch.setattr(terminal, 'live_sessions', lambda **kwargs: [])
    # Native watcher delivery is not the display fingerprint contract under test.
    monkeypatch.setattr(funnel, 'announce', lambda store: [])
    monkeypatch.setattr(funnel, 'alerts', lambda *args: [])
    funnel.invalidate()
    tid = db.create_task({'Title': 'Synthetic display task', 'Status': 'open',
                          'Priority': 'normal'}, 'fixture')
    mid = db.add_message({'TaskId': tid, 'Channel': 'email', 'Status': 'filed',
                          'Subject': 'Synthetic display source', 'BodyText': 'x' * 4500 + ' old tail',
                          'SentAt': datetime.now().isoformat(sep=' ')})
    rid = db.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'reply',
                         'Status': 'pending', 'DraftText': 'Original synthetic draft'})
    # A plain client exercises requests without starting application lifespan jobs.
    client = TestClient(server.app)
    try:
        yield db, client, tid, mid, rid
    finally:
        client.close()
        funnel.invalidate()
        db.cx.close()


def get_pile(client, current=None):
    params = {'force': True}
    if current:
        params['current'] = current
    response = client.get('/api/funnel/pile', params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('change', ['body_tail', 'draft', 'clear_draft', 'priority', 'attachment'])
def test_current_same_key_gets_complete_new_display_revision(display_api, change):
    db, client, tid, mid, rid = display_api
    key = f'review:{rid}'
    first = get_pile(client, key)
    assert first['current']['key'] == key
    stable = (key, first['current']['lane'], first['current'].get('settling'))
    state_before = db.funnel_states()
    if change == 'body_tail':
        db.update_message_body(mid, 'x' * 4500 + ' changed tail')
    elif change == 'draft':
        db.save_review_draft(rid, 'Changed synthetic draft')
    elif change == 'clear_draft':
        db.save_review_draft(rid, '')
    elif change == 'priority':
        db.update_task(tid, {'Priority': 'high'}, 'fixture')
    else:
        db.add_attachment({'MessageId': mid, 'Name': 'synthetic-note.txt',
                           'ContentType': 'text/plain', 'Size': 42})
    second = get_pile(client, key)
    current = second['current']
    assert (current['key'], current['lane'], current.get('settling')) == stable
    assert current['presentation_revision'] != first['current']['presentation_revision']
    assert second['display_revision'] != first['display_revision']
    assert db.funnel_states() == state_before
    assert get_pile(client, key)['display_revision'] == second['display_revision']


def test_current_query_and_null_are_part_of_complete_response_revision(display_api):
    _, client, _, _, rid = display_api
    ordinary = get_pile(client)
    held = get_pile(client, f'review:{rid}')
    missing = get_pile(client, 'msg:999999')
    assert 'current' not in ordinary
    assert held['current']['key'] == f'review:{rid}'
    assert missing['current'] is None
    assert len({ordinary['display_revision'], held['display_revision'], missing['display_revision']}) == 3


def test_query_specific_stamping_does_not_mutate_cached_pile(display_api):
    db, client, _, _, rid = display_api
    cached = funnel.pile(db, force=True)
    before = copy.deepcopy(cached)
    response = client.get('/api/funnel/pile', params={'current': f'review:{rid}'})
    assert response.status_code == 200
    result = response.json()
    assert result['current']['presentation_revision']
    assert cached == before
    assert 'current' not in cached


def test_multiple_card_backing_reads_share_snapshot_during_external_write(tmp_path, monkeypatch):
    path = tmp_path / 'display-wal.db'
    db = SQLiteStore(str(path))
    writer = SQLiteStore(str(path))
    try:
        mids = [db.add_message({'Channel': 'email', 'BodyText': f'Original source {n}'}) for n in range(2)]
        payload = {'items': [{'key': f'msg:{mid}', 'mid': mid, 'lane': 'fyi'} for mid in mids],
                   'hidden': 0, 'alerts': [], 'events': []}
        untouched = copy.deepcopy(payload)
        initial = funnel.present(db, payload)
        original = funnel_presentation._backing
        wrote = False

        def update_other_after_first_backing(cur, item):
            nonlocal wrote
            backing = original(cur, item)
            if not wrote:
                wrote = True
                writer.update_message_body(mids[1], 'Changed later source from external WAL writer')
            return backing

        monkeypatch.setattr(funnel_presentation, '_backing', update_other_after_first_backing)
        during = funnel.present(db, payload)
        assert wrote
        assert during == initial
        assert payload == untouched
        assert not db.cx.in_transaction
        after = funnel.present(db, payload)
        assert after['display_revision'] != initial['display_revision']
        assert after['items'][0]['presentation_revision'] == initial['items'][0]['presentation_revision']
        assert after['items'][1]['presentation_revision'] != initial['items'][1]['presentation_revision']
    finally:
        writer.cx.close()
        db.cx.close()
