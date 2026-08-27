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

def cosine(a, b):
    """Cosine similarity between two token lists (term-count vectors)."""
    ca,cb = Counter(a),Counter(b)
    if not ca or not cb: return 0.0
    dot = sum(ca[t]*cb[t] for t in ca.keys() & cb.keys())
    return dot / (math.sqrt(sum(v*v for v in ca.values())) * math.sqrt(sum(v*v for v in cb.values())))

# Signal weights and the attach threshold. A live thread match alone clears the bar by design;
# content-only matches need subject+body agreement.
WEIGHTS = {'thread': 1.0, 'subject': 0.45, 'sender': 0.15, 'body': 0.40}
ATTACH_THRESHOLD = 0.42

def score_candidate(msg, task):
    """Per-signal scores of one message against one task snapshot.

    Args:
        msg: dict with subject, from_email, body, conversation_id.
        task: dict with task_id, title, subjects (list), senders (list), person_ids (list), text (joined bodies),
              conversation_ids (list).
    Returns:
        dict of signal -> score in [0,1].
    """
    sig = {}
    sig['thread'] = 1.0 if msg.get('conversation_id') and msg['conversation_id'] in (task.get('conversation_ids') or []) else 0.0
    ms = norm_subject(msg.get('subject'))
    subs = [norm_subject(s) for s in (task.get('subjects') or [])] + [norm_subject(task.get('title'))]
    sig['subject'] = max([1.0 if ms and ms==s else cosine(tokens(ms), tokens(s)) for s in subs if s] or [0.0])
    same_handle = (msg.get('from_email') or '').lower() in {(e or '').lower() for e in (task.get('senders') or [])}
    same_person = bool(msg.get('person_id') and msg.get('person_id') in (task.get('person_ids') or []))
    sig['sender'] = 1.0 if same_handle or same_person else 0.0
    sig['body'] = cosine(tokens(msg.get('body')), tokens(task.get('text')))
    return sig

def route(msg, tasks, threshold=ATTACH_THRESHOLD):
    """Route a message against open-task snapshots.

    Args:
        msg: message dict (see score_candidate).
        tasks: list of task snapshot dicts.
        threshold: attach floor (configurable via hubSetting attach_threshold).
    Returns:
        dict: {decision: 'attach'|'create', task_id, score, reason, candidates:
               [{task_id, score, signals}] sorted best-first} - the full routing trail.
    """
    cands = []
    for t in tasks:
        sig = score_candidate(msg, t)
        total = min(1.0, sum(WEIGHTS[k]*v for k,v in sig.items()))
        # A brand-new email (no RE:/FW:, per is_reply) shouldn't attach to an old task on
        # mere subject/body similarity - only a real thread match keeps full weight.
        if msg.get('is_reply') is False and not sig['thread']: total = round(total * 0.6, 4)
        cands.append({'task_id': t['task_id'], 'score': round(total,4), 'signals': {k: round(v,4) for k,v in sig.items()}})
    cands.sort(key=lambda c: -c['score'])
    best = cands[0] if cands else None
    # The reason is read by a person on the timeline, so it says what happened in words. The
    # scores stay in `candidates` for anyone debugging the router - "0.31, attaching needs 0.42"
    # on every card told the owner nothing they could act on.
    if best and best['score'] >= threshold:
        why = ('same conversation thread' if best['signals']['thread'] else
               'reads like the same work' + (', from someone already on it' if best['signals']['sender'] else ''))
        return {'decision':'attach', 'task_id':best['task_id'], 'score':best['score'],
                'reason': f"attached: {why}", 'candidates':cands[:5]}
    near = f" (TQ-{best['task_id']:04d} came closest, not close enough to join)" if best and best['score'] >= threshold * 0.6 else ''
    return {'decision':'create', 'task_id':None, 'score':best['score'] if best else 0.0,
            'reason': f'new task - nothing similar already open{near}', 'candidates':cands[:5]}

# KIND decides who works the task, and 'coding' is the one that starts an agent on a
# checkout - so it has to mean "there is software in here", not "a word appeared". A single
# keyword in flowing prose used to be enough: a Teams message about someone's job scope
# ("I own the deployment system, production/uptime, and support") hit 'deploy' and became a
# CODING task with a CLI session opened on a repository. Prose is not a bug report.
#
# HARD = something only a real technical report contains. Any one of these is enough.
_CODE_HARD = re.compile(
    r'traceback \(most recent call last\)|stack ?trace|^\s+at [\w$.]+\(|'          # a trace
    r'\b[\w./-]+\.(py|js|jsx|ts|tsx|java|cs|go|rs|rb|php|sql|ya?ml|sh|ps1|css|html)\b|'   # a source file
    r'(github|gitlab|bitbucket)\.com/|\bpull request\b|\bmerge request\b|\bPR ?#\d+|'     # a repo
    r'\bhttp \d{3}\b|\b[45]\d{2} (error|response|status)\b|```', re.I | re.M)
# SOFT = words that DO show up in ordinary prose. Two of them together is a signal; one is
# somebody talking about their week.
_CODE_SOFT = ('bug', 'error', 'exception', 'crash', 'broken', 'regression', 'timeout',
              'deploy', 'endpoint', 'fix the', 'not working', 'fails', 'failing')
_ASKS = ('can you', 'could you', 'please send', 'let me know', 'would you mind', 'any chance')


def draft_task_fields(msg, urgent: bool = False, kind: str = None):
    """Title/summary/kind/priority for a task created from a message. `kind` routes the work:
    coding = an agent on a checkout, reply = the responder and Review, general = your list.
    Pass `kind` when the classifier named one (triage.classify_intent) - it read the whole
    message against TRIAGE.md's definition and outranks the keyword scan below, which is the
    fallback for a brain that did not say.

    `urgent` is DECIDED BY A RULE, never guessed here. Priority used to come from a keyword
    scan for urgent/asap/immediately/outage/down, which flagged mail nobody had called
    urgent: bare substrings, so every message carrying the "do not DOWNload attachments"
    external-mail banner came in urgent. A word in a footer is not a priority, and a
    priority every third task carries ranks nothing. Urgency is the owner's judgement about
    WHO is writing, so it lives in an escalate policy they can read and edit."""
    subj = norm_subject(msg.get('subject')) or (msg.get('body') or '')[:80] or 'untitled'
    body = (msg.get('body') or '').strip()
    head = subj + '\n' + body[:2000]           # a trace usually sits below the pleasantries
    low = head.lower()
    kind = (kind if kind in ('coding', 'general') else
            'coding' if _CODE_HARD.search(head) or sum(w in low for w in _CODE_SOFT) >= 2 else
            'reply' if body.rstrip().endswith('?') or any(w in low for w in _ASKS) else 'general')
    return {'title': subj[:300].capitalize(), 'summary': body[:1000], 'kind': kind,
            'priority': 'urgent' if urgent else 'normal'}
