"""The full email chain, fetched once and kept once (PW-009 to PW-015).

A mail arrived alone: triage saw it and whatever earlier messages happened to be stored, and a
reply to a thread that began before the watermark, in another folder, or while the app was closed
had no history at all. A conversation newly encountered - or one with gaps - has its missing
history retrieved from the provider: the thread is LISTED first (ids and metadata only), and only
the messages not yet stored have their bodies fetched, once. Fetched history lives on the
conversation as `history` rows (the owner's own sent mail as `context`), never on a task, never in
the feed or Unread, never re-triaged; coverage is recorded per conversation and an incomplete or
failed retrieval is said in the context the model gets, never presented as the whole thread.
"""
import json
import email, email.utils
from loguru import logger
from . import channels as _ch

GRAPH_LIST_SELECT = 'id,receivedDateTime,from,conversationId'
MAX_PAGES = 200              # 10,000 messages of one conversation - a listing beyond this is a provider fault, not a thread


def list_ids_graph(tok: str, upn: str, conversation_id: str) -> list:
    """Every message of a conversation across the mailbox's folders - ids and metadata only. Listing
    is how gaps are found; it never carries a body (PW-010)."""
    url = f'{_ch.GRAPH}/users/{upn}/messages'
    params, out, seen, urls = {'$filter': f"conversationId eq '{conversation_id}'", '$select': GRAPH_LIST_SELECT, '$top': 50}, [], set(), set()
    # pagination is followed to completion, but never blindly: a page that brings nothing new, a next
    # link already visited, a non-string link or a page budget ends the walk (a mocked transport once
    # kept this loop alive until the process ran out of memory)
    while isinstance(url, str) and url not in urls and len(urls) < MAX_PAGES:
        urls.add(url)
        r = _ch.requests.get(url, headers={'Authorization': f'Bearer {tok}'}, timeout=30, params=params)
        r.raise_for_status(); j = r.json()
        page = [x for x in (j.get('value') if isinstance(j, dict) else None) or [] if isinstance(x, dict) and isinstance(x.get('id'), str) and x['id'] not in seen]
        if not page: break
        out += page; seen.update(x['id'] for x in page)
        url, params = j.get('@odata.nextLink'), None
    return out


def fetch_graph(tok: str, upn: str, ids: list) -> list:
    """The bodies of exactly these messages - the ones the store does not hold."""
    out = []
    for gid in ids:
        r = _ch.requests.get(f'{_ch.GRAPH}/users/{upn}/messages/{gid}', headers={'Authorization': f'Bearer {tok}'},
                             timeout=30, params={'$select': _ch.MAIL_SELECT})
        r.raise_for_status(); out.append(r.json())
    return out


def needs_history(store, conversation_id: str) -> bool:
    """Never completed here, or the last attempt failed - list it again; a complete chain is left alone."""
    cov = store.chain_coverage(conversation_id)
    return cov is None or not cov.get('complete')


def coverage(store, conversation_id: str):
    """What the store knows about how complete this conversation is, or None when never checked."""
    return store.chain_coverage(conversation_id)


def _keep(store, conv: str, ext: str, m: dict, mailbox: str, before: str = None) -> int:
    """One historical message onto the conversation: the owner's own as `context` (the convention
    every surface reads as "you"), anyone else's as `history`. Never a task, never a route, never
    an arrival: chronology and identity kept, nothing revived (PW-012)."""
    if store.message_exists(ext): return 0
    # only what came BEFORE the mail being judged is history: a later reply already at the provider is
    # the poll's to bring in and triage - swallowed here as history it would never be judged at all
    if before and m.get('sent_at') and str(m['sent_at']) >= str(before): return 0
    frm = str(m.get('from_email') or '')
    own = bool(frm) and frm.lower() == str(mailbox or '').lower()
    store.add_message({'TaskId': None, 'ExternalId': ext, 'ConversationId': conv, 'Channel': 'email', 'SourceName': mailbox,
                       'Subject': m.get('subject'), 'FromName': 'You' if own else m.get('from_name'), 'FromEmail': frm or None,
                       'SentAt': m.get('sent_at'), 'BodyText': m.get('body'), 'SourceLink': m.get('source_link'),
                       'Status': 'context' if own else 'history',
                       'RecipientsJson': json.dumps({'to': list(m.get('to') or []), 'cc': list(m.get('cc') or [])})
                                         if (m.get('to') or m.get('cc')) else None})
    return 1


def refresh_outlook(store, tok: str, mailbox: str, conversation_id: str, before: str = None) -> dict:
    """Complete one Graph conversation: list it, fetch only what is missing, record coverage."""
    try:
        listed = list_ids_graph(tok, mailbox, conversation_id)
        missing = [x['id'] for x in listed if x.get('id') and not store.message_exists(f"graph:{x['id']}")]
        added = 0
        for m in fetch_graph(tok, mailbox, missing):
            frm = (m.get('from') or {}).get('emailAddress') or {}
            added += _keep(store, conversation_id, f"graph:{m['id']}",
                           {'subject': m.get('subject'), 'body': _ch._body(m), 'from_name': frm.get('name'), 'from_email': frm.get('address'),
                            'to': _ch._addrs(m.get('toRecipients')), 'cc': _ch._addrs(m.get('ccRecipients')),
                            'sent_at': _ch._local(m.get('receivedDateTime') or ''), 'source_link': m.get('webLink')}, mailbox, before)
        cov = {'complete': True, 'listed': len(listed), 'added': added, 'error': None}
    except Exception as e:
        logger.warning(f'chains: could not complete {conversation_id} from {mailbox}: {e}')
        cov = {'complete': False, 'listed': 0, 'added': 0, 'error': str(e)[:200]}
    store.set_chain_coverage(conversation_id, 'email', mailbox, cov)
    return cov


def _imap_search(M, box: str, root: str, readonly: bool = True) -> list:
    typ, _d = M.select(box if box == 'INBOX' else f'"{box}"', readonly=readonly)
    if typ != 'OK': return []
    typ, data = M.uid('search', None, f'(OR HEADER Message-ID "{root}" HEADER References "{root}")')
    if typ != 'OK': return []
    return sorted(int(x) for x in (data[0] or b'').split())


def refresh_imap(store, M, user: str, root: str, restore: str = 'INBOX', readonly: bool = True, before: str = None) -> dict:
    """Complete one IMAP conversation - the thread keyed by its root Message-ID, through References -
    across INBOX and the Sent folder; the owner's own mail is `context`, the rest `history`."""
    from .imapmail import sent_folder, _dec, _hdr_addrs, _body_and_attachments
    added, seen = 0, 0
    try:
        boxes = [('INBOX', f'imap:{user}:')]
        sent = sent_folder(M)
        if sent: boxes.append((sent, f'imap-sent:{user}:'))
        for box, prefix in boxes:
            for uid in _imap_search(M, box, root):
                seen += 1
                ext = f'{prefix}{uid}'
                if store.message_exists(ext): continue
                typ, parts = M.uid('fetch', str(uid), '(RFC822)')
                if typ != 'OK' or not parts or parts[0] is None: continue
                msg = email.message_from_bytes(parts[0][1])
                name, addr = email.utils.parseaddr(_dec(msg.get('From')))
                body, _atts = _body_and_attachments(msg)
                try: when = email.utils.parsedate_to_datetime(msg.get('Date')).astimezone().strftime('%Y-%m-%d %H:%M:%S')
                except Exception: when = None
                added += _keep(store, root, ext, {'subject': _dec(msg.get('Subject')), 'body': body[:20000], 'from_name': name or addr,
                                                  'from_email': addr, 'to': _hdr_addrs(msg, 'To'), 'cc': _hdr_addrs(msg, 'Cc'), 'sent_at': when}, user, before)
        cov = {'complete': True, 'listed': seen, 'added': added, 'error': None}
    except Exception as e:
        logger.warning(f'chains: could not complete {root} from {user}: {e}')
        cov = {'complete': False, 'listed': seen, 'added': added, 'error': str(e)[:200]}
    finally:
        try: M.select(restore, readonly=readonly)
        except Exception: pass
    store.set_chain_coverage(root, 'email', user, cov)
    return cov
