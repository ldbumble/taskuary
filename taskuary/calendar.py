"""The owner's calendar, read where a reply is about time.

"Tuesday at 1 works for me too" was drafted with no idea whether Tuesday at 1 was free - the
responder had the thread, the voice and the rules, and not the one fact the question turned
on. So a reply whose thread talks about time gets the owner's busy slots for the next
DAYS days in its prompt, with the rule that a busy slot is never offered and a clash is said
out loud with the nearest free alternative.

Two sources, both read-only, both riding credentials already on a connector card:
- Outlook: Microsoft Graph `calendarView` on every mailbox the Outlook card polls, with the
  same app registration the mail comes through - it needs the APPLICATION permission
  Calendars.Read granted once (Test on the card says whether it is).
- Google: the Gmail card is IMAP (an app password), which carries no calendar access, so a
  Google calendar needs an OAuth client + refresh token pasted on the card (google_client_id,
  google_client_secret, google_refresh_token). When present it is read; when absent it is
  simply not one of the sources.
The same read is a tool (`calendar` in reports.REGISTRY) so an agent can check before it
commits anyone to a time.
"""
import json, re, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests
from loguru import logger

DAYS = 14
MAX_EVENTS = 60
GRAPH = 'https://graph.microsoft.com/v1.0'
# words that make a thread about TIME - only then is the calendar fetched (a Graph call per draft otherwise)
SCHEDULING = re.compile(r'\b(availab\w*|free|busy|meet\w*|call|schedul\w*|calendar|slot|appointment|'
                        r'tomorrow|today|tonight|next week|this week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|'
                        r'\d{1,2}(:\d{2})?\s*(am|pm)|\d{1,2}[/-]\d{1,2})\b', re.I)


def about_time(text: str) -> bool: return bool(SCHEDULING.search(text or ''))


def tz_of(store):
    name = (store.get_settings().get('timezone') or '').strip()
    try: return ZoneInfo(name) if name else datetime.now().astimezone().tzinfo
    except Exception: return datetime.now().astimezone().tzinfo


def tz_name(tz) -> str:
    """What to tell a calendar API: the IANA key when the owner set one (Settings -> Display ->
    Timezone), else the machine's own zone name - on Windows that is "Eastern Standard Time",
    which Graph accepts as-is. Blank was sent as UTC and every meeting read five hours late."""
    return getattr(tz, 'key', None) or (time.tzname[0] if time.tzname and time.tzname[0] else 'UTC')


def _iso(d): return d.strftime('%Y-%m-%dT%H:%M:%S')


def outlook_events(cfg: dict, secret: str, mailboxes: list, start: datetime, end: datetime, tz) -> list:
    """Graph calendarView for each mailbox - the poller's own app, one more permission."""
    from .channels import graph_token
    tok = graph_token(cfg, secret)
    out = []
    for mb in mailboxes:
        r = requests.get(f'{GRAPH}/users/{mb}/calendarView', timeout=20,
                         headers={'Authorization': f'Bearer {tok}', 'Prefer': f'outlook.timezone="{tz_name(tz)}"'},
                         params={'startDateTime': _iso(start), 'endDateTime': _iso(end), '$top': MAX_EVENTS,
                                 '$orderby': 'start/dateTime', '$select': 'subject,start,end,isAllDay,showAs,location,organizer'})
        if r.status_code == 403:
            raise RuntimeError(f'Graph refused the calendar for {mb} (403) - grant the APPLICATION permission Calendars.Read on the app and consent')
        if r.status_code != 200: raise RuntimeError(f'calendar read failed for {mb} ({r.status_code}): {r.text[:200]}')
        for e in r.json().get('value') or []:
            if (e.get('showAs') or '').lower() == 'free': continue
            out.append({'start': (e.get('start') or {}).get('dateTime', '')[:16].replace('T', ' '),
                        'end': (e.get('end') or {}).get('dateTime', '')[:16].replace('T', ' '),
                        'subject': e.get('subject') or '(no title)', 'all_day': bool(e.get('isAllDay')),
                        'status': (e.get('showAs') or 'busy').lower(), 'where': ((e.get('location') or {}).get('displayName') or '')[:60],
                        'mailbox': mb})
    return out


def google_events(cfg: dict, start: datetime, end: datetime, tz) -> list:
    """Google Calendar with an OAuth refresh token from the card - primary calendar, expanded."""
    cid, sec, rt = cfg.get('google_client_id'), cfg.get('google_client_secret'), cfg.get('google_refresh_token')
    if not (cid and sec and rt): return []
    t = requests.post('https://oauth2.googleapis.com/token', timeout=20,
                      data={'client_id': cid, 'client_secret': sec, 'refresh_token': rt, 'grant_type': 'refresh_token'})
    if t.status_code != 200: raise RuntimeError(f'Google token failed ({t.status_code}): {t.text[:200]}')
    r = requests.get('https://www.googleapis.com/calendar/v3/calendars/primary/events', timeout=20,
                     headers={'Authorization': f"Bearer {t.json()['access_token']}"},
                     params={'timeMin': start.astimezone(tz).isoformat(), 'timeMax': end.astimezone(tz).isoformat(),
                             'singleEvents': 'true', 'orderBy': 'startTime', 'maxResults': MAX_EVENTS,
                             'timeZone': tz_name(tz)})
    if r.status_code != 200: raise RuntimeError(f'Google calendar read failed ({r.status_code}): {r.text[:200]}')
    out = []
    for e in r.json().get('items') or []:
        if e.get('transparency') == 'transparent' or e.get('status') == 'cancelled': continue
        s, en = e.get('start') or {}, e.get('end') or {}
        out.append({'start': (s.get('dateTime') or s.get('date') or '')[:16].replace('T', ' '),
                    'end': (en.get('dateTime') or en.get('date') or '')[:16].replace('T', ' '),
                    'subject': e.get('summary') or '(no title)', 'all_day': 'date' in s, 'status': 'busy',
                    'where': (e.get('location') or '')[:60], 'mailbox': cfg.get('address') or 'google'})
    return out


def agenda(store, days: int = DAYS) -> dict:
    """{events, errors, sources, start, end, tz} - every calendar the cards can reach."""
    tz = tz_of(store)
    now = datetime.now(tz).replace(second=0, microsecond=0)
    start, end = now, now + timedelta(days=days)
    events, errors, sources = [], [], []
    ol = store.get_connector_by_type('outlook', with_secret=True)
    if ol and ol.get('Active'):
        boxes = [s['Address'] for s in store.list_sources() if s.get('Channel') == 'email' and s.get('Address')
                 and (not s.get('ConnectorId') or s['ConnectorId'] == ol['ConnectorId'])]
        if boxes:
            sources.append(f"outlook: {', '.join(boxes)}")
            try: events += outlook_events(json.loads(ol.get('ConfigJson') or '{}'), ol.get('Secret'), boxes, start, end, tz)
            except Exception as e: errors.append(str(e)[:240])
    gm = store.get_connector_by_type('gmail', with_secret=True)
    if gm and gm.get('Active'):
        cfg = json.loads(gm.get('ConfigJson') or '{}')
        if cfg.get('google_refresh_token'):
            sources.append(f"google: {cfg.get('address') or 'primary'}")
            try: events += google_events(cfg, start, end, tz)
            except Exception as e: errors.append(str(e)[:240])
    events.sort(key=lambda e: e['start'])
    return {'events': events[:MAX_EVENTS], 'errors': errors, 'sources': sources, 'start': _iso(start), 'end': _iso(end),
            'tz': tz_name(tz)}


def render(ag: dict) -> str:
    """The agenda as a prompt reads it: one line per event, grouped by day, free days named."""
    if not ag['sources']: return ''
    by_day = {}
    for e in ag['events']: by_day.setdefault(e['start'][:10], []).append(e)
    start = datetime.fromisoformat(ag['start'][:19])
    lines = [f"Busy times, {ag['tz']}, {ag['start'][:10]} to {ag['end'][:10]} (from {'; '.join(ag['sources'])}):"]
    for i in range((datetime.fromisoformat(ag['end'][:19]) - start).days + 1):
        d = (start + timedelta(days=i)).strftime('%Y-%m-%d'); dow = (start + timedelta(days=i)).strftime('%a')
        evs = by_day.get(d) or []
        if not evs: lines.append(f'  {dow} {d}: free all day'); continue
        lines.append(f'  {dow} {d}:')
        for e in evs:
            when = 'all day' if e['all_day'] else f"{e['start'][11:16]}-{e['end'][11:16]}"
            lines.append(f"    {when} · {e['subject']}" + (f" ({e['status']})" if e['status'] not in ('busy', '') else '') + (f" · {e['where']}" if e['where'] else ''))
    for err in ag['errors']: lines.append(f'  COULD NOT READ: {err}')
    return '\n'.join(lines)


def context_for(store, text: str) -> str:
    """The paragraph the responder gets when the thread is about time - or '' when it is not,
    the switch is off, or no card can reach a calendar. A fetch that fails still returns a
    paragraph: it says the calendar could not be read, so the draft does not claim a free slot."""
    if store.get_settings().get('calendar_enabled', '1') != '1' or not about_time(text): return ''
    try: ag = agenda(store)
    except Exception as e:
        logger.warning(f'calendar: {e}'); return ''
    body = render(ag)
    if not body: return ''
    return ('\n\nYOUR CALENDAR - this thread is about time, so check before you answer. A time that is '
            'busy below is never offered or accepted; if the time asked about is busy, say so plainly and offer '
            'the nearest free one. If the calendar could not be read, say you will confirm rather than '
            'claiming availability.\n' + body)


_UPCOMING = {'at': 0.0, 'data': None}
UPCOMING_TTL = 300          # seconds - the Timeline polls for the countdown far more often than Graph should be asked

def upcoming(store, hours: int = 36, force: bool = False) -> dict:
    """The next events for the Timeline's 'coming up' band: {events, tz, errors, fetched}. Events
    already running (started within the last 15 min) stay so a meeting you are late for still shows."""
    if store.get_settings().get('calendar_enabled', '1') != '1': return {'events': [], 'tz': tz_name(tz_of(store)), 'errors': [], 'fetched': None}
    if not force and _UPCOMING['data'] and time.time() - _UPCOMING['at'] < UPCOMING_TTL: return _UPCOMING['data']
    ag = agenda(store, days=max(1, (hours + 23) // 24))
    tz = tz_of(store); now = datetime.now(tz).replace(tzinfo=None)
    keep = []
    for e in ag['events']:
        try: st = datetime.fromisoformat(e['start']); en = datetime.fromisoformat(e['end']) if e.get('end') else st
        except ValueError: continue
        if e['all_day'] and st.date() >= now.date() or (en >= now - timedelta(minutes=15) and st <= now + timedelta(hours=hours)):
            keep.append(e)
    data = {'events': keep[:10], 'tz': ag['tz'], 'errors': ag['errors'], 'fetched': datetime.now().isoformat(timespec='seconds')}
    _UPCOMING.update(at=time.time(), data=data)
    return data


def run_calendar(cfg: dict):
    """{"days": 7} - the owner's busy times for the next N days (default 14), every calendar the
    cards can reach. Read-only."""
    st = cfg.get('store')
    if st is None: raise RuntimeError('the calendar tool reads the connector cards - it needs the store')
    ag = agenda(st, int(cfg.get('days') or DAYS))
    head = f"{len(ag['events'])} event(s) in the next {int(cfg.get('days') or DAYS)} days" + (f" · {len(ag['errors'])} calendar(s) unreadable" if ag['errors'] else '')
    return head, (render(ag) or 'no calendar is connected - the Outlook card reads calendars once Calendars.Read is granted')
