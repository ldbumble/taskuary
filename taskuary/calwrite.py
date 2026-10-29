"""Answering the calendar: an invite accepted, declined or met with another time, and a meeting set up from a thread.

calendar.py only READS - every reply draft sees the owner's busy times. This is the other half, and nothing in it sends by
itself: each act is DRAFTED as a review whose envelope says what the calendar will be told (Deliver kind 'calendar'), it
waits in the approval queue like any reply, and only the owner's Send reaches `deliver` (verdicts._send_snapshot). The
note box is the reply box; what it holds rides along as the RSVP's comment, or the new invite's body.

Two providers, on the cards that already read the calendar:
- Outlook: Graph events/{id}/accept | decline | tentativelyAccept (proposedNewTime) and POST events, as the mailbox the
  invite arrived in. A signed-in card needs Calendars.ReadWrite - an older sign-in consented to Calendars.Read only, so it
  is asked for again on the next sign-in (msauth.SCOPES); a tenant app needs the APPLICATION permission.
- Google: the Gmail card's OAuth fields with the calendar.events scope - events.patch on the owner's attendee row,
  events.insert for a new one. Google has no "propose a new time": it is a tentative answer whose note names the time.
A card without the write permission keeps the buttons; pressing one says so in one line, with the sign-in as its fix.

What an invite IS comes from the mail system, never its words (counsel.is_invite): Graph's eventMessage family and its
meetingMessageType, or the iCalendar part's METHOD and SEQUENCE. Only a request nobody has answered is the owner's move;
an answer, an update and a cancellation stay fyi.
"""
import base64, json, re, time
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo
from loguru import logger
from . import buttons, calendar as cal, net as requests

GRAPH = cal.GRAPH
MS_WRITE = 'Calendars.ReadWrite'
G_WRITE = ('https://www.googleapis.com/auth/calendar.events', 'https://www.googleapis.com/auth/calendar')
ACTS = ('accept', 'decline', 'propose', 'schedule')
SAID = {'accept': 'Accept', 'decline': 'Decline', 'propose': 'Propose a new time', 'schedule': 'Invite'}
# the line the reply box starts with - the owner's to change or empty; empty sends the answer with no note
NOTE = {'accept': 'See you then.', 'decline': "Sorry - I can't make this one.",
        'propose': 'I have a conflict then - would {when} work instead?', 'schedule': 'As discussed - here is a time.'}
DAY_START, DAY_END, SLOTS, STEP = 9, 17, 3, 30
def send_word() -> str: return buttons.label('approve')       # the one name of the button that is the owner's yes


# ── what an invite is ────────────────────────────────────────────────────────────────────
def _ms_kind(m: dict) -> str:
    t, mt = str(m.get('@odata.type') or '').lower(), str(m.get('meetingMessageType') or '').lower()
    if 'cancel' in mt: return 'cancel'
    if mt in ('meetingaccepted', 'meetingtenativelyaccepted', 'meetingtentativelyaccepted', 'meetingdeclined') or 'response' in t: return 'response'
    if mt == 'meetingrequest' or 'request' in t: return 'request'
    return 'other'


def _local(dt: dict, tz) -> str:
    """Graph's {dateTime, timeZone} as the owner's 'YYYY-MM-DD HH:MM'."""
    s = str((dt or {}).get('dateTime') or '')[:19]
    if not s: return ''
    try: d = datetime.fromisoformat(s)
    except ValueError: return s[:16].replace('T', ' ')
    zone = str((dt or {}).get('timeZone') or '')
    if zone and zone.upper() != 'UTC' and tz is not None and zone == cal.tz_name(tz): return d.strftime('%Y-%m-%d %H:%M')
    # UTC never needs the tz database: Windows has none without tzdata, and ZoneInfo('UTC') raised there
    try: src = timezone.utc if zone.upper() in ('', 'UTC') else ZoneInfo(zone)
    except Exception: return d.strftime('%Y-%m-%d %H:%M')
    return d.replace(tzinfo=src).astimezone(tz).strftime('%Y-%m-%d %H:%M') if tz is not None else d.strftime('%Y-%m-%d %H:%M')


def from_graph(m: dict, mailbox: str, tz=None) -> dict:
    """An eventMessage (with its event expanded, when the poll fetched it) as the stored invite."""
    ev = m.get('event') or {}
    org = ((ev.get('organizer') or m.get('from') or {}).get('emailAddress') or {})
    resp = str(((ev.get('responseStatus') or {}).get('response')) or '').lower()
    return {'kind': _ms_kind(m), 'provider': 'outlook', 'mailbox': mailbox, 'event_id': ev.get('id') or '', 'ical_uid': ev.get('iCalUId') or '',
            'update': bool(m.get('previousStartDateTime') or m.get('previousEndDateTime') or m.get('previousLocation')),
            'moved': bool(m.get('previousStartDateTime') or m.get('previousEndDateTime')),
            'had': _HAD.get(resp, ''), 'answered': resp not in ('', 'none', 'notresponded'), 'asks': m.get('responseRequested') is not False and ev.get('responseRequested') is not False,
            'subject': ev.get('subject') or m.get('subject') or '', 'start': _local(ev.get('start') or m.get('startDateTime'), tz),
            'end': _local(ev.get('end') or m.get('endDateTime'), tz), 'all_day': bool(ev.get('isAllDay')),
            'organizer': org.get('name') or org.get('address') or '', 'organizer_email': (org.get('address') or '').lower(),
            'attendees': [a for a in ((x.get('emailAddress') or {}).get('address') for x in ev.get('attendees') or []) if a][:20]}


def graph_detail(tok: str, mailbox: str, mid: str, tz) -> dict:
    """The invitation itself: the poll's $select cannot name the derived type's fields, so one more read, invites only."""
    r = requests.get(f'{GRAPH}/users/{mailbox}/messages/{mid}', timeout=20, params={'$expand': 'microsoft.graph.eventMessage/event'},
                     headers={'Authorization': f'Bearer {tok}', 'Prefer': f'outlook.timezone="{cal.tz_name(tz)}"'})
    if r.status_code != 200: raise RuntimeError(f'the invite could not be read ({r.status_code})')
    return r.json() or {}


def graph_invite(store, tok: str, mailbox: str, m: dict) -> dict:
    """The poll's invite, read in full when it can be (its event: the id to answer, the times, the owner's response) - and
    from the poll's own fields when that read fails, so a request is still known as one."""
    tz = cal.tz_of(store)
    try: return from_graph({**m, **graph_detail(tok, mailbox, m['id'], tz)}, mailbox, tz)
    except Exception as e:
        logger.info(f'calwrite: invite {str(m.get("id"))[:12]} read from the poll alone - {e}')
        return from_graph(m, mailbox, tz)


def _unfold(text: str) -> list:
    out = []
    for line in str(text or '').replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        if line[:1] in (' ', '\t') and out: out[-1] += line[1:]
        elif line: out.append(line)
    return out


def _ics_time(params: dict, value: str, tz):
    v = value.strip()
    if params.get('VALUE') == 'DATE' or re.fullmatch(r'\d{8}', v):
        return f'{v[:4]}-{v[4:6]}-{v[6:8]} 00:00', True
    try: d = datetime.strptime(v[:15], '%Y%m%dT%H%M%S')
    except ValueError: return '', False
    if v.endswith('Z'): d = d.replace(tzinfo=timezone.utc)      # never ZoneInfo('UTC'): no tz database on Windows without tzdata
    elif params.get('TZID'):
        try: d = d.replace(tzinfo=ZoneInfo(params['TZID'].strip('"')))
        except Exception: d = d.replace(tzinfo=tz) if tz else d
    else: d = d.replace(tzinfo=tz) if tz else d
    return (d.astimezone(tz) if tz and d.tzinfo else d).strftime('%Y-%m-%d %H:%M'), False


def from_ics(text: str, me=(), tz=None) -> dict | None:
    """An iCalendar part (RFC 5545/6047) as the stored invite: METHOD says request, reply or cancel; SEQUENCE above 0 is an
    update; the owner's own PARTSTAT says whether it was answered."""
    method, ev, inside = '', {}, False
    mine = {str(a).lower() for a in me if a}
    for line in _unfold(text):
        head, _, value = line.partition(':')
        name, *ps = head.split(';')
        params = dict(p.split('=', 1) for p in ps if '=' in p)
        name = name.upper()
        if name == 'METHOD' and not inside: method = value.strip().upper()
        elif name == 'BEGIN' and value.strip().upper() == 'VEVENT': inside = True
        elif name == 'END' and value.strip().upper() == 'VEVENT': break
        elif inside and name in ('DTSTART', 'DTEND'):
            ev[name], day = _ics_time(params, value, tz)
            if name == 'DTSTART': ev['all_day'] = day
        elif inside and name in ('UID', 'SUMMARY', 'SEQUENCE'): ev[name] = value.strip()
        elif inside and name == 'ORGANIZER': ev['org'] = (params.get('CN', '').strip('"'), value.split(':')[-1].strip().lower())
        elif inside and name == 'ATTENDEE':
            addr = value.split(':')[-1].strip().lower()
            ev.setdefault('who', []).append(addr)
            if addr in mine: ev['partstat'] = params.get('PARTSTAT', 'NEEDS-ACTION').upper()
    if not ev: return None
    kind = {'REQUEST': 'request', 'REPLY': 'response', 'CANCEL': 'cancel', 'COUNTER': 'response'}.get(method, 'other')
    try: seq = int(ev.get('SEQUENCE') or 0)
    except ValueError: seq = 0
    name, addr = ev.get('org') or ('', '')
    return {'kind': kind, 'provider': 'google', 'ical_uid': ev.get('UID') or '', 'event_id': '', 'update': seq > 0,
            'answered': ev.get('partstat', 'NEEDS-ACTION') not in ('NEEDS-ACTION', ''), 'asks': True,
            'had': _HAD.get(ev.get('partstat', '').lower(), ''),
            'subject': ev.get('SUMMARY') or '', 'start': ev.get('DTSTART') or '', 'end': ev.get('DTEND') or ev.get('DTSTART') or '',
            'all_day': bool(ev.get('all_day')), 'organizer': name or addr, 'organizer_email': addr, 'attendees': (ev.get('who') or [])[:20]}


def ics_of(msg) -> str:
    """The text of an email.message's iCalendar part, or ''."""
    try:
        for p in msg.walk():
            if p.get_content_type() in ('text/calendar', 'application/ics'):
                raw = p.get_payload(decode=True) or b''
                return raw.decode(p.get_content_charset() or 'utf-8', errors='replace')
    except Exception as e: logger.debug(f'calwrite: the calendar part could not be read - {e}')
    return ''


def invite_of(m: dict | None) -> dict | None:
    """The stored invite on a message row (MailMetaJson 'cal'), or the one a fresh message dict carries."""
    if not m: return None
    if isinstance(m.get('cal'), dict): return m['cal']
    if isinstance((m.get('mail_meta') or {}).get('cal'), dict): return m['mail_meta']['cal']
    try: meta = json.loads(m.get('MailMetaJson') or 'null') or {}
    except (TypeError, ValueError): meta = {}
    return meta.get('cal') if isinstance(meta, dict) and isinstance(meta.get('cal'), dict) else None


def needs_answer(c: dict | None) -> bool:
    """The owner's move: a request nobody has answered that asks for one - or an UPDATE that moved the time of a meeting the
    owner had accepted or tentatively accepted (the owner, 2026-10-20); any other update stays fyi."""
    if not c or c.get('kind') != 'request' or c.get('asks', True) is False: return False
    return bool(c.get('moved') and c.get('had')) if c.get('update') else not c.get('answered')


def remember(store, c: dict | None) -> dict | None:
    """An invite read against the earlier mail about the same meeting (its iCalendar UID, or Graph's event id): an update whose
    start or end differs from the last one MOVED it, and what the owner said to that one - the calendar's own answer on it, or
    the answer they sent from here - is what they HAD said. Fills `moved` and `had` in place; the mail alone often cannot say."""
    if not c or c.get('kind') != 'request': return c
    key = c.get('ical_uid') or c.get('event_id')
    if not key: return c
    rows = store._rows("SELECT MessageId, MailMetaJson FROM message WHERE MailMetaJson LIKE ? ORDER BY MessageId DESC LIMIT 20", (f'%{key}%',))
    for r in rows:
        p = invite_of(r)
        if not p or p is c or key not in (p.get('ical_uid'), p.get('event_id')) or (p.get('start'), p.get('end'), p.get('update')) == (c.get('start'), c.get('end'), c.get('update')): continue
        if c.get('update') and (p.get('start'), p.get('end')) != (c.get('start'), c.get('end')): c['moved'] = True
        sent = [env_of(x).get('act') for x in store.reviews_for_message(r['MessageId']) if x.get('DeliveryState') == 'sent' and env_of(x).get('kind') == 'calendar']
        c['had'] = c.get('had') or {'accept': 'accepted', 'propose': 'tentative'}.get(next(iter(sent), ''), '') or p.get('had') or ''
        break
    return c


def when(start: str, end: str = '', all_day: bool = False) -> str:
    """'Thu Oct 22, 2:00-3:00 PM' - the day said once, the AM/PM once where both ends share it."""
    try: d = datetime.fromisoformat(str(start)[:16])
    except ValueError: return str(start or '')
    day = f"{d.strftime('%a %b')} {d.day}"
    return f'{day}, all day' if all_day else f"{day}, {cal.span(str(start), str(end or ''))}"


# ── the owner's time ─────────────────────────────────────────────────────────────────────
_BUSY = {'at': 0.0, 'data': None, 'days': 0}
BUSY_TTL = 300


def busy(store, days: int = 14) -> list:
    """The owner's busy events from now for `days` days, every calendar the cards reach - cached like the reply's read, and read
    again when a longer window is asked for than the cache holds. The demo has no calendar behind it, so it has a scripted week
    (demo.agenda)."""
    from . import demo
    if demo.enabled(): return demo.agenda()
    days = max(14, int(days or 14))
    if _BUSY['data'] is not None and time.time() - _BUSY['at'] < BUSY_TTL and _BUSY['days'] >= days: return _BUSY['data']
    tz = cal.tz_of(store)
    ag = cal.agenda(store, days=days, start=datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0))
    _BUSY.update(at=time.time(), data=ag['events'], days=days)
    return ag['events']


def _dt(s): return datetime.fromisoformat(str(s)[:16])


def clashes(store, start: str, end: str, skip: str = '', events: list = None) -> list:
    """The busy events that overlap [start, end) - never the meeting itself (`skip` is its title) nor an all-day block."""
    try: a, b = _dt(start), _dt(end or start)
    except ValueError: return []
    out = []
    for e in events if events is not None else busy(store):
        if e.get('all_day') or (skip and str(e.get('subject') or '').strip().lower() == skip.strip().lower()): continue
        try: s, en = _dt(e['start']), _dt(e.get('end') or e['start'])
        except (KeyError, ValueError): continue
        if s < b and en > a: out.append(e)
    return out


def clash_line(store, start: str, end: str, skip: str = '', events: list = None) -> str:
    """'clashes with Budget review 2:00-3:00 PM' - or '' when the time is free."""
    hit = clashes(store, start, end, skip, events)
    if not hit: return ''
    e = hit[0]
    more = f' and {len(hit) - 1} more' if len(hit) > 1 else ''
    return f"clashes with {e.get('subject') or 'another meeting'} {cal.span(e['start'], e.get('end') or '')}{more}"


def free_slots(store, minutes: int = 30, start: date = None, end: date = None, n: int = SLOTS, avoid: tuple = None, events: list = None) -> list:
    """Up to `n` free times of `minutes` on working days between `start` and `end`, inside DAY_START-DAY_END, one per day
    first so the choice is a real one; never before now, never over a busy event, never the `avoid` time itself."""
    tz = cal.tz_of(store)
    now = datetime.now(tz).replace(tzinfo=None, second=0, microsecond=0)
    start, minutes = max(start or now.date(), now.date()), max(15, min(int(minutes or 30), 480))
    end = end if end and end >= start else start + timedelta(days=6)
    evs = events if events is not None else busy(store, days=max(1, (end - now.date()).days + 1))
    picks, seen_days, d = [], set(), start
    while d <= end and len(picks) < n * 4:
        if d.weekday() < 5:
            t = datetime(d.year, d.month, d.day, DAY_START)
            while t + timedelta(minutes=minutes) <= datetime(d.year, d.month, d.day, DAY_END):
                a, b = t, t + timedelta(minutes=minutes)
                s, e = a.strftime('%Y-%m-%d %H:%M'), b.strftime('%Y-%m-%d %H:%M')
                if a >= now and not clashes(store, s, e, events=evs) and not (avoid and s < avoid[1] and e > avoid[0]):
                    picks.append({'start': s, 'end': e, 'label': when(s, e)})
                t += timedelta(minutes=STEP)
        d += timedelta(days=1)
    first = []
    for p in picks:                                   # one a day, earliest first, then the next free time on the earliest day
        if p['start'][:10] not in seen_days: seen_days.add(p['start'][:10]); first.append(p)
    rest = [p for p in picks if p not in first]
    return (first + rest)[:n]


# ── which card answers, and whether it may ─────────────────────────────────────────────────
class NoAccess(RuntimeError):
    """The card reads the calendar but may not write to it: the one line and the place that fixes it."""
    def __init__(self, msg, label, href): super().__init__(msg); self.fix = {'label': label, 'href': href}


def _cfg(c):
    try: return json.loads(c.get('ConfigJson') or '{}') or {}
    except (TypeError, ValueError): return {}


def _claims(tok: str) -> dict:
    """A work account's Graph token is a JWT: its `scp` (signed in) or `roles` (tenant app) say what it may do. A personal
    account's token is opaque - nothing to read, so nothing is refused for it."""
    try:
        part = tok.split('.')[1]
        return json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
    except Exception: return {}


def ms_can_write(cfg: dict, tok: str = None) -> bool:
    """A signed-in card wrote down what Microsoft granted (granted_scope, PW-143): Calendars.ReadWrite or not - and a sign-in
    from before it was asked for recorded only Calendars.Read, so none recorded is not granted either. A tenant app is read
    off its token's roles when there is one to read."""
    if (cfg or {}).get('auth') == 'user':
        return MS_WRITE.lower() in str(cfg.get('granted_scope') or '').lower().split()
    if not tok: return True
    c = _claims(tok)
    held = [str(x).lower() for x in (c.get('roles') or [])] + str(c.get('scp') or '').lower().split()
    return not held or any(h.startswith('calendars.readwrite') for h in held)


def _google_token(cfg: dict) -> tuple:
    """(access token, granted scopes) off the Gmail card's refresh token."""
    from .googlecal import client         # a token signed in on Taskuary's own client renews with it (googlecal.client)
    gid, gsec = client(cfg)
    t = requests.post('https://oauth2.googleapis.com/token', timeout=20,
                      data={'client_id': gid, 'client_secret': gsec, 'refresh_token': cfg.get('google_refresh_token'), 'grant_type': 'refresh_token'})
    if t.status_code != 200: raise RuntimeError(f'Google token failed ({t.status_code})')
    j = t.json() or {}
    return j.get('access_token') or '', str(j.get('scope') or '')


MS_FIX = ('Sign in again', '#connector=outlook')
NO_CALENDAR = 'No calendar is connected - connect one, and the answer goes to it.'
G_FIX = ('Open the Gmail card', '#connector=gmail')
NEED_MS = (f'Calendar access needs to be granted - sign in again on the Outlook card and allow {MS_WRITE} '
           '(a tenant app needs it as an application permission).')
NEED_G = 'Calendar access needs to be granted - the Gmail card needs a Google refresh token with the calendar.events scope.'


def account(store, msg: dict = None, provider: str = '') -> dict:
    """The card that answers for this message - the Outlook card of the mailbox it arrived in, else the Gmail card with a
    Google calendar on it - as {provider, connector, cfg, secret, mailbox}. Raises NoAccess with its fix when none can."""
    box = str((msg or {}).get('SourceName') or (invite_of(msg) or {}).get('mailbox') or '')
    want = provider or (invite_of(msg) or {}).get('provider') or ''
    from . import demo
    if demo.enabled(): return {'provider': want or 'outlook', 'connector': 0, 'cfg': {}, 'secret': None, 'mailbox': box or 'demo'}
    if want != 'google':
        for c in store.connectors_by_type('outlook', with_secret=True):
            if not c.get('Active'): continue
            boxes = [s['Address'] for s in store.list_sources() if s.get('Channel') == 'email' and s.get('Address')
                     and (not s.get('ConnectorId') or s['ConnectorId'] == c['ConnectorId'])]
            mb = next((b for b in boxes if b.lower() == box.lower()), boxes[0] if boxes else '')
            if mb: return {'provider': 'outlook', 'connector': c['ConnectorId'], 'cfg': {**_cfg(c), '_cid': c['ConnectorId']}, 'secret': c.get('Secret'), 'mailbox': mb}
    for c in store.connectors_by_type('gmail', with_secret=True):
        cfg = _cfg(c)
        if c.get('Active') and cfg.get('google_refresh_token'):
            return {'provider': 'google', 'connector': c['ConnectorId'], 'cfg': cfg, 'secret': None, 'mailbox': cfg.get('address') or box}
    # NOTHING CONNECTED IS SAID SO, with the connect step (B15, the email walk 2026-10-29): with no mailbox card at all, Accept on an
    # invite talked about a Google refresh token and "Open the Gmail card", and Find a time offered "Sign in again" - nothing had ever
    # been signed in. The Gmail card's calendar wording is for a Gmail card that is there.
    if want == 'google' and any(c.get('Active') for c in store.connectors_by_type('gmail')): raise NoAccess(NEED_G, *G_FIX)
    fix = connect_fix(store)
    raise NoAccess(NO_CALENDAR, fix['label'], fix['href'])


def require_write(store, acct: dict):
    """Refuse, in one line with its fix, a card that reads the calendar and may not write to it. Nothing is drafted then."""
    from . import demo
    if demo.enabled(): return
    if acct['provider'] == 'google':
        try: _, granted = _google_token(acct['cfg'])
        except Exception as e: raise NoAccess(f'The Google calendar could not be reached ({str(e)[:120]}).', *G_FIX)
        if not any(s in granted.split() for s in G_WRITE): raise NoAccess(NEED_G, *G_FIX)
        return
    cfg = acct['cfg']
    if cfg.get('auth') == 'user':
        if not ms_can_write(cfg): raise NoAccess(NEED_MS, *MS_FIX)
        return
    from .channels import graph_token
    try: tok = graph_token(cfg, acct['secret'])
    except Exception as e: raise NoAccess(f'The Outlook calendar could not be reached ({str(e)[:120]}).', *MS_FIX)
    if not ms_can_write(cfg, tok): raise NoAccess(NEED_MS, *MS_FIX)


# ── drafting the answer (nothing leaves here) ──────────────────────────────────────────────
_HAD = {'accepted': 'accepted', 'tentativelyaccepted': 'tentative', 'tentative': 'tentative'}


def window_of(meet: dict | None) -> tuple:
    """(minutes, first day, last day) a thread's ask names - triage's `meet` - else half an hour in the coming week."""
    m = meet or {}
    def day(k):
        try: return date.fromisoformat(str(m.get(k) or '')[:10])
        except ValueError: return None
    a, b = day('from'), day('to')
    try: mins = int(m.get('minutes') or 30)
    except (TypeError, ValueError): mins = 30
    return mins, a, b or a


def meet_of(m: dict | None) -> dict | None:
    """Triage's reading that the message asks the owner to find a time to meet (message.MeetJson), or None."""
    try: j = json.loads((m or {}).get('MeetJson') or 'null')
    except (TypeError, ValueError): j = None
    return j if isinstance(j, dict) else None


def slots_for(store, msg: dict, act: str) -> dict:
    """The 2-3 free times to offer: for a new time on an invite, its own length in the days around it; for a thread's ask,
    the length and the days it names. {slots, minutes}"""
    tz = cal.tz_of(store); today = datetime.now(tz).date()
    if act == 'propose':
        c = invite_of(msg) or {}
        try: a, b = _dt(c['start']), _dt(c.get('end') or c['start'])
        except (KeyError, ValueError): a = b = None
        mins = int((b - a).total_seconds() // 60) if a and b and b > a else 30
        first = max(today, a.date()) if a else today
        out = free_slots(store, mins, first, first + timedelta(days=6), avoid=(c.get('start'), c.get('end')) if a else None)
        return {'slots': out, 'minutes': mins}
    mins, a, b = window_of(meet_of(msg))
    first = max(today, a) if a else today
    last = b if b and b >= first else first + timedelta(days=6)
    out = free_slots(store, mins, first, last)
    # the day they named is full: the next free times after it, said as such rather than nothing
    if not out: out = free_slots(store, mins, last + timedelta(days=1), last + timedelta(days=7))
    return {'slots': out, 'minutes': mins}


def open_on(store, m: dict) -> tuple:
    """(the invite still waits on the owner's answer, the thread's ask for a time is still open) for one message. A DRAFTED answer
    keeps both open - another press replaces it; an answer the calendar took (its review sent) closes its own."""
    sent = {env_of(r).get('act') for r in store.reviews_for_message(m['MessageId']) if r.get('DeliveryState') == 'sent' and env_of(r).get('kind') == 'calendar'}
    return needs_answer(invite_of(m)) and not sent & {'accept', 'decline', 'propose'}, bool(meet_of(m)) and 'schedule' not in sent


def of_task(store, tid: int) -> dict | None:
    """What the task page's row answers the calendar with: the newest message on the task that is an invite waiting on the owner,
    or a thread asking for a time - {mid, invite, meet, line, clash} - and None once the calendar has the answer or the task is closed."""
    t = store.get_task(int(tid)) or {}
    if not t or t.get('Status') in ('done', 'dropped'): return None
    msgs = [m for m in store.list_messages(int(tid)) if m.get('Direction') != 'out' and m.get('Status') not in ('context', 'history')]
    for m in sorted(msgs, key=lambda m: (str(m.get('SentAt') or ''), m['MessageId']), reverse=True):
        inv, meet = open_on(store, m)
        if not (inv or meet): continue
        c = invite_of(m)
        if inv:
            try: clash = clash_line(store, c['start'], c['end'], skip=c.get('subject') or '') if c.get('start') and not c.get('all_day') else ''
            except Exception as e: clash = ''; logger.debug(f'calwrite: no clash read - {e}')
            return {'mid': m['MessageId'], 'invite': True, 'meet': False, 'clash': clash,
                    'line': f"{c.get('organizer') or 'They'} invited you to {c.get('subject') or 'a meeting'}, {when(c.get('start'), c.get('end'), c.get('all_day'))}"}
        return {'mid': m['MessageId'], 'invite': False, 'meet': True, 'clash': '', 'line': ''}
    return None


def _people(store, msg: dict) -> list:
    """Who a meeting from this thread invites: the sender and everyone on the To and Cc lines but the owner."""
    from .ingest import own_addresses
    me = {a.lower() for a in own_addresses(store)} | {str(msg.get('SourceName') or '').lower()}
    try: rec = json.loads(msg.get('RecipientsJson') or 'null') or {}
    except (TypeError, ValueError): rec = {}
    from .outbound import addrs
    return [a for a in addrs([msg.get('FromEmail'), *(rec.get('to') or []), *(rec.get('cc') or [])]) if a.lower() not in me][:20]


def _title(msg: dict) -> str:
    s = re.sub(r'^\s*((re|fw|fwd|aw)\s*:\s*)+', '', str(msg.get('Subject') or ''), flags=re.I).strip()
    return s[:200] or 'Meeting'


def draft(store, mid: int, act: str, start: str = None, end: str = None, actor: str = 'owner') -> dict:
    """The answer, drafted into the approval queue: a review on the message (and its task) whose envelope is the calendar
    act. {reviewId, taskId, say}. Raises ValueError for what the item cannot carry, NoAccess for a card that may not write."""
    if act not in ACTS: raise ValueError(f'not a calendar answer: {act}')
    msg = store.get_message(int(mid))
    if not msg: raise ValueError('that message is gone')
    c = invite_of(msg)
    if act != 'schedule' and not c: raise ValueError('that message is not a meeting invite')
    if act == 'schedule' and not meet_of(msg): raise ValueError('that message does not ask for a time to meet')
    if act in ('propose', 'schedule'):
        try: a, b = _dt(start), _dt(end)
        except (TypeError, ValueError): raise ValueError('pick a time first')
        if b <= a: raise ValueError('that time ends before it starts')
    acct = account(store, msg)
    require_write(store, acct)
    who = _people(store, msg) if act == 'schedule' else [x for x in [c.get('organizer_email')] if x]
    subject = _title(msg) if act == 'schedule' else c.get('subject') or msg.get('Subject') or 'the meeting'
    at = (start, end) if act in ('propose', 'schedule') else (c.get('start'), c.get('end'))
    clash = clash_line(store, at[0], at[1], skip=subject if act != 'schedule' else '') if at[0] else ''
    env = {'kind': 'calendar', 'channel': 'calendar', 'act': act, 'provider': acct['provider'], 'connector_id': acct['connector'],
           'mailbox': acct['mailbox'], 'subject': subject, 'to': who, 'clash': clash,
           **({'event_id': c.get('event_id'), 'ical_uid': c.get('ical_uid'), 'start': c.get('start'), 'end': c.get('end')} if c and act != 'schedule' else {}),
           **({'new_start': start, 'new_end': end} if act == 'propose' else {}), **({'start': start, 'end': end} if act == 'schedule' else {})}
    line = when(*at, all_day=bool(c and c.get('all_day') and act in ('accept', 'decline')))
    # the card's words, said here once: the time the calendar is told, and for a counter-proposal the time it replaces
    env.update(when=line, **({'was': when(c.get('start'), c.get('end'))} if act == 'propose' and c.get('start') else {}))
    head = {'accept': f'Accept {subject} - {line}', 'decline': f'Decline {subject} - {line}',
            'propose': f"Propose {when(start, end)} for {subject}", 'schedule': f'Invite {", ".join(who) or "them"} to {subject} - {line}'}[act]
    old = next((r for r in store.reviews_for_message(int(mid)) if r.get('Status') == 'pending' and env_of(r).get('kind') == 'calendar'), None)
    if old: store.decide_review(old['ReviewId'], 'rejected', old.get('DraftText'), actor, 'replaced by another calendar answer')
    rid = store.add_review({'TaskId': msg.get('TaskId'), 'MessageId': int(mid), 'Kind': 'outbound', 'Status': 'pending',
                            'DraftText': NOTE[act].format(when=when(start, end) if start else ''), 'Deliver': json.dumps(env),
                            'Reason': f"{head}{' · ' + clash if clash else ''} - press {send_word()} and the calendar is told"})
    store.audit('review', rid, 'calendar_drafted', actor, detail={'act': act, 'provider': acct['provider']})
    return {'reviewId': rid, 'taskId': msg.get('TaskId'), 'say': head + (f' ({clash})' if clash else '') + f'. It waits for your {send_word()}.'}


# ── a meeting asked for in the chat (the owner, 2026-10-28: "schedule a meeting" opened an agent's job) ──────────────────────────
def can_book(store) -> bool:
    """A card that can put a meeting on a calendar is connected - Outlook with a mailbox, or a Gmail card signed in with Google.
    Whether it may WRITE is asked at the press (require_write), where the refusal carries its sign-in."""
    try: account(store); return True
    except NoAccess: return False


def connect_fix(store) -> dict:
    """Where a calendar is connected from: the Gmail card's Sign in with Google when the owner's mail is on a Gmail card, else Outlook."""
    gm = any(c.get('Active') for c in store.connectors_by_type('gmail'))
    return {'label': 'Connect a calendar', 'href': '#connector=gmail' if gm else MS_FIX[1]}


def people_of(store, who) -> tuple:
    """(addresses, names nobody could place) for the people a meeting is with - an address as given, a name through the people search
    the pickers use (peoplesearch.search), its best hit taken. A name with no hit is said back, never guessed into an address."""
    from . import peoplesearch
    names = [w.strip() for w in (who if isinstance(who, (list, tuple)) else re.split(r'[,;]|\band\b', str(who or ''))) if str(w or '').strip()]
    got, miss = [], []
    for n in names[:20]:
        if '@' in n: got.append(n.lower()); continue
        hit = next(iter(peoplesearch.search(store, n[:120], 'email').get('data') or []), None)
        (got.append(hit['to'].lower()) if hit and '@' in str(hit.get('to')) else miss.append(n))
    return list(dict.fromkeys(got)), miss


# ── a meeting set up from New → Meeting (the owner, 2026-10-28: "probably new meeting screen is better") ──────────────────────
# The same road as a thread's Find a time, with no thread: the people, a subject and a length typed, free times read off the owner's
# calendar AND the attendees' where the provider answers for them (Graph getSchedule, Google freeBusy), a pick DRAFTED as a review on a
# task of its own - its Close out holds the invite with Send. Nothing is created on any calendar before that Send (deliver).
LENGTHS, PICKS = (15, 30, 45, 60), 5
NO_CAL = 'No calendar is connected, so a meeting cannot be set up yet - connect one, then find times again.'


def within_days(within: str = '', first=None, last=None, today: date = None) -> tuple:
    """(first, last) day the times are looked for in: 'this_week' is today to Friday (a weekend looks at the week ahead), 'next_week'
    Monday to Friday after it, else the range typed - never before today - else the coming week."""
    today = today or date.today()
    if within == 'next_week':
        mon = today + timedelta(days=7 - today.weekday()); return mon, mon + timedelta(days=4)
    if within == 'this_week':
        return within_days('next_week', today=today) if today.weekday() >= 5 else (today, today + timedelta(days=4 - today.weekday()))
    def day(v):
        try: return date.fromisoformat(str(v or '')[:10])
        except ValueError: return None
    a, b = day(first), day(last)
    if a or b:
        a = max(a or today, today); return a, max(b or a, a)
    return today, today + timedelta(days=6)


def _addrs(people) -> list:
    from .outbound import addrs
    return addrs([p for p in (people if isinstance(people, (list, tuple)) else [people]) if p])[:20]


def _graph_busy(store, acct: dict, people: list, a: datetime, b: datetime, tz) -> dict:
    """{address: [busy events]} off Graph getSchedule, asked as the owner's mailbox - only the people it answered for."""
    from .channels import graph_creds, graph_token
    cfg, sec, _ = graph_creds(store, store.get_connector(int(acct['connector'] or 0), with_secret=True))
    t = lambda d: {'dateTime': d.strftime('%Y-%m-%dT%H:%M:%S'), 'timeZone': cal.tz_name(tz)}
    r = requests.post(f"{GRAPH}/users/{acct['mailbox']}/calendar/getSchedule", timeout=20,
                      data=json.dumps({'schedules': people, 'startTime': t(a), 'endTime': t(b), 'availabilityViewInterval': 30}),
                      headers={'Authorization': f'Bearer {graph_token(cfg, sec)}', 'Content-Type': 'application/json',
                               'Prefer': f'outlook.timezone="{cal.tz_name(tz)}"'})
    if r.status_code != 200: raise RuntimeError(f'Graph getSchedule refused ({r.status_code})')
    out = {}
    for v in (r.json() or {}).get('value') or []:
        if v.get('error') or not v.get('scheduleId'): continue
        out[str(v['scheduleId']).lower()] = [{'start': _local(i.get('start'), tz), 'end': _local(i.get('end'), tz), 'subject': 'busy', 'all_day': False}
                                             for i in v.get('scheduleItems') or [] if str(i.get('status') or 'busy').lower() not in ('free', 'workingelsewhere')]
    return out


def _g_local(s: str, tz) -> str:
    try: d = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except ValueError: return str(s)[:16].replace('T', ' ')
    return (d.astimezone(tz) if d.tzinfo and tz else d).strftime('%Y-%m-%d %H:%M')


def _google_busy(acct: dict, people: list, a: datetime, b: datetime, tz) -> dict:
    """{address: [busy events]} off Google freeBusy - a calendar it may not see comes back with errors and is left out."""
    from .googlecal import access_token
    r = requests.post('https://www.googleapis.com/calendar/v3/freeBusy', timeout=20,
                      headers={'Authorization': f"Bearer {access_token(acct['cfg'])}", 'Content-Type': 'application/json'},
                      data=json.dumps({'timeMin': a.replace(tzinfo=tz).isoformat(), 'timeMax': b.replace(tzinfo=tz).isoformat(),
                                       'timeZone': cal.tz_name(tz), 'items': [{'id': p} for p in people]}))
    if r.status_code != 200: raise RuntimeError(f'Google freeBusy refused ({r.status_code})')
    return {str(k).lower(): [{'start': _g_local(x.get('start'), tz), 'end': _g_local(x.get('end'), tz), 'subject': 'busy', 'all_day': False}
                             for x in v.get('busy') or []]
            for k, v in ((r.json() or {}).get('calendars') or {}).items() if not v.get('errors')}


def their_busy(store, acct: dict, people: list, first: date, last: date) -> tuple:
    """(the attendees' busy times, who the provider answered for, who it did not). A failed read is everyone unread - the times
    are then the owner's alone, and the screen says whose calendars were not seen."""
    from . import demo
    people = [p.lower() for p in people]
    if not people: return [], [], []
    if demo.enabled(): return [], people, []
    tz = cal.tz_of(store)
    a, b = datetime(first.year, first.month, first.day), datetime(last.year, last.month, last.day) + timedelta(days=1)
    try: got = _google_busy(acct, people, a, b, tz) if acct['provider'] == 'google' else _graph_busy(store, acct, people, a, b, tz)
    except Exception as e: logger.info(f"calwrite: the attendees' free/busy was not read - {e}"); got = {}
    return [e for p in people for e in got.get(p, [])], [p for p in people if p in got], [p for p in people if p not in got]


def suggest(store, people, minutes: int = 30, within: str = '', first=None, last=None, n: int = PICKS) -> dict:
    """The free times New → Meeting offers: `n` slots of `minutes` in working hours, one a day first, clear on the owner's calendar
    and on every attendee's the provider answered for - and when the days asked are full, the next free times after them (`later`).
    Raises NoAccess with its fix for a card that may not write: the press says so before a pick, not after."""
    acct = account(store); require_write(store, acct)
    tz = cal.tz_of(store); today = datetime.now(tz).date()
    try: mins = int(minutes)
    except (TypeError, ValueError): mins = 30
    mins = mins if mins in LENGTHS else 30
    a, b = within_days(within, first, last, today)
    theirs, read, unread = their_busy(store, acct, _addrs(people), a, b + timedelta(days=7))
    evs = busy(store, days=(b - today).days + 8) + theirs
    out, later = free_slots(store, mins, a, b, n=n, events=evs), False
    if not out: out, later = free_slots(store, mins, b + timedelta(days=1), b + timedelta(days=7), n=n, events=evs), True
    return {'slots': out, 'minutes': mins, 'first': str(a), 'last': str(b), 'later': later, 'read': read, 'unread': unread, 'provider': acct['provider']}


def name_of(store, addr: str) -> str:
    """What to call someone in a title: the name the mail, the org chart or the directory knows them by, else the address."""
    from . import peoplesearch
    try: hit = next((r for r in peoplesearch.known(store, 'email') if r['to'] == addr.lower() and r.get('name')), None)
    except Exception: hit = None
    return hit['name'] if hit else addr


def _and(xs: list) -> str: return ' and '.join(xs) if len(xs) < 3 else f"{', '.join(xs[:-1])} and {xs[-1]}"


def draft_new(store, people, subject: str, start: str, end: str, note: str = '', actor: str = 'owner') -> dict:
    """New → Meeting's pick: a task "Meeting with <who> about <subject>" whose Close out holds the invite, drafted as a review whose
    envelope is the calendar's 'schedule' act - the same one a thread's Find a time drafts. {taskId, ref, reviewId, title, say}.
    Raises ValueError for what is missing, NoAccess for a card that may not write - and then nothing is made."""
    from .store import task_ref
    to, subject = _addrs(people), ' '.join(str(subject or '').split())[:200]
    if not to: raise ValueError('add who the meeting is with')
    if not subject: raise ValueError('say what the meeting is about')
    try: a, b = _dt(start), _dt(end)
    except (TypeError, ValueError): raise ValueError('pick a time first')
    if b <= a: raise ValueError('that time ends before it starts')
    acct = account(store); require_write(store, acct)
    title = f"Meeting with {_and([name_of(store, x) for x in to])} about {subject}"[:300]
    line, clash = when(start, end), clash_line(store, start, end)
    tid = store.create_task({'Title': title, 'Summary': f"{subject} - {line}, with {', '.join(to)}.", 'Kind': 'task', 'Status': 'open',
                             'Priority': 'normal', 'Source': 'meeting'}, actor)
    env = {'kind': 'calendar', 'channel': 'calendar', 'act': 'schedule', 'provider': acct['provider'], 'connector_id': acct['connector'],
           'mailbox': acct['mailbox'], 'subject': subject, 'to': to, 'clash': clash, 'start': start, 'end': end, 'when': line}
    head = f'Invite {", ".join(to)} to {subject} - {line}'
    rid = store.add_review({'TaskId': tid, 'Kind': 'outbound', 'Status': 'pending', 'DraftText': str(note or '').strip()[:4000],
                            'Deliver': json.dumps(env), 'Reason': f"{head}{' · ' + clash if clash else ''} - press {send_word()} and the calendar is told"})
    store.audit('review', rid, 'calendar_drafted', actor, detail={'act': 'schedule', 'provider': acct['provider'], 'new': True})
    return {'taskId': tid, 'ref': task_ref(tid), 'reviewId': rid, 'title': title,
            'say': f"{task_ref(tid)} - {head}" + (f' ({clash})' if clash else '') + f'. The invite waits in Close out for your {send_word()}.'}


def env_of(r) -> dict:
    """A review's delivery envelope - {} when it has none."""
    try: return json.loads(r.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): return {}


def done_line(env: dict, note: str = '') -> str:
    """What the task's history says once the calendar took it."""
    to, s = ', '.join(env.get('to') or []) or 'the organizer', env.get('subject') or 'the meeting'
    said = {'accept': f'Accepted {s}', 'decline': f'Declined {s}',
            'propose': f"Proposed {when(env.get('new_start'), env.get('new_end'))} for {s}",
            'schedule': f"Invited {to} to {s}, {when(env.get('start'), env.get('end'))}"}.get(env.get('act'), f'Answered {s}')
    return f"{said} - {to if env.get('act') != 'schedule' else 'they are'} told by the calendar." + (f' Note: {note.strip()}' if str(note or '').strip() else '')


# ── the owner's Send: the one place a calendar is written ───────────────────────────────────
def _ms_time(s: str, tz) -> dict: return {'dateTime': _dt(s).strftime('%Y-%m-%dT%H:%M:%S'), 'timeZone': cal.tz_name(tz)}


def _g_time(s: str, tz) -> dict: return {'dateTime': _dt(s).replace(tzinfo=tz).isoformat(), 'timeZone': cal.tz_name(tz)}


def _ok(r, what: str):
    if r.status_code >= 300: raise RuntimeError(f'the calendar refused to {what} ({r.status_code}): {str(r.text or "")[:200]}')


def deliver(store, env: dict, note: str) -> dict:
    """Tell the calendar what the owner approved. Called from verdicts._send_snapshot only - behind Send, never before it."""
    act, tz, note = env.get('act'), cal.tz_of(store), str(note or '').strip()
    c = store.get_connector(int(env.get('connector_id') or 0), with_secret=True)
    if not c or not c.get('Active'): raise RuntimeError('the calendar card it was drafted for is gone or switched off')
    to = list(env.get('to') or [])
    if env.get('provider') == 'google':
        cfg = _cfg(c)
        tok, _ = _google_token(cfg)
        h = {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}
        base = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'
        if act == 'schedule':
            body = {'summary': env.get('subject'), 'description': note, 'start': _g_time(env['start'], tz), 'end': _g_time(env['end'], tz),
                    'attendees': [{'email': a} for a in to]}
            r = requests.post(base, params={'sendUpdates': 'all'}, headers=h, timeout=30, data=json.dumps(body)); _ok(r, 'create the meeting')
            return {'channel': 'calendar', 'to': to, 'act': act, 'id': (r.json() or {}).get('id')}
        r = requests.get(base, params={'iCalUID': env.get('ical_uid')}, headers=h, timeout=20); _ok(r, 'find the meeting')
        ev = next(iter((r.json() or {}).get('items') or []), None)
        if not ev: raise RuntimeError('the meeting is not on the Google calendar any more')
        me = str(cfg.get('address') or '').lower()
        status = {'accept': 'accepted', 'decline': 'declined', 'propose': 'tentative'}[act]
        if act == 'propose': note = (note + ' ' if note else '') + f"(Proposed: {when(env['new_start'], env['new_end'])})"
        att = [{**a, 'responseStatus': status, **({'comment': note} if note else {})} if a.get('self') or str(a.get('email') or '').lower() == me else a
               for a in ev.get('attendees') or []]
        r = requests.patch(f"{base}/{ev['id']}", params={'sendUpdates': 'all'}, headers=h, timeout=30, data=json.dumps({'attendees': att}))
        _ok(r, f'{act} the meeting')
        return {'channel': 'calendar', 'to': to, 'act': act}
    from .channels import graph_creds, graph_token
    cfg, sec, _ = graph_creds(store, c)
    h = {'Authorization': f'Bearer {graph_token(cfg, sec)}', 'Content-Type': 'application/json'}
    box = env.get('mailbox')
    if act == 'schedule':
        body = {'subject': env.get('subject'), 'body': {'contentType': 'text', 'content': note}, 'start': _ms_time(env['start'], tz),
                'end': _ms_time(env['end'], tz), 'attendees': [{'emailAddress': {'address': a}, 'type': 'required'} for a in to]}
        r = requests.post(f'{GRAPH}/users/{box}/events', headers=h, timeout=30, data=json.dumps(body)); _ok(r, 'create the meeting')
        return {'channel': 'calendar', 'to': to, 'act': act, 'id': (r.json() or {}).get('id')}
    if not env.get('event_id'): raise RuntimeError('the invite carries no meeting to answer')
    verb = {'accept': 'accept', 'decline': 'decline', 'propose': 'tentativelyAccept'}[act]
    body = {'comment': note, 'sendResponse': True,
            **({'proposedNewTime': {'start': _ms_time(env['new_start'], tz), 'end': _ms_time(env['new_end'], tz)}} if act == 'propose' else {})}
    r = requests.post(f"{GRAPH}/users/{box}/events/{env['event_id']}/{verb}", headers=h, timeout=30, data=json.dumps(body))
    _ok(r, f'{SAID[act].lower()} the invite')
    return {'channel': 'calendar', 'to': to, 'act': act}
