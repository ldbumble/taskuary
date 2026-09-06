"""Progress observes the owned sync stages without opening production connectors."""
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from taskuary import server, channels, ci
from taskuary.store import MemoryStore


@pytest.fixture
def sync_store(monkeypatch):
    store = MemoryStore()
    monkeypatch.setattr(server, 'store', store)
    monkeypatch.setattr(channels, '_poll_jobs', lambda _: [({'Type': 'outlook'}, {})])
    monkeypatch.setattr(channels, 'poll_channels', lambda *a, **k: 2)
    monkeypatch.setattr(server.blackboard, 'roll_daily', lambda _: None)
    monkeypatch.setattr(ci, 'poll', lambda _: None)
    monkeypatch.setattr(server, 'run_due_reports', lambda *a: None)
    monkeypatch.setattr(server, '_drain_worker', lambda _: SimpleNamespace(submit=lambda **kw: SimpleNamespace(wait=lambda: None, error=None)))
    yield store
    store.cx.close()


def test_first_triage_and_checks_and_reports_publish_their_phase_while_held(sync_store, monkeypatch):
    entered = [threading.Event() for _ in range(3)]
    released = [threading.Event() for _ in range(3)]
    def hold(n):
        entered[n].set()
        assert released[n].wait(10), 'test did not release the synthetic stage'
    monkeypatch.setattr(server, '_drain_worker', lambda _: SimpleNamespace(submit=lambda **kw: SimpleNamespace(wait=lambda: hold(0), error=None)))
    monkeypatch.setattr(ci, 'poll', lambda _: hold(1))
    monkeypatch.setattr(server, 'run_due_reports', lambda *a: hold(2))
    with ThreadPoolExecutor(max_workers=1) as pool:
        job = pool.submit(server._poll_reports)
        try:
            client = TestClient(server.app)
            for n, phase in enumerate(('triaging', 'checking', 'running_reports')):
                assert entered[n].wait(10)
                data = client.get('/api/ingest/status').json()
                assert data['status']['state'] == 'running'
                assert data['status']['phase'] == phase
                assert data['status']['lane'] == 'full'
                assert data['lastFetchCompletedAt'] >= data['lastPollAt']
                assert server._POLL_BUSY.locked()
                released[n].set()
            assert job.result(10) == 2
        finally:
            for event in released: event.set()
    assert server.ingest_status()['status'] == {'state': 'idle'}
    assert not server._POLL_BUSY.locked()


def test_skipped_and_failed_fetches_never_advance_completion(sync_store, monkeypatch):
    sync_store.set_setting('ingest_last_fetch_completed_at', '123', 'fixture')
    monkeypatch.setattr(channels, '_poll_jobs', lambda _: [])
    assert server._poll_reports() == 0
    assert server.ingest_status()['lastFetchCompletedAt'] == 123
    monkeypatch.setattr(channels, '_poll_jobs', lambda _: [({'Type': 'outlook'}, {})])
    def fail(*a, **kw): raise RuntimeError('synthetic fetch failure')
    monkeypatch.setattr(channels, 'poll_channels', fail)
    with pytest.raises(RuntimeError, match='synthetic fetch failure'): server._poll_reports()
    assert server.ingest_status()['lastFetchCompletedAt'] == 123
    assert not server._POLL_BUSY.locked()


def test_quick_status_cannot_replace_full_phase_or_fetch_completion(sync_store):
    full = server._status_begin(sync_store, 'full', 'full fetch')
    quick = server._status_begin(sync_store, 'quick', 'chat fetch')
    try:
        server._status_progress(sync_store, full, 'report work', phase='running_reports')
        server._status_progress(sync_store, quick, 'chat work', phase='triaging')
        import json
        assert json.loads(sync_store.get_settings()['ingest_status'])['phase'] == 'running_reports'
        server._status_end(sync_store, quick)
        assert json.loads(sync_store.get_settings()['ingest_status'])['phase'] == 'running_reports'
        assert sync_store.get_settings().get('ingest_last_fetch_completed_at') is None
    finally:
        server._status_end(sync_store, full)
