"""A Teams card with no Microsoft app of its own signs in through the Outlook card's (the owner, 2026-11-05: "for teams you should be able to
click auth with outlook oauth as well"). Invented ids only."""
import json
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import server
from taskuary.store import MemoryStore

APP, TENANT = '11111111-2222-3333-4444-555555555555', '66666666-7777-8888-9999-000000000000'


def _world():
    s = MemoryStore()
    s.save_connector({'Type': 'outlook', 'Name': 'Work mail', 'Active': 1, 'ConfigJson': json.dumps({'client_id': APP, 'tenant_id': TENANT})}, 't')
    teams = s.save_connector({'Type': 'teams', 'Name': 'Teams', 'Active': 1, 'ConfigJson': '{}'}, 't')
    return s, teams


def test_the_teams_card_says_it_signs_in_through_outlook():
    s, teams = _world()
    with mock.patch.object(server, 'store', s):
        rows = TestClient(server.app).get('/api/connectors').json()
    rows = rows.get('data', rows) if isinstance(rows, dict) else rows
    assert next(r for r in rows if r['ConnectorId'] == teams)['MsApp'] == 'outlook'


def test_its_sign_in_uses_the_outlook_app():
    s, teams = _world()
    with mock.patch.object(server, 'store', s):
        r = TestClient(server.app).post(f'/api/connectors/{teams}/ms/signin', json={})
    assert r.status_code == 200, r.text
    assert APP in json.dumps(r.json()) and TENANT in json.dumps(r.json())
    assert not json.loads(s.get_connector(teams)['ConfigJson'] or '{}').get('client_id')     # borrowed, never copied onto the Teams card
