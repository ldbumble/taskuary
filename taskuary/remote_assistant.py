"""The owner's private WhatsApp doorway into the floating Taskuary guide.

This is deliberately not another bot or another conversation. Questions are appended to the
same hidden guide task used by the desktop bubble, and every turn receives general.dock_snapshot.
Only messages sent *by the linked WhatsApp account* in its explicitly named, direct notify chat
are accepted. Other people, other chats, and groups continue through the normal funnel.
"""
import json, re, threading

from loguru import logger


_TASK_LINK = re.compile(r'\[([^\]]+)\]\(#task=\d+\)')
_locks, _locks_guard = {}, threading.Lock()


def _config(connector) -> dict:
    try: return json.loads((connector or {}).get('ConfigJson') or '{}')
    except (TypeError, ValueError): return {}


def _roles(connector) -> set:
    return {x.strip() for x in str((connector or {}).get('Roles') or '').split(',') if x.strip()}


def connector_for_chat(store, jid: str, connector=None):
    """The active WhatsApp notification connector that owns this private chat, if any."""
    rows = [connector] if connector else store.connectors_by_type('whatsapp', with_secret=True)
    return next((c for c in rows if c and c.get('Active') and 'notify' in _roles(c)
                 and str(_config(c).get('notify_chat') or '').strip() == str(jid or '').strip()), None)


def enabled(store, jid: str, connector=None) -> bool:
    return (store.get_settings().get('phone_assistant') == '1'
            and bool(jid) and not str(jid).endswith('@g.us')
            and connector_for_chat(store, jid, connector) is not None)


def intercept(store, jid: str, text: str, *, from_me=False, taskuary=False, connector=None) -> bool:
    """Claim an owner-authored guide question before it can be discarded or triaged.

    ``taskuary`` is stamped by the local bridge on every message Taskuary itself sends. Those
    echoes are always swallowed; otherwise a notification could become the guide's next prompt.
    """
    if taskuary: return True
    question = str(text or '').strip()
    if not from_me or not question or not enabled(store, jid, connector): return False
    c = connector_for_chat(store, jid, connector)
    threading.Thread(target=_locked_respond,
                     args=(store, str(jid), question, c.get('ConnectorId')),
                     name='taskuary-whatsapp-guide', daemon=True).start()
    return True


def _locked_respond(store, jid: str, question: str, connector_id: int):
    key = (id(store), connector_id, jid)
    with _locks_guard: lock = _locks.setdefault(key, threading.Lock())
    with lock: respond(store, jid, question, connector_id)


def _phone_text(reply: str) -> str:
    """Keep Taskuary task references useful without sending desktop-only hash links."""
    return _TASK_LINK.sub(r'\1', str(reply or '')).strip()


def _chunks(text: str, limit=3900) -> list[str]:
    """Split a long walkthrough on paragraph boundaries instead of silently truncating it."""
    text = str(text or '').strip()
    if not text: return []
    out = []
    while len(text) > limit:
        cut = max(text.rfind('\n\n', 0, limit), text.rfind('\n', 0, limit), text.rfind(' ', 0, limit))
        if cut < limit // 2: cut = limit
        out.append(text[:cut].rstrip()); text = text[cut:].lstrip()
    if text: out.append(text)
    return out


def _send(store, jid: str, text: str, connector_id: int):
    from . import messengers
    chunks = _chunks(text)
    for i, chunk in enumerate(chunks):
        prefix = 'Taskuary:\n' if i == 0 else f'Taskuary ({i + 1}/{len(chunks)}):\n'
        messengers.wa_send(store, jid, prefix + chunk, connector_id=connector_id)


def respond(store, jid: str, question: str, connector_id: int):
    """Answer synchronously; the poller runs this on a serialized background worker."""
    from . import general
    try:
        task, _ = general.dock_task(store, 'owner-whatsapp')
        store.audit('task', task['TaskId'], 'whatsapp_assistant_question', 'owner-whatsapp',
                    detail={'channel': 'whatsapp', 'chat': jid, 'chars': len(question)})
        session = general.start_session(store, task['TaskId'], actor='owner-whatsapp')
        reply = session.send_prompt(question)
        _send(store, jid, _phone_text(reply), connector_id)
    except Exception as e:
        logger.warning(f'WhatsApp guide could not answer: {e}')
        try: _send(store, jid, f"I couldn't answer that: {e}", connector_id)
        except Exception as send_error: logger.warning(f'WhatsApp guide could not send its error: {send_error}')
