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
  rerank() - one listwise call to the triage brain over the head of the queue, blended in.
             Ranking is cheap where classifying is not: forty titles in one call, not forty
             calls. Debounced, optional, and falls back to the floor with no AI configured.
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
             else [store.get_connector_by_type(t) for t in _TYPES.get(ch, (ch,))])
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
            store.set_dispatch_value(q['TaskId'], round(0.5 * base + 0.5 * model, 3),
                                     (q.get('Why') or '').split(' → ')[0] + (f" → {whys[ref]}" if whys.get(ref) else ''), floor_=base)
            n += 1
        return n
    except Exception as e:
        logger.debug(f'rerank skipped: {e}'); return 0
    finally:
        _lock.release()


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
