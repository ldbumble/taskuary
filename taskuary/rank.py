"""Bulk processing - rank it, don't clear it.

A worker clears the mailbox: every task is worked in arrival order until the queue is empty.
An executive is cc'd on most of it, and what matters is how much each item deserves attention
RELATIVE to the others. So a connector can be switched from `clear` (today's behaviour) to
`rank`: its coding tasks stop racing for a session and instead enter one value-ordered queue.
The top K (K = auto_sessions, the same "agents at once" the floor shows) are worked; when one
finishes the highest-valued waiting task slides in; new arrivals re-rank the queue rather than
join its tail. Nothing is dropped - a low value waits, it does not vanish - and the owner can
pin a card to the top or push it back.

Value is two layers, and the split is the point:
  floor()  - deterministic, from what the funnel already knows (addressed to you or cc'd, how
             many people, whether a colleague has replied, urgency, who the author is on a code
             host). Runs on everything, costs nothing, and is never shown as a number: the card
             shows the WORDS it came from.
  rank()   - one small listwise call, and its order IS the rank. Ranking is cheap where
             classifying is not: forty subjects in one call, not forty calls. Debounced, and
             the floor is what answers when no brain is configured.

Two queues are ranked, by the same rule and by two functions:
  rank_pending() - the arrivals waiting to be TRIAGED. Only the head of it is judged, and a
                   slot opens as the owner settles one, so 300 pull requests cost a handful
                   of calls instead of 300. It reads the raw arrival: there is no task yet.
  rerank()       - the tasks waiting for an AGENT, ordered by the same rule.
"""
import json, re, threading, time
from datetime import datetime
from loguru import logger

from .store import task_ref

BASE = 0.5
HEAD = 40                 # how many of the queue the rerank call sees
RERANK_EVERY = 60         # seconds between rerank calls - arrivals in between ride on the floor
PIN, LATER = 1.0, 0.05    # what the owner's two buttons set
_TEAM = ('OWNER', 'MEMBER', 'COLLABORATOR')
_ASSOC = re.compile(r'association: ([A-Z_]+)\]', re.I)
_TYPES = {'email': ('outlook', 'gmail', 'imap')}   # channel -> the connector types behind it
HEAD_JUDGED = 4           # how many of the ranked pool are TRIAGED at once - the rest wait, in order
HEAD_RANGE = (1, 20)
RANK_BATCH = 40           # arrivals per listwise ranking call


def head_size(store) -> int:
    """How many ranked arrivals are judged at once. The owner's, clamped: a 0 would judge nothing
    and a 500 would spend the whole saving this exists to make."""
    lo, hi = HEAD_RANGE
    try: n = int(str(store.get_settings().get('bulk_head') or HEAD_JUDGED).strip())
    except (AttributeError, TypeError, ValueError): return HEAD_JUDGED
    return max(lo, min(hi, n))


def build_rank_llm(store):
    """The ranking brain. Its OWN seam, because ranking is not triage: a small prompt over subjects,
    no soul, no learned doc, no notes, no images - see RANK_SYSTEM."""
    from .llm import build_llm
    return build_llm(store)


def mode_for(store, msg_row: dict) -> str:
    """'clear' or 'rank' - the connector the message came through decides. Resolution mirrors
    ingest.source_rules: the message's own source row names its connector, else the channel's
    type-named connector."""
    if not msg_row: return 'clear'
    ch = msg_row.get('Channel')
    src = next((s for s in store.list_sources(active_only=False)
                if s.get('Channel') == ch and s.get('Address') == msg_row.get('SourceName')), None)
    # a channel is not a connector type: 'email' is outlook OR gmail OR imap, so without a source
    # row to name it, any active mail connector in rank mode ranks the mail
    cands = ([store.get_connector(src['ConnectorId'])] if src and src.get('ConnectorId')
             else [c for t in _TYPES.get(ch, (ch,)) for c in store.connectors_by_type(t)])
    for c in cands:
        try:
            if c and c.get('Active') and json.loads(c.get('ConfigJson') or '{}').get('bulk') == 'rank': return 'rank'
        except ValueError: continue
    return 'clear'


def any_rank(store) -> bool:
    """Is any connector in rank mode? Decides whether the Timeline shows the funnel at all."""
    for c in store.list_connectors():
        try:
            if c.get('Active') and json.loads((store.get_connector(c['ConnectorId']) or {}).get('ConfigJson') or '{}').get('bulk') == 'rank': return True
        except ValueError: continue
    return False


def floor(store, task: dict, msg_row: dict = None, mine=()) -> tuple:
    """(value in [0,1], why) from what is already on file. The words are the deliverable - the
    number only orders the pile."""
    from .ingest import others_on_thread
    from .triage import addressed_to_you
    v, why = BASE, []
    if (task or {}).get('Priority') == 'urgent': v += 0.4; why.append('urgent')   # an escalate-policy sender outranks any ordinary signal
    if (task or {}).get('Kind') == 'coding': v += 0.05
    m = msg_row or {}
    rec = json.loads(m.get('RecipientsJson') or 'null') or {}
    how = addressed_to_you({'source_name': m.get('SourceName'), 'to': rec.get('to'), 'cc': rec.get('cc')}, mine)
    n = len(rec.get('to') or []) + len(rec.get('cc') or [])
    if how == 'to': v += 0.2; why.append('to you')
    elif how == 'cc': v -= 0.15; why.append('cc')
    elif how == 'not named': v -= 0.1; why.append('via a group')
    if n > 8: v -= 0.1; why.append(f'{n} people')
    if m.get('ConversationId'):
        th = others_on_thread(store, {'conversation_id': m.get('ConversationId'), 'subject': m.get('Subject'),
                                      'from_email': m.get('FromEmail'), 'from_name': m.get('FromName'),
                                      'source_name': m.get('SourceName')}, mine)
        if th.get('others_replied'): v -= 0.2; why.append('colleague replied')
    if m.get('Channel') == 'github':
        a = _ASSOC.search(str(m.get('BodyText') or '')[:200])
        assoc = (a.group(1) if a else 'NONE').upper()
        if assoc in _TEAM: v += 0.15; why.append('team member')
        elif assoc == 'CONTRIBUTOR': v += 0.05; why.append('contributor')
        else: v -= 0.2; why.append('stranger')
        why.append('pull request' if 'pull request by' in str(m.get('BodyText') or '')[:40].lower() else 'issue')
    if not why: why.append('nothing special about it')
    return max(0.0, min(1.0, round(v, 3))), ' · '.join(why)


def aged(value: float, created_at: str) -> float:
    """A small boost per day waited so nothing starves at the bottom - capped, so it never
    outranks something that matters."""
    try: days = (datetime.now() - datetime.fromisoformat(str(created_at)[:19])).total_seconds() / 86400
    except ValueError: return value
    return min(1.0, value + min(0.1, 0.02 * max(0.0, days)))


RERANK_SYSTEM = (
    'You order a queue of work items by how much attention they deserve from the owner, most first. '
    'Weigh: is the owner asked directly or merely copied; has a colleague already replied; is it '
    'urgent; how many people are on it; on code hosts, who the author is. Output ONLY JSON: '
    '{"order": [{"ref": "TQ-nnnn", "why": "<six words at most>"}...]} covering every item once.')

_last = {'at': 0.0}
_lock = threading.Lock()


def rerank(store, force: bool = False) -> int:
    """One listwise call over the head of the ranked queue; the model's position is blended
    half-and-half with the floor. Returns how many rows were updated. Debounced - a burst of
    arrivals costs one call, not one each."""
    if not force and time.time() - _last['at'] < RERANK_EVERY: return 0
    if not _lock.acquire(blocking=False): return 0
    try:
        _last['at'] = time.time()
        qs = [q for q in store.queued_dispatches() if q.get('Value') is not None][:HEAD]
        if len(qs) < 2: return 0
        from .llm import build_llm
        llm = build_llm(store)
        if not llm: return 0
        items = []
        for q in qs:
            t = store.get_task(q['TaskId']) or {}
            items.append(f"{task_ref(q['TaskId'])} | {str(t.get('Title') or '')[:90]} | signals: {q.get('Why') or ''} | "
                         f"{str(t.get('Summary') or '')[:160]}")
        out = llm(RERANK_SYSTEM, 'Items:\n' + '\n'.join(items), max_tokens=900)
        j = json.loads(re.sub(r'^```(json)?|```$', '', (out or '').strip(), flags=re.M))
        order = [str(o.get('ref') or '') for o in j.get('order') or []]
        whys = {str(o.get('ref') or ''): str(o.get('why') or '')[:60] for o in j.get('order') or []}
        n, k = 0, len(order)
        for q in qs:
            ref = task_ref(q['TaskId'])
            if ref not in order: continue
            model = 1 - order.index(ref) / max(1, k - 1) if k > 1 else 1.0
            base = float(q.get('Floor') if q.get('Floor') is not None else q['Value'])
            # the model's position IS the value. Blending half the floor into it let a handful of
            # deterministic signals outvote the judgement they were only ever standing in for.
            store.set_dispatch_value(q['TaskId'], round(model, 3),
                                     (q.get('Why') or '').split(' → ')[0] + (f" → {whys[ref]}" if whys.get(ref) else ''), floor_=base)
            n += 1
        return n
    except Exception as e:
        logger.debug(f'rerank skipped: {e}'); return 0
    finally:
        _lock.release()


RANK_SYSTEM = (
    'You order ARRIVALS by how much attention they deserve from the owner, most first. Nothing here '
    'has been read yet - you see only what the arrival itself carries. Weigh: is the owner asked '
    'directly or merely copied; how urgent the subject sounds; on code hosts, who the author is '
    '(a team member outranks a stranger). Output ONLY JSON: '
    '{"order": [{"ref": "m<id>", "why": "<six words at most>"}...]} covering every item once.')


def _arrival_line(r: dict) -> str:
    """What the ranking call is given about one arrival. There is no task yet, so no Title and no
    Summary exist - only the header the message came in with."""
    who = r.get('FromName') or r.get('FromEmail') or ''
    bits = [f"m{r['MessageId']}", str(r.get('Subject') or '(no subject)')[:110], f"{who} \u00b7 {r.get('Channel') or ''}"]
    if r.get('Channel') == 'github':
        a = _ASSOC.search(str(r.get('BodyText') or '')[:200])
        bits.append(f"author: {(a.group(1) if a else 'NONE').lower()}")
    return ' | '.join(bits)


def rank_pending(store, force: bool = False) -> int:
    """Rank what is waiting to be JUDGED, before any of it is. One listwise call over the batch -
    forty subjects in one call, never forty calls - and the floor when there is no brain to ask.

    This is the whole point of bulk mode: triage is the expensive step, so it must be spent on the
    items that deserve it, which means something has to order them first, cheaply."""
    if not force and time.time() - _last['at'] < RERANK_EVERY: return 0
    if not _lock.acquire(blocking=False): return 0
    try:
        _last['at'] = time.time()
        rows = [r for r in store.pending_triage(RANK_BATCH) if mode_for(store, r) == 'rank']
        if not rows: return 0
        from .ingest import owner_addresses
        mine = owner_addresses(store)
        # the floor first, so a cold start (or an install with no AI) still has a sane order
        for r in rows:
            v, why = floor(store, {}, r, mine)
            store.set_message_rank(r['MessageId'], v, why, 'rank')
        llm = build_rank_llm(store)
        if not llm or len(rows) < 2: return len(rows)
        try:
            out = llm(RANK_SYSTEM, 'Arrivals:\n' + '\n'.join(_arrival_line(r) for r in rows), max_tokens=900)
            j = json.loads(re.sub(r'^```(json)?|```$', '', (out or '').strip(), flags=re.M))
            order = [str(o.get('ref') or '') for o in j.get('order') or []]
            whys = {str(o.get('ref') or ''): str(o.get('why') or '')[:60] for o in j.get('order') or []}
            k = len(order)
            for r in rows:
                ref = f"m{r['MessageId']}"
                if ref not in order: continue
                # the MODEL's position IS the rank here. The floor is the fallback, not half of it:
                # what deserves attention is a judgement, and a handful of deterministic signals
                # cannot make it (the owner, 2026-09-18: "rank has to be ai").
                store.set_message_rank(r['MessageId'], round(1 - order.index(ref) / max(1, k - 1), 3) if k > 1 else 1.0,
                                       whys.get(ref) or (store.get_message(r['MessageId']) or {}).get('RankWhy') or '', 'rank')
        except Exception as e:
            logger.debug(f'the ranking call did not answer, the floor stands: {e}')
        return len(rows)
    finally:
        _lock.release()


def waiting(store) -> dict:
    """What is ranked and still waiting to be judged - the rail's "296 up next". A count and the
    subjects, straight off the arrivals: looking at them costs no model call."""
    rows = [r for r in store.pending_triage(500, ranked=True) if mode_for(store, r) == 'rank']
    return {'count': len(rows),
            'items': [{'mid': r['MessageId'], 'subject': r.get('Subject') or '(no subject)',
                       'who': r.get('FromName') or r.get('FromEmail') or '', 'channel': r.get('Channel') or '',
                       'value': r.get('RankValue'), 'why': r.get('RankWhy') or '', 'when': r.get('SentAt')}
                      for r in rows]}


def top_up(store, n: int = 1) -> int:
    """A slot opened - judge the next most valuable arrivals. Every settling verb opens one, `later`
    included: it holds the ITEM, it does not hold the queue behind it (the owner, 2026-09-18)."""
    from . import ingest
    return ingest.drain(store, limit=max(0, int(n)), wait=False)


def enqueue(store, tid: int, agent: str) -> dict:
    """Put a task into the ranked queue with its floor value. The caller drains afterwards."""
    from .ingest import owner_addresses
    t = store.get_task(tid) or {}
    msgs = store.list_messages(tid)
    v, why = floor(store, t, msgs[0] if msgs else None, owner_addresses(store))
    store.enqueue_dispatch(tid, None, agent, 'ranked with the rest of the queue', value=v, why=why)
    store.add_comment(tid, 'router', 'agent', f'Ranked: {why}. It starts when it is the most valuable thing waiting and a slot is free.')
    return {'value': v, 'why': why}


def funnel(store) -> dict:
    """What the Timeline's funnel bar shows: who is being worked, what waits and in what order."""
    from . import terminal as term
    from .ingest import auto_sessions
    working = [{'tid': t['taskId'], 'ref': task_ref(t['taskId']), 'agent': t.get('agent') or t.get('label'), 'idle': t.get('idle'),
                'title': (store.get_task(t['taskId']) or {}).get('Title') or ''}
               for t in term.live_sessions() if t.get('taskId')]
    seen = {w['tid'] for w in working}
    for r in store.running_runs():
        if r.get('TaskId') and r['TaskId'] not in seen:
            working.append({'tid': r['TaskId'], 'ref': task_ref(r['TaskId']), 'agent': r.get('AgentName'), 'idle': 0,
                            'title': (store.get_task(r['TaskId']) or {}).get('Title') or ''})
    queued = []
    for q in store.queued_dispatches():
        t = store.get_task(q['TaskId']) or {}
        if t.get('Status') not in ('open', 'in_progress'): continue
        queued.append({'tid': q['TaskId'], 'ref': task_ref(q['TaskId']), 'title': t.get('Title') or '',
                       'value': q.get('Value'), 'why': q.get('Why') or q.get('Reason') or '',
                       'behind': task_ref(q['BehindTaskId']) if q.get('BehindTaskId') else None, 'since': q.get('CreatedAt')})
    return {'mode': 'rank' if any_rank(store) else 'clear', 'width': auto_sessions(store), 'working': working, 'queued': queued}
