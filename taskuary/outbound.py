"""The funnel's other end: answering the person who asked.

Everything else here decides - triage routes, the coder works, you approve - and until now
the answer never left the machine. Sending closes the loop, on the same channel the request
arrived on: an email replies IN ITS THREAD (so it lands under the original, not as a fresh
mail nobody connects), a chat answers in the chat.

Nothing sends itself. Every call here is behind a human verdict or an explicit hand-off.
"""
import json
import requests
from loguru import logger

GRAPH = 'https://graph.microsoft.com/v1.0'


def _graph_token(store, kind='outlook'):
    from .channels import graph_creds, graph_token
    c = store.get_connector_by_type(kind, with_secret=True)
    if not c or not c.get('Active'): raise RuntimeError(f'the {kind} connection is not set up')
    cfg, sec, _ = graph_creds(store, c)
    return graph_token(cfg, sec)


def _mailbox(store, msg=None):
    """Which mailbox sends. The one the message arrived in, else the first email source."""
    if msg and msg.get('SourceName') and '@' in (msg['SourceName'] or ''): return msg['SourceName']
    src = next((s for s in store.list_sources() if s['Channel'] == 'email'), None)
    if not src: raise RuntimeError('no mailbox configured - add one under Connectors → Outlook')
    return src['Address']


def send_email(store, to: list, subject: str, body: str, reply_to_graph_id: str = None, mailbox: str = None) -> dict:
    """Reply in thread when we know the Graph message id, otherwise a new mail. Plain text:
    these are answers from a person, not marketing."""
    tok = _graph_token(store)
    box = mailbox or _mailbox(store)
    to = [t for t in (to or []) if t and '@' in t]
    if not to and not reply_to_graph_id: raise RuntimeError('no recipient')
    hdr = {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}
    if reply_to_graph_id:
        r = requests.post(f'{GRAPH}/users/{box}/messages/{reply_to_graph_id}/reply', headers=hdr, timeout=30,
                          data=json.dumps({'message': {'toRecipients': [{'emailAddress': {'address': a}} for a in to]}
                                           if to else {}, 'comment': body}))
    else:
        r = requests.post(f'{GRAPH}/users/{box}/sendMail', headers=hdr, timeout=30,
                          data=json.dumps({'message': {'subject': subject or '(no subject)',
                                                       'body': {'contentType': 'Text', 'content': body},
                                                       'toRecipients': [{'emailAddress': {'address': a}} for a in to]},
                                           'saveToSentItems': True}))
    if r.status_code >= 300:
        raise RuntimeError(f'graph sendMail failed ({r.status_code}): {r.text[:300]}')
    return {'channel': 'email', 'to': to, 'mailbox': box, 'threaded': bool(reply_to_graph_id)}


def send_teams(store, chat_id: str, body: str) -> dict:
    """Post into a chat. App-only posting needs ChatMessage.Send on the app registration,
    which reading does NOT include - say so plainly rather than failing with a 403 blob."""
    tok = _graph_token(store, 'teams')
    r = requests.post(f'{GRAPH}/chats/{chat_id}/messages', timeout=30,
                      headers={'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'},
                      data=json.dumps({'body': {'contentType': 'text', 'content': body}}))
    if r.status_code == 403:
        raise RuntimeError('Teams refused the post (403). App-only posting needs the ChatMessage.Send '
                           'application permission on your app registration - reading chats does not include it. '
                           'Add it (admin consent), or hand off by email instead.')
    if r.status_code >= 300:
        raise RuntimeError(f'graph chat post failed ({r.status_code}): {r.text[:300]}')
    return {'channel': 'teams', 'chat': chat_id}


def reply_to_message(store, msg: dict, body: str, to: list = None) -> dict:
    """Answer wherever the request came from. The message row carries everything needed:
    the mailbox it arrived in, the Graph id for threading, or the chat id."""
    ch, ext = msg.get('Channel'), str(msg.get('ExternalId') or '')
    if ch == 'email':
        return send_email(store, to or [msg.get('FromEmail')], f"Re: {msg.get('Subject') or ''}".strip(),
                          body, ext[6:] if ext.startswith('graph:') else None, msg.get('SourceName'))
    if ch == 'teams':
        chat = (msg.get('ConversationId') or '')[6:]        # 'teams:19:...'
        if not chat: raise RuntimeError('this chat message has no chat id to answer in')
        return send_teams(store, chat, body)
    raise RuntimeError(f"nothing to answer on: {ch or 'unknown'} messages are read-only here")


HANDOFF_SYSTEM = (
    'You forward work to a colleague on behalf of the owner. Write the message they will '
    'receive: one short paragraph of what is being asked and why it is theirs, then the '
    'concrete details (systems, names, ids, errors) as short lines, then what you need back. '
    'No greeting fluff, no "I hope this finds you well", no markdown headers. '
    'Plain text, under 200 words, in the owner\'s voice.')


def draft_handoff(store, task_id: int, to: str, note: str = None, llm=None) -> str:
    """The AI writes the forward message from the task's own context."""
    from . import agents as hub_agents
    from .llm import build_llm
    llm = llm or build_llm(store)
    if not llm: raise RuntimeError('no AI connector is set up to write the message')
    ctx = hub_agents.task_context(store, task_id)
    ask = f'Forward this to {to}.' + (f' The owner adds: {note}' if note else '')
    out = llm(f"{HANDOFF_SYSTEM}\n\n{store.get_doc('soul') or ''}", f'{ask}\n\n{ctx}', max_tokens=700)
    return (out or '').strip()
