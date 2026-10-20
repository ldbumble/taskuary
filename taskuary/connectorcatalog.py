"""THE connector catalogue, once (taskuary/connectorcatalog.json): every card the Connections tab shows,
working or planned. The tab reads the same file (connectorCatalog.js); the Advisor is handed the cards nothing
here reads and decides itself which one the owner's threads are about (assistant.connect_evidence). A word
matcher over each card's `match` names decided that until 2026-10-11 and is gone: "Federal Holiday - Monday
October 12th" was a thread about Monday.com. The catalogue used to live only in the page's JavaScript, where
the server could not read a word of it (2026-09-18)."""
import json
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).with_name('connectorcatalog.json')


@lru_cache(maxsize=1)
def cards() -> list: return json.loads(_PATH.read_text(encoding='utf-8'))['cards']


def by_type(t: str) -> dict | None: return next((c for c in cards() if c['type'] == t), None)


def is_connected(c: dict) -> bool:
    """A card that is on, has what it needs to reach its system, and is not failing - the one rule the Connections page counts by."""
    return bool(c.get('Active') and (c.get('HasSecret') or c.get('LastSyncAt') or c.get('Secret')) and not c.get('LastError'))


def connected_count(store, cli_connections: dict) -> int:
    """How many connections Connections says are connected: the cards, and every connected AI CLI agent beside them. The page counted
    the cards alone and said "0 connected" over its own AI CLI agents card reading Connected (2026-10-19 UI walk)."""
    return sum(map(is_connected, store.list_connectors() or [])) + len(cli_connections or {})
