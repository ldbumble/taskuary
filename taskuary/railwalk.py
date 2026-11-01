"""THE WALK HAS ONE OWNER (docs/superpowers/specs/2026-10-30-walk-one-owner-design.md). Next, Back, a row opened and every close decide
"what is on the table now" here and nowhere else: the page sends an action, draws the Answer that comes back, and remembers only which
row is on its table. Five places used to decide it and disagreed - a Send that skipped a task, a Back that read an FYI batch, a walk
opened out of order that never reached the rows above it (the owner, 2026-10-30). `walk.py` is the scripted setup tour; this is the rail's.

THE SEVEN RULES (the owner, 2026-10-30, final):
  1 the rail order is fixed - Tasks, Reports, FYI, oldest first by arrival (funnel.order_key); rows never move
  2 Next is the row directly below the one on screen, a clicked row included
  3 Back is the row directly above, greyed at the top; Back never reads or passes anything
  4 Next on a task leaves it on the rail; Next on a report, an idea, an FYI or an agent's finished task reads it and it leaves; opening never reads
  5 Mark done, Close with a note, a Send that closes, Remind me and Not a task close the row AND move to the row that was below it, in one step
  6 never skip: there is no hidden "passed" and no "seen in this walk"
  7 the next item draws at once - `peek` is the same answer `next` gives, built by the same function
The walk starts at the TOP of the rail.

The concierge still words the row (present_turn) and operations still run the closes: this decides WHICH row and WHICH effect."""
import builtins
import hashlib
import json
import threading
import time
from collections import OrderedDict
from datetime import datetime

from loguru import logger

from . import funnel, lanes

KEY = 'rail_walk'
LEGACY_KEYS = ('walk_place', 'walk_started_at')        # what this replaced (2026-10-30): read through once, then cleared
PLACES = 64                                           # rows whose place is kept after they leave the rail (a retry, a double press)
PRESSES = 32
_LOCK = threading.RLock()
_first = builtins.next                                # `next` below is the walk's Next
_PRESSES = OrderedDict()                              # press id -> the Answer it got: a repeated press is that answer, no second line


# ── the line ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def line(items: list) -> list:
    """The rows the walk stands on, in the rail's own drawing order: everything the rail draws but For later (rows Remind me put away,
    rule 5) and rows still being triaged. Nothing else filters it - if the rail draws a row, the walk can stand on it."""
    return sorted((r for r in items or () if not r.get('settling') and lanes.level_of(r) != 'later'), key=funnel.order_key)


def _rows(store) -> list:
    """The rail as last built - the cached pile, the same one /api/funnel/pile serves; built only when something moved since. ...Or the
    line a walk move left in hand (_hold), while nothing but that move has written: a Next's own writes (the read, the badge, its line in
    the chat, the walk's place) emptied the pile's cache, and the next press rebuilt the whole rail for them - 0.5-0.7 s a press on a
    real home of 5,600 rows, twice a Next (2026-10-31). Spec 7.3: the walk reads the rail, it never builds it."""
    # ...and no older than the pile's own cache may be: a Later row comes due with nothing written
    if _HAND.get('store') is store and _HAND.get('mark') is not None and time.time() - _HAND['at'] < funnel.PILE_EVERY             and _mark(store) == _HAND['mark']: return list(_HAND['rows'])
    return list(funnel.pile(store)['items'])


_HAND = {}


def _mark(store):
    """Everything that moves the rail: a write anywhere (the store's dirty-row top) and the live workers (funnel.pile's own two checks)."""
    from . import terminal
    try: workers = funnel.workers_signature(terminal.live_sessions(tail=6))
    except Exception: workers = None
    top = funnel._rail_top(store)
    return None if top is None or workers is None else (top, workers)


def _hold(store, rows):
    """The rows a move computed with its own effect applied, held as the rail until anything else writes - taken after the move's last
    write, so its own writes do not count against it."""
    _HAND.update(store=store, rows=list(rows), mark=_mark(store), at=time.time())


def _is(row: dict, key: str) -> bool: return bool(key) and (row.get('key') == key or key in (row.get('aliases') or ()))


def find(rows, key):
    return _first((r for r in rows or () if _is(r, key)), None)


def members_of(key: str) -> list:
    return [k for k in str(key)[5:].split(',') if k] if str(key or '').startswith('fyis:') else [key] if key else []


def batchable(row: dict) -> bool:
    """Read in an FYI batch: a plain FYI row. An idea is its own section and always walked alone (funnel.batchable)."""
    return lanes.level_of(row) == 'fyi' and funnel.batchable(row)


def kind_of(row: dict | None) -> str:
    """The effect Next has on a row, taken from its section WHEN IT WAS PUT ON SCREEN (3.5): `stays` under Tasks, `reads` under Reports,
    Advisor ideas and FYI (an agent's finished task included), `none` for a For later row or a closed task opened by name."""
    if not row: return 'none'
    if row.get('kind') in ('agentdone', 'fyis'): return 'reads'
    level = lanes.level_of(row)
    if row.get('closed') and level == 'task': return 'none'
    return 'stays' if level == 'task' else 'none' if level == 'later' else 'reads'


def _arrival(store, item: dict):
    """A task opened by name that is not on the rail is placed under Tasks by its arrival (funnelPile.pulledRow is the page's mirror)."""
    tid = item.get('tid')
    if not tid: return item.get('arrived_at')
    t = store.get_task(int(tid)) or {}
    msgs = store.list_messages(int(tid)) if hasattr(store, 'list_messages') else []
    stamps = [x for x in (t.get('CreatedAt'), *(m.get('SentAt') for m in msgs[:1])) if x]
    return min(stamps, key=lambda s: funnel._activity_time(s) or funnel.datetime.max) if stamps else item.get('arrived_at')


def _ok(row: dict) -> list: return list(funnel.order_key(row))


def _tuple(at): return tuple(at) if at is not None else None


def place_of(store, key: str, st: dict = None, rows: list = None):
    """(first, last) - where a row sits on the line, as order keys. A row not on the rail still has a place: the row on screen keeps the
    one it was put up at, a row the walk stood on lately keeps its own, and a task opened by name is placed by its arrival under Tasks."""
    st = st if st is not None else state(store)
    rows = rows if rows is not None else _rows(store)
    if not key: return None
    if str(key).startswith('fyis:'):
        got = [p for p in (place_of(store, k, st, rows) for k in members_of(key)) if p]
        if got: return (min(p[0] for p in got), max(p[1] for p in got))
    # the row on screen keeps the place it was put up at, even where it has moved since: closed by its agent into Reports, made a task by
    # Put it on my list, a task's mail filed as FYI by Not a task - Next goes on from where the walk stood (5: "a row changes section")
    if st.get('on') and (key == st['on'] or key in (st.get('members') or ())) and st.get('first'):
        return (_tuple(st['first']), _tuple(st['last']))
    r = find(rows, key)
    if r is not None: return (funnel.order_key(r),) * 2
    if key in (st.get('places') or {}): return tuple(_tuple(x) for x in st['places'][key])
    it = _lookup(store, key)
    if not it: return None
    if it.get('tid') and not find(rows, it.get('key')):
        it = {**it, 'order_band': 2, 'deferred': False, 'arrived_at': _arrival(store, it)}
    return (funnel.order_key(it),) * 2


def _lookup(store, key: str) -> dict | None:
    """The item a key names, read or not, on the rail or not - never the whole rail rebuilt for it (funnel.next_item's keyed build)."""
    if str(key).startswith('fyis:'): return funnel.batch_item(store, key)
    try: return funnel.next_item(store, key, include_surfaced=True) or funnel.item_for_key(store, key)
    except Exception as e:
        logger.debug(f'railwalk: {key} could not be looked up - {e}'); return None


def _below(ln: list, place, skip=()) -> int | None:
    return _first((n for n, r in enumerate(ln) if funnel.order_key(r) > place and not any(_is(r, k) for k in skip)), None)


def _above(ln: list, place, inclusive: bool = False) -> int | None:
    hits = [n for n, r in enumerate(ln) if (funnel.order_key(r) <= place if inclusive else funnel.order_key(r) < place)]
    return hits[-1] if hits else None


def _batch(store, ln: list, n: int, down: bool) -> list:
    """The rows put up together from ln[n]: FYI reads a handful at once (3.2). Down from it on Next, up from it on Back - so Back-then-Next
    lands on the batch it came back from. Never across a section's edge; an idea is always alone."""
    if not batchable(ln[n]): return [ln[n]]
    size, out, step = funnel.fyi_batch_size(store), [ln[n]], 1 if down else -1
    j = n + step
    while len(out) < size and 0 <= j < len(ln) and batchable(ln[j]):
        out.append(ln[j]); j += step
    return out if down else out[::-1]


def as_item(store, rows: list) -> dict:
    """One row as itself; a handful of FYI as ONE item (funnel.batch_item's shape), so words said about it land on something."""
    if len(rows) == 1: return funnel._present_one(store, rows[0])
    key = 'fyis:' + ','.join(r['key'] for r in rows)
    return funnel._present_one(store, funnel._item(key, 'fyis', 'fyi', f"{len(rows)} fyi", who='', when=rows[0].get('when'),
                                                   since=rows[0].get('since'), channel=rows[0].get('channel'),
                                                   why='people told you things; nothing to do', items=[dict(r) for r in rows],
                                                   members=[r['key'] for r in rows]))


# ── the state ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _blank() -> dict: return {'v': 1, 'on': None, 'members': [], 'first': None, 'last': None, 'kind': 'none', 'ended': False, 'places': {}}


def state(store) -> dict:
    """The one walk (3.3), shared by the desk and the phone (Q5): the row on screen, kept even after that row has left the rail."""
    try: st = json.loads(store.get_setting(KEY) or 'null')
    except (ValueError, TypeError): st = None
    if not isinstance(st, dict) or st.get('v') != 1:
        st = _blank()
        # ...the table the old walk left (concierge's assistant_current:<dock>), read through once: a restart onto this build keeps it
        try:
            from . import general
            dock = general.dock_task(store, 'owner')[0]['TaskId']
            old = str(store.get_setting(f'assistant_current:{dock}') or '')
            if old: st['on'], st['members'], st['_legacy'] = old, members_of(old), dock
        except Exception as e: logger.debug(f'railwalk: no old table to read through - {e}')
    return st


def _write(store, st: dict):
    dock = st.pop('_legacy', None)
    if dock is not None:                              # the old table, read through once: its settings go with this first write
        for k in (f'assistant_current:{dock}', f'assistant_current_closed:{dock}'): store.set_setting(k, '', 'system')
    places = st.get('places') or {}
    if len(places) > PLACES: st['places'] = dict(list(places.items())[-PLACES:])
    store.set_setting(KEY, json.dumps(st, default=str), 'system')
    for k in LEGACY_KEYS:
        if store.get_setting(k): store.set_setting(k, '', 'system')


def on(store) -> str: return str(state(store).get('on') or '')


def _put(st: dict, item: dict, rows: list, place=None):
    """`item` on screen at its place: Next measures from its last member, Back from its first; its effect class as it is now (3.5)."""
    keys = members_of(item['key']) if item.get('kind') == 'fyis' else [item['key']]
    first, last = place or ((funnel.order_key(find(rows, keys[0]) or item), funnel.order_key(find(rows, keys[-1]) or item)))
    st.update(on=item['key'], members=keys, first=list(first), last=list(last), ended=False,
              kind='reads' if item.get('kind') == 'fyis' else kind_of(find(rows, item['key']) or item))
    places = st.setdefault('places', {})
    for k in {item['key'], *keys, *(item.get('aliases') or ())}:
        places.pop(k, None); places[k] = [list(first), list(last)]


# ── answers ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def answer_hash(out: dict) -> str:
    """What an Answer puts on the screen: the prepared one (peek) and the committed one are compared by it (rule 7)."""
    item = out.get('item') or {}
    shown = {'key': item.get('key'), 'say': out.get('say'), 'chips': out.get('chips'), 'options': out.get('options'), 'over': out.get('over')}
    return hashlib.sha256(json.dumps(shown, sort_keys=True, default=str).encode()).hexdigest()


def _walk(store, st: dict, rows: list) -> dict:
    ln = line(rows)
    first = _tuple(st.get('first'))
    if st.get('ended') and st.get('last'):
        n = _above(ln, _tuple(st['last']), inclusive=True)
    else: n = _above(ln, first) if first else None
    return {'on': st.get('on'), 'members': st.get('members') or [], 'ended': bool(st.get('ended')),
            'above': (as_key(store, ln, n, down=False) if n is not None else None)}


def as_key(store, ln, n, down=True) -> str:
    rows = _batch(store, ln, n, down)
    return rows[0]['key'] if len(rows) == 1 else 'fyis:' + ','.join(r['key'] for r in rows)


def _answer(store, st, rows, out: dict) -> dict:
    """The move's Answer, its `rows` the rail with the move's own effect in it: held (_hold) for the next move, so the move's own writes -
    made by now, `out` included - never cost the next press a rebuild."""
    _hold(store, rows)
    out = {**out, 'walk': _walk(store, st, rows)}
    out['answer_hash'] = answer_hash(out)
    return out


def _dock(store, actor):
    from . import general
    return general.dock_task(store, actor)[0]['TaskId']


def _present(store, item, actor, *, picked, record=True, llm=None, rows=None):
    from . import concierge
    return concierge.present_turn(store, item, actor=actor, picked=picked, record=record, llm=llm, left=max(0, len(line(rows or [])) - len(item.get('members') or [item.get('key')])))   # how many besides this one


def _end(store, st, rows, actor, record=True):
    from . import concierge
    return concierge.end_turn(store, line(rows), actor=actor, write=record)


def _remember(press, out):
    if not press: return out
    _PRESSES[press] = out
    while len(_PRESSES) > PRESSES: _PRESSES.popitem(last=False)
    return out


def _again(press):
    return _PRESSES.get(press) if press else None


# ── the calls ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def start(store, actor: str = 'owner', press: str = None, llm=None) -> dict:
    """The Walk button, words asking for a walk, a walk again: the TOP row of the line on screen (a batch when it is FYI). Reads nothing."""
    with _LOCK:
        if (hit := _again(press)): return hit
        st, rows = _blank(), _rows(store)
        st['started'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')     # which walk this is: the phone names an urgent arrival once a walk
        ln = line(rows)
        if not ln:
            st.update(ended=True); _write(store, st)
            return _remember(press, _answer(store, st, rows, _end(store, st, rows, actor)))
        item = as_item(store, _batch(store, ln, 0, True))
        _put(st, item, rows)
        _write(store, st)
        return _remember(press, _answer(store, st, rows, _present(store, item, actor, picked=False, llm=llm, rows=rows)))


def reset(store):
    """A new chat: the old table is forgotten and nothing is put up (the Walk button starts at the top). Read stays read."""
    with _LOCK: _write(store, _blank())


def _effect(store, st, rows, frm, actor, dock):
    """Next's effect on the row it leaves (3.5): `reads` reads every member still on the rail - it leaves; `stays` writes nothing but the
    "Next" badge; `none` nothing at all. A row no longer there is not read. Returns the rail keys it read."""
    from . import concierge
    if not frm: return []
    held = frm == st.get('on') or frm in (st.get('members') or ())
    keys = (st.get('members') or members_of(frm)) if held else members_of(frm)
    kind = st.get('kind') if held else kind_of(find(rows, frm))
    read = []
    if kind == 'reads':
        with store.one_poke() if hasattr(store, 'one_poke') else _null():
            for k in keys:
                row = find(rows, k)
                if row is None: continue
                try: funnel.settle(store, row['key'], 'surfaced', actor, note=row.get('sig'), read=True); read.append(row['key'])
                except Exception as e: logger.debug(f'railwalk: {k} was not read - {e}')
    try: concierge._stamp_next(store, dock, st.get('on') if held else frm)
    except Exception as e: logger.debug(f'railwalk: no badge for {frm} - {e}')
    return read


class _null:
    def __enter__(self): return self
    def __exit__(self, *a): return False


def next(store, from_key: str = None, actor: str = 'owner', press: str = None, read=(), llm=None, effect: bool = True) -> dict:
    """The row directly below the one the page had on screen (`from_key`; with none, the stored one), after the effect of leaving it.
    A key no longer on the rail still resolves - through the stored place. At the bottom: item None, ended. Pressed again there with nothing
    new below, the same end answer and no new line. `read`: rows the owner was reading on a page over the table (the Reports page, 2026-10-30)."""
    with _LOCK:
        if (hit := _again(press)): return hit
        st, rows = state(store), _rows(store)
        frm = from_key or st.get('on')
        if not frm and not st.get('ended'):
            out = start(store, actor, llm=llm)
            return _remember(press, out)
        place = (_tuple(st.get('first')), _tuple(st.get('last'))) if not frm else place_of(store, frm, st, rows)
        if place is None or place[1] is None:
            logger.debug(f'railwalk: {frm} has no place - the walk starts at the top')
            return _remember(press, start(store, actor, llm=llm))
        dock = _dock(store, actor)
        gone = _effect(store, st, rows, frm, actor, dock) if effect and frm else []
        for k in read or ():
            row = find(rows, k)
            if row is not None:
                try: funnel.settle(store, row['key'], 'surfaced', actor, read=True); gone.append(row['key'])
                except Exception as e: logger.debug(f'railwalk: {k} on the page over the table was not read - {e}')
        # ...what was read has left the rail: taken off the rows in hand, never the whole rail rebuilt to see it gone
        if gone: rows = [r for r in rows if r['key'] not in set(gone)]
        ln = line(rows)
        n = _below(ln, place[1], skip=members_of(frm))
        if n is None:
            was_end = st.get('ended') and not frm
            st.update(ended=True, on=None, members=[], first=list(place[0]), last=list(place[1]), kind='none')
            _write(store, st)
            return _remember(press, _answer(store, st, rows, _end(store, st, rows, actor, record=not was_end)))
        item = as_item(store, _batch(store, ln, n, True))
        _put(st, item, rows)
        _write(store, st)
        return _remember(press, _answer(store, st, rows, _present(store, item, actor, picked=False, llm=llm, rows=rows)))


def back(store, from_key: str = None, actor: str = 'owner', press: str = None) -> dict:
    """The row directly above the one on screen, even when the walk did not start at the top. Writes nothing but the walk's own place:
    no read, no mark, no badge (rule 3; the owner, 2026-10-30: "if you click back it's not read only next"). At the top, nothing moves."""
    with _LOCK:
        if (hit := _again(press)): return hit
        st, rows = state(store), _rows(store)
        frm = from_key or st.get('on')
        ln = line(rows)
        if not frm and st.get('ended') and st.get('last'): n = _above(ln, _tuple(st['last']), inclusive=True)
        else:
            place = place_of(store, frm, st, rows) if frm else None
            n = _above(ln, place[0]) if place else None
        if n is None:
            return _remember(press, _answer(store, st, rows, {'item': None, 'say': '', 'options': [], 'chips': [], 'top': True}))
        item = as_item(store, _batch(store, ln, n, False))
        _put(st, item, rows)
        _write(store, st)
        return _remember(press, _answer(store, st, rows, _present(store, item, actor, picked=True, rows=rows)))


def open(store, key: str, actor: str = 'owner', press: str = None, llm=None, at: str = None, record: bool = True) -> dict:
    """A rail click, a name, a link, a section heading (its first row), the Board's open, a search hit: that row on screen at its place.
    Reads nothing (rule 4) - but a task opened clears its "+N" (Q1): what landed on it has now been seen; it stays where it is.
    `at`: the row whose place it takes - Put it on my list keeps the new task on the table, and Next and Back go on from the report's
    place (3.5, W49). `record=False`: the row put on screen with no line in the chat - the caller words it (concierge.set_current)."""
    with _LOCK:
        if (hit := _again(press)): return hit
        st, rows = state(store), _rows(store)
        row = find(rows, key)
        item = as_item(store, [row]) if row is not None else _lookup(store, key)
        if not item:
            from . import concierge
            return _remember(press, _answer(store, st, rows, concierge.missing_turn(store, key, actor)))
        if row is not None and lanes.level_of(row) in ('task', 'later'):
            try: funnel.settle(store, row['key'], 'surfaced', actor, note=row.get('sig'), read=True)
            except Exception as e: logger.debug(f'railwalk: the +N on {key} was not cleared - {e}')
        place = place_of(store, at, st, rows) if at else place_of(store, item['key'], st, rows) if row is None else None
        _put(st, item, rows, place=place)
        if row is None and item.get('tid') and kind_of(item) != 'reads': st['kind'] = 'none'
        _write(store, st)
        return _remember(press, _answer(store, st, rows, _present(store, item, actor, picked=True, llm=llm, rows=rows, record=record)))


def top(store) -> dict | None:
    """The row a walk starts on, as an item - read only: what `start` would put up, with nothing written."""
    ln = line(_rows(store))
    return as_item(store, _batch(store, ln, 0, True)) if ln else None


def section(store, level: str, actor: str = 'owner', press: str = None) -> dict:
    """A section heading clicked: its first row, and Next walks on down the rail past the section's end (Q6: no "Reports done." stop)."""
    rows = _rows(store)
    first = next_in(line(rows) if level != 'later' else rows, level)
    if not first: return {'item': None, 'say': '', 'options': [], 'chips': [], 'walk': _walk(store, state(store), rows)}
    return open(store, first['key'], actor, press)


def next_in(rows, level):
    for r in rows:
        if lanes.level_of(r) == level and not r.get('settling'): return r
    return None


HOW = {'done': 'task.complete', 'note': 'task.complete', 'remind': 'task.defer', 'not_task': 'task.not_a_task', 'not_ours': 'message.file',
       'removed': 'task.not_a_task', 'put_on_list': 'task.create_from_message'}


def _badge(store, op, actor):
    """The press worn on its card, from the server, so a reload draws it - what the operations road the buttons took before did
    (concierge.receipt_turn, press=True): a close made through the walk went past it, and Mark done folded bare (2026-10-31)."""
    if not op: return
    from . import concierge, live as live_bus
    try: concierge.receipt_turn(store, op, actor, table=True, press=True); live_bus.emit(live_bus.CHAT)
    except Exception as e: logger.debug(f'railwalk: no badge for {op.get("id")} - {e}')


def _act(store, item: dict, how: str, actor: str, note: str = None, until: str = None) -> dict:
    """The act `how` names, through the existing operation (3.6) - the same road the page's buttons take, so the demo runs it locally."""
    from . import concierge, operations
    if how == 'sent':
        if not item.get('tid'): return {'closed': False}
        out = concierge.close_after_send(store, int(item['tid']), actor)
        return {'closed': out.get('status') in ('done', 'dropped'), 'kept': out.get('kept_open')}
    if how in ('all_read', 'next'): return {'closed': True, 'read': True}
    # ...the act ran on its own road already (the task page's write-up, a hand-off, a fold, a typed put-down, a proposal): only the move,
    # and the row closed exactly when it has left the line - so a kept-open row is re-presented, never walked past
    if how == 'left': return {'closed': not find(line(_rows(store)), item['key'])}
    # ...a card's own Done (an FYI batch's All read, a reply sent from its card): the row settled, nothing behind it closed
    if how == 'settle': funnel.settle(store, item['key'], 'done', actor); return {'closed': True}
    # ...Remind me through the picker's own road (remind.set_reminder): its agent-open refusal and its receipt stay the same
    if how == 'remind' and item.get('tid'):
        from . import remind
        out = remind.set_reminder(store, int(item['tid']), until, actor)
        _badge(store, operations.record_direct(store, 'task.defer', int(item['tid']), {'until': until or 'none'}, actor, out), actor)
        return {'closed': True, 'outcome': out}
    if how == 'done' and item.get('kind') in ('agentdone', 'report', 'fyis') or (how == 'done' and not item.get('tid')):
        funnel.settle(store, item['key'], 'done', actor); return {'closed': True}
    kind = HOW.get(how)
    if not kind: raise ValueError(f'unknown leave: {how}')
    target = item.get('mid') if kind in ('message.file', 'task.create_from_message') else item.get('tid')
    if not target:
        funnel.settle(store, item['key'], 'done', actor); return {'closed': True}
    t = store.get_task(int(target)) if kind.startswith('task.') and kind != 'task.create_from_message' else None
    if t and t.get('Status') in ('done', 'dropped') and how != 'remind': return {'closed': True, 'already': True}
    params = ({'note': note} if note else {}) if kind == 'task.complete' else {'until': until} if kind == 'task.defer' \
        else {'learn': False} if kind == 'message.file' else {'kind': 'task'} if kind == 'task.create_from_message' else {}
    done = concierge.run_proposal(store, operations.propose(store, kind, int(target), params, actor), actor)
    if done.get('status') != 'done': raise RuntimeError(done.get('error') or f'{kind} did not run')
    if how != 'put_on_list': _badge(store, done, actor)
    o = done.get('outcome') or done.get('result') or {}
    return {'closed': how != 'put_on_list', 'made': o.get('taskId') or o.get('task_id') or o.get('tid'), 'outcome': o}


def leave(store, key: str, how: str, actor: str = 'owner', press: str = None, note: str = None, until: str = None) -> dict:
    """Mark done, Close with a note, a Send that closes, Remind me, Not a task, Not ours, Remove on the row on screen: the act, and IN THE
    SAME CALL the row that was directly below it (rule 5). An act that did not close it - a Send that kept the task open - leaves the same
    row on screen, re-presented. Put it on my list keeps the new task on the table; Next and Back still measure from the report's place."""
    with _LOCK:
        if (hit := _again(press)): return hit
        st, rows = state(store), _rows(store)
        item = find(rows, key)
        item = as_item(store, [item]) if item is not None else _lookup(store, key)
        if not item: raise LookupError(f'nothing to leave: {key}')
        place = place_of(store, key, st, rows)
        if how in ('all_read', 'next'): return _remember(press, next(store, key, actor))
        done = _act(store, item, how, actor, note, until)
        # ...the rail as the act left it, built once: an act that ran elsewhere ('left') was read on its own rows already
        if how != 'left': funnel.invalidate()
        rows = _rows(store)
        if how == 'put_on_list' and done.get('made'):
            made = _lookup(store, f"task:{int(done['made'])}")
            if made:
                _put(st, made, rows, place=place); st['kind'] = 'none'; _write(store, st)
                return _remember(press, _answer(store, st, rows, _present(store, made, actor, picked=True, rows=rows)))
        if not done.get('closed'):
            fresh = _lookup(store, key) or item
            _put(st, fresh, rows, place=place); _write(store, st)
            return _remember(press, _answer(store, st, rows, {**_present(store, fresh, actor, picked=True, record=False, rows=rows), 'kept': done.get('kept') or []}))
        st.update(on=key, members=members_of(key), first=list(place[0]), last=list(place[1]))
        _write(store, st)
        _hold(store, rows)                            # ...and Next below goes on from that same rail, never a second build of it
        # ...with what the act said (a removed task's Undo line, a reminder's warning) riding along for the page to draw
        return _remember(press, {**next(store, key, actor, effect=False), **({'left': done['outcome']} if done.get('outcome') else {})})


def peek(store, actor: str = 'owner') -> dict:
    """Pure: {on, ended, below, above} for the row on screen - `below` the key `next` would bring, `above` the key `back` would. Keys,
    never Answers: the page draws only what a move answers, and reads these to grey Back and Next (one pass over the line, spec 7.3)."""
    with _LOCK:
        st, rows = state(store), _rows(store)
        walk, ln = _walk(store, st, rows), line(rows)
        if st.get('on') or st.get('ended'):
            last = _tuple(st.get('last'))
            n = (0 if ln else None) if last is None else _below(ln, last, skip=st.get('members') or ())
        else: n = 0 if ln else None
        return {**walk, 'below': as_key(store, ln, n) if n is not None else None}
