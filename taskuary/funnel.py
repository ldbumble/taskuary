"""The pipe: everything that could need the owner, as ONE ranked pile the assistant walks them through.

Triage judges each message as it arrives; the Timeline shows them in the order they came. Neither
says what to look at NEXT. This does. It reads what the hub already knows - the feed with triage's
verdicts on it, the pending reviews, the live agents parked on a question, the calendar, the
assistant's own open lines and the follow-ups nobody chased - and sorts it into lanes, in the
order a sharp assistant would raise them:

    blocked    an agent stopped and is waiting on you - it is blocking work, so it comes out first
    time       a meeting inside two hours, an urgent sender
    approve    a reply or an action drafted and waiting for your yes
    asked      a person asked you for something and nobody is on it
    forgotten  the ask that slipped, the promise you made, the thread that went quiet
    report     a report you set up landed; an open task needs its final close decision
    fyi        a person told you something; read it or don't

The queue itself is a TIMELINE, oldest first - the longer a thing has waited, the closer it is to
the mouth - with the promoted lanes (an agent waiting, a meeting, a draft for your yes) jumping to the
front and fyi (nothing to do) demoted to the back. New arrivals land on top and slide to their slot.
This ranked pile is the feed's Unread view and the concierge walks the same items in the same order;
All remains chronological history. A row leaves Unread once it is read or otherwise resolved.
Anything an agent is working on remains visible at the bottom but is skipped by the concierge until
the agent stops or asks. FYI and
reports age out after a day; a draft waiting for a yes never does. No model is involved -
the words on every item are the facts they came from, so what it says can always be checked -
and the whole pile is recomputed on every look: a reply approved, a task closed or a meeting
passed leaves the pile by itself. The only memory is funnel_state: what this walk has already
surfaced, what the owner marked done, what they pushed back and until when.

The concierge (concierge.py) pulls from the mouth. Alerts are the same facts with a clock on
them - a meeting in fifteen minutes, an agent that just asked - and interrupt whatever the
conversation is on.
"""
import hashlib, json, re, threading, time
from datetime import datetime, timedelta
from loguru import logger

from .store import task_ref
from .assistant import _ts, _dt, _short, _gist, _agenda, _OOO

LANES = ('blocked', 'time', 'approve', 'broken', 'asked', 'forgotten', 'report', 'fyi', 'working')
# the lane's one word on the card, and which role colours its dot (theme.jsx ROLES)
LANE_WORDS = {'blocked': ('agent waiting', 'you'), 'broken': ('a check failed', 'bad'), 'time': ('coming up', 'working'), 'approve': ('needs your yes', 'you'),
              'asked': ('asked you', 'working'), 'forgotten': ('slipped', 'info'), 'report': ('landed', 'info'), 'fyi': ('fyi', None),
              'working': ('agent working', 'working')}   # in hand: at the very top, nothing to do until the agent stops or asks
SOON_MIN, ALERT_MIN = 120, 15     # a meeting inside two hours is time-sensitive; inside fifteen it interrupts
SETUP_GRACE_MIN = 15              # a walk-through the owner is still in does not raise its own hand
LATER_HOURS = 3                   # "not now" - it comes back this much later
FEED_DAYS = 7
# the owner's two knobs (Settings > Assistant): how far back the pipe reaches for ordinary mail - a
# first launch must not surface a year of never-triaged mail - and how much it holds at once.
# Drafts waiting for a yes and agents parked on a question ignore the window: they are on you
# whenever they happened.
HOURS_DEFAULT, MAX_DEFAULT = 12, 25
# The assistant's OWN lines get a longer window than mail. A mail going quiet after twelve hours
# is fine; its standing note that something is loose is the opposite - it is still true tomorrow,
# and expiring it is how "TQ-0329 hasn't moved, Nechama asked for that file today" left the pipe
# unseen (the owner, 2026-09-04: "ideas ... should come back every time assistant thinks of
# something new"). Measured on the owner's own store: at 12h two of the 64 open ideas reach the
# pipe, at 24h five, at 72h thirty-eight - so a day is the point where more becomes a flood
# rather than a reminder. An idea whose facts change is re-said, which bumps LastSaid and brings
# it back on its own; this window is only about how long an undecided one waits to be seen.
IDEA_HOURS = 24
# A failed run is named by convention: reports.py sends '<title> - FAILED' (reports.run_report_source
# reads the same suffix back). Matching those words ANYWHERE in the subject called 'Process Error
# Check - 0 rows' a failure, because the report's own name contains 'Error' (the owner, 2026-09-03:
# "that's not a fail, it says all clear?" - and the assistant said Next).
_FAILED = re.compile(r'FAILED\s*$')                # reports.py writes '<title> - FAILED', and it shouts
# Triage's category is not a read receipt. An incoming newsletter, system notice, feed row, or
# Assistant post may be low-value, but it still enters the unread inventory; this small set remains
# only for converting a manually named historical row into a generic FYI card.
_QUIET = {'filed', 'ignored', 'yours'}
PILE_EVERY = 30                   # websocket writes invalidate it; this is only a disconnected-client safety net
_CACHE = {'at': 0.0, 'pile': None, 'store': None, 'generation': 0}
_STATE = {}                        # tid -> 'working' | 'parked' | 'asking' | 'done' | 'idle', as last seen by the watcher
_SEEN = {}                         # tid -> (state, first seen at) - a change must HOLD before it is news
_WATCHED = [False]                 # first LOOK, even when there were no sessions; _STATE empty is not the same thing
DWELL = 12.0                       # seconds a new state must survive before the watcher announces it
_REPORT_SUMMARY = re.compile(r'(?im)^summary:\s*(.+)$')
_LOCK = threading.Lock()


MUTES_KEY = 'funnel_mutes'            # the owner's standing "never show me these again" rules
MUTED_LANES = ('fyi', 'report', 'forgotten')   # only what has nothing to do: a real ask still reaches them


def mutes(store) -> list:
    """The owner's standing rules: [{'sender': <email or ''>, 'words': [...], 'why': '...'}]. Written
    when they sweep the pipe with a reason ("skip all the mfa financial reports, that is taken care
    of") - a sweep alone marked the ones in front of them read and the next batch walked straight back
    in (the owner, 2026-09-03: "was it one time dismiss not a memory")."""
    try: return json.loads(store.get_settings().get(MUTES_KEY) or '[]') or []
    except ValueError: return []


def remember_mute(store, rule: dict, actor: str = 'owner') -> None:
    rules = [r for r in mutes(store) if (r.get('sender'), tuple(r.get('words') or [])) != (rule.get('sender'), tuple(rule.get('words') or []))]
    store.set_setting(MUTES_KEY, json.dumps((rules + [rule])[-25:]), actor)
    invalidate()


def like(words, hay: set) -> int:
    """How many of the owner's words this item carries. Prefixes count BOTH ways: they type
    "financials" about a "Financial Report" and "nozure" about nozur@ (2026-09-03)."""
    long = [h for h in hay if len(h) >= 4]
    return sum(1 for w in words if w in hay or any(h.startswith(w) or (len(w) >= 4 and w.startswith(h)) for h in long))


def muted(rule: dict, i: dict) -> bool:
    from .routing import tokens
    key = str(rule.get('sender') or '').lower()
    if key and key not in (str(i.get('email') or '').lower(), str(i.get('who') or '').lower()): return False
    # a rule can name a LANE rather than words: "skip all the fyi from Chana" is every fyi she sends,
    # not the mails with 'fyi' in the subject (2026-09-03)
    if rule.get('lane'): return i.get('lane') == rule['lane'] and bool(key)
    words = [w for w in (rule.get('words') or []) if w]
    if not words: return bool(key)
    return like(words, set(tokens(f"{i.get('who') or ''} {i.get('email') or ''} {i.get('title') or ''}"))) >= min(2, len(words))


def lane_index(lane: str) -> int: return LANES.index(lane) if lane in LANES else len(LANES)


def _item(key, kind, lane, title, *, who='', when='', since='', why='', mid=None, tid=None, rid=None,
          channel='', category='', preview='', **extra) -> dict:
    return {'key': key, 'kind': kind, 'lane': lane, 'title': _short(title, 140) or '(no subject)', 'who': _short(who, 60),
            'when': _ts(when), 'since': _ts(since or when), 'why': _short(why, 220), 'mid': mid, 'tid': tid,
            'ref': task_ref(tid) if tid else None, 'rid': rid, 'channel': channel, 'category': category,
            'preview': _gist(preview, 240), **extra}


# ── the producers: each reads one thing the hub holds ─────────────────────────────────────────
def _feed_skip(r: dict) -> bool:
    """Rows that are nobody asking anything: our own sends, withdrawn lines, an auto-reply, and
    anything on a task that is over (unless a draft on it still waits for a yes)."""
    if r.get('Direction') == 'out' or r.get('MsgStatus') in ('withdrawn', 'ignored'): return True
    if r.get('TaskStatus') in ('done', 'dropped') and r.get('ReviewStatus') != 'pending': return True
    return bool(_OOO.match(str(r.get('Subject') or '')))


def _assistant_wrapper(r: dict) -> bool:
    """True for a generated Assistant digest whose durable ideas are surfaced separately.

    Plain Assistant messages are real unread arrivals. A generated wrapper is only a container for
    its ``ideas`` rows; showing both is the duplicate-Assistant regression from 2026-09-04.
    """
    if r.get('Channel') != 'assistant' or not r.get('Brief'): return False
    try: return bool(json.loads(r['Brief']).get('ideas'))
    except (TypeError, ValueError, json.JSONDecodeError): return False


def _feed_group(r: dict):
    """The one thing a feed row belongs to.

    Once triage has attached messages to a task, that task is the boundary. A long WhatsApp room can
    contain several different jobs, so grouping only by ConversationId both swallowed those jobs and
    counted unrelated chat as ``+19`` on one task. Rows which do not have a task still group by their
    ordinary mail/chat thread.
    """
    if r.get('TaskId'): return ('task', r['TaskId'])
    if r.get('ConversationId'): return ('conversation', r['ConversationId'])
    return None


def thread_speaker(rows: list) -> dict:
    """Which row speaks for each triaged task (or untriaged conversation): {group: MessageId}.

    A draft waiting for a yes speaks whatever its age, then an agent parked on a question, then the
    newest line. Reviews and agents used to be EXEMPT from the one-line rule rather than winning it,
    so the older mail on the same task came up again as a separate ask.
    """
    best = {}
    for r in rows:
        group = _feed_group(r)
        if not group or _feed_skip(r) or _assistant_wrapper(r): continue
        rank = 2 if (r.get('ReviewStatus') == 'pending' and r.get('ReviewId')) else 1 if r.get('AgentWaiting') else 0
        if group not in best or rank > best[group][0]: best[group] = (rank, r['MessageId'])   # newest first, so ties keep the newest
    return {group: mid for group, (_rank, mid) in best.items()}


def from_feed(store, rows: list) -> list:
    out, agents, reviews, threads = [], set(), set(), {}
    speaks, more = thread_speaker(rows), {}
    for r in rows:
        if _feed_skip(r): continue
        # Generated Assistant reports carry durable ideas. Those ideas are produced below as the
        # actionable unread cards, one latest copy per idea; admitting the wrapper as a second FYI
        # is what made the same Assistant line appear over and over. A plain Assistant message with
        # no idea payload is still an ordinary unread arrival.
        if _assistant_wrapper(r): continue
        # ONE line per triaged task. Before triage makes a task, the conversation is the boundary.
        # This lets seven messages combined onto TQ-0367 come out as one task with +7, without also
        # swallowing every other job discussed later in the same WhatsApp room.
        cid = r.get('ConversationId')
        group = _feed_group(r)
        if group and speaks.get(group) != r['MessageId']:
            more[group] = more.get(group, 0) + 1
            continue
        who = r.get('FromName') or r.get('FromEmail') or r.get('SourceName') or r.get('Channel') or ''
        base = dict(who=who, when=r.get('SentAt'), mid=r['MessageId'], tid=r.get('TaskId'), channel=r.get('Channel') or '',
                    category=r.get('Category') or '', preview=r.get('Preview'), cid=cid, email=r.get('FromEmail') or '')
        subj = r.get('Subject') or r.get('Title') or ''
        if r.get('MsgStatus') == 'triaging':
            out.append(_item(f"msg:{r['MessageId']}", 'triaging', 'fyi', subj, why='just arrived - triage is deciding', settling=True, **base))
            if group and threads.get(group) is None: threads[group] = out[-1]
            continue
        if r.get('ReviewStatus') == 'pending' and r.get('ReviewId'):
            if r['ReviewId'] in reviews: continue
            reviews.add(r['ReviewId'])
            action = r.get('ReviewKind') == 'action'
            rv = store.get_review(r['ReviewId']) or {}
            # A review row is joined to the message the draft originally saw.  Keep that review
            # at the front of its thread, but let its card speak with the newest inbound line on
            # the task.  Otherwise the Assistant can truthfully have six newer Teams messages in
            # SQLite and still show only the old "yes" that opened the draft.
            latest = (store.last_inbound_on_task(r.get('TaskId')) if r.get('TaskId') else
                      store.last_inbound_in(cid) if cid else None)
            stale = bool(latest and latest.get('MessageId') != rv.get('MessageId'))
            if latest:
                base.update(mid=latest.get('MessageId'), when=latest.get('SentAt'),
                            who=latest.get('FromName') or latest.get('FromEmail') or who,
                            preview=latest.get('BodyText') or base.get('preview'),
                            channel=latest.get('Channel') or base.get('channel'))
                subj = latest.get('Subject') or subj
            out.append(_item(f"review:{r['ReviewId']}", 'action' if action else 'review', 'approve', subj, rid=r['ReviewId'],
                             why='an agent proposed an action - it runs only if you say so' if action
                                 else ('a reply is drafted for you to send' if r.get('HasDraft') else 'a reply is owed - draft it with AI or write it'),
                             draft=bool(r.get('HasDraft')), summary=agent_found(store, r.get('TaskId')),
                             stale=stale,
                             sig=hashlib.sha1(str(rv.get('DraftText') or '').encode()).hexdigest()[:10],   # the draft's fingerprint: a rewrite is news
                             **base))
            if group: threads[group] = out[-1]                 # the draft speaks for its task/thread
            continue
        if r.get('AgentWaiting') and r.get('TaskId'):
            if r['TaskId'] in agents: continue
            agents.add(r['TaskId'])
            out.append(_item(f"agent:{r['TaskId']}", 'agent', 'blocked', r.get('Title') or subj, agent=r.get('Working') or 'agent',
                             why=f"{r.get('Working') or 'the agent'} stopped and is waiting on you", **base))
            if group: threads[group] = out[-1]
            continue
        base['working'] = r.get('Working') or ''             # an agent has it: build() lets these go, by name
        if r.get('Channel') == 'report':
            # a run whose own first line says it could not summarise (no AI connector) is on the
            # Timeline and nowhere else - three of them came out of the pipe, one per turn, on a
            # fresh install's first day (the 2026-09-03 break test)
            from .reports import NO_BRAIN
            if NO_BRAIN in str(r.get('Preview') or ''): continue
            sid = report_source_id(store, r.get('SourceName'))
            bad = report_failed(store, sid, subj)
            # ...and a run the owner asked to be TOLD about is not news, it is work. When a report
            # carries a "move it up if" sentence, triage judges the run against it and makes a task
            # of a match (triage.classify_intent's `watch`) - but this branch filed every report row
            # in the report lane regardless, so the promotion the owner had asked for stopped one
            # step short of the pipe (2026-09-04). A matched run falls through and ranks as the work
            # it now is; an ordinary run and a failure keep their own lanes.
            if not bad and r.get('TaskId') and (r.get('NeedsYou') or r.get('Category') in ('coding', 'todo', 'action')):
                base['source_id'] = sid
            else:
                out.append(_item(f"report:{r['MessageId']}", 'report', 'broken' if bad else 'report', subj, bad=bad, source_id=sid,
                                 why='the check failed - the cause is in it' if bad else 'a report you set up landed', **base))
                if group and threads.get(group) is None: threads[group] = out[-1]
                continue
        cat = r.get('Category') or ''
        # A triage category is not a read receipt.  Filed/ignored/automated/promotional rows are
        # still incoming rows; the owner's explicit funnel state is what later removes them.
        if r.get('TheirTurn') or r.get('AnsweredAt'): continue
        urgent = (r.get('Priority') or '') == 'urgent'
        if cat in ('coding', 'todo') and (r.get('NeedsYou') or r.get('Working')):   # a worked row is kept, tagged, and let go in build()
            out.append(_item(f"msg:{r['MessageId']}", 'todo', 'time' if urgent else 'asked', subj, coding=cat == 'coding',
                             why=('an urgent sender - ' if urgent else '') + (r.get('RouteReason') or ('a coding task with no agent on it' if cat == 'coding' else 'real work with nobody on it')), **base))
            if group and threads.get(group) is None: threads[group] = out[-1]
            continue
        if cat == 'review' or (r.get('NeedsYou') and cat not in ('info',)):
            out.append(_item(f"msg:{r['MessageId']}", 'asked', 'time' if urgent else 'asked', subj,
                             why=r.get('RouteReason') or 'a person asked you for something', **base))
            if group and threads.get(group) is None: threads[group] = out[-1]
            continue
        # Anything incoming which reached the Timeline and was not handled above is unread
        # information.  Triage may label it automated/promo/feed/filed/assistant, but classifying
        # it is not the same as the owner reading it.
        out.append(_item(f"msg:{r['MessageId']}", 'fyi', 'fyi', subj, why=r.get('RouteReason') or 'a person told you something; nothing to do', **base))
        if group and out and threads.get(group) is None: threads[group] = out[-1]
    for group, n in more.items():                 # the rest of each task/thread, counted on the row that speaks for it
        held = threads.get(group)
        if held is not None: held['more'] = held.get('more', 0) + n
    return out


_SOURCES = {'at': 0.0, 'by': {}}
def report_source_id(store, name: str) -> int | None:
    """The report source behind a report message (its SourceName is the report's title) - cached a minute."""
    if time.time() - _SOURCES['at'] > 60:
        by = {}
        for src in store.list_sources(active_only=False):
            if src.get('Channel') != 'report': continue
            try: title = json.loads(src.get('ConfigJson') or '{}').get('title')
            except ValueError: title = None
            for k in (src.get('Address'), title):
                if k: by[str(k)] = src['SourceId']
        _SOURCES.update(at=time.time(), by=by)
    return _SOURCES['by'].get(str(name or ''))


def report_failed(store, sid, subject: str) -> bool:
    """Did this run of the report FAIL? The run record says so where we have one; otherwise the
    subject's own convention ('- FAILED'). Never a word found inside the report's name."""
    if sid:
        runs = store.report_runs(sid, 1)
        if runs: return bool(runs[0].get('failed'))
    return bool(_FAILED.search(str(subject or '')))


def reply_to(store, tid) -> int | None:
    """The message a reply from this task would answer. An agent that finished and a wrap-up have no
    message of their own, so "create reply from it to sender" had nothing to work with and the chat
    had to refuse (the owner, 2026-09-03: "why can\'t you create a draft from here")."""
    m = store.last_inbound_on_task(tid) if tid else None
    return m['MessageId'] if m else None


def agent_found(store, tid) -> str:
    """What the agent that worked this task said it found - the CODER REPORT's summary line - so the
    assistant can say 'the agent looked; here is what it found' before asking for the yes."""
    if not tid: return ''
    rep = next((c for c in reversed(store.list_comments(tid)) if str(c.get('Body') or '').startswith(('CODER REPORT', 'HANDOVER NOTE'))), None)
    if not rep: return ''
    m = _REPORT_SUMMARY.search(rep['Body'])
    return _short(m.group(1) if m else rep['Body'].split('\n', 1)[-1], 300)


def from_agents(store) -> list:
    """Live sessions parked on a question - whatever the feed window, an agent waiting is waiting."""
    from . import terminal as term, waitroom
    out = []
    fresh_setup = (datetime.now() - timedelta(minutes=SETUP_GRACE_MIN)).strftime('%Y-%m-%d %H:%M:%S')
    try: live = term.live_sessions(tail=6)
    except Exception: return out
    for t in live:
        tid = t.get('taskId')
        if not tid: continue
        task = store.get_task(tid) or {}
        if task.get('SourceRef') == 'assistant:dock' or task.get('Status') in ('done', 'dropped'): continue
        # A WALK-THROUGH the owner just started is a conversation they are IN. It parked because it
        # said its piece and is waiting for their next line - and the by-the-way bar announced
        # "assistant stopped on TQ-0009 and is waiting on you" sixty seconds after they opened it
        # (the 2026-09-03 break test). It comes back as a blocked row only once it has been left.
        if task.get('SourceRef') == 'assistant:setup' and _ts(t.get('started')) >= fresh_setup: continue
        waiting = t.get('waiting') if t.get('waiting') is not None else (t.get('idle') or 0) >= term.IDLE_WAITING
        if not waiting: continue
        tail = [str(x).strip() for x in (t.get('tail') or []) if str(x).strip()]
        # ...read off the RENDERED screen when there is one, with the TUI's chrome dropped: the
        # card showed a theme toolbar where the agent's question belonged (2026-09-03)
        if t.get('sid'):
            try: tail = [x for x in term.asking_lines(t['sid'], 4)] or tail
            except Exception as e: logger.debug(f'funnel: no rendered screen for {t.get("sid")} - {e}')
        asking = waitroom.looks_like_question(tail)
        agent = t.get('agent') or t.get('label') or 'agent'
        out.append(_item(f"agent:{tid}", 'agent', 'blocked', task.get('Title') or f'task {tid}', who=agent, when=t.get('started'),
                         tid=tid, agent=agent, asking=asking, tail=tail[-4:], sid=t.get('sid'), mode=t.get('mode') or 'terminal',
                         why=f'{agent} asked you something' if asking else f'{agent} stopped and is waiting on you'))
    return out


def from_proposals(store, used_rids: set) -> list:
    """A pending proposal with no mail and no task behind it - a switch the owner asked for in the
    chat, waiting for their yes. Every other review reaches the pile through its message row, so a
    task-less one could only be approved from the chat line that proposed it, and that scrolls away."""
    out = []
    for rv in store.list_reviews('pending'):
        if rv.get('Kind') != 'action' or rv.get('MessageId') or rv.get('TaskId') or rv['ReviewId'] in used_rids: continue
        out.append(_item(f"review:{rv['ReviewId']}", 'action', 'approve', rv.get('Reason') or 'a change waits for your yes',
                         who='you asked for it', when=rv.get('CreatedAt'), rid=rv['ReviewId'],
                         why='a setting waits for your yes - nothing changes until you approve it'))
    return out


def from_calendar(store, now: datetime) -> list:
    out = []
    for e in _agenda(store):
        st, en = _dt(e.get('start')), _dt(e.get('end')) or _dt(e.get('start'))
        if not st or (en and en < now): continue
        mins = int((st - now).total_seconds() // 60)
        if mins > SOON_MIN: continue
        who = [w for w in (e.get('who') or []) if w]
        key = f"meeting:{str(e.get('start') or '')[:16]}:{_short(e.get('subject'), 40)}"
        out.append(_item(key, 'meeting', 'time', e.get('subject') or 'the meeting', who=', '.join(who[:3]), when=e.get('start'),
                         mins=mins, event={k: e.get(k) for k in ('start', 'end', 'subject', 'who', 'where', 'about', 'join', 'organizer')},
                         why=('starting now' if mins <= 0 else f'in {mins} min') + (f" with {', '.join(w.split()[0] for w in who[:3])}" if who else '')))
    return out


def from_forgotten(store, used_mids: set, used_tids: set, used_cids: set = frozenset()) -> list:
    """The assistant's own open lines (assistant.py posts them on its half-hourly check: the ask that
    slipped, the promise, the thread gone quiet). They enter the pipe when SAID - LastSaid, not the
    age of the thread they are about - so a four-day-old silence raised this morning is this morning's."""
    out, seen_cids = [], set()
    for i in store.list_ideas('open'):
        try: a = json.loads(i.get('ActionJson') or '{}')
        except ValueError: a = {}
        if i.get('Kind') == 'prep': continue                      # the calendar lane already has the meeting itself
        # A closed source task does NOT mean the Assistant post was read. The post may also name a
        # separate follow-up or a pattern learned across several tasks (for example, recurring blank
        # logins). It leaves Unread only through its own idea state, never as a side effect of closing
        # the task it cited.
        m0 = (store.get_message(a['mid']) or {}) if a.get('mid') else {}
        tid = a.get('tid') or m0.get('TaskId')
        if not tid and m0.get('ConversationId'):
            # the mail itself never joined the task, but its thread did: the thread's task is the fact
            try: tid = next((c.get('TaskId') for c in store.thread_messages(conversation_id=m0['ConversationId'], limit=12) if c.get('TaskId')), None)
            except Exception: tid = None
        # ...and a line about a thread the owner has since REPLIED on is over too - the reply is the follow-up
        from .assistant import sent_reply_for
        sent = sent_reply_for(store, {'action': a})
        if sent and _ts(sent.get('DecidedAt') or sent.get('CreatedAt')) >= _ts(i.get('LastSaid') or i.get('FirstSeen')):
            store.set_idea_status(i['IdeaId'], 'done', 'funnel'); continue
        if a.get('mid') in used_mids or (a.get('tid') and a['tid'] in used_tids): continue
        lane = 'report' if a.get('section') == 'systems' else 'forgotten'
        m = (store.get_message(a['mid']) or {}) if a.get('mid') else {}
        cid = m.get('ConversationId')
        if cid and (cid in used_cids or cid in seen_cids): continue     # one line per conversation
        if cid: seen_cids.add(cid)
        # a line that NAMES a task belongs to it even when the action does not say so (the older
        # rows, and any the model writes as a bare note): without the tid the pipe cannot tell that
        # an agent has the work, and "TQ-0329 hasn't moved" sat in 'slipped' (2026-09-03)
        if not tid:
            ref = re.search(r'\bTQ-?0*(\d+)\b', f"{i.get('Text') or ''} {a.get('why') or ''}", re.I)
            if ref and store.get_task(int(ref.group(1))): tid = a['tid'] = int(ref.group(1))
        out.append(_item(f"idea:{i['IdeaId']}", 'idea', lane, i['Text'], when=i.get('LastSaid') or i.get('FirstSeen'), mid=a.get('mid'), tid=a.get('tid'),
                         who=m.get('FromName') or m.get('FromEmail') or '', channel=m.get('Channel') or '',
                         idea=i['IdeaId'], idea_kind=i.get('Kind'), action=a, why=a.get('why') or 'the assistant raised this'))
    return out


def from_wrapped(store, now: datetime, busy: set) -> list:
    """Sending a reply and ending an agent run never close a task (the owner controls completion), so a
    task can sit in 'waiting' with the reply sent and the result saved. That last step is the owner's
    - the assistant puts it in front of them once: close it, or keep it open."""
    out = []
    for t in store.list_tasks(active_only=True):
        tid = t['TaskId']
        # in_progress means an agent has it: there is nothing to close yet, whether or not a session
        # is alive right now (the same rule build() uses to put such a task on the shelf)
        if t.get('Status') not in ('open', 'waiting') or tid in busy or t.get('SourceRef') == 'assistant:dock': continue
        if t.get('ReviewStatus') == 'pending' or store.pending_review(tid): continue
        sent = store.sent_reply(task_id=tid)
        # ...or the owner answered from their own mail client: a reply typed in Outlook ends the work
        # exactly as much as one approved here, and this used to see only Taskuary's own sends
        own = None if sent else store.own_reply_on_thread(task_id=tid)
        if not (sent or own): continue
        found = agent_found(store, tid)
        when = (sent.get('DecidedAt') or sent.get('CreatedAt')) if sent else own.get('SentAt')
        out.append(_item(f"wrap:{tid}", 'wrapup', 'report', t.get('Title'), who='you', when=when, tid=tid, summary=found,
                         mid=reply_to(store, tid),
                         sent=_short(sent.get('FinalText') or sent.get('DraftText') if sent else own.get('BodyText'), 200),
                         why='the reply went out' + (' and the agent finished' if found else '') + ' - the task is still open'))
    return out


# ── the pile ─────────────────────────────────────────────────────────────────────────────────
# the queue is a TIMELINE, oldest first inside each band - but what blocks work or has a clock on it
# is promoted to the front, a PERSON asking you comes before the assistant's own follow-up lines,
# those before reports, and fyi (nothing to do) is demoted to the back.
# a failed check is promoted from 'report' (was 5, behind everything) to just under a drafted
# reply: one click sends that reply, while a dead SQL host is real work - but both come before
# a person's ask, because the check is a SYSTEM the owner asked to be told about
_BAND = {'blocked': 0, 'time': 1, 'approve': 2, 'broken': 3, 'asked': 4, 'forgotten': 5, 'report': 6, 'fyi': 7, 'working': 9}


def _order(items: list) -> list:
    """Next-first: the promoted bands, then everything else oldest first, fyi last. A meeting sorts
    by when it starts, soonest first."""
    def k(i): return (_BAND.get(i['lane'], 3), i.get('when') if i['kind'] == 'meeting' else (i.get('since') or i.get('when') or ''))
    return sorted(items, key=k)


def _apply_states(items: list, states: dict, now: datetime, keep_surfaced: bool = False) -> list:
    """Apply the owner's decisions to the assistant's work queue.

    A surfaced row is read and the feed's Unread view removes it. Unresolved approvals and agent
    questions still remain in this internal queue (marked surfaced) so the assistant can report
    that work accurately without presenting it again as the next unread item.
    """
    stamp = now.strftime('%Y-%m-%d %H:%M:%S')
    out = []
    for i in items:
        st = states.get(i['key'])
        if st:
            if st['Status'] == 'done': continue
            if st['Status'] in ('later', 'skip') and (not st.get('Until') or _ts(st['Until']) > stamp): continue
            if st['Status'] == 'surfaced':
                # shown, but CHANGED since - the agent rewrote the draft, the question moved on: new again
                if i.get('sig') and st.get('Note') and st['Note'] != i['sig']:
                    out.append(i); continue
                # Read is gone from the ordinary queue. Only unresolved work that is still on the
                # owner (a draft/approval or an agent question) remains addressable and marked.
                if not keep_surfaced and i['lane'] not in ('blocked', 'approve', 'working'): continue
                i = i | {'surfaced': True, 'surfaced_at': st.get('At')}
        out.append(i)
    return out


def knobs(store) -> tuple[int, int]:
    s = store.get_settings()
    def n(k, d):
        try: return max(1, int(s.get(k) or d))
        except (TypeError, ValueError): return d
    return n('funnel_hours', HOURS_DEFAULT), n('funnel_max', MAX_DEFAULT)


def _aged_out(i: dict, now: datetime, hours: int) -> bool:
    """Older than the owner's window is yesterday's - the pipe is what came in lately, not an archive.
    A meeting, a parked agent, a draft waiting for a yes: on you whenever they happened."""
    if i['lane'] in ('blocked', 'broken', 'time', 'approve', 'working'): return False
    if i['kind'] == 'idea': hours = max(hours, IDEA_HOURS)      # ...and never shorter than a day
    when = _dt(i.get('since') or i.get('when'))
    return bool(when) and when < now - timedelta(hours=hours)


RUN_STALE_MIN = 20        # a 'running' run row nobody has touched for this long is not working anything

def working_tids(store) -> set:
    """Tasks an agent has right now - a live session, or a headless run that is actually running.
    Nothing about them is the owner's to do until the agent stops.

    A run row left at 'running' by a session that died used to be proof enough: TQ-0006 sat in the
    working lane with no session and "nothing for you", and the outage task vanished from the pipe
    altogether - not read, not offered, not findable (the 2026-09-03 break test). A row nobody has
    touched for RUN_STALE_MIN is a corpse, not a worker."""
    from . import terminal as term
    fresh = (datetime.now() - timedelta(minutes=RUN_STALE_MIN)).strftime('%Y-%m-%d %H:%M:%S')
    out = {r['TaskId'] for r in store.running_runs()
           if r.get('TaskId') and str(r.get('UpdatedAt') or r.get('StartedAt') or '') >= fresh}
    try:
        for t in term.live_sessions(tail=0):
            if not t.get('taskId'): continue
            waiting = t.get('waiting') if t.get('waiting') is not None else (t.get('idle') or 0) >= term.IDLE_WAITING
            if not waiting: out.add(t['taskId'])
    except Exception: pass
    return out


def build(store, now: datetime = None, keep_surfaced: bool = False) -> dict:
    now = now or datetime.now()
    rows = store.feed(limit=400, days=FEED_DAYS)
    items = from_feed(store, rows)
    # the live session knows more about a parked agent than its feed row does (its last lines,
    # whether it asked) - so its item replaces the row's
    agents = {a['key']: a for a in from_agents(store)}
    items = [agents.pop(i['key']) | {'mid': i.get('mid')} if i['key'] in agents else i for i in items] + list(agents.values())
    # ...and the mail that STARTED a task whose agent is now waiting is not a second item: the
    # agent's question is the thing to answer, and answering it is answering the mail
    parked = {i['tid'] for i in items if i['kind'] == 'agent'}
    items = [i for i in items if not (i['kind'] in ('asked', 'todo', 'fyi') and i.get('tid') in parked)]
    items += from_proposals(store, {i['rid'] for i in items if i.get('rid')})
    items += from_calendar(store, now)
    # Only a row still inside the walk window may suppress a fresh Assistant follow-up about the
    # same conversation. Once filed/automated mail was admitted to Unread, an old message could
    # occupy used_cids here, hide this morning's follow-up, and then age out itself below—leaving
    # neither one in the queue.
    hours, _cap = knobs(store)
    # Only a source row that is itself still unread can suppress an Assistant idea about the same
    # message/task/thread. Previously a source row marked surfaced remained in `used_*` until the
    # final state pass below; it hid the newer Assistant idea and was then removed itself, leaving
    # neither one visible while Unread claimed All done.
    states = store.funnel_states()
    current = _apply_states([i for i in items if not _aged_out(i, now, hours)], states, now)
    used_mids = {i['mid'] for i in current if i.get('mid')}
    used_tids = {i['tid'] for i in current if i.get('tid')}
    used_cids = {i['cid'] for i in current if i.get('cid')}
    items += from_forgotten(store, used_mids, used_tids, used_cids)
    # Closed is authoritative. The final report remains on the task, but a task the owner or agent
    # has closed is no longer work to walk through and must never be reintroduced into the funnel.
    # an agent mid-job: nothing to do here yet, whatever the mail or the idea says about the task - so it
    # rides at the TOP of the pipe as 'in hand', and drops to the front when the agent stops or asks
    busy = working_tids(store)
    from . import terminal as term
    # Keep the live session's identity on the working row. The message row used to change only its
    # key/lane, so the Assistant knew something was in hand but its card still had no sid, tail or
    # agent and rendered as "coding - nobody on it" after the coder was started from Tasks/Board.
    try:
        live_by_tid = {t['taskId']: t for t in term.live_sessions(tail=6) if t.get('taskId')}
    except Exception:
        live_by_tid = {}
    live_tids = busy | {i['tid'] for i in items if i['kind'] == 'agent' and i.get('tid')}   # working, parked or asking: an agent is on it
    stale_before = (now - timedelta(minutes=RUN_STALE_MIN)).strftime('%Y-%m-%d %H:%M:%S')
    # ...and a task whose STATUS says in_progress is in the middle of being worked, whether or not a
    # session is alive right now: the owner reads it that way ("it's in middle of working... it should
    # say working so it's not in funnel"), and it comes back to the front the moment the watcher moves
    # it to waiting or the agent asks (2026-09-03).
    # 'in_progress' means an agent is mid-job, and the owner reads it that way even between sessions
    # ("it's in middle of working... it should say working so it's not in funnel"). But nobody moves
    # the status back when a session DIES, so the status alone held a task in the working lane for
    # ever: TQ-0006 sat there with no session and "nothing for you", and the outage task fell out of
    # the pipe entirely (the 2026-09-03 break test). Mid-job is a live agent, or a task somebody has
    # touched in the last RUN_STALE_MIN; anything older is abandoned, and comes back to the owner.
    def mid_job(tid):
        t = store.get_task(tid) or {}
        if t.get('Status') != 'in_progress': return False
        return tid in live_tids or str(t.get('UpdatedAt') or t.get('CreatedAt') or '') >= stale_before
    def held(tid): return bool(tid) and (tid in busy or mid_job(tid))
    def in_hand(i): return i['kind'] not in ('agent', 'review', 'action') and (i.get('working') or held(i.get('tid')))
    # ...under the SAME key the parked agent will have (agent:<tid>), so shown-once and the page's live
    # row follow the task through stopping and starting instead of losing it at each change
    def held_item(i):
        if not in_hand(i): return i
        live = live_by_tid.get(i.get('tid')) or {}
        who = i.get('working') or live.get('agent') or live.get('label') or 'an agent'
        return i | {'key': f"agent:{i['tid']}" if i.get('tid') else i['key'], 'lane': 'working',
                    'why': f"{who} has it - nothing for you until it stops or asks",
                    'working': who, 'agent': live.get('agent') or who,
                    'sid': live.get('sid'), 'tail': live.get('tail') or [],
                    'mode': live.get('mode') or 'terminal'}
    items = [held_item(i) for i in items]
    # the wrap-up on a task an agent still holds is not a question yet either
    seen = set(); items = [i for i in items if not (i['key'] in seen or seen.add(i['key']))]
    hours, cap = knobs(store)
    items = [i for i in items if not _aged_out(i, now, hours)]
    items = _apply_states(items, states, now, keep_surfaced)
    # The wrap-up is merged HERE, once the pile is what the owner has left: a task whose message they
    # have already read (or that triage filed as fyi - "Thank you!") is a task nobody closed, and the
    # wrap-up is the one thing still on them. Merged before the read, the row they had just cleared
    # suppressed it and the task fell out of the pipe altogether (2026-09-03).
    wrapped = _apply_states(from_wrapped(store, now, busy), states, now, keep_surfaced)
    wrap_tids = {w['tid'] for w in wrapped}
    items = [i for i in items if not (i['lane'] == 'fyi' and i.get('tid') in wrap_tids)]
    held = {i['tid'] for i in items if i.get('tid')}
    items = _order(items + [w for w in wrapped if w['tid'] not in held])
    # the owner's standing rules: what they told us to stop showing them never enters again. Only the
    # lanes with nothing to do - a rule must not be able to hide something asking them for something.
    rules = mutes(store)
    quiet = [i for i in items if i['lane'] in MUTED_LANES and any(muted(r, i) for r in rules)] if rules else []
    if quiet:
        items = [i for i in items if i not in quiet]
        logger.debug(f'funnel: {len(quiet)} item(s) held back by your standing rules')
    # never more than the owner wants to look at: the rest waits its turn (and its arrivals still land)
    queue, shelf = [i for i in items if i['lane'] != 'working'], [i for i in items if i['lane'] == 'working']
    hidden = max(0, len(queue) - cap) if not keep_surfaced else 0
    if hidden: queue = queue[:cap]
    items = queue + shelf                                        # what an agent has rides above the cap, always visible
    rev = hashlib.sha1('|'.join(f"{i['key']}:{i['lane']}:{int(bool(i.get('settling')))}" for i in items).encode()).hexdigest()[:12] + f':{hidden}:{len(quiet)}'
    return {'rev': rev, 'items': items, 'hidden': hidden, 'muted': len(quiet),
            'rules': [str(r.get('why') or ' '.join(r.get('words') or []))[:120] for r in rules], 'lanes': [{'lane': l, 'word': LANE_WORDS[l][0], 'role': LANE_WORDS[l][1],
                                                                       'n': sum(1 for i in items if i['lane'] == l)} for l in LANES]}


def pile(store, force: bool = False) -> dict:
    """The pile, cached for a few seconds: it is polled while the page is open, and every look
    is a dozen queries."""
    seen_generation = _CACHE.get('generation', 0)
    with _LOCK:
        same_store = _CACHE.get('store') is store
        # One websocket event wakes every open browser. If they all arrive while the first forced
        # rebuild is running, that one result satisfies all of them; rebuilding once per tab is a
        # thundering herd that can hold every other API request behind this lock for a minute. A
        # cache from another Store is never interchangeable (tests and embedded callers can have
        # an in-memory store beside the application store).
        # Compare the cache generation we actually observed before waiting for the lock. Wall
        # clock comparison (`cache_at >= requested_at`) is not a generation check: Windows can
        # give two successive time.time() calls the same value, which made an immediate forced
        # refresh return the old agent/message state.
        refreshed_while_waiting = (same_store and force and _CACHE['pile']
                                   and _CACHE.get('generation', 0) != seen_generation)
        if same_store and _CACHE['pile'] and (refreshed_while_waiting or (not force and time.time() - _CACHE['at'] < PILE_EVERY)):
            return _CACHE['pile']
        events = announce(store)                       # the watcher speaks first: a transition changes the pile too
        p = build(store)
        p['alerts'] = alerts(store, p['items'])
        p['events'] = events
        _CACHE.update(at=time.time(), pile=p, store=store,
                      generation=_CACHE.get('generation', 0) + 1)
        return p


def invalidate(): _CACHE.update(at=0.0, pile=None, store=None); _SOURCES.update(at=0.0, by={})
def forget_states(): _STATE.clear(); _SEEN.clear(); _WATCHED[0] = False


def agent_states(store) -> dict:
    """Every task an agent has, or had: what it is doing now. {tid: (state, agent)}"""
    from . import terminal as term, waitroom
    out = {}
    try: live = term.live_sessions(tail=6)
    except Exception: live = []
    for t in live:
        tid = t.get('taskId')
        if not tid or (store.get_task(tid) or {}).get('SourceRef') == 'assistant:dock': continue
        waiting = t.get('waiting') if t.get('waiting') is not None else (t.get('idle') or 0) >= term.IDLE_WAITING
        tail = [str(x).strip() for x in (t.get('tail') or []) if str(x).strip()]
        out[tid] = (('asking' if waitroom.looks_like_question(tail) else 'parked') if waiting else 'working', t.get('agent') or t.get('label') or 'the agent')
    for r in store.running_runs():
        if r.get('TaskId') and r['TaskId'] not in out: out[r['TaskId']] = ('working', r.get('AgentName') or 'the agent')
    for tid in list(_STATE):
        if tid in out: continue
        t = store.get_task(tid) or {}
        out[tid] = (('done' if t.get('Status') in ('done', 'dropped') else 'idle'), _STATE[tid][1] if isinstance(_STATE[tid], tuple) else 'the agent')
    return out


def announce(store, actor: str = 'assistant') -> list:
    """The watcher's turn: what changed since the last look, said in the chat. An agent that starts
    working ('nothing for you, next'), stops and asks, or finishes. The first
    look only remembers - a restart must not narrate every session it finds. Returns the events."""
    now = agent_states(store)
    # On a quiet first look `now` and _STATE are both empty. Keying "first" on _STATE therefore
    # also suppressed the first agent that started later, which is precisely the transition the
    # open Assistant must announce. Remember that a look happened independently of its contents.
    first = not _WATCHED[0]
    _WATCHED[0] = True
    events = []
    at = time.time()
    for tid, (state, agent) in now.items():
        was = _STATE.get(tid, (None, agent))[0]
        # A change is not news until it has HELD for DWELL seconds: a CLI between two chunks of output
        # can read parked for a moment, and narrating that moment (and then its opposite) is the
        # "stopped - no, working" flapping the owner saw. 'done' is never held back: a task that closed
        # does not un-close, and the status line can clear any card that was on the table at once.
        held, since = _SEEN.get(tid, (None, at))          # never seen: this sighting starts its clock
        if held != state: _SEEN[tid] = (state, at); since = at
        if state != was and state != 'done' and at - since < DWELL: continue
        _STATE[tid] = (state, agent)
        if first or was == state or was is None and state in ('idle',): continue
        t = store.get_task(tid) or {}
        ref, title = task_ref(tid), _short(t.get('Title'), 80)
        if state == 'working' and was in (None, 'idle', 'parked', 'asking'):
            events.append({'tid': tid, 'ref': ref, 'kind': 'working', 'agent': agent,
                           'text': f"{agent} is working on {ref} ({title}) - nothing for you there now. Let's go to the next thing."})
        elif state in ('parked', 'asking') and was in ('working', 'idle', None):   # stopped - or found already parked
            events.append({'tid': tid, 'ref': ref, 'kind': state, 'agent': agent,
                           'text': f"{agent} {'asked you something' if state == 'asking' else 'stopped and is waiting on you'} on {ref} ({title})."})
        elif state == 'done' and was in ('working', 'parked', 'asking', 'idle'):
            summ = agent_found(store, tid)
            events.append({'tid': tid, 'ref': ref, 'kind': 'done', 'agent': agent, 'summary': summ,
                           'text': f"{agent} finished {ref} ({title})" + (f": {summ}" if summ else '.') + ' The task is closed.'})
    if state_dropped := [tid for tid in _STATE if _STATE[tid][0] == 'done']:
        for tid in state_dropped: _STATE.pop(tid, None), _SEEN.pop(tid, None)   # said once; a closed task is not watched again
    if events:
        from . import concierge
        for e in events:
            card = None
            if e['kind'] in ('parked', 'asking'):
                card = next((concierge.card_for(i) for i in build(store, keep_surfaced=True)['items'] if i['key'] == f"agent:{e['tid']}"), None)
            concierge.record(store, concierge.general.dock_task(store)[0]['TaskId'], 'assistant', e['text'], card)
            e['card'] = card
        invalidate()
    return events


MAIL_KINDS = ('review', 'action', 'asked', 'todo', 'fyi')
INTERRUPTS = ('agent', 'meeting')          # what a mail-only walk still stops for: they block work, or the clock
NOT_INCOMING = ('report', 'own', 'assistant')      # a scheduled report, a note to yourself, our own post


def came_in(i: dict) -> bool:
    """Something a PERSON sent, whatever lane it ended up in - mail, a chat line, the thread behind a
    slipped follow-up. "Start with the mail" used to key on the item's KIND, so the assistant's own
    line about a mail ('slipped') was not mail: the walk skipped the very row it had just marked NEXT,
    and the brief said "0 of them are mail" with five in the pipe (the owner, 2026-09-03)."""
    return bool(i.get('mid')) and (i.get('channel') or 'email') not in NOT_INCOMING
FYI_BATCH = 4                              # FYI has no action: the normal chat walk reads four together

def _not_yet(i: dict) -> bool:
    """On the timeline, but nothing to say about it YET - the walk skips it and comes back.

    A meeting enters the pipe two hours out (SOON_MIN) so the day is visible, and its lane is
    'time', which puts it at the very front of the walk. So the assistant opened with a meeting
    that was still an hour and a half away, ahead of mail that wanted answering now. It is the same
    shape as an agent that is mid-run: real, on the board, and not yours to do anything about until
    it stops (the owner, 2026-09-04: "meetings should not go down into the chat until 15 minutes
    before like a agent in middel of working"). alerts() already drew this line at ALERT_MIN; the
    walk did not.
    """
    return i['kind'] == 'meeting' and i.get('mins') is not None and i['mins'] > ALERT_MIN


def next_item(store, key: str = None, only: str = None, include_surfaced: bool = False,
              exclude: str = None) -> dict | None:
    """What comes out of the mouth: the named item (read or not - the chat may return to it), or
    the first unread one - of the mail alone when `only` is 'mail'. Something still being triaged is
    not ready to be talked about."""
    # by key, whatever its state: read already, or with an agent on it now - the concierge decides what to say
    if key: return next((i for i in build(store, keep_surfaced=True)['items'] if i['key'] == key), None) or batch_item(store, key)
    again = (datetime.now() - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
    ready = [i for i in pile(store, force=True)['items'] if not i.get('settling') and i['lane'] != 'working'
             and not _not_yet(i) and i.get('key') != exclude
             and (include_surfaced or not i.get('surfaced')
                  or (i['lane'] in ('blocked', 'approve') and _ts(i.get('surfaced_at')) <= again))]
    if only == 'mail': ready = [i for i in ready if came_in(i) or i['kind'] in INTERRUPTS]
    # New arrivals still lead.  Once those are exhausted, a merely-shown row is walked normally:
    # being put in the conversation never counted as the owner's decision, so it cannot make an
    # unread row unreachable.
    return next((i for i in ready if not i.get('surfaced')), ready[0] if ready else None)


def batch_item(store, key: str) -> dict | None:
    """The fyi batch as ONE item, so words said about it land on something. next_item could not
    resolve a `fyis:` key at all, so after a batch came out "next", "done" and "not ours" were dead
    until a button was clicked (the 2026-09-03 break test)."""
    if not key or not key.startswith('fyis:'): return None
    want = [k for k in key[5:].split(',') if k]
    have = {i['key']: i for i in build(store, keep_surfaced=True)['items']}
    got = [have[k] for k in want if k in have]
    if not got: return None
    return _item(key, 'fyis', 'fyi', f"{len(got)} fyi", who='', when=got[0].get('when'), since=got[0].get('since'),
                 channel=got[0].get('channel'), why='people told you things; nothing to do',
                 items=[dict(i) for i in got], members=[i['key'] for i in got])


def fyi_batch(store, first: dict) -> list:
    """The next few fyi's, the first included - what comes out together when the mouth reaches the fyi lane."""
    ready = [i for i in pile(store, force=True)['items'] if not i.get('settling') and not i.get('surfaced') and i['lane'] == 'fyi']
    return ([first] + [i for i in ready if i['key'] != first['key']])[:FYI_BATCH]


def item_for_key(store, key: str) -> dict | None:
    """An item for a Timeline row that is NOT on the pile - a newsletter, a filed note, anything the
    Recent list pulls into the chat by hand. The pile's own producers run on that one row with the
    quiet filter off; the concierge can then talk about it like anything else."""
    t = re.match(r'^task:(\d+)$', key or '')
    if t:
        tid = int(t.group(1))
        task = store.get_task(tid)
        if not task: return None
        # the task's own mail first - that row has the sender, the channel and the buttons
        row = next((r for r in store.feed(limit=500, days=FEED_DAYS) if r.get('TaskId') == tid), None)
        if row:
            got = from_feed(store, [row | {'Category': 'info' if row.get('Category') in _QUIET else row.get('Category')}])
            if got: return got[0] | {'lane': got[0]['lane'] if got[0]['lane'] != 'fyi' else 'asked'}
        return _item(f'task:{tid}', 'task', 'asked', task.get('Title'), when=task.get('UpdatedAt') or task.get('CreatedAt'), tid=tid,
                     summary=agent_found(store, tid), why=f"{task.get('Status')} {task.get('Kind')} task you asked about")
    m = re.match(r'^(msg|report):(\d+)$', key or '')
    if not m: return None
    mid = int(m.group(2))
    row = next((r for r in store.feed(limit=500, days=FEED_DAYS) if r['MessageId'] == mid), None)
    if not row: return None
    items = from_feed(store, [row | {'Category': 'info' if row.get('Category') in _QUIET else row.get('Category')}])
    it = next((i for i in items if i.get('mid') == mid), None)
    return it | {'lane': 'fyi', 'why': row.get('RouteReason') or it['why']} if it and it['kind'] == 'fyi' else it


VERBS = ('surfaced', 'done', 'later', 'skip', 'ack')

def settle(store, key: str, verb: str, by: str = 'owner', hours: float = None, note: str = None) -> dict:
    """The owner's word on one item. done: gone for good. later: back in `hours` (LATER_HOURS by
    default). skip: back tomorrow morning. surfaced: shown in this walk. ack: an alert was seen."""
    if verb not in VERBS: raise ValueError(f'unknown verb: {verb}')
    if key.startswith('fyis:'):                                   # a batch: the verb lands on every member
        out = [settle(store, k, verb, by, hours, note) for k in key[5:].split(',') if k]
        return {'key': key, 'verb': verb, 'until': (out[0] if out else {}).get('until')}
    until = None
    if verb == 'later': until = (datetime.now() + timedelta(hours=hours or LATER_HOURS)).strftime('%Y-%m-%d %H:%M:%S')
    if verb == 'skip':
        tomorrow = (datetime.now() + timedelta(days=1)).replace(hour=7, minute=0, second=0)
        until = tomorrow.strftime('%Y-%m-%d %H:%M:%S')
    store.set_funnel_state(key, verb, by, until, note)
    invalidate()
    return {'key': key, 'verb': verb, 'until': until}


def reset_walk(store):
    """A new chat. Read stays read - a mail you saw yesterday is not new again because the
    conversation is - but an alert put down in the old chat may speak once more in this one.

    An AGENT waiting on you is the exception to "read stays read": it is the one lane that blocks
    work, and having been shown it once in yesterday's chat is not an answer. A new chat surfaced
    two fyi about lunch while a coder sat parked on a question (the 2026-09-03 break test), because
    a blocked row must come back with the new chat."""
    store.clear_funnel_states(('ack',))
    for k, st in store.funnel_states().items():
        if k.startswith('agent:') and st.get('Status') == 'surfaced': store.clear_funnel_state(k)
    invalidate()


def alerts(store, items: list = None) -> list:
    """What interrupts the conversation, whatever it is on: a meeting inside fifteen minutes and an
    agent that just asked. Each once - acknowledged alerts stay quiet until the fact changes."""
    items = items if items is not None else build(store)['items']
    states = store.funnel_states()
    out = []
    for i in items:
        if i.get('surfaced'): continue                                 # already on, or past, the table
        if i['kind'] == 'meeting' and i.get('mins', 999) <= ALERT_MIN:
            when = 'is starting now' if i['mins'] <= 0 else f"starts in {i['mins']} min"
            out.append({'key': f"alert:{i['key']}", 'item': i['key'], 'kind': 'meeting', 'lane': i['lane'],
                        'text': f"{i['title']} {when}" + (f" with {i['who']}" if i.get('who') else '')})
        elif i['kind'] == 'agent':
            out.append({'key': f"alert:{i['key']}", 'item': i['key'], 'kind': 'agent', 'lane': i['lane'],
                        'text': (f"{i.get('agent') or 'an agent'} asked you something on {i.get('ref') or i['title']}" if i.get('asking')
                                 else f"{i.get('agent') or 'an agent'} stopped on {i.get('ref') or i['title']} and is waiting on you")})
        elif i['lane'] == 'asked' and i['kind'] in ('asked', 'todo') and i.get('who'):
            out.append({'key': f"alert:{i['key']}", 'item': i['key'], 'kind': 'asked', 'lane': 'asked', 'text': f"{i['who']} asked you: {i['title']}"})
        elif i['lane'] in ('time', 'approve') and i['kind'] != 'meeting':      # a meeting further out is not yet news
            # important things waiting: the page shows this only while the owner is on something lesser
            who = f"{i['who']}'s " if i.get('who') else ''
            what = ('reply is waiting for your yes' if i['kind'] == 'review' else 'proposed action is waiting for your yes' if i['kind'] == 'action'
                    else f"urgent: {i['title']}")
            out.append({'key': f"alert:{i['key']}", 'item': i['key'], 'kind': i['kind'], 'lane': i['lane'], 'text': f"{who}{what}"})
    return [a for a in out if (states.get(a['key']) or {}).get('Status') != 'ack']


def more_urgent(items: list, current_key: str = None) -> list:
    """What waits in a promoted lane while the owner is on something lesser - for the assistant to
    mention in a clause, and for the page to raise as a by-the-way."""
    cur = next((i for i in items if i['key'] == current_key), None)
    band = _BAND.get(cur['lane'], 3) if cur else 3
    return [i for i in items if not i.get('surfaced') and not i.get('settling') and _BAND.get(i['lane'], 3) < band and i['key'] != current_key]


def summary(items: list, coming: bool = True) -> str:
    """One line for the concierge's prompt: how much is left and of what. `coming` names the next
    few - left OUT when one item is on the table, so a small model cannot wander off to them."""
    if not items: return 'THE PIPE IS EMPTY - nothing else needs the owner right now.'
    parts = [f"{n} {LANE_WORDS[l][0]}" for l in LANES if (n := sum(1 for i in items if i['lane'] == l))]
    nxt = [i for i in items if not i.get('settling')][:3] if coming else []
    return (f"LEFT IN THE PIPE: {len(items)} - {', '.join(parts)}."
            + (' Coming next: ' + '; '.join(f"{i['who'] + ' - ' if i.get('who') else ''}{i['title']} ({LANE_WORDS[i['lane']][0]}{', shown already, still waiting' if i.get('surfaced') else ''})" for i in nxt) if nxt else ''))
