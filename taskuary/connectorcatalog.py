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
    # ...a vendor's MCP server (remotemcp.py) or a keyed API read (apireads.py) brings nothing in: a tool the agents reach out with;
    # a mailbox preset (Fastmail, Proton Mail) is an IMAP card with its servers filled in, never a connector type of its own
    from .apireads import types as reads
    return tuple(c['type'] for c in cards() if c.get('group') in gs and not c.get('planned') and not c.get('preset') and not c.get('mcp')
                 and c['type'] not in reads())


def own_groups() -> tuple:
    "The groups whose cards sign into the owner's own systems (the catalogue's `own_systems`): a report source on one is theirs by default."
    return tuple(_raw().get('own_systems', {}).get('groups') or ())


def by_type(t: str) -> dict | None: return next((c for c in cards() if c['type'] == t), None)


# A CARD'S SECRET CONFIG FIELDS, DECLARED ONCE: each card's `secret_config` here, and a keyed API read's `write_only` (apireads.json).
# They are sealed in the column (store.py through vault.py) and never sent back to the browser (guard.masked_config) - by what the card
# declares, never by a key's name. An app password kept in ConfigJson beside a sealed Secret sat there as text until 2026-11-24.
@lru_cache(maxsize=1)
def secret_config() -> dict:
    from .apireads import write_only
    out = {c['type']: tuple(c['secret_config']) for c in cards() if c.get('secret_config')}
    for t, ks in write_only().items(): out[t] = tuple(dict.fromkeys((*out.get(t, ()), *ks)))
    return out
def secret_keys(t) -> tuple: return secret_config().get(t, ())


# A CARD NOT SIGNED IN SAYS SO IN PLAIN WORDS, WITH THE WAY TO IT (design round 6, D8: a post failed "save the app's Client ID and Client Secret
# ... or paste a token from the developer portal's OAuth token generator" - setup words, and nothing to press). One line for every connector
def not_signed_in(t: str) -> str:
    n = (by_type(t) or {}).get('title') or t
    return f"{n} isn't signed in - [open its card](#connector={t}) in Connections and press Sign in with {n}"


# IS THIS CONNECTION CONNECTED - ONE ANSWER (rule 3). The Connections page asked it six ways, the phone a seventh and triage an eighth:
# a card switched on and never signed in read "Not set up" on the page while triage and the agents were told they could reach it, and a
# failing card read "connection ✓" in the data-source picker. `state` decides; the API sends it (State) and every surface reads that.
# A card with no sign-in of its own is on once it is switched on: the catalogue's `keyless` cards (a local folder, a free public feed),
# a keyless or borrowed-sign-in API read (apireads, the page's `bare`), and an `mcp` card - each agent CLI signs in to that (remotemcp).
def keyless(t: str) -> bool:
    from . import apireads
    s, c = apireads.table().get(t), by_type(t) or {}
    borrowed = s and s.get('auth') in apireads.SIGN_INS and s.get('auth') != 'oauth' and not s.get('key')     # another card's sign-in
    return bool(c.get('keyless') or c.get('mcp') or (s and (s.get('keyless') or borrowed)))
def signed_in(c: dict, srcs=()) -> bool:
    "A card that is on and holds what it needs to reach its system - a card switched on and never signed in is not (the walks, 2026-11-18)."
    if not c.get('Active'): return False
    try: cfg = json.loads(c.get('ConfigJson') or '{}') or {}
    except (TypeError, ValueError): cfg = {}
    return bool(c.get('HasSecret') or c.get('LastSyncAt') or c.get('Secret') or (isinstance(cfg, dict) and cfg.get('google_refresh_token'))
                or keyless(c.get('Type')) or any(s.get('Active') and s.get('ConnectorId') == c.get('ConnectorId') for s in srcs or ()))


def lapsed(err) -> bool:
    """The system refused the sign-in the card holds: the lapse lines this app writes (msauth, googlecal and chatgptauth's "sign-in has
    lapsed", imapmail.GOOGLE_REFUSED, teamsweb.SIGNED_OUT) and OAuth's own refusal code. Gmail's raw "invalid_grant" missed the page's
    word list, and the card said "Not answering - click to fix it" over a sign-in to do (2026-11-19)."""
    from .imapmail import GOOGLE_REFUSED
    from .teamsweb import SIGNED_OUT
    s = str(err or '')
    return any(m in s for m in ('sign-in has lapsed', 'invalid_grant', GOOGLE_REFUSED, SIGNED_OUT))
def signed_out(c: dict) -> bool: return bool((c or {}).get('Active') and lapsed(c.get('LastError')))


LINES = {'connected': 'Connected', 'not_signed_in': 'Not signed in', 'signed_out': 'Needs sign-in',
         'failing': 'Not answering - open it to fix it', 'off': 'Not set up'}
def state(c: dict, srcs=()) -> dict:
    """{state, line, fix}: 'connected' | 'not_signed_in' | 'signed_out' | 'failing' | 'off', its plain line, and the card's link. `srcs`
    are the store's sources: a card a source of its own reads through is signed in by it."""
    k = ('off' if not c.get('Active') else 'signed_out' if signed_out(c) else 'not_signed_in' if not signed_in(c, srcs)
         else 'failing' if c.get('LastError') else 'connected')
    return {'state': k, 'line': LINES[k], 'fix': '' if k == 'connected' else f"#connector={c.get('Type') or ''}"}
def is_connected(c: dict, srcs=()) -> bool: return state(c, srcs)['state'] == 'connected'
SIGNED_IN = ('connected', 'failing', 'signed_out')     # signed in once: a card failing for a moment is still his system, said as failing
def connected(store, failing=False) -> list:
    """The cards that are connected, each with its State: what Connections counts and the phone says. failing=True keeps a card that is
    signed in but failing or lapsed right now - triage and the agents are still told of it, with its line, never as if it were gone."""
    srcs = store.list_sources() if hasattr(store, 'list_sources') else ()
    ok = SIGNED_IN if failing else ('connected',)
    return [c | {'State': st} for c in store.list_connectors() or [] if (st := state(c, srcs))['state'] in ok]
def as_now(c) -> str:
    "' - not answering right now' / ' - needs sign-in right now' for a card connected(failing=True) kept, '' for a connected one."
    st = c.get('State') or {}
    return '' if st.get('state') in (None, 'connected') else f" - {st['line'].split(' - ')[0].lower()} right now"


def connected_count(store, cli_connections: dict) -> int:
    """How many connections Connections says are connected: the cards, and every connected AI CLI agent beside them. The page counted
    the cards alone and said "0 connected" over its own AI CLI agents card reading Connected (2026-10-19 UI walk)."""
    return len(connected(store)) + len(cli_connections or {})


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
    """The owner's changes on the card, at the press: only the fields its act declares editable (never the tool, the connection or a path) -
    a choice only among its own values, a line of words (a title, labels) as he left it. Anything else is refused, not dropped - the owner
    pressed for what the card said."""
    act = action_for((p or {}).get('type'))
    if not fields: return p
    if not act: raise ValueError('this step has no card to change it on')
    out = dict(p)
    for k, v in fields.items():
        f = field(act, k)
        if not (f and f.get('edit')) or f['type'] in ('text', 'image', 'files', 'people'): raise ValueError(f'{k} cannot be changed on this card')
        if not choice_ok(f, v): raise ValueError(f'{v!r} is not one of the choices for {f["label"]}')
        # ...an emptied line goes empty only where the act may go without it: an issue with no title is no issue
        if f['type'] == 'line' and not (v := str(v or '').strip()) and not f.get('optional'): raise ValueError(f'{f["label"]} cannot be empty')
        out[k] = v
    return out
