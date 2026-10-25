"""Handled mail, filed where it came from. The mark-read switch grew a third answer (the owner, 2026-10-25: "a mark-read
setting already exists - extend that setting rather than adding something new"): leave the mailbox alone, mark read what
the funnel took (what '1' always did), or that AND move the mail out of the Inbox into Archive once it is HANDLED here -
its task closed, or the row put down with Handled. Unhandled mail is never moved: the Inbox keeps exactly what is still owed.

Best-effort like every marker in channels.py: a refused consent or a server with no Archive is written down once per
message and never costs the poll. Only mail handled AFTER the choice was made is filed - choosing it must not empty a
mailbox of a year of closed work in one poll."""
import logging
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
    """Inbound mail the hub is done with since `since`, not filed yet: its task closed, or its row (msg: or the processing
    item it belongs to) settled done. Only mailbox mail - Graph or IMAP ids - is anything this module can move."""
    return store._rows(
        """SELECT m.MessageId, m.ExternalId, m.SourceName FROM message m LEFT JOIN task t ON t.TaskId=m.TaskId
           WHERE m.Channel='email' AND COALESCE(m.Direction,'in')='in' AND (m.ExternalId LIKE 'graph:%' OR m.ExternalId LIKE 'imap:%')
             AND NOT EXISTS (SELECT 1 FROM mail_filed f WHERE f.MessageId=m.MessageId)
             AND ((t.Status IN ('done','dropped') AND t.ClosedAt>=?)
               OR EXISTS (SELECT 1 FROM funnel_state s WHERE s.Key='msg:'||m.MessageId AND s.Status='done' AND s.At>=?)
               OR EXISTS (SELECT 1 FROM processing_member p JOIN funnel_state s ON s.Key='processing:'||p.ItemId
                          WHERE p.EntityKind='message' AND p.LocalId=CAST(m.MessageId AS TEXT) AND p.RetiredAt IS NULL
                            AND s.Status='done' AND s.At>=?))
           ORDER BY m.MessageId LIMIT ?""", (since, since, since, limit))


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


def _file_imap(store, c, rows) -> int:
    from . import imapmail
    M, _user = imapmail._login(c)
    try:
        typ, _d = M.select('INBOX', readonly=False)
        if typ != 'OK': raise RuntimeError(f'SELECT INBOX returned {typ}')
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
    finally:
        try: M.logout()
        except Exception: pass


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
