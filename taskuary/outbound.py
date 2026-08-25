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
        # Graph reads the reply `comment` as HTML, so plain-text newlines collapse into one long
        # line - greeting, body and signature all jammed together. Escape and give the breaks back.
        import html as _html
        comment = _html.escape(body).replace(chr(10), '<br>')
        r = requests.post(f'{GRAPH}/users/{box}/messages/{reply_to_graph_id}/reply', headers=hdr, timeout=30,
                          data=json.dumps({'message': {'toRecipients': [{'emailAddress': {'address': a}} for a in to]}
                                           if to else {}, 'comment': comment}))
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
    if r.status_code in (401, 403):
        # Graph explains itself and we used to throw that away, so a chat that CANNOT be posted to
        # (someone outside the tenant is in it) read as a permission you had forgotten to grant.
        try: said = str(((r.json() or {}).get('error') or {}).get('message') or '')
        except ValueError: said = r.text[:300]
        low = said.lower()
        if any(w in low for w in ('federat', 'external', 'guest', 'cross-tenant', 'crosstenant')):
            why = ('someone outside your tenant is in this chat, and Graph does not let an app post into '
                   'a federated chat at all - no permission changes that. Reply by email instead.')
        else:
            why = ('app-only posting needs the ChatMessage.Send APPLICATION permission on your app '
                   'registration, with admin consent - reading chats does not include it.')
        raise RuntimeError(f'Teams refused the post ({r.status_code}): {why}'
                           + (f' Graph said: "{said[:200]}"' if said else ''))
    if r.status_code >= 300:
        raise RuntimeError(f'graph chat post failed ({r.status_code}): {r.text[:300]}')
    return {'channel': 'teams', 'chat': chat_id}


# Which channels Taskuary DRAFTS AND SENDS replies on. One answer, asked by everything:
# triage (should this become a reply task?), the coder wrap-up (is there a reply to draft?),
# and the Review buttons (can Approve actually send?). Before this, each decided for itself
# and they disagreed - a github task with replies off closed with no draft while the UI
# still promised one.
#
# 'report' and the read-only trackers can never carry a reply: nothing is written back to
# Jira or Sentry by design. github is gated on its own card switch (a public comment is the
# owner's call). Everything else is the owner's setting.
SENDABLE = ('email', 'teams', 'slack', 'telegram', 'whatsapp', 'discord', 'github')
NEVER = {'report', 'jira', 'asana', 'monday', 'clickup', 'todoist', 'gitlab', 'azdo',
         'linear', 'trello', 'notion', 'sentry', 'pagerduty', 'aws', 'azure'}


def reply_channels(store) -> set:
    """The channels the owner has replies switched ON for (Settings → Replies)."""
    raw = store.get_settings().get('reply_channels')
    if raw is None: return set(SENDABLE)
    return {c.strip() for c in str(raw).split(',') if c.strip()}


def can_reply(store, channel) -> bool:
    """May a reply be drafted and sent on this channel at all?

    The setting is a switch over the channels it LISTS, not a whitelist over everything -
    anything else (an item pushed in over /api/ingest/push, a channel added by a future
    connector) stays replyable, because silently refusing to answer an unrecognised channel
    is the worse failure. Only NEVER is absolute."""
    ch = (channel or '').lower()
    if not ch or ch in NEVER: return False
    if ch in SENDABLE and ch not in reply_channels(store): return False
    if ch == 'github': return store.github_replies_ok()
    return True


def send_out(store, channel: str, to, subject: str, body: str) -> dict:
    """Send something nobody asked for: a report going OUT, to an address the owner chose.

    reply_to_message answers a message - it reads the mailbox, thread id and chat id off the row
    that arrived. An outbound report has no such row, so the destination has to be given. Same
    senders underneath, same credentials, same channel switches: a channel the owner turned off
    for replies is off for this too, because "Taskuary may write to Slack" is one decision and
    not two.
    """
    to = [t.strip() for t in (to if isinstance(to, (list, tuple)) else str(to or '').split(',')) if str(t).strip()]
    ch = (channel or 'email').lower()
    if not can_reply(store, ch):
        raise RuntimeError(f'sending on {ch} is off - Settings → Replies decides which channels '
                           'Taskuary may write to, and it governs outbound reports too')
    if ch == 'email':
        if not to: raise RuntimeError('no recipient - an outbound email needs an address')
        # Graph when the Outlook card is connected, otherwise the IMAP mailbox's own SMTP
        c = store.get_connector_by_type('outlook')
        if c and c.get('Active'):
            return send_email(store, to, subject or '(no subject)', body)
        from .imapmail import send_smtp
        box = next((store.get_connector(x['ConnectorId'], with_secret=True) for x in store.list_connectors()
                    if x['Type'] in ('gmail', 'imap') and x['Active']), None)
        if not box: raise RuntimeError('no mailbox is connected to send from')
        return send_smtp(store, box, to, subject or '(no subject)', body)
    if ch == 'teams':
        if not to: raise RuntimeError('no chat id - a Teams message needs one to land in')
        return send_teams(store, to[0], f'**{subject}**\n\n{body}' if subject else body)
    if ch in ('telegram', 'whatsapp'):
        from . import messengers
        if not to: raise RuntimeError(f'no chat id - a {ch} message needs one to land in')
        return (messengers.tg_send if ch == 'telegram' else messengers.wa_send)(
            store, to[0], f'{subject}\n\n{body}' if subject else body)
    if ch == 'discord':
        from .devtools import discord_send
        if not to: raise RuntimeError('no channel id - a Discord message needs one to land in')
        return discord_send(store, to[0], f'**{subject}**\n\n{body}' if subject else body)
    raise RuntimeError(f'cannot send on {ch} - email, Teams, Telegram, WhatsApp and Discord can carry a report out')


def reply_to_message(store, msg: dict, body: str, to: list = None) -> dict:
    """Answer wherever the request came from. The message row carries everything needed:
    the mailbox it arrived in, the Graph id for threading, or the chat id."""
    ch, ext = msg.get('Channel'), str(msg.get('ExternalId') or '')
    if ch == 'email' and ext.startswith('imap:'):
        # mail that arrived over IMAP goes back over the provider's own SMTP, in-thread
        from .imapmail import send_smtp
        box = msg.get('SourceName') or ''
        c = next((store.get_connector(x['ConnectorId'], with_secret=True) for x in store.list_connectors()
                  if x['Type'] in ('gmail', 'imap') and x['Active']
                  and json.loads(x.get('ConfigJson') or '{}').get('address', '').lower() == box.lower()), None)
        if not c: raise RuntimeError(f'no IMAP connection is set up for {box}')
        return send_smtp(store, c, to or [msg.get('FromEmail')], f"Re: {msg.get('Subject') or ''}".strip(),
                         body, in_reply_to=msg.get('ConversationId'))
    if ch == 'email':
        return send_email(store, to or [msg.get('FromEmail')], f"Re: {msg.get('Subject') or ''}".strip(),
                          body, ext[6:] if ext.startswith('graph:') else None, msg.get('SourceName'))
    if ch == 'teams':
        chat = (msg.get('ConversationId') or '')[6:]        # 'teams:19:...'
        if not chat: raise RuntimeError('this chat message has no chat id to answer in')
        return send_teams(store, chat, body)
    if ch in ('telegram', 'whatsapp'):
        from . import messengers
        chat = str(msg.get('ConversationId') or '').split(':', 1)[-1]   # 'telegram:<id>' / 'whatsapp:<jid>'
        if not chat: raise RuntimeError('this chat message has no chat id to answer in')
        return (messengers.tg_send if ch == 'telegram' else messengers.wa_send)(store, chat, body)
    if ch == 'discord':
        from .devtools import discord_send
        chat = str(msg.get('ConversationId') or '').split(':', 1)[-1]   # 'discord:<channel_id>'
        if not chat: raise RuntimeError('this chat message has no channel id to answer in')
        return discord_send(store, chat, body)
    if ch == 'github':
        # the answer is a PUBLIC comment on the issue/PR - so it goes only with the owner's
        # explicit say-so (the GitHub card's 'Reply to issue/PR authors' switch)
        if not store.github_replies_ok():
            raise RuntimeError("replying on GitHub is off - flip 'Reply to issue/PR authors' "
                               'on the GitHub connector card to post comments')
        repo, _, num = ext[3:].rpartition('#')              # 'gh:owner/repo#N'
        if not (ext.startswith('gh:') and repo and num.isdigit()):
            raise RuntimeError('this github item carries no issue/PR reference to comment on')
        c = store.get_connector_by_type('github', with_secret=True)
        if not (c and c.get('Secret')): raise RuntimeError('no GitHub PAT saved')
        from .github import comment_issue
        url = comment_issue(c['Secret'], repo, int(num), body)
        return {'channel': 'github', 'to': [f'{repo}#{num}'], 'url': url}
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
    out = llm(f"{HANDOFF_SYSTEM}\n\n{store.doc('soul') or ''}", f'{ask}\n\n{ctx}', max_tokens=700)
    return (out or '').strip()


# ── notifications: the timeline pushed INTO a chat, instead of you polling the tab ──────
# A channel can be an input (trigger), an output (notify), or both: give the connector the
# notify role and name the chat in its config (notify_chat). What qualifies is one setting -
# notify_level: needs_me (default) pings only what is waiting on YOU; all pings every new item.
def notify_targets(store) -> list:
    """[(channel, chat_id)] for every connector wearing the notify role with a chat named."""
    from .channels import _cfg
    from .store import roles_of
    out = []
    for c in store.list_connectors():
        if not c['Active'] or 'notify' not in roles_of(c): continue
        chat = str(_cfg(c).get('notify_chat') or '').strip()
        if chat and c['Type'] in ('telegram', 'whatsapp', 'teams'): out.append((c['Type'], chat))
    return out


def notify(store, text: str, about: dict = None) -> int:
    """Push one short line to every notify channel. Never raises - a ping that fails must not
    take the ingest down with it - and never echoes: an event that HAPPENED in the notify chat
    is one you are already looking at."""
    from . import messengers
    sent = 0
    for ch, chat in notify_targets(store):
        if about and about.get('Channel') == ch and str(about.get('ConversationId') or '').endswith(chat):
            continue
        try:
            if ch == 'telegram': messengers.tg_send(store, chat, text)
            elif ch == 'whatsapp': messengers.wa_send(store, chat, text)
            else: send_teams(store, chat, text)
            sent += 1
        except Exception as e:
            logger.warning(f'notify via {ch} failed: {e}')
    return sent
