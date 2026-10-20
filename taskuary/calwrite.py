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
from datetime import datetime, timedelta, date
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
    try: src = ZoneInfo('UTC' if zone.upper() in ('', 'UTC') else zone)
    except Exception: return d.strftime('%Y-%m-%d %H:%M')
    return d.replace(tzinfo=src).astimezone(tz).strftime('%Y-%m-%d %H:%M') if tz is not None else d.strftime('%Y-%m-%d %H:%M')


def from_graph(m: dict, mailbox: str, tz=None) -> dict:
    """An eventMessage (with its event expanded, when the poll fetched it) as the stored invite."""
    ev = m.get('event') or {}
    org = ((ev.get('organizer') or m.get('from') or {}).get('emailAddress') or {})
    resp = str(((ev.get('responseStatus') or {}).get('response')) or '').lower()
    return {'kind': _ms_kind(m), 'provider': 'outlook', 'mailbox': mailbox, 'event_id': ev.get('id') or '', 'ical_uid': ev.get('iCalUId') or '',
            'update': bool(m.get('previousStartDateTime') or m.get('previousEndDateTime') or m.get('previousLocation')),
            'answered': resp not in ('', 'none', 'notresponded'), 'asks': m.get('responseRequested') is not False and ev.get('responseRequested') is not False,
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
    if v.endswith('Z'): d = d.replace(tzinfo=ZoneInfo('UTC'))
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
    """The owner's move: a request, not an update, that nobody has answered and that asks for one."""
    return bool(c) and c.get('kind') == 'request' and not c.get('update') and not c.get('answered') and c.get('asks', True) is not False


def when(start: str, end: str = '', all_day: bool = False) -> str:
    """'Thu Oct 22, 2:00-3:00 PM' - the day said once, the AM/PM once where both ends share it."""
    try: d = datetime.fromisoformat(str(start)[:16])
    except ValueError: return str(start or '')
    day = f"{d.strftime('%a %b')} {d.day}"
    return f'{day}, all day' if all_day else f"{day}, {cal.span(str(start), str(end or ''))}"


# ── the owner's time ─────────────────────────────────────────────────────────────────────
_BUSY = {'at': 0.0, 'data': None}
BUSY_TTL = 300


def busy(store, days: int = 14) -> list:
    """The owner's busy events from now for `days` days, every calendar the cards reach - cached like the reply's read. The
    demo has no calendar behind it, so it has a scripted week (demo.agenda)."""
    from . import demo
    if demo.enabled(): return demo.agenda()
    if _BUSY['data'] is not None and time.time() - _BUSY['at'] < BUSY_TTL: return _BUSY['data']
    tz = cal.tz_of(store)
    ag = cal.agenda(store, days=days, start=datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0))
    _BUSY.update(at=time.time(), data=ag['events'])
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
    t = requests.post('https://oauth2.googleapis.com/token', timeout=20,
                      data={'client_id': cfg.get('google_client_id'), 'client_secret': cfg.get('google_client_secret'),
                            'refresh_token': cfg.get('google_refresh_token'), 'grant_type': 'refresh_token'})
    if t.status_code != 200: raise RuntimeError(f'Google token failed ({t.status_code})')
    j = t.json() or {}
    return j.get('access_token') or '', str(j.get('scope') or '')


MS_FIX = ('Sign in again', '#connector=outlook')
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
    if want == 'google': raise NoAccess(NEED_G, *G_FIX)
    raise NoAccess('No calendar is connected to answer from - sign in on the Outlook card, or add a Google calendar to the Gmail card.', *MS_FIX)


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


def of_task(store, tid: int) -> dict | None:
    """What the task page's row answers the calendar with: the newest message on the task that is an invite waiting on the owner,
    or a thread asking for a time - {mid, invite, meet, line, clash} - and None once an answer is drafted or the task is closed."""
    t = store.get_task(int(tid)) or {}
    if not t or t.get('Status') in ('done', 'dropped'): return None
    msgs = [m for m in store.list_messages(int(tid)) if m.get('Direction') != 'out' and m.get('Status') not in ('context', 'history')]
    for m in sorted(msgs, key=lambda m: (str(m.get('SentAt') or ''), m['MessageId']), reverse=True):
        c, meet = invite_of(m), meet_of(m)
        if not (needs_answer(c) or meet): continue
        if any(r.get('Status') == 'pending' and env_of(r).get('kind') == 'calendar' for r in store.reviews_for_message(m['MessageId'])): return None
        if needs_answer(c):
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
