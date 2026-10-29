"""How readily triage joins a connection's messages onto a task already there, 1 (keep separate) to 5 (combine), one level per
connection TYPE (the owner, 2026-10-29). The level is handed to triage with the message; what each level means is the guide's
(templates/triage.md, "How far to combine") and the model decides - nothing here reads a word of any message."""
KEY, LO, HI, BASE = 'combine:', 1, 5, 3
DEFAULTS = {'whatsapp': 4, 'email': 4}
MAILBOXES = ('outlook', 'gmail', 'imap')     # the connector types whose messages arrive as channel 'email'
RECENT_DAYS = 7                              # how far back a closed task is still one a message may join


def kind(t) -> str:
    "The connection type a level is kept under: a mailbox card and the 'email' channel its mail arrives on are one."
    t = str(t or '').strip().lower()
    return 'email' if t in MAILBOXES else t


def default(t) -> int: return DEFAULTS.get(kind(t), BASE)


def clamp(v):
    "A level 1-5, or None for anything that is not one."
    try: n = int(str(v).strip())
    except (TypeError, ValueError): return None
    return n if LO <= n <= HI else None


def level(store, t) -> int:
    k = kind(t)
    return clamp(store.get_setting(KEY + k)) or default(k) if k else BASE


def set_level(store, t, v, actor: str = 'owner') -> int:
    k, n = kind(t), clamp(v)
    if not k: raise ValueError('which connection?')
    if n is None: raise ValueError(f'a combine level is {LO} to {HI}')
    store.set_setting(KEY + k, str(n), actor)
    return n


def levels(store, types=()) -> dict:
    "Every connection type's level: the ones asked for, the ones with defaults, and any the owner set."
    have = [s['Name'][len(KEY):] for s in store.list_settings() if str(s.get('Name') or '').startswith(KEY)]
    return {k: level(store, k) for k in dict.fromkeys([*map(kind, types), *DEFAULTS, *have]) if k}


def for_triage(store, msg: dict) -> dict:
    "What triage is handed: the message's connection and its level."
    k = kind(msg.get('channel'))
    return {'connection': k, 'level': level(store, k)} if k else {}
