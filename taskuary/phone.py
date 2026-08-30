"""Answer agents and approve replies from your phone. With `phone_approvals` on, a waiting
agent ping carries [tqN]; replying to that quoted ping types the owner's answer into that
exact live terminal. A review ping carries [rvN], where approve/reject/no-reply retain their
existing meanings and any other text replaces the draft.

Pollers call this before triage, so an answer or verdict never becomes new work. Explicit
tags win. Reviews retain the convenient last-ping fallback, but agent answers require their
tag because several coding sessions can be waiting at once.
"""
import json, re
from loguru import logger

TAG = re.compile(r'\[rv(\d+)\]')
TASK_TAG = re.compile(r'\[tq0*(\d+)\]', re.I)
APPROVE = re.compile(r'^\W*(approve[d]?|send( it)?|yes|ok(ay)?)\W*$', re.I)
REJECT = re.compile(r'^\W*reject(ed)?\W*$', re.I)
NO_REPLY = re.compile(r'^\W*no( reply| response)?( needed| required)?\W*$', re.I)

HOW = "reply 'approve' to send it, 'reject', 'no reply' — or your own text to send that instead"
TASK_HOW = "reply to this message with your answer — it goes straight to the live agent"


def notify_chats_of(store, channel: str) -> set:
    out = set()
    for c in store.connectors_by_type(channel):
        try:
            chat = str(json.loads((c or {}).get('ConfigJson') or '{}').get('notify_chat') or '')
            if chat: out.add(chat)
        except ValueError: continue
    return out


def notify_chat_of(store, channel: str) -> str:
    """Compatibility helper for callers displaying one destination."""
    return next(iter(notify_chats_of(store, channel)), '')


def ping_tail(store, rid: int, draft: str = None) -> str:
    """What a review ping carries when phone approvals are on: the draft (so the phone shows
    what 'approve' would send) and the tag + verbs. Remembers the ping so a bare 'approve'
    with nothing quoted still lands on the right review."""
    if store.get_settings().get('phone_approvals') != '1': return ''
    store.set_setting('last_pinged_review', str(rid), 'notify')
    return (f'\n\nDRAFT:\n{draft.strip()[:800]}' if (draft or '').strip() else '') + f'\n\n[rv{rid}] {HOW}'


def task_ping_tail(store, tid: int) -> str:
    """Explicit routing for an agent answer. There is intentionally no "last task" fallback:
    with concurrent sessions, a bare "yes" is not enough information to safely type anywhere."""
    if store.get_settings().get('phone_approvals') != '1': return ''
    return f'\n\n[tq{int(tid):04d}] {TASK_HOW}'


def _find_review(store, text: str, quoted: str):
    m = TAG.search(quoted or '') or TAG.search(text or '')
    rid = int(m.group(1)) if m else 0
    if not rid:
        try: rid = int(store.get_settings().get('last_pinged_review') or 0)
        except ValueError: rid = 0
    return (store.get_review(rid), rid) if rid else (None, 0)


def intercept(store, channel: str, chat_id: str, text: str, quoted: str = None) -> bool:
    """True = this was a verdict in the notify chat and it was handled - never ingest it.
    False = not ours (feature off, another chat, or nothing to decide) - flow on to triage."""
    if store.get_settings().get('phone_approvals') != '1': return False
    if not chat_id or str(chat_id) not in notify_chats_of(store, channel): return False
    t = (text or '').strip()
    if not t: return False
    # our OWN pings and acks come back through the WhatsApp bridge as fromMe messages in
    # this very chat - swallow them, or a ping's text would read as an 'edit' verdict
    if HOW in t or TASK_HOW in t or t.startswith('✓') or ' is not waiting on a verdict' in t \
            or ' has no live agent to answer' in t: return True
    # A reply quoting a waiting-agent ping is an answer for that exact task. It wins over the
    # review fallback, so "approve" under [tq0251] reaches the agent and cannot send an email.
    tm = TASK_TAG.search(quoted or '') or TASK_TAG.search(t)
    if tm:
        tid = int(tm.group(1))
        answer = TASK_TAG.sub('', t).strip()
        if not answer:
            _ack(store, channel, chat_id, f'tq{tid:04d} needs an answer after the tag.')
            return True
        from . import terminal
        ok = terminal.say_to_task(store, tid, {'FromName': 'the owner', 'Channel': channel,
                                               'BodyText': answer}, actor='owner-phone')
        if ok:
            store.audit('task', tid, 'phone_answer', 'owner-phone', detail={'channel': channel})
            _ack(store, channel, chat_id, f'✓ tq{tid:04d}: sent to the live agent.')
        else:
            _ack(store, channel, chat_id, f'tq{tid:04d} has no live agent to answer any more.')
        return True
    rv, rid = _find_review(store, t, quoted)
    if not rid: return False                      # nothing was ever pinged: a plain chat message
    if not rv or rv['Status'] != 'pending':
        _ack(store, channel, chat_id, f'rv{rid} is not waiting on a verdict any more.')
        return True
    if REJECT.match(t): verb, final = 'reject', None
    elif NO_REPLY.match(t): verb, final = 'no_reply', None
    elif APPROVE.match(t): verb, final = 'approve', None
    else: verb, final = 'edit', TAG.sub('', t).strip()      # your words become the reply
    if verb == 'approve' and not (rv.get('DraftText') or '').strip():
        _ack(store, channel, chat_id, f'rv{rid} has no draft yet (still being written) - '
                                      'send your own text and that goes instead.')
        return True
    from .verdicts import decide
    out = decide(store, rv, verb, final, note='decided from the phone', actor='owner-phone')
    store.audit('review', rid, f'phone_{verb}', 'owner-phone', detail={'channel': channel})
    if out.get('send_error'):
        _ack(store, channel, chat_id, f"rv{rid} approved, but sending FAILED: {out['send_error']} "
                                      '- it is back in Review wearing the error.')
    elif verb in ('approve', 'edit'):
        sent = out.get('sent') or {}
        _ack(store, channel, chat_id, f"✓ rv{rid} sent by {sent.get('channel') or 'its channel'}"
                                      + (' (your text, not the draft)' if verb == 'edit' else ''))
    else:
        _ack(store, channel, chat_id, f'✓ rv{rid}: {verb.replace("_", " ")} - nothing was sent.')
    return True


def _ack(store, channel: str, chat_id: str, text: str):
    """Confirmation back into the same chat; a failed ack never breaks the poll."""
    try:
        from . import messengers
        (messengers.tg_send if channel == 'telegram' else messengers.wa_send)(store, chat_id, text)
    except Exception as e:
        logger.warning(f'phone ack failed: {e}')
