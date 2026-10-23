"""EVERY PRESS, KEPT (the Advisor and memory design, phase B, 2026-10-23). Only a desk press made while the Advisor's line showed was
recorded, so the Tasks tab, the phone and every press with nothing lit were lost - and a habit learned from a third of the presses
is a guess. One recorder for every surface: what was pressed, on which surface, what that surface had lit, which other buttons were
live (a press with no other button is no choice, and no evidence), and what the item was and whom it was from. Nothing is learned
here - that is phase C, which reads these rows through rows() and instructions(). Nothing on screen changes for it."""
import json, time, threading
from datetime import datetime, timedelta
from loguru import logger

SURFACES = ('desk', 'task', 'phone')
CODE_CHANNELS = ('github', 'gitlab', 'azdo', 'bitbucket')
SAME_PRESS_SECS = 3          # one press told twice (the row's press and the card's handler it runs) is one press
_LOCK = threading.Lock()


def _now() -> str: return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def _last(store) -> dict:
    """(key, verb, surface) -> (when, row id) for this store's last presses - a poll worker's proxy is the same store."""
    s = getattr(store, '_store', store)
    if not hasattr(s, '_press_last'): s._press_last = {}
    return s._press_last
def _verb(v) -> str:
    from .advisor import pressed_verb
    return pressed_verb(v) if v else ''


def personal(store, item: dict | None, m: dict | None = None) -> bool:
    """Mail from a mailbox the owner marked personal ({"personal": true} on its source) teaches nothing (the owner, 2026-10-23:
    "nothing learned from personal mail"). The app has no other mark of personal mail: a mailbox is work unless marked."""
    m = m or {}
    name, ch = str(m.get('SourceName') or '').lower(), str(m.get('Channel') or (item or {}).get('channel') or '').lower()
    if not name: return False
    try: srcs = store.list_sources(active_only=False)
    except Exception: return False
    for s in srcs:
        if str(s.get('Address') or '').lower() != name or (ch and str(s.get('Channel') or '').lower() not in (ch, '')): continue
        try: cfg = json.loads(s.get('ConfigJson') or '{}') or {}
        except ValueError: cfg = {}
        if cfg.get('personal'): return True
    return False


def _message(store, item: dict) -> dict:
    """The item's newest inbound message - who it is from (advisor.who_of reads the same one)."""
    mid = item.get('mid')
    m = store.get_message(int(mid)) if mid else None
    if not m and item.get('tid'):
        ms = [x for x in store.list_messages(int(item['tid'])) if str(x.get('Direction') or 'in') != 'out']
        m = ms[-1] if ms else None
    return m or {}


def advised_now(store, tgt) -> str:
    """The Advisor's verb standing on the item at its current revision - read from its rows, never a new judgement."""
    from . import advisor, concierge
    try:
        r = advisor.row(store, tgt[0], tgt[1], advisor.revision(store, *tgt))
        return concierge.canon_verb(r['Verb']) or '' if r and r.get('Verb') else ''
    except Exception: return ''


def live_now(store, item: dict, surface: str = 'desk') -> list:
    """The buttons the item's row draws now (concierge.row_buttons), and Next where the surface has one (the Tasks tab has none) - for a
    surface that did not say what it drew."""
    from . import concierge
    nxt = [] if surface == 'task' else ['next']
    try: return [b['verb'] for b in concierge.row_buttons(store, item)] + nxt
    except Exception: return nxt


def record(store, key: str, pressed: str, surface: str = 'desk', lit: str = None, live: list = None, rev: str = None,
           advised: str = None, item: dict = None) -> int:
    """One press on `key`. `lit`: the verb the surface had filled ('' for none; None reads the Advisor's own). `live`: the verbs the owner
    could have pressed instead (None reads the row's). `advised`: the Advisor's verb, when the surface showed its line. Returns the row id,
    or 0 when nothing is kept: a key with nothing behind it, or personal mail. Never raises past a logged warning."""
    return kept(store, key, pressed, surface, lit, live, rev, advised, item)[0]


def kept(store, key, pressed, surface='desk', lit=None, live=None, rev=None, advised=None, item=None) -> tuple:
    """record(), and whether the row is new: (id, True), or (id, False) for the same press told twice."""
    from . import advisor
    try:
        tgt = advisor.target_of(store, key)
        got = _verb(pressed)
        if not tgt or not got: return 0, False
        surface = surface if surface in SURFACES else 'desk'
        last, k = _last(store), (key, got, surface)
        with _LOCK:
            seen = last.get(k)
            if seen and time.monotonic() - seen[0] < SAME_PRESS_SECS: return seen[1], False
        item = item if item and item.get('key') == key else (advisor._item(store, *tgt, key=key) or item or {})
        m = _message(store, item)
        if personal(store, item, m): return 0, False
        w = advisor.who_of(store, item)
        adv = _verb(advised) if advised else advised_now(store, tgt) if advised is None else ''
        shown = adv if lit is None else _verb(lit)
        others = list(dict.fromkeys(v for v in (_verb(x) for x in (live_now(store, item, surface) if live is None else live)) if v and v != got))
        try: now = advisor.revision(store, *tgt)
        except Exception: now = None
        repo = (m.get('SourceName') or '') if w['channel'] in CODE_CHANNELS else ''
        rid = store._exec('INSERT INTO advice_press (Key,TargetKind,TargetId,Revision,Advised,Pressed,Match,ItemKind,Channel,Sender,SenderDomain,'
                          'Scope,Thread,Stale,CreatedAt,Surface,Lit,Live,Choice,Repo) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          (key, tgt[0], int(tgt[1]), rev or '', adv or None, got, int(bool(shown) and shown == got), str(item.get('kind') or ''),
                           w['channel'], w['sender'], w['domain'], w['scope'], w['thread'], int(bool(rev) and bool(now) and rev != now), _now(),
                           surface, shown or '', json.dumps(others), int(bool(others)), str(repo).lower()))
        with _LOCK:
            last[k] = (time.monotonic(), rid)
            for o in [o for o, (t, _i) in last.items() if time.monotonic() - t > SAME_PRESS_SECS]: last.pop(o, None)
        return rid, True
    except Exception as e:
        logger.warning(f'press {pressed} on {key} not recorded: {e}'); return 0, False


def _row(r: dict) -> dict:
    try: live = json.loads(r.get('Live') or '[]') or []
    except ValueError: live = []
    return {'id': r['Id'], 'at': r['CreatedAt'], 'key': r['Key'], 'target': (r['TargetKind'], r['TargetId']), 'surface': r.get('Surface') or 'desk',
            'pressed': r['Pressed'], 'lit': r.get('Lit') if r.get('Surface') else (r.get('Advised') or ''), 'advised': r.get('Advised') or '',
            'live': live, 'choice': bool(r['Choice']) if r.get('Choice') is not None else True, 'match': bool(r.get('Match')),
            'stale': bool(r.get('Stale')), 'kind': r.get('ItemKind') or '', 'channel': r.get('Channel') or '', 'sender': r.get('Sender') or '',
            'domain': r.get('SenderDomain') or '', 'repo': r.get('Repo') or '', 'scope': r.get('Scope') or '', 'thread': r.get('Thread') or ''}


_FIELDS = {'surface': 'Surface', 'pressed': 'Pressed', 'kind': 'ItemKind', 'channel': 'Channel', 'sender': 'Sender', 'domain': 'SenderDomain',
           'repo': 'Repo', 'scope': 'Scope', 'key': 'Key'}


def rows(store, since: str = None, days: int = None, choice: bool = None, fresh: bool = True, limit: int = None, **eq) -> list:
    """THE PRESS LOG, READ (what phase C learns from): oldest first, as dicts - {id, at, key, surface, pressed, lit, advised, live, choice,
    match, stale, kind, channel, sender, domain, repo, scope, thread}. Narrow by any of surface / pressed / kind / channel / sender /
    domain / repo / scope / key (exact), `since` or the last `days`, `choice` (only real choices, or only none), `fresh` (drop presses
    that answered an older screen). A row from before 2026-10-23 is a desk press under a line: its lit is the Advisor's verb."""
    q, p = ['1=1'], []
    if days is not None: since = max(since or '', (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S'))
    if since: q.append('CreatedAt>=?'); p.append(since)
    if fresh: q.append('IFNULL(Stale,0)=0')
    if choice is not None: q.append('IFNULL(Choice,1)=?'); p.append(int(choice))
    for k, v in eq.items():
        if k not in _FIELDS: raise ValueError(f'no press field {k}')
        if v is None: continue
        if k == 'surface' and v == 'desk': q.append("IFNULL(Surface,'desk')='desk'"); continue
        q.append(f'LOWER(IFNULL({_FIELDS[k]},\'\'))=?'); p.append(str(v).lower())
    sql = f"SELECT * FROM advice_press WHERE {' AND '.join(q)} ORDER BY Id" + (f' LIMIT {int(limit)}' if limit else '')
    return [_row(r) for r in store._rows(sql, tuple(p))]


def instructions(store, to: str = None, domain: str = None, since: str = None) -> list:
    """THE OWNER'S WORDS FOR DRAFTS, kept on each review (review.Instructions): [{rid, tid, mid, to, domain, text, at}], oldest first -
    to whom the reply was going, so the second time the same is said to the same person can become a style line (phase C). Narrow by
    `to` (an address) or `domain`."""
    out = []
    for r in store._rows("SELECT ReviewId, TaskId, MessageId, Deliver, Instructions FROM review WHERE IFNULL(Instructions,'')<>'' ORDER BY ReviewId"):
        try: said = json.loads(r['Instructions'] or '[]') or []
        except ValueError: continue
        m = store.get_message(int(r['MessageId'])) if r.get('MessageId') else None
        try: d = json.loads(r.get('Deliver') or '{}') or {}
        except ValueError: d = {}
        who = str((m or {}).get('FromEmail') or next(iter(d.get('to') or []), '') or '').lower()
        if personal(store, None, m): continue
        dom = who.rsplit('@', 1)[1] if '@' in who else ''
        if (to and who != to.lower()) or (domain and dom != domain.lower()): continue
        out += [{'rid': r['ReviewId'], 'tid': r.get('TaskId'), 'mid': r.get('MessageId'), 'to': who, 'domain': dom, 'text': s.get('text') or '',
                 'at': s.get('at') or ''} for s in said if (s.get('text') or '').strip() and (not since or str(s.get('at') or '') >= since)]
    return sorted(out, key=lambda x: x['at'])
