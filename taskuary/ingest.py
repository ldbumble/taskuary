"""Ingest: anything -> the funnel. No vendor connectors baked in - push messages via the
HTTP API (POST /api/ingest/push) or your own plugin; report connections run on schedule.

Pipeline per message: dedup -> deterministic policy -> route to a task -> intent triage
(task / reply_only / fyi) -> file or create. Real tasks NEVER get an auto reply-draft:
answering is the responder's job (reply_only), doing is the coder's.
"""
import re, threading
from loguru import logger
from .routing import route, draft_task_fields
from .policy import evaluate
from .triage import classify_intent, heuristic_intent
from .store import task_ref


def ingest_message(store, msg: dict, actor: str = 'router', llm=None, file_only: bool = False) -> dict:
    """file_only = this connection is a FEED, not a trigger: the item is shown on the
    timeline and nothing else happens to it - no triage, no AI call, no task. It is a
    cheaper and quieter path than 'ignore', which is a verdict about the message."""
    if store.message_exists(msg.get('external_id') or ''):
        return {'status': 'duplicate', 'task_id': None, 'message_id': None}
    if file_only:
        mid = store.add_message({**_fields(msg, None), 'Status': 'feed'})
        store.add_route(mid, None, 'feed', None,
                        'shown for information - this connection is a feed, not a task trigger', [], 'feed')
        return {'status': 'feed', 'task_id': None, 'message_id': mid}
    cfg = store.get_settings()
    pol = evaluate(msg, store.list_policies(), store.known_sender(msg.get('from_email')),
                   cfg.get('default_action', 'draft'))
    if pol['action'] in ('skip', 'ignore'):
        # skip = stored for dedupe but NEVER shown (flood senders); ignore = shown, no task
        mid = store.add_message({**_fields(msg, None), 'Status': 'skipped' if pol['action'] == 'skip' else 'ignored'})
        store.add_route(mid, None, pol['action'], None, f"policy '{pol['rule']}': {pol['reason']}", [], 'policy')
        return {'status': pol['action'] + ('ped' if pol['action'] == 'skip' else 'd'), 'task_id': None, 'message_id': mid}

    r = route(msg, store.snapshots(), float(cfg.get('attach_threshold', 0.42)))
    if r['decision'] == 'attach':
        tid = r['task_id']
        mid = store.add_message(_fields(msg, tid))
        store.add_comment(tid, actor, 'agent', f"New {msg.get('channel')} from {msg.get('from_email') or 'unknown'}: {msg.get('subject') or ''}")
    else:
        # AI-gated triage: without an active AI connector, nothing becomes a task on its
        # own - messages FILE onto the timeline (visible, promotable by hand) instead of
        # heuristics spraying tasks for every automated notification. Heuristics still
        # short-circuit the obvious fyi noise before spending an AI call.
        if cfg.get('intent_classify_enabled', '1') == '1':
            h = heuristic_intent(msg)
            if h['intent'] == 'fyi':                     # obvious automated noise: no AI call needed
                intent = h
            elif llm is None:
                mid = store.add_message({**_fields(msg, None), 'Status': 'filed'})
                store.add_route(mid, None, 'file', None,
                                'awaiting AI triage - connect an AI connector (Connectors → AI) to classify inbound automatically', [], 'triage')
                logger.debug(f"ingest: filed (no AI connector) - {msg.get('subject') or ''}")
                return {'status': 'filed', 'task_id': None, 'message_id': mid}
            else:
                fail = {}
                def _guarded(sys_, usr_):
                    try:
                        return llm(sys_, usr_)
                    except Exception as e:
                        fail['err'] = str(e)[:200]
                        raise
                from .learn import injectable
                intent = classify_intent(msg, llm=_guarded, soul=store.doc('soul'),
                                         learned=injectable(store.doc('learned') or ''),
                                         notes=notes_for(store, msg), images=msg.get('images'))
                if fail:
                    # the AI errored - filing beats the old default-to-task heuristic
                    mid = store.add_message({**_fields(msg, None), 'Status': 'filed'})
                    store.add_route(mid, None, 'file', None,
                                    f"AI triage failed ({fail['err']}) - filed; fix the AI connector and it will classify new mail", [], 'triage')
                    logger.warning(f"ingest: AI triage failed, filed - {fail['err']}")
                    return {'status': 'filed', 'task_id': None, 'message_id': mid}
        else:
            intent = {'intent': 'task', 'why': ''}
        if intent['intent'] == 'fyi':
            mid = store.add_message({**_fields(msg, None), 'Status': 'filed'})
            store.add_route(mid, None, 'file', None, f"triage: {intent.get('why') or 'informational'}", [], 'triage')
            return {'status': 'filed', 'task_id': None, 'message_id': mid}
        f = draft_task_fields(msg)
        if intent['intent'] == 'reply_only': f['kind'] = 'reply'
        tid = store.create_task({'Title': f['title'], 'Summary': f['summary'], 'Kind': f['kind'],
                                 'Priority': f['priority'], 'Source': msg.get('channel') or 'api',
                                 'SourceRef': msg.get('source_link')}, actor)
        store.audit('task', tid, 'create', actor, 'agent', {'from': msg.get('from_email'), 'reason': r['reason']})
        mid = store.add_message(_fields(msg, tid))
        # the agents actually pick work up here:
        # - reply tasks ALWAYS enter the review queue ("needs me"); auto_draft_enabled
        #   additionally has the responder write the draft in the background
        # - real tasks auto-dispatch to the coder when coder_auto_enabled is on
        if f['kind'] == 'reply':
            rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                                    'Reason': f"needs a reply: {intent.get('why') or 'question for you'}"})
            if cfg.get('auto_draft_enabled') == '1':
                _spawn(_auto_draft, store, tid, rid)
        elif cfg.get('coder_auto_enabled') == '1':
            _spawn(_auto_code, store, tid)
    store.add_route(mid, tid, r['decision'], r['score'], r['reason'], r['candidates'], actor)
    logger.info(f"ingest: {r['decision']} -> {task_ref(tid)}")
    # the timeline pushed INTO a chat: 'needs_me' pings only what is waiting on YOU - a question
    # to answer, or a task nobody was dispatched at. A task an agent just started is being
    # handled; the ping for those comes later, when its reply is drafted (coder.raise_reply).
    lvl = cfg.get('notify_level') or 'needs_me'
    # on an attach there was no fresh triage (`f` only exists on create) - the task itself knows
    kind = f['kind'] if r['decision'] != 'attach' else (store.get_task(tid) or {}).get('Kind')
    dispatched = kind != 'reply' and cfg.get('coder_auto_enabled') == '1'
    if lvl == 'all' or (lvl == 'needs_me' and not dispatched):
        _notify_new(store, msg, tid, mid,
                    'a question for you' if kind == 'reply' else 'new task on your list')
    return {'status': 'attached' if r['decision'] == 'attach' else 'created', 'task_id': tid, 'message_id': mid}


def _notify_new(store, msg: dict, tid, mid, why: str):
    """One short line to the notify channels. Failure is a log line, never a broken ingest."""
    from .outbound import notify
    from .store import task_ref
    try:
        who = msg.get('from_name') or msg.get('from_email') or msg.get('source_name') or 'someone'
        body_head = str(msg.get('body') or '').strip().splitlines()
        head = msg.get('subject') or (body_head[0][:80] if body_head else '(no subject)')
        line = f"{task_ref(tid)} - {why}\n{head}\nfrom {who} on {msg.get('channel') or 'api'}"
        notify(store, line, about={'Channel': msg.get('channel'), 'ConversationId': msg.get('conversation_id')})
    except Exception as e:
        logger.warning(f'notify failed for message {mid}: {e}')


def notes_for(store, msg: dict) -> list:
    """The owner's standing notes that apply to this message - global ones plus anything
    learned about this sender or their domain. Triage reads them, so a verdict given once
    ("this kind of mail is not ours") applies to every message like it afterwards."""
    em = (msg.get('from_email') or '').lower()
    dom = em.rsplit('@', 1)[-1] if '@' in em else ''
    return [n['Note'] for n in store.list_memories()
            if n['Scope'] == 'global'
            or (n['Scope'] == 'sender' and (n.get('ScopeKey') or '').lower() == em)
            or (n['Scope'] == 'sender_domain' and (n.get('ScopeKey') or '').lower() == dom)]


def task_from_message(store, mid: int, actor: str = 'owner', kind: str = 'coding', assignee: str = None) -> int:
    """Promote a filed/ignored/report message into a real task: to hand to an agent, or - with
    `assignee` - to keep on your own list, because plenty of work is real work no agent can do
    (go into some web app and click the thing). Already-routed messages keep the task they are on."""
    m = store.get_message(mid)
    if not m: raise ValueError(f'no message {mid}')
    if m.get('TaskId'): return m['TaskId']
    title = (m.get('Subject') or f"{m.get('FromName') or m.get('FromEmail') or m.get('Channel')} message")[:200]
    tid = store.create_task({'Title': title, 'Summary': str(m.get('BodyText') or '')[:1000], 'Kind': kind,
                             'Source': m.get('Channel') or 'api', 'SourceRef': m.get('SourceLink'),
                             **({'Assignee': assignee} if assignee else {})}, actor)
    store.attach_message(mid, tid)
    store.add_route(mid, tid, 'create', None,
                    f"promoted by the owner - {'theirs to do' if assignee else 'to hand it to an agent'}", [], actor)
    store.audit('task', tid, 'create_from_message', actor, detail={'message_id': mid, 'subject': title})
    return tid


GREETING = re.compile(r'^(hi|hello|hey|dear|good (morning|afternoon|evening))\b', re.I)

def ask_line(body: str) -> str:
    """The line that carries the ask - never the greeting it opens with."""
    lines = [l.strip() for l in (body or '').splitlines() if l.strip()]
    real = [l for l in lines if not GREETING.match(l) and len(l) > 12]
    return (real or lines or [''])[0][:120]


def split_message(store, mid: int, actor: str = 'owner', kind: str = None) -> int:
    """Pull one message OUT of the task it was threaded onto and give it its own. Two asks
    that arrived in the same chat are one conversation but two jobs - and an agent sent at
    the task only ever gets the first one's prompt."""
    m = store.get_message(mid)
    if not m: raise ValueError(f'no message {mid}')
    old = m.get('TaskId')
    parent = store.get_task(old) if old else None
    title = (m.get('Subject') or m.get('FromName') or 'message')[:200]
    body = str(m.get('BodyText') or '')
    # the ask itself is the title when the subject is just the chat's name every message
    # shares - and the ask is never the greeting line it opens with
    if parent and (parent.get('Title') or '').strip().lower() == title.strip().lower():
        lines = [l.strip() for l in body.splitlines() if l.strip()]
        greet = re.compile(r'^(hi|hello|hey|dear|good (morning|afternoon|evening))\b', re.I)
        title = next((l for l in lines if not greet.match(l) and len(l) > 12), lines[0] if lines else title)[:120]
    tid = store.create_task({'Title': title, 'Summary': body[:2000],
                             'Kind': kind or (parent or {}).get('Kind') or 'coding',
                             'Source': m.get('Channel') or 'api', 'SourceRef': m.get('SourceLink')}, actor)
    store.attach_message(mid, tid)
    store.add_route(mid, tid, 'create', None,
                    f'split off {task_ref(old)} - a separate ask in the same thread' if old else 'made its own task',
                    [], actor)
    if old: store.add_comment(old, actor, 'human', f'Split "{title}" out into {task_ref(tid)} - unrelated ask.')
    store.audit('task', tid, 'split_from_message', actor, detail={'message_id': mid, 'from_task': old})
    return tid


def _spawn(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


AUTO_SESSIONS = 4      # unattended sessions to keep alive at once; past this it waits for you

def _auto_code(store, tid):
    """Auto-dispatch puts the CLI on the task in a REAL session - the same one you see when
    you open the task. Nothing runs where you cannot watch it, interrupt it or answer it."""
    from . import terminal as term
    # the note belongs INSIDE the worker: written before the thread started, a task could
    # claim "auto-dispatched" with no session behind it whenever the process died first
    if len([t for t in term.SESSIONS.values() if t.alive]) >= AUTO_SESSIONS:
        store.add_comment(tid, 'router', 'agent',
                          f'Not auto-started: {AUTO_SESSIONS} agent sessions are already live. '
                          'Open the task and start it when you are ready.')
        return
    try:
        term.start_on_task(store, tid, store.get_settings().get('default_agent') or 'coder', actor='router')
        store.add_comment(tid, 'router', 'agent', 'auto-started a live coder session (coder_auto_enabled)')
    except Exception as e:
        logger.warning(f'auto dispatch failed for task {tid}: {e}')
        store.add_comment(tid, 'router', 'agent', f'Auto-start failed: {str(e)[:200]}')


def _auto_draft(store, tid, rid):
    """A reply needs an answer, not an agent: the MAIN AI writes it and it waits for approval.
    A CLI agent named `responder` takes over only if the owner deliberately configured one."""
    from . import responder
    try: responder.write_draft(store, tid, rid, actor='auto-draft')
    except Exception as e:
        logger.warning(f'auto-draft failed for task {tid}: {e}')


def _fields(msg, task_id):
    return {'TaskId': task_id, 'ExternalId': msg.get('external_id'), 'ConversationId': msg.get('conversation_id'),
            'Channel': msg.get('channel') or 'api', 'SourceName': msg.get('source_name'),
            'Subject': (msg.get('subject') or '')[:500], 'FromName': msg.get('from_name'),
            'FromEmail': msg.get('from_email'), 'SentAt': msg.get('sent_at'),
            'BodyText': msg.get('body'), 'SourceLink': msg.get('source_link'), 'Status': 'routed'}
