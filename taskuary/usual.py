"""THE OWNER'S OWN USUAL, COUNTED FROM WHAT THEY DID (slice 4 of the memory redesign, 2026-10-25).

The Advisor says a line only for a checkable fact the card does not show (the owner's ruling 1, 2026-10-23), and now that includes what
the memory knows about how the owner works - kept to ONE line on the strip (the owner, 2026-10-25: "Reply: you usually answer Erin within
the hour; this is 3h"). Each fact here is counted from the owner's own acts, the same rows the episodes are written from (episodes.py),
and cited by the same ids, so Why? can show what it rests on:

    reply_lag    how soon the owner answers this person: the median of their last answers (msg ids, the asks they answered)
    late_reply   that usual, against how long THIS ask has waited - only when it has waited well past it
    put_off_habits  the weekday the owner puts a sender's mail off to - fs ids, the tasks put off. The count writes or confirms a How
                 you work line through the reflection (learn.put_off_lines), and it is THAT line Remind me reads (remind_day): the owner
                 can see it and correct it, and the default follows (the owner, 2026-10-25: "Remind me's learned day comes from a How you
                 work line ... the owner can see and correct")
    handed_to    whom the owner handed this sender's asks to - evidence the model weighs (a topic is the model's to read, never a
                 count's), never a button lit by a count; Hand it to a person opens with that person chosen, not sent (handoff_usual)
    chase_usual  the day a silence is late for this person (ruling 8: after 3 working days, then learned per person), from the ledger

Times, addresses and weekdays are facts, not meaning: nothing here reads a mail's words. Fewer than three answers (or two put-offs) is
no habit, and says nothing."""
import json, math, re
from collections import Counter
from datetime import datetime, timedelta
from .episodes import _dt, _mine, _skip

ANSWERS, PUT_OFFS = 3, 2            # what makes a habit: three answers, two put-offs to one weekday
IN_USE = 3                          # ...and a put-off line is in use at three of them: the ladder every line climbs (three episodes)
LATE_X, LATE_MIN = 2, 60            # late is twice the usual, and an hour at least - "you usually answer in 10 min; this is 25" is noise
LOOK_DAYS, REPLY_DAYS, KEEP = 90, 7, 10
HELD_DAYS = 14                      # the owner's ruling 7: the learned day only after about two weeks of data
DAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')


def _ago(days: int, now=None) -> str: return ((now or datetime.now()) - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
def _first(name: str, email: str) -> str: return (' '.join(str(name or '').split()).split(' ') or [''])[0] or str(email or '').split('@')[0]
def median(xs: list): xs = sorted(xs); n = len(xs); return None if not n else xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def span(m: float) -> str:
    """Minutes in the words a person uses: '25 min', '3h', '2 days'."""
    m = int(m)
    return f'{m} min' if m < 90 else f'{round(m / 60)}h' if m < 36 * 60 else f'{round(m / 1440)} days'


def days(d: float) -> str: return 'a day' if d <= 1 else f'{round(d)} days'


def within(m: float) -> str:
    """A usual answer time as a promise of speed: 'within the hour', 'within 3h', 'within a day', 'within 2 days'."""
    return ('within the hour' if m <= 60 else f'within {math.ceil(m / 60)}h' if m < 20 * 60 else 'within a day' if m <= 30 * 60
            else f'within {math.ceil(m / 1440)} days')


def reply_lag(store, who: str, now=None, skip=()) -> dict:
    """{n, minutes, evidence}: how soon the owner answered `who`'s last asks - each ask's first answer of the owner's on its own thread
    within REPLY_DAYS, newest KEEP. `skip`: message ids not to count (the ask being judged)."""
    who = str(who or '').strip().lower()
    if '@' not in who: return {'n': 0, 'minutes': None, 'evidence': []}
    ins = [m for m in store._rows("SELECT * FROM message WHERE lower(IFNULL(FromEmail,''))=? AND IFNULL(Direction,'in')<>'out' "
                                  "AND Status NOT IN ('context','skipped','history') AND SentAt>=? ORDER BY SentAt DESC", (who, _ago(LOOK_DAYS, now)))
           if m['MessageId'] not in skip and not _skip(store, m)]
    cids = list({m['ConversationId'] for m in ins if m.get('ConversationId')})
    outs = store._rows(f"SELECT ConversationId, SentAt FROM message WHERE Direction='out' AND ConversationId IN ({','.join('?' * len(cids))}) "
                       "ORDER BY SentAt", cids) if cids else []
    got = []
    for m in ins:
        a = _dt(m.get('SentAt'))
        o = next((_dt(o['SentAt']) for o in outs if o['ConversationId'] == m.get('ConversationId') and _dt(o['SentAt']) and a and _dt(o['SentAt']) > a), None)
        if a and o and (o - a).days < REPLY_DAYS: got.append(((o - a).total_seconds() / 60, f"msg{m['MessageId']}"))
        if len(got) >= KEEP: break
    return {'n': len(got), 'minutes': median([g[0] for g in got]), 'evidence': [g[1] for g in got]}


def answered(store, m: dict) -> bool:
    """Whether the owner already wrote on this ask's thread after it came - then nothing is late."""
    return bool(m.get('ConversationId') and store._one("SELECT 1 x FROM message WHERE ConversationId=? AND Direction='out' AND SentAt>? LIMIT 1",
                                                      (m['ConversationId'], str(m.get('SentAt') or ''))))


def late_reply(store, m: dict, now=None) -> dict | None:
    """{who, usual, age, evidence} when this ask (the newest inbound message on the item) has waited past the owner's usual for its sender:
    twice the usual, an hour at least. None while there is no habit, the ask is answered, or it is not late."""
    if not m or answered(store, m) or str(m.get('FromEmail') or '').lower() in _mine(store): return None
    at = _dt(m.get('SentAt') or m.get('CreatedAt'))
    if not at: return None
    u = reply_lag(store, m.get('FromEmail'), now, skip={m.get('MessageId')})
    if u['n'] < ANSWERS: return None
    waited = ((now or datetime.now()) - at).total_seconds() / 60
    if waited < max(LATE_X * u['minutes'], LATE_MIN): return None
    return {'who': _first(m.get('FromName'), m.get('FromEmail')), 'usual': within(u['minutes']), 'age': span(waited), 'evidence': u['evidence'][:3]}


def _sender_of(store, tid) -> str:
    m = next((x for x in store.list_messages(int(tid)) if str(x.get('Direction') or 'in') != 'out'), None)
    return str((m or {}).get('FromEmail') or '').strip().lower()


def _put_offs(store, now=None) -> list:
    """[(task id, set at, until)] - every put-off of the owner's own with a day: the rail's For later (funnel_state, set by the owner) and a
    task's Remind me (its audit row). One per task, the latest."""
    out = {}
    for r in store._rows("SELECT Key, Until, At FROM funnel_state WHERE Key LIKE 'task:%' AND IFNULL(Until,'')<>'' AND IFNULL(By,'owner')='owner' AND At>=?",
                         (_ago(LOOK_DAYS * 2, now),)):
        try: out[int(r['Key'].split(':', 1)[1])] = (r['At'], r['Until'])
        except ValueError: continue
    for a in store._rows("SELECT EntityId, Detail, CreatedAt FROM audit WHERE EntityType='task' AND Action='remind' AND Actor='owner' AND CreatedAt>=? ORDER BY Id",
                         (_ago(LOOK_DAYS * 2, now),)):
        try: to = (json.loads(a.get('Detail') or '{}') or {}).get('to')
        except ValueError: to = None
        if to: out[int(a['EntityId'])] = (a['CreatedAt'], to)
    return [(t, at, until) for t, (at, until) in out.items()]


def put_off_habits(store, now=None) -> list:
    """[{by, day, n, of, held, evidence}] - THE COUNT a How you work line is written or confirmed from (learn.put_off_lines): each sender
    whose put-offs went to one weekday, at least PUT_OFFS times and two in three, and each domain whose several senders did. `held`: the
    first of them HELD_DAYS ago or more (the owner's ruling 7: about two weeks of data). It sets no default by itself - Remind me reads
    the line, which the owner can see and correct (the owner, 2026-10-25)."""
    now = now or datetime.now()
    rows = [(t, _dt(at), _dt(until), _sender_of(store, t)) for t, at, until in _put_offs(store, now)]
    rows = [r for r in rows if r[1] and r[2] and '@' in r[3]]
    def habit(by, hits):
        (wd, n), = Counter(u.weekday() for _, _, u, _ in hits).most_common(1)
        if n < PUT_OFFS or n * 3 < len(hits) * 2: return None
        ev = [f'fs{t}' for t, _, u, _ in sorted(hits, key=lambda h: h[1]) if u.weekday() == wd][-KEEP:]
        return {'by': by, 'day': DAYS[wd], 'n': n, 'of': len(hits), 'held': min(h[1] for h in hits) <= now - timedelta(days=HELD_DAYS), 'evidence': ev}
    by_who, by_dom = {}, {}
    for r in rows: by_who.setdefault(r[3], []).append(r); by_dom.setdefault(r[3].rsplit('@', 1)[1], []).append(r)
    return ([h for w, hs in by_who.items() if (h := habit(w, hs))]
            + [h for d, hs in by_dom.items() if len({r[3] for r in hs}) > 1 and (h := habit(d, hs))])


_DAY = re.compile(r'\b(' + '|'.join(DAYS) + r')s?\b', re.I)


def weekday_of(text: str):
    """The one weekday a line names (0 = Monday), else None - two days, or none, is no day to open on."""
    got = {m.group(1).capitalize() for m in _DAY.finditer(str(text or ''))}
    return DAYS.index(got.pop()) if len(got) == 1 else None


def put_off_line(store, who: str, doc: str = None) -> dict | None:
    """{text, key, by, evidence}: the in-use How you work line Remind me's day comes from for mail from `who` - a learned line whose
    put-offs (fs ids) were this sender's, else their domain's; or one of the owner's own lines there naming the address or domain. The
    owner's own line first, then the closest. Whatever day the line says now is the day: reworded, the default follows; deleted, there
    is none (the owner, 2026-10-25)."""
    from .learnedgraph import TAG
    from .learned_cut import WORK, lines as section_lines
    who = str(who or '').strip().lower()
    if '@' not in who: return None
    dom = who.rsplit('@', 1)[1]
    doc = store.get_doc('learned') if doc is None else doc
    got = []
    for raw, key in section_lines(doc or '', WORK):
        m = TAG.match(raw)
        text = m.group('text').strip() if m else raw.strip().lstrip('-* ').strip()
        if weekday_of(text) is None: continue
        if m:
            ev = [e.strip() for e in m.group('ev').split(',') if e.strip().startswith('fs')]
            senders = {_sender_of(store, e[2:]) for e in ev if e[2:].isdigit()}
            near = 0 if who in senders else 1 if any(w.endswith('@' + dom) for w in senders) else None
        else:
            low, ev = text.lower(), []
            near = 0 if who in low else 1 if re.search(rf'(?<![\w.-]){re.escape(dom)}\b', low) else None
        if near is not None: got.append((near, bool(m), {'text': text, 'key': key, 'by': who if near == 0 else dom, 'evidence': ev[:3]}))
    return min(got, key=lambda g: g[:2])[2] if got else None


def remind_day(store, tid, now=None) -> dict | None:
    """{on, day, by, line, key, evidence}: the day Remind me opens on for this task - the weekday its How you work line says (put_off_line),
    `on` the next such day after today (YYYY-MM-DD). None while no line says one: the count alone sets no default."""
    now = now or datetime.now()
    l = put_off_line(store, _sender_of(store, tid))
    if not l: return None
    wd = weekday_of(l['text'])
    on = now.date() + timedelta(days=(wd - now.weekday()) % 7 or 7)
    return {'on': on.isoformat(), 'day': DAYS[wd], 'by': l['by'], 'line': l['text'], 'key': l['key'], 'evidence': l['evidence']}


def handed_to(store, who: str, skip=None) -> dict | None:
    """{to, n, of, channel, evidence}: whom the owner handed this sender's asks to, when it was the same person at least twice, and on
    the channel they last used for it - evidence for the model (what the ask is ABOUT is its to read), never a lit button by itself."""
    who = str(who or '').strip().lower()
    if '@' not in who: return None
    got = []
    for a in store._rows("SELECT EntityId, Detail FROM audit WHERE EntityType='task' AND Action='handoff' AND IFNULL(ActorType,'human')<>'agent' ORDER BY Id DESC LIMIT 200"):
        if skip and int(a['EntityId']) == int(skip): continue
        try: d = json.loads(a.get('Detail') or '{}') or {}
        except ValueError: continue
        to = str(d.get('to') or '').strip().lower()
        if to and _sender_of(store, a['EntityId']) == who: got.append((to, f"task{a['EntityId']}", str(d.get('channel') or '')))
    if not got: return None
    (to, n), = Counter(t for t, *_ in got).most_common(1)
    return ({'to': to, 'n': n, 'of': len(got), 'channel': next(c for t, _, c in got if t == to), 'evidence': [e for t, e, _ in got if t == to][:3]}
            if n >= 2 else None)


def handoff_usual(store, tid) -> dict | None:
    """{to, channel, from, n, of, evidence}: whom Hand it to a person opens on for this task - the person the owner handed its sender's
    asks to (handed_to). Chosen, not sent: the drawer only fills the recipient, and the owner still presses (the owner, 2026-10-25)."""
    who = _sender_of(store, tid)
    h = handed_to(store, who, skip=tid)
    return {**h, 'from': who} if h else None


def chase_usual(store, who: str) -> dict | None:
    """{days, median}: the day a silence is late for this person, once three of their answers say what their median is (outcomes.late_after);
    None while there is no habit - the rule's three working days stand."""
    from . import outcomes
    f = outcomes.person_facts(store, who)
    if f['answered'] < ANSWERS or f['median_days'] is None: return None
    return {'days': outcomes.late_after(store, who), 'median': f['median_days']}


def prompt_lines(store, m: dict, tid=None, now=None) -> list:
    """What the Advisor's model reads about the owner's own usual with this item's sender - facts, each with the ids it rests on."""
    if not m: return []
    who, out = str(m.get('FromEmail') or '').lower(), []
    u = reply_lag(store, who, now, skip={m.get('MessageId')})
    if u['n'] >= ANSWERS:
        at = _dt(m.get('SentAt') or m.get('CreatedAt'))
        waited = span(((now or datetime.now()) - at).total_seconds() / 60) if at else ''
        out.append(f"HOW SOON YOU ANSWER {who}: {within(u['minutes'])} - the median of your last {u['n']} answers ({', '.join(u['evidence'][:3])})"
                   + ('; you have answered this one' if answered(store, m) else f'; this one has waited {waited}' if waited else ''))
    if tid and (d := remind_day(store, tid, now)):
        out.append(f"WHEN YOU PUT THEIR MAIL OFF (a How you work line the owner can correct): \"{d['line']}\""
                   + (f" ({', '.join(d['evidence'])})" if d['evidence'] else '') + f" - Remind me opens on {d['on']}, a {d['day']}")
    if (h := handed_to(store, who, skip=tid)):
        out.append(f"WHOM YOU HANDED THEIR ASKS TO: {h['to']}, {h['n']} of {h['of']} times ({', '.join(h['evidence'])}) - whether THIS ask is "
                   "the same kind of work is yours to read")
    return out
