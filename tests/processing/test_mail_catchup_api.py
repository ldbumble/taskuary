"""An isolated Sync now request retries a paged mailbox without changing old reads."""
from datetime import datetime, timedelta, timezone
import json
import re
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi.testclient import TestClient

from taskuary import channels, server, terminal
from taskuary.store import SQLiteStore


def test_sync_api_recovers_a_late_mail_page_and_preserves_owner_state(tmp_path, monkeypatch):
    db = SQLiteStore(str(tmp_path / 'mail-api.db'))
    monkeypatch.setattr(server, 'store', db)
    monkeypatch.setattr(server, '_llm', lambda *args: object())
    monkeypatch.setattr(terminal, 'live_sessions', lambda **kwargs: [])
    monkeypatch.setattr(server, 'run_due_reports', lambda *args: None)
    monkeypatch.setattr('taskuary.ci.poll', lambda *args: None)
    monkeypatch.setattr(server.blackboard, 'roll_daily', lambda *args: None)
    monkeypatch.setattr(channels, 'graph_token', lambda *args: 'fixture-token')
    cid = db.get_connector_by_type('outlook')['ConnectorId']
    db.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': 'synthetic', 'Roles': 'feed',
                       'ConfigJson': '{"tenant_id":"fixture","client_id":"fixture"}'}, 'fixture')
    sid = db.save_source({'Channel': 'email', 'Address': 'synthetic@example.invalid',
                          'ConnectorId': cid, 'Active': 1,
                          'ConfigJson': '{"folders":["inbox"],"custom":"before fetch"}'}, 'fixture')
    origin = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=2)
    watermark = (origin - timedelta(hours=1)).astimezone().strftime('%Y-%m-%d %H:%M:%S')
    db._exec('UPDATE source SET LastPolledAt=? WHERE SourceId=?', (watermark, sid))
    db.set_setting('mark_read_enabled', '0', 'fixture')
    old_mid = db.add_message({'ExternalId': 'graph:inbox-0', 'Channel': 'email',
                              'Status': 'filed', 'BodyText': 'Preserve the historical stored body',
                              'SentAt': origin.astimezone().strftime('%Y-%m-%d %H:%M:%S')})
    db.set_funnel_state(f'msg:{old_mid}', 'done', 'owner')
    db.save_doc('soul', 'Owner document must remain exact.', 'owner')
    old_message, old_reads = db.get_message(old_mid), db.funnel_states()
    messages = [{
        'id': f'inbox-{i}', 'subject': f'Synthetic backlog {i}',
        'receivedDateTime': (origin + timedelta(seconds=i)).isoformat(),
        'from': {'emailAddress': {'name': 'Fixture sender', 'address': 'sender@example.invalid'}},
        'body': {'content': f'Synthetic body {i}', 'contentType': 'text'},
        'conversationId': f'fixture-thread-{i}', 'isRead': True, 'hasAttachments': False,
    } for i in range(600)]
    failing, edited, fetched = [True], [False], []

    def get(url, headers=None, timeout=None, params=None):
        parsed = urlsplit(url)
        assert parsed.hostname == 'graph.microsoft.com'
        assert headers == {'Authorization': 'Bearer fixture-token'}
        assert timeout == 30
        query = dict(params) if params is not None else {k: v[0] for k, v in parse_qs(parsed.query).items()}
        folder = parsed.path.split('/mailFolders/')[1].split('/')[0]
        rows = messages if folder == 'inbox' else []
        for op, raw in re.findall(r'receivedDateTime\s+(gt|ge|le|lt)\s+([^\s)]+)', query['$filter']):
            bound = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            def qualifies(row):
                when = datetime.fromisoformat(row['receivedDateTime'])
                return {'gt': when > bound, 'ge': when >= bound,
                        'le': when <= bound, 'lt': when < bound}[op]
            rows = [row for row in rows if qualifies(row)]
        skip, size = int(query.get('$skip', 0)), int(query.get('$top', 50))
        page = rows[skip:skip + size]
        fetched.append((folder, tuple(row['id'] for row in page)))
        if folder == 'inbox' and page and int(page[0]['id'].split('-')[1]) >= 550:
            if not edited[0]:
                cfg = json.loads(db.get_source(sid)['ConfigJson'])
                db.save_source({'SourceId': sid, 'ConfigJson': json.dumps({**cfg, 'custom': 'owner edit during fetch'})}, 'owner')
                edited[0] = True
            if failing[0]: raise RuntimeError('synthetic late Graph page unavailable')
        body = {'value': page}
        if skip + len(page) < len(rows):
            body['@odata.nextLink'] = parsed._replace(query=urlencode({**query, '$skip': skip + len(page)})).geturl()

        class Response:
            def raise_for_status(self): pass
            def json(self): return body
        return Response()

    monkeypatch.setattr(channels.requests, 'get', get)
    client = TestClient(server.app)
    try:
        response = client.post('/api/ingest/poll')
        assert response.status_code == 200, response.text
        card = client.get('/api/connectors').json()['data']
        assert 'synthetic late Graph page unavailable' in next(c for c in card if c['ConnectorId'] == cid)['LastError']
        assert db.get_source(sid)['LastPolledAt'] == watermark
        assert db._one("SELECT COUNT(*) n FROM message WHERE ExternalId LIKE 'graph:inbox-%'")['n'] == 500
        assert json.loads(db.get_source(sid)['ConfigJson'])['custom'] == 'owner edit during fetch'

        failing[0] = False
        assert client.post('/api/ingest/poll').status_code == 200
        rows = db._rows("SELECT * FROM message WHERE ExternalId LIKE 'graph:inbox-%'")
        assert {row['ExternalId'] for row in rows} == {f'graph:inbox-{i}' for i in range(600)}
        assert len(rows) == 600
        assert not db.get_connector(cid).get('LastError')
        assert db.get_source(sid)['LastPolledAt'] != watermark
        visible = client.get('/api/feed', params={'channel': 'email', 'limit': 100})
        assert visible.status_code == 200, visible.text
        assert any(row['Subject'] == 'Synthetic backlog 599' for row in visible.json()['data'])
        assert client.post('/api/ingest/poll').status_code == 200
        assert db._one("SELECT COUNT(*) n FROM message WHERE ExternalId LIKE 'graph:inbox-%'")['n'] == 600
        assert db.get_message(old_mid) == old_message
        assert db.funnel_states() == old_reads
        assert db.get_doc('soul') == 'Owner document must remain exact.'
        assert json.loads(db.get_source(sid)['ConfigJson'])['custom'] == 'owner edit during fetch'
        assert any(folder == 'sentitems' for folder, _ in fetched)
    finally:
        assert server.join_drains(db, timeout=5)
        client.close()
        db.cx.close()
