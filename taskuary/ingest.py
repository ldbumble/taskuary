"""Ingest: anything -> the funnel. No vendor connectors baked in - push messages via the
HTTP API (POST /api/ingest/push) or your own plugin; report connections run on schedule.

Pipeline per message: dedup -> deterministic policy -> route to a task -> intent triage
(task / reply_only / fyi) -> file or create. Real tasks NEVER get an auto reply-draft:
answering is the responder's job (reply_only), doing is the coder's.
"""
from loguru import logger
from .routing import route, draft_task_fields
from .policy import evaluate
from .triage import classify_intent
from .store import task_ref


def ingest_message(store, msg: dict, actor: str = 'router', llm=None) -> dict:
    if store.message_exists(msg.get('external_id') or ''):
        return {'status': 'duplicate', 'task_id': None, 'message_id': None}
    cfg = store.get_settings()
    pol = evaluate(msg, store.list_policies(), store.known_sender(msg.get('from_email')),
                   cfg.get('default_action', 'draft'))
    if pol['action'] == 'ignore':
        mid = store.add_message({**_fields(msg, None), 'Status': 'ignored'})
        store.add_route(mid, None, 'ignore', None, f"policy '{pol['rule']}': {pol['reason']}", [], 'policy')
        return {'status': 'ignored', 'task_id': None, 'message_id': mid}

    r = route(msg, store.snapshots(), float(cfg.get('attach_threshold', 0.42)))
    if r['decision'] == 'attach':
        tid = r['task_id']
        mid = store.add_message(_fields(msg, tid))
        store.add_comment(tid, actor, 'agent', f"New {msg.get('channel')} from {msg.get('from_email') or 'unknown'}: {msg.get('subject') or ''}")
    else:
        intent = classify_intent(msg, llm=llm, soul=store.get_doc('soul')) \
            if cfg.get('intent_classify_enabled', '1') == '1' else {'intent': 'task', 'why': ''}
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
    store.add_route(mid, tid, r['decision'], r['score'], r['reason'], r['candidates'], actor)
    logger.info(f"ingest: {r['decision']} -> {task_ref(tid)}")
    return {'status': 'attached' if r['decision'] == 'attach' else 'created', 'task_id': tid, 'message_id': mid}


def _fields(msg, task_id):
    return {'TaskId': task_id, 'ExternalId': msg.get('external_id'), 'ConversationId': msg.get('conversation_id'),
            'Channel': msg.get('channel') or 'api', 'SourceName': msg.get('source_name'),
            'Subject': (msg.get('subject') or '')[:500], 'FromName': msg.get('from_name'),
            'FromEmail': msg.get('from_email'), 'SentAt': msg.get('sent_at'),
            'BodyText': msg.get('body'), 'SourceLink': msg.get('source_link'), 'Status': 'routed'}
