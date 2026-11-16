"""Handled mail, filed where it came from. The mark-read switch grew a third answer (the owner, 2026-10-25: "a mark-read
setting already exists - extend that setting rather than adding something new"): leave the mailbox alone, mark read what
the funnel took (what '1' always did), or that AND move the mail out of the Inbox into Archive once it is HANDLED here -
its task closed (never an FYI or report put down without a task). Unhandled mail is never moved: the Inbox keeps exactly what is still owed.

Best-effort like every marker in channels.py: a refused consent or a server with no Archive is written down once per
message and never costs the poll. Only mail handled AFTER the choice was made is filed - choosing it must not empty a
mailbox of a year of closed work in one poll.

Its sibling, per mail card: mail the owner READ here marked read there (mark_read_back, below)."""
import contextlib, json, logging, threading, time
from datetime import datetime

logger = logging.getLogger(__name__)
MODES = ('0', '1', 'archive')                     # leave · mark read · mark read + file handled mail in Archive
SINCE = 'mail_filing_since'                       # when archive was first seen on: handled before it is left where it is
ARCHIVE_NAMES = ('Archive', 'Archives', 'INBOX.Archive', 'INBOX/Archive')


def mode(store) -> str:
    try: v = str(store.get_setting('mark_read_enabled') or '0')
    except Exception: return '0'
    return v if v in MODES else '0'


def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def handled(store, since: str, limit: int = 200) -> list:
    """Inbound mail the hub is done with since `since`, not filed yet: its task closed. Only mailbox mail - Graph or IMAP ids
    - is anything this module can move."""
    # Closed tasks only (the owner, 2026-10-25: "Archive ... covers closed tasks only"): an FYI or a report put down here has
    # no task, and moving it out of the Inbox filed every read FYI in the mailbox - the press only said "read" (2026-10-26).
    return store._rows(
        """SELECT m.MessageId, m.ExternalId, m.SourceName FROM message m JOIN task t ON t.TaskId=m.TaskId
           WHERE m.Channel='email' AND COALESCE(m.Direction,'in')='in' AND (m.ExternalId LIKE 'graph:%' OR m.ExternalId LIKE 'imap:%')
             AND NOT EXISTS (SELECT 1 FROM mail_filed f WHERE f.MessageId=m.MessageId)
             AND t.Status IN ('done','dropped') AND t.ClosedAt>=?
           ORDER BY m.MessageId LIMIT ?""", (since, limit))


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


def file_handled(store) -> int:
    """One sweep, after a poll: every handled mail since archive was chosen, moved to its mailbox's Archive."""
    if mode(store) != 'archive':
        if store.get_setting(SINCE): store.set_setting(SINCE, '', 'filing')   # off again: a later On starts from then
        return 0
    since = store.get_setting(SINCE)
    if not since: store.set_setting(SINCE, _now(), 'filing'); return 0
    rows = handled(store, since)
    if not rows: return 0
    from .channels import graph_creds, graph_token
    src = {(s.get('Address') or '').lower(): s.get('ConnectorId') for s in store.list_sources() if s['Channel'] == 'email'}
    by_card = {}
    for r in rows: by_card.setdefault(src.get((r['SourceName'] or '').lower()), []).append(r)
    n = 0
    for cid, mine in by_card.items():
        c = store.get_connector(cid, with_secret=True) if cid else None
        if not c or not c.get('Active'):
            for r in mine: _filed(store, r['MessageId'], 'skipped: the mailbox is no longer connected')
            continue
        try:
            if c['Type'] == 'outlook':
                gcfg, gsec, _ = graph_creds(store, c)
                tok = graph_token(gcfg, gsec)
                for r in mine:
                    try: graph_archive(tok, r['SourceName'], r['ExternalId'][6:]); _filed(store, r['MessageId'], 'archived'); n += 1
                    except Exception as e: logger.warning(f'filing {r["ExternalId"]} failed: {e}'); _filed(store, r['MessageId'], f'failed: {e}')
            elif c['Type'] in ('imap', 'gmail'): n += _file_imap(store, c, mine)
            else:
                for r in mine: _filed(store, r['MessageId'], f"skipped: {c['Type']} has no Archive")
        except Exception as e:
            # the sign-in itself failed: nothing was moved and nothing is written down, so the next poll tries again
            logger.warning(f"filing handled mail on {c.get('Name') or c['Type']} failed: {e}")
    return n


# ── read here, read there ───────────────────────────────────────────────────────────────────────────────────────────────────
# A setting on each mail card (the owner, 2026-11-16: "mark email read as you read them, it should be a setting on the
# connector"). "Read here" is the owner's read receipt - processing_read_receipt, the one record every way of reading writes
# (opening it, shown in the chat, Next, All read on an FYI batch, Done on its task: store.set_funnel_state) - so the write-back
# hangs off that table once, never off a view. Only what was read after the switch went on counts; each mail is written back
# once (mail_read_back); a refusal is kept on the card's switch as one line with its fix, and everything else is tried again.
READ_KEY, READ_PROBLEM, MAIL_CARDS = 'mark_read_here', 'mark_read_problem', ('outlook', 'gmail', 'imap')
OWNER_READS = ('explicit_done', 'surfaced', 'own_words')          # never legacy_preserved: a migration is not the owner reading
SCOPE_LINE = {True: 'Your Microsoft sign-in can read mail but not mark it read - sign in with Microsoft again on this card to allow it.',
              False: 'Microsoft refused to mark mail read - the company app needs Mail.ReadWrite, which its admin grants.'}
READ_EVERY = 15                                                    # seconds between sweeps on the quick clock


def read_since_key(cid) -> str: return f'mark_read_since:{cid}'
def marks_read_here(c) -> bool:
    try: return c.get('Type') in MAIL_CARDS and bool(json.loads(c.get('ConfigJson') or '{}').get(READ_KEY))
    except ValueError: return False


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
    from .channels import graph_creds, graph_token, mark_mail_read, _status
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
    """One sweep: every mail the owner read here, on a card whose switch is on, marked read in that card's own mailbox."""
    n, srcs = 0, None
    for c in store.list_connectors():
        if c['Type'] not in MAIL_CARDS: continue
        key = read_since_key(c['ConnectorId']); since = store.get_setting(key)
        if not (c.get('Active') and marks_read_here(c)):
            if since: store.set_setting(key, '', 'filing')         # off again: a later On starts from then
            continue
        if not since: store.set_setting(key, _now(), 'filing'); continue
        if srcs is None: srcs = [s for s in store.list_sources() if s['Channel'] == 'email' and s.get('Active') and s.get('Address')]
        rows = read_here(store, since, [s['Address'] for s in srcs if s.get('ConnectorId') == c['ConnectorId']])
        if not rows: continue
        full = store.get_connector(c['ConnectorId'], with_secret=True)
        try: got = (_read_graph if c['Type'] == 'outlook' else _read_imap)(store, full, rows)
        except Exception as e:
            from .channels import plain_failure
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
