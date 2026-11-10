"""The shared displayed funnel and captured assistant selection.

Attention bands sort the rail into its sections: every task (owner input/approval, other actionable work, a task an agent is
working), results, FYIs. Urgent requests and imminent calendar events sit among the tasks, shaded, and Next takes them first.
Arrival orders each section, oldest first; stable keys break ties.
Presentation lanes remain available for their existing controls and status copy.

This ordering activation preserves the existing read, age, mute and capacity rules
until the separate canonical Unread/read-state cutover. All remains chronological.
"""
import contextlib, contextvars, hashlib, json, re, threading, time
from datetime import datetime, timedelta
from loguru import logger

from . import kinds as task_kinds
from .timewords import plural
from .store import task_ref, auto_code_enabled
from . import buttons, lanes
from .lanes import level_of, on_you, waits_on_you, SECTION_WORDS, MAIL_KINDS   # the rail's rules, where their readers find them
from .categories import agent_word
from .timewords import until_m
from .wrapup import REPORTS
from .assistant import _ts, _dt, _short, _cut, _gist, _agenda
from .autoreply import is_auto
from .funnel_presentation import present as _present, attach as _attach
from .processing_order import attention_band, gave_up, priority_rank
from .workerstate import says as agent_says, sub_state, request_line   # funnel.says is a message's subject

# ONE VOCABULARY, in taskuary/lanes.json - the words, roles and marks a lane wears, loaded here and
# imported by the desktop (website/src/funnelPile.js) from the same file. They were two hand-kept
# tables in two languages and had already drifted: this file said a report lane reads 'landed' while
# the page said 'report', and nothing could tell you which was the mistake (the owner, 2026-09-15:
# "we built one idea and then it was changed... it's in a bunch of places").
#
# ONE WORD PER AGENT STATE (the owner, 2026-09-25: "let's unify the vocab for agent status ... show
# it everywhere"): waiting to start, agent working, agent waiting on you, session saved, agent
# stopped, agent finished - each with one mark, on the rail, the Timeline, the task page and the phone.
_VOCAB = lanes.VOCAB
LANES = tuple(l['key'] for l in _VOCAB['lanes'])
LANE_WORDS = {l['key']: (l['word'], l['role']) for l in _VOCAB['lanes']}   # the word, and the theme role its dot takes
# ...and the form that COUNTS. "3 landed" is English; "3 report" is not - the only reason one lane
# ever carried two words. Everything else counts under the word it wears.
LANE_COUNTED = {l['key']: l.get('counted') or l['word'] for l in _VOCAB['lanes']}
# A chat cannot draw an icon, so it wears the emoji the desktop uses - the same entry, not a copy.
# A few KINDS outrank their lane: an agent's own finish is a task in a task lane, worded "agent finished", not "on you".
LANE_MARKS = {l['key']: l['mark'] for l in _VOCAB['lanes']}
KIND_MARKS = {k['key']: k['mark'] for k in _VOCAB['kinds']}
# ...and where it came from. The desktop paints a brand logo here; a chat gets one emoji per source,
# and a source we have no mark for gets NONE - an invented glyph says something untrue about it.
CHANNEL_MARKS = {'email': '📧', 'teams': '👥', 'slack': '💬', 'telegram': '✈️', 'whatsapp': '📱', 'imessage': '📱',
                 'discord': '🎮', 'mattermost': '💬', 'rocketchat': '🚀', 'matrix': '💬',
                 'google_chat': '💬', 'github': '🐙', 'gitlab': '🦊', 'jira': '🐞', 'sentry': '🚨', 'pagerduty': '📟',
                 'report': '📄', 'own': '📝', 'assistant': '✨', 'ai': '✨', 'idea': '💡', 'meeting': '📅',
                 'promise': '🤝', 'followup': '📨', 'prep': '📅', 'cold': '🥶'}


def owed_no_draft(item: dict) -> bool:
    """A reply owed with NO DRAFT YET (the owner, 2026-10-27): it rode the 'approve' lane and said "ready to send" with its flag on the
    rail, the header and the phone over a reply nothing had written. It reads "reply owed" until the draft lands (railStatus.owedNoDraft)."""
    return bool(item) and item.get('lane') == 'approve' and item.get('kind') == 'review' and item.get('draft') is False and not item.get('not_sent')


def lane_word(item: dict) -> str:
    """The word a row's state wears in a sentence: its lane's, or "reply owed" for a reply nothing has drafted yet - and a CHAT task's waiting
    move, any action, "agent ready for you" (build marks its row `chat`; the owner, 2026-11-05), on the phone and in the Assistant's words as
    on the rail. A coding task keeps its own."""
    it = item or {}
    if it.get('chat_done'): return lanes.word('chat_done')
    if it.get('chat') and it.get('lane') in CHAT_READY_LANES: return lanes.word('chat_ready')
    return lanes.word('owed') if owed_no_draft(item) else (LANE_WORDS.get(str(it.get('lane') or '')) or ('',))[0]


def mark_for(item: dict) -> str:
    """The one emoji that identifies a row: its kind's when that says more than its lane's."""
    if not item: return ''
    if owed_no_draft(item): return KIND_MARKS['owed']
    return KIND_MARKS.get(str(item.get('kind') or '')) or LANE_MARKS.get(str(item.get('lane') or ''), '')
SOON_MIN, ALERT_MIN, STARTED_MIN = 120, lanes.ALERT_MIN, 5   # calendar visibility window; attention boundary (lanes.json `urgent`); grace after the start
SETUP_GRACE_MIN = 15              # a walk-through the owner is still in does not raise its own hand
LATER_HOURS = 3                   # "not now" - it comes back this much later
FEED_DAYS = 7
# what two Settings knobs ship as (settings_defaults.json is written from them): how far back unread ordinary mail
# reaches (funnel_hours, read by the store) and the cap the rail once had (funnel_max, a retained value nothing applies).
HOURS_DEFAULT, MAX_DEFAULT = 12, 25
# A failed run is named by convention: reports.py sends '<title> - FAILED' (reports.run_report_source
# reads the same suffix back). Matching those words ANYWHERE in the subject called 'Process Error
# Check - 0 rows' a failure, because the report's own name contains 'Error' (the owner, 2026-09-03:
# "that's not a fail, it says all clear?" - and the assistant said Next).
_FAILED = re.compile(r'FAILED\s*$')                # reports.py writes '<title> - FAILED', and it shouts
# Triage's category is not a read receipt. An incoming newsletter, system notice, feed row, or
# Assistant post may be low-value, but it still enters the unread inventory; this small set remains
# only for converting a manually named historical row into a generic FYI card.
_QUIET = {'filed', 'ignored', 'yours', 'error'}   # error: triage failed - unread information with a retry, never work
PILE_EVERY = 30                   # websocket writes invalidate it; this is only a disconnected-client safety net
_CACHE = {'at': 0.0, 'pile': None, 'store': None, 'generation': 0, 'full': None, 'mark': None, 'workers': None}   # full: the build with read items kept; mark/workers: rail_top + live sessions at build
_STATE = {}                        # tid -> 'working' | a blocked sub-state | 'done' | 'idle', as last seen by the watcher
BLOCKED = ('parked', 'asking', 'approval', 'stalled')   # the sub-states of the blocked lane (workerstate.sub_state)
_SEEN = {}                         # tid -> (state, first seen at) - a change must HOLD before it is news
# the mails folded under each FYI row (its "+N"), as the rail last drew it - kept past invalidate(): every settle empties _CACHE, so a sweep
# that read rows one by one ("clear the FYI") found the thread under its first row only, and the rest came back as "+N" rows (TQ-1300)
_THREADS = {'store': None, 'by': {}}
_WATCHED = [False]                 # first LOOK, even when there were no sessions; _STATE empty is not the same thing
DWELL = 12.0                       # seconds a new state must survive before the watcher announces it
_REPORT_SUMMARY = re.compile(r'(?im)^summary:\s*(.+)$')
_LIVE_UNSET = object()
_LOCK = threading.Lock()
# THE RAIL LAST BUILT, kept past invalidate() (2026-11-09): every write empties _CACHE, and a press or the Advisor that found it empty waited
# behind the next build - Mark done 67 s, the Advisor 84 s, while a busy agent's writes and two tabs rebuilt it in turn. What only needs
# the rail as it stood (known) reads this, and never takes _LOCK. `began`: when the build behind it started (pile's convoy check).
_KNOWN = {'store': None, 'pile': None, 'full': None, 'began': 0.0}


MUTES_KEY = 'funnel_mutes'            # the owner's standing "never show me these again" rules
MUTED_LANES = ('fyi', 'report')     # only what has nothing to do: a real ask still reaches them; slipped is the owner's move (2026-10-12)


def mutes(store) -> list:
    """The owner's standing rules: [{'sender': <email or ''>, 'words': [...], 'why': '...'}]. Written
    when they sweep the pipe with a reason ("skip all the northwind financial reports, that is taken care
    of") - a sweep alone marked the ones in front of them read and the next batch walked straight back
    in (the owner, 2026-09-03: "was it one time dismiss not a memory")."""
    try: return json.loads(store.get_setting(MUTES_KEY) or '[]') or []
    except ValueError: return []


def like(words, hay: set) -> int:
    """How many of the owner's words this item carries. Prefixes count BOTH ways: they type
    "financials" about a "Financial Report" and "pvancer" about pvance@ (2026-09-03)."""
    long = [h for h in hay if len(h) >= 4]
    return sum(1 for w in words if w in hay or any(h.startswith(w) or (len(w) >= 4 and w.startswith(h)) for h in long))


def muted(rule: dict, i: dict) -> bool:
    from .routing import tokens
    key = str(rule.get('sender') or '').lower()
    if key and key not in (str(i.get('email') or '').lower(), str(i.get('who') or '').lower()): return False
    # a rule can name a LANE rather than words: "skip all the fyi from Erin" is every fyi she sends,
    # not the mails with 'fyi' in the subject (2026-09-03)
    if rule.get('lane'): return i.get('lane') == rule['lane'] and bool(key)
    words = [w for w in (rule.get('words') or []) if w]
    if not words: return bool(key)
    return like(words, set(tokens(f"{i.get('who') or ''} {i.get('email') or ''} {i.get('title') or ''}"))) >= min(2, len(words))


# Chat is not mail: WhatsApp and Slack send no subject at all, and Teams titles a chat after the
# people the row already names ("Teams chat with Gail Moreno"). Both left the pipe and the work
# list reading "(no subject)" next to a message you had to open to see (owner, 2026-09-07).
_CHAT_TITLE = re.compile(r'^((teams|slack|whatsapp|telegram) )?(group )?(chat|conversation) with\b', re.I)
PILL = 90                        # one line in a pill; the rest is an ellipsis, cut on a word


def says(r: dict) -> str:
    """What a row is ABOUT: triage's own title when it wrote one, else the subject, else the opening line."""
    # TRIAGE'S TITLE FIRST. It answers "what the work is, 12 words max" (triage.TASK_FIELDS) and is
    # already stored as the task's Title (ingest), but this read Subject BEFORE it - so a row whose
    # work triage had already named in a sentence went out wearing a mail header instead, and the
    # rail's one line was the least readable thing on the screen (the owner, 2026-09-16: a row
    # reading "rrdbreports@northwind.example - Northwind - PCC ..."). Only the agent rows ever preferred it.
    # the TASK's title first - it is the whole job, where a follow-up's own line is only the latest
    # thing said about it - then this message's own verdict line, for the rows that never became work
    title = _short(r.get('Title') or r.get('TriageTitle') or '', 140)
    if title and not _CHAT_TITLE.match(title): return title
    subj = _short(r.get('Subject') or '', 140)
    said = f"{r.get('FromName') or ''} in {r.get('SourceName') or ''}"
    if subj and subj != said and not _CHAT_TITLE.match(subj): return subj
    return _cut(_gist(r.get('Preview') or r.get('BodyText') or '', 240), PILL) or subj


CHAT_READY_LANES = ('blocked', 'approve')
def lane_index(lane: str) -> int: return LANES.index(lane) if lane in LANES else len(LANES)


def _item(key, kind, lane, title, *, who='', when='', since='', why='', mid=None, tid=None, rid=None,
          channel='', category='', preview='', **extra) -> dict:
    return {'key': key, 'kind': kind, 'lane': lane, 'title': _cut(title, 300) or '(no subject)', 'who': _short(who, 60),
            'when': _ts(when), 'since': _ts(since or when), 'sort_at': str(since or when or ''), 'why': _short(why, 220), 'mid': mid, 'tid': tid,
            'ref': task_ref(tid) if tid else None, 'rid': rid, 'channel': channel, 'category': category,
            'preview': _gist(preview, 240), **extra}


# ── the producers: each reads one thing the hub holds ─────────────────────────────────────────

CONN_LABELS = {'chatgpt': 'ChatGPT', 'outlook': 'Outlook', 'gmail': 'Gmail', 'imap': 'IMAP', 'teams': 'Teams', 'slack': 'Slack',
               'github': 'GitHub', 'gitlab': 'GitLab', 'whatsapp': 'WhatsApp', 'telegram': 'Telegram',
               'jira': 'Jira', 'sentry': 'Sentry', 'intacct': 'Intacct', 'quickbooks': 'QuickBooks'}


def _feed_skip(r: dict) -> bool:
    """Rows that are nobody asking anything: our own sends, withdrawn lines, an auto-reply, and
    anything on a task that is over (unless a draft on it still waits for a yes)."""
    if r.get('Direction') == 'out' or r.get('MsgStatus') in ('withdrawn', 'ignored'): return True
    if r.get('TaskStatus') in ('done', 'dropped') and r.get('ReviewStatus') != 'pending': return True
    return is_auto(r)                 # the mail system's mark (autoreply.py), never the subject


def _said_at(stamp) -> str:
    "'today at 09:33', or 'on 2026-10-20 at 18:00'."
    s = str(stamp or '')
    return ('today' if s[:10] == datetime.now().strftime('%Y-%m-%d') else f'on {s[:10]}') + f' at {s[11:16]}'


def closed_why(r: dict) -> str:
    "What happened to a closed task's mail, from the facts: 'handled - you replied today at 09:33; closed', or 'closed'."
    replied = f"you replied {_said_at(r['AnsweredAt'])}; " if r.get('AnsweredAt') else ''
    return ('handled - ' if r.get('TaskStatus') == 'done' else '') + replied + ('closed' if r.get('TaskStatus') == 'done' else 'dropped, closed')


def _assistant_wrapper(r: dict) -> bool:
    """True for an Assistant message that is only a VEHICLE for an idea shown in its own right.

    Plain Assistant messages are real unread arrivals. Two kinds are not:

    - a generated digest post, which is a container for the ``ideas`` in its Brief;
    - the message an idea is carried into triage on (assistant._idea_message writes one per idea,
      external id ``idea:<n>``, so the verdict has a message to hang off).

    Showing either beside the idea it belongs to is the duplicate-Assistant regression of
    2026-09-04, and the second kind was still doing it on both roads (the owner, 2026-09-07: "still
    duplicating this in timeline??" - one thought, two rows, the vehicle saying nothing when opened).
    """
    if r.get('Channel') != 'assistant': return False
    if re.fullmatch(r'idea:\d+', str(r.get('ExternalId') or '')): return True
    if not r.get('Brief'): return False
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


def _preview(store, r: dict):
    """A row's line of words - and a mail with none says what came with it ("Attached: October.xlsx"), never an empty line on its card
    (the owner, 2026-11-03: a picture-only mail "showed nothing"). Asked only of a wordless row, so a day of mail costs no extra read."""
    if str(r.get('Preview') or '').strip() or not r.get('MessageId'): return r.get('Preview')
    try: names = [a['Name'] for a in store.list_attachments(r['MessageId']) if a.get('Name')]
    except Exception: names = []
    return f"Attached: {', '.join(names[:3])}{f' and {len(names) - 3} more' if len(names) > 3 else ''}" if names else r.get('Preview')


def from_feed(store, rows: list, *, canonical=False) -> list:
    out, agents, reviews, threads = [], set(), set(), {}
    speaks, more = thread_speaker(rows), {}
    for r in rows:
        if not canonical and _feed_skip(r): continue
        # Generated Assistant reports carry durable ideas. Those ideas are produced below as the
        # actionable unread cards, one latest copy per idea; admitting the wrapper as a second FYI
        # is what made the same Assistant line appear over and over. A plain Assistant message with
        # no idea payload is still an ordinary unread arrival.
        if not canonical and _assistant_wrapper(r): continue
        # ONE line per triaged task. Before triage makes a task, the conversation is the boundary.
        # This lets seven messages combined onto TQ-0367 come out as one task with +7, without also
        # swallowing every other job discussed later in the same WhatsApp room.
        cid = r.get('ConversationId')
        group = _feed_group(r)
        if not canonical and group and speaks.get(group) != r['MessageId']:
            more[group] = more.get(group, 0) + 1
            continue
        who = r.get('FromName') or r.get('FromEmail') or r.get('SourceName') or r.get('Channel') or ''
        # ...and the two fields the ROAD is read from, so the rail's pill can say what triage said
        # rather than what is waiting now - the same rule the Timeline row and its Triage tab use
        # (timelineState.roadOf; the owner, 2026-09-07: "once the ai decides it should show what the
        # ai decided. Same in work and timeline tabs")
        base = dict(who=who, when=r.get('SentAt'), mid=r['MessageId'], tid=r.get('TaskId'), channel=r.get('Channel') or '',
                    category=r.get('Category') or '', preview=_preview(store, r), cid=cid, email=r.get('FromEmail') or '',
                    priority=r.get('Priority'), route=r.get('RouteReason') or '', task_kind=r.get('TaskKind') or '',
                    # the mail's own subject beside triage's title, and the danger triage read in it (message.Danger) - shown, never a gate
                    subject=_short(r.get('Subject') or '', 140), danger=_short(r.get('Danger') or '', 200) or None,
                    # ...and whom it is aimed at, the owner or the agent: a scam on the owner is said as one (the owner, 2026-10-30)
                    danger_aim=(r.get('DangerAim') or 'agent') if r.get('Danger') else None)
        subj = says(r)
        if r.get('MsgStatus') == 'triaging':
            # A RANKED ARRIVAL WAITING ITS TURN IS NOT BEING TRIAGED (the owner, 2026-09-28: "they should be ranked
            # and not triaged"): it is off the rail, counted by the "N more" pill on its input's last row
            from .rank import mode_for
            waits = mode_for(store, {'Channel': r.get('Channel'), 'SourceName': r.get('SourceName')}) == 'rank'
            out.append(_item(f"msg:{r['MessageId']}", 'triaging', 'fyi', subj, why='just arrived - triage is deciding', settling=True,
                             ranked_wait=waits, **base))
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
            latest = None if canonical else (store.last_inbound_on_task(r.get('TaskId')) if r.get('TaskId') else
                      store.last_inbound_in(cid) if cid else None)
            stale = bool(latest and latest.get('MessageId') != rv.get('MessageId'))
            if latest:
                base.update(mid=latest.get('MessageId'), when=latest.get('SentAt'),
                            who=latest.get('FromName') or latest.get('FromEmail') or who,
                            preview=latest.get('BodyText') or base.get('preview'),
                            channel=latest.get('Channel') or base.get('channel'))
                subj = says(latest) or subj
            out.append(_item(f"review:{r['ReviewId']}", 'action' if action else 'review', 'approve', subj, rid=r['ReviewId'],
                             why='an agent proposed an action - it runs only if you say so' if action
                                 else ('a reply is drafted for you to send' if r.get('HasDraft') else 'a reply is owed - draft it with AI or write it'),
                             draft=bool(r.get('HasDraft')), summary=agent_found(store, r.get('TaskId')),
                             stale=stale,
                             sig=hashlib.sha1(str(rv.get('DraftText') or '').encode()).hexdigest()[:10],   # the draft's fingerprint: a rewrite is news
                             **base))
            # A SEND THE SERVER REFUSED IS NOT READY TO SEND: the row said "ready to send" in green over a reply the mail server
            # had turned away, its reason a grey line on the card (the UI audit, 2026-10-21) - it says not sent, and why
            if not action and rv.get('DeliveryState') == 'failed':
                out[-1].update(not_sent=True, why=re.sub(r'^Not sent:\s*', '', str(rv.get('Reason') or '')).rstrip('.') or 'the send was refused')
            from . import proposals
            co = proposals.CLOSEOUT.get(proposals._action(rv)) if action else None
            if not action and r.get('TaskId'):         # a reply whose task also waits on its merge: Close out runs both
                other = proposals.closeout_pending(store, r['TaskId'])
                if other: out[-1].update(closeout=proposals.CLOSEOUT.get(proposals._action(other)), rides=True)
            if co: out[-1].update(closeout=co, why=f"the agent finished - {buttons.label('approve', 'action')} {co}",
                                  rides=bool(store._one("SELECT 1 x FROM review WHERE TaskId=? AND Status='pending' AND Kind<>'action'", (r.get('TaskId'),))))
            if group: threads[group] = out[-1]                 # the draft speaks for its task/thread
            continue
        if r.get('AgentWaiting') and r.get('TaskId'):
            if r['TaskId'] in agents: continue
            agents.add(r['TaskId'])
            out.append(_item(f"agent:{r['TaskId']}", 'agent', 'blocked', r.get('Title') or subj, agent=r.get('Working') or 'agent',
                             why=agent_says('parked'), **base))
            if group: threads[group] = out[-1]
            continue
        base['working'] = r.get('Working') or ''             # an agent has it: build() lets these go, by name
        if r.get('Channel') == 'report':
            # a run whose own first line says it could not summarise (no AI connector) is on the
            # Timeline and nowhere else - three of them came out of the pipe, one per turn, on a
            # fresh install's first day (the 2026-09-03 break test)
            from .reports import NO_BRAIN
            if not canonical and NO_BRAIN in str(r.get('Preview') or ''): continue
            sid = report_source_id(store, r.get('SourceName'))
            bad = r['ReportFailed'] if 'ReportFailed' in r else report_failed(store, subj, r.get('MessageId'))
            # ...and a run the owner asked to be TOLD about is not news, it is work. When a report
            # carries a "move it up if" sentence, triage judges the run against it and makes a task
            # of a match (triage.classify_intent's `watch`) - but this branch filed every report row
            # in the report lane regardless, so the promotion the owner had asked for stopped one
            # step short of the pipe (2026-09-04). A matched run falls through and ranks as the work
            # it now is; an ordinary run and a failure keep their own lanes.
            if not bad and r.get('TaskId') and (r.get('NeedsYou') or r.get('Category') in ('coding', 'todo', 'action')):
                base['source_id'] = sid
            else:
                ran = _activity_time(base.get('since') or base.get('when'))
                brief = not bad and is_digest_source(store, sid) and ran is not None and ran.date() == datetime.now().date()
                # a DASHBOARD's row opens the dashboard over the canvas (dashboards.py), and wears its own mark on the rail
                dash = {'dashboard': True} if sid in _SOURCES.get('dash', ()) else {}
                out.append(_item(f"report:{r['MessageId']}", 'report', 'broken' if bad else 'report', subj, bad=bad, source_id=sid,
                                 brief_today=brief, **dash,
                                 why='your brief for today - what is going on, and what is pressing' if brief
                                     else ('the check failed - the cause is in it' if bad else 'a report you set up landed'), **base))
                if group and threads.get(group) is None: threads[group] = out[-1]
                continue
        cat = r.get('Category') or ''
        # A triage category is not a read receipt.  Filed/ignored/automated/promotional rows are
        # still incoming rows; the owner's explicit funnel state is what later removes them.
        if not canonical and (r.get('TheirTurn') or r.get('AnsweredAt')): continue
        urgent = priority_rank(r.get('Priority')) == 0
        # A REPLY IS NOT THE WORK. NeedsYou is zeroed once the owner has answered the thread or the
        # ball is in the sender's court (store.NEEDS_YOU) - true of a message waiting on a reply, and
        # false of an open task with work still in it. TQ-0588 was an open coding task assigned to
        # the coding agent with nothing ticked off, and it left the rail completely the moment the owner
        # replied to the mail that started it: not in your task, not in agents working, filed into
        # fyi behind seventy rows (the owner, 2026-09-16: "2 tasks on in progress ... only showing
        # one"). Real work standing open is its own reason to be on the rail.
        open_work = (r.get('TaskStatus') not in ('done', 'dropped')
                     and str(r.get('TaskKind') or '') in task_kinds.TRIAGE)
        # WHOSE it is decides the word. Work triage handed to an agent that has not run is QUEUED -
        # waiting to start; work with nobody on it is the owner's own, and its kind ('todo') carries
        # the word for that. Both used to say "asked you", which claimed a person had asked for
        # something on rows triage derived from a report (the owner, 2026-09-16: "i don't like this
        # asked you, it's queued, working on it, or agent waiting on you").
        def _work(open_only=False, why=''):
            handed = str((store.get_task(r['TaskId']) or {}).get('Assignee') or '').startswith('agent:')
            lane = 'time' if urgent else ('queued' if handed and not r.get('Working') else 'yours')
            # open_only: the row is here for the open task alone (its own line was a thank-you, an
            # fyi) - build() lets the wrap-up outrank exactly these, and never a line triage kept as work
            out.append(_item(f"msg:{r['MessageId']}", 'todo', lane, subj, coding=cat == 'coding', open_only=open_only,
                             why=('urgent - ' if urgent else '') + (why or r.get('RouteReason') or ('a coding task with no agent on it' if cat == 'coding' else 'real work with nobody on it')), **base))
            if group and threads.get(group) is None: threads[group] = out[-1]
        if cat in ('coding', 'todo') and (r.get('NeedsYou') or r.get('Working') or open_work):   # a worked row is kept, tagged, and let go in build()
            _work(); continue
        # ...and a REPORT RUN that became a task - the owner's Put it on my list, a watch match, Reopen task on one - is that work: no person
        # wrote it, so it never "asked you". It fell to the asked lane, drew 🙋 asked you and lit Reply over a report (2026-10-26)
        if r.get('Channel') == 'report' and r.get('TaskId'):
            _work(why='' if r.get('RouteReason') else 'your own work from a report'); continue
        # ANSWERED IS NOT ASKED (the owner, 2026-10-18: "sending and closing are two steps"): a reply sent leaves its task open, and
        # the thread behind it said "asked you" over an answer that had gone - the task stands as itself, on you, for its Mark done
        if r.get('TaskId') and r.get('TaskStatus') not in ('done', 'dropped') and (r.get('TheirTurn') or r.get('AnsweredAt')) \
                and not r.get('NeedsYou'):
            _work(open_only=True, why='you answered - the task is still open'); continue
        if cat == 'review' or (r.get('NeedsYou') and cat not in ('info',)):
            out.append(_item(f"msg:{r['MessageId']}", 'asked', 'time' if urgent else 'asked', subj,
                             why=r.get('RouteReason') or 'a person asked you for something', **base))
            if group and threads.get(group) is None: threads[group] = out[-1]
            continue
        # Anything incoming which reached the Timeline and was not handled above is unread
        # information.  Triage may label it automated/promo/feed/filed/assistant, but classifying
        # it is not the same as the owner reading it.
        # ...except a row NOTHING judged. It reached no verdict, so it cannot wear the word for
        # "somebody told you something; nothing to do" - which is the exact face the error state was
        # added to keep it out of (ingest, PW-036). Same quiet band, honest word, and the Retry is
        # one tap in (the owner, 2026-09-15: "were they put to fyi even with a error? that's a bad bug").
        # ...and once the retry has GIVEN UP on it, the quiet band is where it would be lost: `held` lifts it to your
        # task (_band), the lane and its Retry stay (processing_order.gave_up)
        if cat == 'error':
            out.append(_item(f"msg:{r['MessageId']}", 'fyi', 'unjudged', subj, held=gave_up(r),
                             why=r.get('RouteReason') or 'triage could not classify this - nothing was started', **base))
            if group and threads.get(group) is None: threads[group] = out[-1]
            continue
        # ...AND THE LAST MESSAGE DOES NOT GET A VOTE ON AN OPEN TASK. Everything above judged the row
        # by its own line, and a chain whose newest line was a thank-you ("thanks", triaged fyi) fell
        # through to fyi with its task still open - TQ-0626 sat there a day (the owner, 2026-09-18).
        # What the newest message was about is not what the task is: the open task is the row.
        if open_work and r.get('TaskId'):
            _work(open_only=True); continue
        # ...AND A CLOSED TASK'S MAIL IS NOT FYI. Opened again, it wore the fyi face - "I read it as just for your information -
        # attached: same conversation thread" - over mail triage had judged work, that reopened the task and was answered.
        # A closed task says what happened to it: handled, when you replied, closed.
        if r.get('TaskId') and r.get('TaskStatus') in ('done', 'dropped'):
            out.append(_item(f"msg:{r['MessageId']}", 'fyi', 'fyi', subj, closed=True, why=closed_why(r), **base))
            if group and threads.get(group) is None: threads[group] = out[-1]
            continue
        # ...and a list's way off it, still unpressed (store.feed `Unsub`): the card's Unsubscribe (unsubscribe.py)
        out.append(_item(f"msg:{r['MessageId']}", 'fyi', 'fyi', subj, why=r.get('RouteReason') or 'a person told you something; nothing to do',
                         **({'unsub': r['Unsub']} if r.get('Unsub') else {}), **base))
        if group and out and threads.get(group) is None: threads[group] = out[-1]
    # ONE brief leads the day. `brief_today` is true of every digest run made today, and the digest
    # ran twice on 2026-09-14 - so two identical "Morning digest" rows sat at the top of the work
    # rail, both promoted out of the report band ("we should only have the latest one. The other one
    # should be in the timeline report"). A later run REPLACES the earlier one: it summarises the
    # same day from further along it. The one it replaced is the ordinary landed report it always
    # was - still on the Timeline, no longer leading the day.
    if len(briefs := [i for i in out if i.get('brief_today')]) > 1:
        stamp = lambda i: _activity_time(i.get('sort_at') or i.get('since') or i.get('when')) or datetime.min
        for i in sorted(briefs, key=stamp)[:-1]:
            i['brief_today'] = False
            i['why'] = 'a later brief has replaced this one - the day is summarised above'
    for group, n in more.items():                 # the rest of each task/thread, counted on the row that speaks for it
        held = threads.get(group)
        if held is not None: held['more'] = held.get('more', 0) + n
    return out


_SOURCES = {'at': 0.0, 'by': {}, 'digest': set(), 'dash': set()}
def report_source_id(store, name: str) -> int | None:
    """The report source behind a report message (its SourceName is the report's title) - cached a minute."""
    if time.time() - _SOURCES['at'] > 60:
        by, digest, dash = {}, set(), set()
        for src in store.list_sources(active_only=False):
            if src.get('Channel') != 'report': continue
            try: cfg = json.loads(src.get('ConfigJson') or '{}')
            except ValueError: cfg = {}
            title = cfg.get('title')
            # the SAME test reports.py uses to decide a run is the digest, so a renamed report is
            # still the brief and a report merely CALLED "digest" is not
            if 'digest' in {cfg.get('type'), *(s.get('type') for s in cfg.get('sources') or [])}:
                digest.add(src['SourceId'])
            if cfg.get('type') == 'dashboard': dash.add(src['SourceId'])
            for k in (src.get('Address'), title):
                if k: by[str(k)] = src['SourceId']
        _SOURCES.update(at=time.time(), by=by, digest=digest, dash=dash)
    return _SOURCES['by'].get(str(name or ''))


def is_digest_source(store, sid) -> bool:
    """Is this report source the Morning digest? Read from its CONFIGURATION, never its title - the
    owner may rename it, and matching the word would also catch a report that is merely about digests."""
    if not sid: return False
    report_source_id(store, '')                     # warms the same one-minute cache
    return sid in _SOURCES['digest']


def todays_brief(item: dict) -> bool:
    """TODAY's morning digest - the one row that leads the work rail (the owner, 2026-09-10: "just
    surface the morning digest report to the top of the work and then we are good"). Yesterday's is an
    ordinary landed report: a stale brief sitting at the top of the day is worse than no brief at all."""
    return bool(item.get('brief_today'))


# the clause triage writes on a route whose start waits for the owner (ingest.HELD), and the words it used before
AUTO_OFF, AUTO_OFF_OLD = 'held for you:', 'not auto-worked:'
def held_clause(reason) -> str | None:
    "The sentence after a route's hold clause, in either wording - None when the route held nothing."
    r = str(reason or '')
    k = next((k for k in (AUTO_OFF, AUTO_OFF_OLD) if k in r), None)
    return r.split(k, 1)[1].strip() if k else None
# A START THAT ASKED "WHICH REPOSITORY?" (the owner, 2026-10-12: "if i don't fill it out it should warn me at least?"): the
# answer was a line on a sheet that closed at once, and the task said "nobody on it" as if nothing had been asked for
HELD_REPO = 'held:repo'
# ...and how a start's refusal says it: the checkout guard's own sentences (terminal.open_session), read by every door that starts one. Only a
# repository somebody NAMED and nobody can find is asked about now - one nothing placed opens in its task's folder and the agent picks (repochoice)
NEEDS_REPO = re.compile(r'no local path|does not exist', re.I)

def held_for_repo(t) -> bool: return HELD_REPO in re.split(r'[\s,]+', str((t or {}).get('Tags') or ''))

def hold_for_repo(store, tid, reason=''):
    "The start stopped on a repository nobody named: the task says so until a repo is set or a session opens."
    if store.tag_task(tid, HELD_REPO, True, 'router'):
        store.add_comment(tid, 'router', 'agent', 'Waiting for you: it needs a repository. '
                          + (' '.join(str(reason).split())[:200] + ' ' if reason else '') + 'Pick one on the task and the coding agent starts.')


def news_since_agent(store, tid) -> dict | None:
    "The message somebody sent AFTER the agent's last session ended - what an open task is about now - or None (taskstate.TaskState.news)."
    from . import taskstate
    return taskstate.task_state(store, tid=tid).news


def news_line(store, tid, m=None) -> str:
    m = m or news_since_agent(store, tid) or {}
    if not m: return ''
    who = agent_word((store.get_task(tid) or {}).get('Kind'))
    frm = str(m.get('FromName') or m.get('FromEmail') or 'Someone').split(' at ')[0]
    when = str(m.get('SentAt') or '')
    day = 'today' if when[:10] == datetime.now().strftime('%Y-%m-%d') else when[:10]
    # THE STATE, never a move: a sentence that names a button names one the item shows (2026-10-17), and this one is read on the task
    # page, the rail and the walk alike - each says its own buttons (concierge._from_you)
    # ...and no "its record is below": the desk keeps that record in the Agent section beside Came from, not under it (the state matrix, 2026-10-28)
    return f"{frm} wrote again {day} at {when[11:16]}, after {who} last worked on it."


def _cap(x: str) -> str: return x[:1].upper() + x[1:]

def _sentence(x: str) -> str:
    "A reason written before its words were sentences ('first message from x') read as one; a sentence is left alone."
    x = ' '.join(str(x or '').split())
    return x if not x or x.endswith(('.', '!', '?')) else _cap(x.rstrip(' -;,')) + '.'


def run_failed(store, tid, live_too: bool = False, st=None) -> dict | None:
    """{sentence, fix} when the task's last run ended FAILED by its own word (workerstate.ended), nothing live on it: the reason in
    plain words (failures.classify) and the place that fixes it - Connect an AI for an agent with no AI to run on - else None.
    `st`: the task's record (taskstate.TaskState), when the caller holds it - its ending is read there."""
    from . import workerstate
    from .failures import classify
    # live_too: whatever the session does (R2)
    if (workerstate.ended(store, tid, live_too) if st is None or live_too else st.end) != 'failed': return None
    last = (st.last(('failed',)) if st else store.last_worker_event(tid, kinds=('failed',))) or {}
    c = classify(' '.join(str(last.get('Text') or '').split()) or 'it stopped without saying why', tid=tid)
    return {'sentence': _sentence(c['sentence']), 'fix': c['fix']}


def timed_out(store, tid, st=None) -> str:
    "The run's own sentence when its last word is a turn that ran out of time (general.TIMED_OUT), nothing live on it - else ''."
    from . import general, workerstate
    last = st.last(skip=workerstate.NOTES) if st else store.last_worker_event(tid, skip=workerstate.NOTES)
    ok = (last and last['Kind'] == 'stopped' and last.get('Source') == general.TIMED_OUT
          and (workerstate.ended(store, tid) if st is None else st.end) == 'stopped')
    return str(last.get('Text') or '') if ok else ''


def idle_state(store, tid, st=None) -> dict:
    """Why nothing is running on a task that was handed to an agent and never began: {'kind', 'line', 'row'}.

    "waiting to start" says the state and not the cause, so the owner reads it as a queue that will
    clear itself - and it will not: every reason below needs them (the owner, 2026-09-14: "if the
    agent did not start, tell the user why it did not start, or left over from yesterday").

    `line` is the task page's whole sentence, led by its state - "Waiting for you.", "Couldn't start.", "Waiting its
    turn." - and `row` the rail's few words for the same fact. The agent is named by what it IS, the assistant or the
    coding agent: "coder could not start: unknown agent: coder" named a profile as the actor and blamed it for its own
    absence (the owner, 2026-10-16). `kind`: news | saved | interrupted | held | failed | retrying | queued | left | idle.

    Structured facts first, our own written sentence last. The `interrupted` tag is the strongest -
    terminal.release_task writes it when Taskuary itself closed on top of a live worker (PW-262),
    and nothing restarts by itself. Then a run that really ran and stopped. Then triage's own words
    about why it declined to start (the first-time-sender gate writes them, and a no-reply address
    will never clear it). `line` is '' when the task is not actually idle - the caller decides who asks.

    `st`: the task's record (taskstate.TaskState), when the caller holds one. The facts are its own - this words them, in this order.
    """
    from . import taskstate
    from .blackboard import is_permanent, failed_line
    st = st or taskstate.task_state(store, tid=tid)
    t = st.t
    agent = agent_word(t.get('Kind'))
    old = ' It has been waiting since yesterday.' if str(t.get('CreatedAt') or '')[:10] < datetime.now().strftime('%Y-%m-%d') else ''
    out = lambda kind, line, row='': {'kind': kind, 'line': line, 'row': row}
    if st.news: return out('news', news_line(store, tid, st.news))
    # ...and a run that RAN OUT OF TIME says so in its own words, whatever mark the task wears: "You stopped it" stood over a turn killed at
    # its limit, the owner having stopped nothing (2026-11-04) - it paused, and Continue picks it up (general.TIMED_OUT)
    if (to := timed_out(store, tid, st)): return out('left', to, 'cut off by a time limit - continue it')
    if st.saved: return out('saved', 'You stopped it and its report is written.')     # the moves are the item's own buttons (news_line)
    if st.interrupted:
        return out('interrupted', f'Taskuary closed while {agent} had this, so its work stopped there. Nothing restarts by itself.' + old)
    if held_for_repo(t):
        # plain words: "repository" is on the jargon list (words.json) - the row's own Choose where the code is answers it
        # ...and a run that found the work is in other code asked to move it (wrapup.asks_to_move): it did start, so it never says "before it can start"
        if st.transcript:
            return out('held', f'Waiting for you. {agent[:1].upper() + agent[1:]} found the work is not in this code and asks where to move it - '
                               'change where the code is and it starts there.', 'asks to move - where is the code?')
        return out('held', f'Waiting for you. It needs to know where the code is before {agent} can start.' + old, 'not started - it needs to know where the code is')
    # THE QUEUE SAYS WHY (A3, 2026-09-25): a full house, a start that keeps failing and a CLI that is not installed all
    # read "nothing has started it" - only the Tasks list showed the queue
    q = store.get_dispatch(tid) or {}
    if q:
        err = ' '.join(str(q.get('LastError') or '').split()).rstrip('.')[:160]
        short = err.split(': ', 1)[0] if len(err) > 60 else err
        if q.get('State') == 'failed':
            return out('failed', failed_line(err or 'the start failed', is_permanent(err), int(q.get('Attempts') or 0)) + old,
                       f"couldn't start: {short or 'the start failed'}")
        if q.get('State') == 'retrying':
            at = str(q.get('NextAt') or '')[11:16]
            return out('retrying', f"Couldn't start yet ({err or 'no reason given'}) - trying again {f'at {at}' if at else 'shortly'}." + old,
                       f"couldn't start yet - trying again {f'at {at}' if at else 'shortly'}")
        # a ranked wait is not a full house: it waits for its turn in value order, with free slots or not (rank.py)
        if q.get('Value') is not None:
            return out('queued', 'Waiting its turn. Waiting work starts most valuable first, and this starts when it comes up.' + old,
                       'queued - waiting its turn')
        return out('queued', f'Waiting its turn. Every agent slot is busy, and {agent} starts on this when one frees up.' + old,
                   'queued - starts when a slot frees')
    # A RUN THAT FAILED SAYS SO, with its reason in plain words (owner-approved, 2026-10-21): it read "Not started yet. Nothing has
    # started the assistant on this." under a chip saying stopped, while the run's own last word was why it failed
    if (f := st.failed): return out('failed', f"Failed - {f['sentence']}", f"failed - {f['sentence'][:1].lower()}{f['sentence'][1:]}")
    if any(r.get('Status') in ('stopped', 'failed', 'error') for r in st.runs):
        return out('left', f'{_cap(agent)} ran on this and stopped without finishing it.' + old)
    # ...and a pty worker leaves NO run row at all - it writes a transcript on the way out, which is
    # the very thing the task card reads to offer "Continue previous work". Only runs were consulted
    # here, so two tasks an agent had actually worked and walked away from reported "it was handed to
    # an agent and nothing has started it" for six hours (TQ-0588/0589, 2026-09-16: transcripts from
    # copilot and from the coding profile, no run rows, no live session). A transcript IS proof that it ran.
    # ...but a session that FINISHED did not leave anything: it said it was done and wrote its report, and the task came
    # back only because somebody wrote again (TQ-1040, 2026-10-12: an agent closed its task, the reply went out, the sender
    # answered, and the step said the agent "left without finishing" over its own finished record)
    # ...and nothing came in since, or news_since_agent would have said so above: "Nothing has started on what came in since" was
    # said over a batch whose session closed with nothing new on it at all (TQ-1112 shape) - the task is simply still open
    if st.finished:
        return out('left', f'{_cap(agent)} finished its work - its record is below. The task is still open.' + old)
    if st.transcript:
        return out('left', f'{_cap(agent)} ran on this and left without finishing it.' + old)
    msg, lifted = st.inbound, False
    for r in reversed(store.message_routes(msg.get('MessageId')) or []) if msg.get('MessageId') else []:
        said = held_clause(r.get('Reason'))
        if said is None: continue
        # the old words read as a queue that clears by itself; a GitHub hold now says who wrote it and whom the repo trusts
        if said.startswith('github items queue') and str(msg.get('Channel') or '') == 'github':
            from .ingest import gh_hold_why
            said = gh_hold_why(store, {'source_name': msg.get('SourceName'), 'body': msg.get('BodyText')})
        # the route kept the sender rule's words from when it arrived; a sender trusted SINCE (a Teams colleague resolved after
        # the fact, channels.teams_org) is no hold any more - the task just waits for its normal start, and origin.of_task drops
        # the stale hold tag. It is not started for them: what was held when it came in stays the owner's to start.
        # ...and so is one the owner vouched for on this very task (Trust them, the Trust buttons below): a mail sender's say-so is the
        # task's TrustedThrough, not a remembered person, and the box went on asking for the press it had just had
        if str(msg.get('Channel') or '') != 'github' and 'no agent starts on' in said:
            from . import origin
            if msg['MessageId'] <= int(t.get('TrustedThrough') or 0) or origin.of_message(store, msg)[0] == 'trusted':
                origin.of_task(store, tid); lifted = True; continue
            # THE HOLD OFFERS ITS WAY OUT (the owner, 2026-10-26: "we should have button on untrusted user to either trust user or trust
            # domain and then we won't have issue again"): the box that says why nothing started carries the two presses, worded for
            # the channel (senders.trust_offer)
            from .senders import trust_offer
            return {**out('held', f'Waiting for you. {_sentence(said)}' + old, 'held for you - not started'), 'trust': trust_offer(store, tid)}
        return out('held', f'Waiting for you. {_sentence(said)}' + old, 'held for you - not started')
    if not auto_code_enabled(store) and (t.get('Kind') or '') == 'coding':
        return out('held', f'Waiting for you. Starting {agent} by itself is switched off, so it waits for you.' + old,
                   'held for you - not started')
    # ...the box says the hold is gone, and that it still waits for the owner's own Start: trusting is not starting (2026-10-26)
    # ...and A LIVE SESSION IS NOT "NOT STARTED" (the stress test, 2026-11-02): a general session leaves no run row and no transcript while it
    # lives, so a parked one fell through every fact above to "Not started yet. Nothing has started the assistant on this." - beside "needs you"
    if (live := live_session_state(tid, agent)): return out('live', *live)
    if lifted: return out('idle', f'Not started yet. The sender is trusted now - start {agent} when you want it; what was held never starts by itself.' + old,
                          'not started yet')
    return out('idle', f'Not started yet. Nothing has started {agent} on this.' + old, 'not started yet')


def not_started_why(store, tid) -> str: return idle_state(store, tid)['line']


def live_session_state(tid, agent: str = 'the agent') -> tuple | None:
    "(line, row) for the session live on this task - parked waiting on you, or working - or None when none is."
    from . import terminal
    try:
        s = terminal.session_for(tid)
        if not (s and getattr(s, 'alive', False)): return None
        waiting = bool(s.waiting()) if callable(getattr(s, 'waiting', None)) else getattr(s, 'busy', True) is False
    except Exception: return None
    # ...a CHAT agent's parked turn is ready for you, whatever its next move is (lane_word, the owner 2026-11-05); a coding one waits on you
    if waiting and type(s).__name__ == 'GeneralSession':
        return (f'Ready for you. {_cap(agent)} finished its turn - the next move is yours.', lanes.word('chat_ready'))
    return (f'Waiting for you. {_cap(agent)} finished its turn and waits on you.', 'waiting on you') if waiting \
        else (f'{_cap(agent)} is working on this.', 'working')


# the worker's own events in the owner's words - one line each on the agent step's timeline
_EVENT_SAYS = {'turn_end': 'Finished a turn', 'input_needed': 'Asked you something', 'approval_needed': 'Asked for your approval',
               'answered': 'Got your answer', 'background': 'Kept working in the background', 'stalled': 'Stalled',
               'finished': 'Said it was done', 'failed': 'Failed', 'stopped': 'Stopped'}


def _said(text, n=700) -> str:
    """The agent's last message, cut on a word; its own line breaks kept, since it is often a list."""
    t = '\n'.join(x.rstrip() for x in str(text or '').strip().splitlines() if x.strip())
    return t if len(t) <= n else t[:n].rsplit(' ', 1)[0] + '…'


def agent_story(store, tid) -> dict | None:
    """What the agent step says when nothing is live on it: WHY it never started, or WHAT it did before it went.

    The step showed a Start button and nothing else, both on a pull request held because its author was new and on a
    session a restart cut off mid-turn - the page could not tell "never started" from "did half and was killed" (the
    owner, 2026-10-11: "it should say what the agent did so far and was interrupted or it never started"). Facts only:
    not_started_why's sentence, and for work that went, the run's own worker events - no model. None when no agent
    was ever meant to have the task. The caller hides it behind a live session."""
    from . import general, terminal, taskstate
    st = taskstate.task_state(store, tid=tid); t = st.t          # one record: the story and its idle line tell the same facts
    if not t or t.get('Status') in ('done', 'dropped'): return None
    who = agent_word(t.get('Kind'))
    if st.news: return {'kind': 'news', 'line': news_line(store, tid, st.news)}
    left, q, idle = bool(st.left), store.get_dispatch(tid), st.idle
    held, why = idle['kind'] == 'held', idle['line']
    if not (str(t.get('Assignee') or '').startswith('agent:') or left or q or held):
        # ...but WHY NONE WAS MEANT is said where the agent would be (the email walk, 2026-10-29): the owner's own task and a reply
        # opened on an empty Agent section, the reason only in triage's panel ("on your list - no agent works it")
        why = no_agent_why(store, t)
        return {'kind': 'none', 'line': why} if why else None
    # the sentence is whole and leads with its state ("Waiting for you.", "Couldn't start."): the page adds nothing before it
    # ...and a run that FINISHED is finished, not "not started" over its own "finished its work" sentence (G7, 2026-10-20)
    if not left: return {'kind': 'held' if held else 'queued' if q else 'finished' if st.finished
                                 else 'live' if idle['kind'] == 'live' else 'idle', 'line': why,
                         **({'trust': idle['trust']} if held and idle.get('trust') else {})}
    evs = st.events
    sid = str(evs[-1]['Sid']) if evs else None
    run = [e for e in evs if str(e['Sid']) == sid]
    cut = next((e for e in reversed(run) if e['Kind'] == 'disconnected' and e.get('Source') in terminal.INTERRUPTING), None)
    interrupted = st.interrupted
    # a restart that finds the session already dead writes no worker event - release_task's note on the task is the cut
    if interrupted and not cut:
        n = next((c for c in reversed(store.list_comments(tid) or []) if c.get('Actor') in terminal.INTERRUPTING), None)
        if n: cut = {'Kind': 'disconnected', 'Source': n['Actor'], 'CreatedAt': n['CreatedAt'], 'Sid': sid}; run = [*run, cut]
    how = 'restarted' if cut and cut.get('Source') == 'startup' else 'closed'
    line = why
    if interrupted and cut:
        t0, t1 = _dt(run[0]['CreatedAt']), _dt(cut['CreatedAt'])
        mins = int((t1 - t0).total_seconds() // 60) if t0 and t1 else None
        into = f', {plural(mins, "minute")} in,' if mins else ','
        line = f'Taskuary {how} at {str(cut["CreatedAt"])[11:16]} while {who} had this{into} so its work stopped there. Nothing restarts by itself.'
    steps = []
    for e in run:
        k, src = e['Kind'], e.get('Source')
        w = ('Started' if not steps else None) if k == 'working' else \
            (f'Cut off - Taskuary {how}' if src in terminal.INTERRUPTING else 'Session ended') if k == 'disconnected' else \
            'Cut off by a time limit' if k == 'stopped' and src == general.TIMED_OUT else _EVENT_SAYS.get(k)
        if w and (not steps or steps[-1]['text'] != w):
            steps.append({'at': e['CreatedAt'], 'text': w, 'cut': k == 'disconnected' and src in terminal.INTERRUPTING})
    if len(steps) > 8: steps = steps[:1] + steps[-7:]
    said = next((e for e in reversed(run) if e['Kind'] == 'turn_end' and str(e.get('Text') or '').strip()), None)
    # ...and a run that FAILED is a failure, with the place that fixes it when there is one (Connect an AI): the step offers Try again
    failed = idle['kind'] == 'failed' and not interrupted
    # ...and A RUN THAT FAILED SAYS WHY FIRST, whatever cut it after (the owner, 2026-10-26: "you can't see what you have to do"): a
    # restart's note led the Result and "could not start: this tool has no built-in reviewer" sat at the foot of the transcript under it
    ran = st.failed or {}
    why = ran.get('sentence') or ''
    return {'kind': 'interrupted' if interrupted else 'failed' if failed else 'left', 'line': line, 'steps': steps,
            'said': _said(said['Text']) if said else '', 'said_at': said['CreatedAt'] if said else None,
            **({'why': why} if why and why.rstrip('.') not in line else {}),
            **({'fix': ran.get('fix')} if failed else {})}


def no_agent_why(store, t: dict) -> str:
    """Why no agent works a task of a kind no agent works (task, reply): the newest "No agent started:" line written on it
    (ingest.not_started), else the ending its route recorded (ingest's `act`, the route reason's last clause). '' for agent work."""
    from . import general
    from .ingest import NOT_STARTED
    if not t or t.get('Kind') in task_kinds.AGENT or general.handles(t): return ''
    tid = t['TaskId']
    said = next((str(c['Body']) for c in reversed(store.list_comments(tid) or []) if str(c.get('Body') or '').startswith(NOT_STARTED)), '')
    if said: return said
    r = next((r for r in reversed(store.list_routes(tid) or []) if r.get('Decision') != 'attach' and r.get('Reason')), None)
    tail = str(r['Reason']).rsplit(' · ', 1)[-1].strip().rstrip('.') if r else ''
    return f'{NOT_STARTED} {tail}.' if tail else ''


def left_by_facts(tags, runs) -> str:
    """'saved' | 'stopped' | '' from the task's tags and its runs - the rule the rail (taskstate.TaskState.left), the task's key
    (TaskState.key) and All (processing_all.row_lane) share, so one task cannot read "waiting to start" in one and "agent stopped"
    in the other (A16, 2026-09-25). All reads no further than this: its row is built from the census's view, which carries the
    tags and the runs and not the worker's events or the transcript the record goes on to read."""
    from . import terminal
    tg = [x.strip() for x in str(tags or '').split(',')]
    if terminal.SAVED in tg: return 'saved'
    if terminal.INTERRUPTED in tg or any(r.get('Status') in ('stopped', 'failed', 'error') for r in runs or []): return 'stopped'
    return ''


def general_not_started(task: dict, has_conversation: bool, routes=()) -> bool:
    """A regular-agent task triage handed on and nothing started: its route says so (`not auto-worked`) and there is no
    conversation yet. Left unassigned when triage named no specialist, it read as the owner's own work; it is waiting to
    start (A10, 2026-09-25). `general` is also the default kind of any task, so the route is what says it was meant for an
    agent."""
    return (str((task or {}).get('Kind') or '') == 'general' and not has_conversation
            and any(held_clause(r.get('Reason')) is not None for r in routes or ()))


def session_saved(store, tid) -> bool:
    "The owner ended the agent's session and its result is written - `session saved` (taskstate.TaskState.saved)."
    from . import taskstate
    return taskstate.task_state(store, tid=tid).saved


def agent_left(store, tid) -> bool:
    "An agent HAD this and is gone - a session saved, cut off, stopped or failed, or a transcript nothing finished (taskstate.TaskState.left)."
    from . import taskstate
    return bool(taskstate.task_state(store, tid=tid).left)


def session_finished(store, tid, evs=None) -> bool:
    """Did the LAST session end by finishing - it said it was done (its `finished` event), or its report was written
    after it began? Then nothing was left half-done: a task open again after it is open for what arrived since.
    `evs`: the task's worker events, when the caller has read them."""
    if evs is None: evs = store.worker_events(tid) or []
    if not evs: return False                     # no account of the session at all: nothing says it finished
    sid = str(evs[-1]['Sid'])
    run = [e for e in evs if str(e['Sid']) == sid]
    if any(e['Kind'] == 'finished' for e in run): return True
    began = str(run[0].get('CreatedAt') or '')
    return bool(began) and any(str(c.get('Body') or '').startswith(REPORTS) and str(c.get('CreatedAt') or '') >= began
                               for c in store.list_comments(tid) or [])


def report_failed(store, subject: str, mid=None) -> bool:
    """Did the run that produced THIS row fail? The run linked to this very message says so
    (report_run.MessageId); otherwise the subject's own convention ('- FAILED'). Never a word found
    inside the report's name.

    It used to read the source's LATEST run, so every historical row of a report inherited the newest
    verdict: two "Process Error Check - FAILED" rows sat in the pipe as landed results because the
    most recent run had said "0 rows" (the owner, 2026-09-10). It cut both ways - one fresh failure
    re-marked every older good row as broken and lifted the lot to band 2."""
    if mid is not None:
        try: failed = store.report_run_failed(mid)
        except Exception as e:
            logger.debug(f'funnel: no run record for message {mid} - {e}')
            failed = None
        if failed is not None: return failed
    return bool(_FAILED.search(str(subject or '')))


def reply_to(store, tid) -> int | None:
    """The message a reply from this task would answer. An agent that finished and a wrap-up have no
    message of their own, so "create reply from it to sender" had nothing to work with and the chat
    had to refuse (the owner, 2026-09-03: "why can\'t you create a draft from here")."""
    m = store.last_inbound_on_task(tid) if tid else None
    # ...and a promise task's is the owner's own mail the promise was made in: it is owed to whom that went (store.promised_in)
    return m['MessageId'] if m else (store.promised_in(store.get_task(tid)) or {}).get('MessageId') if tid else None


def agent_found(store, tid) -> str:
    """What the agent that worked this task said it found - the AGENT REPORT's summary line - so the
    assistant can say 'the agent looked; here is what it found' before asking for the yes."""
    if not tid: return ''
    rep = next((c for c in reversed(store.list_comments(tid)) if str(c.get('Body') or '').startswith((*REPORTS, 'HANDOVER NOTE'))), None)
    if not rep: return ''
    m = _REPORT_SUMMARY.search(rep['Body'])
    return _short(m.group(1) if m else rep['Body'].split('\n', 1)[-1], 300)


def chat_done(store, task: dict, when=None) -> dict:
    """A chat agent done for now - its turn asked nothing - as the task's wrap-up row: after a Send, that the reply went (taskstate.chat_moved_on).
    In the task's own lane: the task is still open and still the owner's, so its row stays under Tasks where it was (rows never move
    sections). It was built on `report`, a lane from before the rail had sections - and an open task jumped to the Reports pile the
    moment its reply went, then left the rail at the next Next as a report that had been read (the agent walk, 2026-11-09)."""
    from . import taskstate
    tid = task['TaskId']
    why = ('your reply went out - the agent is done for now, and the task is still open' if taskstate.chat_moved_on(store, tid)
           else 'the agent is done for now - type to carry on, and the task is still open')
    return _item(f"wrap:{tid}", 'wrapup', 'yours', task.get('Title') or f'task {tid}', who='you', when=when, tid=tid,
                 priority=task.get('Priority'), chat_done=True, why=why)


def paused_conversation(store, item: dict, st=None) -> dict:
    """Render resumable general work as a paused agent conversation, never as an unowned task.
    `st`: the task's record (taskstate.TaskState), when the row's builder holds one."""
    tid = item.get('tid')
    if not tid or item.get('lane') == 'working': return item
    from . import taskstate
    st = st or taskstate.task_state(store, tid=tid)
    task = st.t
    if task.get('Status') not in ('open', 'waiting', 'in_progress') or not store.saved_session(tid): return item
    try:
        from . import general
        if not general.handles(task) or tid in general.OPENING or general.session_for(tid): return item
        # ...nor one that IDLED OUT (general.idle_out): nothing stopped and nothing was saved - its agent is just not running until the next
        # input, and the task reads as the task (a reply ready, on you), never "agent stopped" or "conversation saved" (the owner, 2026-11-05)
        # ...and AS IT READ LIVE (the owner, 2026-11-07): its open question still asks you, and a turn that asked nothing is done for now
        if general.idled(tid, store):
            if (q := taskstate.open_question(store, tid)):
                return item | {'key': f'agent:{tid}', 'kind': 'agent', 'lane': 'blocked', 'asking': True, 'agent': 'assistant', 'mode': 'assistant',
                               'tail': [str(q.get('text') or '')[:300]], 'request_id': q.get('request_id'), 'request_kind': q.get('kind'),
                               'since': _ts(q.get('at')) or item.get('since'), 'why': request_line(None, q)}
            if item.get('lane') in ('yours', 'queued') and not store.waiting_on_owner(tid) and st.key == 'agentdone':
                return item | {k: v for k, v in chat_done(store, task).items() if k in ('key', 'kind', 'lane', 'who', 'why', 'chat_done')}
            return item
    except Exception:
        return item
    replies = [c for c in store.list_comments(tid) if c.get('ActorType') == 'assistant_agent']
    if not replies: return item
    last = str(replies[-1].get('Body') or '').strip()
    # what is TRUE of it: a conversation that finished and was saved, often reopened by mail that came after it - never "paused when
    # Taskuary stopped", which a reopened ask read as and the Advisor repeated as its reason to Continue (the owner, 2026-10-14)
    from .continuity import since_line, mail_since
    # ...and nothing is ASKING: no session is live here (session_for above), so `blocked` - "agent waiting on you", the hand - was
    # untrue of every saved or failed one (2026-10-22 walk). It is saved or stopped, and a failed last run says it failed (R2)
    failed = st.failed
    return item | {'key': f'agent:{tid}', 'kind': 'agent', 'lane': 'saved' if st.saved else 'stopped', 'paused': True,
                   'agent': 'assistant', 'mode': 'assistant', 'tail': [last[:600]] if last else [],
                   'news': bool(mail_since(store, tid)), **({'failed': True} if failed else {}),
                   'why': (f"Failed - {failed['sentence']}" if failed else '')
                          or since_line(store, tid, 'the assistant') or 'its saved conversation can pick up where it left off'}


def from_agents(store, live_state=_LIVE_UNSET, now: datetime = None) -> list:
    """Live sessions parked on a question - whatever the feed window, an agent waiting is waiting."""
    from . import terminal as term
    out = []
    fresh_setup = ((now or datetime.now()) - timedelta(minutes=SETUP_GRACE_MIN)).strftime('%Y-%m-%d %H:%M:%S')
    if live_state is _LIVE_UNSET:
        try: live = observe()
        except Exception: return out
    else:
        live = live_state
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
        if t.get('sid') and live_state is _LIVE_UNSET:
            try: tail = [x for x in term.asking_lines(t['sid'], 4)] or tail
            except Exception as e: logger.debug(f'funnel: no rendered screen for {t.get("sid")} - {e}')
        agent = task_kinds.shown(t)                       # Taskuary, or a coding session's tool - never the profile
        req = t.get('request') or None
        # a workflow run wears the workflow's mark (ChannelIcon 'workflow') - the terminal is for work with no source at all
        src = 'workflow' if task.get('Source') == 'workflow' else ''
        if req:
            # the worker said what it needs (workerstate.py, PW-228): the exact question or action, its kind and
            # choices - the card shows that, not four lines of screen
            out.append(_item(f"agent:{tid}", 'agent', 'blocked', task.get('Title') or f'task {tid}', who=agent, when=t.get('started'),
                             tid=tid, agent=agent, priority=task.get('Priority'), since=req.get('at') or t.get('started'), asking=req.get('kind') == 'input_needed', tail=[str(req.get('text') or '')[:300]], sid=t.get('sid'),
                             channel=src, mode=t.get('mode') or 'terminal', request_id=req.get('request_id'), request_kind=req.get('kind'), choices=list(req.get('choices') or []),
                             why=request_line(agent, req), questions=list(t.get('questions') or []), held=bool(t.get('held'))))
            continue
        # ONE READING of "is it asking" (A15, 2026-09-25): the session's own state and sentence (terminal.worker_fields,
        # general.info) - the rail read the screen with a question regex of its own, and could say "asked you" where the
        # Timeline, reading the session, said "is waiting on you". No words on the tail decide it any more (2026-10-11):
        # a session with no state of its own is parked, never "asked you" from a "?" in what it wrote.
        asking = t.get('state') == 'asking'
        # ...A CHAT AGENT THAT ASKED NOTHING is done for now (the owner, 2026-11-07; after a Send too, 2026-11-06): its row said "Taskuary is
        # waiting on you" - it is the task's wrap-up, "agent done", until something is typed again. A reply or an email it drafted still waits on you
        from . import general
        if not asking and t.get('mode') == 'assistant' and general.handles(task) and not store.waiting_on_owner(tid):
            out.append(chat_done(store, task, t.get('started'))); continue
        out.append(_item(f"agent:{tid}", 'agent', 'blocked', task.get('Title') or f'task {tid}', who=agent, when=t.get('started'),
                         tid=tid, agent=agent, priority=task.get('Priority'), asking=asking, tail=tail[-4:], sid=t.get('sid'), mode=t.get('mode') or 'terminal',
                         channel=src,
                         why=t.get('line') or agent_says('asking' if asking else 'parked', agent)))
    return out


def from_calendar(store, now: datetime) -> list:
    out = []
    # how long a started meeting stays on the rail - a setting (the owner, 2026-09-25), STARTED_MIN when unset
    try: grace = max(0, int(store.get_setting('meeting_grace_minutes') or STARTED_MIN))
    except (TypeError, ValueError): grace = STARTED_MIN
    # block=False: the pile is a read the owner is waiting on, and the calendar is a network call
    for e in _agenda(store, block=False):
        st, en = _activity_time(e.get('start')), _activity_time(e.get('end')) or _activity_time(e.get('start'))
        # a meeting is unread work until it starts; a few minutes into it there is nothing to walk the owner
        # into (2026-09-07: an hour-old meeting sat at the top of Unread as "next - coming up")
        if not st or (en and en <= now) or st <= now - timedelta(minutes=grace): continue
        mins = int((st - now).total_seconds() // 60)
        if mins > SOON_MIN and st.date() != now.date(): continue   # the rest of today is visible; the walk still waits for ALERT_MIN
        who = [w for w in (e.get('who') or []) if w]
        key = f"meeting:{str(e.get('start') or '')[:16]}:{_short(e.get('subject'), 40)}"
        out.append(_item(key, 'meeting', 'time', e.get('subject') or 'the meeting', who=', '.join(who[:3]), when=e.get('start'),
                         mins=mins, calendar_ready=(st - now).total_seconds() <= ALERT_MIN * 60, event={k: e.get(k) for k in ('start', 'end', 'subject', 'who', 'where', 'about', 'join', 'organizer')},
                         why=('starting now' if mins <= 0 else until_m(mins)) + (f" with {', '.join(w.split()[0] for w in who[:3])}" if who else '')))
    return out


def slipped_followup(store, action: dict, now: datetime = None) -> tuple:
    """SLIPPED (spec 2026-10-12): a follow-up quiet past THAT person's day is the owner's move, in the slipped lane. The day is
    the ledger's (outcomes.late_after), the default the owner's (Settings -> Advisor); someone away never slips, and a reply
    from them ends it. Returns (lane, days past the person's day, days quiet, the person's day): lane is 'forgotten', 'answered'
    (close the idea) or None - one rule for the rail and the Advisor's own read of it."""
    a = action or {}
    if a.get('type') != 'followup' or not a.get('who_email') or not a.get('asked_at') or a.get('away'): return (None, 0, 0, 0)
    from . import outcomes
    # THEIR REPLY ENDS IT: a material word from them on the thread since the ask is the answer, whatever the idea row still says
    m = store.get_message(a.get('mid')) if a.get('mid') else None
    if m and m.get('ConversationId') and outcomes._material_inbound_after(store, m['ConversationId'], a['asked_at']): return ('answered', 0, 0, 0)
    day = outcomes.late_after(store, a['who_email'], int(store.get_setting('slipped_default_days', 5) or 5))
    quiet = max(0, int(((now or datetime.now()) - (_dt(a['asked_at']) or datetime.now())).total_seconds() // 86400))
    return ('forgotten', quiet - day, quiet, day) if quiet >= day else (None, 0, quiet, day)


def slipped_why(who_email: str, quiet: int, day: int) -> str:
    from .processing_unread import holder_name
    return f"No answer from {holder_name('person:' + str(who_email or ''))} in {quiet} days - late for them after {day}"


# ── the pile ─────────────────────────────────────────────────────────────────────────────────
# Lanes retain presentation/state semantics; the shared five bands own ordering across the pile and
# the feed. INSIDE the actionable band the lane ranks (the owner, 2026-09-07: "asked you" sat under
# reports because both were one band): what asks you, then what waits for an agent, then what broke, then what landed.
# The band is the lane's own entry in lanes.json (lanes.band_of): 'slipped' is the owner's move, a landed result is its own
# level, and a lane nobody wrote down is work - falling to the fyi band buried it among the newsletters, which is how work
# disappears. Today's brief is a REPORT, first among the reports (the sort key below; the owner, 2026-09-23).
_band = lanes.band_of


# THE RAIL'S SECTIONS live in lanes.json `sections` - their order, headings and bands - and level_of (lanes.py, re-exported
# here) is the one rule the page's levelOf (website/src/lanes.js) mirrors, pinned by tests/fixtures/rail_levels.json. The
# canvas redesign (2026-09-29) walks a section by its heading and the phone doorway offers the same sections as picks, so the
# walk and the rail must agree on which row is in which.


def section_done(section: str) -> str:
    return f"{SECTION_WORDS.get(section, section)} done."


def _activity_time(value):
    """Stored-local compatibility, retaining subseconds and explicit offsets."""
    try:
        stamp = datetime.fromisoformat(str(value or '').replace('Z', '+00:00'))
        return stamp.astimezone().replace(tzinfo=None) if stamp.tzinfo else stamp
    except ValueError:
        return None


def not_ahead(stamps) -> list:
    """The stamps that are not in the future: a mail's Date header is the sender's clock, and one set hours ahead made the rail read
    "in 5h" over a row that had already arrived (the email walk, 2026-10-29). Nothing arrives later than now; all ahead, all kept."""
    now = datetime.now() + timedelta(minutes=1)
    return [x for x in stamps if (t := _activity_time(x)) and t <= now] or list(stamps)


def arrived(item):
    """When a row ARRIVED - its task's creation, else its first message (`arrived_at`, stamped by the builders) - the one clock its
    place on the rail is read from. Never its last activity: a reply landing, an agent starting or asking and the walk's own marks
    all moved rows, and the owner saw 19h, 17h, 11h, <30m, 1h (2026-10-22: "set by time, oldest to newest and then never move")."""
    return _activity_time(item.get('arrived_at') or item.get('sort_at') or item.get('since') or item.get('when'))


_LEVEL_RANK = {k: n for n, k in enumerate(lanes.LEVEL_ORDER)}


def order_key(item) -> tuple:
    """A row's place: its SECTION in the rail's drawing order (lanes.json), then when it arrived - oldest first, in every section,
    reports too (the owner, 2026-10-22: "reports should go oldest first like everything else"; they were newest first from
    2026-10-02) - then a stable key. Nothing about its agent, its read state, its urgency, the table or the walk enters it, so a row
    moves only by leaving its section. Today's brief leads Reports, whatever the clock says - it summarises the day, so it is read
    first. ONE key for the rail, desktop Next and phone Next (railwalk.line)."""
    level, at = level_of(item), arrived(item)
    t = (at - datetime.min).total_seconds() if at else 0.0
    return (_LEVEL_RANK.get(level, len(_LEVEL_RANK)), not todays_brief(item), at is None, t, *place_id(item))


def _num(x):
    if isinstance(x, bool) or (isinstance(x, float) and not x.is_integer()): return None
    try: return int(x)
    except (TypeError, ValueError): return None


def place_id(item) -> tuple:
    """A TIE IN THE SAME SECOND, settled by ids that never change: the task number, then the row's first message, and only then its key.
    A goal and the steps made with it arrive together (the goal is made first); two dashboards filed by one run land in the same second
    (the first filed first); rows of one task (its agent's, its draft's) keep their key between them. The key alone is a hash -
    `processing:pi_<hex>` - and the page, placing a row it put back by arrival alone (funnelPile.placeOrder), disagreed with it: the two swapped, drawn over each other, while the rail moved (the dead-end walk's SWAP;
    2026-10-25). ONE rule, mirrored line for line by funnelPile.placeId."""
    tid = _num(item.get('tid'))
    mids = [n for m in item.get('member_ids') or () if str(m).startswith('message:') for n in [_num(str(m)[8:])] if n is not None]
    mid = None if tid is not None else min(mids) if mids else _num(item.get('mid'))
    # ...and a row with neither - an idea, a review, a run filed on its own - by its first member, kind then number, before the hash
    # (the release walk's sweep, 2026-10-25: two such rows of one second still drawn over each other)
    return (tid is None, tid or 0, mid is None, mid or 0, '' if tid is not None or mid is not None else first_member(item), str(item.get('key') or ''))


def first_member(item) -> str:
    """The smallest of a row's own members as `kind:000000000012` - zero-padded so the text sorts as the number does, on the page too."""
    ids = [f"{k}:{n:012d}" for m in item.get('member_ids') or () for k, _, v in [str(m).partition(':')] for n in [_num(v)] if n is not None and n >= 0]
    return min(ids, default='')


def _order(items: list) -> list:
    """The sections, then the oldest first inside one, then a stable key - and nothing else (the
    owner, 2026-09-07: "within one level oldest wins first"; 2026-10-22: "then never move"). See order_key."""
    return sorted(items, key=order_key)


RUN_STALE_MIN = 20        # a 'running' run row nobody has touched for this long is not working anything

def working_tids(store, live_state=_LIVE_UNSET, now: datetime = None) -> set:
    """Tasks an agent has right now - a live session, or a headless run that is actually running.
    Nothing about them is the owner's to do until the agent stops.

    A run row left at 'running' by a session that died used to be proof enough: TQ-0006 sat in the
    working lane with no session and "nothing for you", and the outage task vanished from the pipe
    altogether - not read, not offered, not findable (the 2026-09-03 break test). A row nobody has
    touched for RUN_STALE_MIN is a corpse, not a worker."""
    from . import terminal as term
    fresh = ((now or datetime.now()) - timedelta(minutes=RUN_STALE_MIN)).strftime('%Y-%m-%d %H:%M:%S')
    out = {r['TaskId'] for r in store.running_runs()
           if r.get('TaskId') and str(r.get('UpdatedAt') or r.get('StartedAt') or '') >= fresh}
    try:
        live = observe(0) if live_state is _LIVE_UNSET else live_state
        for t in live:
            if not t.get('taskId'): continue
            waiting = t.get('waiting') if t.get('waiting') is not None else (t.get('idle') or 0) >= term.IDLE_WAITING
            if not waiting: out.add(t['taskId'])
    except Exception: pass
    return out


def build(store, now: datetime = None, keep_surfaced: bool = False, live_state=_LIVE_UNSET,
          full_history: bool = False, keys=None) -> dict:
    """The rail, from the one builder there is (processing_unread.build). `keys`: a lookup - it cards only what answers to them."""
    from .processing_unread import build as shared_build
    return shared_build(store, now=now or datetime.now(), include_read=keep_surfaced,
                        live_state=None if live_state is _LIVE_UNSET else live_state,
                        full_history=full_history, keys=keys)


def _chat_only(store, low, high) -> bool:
    """Every write since the cached build was the Assistant's own conversation - a line it said, a badge it stamped, on its dock task. The
    rail draws nothing from that task, and each walk move writes there: counted as a change, every press rebuilt the whole rail for its
    own words (0.5-0.7 s on a real home, 2026-10-31)."""
    written = getattr(store, 'rail_written', None)
    dock = str(store.get_setting('assistant_dock_task_id') or '') if callable(written) else ''
    got = written(low, high) if dock else None
    return bool(got) and got <= {('task', dock)}


def _rail_top(store):
    top = getattr(store, 'rail_top', None)
    return top() if callable(top) else None


# A WORKING AGENT'S SCREEN IS NOT A NEW PILE (2026-11-09). The signature hashed every field of every session, its last six screen
# lines too, and a working agent prints every second: hardly a read of the pile while one worked came back warm (81 of 102 that
# morning took over a second, the worst 33 s), and the Advisor, the walk and every open tab each rebuilt it in turn behind one lock -
# a Not for me sat ~45 s. A working row only SHOWS its tail (laid on fresh as the pile is served: _fresh_tails); a parked one is read
# off it (from_agents), so its tail stays in. The git-dirty files, the witness's work and the browser are on no card at all.
SCREEN_ONLY = ('files', 'work', 'browser')


def _attention(t) -> dict:
    from .processing_projection import _worker_attention
    row = {k: v for k, v in _worker_attention(t).items() if k not in SCREEN_ONLY}
    if not row['waiting']: row.pop('tail', None)
    return row


def workers_signature(live_state) -> str | None:
    """What the pile reads from the live sessions, hashed - so a worker that stopped, asked or finished since the cache was built is a
    different pile, and one that only printed another line is not. None when the sessions cannot be observed right now."""
    if live_state is None: return None
    rows = sorted(json.dumps(_attention(t), ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) for t in live_state)
    return hashlib.sha256('\n'.join(rows).encode()).hexdigest()


def observe(tail: int = 6):
    """The live sessions as the pile's checks read them: the light road - no `git status` per session, no witness (SCREEN_ONLY)."""
    from . import terminal as term
    try: return term.live_sessions(tail=tail, details=False)
    except TypeError: return term.live_sessions(tail=tail)       # a stand-in that predates `details`


def _fresh_tails(p: dict, observed) -> dict:
    """A cached pile served with each working row's screen as it is NOW - the one thing the signature lets move under it."""
    tails = {t['sid']: t['tail'] for t in observed or () if t.get('sid') and t.get('tail') is not None}
    for i in p.get('items') or ():
        if i.get('lane') == 'working' and i.get('sid') in tails: i['tail'] = tails[i['sid']]
    return p


_OBSERVE = object()


def _moved(store, workers) -> bool:
    """Written to, or a worker moved, since the cached build began. Held under _LOCK."""
    top = _rail_top(store)
    if workers is None or workers != _CACHE.get('workers'): return True
    if top is None or _CACHE.get('mark') is None or top == _CACHE['mark']: return False
    if not _chat_only(store, _CACHE['mark'], top): return True
    _CACHE['mark'] = top; return False                 # ...the Assistant's own words only: the build stands, at the new mark


def warm(store) -> bool:
    """A read of the pile now is served from the cache: built for this store, in its time, and nothing written or moved since."""
    try: workers = workers_signature(observe())
    except Exception: return False
    # ...and a build running now is no warm rail: asked behind it, a walk press waited out the whole build only to be told no (2026-11-09)
    if not _LOCK.acquire(blocking=False): return False
    try:
        return (_CACHE.get('store') is store and bool(_CACHE.get('pile')) and time.time() - _CACHE.get('at', 0) < PILE_EVERY
                and not _moved(store, workers))
    finally: _LOCK.release()


def pile(store, force: bool = False, quiet: bool = False, observed=_OBSERVE, seen=None) -> dict:
    """The pile, cached for a few seconds: it is polled while the page is open, and every look
    is a dozen queries.

    A cached pile is served only while NOTHING has moved since it was built: no write in any process
    (the store's dirty-row top, rail_top, says so) and no change among the live workers (`observed`,
    the sessions as seen now - taken here when not handed in). So a turn can take its selection from
    here instead of building the rail a second time (design B, 2026-09-17). `quiet` skips the
    watcher: a Next that turns out stale must reach no write, and announce() writes notices."""
    from . import live
    seen_generation, asked = _CACHE.get('generation', 0), time.perf_counter()
    # the newest write stamp a build begun now has seen (live.seq: the page's reload check) - taken before the workers are, whose
    # moves are stamped too; a caller that observed them itself says when (`seen`), or the build claims no stamp at all
    own = seen is None and observed is _OBSERVE
    if own: seen = live.seq()
    if observed is _OBSERVE:
        try: observed = observe()
        except Exception: observed = None            # unobservable: never compare, always rebuild (the build says why)
    workers = workers_signature(observed)
    with _LOCK:
        same_store = _CACHE.get('store') is store
        moved = lambda: _moved(store, workers)
        if same_store and _CACHE['pile'] and not force and moved(): _CACHE.update(at=0.0); force = True
        # One websocket event wakes every open browser. If they all arrive while the first forced
        # rebuild is running, that one result satisfies all of them; rebuilding once per tab is a
        # thundering herd that can hold every other API request behind this lock for a minute. A
        # cache from another Store is never interchangeable (tests and embedded callers can have
        # an in-memory store beside the application store).
        # Compare the cache generation we actually observed before waiting for the lock. Wall
        # clock comparison (`cache_at >= requested_at`) is not a generation check: Windows can
        # give two successive time.time() calls the same value, which made an immediate forced
        # refresh return the old agent/message state.
        # ...and only one that holds every write so far: a rebuild already running when a write landed was built without it. Next's
        # admission waited on the page's own pile read, took that build as its selection, and its commit check - building again, with
        # the write - saw the shown item's stamp move and refused the press (PW-118: a comment landed on the task about to be shown)
        refreshed_while_waiting = (same_store and force and _CACHE['pile']
                                   and _CACHE.get('generation', 0) != seen_generation and not moved())
        # ...and a read that waited out a build BEGUN AFTER it was asked has that build: it holds every write made before the ask. Without it
        # each reader queued behind a build rebuilt in turn while an agent kept writing - a tab, the Advisor and a press, one after another
        # (a write after the ask that emptied _CACHE since is the next read's, not this one's)
        if (_CACHE.get('generation', 0) != seen_generation and _KNOWN.get('store') is store and _KNOWN['pile']
                and _KNOWN.get('began', 0.0) > asked): return _fresh_tails(_KNOWN['pile'], observed)
        if same_store and _CACHE['pile'] and (refreshed_while_waiting or (not force and time.time() - _CACHE['at'] < PILE_EVERY)):
            return _fresh_tails(_CACHE['pile'], observed)
        # ...the stamp and the workers as the BUILD begins, not as the wait for the lock did: a read that waited out another build
        # was built with a press's write that landed meanwhile and still claimed the older stamp - the page read the rail again for a
        # write it held (CI's slower runners, reads-once). Same order as above: stamp, then workers, then the dirty-row mark.
        if own:
            seen = live.seq()
            try: observed = observe()
            except Exception: observed = None
            workers = workers_signature(observed)
        mark, began = _rail_top(store), time.perf_counter()   # taken BEFORE the build: a write during it counts as after
        # the watcher speaks first: a transition changes the pile too. Quiet, it keeps what it last said.
        events = ((_CACHE['pile'] or {}).get('events') or [] if same_store else []) if quiet else announce(store)
        # ONE build serves the pile and the item the page is holding: the builder computes
        # every card's read state anyway, and the pile is its unread subset (processing_unread.build)
        from .processing_unread import rail_of
        full = build(store, keep_surfaced=True)
        items = rail_of(full['items'])
        p = {**full, 'items': items, 'lanes': [{**l, 'n': sum(i['lane'] == l['lane'] for i in items)} for l in full['lanes']],
             'counts': {**full['counts'], 'unread': len(items), 'actionable': sum(i['actionable'] for i in items)}}
        # A CLOSE ON ITS WAY IS CLOSED (the owner, 2026-11-09: "i marked task done, the one before came back and then disappeared again"):
        # Mark done on an agent's task writes it up first and closes after (writeup.closing); a read meanwhile drew it again for a read or two
        from . import writeup
        if (gone := {i['tid'] for i in p['items'] if i.get('tid') and writeup.closing(i['tid'])}):
            items = [i for i in p['items'] if i.get('tid') not in gone]
            p = {**p, 'items': items, 'lanes': [{**l, 'n': sum(i['lane'] == l['lane'] for i in items)} for l in p.get('lanes') or []]}
        for i in p['items']: _attach(i)                  # how each row reads, once, for the rail and the phone alike
        _label_workstreams(store, p['items'])            # ...and which workstream each task row is under, for its small label
        p['alerts'] = alerts(store, p['items'])
        # BULK PROCESSING: which row wears the "250 more" pill. None on an install that ranks
        # nothing, which is what keeps this whole feature invisible to an owner who takes one
        # item at a time (the owner, 2026-09-18: "i should not see it since i process each by
        # itself and not in bulk").
        try:
            from . import rank
            p['more_markers'] = rank.more_markers(store, p['items'])
            p['rank_numbers'] = rank.rank_numbers(store, p['items'])
        except Exception as e:
            logger.debug(f'the ranked count did not reach the rail: {e}')
            p['more_markers'], p['rank_numbers'] = [], {}
        # ...and a BATCH row says how far it got: "2 of 4 done · ③ needs you", with a bar of its items (batch.py)
        try:
            from . import batch
            p['batch_progress'] = batch.rail(store, p['items'])
        except Exception as e:
            logger.debug(f'batch progress did not reach the rail: {e}'); p['batch_progress'] = {}
        p['events'] = events
        p['live_seq'] = seen
        _CACHE.update(at=time.time(), pile=p, store=store, full=full['items'],
                      generation=_CACHE.get('generation', 0) + 1, mark=mark, workers=workers)
        _KNOWN.update(store=store, pile=p, full=_CACHE['full'], began=began)
        _keep_threads(store, [*full['items'], *p['items']])
        return p


# THE FYI TAIL IS PAGED FOR THE PAGE (the owner approved, 2026-10-20: "first page at once, more as the owner scrolls or asks;
# same rows, same order, same counts shown"). Six months of FYI was 2,487 of a big mailbox's 2,876 rows and 3 MB of every
# answer, while the rail draws a handful of them under "N more fyi". The page asks for `fyi` plain FYI rows; the rest go as
# `fyi_tail`, the few fields the page COUNTS by (its headings, the day's opener, "in today", the channel picker), one short
# list per row. A plain FYI row is one in the fyi lane and band with nothing else about it - the row on the table, the
# walk's next pick and its batch are always sent whole, wherever they sit.
FYI_PAGE = 50
TAIL_FIELDS = ('key', 'kind', 'title', 'who', 'agent', 'shows_who', 'ref', 'tid', 'when', 'category', 'status', 'channel')


def _plain_fyi(i) -> bool:
    return (i.get('lane') == 'fyi' and i.get('order_band') == 4 and i.get('kind') != 'idea' and not str(i.get('kind') or '').startswith('goal')
            and not any(i.get(k) for k in ('settling', 'deferred', 'surfaced', 'news')))


def page_fyi(payload: dict, n: int, keep=()) -> dict:
    """The payload with its plain FYI rows past the first `n` (in the pile's own order) folded into `fyi_tail`. Every other
    row, every count the server made and the selection are untouched; `keep` names rows that are sent whole regardless."""
    keep = {k for k in keep if k}
    keep |= {m for k in list(keep) if str(k).startswith('fyis:') for m in str(k)[5:].split(',')}
    items, tail, sent = [], [], 0
    for i in payload.get('items') or []:
        if _plain_fyi(i) and i.get('key') not in keep and keep.isdisjoint(i.get('aliases') or ()):
            if sent >= n:
                tail.append([(i.get('shows') or {}).get('who') if f == 'shows_who' else i.get(f) for f in TAIL_FIELDS]); continue
            sent += 1
        items.append(i)
    return {**payload, 'items': items, 'fyi_tail': {'fields': list(TAIL_FIELDS), 'lane': 'fyi', 'order_band': 4, 'rows': tail}}


def full_items(store) -> list | None:
    """The cached build with read items kept, for a same-request lookup of the item on the table."""
    return _CACHE['full'] if _CACHE.get('store') is store and _CACHE['pile'] else None


def built_as_of_now(store) -> bool:
    """Has nothing been written since the cached rail's build began? (Unknowable - no dirty-row top - counts as yes.)"""
    top = _rail_top(store)
    return top is None or _CACHE.get('store') is not store or _CACHE.get('mark') == top


def unwritten_full_items(store) -> list | None:
    """full_items, only while nothing at all has been written since that build began (the dirty-row top it was built at)."""
    top = _rail_top(store)
    return full_items(store) if top is not None and _CACHE.get('mark') == top else None


def _keep_threads(store, items):
    """Remember each drawn row's folded thread; a row drawn alone forgets one it had. Rows no longer drawn (read) keep theirs."""
    if _THREADS['store'] is not store: _THREADS.update(store=store, by={})
    for i in items:
        if not str(i.get('key') or '').startswith('processing:'): continue
        if i.get('thread'): _THREADS['by'][i['key']] = list(i['thread'])
        else: _THREADS['by'].pop(i['key'], None)


def thread_of(store, key: str) -> list:
    """The keys folded under the FYI row `key` - the other mails on its email thread - as the rail last drew it, even after a settle
    emptied the rail's cache (_THREADS)."""
    if not str(key or '').startswith('processing:'): return []
    if _CACHE.get('store') is store:
        rows = [*(_CACHE.get('full') or ()), *((_CACHE.get('pile') or {}).get('items') or ())]
        if (got := next((i.get('thread') for i in rows if i.get('key') == key and i.get('thread')), None)): return list(got)
    return list(_THREADS['by'].get(key) or []) if _THREADS['store'] is store else []


def _label_workstreams(store, items: list):
    """THE RAIL ROW'S WORKSTREAM LABEL (the owner, 2026-11-01): a task row carries its task's workstream, read in one query - only what is
    placed already (workstreams.of_task places on read; the rail never writes). An idea row keeps its own."""
    tids = sorted({int(i['tid']) for i in items if i.get('tid') and not i.get('workstream')})
    if not tids: return
    try: ws = {r['TaskId']: r['Workstream'] for r in store._rows(f"SELECT TaskId, Workstream FROM task WHERE TaskId IN ({','.join('?' * len(tids))}) "
                                                                  "AND IFNULL(Workstream,'')<>''", tuple(tids))}
    except Exception: return
    for i in items:
        if i.get('tid') and not i.get('workstream') and (w := ws.get(int(i['tid']))): i['workstream'] = w


def rail_item(store, key: str) -> dict | None:
    """The row answering to `key` in the rail's own build, while nothing has been written since it began - or None, and the
    caller looks it up as it always did (next_item). A batch key is no row."""
    full = unwritten_full_items(store) if key and not str(key).startswith('fyis:') else None
    return next((i for i in full or () if i['key'] == key or key in i.get('aliases', [])), None)


def cached_pile(store) -> dict | None:
    """The rail as last built, or None - never a build (the Tasks list asks, and must not pay for one)."""
    return _CACHE['pile'] if _CACHE.get('store') is store else None
def cached_at(store) -> float: return _CACHE.get('at', 0.0) if _CACHE.get('store') is store else 0.0
def known(store) -> dict | None:
    """The rail as last built, however much was written since - None only before the first build. Never a build, never a wait."""
    return _KNOWN['pile'] if _KNOWN.get('store') is store else None
def building() -> bool: return _LOCK.locked()          # a pile build (or its cache check) holds the lock right now
def known_full(store) -> list | None: return _KNOWN['full'] if _KNOWN.get('store') is store else None


def invalidate(): _CACHE.update(at=0.0, pile=None, store=None, full=None, mark=None, workers=None); _SOURCES.update(at=0.0, by={})
def forget_states(): _STATE.clear(); _SEEN.clear(); _WATCHED[0] = False; _THREADS.update(store=None, by={})


def present(store, payload: dict) -> dict:
    """Detach and fingerprint a selected funnel payload without changing its selection."""
    return _present(store, payload)


def _present_one(store, item: dict | None) -> dict | None:
    return present(store, {'items': [item]})['items'][0] if item is not None else None


def agent_states(store) -> dict:
    """Every task an agent has, or had: what it is doing now. {tid: (state, agent)}"""
    from . import terminal as term
    out = {}
    try: live = observe()
    except Exception: live = []
    for t in live:
        tid = t.get('taskId')
        if not tid or (store.get_task(tid) or {}).get('SourceRef') == 'assistant:dock': continue
        waiting = t.get('waiting') if t.get('waiting') is not None else (t.get('idle') or 0) >= term.IDLE_WAITING
        out[tid] = (sub_state(waiting, t.get('state') == 'asking', t.get('request')) or 'working', task_kinds.shown(t))
    for r in store.running_runs():
        if r.get('TaskId') and r['TaskId'] not in out: out[r['TaskId']] = ('working', task_kinds.SHOWN)
    for tid in list(_STATE):
        if tid in out: continue
        t = store.get_task(tid) or {}
        out[tid] = (('done' if t.get('Status') in ('done', 'dropped') else 'idle'), _STATE[tid][1] if isinstance(_STATE[tid], tuple) else task_kinds.SHOWN)
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
        if state == 'working' and was in (None, 'idle', *BLOCKED):
            events.append({'tid': tid, 'ref': ref, 'kind': 'working', 'agent': agent,
                           'text': f"{agent} is working on {ref} ({title}) - nothing for you there now."})
        elif state in BLOCKED and was in ('working', 'idle', None):   # stopped - or found already parked
            events.append({'tid': tid, 'ref': ref, 'kind': state, 'agent': agent, 'text': f"{agent_says(state, agent)} on {ref} ({title})."})
        elif state == 'done' and was in ('working', 'idle', *BLOCKED):
            summ = agent_found(store, tid)
            events.append({'tid': tid, 'ref': ref, 'kind': 'done', 'agent': agent, 'summary': summ,
                           'text': f"{agent} finished {ref} ({title})" + (f": {summ}" if summ else '.') + ' The task is closed.'})
    if state_dropped := [tid for tid in _STATE if _STATE[tid][0] == 'done']:
        for tid in state_dropped: _STATE.pop(tid, None), _SEEN.pop(tid, None)   # said once; a closed task is not watched again
    if events:
        # an unsolicited update is a NOTICE for the bottom strip (PW-165) - never a line or a card the watcher
        # writes into the chat by itself. A parked or asking agent is already an alert of the pile's own, so it
        # is not kept twice; a newer fact about the same task replaces the older notice, so nothing repeats
        # unless the facts changed.
        # A FINISHED task is not one of them. The strip is for what is waiting on the owner, and a closed task
        # is waiting for nothing - so "codex finished TQ-0505. The task is closed." sat on the strip for three
        # days wanting a click that changed nothing (the owner, 2026-09-14: "why is this showing up if it's
        # closed?"). The done event still fires - it clears the working notice and lets the table drop a closed
        # card - it just does not become a row of its own. What the agent LEFT behind is what speaks: a question
        # it parked on, a draft wanting a yes, both alerts the pile raises by itself.
        for e in events:
            e['card'] = None
            store.clear_funnel_state(f"notice:{e['tid']}")
            if e['kind'] == 'working': notify(store, e, actor)
        invalidate()
    return events


def notify(store, e: dict, by: str = 'assistant'):
    """One notice per task, kept on the funnel state (PW-166): Later marks it `ack`, a new fact rewrites it."""
    store.set_funnel_state(f"notice:{e['tid']}", 'notice', by, None, json.dumps({k: v for k, v in e.items() if k != 'card'}))


def worked_now(store) -> set:
    """The tasks an agent is on RIGHT NOW - a live session or a running run."""
    from . import terminal as term
    try: live = {t.get('taskId') for t in term.live_sessions(tail=0, details=False)}
    except Exception: live = set()
    return {t for t in live if t} | {r['TaskId'] for r in store.running_runs() if r.get('TaskId')}


def notices(store, states: dict = None) -> list:
    """The strip's own notices: the watcher's events, in the shape of an alert, until Open or Later.

    A `working` notice is a CLAIM about live state, so it is checked against live state when it is
    read. The transition that would retire it (working -> done) is seen only by the in-memory watcher,
    and a restart makes its first look remember instead of announce - so the row outlived its agent by
    days and every fresh phone walk re-told it (the owner, 2026-09-10: "there are no agents open??").
    A `done` notice is no longer written at all, and one left over from a build that did write them is
    dropped here rather than left waiting for a click - see `announce`.
    """
    states = states if states is not None else store.funnel_states()
    out, worked = [], None
    for k, st in states.items():
        if not k.startswith('notice:') or st.get('Status') != 'notice' or not st.get('Note'): continue
        try: e = json.loads(st['Note'])
        except ValueError: continue
        # nothing is owed on a closed task; a leftover row from an older build goes quietly
        if e.get('kind') == 'done': store.clear_funnel_state(k); continue
        working = e.get('kind') == 'working'
        if working:
            if worked is None: worked = worked_now(store)
            if e.get('tid') not in worked or (store.get_task(e.get('tid')) or {}).get('Status') in ('done', 'dropped'):
                store.clear_funnel_state(k); continue
        out.append({'key': k, 'item': f"{'agent' if working else 'task'}:{e.get('tid')}", 'kind': e.get('kind'), 'lane': 'working' if working else 'report',
                    'text': e.get('text') or '', 'notice': True, 'order_band': 3, 'at': st.get('At'), 'tid': e.get('tid'), 'ref': e.get('ref')})
    return sorted(out, key=lambda a: str(a.get('at') or ''))


FYI_BATCH = 4                             # FYI has no action: the walk reads a few together - four where no screen said how many
FYI_BATCH_RANGE = (1, 10)                  # ...and how many is the owner's (Settings -> Assistant)
# ...BY THE SCREEN THAT ASKED (the owner, 2026-10-28: "by default do 6 at a time so it looks combined? though if the screen is smaller maybe
# 4 at a time - based off screen size"): the page sends X-Taskuary-Fyi-Batch on every request (website/src/fyiBatch.js) - six on a desktop,
# four on a laptop under 800px tall or a phone - and the server's middleware puts it here for that request. A number the owner SET wins
SCREEN_BATCH = contextvars.ContextVar('fyi_batch_screen', default=None)


def fyi_batch_size(store) -> int:
    """How many fyi the walk puts up together. Clamped: a hand-edited 0 would empty the fyi lane
    from the walk entirely, and a 500 would answer the day in one unreadable card."""
    lo, hi = FYI_BATCH_RANGE
    # ...the shipped '4' is a default, not a choice: only a number the owner wrote holds against the screen's (SCREEN_BATCH)
    screen = SCREEN_BATCH.get()
    try: own = store.setting_writer('fyi_batch') == 'owner'
    except Exception: own = False
    if screen and not own: return max(lo, min(hi, int(screen)))
    # ...and a store that cannot answer gets the default rather than an exception: how many fyi to
    # read together is a preference, and no preference is worth failing a selection over.
    try: n = int(str(store.get_setting('fyi_batch') or FYI_BATCH).strip())
    except (AttributeError, TypeError, ValueError): return FYI_BATCH
    return max(lo, min(hi, n))

# On the timeline, but nothing to say about it YET - the walk skips it and comes back. A meeting enters the pipe two hours out
# (SOON_MIN) so the day is visible, and the assistant opened with one still an hour and a half away, ahead of mail that wanted
# answering now (the owner, 2026-09-04: "meetings should not go down into the chat until 15 minutes before like a agent in
# middel of working"). The same line that turns a meeting urgent (lanes.not_yet, at ALERT_MIN).
_not_yet = lanes.not_yet


def next_item(store, key: str = None, include_surfaced: bool = False, items: list | None = None) -> dict | None:
    """The named item, read or not - the chat may return to it. With no key there is nothing to look up: WHICH row comes next is
    railwalk's alone (the walk has one owner, 2026-10-30; railwalk.top is the row a walk starts on)."""
    # by key, whatever its state: read already, or with an agent on it now - the concierge decides what to say
    if key:
        # A batch is not an item, so there is nothing to look for: the lookup below never found it and
        # fell through to the FULL-HISTORY build (every root in the database, ~9 s live) just to return
        # None before batch_item answered - on every "All read, Next", since the page sends the key it
        # holds as `current` (the owner, 2026-09-17: "hitting all read next still takes forever").
        if key.startswith('fyis:'): return batch_item(store, key)
        # ...and a task or a message opened while the first rail after a restart is still being built is drawn from its own rows
        # (item_for_key), not held until that build ends: opening a task waited up to 28 s on it (2026-10-21)
        if items is None and getattr(store, 'rail_cold_building', lambda: False)():
            quick = item_for_key(store, key)
            if quick: return quick
        # ...and a key is looked up, never the rail rebuilt for it: the keyed build cards only what answers to it (the
        # same cards, the same order), where the whole one carded every root to keep one - Current is restored on
        # every chat read, every 30 s tick, and outside the window it paid for the WHOLE history each time (P4).
        pool = items if items is not None else build(store, keep_surfaced=True, keys=[key])['items']
        item = next((i for i in pool if i['key'] == key or key in i.get('aliases', [])), None)
        if item is None:
            item = next((i for i in build(store, keep_surfaced=True, full_history=True, keys=[key])['items']
                         if i['key'] == key or key in i.get('aliases', [])), None)
        return shut(store, _present_one(store, item)) or batch_item(store, key)
    return None


def shut(store, it):
    """A CLOSED TASK SAYS SO: brought up by its ref it carried no `closed`, so its row offered Mark done, Close with a note and Remove
    beside Reopen task, and a typed close ran task.complete on it a second time (2026-10-26). Only Reopen task reopens it. ...And opened, it is
    only shown - the page draws no row for it under Tasks (funnelPile.pulledRow, the owner 2026-11-08) - whichever road found it."""
    return it if not it or not it.get('tid') or (store.get_task(int(it['tid'])) or {}).get('Status') not in ('done', 'dropped') else it | {'closed': True}


def batch_item(store, key: str) -> dict | None:
    """The fyi batch as ONE item, so words said about it land on something. next_item could not
    resolve a `fyis:` key at all, so after a batch came out "next", "done" and "not ours" were dead
    until a button was clicked (the 2026-09-03 break test)."""
    if not key or not key.startswith('fyis:'): return None
    want = [k for k in key[5:].split(',') if k]
    have = {alias: i for i in build(store, keep_surfaced=True, keys=want)['items']
            for alias in [i['key'], *i.get('aliases', [])]}
    seen = set()
    got = [have[k] for k in want if k in have
           and not (have[k]['key'] in seen or seen.add(have[k]['key']))]
    if not got: return None
    return _present_one(store, _item(key, 'fyis', 'fyi', f"{len(got)} fyi", who='', when=got[0].get('when'), since=got[0].get('since'),
                                     channel=got[0].get('channel'), why='people told you things; nothing to do',
                                     items=[dict(i) for i in got], members=[i['key'] for i in got]))


def batchable(item: dict) -> bool:
    """Does this row read in an FYI batch? An idea has things to do - make it a task, hand it on, let it go - so it is walked alone."""
    return item.get('lane') == 'fyi' and item.get('kind') != 'idea'


# a task's status in the owner's words - "in_progress general task you asked about" was the line under a task opened by name
STATUS_SAYS = {'open': 'Open', 'in_progress': 'In progress', 'waiting': 'Waiting on someone', 'blocked': 'Stuck',
               'review': 'Waiting for your yes', 'done': 'Done', 'dropped': 'Let go'}


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
        # Asked for by id, not fished out of 500 built rows (0.7-1.2 s a look-up, twice a turn). The window first so a
        # task with recent mail speaks through the same row as before; past it, its newest row anywhere in the history.
        row = next(iter(store.feed(limit=1, days=FEED_DAYS, task_id=tid) or store.feed(limit=1, days=3650, task_id=tid)), None)
        if row:
            got = from_feed(store, [row | {'Category': 'info' if row.get('Category') in _QUIET else row.get('Category')}])
            if got: return shut(store, _present_one(store, got[0] | {'lane': got[0]['lane'] if got[0]['lane'] != 'fyi' else 'asked'}))
        return shut(store, _present_one(store, _item(f'task:{tid}', 'task', 'asked', task.get('Title'), when=task.get('UpdatedAt') or task.get('CreatedAt'), tid=tid,
                                               summary=agent_found(store, tid), why=f"{STATUS_SAYS.get(task.get('Status'), 'Open')} - you asked about it")))
    m = re.match(r'^(msg|report):(\d+)$', key or '')
    if not m: return None
    mid = int(m.group(2))
    row = next(iter(store.feed(limit=1, days=3650, ids=[mid])), None)   # any age: a Recent row older than a week is still that row
    if not row:                                  # a message the feed hides opens its thread's row, or its task (TQ-1293)
        shown, tid = store.shown_message_of(mid), (store.get_message(mid) or {}).get('TaskId')
        return item_for_key(store, f'msg:{shown}') if shown and shown != mid else item_for_key(store, f'task:{tid}') if tid else None
    items = from_feed(store, [row | {'Category': 'info' if row.get('Category') in _QUIET else row.get('Category')}])
    it = next((i for i in items if i.get('mid') == mid), None)
    if it and it['kind'] == 'fyi': it = it | {'lane': 'fyi', 'why': row.get('RouteReason') or it['why']}
    return shut(store, _present_one(store, it))


def message_item(store, key: str) -> dict | None:
    """A MESSAGE NAMED BY ITS OWN ID IS THAT MESSAGE (a colleague, 2026-11-03: a Search hit clicked put "…" on the canvas, then nothing, and
    "I can't find that one" in the chat): Search lists every message whatever became of it - skipped at the first sync, ignored, answered,
    sent, on a closed task - and item_for_key knows only the rows a Timeline would show. Those first, as they are; past them, the row read
    whatever its status and worded as itself, never judged against the rail's rules for what is news."""
    if (it := item_for_key(store, key)) or not (m := re.match(r'^(msg|report):(\d+)$', key or '')): return it
    mid = int(m[2])
    row = next(iter(store.feed(limit=1, days=36500, ids=[mid], every=True)), None)
    if not row: return None
    it = next((i for i in from_feed(store, [row], canonical=True) if i.get('mid') == mid), None)
    if it is None: return None
    if row.get('Direction') == 'out': it = it | {'lane': 'fyi', 'why': 'you sent this'}
    elif it['kind'] == 'fyi': it = it | {'lane': 'fyi', 'why': row.get('RouteReason') or it['why']}
    if row.get('TaskStatus') in ('done', 'dropped'): it = it | {'closed': True}
    return _present_one(store, it)


VERBS = ('surfaced', 'done', 'later', 'skip', 'ack')


def _task_ideas(store, tid: int) -> list:
    """The Advisor's open ideas ABOUT this task: tied to it (its `about`), or raised on a mail of it. The task's close settles
    `task:<n>` and nothing else, so an idea on its mail stood alone on the rail as 'asked' with the work it named already
    closed (real-AI walk, 2026-10-18). Closing is the owner's word on that work, written into the idea's own state."""
    mids = {r['MessageId'] for r in store.list_messages(tid)}
    def about(i):
        try: a = json.loads(i.get('ActionJson') or '{}')
        except ValueError: return False
        return a.get('tid') == tid or (a.get('mid') is not None and a['mid'] in mids)
    return [i['IdeaId'] for i in store.list_ideas() if i.get('Status') in ('open', 'snoozed') and about(i)]


def _idea_done(store, key: str, by: str):
    """Done on an Advisor idea's own row puts the IDEA down, not only the row: the rail wrote its own state and
    nothing else, so the Advisor went on reading the idea as open (I4, 2026-09-27). Not ours is a dismiss before this."""
    m, t = re.fullmatch(r'idea:(\d+)', str(key or '')), re.fullmatch(r'task:(\d+)', str(key or ''))
    try: ids = ([int(m.group(1))] if m else _task_ideas(store, int(t.group(1))) if t else
                store.processing_item_ideas(key) if str(key).startswith('processing:') else [])
    except Exception as e: logger.debug(f'the idea behind {key} was not read: {e}'); ids = []
    for i in ids:
        if (store.get_idea(i) or {}).get('Status') in ('open', 'snoozed'): store.set_idea_status(i, 'done', by)
    # ...and the owner's own Done ON THE IDEA ITSELF says what is worth bringing up (the 2026-11-01 audit: "What to bring up" stayed empty
    # while hundreds of ideas were put down this way - only Make a task and Dismiss taught it). Never one line per press: the model weighs
    # it against the lines already there (memorylines.teach); a personal one teaches nothing
    if m and by == 'owner' and (i := store.get_idea(int(m.group(1)))):
        from . import memorylines
        facts = f"The idea: {' '.join(str(i.get('Text') or '').split())[:400]}\nIts kind: {i.get('Kind') or 'idea'}\nThe owner: handled it (Done)"
        memorylines.teach_soon(store, 'idea_done', f"idea{i['IdeaId']}", facts, section='bring')

_SHOWING = contextvars.ContextVar('funnel_showing', default=None)


@contextlib.contextmanager
def showing(revisions):
    """Settles inside this put down what these cards showed ({key: view_revision}) - a phone pick carries the revision of
    the message it was pressed off, and the proposal it runs reaches settle() several calls down."""
    tok = _SHOWING.set(revisions or None)
    try: yield
    finally: _SHOWING.reset(tok)


SETTLE_TRIES = 3          # a settle the census lag refused, reconciled and tried again - mail can land between each


def settle(store, key: str, verb: str, by: str = 'owner', hours: float = None, note: str = None, *, expected_context=None, read: bool = False,
           shown=None, thread=None) -> dict:
    """The owner's word on one item. done: gone for good. later: back in `hours` (LATER_HOURS by
    default). skip: back tomorrow morning. surfaced: shown in this walk - and, with `read`, READ: once
    it has been put in the chat it leaves Unread (the owner, 2026-09-06). ack: an alert was seen.

    `shown` ({key: view_revision}) is the card the press was made on: its receipts cover what that card showed, and a
    message that landed after it was drawn stays unread. Without it, the card the rail last drew. `thread`: the mails folded under the row
    (its `thread`), from a caller holding it - else the rail's cache, which every settle empties (thread_of)."""
    if shown is None: shown = _SHOWING.get()
    if verb not in VERBS: raise ValueError(f'unknown verb: {verb}')
    if key.startswith('fyis:'):                                   # a batch: the verb lands on every member
        # ...and wakes the tabs ONCE. Each settle empties the pile cache and fires the live event
        # every open Assistant answers with a forced rebuild, so four fyi settled together set four
        # rebuilds of a 60-item pile racing each other in front of the Next that follows.
        # ...each member's folded thread taken BEFORE the first settle empties the cache it is read from: from the second row on, the mails
        # under it stayed unread and a "+3" row came back after the walk said it was done (2026-11-03)
        ks = [k for k in key[5:].split(',') if k]
        threads = {k: thread_of(store, k) for k in ks}
        with store.one_poke():
            out = [settle(store, k, verb, by, hours, note, expected_context=expected_context, read=read, shown=shown, thread=threads[k]) for k in ks]
        return {'key': key, 'verb': verb, 'until': (out[0] if out else {}).get('until')}
    # A MEETING IS WALKED LIKE A TASK (Q3, 2026-10-30): Next on it writes nothing and it leaves the rail by itself after its grace
    # minutes - it was held `later` until its start (2026-09-28), a row the walk skipped
    until, says = None, ''
    if verb == 'later' and until is None:
        back, says = later_until(store, hours=hours)
        until = back.strftime('%Y-%m-%d %H:%M:%S')
    if verb == 'skip':
        tomorrow = (datetime.now() + timedelta(days=1)).replace(hour=7, minute=0, second=0)
        until = tomorrow.strftime('%Y-%m-%d %H:%M:%S')
    kw = {'read': read, 'shown': shown} if expected_context is None else {'read': read, 'shown': shown, 'expected_context': expected_context}
    for tries in range(SETTLE_TRIES):
        try:
            store.set_funnel_state(key, verb, by, until, note, **kw); break
        except ValueError as e:
            # Mail landing mid-settle moves the membership census, and the owner was handed that sentence
            # verbatim while nothing moved - 27 items stayed in the pipe (the owner, 2026-09-07: "what does
            # this mean as well when I got it to clear the rest of what was left?"). It is the worker's lag,
            # not a refusal: do the very thing the message asks for, and settle again. A row that only just
            # landed is the same lag - its item is not built yet ("processing target is unavailable"): a report the
            # AI judge turned down stayed on the rail and its run was logged as failed (2026-10-01).
            # ...and AGAIN while it keeps landing: on a busy mailbox more mail arrived between the reconcile and the one retry, and the
            # morning digest - written and saved four minutes earlier - was logged as failed for its own row's settle (TQ-1251)
            if ('reconciled before settlement' not in str(e) and 'processing target is unavailable' not in str(e)) or tries == SETTLE_TRIES - 1: raise
            from . import processing_all
            processing_all.wait_settled(store)
            store.reconcile_processing_membership()
    if verb == 'done': _idea_done(store, key, by)
    # ...and an FYI row that speaks for its whole email thread settles the mails folded under it (processing_unread.fold_fyi_threads)
    for k in (thread_of(store, key) if thread is None else thread):
        # ...a folded mail settles alone: its own remembered thread (_THREADS) names the row above it again, and mails on one thread settled
        # each other over and over - the walk table's world took 0.6s, then 1, 3, 10, 48, 300s (CI, 2026-11-04)
        try: settle(store, k, verb, by, hours, note, read=read, thread=())
        except Exception as e: logger.debug(f'funnel: {k} under {key} not settled - {e}')
    invalidate()
    # BULK PROCESSING: an item leaving the head is what pays for the next one to be judged - triage
    # is spent as the owner makes room, not 300 times on arrival (rank.py). `later` counts: it holds
    # the ITEM, never the queue behind it (the owner, 2026-09-18: "later should open the slot").
    # A bare `surfaced` does not - it was shown, not dealt with, and the head is still full.
    if verb in ('done', 'later', 'skip') or (verb == 'surfaced' and read):
        try:
            from . import rank
            if rank.any_rank(store): rank.top_up(store, 1)
        except Exception as e:
            logger.debug(f'the ranked queue did not top up: {e}')
    return {'key': key, 'verb': verb, 'until': until, **({'says': says} if says else {})}


def later_until(store, now: datetime = None, hours: float = None) -> tuple:
    """When Later brings it back, and the sentence that says so. Three hours on - unless the calendar shows her in
    meetings: then five minutes after the run of them she is in now, or the one the three hours would land in (the
    owner could only say "later" and get it back mid-call, 2026-10-06). Today's meetings as already read, never a live
    calendar call in front of a press; no calendar, plain hours."""
    from .remind import agenda, busy_run, clock, AFTER_MIN
    now = now or datetime.now()
    back = now + timedelta(hours=hours or LATER_HOURS)
    events = agenda(store) if not hours else []
    run = busy_run(events, now + timedelta(minutes=ALERT_MIN)) or busy_run(events, back)
    if run and run[0] + timedelta(minutes=AFTER_MIN) > now:
        back = run[0] + timedelta(minutes=AFTER_MIN)
        day = '' if back.date() == now.date() else 'tomorrow ' if back.date() == (now + timedelta(days=1)).date() else f"{back:%a} "
        return back, f"You're in meetings until {clock(run[0])}. I'll bring it back {day}at {clock(back)}."
    day = '' if back.date() == now.date() else 'tomorrow '
    return back, f"I'll bring it back {day}at {clock(back)}."


def reset_walk(store):
    """A new chat. Read stays read - a mail you saw yesterday is not new again because the conversation is - but an alert put down in
    the old chat may speak once more in this one, and the walk starts again from the top (railwalk.reset; the Walk button's start)."""
    # ...but a notice the owner put down stays down: a new chat does not raise a finished agent again (PW-166)
    for k, st in store.funnel_states().items():
        if k.startswith('notice:') and st.get('Status') == 'ack': store.clear_funnel_state(k)
    store.clear_funnel_states(('ack',))
    from . import railwalk
    railwalk.reset(store)
    invalidate()


def alerts(store, items: list = None) -> list:
    """What interrupts the conversation, whatever it is on: a meeting inside fifteen minutes and an
    agent that just asked. Each once - acknowledged alerts stay quiet until the fact changes."""
    items = items if items is not None else build(store)['items']
    states = store.funnel_states()
    out = []
    for i in items:
        if i.get('surfaced'): continue                                 # already on, or past, the table
        if i['kind'] == 'meeting' and not _not_yet(i):
            when = 'is starting now' if i['mins'] <= 0 else f"starts {until_m(i['mins'])}"
            out.append({'key': f"alert:{i['key']}", 'item': i['key'], 'kind': 'meeting', 'lane': i['lane'],
                        'text': f"{i['title']} {when}" + (f" with {i['who']}" if i.get('who') else '')})
        # ...an agent WAITING ON YOU. One merely working was pushed too - "is working on it, nothing for you there now", twice
        # a minute apart in two wordings (2026-09-29 audit) - an interruption to say there is nothing to do
        elif i['kind'] == 'agent' and i['lane'] == 'blocked':
            out.append({'key': f"alert:{i['key']}", 'item': i['key'], 'kind': 'agent', 'lane': i['lane'], 'asking': bool(i.get('asking')),
                        'text': f"{i.get('why') or agent_says('parked', i.get('agent') or task_kinds.SHOWN)} ({i.get('ref') or i['title']})"})
        elif i['lane'] == 'asked' and i['kind'] in ('asked', 'todo') and i.get('who'):
            out.append({'key': f"alert:{i['key']}", 'item': i['key'], 'kind': 'asked', 'lane': 'asked', 'text': f"{i['who']} asked you: {i['title']}"})
        elif i['lane'] in ('time', 'approve') and i['kind'] != 'meeting':      # a meeting further out is not yet news
            # important things waiting: the page shows this only while the owner is on something lesser
            who = f"{i['who']}'s " if i.get('who') else ''
            what = ('reply is waiting for your yes' if i['kind'] == 'review' else 'proposed action is waiting for your yes' if i['kind'] == 'action'
                    else f"urgent: {i['title']}")
            out.append({'key': f"alert:{i['key']}", 'item': i['key'], 'kind': i['kind'], 'lane': i['lane'], 'text': f"{who}{what}"})
    bands = {i['key']: _band(i) for i in items}
    return ([a | {'order_band': bands.get(a['item'], 3)} for a in out
             if (states.get(a['key']) or {}).get('Status') != 'ack']
            + notices(store, states))                                  # the watcher's own, kept until Open or Later


def desk_alerts(alerts_: list) -> list:
    """The by-the-way lines the DESKTOP draws: all but an agent's question (the owner, 2026-10-21: "general agent question should only
    be once on the canvas ... save 'The agent asked' for whatsapp"). The question is in its Agent work pane's answer box; the phone,
    which has no box, still says the agent asked (remote_assistant.push_alerts reads the pile's own alerts)."""
    return [a for a in alerts_ or [] if not (a.get('kind') == 'agent' and a.get('asking'))]


def more_urgent(items: list, current_key: str = None) -> list:
    """What waits in a promoted lane while the owner is on something lesser - for the assistant to
    mention in a clause, and for the page to raise as a by-the-way."""
    cur = next((i for i in items if i['key'] == current_key), None)
    band = _band(cur) if cur else 3
    return [i for i in items if not i.get('surfaced') and not i.get('settling')
            and not _not_yet(i) and _band(i) < band and i['key'] != current_key]


def summary(items: list, coming: bool = True) -> str:
    """One line for the concierge's prompt: how much is left and of what. `coming` names the next
    few - left OUT when one item is on the table, so a small model cannot wander off to them."""
    if not items: return 'THE PIPE IS EMPTY - nothing else needs the owner right now.'
    parts = [f"{n} {LANE_COUNTED[l]}" for l in LANES if (n := sum(1 for i in items if i['lane'] == l))]
    nxt = [i for i in items if not i.get('settling')][:3] if coming else []
    return (f"LEFT IN THE PIPE: {len(items)} - {', '.join(parts)}."
            + (' Coming next: ' + '; '.join(f"{i['who'] + ' - ' if i.get('who') else ''}{i['title']} ({lane_word(i)}{', shown already, still waiting' if i.get('surfaced') else ''})" for i in nxt) if nxt else ''))
