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


def _source_connector_id(store, channel, address):
    """The instance owning a source address/chat. Replies must leave through the same account
    they arrived through when several connectors share a type."""
    src = next((s for s in store.list_sources(active_only=False)
                if s.get('Channel') == channel and str(s.get('Address') or '') == str(address or '')
                and s.get('ConnectorId')), None)
    return src.get('ConnectorId') if src else None


def _graph_token(store, kind='outlook', connector_id=None):
    from .channels import graph_creds, graph_token
    c = store.get_connector(int(connector_id), with_secret=True) if connector_id else \
        store.get_connector_by_type(kind, with_secret=True)
    if c and c.get('Type') != kind: c = None
    if not c or not c.get('Active'): raise RuntimeError(f'the {kind} connection is not set up')
    cfg, sec, _ = graph_creds(store, c)
    return graph_token(cfg, sec)


def _mailbox(store, msg=None):
    """Which mailbox sends. The one the message arrived in, else the first email source."""
    if msg and msg.get('SourceName') and '@' in (msg['SourceName'] or ''): return msg['SourceName']
    src = next((s for s in store.list_sources() if s['Channel'] == 'email'), None)
    if not src: raise RuntimeError('no mailbox configured - add one under Connections → Outlook')
    return src['Address']


def addrs(xs) -> list:
    """The addresses in a list, deduplicated, order kept. Anything without an @ is not one."""
    seen, out = set(), []
    for x in xs or []:
        a = str(x or '').strip()
        if '@' in a and a.lower() not in seen: seen.add(a.lower()); out.append(a)
    return out


def send_email(store, to: list, subject: str, body: str, reply_to_graph_id: str = None, mailbox: str = None,
               connector_id=None, cc: list = None) -> dict:
    """Reply in thread when we know the Graph message id, otherwise a new mail. Plain text:
    these are answers from a person, not marketing.

    `cc` is looping somebody in - the owner adding a colleague to their own answer, in the open
    where the sender can see it. It rides the same approval and the same audit line as the reply
    itself, because it IS the reply: one send, one record of who received it."""
    box = mailbox or _mailbox(store)
    connector_id = connector_id or _source_connector_id(store, 'email', box)
    tok = _graph_token(store, connector_id=connector_id)
    to, cc = addrs(to), addrs(cc)
    if not to and not reply_to_graph_id: raise RuntimeError('no recipient')
    hdr = {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}
    if reply_to_graph_id:
        # Graph reads the reply `comment` as HTML, so plain-text newlines collapse into one long
        # line - greeting, body and signature all jammed together. Escape and give the breaks back.
        import html as _html
        comment = _html.escape(body).replace(chr(10), '<br>')
        # a reply with NO message object keeps Graph's own recipients; the moment we send one it
        # replaces them, so `to` has to go back in whenever there is a cc to add
        m = {}
        if to: m['toRecipients'] = [{'emailAddress': {'address': a}} for a in to]
        if cc: m['ccRecipients'] = [{'emailAddress': {'address': a}} for a in cc]
        r = requests.post(f'{GRAPH}/users/{box}/messages/{reply_to_graph_id}/reply', headers=hdr, timeout=30,
                          data=json.dumps({'message': m, 'comment': comment}))
    else:
        r = requests.post(f'{GRAPH}/users/{box}/sendMail', headers=hdr, timeout=30,
                          data=json.dumps({'message': {'subject': subject or '(no subject)',
                                                       'body': {'contentType': 'Text', 'content': body},
                                                       'toRecipients': [{'emailAddress': {'address': a}} for a in to],
                                                       **({'ccRecipients': [{'emailAddress': {'address': a}} for a in cc]} if cc else {})},
                                           'saveToSentItems': True}))
    if r.status_code >= 300:
        raise RuntimeError(f'graph sendMail failed ({r.status_code}): {r.text[:300]}')
    return {'channel': 'email', 'to': to, 'cc': cc, 'mailbox': box, 'threaded': bool(reply_to_graph_id)}


def send_teams(store, chat_id: str, body: str, connector_id=None) -> dict:
    """Post into a chat. App-only posting needs ChatMessage.Send on the app registration,
    which reading does NOT include - say so plainly rather than failing with a 403 blob."""
    tok = _graph_token(store, 'teams', connector_id)
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
SENDABLE = ('email', 'teams', 'slack', 'telegram', 'whatsapp', 'imessage', 'discord', 'github')
# 'own' and 'assistant' are rows TASKUARY WROTE: work you started here, a note to yourself, a
# meeting prep, the assistant speaking up. Nobody sent them, so there is nobody to answer - and
# without them here a prep task closing drafted a reply, signed it in the owner's name, and put
# it in Review addressed to no one at all.
NEVER = {'report', 'own', 'assistant', 'jira', 'asana', 'monday', 'clickup', 'todoist', 'gitlab',
         'azdo', 'linear', 'trello', 'notion', 'sentry', 'pagerduty', 'aws', 'azure'}


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


def send_out(store, channel: str, to, subject: str, body: str, cc: list = None) -> dict:
    """Send something nobody asked for: a report going OUT, to an address the owner chose.

    reply_to_message answers a message - it reads the mailbox, thread id and chat id off the row
    that arrived. An outbound report has no such row, so the destination has to be given. Same
    senders underneath, same credentials, same channel switches: a channel the owner turned off
    for replies is off for this too, because "Taskuary may write to Slack" is one decision and
    not two.
    """
    to = [t.strip() for t in (to if isinstance(to, (list, tuple)) else str(to or '').split(',')) if str(t).strip()]
    ch, cc = (channel or 'email').lower(), addrs(cc)
    if cc and ch != 'email':
        raise RuntimeError(f'{ch} has no cc - only mail can copy somebody in')
    if not can_reply(store, ch):
        raise RuntimeError(f'sending on {ch} is off - Settings → Replies decides which channels '
                           'Taskuary may write to, and it governs outbound reports too')
    if ch == 'email':
        if not to: raise RuntimeError('no recipient - an outbound email needs an address')
        # Graph when the Outlook card is connected, otherwise the IMAP mailbox's own SMTP
        c = store.get_connector_by_type('outlook')
        if c and c.get('Active'):
            return send_email(store, to, subject or '(no subject)', body, cc=cc)
        from .imapmail import send_smtp
        box = next((store.get_connector(x['ConnectorId'], with_secret=True) for x in store.list_connectors()
                    if x['Type'] in ('gmail', 'imap') and x['Active']), None)
        if not box: raise RuntimeError('no mailbox is connected to send from')
        return send_smtp(store, box, to, subject or '(no subject)', body, cc=cc)
    if ch == 'teams':
        if not to: raise RuntimeError('no chat id - a Teams message needs one to land in')
        return send_teams(store, to[0], f'**{subject}**\n\n{body}' if subject else body)
    if ch in ('telegram', 'whatsapp'):
        from . import messengers
        if not to: raise RuntimeError(f'no chat id - a {ch} message needs one to land in')
        return (messengers.tg_send if ch == 'telegram' else messengers.wa_send)(
            store, to[0], f'{subject}\n\n{body}' if subject else body)
    if ch == 'imessage':
        from .imessage import send_text
        if not to: raise RuntimeError('no chat id - an Apple Messages message needs the chat guid to land in')
        return send_text(store, to[0], f'{subject}\n\n{body}' if subject else body)
    if ch == 'discord':
        from .devtools import discord_send
        if not to: raise RuntimeError('no channel id - a Discord message needs one to land in')
        return discord_send(store, to[0], f'**{subject}**\n\n{body}' if subject else body)
    raise RuntimeError(f'cannot send on {ch} - email, Teams, Telegram, WhatsApp, Apple Messages and Discord can carry a report out')


# ── where a report may be SENT: the destinations the builder is allowed to offer ────────
# A chat id is a Graph id or a WhatsApp JID - nothing anyone can look up, and a typo is a
# silent failure at 6am - so the report builder PICKS both the channel and the destination
# out of what Taskuary can actually reach today. A channel with no connection behind it, or
# one switched off under Settings → Replies, is not an option at all.
REPORTABLE = ('email', 'teams', 'telegram', 'whatsapp', 'imessage', 'discord')   # what send_out can carry
MAILBOXES = ('outlook', 'gmail', 'imap')


def send_channels(store) -> list:
    """The channels a report can go out on right now: send_out can carry them, replies are on
    for them, and a connector of that kind is active."""
    live = {c['Type'] for c in store.list_connectors() if c['Active']}
    have = lambda ch: bool(live.intersection(MAILBOXES)) if ch == 'email' else ch in live
    return [ch for ch in REPORTABLE if can_reply(store, ch) and have(ch)]


def _chat_id(channel: str, cid) -> str:
    """'whatsapp:1555...@s.whatsapp.net' -> the JID; 'teams:19:x@thread.v2' -> '19:x@thread.v2'."""
    cid = str(cid or '')
    return cid[len(channel) + 1:] if cid.lower().startswith(f'{channel}:') else cid


def send_targets(store) -> list:
    """[{'channel', 'to': [{'to', 'name', 'hint'}]}] - every destination known on every
    channel a report can go out on: your own notify chat first, then the chats you already
    take messages from, then everything else that has written in. Email also gets the
    address book, and is the one channel where typing a new address still makes sense."""
    from .channels import _cfg
    seen = {ch: {} for ch in send_channels(store)}

    def add(ch, to, name='', hint=''):
        to = str(to or '').strip()
        if not to or ch not in seen: return
        r = seen[ch].setdefault(to, {'to': to, 'name': '', 'hint': ''})
        if name and not r['name']: r['name'] = name
        if hint and not r['hint']: r['hint'] = hint

    for c in store.list_connectors():
        if not c['Active']: continue
        ch = 'email' if c['Type'] in MAILBOXES else c['Type']
        cfg = _cfg(c)
        add(ch, cfg.get('notify_chat'), f'you — your own {ch}', f"the notify chat on the {c['Name']} card")
        if ch == 'email': add(ch, cfg.get('address'), f"you — {cfg.get('address')}", f"the mailbox on the {c['Name']} card")
    for s in store.list_sources():
        add((s.get('Channel') or '').lower(), s.get('Address'), '', 'a chat you already take messages from')
    for r in store.chats():
        ch = (r['Channel'] or '').lower()
        add(ch, _chat_id(ch, r['Cid']), r['Name'], f"{r['N']} message{'' if r['N'] == 1 else 's'}, last {(r['Last'] or '')[:16]}")
    if 'email' in seen:
        for p in store.people(30):
            add('email', p['Email'], p['Name'], f"{p['N']} message{'' if p['N'] == 1 else 's'}, last {(p['Last'] or '')[:16]}")
    for tos in seen.values():
        for r in tos.values():
            if not r['name']: r['name'] = r['to']
    return [{'channel': ch, 'to': list(tos.values())} for ch, tos in seen.items()]


def reply_to_message(store, msg: dict, body: str, to: list = None, cc: list = None) -> dict:
    """Answer wherever the request came from. The message row carries everything needed:
    the mailbox it arrived in, the Graph id for threading, or the chat id."""
    ch, ext = msg.get('Channel'), str(msg.get('ExternalId') or '')
    cc = addrs(cc)
    # cc is a mail idea. A chat has members, not recipients, and quietly dropping the person the
    # owner meant to loop in is the one outcome worth refusing over
    if cc and ch != 'email':
        raise RuntimeError(f'a {ch} message has no cc - answer by email to copy somebody, '
                           'or add them to the chat itself')
    if ch == 'email' and ext.startswith('imap:'):
        # mail that arrived over IMAP goes back over the provider's own SMTP, in-thread
        from .imapmail import send_smtp
        box = msg.get('SourceName') or ''
        c = next((store.get_connector(x['ConnectorId'], with_secret=True) for x in store.list_connectors()
                  if x['Type'] in ('gmail', 'imap') and x['Active']
                  and json.loads(x.get('ConfigJson') or '{}').get('address', '').lower() == box.lower()), None)
        if not c: raise RuntimeError(f'no IMAP connection is set up for {box}')
        return send_smtp(store, c, to or [msg.get('FromEmail')], f"Re: {msg.get('Subject') or ''}".strip(),
                         body, in_reply_to=msg.get('ConversationId'), cc=cc)
    if ch == 'email':
        return send_email(store, to or [msg.get('FromEmail')], f"Re: {msg.get('Subject') or ''}".strip(),
                          body, ext[6:] if ext.startswith('graph:') else None, msg.get('SourceName'),
                          _source_connector_id(store, 'email', msg.get('SourceName')), cc=cc)
    if ch == 'teams':
        chat = (msg.get('ConversationId') or '')[6:]        # 'teams:19:...'
        if not chat: raise RuntimeError('this chat message has no chat id to answer in')
        return send_teams(store, chat, body, _source_connector_id(store, 'teams', msg.get('SourceName')))
    if ch in ('telegram', 'whatsapp'):
        from . import messengers
        chat = str(msg.get('ConversationId') or '').split(':', 1)[-1]   # 'telegram:<id>' / 'whatsapp:<jid>'
        if not chat: raise RuntimeError('this chat message has no chat id to answer in')
        send = messengers.tg_send if ch == 'telegram' else messengers.wa_send
        connector_id = _source_connector_id(store, ch, chat)
        return send(store, chat, body, connector_id) if connector_id else send(store, chat, body)
    if ch == 'imessage':
        from .imessage import send_text
        chat = str(msg.get('ConversationId') or '')[9:]                 # 'imessage:<chat guid>'
        if not chat: raise RuntimeError('this chat message has no chat id to answer in')
        connector_id = _source_connector_id(store, 'imessage', chat)
        return send_text(store, chat, body, connector_id) if connector_id else send_text(store, chat, body)
    if ch == 'discord':
        from .devtools import discord_send
        chat = str(msg.get('ConversationId') or '').split(':', 1)[-1]   # 'discord:<channel_id>'
        if not chat: raise RuntimeError('this chat message has no channel id to answer in')
        connector_id = _source_connector_id(store, 'discord', chat)
        return discord_send(store, chat, body, connector_id) if connector_id else discord_send(store, chat, body)
    if ch == 'github':
        # the answer is a PUBLIC comment on the issue/PR - so it goes only with the owner's
        # explicit say-so (the GitHub card's 'Reply to issue/PR authors' switch)
        if not store.github_replies_ok():
            raise RuntimeError("replying on GitHub is off - flip 'Reply to issue/PR authors' "
                               'on the GitHub connector card to post comments')
        repo, _, num = ext[3:].rpartition('#')              # 'gh:owner/repo#N'
        if not (ext.startswith('gh:') and repo and num.isdigit()):
            raise RuntimeError('this github item carries no issue/PR reference to comment on')
        connector_id = _source_connector_id(store, 'github', repo)
        c = store.get_connector(connector_id, with_secret=True) if connector_id else \
            store.get_connector_by_type('github', with_secret=True)
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
        if chat and c['Type'] in ('telegram', 'whatsapp', 'teams'):
            out.append((c['Type'], chat, c['ConnectorId']))
    return out


def notify(store, text: str, about: dict = None) -> int:
    """Push one short line to every notify channel. Never raises - a ping that fails must not
    take the ingest down with it - and never echoes: an event that HAPPENED in the notify chat
    is one you are already looking at."""
    from . import messengers
    sent = 0
    for ch, chat, connector_id in notify_targets(store):
        if about and about.get('Channel') == ch and str(about.get('ConversationId') or '').endswith(chat):
            continue
        try:
            if ch == 'telegram': messengers.tg_send(store, chat, text, connector_id)
            elif ch == 'whatsapp': messengers.wa_send(store, chat, text, connector_id)
            else: send_teams(store, chat, text, connector_id)
            sent += 1
        except Exception as e:
            logger.warning(f'notify via {ch} failed: {e}')
    return sent
