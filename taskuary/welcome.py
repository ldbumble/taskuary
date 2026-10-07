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
from datetime import datetime, timedelta
from loguru import logger

from .general import DOCK_TAG

SEEN_KEY, CLOSED_KEY, GREETED_KEY = 'assistant_seen_at', 'assistant_closed_at', 'assistant_greeted_on'
GAP_HOURS, DAY_STARTS = 16, 5          # "welcome back" after this long away; no "good morning" before 5am
NEEDS = ('blocked', 'approve', 'asked', 'yours', 'forgotten')    # the lanes that wait on the owner, not on anybody else
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

def goodbye(store) -> str:
    """What is true once the window closes: nothing watches, nothing is lost, and the catch-up runs at the next open."""
    home = mail_home(store)
    if home: return f"While I'm closed I can't watch your mail, but it waits safely in {home}. I'll catch up the moment you open me."
    return "While I'm closed I can't watch for anything new. Nothing is lost - I'll catch up the moment you open me."

def closing(store, now: datetime = None) -> str:
    """The window is going: write down when (the next arrival counts from here), and say goodbye."""
    t = _stamp(now or datetime.now())
    for k in (CLOSED_KEY, SEEN_KEY): store.set_setting(k, t, 'assistant')
    return goodbye(store)

def last_here(store):
    """When the owner was last in front of Taskuary: the later of the last look and the last close."""
    got = [d for d in (_at(store.get_setting(SEEN_KEY)), _at(store.get_setting(CLOSED_KEY))) if d]
    return max(got) if got else None


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

def needs_you(items: list) -> list: return [i for i in items or [] if i.get('lane') in NEEDS and not i.get('settling')]

def _arrived(i, since): return (_at(i.get('since') or i.get('when')) or datetime.min) >= since

def away_word(since: datetime, now: datetime) -> str:
    """'Over the weekend' when Saturday fell inside the gap, 'Overnight' across midnight, else 'While you were away'."""
    d, sat = since.date(), False
    while d < now.date():
        d += timedelta(days=1); sat = sat or d.weekday() == 5
    return 'Over the weekend' if sat else 'Overnight' if since.date() < now.date() else 'While you were away'

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

def opening(store, now: datetime = None, since=None, items: list = None, new_day: bool = True, back: bool = False, fetch: bool = True) -> str:
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
    if since:
        n, word = came_in(store, since), away_word(since, now)
        fresh = sum(1 for i in needs_you(items) if _arrived(i, since))
        out.append(f"{word}: {n} came in, {fresh} need{'s' if fresh == 1 else ''} you." if n
                   else f"{word}: nothing new came in.")
        done = settled(store, since) if word == 'Over the weekend' or back else 0
        if done: out.append(f"{_cap(num(done))} {'was' if done == 1 else 'were'} settled without you.")
    out.append(three_things(items, today=new_day))
    out += [x for x in (next_meeting(store, now, fetch), promise_today(store, now)) if x]
    return ' '.join(x for x in out if x)


def due(store, now: datetime) -> tuple:
    """(a new day, back after a gap, when they were last here). A new day is the first look since the day began at
    DAY_STARTS - not merely an ungreeted one: a look at 8 after one at 7 is the same morning, and a brand-new install has
    nobody to welcome back (its welcome block says hello)."""
    prev = last_here(store)
    began = now.replace(hour=DAY_STARTS, minute=0, second=0, microsecond=0)
    new_day = bool(prev and prev < began <= now and str(store.get_setting(GREETED_KEY) or '') != now.strftime('%Y-%m-%d'))
    back = bool(prev and now - prev >= timedelta(hours=GAP_HOURS))
    return new_day, back, prev

def _spend(store, now: datetime):
    store.set_setting(GREETED_KEY, now.strftime('%Y-%m-%d'), 'assistant')
    store.set_setting(SEEN_KEY, _stamp(now), 'assistant')

def arrive(store, now: datetime = None, actor: str = 'owner', leaving: bool = False) -> dict:
    """The owner is in front of the desktop chat (it opened, or the window got focus). Once a day - or after GAP_HOURS
    away - the chat opens with the day, as a line with the walk's Next under it; otherwise it only notes they were here.
    `leaving` (the window lost focus) only notes it. Never while the walk is handed to the phone: that chat is where they are."""
    from . import concierge, general, remote_assistant
    now = now or datetime.now()
    new_day, back, prev = due(store, now)
    if leaving or not (new_day or back) or remote_assistant.handoff(store):
        store.set_setting(SEEN_KEY, _stamp(now), 'assistant'); return {'said': ''}
    from . import funnel
    try: items = funnel.pile(store).get('items') or []
    except Exception as e:
        logger.warning(f'welcome: no pile - {e}'); items = []
    say = opening(store, now, prev, items, new_day=new_day, back=back)
    _spend(store, now)
    tid = general.dock_task(store, actor)[0]['TaskId']
    chips = concierge.walk_chips(len(items))
    concierge.record(store, tid, 'assistant', say, {'key': 'brief', 'kind': 'brief', 'lane': 'report', 'title': 'Today', 'n': len(items),
                                                     'mail': sum(1 for i in items if i.get('kind') in funnel.MAIL_KINDS), 'chips': chips})
    return {'said': say, 'chips': chips}

def phone_lead(store, now: datetime = None) -> str:
    """The same opening, for the phone - which never speaks first, so it rides on the answer to their first message of the
    day. '' when it is not due, or the desk already said it."""
    now = now or datetime.now()
    new_day, back, prev = due(store, now)
    if not (new_day or back):
        store.set_setting(SEEN_KEY, _stamp(now), 'assistant'); return ''
    say = opening(store, now, prev, new_day=new_day, back=back, fetch=False)
    _spend(store, now)
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
    from . import assistant
    now = now or datetime.now()
    try: asked = assistant.unanswered(store)
    except Exception as e:
        logger.warning(f'missed: unanswered failed - {e}'); asked = []
    try: waiting = assistant.followups(store, 24, ('followup',))
    except Exception as e:
        logger.warning(f'missed: followups failed - {e}'); waiting = []
    urgent = [t for t in store.list_tasks(active_only=True) if t.get('Priority') == 'urgent' and t.get('Status') in ('open', 'in_progress', 'waiting')
              and DOCK_TAG not in str(t.get('Tags') or '')]
    return {'asked': asked, 'waiting': waiting, 'blind': couldnt_see(store, now), 'urgent': urgent}

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
                   + '; '.join(f"{first_name(a.get('who'))} - \"{a.get('gist') or ''}\" ({a.get('ago')} ago)" for a in asked[:4])
                   + (f"; and {len(asked) - 4} more" if len(asked) > 4 else '') + '.')
    for w in waiting[:3]:
        out.append(f"{first_name(w.get('who'))} still hasn't answered you about \"{w.get('subject') or ''}\" ({w.get('days')} day{'s' if w.get('days') != 1 else ''}).")
    if len(waiting) > 3: out.append(f"{_cap(num(len(waiting) - 3))} more {'is' if len(waiting) == 4 else 'are'} quiet on you too.")
    if not asked and not waiting: out.append("Nobody is waiting on you, and you aren't waiting on anybody.")
    if blind:
        names = [n for n, _ in blind]
        said = ' or '.join(names) if len(names) < 3 else ', '.join(names[:-1]) + f' or {names[-1]}'
        out.append(f"I couldn't check {said} {_when_down(blind[0][1], now)}, so I can't vouch for {'that' if len(names) == 1 else 'those'}.")
    return ' '.join(out)
