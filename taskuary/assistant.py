"""The assistant on the Timeline: a check every 30 minutes, a post only when it has something to say.

Triage judges each message as it arrives and then nothing ever spoke up later - the reply the
owner sent on Monday and never heard back on, the meeting in two hours with five mails of
history behind it, the task that went quiet. This is the voice that does: on its own clock it gathers what the hub can see
(followups: the owner wrote last and asked for something; prep: meetings ahead, with what came
before them; cold: work nothing has touched; and its own ideas
from the day's mail), asks the model for its read GIVEN WHAT IT ALREADY SAID, and posts only what
is new as ONE row on the Timeline. The owner can talk back to every line; a correction or question
gets an answer and becomes context for later checks. A concrete suggestion may also offer Follow up
(the chase is drafted in Review) or Make it a task.

It never repeats itself: every idea has a key and a state (idea table). Said once with the same
facts is said; dismissed stays dismissed until the facts change; snoozed sleeps. Those legacy states
remain understood, but the panel asks the owner to explain what is wrong instead of exposing opaque verdict buttons.

Nothing sits pinned above the Timeline: the assistant IS its rows, each posted for something
specific, and what is open, in flight and waiting on the owner is the Morning digest's job on its
own clock (the owner, 2026-08-30: the status strip with its counts and 'ask now' was noise). The
thresholds and the producers are settings (assistant_*); the clock and the instruction are the
'Assistant' report on the Reports tab.

What it READS decides what it can say (the owner, 2026-08-30: "keep iterating from prompt to the data
it brings in until it says something useful and surprising"). Handed only subject lines and counts it
wrote 'no content given' in its own notes; so the check now reads WHAT PEOPLE SAID (the words of every
human thread of the last two days, the owner's lines marked), who is OUT OF OFFICE (from auto-replies -
a chase to someone away is worse than silence), the CALENDAR, and the machines' mail with each report's
schedule and each failure's cause beside the count. That is where "Yittie said exporting freezes the
app - and she is in Monday's meeting" comes from.

It also leaves itself a NOTE: each check ends with what it looked at and found nothing in, when
something becomes worth raising, whatever it would otherwise work out again - and the next check
starts by reading it (assistant_notes). Half-hourly checks are cheap only if each one does not
start from zero; a quiet check still rewrites the note, it just posts nothing. How it SPEAKS is
COUNSEL.md (Docs tab) - the owner edits that to change its voice and what it takes a position on;
the report's prompt is what it watches for.
"""
import json, re, threading
from datetime import datetime, timedelta
from loguru import logger

from .store import task_ref

CHANNEL = 'assistant'
PRODUCERS = ('followup', 'promise', 'prep', 'cold', 'idea')
DAYS = 30                  # how far back followups and promises are read
MAX_LINES = 5              # lines per post by default - a post nobody reads to the end is a post that failed
POST_TOKENS = 900
PEOPLE_THREADS, PEOPLE_CHARS = 14, 5200   # what people said: threads shown, and the block's ceiling
_LOCK = threading.Lock()   # one check at a time: two clocks firing in the same second posted the same line twice (2026-08-29 23:59:02)
# the owner's last word on a thread ASKED for something - that is what a chase is for...
_ASKS = re.compile(r'\?|\b(let me know|could you|can you|would you|please (send|confirm|share|advise|review|check)|get back to me|'
                   r'by (monday|tuesday|wednesday|thursday|friday|eod|end of (day|week)|tomorrow|next week))\b', re.I)
# ...or PROMISED something, which is the owner's own open item, not the other side's
_PROMISE = re.compile(r"\b(i('ll| will)|i'?m going to|let me) (send|get|have|follow|circle|check|share|update|confirm|look|review|come back|revert)\b", re.I)

# The editable instruction - what a real assistant watches for. Seeded as the 'Assistant' report
# on the Reports tab (store.__init__), so the owner edits it there like the Morning digest's;
# this copy is the default and the fallback. CONTRACT (the JSON shape) stays in code.
PROMPT = (
    'You are my assistant; every 30 minutes you check in. Tell me only what a sharp human assistant who had READ everything '
    'would lean over and say - never a summary of my inbox, never a count I can see myself. A good line connects two things I '
    'have not connected, or names the one thing I am about to miss. Read, in this order of worth:\n'
    '1. WHAT PEOPLE SAID - the actual words, by thread. The ask buried in a chat ("can you fill out the form?") that got a '
    'reply but not the thing itself; the colleague mentioning in passing that a system fails "every day 4-5"; the person '
    'answering a question nobody asked me; the thread where the last word is theirs and it wants something from me. Say who, '
    'what, and what I would do - "Mindy asked for X on Thursday; I would send it before her Monday 1pm".\n'
    '2. What I am waiting on and have not chased (CANDIDATES followup) - but check OUT OF OFFICE first: a chase to someone '
    'who is away is worse than silence; say when they are back instead.\n'
    '3. What I promised and have not done (promise): the date I gave, and whether it has passed.\n'
    '4. CALENDAR: for each meeting in the next two days, what in the mail and chats bears on it - the person in the room '
    'who asked me something this week, the thread it will be about. A recurring standup with nothing behind it needs no line.\n'
    '5. Work gone quiet (cold): push it or drop it - say which.\n'
    '6. What the machines are telling me, read not counted: a report marked FAILED says WHY (the error is in the line) - name '
    'the cause; a job that fails the same way N times is one finding, with the cause; a report whose every run says "0 rows" '
    'is a report nobody needs. Reports carry their schedule: "on app start" firing 20 times means the app was started 20 '
    'times, not that the scheduler is broken.\n'
    '7. My own work (DONE THIS WEEK, OPEN WORK): the fix that keeps coming back, the task that closed without shipping, the '
    'process change worth proposing. Name the evidence: TQ-ref, count, sender. Never restate what I did.\n'
    'Be useful, not busy: a check with nothing NEW posts nothing, and most checks are that. When you do speak, prefer the '
    'specific over the general: a name, a date, a quoted phrase, a cause. One idea about my own work a day is right; three is '
    'noise. Never repeat anything under ALREADY SAID, reworded or not - but a fact that CHANGES an earlier line (they are out '
    'of office; the failure has a cause; they answered) is new and worth one line.\n'
    'End every check with a note to your next one: what you looked at and found nothing in, when something becomes worth '
    'raising (a date, a length of silence), anything you would otherwise have to work out again - facts, never rules.')
# a stock prompt still starting like one of these is healed to PROMPT (store.__init__)
OLD_PROMPT_HEADS = ('You are my assistant. Once an hour,', 'You are my assistant. Every 20 minutes you check in;',
                    'You are my assistant. Every 30 minutes you check in;')


def cfg(store) -> dict:
    s = store.get_settings()
    def n(k, d):
        try: return max(0, int(s.get(k) or d))
        except (TypeError, ValueError): return d
    raw = s.get('assistant_producers')
    prod = {p.strip() for p in (raw if raw is not None else ','.join(PRODUCERS)).split(',') if p.strip()}
    return {'followup_h': n('assistant_followup_hours', 24), 'cold_d': n('assistant_cold_days', 3), 'max': max(1, n('assistant_max_lines', MAX_LINES)),
            'producers': prod, 'last': s.get('assistant_last_run') or ''}


def source(store) -> dict | None:
    """The 'Assistant' row on the Reports tab: its schedule, its instruction, and whether it is on at
    all - the same three things the Morning digest keeps there. None when the owner deleted it."""
    for src in store.list_sources(active_only=False):
        if src.get('Channel') != 'report': continue
        try: c = json.loads(src.get('ConfigJson') or '{}')
        except ValueError: continue
        if c.get('type') == 'assistant': return src | {'cfg': c}
    return None


def _ts(s): return str(s or '')[:19].replace('T', ' ')
def _since(days): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
def _short(s, n=90): return ' '.join(str(s or '').split())[:n]
def _dt(s):
    try: return datetime.fromisoformat(_ts(s))
    except ValueError: return None
def _when(s) -> str:
    """'Thu 28 Aug 11:21' - a day name the model can hold against a calendar, no year."""
    d = _dt(s); return d.strftime('%a %d %b %H:%M') if d else str(s or '')[:16]
# the corporate wrapper around a body, not the sender's words: the external-mail banner and the "you don't often get email" hint
_BANNER = re.compile(r"(this email was sent from outside of[^*\n]*(\*\*[^*]*\*\*)?\s*|\[?\s*you don'?t often get email from \S+\.?( learn why this is important( at \S+)?)?\s*\]?)", re.I)
def _gist(body, n=180) -> str:
    """The sender's own words, one line: banner, legal footer and signature gone (triage.strip_boilerplate)."""
    from .triage import strip_boilerplate
    return _short(strip_boilerplate(_BANNER.sub('', str(body or ''))), n)

_OOO = re.compile(r'^(automatic reply|auto(matic)?[ -]?reply|out of (the )?office)', re.I)
_UNTIL = re.compile(r'\b(until|through|returning( on)?|back (on|in the office on))\s+([A-Z][a-z]+day,?\s+)?([A-Z][a-z]+ \d{1,2}(st|nd|rd|th)?|\d{1,2}/\d{1,2}(/\d{2,4})?)', re.I)
def ooo(store, days: int = 14) -> dict:
    """{sender email: 'out until Monday August 31st (auto-reply Thu 28 Aug)'} from the auto-replies in the
    window - a chase to someone who is away is worse than silence, and the hub already holds the answer."""
    out = {}
    for r in store.recent_messages(_since(days), limit=600):
        if not _OOO.match(str(r.get('Subject') or '')): continue
        em = (r.get('FromEmail') or '').lower()
        if not em or em in out: continue                          # newest first: the latest auto-reply wins
        m = _UNTIL.search(str(r.get('BodyText') or ''))
        out[em] = (f"out {m.group(0)}" if m else 'out of office') + f" (auto-reply {_when(r['SentAt'])[:10]})"
    return out


# ── the candidates: facts the hub can find without a model ───────────────────────────────────
def followups(store, hours: int, want=('followup', 'promise')) -> list:
    """Threads where the last word is the owner's, `hours` old or more, and that word ASKED for
    something (followup - theirs to answer, ours to chase) or PROMISED something (promise - the
    owner's own open item). Silence after a plain "thanks" is neither. A sender's auto-reply in
    the window rides on the line: silence from someone who is away is not silence."""
    from .triage import strip_boilerplate
    cut = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    out, away = [], None
    for r in store.owner_last_words(_since(DAYS), cut):
        body = strip_boilerplate(str(r.get('BodyText') or ''))
        kind = 'promise' if _PROMISE.search(body) else 'followup' if _ASKS.search(body) else None
        if not kind or kind not in want: continue
        inbound = store.last_inbound_in(r['ConversationId'])
        if not inbound: continue                                    # nothing of theirs to answer under
        who = inbound.get('FromName') or inbound.get('FromEmail') or 'them'
        sent = _dt(r['SentAt']) or datetime.now()
        days = max(1, int((datetime.now() - sent).total_seconds() // 86400))
        subj = _short(inbound.get('Subject'), 60)
        if away is None: away = ooo(store)
        gone = away.get((inbound.get('FromEmail') or '').lower(), '')
        if kind == 'promise':
            out.append({'key': f"promise:{r['ConversationId']}", 'kind': 'promise', 'sig': _ts(r['SentAt']),
                        'facts': f"You told {who} on {_ts(r['SentAt'])[:10]} re \"{_short(r.get('Subject'), 70)}\": \"{_short(body, 160)}\" - {days} day(s) ago, and the thread has not moved.",
                        'text': f"You told {who} you would - \"{_short(body, 70)}\" - {days} day{'s' if days != 1 else ''} ago on \"{subj}\". Done?",
                        'action': {'type': 'message', 'mid': inbound['MessageId'], 'tid': inbound.get('TaskId')}})
        else:
            out.append({'key': f"followup:{r['ConversationId']}", 'kind': 'followup', 'sig': _ts(r['SentAt']) + (':away' if gone else ''),
                        'facts': (f"You wrote {who} on {_ts(r['SentAt'])[:10]} re \"{_short(r.get('Subject'), 70)}\": \"{_short(body, 160)}\" "
                                  f"- nothing has come back in {days} day(s)." + (f" BUT {who} is {gone}." if gone else '')),
                        'text': (f"No answer from {who} in {days} day{'s' if days != 1 else ''} on \"{subj}\" - " + (f"they are {gone}; I'd wait." if gone else 'follow up?')),
                        'action': {'type': 'followup', 'mid': inbound['MessageId'], 'tid': inbound.get('TaskId')}})
    return out


def cold(store, days: int) -> list:
    """Open work nothing has touched for `days`: no comment, no message, no run. A live agent on
    it is activity; a draft waiting in Review is the owner's to move."""
    cut = _since(days)
    out = []
    for t in store.list_tasks(active_only=True):
        if t.get('Status') not in ('open', 'in_progress', 'waiting') or t.get('RunStatus') == 'running': continue
        last = _ts(store.task_last_activity(t['TaskId']) or t.get('UpdatedAt') or t.get('CreatedAt'))
        if not last or last > cut: continue
        age = max(days, (datetime.now() - (_dt(last) or datetime.now())).days)
        wait = t.get('Status') == 'waiting' or t.get('ReviewStatus') == 'pending'
        ref = task_ref(t['TaskId'])
        out.append({'key': f'cold:{ref}', 'kind': 'cold', 'sig': last,
                    'facts': f"{ref} \"{_short(t.get('Title'), 80)}\" [{t['Status']}, kind {t.get('Kind')}] - nothing has happened on it for {age} days"
                             + (' and a draft waits for you in Review' if wait else ''),
                    'text': (f"{ref} has a reply waiting on you for {age} days - \"{_short(t.get('Title'), 60)}\"" if wait
                             else f"{ref} has sat quiet for {age} days - \"{_short(t.get('Title'), 60)}\". Push it or drop it?"),
                    'action': {'type': 'task', 'tid': t['TaskId']}})
    return out


_AGENDA = {}               # one calendar read per check: prep's candidates and the CALENDAR block share it
def _agenda(store) -> list:
    if store.get_settings().get('calendar_enabled', '1') != '1': return []
    if _AGENDA.get('at', 0) > datetime.now().timestamp() - 60: return _AGENDA['events']
    from . import calendar as cal
    try: ev = [e for e in (cal.agenda(store, days=2).get('events') or []) if not e.get('all_day')]
    except Exception as e:
        logger.debug(f'assistant: calendar skipped - {e}'); ev = []
    _AGENDA.update(at=datetime.now().timestamp(), events=ev)
    return ev


def prep(store) -> list:
    """Meetings in the next two days, each with what the hub already knows about the people in it
    and the subject - the prep note counsel writes for an invite, written for the ones already
    on the calendar."""
    from . import calendar as cal
    from .counsel import dossier
    out = []
    for e in _agenda(store)[:6]:
        who = list(e.get('who') or [])
        dos = dossier(store, {'from_email': '', 'from_name': ' '.join(who[:4]), 'subject': e.get('subject') or ''}, calendar=False)
        out.append({'key': f"prep:{e['start'][:16]}:{_short(e.get('subject'), 40)}", 'kind': 'prep', 'sig': e['start'][:16],
                    'facts': f"MEETING {e['start'][:16]} \"{e.get('subject')}\"" + (f" with {', '.join(who[:6])}" if who else '')
                             + (f" - about: {e['about']}" if e.get('about') else '')
                             + (f"\n  what the hub knows:\n  {dos[:1200]}" if dos else '\n  (nothing on file about these people or this subject)'),
                    'text': f"{cal.span(e['start'], e.get('end') or '')} {e.get('subject')}"
                            + (f" with {', '.join(w.split()[0] for w in who[:3])}" if who else '')
                            + (' - here is what came before it' if dos else ' - nothing on file, walk in fresh'),
                    'action': {'type': 'meeting', 'event': {k: e.get(k) for k in ('start', 'end', 'subject', 'who', 'where', 'about', 'join', 'organizer')}}})
    return out


def candidates(store, c: dict) -> list:
    out = []
    want = tuple(k for k in ('followup', 'promise') if k in c['producers'])
    for name, fn in (('followup/promise', lambda: followups(store, c['followup_h'], want) if want else []),
                     ('prep', lambda: prep(store) if 'prep' in c['producers'] else []),
                     ('cold', lambda: cold(store, c['cold_d']) if 'cold' in c['producers'] else [])):
        try: out += fn()
        except Exception as e: logger.warning(f'assistant: {name} candidates failed - {e}')
    return out


def fresh(state: dict, cand: dict, now: datetime) -> bool:
    """Worth saying now? Never said: yes. Said with these facts: no. Dismissed or done: only when
    the facts changed (a new last word on the thread, a moved meeting). Snoozed: when it wakes."""
    i = state.get(cand['key'])
    if not i: return True
    if i.get('Status') == 'snoozed': return bool(i.get('SnoozeUntil')) and _ts(i['SnoozeUntil']) <= now.strftime('%Y-%m-%d %H:%M:%S')
    return (i.get('Sig') or '') != (cand.get('sig') or '')


# ── the model's pass: its own read, given what it already said ───────────────────────────────
CONTRACT = ('\n\nYou are writing your POST on the owner\'s Timeline - the short list of things worth saying right now. You get '
            'CANDIDATES the hub found itself (each with a key), WHAT PEOPLE SAID (the words, by thread), who is OUT OF OFFICE, the '
            'CALENDAR, what arrived (with each report\'s schedule and each failure\'s cause), what got done, what is open, and WHAT '
            'YOU ALREADY SAID. Answer JSON only: {"say": [{"key": "<a candidate key, or idea:<short-slug> for a thought of your own>", '
            '"text": "<one line, under 30 words, first person: the fact and what I would do - quote the phrase or name the cause when there is one>", '
            '"why": "<one line: what this rests on - the mail, the date, the silence, the pattern - named as it appears in what you '
            'were given (sender, subject, mid, TQ-ref), so the owner can check it>", "mid": <the message id it is '
            'about, or null>, "task": "<idea:* only - a task title the owner could accept as-is, or null>"}], '
            '"notes": "<your note to the next check, under 120 words: FACTS AND TIMINGS ONLY - what you looked at and found nothing in, '
            'the date or silence length at which something becomes worth raising, a fact you settled so it need not be worked out again. '
            'Never a standing rule about what to ignore or what is noise: the instruction decides that, and a note that says '
            '\'ignore X\' would silence you for good. Rewrite it whole each time; empty if nothing>"}.\n'
            'At most {max_lines} entries. Skip a candidate that is not worth the owner\'s eye (a standing standup needs no prep; a '
            'one-day silence from someone who always takes a week is not news) - skipping is free, repeating is not: never say '
            'again, reworded or not, anything under ALREADY SAID. Your own ideas are the point: a thread going in circles, a '
            'promise buried in a mail, two people asking the same thing, the thing to do now so the next ask never comes. '
            'Facts only from what you are given; never invent a name, a date or a number. Nothing new to say -> {"say": []}.')


def _schedules(store) -> dict:
    """{report title: 'daily 08:00 + on every app start'} - a report's arrivals mean nothing without its
    clock: 25 digests in two days on an on_startup report is 25 launches, not a scheduler bug."""
    out = {}
    for src in store.list_sources(active_only=False):
        if src.get('Channel') != 'report': continue
        try: c = json.loads(src.get('ConfigJson') or '{}')
        except ValueError: continue
        parts = ([f"every {c['every_minutes']} min"] if c.get('every_minutes') else []) + ([f"daily {c['daily_at']}"] if c.get('daily_at') else []) \
              + ([f"cron {c['cron']}"] if c.get('cron') else []) + (['on every app start'] if c.get('on_startup') else [])
        out[c.get('title') or src.get('Address')] = ' + '.join(parts) or 'no schedule'
    return out

_FAILS = re.compile(r'fail|error|denied|timeout|could not|unable', re.I)
_GH_FAILED = re.compile(r'^(.+?) Failed in ', re.M)          # the job lines of GitHub's "Run failed" mail
def _cause(r: dict) -> str:
    """For a machine's mail that says something broke: the cause, not the count. GitHub's run mail
    names the failed jobs; a report's FAILED body starts with the error."""
    subj, body = str(r.get('Subject') or ''), str(r.get('Preview') or r.get('BodyText') or '')
    if not _FAILS.search(subj): return ''
    jobs = _GH_FAILED.findall(body)
    if jobs: return ' -> failed: ' + ', '.join(_short(j.split('/', 1)[-1], 40) for j in jobs[:4])
    return f' -> "{_gist(body, 150)}"' if body.strip() else ''

def _recent(store, days: int = 2) -> str:
    """The last two days' arrivals, ROLLED UP: one line per sender+subject with a count, newest
    first. A pattern (87 alerts from one system, the same ask twice) is a number the model can see
    instead of a list it has to count - and calendar-today at 00:49 was a 49-minute window. A report
    carries its schedule, and a failure its cause (the machines are to be read, not counted)."""
    by, sched = {}, _schedules(store)
    for r in store.feed(limit=400, days=days):
        if r.get('Channel') == CHANNEL: continue
        k = (r.get('FromName') or r.get('FromEmail') or r.get('SourceName') or '?',
             re.sub(r'^((re|fw|fwd|aw)\s*:\s*)+', '', _short(r.get('Subject'), 60), flags=re.I).lower())
        g = by.setdefault(k, {'n': 0, 'r': r, 'cats': set()}); g['n'] += 1; g['cats'].add(r.get('Category') or '')
    lines = []
    for (who, _), g in sorted(by.items(), key=lambda kv: -kv[1]['n'])[:35]:
        r = g['r']
        clock = f" [schedule: {sched[who]}]" if r.get('Channel') == 'report' and who in sched else ''
        lines.append(f"- {'x%d ' % g['n'] if g['n'] > 1 else ''}[{'/'.join(sorted(c for c in g['cats'] if c))}] {who}: \"{_short(r.get('Subject'), 70)}\" "
                     f"(latest mid {r['MessageId']} {_when(r['SentAt'])}" + (f", {task_ref(r['TaskId'])}" if r.get('TaskId') else '') + ')' + clock + _cause(r))
    return '\n'.join(lines) or '(nothing arrived in the last two days)'


def _people_context(store, days: int = 2) -> tuple[str, list[int]]:
    """WHAT PEOPLE SAID: the human threads of the last two days with the words in them - newest
    first, the last few lines of each, the owner's own lines marked. The subject line said
    "Teams chat with Mindy"; the words said "can you fill out the performance review?" - the
    ask, the pattern and the promise all live here, and a model handed only subjects wrote
    'no content given' in its notes."""
    from .categories import sender_class, team_domains_of
    team = team_domains_of(store.get_settings())
    rows = [r for r in store.recent_messages(_since(days), limit=500)
            if r.get('Channel') not in ('report', CHANNEL) and not _OOO.match(str(r.get('Subject') or ''))]
    # the owner's own lines are 'context' rows - recent_messages leaves them out, so fetch the threads' chains
    by = {}
    for r in rows:
        if sender_class(r, team) != 'person': continue
        k = r.get('ConversationId') or re.sub(r'^((re|fw|fwd|aw)\s*:\s*)+', '', _short(r.get('Subject'), 60), flags=re.I).lower()
        by.setdefault(k, []).append(r)
    me = (store.get_settings().get('owner_email') or '').lower()
    out, used, mids = [], 0, []
    for k, rs in list(by.items())[:PEOPLE_THREADS]:
        chain = store.thread_messages(conversation_id=rs[0].get('ConversationId'), subject=rs[0].get('Subject'), limit=12) if rs[0].get('ConversationId') else rs
        chain = sorted((c for c in chain if c.get('Status') != 'skipped'), key=lambda c: _ts(c.get('SentAt')))[-8:]
        last = chain[-1]
        mine = lambda c: c.get('Status') == 'context' or c.get('Direction') == 'out' or (c.get('FromEmail') or '').lower() == me
        who = next((c.get('FromName') or c.get('FromEmail') for c in reversed(chain) if not mine(c)), rs[0].get('FromName') or '?')
        tid = next((c.get('TaskId') for c in reversed(chain) if c.get('TaskId')), None)
        t = store.get_task(tid) if tid else None
        head = (f"- {who} [{rs[0].get('Channel')}] re \"{_short(rs[0].get('Subject'), 60)}\" - {len(rs)} new, last word {'YOURS' if mine(last) else 'THEIRS'} {_when(last['SentAt'])}"
                + (f", {task_ref(tid)} {t.get('Kind')} {t.get('Status')}" if t else '') + f" (latest mid {rs[0]['MessageId']})")
        first = lambda c: ((c.get('FromName') or c.get('FromEmail') or '?').split(',')[0].split() or ['?'])[0]
        def quote(c):
            attachments = store.list_attachments(c['MessageId'])
            files = ', '.join(f"{a.get('Name') or 'attachment'}" + (f" ({a['Path']})" if a.get('Path') else '')
                              for a in attachments[:4])
            return (f"    {'you' if mine(c) else first(c)} {_when(c['SentAt'])[:6]}: \"{_gist(c.get('BodyText'), 150)}\""
                    + (f" [attachments: {files}]" if files else ''))
        quotes = [quote(c) for c in chain]
        block = '\n'.join([head] + [q for q in quotes if not q.endswith(': ""')])
        if used + len(block) > PEOPLE_CHARS: break
        out.append(block); used += len(block); mids += [c['MessageId'] for c in chain]
    return '\n'.join(out) or '(no person wrote in the last two days)', mids


def _people(store, days: int = 2) -> str:
    return _people_context(store, days)[0]


def _calendar(store) -> str:
    from . import calendar as cal
    ev = _agenda(store)
    return '\n'.join(f"- {_when(e['start'])} {cal.span(e['start'], e.get('end') or '')} \"{e.get('subject')}\"" + (f" with {', '.join(list(e.get('who') or [])[:6])}" if e.get('who') else '')
                     for e in ev[:8]) or '(nothing on the calendar for two days' + (')' if store.get_settings().get('calendar_enabled', '1') == '1' else ' - calendar off)')


def _week(store) -> str:
    """What got DONE this week - closed tasks, each with the agent's own summary line where there is
    one. The ideas worth having about the owner's work (the fix that keeps recurring, the report
    nobody reads, the automation) live here, not in today's mail."""
    cut = _since(7)
    ts = [t for t in store.list_tasks() if t.get('Status') == 'done' and _ts(t.get('ClosedAt') or t.get('UpdatedAt')) >= cut][:25]
    out = []
    for t in ts:
        rep = next((c for c in reversed(store.list_comments(t['TaskId'])) if str(c.get('Body') or '').startswith('CODER REPORT')), None)
        summ = ''
        if rep:
            m = re.search(r'(?im)^summary:\s*(.+)$', rep['Body'])
            summ = ' - ' + _short(m.group(1) if m else rep['Body'].split('\n', 1)[-1], 110)
        repo = (re.search(r'repo:([^\s,]+)', str(t.get('Tags') or '')) or [None, None])[1]
        out.append(f"- {task_ref(t['TaskId'])} [{t.get('Kind')}{', ' + repo if repo else ''}] {_short(t.get('Title'), 70)}{summ}")
    return '\n'.join(out) or '(nothing closed this week)'


def _open(store) -> str:
    ts = [t for t in store.list_tasks(active_only=True) if t.get('Status') in ('open', 'in_progress', 'waiting')]
    def line(t):
        last = _dt(store.task_last_activity(t['TaskId']) or t.get('UpdatedAt') or t.get('CreatedAt'))
        age = f"{int((datetime.now() - last).total_seconds() // 3600)}h since anything happened" if last else ''
        state = f"{t.get('RunAgent') or 'an agent'} is working it" if t.get('RunStatus') == 'running' else 'a draft waits for you in Review' if t.get('ReviewStatus') == 'pending' else age
        return f"- {task_ref(t['TaskId'])} [{t['Status']}, {t.get('Kind')}] {_short(t.get('Title'), 80)}" + (f" - {state}" if state else '')
    return '\n'.join(line(t) for t in ts[:20]) or '(nothing open)'


def _said(store) -> str:
    rows = [i for i in store.list_ideas() if i.get('Status') in ('open', 'dismissed', 'snoozed')][:40]
    out = []
    for i in rows:
        out.append(f"- ({i['Status']}) {i['Text']}")
        try: chat = json.loads(i.get('ActionJson') or '{}').get('chat') or []
        except ValueError: chat = []
        for turn in chat[-4:]:
            out.append(f"    {turn.get('role')}: {_short(turn.get('text'), 300)}")
    return '\n'.join(out) or '(nothing yet)'


def parse(text: str, cands: list, max_lines: int = MAX_LINES) -> list:
    """The model's list, kept honest: a key it invents must be idea:*, a candidate key keeps its
    kind and its buttons, and the text is the model's when it gave one. Every line keeps its WHY -
    the hub's facts for a candidate (plus the model's read on them), the model's own for an idea -
    so the owner can see what it rests on (the owner, 2026-08-30: "why it brings up something,
    what is driving it")."""
    try: j = json.loads(re.sub(r'^```(json)?|```$', '', (text or '').strip(), flags=re.M))
    except ValueError: return []
    by = {c['key']: c for c in cands}
    out, seen = [], set()
    for s in (j.get('say') or []) if isinstance(j, dict) else []:
        if not isinstance(s, dict): continue
        key, txt, why = str(s.get('key') or '').strip(), _short(s.get('text'), 240), _short(s.get('why'), 400)
        if not key or key in seen or not txt: continue
        if key in by:
            # the first line of the facts: prep's line carries a 1200-char dossier under it that belongs in 'skipped', not under a button
            out.append({**by[key], 'text': txt, 'why': by[key]['facts'].split('\n', 1)[0] + (f"\nThe model's read: {why}" if why else '')})
        elif key.startswith('idea:') and len(key) > 5:
            mid = s.get('mid') if isinstance(s.get('mid'), int) else None
            title = _short(s.get('task'), 120) or None
            act = {'type': 'task', 'mid': mid, 'title': title} if title and mid else {'type': 'message', 'mid': mid} if mid else {'type': 'note'}
            out.append({'key': key[:120], 'kind': 'idea', 'sig': txt[:60], 'text': txt, 'action': act,
                        'why': why or 'the model gave no reason - treat it as a hunch' + (f' (about mid {mid})' if mid else '')})
        else: continue
        seen.add(key)
        if len(out) >= max_lines: break
    return out


def inputs(store, cands: list, head: str = 'CANDIDATES') -> str:
    """Everything one check reads, as the model sees it - the same text is the Reports tab's Preview
    (facts) and the run record (reports.run_report_source), so what it was given is never a guess."""
    now = datetime.now()
    away = ooo(store)
    return (f"NOW: {now.strftime('%A %d %B %Y %H:%M')}\n\n{head}:\n" + ('\n'.join(f"[{c['key']}] {c['facts']}" for c in cands) or '(none)')
            + f"\n\nWHAT PEOPLE SAID (the last two days, by thread, newest first; the last lines of each, oldest first):\n{_people(store)}"
            + '\n\nOUT OF OFFICE (from their auto-replies):\n' + ('\n'.join(f'- {k}: {v}' for k, v in away.items()) or '(nobody)')
            + f"\n\nCALENDAR (the next two days):\n{_calendar(store)}"
            + f"\n\nARRIVED IN THE LAST TWO DAYS (xN = that many alike; a report carries its schedule, a failure its cause):\n{_recent(store)}"
            + f"\n\nDONE THIS WEEK (my own work, with the agent's summary):\n{_week(store)}"
            + f"\n\nOPEN WORK:\n{_open(store)}\n\nALREADY SAID (never repeat):\n{_said(store)}\n\n{_notes_block(store)}")


def think(store, cands: list, llm, instruction: str = None, max_lines: int = MAX_LINES) -> list:
    """One call: COUNSEL.md's voice, the owner's instruction (the Reports tab), the candidates, the
    day, what was already said."""
    doc = re.sub(r'<!--.*?-->', '', store.doc('counsel') or '', flags=re.S).strip()
    soul = store.doc('soul') or ''
    system = (doc + f"\n\nYOUR INSTRUCTION (the owner's, from the Reports tab):\n{(instruction or PROMPT).strip()}" + CONTRACT.replace('{max_lines}', str(max_lines))
              + (f"\n\nWho the owner is (their own document; its reply rules are for text sent to OTHERS):\n{soul[:1500]}" if soul else ''))
    user = inputs(store, cands)
    from .llm import readable_images
    images = readable_images(store, _people_context(store)[1])
    text = llm(system, user, max_tokens=POST_TOKENS, **({'images': images} if images else {}))
    return parse(text, cands, max_lines), _notes(text), user


def facts(store) -> str:
    """What a run would hand the model, as text - the Reports tab's Preview (reports.run_assistant)."""
    c = cfg(store); now = datetime.now()
    state = {i['Key']: i for i in store.list_ideas()}
    return inputs(store, [x for x in candidates(store, c) if fresh(state, x, now)], 'CANDIDATES (new since the last post)')


# ── the note to the next check ───────────────────────────────────────────────────────────────
def notes(store) -> tuple:
    """(text, when) of the note the last check left - '' if none yet."""
    s = store.get_settings()
    return (s.get('assistant_notes') or '').strip(), s.get('assistant_notes_at') or ''

def _notes_block(store) -> str:
    n, at = notes(store)
    return (f"YOUR NOTES FROM YOUR LAST CHECK ({_ts(at)}; your own facts and timings - use them, then rewrite them; they are not rules):\n{n}" if n
            else 'YOUR NOTES FROM YOUR LAST CHECK: (none yet - this is your first check, or the last one left none)')

def _notes(text: str) -> str:
    try: j = json.loads(re.sub(r'^```(json)?|```$', '', (text or '').strip(), flags=re.M))
    except ValueError: return ''
    return ' '.join(str(j.get('notes') or '').split())[:900] if isinstance(j, dict) else ''


# ── the post ─────────────────────────────────────────────────────────────────────────────────
def _public(i: dict) -> dict:
    try: a = json.loads(i.get('ActionJson') or '{}')
    except ValueError: a = {}
    return {'id': i['IdeaId'], 'key': i['Key'], 'kind': i['Kind'], 'text': i['Text'], 'why': a.pop('why', ''), 'action': a, 'status': i.get('Status')}


def talk(store, idea_id: int, text: str, actor: str = 'owner', llm=None) -> dict:
    """Let the owner challenge or question one suggestion and keep the exchange with it.

    This is deliberately not a verdict. A correction becomes context under ALREADY SAID on
    later checks, while the assistant answers now from the same people/calendar/work inputs
    (and the same attached images) that should have informed the suggestion initially.
    """
    i = store.get_idea(idea_id)
    if not i: raise ValueError(f'no idea {idea_id}')
    text = _short(text, 1200)
    if not text: raise ValueError('say what the assistant missed or ask a question')
    try: action = json.loads(i.get('ActionJson') or '{}')
    except ValueError: action = {}
    chat = [t for t in (action.get('chat') or []) if isinstance(t, dict)][-10:]
    if llm is None:
        from .llm import build_llm
        llm = build_llm(store)
    if not llm: raise ValueError('the assistant needs an active AI connector to answer')
    counsel = re.sub(r'<!--.*?-->', '', store.doc('counsel') or '', flags=re.S).strip()
    system = ((counsel + '\n\n') if counsel else '') + (
        'The owner is talking back to one of your assistant suggestions. Answer as their assistant, '
        'not as customer support. If they correct you, acknowledge the mistake plainly and update your '
        'understanding from the evidence below. If they ask a question, answer it directly. Do not claim '
        'you performed an action, sent anything, or saw a file that was not provided. Be brief: 2-4 sentences.')
    history = '\n'.join(f"{t.get('role')}: {t.get('text')}" for t in chat)
    user = (f"YOUR SUGGESTION:\n{i['Text']}\nWHY YOU GAVE:\n{action.get('why') or '(none)'}"
            + (f"\nCONVERSATION SO FAR:\n{history}" if history else '')
            + f"\nOWNER NOW SAYS:\n{text}\n\nCURRENT HUB CONTEXT:\n{inputs(store, [], 'NEW CANDIDATES (not relevant to this reply)')}")
    from .llm import readable_images
    images = readable_images(store, _people_context(store)[1])
    answer = _short(llm(system, user, max_tokens=400, **({'images': images} if images else {})), 1200)
    if not answer: raise ValueError('the assistant returned no answer')
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    chat = (chat + [{'role': 'owner', 'text': text, 'at': stamp},
                    {'role': 'assistant', 'text': answer, 'at': stamp}])[-12:]
    action['chat'] = chat
    store.set_idea_action(idea_id, action)
    store.audit('idea', idea_id, 'talk', actor, detail={'owner': text[:300], 'assistant': answer[:300]})
    return {'ideaId': idea_id, 'reply': answer, 'chat': chat}


def reviewed(cands: list, say: list, recent: str, open_: str, said: str, model: bool, week: str = '(', people: str = '(') -> dict:
    """What this post was built from, so the owner can judge it: the candidates by kind, the ones it
    looked at and let go (with their facts), how much of the day and the open work it read, how many
    of its own lines it was told not to repeat. Stored on the post (Brief.reviewed) and written
    under it in plain text."""
    kept = {s_['key'] for s_ in say}
    n = lambda txt: 0 if txt.startswith('(') else txt.count('\n') + 1
    by = {}
    for c in cands: by[c['kind']] = by.get(c['kind'], 0) + 1
    return {'candidates': by, 'skipped': [{'key': c['key'], 'kind': c['kind'], 'facts': c['facts']} for c in cands if c['key'] not in kept],
            'recent': n(recent), 'week': n(week), 'open': n(open_), 'said': n(said), 'model': model,
            'people': 0 if people.startswith('(') else sum(1 for l in people.split('\n') if l.startswith('- '))}


def _footer(r: dict) -> str:
    kinds = ', '.join(f"{v} {k}" for k, v in r['candidates'].items()) or 'no candidates'
    skip = f"; let go: {len(r['skipped'])}" if r['skipped'] else ''
    return (f"Reviewed: {kinds}{skip} - {r.get('people', 0)} thread(s) of what people said, {r['recent']} sender/subject line(s) from the last two days, "
            f"{r['week']} task(s) closed this week, {r['open']} open task(s), {r['said']} line(s) already said"
            + ('' if r['model'] else " - no model: the facts in the hub's own words"))


def run(store, llm=None, force: bool = False, instruction: str = None) -> dict:
    """One post. The Reports tab's scheduler calls this when the 'Assistant' report is due
    (reports.run_report_source) and its "Run now" calls it forced; the instruction is the report's
    editable prompt. Deleting or switching off that report is the off switch - a forced run still
    answers. Posts nothing when nothing is new."""
    src = source(store)
    if not force and not (src and src.get('Active')): return {'ran': False, 'said': 0}
    if instruction is None and src: instruction = (src['cfg'].get('ai_prompt') or '').strip() or None
    with _LOCK: return _run(store, llm, instruction)


def _run(store, llm, instruction) -> dict:
    c = cfg(store); now = datetime.now()
    store.set_setting('assistant_last_run', now.isoformat(timespec='seconds'), 'assistant')
    state = {i['Key']: i for i in store.list_ideas()}
    cands = [x for x in candidates(store, c) if fresh(state, x, now)]
    if llm is None:
        from .llm import build_llm
        try: llm = build_llm(store)
        except Exception as e:
            logger.debug(f'assistant: no model - {e}'); llm = None
    used, note, read = bool(llm and 'idea' in c['producers']), '', ''
    if used:
        try: say, note, read = think(store, cands, llm, instruction, c['max'])
        except Exception as e:
            logger.warning(f'assistant: the model pass failed, posting the facts alone - {e}'); say, used = cands[:c['max']], False
    else: say = cands[:c['max']]          # no model: the facts still stand, in the hub's own words
    if not read: read = inputs(store, cands, 'CANDIDATES (no model pass - these posted as facts)')
    # the note outlives the post: a quiet check leaves one too, so the next check starts where this one stopped
    if note:
        store.set_setting('assistant_notes', note, 'assistant'); store.set_setting('assistant_notes_at', now.strftime('%Y-%m-%d %H:%M:%S'), 'assistant')
    # the state is read AGAIN here: another process may have posted while the model was thinking, and a
    # model echoing a dismissed key changes nothing
    state = {i['Key']: i for i in store.list_ideas()}
    say = [s | {'why': s.get('why') or s.get('facts') or ''} for s in say if fresh(state, s, now)]
    rv = reviewed(cands, say, _recent(store), _open(store), _said(store), used, _week(store), _people(store)) | {'notes': note}
    if not say: return {'ran': True, 'said': 0, 'reviewed': rv, 'inputs': read}
    stamp = now.strftime('%Y-%m-%d %H:%M:%S')
    rows = [store.upsert_idea(s | {'action': (s.get('action') or {}) | {'why': s['why']}}, stamp) for s in say]
    body = ('\n'.join(f"- {i['Text']}\n    why: {s_['why']}" for i, s_ in zip(rows, say)) + '\n\n' + _footer(rv)
            + (f"\nNote to my next check: {note}" if note else ''))
    # the row's one line: the first idea, cut at a word, and how many more wait behind it
    head = rows[0]['Text'] if len(rows[0]['Text']) <= 90 else rows[0]['Text'][:90].rsplit(' ', 1)[0] + '…'
    subj = head + (f' (+{len(rows) - 1} more)' if len(rows) > 1 else '')
    mid = store.add_message({'TaskId': None, 'ExternalId': f'assistant:{stamp}', 'ConversationId': 'assistant', 'Channel': CHANNEL,
                             'SourceName': 'Assistant', 'Subject': subj, 'FromName': 'Assistant', 'SentAt': stamp,
                             'BodyText': body, 'Status': 'feed'})
    store.add_route(mid, None, 'feed', None, "the assistant's post: what it noticed and what it would do - open it to talk back or act",
                    [], 'assistant')
    store.set_brief(mid, json.dumps({'ideas': [_public(i) for i in rows], 'reviewed': rv}))
    store.set_ideas_message([i['IdeaId'] for i in rows], mid)
    store.audit('message', mid, 'assistant_post', 'assistant', 'agent', {'ideas': len(rows)})
    logger.info(f'assistant: posted {len(rows)} idea(s) as message {mid}')
    return {'ran': True, 'said': len(rows), 'message_id': mid, 'reviewed': rv, 'inputs': read, 'lines': [_public(i) for i in rows]}


# ── the buttons ──────────────────────────────────────────────────────────────────────────────
def nudge(store, mid: int, why: str, actor: str = 'owner', llm=None) -> dict:
    """The chase, drafted in the owner's voice and parked in Review - never sent by itself."""
    from .ingest import task_from_message
    from . import responder
    m = store.get_message(mid)
    if not m: raise ValueError(f'no message {mid}')
    tid = m.get('TaskId') or task_from_message(store, mid, actor, 'reply')
    if (store.get_task(tid) or {}).get('Status') in ('done', 'dropped'): store.update_task(tid, {'Status': 'waiting'}, actor)
    rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                            'Reason': f'follow-up the assistant suggested: {why[:160]}'})
    try: responder.write_draft(store, tid, rid, actor=actor, llm=llm, nudge=why)
    except Exception as e: logger.warning(f'follow-up draft failed for review {rid}: {e}')   # Review keeps the empty draft; 'Draft with AI' retries
    store.add_comment(tid, 'assistant', 'agent', f'FOLLOW-UP\n{why}\nThe chase is drafted in Review - approving sends it.')
    return {'taskId': tid, 'ref': task_ref(tid), 'reviewId': rid}


def act(store, idea_id: int, verb: str, actor: str = 'owner', llm=None, days: int = 1, learn_async=None) -> dict:
    """One click on the panel. followup / task DO the thing and close the idea; dismiss and snooze
    are verdicts (dismiss teaches LEARNED.md which nudges this owner never wants); done says the
    owner handled it themselves."""
    i = store.get_idea(idea_id)
    if not i: raise ValueError(f'no idea {idea_id}')
    try: a = json.loads(i.get('ActionJson') or '{}')
    except ValueError: a = {}
    out = {'ideaId': idea_id, 'verb': verb}
    if verb == 'followup':
        if not a.get('mid'): raise ValueError('this idea is not about a message, so there is nothing to follow up on')
        out |= nudge(store, a['mid'], i['Text'], actor, llm)
    elif verb == 'task':
        if not a.get('mid'): raise ValueError('this idea is not about a message, so there is nothing to make a task from')
        from . import ingest
        tid = ingest.task_from_message(store, a['mid'], actor, 'coding')
        if a.get('title'): store.update_task(tid, {'Title': str(a['title'])[:200]}, actor)
        if store.get_settings().get('coder_auto_enabled') == '1': ingest._spawn(ingest._auto_code, store, tid)
        out |= {'taskId': tid, 'ref': task_ref(tid)}
    elif verb == 'snooze':
        until = (datetime.now() + timedelta(days=max(1, int(days or 1)))).strftime('%Y-%m-%d %H:%M:%S')
        store.set_idea_status(idea_id, 'snoozed', actor, until)
        store.audit('idea', idea_id, verb, actor, detail={'until': until})
        return out | {'until': until}
    elif verb not in ('dismiss', 'done'): raise ValueError(f'unknown verb: {verb}')
    store.set_idea_status(idea_id, 'dismissed' if verb == 'dismiss' else 'done', actor)
    if verb == 'dismiss':
        from . import learn
        ev = f"idea{idea_id}: the owner dismissed the assistant's {i.get('Kind')} suggestion \"{i['Text'][:200]}\" - not worth their eye"
        if learn_async: learn_async(learn.learn_from, store, ev)
        else: learn.learn_from(store, ev)
    store.audit('idea', idea_id, verb, actor, detail={'kind': i.get('Kind')})
    return out
