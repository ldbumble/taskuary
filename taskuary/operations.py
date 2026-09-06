"""Shared operations: a proposal, its confirmation, one execution, and what it taught (PW-129 to PW-134).

Every owner action used to be its own endpoint doing its own thing: the same correction was written
five ways, a double click ran an action twice, and what the owner and the assistant said about an
item lived only in the browser. An action is now a PROPOSAL - immutable id, exact target and
parameters, the context revision it was judged on, a confirmation version that edits bump - and
EXECUTION is one shared path: a repeated confirmation returns the first receipt without running
again, a stale version or changed context is refused for review, a failure is reported as a failure
and can be retried, and a success that differs from what triage said is recorded as correction
EVIDENCE keyed to the operation. Evidence informs fresh triage (it rides into the classifier beside
the owner's notes); it is not a memory note, not a rule and never a sender exclusion - those have
their own confirmed handlers. Discussion about a source item is kept against the item and travels
onto the task it later becomes, per item, never onto its batch siblings.
"""
import contextlib, hashlib, json, threading, uuid
from datetime import datetime
from loguru import logger

# kind -> (target kind, required parameters, how to read "what the owner made of it" for the correction
# comparison: a fixed word, 'kind' for the parameter of that name, or None when the action is never a
# correction - deferring, completing, reopening and excluding are decisions about the item, not about
# triage's reading of it)
KINDS = {
    'task.create_from_message': ('message', ('kind',), 'kind'),
    'dispatch.prepare':         ('task', ('kind',), 'kind'),
    'task.set_kind':            ('task', ('kind',), 'kind'),
    'message.file':             ('message', (), 'dismissed'),
    'task.not_a_task':          ('task', (), 'dismissed'),
    'message.reply':            ('message', (), 'reply'),
    'task.complete':            ('task', (), None),
    'task.reopen':              ('task', (), None),
    'task.defer':               ('task', ('until',), None),
    'preference.exclude_sender': ('message', ('scope',), None),
    # ...and what the assistant's chat can put in front of the owner (concierge.PROPOSALS, PW-123)
    'task.create_from_text':    ('text', ('kind', 'text'), None),
    'message.archive':          ('message', (), 'dismissed'),
    'item.settle':              ('item', ('key', 'verb'), None),
    'review.approve':           ('review', (), None),
    'agent.answer':             ('task', ('text',), None),
    'agent.stop':               ('task', (), None),
    'report.rerun':             ('source', (), None),
    'memory.remember':          ('memory', ('note',), None),
    'task.split':               ('task', ('text',), None),
    'pipe.clear':               ('pipe', ('text',), None),
    'task.setup':               ('text', ('text',), None),
}
# triage's `task` and `general` are one answer for this comparison (work, no coder); `coding` is another
SAME = {frozenset(('task', 'general'))}
EVIDENCE_CAP = 5

_running = threading.local()


def _now(): return datetime.now().isoformat(sep=' ', timespec='seconds')


def _change(kind: str, params: dict) -> str | None:
    how = KINDS[kind][2]
    if how is None: return None
    if how != 'kind': return how
    k = str((params or {}).get('kind') or '').lower()
    return k if k in ('coding', 'general') else 'task'


def verdict_of_message(store, m: dict) -> tuple:
    """(what triage decided about this message, the route row that says so) - read the way the panel
    reads it: the newest route's reason, then the task's kind."""
    routes = store.message_routes(m['MessageId']) or []
    last = routes[-1] if routes else {}
    reason = str(last.get('Reason') or '')
    if 'triage: fyi' in reason: return 'fyi', last.get('RouteId')
    if 'triage: reply_only' in reason: return 'reply', last.get('RouteId')
    if m.get('TaskId'):
        kind = str((store.get_task(m['TaskId']) or {}).get('Kind') or '').lower()
        return (kind if kind in ('coding', 'general', 'task') else 'task'), last.get('RouteId')
    return '', last.get('RouteId')


def verdict_of_task(store, tid: int) -> tuple:
    t = store.get_task(tid) or {}
    kind = str(t.get('Kind') or '').lower()
    msgs = store.list_messages(tid)
    routes = store.message_routes(msgs[0]['MessageId']) if msgs else []
    return (kind if kind in ('coding', 'general', 'task') else ('task' if t else '')), (routes[-1].get('RouteId') if routes else None)


def _verdict(store, target_kind: str, target_id: int) -> tuple:
    if target_kind == 'message':
        m = store.get_message(target_id)
        return verdict_of_message(store, m) if m else ('', None)
    if target_kind == 'task': return verdict_of_task(store, target_id)
    return ('', None)


def context_revision(store, target_kind: str, target_id: int) -> str:
    """The substantive state of the target: which messages are on it and how each stands. A new
    message on the thread or the task changes it; a read mark or a re-render does not."""
    if target_kind == 'message':
        m = store.get_message(target_id) or {}
        rows = store.thread_messages(m.get('ConversationId'), m.get('Subject'), limit=500) if m.get('ConversationId') else [m]
        basis = [(r.get('MessageId'), r.get('Status'), r.get('TaskId')) for r in rows]
    elif target_kind == 'review':
        rv = store.get_review(target_id) or {}
        return context_revision(store, 'task', rv['TaskId']) if rv.get('TaskId') else ''
    elif target_kind != 'task': return ''              # a memory, a sweep, a report rerun: nothing to go stale against
    else:
        t = store.get_task(target_id) or {}
        basis = [(r.get('MessageId'), r.get('Status')) for r in store.list_messages(target_id)] + [t.get('Kind'), t.get('Status')]
    return hashlib.sha1(json.dumps(basis, default=str).encode()).hexdigest()[:16]


def message_revision(store, task_id: int) -> str:
    """The inbound message set of a task - which messages, in what state - and nothing else: a task's kind
    or status changing is not new context for a REPLY, a new inbound line is (PW-048/055); an FYI triage
    filed with nothing to do is not either (PW-240) - invalidation follows material change, never an arrival."""
    rows = [(m['MessageId'], m.get('Status')) for m in store.list_messages(task_id)
            if m.get('Status') not in ('context', 'history', 'skipped', 'filed') and str(m.get('Direction') or 'in') != 'out']
    return hashlib.sha1(json.dumps(rows, default=str).encode()).hexdigest()[:16]


def _public(op: dict) -> dict:
    try: params = json.loads(op.get('ParamsJson') or '{}')
    except ValueError: params = {}
    try: outcome = json.loads(op['OutcomeJson']) if op.get('OutcomeJson') else None
    except ValueError: outcome = None
    return {'id': op['OpId'], 'kind': op['Kind'], 'targetKind': op['TargetKind'], 'target': op['TargetId'], 'params': params,
            'version': op['Version'], 'status': op['Status'], 'outcome': outcome, 'error': op.get('Error'),
            'evidence': op.get('Evidence'), 'verdict': op.get('Verdict'), 'contextRevision': op.get('ContextRevision'),
            'actor': op.get('Actor'), 'createdAt': op.get('CreatedAt'), 'executedAt': op.get('ExecutedAt')}


def _check(kind: str, params: dict):
    if kind not in KINDS: raise ValueError(f'unknown operation: {kind}')
    missing = [k for k in KINDS[kind][1] if not (params or {}).get(k)]
    if missing: raise ValueError(f'{kind} needs {", ".join(missing)}')


def _processing_context(store, params):
    keys = str(params.get('key') or '')
    keys = keys[5:].split(',') if keys.startswith('fyis:') else [keys]
    result = {}
    with store._processing_read() as cur:
        from .processing_projection import processing_projection
        for key in keys:
            target = store._processing_read_target(cur, key)
            if target:
                iid = target[0]
                result[iid] = processing_projection(cur, iid)['context_revision']
            elif key.startswith('processing:'):
                raise ValueError('The proposed item is no longer available')
    return result


def propose(store, kind: str, target_id: int, params: dict = None, actor: str = 'owner') -> dict:
    """A proposal: validated before anything is written, judged against the target as it stands now."""
    params = dict(params or {}); _check(kind, params)
    if kind == 'item.settle' and store.processing_reads_active():
        params['processing_context'] = _processing_context(store, params)
    tk = KINDS[kind][0]
    verdict, route_id = _verdict(store, tk, target_id)
    oid = uuid.uuid4().hex[:12]
    store.add_operation({'OpId': oid, 'Kind': kind, 'TargetKind': tk, 'TargetId': int(target_id), 'ParamsJson': json.dumps(params),
                         'Actor': actor, 'ContextRevision': context_revision(store, tk, target_id), 'Version': 1, 'Status': 'proposed',
                         'Verdict': verdict, 'VerdictRouteId': route_id})
    return get(store, oid)


def get(store, op_id: str) -> dict | None:
    op = store.get_operation(op_id)
    return _public(op) if op else None


def revise(store, op_id: str, params: dict, actor: str = 'owner') -> dict:
    """An edit is a new confirmation version of the same proposal; the old confirmation is stale."""
    op = store.get_operation(op_id)
    if not op: raise ValueError('no such proposal')
    if op['Status'] not in ('proposed', 'error'): raise ValueError(f"a {op['Status']} proposal cannot be edited")
    params = dict(params or {}); _check(op['Kind'], params)
    if op['Kind'] == 'item.settle' and store.processing_reads_active():
        params['processing_context'] = _processing_context(store, params)
    store.update_operation(op_id, {'ParamsJson': json.dumps(params), 'Version': int(op['Version']) + 1, 'Actor': actor})
    return get(store, op_id)


def cancel(store, op_id: str, actor: str = 'owner') -> dict:
    op = store.get_operation(op_id)
    if not op: raise ValueError('no such proposal')
    if op['Status'] in ('proposed', 'error'): store.update_operation(op_id, {'Status': 'cancelled', 'Actor': actor})
    return get(store, op_id)


def _stale(op, why): return {**_public(op), 'status': 'stale', 'error': why, 'duplicate': False}


def execute(store, op_id: str, version: int, run, actor: str = 'owner') -> dict:
    """Confirm and carry out: once. `run` is the shared handler for this kind; the receipt is what it
    returned. The same confirmation again is the same receipt and no second effect."""
    op = store.get_operation(op_id)
    if not op: raise ValueError('no such proposal')
    if op['Status'] == 'cancelled': return {**_public(op), 'error': 'this proposal was cancelled', 'duplicate': False}
    if op['Status'] == 'done': return {**_public(op), 'duplicate': True}
    if int(version) != int(op['Version']):
        return _stale(op, f"the proposal was edited since (it is now version {op['Version']}) - confirm the current one")
    params = json.loads(op.get('ParamsJson') or '{}')
    if op['Kind'] == 'item.settle' and store.processing_reads_active():
        if 'processing_context' not in params or _processing_context(store, params) != params['processing_context']:
            return _stale(op, 'The item changed since this was proposed. Review it again before confirming.')
    if op.get('ContextRevision') and context_revision(store, op['TargetKind'], op['TargetId']) != op['ContextRevision']:
        return _stale(op, 'the context changed since this was proposed - review it again before confirming')
    _running.op = op_id
    try: outcome = run()
    except Exception as e:
        logger.warning(f'operation {op_id} ({op["Kind"]}) failed: {e}')
        store.update_operation(op_id, {'Status': 'error', 'Error': str(e)[:500], 'Actor': actor})
        return {**_public(store.get_operation(op_id)), 'duplicate': False}
    finally: _running.op = None
    store.update_operation(op_id, {'Status': 'done', 'OutcomeJson': json.dumps(outcome, default=str) if outcome is not None else None,
                                   'Error': None, 'ExecutedAt': _now(), 'Actor': actor})
    _evidence(store, op_id)
    return {**_public(store.get_operation(op_id)), 'duplicate': False}


def under_operation() -> bool:
    """True while a proposal is being carried out, so an entry point's own direct record is not written
    a second time on top of the operation's."""
    return bool(getattr(_running, 'op', None))


def record_direct(store, kind: str, target_id: int, params: dict, actor: str, outcome, verdict: str = None, route_id=None) -> dict | None:
    """An entry point that already carried the action out (a task-page button, the timeline) records
    the same operation and the same evidence the confirmation box would - one receipt per success."""
    if under_operation(): return None
    try:
        params = dict(params or {}); _check(kind, params)
        tk = KINDS[kind][0]
        if verdict is None: verdict, route_id = _verdict(store, tk, target_id)
        oid = uuid.uuid4().hex[:12]
        store.add_operation({'OpId': oid, 'Kind': kind, 'TargetKind': tk, 'TargetId': int(target_id), 'ParamsJson': json.dumps(params),
                             'Actor': actor, 'ContextRevision': context_revision(store, tk, target_id), 'Version': 1, 'Status': 'done',
                             'Verdict': verdict or '', 'VerdictRouteId': route_id, 'ExecutedAt': _now(),
                             'OutcomeJson': json.dumps(outcome, default=str) if outcome is not None else None})
        _evidence(store, oid)
        return get(store, oid)
    except Exception as e:
        logger.warning(f'operation record skipped ({kind} on {target_id}): {e}')
        return None


# ── correction evidence ─────────────────────────────────────────────────────────────────────────
def correction_for(store, op: dict) -> dict | None:
    """The owner's successful change against triage's verdict - or None when nothing was corrected:
    the same answer, an action that is not about the verdict, or no verdict on record."""
    try: params = json.loads(op.get('ParamsJson') or '{}')
    except ValueError: params = {}
    change, verdict = _change(op['Kind'], params), str(op.get('Verdict') or '')
    if not change or not verdict or change == verdict or frozenset((change, verdict)) in SAME: return None
    if op['TargetKind'] == 'message':
        m = store.get_message(op['TargetId']) or {}
        try: tid = (json.loads(op['OutcomeJson']) if op.get('OutcomeJson') else {}).get('taskId') or m.get('TaskId')
        except (ValueError, AttributeError): tid = m.get('TaskId')
        mid = op['TargetId']
    else:
        tid, msgs = op['TargetId'], store.list_messages(op['TargetId'])
        m = msgs[0] if msgs else {}
        mid = m.get('MessageId')
    from .routing import subject_topic
    return {'OpId': op['OpId'], 'MessageId': mid, 'TaskId': tid, 'Sender': (m.get('FromEmail') or '').lower() or None,
            'Topic': subject_topic(m.get('Subject') or '') or None, 'Verdict': verdict, 'VerdictRouteId': op.get('VerdictRouteId'),
            'Change': change, 'ContextJson': json.dumps({'subject': m.get('Subject'), 'sentAt': m.get('SentAt'), 'params': params})}


def _evidence(store, op_id: str):
    op = store.get_operation(op_id)
    c = correction_for(store, op)
    if c is None: store.update_operation(op_id, {'Evidence': 'none'}); return
    try:
        store.add_correction(c)
        store.update_operation(op_id, {'Evidence': 'recorded'})
    except Exception as e:
        # the action happened; the lesson is owed. Marked so recover_evidence writes it later without
        # repeating the action (PW-130)
        logger.warning(f'correction evidence for {op_id} not written yet: {e}')
        store.update_operation(op_id, {'Evidence': 'pending'})


def recover_evidence(store) -> int:
    n = 0
    for op in store.operations_pending_evidence():
        _evidence(store, op['OpId'])
        if (store.get_operation(op['OpId']) or {}).get('Evidence') == 'recorded': n += 1
    return n


def corrections(store, message_id: int = None, task_id: int = None, sender: str = None) -> list:
    return store.corrections(message_id=message_id, task_id=task_id, sender=sender)


def evidence_lines(store, msg: dict, cap: int = EVIDENCE_CAP) -> list:
    """Past corrections that bear on this message - same sender, or the same topic - worded as what
    happened, for the classifier to weigh (PW-131: evidence, not a rule)."""
    from .routing import subject_topic
    from .ingest import topic_hit
    sender, topic = str(msg.get('from_email') or '').lower(), subject_topic(msg.get('subject') or '')
    hits = store.corrections(sender=sender) if sender else []
    seen = {c['Id'] for c in hits}
    if topic:
        hits += [c for c in store.corrections(topic=topic) if c['Id'] not in seen]
        hits += [c for c in store.corrections(limit=50) if c['Id'] not in seen and c.get('Topic') and topic_hit(c['Topic'], msg.get('subject') or '')]
    out, done = [], set()
    for c in sorted(hits, key=lambda c: c['CreatedAt'], reverse=True):
        if c['Id'] in done: continue
        done.add(c['Id'])
        try: subj = (json.loads(c.get('ContextJson') or '{}').get('subject') or '')[:80]
        except ValueError: subj = ''
        out.append(f"{str(c['CreatedAt'])[:10]}: triage called \"{subj}\"{' from ' + c['Sender'] if c.get('Sender') else ''} {c['Verdict']}; "
                   f"the owner made it {c['Change']} (one correction, not a rule)")
        if len(out) >= cap: break
    return out


# ── discussion and history ─────────────────────────────────────────────────────────────────────
def discuss(store, actor: str, body: str, message_id: int = None, task_id: int = None, op_id: str = None) -> int:
    """One turn about an item, kept against the item (and its task when it has one) - not in the chat's
    retention window, not as a preference."""
    body = str(body or '').strip()
    if not body: raise ValueError('nothing to keep')
    if message_id and not task_id: task_id = (store.get_message(message_id) or {}).get('TaskId')
    return store.add_discussion({'MessageId': message_id, 'TaskId': task_id, 'Actor': actor, 'Body': body[:4000], 'OpId': op_id})


def link_discussion(store, task_id: int, message_ids: list) -> int:
    """An FYI became a task: what was said about THAT message travels onto the task - by identity, so a
    batch sibling's discussion never does."""
    return store.link_discussion(task_id, [int(x) for x in message_ids if x])


def discussion(store, task_id: int = None, message_id: int = None) -> list:
    return store.discussion(task_id=task_id, message_id=message_id)


_RANK = {'discussion': 0, 'operation': 1, 'correction': 2}


def history(store, task_id: int = None, message_id: int = None) -> list:
    """The durable record of an item: what was said, what was proposed and carried out (with its real
    outcome), and what it corrected - oldest first."""
    mids = set()
    if message_id: mids.add(int(message_id))
    if task_id: mids |= {m['MessageId'] for m in store.list_messages(task_id)}
    out = []
    for d in store.discussion(task_id=task_id, message_id=message_id):
        out.append({'type': 'discussion', 'at': d['CreatedAt'], 'actor': d['Actor'], 'body': d['Body'], 'messageId': d['MessageId'], 'id': d['Id']})
    for op in store.operations_for(task_id=task_id, message_ids=sorted(mids)):
        p = _public(op)
        out.append({'type': 'operation', 'at': op['CreatedAt'], **{k: p[k] for k in ('id', 'kind', 'params', 'version', 'status', 'outcome', 'error', 'actor')},
                    'executedAt': op.get('ExecutedAt')})
    for c in store.corrections(task_id=task_id, message_id=message_id):
        out.append({'type': 'correction', 'at': c['CreatedAt'], 'verdict': c['Verdict'], 'change': c['Change'], 'opId': c['OpId'], 'id': c['Id']})
    out.sort(key=lambda x: (str(x['at'] or ''), _RANK[x['type']], str(x.get('id') or '')))
    return out
