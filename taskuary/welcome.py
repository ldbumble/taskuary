"""Taken care of: what the assistant says when the owner arrives, when they leave, and when they ask whether they missed
anything. All of it is code - counts and facts already recorded - so none of it waits on a model.

- GOODBYE. Closing the window stops the server (desktop.py); there is no tray to keep watching. So the window says what
  is true before it goes: what it cannot watch while closed, and where the mail waits meanwhile.
- ARRIVAL. The first open of a calendar day, or a return after GAP_HOURS away, opens with the day in a breath: what came
  in while they were gone, the three things that need them (the first one named), the next meeting. Said once - in the
  desktop chat as a line, or added to their first message on the phone (the phone never speaks first).
- MISSED. "Did I miss anything?" - the asks nobody answered, the people who have not answered them, and what could not be
  checked. A look-up the model calls (lookups.READ 'missed.check'): typed words always go to the model, never a word list.

The voice is COUNSEL.md's calm rule: what happened, that nothing is lost, and what (if anything) is theirs to do.
"""
import threading
from datetime import datetime, timedelta
from loguru import logger

from .timewords import plural
from .general import DOCK_TAG
from . import lanes

SEEN_KEY, CLOSED_KEY, GREETED_KEY = 'assistant_seen_at', 'assistant_closed_at', 'assistant_greeted_on'
GAP_HOURS, DAY_STARTS = 16, 5          # "welcome back" after this long away; no "good morning" before 5am
AWAY_KEY = 'assistant_away_from'       # where the owner's latest away began (the greeting's gap, or any silence of AWAY_MINUTES since)
ACTIVE_KEY, AWAY_MINUTES = 'assistant_active_at', 45   # the owner's last press, send or focus; this long without one is an away
AWAY_MAX_DAYS, EVENING = 21, 18        # never reach back past three weeks; with nobody here before, "away" is since six last evening
CATCHUP_WAIT = 300                     # a greeting waits this long (seconds) for the startup catch-up, then says it is still reading
MAIL_APPS = {'outlook': 'Outlook', 'gmail': 'Gmail', 'imap': 'your mailbox'}
_WORDS = ('no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve')


def num(n: int) -> str: return _WORDS[n] if 0 <= n < len(_WORDS) else str(n)
def times(n: int) -> str: return {1: 'once', 2: 'twice'}.get(n, f'{num(n)} times')
def _cap(s: str) -> str: return s[:1].upper() + s[1:]
def _stamp(d: datetime) -> str: return d.strftime('%Y-%m-%d %H:%M:%S')

def _at(s):
    try: return datetime.fromisoformat(str(s)[:19].replace('T', ' ')) if s else None
    except ValueError: return None

def first_name(who: str) -> str:
    """'Erin Blake' -> 'Erin'; a company or an address stays whole."""
    w = ' '.join(str(who or '').split())
    return w.split(' ')[0] if ' ' in w and '@' not in w else w

def greeting(now: datetime) -> str: return 'Good morning' if now.hour < 12 else 'Good afternoon' if now.hour < 18 else 'Good evening'


# ── where things are while Taskuary is closed ───────────────────────────────────────────────────
def mail_home(store) -> str:
    """The app the owner's mail lives in, by name - '' when no mailbox is connected."""
    for c in store.list_connectors():
        if c.get('Active') and c.get('Type') in MAIL_APPS: return MAIL_APPS[c['Type']]
    return ''

def working(store) -> list:
    """The tasks a worker has RIGHT NOW - a live session or a headless run - which closing the window stops (terminal.shutdown_sessions)."""
    from . import terminal
    live = {getattr(t, 'task_id', None) for t in list(terminal.SESSIONS.values()) if getattr(t, 'alive', False)}
    try: live |= {r.get('TaskId') for r in store.running_runs()}
    except Exception as e: logger.debug(f'welcome: no runs read - {e}')
    return [t for t in store.list_tasks(status='in_progress') if t['TaskId'] in live and DOCK_TAG not in str(t.get('Tags') or '')]

def _refs(tasks: list) -> str:
    from .store import task_ref
    r = [task_ref(t['TaskId']) for t in tasks]
    if len(r) > 4: return ', '.join(r[:3]) + f' and {len(r) - 3} more'
    return r[0] if len(r) == 1 else ', '.join(r[:-1]) + f' and {r[-1]}'

def still_working(tasks: list) -> str:
    """'TQ-0012 and TQ-0014 are still being worked on. ...' - what the close asks about first (desktop.closing_handler)."""
    return f"{_refs(tasks)} {'is' if len(tasks) == 1 else 'are'} still being worked on. Closing Taskuary stops that work." if tasks else ''

def goodbye(store, busy: list = None) -> str:
    """What is true once the window closes: nothing watches, nothing is lost, and the catch-up runs at the next open. Work still
    running is named first - the close stops it, and "Nothing is lost" said over a stopped run was the one untrue line (B3, 2026-10-11)."""
    busy = working(store) if busy is None else busy
    stop = (f"Closing stops the work on {_refs(busy)} - {'it goes' if len(busy) == 1 else 'they go'} back on your list, and nothing "
            "starts again until you say so. ") if busy else ''
    home = mail_home(store)
    if home: return stop + f"While I'm closed I can't watch what comes in, but it waits safely in {home} and your other sources. I'll catch up the moment you open me."
    return stop + "While I'm closed I can't watch for anything new. " + ('' if busy else 'Nothing is lost - ') + "I'll catch up the moment you open me."

def closing(store, now: datetime = None) -> str:
    """The window is going: write down when (the next arrival counts from here), and say goodbye."""
    t = _stamp(now or datetime.now())
    for k in (CLOSED_KEY, SEEN_KEY): store.set_setting(k, t, 'assistant')
    return goodbye(store)

def last_here(store):
    """When the owner was last in front of Taskuary: the later of the last look and the last close."""
    got = [d for d in (_at(store.get_setting(SEEN_KEY)), _at(store.get_setting(CLOSED_KEY))) if d]
    return max(got) if got else None

def last_active(store):
    """The owner's last sign of life: a look, a close, or anything they pressed or sent since (touch)."""
    got = [d for d in (last_here(store), _at(store.get_setting(ACTIVE_KEY))) if d]
    return max(got) if got else None

def touch(store, now: datetime = None, key: str = ACTIVE_KEY):
    """The owner did something - a press, a send, the window's focus. THE one place presence is written, in the store so it
    outlives a restart. A silence of AWAY_MINUTES before it was an away, and where that began is what "while you were away"
    counts from (AWAY_KEY). Presses write ACTIVE_KEY, never SEEN_KEY: the greeting's own gap (due) reads SEEN_KEY, and a click
    landing before the window's arrive must not spend it."""
    now = now or datetime.now(); prev = last_active(store)
    if prev and now - prev >= timedelta(minutes=AWAY_MINUTES): store.set_setting(AWAY_KEY, _stamp(prev), 'assistant')
    if key == ACTIVE_KEY and prev and timedelta(0) <= now - prev < timedelta(minutes=1): return      # a write a minute is plenty
    store.set_setting(key, _stamp(now), 'assistant')


# ── what happened while they were gone ───────────────────────────────────────────────────────────
def came_in(store, since: datetime) -> int:
    """Messages people sent since then - reports and the assistant's own rows are not mail that came in."""
    row = store._rows("SELECT COUNT(*) n FROM message WHERE COALESCE(Direction,'in')='in' AND Channel NOT IN ('report','assistant') "
                      "AND Status NOT IN ('context','history') AND SentAt>=?", (_stamp(since),))
    return int((row[0] if row else {}).get('n') or 0)

def settled(store, since: datetime) -> int:
    """Work closed since then by somebody other than the owner - an agent, a rule, the sender's own answer."""
    row = store._rows("SELECT COUNT(*) n FROM task WHERE Status IN ('done','dropped') AND ClosedAt>=? AND COALESCE(UpdatedBy,'')<>'owner' "
                      "AND COALESCE(Tags,'') NOT LIKE ?", (_stamp(since), f'%{DOCK_TAG}%'))
    return int((row[0] if row else {}).get('n') or 0)

# WHAT NEEDS YOU IS THE RAIL'S OWN ANSWER (lanes.on_you): Tasks that are on you, never "waiting on them", which is on somebody else.
# A lane list of its own here drifted from the funnel: a stopped agent and a failed check were the owner's on the rail and
# missing from the greeting, so the morning after a close said "Nothing needs you yet" over both (B3, 2026-10-11). It also
# counted For later, which the opening card beside it does not (U6, 2026-10-17) - the greeting says the card's number now.
def needs_you(items: list) -> list: return [i for i in items or [] if lanes.on_you(i)]

def _arrived(i, since): return (_at(i.get('since') or i.get('when')) or datetime.min) >= since

def away_word(since: datetime, now: datetime) -> str:
    """'Over the weekend' when Saturday fell inside a gap of three days at most, 'Over the last nine days' for a longer one (a week
    away was "Over the weekend" too, 2026-10-11), 'Overnight' across midnight, else 'While you were away'."""
    d, sat, days = since.date(), False, (now.date() - since.date()).days
    if days > 3: return f'Over the last {num(days)} days'
    while d < now.date():
        d += timedelta(days=1); sat = sat or d.weekday() == 5
    return 'Over the weekend' if sat else 'Overnight' if since.date() < now.date() else 'While you were away'

def away_window(store, now: datetime = None) -> tuple:
    """(start, word): where "while you were away" begins, for EVERY reader of it - the greeting, the opening screen's counts,
    "did I miss anything?", the Morning digest. Each used to keep its own clock (six last evening, two days back, midnight), so on
    a Monday the asks of Friday afternoon fell between them and the counts disagreed (B5, 2026-10-11). The gap a greeting is held
    for; else, gone AWAY_MINUTES now, their last sign of life; else the latest away they came back from. The morning's gap held
    all day read "While you were away · since 2:05 AM" at eleven at night over a day of presses (2026-10-22). Never past
    AWAY_MAX_DAYS. Nobody here before: last night."""
    now = now or datetime.now()
    got, last, away = _HELD.get('prev'), last_active(store), _at(store.get_setting(AWAY_KEY))
    if not got and last:
        got = last if now - last >= timedelta(minutes=AWAY_MINUTES) or not away or away > last else away
    if not got: return (now - timedelta(days=1)).replace(hour=EVENING, minute=0, second=0, microsecond=0), 'Since last night'
    got = max(got, now - timedelta(days=AWAY_MAX_DAYS))
    return got, away_word(got, now)

def away_days(store, now: datetime = None) -> float:
    """How far back an ask can still be one nobody answered: the whole gap and the day before it, two days at the least."""
    now = now or datetime.now()
    return min(AWAY_MAX_DAYS, max(2.0, (now - away_window(store, now)[0]).total_seconds() / 86400 + 1))

def next_meeting(store, now: datetime, fetch: bool = True) -> str:
    """'Your next meeting is Budget review at 2:00 PM.' - from the calendar's cache unless `fetch` (never on a button)."""
    from . import calendar as cal
    try:
        t = cal.today(store) if fetch else (cal._TODAY.get('data') if cal._TODAY.get('day') == now.strftime('%Y-%m-%d') else None)
    except Exception as e:
        logger.debug(f'welcome: calendar skipped - {e}'); return ''
    hhmm = now.strftime('%H:%M')
    ev = next((e for e in (t or {}).get('events') or [] if not e.get('all_day') and str(e.get('start') or '')[11:16] > hhmm), None)
    return f"Your next meeting is {ev.get('subject') or 'on the calendar'} at {cal.span(ev['start'], '')}." if ev else ''

def promise_today(store, now: datetime = None) -> str:
    """One line, only when one of the owner's own promises falls due today (assistant.promises_due)."""
    from . import assistant
    try: due = assistant.promises_due(store, now)
    except Exception as e:
        logger.debug(f'welcome: promises skipped - {e}'); return ''
    if not due: return ''
    p = due[0]
    return f"You told {first_name(p['who'])} you'd {p['what']} today." + (f" ({len(due) - 1} more promise{'s' if len(due) > 2 else ''} like it.)" if len(due) > 1 else '')

def three_things(items: list, today: bool = True) -> str:
    """"Three things today, Erin's first: the staffing sheet by noon. Then Gail and Paula." - never a bare count."""
    need = needs_you(items)
    if not need: return 'Nothing needs you yet.'
    top, rest = need[:3], len(need) - 3
    one = top[0]; who = first_name(one.get('who') or '')
    what = ' '.join(str(one.get('title') or 'it').split()).rstrip('.')
    head = (f"{_cap(num(len(top)))} thing{'s' if len(top) != 1 else ''} {'today' if today else 'for you'}"
            + (f", {who}'s first: {what}." if len(top) > 1 and who else f", from {who}: {what}." if who else f": {what}."))
    then = [first_name(i.get('who') or '') or (i.get('title') or '')[:40] for i in top[1:]]
    out = [head] + ([f"Then {' and '.join(x for x in then if x)}."] if any(then) else [])
    if rest > 0: out.append(f"{_cap(num(rest))} more after those - I'm holding {'it' if rest == 1 else 'them'} for you.")
    elif len(items or []) > len(top): out.append("I'm holding the rest.")
    return ' '.join(out)

def away_lines(store, now: datetime, since, items: list, back: bool = False, reading: bool = False) -> list:
    """What came in while they were gone, what was settled without them, and - when the catch-up outlived CATCHUP_WAIT - that the
    count is not the whole of it yet. Its own piece so the opening card can draw it (it was computed and never shown, 2026-10-11)."""
    if not since: return []
    n, word, out = came_in(store, since), away_word(since, now), []
    fresh = sum(1 for i in needs_you(items) if _arrived(i, since))
    # ONE WORD FOR WHAT IS YOURS (U6): "3 need you" here, "Waiting · 30" on the card - the rail's own "on you" for both
    out.append(f"{word}: {n} came in{' so far' if reading else ''}, {fresh} on you." if n
               else f"{word}: nothing new came in{' yet' if reading else ''}.")
    done = settled(store, since) if word == 'Over the weekend' or back else 0
    if done: out.append(f"{_cap(num(done))} {'was' if done == 1 else 'were'} settled without you.")
    if reading: out.append(f"I'm still reading {mail_home(store) or 'what came in'} - I'll put the rest in front of you as it lands.")
    return out

def opening(store, now: datetime = None, since=None, items: list = None, new_day: bool = True, back: bool = False, fetch: bool = True,
            reading: bool = False) -> str:
    """The day in a breath, in the calm voice: hello, what came in while away, three things, the next meeting, and a promise
    only when one is due today. Facts only - every number is counted here."""
    from . import funnel
    now = now or datetime.now()
    if items is None:
        try: items = funnel.pile(store).get('items') or []
        except Exception as e:
            logger.warning(f'welcome: no pile - {e}'); items = []
    hello = greeting(now)
    out = [f"{hello}, and welcome back." if new_day and back else f"{hello}." if new_day else 'Welcome back.']
    out += away_lines(store, now, since, items, back, reading)
    out.append(three_things(items, today=new_day))
    out += [x for x in (next_meeting(store, now, fetch), promise_today(store, now)) if x]
    return ' '.join(x for x in out if x)


def due(store, now: datetime) -> tuple:
    """(a new day, back after a gap, when they were last here). A new day is the first look since the day began at
    DAY_STARTS - not merely an ungreeted one: a look at 8 after one at 7 is the same morning, and a brand-new install has
    nobody to welcome back (its welcome block says hello)."""
    prev = _HELD.get('prev') or last_here(store)           # a held greeting keeps its gap, whatever a blur wrote meanwhile
    began = now.replace(hour=DAY_STARTS, minute=0, second=0, microsecond=0)
    new_day = bool(prev and prev < began <= now and str(store.get_setting(GREETED_KEY) or '') != now.strftime('%Y-%m-%d'))
    back = bool(prev and now - prev >= timedelta(hours=GAP_HOURS))
    return new_day, back, prev

def _spend(store, now: datetime, prev: datetime = None):
    _HELD.clear()
    if prev: store.set_setting(AWAY_KEY, _stamp(prev), 'assistant')
    store.set_setting(GREETED_KEY, now.strftime('%Y-%m-%d'), 'assistant')
    store.set_setting(SEEN_KEY, _stamp(now), 'assistant')


# ── the startup catch-up: the greeting waits for the mail ────────────────────────────────────────────
# On a Monday the greeting fired while the catch-up was still reading the weekend (91 s on the owner's box), said "Over the
# weekend: nothing new came in", spent itself, and was never corrected (B4, 2026-10-11). In memory on purpose: a crash mid
# catch-up must not leave a greeting held into the next launch.
_CATCHUP, _HELD, _STARTUP = {}, {}, {}

def catch_up_began(now: datetime = None):
    """The startup catch-up started reading. A greeting asked for meanwhile is drawn, not spent; past CATCHUP_WAIT the page is
    woken anyway, to say honestly that it is still reading."""
    _CATCHUP['at'] = _STARTUP['reports'] = now or datetime.now()
    t = threading.Timer(CATCHUP_WAIT + 1, _wake); t.daemon = True; t.start()

def catch_up_ended():
    """The mail is in and judged: wake the page, so a held greeting is said with the real counts."""
    _CATCHUP.clear(); _wake()

def startup_reports_done(): _STARTUP.clear()
def startup_reports_pending() -> bool:
    "The launch's own report pass (the on-start Morning digest among them) has not finished yet."
    return bool(_STARTUP)

def mail_reading() -> bool: return bool(_CATCHUP)

def _wake():
    from . import live
    if _HELD: live.emit(live.ARRIVE)

def _reading(now: datetime):
    """None when no catch-up runs, 'wait' inside CATCHUP_WAIT, 'late' past it."""
    at = _CATCHUP.get('at')
    return None if not at else 'wait' if now - at < timedelta(seconds=CATCHUP_WAIT) else 'late'

def arrive(store, now: datetime = None, actor: str = 'owner', leaving: bool = False) -> dict:
    """The owner is in front of the desktop chat (it opened, or the window got focus). Once a day - or after GAP_HOURS
    away - the chat opens with the day, as a line with the walk's Next under it; otherwise it only notes they were here.
    `leaving` (the window lost focus) only notes it. Never while the walk is handed to the phone: that chat is where they are."""
    from . import concierge, general, remote_assistant
    now = now or datetime.now()
    new_day, back, prev = due(store, now)
    if leaving or not (new_day or back) or remote_assistant.handoff(store):
        # leaving says they were here until now; only coming back can end an away
        if leaving: store.set_setting(SEEN_KEY, _stamp(now), 'assistant')
        else: touch(store, now, SEEN_KEY)
        return {'said': ''}
    reading = _reading(now)
    tid = general.dock_task(store, actor)[0]['TaskId']
    if reading == 'wait':
        # DRAWN NOW, FILLED LATER: held whole, the opener came in a minute and a half after launch - UNDER the walk the owner had
        # started meanwhile, the Morning digest with it (the owner, 2026-10-14: "why can't you put the digest right away on load
        # and the numbers ... in loading mode"). The card goes up at once, marked reading; the counts rewrite it in its place.
        _HELD.setdefault('prev', prev)
        if 'cid' in _HELD: return {'said': '', 'pending': True}
        _HELD['cid'] = concierge.record(store, tid, 'assistant', f"{greeting(now)}.", {'key': 'brief', 'kind': 'brief', 'lane': 'report',
                                                                                          'title': 'Today', 'reading': True})
        return {'said': '', 'pending': True, 'drawn': True}
    from . import funnel
    try: items = funnel.pile(store).get('items') or []
    except Exception as e:
        logger.warning(f'welcome: no pile - {e}'); items = []
    say = opening(store, now, prev, items, new_day=new_day, back=back, reading=bool(reading))
    away = ' '.join(away_lines(store, now, prev, items, back, bool(reading)))
    cid = _HELD.get('cid')
    _spend(store, now, prev)
    chips = concierge.walk_chips(len(items))
    # the headline counts what is ON YOU; reports and notices are reading, never "waiting" (U6: "Waiting · 30" over rows that said
    # "Nothing to decide") - the greeting's own count (needs_you), the header's and the page's opener all ask lanes.on_you
    # ...one census (lanes.census) for every count the owner reads, so the opener, the rail and the walk's end never disagree
    c = lanes.census(items)
    card = {'key': 'brief', 'kind': 'brief', 'lane': 'report', 'title': 'Today', 'n': len(items),
            'on_you': c['on_you'], 'to_read': c['to_read'], 'tasks': c['tasks'],
            'mail': sum(map(lanes.is_mail, items)), 'chips': chips, 'away': away}
    if cid: concierge.rewrite(store, cid, say, card)
    else: concierge.record(store, tid, 'assistant', say, card)
    return {'said': say, 'chips': chips}

def phone_lead(store, now: datetime = None) -> str:
    """The same opening, for the phone - which never speaks first, so it rides on the answer to their first message of the
    day. '' when it is not due, or the desk already said it."""
    now = now or datetime.now()
    new_day, back, prev = due(store, now)
    if not (new_day or back):
        touch(store, now, SEEN_KEY); return ''
    reading = _reading(now)
    if reading == 'wait':                     # the next message hears it, with the mail in
        _HELD.setdefault('prev', prev); return ''
    say = opening(store, now, prev, new_day=new_day, back=back, fetch=False, reading=bool(reading))
    _spend(store, now, prev)
    return say

def mark_greeted(store, now: datetime = None): _spend(store, now or datetime.now())


# ── "did I miss anything?" ───────────────────────────────────────────────────────────────────────
def couldnt_see(store, now: datetime = None) -> list:
    """[(name, since)] for every place Taskuary reads that is not answering: its last poll failed, or it has no sign-in.
    An AI connection is not a place the owner's work arrives, so it is not one of these."""
    from .llm import AI_TYPES
    from . import funnel
    out = []
    for c in store.list_connectors():
        if not c.get('Active') or c.get('Type') in AI_TYPES or c.get('Type') in ('agent', 'human', 'task', 'knowledge'): continue
        name = c.get('Name') or funnel.CONN_LABELS.get(c.get('Type'), c.get('Type') or 'one of your connections')
        if str(c.get('LastError') or '').strip(): out.append((name, c.get('LastErrorAt') or ''))
    return out

def _when_down(since: str, now: datetime) -> str:
    d = _at(since)
    if not d: return 'lately'
    if d.date() == now.date(): return 'this morning' if d.hour < 12 else 'today'
    return 'since yesterday' if (now.date() - d.date()).days == 1 else f"since {d.strftime('%A')}"

def missed(store, now: datetime = None) -> dict:
    """The three checks the morning brief already runs, for the chat: who asked and heard nothing back, who has not answered
    the owner, what could not be seen - plus whether anything open is marked urgent."""
    from . import assistant, sentjudge
    now = now or datetime.now()
    try: asked, unjudged = assistant.their_asks(store, away_days(store, now))     # two days back lost Friday's asks on a Monday (B5)
    except Exception as e:
        logger.warning(f'missed: unanswered failed - {e}'); asked, unjudged = [], []
    try: waiting = assistant.followups(store, 24, ('followup',))
    except Exception as e:
        logger.warning(f'missed: followups failed - {e}'); waiting = []
    # what the model could not read is said, never counted as "nothing": no AI, or sent words not judged yet (2026-10-11)
    try: untracked = sentjudge.blind(store)
    except Exception as e:
        logger.warning(f'missed: sent-words check failed - {e}'); untracked = ''
    urgent = [t for t in store.list_tasks(active_only=True) if t.get('Priority') == 'urgent' and t.get('Status') in ('open', 'in_progress', 'waiting')
              and DOCK_TAG not in str(t.get('Tags') or '')]
    return {'asked': asked, 'unjudged': unjudged, 'waiting': waiting, 'untracked': untracked, 'blind': couldnt_see(store, now), 'urgent': urgent}

def missed_says(d: dict, now: datetime = None) -> str:
    """The answer, in the calm voice: "Nothing urgent. Two people asked you something: ... Payworth still hasn't answered
    you. I couldn't check Teams this morning, so I can't vouch for that." """
    now = now or datetime.now()
    asked, waiting, blind, urgent = d.get('asked') or [], d.get('waiting') or [], d.get('blind') or [], d.get('urgent') or []
    out = [f"{_cap(num(len(urgent)))} thing{'s are' if len(urgent) != 1 else ' is'} marked urgent: "
           + '; '.join(f"\"{' '.join(str(t.get('Title') or '').split())[:70]}\"" for t in urgent[:3]) + '.' if urgent else 'Nothing urgent.']
    if asked:
        people = len({a.get('who') for a in asked})
        out.append(f"{_cap(num(people))} {'person is' if people == 1 else 'people are'} still waiting on an answer from you: "
                   + '; '.join(f"{first_name(a.get('who'))} - \"{a.get('gist') or ''}\" ({a.get('ago')})" for a in asked[:4])
                   + (f"; and {len(asked) - 4} more" if len(asked) > 4 else '') + '.')
    unjudged, untracked = d.get('unjudged') or [], d.get('untracked') or ''
    if unjudged:
        names = list(dict.fromkeys(first_name(u.get('who')) for u in unjudged))
        out.append(f"I couldn't judge {num(len(unjudged))} message{'s' if len(unjudged) != 1 else ''} - from {', '.join(names[:3])}"
                   + (f" and {len(names) - 3} more" if len(names) > 3 else '') + f" - so I can't say whether {'they ask' if len(unjudged) != 1 else 'it asks'} you anything.")
    for w in waiting[:3]:
        out.append(f"{first_name(w.get('who'))} still hasn't answered you about \"{w.get('subject') or ''}\" ({plural(w.get('days'), 'day')}).")
    if len(waiting) > 3: out.append(f"{_cap(num(len(waiting) - 3))} more {'is' if len(waiting) == 4 else 'are'} quiet on you too.")
    # "nobody" only where it was checked: a message triage never read, or sent words no model read, is not a nobody (2026-10-11)
    if not asked and not unjudged and not waiting:
        out.append('Nobody is waiting on you.' if untracked else "Nobody is waiting on you, and you aren't waiting on anybody.")
    if untracked: out.append(untracked)
    if blind:
        names = [n for n, _ in blind]
        said = ' or '.join(names) if len(names) < 3 else ', '.join(names[:-1]) + f' or {names[-1]}'
        out.append(f"I couldn't check {said} {_when_down(blind[0][1], now)}, so I can't vouch for {'that' if len(names) == 1 else 'those'}.")
    return ' '.join(out)
