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
    M = imaplib.IMAP4_SSL(imap_h, int(cfg.get('imap_port') or 993))
    M.login(user, c['Secret'])
    return M, user


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


def poll_imap(store, c, sources: list, llm=None, file_only=False, backfill_days: int = 0) -> int:
    """UIDs are IMAP's own cursor: strictly increasing per mailbox, so the watermark on the
    connector never re-ingests - and a backfill just lowers the SINCE date, with dedupe
    catching anything already seen."""
    from .channels import images_for_triage, save_attachments
    from .ingest import ingest_message
    M, user = _login(c)
    n = 0
    try:
        M.select('INBOX', readonly=True)
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
                # References threads replies the way Graph's conversationId does
                'conversation_id': (msg.get('References') or msg.get('Message-ID') or '').split()[0][:200] or None,
                'sent_at': sent, 'source_name': user,
                'images': images_for_triage(store, atts)}, llm=llm)
            n += out['status'] != 'duplicate'
            if atts and out.get('message_id') and out['status'] != 'duplicate':
                try: save_attachments(store, out['message_id'], atts, f'imap:{user}:{uid}')
                except Exception as e: logger.warning(f'imap attachments failed: {e}')
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
