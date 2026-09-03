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
a chase to someone away is worse than silence), the CALENDAR, and the actual words in every rolled-up
arrival (including machine mail), with each report's schedule and each failure's cause beside the count. That is where "Yittie said exporting freezes the
app - and she is in Monday's meeting" comes from.

It also leaves itself a NOTE: each check ends with what it looked at and found nothing in, when
something becomes worth raising, whatever it would otherwise work out again - and the next check
starts by reading it (assistant_notes). Half-hourly checks are cheap only if each one does not
start from zero; a quiet check still rewrites the note, it just posts nothing. How it SPEAKS is
COUNSEL.md (Docs tab) - the owner edits that to change its voice and what it takes a position on;
the report's prompt is what it watches for.
"""
import json, math, re, threading
from datetime import datetime, timedelta
from loguru import logger

from .store import task_ref

CHANNEL = 'assistant'
PRODUCERS = ('followup', 'promise', 'prep', 'cold', 'idea')
DAYS = 30                  # how far back followups and promises are read
MAX_LINES = 5              # lines per post by default - a post nobody reads to the end is a post that failed
POST_TOKENS = 900
WATCH_SOURCE_CHARS = 6_000
WATCH_TOTAL_CHARS = 18_000
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
    'You are my assistant; every 30 minutes you check in across the systems and conversations I chose. Tell me only what a sharp human assistant who had READ everything '
    'would lean over and say - never a summary of my inbox, never a count I can see myself. A good line connects two things I '
    'have not connected, or names the one thing I am about to miss. Read, in this order of worth:\n'
    '0. CONFIGURED SYSTEM CHECKS - current views from finance, operations, CRM, infrastructure, or any other connected system. '
    'Look for threshold breaches, unusual totals, sharp changes, missing expected activity, and facts that conflict across systems.\n'
    '1. WHAT PEOPLE SAID - the actual words, by thread. The ask buried in a chat ("can you fill out the form?") that got a '
    'reply but not the thing itself; the colleague mentioning in passing that a system fails "every day 4-5"; the person '
    'answering a question nobody asked me; the thread where the last word is theirs and it wants something from me. Say who, '
    'what, and what I would do - "Marcus asked for X on Thursday; I would send it before his Monday 1pm".\n'
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
                    'You are my assistant. Every 30 minutes you check in;',
                    'You are my assistant; every 30 minutes you check in.')


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


def _reply_text(review: dict | None) -> str:
    """The words that left through Review, never an unsent draft."""
    return str((review or {}).get('FinalText') or (review or {}).get('DraftText') or '').strip()

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


def unanswered(store, days: float = 2, hours: int = 3) -> list:
    """The mirror of followups(): threads where THEIR last word asked the owner for something and
    nothing of the owner's came after it - the ask that slipped. `hours` old at least (fresh mail
    is not yet missed). Each carries what covers it: a draft in Review, a task and its state, or
    nothing at all - the morning brief's "what slipped" is built from these."""
    from .categories import sender_class, team_domains_of
    from .triage import strip_boilerplate
    settings = store.get_settings(); team = team_domains_of(settings); me = (settings.get('owner_email') or '').lower()
    cut = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    pend = {r['TaskId'] for r in store.list_reviews('pending')}
    mine = lambda c: c.get('Status') == 'context' or c.get('Direction') == 'out' or (c.get('FromEmail') or '').lower() == me
    seen, out, away = set(), [], None
    for r in store.recent_messages(_since(days), limit=500):
        cid = r.get('ConversationId')
        if not cid or cid in seen or r.get('Channel') in ('report', CHANNEL) or _OOO.match(str(r.get('Subject') or '')): continue
        seen.add(cid)
        if sender_class(r, team) != 'person': continue
        chain = sorted((c for c in store.thread_messages(conversation_id=cid, limit=12) if c.get('Status') != 'skipped'), key=lambda c: _ts(c.get('SentAt')))
        if not chain: continue
        last = chain[-1]
        if mine(last) or _ts(last.get('SentAt')) > cut: continue
        body = strip_boilerplate(_BANNER.sub('', str(last.get('BodyText') or '')))
        if not _ASKS.search(body): continue
        tid = next((c.get('TaskId') for c in reversed(chain) if c.get('TaskId')), None)
        t = store.get_task(tid) if tid else None
        cover = ('a draft waits for you in Review' if tid in pend else
                 f"{task_ref(tid)} is {t.get('Status')}" + (', an agent is on it' if t.get('RunStatus') == 'running' else '') if t else 'no task, no draft')
        who = last.get('FromName') or last.get('FromEmail') or 'someone'
        age = datetime.now() - (_dt(last['SentAt']) or datetime.now())
        ago = f"{age.days} day{'s' if age.days != 1 else ''}" if age.days else f"{int(age.total_seconds() // 3600)}h"
        if away is None: away = ooo(store)
        gone = away.get((last.get('FromEmail') or '').lower(), '')
        out.append({'key': f'asked:{cid}', 'kind': 'asked', 'sig': _ts(last['SentAt']),
                    'facts': f"{who} asked {_when(last['SentAt'])} re \"{_short(last.get('Subject'), 70)}\": \"{_gist(body, 160)}\" - no answer from you in {ago}; {cover}"
                             + (f"; {who} is {gone}" if gone else ''),
                    'text': f"{who} asked \"{_gist(body, 60)}\" {ago} ago - no answer yet ({cover})",
                    'action': {'type': 'message', 'mid': last['MessageId'], 'tid': tid}})
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
            '"section": "<people|loose|ideas|systems - which part of the post this belongs under: people = what somebody said '
            'or asked, loose = something waiting on somebody (a chase, a promise, work gone quiet), systems = a threshold, a '
            'failure or a number out of a connected system, ideas = your own thought. A candidate the hub found has a section '
            'already and yours is ignored for those; this is for idea:* lines>", '
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
    instead of a list it has to count - and calendar-today at 00:49 was a 49-minute window. Every
    line carries the latest message's actual words too: WHAT PEOPLE SAID has fuller human threads,
    but invitations and other machine mail must not collapse to a subject line. A report carries
    its schedule, and a failure its cause (the machines are to be read, not counted)."""
    by, sched, since = {}, _schedules(store), _since(days)
    for r in store.feed(limit=400, days=math.ceil(days)):
        if r.get('Channel') == CHANNEL or _ts(r.get('SentAt')) < since: continue
        k = (r.get('FromName') or r.get('FromEmail') or r.get('SourceName') or '?',
             re.sub(r'^((re|fw|fwd|aw)\s*:\s*)+', '', _short(r.get('Subject'), 60), flags=re.I).lower())
        g = by.setdefault(k, {'n': 0, 'r': r, 'cats': set()}); g['n'] += 1; g['cats'].add(r.get('Category') or '')
    lines = []
    for (who, _), g in sorted(by.items(), key=lambda kv: -kv[1]['n'])[:35]:
        r = g['r']
        clock = f" [schedule: {sched[who]}]" if r.get('Channel') == 'report' and who in sched else ''
        cause = _cause(r)
        words = _gist(r.get('Preview'), 220)
        detail = cause or (f' -> says: "{words}"' if words else '')
        lines.append(f"- {'x%d ' % g['n'] if g['n'] > 1 else ''}[{'/'.join(sorted(c for c in g['cats'] if c))}] {who}: \"{_short(r.get('Subject'), 70)}\" "
                     f"(latest mid {r['MessageId']} {_when(r['SentAt'])}" + (f", {task_ref(r['TaskId'])}" if r.get('TaskId') else '') + ')' + clock + detail)
    return '\n'.join(lines) or '(nothing arrived in the last two days)'


def _people_context(store, days: int = 2) -> tuple[str, list[int]]:
    """WHAT PEOPLE SAID: the human threads of the last two days with the words in them - newest
    first, the last few lines of each, the owner's own lines marked. The subject line said
    "Teams chat with Marcus"; the words said "can you fill out the performance review?" - the
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
        # A reply sent from Review has a durable send receipt there, but many channels do not
        # ingest that outbound line back into `message` immediately. Without this virtual final
        # message, the Assistant saw the finished task and the inbound ask, then confidently
        # claimed "nobody told them" minutes after the owner had approved and sent the reply.
        sent = store.sent_reply(task_id=tid) if tid else None
        if not sent:
            for c in reversed(chain):
                sent = store.sent_reply(message_id=c['MessageId'])
                if sent: break
        sent_text = _reply_text(sent)
        sent_at = (sent or {}).get('DecidedAt') or (sent or {}).get('CreatedAt')
        # Do not print it twice once the channel has ingested the same outbound line as context.
        sent_norm = ' '.join(sent_text.split()).casefold()
        own_after = any(mine(c) and (
            ' '.join(str(c.get('BodyText') or '').split()).casefold() == sent_norm
            or (sent_at and _ts(c.get('SentAt')) >= _ts(sent_at))) for c in chain)
        virtual_reply = bool(sent_text and not own_after)
        last_mine = virtual_reply or mine(last)
        last_at = sent_at if virtual_reply else last.get('SentAt')
        # ...and what TRIAGE decided when the latest line arrived - the other brain's verdict, so
        # this one argues with it in the open ("triage filed this as fyi, but...") instead of
        # raising the thread as if nothing had judged it
        judged = next((r.get('Reason') for r in reversed(store.message_routes(rs[0]['MessageId'])) if r.get('Reason')), '')
        head = (f"- {who} [{rs[0].get('Channel')}] re \"{_short(rs[0].get('Subject'), 60)}\" - {len(rs)} new, last word {'YOURS' if last_mine else 'THEIRS'} {_when(last_at)}"
                + (f", {task_ref(tid)} {t.get('Kind')} {t.get('Status')}" if t else '') + f" (latest mid {rs[0]['MessageId']})"
                + (f' - triage said: "{_short(judged, 140)}"' if judged else ''))
        first = lambda c: ((c.get('FromName') or c.get('FromEmail') or '?').split(',')[0].split() or ['?'])[0]
        def quote(c):
            attachments = store.list_attachments(c['MessageId'])
            files = ', '.join(f"{a.get('Name') or 'attachment'}" + (f" ({a['Path']})" if a.get('Path') else '')
                              for a in attachments[:4])
            return (f"    {'you' if mine(c) else first(c)} {_when(c['SentAt'])[:6]}: \"{_gist(c.get('BodyText'), 150)}\""
                    + (f" [attachments: {files}]" if files else ''))
        quotes = [quote(c) for c in chain]
        if virtual_reply:
            quotes.append(f"    you {_when(sent_at)[:6]}: \"{_gist(sent_text, 150)}\" [reply sent from Review]")
        block = '\n'.join([head] + [q for q in quotes if not q.endswith(': ""')])
        if used + len(block) > PEOPLE_CHARS: break
        out.append(block); used += len(block); mids += [c['MessageId'] for c in chain]
    return '\n'.join(out) or '(no person wrote in the last two days)', mids


def _people(store, days: int = 2) -> str:
    return _people_context(store, days)[0]


def said_about(store, conversation_id: str, limit: int = 4) -> list:
    """What this voice has already raised about ONE thread - for TRIAGE to read before it judges
    the next line on it. The two brains read the same threads with different prompts and never
    saw each other's conclusions, so a chase the assistant suggested and the owner dismissed was
    news to triage the next morning, and a thread the assistant had flagged as waiting on the
    owner was classified as if nobody had ever looked at it. Keys are per thread
    (followup:/promise:/asked:<conversation id>), so this is a lookup, not a search."""
    if not conversation_id: return []
    tail = f':{conversation_id}'
    return [f"{i.get('Kind')} raised {str(i.get('LastSaid') or '')[:10]}, now {i.get('Status')}: \"{_short(i.get('Text'), 140)}\""
            for i in store.list_ideas() if str(i.get('Key') or '').endswith(tail)][:limit]


def _calendar(store) -> str:
    from . import calendar as cal
    ev = _agenda(store)
    return '\n'.join(f"- {_when(e['start'])} {cal.span(e['start'], e.get('end') or '')} \"{e.get('subject')}\"" + (f" with {', '.join(list(e.get('who') or [])[:6])}" if e.get('who') else '')
                     for e in ev[:8]) or '(nothing on the calendar for two days' + (')' if store.get_settings().get('calendar_enabled', '1') == '1' else ' - calendar off)')


def _done(store, days: float = 7) -> str:
    """What got DONE in the window - closed tasks, each with the agent's own summary line where there
    is one. The ideas worth having about the owner's work (the fix that keeps recurring, the report
    nobody reads, the automation) live here, not in today's mail."""
    cut = _since(days)
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
    return '\n'.join(out) or '(nothing closed in this window)'


def _week(store) -> str: return _done(store, 7)


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


def raised(store, days: float = 2) -> str:
    """The assistant's own lines from the window, each with its state and what the owner said back -
    the morning brief reads these so it can say what still stands instead of finding it again."""
    cut = _since(days)
    rows = [i for i in store.list_ideas() if _ts(i.get('LastSaid') or i.get('FirstSeen')) >= cut][:30]
    out = []
    for i in rows:
        out.append(f"- ({i.get('Status')}, said {_when(i.get('LastSaid') or i.get('FirstSeen'))}) {i['Text']}")
        try: chat = json.loads(i.get('ActionJson') or '{}').get('chat') or []
        except ValueError: chat = []
        out += [f"    {turn.get('role')}: {_short(turn.get('text'), 200)}" for turn in chat[-2:]]
    return '\n'.join(out) or '(the assistant raised nothing in this window)'


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
            # where in the post it goes. Only an idea gets to choose: a candidate the hub found is
            # placed by the producer that found it, and no model answer overrides that.
            act['section'] = section_of({'section': s.get('section'), 'kind': 'idea'})
            out.append({'key': key[:120], 'kind': 'idea', 'sig': txt[:60], 'text': txt, 'action': act,
                        'why': why or 'the model gave no reason - treat it as a hunch' + (f' (about mid {mid})' if mid else '')})
        else: continue
        seen.add(key)
        if len(out) >= max_lines: break
    return out


_UNANSWERED_CLAIM = re.compile(
    r"\b(no (?:reply|response|answer)|nobody (?:told|replied|answered)|"
    r"has(?:n['’]?t| not) (?:been )?(?:told|answered)|"
    r"(?:i['’]?d|would) (?:reply|answer)|ask (?:him|her|them) to retry)\b", re.I)


def sent_reply_for(store, line: dict) -> dict | None:
    """Find the successful send behind an idea, including another message in its task thread."""
    action = line.get('action') or {}
    mid, tid = action.get('mid'), action.get('tid')
    reply = store.sent_reply(message_id=mid) if mid else None
    if not tid and mid:
        message = store.get_message(mid)
        tid = (message or {}).get('TaskId')
    return reply or (store.sent_reply(task_id=tid) if tid else None)


def contradicts_sent_reply(store, line: dict) -> bool:
    """Reject a model idea whose premise is disproved by an actual send receipt.

    The full reply is also put into the model's people context. This is the final factual gate:
    a model may overlook context, but Taskuary must not publish "nobody replied" when its own
    Review table records the exact response and the successful decision.
    """
    if not _UNANSWERED_CLAIM.search(str(line.get('text') or '')): return False
    return bool(sent_reply_for(store, line))


def _ids(raw) -> list[int]:
    if not isinstance(raw, list): raw = [] if raw in (None, '') else [raw]
    out = []
    for value in raw:
        try: sid = int(value)
        except (TypeError, ValueError): continue
        if sid not in out: out.append(sid)
    return out[:20]


def _inline(raw) -> list[dict]:
    """Data views written ON the Assistant report itself. Checking a system must never require
    saving a standalone report first (the owner, 2026-08-31) - a source card here is pulled the
    same way a chosen saved view is, and an Assistant still cannot watch itself."""
    if isinstance(raw, dict): raw = [raw]
    if not isinstance(raw, list): return []
    return [dict(x) for x in raw if isinstance(x, dict) and x.get('type') and x.get('type') != 'assistant'][:20]


def _watch(store) -> tuple[list[int], list[dict]]:
    """(saved view ids, own source cards) the Assistant report says to pull on every check."""
    c = (source(store) or {}).get('cfg') or {}
    return _ids(c.get('watch_source_ids')), _inline(c.get('watch_sources'))


def system_checks(store, source_ids=None, inline=None) -> str:
    """Silently pull this check's data views as the Assistant's live system context.

    Two kinds, neither of which files a report: sources written on the Assistant itself, and saved
    report pipelines chosen by id (whose query and credentials stay owned by that view). A saved
    report is the generic data-view contract - Intacct, REST, MCP, SQL, cloud, files and every
    future connector already know how to execute there - so both kinds run through that same
    executor, without touching a schedule, delivering anything, or applying a view's own AI summary.
    """
    saved, own = _watch(store)
    ids = saved if source_ids is None else _ids(source_ids)
    subs = own if inline is None else _inline(inline)
    if not ids and not subs:
        return '(none selected - add a data source, or choose saved data views, on Reports -> Assistant)'
    from . import reports
    found = {s['SourceId']: s for s in store.list_sources(active_only=False) if s.get('Channel') == 'report'}
    jobs = []                                     # (title, cfg to render, or a note to print instead)
    for sid in ids:
        src = found.get(sid)
        if not src: jobs.append((f'missing report source {sid}', None, 'This saved data view no longer exists.')); continue
        try: cfg_ = json.loads(src.get('ConfigJson') or '{}')
        except ValueError: cfg_ = {}
        title = str(cfg_.get('title') or src.get('Address') or f'report {sid}')
        if cfg_.get('type') == 'assistant': jobs.append((title, None, 'Skipped: an Assistant cannot watch itself.'))
        else: jobs.append((title, cfg_, None))
    for i, sub in enumerate(subs, 1):
        jobs.append((str(sub.get('label') or sub.get('title') or '').strip() or f"{sub.get('type')} #{i}", sub, None))
    blocks, used = [], 0
    for title, cfg_, note in jobs:
        if note: block = f'=== {title} ===\n{note}'
        else:
            # Its prompt controls the report when it runs independently. Here the Assistant
            # needs the underlying current facts so one cross-system instruction can judge them.
            raw_cfg = {k: v for k, v in cfg_.items() if k not in ('ai_prompt', 'ai_brain', 'ai_model')}
            try:
                headline, body = reports.render_report(store, raw_cfg, None)
                block = f'=== {title} ({headline}) ===\n{str(body or "(no data returned)")[:WATCH_SOURCE_CHARS]}'
            except Exception as e:
                block = f'=== {title} (FAILED) ===\n{str(e)[:500]}'
                logger.warning(f'assistant system check "{title}" failed: {e}')
        if used + len(block) > WATCH_TOTAL_CHARS:
            blocks.append(f'({len(jobs) - len(blocks)} additional configured views omitted by the context limit)')
            break
        blocks.append(block); used += len(block)
    return '\n\n'.join(blocks)


def _verdicts_block(store, cands: list, source: str = "") -> str:
    """The owner's standing verdicts - the SAME memory triage reads before it classifies
    (ingest.relevant_notes / applicable_notes).

    The assistant was the one brain in this app that never saw them. So "resident refunds are not
    our problem" stayed true for triage - which quietly files them - and was news to the brief,
    which went on raising the next refund thread as an idea worth acting on. A verdict the owner
    gives once should not have to be given again per surface.

    Scoped by the words of the material this check is READING, so a note about a topic nothing
    today touches costs nothing; global notes always apply.

    `source` is what the model was handed - the threads and the sender/subject lines - and it
    matters more here than the candidates do. A subject-scoped verdict is matched (ingest.topic_hit)
    against the words it was learned from, "resident refund request approved"; a candidate's
    `facts` is the MODEL'S PARAPHRASE of a thread, and "Barnes and Watson stall the same way"
    carries not one of those four words. So the ruling missed and the brief went on raising a
    subject the owner had closed. Match the source it summarised, not the summary."""
    from .ingest import relevant_notes
    text = ' '.join([source or '', *(str(c.get('facts') or c.get('text') or '') for c in cands)])[:8000]
    if not text.strip():
        return ''
    try:
        emails = sorted({(r.get('FromEmail') or '').lower()
                         for r in store.recent_messages(_since(2), limit=500) if r.get('FromEmail')})
        notes_, left = relevant_notes(store, emails, text)
    except Exception as e:
        logger.debug(f'assistant: standing verdicts skipped - {e}')
        return ''
    if not notes_:
        return ''
    more = f' ({left} more matched and were left out)' if left else ''
    return ('\n\nWHAT THE OWNER HAS ALREADY DECIDED - their standing verdicts, the same ones triage '
            f'reads before it files anything{more}. Never raise something they have ruled out, and '
            'never argue with one:\n' + '\n'.join(f'- {n}' for n in notes_))


def inputs(store, cands: list, head: str = 'CANDIDATES', watch_source_ids=None, watch_sources=None) -> str:
    """Everything one check reads, as the model sees it - the same text is the Reports tab's Preview
    (facts) and the run record (reports.run_report_source), so what it was given is never a guess."""
    now = datetime.now()
    away = ooo(store)
    from . import knowledge
    facts_text = ' '.join(str(c.get('facts') or '') for c in cands)[:4000]
    # built once: the model reads them, and so does the verdict matcher, which needs the real
    # subjects rather than the model's words about them
    said, recent = _people(store), _recent(store)
    return (f"NOW: {now.strftime('%A %d %B %Y %H:%M')}\n\n{head}:\n" + ('\n'.join(f"[{c['key']}] {c['facts']}" for c in cands) or '(none)')
            + knowledge.block(store, facts_text)
            + f"\n\nCONFIGURED SYSTEM CHECKS (pulled live for this check; failures are also worth noticing):\n{system_checks(store, watch_source_ids, watch_sources)}"
            + f"\n\nWHAT PEOPLE SAID (the last two days, by thread, newest first; the last lines of each, oldest first. "
              f"Each head quotes what triage decided when the latest line arrived: when you disagree, say so in your line - "
              f"'triage filed this as fyi, but...' - never raise a thread as if nothing had judged it):\n{said}"
            + '\n\nOUT OF OFFICE (from their auto-replies):\n' + ('\n'.join(f'- {k}: {v}' for k, v in away.items()) or '(nobody)')
            + f"\n\nCALENDAR (the next two days):\n{_calendar(store)}"
            + f"\n\nARRIVED IN THE LAST TWO DAYS (xN = that many alike; each line carries the latest message's words, a report's schedule, and a failure's cause):\n{recent}"
            + f"\n\nDONE THIS WEEK (my own work, with the agent's summary):\n{_week(store)}"
            + f"\n\nOPEN WORK:\n{_open(store)}\n\nALREADY SAID (never repeat):\n{_said(store)}"
            + _verdicts_block(store, cands, f'{said}\n{recent}')
            + f"\n\n{_notes_block(store)}")


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


def facts(store, watch_source_ids=None, watch_sources=None) -> str:
    """What a run would hand the model, as text - the Reports tab's Preview (reports.run_assistant)."""
    c = cfg(store); now = datetime.now()
    state = {i['Key']: i for i in store.list_ideas()}
    return inputs(store, [x for x in candidates(store, c) if fresh(state, x, now)],
                  'CANDIDATES (new since the last post)', watch_source_ids, watch_sources)


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
# ── the post's shape ────────────────────────────────────────────────────────────────────
# A flat list of lines is what the post used to be, and the owner (2026-09-01): "it should
# summarize into sections... summary of what the info emails said to you, then open tasks and
# what they are working on, then things you forgot to follow up from last week, then some stats".
# The lines themselves stay exactly as they were - each one still carries its own buttons and its
# own state, which is the whole value of them - they are just SORTED into sections that say what
# kind of thing you are looking at.
#
# Two of the sections are not the model's work at all. What is in flight and what the day counted
# are FACTS the hub already holds, and asking a model to restate them is how a brief starts
# inventing a task that is not there (the digest did exactly that: TQ-0032 "pending review" when
# nothing was pending). So they are computed here and the model never sees them as its own output.
SECTIONS = (
    ('people',  '📥', 'What people said',  'the ask in a thread, the thing somebody told you, the answer nobody picked up'),
    ('flight',  '🚀', 'In flight',         'what an agent has, what closed, what has gone quiet'),
    ('loose',   '🧵', 'Loose ends',        'what you are waiting on, what you promised, what went cold'),
    ('ideas',   '💡', 'Worth a thought',   'the connection nobody made, the thing to do now so the next ask never comes'),
    ('systems', '🛠️', 'From the systems',  'a threshold crossed, a job failing the same way twice, a number that moved'),
)
SECTION_KEYS = tuple(s[0] for s in SECTIONS)
# where a candidate lands when the model does not say (and it never says for hub-found ones)
KIND_SECTION = {'followup': 'loose', 'promise': 'loose', 'cold': 'loose', 'prep': 'people', 'idea': 'ideas'}


def section_of(line: dict) -> str:
    """Which section one line belongs in. The model's own choice wins for its ideas; a candidate
    the hub found is placed by its kind, which is the thing that produced it."""
    s = str(line.get('section') or '').strip().lower()
    if s in SECTION_KEYS: return s
    return KIND_SECTION.get(str(line.get('kind') or ''), 'ideas')


def in_flight(store) -> list:
    """What is being worked, straight off the tasks - never the model's recollection of it.
    [{ref, tid, title, state}] newest activity first, the ones an agent has at the top."""
    from . import terminal as term
    live = {}
    try: live = {t['taskId']: (t.get('agent') or t.get('label') or 'an agent') for t in term.live_sessions(tail=0) if t.get('taskId')}
    except Exception: pass
    out = []
    for t in store.list_tasks(active_only=True):
        if t.get('Status') not in ('open', 'in_progress', 'waiting'): continue
        tid = t['TaskId']
        agent = live.get(tid) or (t.get('RunAgent') if t.get('RunStatus') == 'running' else None)
        last = _dt(store.task_last_activity(tid) or t.get('UpdatedAt') or t.get('CreatedAt'))
        quiet_h = int((datetime.now() - last).total_seconds() // 3600) if last else None
        state = (f'{agent} has it' if agent
                 else 'a reply is drafted and waiting on you' if t.get('ReviewStatus') == 'pending'
                 else f'quiet for {quiet_h}h' if quiet_h and quiet_h >= 24
                 else 'nobody is on it')
        out.append({'tid': tid, 'ref': task_ref(tid), 'title': _short(t.get('Title'), 90),
                    'kind': t.get('Kind') or '', 'agent': agent or '', 'state': state,
                    'hot': bool(agent) or t.get('ReviewStatus') == 'pending'})
    out.sort(key=lambda r: (not r['hot'],))
    return out[:8]


def day_stats(store) -> list:
    """The few numbers that mean something, counted - not asked for. [{n, label}]."""
    from .categories import category_of, team_domains_of
    team = team_domains_of(store.get_settings())
    rows = store.feed(400, 1)
    cats = [category_of(r, team) for r in rows]
    tasks = [t for t in store.list_tasks(active_only=True) if t.get('Status') in ('open', 'in_progress', 'waiting')]
    return [{'n': len(rows), 'label': 'arrived today'},
            {'n': sum(1 for c in cats if c in ('info', 'automated', 'promo', 'feed', 'report')), 'label': 'wanted nothing'},
            {'n': len(tasks), 'label': 'open'},
            {'n': sum(1 for t in tasks if t.get('ReviewStatus') == 'pending'), 'label': 'waiting on you', 'hot': True}]


def _public(i: dict) -> dict:
    try: a = json.loads(i.get('ActionJson') or '{}')
    except ValueError: a = {}
    return {'id': i['IdeaId'], 'key': i['Key'], 'kind': i['Kind'], 'text': i['Text'], 'why': a.pop('why', ''), 'action': a, 'status': i.get('Status'),
            'section': section_of({'section': a.get('section'), 'kind': i['Kind']})}


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


def discussion_task(store, idea_id: int, actor: str = 'owner') -> dict:
    """Open one Timeline idea as a normal Assistant workspace conversation.

    The Timeline used to own a second, smaller chat implementation. A discussion now gets
    one non-coding task and the task's comment history becomes the sole conversation record.
    ``discussion_tid`` is separate from ``tid`` because an idea about an existing coding task
    must not turn that task's terminal workspace into an Assistant workspace.
    """
    i = store.get_idea(idea_id)
    if not i: raise ValueError(f'no idea {idea_id}')
    try: action = json.loads(i.get('ActionJson') or '{}')
    except ValueError: action = {}
    existing = action.get('discussion_tid')
    if existing and store.get_task(existing):
        return {'ideaId': idea_id, 'taskId': existing, 'ref': task_ref(existing), 'created': False}

    title = str(action.get('title') or i.get('Text') or 'Discuss assistant suggestion').strip()[:200]
    why = str(action.get('why') or '').strip()
    summary = str(i.get('Text') or '').strip()
    if why: summary += f'\n\nWhy the assistant raised it: {why}'
    tid = store.create_task({'Title': title, 'Summary': summary[:2000], 'Kind': 'general',
                             'Source': 'assistant', 'SourceRef': f'assistant:idea:{idea_id}'}, actor)
    seed = str(i.get('Text') or '').strip()
    if why: seed += f'\n\nWhy I raised this: {why}'
    if action.get('tid'): seed += f'\n\nRelated task: {task_ref(action["tid"])}'
    store.add_comment(tid, 'assistant', 'assistant_agent', seed)
    for turn in [t for t in (action.get('chat') or []) if isinstance(t, dict)]:
        text = str(turn.get('text') or '').strip()
        if text:
            role = 'assistant_agent' if turn.get('role') == 'assistant' else 'assistant_user'
            store.add_comment(tid, 'assistant' if role == 'assistant_agent' else actor, role, text)
    action['discussion_tid'] = tid
    store.set_idea_action(idea_id, action)
    store.audit('task', tid, 'create_from_assistant_idea', actor,
                detail={'idea_id': idea_id, 'message_id': i.get('MessageId'), 'related_task_id': action.get('tid')})
    return {'ideaId': idea_id, 'taskId': tid, 'ref': task_ref(tid), 'created': True}


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
    # Selecting system views is itself an explicit request for model judgement. It must keep
    # working even if the owner turns off the free-form "idea" producer in Settings.
    used, note, read = bool(llm and ('idea' in c['producers'] or any(_watch(store)))), '', ''
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
    say = [s | {'why': s.get('why') or s.get('facts') or ''} for s in say
           if fresh(state, s, now) and not contradicts_sent_reply(store, s)]
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
    # the two blocks the model does not write. What is in flight and what the day counted are facts
    # the hub already holds; asking a model to restate them is how a brief starts describing work
    # that is not there. Snapshotted onto the post so it still reads correctly tomorrow.
    store.set_brief(mid, json.dumps({'ideas': [_public(i) for i in rows], 'reviewed': rv,
                                     'flight': in_flight(store), 'stats': day_stats(store)}))
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
