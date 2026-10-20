"""Connections says "N connected" once, from the server, and counts the AI CLI agents with the cards: the page counted the cards alone
and read "0 connected" over its own AI CLI agents card saying Connected (2026-10-19 UI walk)."""
import unittest
from taskuary import connectorcatalog as cc


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

    def test_the_page_reads_the_servers_count(self):
        from pathlib import Path
        page = (Path(__file__).parent.parent / 'website' / 'src' / 'ConnectorsView.jsx').read_text(encoding='utf-8')
        self.assertIn('c.data.connected', page)
        src = (Path(__file__).parent.parent / 'taskuary' / 'server.py').read_text(encoding='utf-8')
        self.assertIn("'connected': connected_count(store, cfg.get('cli_connections'))", src)


if __name__ == '__main__': unittest.main()
