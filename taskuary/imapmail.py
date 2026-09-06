"""Any mailbox as an inbound channel: IMAP in, SMTP out - the protocols every provider speaks.

Outlook/Microsoft 365 has its own connector (Graph does threading and attachments better
there), but the rest of the world is Gmail, a domain.com mailbox, Yahoo, an ISP - and they
all take IMAP with a password or app password. Two catalog cards (`gmail` pre-filled,
`imap` blank) share this one implementation; both land messages as channel 'email', through
the same triage, with the same attachment pipeline, and replies go back over SMTP in-thread
(In-Reply-To/References), from the same address the mail arrived at.

Stdlib only (imaplib, smtplib, email) - nothing new frozen into the exe.
"""
import base64, email, email.utils, hashlib, imaplib, json, re, smtplib, socket, ssl
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.mime.text import MIMEText
from loguru import logger

BATCH = 25                  # messages per batch: the watermark is saved after each, the poll goes on until the gap is drained
TRANSPORT = (imaplib.IMAP4.abort, OSError)   # the CONNECTION went, not one message: stop, keep the watermark, retry next poll
HOSTS = {'gmail': ('imap.gmail.com', 'smtp.gmail.com')}


class IMAPCommandError(RuntimeError):
    """The server did not complete a mailbox command; treating that as empty loses mail."""


class IMAPPartialFailure(RuntimeError):
    """Some UIDs landed and others remain durable retry holes."""
    def __init__(self, failures, ingested=0):
        self.failures = tuple(str(x) for x in failures)
        self.ingested = int(ingested)
        super().__init__('; '.join(self.failures))


class _UIDFetchFailure(RuntimeError):
    pass


def _cfg(c): return json.loads(c.get('ConfigJson') or '{}')


# ── WHOSE CERTIFICATE IS THAT ───────────────────────────────────────────────────────────
# Shared hosting is the common case this exists for: you connect to smtp.yourdomain.com and the
# server presents a certificate issued for the HOST's own name (mail.provider.net). The traffic is
# encrypted and the server is the right one - the name on the certificate just is not yours.
# Outlook shows a dialog, you dismiss it, and it works forever after; `tls_accept` on the mailbox
# card is how you say the same thing here, and it is deliberately not a global switch.
#
#   unset       every certificate is checked, name included. Where every mailbox should start.
#   <sha256>    accept exactly THIS certificate, whatever name it carries. The name check is off
#               and the pin replaces it: swap the certificate and sending stops, which is the
#               part "just turn verification off" throws away.
#   any         no checking at all - for a self-signed server, when there is nothing to pin to.
#
# The fingerprint to paste is in the error you get when it refuses, so accepting one is: read the
# message, copy the line it gives you. There is no dialog because there is nobody at the screen
# when a scheduled reply goes out at 6am.
TLS_HELP = ('the mailbox card can accept it: put the fingerprint above in tls_accept (Connections '
            "→ the mailbox → TLS certificate), or 'any' to stop checking certificates for this "
            'mailbox altogether')


def ssl_ctx(cfg: dict):
    """Strict, unless this mailbox says otherwise. A pin does its own checking after the
    handshake (verify_ok), so the context stops at 'encrypt it'."""
    ctx = ssl.create_default_context()
    if str(cfg.get('tls_accept') or '').strip():
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fingerprint(sock) -> str:
    return hashlib.sha256(sock.getpeercert(True) or b'').hexdigest()


def verify_pin(sock, cfg: dict, host: str):
    """The half of the check the context skipped. Nothing to do when tls_accept is unset (the
    context already verified) or 'any' (the owner asked for no checking)."""
    want = str(cfg.get('tls_accept') or '').strip().lower()
    if not want or want == 'any': return
    got = fingerprint(sock)
    if got != want.replace(':', ''):
        raise RuntimeError(f'{host} presented a different certificate than the one this mailbox '
                           f'accepted.\n  now:      sha256:{got}\n  accepted: sha256:{want}\n'
                           'If the mail host renewed its certificate this is expected - put the new '
                           'fingerprint in tls_accept. If it did not, something is between you and '
                           'the mail server: do not accept it.')


def peer_cert(host: str, port: int, starttls: bool) -> tuple:
    """(names the certificate IS valid for, its sha256) - for the error text, so the owner can see
    whose certificate it is before deciding to accept it. Read on a second connection that verifies
    the chain but not the name; a self-signed server falls through to the fingerprint alone."""
    def read(ctx):
        if starttls:
            with smtplib.SMTP(host, port, timeout=15) as S:
                S.starttls(context=ctx)
                return (S.sock.getpeercert() or {}), fingerprint(S.sock)
        with socket.create_connection((host, port), timeout=15) as s:
            with ctx.wrap_socket(s, server_hostname=host) as w:
                return (w.getpeercert() or {}), fingerprint(w)
    for verify in (True, False):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        if not verify: ctx.verify_mode = ssl.CERT_NONE
        try: cert, fp = read(ctx)
        except Exception: continue
        names = [v for k, v in (cert.get('subjectAltName') or ()) if k == 'DNS']
        if not names:
            names = [v for pair in (cert.get('subject') or ()) for k, v in pair if k == 'commonName']
        return names, fp
    return [], ''


def tls_error(e: Exception, host: str, port: int, starttls: bool) -> RuntimeError:
    """Python says 'certificate is not valid for smtp.yours.com' and stops. Say whose certificate
    it actually is and what to do about it - that is the whole difference between this being a
    dead end and being one setting."""
    names, fp = peer_cert(host, port, starttls)
    whose = f" It is valid for {', '.join(names[:6])}." if names else ''
    pin = f'\n  sha256:{fp}\n' if fp else '\n'
    return RuntimeError(f'{host}:{port} refused the TLS check: {e}.{whose} The certificate it '
                        f'presents is:{pin}{TLS_HELP}')


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
    # timeout: a half-open socket after a sleep or a Wi-Fi change hung the poll thread in recv
    # forever, and every later poll skipped because the lock was held (audit 2026-09-02)
    try: M = imaplib.IMAP4_SSL(imap_h, port, timeout=30, ssl_context=ssl_ctx(cfg))
    except ssl.SSLCertVerificationError as e:
        raise tls_error(e, imap_h, port, False) from e
    except OSError as e:
        if getattr(e, 'winerror', None) == 10013 or 'forbidden by its access permissions' in str(e):
            raise RuntimeError(f'this PC blocked the connection to {imap_h}:{port} - a firewall or security agent stops '
                               'Taskuary from reaching the mail server; ask IT to allow it (or allow port 993)') from e
        raise
    verify_pin(M.sock, cfg, imap_h)
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
        elif ctype == 'text/plain' and not text: text = _decode(payload, part)
        elif ctype == 'text/html' and not html: html = _decode(payload, part)
    return (text or _clean(html) or '').strip(), atts


def _decode(payload: bytes, part) -> str:
    """The declared charset when Python has a codec for it. 'replace' covers bad BYTES, not a codec
    name Python does not know (iso-8859-8-i, x-unknown): that raised LookupError, and one such
    mail wedged the whole mailbox (audit 2026-09-02). latin-1 at the end never fails."""
    try: return payload.decode(part.get_content_charset() or 'utf-8', 'replace')
    except LookupError: pass
    try: return payload.decode('utf-8')            # strict, so real latin-1 bytes fall through to latin-1
    except UnicodeDecodeError: return payload.decode('latin-1')


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


def sent_folder(M, strict=False) -> str:
    """The mailbox's Sent folder, as this server spells it. '' when it genuinely has none.

    The history sampler is deliberately best-effort.  Polling passes ``strict=True`` because a
    failed LIST is not evidence that Sent is empty; calling it empty would advance the connector
    as though the owner's replies had been read.
    """
    # Small protocol fakes used by the established inbound-only tests intentionally expose no
    # LIST operation at all. Real imaplib connections always do; absence here means that bounded
    # fake has no Sent capability, while an implemented LIST that fails remains a poll failure.
    if not hasattr(M, 'list'): return ''
    try: typ, data = M.list()
    except Exception:
        if strict: raise
        return ''
    if typ != 'OK':
        if strict: raise IMAPCommandError(f'LIST folders returned {typ}')
        return ''
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


def _validity(M):
    """The selected mailbox's UIDVALIDITY, or None when the server (or a fake) does not say."""
    try:
        _typ, data = M.response('UIDVALIDITY')
        return int(data[0]) if data and data[0] else None
    except Exception: return None


def _uids(M, last_uid: int, days: int) -> list:
    """Which UIDs to read, OLDEST first. With a cursor: everything above it - the whole gap,
    whatever the date. A window sized from the startup catch-up (3 days) excluded the mail of a
    two-week absence even though its UIDs were above the cursor (PW-008). Without a cursor, the
    first import, the date window stands: years of history never import by accident."""
    if last_uid > 0: typ, data = M.uid('search', None, f'(UID {last_uid + 1}:*)')
    else:
        since = (datetime.now() - timedelta(days=max(1, days))).strftime('%d-%b-%Y')
        typ, data = M.uid('search', None, f'(SINCE {since})')
    if typ != 'OK': raise IMAPCommandError(f'UID SEARCH returned {typ}')
    # RFC 3501: `n:*` never comes back empty - it returns the highest UID even below n, hence the filter
    return sorted(u for u in (int(x) for x in (data[0] or b'').split()) if u > last_uid)


def _rewound(user: str, box: str, saved, seen) -> bool:
    """A changed UIDVALIDITY renumbered the mailbox: the saved cursor points at nothing. Say so, import afresh."""
    if seen is None or saved in (None, ''): return False
    try: changed = int(saved) != seen
    except (TypeError, ValueError): changed = True
    if changed: logger.warning(f'imap {user} {box}: UIDVALIDITY changed {saved} -> {seen}; the saved cursor means nothing now, importing afresh')
    return changed


def _fetch_message(M, uid: int):
    """Fetch and decode one message, distinguishing a retryable UID hole from local persistence."""
    typ, parts = M.uid('fetch', str(uid), '(RFC822)')
    if typ != 'OK' or not parts or parts[0] is None:
        raise _UIDFetchFailure(f'uid {uid} FETCH returned {typ}')
    try:
        part = parts[0]
        if not isinstance(part, (tuple, list)) or len(part) < 2 or not isinstance(part[1], (bytes, bytearray)):
            raise ValueError('missing RFC822 bytes')
        msg = email.message_from_bytes(bytes(part[1]))
        body, atts = _body_and_attachments(msg)
        return msg, body, atts
    except Exception as e:
        raise _UIDFetchFailure(f'uid {uid} could not be decoded: {e}') from e


def _drain(uids: list, read, progress, *, cursor=0, holes=()) -> tuple:
    """Drain new UIDs and older retry holes without letting either hide the other.

    FETCH/decoding failures become durable holes and the later UIDs still progress. Transport,
    ingest and checkpoint failures abort: those failures must never be mistaken for poison mail.
    ``progress`` receives the high-water cursor and the full pending-hole set atomically.
    """
    pending = {int(u) for u in holes if int(u) > 0}
    candidates = sorted(pending | {int(u) for u in uids if int(u) > 0})
    n, done, failures, dirty = 0, int(cursor or 0), [], False
    for i in range(0, len(candidates), BATCH):
        for uid in candidates[i:i + BATCH]:
            try:
                n += read(uid)
            except _UIDFetchFailure as e:
                pending.add(uid)
                failures.append(str(e))
                logger.warning(f'imap {e}; retained for retry')
            except Exception:
                if dirty: progress(done, pending)
                raise
            else:
                pending.discard(uid)
            done = max(done, uid)
            dirty = True
        if dirty:
            progress(done, pending)
            dirty = False
    return n, done, pending, failures


_POLL_IDENTITY_FIELDS = ('address', 'imap_host', 'imap_port')


def _scope(host: str, port: int, user: str, box: str) -> str:
    """Stable opaque mailbox/folder identity; UIDVALIDITY is the epoch within this scope."""
    raw = '\0'.join((str(host or '').strip().casefold(), str(port),
                     str(user or '').strip().casefold(), str(box or '')))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]


def _keys(sent=False) -> dict:
    stem = 'imap_sent' if sent else 'imap'
    return {'uid': f'{stem}_uid', 'validity': f'{stem}_uidvalidity',
            'scope': f'{stem}_uid_scope', 'mode': f'{stem}_uid_identity',
            'holes': f'{stem}_retry_uids'}


def _number(value):
    if value in (None, ''): return None
    try: return int(value)
    except (TypeError, ValueError): raise RuntimeError(f'invalid saved IMAP UID value {value!r}')


def _hole_state(raw, *, scope, validity, mode, allow_validity_rebind=False) -> set:
    if raw in (None, '', {}): return set()
    if not isinstance(raw, dict) or not isinstance(raw.get('uids'), list):
        raise RuntimeError('invalid saved IMAP retry UID state')
    same_validity = raw.get('uidvalidity') == validity
    if allow_validity_rebind and raw.get('uidvalidity') is None:
        same_validity = True
    if raw.get('scope') != scope or not same_validity or raw.get('identity') != mode:
        return set()
    try:
        values = {int(u) for u in raw['uids'] if int(u) > 0}
    except (TypeError, ValueError):
        raise RuntimeError('invalid saved IMAP retry UID')
    return values


def _hole_json(scope, validity, mode, holes) -> dict:
    return {'scope': scope, 'uidvalidity': validity, 'identity': mode,
            'uids': sorted(int(u) for u in holes)}


def _external_id(sent: bool, user: str, uid: int, *, scope: str, validity, mode: str) -> str:
    prefix = 'imap-sent' if sent else 'imap'
    # An upgraded, unchanged mailbox keeps the exact old identity. This is deliberately
    # conservative: rows may have landed just before an old checkpoint write failed. Only a
    # confirmed UID epoch/scope change switches away from legacy IDs.
    if mode == 'legacy':
        return f'{prefix}:{user}:{uid}'
    # UIDVALIDITY may appear after a server previously omitted it. Learning the number does not
    # prove a new epoch, so keep the already-persisted unknown namespace until a later confirmed
    # validity or scope change resets the folder.
    epoch = 'unknown' if mode == 'scoped-unknown-v1' else validity
    if epoch is None: epoch = 'unknown'
    return f'{prefix}:{scope}:v{epoch}:{uid}'


def _unmarked_folder(cfg: dict, sent: bool) -> bool:
    return not any(name in cfg for name in _keys(sent).values())


def _legacy_evidence(store, connector_id: int, user: str, sent: bool, uids) -> bool:
    """Whether exact replay candidates belong to this connector's pre-checkpoint mailbox.

    Legacy message rows name the mailbox but not ConnectorId. Adopt their namespace only when
    source ownership makes that mailbox unambiguous; two connectors using the same address must
    not suppress one another's fresh mail.
    """
    matching = [s for s in store.list_sources(active_only=False)
                if s.get('Channel') == 'email'
                and str(s.get('Address') or '').strip().casefold() == user.casefold()]
    if not matching or any(s.get('ConnectorId') != connector_id for s in matching):
        return False
    prefix = 'imap-sent' if sent else 'imap'
    for uid in uids:
        row = store.message_by_external(f'{prefix}:{user}:{uid}')
        if not row or row.get('Channel') != 'email': continue
        if str(row.get('SourceName') or '').strip().casefold() != user.casefold(): continue
        return True
    return False


def _prepare_folder(checkpoint, cfg: dict, *, sent: bool, scope: str, seen_validity,
                    legacy_evidence=False):
    """Adopt or reset a folder checkpoint and persist the basis before any message lands."""
    k = _keys(sent)
    cursor = _number(cfg.get(k['uid'])) or 0
    saved_validity = _number(cfg.get(k['validity']))
    stored_scope = cfg.get(k['scope'])
    mode = cfg.get(k['mode'])
    if mode not in (None, 'legacy', 'scoped-v1', 'scoped-unknown-v1'):
        raise RuntimeError(f'invalid saved IMAP identity mode {mode!r}')

    # An established checkpoint without a marker is an upgraded legacy epoch. Keeping its exact
    # old identity avoids re-importing a row written before an old cursor save. A genuinely fresh
    # folder starts with scoped IDs, so its first future UIDVALIDITY reset is safe too.
    mode = mode or ('legacy' if legacy_evidence or k['uid'] in cfg or k['validity'] in cfg
                    else 'scoped-v1' if seen_validity is not None else 'scoped-unknown-v1')
    scope_changed = stored_scope not in (None, scope)
    validity_changed = (seen_validity is not None and saved_validity is not None
                        and int(seen_validity) != saved_validity)
    reset = scope_changed or validity_changed
    if reset:
        logger.warning(f'imap folder identity changed; resetting cursor for scope {scope}')
        cursor, mode, holes = (0, 'scoped-v1' if seen_validity is not None
                               else 'scoped-unknown-v1', set())
        saved_validity = seen_validity
    else:
        effective_validity = seen_validity if seen_validity is not None else saved_validity
        holes = _hole_state(cfg.get(k['holes']), scope=scope,
                            validity=effective_validity, mode=mode,
                            allow_validity_rebind=(saved_validity is None and seen_validity is not None))
        saved_validity = effective_validity

    values = {k['uid']: cursor, k['scope']: scope, k['mode']: mode,
              k['holes']: _hole_json(scope, saved_validity, mode, holes)}
    if saved_validity is not None: values[k['validity']] = saved_validity
    remove = (k['validity'],) if reset and saved_validity is None else ()
    if any(cfg.get(name) != value for name, value in values.items()) or any(name in cfg for name in remove):
        checkpoint(values, remove)
    return {'keys': k, 'cursor': cursor, 'validity': saved_validity,
            'scope': scope, 'mode': mode, 'holes': holes}


def poll_sent(store, M, user: str, last_uid: int, days: int, state: dict = None) -> tuple:
    """The replies the owner wrote in Outlook, Gmail's web UI, their phone - anywhere but here.

    Graph's mailbox has read them since the beginning (channels.ingest_outbound_mail); an IMAP
    one never did, so on those installs a mail answered in the mailbox stayed "on your list"
    with nothing on the thread to say otherwise. Same ride as Graph's: a `context` row on the
    thread, never work, never a timeline row of its own. Its own watermark - the Sent folder is
    a separate UID space from INBOX, and sharing one would skip whole days of either.

    `state` (optional) carries the folder checkpoint adapter, retry holes and observed validity;
    each bounded batch saves its high-water UID and holes together, so a poll that dies keeps
    both its progress and every UID still owed.
    Returns (ingested, new watermark)."""
    from .channels import ingest_own_message
    state = state if state is not None else {}
    box = sent_folder(M, strict=bool(state.get('strict')))
    if not box: return 0, last_uid
    typ, _d = M.select(_quoted(box), readonly=True)
    if typ != 'OK': raise IMAPCommandError(f'SELECT {box} returned {typ}')
    state['box'] = box
    state['validity'] = _validity(M)
    selected_uids = _uids(M, last_uid, days)
    if state.get('prepare'):
        folder = state['prepare'](box, state['validity'], selected_uids)
        if folder['cursor'] != last_uid:
            selected_uids = _uids(M, folder['cursor'], days)
        last_uid = folder['cursor']
        state.update(folder)
    elif _rewound(user, box, state.get('saved_validity'), state['validity']):
        last_uid = 0
        selected_uids = _uids(M, last_uid, days)
    def read(uid) -> int:
        msg, body, _atts = _fetch_message(M, uid)
        try: when = email.utils.parsedate_to_datetime(msg.get('Date')).astimezone().strftime('%Y-%m-%d %H:%M:%S')
        except Exception: when = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return ingest_own_message(store, {
            'external_id': _external_id(True, user, uid, scope=state.get('scope', ''),
                                        validity=state.get('validity'), mode=state.get('mode', 'legacy')),
            'channel': 'email', 'source_name': user,
            'subject': _dec(msg.get('Subject')), 'body': body[:20000], 'from_email': user, 'sent_at': when,
            # the SAME thread key the inbound side derives, or the reply lands on nothing
            'conversation_id': (msg.get('References') or msg.get('Message-ID') or '').split()[0][:200] or None},
            'your reply on this thread - kept for context')
    def progress(uid, holes):
        state['uid'], state['holes'] = uid, set(holes)
        if state.get('save'): state['save'](uid, holes)
    n, done, holes, failures = _drain(selected_uids, read, progress,
                                      cursor=last_uid, holes=state.get('holes', ()))
    state['uid'], state['holes'], state['failures'] = done, holes, failures
    return n, (done if done is not None else last_uid)


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
    connector never re-ingests. With a cursor the poll asks for everything above it and drains
    it oldest-first in batches, saving the watermark plus retry holes as each batch lands
    (PW-007/PW-008); the SINCE window applies to the first import only. The 25-highest-then-jump
    of before skipped the lower pending UIDs for good, and the date window hid a long absence."""
    from .channels import images_for_triage, save_attachments, wants_read
    from .ingest import ingest_message
    M, user = _login(c)
    n = 0
    imap_h, _smtp_h, cfg = _hosts(c)
    try: imap_port = int(cfg.get('imap_port') or 993)
    except (TypeError, ValueError): raise RuntimeError('invalid IMAP port')
    poll_keys = set(_keys(False).values()) | set(_keys(True).values())
    expected_config = {name: cfg.get(name) for name in (*_POLL_IDENTITY_FIELDS, *sorted(poll_keys))}
    expected_fields = {name: c.get(name) for name in ('Type', 'Active', 'Secret')}

    def checkpoint(values, remove=()):
        values = dict(values or {})
        ok = store.patch_connector_poll_state(
            c['ConnectorId'], config_set=values, config_remove=remove,
            expect_fields=expected_fields, expect_config=expected_config)
        if not ok:
            raise RuntimeError('mailbox changed while IMAP was polling; its stale checkpoint was not saved')
        cfg.update(values)
        for name, value in values.items():
            expected_config[name] = value
        for name in remove:
            cfg.pop(name, None)
            expected_config[name] = None

    def prepare(sent, box, validity, selected_uids):
        legacy = (_unmarked_folder(cfg, sent)
                  and _legacy_evidence(store, c['ConnectorId'], user, sent, selected_uids))
        return _prepare_folder(checkpoint, cfg, sent=sent,
                               scope=_scope(imap_h, imap_port, user, box),
                               seen_validity=validity, legacy_evidence=legacy)
    try:
        # readonly is what has always kept the funnel invisible in the mailbox: an ordinary
        # RFC822 fetch sets \Seen by itself. Only the mark-read switch opens the box for
        # writing, and then the flag is set explicitly, per message, after it is safely in.
        read_it = wants_read(store)
        typ, _data = M.select('INBOX', readonly=not read_it)
        if typ != 'OK': raise IMAPCommandError(f'SELECT INBOX returned {typ}')
        initial_cursor = _number(cfg.get('imap_uid')) or 0
        selected_uids = _uids(M, initial_cursor, max(backfill_days, 1))
        folder = prepare(False, 'INBOX', _validity(M), selected_uids)
        if folder['cursor'] != initial_cursor:
            selected_uids = _uids(M, folder['cursor'], max(backfill_days, 1))
        last_uid = folder['cursor']
        protected_inbox = set(selected_uids) | set(folder['holes'])
        inbox_frontier = max({last_uid, *protected_inbox})
        def chain_folder_identity(sent, box, validity, _chain_uids):
            if not sent:
                # The active drain closure owns this exact epoch. Re-preparing it after a
                # mid-drain UIDVALIDITY change would leave that closure stale.
                if (validity is not None and folder['validity'] is not None
                        and int(validity) != int(folder['validity'])):
                    raise RuntimeError('INBOX UIDVALIDITY changed during chain retrieval')
                return folder
            # Prepare Sent from the same complete pending set poll_sent will use. Restricting
            # legacy attribution to this chain's matching UIDs could switch a legacy folder to
            # scoped IDs merely because its existing evidence belongs to another conversation.
            sent_uids = _uids(M, _number(cfg.get('imap_sent_uid')) or 0,
                              max(backfill_days, 1))
            return prepare(True, box, validity, sent_uids)
        def read(uid) -> int:
            msg, body, atts = _fetch_message(M, uid)
            try:
                frm_name, frm_addr = email.utils.parseaddr(_dec(msg.get('From')))
                if frm_addr.lower() == user.lower(): return 0       # my own mail is not inbound work
                try: sent_at = email.utils.parsedate_to_datetime(msg.get('Date')).astimezone().strftime('%Y-%m-%d %H:%M:%S')
                except Exception: sent_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ext_id = _external_id(False, user, uid, scope=folder['scope'],
                                      validity=folder['validity'], mode=folder['mode'])
                incoming = {
                    'external_id': ext_id, 'channel': 'email',
                    'subject': _dec(msg.get('Subject')), 'body': body[:20000],
                    'from_name': frm_name or frm_addr, 'from_email': frm_addr,
                    'to': _hdr_addrs(msg, 'To'), 'cc': _hdr_addrs(msg, 'Cc'),
                    # References threads replies the way Graph's conversationId does
                    'conversation_id': (msg.get('References') or msg.get('Message-ID') or '').split()[0][:200] or None,
                    'sent_at': sent_at, 'source_name': user}
            except Exception as e:
                raise _UIDFetchFailure(f'uid {uid} headers could not be decoded: {e}') from e
            conv = incoming['conversation_id']
            from . import chains
            fresh_thread = bool(conv) and chains.needs_history(store, conv)
            incoming['images'] = images_for_triage(store, atts)
            out = ingest_message(store, file_only=file_only, msg=incoming, llm=llm)
            existing = store.message_by_external(ext_id) if not out.get('message_id') else None
            message_id = out.get('message_id') or (existing or {}).get('MessageId')
            if atts and message_id:
                save_attachments(store, message_id, atts, ext_id)
            if read_it:
                try: M.uid('store', str(uid), '+FLAGS', r'(\Seen)')
                except Exception as e: logger.warning(f'marking {user} uid {uid} seen failed: {e}')
            if fresh_thread and out['status'] != 'duplicate':
                # the thread's history, completed once from INBOX and Sent (chains.py, PW-011); the poll's
                # own mailbox selection is restored afterwards
                chains.refresh_imap(
                    store, M, user, conv, restore='INBOX', readonly=not read_it, before=sent_at,
                    folder_identity=chain_folder_identity,
                    protected={'INBOX': protected_inbox},
                    protected_after={'INBOX': inbox_frontier})
            return int(out['status'] != 'duplicate')
        def progress(uid, holes):
            checkpoint({folder['keys']['uid']: uid,
                        folder['keys']['holes']: _hole_json(folder['scope'], folder['validity'],
                                                            folder['mode'], holes)})
        got, _done, holes, failures = _drain(
            selected_uids, read, progress,
            cursor=last_uid, holes=folder['holes'])
        n += got
        # ...and the other half of the conversation: what the owner sent from the mailbox itself
        state = {'strict': True,
                 'prepare': lambda box, validity, uids: prepare(True, box, validity, uids)}
        def save_sent(uid, sent_holes):
            checkpoint({state['keys']['uid']: uid,
                        state['keys']['holes']: _hole_json(state['scope'], state['validity'],
                                                          state['mode'], sent_holes)})
        state['save'] = save_sent
        got, _sent_uid = poll_sent(store, M, user, _number(cfg.get('imap_sent_uid')) or 0,
                                   max(backfill_days, 1), state)
        n += got
        failures += [f'{state.get("box", "Sent")}: {e}' for e in state.get('failures', [])]
        if failures:
            raise IMAPPartialFailure(failures, n)
    finally:
        try: M.logout()
        except Exception: pass
    return n


def send_smtp(store, c, to: list, subject: str, body: str, in_reply_to: str = None, cc: list = None) -> dict:
    """The reply, over the provider's own SMTP, threaded with In-Reply-To/References. `cc` is the
    colleague the owner looped in: on the header so everyone sees it, and in the envelope so the
    server actually delivers to them (the header alone sends nothing - it is only text)."""
    imap_h, smtp_h, cfg = _hosts(c)
    user = (cfg.get('address') or '').strip()
    cc = [a for a in (cc or []) if a]
    m = MIMEText(body, 'plain', 'utf-8')
    m['From'], m['To'], m['Subject'] = user, ', '.join(to), subject or '(no subject)'
    if cc: m['Cc'] = ', '.join(cc)
    if in_reply_to:
        m['In-Reply-To'] = in_reply_to
        m['References'] = in_reply_to
    port = int(cfg.get('smtp_port') or 587)
    with smtplib.SMTP(smtp_h, port, timeout=30) as S:
        try: S.starttls(context=ssl_ctx(cfg))
        except ssl.SSLCertVerificationError as e: raise tls_error(e, smtp_h, port, True) from e
        verify_pin(S.sock, cfg, smtp_h)
        S.login(user, c['Secret'])
        S.sendmail(user, list(to) + cc, m.as_string())
    return {'channel': 'email', 'to': to, 'cc': cc, 'mailbox': user, 'threaded': bool(in_reply_to)}
