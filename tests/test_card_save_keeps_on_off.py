"""#242: a card's settings saved without `Active` leave it as the owner left it - off stays off, on stays on.
The data card's Save used to send Active: true with every save; the page no longer does, and the route must not
read a missing `Active` as either."""
import json

from fastapi.testclient import TestClient

from taskuary import server

c = TestClient(server.app)


def _card(name, active):
    cid = c.post('/api/connectors', json={'Type': 'prometheus', 'Name': name}).json()['connectorId']
    c.post('/api/connectors', json={'ConnectorId': cid, 'Active': active})
    return cid


def test_a_settings_save_keeps_the_card_on_or_off():
    for name, on in (('Northwind metrics off', False), ('Northwind metrics on', True)):
        cid = _card(name, on)
        r = c.post('/api/connectors', json={'ConnectorId': cid, 'ConfigJson': json.dumps({'base_url': 'https://metrics.northwind.example'})})
        assert r.status_code == 200, r.text
        got = server.store.get_connector(cid)
        assert bool(got['Active']) is on, f'{name}: a settings save switched the card {"off" if on else "on"}'
        assert json.loads(got['ConfigJson'])['base_url'] == 'https://metrics.northwind.example'
