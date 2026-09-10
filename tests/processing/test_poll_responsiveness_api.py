"""Fresh intake stays visible through the real API while its ordered judge is busy."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import threading

import pytest

from fastapi.testclient import TestClient

from taskuary import channels, ingest, server, terminal
from taskuary.store import SQLiteStore


@pytest.mark.parametrize('kind', ['teams', 'slack', 'telegram', 'whatsapp', 'imessage', 'discord'])
@pytest.mark.parametrize('raw,elapsed,due', [
    (None, 29, False), ('', 30, True), ('0', 300, False), ('45', 44, False), ('45', 45, True),
])
def test_card_interval_semantics_use_actual_backend_parser(tmp_path, monkeypatch, kind, raw, elapsed, due):
    db = SQLiteStore(str(tmp_path / 'poll-interval.db'))
    monkeypatch.setattr(server, 'store', db)
    monkeypatch.setattr(server, '_QUICK_LAST', {kind: 1000})
    monkeypatch.setattr(server.time, 'time', lambda: 1000 + elapsed)
    try:
        cid = db.get_connector_by_type(kind)['ConnectorId']
        config = {} if raw is None else {'poll_seconds': raw}
        db.save_connector({'ConnectorId': cid, 'Active': 1, 'ConfigJson': json.dumps(config)}, 'fixture')
        assert (kind in server._quick_due()) is due
    finally:
        db.cx.close()


@pytest.mark.parametrize('raw,enabled', [('0', False), ('10', True), ('bad', True)])
def test_global_setting_controls_real_fast_clock_without_connecting(tmp_path, monkeypatch, raw, enabled):
    db = SQLiteStore(str(tmp_path / 'poll-global.db'))
    monkeypatch.setattr(server, 'store', db)
    db.set_setting('poll_minutes', raw, 'fixture')
    calls = []
    monkeypatch.setattr(server, '_quick_due', lambda: ['teams'])
    monkeypatch.setattr(server, '_poll_reports', lambda *args, **kwargs: calls.append(kwargs))

    def stop_cycle(*args):
        raise StopIteration

    monkeypatch.setattr(server.time, 'sleep', stop_cycle)
    try:
        with pytest.raises(StopIteration): server.quick_forever()
        assert bool(calls) is enabled
    finally:
        db.cx.close()


def test_second_chat_arrival_is_visible_while_quick_triage_is_held(tmp_path, monkeypatch):
    db = SQLiteStore(str(tmp_path / 'poll-api.db'))
    monkeypatch.setattr(server, 'store', db)
    monkeypatch.setattr(terminal, 'live_sessions', lambda **kwargs: [])
    monkeypatch.setattr(server, '_llm', lambda *args: object())
    cid = db.get_connector_by_type('teams')['ConnectorId']
    db.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': 'synthetic',
                       'ConfigJson': json.dumps({'poll_seconds': 30})}, 'fixture')
    db.save_source({'Channel': 'teams', 'Address': 'synthetic-channel', 'Active': 1,
                    'ConnectorId': cid, 'Owner': 'fixture'}, 'fixture')
    old_mid = db.add_message({'Channel': 'teams', 'Status': 'filed',
                              'BodyText': 'Historical synthetic item already read',
                              'SentAt': datetime.now().isoformat(sep=' ')})
    db.set_funnel_state(f'msg:{old_mid}', 'done', 'owner')
    db.save_doc('soul', 'Owner synthetic document; preserve exactly.', 'owner')
    old_states = db.funnel_states()
    arrived, judged = [], []
    started, release = threading.Event(), threading.Event()

    def fetch(store, days, progress=None, only=None):
        assert only == ['teams']
        mid = store.add_message({'Channel': 'teams', 'Status': 'triaging',
                                 'ExternalId': f'synthetic-chat:{len(arrived)}',
                                 'Subject': f'Synthetic arrival {len(arrived)}',
                                 'BodyText': 'Fresh chat awaiting its ordered judge',
                                 'FromName': 'Synthetic colleague',
                                 'SentAt': datetime.now().isoformat(sep=' ')})
        arrived.append(mid)
        return 1

    def judge(store, msg, **kwargs):
        started.set()
        assert release.wait(10), 'test must release its owned judge'
        judged.append(msg['_mid'])
        store.place_message(msg['_mid'], None, 'filed')

    monkeypatch.setattr(channels, 'poll_channels', fetch)
    monkeypatch.setattr(ingest, 'ingest_message', judge)
    client = TestClient(server.app)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(server._poll_reports, 0, only=['teams'])
            try:
                assert started.wait(5)
                assert first.result(timeout=3) == 1, 'fetch must not wait for its own slow judge'
                second = pool.submit(server._poll_reports, 0, only=['teams'])
                assert second.result(timeout=3) == 1
                response = client.get('/api/feed', params={'limit': 100})
                assert response.status_code == 200, response.text
                rows = response.json()['data']
                assert set(arrived).issubset({row['MessageId'] for row in rows})
                assert judged == [], 'both arrivals must be visible before the held judge finishes'
                assert db.funnel_states() == old_states
                assert db.get_doc('soul') == 'Owner synthetic document; preserve exactly.'
            finally:
                release.set()
            assert first.result(timeout=5) == 1
        assert ingest.await_quiet(db, ['teams'], timeout=5)
        assert judged == arrived, 'ordered routing must follow arrival order'
        assert db.funnel_states() == old_states
        assert db.get_doc('soul') == 'Owner synthetic document; preserve exactly.'
    finally:
        release.set()
        # The async worker API is supplied by the bounded polling implementation.
        assert server.join_drains(db, timeout=5), 'owned drain worker must finish before fixture teardown'
        client.close()
        db.cx.close()


def test_chat_arrival_is_visible_while_full_sync_report_is_held(tmp_path, monkeypatch):
    db = SQLiteStore(str(tmp_path / 'poll-report-api.db'))
    monkeypatch.setattr(server, 'store', db)
    monkeypatch.setattr(terminal, 'live_sessions', lambda **kwargs: [])
    monkeypatch.setattr(server, '_llm', lambda *args: object())
    monkeypatch.setattr(ingest, 'drain', lambda *args, **kwargs: 0)
    monkeypatch.setattr('taskuary.ci.poll', lambda *args: None)
    monkeypatch.setattr(server.blackboard, 'roll_daily', lambda *args: None)
    cid = db.get_connector_by_type('teams')['ConnectorId']
    db.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': 'synthetic'}, 'fixture')
    db.save_source({'Channel': 'teams', 'Address': 'synthetic-channel', 'Active': 1,
                    'ConnectorId': cid, 'Owner': 'fixture'}, 'fixture')
    started, release = threading.Event(), threading.Event()
    arrived, fetches = [], []

    def held_report(target, startup=False):
        assert target is db
        started.set()
        assert release.wait(10), 'test must release its owned report'

    def fetch(target, days, progress=None, only=None):
        assert target is db and only == ['teams']
        fetches.append(list(only))
        if not started.is_set(): return 0
        arrived.append(target.add_message({'Channel': 'teams', 'Status': 'triaging',
                                           'BodyText': 'Synthetic arrival while report runs',
                                           'SentAt': datetime.now().isoformat(sep=' ')}))
        return 1

    monkeypatch.setattr(server, 'run_due_reports', held_report)
    monkeypatch.setattr(channels, 'poll_channels', fetch)
    client = TestClient(server.app)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            full = pool.submit(server._poll_reports)
            try:
                assert started.wait(5)
                quick = pool.submit(server._poll_reports, 0, only=['teams'])
                assert quick.result(timeout=3) == 1
                response = client.get('/api/feed', params={'limit': 100})
                assert response.status_code == 200, response.text
                assert arrived[0] in {row['MessageId'] for row in response.json()['data']}
                assert fetches == [['teams'], ['teams']]
                assert not full.done(), 'chat visibility must not depend on report completion'
            finally:
                release.set()
            assert full.result(timeout=5) == 0
    finally:
        release.set()
        assert server.join_drains(db, timeout=5)
        client.close()
        db.cx.close()
