"""Pure routing engine: decide whether an incoming message belongs to an existing task.

No DB, no network - operates on plain dicts so it is unit-testable offline and reusable
outside this repo. Signals (strongest first):
    thread   - same ConversationId as a message already on the task (near-certain match)
    subject  - normalized-subject token overlap with the task title/known subjects
    sender   - the sender already appears on the task
    body     - token-overlap (cosine on term counts) between body and task text
The decision keeps every candidate's per-signal scores so the "why" is fully replayable.
"""
import re, math
from collections import Counter

from . import kinds as task_kinds

# Common reply/forward prefixes stripped before subject comparison (incl. localized ones).
_SUBJ_PREFIX = re.compile(r'^\s*((re|fw|fwd|aw|sv|vs)\s*(\[\d+\])?\s*:\s*)+', re.I)
_TOKEN = re.compile(r'[a-z0-9]{2,}')
_STOP = {'the','and','for','you','are','not','with','this','that','have','from','was','were',
         'will','has','had','but','all','can','our','your','their','been','they','its','per',
         'any','out','get','let','who','him','her','she','his','one','two','when','what',
         'please','thanks','thank','regards','hello','sent','subject'}

def norm_subject(s): return _SUBJ_PREFIX.sub('', s or '').strip().lower()
def tokens(s): return [t for t in _TOKEN.findall((s or '').lower()) if t not in _STOP]

# The STANDING part of a subject line. "Resident Refund Request - Doe, Jane" is one
# recurring topic and one resident: the trailing " - <somebody>" changes with every mail, so it
# is not what the mail is ABOUT. Keeping it makes the name half the words - which puts a topic
# match on a knife edge and makes a hundred one-off subjects out of one piece of routine work.
_SUBJ_TAIL = re.compile(r'\s+[-–—]\s+[^-–—]{1,40}$')

def subject_topic(s, min_words=2):
    """'' when there is not enough of a subject left to be a topic at all."""
    norm = norm_subject(s)
    trimmed = _SUBJ_TAIL.sub('', norm).strip()
    for cand in (trimmed, norm):
        if len(tokens(cand)) >= min_words: return cand[:200]
    return ''

# the channels where a conversation id names a ROOM and not a topic (store.CHAT_CHANNELS is the
# same set; this module stays pure, so it keeps its own copy rather than importing the store)
CHAT_CHANNELS = {'teams', 'slack', 'telegram', 'whatsapp', 'discord', 'imessage'}
def first_line(body: str) -> str:
    """The first line with words on it - no rule about which words a line may open with. GREETING skipped
    "hi/hello/dear" lines and so skipped "Hi-res scans of the Q3 file are missing" too; triage's own title
    is the name of an ask (the owner, 2026-10-11: "Everything should be ai"), this is only its fallback."""
    return next((l.strip() for l in (body or '').splitlines() if l.strip()), '')[:120]

def cosine(a, b):
    """Cosine similarity between two token lists (term-count vectors)."""
    ca,cb = Counter(a),Counter(b)
    if not ca or not cb: return 0.0
    dot = sum(ca[t]*cb[t] for t in ca.keys() & cb.keys())
    return dot / (math.sqrt(sum(v*v for v in ca.values())) * math.sqrt(sum(v*v for v in cb.values())))

# Signal weights for ranking candidate tasks (reshape, context). route() and its attach threshold are gone
# (2026-10-11): ingest imported it and never called it - identity_route and triage's same_as decide joins.
#
# THE RULE FOR A THREAD WHOSE TASK HAS CLOSED - written down because it is easy to break by
# accident and the two halves look inconsistent until you see why they are not:
#   THEIR reply on a closed thread is NEW WORK. routing only ever sees open tasks
#   (store.snapshots), so it opens a new task and triage judges the ask afresh - a closed task is
#   a finished piece of work, and a thread that comes back to life is asking for another one.
#   YOUR reply on a closed thread is RECORD, not work. channels.ingest_own_message attaches it to
#   the closed task (store.task_for_conversation reads open and closed alike) so the chain keeps
#   the last thing said on it; it never reopens the task and never makes a new one.
# A chat room is neither: its conversation id names the ROOM, so the thread signal is only a
# candidate there and ingest.chat_continues decides whether the line joins (owner, 2026-09-02).
WEIGHTS = {'thread': 1.0, 'subject': 0.45, 'sender': 0.15, 'body': 0.40}

def score_candidate(msg, task):
    """Per-signal scores of one message against one task snapshot.

    Args:
        msg: dict with subject, from_email, body, conversation_id.
        task: dict with task_id, title, subjects (list), senders (list), text (joined bodies),
              conversation_ids (list).
    Returns:
        dict of signal -> score in [0,1].
    """
    sig = {}
    sig['thread'] = 1.0 if msg.get('conversation_id') and msg['conversation_id'] in (task.get('conversation_ids') or []) else 0.0
    ms = norm_subject(msg.get('subject'))
    subs = [norm_subject(s) for s in (task.get('subjects') or [])] + [norm_subject(task.get('title'))]
    sig['subject'] = max([1.0 if ms and ms==s else cosine(tokens(ms), tokens(s)) for s in subs if s] or [0.0])
    sig['sender'] = 1.0 if (msg.get('from_email') or '').lower() in {(e or '').lower() for e in (task.get('senders') or [])} else 0.0
    sig['body'] = cosine(tokens(msg.get('body')), tokens(task.get('text')))
    return sig

# NOTHING HERE SCANS FOR CODE ANY MORE. `_CODE_HARD` / `_CODE_SOFT` used to decide `kind` from
# the words in a message; 8b89e26a (2026-09-06) made an unnamed kind `general` outright and left
# the two patterns behind, referenced by nobody, with the docstring below still calling them "the
# keyword scan". They read as live for ten days - and they were the reason a pull request LOOKED
# handled here (`_CODE_HARD` matches `pull request` and `github.com/`) while every PR was in fact
# going to the assistant. Dead code that describes the behaviour you expect is worse than none:
# `kind` is the model's, against TRIAGE.md, and this file no longer has an opinion about it. (`_ASKS`, a dead
# phrase tuple beside them, went the same way on 2026-10-11.)


def draft_task_fields(msg, urgent: bool = False, kind: str = None):
    """Title/summary/kind/priority for a task created from a message. `kind` routes the work:
    coding = an agent on a checkout, reply = the responder and Review, general = the assistant's
    chat, task = the owner's own list with nothing working it.
    Pass `kind` when the classifier named one (triage.classify_intent): it read the whole message
    against TRIAGE.md's definition, and it is the ONLY thing that ever says `coding`. A kind
    nobody named falls to `reply` or `general` below - never to coding, because no coding session
    starts on a guess made here.

    `urgent` is DECIDED BY TRIAGE (its `urgent` verdict, 2026-09-25) or an escalate rule, never guessed here. Priority used to come from a keyword
    scan for urgent/asap/immediately/outage/down, which flagged mail nobody had called
    urgent: bare substrings, so every message carrying the "do not DOWNload attachments"
    external-mail banner came in urgent. A word in a footer is not a priority, and a
    priority every third task carries ranks nothing. Urgency is the owner's judgement about
    WHO is writing, so it lives in an escalate policy they can read and edit."""
    subj = norm_subject(msg.get('subject')) or (msg.get('body') or '')[:80] or 'untitled'
    body = (msg.get('body') or '').strip()
    # A CHAT's "subject" is the ROOM - "Teams chat with Priya", the WhatsApp group's name - which
    # every line in it shares, so titling tasks with it produced a board of identical rows naming
    # a person instead of a job. Triage's title replaces this (ingest); with none, the first line is the title.
    if str(msg.get('channel') or '').lower() in CHAT_CHANNELS: subj = first_line(body) or subj
    head = subj + '\n' + body[:2000]           # a trace usually sits below the pleasantries
    low = head.lower()
    # the last branch used to be 'general', back when general MEANT the owner's list. It means
    # the assistant's chat now, and a keyword scan that could not tell what this is has no
    # business opening one - `task` is the honest end of a guess: it lands on the owner's list
    # and waits, which is what the old word did.
    # A kind nobody named is TASK - the owner's list, where nothing starts on a guess (the owner,
    # 2026-09-23: "if a triage is unknown ... it should just be task. I don't like coding by default";
    # it was GENERAL from 2026-09-05, PW-067). `coding` and `general` are the classifier's explicit
    # calls; a plain question is a reply.
    # ...and never a guess from punctuation (the owner, 2026-09-25: "? never decides anything"): a question mark
    # used to turn a task triage named without a kind into a reply with a drafted answer. Triage's reply_only is
    # the only road to a reply.
    kind = task_kinds.triage_kind(kind)
    # THE ASK, NOT THE EMAIL. This stored body[:1000], so a task's own summary was the greeting, the
    # signature, the legal footer and the quoted thread underneath - 5,998 characters of Paula's
    # reply, of which the ask was the first sentence (the owner, 2026-09-14: "why is the whole email
    # showing up not the specific task?"). The hand-promote road was fixed this way on 2026-09-10
    # (ingest.promote); the automatic one kept the raw body. A verdict that names its own summary
    # still outranks this - it is the fallback for one that does not, and for triage switched off.
    # ...and the CHAIN under it is not the ask either: strip_boilerplate reads the tail of a body,
    # which on a forwarded mail belongs to whoever was quoted (own_words, TQ-0665).
    from .triage import own_words
    return {'title': subj[:300].capitalize(), 'summary': own_words(body)[:1000], 'kind': kind,
            'priority': 'urgent' if urgent else 'normal'}
