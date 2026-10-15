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
def _cards() -> list: return json.loads(_PATH.read_text(encoding='utf-8'))['cards']


def cards(language=None) -> list:
    if language is None: return _cards()
    from . import i18n
    return [i18n.presentation(c, language) for c in _cards()]


def by_type(t: str) -> dict | None: return next((c for c in cards() if c['type'] == t), None)
