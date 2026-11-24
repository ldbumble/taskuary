"""THE MAILBOX ITSELF, READ-ONLY (the owner, 2026-11-24: "the Advisor should look at Taskuary AND the connector itself").

Taskuary's stored mail is a window: a sent mail it never read back, a reply that landed outside the sync window, a thread older than
the first sync are only in the mailbox. This asks the connected mailbox directly - every email source's own card, Graph for Outlook,
IMAP for Gmail and IMAP cards - by person, subject and date, in the Sent folder, the Inbox or both. It never sends, moves, flags or
marks anything: Graph is only GET, an IMAP folder is SELECTed read-only and fetched with BODY.PEEK.

One answer shape for every provider: {box, folder ('sent' | 'inbox'), at, from, to, subject, conv, snippet}. A box that could not be
asked is said in `errors`, never taken as "nothing there".
"""
import email, email.utils
from datetime import datetime, timedelta
from loguru import logger

FOLDERS, SNIP, CAP = ('sent', 'inbox'), 300, 25


def boxes(store) -> list:
    "[(the mailbox address, its connector with its secret)] for every active email source whose card can be asked"
    out = []
    for s in store.list_sources():
        if s.get('Channel') != 'email' or not s.get('ConnectorId') or not s.get('Address'): continue
        c = store.get_connector(s['ConnectorId'], with_secret=True)
        if c and c.get('Active') and c.get('Type') in ('outlook', 'gmail', 'imap'): out.append((s['Address'], c))
    return out


def search(store, who: str = '', subject: str = '', folder: str = '', days: int = 30, limit: int = 10) -> tuple:
    """(hits newest first, errors): messages in the connected mailboxes where `who` is the other side (to them in Sent, from them in the
    Inbox) and the subject holds `subject`, sent in the last `days`. `folder`: 'sent', 'inbox', or '' for both."""
    who, subject = ' '.join(str(who or '').replace('"', '').split())[:120], ' '.join(str(subject or '').replace('"', '').split())[:120]
    folders = [folder] if folder in FOLDERS else list(FOLDERS)
    since, limit = datetime.now() - timedelta(days=max(1, min(int(days or 30), 365))), max(1, min(int(limit or 10), CAP))
    hits, errors = [], []
    for box, c in boxes(store):
        for f in folders:
            try: hits += (_graph if c['Type'] == 'outlook' else _imap)(store, c, box, f, who, subject, since, limit)
            except Exception as e:
                logger.info(f'mailboxread: {box} {f} not read - {e}'); errors.append(f'{box} {f}: {str(e)[:120]}')
    return sorted(hits, key=lambda h: h['at'], reverse=True)[:limit], errors


def _hit(box, folder, at, frm, to, subject, conv, body) -> dict:
    text = ' '.join(str(body or '').split())
    return {'box': box, 'folder': folder, 'at': at, 'from': frm, 'to': to, 'subject': ' '.join(str(subject or '').split()),
            'conv': conv or '', 'snippet': text[:SNIP] + ('…' if len(text) > SNIP else '')}


def _graph(store, c, box, folder, who, subject, since, limit) -> list:
    import requests
    from .channels import GRAPH, _local, graph_creds, graph_token
    cfg, sec, _ = graph_creds(store, c)
    # KQL: Graph's $search takes no $filter or $orderby beside it, so the date is checked here
    kql = ' AND '.join([*([f"{'to' if folder == 'sent' else 'from'}:{who}"] if who else []), *([f'subject:{subject}'] if subject else [])])
    params = {'$top': limit * 2, '$select': 'subject,from,toRecipients,sentDateTime,receivedDateTime,conversationId,bodyPreview'}
    if kql: params['$search'] = f'"{kql}"'
    else: params |= {'$orderby': 'receivedDateTime desc', '$filter': f"receivedDateTime ge {since.strftime('%Y-%m-%dT%H:%M:%SZ')}"}
    r = requests.get(f"{GRAPH}/users/{box}/mailFolders/{'sentitems' if folder == 'sent' else 'inbox'}/messages", timeout=20,
                     headers={'Authorization': f'Bearer {graph_token(cfg, sec)}'}, params=params)
    r.raise_for_status()
    out = []
    for m in (r.json() or {}).get('value') or []:
        at = str(_local(m.get('sentDateTime') or m.get('receivedDateTime') or ''))[:19]
        if at < since.strftime('%Y-%m-%d %H:%M:%S'): continue
        frm = ((m.get('from') or {}).get('emailAddress') or {}).get('address') or ''
        to = [(x.get('emailAddress') or {}).get('address') or '' for x in m.get('toRecipients') or []]
        out.append(_hit(box, folder, at, frm, to, m.get('subject'), m.get('conversationId'), m.get('bodyPreview')))
    return out


def _imap(store, c, box, folder, who, subject, since, limit) -> list:
    from .imapmail import FETCH_BODY, _body_and_attachments, _dec, _hdr_addrs, _login, _quoted, sent_folder, thread_key
    M, _user = _login(c)
    try:
        name = sent_folder(M) if folder == 'sent' else 'INBOX'
        if not name: return []
        typ, _ = M.select(_quoted(name), readonly=True)
        if typ != 'OK': return []
        q = [f"SINCE {since.strftime('%d-%b-%Y')}", *([f"{'TO' if folder == 'sent' else 'FROM'} \"{who}\""] if who else []),
             *([f'SUBJECT "{subject}"'] if subject else [])]
        typ, data = M.uid('search', None, f"({' '.join(q)})")
        if typ != 'OK': return []
        out = []
        for uid in [u for u in (data[0] or b'').split()][-limit:]:
            typ, parts = M.uid('fetch', uid.decode() if isinstance(uid, bytes) else str(uid), f'({FETCH_BODY})')
            if typ != 'OK' or not parts or not isinstance(parts[0], (tuple, list)): continue
            msg = email.message_from_bytes(bytes(parts[0][1]))
            try: at = email.utils.parsedate_to_datetime(msg.get('Date')).astimezone().strftime('%Y-%m-%d %H:%M:%S')
            except Exception: at = ''
            frm = (_hdr_addrs(msg, 'From') or [''])[0]
            out.append(_hit(box, folder, at, frm, _hdr_addrs(msg, 'To'), _dec(msg.get('Subject')), str(thread_key(msg) or ''),
                            _body_and_attachments(msg)[0]))
        return out
    finally:
        try: M.logout()
        except Exception: pass


def line(h: dict) -> str:
    "One hit as the Advisor reads it: when, which folder, who wrote whom, the subject and its first words."
    who = f"the owner wrote to {', '.join(h['to'][:3]) or 'someone'}" if h['folder'] == 'sent' else f"from {h['from'] or '?'}"
    return f"- mailbox {h['at'][:16]} [{h['folder']}] {who}: \"{h['subject'][:90]}\" - {h['snippet'][:160]}"

