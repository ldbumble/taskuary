"""NOTHING FALLS THROUGH: the person nobody answered. No model - every fact here is already in the store.

The point of the app is that nothing is lost between the contexts it holds, and a hole stayed open:

- A PERSON'S ASK NOBODY ANSWERED (aged_asks). Their mail asked something (triage's own verdict), no task came of it, nothing of the
  owner's went back, and nobody ruled on it - and once it aged off the rail (unread for funnel_hours, history for feed_days) it
  was simply gone.
  Past AGED_DAYS it comes back as an ordinary row under On you, the way the Advisor's finds land: an idea whose verdict is the
  mail's own, so no model reads it again. A sender that is not a person (automated, bulk, a notice) is never raised.
It is said once per set of facts (the idea's Sig): not again tomorrow for the same ask unless it changed, and never again
after the owner put it down, until it changes.
"""
import json
from datetime import datetime
from loguru import logger

from . import lanes, words

SWEPT_KEY = 'loose_ends_swept'
AGED_DAYS = 5              # a person's ask unanswered this long, with nothing deciding it, is raised
LOOKBACK_DAYS = 120        # how far back the aged asks are read - past the rail's own window on purpose
ASK = 'unanswered'
SAY = words.LOOSE


def _ts(s): return str(s or '')[:19].replace('T', ' ')
def _action(i):
    try: return json.loads(i.get('ActionJson') or '{}') or {}
    except (TypeError, ValueError): return {}


# ── the aged ask ──────────────────────────────────────────────────────────────────────────────

def _ruled(store, mid: int, states: dict) -> bool:
    """Did the owner decide anything about this mail? A draft decided (sent, no reply, rejected), a Done / Remind me on its row,
    or an Advisor line about it put down - each is a ruling, and a ruled ask is not one that slipped."""
    if store._one("SELECT 1 x FROM review WHERE MessageId=? LIMIT 1", (mid,)): return True       # a draft at all: waiting or decided
    keys = [f'msg:{mid}']
    row = store._one("SELECT ItemId FROM processing_member WHERE EntityKind='message' AND LocalId=? AND RetiredAt IS NULL", (str(mid),))
    if row: keys.append(f"processing:{row['ItemId']}")
    if any((states.get(k) or {}).get('Status') in ('done', 'later', 'skip') for k in keys): return True
    return any(_action(i).get('mid') == mid and i.get('Status') in ('dismissed', 'done') for i in store.list_ideas())


def aged_asks(store, now: datetime = None, shown: set = frozenset()) -> list:
    """The asks past their day: [{key, kind, text, sig, action}] - the Advisor's candidate shape. `shown` is the mail already on
    the rail as the owner's move: raising it again would be the same ask twice."""
    from .assistant import their_asks
    days = max(1, int(store.get_setting('aged_ask_days', AGED_DAYS) or AGED_DAYS))
    asks, _ = their_asks(store, days=LOOKBACK_DAYS, hours=days * 24)
    states, out = store.funnel_states(), []
    said = {i['Key']: i for i in store.list_ideas()}
    for a in asks:
        act, cid = a.get('action') or {}, a['key'].split(':', 1)[1]
        mid = act.get('mid')
        m = store.get_message(mid) if mid else None
        # no task (theirs_asks reads the thread's), no draft, nothing decided, not on the rail already, not the Advisor's line already
        if not m or act.get('tid') or m.get('TaskId') or mid in shown or _ruled(store, mid, states): continue
        if (said.get(f'asked:{cid}') or {}).get('Status') == 'open': continue
        v = store.message_verdict(mid) or {}
        out.append({'key': f'{ASK}:{cid}', 'kind': ASK, 'sig': _ts(m.get('SentAt')),
                    'text': SAY['unanswered'].format(who=a['who'], gist=a['gist'], ago=a['ago']),
                    'action': {'type': 'message', 'mid': mid, 'tid': None, 'who': a['who'], 'by': 'sweep',
                               'why': SAY['unanswered_why'].format(days=days),
                               # its verdict is the MAIL's own, already reached: no model reads it again, and the rail draws it
                               # as an ask (processing_all.idea_lane) under On you
                               'triage': {'intent': v.get('intent'), 'kind': v.get('kind'), 'why': str(v.get('why') or '')[:200],
                                          'sig': _ts(m.get('SentAt')), 'at': (now or datetime.now()).strftime('%Y-%m-%d %H:%M:%S'),
                                          'linked_task': None, 'error': None, 'by': 'sweep'}}})
    return out


# ── the check ─────────────────────────────────────────────────────────────────────────────────

def _say_once(store, cands: list, stamp: str) -> list:
    """Upsert each candidate whose facts are new: never said, or said with another Sig. The same facts are not said again - not
    tomorrow, and not after the owner put the line down."""
    old, said = {i['Key']: i for i in store.list_ideas()}, []
    for c in cands:
        i = old.get(c['key'])
        if i and (i.get('Sig') or '') == c['sig']: continue
        said.append(store.upsert_idea(c, stamp))
    return said


def run(store, now: datetime = None) -> dict:
    """The check, now: raise what fell through, put down what has since been answered. Returns {'asks', 'said', 'cleared'}."""
    now = now or datetime.now()
    stamp = now.strftime('%Y-%m-%d %H:%M:%S')
    from . import processing_unread
    canonical = store.processing_reads_active()
    if canonical: store.reconcile_processing_membership()      # the rail as it stands now, not as the last settle left it
    # the rail as the owner has it, read rows too: what is already on it as their move is not raised twice
    cards = processing_unread.build(store, now=now, include_read=True)['items'] if canonical else []
    shown = set()
    for c in cards:
        # ...the mail's own row, never this check's line about it: that one is the ask said, not the ask seen
        if c.get('unread') and lanes.on_you(c) and c.get('mid') and c.get('idea_kind') != ASK: shown.add(c['mid'])
    asks = aged_asks(store, now, shown)
    said = _say_once(store, asks, stamp)
    # ...and a line whose ask was answered, tasked or ruled since, is put down
    want, cleared = {c['key'] for c in asks}, 0
    for i in store.list_ideas('open'):
        if i.get('Kind') == ASK and i['Key'] not in want:
            store.set_idea_status(i['IdeaId'], 'done', 'sweep'); cleared += 1
    if said or cleared:
        from . import funnel
        funnel.invalidate()
    logger.info(f'sweep: {len(asks)} aged ask(s); {len(said)} said, {cleared} put down')
    return {'asks': len(asks), 'said': len(said), 'cleared': cleared}


def run_if_due(store, now: datetime = None):
    """Once a day, from the poll's housekeeping beside the outcome sweep: None when today's check already ran."""
    now = now or datetime.now(); today = now.strftime('%Y-%m-%d')
    if store.get_setting(SWEPT_KEY, '') == today: return None
    out = run(store, now)
    store.set_setting(SWEPT_KEY, today, 'sweep')
    return out
