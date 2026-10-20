"""The assistant on the Timeline: a check every 30 minutes, a post only when it has something to say.

Triage judges each message as it arrives and then nothing ever spoke up later - the reply the
owner sent on Monday and never heard back on, the meeting in two hours with five mails of
history behind it, the task that went quiet. This is the voice that does: on its own clock it gathers what the hub can see
(followups: the owner wrote last and asked for something; prep: meetings ahead, with what came
before them; cold: work nothing has touched; and its own ideas
from the day's mail), asks the model for its read GIVEN WHAT IT ALREADY SAID, and posts only what
is new as ONE row on the Timeline. The owner can talk back to every line; a correction or question
gets an answer and becomes context for later checks. A concrete suggestion may also offer Follow up
(the chase is drafted on the task) or Make it a task.

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
arrival (including machine mail), with each report's schedule, when it last ran and what that run did, and each failure's cause beside the count. That is where "Yittie said exporting freezes the
app - and she is in Monday's meeting" comes from.

It also leaves itself a NOTE: each check ends with what it looked at and found nothing in, when
something becomes worth raising, whatever it would otherwise work out again - and the next check
starts by reading it (assistant_notes). Half-hourly checks are cheap only if each one does not
start from zero; a quiet check still rewrites the note, it just posts nothing. How it SPEAKS is
COUNSEL.md (Settings → Docs) - the owner edits that to change its voice and what it takes a position on;
the report's prompt is what it watches for.
"""
import json, math, re, threading
from datetime import datetime, timedelta
from loguru import logger

from . import kinds as task_kinds
from .store import is_model_idea, task_ref, auto_code_enabled
from .timewords import ago_m, plural, span
from .assistantblocks import said_number   # the payload's own English for a window: 'the last two days'

CHANNEL = 'assistant'
PRODUCERS = ('followup', 'promise', 'prep', 'cold', 'idea')
DAYS = 30                  # how far back followups and promises are read
CHASE_STEPS = (2, 5, 9, 14, 21)   # days of silence at which an open follow-up or promise is said again
FORCED_CHASES = 2                 # of those, said per run even when the model let them go
MAX_LINES = 5              # lines per post by default - a post nobody reads to the end is a post that failed
POST_TOKENS = 900
WATCH_SOURCE_CHARS = 6_000
WATCH_TOTAL_CHARS = 18_000
PEOPLE_THREADS, PEOPLE_CHARS = 14, 5200   # what people said: threads shown, and the block's ceiling
SOUL_CHARS = 20000                        # SOUL.md goes whole; this only stops a runaway document
_LOCK = threading.Lock()   # one check at a time: two clocks firing in the same second posted the same line twice (2026-08-29 23:59:02)
# The editable instruction - what a real assistant watches for. Seeded as the 'Assistant' report
# on the Reports tab (store.__init__), so the owner edits it there like the Morning digest's;
# this copy is the default and the fallback. CONTRACT (the JSON shape) stays in code.
# Each section names the source card it reads, as a token (reports.substitute): the card's rows are
# placed right there when the check runs, so the prompt IS the payload's shape - the owner reads
# which data feeds which instruction, and can move or drop a card by editing the words.
PROMPT = (
    'You are my assistant; every 30 minutes you read the sources below and check in. Tell me only what a sharp human assistant who had READ everything '
    'would lean over and say - never a summary of my inbox, never a count I can see myself. A good line connects two things I '
    'have not connected, or names the one thing I am about to miss. Read, in this order of worth:\n'
    '0. CONFIGURED SYSTEM CHECKS - current views from finance, operations, CRM, infrastructure, or any other connected system (they follow '
    'this prompt, each under its own name). Look for threshold breaches, unusual totals, sharp changes, missing expected activity, and facts '
    'that conflict across systems.\n'
    '1. WHAT PEOPLE SAID, who is out of office, what arrived, and what waits on somebody:\n[taskuary.messages]\n'
    'The actual words, by thread: the ask buried in a chat ("can you fill out the form?") that got a '
    'reply but not the thing itself; the colleague mentioning in passing that a system fails "every day 4-5"; the person '
    'answering a question nobody asked me; the thread where the last word is theirs and it wants something from me. Say who '
    'and what, and whose move it is - "Marcus asked on Thursday for X and it has not gone; it is mine, before his Monday 1pm". '
    'What you would do about it is a suggestion, said apart from the finding, and only when it adds something. '
    'What I am waiting on and have not chased (CANDIDATES followup) - but check OUT OF OFFICE first: a chase to someone '
    'who is away is worse than silence; say when they are back instead. What I promised and have not done (promise): the date '
    'I gave, and whether it has passed. What the machines are telling me, read not counted: a report marked FAILED says WHY '
    '(the error is in the line) - name the cause; a job that fails the same way N times is one finding, with the cause; a report '
    'whose every run says "0 rows" is a report nobody needs. Reports carry their schedule: "on app start" firing 20 times means '
    'the app was started 20 times, not that the scheduler is broken. The same in reverse: read WHEN TASKUARY WAS RUNNING before '
    'calling a report late or the scheduler dead - a report cannot fire while the app is shut, an overnight close is not a missed '
    'run, and minutes after a launch nothing due today has had its turn yet.\n'
    '2. THE CALENDAR:\n[taskuary.calendar]\n'
    'For each meeting in the next two days, what in the mail and chats bears on it - the person in the room '
    'who asked me something this week, the thread it will be about. A recurring standup with nothing behind it needs no line.\n'
    '3. MY OWN WORK:\n[taskuary.work]\n'
    'Work gone quiet (cold): push it or drop it - say which. The fix that keeps coming back, the task that closed without '
    'shipping, the process change worth proposing. Name the evidence: TQ-ref, count, sender. Never restate what I did.\n'
    '4. THE APP AND THE SYSTEMS PEOPLE NAME:\n[taskuary.systems]\n'
    '5. WHAT REPEATS - once a week, a month of my traffic counted:\n[taskuary.automation]\n'
    'The automation worth having IN THIS APP, ranked by the minutes it saves me a week and resting on the numbers: a skip rule on '
    'a sender nobody reads, an auto-answer for the question that always gets the same reply, a standing prompt, a scheduled '
    'report, auto-draft for drafts I always approve untouched. Never one the existing rules already cover; one a week is plenty, '
    'none when nothing repeats enough.\n'
    '6. WHAT I ALREADY KNOW - never repeat anything under ALREADY SAID, reworded or not; use my notes; draw on the knowledge base by name:\n[taskuary.memory]\n'
    'Be useful, not busy: a check with nothing NEW posts nothing, and most checks are that. When you do speak, prefer the '
    'specific over the general: a name, a date, a quoted phrase, a cause. One idea about my own work a day is right; three is '
    'noise. A fact that CHANGES an earlier line (they are out of office; the failure has a cause; they answered) is new and worth one line.\n'
    'End every check with a note to your next one: what you looked at and found nothing in, when something becomes worth '
    'raising (a date, a length of silence), anything you would otherwise have to work out again - facts, never rules.')

# An Assistant report with sources written on it is a monitor, not the general check above. Its
# instruction and those source results are the whole input. In particular it must not quietly add
# inbox, calendar, tasks, Morning digest material, or another Assistant report's configured views.
SYSTEMS_PROMPT = (
    'You are monitoring only the configured data sources in this report. Apply the owner\'s instruction '
    'to the returned data and say only what needs attention now. Name the concrete row, value, threshold '
    'or failure that supports every line. Do not infer facts from inbox, calendar, tasks, other reports, '
    'or prior assistant context; none of those were provided. Nothing actionable -> {"say": []}.\n'
    'SILENCE IS THE NORMAL ANSWER. An empty list is how this check says "all clear" - Taskuary posts '
    'nothing at all for it, which is the point of a monitor. Never return a line that only says '
    'everything is fine, and ignore any instruction below asking you to; if the owner wants to see '
    'every run they set that on the report, not in your answer.')
SYSTEMS_CONTRACT = (
    '\n\nAnswer JSON only: {"say": [{"key": "idea:<short stable slug>", "text": "<one line, '
    'under 30 words: the finding - what is true, with the row or value>", "whose": "<whose move it is: the owner, someone '
    'else by name, or nobody yet>", "suggest": "<what I would do about it, one short line, or null>", "section": "systems", '
    '"why": "<the exact row, value, threshold or failure behind it>", "mid": null, "task": null}], '
    '"notes": ""}. At most {max_lines} entries. Use only CONFIGURED DATA SOURCES. If nothing '
    'needs attention, return {"say": []}.')
# a stock prompt still starting like one of these is healed to PROMPT (store.__init__)
# ...and the shipped prompts that open like today's, by their sha256: an unedited copy saved on the seeded row is healed
# to PROMPT (store.py) - 2026-09-25, the one before the automation card [taskuary.automation] joined it
OLD_PROMPT_SHA = ('06a4ec48fcec9d8bbc9fc6f423f52360aa1b0a2e7f5affe31582e7da56d1e302',
                  # 2026-10-09, before the finding and the suggestion were said apart ("what I would do")
                  'e37ca9e1a91e6880a304306482a0a682b5260bc402639cc94a9cc6e0f8a6ef3c')
OLD_PROMPT_HEADS = ('You are my assistant. Once an hour,', 'You are my assistant. Every 20 minutes you check in;',
                    'You are my assistant. Every 30 minutes you check in;',
                    'You are my assistant; every 30 minutes you check in.',
                    'You are my assistant; every 30 minutes you check in across the systems and conversations I chose.')


def cfg(store) -> dict:
    s = store.get_settings()
    def n(k, d):
        try: return max(0, int(s.get(k) or d))
        except (TypeError, ValueError): return d
    raw = s.get('assistant_producers')
    prod = {p.strip() for p in (raw if raw is not None else ','.join(PRODUCERS)).split(',') if p.strip()}
    fh = n('assistant_followup_hours', 24)
    # promise_h is the SAME setting until a report says otherwise (assistantblocks.producer_cfg):
    # the global knob is one number, and two blocks reading it is not two knobs
    return {'followup_h': fh, 'promise_h': fh, 'cold_d': n('assistant_cold_days', 3), 'max': max(1, n('assistant_max_lines', MAX_LINES)),
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
def _cut(s, n=100):
    t = ' '.join(str(s or '').split())
    return t if len(t) <= n else t[:n].rsplit(' ', 1)[0] + '…'   # a subject is cut on a word, never at "I'd"
def _dt(s):
    try: return datetime.fromisoformat(_ts(s))
    except ValueError: return None
def _when(s) -> str:
    """'Thu 28 Aug 11:21' - a day name the model can hold against a calendar, no year."""
    d = _dt(s); return d.strftime('%a %d %b %H:%M') if d else str(s or '')[:16]
# the corporate wrapper around a body: one pattern for every surface, kept in triage.py (PW-029)
from .triage import _BANNER
def _gist(body, n=180) -> str:
    """The sender's own words, one line: banner, legal footer, signature and the chain they wrote on
    top of all gone (triage.own_words) - a preview of a forward used to be the forward (TQ-0665)."""
    from .triage import own_words
    return _short(own_words(_BANNER.sub('', str(body or ''))), n)


def _reply_text(review: dict | None) -> str:
    """The words that left through Review, never an unsent draft."""
    return str((review or {}).get('FinalText') or (review or {}).get('DraftText') or '').strip()

from .autoreply import is_auto as _ooo_row                 # the mail system's own auto-reply mark, never a subject (autoreply.py)
from .counsel import is_invite as _cal_mail                # a calendar's own mail: its MIME part / Graph type, never a subject
_UNTIL = re.compile(r'\b(until|through|returning( on)?|back (on|in the office on))\s+([A-Z][a-z]+day,?\s+)?([A-Z][a-z]+ \d{1,2}(st|nd|rd|th)?|\d{1,2}/\d{1,2}(/\d{2,4})?)', re.I)
def ooo(store, days: int = 14) -> dict:
    """{sender email: 'out until Monday August 31st (auto-reply Thu 28 Aug)'} from the auto-replies in the
    window - a chase to someone who is away is worse than silence, and the hub already holds the answer."""
    out = {}
    for r in store.recent_messages(_since(days), limit=600):
        if not _ooo_row(r): continue
        em = (r.get('FromEmail') or '').lower()
        if not em or em in out: continue                          # newest first: the latest auto-reply wins
        m = _UNTIL.search(str(r.get('BodyText') or ''))
        out[em] = (f"out {m.group(0)}" if m else 'out of office') + f" (auto-reply {_when(r['SentAt'])[:10]})"
    return out


# ── the candidates: facts the hub can find, and the model's own reading of the words ─────────
def _owner_closed(store, key: str, sent) -> bool:
    """The owner put this promise down (done or dismissed on its Advisor line) - for the readers that do not go
    through fresh(): the brief's loops, the day's promise line. A later promise on the thread is a new one."""
    i = store._one('SELECT Status, Sig FROM idea WHERE Key=?', (key,))
    return bool(i and i.get('Status') in ('dismissed', 'done') and str(i.get('Sig') or '').split('|')[0] == _ts(sent))


def _other_side(store, cid):
    """The last word of theirs on the thread, or None when there is nobody to chase: no inbound at all, or a report,
    the Advisor's own thread, an auto-reply or a calendar response - the mail system wrote those (2026-10-06). Nor a
    machine's mail: the owner answering a portal's notification with a question raised "No answer from Vendor Portal in
    3 days - follow up?" - a noreply address never answers, and nobody is there to chase (the rail Advisor's eval)."""
    from .categories import sender_class
    inbound = store.last_inbound_in(cid) if cid else None
    if not inbound: return None
    if inbound.get('Channel') in ('report', CHANNEL) or _ooo_row(inbound) or _cal_mail(inbound): return None
    if sender_class(inbound) in ('automated', 'bulk'): return None
    return inbound


def _own(r: dict) -> str:
    from .triage import own_words
    return own_words(str(r.get('BodyText') or ''))


def followups(store, hours: int, want=('followup', 'promise')) -> list:
    """What the owner is owed and what they owe, `hours` old or more, read from the MODEL's verdict on their own sent
    words (sentjudge.py) - never a word list (the owner, 2026-10-11: "remove step 1. Everything should be ai").
    followup: the owner's last word on the thread asked them for something - theirs to answer, ours to chase.
    promise: the owner committed to something and no later message of theirs delivered it - the other side replying
    does not close it ("Great, thanks!" is not the budget); the owner closing the line does. A sent message not judged
    yet is in neither (sentjudge.blind says so). A sender's auto-reply rides on the line: silence from someone away is
    not silence."""
    cut = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    out, away, seen, rows = [], None, set(), []
    # ...a promise that is already a TASK on the owner (store.task_for_promise) is a row on the rail, not a line here
    if 'promise' in want: rows += [('promise', r) for r in store.open_promises(_since(DAYS), cut) if not store.promise_task(r['MessageId'])]
    if 'followup' in want:
        rows += [('followup', r) for r in store.owner_last_words(_since(DAYS), cut) if (store.sent_verdict(r['MessageId']) or {}).get('AsksThem')]
    for kind, r in sorted(rows, key=lambda kr: _ts(kr[1].get('SentAt')), reverse=True):
        cid = r['ConversationId']
        if (kind, cid) in seen: continue                            # the newest open promise on a thread speaks for it
        seen.add((kind, cid))
        if kind == 'promise' and _owner_closed(store, f'promise:{cid}', r.get('SentAt')): continue
        inbound = _other_side(store, cid)
        if not inbound: continue
        # three Let-it-gos on one person and the Advisor stops raising them - the spec's one rule about silence (2026-10-12)
        if kind == 'followup':
            from . import outcomes
            if outcomes.let_go_count(store, (inbound.get('FromEmail') or '').lower()) >= 3: continue
        body = _own(r)
        who = inbound.get('FromName') or inbound.get('FromEmail') or 'them'
        sent = _dt(r['SentAt']) or datetime.now()
        days = max(1, int((datetime.now() - sent).total_seconds() // 86400))
        subj = _short(inbound.get('Subject'), 60)
        if away is None: away = ooo(store)
        gone = away.get((inbound.get('FromEmail') or '').lower(), '')
        # ...and SILENCE THAT GROWS is said again: the Sig was the last word alone, so a follow-up said once came back only
        # when the thread moved - a vendor who never answered was raised on day 2 as the second line of a 6:56 post, and
        # not again for eleven days (2026-10-06). Each step it crosses is new; a dismissed or done one stays down (fresh).
        step = f"|{sum(1 for d in CHASE_STEPS if days >= d)}"
        if kind == 'promise':
            what, due = r.get('PromiseWhat') or _short(body, 70), r.get('PromiseDue')
            late = f" - it was due {due}" if due and due < datetime.now().strftime('%Y-%m-%d') else f" - due {due}" if due else ''
            out.append({'key': f"promise:{cid}", 'kind': 'promise', 'sig': _ts(r['SentAt']) + step,
                        'facts': f"You told {who} on {_ts(r['SentAt'])[:10]}" + (f" re \"{_short(r.get('Subject'), 70)}\"" if subj else '') + f": \"{_short(body, 160)}\" - "
                                 f"the promise: {what}{late}; made {ago_m(days * 1440, long=True)}, and nothing you have sent since delivers it.",
                        'text': f"You told {who} you would {what}{late} - {ago_m(days * 1440, long=True)}" + (f" on \"{subj}\"" if subj else '') + ". Done?",
                        'action': {'type': 'message', 'mid': inbound['MessageId'], 'tid': inbound.get('TaskId')},
                        'who': who, 'what': what, 'due': due})
        else:
            from . import outcomes
            late_day = outcomes.late_after(store, (inbound.get('FromEmail') or '').lower(), int(store.get_setting('slipped_default_days', 5) or 5))
            out.append({'key': f"followup:{cid}", 'kind': 'followup', 'sig': _ts(r['SentAt']) + (':away' if gone else '') + step,
                        'facts': (f"You wrote {who} on {_ts(r['SentAt'])[:10]} re \"{_short(r.get('Subject'), 70)}\": \"{_short(body, 160)}\" "
                                  f"- nothing has come back in {plural(days, 'day')}; late for them after {late_day} days." + (f" BUT {who} is {gone}." if gone else '')),
                        'text': (f"No answer from {who} in {plural(days, 'day')} on \"{subj}\" - " + (f"they are {gone}; I'd wait." if gone else 'follow up?')),
                        # the person key, the day asked and whether they are away: what the slipped lane reads (funnel.slipped_followup)
                        'action': {'type': 'followup', 'mid': inbound['MessageId'], 'tid': inbound.get('TaskId'),
                                   'who_email': (inbound.get('FromEmail') or '').lower(), 'asked_at': _ts(r['SentAt']), 'away': bool(gone)},
                        'who': who, 'subject': subj, 'days': days, 'away': gone})
    return out


def promises_due(store, now=None) -> list:
    """The owner's own open promises whose day - the one the model read out of their words (sentjudge) - is TODAY.
    [{'who', 'what', 'mid'}] - the arrival's one promise line (welcome.py)."""
    now = now or datetime.now()
    day, out = now.strftime('%Y-%m-%d'), []
    for r in store.open_promises(_since(DAYS), now.strftime('%Y-%m-%d %H:%M:%S')):
        if r.get('PromiseDue') != day or _owner_closed(store, f"promise:{r['ConversationId']}", r.get('SentAt')): continue
        inbound = store.last_inbound_in(r['ConversationId']) or {}
        out.append({'who': inbound.get('FromName') or inbound.get('FromEmail') or 'them', 'what': r.get('PromiseWhat') or 'get back to them',
                    'mid': r.get('MessageId')})
    return out


ASKING = ('task', 'reply_only')       # the triage intents that want something of the owner


def unanswered(store, days: float = 2, hours: int = 3) -> list:
    """The mirror of followups(): threads where THEIR last word asked the owner for something - TRIAGE'S stored
    verdict on it said task or reply_only - and nothing of the owner's came after it. See their_asks()."""
    return their_asks(store, days, hours)[0]


def their_asks(store, days: float = 2, hours: int = 3) -> tuple:
    """(asks, unjudged). asks: their last word is an ask by triage's own verdict (route.VerdictJson) and nothing of the
    owner's came after it - the ask that slipped, `hours` old at least (fresh mail is not yet missed). Each carries what
    covers it: a draft on the task, a task and its state, or nothing - the morning brief's "what slipped".
    unjudged: their last word has NO verdict - triage failed, returned nothing usable, or never ran - so whether it asks
    anything is not known. It was a regex here (_ASKS) and missed "Please approve the invoice." outright; a message
    triage never read is said as not judged, never silently "not an ask" (the owner, 2026-10-11)."""
    from .categories import sender_class, team_domains_of
    from .autoreply import STATUS as AUTO
    from .triage import own_words
    settings = store.get_settings(); team = team_domains_of(settings); me = (settings.get('owner_email') or '').lower()
    cut = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    pend = {r['TaskId'] for r in store.list_reviews('pending')}
    # a note the owner handed an agent (channel `own`) is their own word, not an ask of them - it put
    # "You asked ... no answer from you" under People want for two handoffs the agents had already done
    mine = lambda c: (c.get('Status') == 'context' or c.get('Direction') == 'out' or c.get('Channel') == 'own'
                      or (c.get('FromEmail') or '').lower() == me)
    seen, out, blank, away = set(), [], [], None
    # 500 rows was two quiet days; the away window reaches back up to three weeks (welcome.away_days), so the page grows with it
    for r in store.recent_messages(_since(days), limit=max(500, min(5000, int(days * 250)))):
        cid = r.get('ConversationId')
        if not cid or cid in seen or r.get('Channel') in ('report', CHANNEL) or _ooo_row(r): continue
        seen.add(cid)
        if sender_class(r, team) != 'person': continue
        chain = sorted((c for c in store.thread_messages(conversation_id=cid, limit=12) if c.get('Status') != 'skipped'), key=lambda c: _ts(c.get('SentAt')))
        if not chain: continue
        last = chain[-1]
        # the owner's own rule (ignore), a feed connection and an auto-reply were settled without triage on purpose
        if mine(last) or _ts(last.get('SentAt')) > cut or last.get('Status') in ('ignored', 'feed', AUTO): continue
        body = own_words(_BANNER.sub('', str(last.get('BodyText') or '')))
        v = store.message_verdict(last['MessageId'])
        if v is not None and v.get('intent') not in ASKING: continue
        tid = next((c.get('TaskId') for c in reversed(chain) if c.get('TaskId')), None)
        t = store.get_task(tid) if tid else None
        # a task closed AFTER the ask is what answered it; an ask that came after the close is new work
        if t and t.get('Status') in ('done', 'dropped') and _ts(t.get('ClosedAt')) >= _ts(last.get('SentAt')): continue
        who = last.get('FromName') or last.get('FromEmail') or 'someone'
        m = (datetime.now() - (_dt(last['SentAt']) or datetime.now())).total_seconds() / 60
        ago, said_ago = span(m, long=True), ago_m(m, long=True)
        if v is None:
            why = 'triage failed on it' if last.get('Status') == 'error' else 'triage has not judged it'
            blank.append({'key': f'unjudged:{cid}', 'kind': 'unjudged', 'sig': _ts(last['SentAt']),
                          'facts': f"{who} wrote {_when(last['SentAt'])} re \"{_short(last.get('Subject'), 70)}\": \"{_gist(body, 160)}\" - {why}, "
                                   f"so whether it asks you anything is NOT KNOWN; nothing of yours came after it in {ago}",
                          'action': {'type': 'message', 'mid': last['MessageId'], 'tid': tid},
                          'who': who, 'gist': _gist(body, 60), 'ago': said_ago, 'why': why})
            continue
        cover = ('a draft waits for you on the task' if tid in pend else
                 f"{task_ref(tid)} is {t.get('Status')}" + (', an agent is on it' if t.get('RunStatus') == 'running' else '') if t else 'no task, no draft')
        if away is None: away = ooo(store)
        gone = away.get((last.get('FromEmail') or '').lower(), '')
        out.append({'key': f'asked:{cid}', 'kind': 'asked', 'sig': _ts(last['SentAt']),
                    'facts': f"{who} asked {_when(last['SentAt'])} re \"{_short(last.get('Subject'), 70)}\": \"{_gist(body, 160)}\" - no answer from you in {ago}; {cover}"
                             + (f"; {who} is {gone}" if gone else ''),
                    'text': f"{who} asked \"{_gist(body, 60)}\" {said_ago} - no answer yet ({cover})",
                    'action': {'type': 'message', 'mid': last['MessageId'], 'tid': tid},
                    'who': who, 'gist': _gist(body, 60), 'ago': said_ago})
    return out, blank


def cold(store, days: int) -> list:
    """Open work nothing has touched for `days`: no comment, no message, no run. A live agent on
    it is activity; a draft waiting on the task is the owner's to move."""
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
                             + (' and a draft waits for you on the task' if wait else ''),
                    'text': (f"{ref} has a reply waiting on you for {age} days - \"{_short(t.get('Title'), 60)}\"" if wait
                             else f"{ref} has sat quiet for {age} days - \"{_short(t.get('Title'), 60)}\". Push it or drop it?"),
                    'action': {'type': 'task', 'tid': t['TaskId']}})
    return out


_AGENDA = {}               # one calendar read per check: prep's candidates and the CALENDAR block share it
_AGENDA_FRESH = 60         # seconds a read stays good
_AGENDA_LOCK = threading.Lock()

def _agenda(store, *, block: bool = True, days: int = 2) -> list:
    """The next `days` of meetings - two, unless the owner widened the CALENDAR block - cached for
    _AGENDA_FRESH seconds.

    Reading this is a LIVE Microsoft Graph call - a token POST plus one calendarView per mailbox,
    20s timeout each. Whoever found the cache stale used to pay for all of it, and the pile reads
    it: most /api/funnel/pile calls were ~5s and the one that refreshed was 45s (2026-09-09).

    So a caller the OWNER is waiting on passes block=False and gets what is known right now while
    the refresh runs on its own thread. A report composing a brief keeps the blocking read - an
    empty calendar in the morning digest would be a wrong answer, not a slow one.

    A cached read WIDER than the caller asked for is trimmed rather than fetched again: the pile's
    two days and a widened CALENDAR block then share one Graph call instead of evicting each other
    every minute.
    """
    if store.get_setting('calendar_enabled', '1') != '1': return []
    wide = _AGENDA.get('days', 0) >= days
    if wide and _AGENDA.get('at', 0) > datetime.now().timestamp() - _AGENDA_FRESH: return _within(_AGENDA['events'], days)
    if block: return _read_agenda(store, days)
    _refresh_agenda(store, days)
    return _within(_AGENDA.get('events', []), days) if wide else []


def _within(events: list, days: int) -> list:
    cut = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    return [e for e in events if _ts(e.get('start')) <= cut]


def _read_agenda(store, days: int = 2) -> list:
    from . import calendar as cal
    try: ev = [e for e in (cal.agenda(store, days=days).get('events') or []) if not e.get('all_day')]
    except Exception as e:
        logger.debug(f'assistant: calendar skipped - {e}'); ev = []
    _AGENDA.update(at=datetime.now().timestamp(), events=ev, days=days)
    return ev


def _refresh_agenda(store, days: int = 2):
    """One refresh at a time, whoever asked for it. The stamp is written by _read_agenda even when
    the read failed, so a calendar nobody can reach is retried on the clock rather than on every
    read - which is what kept a stalled Graph call in front of the pile."""
    with _AGENDA_LOCK:
        if _AGENDA.get('reading'): return
        _AGENDA['reading'] = True
    def go():
        try: _read_agenda(store, days)
        finally: _AGENDA['reading'] = False
    threading.Thread(target=go, name='taskuary-agenda', daemon=True).start()


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


def _asks_and_promises(store, c: dict) -> list:
    """The two halves of followups(). ONE pass while they share a window - that is the order the
    payload has always listed them in, interleaved by thread - and one pass each the moment a report
    gives them different hours, because then there is no single window to make one pass with."""
    want = tuple(k for k in ('followup', 'promise') if k in c['producers'])
    fh, ph = c['followup_h'], c.get('promise_h', c['followup_h'])
    if not want: return []
    if fh == ph or len(want) == 1: return followups(store, fh if 'followup' in want else ph, want)
    return followups(store, fh, ('followup',)) + followups(store, ph, ('promise',))


def candidates(store, c: dict) -> list:
    out = []
    for name, fn in (('followup/promise', lambda: _asks_and_promises(store, c)),
                     ('prep', lambda: prep(store) if 'prep' in c['producers'] else []),
                     ('cold', lambda: cold(store, c['cold_d']) if 'cold' in c['producers'] else [])):
        try: out += fn()
        except Exception as e: logger.warning(f'assistant: {name} candidates failed - {e}')
    # ...minus what a task already covered (asks.py): an hour after a task emailed Paula, "follow up with Paula" is not news
    from . import asks
    try: return asks.not_just_said(store, out, c.get('followup_h') or 24)
    except Exception as e:
        logger.warning(f'assistant: could not check candidates against recent tasks - {e}'); return out


# ── the report proposes (the assistant-runs-the-app design, 2026-09-18) ──────────────────────────
# Two idea kinds the REPORT raises and the chat assistant never invents: the app's own health (a deterministic
# read, no model) and a system worth connecting (the Advisor's own pass judges it, below). Each lands as a row like every other idea,
# is taken or declined in the walk, and the decline is remembered on its key (fresh() below - a
# constant `sig` means a dismissed idea never returns; a health sig is the failure's own stamp, so a
# NEW failure comes back after the old one was seen).
def health_ideas(store, now: datetime = None) -> list:
    """A report that failed its last three runs; a workflow never run since it was saved; a live
    connection erroring; a brain left blank while mail waits. One row each, the door is the tab that fixes it."""
    from . import appfacts
    out, now = [], now or datetime.now()
    for r in appfacts.reports(store):
        if not r['active']: continue
        runs = store.report_runs(r['source_id'], 3) or []
        if len(runs) >= 3 and all(x.get('failed') for x in runs):
            # the SAME failure is one idea, said once: the sig is the error, numbers read as one (a timestamp, a run
            # id). It was the last run's time, so every failed run re-raised it (the owner, 2026-09-28: "as long as
            # it's not the same idea a 100 times"); a different error is a new fact and comes back
            sig = re.sub(r'\d+', '#', ' '.join(str(runs[0].get('error') or '').split()))[:120]
            out.append({'key': f"health:report:{r['source_id']}", 'kind': 'health', 'sig': sig,
                        'text': f"{r['title']} failed its last three runs - {_short(runs[0].get('error') or 'no reason recorded', 80)}.",
                        'action': {'type': 'health', 'tab': 'Reports', 'hash': f"report={r['source_id']}", 'source_id': r['source_id'],
                                   'why': 'three failures in a row is a broken report, not a bad day'}})
        elif r['workflow'] and not runs:
            out.append({'key': f"health:workflow:{r['source_id']}", 'kind': 'health', 'sig': 'never',
                        'text': f"{r['title']} is a workflow that has never run - its clock is {r['schedule'] or 'not set'}.",
                        'action': {'type': 'health', 'tab': 'Reports', 'hash': f"report={r['source_id']}", 'source_id': r['source_id'],
                                   'why': 'a workflow that never ran is either mis-clocked or waiting on a sign-in'}})
    # An erroring CONNECTION is not raised here: the rail already carries it as its own "stopped answering" row
    # (funnel.broken_connections), and said twice it became an idea, then a task, then a coding agent investigating
    # a connection the owner was looking at (the owner, 2026-09-30: "don't need both ... if it fails we don't need
    # advisor to tell us").
    try:
        waiting = len(store.pending_triage(limit=50))
        from . import llm
        brain = str(store.get_setting('triage_ai') or '').strip()
        if waiting and not brain and not any(x['active'] and x['has_secret'] for x in appfacts.connections(store) if x['type'] in llm.AI_TYPES):
            out.append({'key': 'health:brain', 'kind': 'health', 'sig': 'no-brain',
                        'text': f'{plural(waiting, "message")} wait{"s" if waiting == 1 else ""} for triage and no brain is set to read {"it" if waiting == 1 else "them"}.',
                        'action': {'type': 'health', 'tab': 'Settings', 'hash': 'settings=config&group=How%20mail%20is%20sorted',
                                   'why': 'nothing is judged until a brain is chosen'}})
    except Exception as e: logger.debug(f'health: the brain check was skipped - {e}')
    return out


# A SYSTEM WORTH CONNECTING is the Advisor's own call, made in its one pass (the owner, 2026-10-11: connector suggestions
# "should be ai as well", and part of the Advisor, not a judge of their own). A name matcher used to pick the system and
# count its threads - whole-word product names, a GENERIC blocklist, a title-splitting rule - and the model saw only the
# card it had already picked: "Federal Holiday - Monday October 12th" was a thread about Monday.com until a veto sentence
# asked the model to undo it. Now the month's thread subjects ride in the Advisor's prompt numbered (the `connectors`
# block), beside the cards nothing here reads, and the model cites the threads really about one. Code only checks that
# what it cited exists, clears the floor, and was never raised before.
CONNECT_THREADS = 300      # newest inbound threads it reads - a month on a busy mailbox is more, and every run pays for them


def connect_evidence(store, days: int = 30, floor: int = 3) -> dict:
    """What the Advisor reads to judge a system worth connecting: one line per inbound THREAD of the last `days`
    (sender's domain + subject, the owner's own domains blanked - three replies on one pull request are one thread, and
    the app's own posts are no thread at all, TQ-0651 / store.inbound_threads), what the owner's routing facts and report
    titles name, and the catalogue cards neither connected nor raised before. SOUL.md is already whole in the prompt."""
    from . import appfacts, connectorcatalog
    from .senders import own_domains
    threads = []
    try:
        mine = own_domains(store)
        for m in sorted(store.inbound_threads(days=days), key=lambda r: -int(r.get('MessageId') or 0))[:CONNECT_THREADS]:
            frm = str(m.get('FromEmail') or '')
            dom = frm.rsplit('@', 1)[-1].lower() if '@' in frm else ''
            threads.append(f"{dom if dom and dom not in mine else '-'} | {_short(m.get('Subject'), 120) or '(no subject)'}")
    except Exception as e: logger.debug(f'connect: the threads were not read - {e}')
    named = []
    try: named += [f"routing fact: {_short(f['Value'], 120)}" for f in store.routing_facts(field='system')]
    except Exception: pass
    try: named += [f"report: {_short(r['title'], 120)}" for r in appfacts.reports(store)]
    except Exception: pass
    connected = {c['type'] for c in appfacts.connections(store) if c['active']}
    raised = {i['Key'] for i in store.list_ideas() if str(i['Key']).startswith('connect:')}
    offer = {c['type']: c for c in connectorcatalog.cards() if c['type'] not in connected and f"connect:{c['type']}" not in raised}
    return {'threads': threads, 'named': named, 'offer': offer, 'floor': floor, 'soul': bool(str(store.doc('soul') or '').strip())}


def connect_text(ev: dict) -> str:
    """The block's body: the cards, what the owner's own setup names, then the threads - numbered, because the numbers
    are what the model cites and what the owner is told was counted. Nothing to offer or nothing to read prints nothing."""
    if not ev or not ev['offer'] or not (ev['threads'] or ev['named'] or ev['soul']): return ''
    # the card's group says what kind of system it is in two words; its desc is setup prose ("Paste a PAT...") and was
    # two thirds of the block's tokens, paid on every run
    cards = '\n'.join(f"{t}: {c['title']} ({c.get('group') or 'other'})" for t, c in ev['offer'].items())
    named = '\n'.join(f'[N{i}] {x}' for i, x in enumerate(ev['named'], 1)) or '(none)'
    threads = '\n'.join(f'[T{i}] {x}' for i, x in enumerate(ev['threads'], 1)) or '(none)'
    return (f"NOT CONNECTED (type: name (kind of system)):\n{cards}\n\nNAMED IN THE OWNER'S OWN SETUP:\n{named}\n\n"
            f"THREADS (sender's domain | subject; '-' is the owner's own company):\n{threads}")


def _cited(vals, tag: str, n: int) -> list:
    """The numbers the model cited that exist - T3, "3" and 3 alike; anything else is not a citation."""
    out = set()
    for v in vals if isinstance(vals, list) else []:
        m = re.fullmatch(rf'{tag}?(\d+)', str(v).strip(), re.I)
        if m and 1 <= int(m.group(1)) <= n: out.add(int(m.group(1)))
    return sorted(out)


def connect_line(store, ev: dict, s: dict, key: str, why: str) -> dict | None:
    """The model's connect:<type> line, validated: the type is one of the cards it was offered (never one connected or
    raised - read again, another run may have raised it meanwhile), the threads it cited exist, and they clear the
    floor - or the owner's own setup (a routing fact, a report, SOUL.md) names it. The count said is the threads it
    cited, never a word count."""
    t = key[len('connect:'):].strip()
    card = ((ev or {}).get('offer') or {}).get(t)
    if not card or any(i['Key'] == key for i in store.list_ideas()): return None
    cited = _cited(s.get('threads'), 'T', len(ev['threads']))
    said = s.get('named_in') if isinstance(s.get('named_in'), list) else []
    named = [ev['named'][i - 1] for i in _cited(said, 'N', len(ev['named']))]
    if ev['soul'] and any(str(v).strip().upper() in ('SOUL', 'SOUL.MD') for v in said): named.append('SOUL.md')
    n, title = len(cited), card['title']
    if n < ev['floor'] and not named:
        logger.info(f"assistant: dropped {key} - it cited {n} thread(s), under the floor of {ev['floor']}, and nothing of yours names it")
        return None
    subjects = '; '.join(f'"{_short(ev["threads"][i - 1].split(" | ", 1)[-1], 90)}"' for i in cited[:6])
    lead = f"{plural(n, 'thread')} this month {'were' if n != 1 else 'was'} about {title}" if n else f"Your own setup names {title}"
    return {'key': key, 'kind': 'connect', 'sig': t,
            'facts': f"{title} is not connected; the threads about it: {subjects or '(none)'}" + (f"; named in {', '.join(named)}" if named else '') + '.',
            'text': f"{lead} and nothing here reads it. " + ('It is on the roadmap - say so and it moves up.' if card.get('planned') else f"Connect {title}?"),
            'action': {'type': 'connect', 'connector_type': t, 'title': title, 'planned': bool(card.get('planned')), 'count': n,
                       'why': 'the systems your own mail and tasks name are the ones worth reading'},
            'why': why or f'{n} thread(s) about it' + (f", named in {', '.join(named)}" if named else '')}


def fresh(state: dict, cand: dict, now: datetime) -> bool:
    """Worth saying now? Never said: yes. Snoozed: when it wakes. The model's OWN idea (idea:<slug>), said once:
    never again - the Advisor raises new ideas, it never edits one (the owner, 2026-09-25). Its Sig is the start of
    its wording, so "the facts changed" was a rewording, and a read idea came back rewritten every run. A candidate
    the hub found (a follow-up, a quiet thread) has a real Sig - its last word - and comes back when that moves."""
    i = state.get(cand['key'])
    if not i: return True
    if i.get('Status') == 'snoozed': return bool(i.get('SnoozeUntil')) and _ts(i['SnoozeUntil']) <= now.strftime('%Y-%m-%d %H:%M:%S')
    # a chase's Sig is its last word and how long the silence has run ("|n", followups): the silence growing brings an OPEN
    # one back, never one the owner dismissed or did - that waits for the thread itself to move
    was, now_sig = str(i.get('Sig') or ''), str(cand.get('sig') or '')
    if i.get('Status') in ('dismissed', 'done') and was.split('|')[0] == now_sig.split('|')[0]: return False
    return not is_model_idea(cand['key']) and was != now_sig


def again(state: dict, cand: dict) -> dict:
    """A chase said before and back because the silence grew says so in its facts. The prompt's "never repeat anything
    under ALREADY SAID" let the model drop it as a repeat: the vendor follow-up came back at twelve days and was skipped,
    the 9/25 line about it still listed as said (2026-10-06). The longer silence IS the new fact."""
    i = state.get(cand.get('key'))
    if not (i and cand.get('kind') in ('followup', 'promise') and i.get('LastSaid')): return cand
    was = str(i.get('Sig') or '').split('|')[1:] or ['0']
    return {**cand, 'again': True, 'plain': cand['facts'], 'facts': cand['facts'] + (f" RAISED BEFORE on {_ts(i['LastSaid'])[:10]} and STILL unanswered - the silence has grown "
                                             f"since (step {was[0]} then): that is new, say it again, plainly, with how long it has been.")}


def source_of(line: dict, mids: dict, chosen: dict) -> dict | None:
    """Which block put this line in front of the model. LOOKED UP, never asked for: a candidate a
    producer raised carries its own block id, and for the model's own lines the block is read off
    the message id it returned. No mid, or a mid no block contributed, means NO source line - a
    wrong provenance is worse than none, and this is the one thing on the post whose whole value is
    that the owner can trust it."""
    from . import assistantblocks as blk
    bid = line.get('block') or blk.BLOCK_OF_KIND.get(line.get('kind'))
    if not bid:
        mid = line.get('mid') or (line.get('action') or {}).get('mid')
        try: bid = mids.get(int(mid)) if mid else None
        except (TypeError, ValueError): bid = None
    if not bid: return None
    o = (chosen or {}).get(bid) or {}
    win = f"{o['days']}d" if o.get('days') else f"{o['hours']}h" if o.get('hours') else ''
    rows = [int(line['mid'])] if line.get('mid') else []
    return {'block': bid, 'label': (blk_label(bid) or bid), 'window': win, 'rows': rows}


def blk_label(bid: str) -> str:
    from . import assistantblocks as blk
    b = blk.by_id(bid)
    return b.label if b else ''


# ── the model's pass: its own read, given what it already said ───────────────────────────────
CONTRACT = ('\n\nYou are writing your POST on the owner\'s Timeline - the short list of things worth saying right now. You get '
            'CANDIDATES the hub found itself (each with a key), WHAT PEOPLE SAID (the words, by thread), who is OUT OF OFFICE, the '
            'CALENDAR, what arrived (with each report\'s schedule, when it last ran and what that run did, and each failure\'s cause), what got done, what is open, and WHAT '
            'YOU ALREADY SAID. Answer JSON only: {"say": [{"key": "<a candidate key, or idea:<short-slug> for a thought of your own>", '
            # THE FINDING, THEN WHOSE MOVE, THEN ANY SUGGESTION - apart (the owner, 2026-10-09). "The fact and what I would do"
            # in one first-person line made every idea read as an order: triage took "I'd read it through" as work for the owner
            # on a mail sent to another team (TQ-1028), and the card could not show what was true apart from what was advised.
            '"text": "<one line, under 30 words: the finding - what is true, quoting the phrase or naming the cause when there is one; '
            'not what to do about it>", '
            '"whose": "<whose move it is: the owner, someone else by name (\'the Ops Team\', \'Erin\'), or nobody yet>", '
            '"suggest": "<what I would do about it, one short line - or null when the finding says enough>", '
            '"section": "<people|loose|ideas|systems - which part of the post this belongs under: people = what somebody said '
            'or asked, loose = something waiting on somebody (a chase, a promise, work gone quiet), systems = a threshold, a '
            'failure or a number out of a connected system, ideas = your own thought. A candidate the hub found has a section '
            'already and yours is ignored for those; this is for idea:* lines>", '
            '"why": "<one line: what this rests on - the mail, the date, the silence, the pattern - named as it appears in what you '
            'were given (sender, subject, mid, TQ-ref), so the owner can check it>", "mid": <the message id it is '
            'about, or null>, "about": "<the TQ-ref of the task this line is about - open OR closed - or null; '
            'this field is the ONLY thing that ties the line to a task, so a line about a task always names it here>", '
            '"task": "<idea:* only - a task title the owner could accept as-is, or null>", '
            '"kind": "<when task is not null: coding if it needs a repository/system changed, otherwise general>", '
            '"premise_unanswered": <true when the line rests on nobody having replied or told them (no answer yet, nobody told X), else false>, '
            '"threads": [<connect:* only - the T numbers of every thread under SYSTEMS NOTHING HERE READS really about that system>], '
            '"named_in": [<connect:* only - the N numbers there that name it, and "SOUL" when the owner\'s own document does>]}], '
            '"notes": "<your note to the next check, under 120 words: FACTS AND TIMINGS ONLY - what you looked at and found nothing in, '
            'the date or silence length at which something becomes worth raising, a fact you settled so it need not be worked out again. '
            'Never a standing rule about what to ignore or what is noise: the instruction decides that, and a note that says '
            '\'ignore X\' would silence you for good. Rewrite it whole each time; empty if nothing>"}.\n'
            'At most {max_lines} entries. A line about ONE message must tell the owner something the message does not: the mail '
            'is already on their Timeline with triage\'s own verdict on it, so "X forwarded this with no message, I would ask '
            'what they want" is a second copy of the mail and not a line. Say the thing they could not see - who else is in it, '
            'what it answers, what it costs them on Monday - or say nothing (the owner, 2026-09-07: "Why did assistant triagger '
            'on bare email meaning saying the same thing?"). This rule is the contract\'s, not the instruction\'s, so it holds '
            'whatever prompt the owner writes.\n'
            'Skip a candidate that is not worth the owner\'s eye (a standing standup needs no prep; a '
            'one-day silence from someone who always takes a week is not news) - skipping is free, repeating is not: never say '
            'again, reworded or not, anything under ALREADY SAID - and if a line of yours IS about the same subject as one there, give it '
            'THAT line\'s key, never a new slug for it. A task under DONE was just HANDLED: for a week after it closed, '
            'never raise its subject again - not that it happened again, not that the fix did not hold, not a new angle on it. '
            'A recurrence reaches the owner as its own mail, and triage puts it back on that task; a line from you is a second '
            'copy of work they just finished (the owner, 2026-09-25: "it should not make another advice if we just did it"). '
            'Your own ideas are the point: a thread going in circles, a '
            'promise buried in a mail, two people asking the same thing, the thing to do now so the next ask never comes. '
            # the system worth connecting is the model's call (the owner, 2026-10-11): a word match chose it before
            'At most ONE line may suggest a system to connect, keyed connect:<type> with a type listed under SYSTEMS NOTHING HERE '
            'READS - only when the owner\'s work clearly involves it, citing the threads really about it; a thread that only '
            'shares a word with its name is not about it. None clearly is -> no connect line. '
            'Facts only from what you are given; never invent a name, a date or a number. Nothing new to say -> {"say": []}.')


def _schedules(store) -> dict:
    """{report title: 'daily at 08:00 + on app start (at most once a day)'} - a report's arrivals mean
    nothing without its clock: 25 digests in two days on an on_startup report is 25 launches, not a
    scheduler bug, and two seeded reports at one timestamp is one launch, not a restart to explain."""
    from . import reports
    out, st = {}, store.get_settings()
    for src in store.list_sources(active_only=False):
        if src.get('Channel') != 'report': continue
        try: c = json.loads(src.get('ConfigJson') or '{}')
        except ValueError: continue
        out[c.get('title') or src.get('Address')] = reports.schedule_words(c) + _last_run(st, src)
    return out

def _last_run(settings: dict, src: dict) -> str:
    """'; last ran Tue 22 Sep 20:37, nothing to report so nothing was filed' - or ''. The clock alone
    misled: a routed report whose judge holds a run back files NO message, so the newest mid read as
    the last firing and a 140-minute timer looked stalled two runs after it fired on time (TQ-0685).
    The run record on the source (reports.LAST_RUN) is the receipt the arrivals cannot carry."""
    from .reports import LAST_RUN
    try: rec = json.loads(settings.get(f"{LAST_RUN}{src['SourceId']}") or '{}')
    except (ValueError, TypeError): rec = {}
    if not rec.get('at'): return ''
    what = 'failed' if rec.get('failed') else f"posted mid {rec['message_id']}" if rec.get('message_id') else 'nothing to report so nothing was filed'
    return f"; last ran {_when(rec['at'])}, {what}"

_GH_FAILED = re.compile(r'^(.+?) Failed in ', re.M)          # the job lines of GitHub's "Run failed" mail
def _cause(r: dict) -> str:
    """The failed jobs GitHub's run mail lists, parsed out of its body - '' when it lists none. Whether a mail says
    something broke is the model's to read from the words beside it: a subject word list (fail|error|...) decided it
    here, and a mail that broke without saying "fail" lost its cause (the owner, 2026-10-11: everything should be ai)."""
    jobs = _GH_FAILED.findall(str(r.get('Preview') or r.get('BodyText') or ''))
    return ' -> failed: ' + ', '.join(_short(j.split('/', 1)[-1], 40) for j in jobs[:4]) if jobs else ''

def _recent(store, days: int = 2) -> str:
    """The last two days' arrivals, ROLLED UP: one line per sender+subject with a count, newest
    first. A pattern (87 alerts from one system, the same ask twice) is a number the model can see
    instead of a list it has to count - and calendar-today at 00:49 was a 49-minute window. Every
    line carries the latest message's actual words too: WHAT PEOPLE SAID has fuller human threads,
    but invitations and other machine mail must not collapse to a subject line. A report carries
    its schedule, and a failure its cause (the machines are to be read, not counted)."""
    from . import funnel
    by, sched, since, mutes = {}, _schedules(store), _since(days), funnel.mutes(store)
    for r in store.feed(limit=400, days=math.ceil(days)):
        if r.get('Channel') == CHANNEL or _ts(r.get('SentAt')) < since: continue
        # a muted report is out of the brief too: a mute is "never show me these again" (G1, 2026-09-28)
        if r.get('Channel') == 'report' and any(funnel.muted(m, {'who': r.get('SourceName'), 'title': r.get('Subject'), 'lane': 'report'}) for m in mutes): continue
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
    return '\n'.join(lines) or f'(nothing arrived in the last {said_number(days)} days)'


def _people_context(store, days: int = 2) -> tuple[str, list[int]]:
    """WHAT PEOPLE SAID: the human threads of the last two days with the words in them - newest
    first, the last few lines of each, the owner's own lines marked. The subject line said
    "Teams chat with Marcus"; the words said "can you fill out the performance review?" - the
    ask, the pattern and the promise all live here, and a model handed only subjects wrote
    'no content given' in its notes."""
    from .categories import sender_class, team_domains_of
    team = team_domains_of(store.get_settings())
    rows = [r for r in store.recent_messages(_since(days), limit=500)
            if r.get('Channel') not in ('report', CHANNEL) and not _ooo_row(r)]
    # the owner's own lines are 'context' rows - recent_messages leaves them out, so fetch the threads' chains
    by = {}
    for r in rows:
        if sender_class(r, team) != 'person': continue
        k = r.get('ConversationId') or re.sub(r'^((re|fw|fwd|aw)\s*:\s*)+', '', _short(r.get('Subject'), 60), flags=re.I).lower()
        by.setdefault(k, []).append(r)
    me = (store.get_setting('owner_email') or '').lower()
    mine = lambda c: c.get('Status') == 'context' or c.get('Direction') == 'out' or (c.get('FromEmail') or '').lower() == me
    def chain_of(rs):
        chain = store.thread_messages(conversation_id=rs[0].get('ConversationId'), subject=rs[0].get('Subject'), limit=12) if rs[0].get('ConversationId') else rs
        return sorted((c for c in chain if c.get('Status') != 'skipped'), key=lambda c: _ts(c.get('SentAt')))[-8:] or rs
    # A CONVERSATION BEFORE A FORWARD (the owner, 2026-09-25): seven refund forwards from one sender filled the block,
    # and the chat where the owner and a colleague restarted a frozen system - "try now", "that worked" - was cut, so
    # the Advisor read "try now" as one rolled-up line beside unrelated mail from the same app and joined them. A
    # thread the owner wrote in goes first; after a sender's first one-way thread the rest fold to one line.
    threads = [(rs, chain_of(rs)) for rs in by.values()]
    threads.sort(key=lambda x: not any(mine(c) for c in x[1]))              # stable: newest first within each
    out, used, mids, shown, folded = [], 0, [], set(), {}
    for rs, chain in threads:
        if len(out) >= PEOPLE_THREADS: break
        last = chain[-1]
        who = next((c.get('FromName') or c.get('FromEmail') for c in reversed(chain) if not mine(c)), rs[0].get('FromName') or '?')
        if who in shown and not any(mine(c) for c in chain):
            folded.setdefault(who, []).append(rs[0]); continue
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
        if used + len(block) > PEOPLE_CHARS: continue          # a long one is skipped, not the end of the list
        out.append(block); used += len(block); mids += [c['MessageId'] for c in chain]; shown.add(who)
    for who, rs in folded.items():
        subj = '; '.join(dict.fromkeys(_short(r.get('Subject'), 50) for r in rs[:4]))
        out.append(f"- {who}: {len(rs)} more one-way thread(s) like the one above - re \"{subj}\""
                   f" (latest mids {', '.join(str(r['MessageId']) for r in rs[:4])})")
    return '\n'.join(out) or f'(no person wrote in the last {said_number(days)} days)', mids


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


def _calendar(store, days: int = 2) -> str:
    from . import calendar as cal
    ev = _agenda(store, days=days)
    return '\n'.join(f"- {_when(e['start'])} {cal.span(e['start'], e.get('end') or '')} \"{e.get('subject')}\"" + (f" with {', '.join(list(e.get('who') or [])[:6])}" if e.get('who') else '')
                     for e in ev[:8]) or f'(nothing on the calendar for {said_number(days)} days' + (')' if store.get_setting('calendar_enabled', '1') == '1' else ' - calendar off)')


def _done(store, days: float = 7) -> str:
    """What got DONE in the window - closed tasks, each with the agent's own summary line where there
    is one. The ideas worth having about the owner's work (the fix that keeps recurring, the report
    nobody reads, the automation) live here, not in today's mail."""
    cut = _since(days)
    closed = lambda t: _ts(t.get('ClosedAt') or t.get('UpdatedAt'))
    # newest first, WHEN it closed and what its agent concluded: the self-close note ("The agent closed this itself:")
    # never reached this list, so a vendor loop fixed yesterday read as an open question and was raised again (2026-09-25)
    ts = sorted((t for t in store.list_tasks() if t.get('Status') == 'done' and closed(t) >= cut), key=closed, reverse=True)[:25]
    out = []
    for t in ts:
        notes = [str(c.get('Body') or '') for c in reversed(store.list_comments(t['TaskId']))]
        said = next((b.split(':', 1)[1] for b in notes if b.startswith('The agent closed this itself:')), None)
        rep = next((b for b in notes if b.startswith(('AGENT REPORT', 'CODER REPORT'))), None) if said is None else None
        if rep:
            m = re.search(r'(?im)^summary:\s*(.+)$', rep)
            said = m.group(1) if m else rep.split('\n', 1)[-1]
        repo = (re.search(r'repo:([^\s,]+)', str(t.get('Tags') or '')) or [None, None])[1]
        out.append(f"- {task_ref(t['TaskId'])} [{t.get('Kind')}{', ' + repo if repo else ''}] {_short(t.get('Title'), 70)}"
                   f" - closed {_when(closed(t))}" + (f": {_short(said, 160)}" if said else ''))
    return '\n'.join(out) or '(nothing closed in this window)'


def _week(store) -> str: return _done(store, 7)


JUST_HANDLED_DAYS = 7


def just_handled(store, act: dict):
    """The task an idea's action points at - by its tid, or the task its message went to - when that task was
    closed within JUST_HANDLED_DAYS; else None."""
    tid = act.get('tid') or ((store.get_message(act['mid']) or {}).get('TaskId') if act.get('mid') else None)
    t = store.get_task(tid) if tid else None
    if not t or t.get('Status') not in ('done', 'dropped'): return None
    return tid if _ts(t.get('ClosedAt') or t.get('UpdatedAt')) >= _since(JUST_HANDLED_DAYS) else None


def _open(store, cap: int = 20) -> str:
    ts = [t for t in store.list_tasks(active_only=True) if t.get('Status') in ('open', 'in_progress', 'waiting')]
    def line(t):
        last = _dt(store.task_last_activity(t['TaskId']) or t.get('UpdatedAt') or t.get('CreatedAt'))
        age = f"{int((datetime.now() - last).total_seconds() // 3600)}h since anything happened" if last else ''
        state = f"{t.get('RunAgent') or 'an agent'} is working it" if t.get('RunStatus') == 'running' else 'a draft waits for you on the task' if t.get('ReviewStatus') == 'pending' else age
        return f"- {task_ref(t['TaskId'])} [{t['Status']}, {t.get('Kind')}] {_short(t.get('Title'), 80)}" + (f" - {state}" if state else '')
    return '\n'.join(line(t) for t in ts[:cap]) or '(nothing open)'


def owns(store, report_id):
    """Which idea keys are this report's (I8, 2026-09-27): its own namespace, or - for the Advisor - every key outside
    one. What was already said, the same-subject key and the retry all read across every report, so one report's
    open idea could silence another's line."""
    pre = f'report:{report_id}:' if own_identity(store, report_id) else None
    return (lambda k: str(k).startswith(pre)) if pre else (lambda k: not str(k).startswith('report:'))


def _said(store, cap: int = 40, done_days: float = 7, report_id=None) -> str:
    """Every line the owner has from me, WITH ITS KEY (the owner, 2026-09-25: "advisor should know what it sent in the
    past and not recreate them"). Without the key the model saw a line it half-recognised, minted a new slug for the
    same subject, and the code took it as news - the same budget question four posts running. Seeing the key, it
    reuses it, and fresh() refuses a known key. What was acted on this week is here too, or it comes straight back."""
    cut, mine = _since(done_days), owns(store, report_id)
    rows = [i for i in store.list_ideas() if mine(i['Key']) and i.get('Status') in ('open', 'dismissed', 'snoozed')
            or (i.get('Status') == 'done' and _ts(i.get('DecidedAt') or i.get('LastSaid') or '') >= cut)][:cap]
    out = []
    for i in rows:
        n = int(i.get('SaidCount') or 1)
        out.append(f"- ({i['Status']}) {i['Text']}  [key {i['Key']} · said {_when(i.get('LastSaid') or i.get('FirstSeen'))}"
                   f"{f', {n} times' if n > 1 else ''}]")
        try: chat = json.loads(i.get('ActionJson') or '{}').get('chat') or []
        except ValueError: chat = []
        for turn in chat[-4:]:
            out.append(f"    {turn.get('role')}: {_short(turn.get('text'), 300)}")
    said = '\n'.join(out) or '(nothing yet)'
    v = verdicts_block(store, report_id)
    return f'{said}\n\n{v}' if v else said


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


def parse(store, text: str, cands: list, max_lines: int = MAX_LINES, report_id=None, connect: dict = None) -> list:
    """The model's list, kept honest: a key it invents must be idea:*, a candidate key keeps its
    kind and its buttons, and the text is the model's when it gave one. Every line keeps its WHY -
    the hub's facts for a candidate (plus the model's read on them), the model's own for an idea -
    so the owner can see what it rests on (the owner, 2026-08-30: "why it brings up something,
    what is driving it")."""
    try: j = json.loads(re.sub(r'^```(json)?|```$', '', (text or '').strip(), flags=re.M))
    except ValueError: return []
    by = {c['key']: c for c in cands}
    # an idea already about this message or task keeps its key: the model invents a slug per run, and one
    # situation came back as idea:gail-sample-file, idea:gail-sample-file-compass, idea:gail-in-... A DISMISSED or
    # snoozed one too - read only among open ideas, a thought put down came straight back under a new slug (I2,
    # 2026-09-27). Only the model's own keys, and only this report's: a model line that took a follow-up's key
    # rewrote it every run, and the follow-up re-raised itself on the next (I3, I8)
    aimed, mine = {}, owns(store, report_id)
    for i in store.list_ideas():
        if i.get('Status') not in ('open', 'dismissed', 'snoozed') or not is_model_idea(i['Key']) or not mine(i['Key']): continue
        try: a = json.loads(i.get('ActionJson') or '{}')
        except (ValueError, TypeError): a = {}
        for f in ('tid', 'mid'):
            if a.get(f): aimed.setdefault((f, a[f]), i['Key'])
    out, seen = [], set()
    for s in (j.get('say') or []) if isinstance(j, dict) else []:
        if not isinstance(s, dict): continue
        key, txt, why = str(s.get('key') or '').strip(), _short(s.get('text'), 240), _short(s.get('why'), 400)
        if not key or key in seen or not txt: continue
        # whose move it is and what the Advisor would do, kept apart from the finding (CONTRACT)
        said = {k: v for k, v in (('whose', _short(s.get('whose'), 80)), ('suggest', _short(s.get('suggest'), 200)))
                if v and str(v).strip().lower() not in ('null', 'none')}
        # the model says when its line rests on "nobody replied"; contradicts_sent_reply holds that against the send receipt
        if s.get('premise_unanswered') is True: said['unanswered'] = True
        if key in by:
            # ...and the task it is ABOUT, for every line, not only an idea's: a meeting-prep line about a question already on an open
            # task ("TQ-0702 already has a draft waiting") reached triage tied to nothing, and became a second task for the same ask -
            # answered on the first, still open on the second (the owner, 2026-10-14). The ref is the model's `about`, never guessed.
            about = re.search(r'\bTQ-?0*(\d+)\b', str(s.get('about') or ''), re.I)
            pick = store.get_task(int(about.group(1))) if about else None
            if pick and pick.get('Status') not in ('done', 'dropped') and not (by[key].get('action') or {}).get('tid'): said['tid'] = pick['TaskId']
            # the first line of the facts: prep's line carries a 1200-char dossier under it that belongs in 'skipped', not under a button
            out.append({**by[key], 'text': txt, 'action': (by[key].get('action') or {}) | said,
                        'why': (by[key].get('plain') or by[key]['facts']).split('\n', 1)[0] + (f"\nThe model's read: {why}" if why else '')})
        elif key.startswith('connect:'):
            # one per run, and only what connect_line validates against the evidence the model was shown
            if any(o.get('kind') == 'connect' for o in out) or not (line := connect_line(store, connect, s, key, why)): continue
            out.append(line | {'action': line['action'] | said})
        elif key.startswith('idea:') and len(key) > 5:
            mid = s.get('mid') if isinstance(s.get('mid'), int) else None
            title = _short(s.get('task'), 120) or None
            act = {'type': 'task', 'mid': mid, 'title': title} if title and mid else {'type': 'message', 'mid': mid} if mid else {'type': 'note'}
            if act['type'] == 'task' and str(s.get('kind') or '').lower() in task_kinds.AGENT:
                act['kind'] = str(s['kind']).lower()
            # a line that NAMES a task belongs to it, whatever else it carries: without the tid the
            # pipe could not tell that an agent had the work, so "TQ-0329 July financials hasn't moved"
            # sat in 'slipped' while the task said in_progress (the owner, 2026-09-03)
            # WHICH task is the model's `about` (CONTRACT), and only that: a fallback scanned the line's words for TQ refs and
            # guessed - "TQ-0734 granted it, but TQ-0736 says the tab is still missing" needed a rule about open ones to land
            # on 0736 at all (the owner, 2026-10-11: everything should be ai). The ref is parsed out of `about`, never chosen.
            about = re.search(r'\bTQ-?0*(\d+)\b', str(s.get('about') or ''), re.I)
            pick = store.get_task(int(about.group(1))) if about else None
            # JUST HANDLED IS NOT NEWS (the owner, 2026-09-25): an idea about a task closed this week is a second copy
            # of finished work - the vendor loop fixed yesterday came back as a fresh idea and a fresh task. A
            # recurrence reaches the owner as its own mail; triage puts that back on the task.
            if (gone := just_handled(store, {'tid': pick['TaskId']} if pick else act)):
                logger.info(f"assistant: dropped {key} - it is about {task_ref(gone)}, handled this week")
                continue
            # ...and one about work closed LONGER ago stands alone: tied to that task, the rail filed it under a closed
            # row and nobody saw it (I6, 2026-09-27)
            if pick and not act.get('tid') and pick.get('Status') not in ('done', 'dropped'): act['tid'] = pick['TaskId']
            # where in the post it goes. Only an idea gets to choose: a candidate the hub found is
            # placed by the producer that found it, and no model answer overrides that.
            act['section'] = section_of({'section': s.get('section'), 'kind': 'idea'})
            act |= said
            key = aimed.get(('tid', act.get('tid'))) or aimed.get(('mid', act.get('mid'))) or key
            if key in seen: continue
            for f in ('tid', 'mid'):
                if act.get(f): aimed.setdefault((f, act[f]), key)      # two lines in one answer about one thing: one idea
            out.append({'key': key[:120], 'kind': 'idea', 'sig': txt[:60], 'text': txt, 'action': act,
                        'why': why or 'the model gave no reason - treat it as a hunch' + (f' (about mid {mid})' if mid else '')})
        else: continue
        seen.add(key)
        if len(out) >= max_lines: break
    return out


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
    review table records the exact response and the successful decision. Whether the line RESTS on "nobody replied" is
    the model's own answer (premise_unanswered in CONTRACT, kept on the action) - a phrase list read the line's words
    here and let "still waiting on you" through (the owner, 2026-10-11: everything should be ai).
    """
    if not (line.get('action') or {}).get('unanswered'): return False
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
    # a Taskuary card sits in the same list (2026-09-20) but is a block choice, not a system to pull
    return [dict(x) for x in raw if isinstance(x, dict) and x.get('type') and x.get('type') not in ('assistant', 'taskuary')][:20]


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
    # Supplying both arguments means a particular report is being run. Do not even consult the
    # first Assistant row in the database: there can be several, and that was how a SQL monitor
    # wound up reading another Assistant's configuration.
    saved, own = _watch(store) if source_ids is None or inline is None else ([], [])
    ids = saved if source_ids is None else _ids(source_ids)
    subs = own if inline is None else _inline(inline)
    if not ids and not subs:
        return '(none selected - add a data source, or choose saved data views, on Reports -> Advisor)'
    from . import reports
    found = {s['SourceId']: s for s in store.list_sources(active_only=False) if s.get('Channel') == 'report'}
    jobs = []                                     # (title, cfg to render, or a note to print instead)
    for sid in ids:
        src = found.get(sid)
        if not src: jobs.append((f'missing report source {sid}', None, 'This saved data view no longer exists.')); continue
        try: cfg_ = json.loads(src.get('ConfigJson') or '{}')
        except ValueError: cfg_ = {}
        title = str(cfg_.get('title') or src.get('Address') or f'report {sid}')
        if cfg_.get('type') == 'assistant': jobs.append((title, None, 'Skipped: an Advisor cannot watch itself.'))
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


def _uptime_block(store) -> str:
    """An EMPTY labelled section is worse than none: it reads as "nothing was running"."""
    from . import reports as _r
    up = _r.uptime_words(store)
    # ...and a start is the owner opening it. An Advisor read a restart as an incident and raised "investigate the
    # unexpected restart" - a task an agent then started on (the owner, 2026-09-28: "doing stupid stuff like checking
    # why it restarted"). This block is context for judging reports, never a finding of its own.
    return (f"WHEN TASKUARY WAS RUNNING (it is a window on this machine: while it is shut nothing polls, no report "
            f"fires and no mail arrives - so a gap here is not a fault. A start or restart is the owner opening or "
            f"reopening the app, or an update: never a problem, never worth an idea, never something to investigate. "
            f"Use this only to judge whether a report could have run):\n{up}\n") if up else ''


def build_inputs(store, cands: list, head: str = 'CANDIDATES', watch_source_ids=None, watch_sources=None, blocks=None, report_id=None) -> tuple:
    """(the text the model sees, {message id: the block that supplied it}). The same text is the
    Reports tab's Preview (facts) and the run record (reports.run_report_source), so what it was
    given is never a guess; the index is how a line is attributed without asking the model.
    `blocks` is the report's resolved choice; None means the declared defaults, which is what this
    function read when the list was hardcoded (assistantblocks.CATALOGUE is that list).

    Returns the index rather than stashing it on the function: this install runs two Assistant
    reports, and a module-level `last_mids` would have the second one reading the first's sources."""
    lead, parts, mids = build_sections(store, cands, head, watch_source_ids, watch_sources, blocks, report_id)
    return lead + ''.join(t for _, t in parts), mids


def build_sections(store, cands: list, head: str = 'CANDIDATES', watch_source_ids=None, watch_sources=None, blocks=None, report_id=None, connect=None) -> tuple:
    """(the lead - the clock and the candidates, [(block id, its section)], {message id: block}).
    The payload in parts, so a prompt that names a card (`[taskuary.messages]`) can be handed that
    card's sections where it asks for them and the rest underneath (think). Joined, the parts are
    build_inputs' text byte for byte; the verdicts cross-check is a part of its own."""
    from . import assistantblocks as blk
    now, mids, said = datetime.now(), {}, {}
    chosen = blocks if blocks is not None else {b.id: blk.defaults(store, b) for b in blk.CATALOGUE}
    lead = (f"NOW: {now.strftime('%A %d %B %Y %H:%M')}\n{_uptime_block(store)}"
            f"\n{head}:\n" + ('\n'.join(f"[{c['key']}] {c['facts']}" for c in cands) or '(none)'))
    parts = []
    verdicts_before = 'notes'          # the cross-check sits after ALREADY SAID and before the notes, where it has always sat
    for b in blk.CATALOGUE:
        o = chosen.get(b.id)
        # a PRODUCER (no heading) is already in `cands`: the caller ran candidates() and paid for it once
        if not o or not o.get('on') or not b.heading: continue
        # the run-time opts, stamped in ONE place the card prices through too (assistantblocks.stamp)
        o = blk.stamp(b, o, facts=' '.join(str(c.get('facts') or '') for c in cands)[:4000],
                      report_id=report_id, source_ids=watch_source_ids, inline=watch_sources)
        # the connect evidence the run validates against is the evidence the model reads - built once, by think
        if b.id == 'connectors' and connect is not None: o = o | {'evidence': connect}
        out, got = blk.render(store, b, o)
        said[b.id] = out
        for m in got: mids[int(m)] = b.id
        if b.id == verdicts_before: parts.append(('_verdicts', _verdicts(store, cands, said))); verdicts_before = None
        if not str(out).strip(): continue                 # nothing to say prints no head: an empty labelled section reads as an answer
        parts.append((b.id, out if b.whole else '\n\n' + blk.headline(b, o) + ':\n' + out))
    if verdicts_before: parts.append(('_verdicts', _verdicts(store, cands, said)))
    return lead, parts, mids


# What the system prompt says in the instruction's place once the instruction has moved into the
# message with its data, and how that message opens - the one text the model reads, the run record
# keeps and the Preview shows.
PLACED_SAYS = 'It is at the top of the message, with the cards it names placed where it names them.'
PLACED_HEAD = "YOUR INSTRUCTION (the owner's, from the Reports tab), with the cards it names placed in it:"


def placed_message(shaped: str, rest: str) -> str: return f'{PLACED_HEAD}\n{shaped}\n\n{rest}'


def placed(instruction: str, lead: str, parts: list, chosen: dict = None) -> tuple:
    """(the instruction with every card it names in its place, the payload without those cards).
    A prompt naming no card leaves both exactly as they were - the substitution costs nothing
    when nobody asked for it."""
    from . import assistantblocks as blk
    from .reports import names_sources, substitute
    if not names_sources(instruction): return instruction, lead + ''.join(t for _, t in parts)
    text, used, missing = substitute(instruction, blk.sections_by_card(parts, chosen))
    if missing: logger.warning(f'assistant prompt names sources this report does not have: {", ".join(missing)}')
    return text, lead + ''.join(t for bid, t in parts if f'{blk.TOKEN_TYPE}.{blk.CARD_OF.get(bid)}' not in used)


def _verdicts(store, cands: list, said: dict) -> str:
    """The standing verdicts are matched against the THREADS and the ARRIVALS the model was handed -
    the real subjects, not the model's words about them (see _verdicts_block)."""
    return _verdicts_block(store, cands, f"{said.get('threads', '')}\n{said.get('arrivals', '')}")


def inputs(store, cands: list, head: str = 'CANDIDATES', watch_source_ids=None, watch_sources=None, blocks=None, report_id=None) -> str:
    """The text alone, for every caller that does not need to know which block said what."""
    return build_inputs(store, cands, head, watch_source_ids, watch_sources, blocks, report_id)[0]


def systems_inputs(store, watch_source_ids=None, watch_sources=None) -> str:
    """The complete model input for a source-backed Assistant report."""
    now = datetime.now()
    return (f"NOW: {now.strftime('%A %d %B %Y %H:%M')}\n\n"
            "CONFIGURED DATA SOURCES (the only facts available to this report):\n"
            f"{system_checks(store, watch_source_ids or [], watch_sources or [])}")


def think(store, cands: list, llm, instruction: str = None, max_lines: int = MAX_LINES,
          watch_source_ids=None, watch_sources=None, systems_only: bool = False, blocks=None, report_id=None) -> list:
    """One call: the owner's instruction (the Reports tab), the candidates, the day, what was already said."""
    from .triage import job_doc
    soul, job = store.doc('soul') or '', job_doc(store, SOUL_CHARS)
    direction = ((SYSTEMS_PROMPT + (f"\n\nTHE OWNER'S RULE FOR THIS MONITOR:\n{instruction.strip()}" if instruction else ''))
                 if systems_only else (instruction or PROMPT).strip())
    contract = SYSTEMS_CONTRACT if systems_only else CONTRACT
    ev = None if systems_only else _connect_evidence_for(store, blocks)
    if systems_only: user, mids = systems_inputs(store, watch_source_ids, watch_sources), {}
    else:
        # a card the instruction names is placed in it, and the instruction then travels IN the
        # message with its data (one text: what the model reads, the run record, the Preview); the
        # rest of the payload follows it as it always did
        lead, parts, mids = build_sections(store, cands, watch_source_ids=watch_source_ids, watch_sources=watch_sources, blocks=blocks, report_id=report_id, connect=ev)
        shaped, rest = placed(direction, lead, parts, blocks)
        if shaped is direction: user = rest
        else: direction, user = PLACED_SAYS, placed_message(shaped, rest)
    # the report's prompt is the report's own: instruction, data scope, output contract, owner (PW-242).
    # COUNSEL is the chat's document; its walkthrough rules governed idea generation until 2026-09-06.
    system = (f"YOUR INSTRUCTION (the owner's, from the Reports tab):\n{direction}" + contract.replace('{max_lines}', str(max_lines))
              # WHOLE (the owner, 2026-09-25): cut at 1500 chars it stopped inside "Escalate", and the systems, people and
              # repository map - what the ledger repository is, who owns what - never reached the voice that reasons about them
              + (f"\n\nWho the owner is (their own document; its reply rules are for text sent to OTHERS):\n{soul[:SOUL_CHARS]}" if soul else '')
              # ...and what their JOB is - what they are accountable for, who they serve, the cadences. SOUL says how the
              # funnel behaves; this is what "matters" is measured against when the assistant says what comes first
              + (f"\n\nThe owner's job (their own document - weigh what matters by it):\n{job}" if job else ''))
    images = []
    if not systems_only:
        from .llm import readable_images
        images = readable_images(store, _people_context(store)[1])
    text = llm(system, user, max_tokens=POST_TOKENS, **({'images': images} if images else {}))
    return parse(store, text, cands, max_lines, report_id, connect=ev), _notes(text), user, mids


def _connect_evidence_for(store, blocks) -> dict | None:
    """The connect evidence when this report reads the `connectors` block, with the report's own window and floor."""
    from . import assistantblocks as blk
    b = blk.by_id('connectors')
    o = (blocks or {}).get('connectors') if blocks is not None else blk.defaults(store, b)
    if not (o and o.get('on')): return None
    try: return connect_evidence(store, o.get('days', 30), o.get('floor', 3))
    except Exception as e:
        logger.warning(f'assistant: the connect evidence was not read - {e}'); return None


def facts(store, watch_source_ids=None, watch_sources=None, systems_only: bool = False, blocks=None, report_id=None,
          instruction: str = None) -> str:
    """What a run would hand the model, as text - the Reports tab's Preview (reports.run_assistant).
    Preview and run share `blocks`, so the Preview is the payload rather than a picture of one. A
    prompt that names a card shows that card placed in it, above the rest - the run's own shape."""
    if systems_only:
        return systems_inputs(store, watch_source_ids, watch_sources)
    c = cfg(store); now = datetime.now()
    if blocks is not None:
        from . import assistantblocks as blk
        c = c | blk.producer_cfg(blocks, c)
    state = {i['Key']: i for i in store.list_ideas()}
    lead, parts, _ = build_sections(store, [x for x in candidates(store, c) if fresh(state, x, now)],
                                    'CANDIDATES (new since the last post)', watch_source_ids, watch_sources, blocks, report_id)
    from .reports import names_sources
    if not names_sources(instruction): return lead + ''.join(t for _, t in parts)
    return placed_message(*placed(instruction, lead, parts, blocks))


# ── the note to the next check ───────────────────────────────────────────────────────────────
def notes_key(store, report_id=None) -> str:
    """Which setting holds THIS check's note to itself. The note is one report's private memory of
    its own last run - a second Assistant report reading it is cross-talk, not context - so every
    report owning its identity gets its own key. The seeded Assistant keeps the bare name it has
    always had, so nothing on an existing install moves."""
    return f'assistant_notes:{report_id}' if own_identity(store, report_id) else 'assistant_notes'


def notes(store, report_id=None) -> tuple:
    """(text, when) of the note this check's last run left - '' if none yet."""
    s, k = store.get_settings(), notes_key(store, report_id)
    return (s.get(k) or '').strip(), s.get(f'{k}_at') or ''

# WORTH AUTOMATING (the owner, 2026-09-25): the weekly "Automation ideas" report folded into the Advisor. Its
# evidence - a month of traffic counted - is ~17k characters, so it rides in once a week, not every 30 minutes.
AUTOMATION_EVERY_DAYS, AUTOMATION_HEAD = 7, 'WORTH AUTOMATING'


def automation_key(store, report_id=None) -> str:
    return f'assistant_automation_read:{report_id}' if own_identity(store, report_id) else 'assistant_automation_read'


def automation_due(store, report_id=None) -> bool:
    """Whether this report's next check should read the month of counts: never read, or a week since."""
    at = store.get_setting(automation_key(store, report_id)) or ''
    return not at or _ts(at) <= _since(AUTOMATION_EVERY_DAYS)


def _notes_block(store, report_id=None) -> str:
    n, at = notes(store, report_id)
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


def section_of(line: dict) -> str:
    """Which section one line belongs in. The model's own choice wins for its ideas; a candidate the hub found (the model never
    places those) is placed by its kind, which is the thing that produced it - lanes.json `idea_kinds`."""
    from .lanes import idea_section
    s = str(line.get('section') or '').strip().lower()
    if s in SECTION_KEYS: return s
    return idea_section(line.get('kind'))


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


def _idea_message(store, i: dict, a: dict, report_title=None) -> tuple:
    """An idea as the message triage reads: its words, its why, and idea_context - the report it came
    from, the task it names (with status) and whether a worker has it. Returns (msg, linked task id, active)."""
    m0 = (store.get_message(a['mid']) or {}) if a.get('mid') else {}
    tid = a.get('tid') or m0.get('TaskId')
    task = store.get_task(tid) if tid else None
    active = bool(task and task.get('Status') in ('open', 'in_progress', 'waiting'))
    working = bool(active and any(r.get('Status') == 'running' for r in store.list_runs(tid)))
    stamp = i.get('LastSaid') or i.get('FirstSeen') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    who = report_title or 'Advisor'
    # one arrival per idea: the stamp in the id made every re-say a fresh message, and a fresh task once the first closed
    msg = {'external_id': f"idea:{i['IdeaId']}", 'channel': CHANNEL, 'from_name': who, 'source_name': who,
           'conversation_id': str(i.get('Key') or f"idea:{i['IdeaId']}"), 'subject': f"Advisor idea: {_cut(i.get('Text'), 100)}",
           'sent_at': stamp, 'body': str(i.get('Text') or '') + (f"\n\nwhose move: {a['whose']}" if a.get('whose') else '')
                                    + (f"\nthe Advisor's suggestion: {a['suggest']}" if a.get('suggest') else '')
                                    + (f"\n\nwhy: {a.get('why')}" if a.get('why') else ''),
           'idea_context': {'report': report_title, 'kind': i.get('Kind'),
                            'linked_task': f"{task_ref(tid)} [{task.get('Status')}] {_short(task.get('Title'), 80)}" if task else None,
                            'worker': 'an agent is working that task now' if working else ('nobody has that task' if task else None)}}
    return msg, (tid if task else None), active


def retry_stuck_ideas(store, report_id=None, report_title: str = None) -> int:
    """L3 (the owner, 2026-09-25): an open idea whose triage FAILED, or that waited for a brain, is judged again on
    the next run of the report that said it - under that report's name, not every report's as "Advisor" (I8)."""
    stuck, mine = [], owns(store, report_id)
    for i in store.list_ideas('open'):
        if not mine(i['Key']): continue
        try: t = (json.loads(i.get('ActionJson') or '{}') or {}).get('triage') or {}
        except ValueError: continue
        if t.get('error') or t.get('pending'): stuck.append(i)
    if not stuck: return 0
    try:
        from .llm import build_llm
        brain = build_llm(store)
    except Exception: brain = None
    if brain is None: return 0
    try: return len(triage_ideas(store, stuck, brain, report_title=report_title if own_identity(store, report_id) else None))
    except Exception as e:
        logger.warning(f'assistant: retrying stuck ideas failed - {e}'); return 0


def triage_ideas(store, rows: list, llm, report_title: str = None) -> list:
    """The shared verdict for every newly said idea (PW-199/PW-200). Judged once per set of facts (the
    idea's Sig); recorded on the idea as action.triage - intent, kind, why, the task it is linked to - or
    as error (retried on the next say) or pending (no brain). An actionable idea about NO task at all
    opens work through the shared intake with the verdict it already has, so kind defaults and startup
    rules apply and no second model call is made; one that names a task creates nothing. A generated
    claim never completes anything. Returns the ideas judged this pass.

    "No task at all" is the test, not "no OPEN task" (TQ-0487, 2026-09-10). The verdict used to turn on
    the linked task's status, and every re-say rewords the idea, so its Sig changes and it is judged
    again: close the work and the next say read 'linked task not active' as 'about nothing', opening a
    duplicate on the very mail just closed - with a coding agent on it. A follow-up noticed after the work
    closed is real, but it is the OWNER's click (act(verb='task'), which carries the evidence across and
    names the completed task), never something a check opens by itself."""
    from .ingest import judge, ingest_message, owner_addresses, own_addresses
    now, done = datetime.now().strftime('%Y-%m-%d %H:%M:%S'), []
    for i in rows:
        try: a = json.loads(i.get('ActionJson') or '{}')
        except ValueError: a = {}
        tri = a.get('triage') or {}
        if tri and tri.get('sig') == (i.get('Sig') or '') and not tri.get('error') and not tri.get('pending'): continue
        if i.get('Kind') == 'rule':
            # a rule question is the owner's yes or no on the row itself: triage reading it as work opened a task to make the rule
            a['triage'] = {'intent': 'fyi', 'kind': None, 'why': 'a question for you - its own row says yes or no', 'sig': i.get('Sig') or '',
                           'at': now, 'linked_task': None, 'error': None}
            store.set_idea_action(i['IdeaId'], a); done.append(i['IdeaId']); continue
        msg, tid, _ = _idea_message(store, i, a, report_title)      # the task's status is the model's to weigh, not this branch's
        if llm is None:
            a['triage'] = {'pending': True, 'sig': i.get('Sig') or '', 'at': now}
            store.set_idea_action(i['IdeaId'], a); continue
        try:
            intent, fail = judge(store, msg, llm, owner_addresses(store), own_addresses(store))
            if fail: raise RuntimeError(fail.get('err') or 'the model failed')
            if intent.get('degraded'): raise RuntimeError(intent.get('parse_error') or 'the answer was not a verdict')
        except Exception as e:
            a['triage'] = {'error': str(e)[:200], 'sig': i.get('Sig') or '', 'at': now}
            store.set_idea_action(i['IdeaId'], a); continue
        a['triage'] = {'intent': intent.get('intent'), 'kind': intent.get('kind'), 'why': str(intent.get('why') or '')[:200],
                       'sig': i.get('Sig') or '', 'at': now, 'linked_task': tid, 'error': None}
        if tid: a['tid'] = tid
        if intent.get('intent') in ('task', 'reply_only') and not tid:
            try:
                out = ingest_message(store, {**msg, '_verdict': (intent, {})}, actor='assistant', llm=llm)
                if out.get('task_id'):
                    a['tid'] = out['task_id']
                    store.update_task(out['task_id'], {'SourceRef': f"assistant:idea:{i['IdeaId']}"}, 'assistant')
            except Exception as e:
                a['triage'] = {'error': f'opening the work failed: {str(e)[:160]}', 'sig': i.get('Sig') or '', 'at': now}
        store.set_idea_action(i['IdeaId'], a); done.append(i['IdeaId'])
    return done


def _public(i: dict) -> dict:
    try: a = json.loads(i.get('ActionJson') or '{}')
    except ValueError: a = {}
    return {'id': i['IdeaId'], 'key': i['Key'], 'kind': i['Kind'], 'text': i['Text'], 'why': a.pop('why', ''), 'action': a, 'status': i.get('Status'),
            'source': a.get('source'), 'section': section_of({'section': a.get('section'), 'kind': i['Kind']}),
            # a put-away idea says which day it comes back, not "until its day"
            'until': i.get('SnoozeUntil') if i.get('Status') == 'snoozed' else None}


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


def read_blocks(chosen: dict) -> list:
    """[{id, label, window}] for the blocks this run actually read, in catalogue order. What the
    receipt under the post is written from - it used to be a fixed sentence with hand-counted
    numbers, which could only ever describe the one report it was written for."""
    from . import assistantblocks as blk
    out = []
    for b in blk.CATALOGUE:
        o = (chosen or {}).get(b.id)
        if chosen is not None and not (o or {}).get('on'): continue
        o = o or {}
        win = f"{o['days']}d" if o.get('days') else f"{o['hours']}h" if o.get('hours') else ''
        out.append({'id': b.id, 'label': b.label, 'window': win})
    return out


def _footer(r: dict) -> str:
    if r.get('scope') == 'sources':
        n = int(r.get('systems') or 0)
        return f"Reviewed: {plural(n, 'configured data source')} only"
    from .lanes import idea_counted   # the words the Reports tab counts the same candidates in, never the internal kind
    kinds = ', '.join(f"{v} {idea_counted(k)}" for k, v in r['candidates'].items()) or 'no candidates'
    skip = f"; let go: {len(r['skipped'])}" if r['skipped'] else ''
    counted = (f"Reviewed: {kinds}{skip} - {r.get('people', 0)} thread(s) of what people said, {r['recent']} sender/subject line(s) from the last two days, "
               f"{r['week']} task(s) closed this week, {r['open']} open task(s), {r['said']} line(s) already said"
               + ('' if r['model'] else " - no model: the facts in the hub's own words"))
    # THE COUNTS STAY. Naming the blocks does not make "41 sender/subject lines" less of a fact,
    # and a test caught me dropping them. `Read:` adds WHICH queries produced them - the part
    # nobody could see - on its own line, because sixteen names run on after "Reviewed:" read as a
    # paragraph. Labels as WRITTEN: lowercasing turned "What I promised" into "what i promised".
    # A post from before blocks carries no `blocks` key and keeps the counts alone; rewriting its
    # receipt from today's catalogue would be a guess about a run nobody can re-read.
    if r.get('blocks') is None: return counted
    named = ', '.join(b['label'] + (f" ({b['window']})" if b['window'] else '') for b in r['blocks']) or 'nothing'
    return counted + '\nRead: ' + named


def _judged(judge, say: list) -> dict | None:
    """The card's answer for these lines, or None when no judge answered - the judge is handed the
    lines as they will read on the post (text and why), never a paraphrase of them."""
    lines = '\n'.join(f"- {s.get('text') or ''}\n    why: {s.get('why') or ''}" for s in say)
    try: return judge(lines, len(say))
    except Exception as e:
        logger.warning(f'assistant: the routing judge failed, so the post reaches you - {e}'); return None


def run(store, llm=None, force: bool = False, instruction: str = None, *,
        watch_source_ids=None, watch_sources=None, systems_only: bool = False, blocks=None,
        report_id=None, report_title: str = None, always_post: bool = False, judge=None) -> dict:
    """One post. The Reports tab's scheduler calls this when the 'Assistant' report is due
    (reports.run_report_source) and its "Run now" calls it forced; the instruction is the report's
    editable prompt. Deleting or switching off that report is the off switch - a forced run still
    answers. Posts nothing when nothing is new.

    `judge(lines, n) -> {'timeline': bool, ...}` is the report's routing card, asked BEFORE anything
    posts (reports.decide). Every idea is triaged whatever it says (the owner, 2026-09-28: whether it is
    work is triage's call); timeline=no puts down at once each idea triage made no task of."""
    src = source(store)
    if not force and not (src and src.get('Active')): return {'ran': False, 'said': 0}
    if instruction is None and src and report_id is None:
        instruction = (src['cfg'].get('ai_prompt') or '').strip() or None
    # Direct calls retain the seeded Assistant's configuration. Report-scheduled calls pass their
    # own lists, including empty lists, so one Assistant report can never borrow another's sources.
    if report_id is None and watch_source_ids is None and watch_sources is None:
        watch_source_ids, watch_sources = _watch(store)
    with _LOCK:
        retry_stuck_ideas(store, report_id, report_title)
        return _run(store, llm, instruction, watch_source_ids or [], watch_sources or [],
                    systems_only, report_id, report_title, always_post, blocks, judge)


def seeded_source(store) -> dict | None:
    """THE Assistant row the installer wrote (store.py, `assistant_report_seeded`) - the one whose
    posts are the Timeline's `assistant` thread.

    Not `source()`, which returns the FIRST assistant-typed report and is the right answer for "is
    the Assistant switched on". Deleting the seeded row is the documented off switch, and once it is
    gone `source()` starts naming the owner's OWN Assistant report - which would have handed that
    report the shared thread and the shared idea namespace, the very collision own_identity exists
    to prevent. The anchor is `Owner='template'`: every seeded row carries it, the API never writes
    it (server.py builds report rows as the owner), and it survives an edited title or schedule."""
    for src in store.list_sources(active_only=False):
        if src.get('Channel') != 'report' or src.get('Owner') != 'template': continue
        try: c = json.loads(src.get('ConfigJson') or '{}')
        except ValueError: continue
        if c.get('type') == 'assistant': return src | {'cfg': c}
    return None


def own_identity(store, report_id) -> bool:
    """Does this post belong to a REPORT of its own, rather than to the app's Assistant?

    Identity and data scope used to be the same flag. `systems_only` decided the post's
    ConversationId, its displayed name AND the namespace its idea keys live in - which worked only
    while "has sources of its own" and "is its own monitor" were the same sentence. Tick a Taskuary
    block on a sourced monitor and it would have lost its namespace mid-life: two Assistant reports
    suppressing each other's findings on a shared idea key, the failure system_checks() is already
    commented for. So identity is the report, and the report alone.

    The SEEDED Assistant row is the exception that keeps this backwards-compatible: its posts ARE
    the Timeline's `assistant` thread and have always been. Anchored on that row (seeded_source),
    never on "the first assistant-typed report" - delete the seeded row, which is the documented off
    switch, and the owner's own Assistant report would inherit the exception along with the shared
    namespace this function exists to keep it out of."""
    if report_id is None: return False
    try:
        src = seeded_source(store)
        return not (src and str(src.get('SourceId')) == str(report_id))
    except Exception: return True


def _run(store, llm, instruction, watch_source_ids, watch_sources, systems_only=False,
         report_id=None, report_title=None, always_post=False, blocks=None, judge=None) -> dict:
    c = cfg(store); now = datetime.now()
    # the report's own block choice drives its producers too - ticking "Work gone quiet" off and
    # still getting cold rows would be the card describing a choice nothing read
    if blocks is not None:
        from . import assistantblocks as blk
        c = c | blk.producer_cfg(blocks, c)
    store.set_setting('assistant_last_run', now.isoformat(timespec='seconds'), 'assistant')
    # A report that reads NOTHING - every block off and no data source either - would otherwise
    # swap in the systems prompt, hand the model "(none selected)" and post whatever it invented
    # from that. It runs on a clock, so it would do that for ever without saying why. Say why.
    if systems_only and not (_ids(watch_source_ids) or _inline(watch_sources)):
        why = ('this report reads nothing: no Taskuary block is ticked and no data source is chosen '
               '- tick a block, or choose a source, on the report')
        logger.warning(f"assistant: {report_title or 'Advisor'} ran and read nothing - {why}")
        return {'ran': True, 'said': 0, 'reads_nothing': True, 'summary': why, 'inputs': '',
                'reviewed': {'notes': '', 'scope': 'nothing', 'systems': 0, 'why': why}}
    state = {i['Key']: i for i in store.list_ideas()}
    from .firstrun import unchosen
    if llm is None and not unchosen(store):           # before the first run picks an AI there is none to ask - the facts stand
        from .llm import build_llm
        try: llm = build_llm(store)
        except Exception as e:
            logger.debug(f'assistant: no model - {e}'); llm = None
    # the owner's own sent words are read by the model BEFORE the candidates are found: which of them asked for
    # something and which promised it is the judge's call, one batched call a run, each message once (sentjudge.py)
    if llm is not None and not systems_only and c['producers'] & {'followup', 'promise'}:
        from . import sentjudge
        try: sentjudge.judge(store, llm)
        except Exception as e: logger.warning(f'assistant: the sent-words judge was skipped - {e}')
    cands = [] if systems_only else [again(state, x) for x in candidates(store, c) if fresh(state, x, now)]
    # Selecting system views is itself an explicit request for model judgement. It must keep
    # working even if the owner turns off the free-form "idea" producer in Settings.
    configured = bool(_ids(watch_source_ids) or _inline(watch_sources))
    used, note, read, mids = bool(llm and (configured if systems_only else ('idea' in c['producers'] or configured))), '', '', {}
    # A SYSTEM WORTH CONNECTING is no candidate: the model reads the `connectors` block in think() and raises it itself,
    # or not (connect_line). No model, no line - there is nothing to judge it with, and no word match stands in.
    if used:
        try:
            say, note, read, mids = think(store, cands, llm, instruction, c['max'],
                                          watch_source_ids, watch_sources, systems_only, blocks, report_id)
            # the week starts when a check that READ the counts came back - never on a preview or a failed pass
            if AUTOMATION_HEAD in (read or ''):
                store.set_setting(automation_key(store, report_id), now.isoformat(sep=' ', timespec='seconds'), 'assistant')
        except Exception as e:
            # A MODEL THAT FAILED IS A FAILED RUN (R2, the owner 2026-09-28: "same error" as a report's):
            # posting the facts alone read as a success, moved the clock, and nothing said it broke
            logger.warning(f'assistant: the model pass failed - {e}')
            return {'ran': True, 'said': 0, 'failed': True, 'error': f'the model pass failed: {str(e)[:400]}', 'inputs': ''}
    else: say = cands[:c['max']]          # no model: the facts still stand, in the hub's own words
    if not read:
        if systems_only: read = systems_inputs(store, watch_source_ids, watch_sources)
        else: read, mids = build_inputs(store, cands, 'CANDIDATES (no model pass - these posted as facts)',
                                        watch_source_ids, watch_sources, blocks, report_id)
    own_post = own_identity(store, report_id)
    # the note outlives the post: a quiet check leaves one too, so the next check starts where this
    # one stopped. Each report writes and reads its OWN note (notes_key) - one global note meant a
    # second Assistant report reading the first's private memory, and overwriting it.
    if note and not systems_only:
        k = notes_key(store, report_id)
        store.set_setting(k, note, 'assistant'); store.set_setting(f'{k}_at', now.strftime('%Y-%m-%d %H:%M:%S'), 'assistant')
    # Namespace monitor findings so two SQL checks can use the same natural idea key without one
    # report suppressing the other report's finding. Keyed on the REPORT, never on its data scope
    # (own_identity): a monitor that also reads a Taskuary block is still its own monitor.
    if own_post:
        say = [{**s, 'key': f"report:{report_id}:{s['key']}"} if str(s.get('key') or '').startswith('idea:') else s for s in say]
    # the state is read AGAIN here: another process may have posted while the model was thinking, and a
    # model echoing a dismissed key changes nothing
    state = {i['Key']: i for i in store.list_ideas()}
    say = [s | {'why': s.get('why') or s.get('plain') or s.get('facts') or ''} for s in say
           if fresh(state, s, now) and (systems_only or not contradicts_sent_reply(store, s))]
    # A CHASE THAT GREW IS SAID, whatever the model chose: told "be useful, not busy" and reading its own "nothing new" note,
    # it let a vendor's twelve days of silence go twice in a row, the owner's ask still open (2026-10-06). Only one it
    # raised before and the owner left open - once per step of silence (followups), the longest silence first.
    if not systems_only:
        have = {s['key'] for s in say}
        grown = sorted((x for x in cands if x.get('again') and x['key'] not in have and fresh(state, x, now)
                        and ':away' not in str(x.get('sig') or '')),                     # "they are away, I'd wait" can wait
                       key=lambda x: x.get('sig') or '', reverse=True)[:FORCED_CHASES]      # the newest silence first: the most to act on
        say = [x | {'why': x.get('plain') or x.get('facts') or ''} for x in grown] + say    # the owner reads facts, not the model's note
    if systems_only:
        rv = reviewed([], say, '(', '(', '(', used, '(', '(') | {
            'notes': '', 'scope': 'sources', 'systems': len(_ids(watch_source_ids)) + len(_inline(watch_sources))}
    else:
        rv = reviewed(cands, say, _recent(store), _open(store), _said(store, report_id=report_id), used, _week(store), _people(store)) | {
            'notes': note, 'blocks': read_blocks(blocks)}
    # ...and what the REPORT proposes on its own: the app's health. Read, not thought; fresh() keeps a declined one
    # from coming back, and a raised one from repeating. A system worth connecting is NOT here: the model raises it
    # in its own pass (connect_line), because a name match raised Monday.com off three holiday notices.
    if not systems_only:
        have = {s['key'] for s in say}
        # the report raises it as a block like any other: off in this report's choice, off here
        on = lambda bid: blocks is None or bool((blocks.get(bid) or {}).get('on'))
        try:
            props = health_ideas(store, now) if on('health') else []
            # ...and a rule the owner's own presses already draw, asked once (promote.py) - counted, never thought
            if on('rules'):
                from . import promote
                props += promote.ideas(store, state)
            # ...and it is a line like any other: it counts toward "Lines per post", first because it is the app's own
            # (health rode on top of the cap, and a post said to hold 3 lines held 5 - I9, 2026-09-27)
            say = ([x | {'why': x['action'].get('why', '')} for x in props if x['key'] not in have and fresh(state, x, now)]
                   + list(say))[:c['max']]
        except Exception as e: logger.warning(f'assistant: the health check was skipped - {e}')
    stamp = now.strftime('%Y-%m-%d %H:%M:%S')
    # the report's routing card reads the lines BEFORE they post; a judge that fails leaves the run
    # unjudged, and an unjudged run reaches the owner (reports.decide's rule)
    d = _judged(judge, say) if say and judge else None
    if not say:
        # Nothing to say is the normal outcome of a monitor and it posts NOTHING - unless the owner
        # chose "every run", in which case the check still says it ran, in one line, with what it
        # read behind it. A setting that promises every run and then shows nothing is a lie.
        if not always_post: return {'ran': True, 'said': 0, 'reviewed': rv, 'inputs': read}
        who = (report_title or 'Advisor') if own_post else 'Advisor'
        me = f'assistant:{report_id}' if own_post else 'assistant'
        mid = store.add_message({'TaskId': None, 'ExternalId': f'{me}:{stamp}', 'ConversationId': me, 'Channel': CHANNEL,
                                 'SourceName': who, 'Subject': f'{who} - nothing to report', 'FromName': who,
                                 'SentAt': stamp, 'BodyText': f'I checked and found nothing that needs you.\n\n{_footer(rv)}',
                                 'Status': 'feed'})
        store.add_route(mid, None, 'feed', None, 'the check ran and found nothing - you asked to see every run', [], 'assistant')
        store.set_brief(mid, json.dumps({'ideas': [], 'reviewed': rv, 'flight': [], 'stats': []}))
        return {'ran': True, 'said': 0, 'message_id': mid, 'reviewed': rv, 'inputs': read}
    # every line names the block behind it, looked up rather than asked for (source_of)
    rows = [store.upsert_idea(s | {'action': (s.get('action') or {}) | {'why': s['why']}
                                   | ({'source': src} if (src := source_of(s, mids, blocks)) else {})}, stamp) for s in say]
    # the source goes in the BODY, not only on the card: the Timeline's detail pane renders an
    # assistant post as its plain text, so a provenance that lived only in the React card was
    # invisible exactly where the owner reads the post
    def _said_line(i, s_):
        src, a_ = source_of(s_, mids, blocks), s_.get('action') or {}
        head = (f"- {i['Text']}" + (f"\n    whose move: {a_['whose']}" if a_.get('whose') else '')
                + (f"\n    suggestion: {a_['suggest']}" if a_.get('suggest') else '') + f"\n    why: {s_['why']}")
        if not src: return head
        win = f" ({src['window']})" if src['window'] else ''
        return f"{head}\n    from: {src['label']}{win}"
    body = ('\n'.join(_said_line(i, s_) for i, s_ in zip(rows, say)) + '\n\n' + _footer(rv)
            + (f"\nNote to my next check: {note}" if note else ''))
    # the row's one line: the first idea, cut at a word, and how many more wait behind it
    head = rows[0]['Text'] if len(rows[0]['Text']) <= 90 else rows[0]['Text'][:90].rsplit(' ', 1)[0] + '…'
    subj = head + (f' (+{len(rows) - 1} more)' if len(rows) > 1 else '')
    identity = f'assistant:{report_id}' if own_post else 'assistant'
    name = (report_title or 'Advisor') if own_post else 'Advisor'
    mid = store.add_message({'TaskId': None, 'ExternalId': f'{identity}:{stamp}', 'ConversationId': identity, 'Channel': CHANNEL,
                             'SourceName': name, 'Subject': subj, 'FromName': name, 'SentAt': stamp,
                             'BodyText': body, 'Status': 'feed'})
    store.add_route(mid, None, 'feed', None, "the assistant's post: what it noticed and what it would do - open it to talk back or act",
                    [], 'assistant')
    # the two blocks the model does not write. What is in flight and what the day counted are facts
    # the hub already holds; asking a model to restate them is how a brief starts describing work
    # that is not there. Snapshotted onto the post so it still reads correctly tomorrow.
    store.set_brief(mid, json.dumps({'ideas': [_public(i) for i in rows], 'reviewed': rv,
                                     'flight': [] if systems_only else in_flight(store),
                                     'stats': [] if systems_only else day_stats(store)}))
    store.set_ideas_message([i['IdeaId'] for i in rows], mid)
    store.audit('message', mid, 'assistant_post', 'assistant', 'agent', {'ideas': len(rows)})
    # the ideas are ARRIVALS: each newly said one goes through the same triage as a mail (PW-199) - by
    # the TRIAGE brain, the one every message is judged by, not the assistant's own model. Unless the
    # report's triage line says not (reports.LINES, 2026-10-16): then they are shown, and only shown
    if d is None or d.get('triage', True):
        try:
            from .llm import build_llm
            try: brain = build_llm(store)
            except Exception: brain = None
            triage_ideas(store, rows, brain, report_title=name if own_post else None)
        except Exception as e: logger.warning(f'assistant: idea triage skipped - {e}')
    if d is not None and not d.get('timeline'):
        # TIMELINE NEVER MEANS NEVER: an idea triage made no task of is put down at once - a task or nothing
        from . import funnel
        for i in rows:
            if not linked_task(store, i['IdeaId'], json.loads(i.get('ActionJson') or '{}')): funnel.settle(store, f"idea:{i['IdeaId']}", 'done', 'report')
    logger.info(f'assistant: posted {len(rows)} idea(s) as message {mid}')
    return {'ran': True, 'said': len(rows), 'message_id': mid, 'reviewed': rv, 'inputs': read, 'lines': [_public(i) for i in rows],
            **({'decided': d} if d is not None else {})}


# ── the buttons: the same five words on every surface (the owner, 2026-09-27) ────────────────
# Make a task (task: yours, nothing works it), Send to agent (agent), Not ours (dismiss: never said again), Remind me
# (snooze: back on its day), and done - handled some other way, which is what the rail's Done writes. Next is the
# walk's own and touches nothing. Draft follow-up, Discuss and the talk-back chat are gone: a task's agent drafts.
# ...and a rule question's yes (promote.py): the rule it proposed is made, through the one create path
VERBS = ('task', 'agent', 'dismiss', 'dismiss_kind', 'snooze', 'done', 'rule')
# WHAT THE OWNER DID WITH AN IDEA, kept where the Advisor reads it (the owner, 2026-10-02: "feedback on assistant ideas even on
# desktop does it teach it anything? we should have that"). The idea row's status said dismissed or done - and done covered a
# task made from it and a line merely handled alike - and a dismissed row ages out of ALREADY SAID with the rest. This log is
# the verdict itself, newest first and capped, so the prompt stays small and a turned-down KIND outlives its one idea.
VERDICTS_KEY, VERDICTS_CAP = 'advisor_idea_verdicts', 30
VERDICT_WORD = {'task': 'took it up - made it a task', 'agent': 'took it up - sent it to an agent', 'done': 'handled it',
                'dismiss': 'turned it down', 'dismiss_kind': 'turned it down - no more ideas like this'}


def verdicts(store) -> list:
    try: v = json.loads(store.get_setting(VERDICTS_KEY) or '[]')
    except ValueError: v = []
    return v if isinstance(v, list) else []


def _keep_verdict(store, i: dict, verb: str, actor: str):
    row = {'key': i.get('Key'), 'text': _short(i.get('Text'), 160), 'verdict': verb, 'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    store.set_setting(VERDICTS_KEY, json.dumps(([row] + [r for r in verdicts(store) if r.get('key') != row['key']])[:VERDICTS_CAP]), actor)


def verdicts_block(store, report_id=None) -> str:
    """The owner's verdicts on this report's ideas, as evidence - the model reads intent, nothing here routes on a word."""
    mine = owns(store, report_id)
    rows = [r for r in verdicts(store) if mine(str(r.get('key') or ''))]
    if not rows: return ''
    return ("WHAT THE OWNER DID WITH YOUR IDEAS (newest first - raise more like the ones taken up; do not raise again what was "
            "turned down, and nothing like the ones marked 'no more ideas like this', unless the facts are new):\n"
            + '\n'.join(f"- {VERDICT_WORD.get(r.get('verdict'), r.get('verdict'))} ({_when(r.get('at'))}): {r.get('text')}" for r in rows))


def linked_task(store, idea_id: int, a: dict) -> dict | None:
    """The LIVE task this idea already has: the one triage opened for it, else the one it is about. Make a task
    ignored both and opened a second task beside the one triage had opened (I1, 2026-09-27). A closed one is
    history - an idea never reopens it (I7)."""
    for t in store.dock_tasks(f'assistant:idea:{idea_id}', limit=1) + ([store.get_task(a['tid'])] if a.get('tid') else []):
        if t and t.get('Status') not in ('done', 'dropped'): return t
    return None


def _make_task(store, i: dict, a: dict, agent: bool, actor: str) -> dict:
    from . import ingest
    m = (store.get_message(a['mid']) or {}) if a.get('mid') else {}
    prior = store.get_task(m['TaskId']) if m.get('TaskId') else None
    t = linked_task(store, i['IdeaId'], a) or (prior if prior and prior.get('Status') not in ('done', 'dropped') else None)
    kind = str(a.get('kind') or (a.get('triage') or {}).get('kind') or (t or {}).get('Kind') or 'general').lower()
    kind = kind if kind in task_kinds.AGENT else 'general'
    # an idea that would be coding, on an install with no coding tool, is the general agent's (agents.coding_ready, 2026-10-16)
    from . import capabilities
    if kind == 'coding' and not capabilities.can_code(store): kind = 'general'
    if t:
        tid = t['TaskId']
        if agent and t.get('Kind') not in task_kinds.AGENT: store.update_task(tid, {'Kind': kind}, actor)
    elif m and not prior: tid = ingest.task_from_message(store, a['mid'], actor, kind if agent else 'task', None if agent else actor)
    else:
        # no message, or its task is CLOSED: new work noticed after the old was done. A message points at one task,
        # so the closed one keeps it and the evidence is carried into a fresh task
        summary = str(i.get('Text') or '').strip()
        body = str(m.get('BodyText') or '').strip()
        if body and body not in summary: summary += f'\n\nSource message: {body}'
        tid = store.create_task({'Title': str(a.get('title') or i.get('Text') or 'Advisor idea').strip()[:200], 'Summary': summary[:2000],
                                 'Kind': kind if agent else 'task', 'Source': 'assistant', 'SourceRef': f"assistant:idea:{i['IdeaId']}",
                                 **({} if agent else {'Assignee': actor})}, actor)
        if prior: store.add_comment(tid, 'assistant', 'assistant_agent', f"Opened from an Advisor idea; the earlier task {task_ref(prior['TaskId'])} is done.")
        store.audit('task', tid, 'create_from_assistant_idea', actor, detail={'idea_id': i['IdeaId'], 'message_id': a.get('mid'),
                                                                              'related_task_id': (prior or {}).get('TaskId')})
    if not t and a.get('title'): store.update_task(tid, {'Title': str(a['title'])[:200]}, actor)
    store.set_idea_action(i['IdeaId'], a | {'tid': tid})
    if agent:
        brief = str(a.get('title') or i.get('Text') or '').strip()
        if a.get('why'): brief += f"\n\nWhy the assistant raised it: {a['why']}"
        # ...and the report it points at, or the agent can only ask for it to be pasted (2026-09-23)
        if m and m.get('Channel') != 'assistant' and m.get('BodyText'):
            brief += f"\n\nThe source - {m.get('Subject') or 'the message'}:\n" + m['BodyText'].split('\n--- raw data ---')[0].strip()[:6000]
        # the SAME start as any task of its kind: the slot cap, the queue and the retry budget (A18, 2026-09-25)
        if kind == 'general': ingest._spawn(ingest._auto_general, store, tid, brief)
        elif auto_code_enabled(store): ingest._spawn(ingest._auto_code, store, tid)
    return {'taskId': tid, 'ref': task_ref(tid)}


def act(store, idea_id: int, verb: str, actor: str = 'owner', days: int = 1, until: str = None) -> dict:
    """One word on one idea. Every word writes the IDEA's own status - the rail's used to write only the rail's,
    and the Advisor went on listing an idea the owner had put down as open (I4, 2026-09-27)."""
    i = store.get_idea(idea_id)
    if not i: raise ValueError(f'no idea {idea_id}')
    if verb not in VERBS: raise ValueError(f'unknown verb: {verb}')
    try: a = json.loads(i.get('ActionJson') or '{}')
    except ValueError: a = {}
    out = {'ideaId': idea_id, 'verb': verb}
    if verb == 'snooze':
        # Remind me reads a day the way the task's own picker does ('2 weeks', a date, 'tomorrow')
        from . import remind
        at = remind.parse(until) if until else (datetime.now() + timedelta(days=max(1, int(days or 1)))).strftime('%Y-%m-%d %H:%M:%S')
        if not at: raise ValueError('say which day to bring it back')
        store.set_idea_status(idea_id, 'snoozed', actor, at)
        store.audit('idea', idea_id, verb, actor, detail={'until': at})
        return out | {'until': at, 'remindAt': at, 'when': remind.when(at)}
    if verb in ('task', 'agent'): out |= _make_task(store, i, a, verb == 'agent', actor)
    if verb == 'rule':
        from . import promote
        out |= promote.accept(store, i, a, actor)
    store.set_idea_status(idea_id, 'dismissed' if verb in ('dismiss', 'dismiss_kind') else 'done', actor)
    store.audit('idea', idea_id, verb, actor, detail={'kind': i.get('Kind')})
    _keep_verdict(store, i, verb, actor)
    return out
