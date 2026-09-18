"""THE connector catalogue, once (taskuary/connectorcatalog.json): every card the Connections tab shows,
working or planned, with the words that mean that system. The tab reads the same file (connectorCatalog.js).
The Assistant report reads it here to say "six threads this month were about ADP and nothing here reads
it - connect ADP?" (assistant.connect_ideas). The catalogue used to live only in the page's JavaScript,
where the server could not read a word of it (2026-09-18)."""
import json, re
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).with_name('connectorcatalog.json')


@lru_cache(maxsize=1)
def cards() -> list: return json.loads(_PATH.read_text(encoding='utf-8'))['cards']


def by_type(t: str) -> dict | None: return next((c for c in cards() if c['type'] == t), None)


# Words that name no system. Every card's `match` was written by splitting its title, so "Network
# file share" shipped matching the bare words `network`, `file` and `share` - three of the commonest
# words in office mail - and `mentions` counted "can you share the file?" as a thread about an SMB
# share. A single one of these is dropped; a PHRASE that contains one ("network file share",
# "bank & card feed (teller)") is kept, which is what keeps every card matchable by its own title.
GENERIC = frozenset({'any', 'bank', 'card', 'cloud', 'connection', 'data', 'database', 'feed', 'file',
                     'files', 'historical', 'market', 'network', 'search', 'server', 'services',
                     'share', 'string', 'team', 'web'})


def words(card: dict) -> list:
    """The match words that survive GENERIC - the card's own title always among them."""
    return [w for w in card.get('match') or [] if len(w) > 2 and w.lower() not in GENERIC]


def _patterns(card: dict) -> list:
    return [re.compile(r'(?<![a-z0-9])' + re.escape(w) + r'(?![a-z0-9])', re.I) for w in words(card)]


def mentions(texts: list, exclude_types: set = frozenset()) -> dict:
    """{type: how many of `texts` name that system} - whole words, case-insensitive, one hit per text per
    card. Generic words ("search", "database") are kept out of `match` by the catalogue itself."""
    out = {}
    pats = [(c['type'], _patterns(c)) for c in cards() if c['type'] not in exclude_types]
    for t in texts:
        s = str(t or '')
        if not s: continue
        for typ, ps in pats:
            if any(p.search(s) for p in ps): out[typ] = out.get(typ, 0) + 1
    return out
