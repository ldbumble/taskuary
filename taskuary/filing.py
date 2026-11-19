"""What Taskuary does to a message at its source - ONE choice on each card (the owner, 2026-11-16: the app-wide "Handled mail,
at the source" and the mail card's "mark read when you read it here" became one per-card choice). A mail card (Outlook,
Gmail, IMAP) can leave its mailbox as it is, mark a mail read when the owner reads it HERE, mark it read once Taskuary takes it
in, or that AND move it out of the Inbox into Archive once it is HANDLED here - its task closed (never an FYI or a report put
down without a task: unhandled mail is never moved). A chat card the app-wide setting reached (Teams, Slack, WhatsApp) keeps
what it could do there: leave, or mark read what Taskuary takes in. `read_mode` reads the knob; nothing else does.

Every act is best-effort and never costs the poll. Only mail read or handled AFTER the choice was made is acted on - choosing
it must not empty a mailbox of a year of work in one sweep (_since)."""
import contextlib, json, logging, threading, time
from datetime import datetime

logger = logging.getLogger(__name__)
MODE_KEY, OLD_KEY, OLD_SINCE = 'mark_read', 'mark_read_enabled', 'mail_filing_since'
MAIL_CARDS, CHAT_CARDS = ('outlook', 'gmail', 'imap'), ('teams', 'slack', 'whatsapp')
# leave · mark read when read here · mark read when taken in · that + file handled mail in Archive
MAIL_MODES, CHAT_MODES = ('0', 'read', 'taken', 'archive'), ('0', 'taken')
ARCHIVE_NAMES = ('Archive', 'Archives', 'INBOX.Archive', 'INBOX/Archive')


def modes_of(kind) -> tuple: return MAIL_MODES if kind in MAIL_CARDS else CHAT_MODES if kind in CHAT_CARDS else ('0',)
def read_mode(c) -> str:
    """THE knob: what this card does to a message at its source. Anything unknown - or a card it does not apply to - leaves it."""
    try: v = str(json.loads((c or {}).get('ConfigJson') or '{}').get(MODE_KEY) or '0')
    except (ValueError, AttributeError): return '0'
    return v if v in modes_of((c or {}).get('Type')) else '0'
def takes_read(c) -> bool: return read_mode(c) in ('taken', 'archive')


def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def handled(store, since: str, addresses, limit: int = 200) -> list:
    """Inbound mail of these mailboxes the hub is done with since `since`, not filed yet: its task closed. Only mailbox mail -
    Graph or IMAP ids - is anything this module can move."""
    # Closed tasks only (the owner, 2026-10-25: "Archive ... covers closed tasks only"): an FYI or a report put down here has
    # no task, and moving it out of the Inbox filed every read FYI in the mailbox - the press only said "read" (2026-10-26).
    return store._rows(
        f"""SELECT m.MessageId, m.ExternalId, m.SourceName FROM message m JOIN task t ON t.TaskId=m.TaskId
           WHERE m.Channel='email' AND COALESCE(m.Direction,'in')='in' AND (m.ExternalId LIKE 'graph:%' OR m.ExternalId LIKE 'imap:%')
             AND LOWER(m.SourceName) IN ({','.join('?' * len(addresses))})
             AND NOT EXISTS (SELECT 1 FROM mail_filed f WHERE f.MessageId=m.MessageId)
             AND t.Status IN ('done','dropped') AND t.ClosedAt>=?
           ORDER BY m.MessageId LIMIT ?""", (*[a.lower() for a in addresses], since, limit)) if addresses else []


def _filed(store, mid, result): store._exec('INSERT OR REPLACE INTO mail_filed (MessageId, FiledAt, Result) VALUES (?,?,?)', (mid, _now(), result[:200]))


def graph_archive(tok: str, upn: str, graph_id: str):
    """Graph's well-known 'archive' folder is the one Outlook's own Archive button moves to."""
    import requests
    from .channels import GRAPH
    requests.post(f'{GRAPH}/users/{upn}/messages/{graph_id}/move', timeout=20, headers={'Authorization': f'Bearer {tok}'},
                  json={'destinationId': 'archive'}).raise_for_status()


def archive_folder(M, gmail: bool = False) -> str:
    """The server's Archive, as it names it: the special-use \\Archive flag, else a folder called Archive. For Gmail, All
    Mail IS archiving - moving out of INBOX takes the Inbox label off and nothing else. '' when the box has none."""
    from .imapmail import _list_line
    try: typ, data = M.list()
    except Exception: return ''
    if typ != 'OK': return ''
    rows = [_list_line(r) for r in data or []]
    for flags, name in rows:
        if name and ('\\Archive' in flags or (gmail and '\\All' in flags)): return name
    lower = {n.lower(): n for _f, n in rows if n}
    return next((lower[w.lower()] for w in ARCHIVE_NAMES if w.lower() in lower), '')


def _uid_of(ext_id: str, validity):
    """The UID inside an imap: id, or None when it names a different UIDVALIDITY epoch (that UID is someone else now)."""
    parts = ext_id.split(':')
    if len(parts) == 4 and parts[2].startswith('v') and parts[2][1:] not in ('unknown', str(validity)): return None
    try: return int(parts[-1])
    except ValueError: return None


@contextlib.contextmanager
def _inbox(c):
    """The card's INBOX, signed in and opened for writing - the one folder Taskuary reads mail from."""
    from . import imapmail
    M, _user = imapmail._login(c)
    try:
        typ, _d = M.select('INBOX', readonly=False)
        if typ != 'OK': raise RuntimeError(f'SELECT INBOX returned {typ}')
        yield M
    finally:
        try: M.logout()
        except Exception: pass


def _file_imap(store, c, rows) -> int:
    from . import imapmail
    with _inbox(c) as M:
        box = archive_folder(M, gmail=c['Type'] == 'gmail' or 'gmail' in (imapmail._hosts(c)[0] or ''))
        if not box:
            for r in rows: _filed(store, r['MessageId'], 'skipped: this mailbox has no Archive folder')
            return 0
        validity, n = imapmail._validity(M), 0
        for r in rows:
            uid = _uid_of(r['ExternalId'], validity)
            if uid is None: _filed(store, r['MessageId'], 'skipped: the mailbox was renumbered'); continue
            try:
                typ, _d = M.uid('MOVE', str(uid), imapmail._quoted(box))
                if typ != 'OK': raise RuntimeError(f'MOVE returned {typ}')
                _filed(store, r['MessageId'], f'archived: {box}'); n += 1
            except Exception as e:
                logger.warning(f'filing {r["ExternalId"]} failed: {e}'); _filed(store, r['MessageId'], f'failed: {e}')
        return n


def _since(store, c, mode: str):
    """When this card's current choice began, or None when it begins now: a choice that just began starts its clock and acts on
    nothing before it, and changing the choice starts it again."""
    key, wants = f'mark_read_since:{c["ConnectorId"]}', mode in ('read', 'archive')
    m, _, at = (store.get_setting(key) or '').partition(' ')
    if m == mode and at: return at
    if wants or m: store.set_setting(key, f'{mode} {_now()}' if wants else '', 'filing')
    return None


def _cards(store, mode: str):
    """(card, since, its mailbox addresses) for every connected mail card whose choice is `mode` and whose clock has run."""
    srcs = None
    for c in store.list_connectors():
        if c['Type'] not in MAIL_CARDS: continue
        on = bool(c.get('Active')) and read_mode(c) == mode
        since = _since(store, c, read_mode(c) if c.get('Active') else '0')
        if not (on and since): continue
        if srcs is None: srcs = [s for s in store.list_sources() if s['Channel'] == 'email' and s.get('Active') and s.get('Address')]
        yield c, since, [s['Address'] for s in srcs if s.get('ConnectorId') == c['ConnectorId']]


def file_handled(store) -> int:
    """One sweep, after a poll: every mail handled since its card chose archive, moved to that mailbox's Archive."""
    n = 0
    for c, since, addrs in list(_cards(store, 'archive')):
        rows = handled(store, since, addrs)
        if not rows: continue
        full = store.get_connector(c['ConnectorId'], with_secret=True)
        try:
            if c['Type'] == 'outlook':
                from .channels import graph_creds, graph_token
                gcfg, gsec, _ = graph_creds(store, full)
                tok = graph_token(gcfg, gsec)
                for r in rows:
                    try: graph_archive(tok, r['SourceName'], r['ExternalId'][6:]); _filed(store, r['MessageId'], 'archived'); n += 1
                    except Exception as e: logger.warning(f'filing {r["ExternalId"]} failed: {e}'); _filed(store, r['MessageId'], f'failed: {e}')
            else: n += _file_imap(store, full, rows)
        except Exception as e:
            # the sign-in itself failed: nothing was moved and nothing is written down, so the next poll tries again
            logger.warning(f"filing handled mail on {c.get('Name') or c['Type']} failed: {e}")
    return n


# ── read here, read there ───────────────────────────────────────────────────────────────────────────────────────────────────
# "Read here" is the owner's read receipt - processing_read_receipt, the one record every way of reading writes (opening it,
# shown in the chat, Next, All read on an FYI batch, Done on its task: store.set_funnel_state) - so the write-back hangs off
# that table once, never off a view. Each mail is written back once (mail_read_back); a refusal is kept on the card's choice
# as one line with its fix, and everything else is tried again.
READ_PROBLEM = 'mark_read_problem'
OWNER_READS = ('explicit_done', 'surfaced', 'own_words')          # never legacy_preserved: a migration is not the owner reading
SCOPE_LINE = {True: 'Your Microsoft sign-in can read mail but not mark it read - sign in with Microsoft again on this card to allow it.',
              False: 'Microsoft refused to mark mail read - the company app needs Mail.ReadWrite, which its admin grants.'}
READ_EVERY = 15                                                    # seconds between sweeps on the quick clock


def read_here(store, since: str, addresses, limit: int = 200) -> list:
    """Inbound mail of these mailboxes the owner read here since `since`, not yet marked read there."""
    if not addresses: return []
    return store._rows(f"""SELECT m.MessageId, m.ExternalId, m.SourceName FROM message m
        WHERE m.Channel='email' AND COALESCE(m.Direction,'in')='in' AND (m.ExternalId LIKE 'graph:%' OR m.ExternalId LIKE 'imap:%')
          AND LOWER(m.SourceName) IN ({','.join('?' * len(addresses))})
          AND NOT EXISTS (SELECT 1 FROM mail_read_back b WHERE b.MessageId=m.MessageId)
          AND EXISTS (SELECT 1 FROM processing_read_receipt r WHERE r.EntityKind='message' AND r.LocalId=CAST(m.MessageId AS TEXT)
                      AND r.Origin IN ({','.join('?' * len(OWNER_READS))}) AND julianday(r.ReadAt)>=julianday(?))
        ORDER BY m.MessageId LIMIT ?""", (*[a.lower() for a in addresses], *OWNER_READS, since, limit))


def _read_back(store, mid, result): store._exec('INSERT OR REPLACE INTO mail_read_back (MessageId, At, Result) VALUES (?,?,?)', (mid, _now(), result[:200]))


def _problem(store, c, line: str) -> int:
    """The card's one line under its switch: set to what stopped the write-back, cleared once one goes through."""
    try: had = json.loads(c.get('ConfigJson') or '{}').get(READ_PROBLEM) or ''
    except ValueError: had = ''
    if had != line: store.merge_connector_config(c['ConnectorId'], {READ_PROBLEM: line or None})
    return 0


def _read_graph(store, c, rows) -> int:
    from . import msauth
    from .channels import graph_creds, graph_token, mark_mail_read
    from .say import _status
    cfg, sec, _ = graph_creds(store, c)
    user = cfg.get('auth') == 'user'
    if user and msauth.granted(cfg, 'Mail.ReadWrite') is False: return _problem(store, c, SCOPE_LINE[True])
    tok, n = graph_token(cfg, sec), 0
    for r in rows:
        try: mark_mail_read(tok, r['SourceName'], r['ExternalId'][6:])
        except Exception as e:
            code = _status(e)
            if code == 403: return _problem(store, c, SCOPE_LINE[user]) + n
            if code in (404, 410): _read_back(store, r['MessageId'], 'gone: no longer in the mailbox'); continue
            raise                                                  # anything else: the rest waits for the next sweep
        _read_back(store, r['MessageId'], 'read'); n += 1
    return n


def _read_imap(store, c, rows) -> int:
    from . import imapmail
    with _inbox(c) as M:
        validity, n = imapmail._validity(M), 0
        for r in rows:
            uid = _uid_of(r['ExternalId'], validity)
            if uid is None: _read_back(store, r['MessageId'], 'skipped: the mailbox was renumbered'); continue
            imapmail.mark_seen(M, uid)
            _read_back(store, r['MessageId'], 'read'); n += 1
        return n


def mark_read_back(store) -> int:
    """One sweep: every mail the owner read here, on a card whose choice is "when I read it here", marked read in its mailbox."""
    n = 0
    for c, since, addrs in list(_cards(store, 'read')):
        rows = read_here(store, since, addrs)
        if not rows: continue
        full = store.get_connector(c['ConnectorId'], with_secret=True)
        try: got = (_read_graph if c['Type'] == 'outlook' else _read_imap)(store, full, rows)
        except Exception as e:
            from .say import plain_failure
            logger.warning(f"marking read mail read on {c.get('Name') or c['Type']} failed: {e}")
            _problem(store, c, f"Could not mark mail read there just now - tried again shortly. {plain_failure(e, c['Type'] == 'outlook')[:200]}")
            continue
        if got: _problem(store, c, '')
        n += got
    return n


_SWEEP, _LAST = threading.Lock(), [0.0]


def read_back_soon(store):
    """The quick clock's tick: one sweep at a time, on its own thread, never more often than READ_EVERY - a slow mailbox
    holds neither the clock nor the press that read the mail."""
    from . import demo
    if demo.enabled() or time.monotonic() - _LAST[0] < READ_EVERY or not _SWEEP.acquire(blocking=False): return
    _LAST[0] = time.monotonic()
    def run():
        try: mark_read_back(store)
        except Exception as e: logger.warning(f'marking read mail read failed: {e}')
        finally: _SWEEP.release()
    threading.Thread(target=run, name='mark-read-back', daemon=True).start()


def migrate(store) -> int:
    """Once (2026-11-16): the app-wide "Handled mail, at the source" becomes each card's own choice, then goes. Every card it
    reached keeps what it did there; a mail card whose own "when you read it here" switch was on, with the app-wide one left
    alone, keeps that. Archive's clock and the switch's carry over, so neither acts on anything older than it did."""
    old = store.get_setting(OLD_KEY)
    if old is None: return 0
    was = {'1': 'taken', 'archive': 'archive'}.get(str(old), '0')
    since, n = store.get_setting(OLD_SINCE) or '', 0
    for c in store.list_connectors():
        if c['Type'] not in MAIL_CARDS + CHAT_CARDS: continue
        try: cfg = json.loads(c.get('ConfigJson') or '{}')
        except ValueError: cfg = {}
        mode = was if was in modes_of(c['Type']) else 'taken' if was != '0' else '0'
        if mode == '0' and cfg.get('mark_read_here'): mode = 'read'
        if mode == '0' and 'mark_read_here' not in cfg: continue
        store.merge_connector_config(c['ConnectorId'], {MODE_KEY: None if mode == '0' else mode, 'mark_read_here': None})
        key = f'mark_read_since:{c["ConnectorId"]}'
        at = since if mode == 'archive' else (store.get_setting(key) or '') if mode == 'read' else ''
        store.set_setting(key, f'{mode} {at}' if at else '', 'migration')
        n += mode != '0'
    store._exec('DELETE FROM setting WHERE Name IN (?,?)', (OLD_KEY, OLD_SINCE))
    return n
