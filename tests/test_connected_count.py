"""Connections says "N connected" once, from the server, and counts the AI CLI agents with the cards: the page counted the cards alone
and read "0 connected" over its own AI CLI agents card saying Connected (2026-10-19 UI walk).

...and IS THIS CONNECTION CONNECTED is answered once (connectorcatalog.state): the page, the phone, search, triage and the agent's brief
each had their own rule, and a card switched on and never signed in read "Not set up" on the page while triage was told it could reach it."""
import json, unittest
from pathlib import Path
from unittest import mock
from taskuary import connectorcatalog as cc
from taskuary.store import MemoryStore

ROOT = Path(__file__).parent.parent


class _Store:
    def __init__(self, rows): self.rows = rows
    def list_connectors(self): return self.rows


class ConnectedCount(unittest.TestCase):
    def test_cards_and_cli_agents_are_counted_once(self):
        rows = [{'Active': 1, 'HasSecret': 1}, {'Active': 1, 'LastSyncAt': 'x'}, {'Active': 1, 'HasSecret': 1, 'LastError': 'boom'},
                {'Active': 0, 'HasSecret': 1}, {'Active': 1}]
        self.assertEqual(cc.connected_count(_Store(rows), {}), 2)
        self.assertEqual(cc.connected_count(_Store([]), {'claude': {'cmd': 'claude'}}), 1, 'a connected CLI agent is a connection')
        self.assertEqual(cc.connected_count(_Store(rows), {'claude': {}, 'codex': {}}), 4)
        self.assertEqual(cc.connected_count(_Store([]), None), 0)


def _card(s, typ, **f):
    cid = next(c['ConnectorId'] for c in s.list_connectors() if c['Type'] == typ)
    s.save_connector({'ConnectorId': cid, **f}, 't')
    return cid


def _api(s):
    from fastapi.testclient import TestClient
    from taskuary import server
    with mock.patch.object(server, 'store', s):
        return {c['ConnectorId']: c for c in TestClient(server.app).get('/api/connectors').json()['data']}


def test_a_card_switched_on_and_never_signed_in_is_not_connected_on_any_surface():
    """The live shape: LinkedIn switched on, no sign-in. The page (State) said not connected; triage's connected_systems and the agent's
    brief said it could be posted to; the phone and search had their own rules. One answer now."""
    from taskuary import doorway_browse, docsync, ingest, search
    s = MemoryStore()
    cid = _card(s, 'linkedin', Active=1)
    page = _api(s)[cid]['State']
    assert page['state'] == 'not_signed_in' and page['fix'] == '#connector=linkedin'
    assert not any('(linkedin)' in n for n in ingest.connected_systems(s)), 'triage is told what the page says'
    assert f'connector_id {cid}' not in docsync.agent_systems(s), "the agent's brief is told the same"
    assert doorway_browse._connected(s)['linkedin'] == page['line'].lower(), 'the phone says the card\'s own line'
    hit = next(h for h in search._connectors(s, ['linkedin']) if h['id'] == 'con:linkedin')
    assert hit['sub'] == 'not connected'
    s.save_connector({'ConnectorId': cid, 'Secret': 'tok'}, 't')                    # ...and signed in, every surface turns together
    assert _api(s)[cid]['State']['state'] == 'connected'
    assert any('(linkedin)' in n for n in ingest.connected_systems(s)) and f'connector_id {cid}' in docsync.agent_systems(s)
    assert doorway_browse._connected(s)['linkedin'] == 'connected'


def test_a_card_failing_for_a_moment_is_still_known_to_triage_and_the_agent_as_failing():
    """A signed-in card whose last read failed is his system still: triage and the agent's brief name it with its state instead of
    dropping it (it vanished from both on the first cut of the one answer); the page and the phone count it as not connected."""
    from taskuary import docsync, ingest
    s = MemoryStore()
    cid = _card(s, 'linkedin', Active=1, Secret='tok')
    n = cc.connected_count(s, None)
    s.touch_connector(cid, 'timed out')
    assert _api(s)[cid]['State']['state'] == 'failing' and cc.connected_count(s, None) == n - 1
    assert any(n.startswith('LinkedIn') and n.endswith('(linkedin) - not answering right now') for n in ingest.connected_systems(s))
    brief = docsync.agent_systems(s)
    assert f'connector_id {cid}' in brief and 'not answering right now' in brief


def test_a_card_with_no_sign_in_of_its_own_is_connected_once_on():
    s = MemoryStore()
    cid = _card(s, 'handbook', Active=1)
    assert _api(s)[cid]['State']['state'] == 'connected'
    from taskuary import ingest
    assert any('(handbook)' in n for n in ingest.connected_systems(s))


def test_gmails_refused_sign_in_reads_signed_out_on_the_card_and_the_bell_alike():
    """Gmail's raw "invalid_grant" missed the page's word list: the card said "Not answering - click to fix it" while a sign-in was
    all it needed, and the bell (Outlook-only) said nothing of a sign-in at all."""
    from taskuary import outbound, problems
    s = MemoryStore()
    err = 'Google token failed (400): {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}'
    cid = _card(s, 'gmail', Active=1, Secret='app-pw')
    s.touch_connector(cid, err)
    card = _api(s)[cid]
    assert card['State']['state'] == 'signed_out' and card['SignedOut'] is True
    bell = next(p for p in problems.collect(s) if p['connector'] == str(cid))
    assert bell['kind'] == 'signed_out' and bell['title'].startswith('Google signed you out')
    assert outbound.auth_fix(RuntimeError(err))['label'] == 'Sign in again', 'a send on it is fixed the same way'
    page = (ROOT / 'website' / 'src' / 'ConnectorsView.jsx').read_text(encoding='utf-8')
    assert 'SIGNED_OUT' not in page and 'LastError.test' not in page, 'the page never reads error text for it'


def test_a_rejected_token_reads_signed_out_on_its_card_and_clears_when_it_works_again():
    """A revoked GitHub token answered 401 on every repo read: the card said "last test failed" over a sign-in to do. A 401 is the
    credentials refused, whatever system says it - the card and the bell both say sign in again, once, and a read that works clears both."""
    from taskuary import problems
    s = MemoryStore()
    cid = _card(s, 'github', Active=1, Secret='tok')
    for _ in range(2): s.touch_connector(cid, 'org/app: 401 Client Error: Unauthorized for url: https://api.github.example/repos/org/app/issues')
    assert _api(s)[cid]['State']['state'] == 'signed_out'
    assert [p['kind'] for p in problems.collect(s) if p['connector'] == str(cid)] == ['signed_out'], 'one bell item, however many reads failed'
    s.touch_connector(cid)
    assert _api(s)[cid]['State']['state'] == 'connected' and not [p for p in problems.collect(s) if p['connector'] == str(cid)]
    chatgpt = _card(s, 'chatgpt', Active=1, Secret='rt')
    s.touch_connector(chatgpt, 'the ChatGPT sign-in has lapsed - sign in again on the ChatGPT card')
    assert _api(s)[chatgpt]['State']['state'] == 'signed_out'
    for err in ('GitHub refused the read (permissions or rate limit)', 'timed out after 401 seconds'):
        assert not cc.signed_out({'Active': 1, 'LastError': err}), err


def test_a_failing_data_card_is_not_connection_ok_in_the_picker():
    "The data-source picker read LastSyncAt alone - a switched-off card that once read said 'connection ✓'; it reads State now."
    page = (ROOT / 'website' / 'src' / 'ConnectorsView.jsx').read_text(encoding='utf-8')
    assert 'c?.LastSyncAt ? "connection ✓"' not in page and 'c.LastSyncAt ? "connection ✓"' not in page
    assert 'connWord(c)' in page
    st = cc.state({'Type': 'mssql', 'Active': 0, 'LastSyncAt': 'x'})
    assert st['state'] == 'off'


def test_a_settings_address_is_one_road_with_the_pages_twin():
    "A group named 'Mail / routing' opened the wrong anchor from concierge's inline quote(); every road and the page are held to one table."
    from taskuary import settings_schema as ss
    cases = json.loads((ROOT / 'website' / 'test' / 'settingHref.cases.json').read_text(encoding='utf-8'))['cases']
    for c in cases: assert ss.href(c['key'], c['group']) == c['href'], c
    for k, p in ss.panels().items(): assert ss.href(k) == ss.href(k, p['group'])
    for f in ('search.py', 'concierge.py'):
        assert '&group={quote(' not in (ROOT / 'taskuary' / f).read_text(encoding='utf-8'), f'{f} builds its own address'


if __name__ == '__main__': unittest.main()
