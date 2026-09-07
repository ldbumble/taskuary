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


class ListingStopped(RuntimeError):
    """The provider's paging ended before the conversation did (PW-010): what was listed so far, and why.
    A repeated page, an empty continued page or the page budget used to end the walk silently, and the
    coverage row then claimed the thread was complete."""
    def __init__(self, ids: list, why: str): super().__init__(why); self.ids, self.why = ids, why


class IMAPIdentityError(RuntimeError):
    """The poll's captured folder identity changed while its chain was being read."""


class IMAPRestoreError(RuntimeError):
    """A chain lookup could not prove that it restored the poll's selected folder."""


def list_ids_graph(tok: str, upn: str, conversation_id: str) -> list:
    """Every message of a conversation across the mailbox's folders - ids and metadata only. Listing
    is how gaps are found; it never carries a body (PW-010)."""
    url = f'{_ch.GRAPH}/users/{upn}/messages'
    params, out, seen, urls = {'$filter': f"conversationId eq '{conversation_id}'", '$select': GRAPH_LIST_SELECT, '$top': 50}, [], set(), set()
    # pagination is followed to completion, but never blindly (a mocked transport once kept this loop alive
    # until the process ran out of memory). A walk that ENDS EARLY - a repeated link, an empty continued
    # page, the page budget - is not a complete listing: it raises with what it has, so coverage says so.
    while isinstance(url, str):
        if url in urls: raise ListingStopped(out, 'the provider repeated a page of the listing')
        if len(urls) >= MAX_PAGES: raise ListingStopped(out, f'the listing passed the {MAX_PAGES}-page budget')
        urls.add(url)
        r = _ch.requests.get(url, headers={'Authorization': f'Bearer {tok}'}, timeout=30, params=params)
        r.raise_for_status(); j = r.json()
        page = [x for x in (j.get('value') if isinstance(j, dict) else None) or [] if isinstance(x, dict) and isinstance(x.get('id'), str) and x['id'] not in seen]
        if not page:
            if out: raise ListingStopped(out, 'an empty page ended the listing early')
            break                                          # a conversation with nothing in it is complete, not stopped
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


def needs_history(store, conversation_id: str, mailbox: str = None) -> bool:
    """Never completed FROM THIS MAILBOX, or the last attempt failed - list it again; a complete chain is left
    alone. Coverage is the mailbox's (PW-011): another account sharing the conversation id completes its own."""
    cov = store.chain_coverage(conversation_id, mailbox)
    return cov is None or not cov.get('complete')


def coverage(store, conversation_id: str, mailbox: str = None):
    """What the store knows about how complete this conversation is (for one mailbox, or the latest row
    when the caller has none), or None when never checked."""
    return store.chain_coverage(conversation_id, mailbox)


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
    stopped = None
    try:
        try: listed = list_ids_graph(tok, mailbox, conversation_id)
        except ListingStopped as e: listed, stopped = e.ids, e.why           # keep what was listed; the coverage says it stopped
        missing = [x['id'] for x in listed if x.get('id') and not store.message_exists(f"graph:{x['id']}")]
        added = 0
        for m in fetch_graph(tok, mailbox, missing):
            frm = (m.get('from') or {}).get('emailAddress') or {}
            added += _keep(store, conversation_id, f"graph:{m['id']}",
                           {'subject': m.get('subject'), 'body': _ch._body(m), 'from_name': frm.get('name'), 'from_email': frm.get('address'),
                            'to': _ch._addrs(m.get('toRecipients')), 'cc': _ch._addrs(m.get('ccRecipients')),
                            'sent_at': _ch._local(m.get('receivedDateTime') or ''), 'source_link': m.get('webLink')}, mailbox, before)
        cov = {'complete': stopped is None, 'listed': len(listed), 'added': added, 'error': stopped}
    except Exception as e:
        logger.warning(f'chains: could not complete {conversation_id} from {mailbox}: {e}')
        cov = {'complete': False, 'listed': 0, 'added': 0, 'error': str(e)[:200]}
    store.set_chain_coverage(conversation_id, 'email', mailbox, cov)
    return cov


def _imap_search(M, box: str, root: str, readonly: bool = True) -> list:
    typ, _d = M.select(box if box == 'INBOX' else f'"{box}"', readonly=readonly)
    if typ != 'OK': raise RuntimeError(f'SELECT {box} returned {typ}: {_d}')
    typ, data = M.uid('search', None, f'(OR HEADER Message-ID "{root}" HEADER References "{root}")')
    if typ != 'OK': raise RuntimeError(f'SEARCH {box} returned {typ}: {data}')
    return sorted(int(x) for x in (data[0] or b'').split())


def refresh_imap(store, M, user: str, root: str, restore: str = 'INBOX', readonly: bool = True,
                 before: str = None, folder_identity=None, protected=None,
                 protected_after=None) -> dict:
    """Complete one IMAP conversation - the thread keyed by its root Message-ID, through References -
    across INBOX and the Sent folder; the owner's own mail is `context`, the rest `history`.

    The poll supplies its exact folder identity and protects every Inbox UID it still owns. That
    keeps history retrieval from duplicating a scoped row or swallowing pending work as history.
    """
    from .imapmail import sent_folder, _dec, _hdr_addrs, _body_and_attachments, _external_id, _validity
    protected = {str(box): {int(uid) for uid in uids}
                 for box, uids in dict(protected or {}).items()}
    protected_after = {str(box): int(uid) for box, uid in dict(protected_after or {}).items()}
    added, seen, failed, fatal = 0, 0, 0, None
    try:
        boxes = [('INBOX', False)]
        sent = sent_folder(M)
        if sent: boxes.append((sent, True))
        for box, is_sent in boxes:
            # Historical discovery is always read-only. The owner's mark-read switch applies to
            # arriving Inbox work, never to old context fetched for a chain.
            uids = _imap_search(M, box, root, readonly=True)
            identity = None
            if folder_identity:
                try:
                    identity = folder_identity(is_sent, box, _validity(M), tuple(uids))
                except Exception as e:
                    raise IMAPIdentityError(f'IMAP folder identity changed while reading {box}') from e
            for uid in uids:
                seen += 1
                if (uid in protected.get(box, set())
                        or (box in protected_after and uid > protected_after[box])):
                    continue
                ext = (_external_id(is_sent, user, uid, scope=identity['scope'],
                                    validity=identity.get('validity'), mode=identity['mode'])
                       if identity else f'{"imap-sent" if is_sent else "imap"}:{user}:{uid}')
                if store.message_exists(ext): continue
                typ, parts = M.uid('fetch', str(uid), '(RFC822)')
                if typ != 'OK' or not parts or parts[0] is None: failed += 1; continue   # counted: a skipped body is a gap, not coverage (PW-010)
                msg = email.message_from_bytes(parts[0][1])
                name, addr = email.utils.parseaddr(_dec(msg.get('From')))
                body, _atts = _body_and_attachments(msg)
                try: when = email.utils.parsedate_to_datetime(msg.get('Date')).astimezone().strftime('%Y-%m-%d %H:%M:%S')
                except Exception: when = None
                added += _keep(store, root, ext, {'subject': _dec(msg.get('Subject')), 'body': body[:20000], 'from_name': name or addr,
                                                  'from_email': addr, 'to': _hdr_addrs(msg, 'To'), 'cc': _hdr_addrs(msg, 'Cc'), 'sent_at': when}, user, before)
        cov = {'complete': failed == 0, 'listed': seen, 'added': added,
               'error': None if not failed else f'{failed} message{"s" if failed != 1 else ""} of the thread could not be fetched'}
    except IMAPIdentityError as e:
        fatal = e
        cov = {'complete': False, 'listed': seen, 'added': added, 'error': str(e)[:200]}
    except Exception as e:
        logger.warning(f'chains: could not complete {root} from {user}: {e}')
        cov = {'complete': False, 'listed': seen, 'added': added, 'error': str(e)[:200]}
    restore_error = None
    try:
        typ, detail = M.select(restore, readonly=readonly)
        if typ != 'OK':
            restore_error = IMAPRestoreError(f'SELECT {restore} returned {typ}: {detail}')
        elif folder_identity:
            try:
                folder_identity(False, restore, _validity(M), ())
            except Exception as e:
                restore_error = IMAPRestoreError(
                    f'{restore} identity changed while restoring after chain retrieval: {e}')
    except Exception as e:
        restore_error = IMAPRestoreError(f'SELECT {restore} failed: {e}')
    if restore_error:
        cov = {'complete': False, 'listed': seen, 'added': added, 'error': str(restore_error)[:200]}
    store.set_chain_coverage(root, 'email', user, cov)
    if restore_error:
        raise restore_error
    if fatal:
        raise fatal
    return cov
