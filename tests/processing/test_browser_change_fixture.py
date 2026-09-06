"""New synthetic browser edits must never relax the demo's production routes."""
import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from taskuary import demo
from taskuary.store import SQLiteStore


def test_private_fixture_edits_preserve_all_production_demo_refusals(tmp_path, monkeypatch):
    monkeypatch.setenv('TASKUARY_DEMO', '1')
    monkeypatch.setenv('TASKUARY_HOME', str(tmp_path))
    # Record the original function so pytest restores it after fixture installation.
    monkeypatch.setattr(demo, 'refuse', demo.refuse)
    cases = [(method, path) for method in ('GET', 'POST', 'PATCH', 'PUT', 'DELETE')
             for path in ('/api/ingest/push', '/api/sync', '/api/tools/run',
                          '/api/reviews/1/decide', '/api/reviews/1', '/api/terminals',
                          '/api/connectors', '/api/funnel/settle', '/api/fixture/processing/other')]
    original = {(method, path): demo.refuse(method, path) for method, path in cases}
    path = Path(__file__).resolve().parents[2] / 'website' / 'browser' / 'fixture_changes.py'
    spec = importlib.util.spec_from_file_location('processing_browser_fixture_edits', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    db = SQLiteStore(str(tmp_path / 'fixture-edits.db'))
    client = None
    try:
        mid = db.add_message({'Channel': 'email', 'BodyText': 'Original synthetic source'})
        app = FastAPI()
        module.install_processing_changes(app, db)
        assert {(method, path): demo.refuse(method, path) for method, path in cases} == original
        assert demo.refuse('POST', '/api/fixture/processing/source') == ''
        assert demo.refuse('DELETE', '/api/fixture/processing/source')
        client = TestClient(app)
        for bad in ({'message_id': True, 'body': 'bad'}, {'message_id': mid, 'body': 'x' * 50001},
                    {'message_id': mid, 'body': 'bad', 'sql': 'not a fixture field'}):
            assert client.post('/api/fixture/processing/source', json=bad).status_code == 422
        assert db.get_message(mid)['BodyText'] == 'Original synthetic source'
        assert client.post('/api/fixture/processing/source', json={'message_id': mid, 'body': 'New source'}).status_code == 200
        assert db.get_message(mid)['BodyText'] == 'New source'
    finally:
        if client:
            client.close()
        db.cx.close()
