"""Any mailbox as an inbound channel: IMAP in, SMTP out - the protocols every provider speaks.

Outlook/Microsoft 365 has its own connector (Graph does threading and attachments better
there), but the rest of the world is Gmail, a domain.com mailbox, Yahoo, an ISP - and they
all take IMAP with a password or app password. Two catalog cards (`gmail` pre-filled,
`imap` blank) share this one implementation; both land messages as channel 'email', through
the same triage, with the same attachment pipeline, and replies go back over SMTP in-thread
(In-Reply-To/References), from the same address the mail arrived at.

Stdlib only (imaplib, smtplib, email) - nothing new frozen into the exe.
"""
import base64, email, email.utils, imaplib, json, re, smtplib, ssl
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.mime.text import MIMEText
from loguru import logger

BATCH = 25                  # messages per poll, like every other channel
HOSTS = {'gmail': ('imap.gmail.com', 'smtp.gmail.com')}


def _cfg(c): return json.loads(c.get('ConfigJson') or '{}')


def _hosts(c) -> tuple:
    cfg = _cfg(c)
    imap_h, smtp_h = HOSTS.get(c['Type'], (None, None))
    imap_h = (cfg.get('imap_host') or imap_h or '').strip()
    # the SMTP twin is usually the IMAP host with the service renamed - offer that guess
    smtp_h = (cfg.get('smtp_host') or smtp_h or imap_h.replace('imap.', 'smtp.', 1)).strip()
    return imap_h, smtp_h, cfg


def _login(c):
    imap_h, _smtp, cfg = _hosts(c)
    if not imap_h: raise RuntimeError('no IMAP host set - e.g. imap.yourdomain.com')
    user = (cfg.get('address') or '').strip()
    if not user: raise RuntimeError('no mailbox address set')
    if not c.get('Secret'): raise RuntimeError('no password saved - for Gmail use an App Password '
                                               '(myaccount.google.com > Security > App passwords)')
    if _microsoft(user, imap_h):
        # basic auth is gone from Outlook.com (Sept 2024) and Exchange Online (2023): the
        # password would be refused after the socket opened, so say the useful thing first
        raise RuntimeError('Microsoft mailboxes (Outlook.com, Hotmail, Microsoft 365) no longer accept IMAP passwords - '
                           'use the Outlook connector and Sign in with Microsoft')
    port = int(cfg.get('imap_port') or 993)
    try: M = imaplib.IMAP4_SSL(imap_h, port)
    except OSError as e:
        if getattr(e, 'winerror', None) == 10013 or 'forbidden by its access permissions' in str(e):
            raise RuntimeError(f'this PC blocked the connection to {imap_h}:{port} - a firewall or security agent stops '
                               'Taskuary from reaching the mail server; ask IT to allow it (or allow port 993)') from e
        raise
    M.login(user, c['Secret'])
    return M, user


_MS_DOMAINS = {'outlook.com', 'hotmail.com', 'live.com', 'msn.com', 'outlook.co.uk', 'hotmail.co.uk', 'live.co.uk'}
_MS_HOSTS = {'outlook.office365.com', 'outlook.office.com', 'imap-mail.outlook.com', 'smtp-mail.outlook.com', 'smtp.office365.com'}
def _microsoft(user: str, host: str) -> bool:
    return (user or '').rsplit('@', 1)[-1].lower() in _MS_DOMAINS or (host or '').lower() in _MS_HOSTS


def test_imap(store, c) -> str:
    M, user = _login(c)
    try:
        typ, data = M.select('INBOX', readonly=True)
        if typ != 'OK': raise RuntimeError(f'could not open INBOX: {data}')
        n = int((data[0] or b'0').decode() or 0)
        if not any(s['Channel'] == 'email' and s['Address'] == user for s in store.list_sources(active_only=False)):
            store.save_source({'Channel': 'email', 'Address': user, 'ConnectorId': c['ConnectorId'], 'Active': 1}, 'connector-test')
        return f'logged in as {user} - INBOX holds {n} messages; new mail flows in on the next sync'
    finally:
        M.logout()


def _dec(v) -> str:
    try: return str(make_header(decode_header(v or '')))
    except Exception: return v or ''


def _hdr_addrs(msg, name) -> list:
    """The addresses on one header. Cc vs To is what tells triage whether the mail was aimed
    at this mailbox or merely copied to it."""
    return [a for _n, a in email.utils.getaddresses([_dec(v) for v in (msg.get_all(name) or [])]) if a]


def _body_and_attachments(msg) -> tuple:
    """(text, attachments-shaped-like-Graph) so save_attachments and vision reuse the pipeline."""
    from .channels import _clean
    text, html, atts = '', '', []
    for part in msg.walk():
        if part.is_multipart(): continue
        ctype = part.get_content_type()
        fname = part.get_filename()
        payload = part.get_payload(decode=True) or b''
        if fname or part.get('Content-ID'):
            atts.append({'id': (part.get('Content-ID') or fname or str(len(atts))).strip('<>')[:60],
                         'name': _dec(fname) or f'part-{len(atts)}', 'contentType': ctype,
                         'size': len(payload), 'isInline': bool(part.get('Content-ID')),
                         'contentBytes': base64.b64encode(payload).decode()})
        elif ctype == 'text/plain' and not text:
            text = payload.decode(part.get_content_charset() or 'utf-8', 'replace')
        elif ctype == 'text/html' and not html:
            html = payload.decode(part.get_content_charset() or 'utf-8', 'replace')
    return (text or _clean(html) or '').strip(), atts


# ── the Sent folder ─────────────────────────────────────────────────────────────────────
# Outlook has one name for it and Graph exposes it as `sentitems`; IMAP servers agree on nothing,
# and Gmail hides it under a namespace. Without it an IMAP install has NO record of what the owner
# writes, which is why "Generate my reply style" on a perfectly connected IMAP card answered "no
# sent mail to learn from - connect the Outlook card" (owner, 2026-09-02). Ask the server instead
# of guessing: RFC 6154 marks the folder with \Sent, and the familiar names are the fallback.
SENT_NAMES = ('Sent', 'Sent Items', 'Sent Mail', 'INBOX.Sent', 'INBOX.Sent Items', '[Gmail]/Sent Mail')
# (flags) "separator" name - the name may be quoted or bare, and may itself contain the separator
_LIST_LINE = re.compile(r'^\((?P<flags>[^)]*)\)\s+(?:"(?P<sep>[^"]*)"|NIL)\s+(?P<name>.*)$')


def _list_line(raw) -> tuple:
    line = raw.decode('utf-8', 'replace') if isinstance(raw, (bytes, bytearray)) else str(raw)
    m = _LIST_LINE.match(line.strip())
    if not m: return '', ''
    return m.group('flags') or '', (m.group('name') or '').strip().strip('"')


def sent_folder(M) -> str:
    """The mailbox's Sent folder, as this server spells it. '' when there is none to be found."""
    try: typ, data = M.list()
    except Exception: return ''
    if typ != 'OK': return ''
    named = []
    for raw in data or []:
        flags, name = _list_line(raw)
        if not name: continue
        if '\\Sent' in flags: return name            # the server said so: no guessing needed
        named.append(name)
    lower = {n.lower(): n for n in named}
    return next((lower[w.lower()] for w in SENT_NAMES if w.lower() in lower), '')


def sent_window(c, days: int, cap: int = 300, progress=None) -> list:
    """What this mailbox has SENT in the last `days`, oldest first, each as
    {subject, body, sent_at, to, conversation_id, external_id}. [] when there is no Sent folder.

    Read-only by construction - the owner's own outbox is never modified, and nothing here is
    triaged: sent mail is evidence about how they write, never work arriving."""
    M, user = _login(c)
    try:
        box = sent_folder(M)
        if not box: return []
        typ, _d = M.select(_quoted(box), readonly=True)
        if typ != 'OK': return []
        since = (datetime.now() - timedelta(days=max(1, days))).strftime('%d-%b-%Y')
        typ, data = M.uid('search', None, f'(SINCE {since})')
        if typ != 'OK': return []
        uids = [int(u) for u in (data[0] or b'').split()][-cap:]
        out = []
        for uid in uids:
            # one fetch per message: say how far along, or the button sits silent for a minute
            if progress and len(out) % 20 == 0:
                progress('running', f'reading {user} - {len(out)} of {len(uids)} sent mails')
            try:
                typ, parts = M.uid('fetch', str(uid), '(RFC822)')
                if typ != 'OK' or not parts or parts[0] is None: continue
                msg = email.message_from_bytes(parts[0][1])
                body, _atts = _body_and_attachments(msg)
                try: when = email.utils.parsedate_to_datetime(msg.get('Date')).astimezone().strftime('%Y-%m-%d %H:%M:%S')
                except Exception: when = ''
                out.append({'external_id': f'imap-sent:{user}:{uid}', 'subject': _dec(msg.get('Subject')),
                            'body': body[:20000], 'sent_at': when, 'to': _hdr_addrs(msg, 'To'),
                            'from_email': user,
                            'conversation_id': (msg.get('References') or msg.get('Message-ID') or '').split()[0][:200] or None})
            except Exception as e:
                logger.debug(f'imap: sent uid {uid} skipped - {e}')
        return out
    finally:
        try: M.logout()
        except Exception: pass


def _quoted(name: str) -> str:
    """A folder with a space in it ('Sent Items', '[Gmail]/Sent Mail') must reach SELECT quoted."""
    return f'"{name}"' if any(ch in name for ch in ' ()') else name


def sent_history(store, days: int, cap: int = 300, progress=None) -> list:
    """Every IMAP/Gmail card's Sent folder for the window. The card list is the point: an install
    can have two mailboxes, and the owner writes the same way in both."""
    out = []
    for c in store.list_connectors():
        if c['Type'] not in ('imap', 'gmail') or not c['Active']: continue
        try: out += sent_window(store.get_connector(c['ConnectorId'], with_secret=True), days, cap, progress)
        except Exception as e:
            logger.warning(f"imap: could not read sent mail from {c.get('Name') or c['Type']} - {e}")
    return sorted(out, key=lambda m: m.get('sent_at') or '')


def ensure_source(store, c) -> bool:
    """Give an IMAP/Gmail card the source row the poller reads it through, if it has none. True
    when one was just made. The mailbox address IS the source name and it is already saved on the
    card, so there is nothing to ask the owner and nothing to guess."""
    user = (_cfg(c).get('address') or '').strip()
    if not user: return False
    if any(s['Channel'] == 'email' and (s.get('Address') or '').lower() == user.lower()
           for s in store.list_sources(active_only=False)): return False
    store.save_source({'Channel': 'email', 'Address': user, 'ConnectorId': c['ConnectorId'], 'Active': 1}, 'self-heal')
    logger.info(f'imap: {user} had no source row - added one so it is actually polled')
    return True


def poll_imap(store, c, sources: list, llm=None, file_only=False, backfill_days: int = 0) -> int:
    """UIDs are IMAP's own cursor: strictly increasing per mailbox, so the watermark on the
    connector never re-ingests - and a backfill just lowers the SINCE date, with dedupe
    catching anything already seen."""
    from .channels import images_for_triage, save_attachments, wants_read
    from .ingest import ingest_message
    M, user = _login(c)
    n = 0
    try:
        # readonly is what has always kept the funnel invisible in the mailbox: an ordinary
        # RFC822 fetch sets \Seen by itself. Only the mark-read switch opens the box for
        # writing, and then the flag is set explicitly, per message, after it is safely in.
        read_it = wants_read(store)
        M.select('INBOX', readonly=not read_it)
        _imap_h, _smtp_h, cfg = _hosts(c)
        last_uid = int(cfg.get('imap_uid') or 0)
        since = (datetime.now() - timedelta(days=max(backfill_days, 1))).strftime('%d-%b-%Y')
        typ, data = M.uid('search', None, f'(SINCE {since})')
        uids = [int(u) for u in (data[0] or b'').split()]
        new = [u for u in uids if u > last_uid][-BATCH:]
        for uid in new:
            typ, parts = M.uid('fetch', str(uid), '(RFC822)')
            if typ != 'OK' or not parts or parts[0] is None: continue
            msg = email.message_from_bytes(parts[0][1])
            frm_name, frm_addr = email.utils.parseaddr(_dec(msg.get('From')))
            if frm_addr.lower() == user.lower(): continue           # my own mail is not inbound work
            body, atts = _body_and_attachments(msg)
            try: sent = email.utils.parsedate_to_datetime(msg.get('Date')).astimezone().strftime('%Y-%m-%d %H:%M:%S')
            except Exception: sent = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            out = ingest_message(store, file_only=file_only, msg={
                'external_id': f'imap:{user}:{uid}', 'channel': 'email',
                'subject': _dec(msg.get('Subject')), 'body': body[:20000],
                'from_name': frm_name or frm_addr, 'from_email': frm_addr,
                'to': _hdr_addrs(msg, 'To'), 'cc': _hdr_addrs(msg, 'Cc'),
                # References threads replies the way Graph's conversationId does
                'conversation_id': (msg.get('References') or msg.get('Message-ID') or '').split()[0][:200] or None,
                'sent_at': sent, 'source_name': user,
                'images': images_for_triage(store, atts)}, llm=llm)
            n += out['status'] != 'duplicate'
            if atts and out.get('message_id') and out['status'] != 'duplicate':
                try: save_attachments(store, out['message_id'], atts, f'imap:{user}:{uid}')
                except Exception as e: logger.warning(f'imap attachments failed: {e}')
            if read_it:
                try: M.uid('store', str(uid), '+FLAGS', r'(\Seen)')
                except Exception as e: logger.warning(f'marking {user} uid {uid} seen failed: {e}')
        if new:
            store.set_connector_config(c['ConnectorId'], {**cfg, 'imap_uid': max(new)})
    finally:
        M.logout()
    return n


def send_smtp(store, c, to: list, subject: str, body: str, in_reply_to: str = None) -> dict:
    """The reply, over the provider's own SMTP, threaded with In-Reply-To/References."""
    imap_h, smtp_h, cfg = _hosts(c)
    user = (cfg.get('address') or '').strip()
    m = MIMEText(body, 'plain', 'utf-8')
    m['From'], m['To'], m['Subject'] = user, ', '.join(to), subject or '(no subject)'
    if in_reply_to:
        m['In-Reply-To'] = in_reply_to
        m['References'] = in_reply_to
    port = int(cfg.get('smtp_port') or 587)
    with smtplib.SMTP(smtp_h, port, timeout=30) as S:
        S.starttls(context=ssl.create_default_context())
        S.login(user, c['Secret'])
        S.sendmail(user, to, m.as_string())
    return {'channel': 'email', 'to': to, 'mailbox': user, 'threaded': bool(in_reply_to)}
