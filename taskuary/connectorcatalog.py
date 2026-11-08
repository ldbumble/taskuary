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
def _raw() -> dict: return json.loads(_PATH.read_text(encoding='utf-8'))
def cards() -> list: return _raw()['cards']


def source_types() -> tuple:
    """Where work comes in: the working cards of the groups the catalogue marks as sources (its `sources`), in its own order.
    Setup's main source is any one of them - mail, chat or a task system (the owner, 2026-10-21: "normally it's email ... any
    messaging/email/task system (e.g. monday.com) as an option") - so the list is the catalogue's, never a name list here."""
    gs = _raw()['sources']['groups']
    # ...and a vendor's MCP server (remotemcp.py) brings nothing in: it is a tool the agents reach out with, never a source
    return tuple(c['type'] for c in cards() if c.get('group') in gs and not c.get('planned') and not c.get('mcp'))


def own_groups() -> tuple:
    "The groups whose cards sign into the owner's own systems (the catalogue's `own_systems`): a report source on one is theirs by default."
    return tuple(_raw().get('own_systems', {}).get('groups') or ())


def by_type(t: str) -> dict | None: return next((c for c in cards() if c['type'] == t), None)


def is_connected(c: dict) -> bool:
    """A card that is on, has what it needs to reach its system, and is not failing - the one rule the Connections page counts by."""
    return bool(c.get('Active') and (c.get('HasSecret') or c.get('LastSyncAt') or c.get('Secret')) and not c.get('LastError'))


def connected_count(store, cli_connections: dict) -> int:
    """How many connections Connections says are connected: the cards, and every connected AI CLI agent beside them. The page counted
    the cards alone and said "0 connected" over its own AI CLI agents card reading Connected (2026-10-19 UI walk)."""
    return sum(map(is_connected, store.list_connectors() or [])) + len(cli_connections or {})


# WHAT THE OWNER PRESSES, PER CONNECTOR (the catalogue's `actions`, the owner 2026-11-05): the fields an act's card shows, which the owner
# may change before the press, which the agent may name, and the per-connection defaults. One card draws them all (ActionCard.jsx).
def actions(t: str) -> list: return list((by_type(t) or {}).get('actions') or [])
def action_for(tool: str) -> dict | None:
    "The declared act a run_tool on `tool` is, with the card it belongs to - None for a tool no card sets up for a press."
    return next(({**a, 'card': c['type']} for c in cards() for a in c.get('actions') or [] if a.get('tool') == tool), None) if tool else None
def field(act: dict, key: str) -> dict | None: return next((f for f in (act or {}).get('fields') or [] if f['key'] == key), None)
def text_key(act: dict) -> str | None:
    "The act's words the owner edits in its box (a post's `text`, a tracker comment's `body`)."
    return next((f['key'] for f in (act or {}).get('fields') or [] if f['type'] == 'text' and f.get('edit')), None)
def choice_ok(f: dict, v) -> bool: return f.get('type') != 'choice' or str(v) in {str(c['value']) for c in f.get('choices') or []}


def with_defaults(p: dict, conf: dict) -> dict:
    """An agent's proposal, its unnamed choices filled: the connection's own default (`default_<key>` on its card, set under Connections),
    else the catalogue's. What the agent named stays - the card shows the result, and the owner may change it before pressing."""
    act = action_for((p or {}).get('type'))
    if not act: return p
    mine = lambda f: (conf or {}).get(f'default_{f["key"]}')
    fill = {f['key']: mine(f) if mine(f) not in (None, '') and choice_ok(f, mine(f)) else f.get('default') for f in act['fields'] if f.get('setting') or f.get('default')}
    return {**{k: v for k, v in fill.items() if v not in (None, '')}, **{k: v for k, v in p.items() if v not in (None, '')}}


def owner_edits(p: dict, fields: dict) -> dict:
    """The owner's changes on the card, at the press: only the fields its act declares editable (never the tool, the connection or a path),
    a choice only among its own values. Anything else is refused, not dropped - the owner pressed for what the card said."""
    act = action_for((p or {}).get('type'))
    if not fields: return p
    if not act: raise ValueError('this step has no card to change it on')
    out = dict(p)
    for k, v in fields.items():
        f = field(act, k)
        if not (f and f.get('edit')) or f['type'] in ('text', 'image', 'files', 'people'): raise ValueError(f'{k} cannot be changed on this card')
        if not choice_ok(f, v): raise ValueError(f'{v!r} is not one of the choices for {f["label"]}')
        out[k] = v
    return out
