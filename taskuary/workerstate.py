"""One worker status model, fed by explicit events, read by every surface (PW-222, PW-226, PW-227, PW-137, PW-139, PW-141).

A session's status was read off its screen: a bare prompt meant "stopped and waiting on you", a quiet
terminal meant a question, and every consumer disagreed with the next. A worker's state is derived
here from explicit, persisted events - Working, Input needed (with the unanswered question), Approval
needed (with the specific pending action), Finished (an explicit result), Failed, Disconnected,
Stopped - keyed by task, run (session id) and request id, deduplicated, with events from a run that is
no longer the task's current one rejected. A response ending (`turn_end`) is not a finish: without an
explicit result or an open request the state is `unknown`, never a guessed hand raise. An answer is
bound to the exact outstanding request and run: delivered once, refused when resolved or when the run
changed, and written into the task's discussion with its delivery outcome.
"""
import hashlib, json
from loguru import logger

KINDS = ('working', 'turn_end', 'input_needed', 'approval_needed', 'answered', 'finished', 'failed', 'disconnected', 'stopped')
REQUESTS = ('input_needed', 'approval_needed')
TERMINAL = ('failed', 'disconnected', 'stopped')


def request_id_for(text: str) -> str:
    """A stable id for a request whose producer gave none: the same question asked twice is one request."""
    return hashlib.sha1(' '.join(str(text or '').split()).lower().encode()).hexdigest()[:12]


def _live(tid: int):
    from . import terminal as term
    return next((x for x in list(term.SESSIONS.values()) if getattr(x, 'task_id', None) == tid and getattr(x, 'alive', False)), None)


def current_sid(store, tid: int):
    """The run that owns the task now: its live session, else the newest run that ever reported."""
    s = _live(tid)
    if s: return str(s.sid)
    evs = store.worker_events(tid)
    return str(evs[-1]['Sid']) if evs else None


def record(store, tid: int, sid: str, kind: str, request_id: str = None, text: str = '', choices: list = None,
           source: str = 'api', event_id: str = None) -> bool:
    """One event. False when it is a replay (same event id), a duplicate open request, or from a run that
    is no longer the task's current one (PW-227)."""
    if kind not in KINDS: raise ValueError(f'unknown worker event: {kind}')
    if event_id and store.worker_event_exists(event_id): return False
    # a LIVE run owns the task: another run's word is stale and ignored. With no live run the newest run to
    # report is the task's current one (a restart, a headless worker) - its events are kept
    live = _live(tid)
    if live and str(sid) != str(live.sid) and kind not in TERMINAL:
        logger.debug(f'worker event from run {sid} ignored: task {tid} is with run {live.sid}')
        return False
    if kind in REQUESTS:
        request_id = request_id or request_id_for(text)
        if any(r['request_id'] == request_id for r in status(store, tid)['requests']): return False
    store.add_worker_event({'TaskId': tid, 'Sid': str(sid), 'Kind': kind, 'RequestId': request_id, 'Text': str(text or '')[:4000],
                            'ChoicesJson': json.dumps(list(choices)) if choices else None, 'Source': source, 'EventId': event_id})
    try: store._poke('task-changed', task_id=tid)
    except Exception: pass
    return True


def events(store, tid: int, sid: str = None) -> list:
    return [e for e in store.worker_events(tid) if sid is None or str(e['Sid']) == str(sid)]


def _public_request(e: dict) -> dict:
    try: choices = json.loads(e['ChoicesJson']) if e.get('ChoicesJson') else []
    except ValueError: choices = []
    return {'request_id': e['RequestId'], 'kind': e['Kind'], 'text': e['Text'], 'choices': choices, 'sid': e['Sid'], 'at': e['CreatedAt']}


def status(store, tid: int) -> dict:
    """{state, requests, result, sid, live}. Derived, never guessed: no event and no request is `unknown`."""
    sid = current_sid(store, tid)
    live = _live(tid) is not None
    evs = events(store, tid, sid) if sid else []
    answered = {e['RequestId'] for e in evs if e['Kind'] == 'answered'}
    requests = [_public_request(e) for e in evs if e['Kind'] in REQUESTS and e['RequestId'] not in answered]
    out = {'sid': sid, 'live': live, 'requests': requests, 'result': None, 'state': 'unknown'}
    if not evs: return out
    last = evs[-1]
    if last['Kind'] in TERMINAL: out['state'] = last['Kind']; return out
    if any(r['kind'] == 'approval_needed' for r in requests): out['state'] = 'approval_needed'; return out
    if requests: out['state'] = 'input_needed'; return out
    # a finish counts until a new turn starts work again
    for e in reversed(evs):
        if e['Kind'] == 'finished': out['state'], out['result'] = 'finished', e['Text']; return out
        if e['Kind'] == 'working': break
    if not live: out['state'] = 'disconnected'; return out
    # the newest word decides: a prompt submitted is work in flight; an answer delivered is work resumed; a
    # response that merely ended is nothing anyone should act on (PW-226)
    out['state'] = 'working' if last['Kind'] in ('working', 'answered') else 'unknown'
    return out


def answer(store, tid: int, request_id: str, text: str, actor: str = 'owner') -> dict:
    """Deliver the owner's answer to ONE outstanding request of the run that asked it (PW-139/141): once,
    to that run, and say what happened - delivered, resolved already, stale (the run changed),
    disconnected (no live worker: open the workspace), or failed."""
    from . import terminal as term
    text = ' '.join(str(text or '').split())
    if not text: raise ValueError('say something')
    # the request is looked up across every run of the task: one that belongs to a run that is no longer the
    # task's is STALE, not silently forwarded to whatever worker has the task now (PW-139)
    evs = events(store, tid)
    answered = {e['RequestId'] for e in evs if e['Kind'] == 'answered'}
    asked = next((_public_request(e) for e in reversed(evs) if e['Kind'] in REQUESTS and e['RequestId'] == request_id), None)
    if not asked or request_id in answered: return {'delivered': False, 'state': 'resolved', 'why': 'that request is no longer outstanding'}
    req = asked
    sess = _live(tid)
    if not sess:
        store.add_comment(tid, actor, 'human', f'Answer to "{req["text"][:160]}": {text[:500]} - could not be delivered: no live worker on this task. Open the workspace to continue.')
        return {'delivered': False, 'state': 'disconnected', 'why': 'no live worker on this task'}
    if str(sess.sid) != str(req['sid']):
        store.add_comment(tid, actor, 'human', f'Answer to "{req["text"][:160]}": {text[:500]} - not delivered: the run that asked ({req["sid"]}) is gone and a different worker has the task.')
        return {'delivered': False, 'state': 'stale', 'why': 'the run that asked is no longer the one on the task'}
    who = getattr(sess, 'agent', None) or getattr(sess, 'label', None) or 'the agent'
    try:
        if hasattr(sess, 'send_prompt'): sess.send_prompt(text)
        else: term.type_into(sess, text)
    except Exception as e:
        store.add_comment(tid, actor, 'human', f'Answer to "{req["text"][:160]}": {text[:500]} - could not be delivered to {who}: {str(e)[:200]}')
        return {'delivered': False, 'state': 'failed', 'why': str(e)[:200]}
    record(store, tid, sess.sid, 'answered', request_id=request_id, text=text, source='owner')
    store.add_comment(tid, actor, 'human', f'Answered "{req["text"][:160]}": {text[:500]} - delivered to {who} (run {sess.sid}).')
    store.audit('task', tid, 'worker_answer', actor, detail={'request_id': request_id, 'sid': sess.sid})
    return {'delivered': True, 'state': 'delivered', 'sid': sess.sid}
