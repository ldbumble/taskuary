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
    if best and best['score'] >= threshold:
        why = ('same conversation thread' if best['signals']['thread'] else
               'subject/body similarity' + (' + known sender' if best['signals']['sender'] else ''))
        return {'decision':'attach', 'task_id':best['task_id'], 'score':best['score'],
                'reason': f"attached: {why} (score {best['score']:.2f} >= {threshold})", 'candidates':cands[:5]}
    top = f" (closest open task: TQ-{best['task_id']:04d} at {best['score']:.2f}, attaching needs {threshold})" if best else ''
    return {'decision':'create', 'task_id':None, 'score':best['score'] if best else 0.0,
            'reason': f'new task - nothing similar already open{top}', 'candidates':cands[:5]}

def draft_task_fields(msg):
    """Title/summary/kind/priority for a task created from a message (heuristic v1)."""
    subj = norm_subject(msg.get('subject')) or (msg.get('body') or '')[:80] or 'untitled'
    body = (msg.get('body') or '').strip()
    low = (subj + ' ' + body[:500]).lower()
    kind = ('coding' if any(w in low for w in ('bug','error','stack trace','exception','deploy','endpoint','fix the','broken')) else
            'reply' if body.rstrip().endswith('?') or any(w in low for w in ('can you','could you','please send','let me know')) else 'triage')
    pri = 'urgent' if any(w in low for w in ('urgent','asap','immediately','outage','down')) else 'normal'
    return {'title': subj[:300].capitalize(), 'summary': body[:1000], 'kind': kind, 'priority': pri}
