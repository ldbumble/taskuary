"""Apple Messages as an inbound channel - the Mac's own iMessage / SMS / RCS.

There is no API and no token: Messages.app keeps every conversation that reaches this Mac in
a SQLite file (~/Library/Messages/chat.db), and macOS lets a process read it once the owner
grants that process Full Disk Access. So the poller is a read-only SQLite cursor on message
ROWID, and a reply is Messages.app's own public AppleScript `send` command, run through
osascript with the text and chat id passed as ARGV - never spliced into script source.

Two macOS permissions are involved and both belong to macOS, not Taskuary: Full Disk Access
to read the database, and Automation (Messages) to send. Neither is bypassed or reset here;
the Test result names which one is missing and which process macOS will list, because the
thing that needs the permission is whatever launched Taskuary - Terminal, iTerm, an IDE,
or a bare python - and a checkbox next to the wrong one is the classic dead end.

Same shape as the other chat channels: one conversation id per chat, replies go back into
the same chat, own messages ride along as context on the chat's task.
"""
import json, os, platform, sqlite3, subprocess, sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from loguru import logger

DB_PATH = Path.home() / 'Library' / 'Messages' / 'chat.db'
APPLE_EPOCH = 978307200            # 2001-01-01T00:00:00Z as a unix timestamp
POLL_LIMIT = 500                   # rows per page; the poll loops until caught up
SEND_MAX = 4000                    # per message; longer replies are split at paragraphs
SEND_TIMEOUT = 15
MIN_SUPPORTED = 13                 # the maintained test matrix starts at Ventura
MAX_KNOWN = 26                     # anything newer is "experimental" until a smoke test passes
MAX_BLOB = 512 * 1024              # attributedBody larger than this is not a text message

# Baseline schema: absent = a database this connector does not understand. Everything else
# is feature-detected and NULL-aliased so a column Apple adds or drops never breaks the poll.
REQUIRED = {'message': ('ROWID', 'guid', 'text', 'date', 'is_from_me', 'handle_id'),
            'chat': ('ROWID', 'guid'), 'handle': ('ROWID', 'id'),
            'chat_message_join': ('chat_id', 'message_id')}
OPTIONAL_MESSAGE = ('attributedBody', 'associated_message_type', 'item_type', 'date_edited',
                    'date_retracted', 'cache_has_attachments', 'service')
OPTIONAL_CHAT = ('display_name', 'chat_identifier', 'style', 'service_name')

# Messages.app's scripting dictionary - a module constant, so what reaches osascript as source
# never depends on user text. Text and chat id arrive as `on run argv` items.
SEND_SCRIPT = '''on run argv
    set messageText to item 1 of argv
    set chatGuid to item 2 of argv
    tell application "Messages"
        send messageText to chat id chatGuid
    end tell
end run'''

# What the Apple Events layer answers with, in words. -1743 is the one everybody hits.
OSA_ERRORS = {'-1743': 'macOS has not allowed this process to control Messages (Automation) - '
                       'System Settings → Privacy & Security → Automation, then retry',
              '-1728': 'Messages.app could not find that chat - it must already exist in Messages',
              '-600': 'Messages.app is not running and could not be launched',
              '-10810': 'Messages.app could not be launched'}


def _cfg(c): return json.loads(c.get('ConfigJson') or '{}')


class SetupError(RuntimeError):
    """A failure the owner fixes in System Settings, not in Taskuary. The message is the
    plain sentence every card shows; `setup` is the structured half the Apple Messages card
    turns into buttons (which pane, which host, retry hint). Stable `code`s, never parsed
    text: the React side switches on them."""
    def __init__(self, code: str, detail: str, pane: str | None = None):
        super().__init__(detail)
        self.code, self.setup = code, setup_info(code, pane)


# The two panes this connector ever opens, as fixed URLs the server picks by enum - a URL
# never travels from the browser. Apple documents the modern scheme loosely, so the manual
# breadcrumb always rides alongside on the card.
SETTINGS_URLS = {
    ('full_disk_access', 'modern'): 'x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_AllFiles',
    ('full_disk_access', 'legacy'): 'x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles',
    ('automation', 'modern'): 'x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Automation',
    ('automation', 'legacy'): 'x-apple.systempreferences:com.apple.preference.security?Privacy_Automation',
}
PANES = ('full_disk_access', 'automation')
BREADCRUMBS = {'full_disk_access': 'System Settings → Privacy & Security → Full Disk Access',
               'automation': 'System Settings → Privacy & Security → Automation'}


# ── platform and permissions ─────────────────────────────────────────────────────────────
def platform_support() -> dict:
    """macOS or not, and which support tier the version falls in. Versions are compared as
    numbers (platform.mac_ver), never by marketing name."""
    if sys.platform != 'darwin':
        return {'platform': sys.platform, 'support': 'unavailable', 'product_version': None}
    ver = platform.mac_ver()[0] or ''
    try: major = int(ver.split('.')[0])
    except ValueError: major = 0
    support = ('supported' if MIN_SUPPORTED <= major <= MAX_KNOWN
               else 'experimental_future_version' if major > MAX_KNOWN
               else 'best_effort' if major == 12 else 'unsupported')
    return {'platform': 'darwin', 'product_version': ver, 'major': major,
            'machine': platform.machine(), 'support': support}


_HOSTS = {'com.apple.Terminal': 'Terminal', 'com.googlecode.iterm2': 'iTerm',
          'com.mitchellh.ghostty': 'Ghostty', 'net.kovidgoyal.kitty': 'kitty',
          'dev.warp.Warp-Stable': 'Warp', 'com.microsoft.VSCode': 'Visual Studio Code',
          'com.todesktop.230313mzl4w4u92': 'Cursor', 'com.jetbrains.pycharm': 'PyCharm'}


def host_process() -> dict:
    """The thing macOS will show in the Full Disk Access list. A process launched from an app
    inherits __CFBundleIdentifier, which names that app; otherwise it is the Python binary
    itself, and the owner has to drag that into the list."""
    env = os.environ
    bid = env.get('__CFBundleIdentifier') or ''
    name = _HOSTS.get(bid) or (bid.rsplit('.', 1)[-1] if bid else None)
    exe = os.path.realpath(sys.executable)
    if name:
        rec = f'grant it to {name} (the app Taskuary was launched from), then relaunch {name}'
    else:
        rec = f'grant it to the Python executable at {exe} - click + in the list and pick that file - then restart Taskuary'
    return {'name': name, 'bundle_id': bid or None, 'python': exe, 'recommendation': rec}


FDA_HINT = BREADCRUMBS['full_disk_access']


def setup_info(code: str, pane: str | None) -> dict:
    ps, h = platform_support(), host_process()
    return {'code': code, 'pane': pane, 'platform': ps['platform'], 'product_version': ps.get('product_version'),
            'support': ps['support'], 'host_name': h['name'], 'host_path': h['python'] if not h['name'] else None,
            'host_bundle_id': h['bundle_id'], 'breadcrumb': BREADCRUMBS.get(pane),
            'restart_may_be_required': pane == 'full_disk_access'}


def settings_url(pane: str) -> str:
    """macOS 13+ has System Settings; 12 and earlier the old System Preferences scheme."""
    if pane not in PANES: raise ValueError(f'unknown settings pane: {pane}')
    ps = platform_support()
    return SETTINGS_URLS[(pane, 'modern' if (ps.get('major') or 0) >= 13 else 'legacy')]


def open_settings(pane: str) -> dict:
    """`open <fixed url>` - argv, no shell, and only the panes above."""
    if sys.platform != 'darwin': raise SetupError('macos_required', 'System Settings only exists on a Mac')
    url = settings_url(pane)
    subprocess.run(['open', url], check=False, timeout=10)
    return {'ok': True, 'pane': pane, 'breadcrumb': BREADCRUMBS[pane]}


# A non-sending Apple Event: asking Messages.app for its name is enough to make macOS decide
# (and, the first time, ask) whether this process may control it. Nothing is sent.
PROBE_SCRIPT = 'tell application "Messages" to get name'


def automation_probe() -> dict:
    """Explained on the card BEFORE it runs, because it is what makes macOS pop the prompt."""
    if sys.platform != 'darwin': raise SetupError('macos_required', 'Messages.app automation only exists on a Mac')
    try:
        r = subprocess.run(['osascript', '-'], input=PROBE_SCRIPT, capture_output=True, text=True, timeout=SEND_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise SetupError('messages_app_unavailable', f'Messages.app did not answer within {SEND_TIMEOUT}s - is it able to launch?')
    err = (r.stderr or '').strip()
    if r.returncode != 0:
        if '-1743' in err:
            raise SetupError('automation_denied', 'macOS has not allowed this process to control Messages - allow '
                             f'{host_process()["name"] or "it"} under {BREADCRUMBS["automation"]}, then test again', 'automation')
        raise SetupError('messages_app_unavailable', f'Messages.app could not be reached: {err or "no detail"}')
    return {'ok': True, 'detail': f'Messages.app answered ({(r.stdout or "").strip() or "Messages"}) - this process may send through it'}


def db_path(cfg: dict) -> Path:
    """Overridable only through the connector config - for fixtures and development, never a
    field on the card."""
    return Path(cfg.get('db_path') or DB_PATH).expanduser()


def connect(path: Path) -> sqlite3.Connection:
    """Read-only through the URI, and NOT immutable=1: Messages writes through WAL, and an
    immutable handle can keep showing the snapshot it opened with."""
    cx = sqlite3.connect(f'file:{quote(str(path))}?mode=ro', uri=True, timeout=5)
    cx.row_factory = sqlite3.Row
    return cx


def columns(cx) -> dict:
    out = {}
    for t in list(REQUIRED) + ['attachment']:
        try: out[t] = {r[1] for r in cx.execute(f'PRAGMA table_info({t})')}
        except sqlite3.Error: out[t] = set()
    return out


def missing_columns(cols: dict) -> list:
    return [f'{t}.{c}' for t, need in REQUIRED.items() for c in need if c not in cols.get(t, ())]


def open_db(cfg: dict):
    """(connection, columns) or a RuntimeError whose message says what to do. The proof of
    access is a real SELECT on message - file existence and Settings checkboxes both lie."""
    ps = platform_support()
    if ps['support'] == 'unavailable':
        raise SetupError('macos_required', 'Apple Messages needs a Mac - Messages.app keeps its history in a local '
                         'database that only exists on macOS')
    if ps['support'] == 'unsupported':
        raise SetupError('unsupported_macos_version',
                         f"macOS {ps['product_version']} is not supported - Apple Messages needs macOS 12 or later")
    path = db_path(cfg)
    if not path.exists() and not os.access(path.parent, os.R_OK):
        # the folder itself is TCC-protected: a missing file here almost always means no FDA
        raise _fda_error(path)
    if not path.exists():
        raise SetupError('messages_database_missing', f'no Messages database at {path} - sign in to Messages.app on this Mac first')
    try:
        cx = connect(path)
        cx.execute('SELECT ROWID FROM message LIMIT 1').fetchall()
    except (sqlite3.OperationalError, sqlite3.DatabaseError, PermissionError) as e:
        s = str(e).lower()
        if 'locked' in s or 'busy' in s:
            raise SetupError('messages_database_busy', 'the Messages database is busy - Messages.app is writing; try again in a moment')
        if 'unable to open' in s or 'authorization' in s or 'permission' in s or 'not a database' in s:
            raise _fda_error(path)
        raise RuntimeError(f'could not read the Messages database: {e}')
    cols = columns(cx)
    miss = missing_columns(cols)
    if miss:
        cx.close()
        raise SetupError('unsupported_messages_schema',
                         f"this Messages database is not one Taskuary understands (macOS {ps['product_version']}, "
                         f"missing {', '.join(miss)}) - please report it with these details")
    return cx, cols


def _fda_error(path) -> SetupError:
    h = host_process()
    return SetupError('full_disk_access_required',
                      f'macOS is not letting this process read the Messages database ({path}). It needs Full Disk '
                      f'Access - {FDA_HINT} - {h["recommendation"]}. This is a macOS permission: Taskuary cannot '
                      f'grant it, and Settings may only apply after the host is relaunched.', 'full_disk_access')


def test(store, c) -> str:
    """Live probe: a real read of the database, never a send. Automation is left to the first
    reply on purpose - probing it makes macOS pop a prompt during setup, before the owner has
    seen why. The cursor is never touched here."""
    cx, cols = open_db(_cfg(c))
    try:
        n = cx.execute('SELECT COUNT(*) FROM chat').fetchone()[0]
        top = cx.execute('SELECT MAX(ROWID) FROM message').fetchone()[0] or 0
    finally: cx.close()
    if not any(s['Channel'] == 'imessage' for s in store.list_sources(active_only=False)):
        store.save_source({'Channel': 'imessage', 'Address': '*', 'ConnectorId': c['ConnectorId'], 'Active': 1}, 'connector-test')
    ps = platform_support()
    extra = {'best_effort': ' · macOS 12 is best-effort, outside the maintained test matrix',
             'experimental_future_version': f" · macOS {ps['product_version']} is newer than this connector has been tested on"}
    opt = [x for x in OPTIONAL_MESSAGE if x not in cols['message']]
    return (f"Messages database readable · {n} chats · new messages from here on (row {top}). "
            f"Sending goes through Messages.app: macOS asks once, on the first reply, whether "
            f"{host_process()['name'] or 'this process'} may control Messages - allow it"
            + extra.get(ps['support'], '') + (f" · schema without {', '.join(opt)}" if opt else ''))


# ── reading ──────────────────────────────────────────────────────────────────────────────
def apple_date(v) -> str:
    """Core Data time: seconds since 2001 in old databases, nanoseconds in new ones - told
    apart by magnitude. Lands as local 'YYYY-MM-DD HH:MM:SS' like every other channel."""
    if not v: return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    secs = v / 1e9 if abs(v) > 1e11 else v
    return datetime.fromtimestamp(APPLE_EPOCH + secs).strftime('%Y-%m-%d %H:%M:%S')


def extract_attributed_text(blob) -> str | None:
    """Newer databases leave message.text NULL and keep the body inside attributedBody, an
    NSKeyedArchiver-free 'typedstream' of an NSAttributedString. The string is the NSString
    payload right after the class name: a one-byte length, or 0x81 + 2-byte / 0x82 + 4-byte
    little-endian for longer text. Only that payload is taken - never a sweep of printable
    bytes, which is how attribute keys end up as message bodies."""
    if not blob or len(blob) > MAX_BLOB or not blob.startswith(b'\x04\x0bstreamtyped'): return None
    i = blob.find(b'NSString\x01\x94\x84\x01+')   # class record, version, '+' = a string follows
    if i < 0: return None
    i += len(b'NSString\x01\x94\x84\x01+')
    if i >= len(blob): return None
    n, k = blob[i], 1
    if n == 0x81: n, k = int.from_bytes(blob[i + 1:i + 3], 'little'), 3
    elif n == 0x82: n, k = int.from_bytes(blob[i + 1:i + 5], 'little'), 5
    elif n > 0x82: return None
    raw = blob[i + k:i + k + n]
    if len(raw) != n: return None
    try: return raw.decode('utf-8').strip() or None
    except UnicodeDecodeError: return None      # not text - never guess a body


def _select(cols: dict) -> str:
    def opt(t, alias, names, avail):
        return ', '.join(f'{alias}.{c}' if c in avail else f'NULL AS {c}' for c in names)
    return (f"SELECT m.ROWID AS rowid, m.guid AS message_guid, m.text, m.date, m.is_from_me, "
            f"{opt('message', 'm', OPTIONAL_MESSAGE, cols['message'])}, "
            f"h.id AS sender_handle, c.guid AS chat_guid, "
            f"{opt('chat', 'c', OPTIONAL_CHAT, cols['chat'])} "
            f"FROM message m JOIN chat_message_join cmj ON cmj.message_id = m.ROWID "
            f"JOIN chat c ON c.ROWID = cmj.chat_id LEFT JOIN handle h ON h.ROWID = m.handle_id "
            f"WHERE m.ROWID > ? ORDER BY m.ROWID ASC LIMIT ?")


def normalize_row(row) -> dict | None:
    """One message dict, or None for rows that are not messages: tapbacks and their removals
    (associated_message_type), group events like renames (item_type), unsent text, blanks."""
    r = dict(row)
    if r.get('associated_message_type') or r.get('item_type') or r.get('date_retracted'): return None
    text = (r.get('text') or '').strip() or extract_attributed_text(r.get('attributedBody'))
    if not text:
        if r.get('cache_has_attachments'): text = '(attachment - see Messages)'
        else: return None
    handle = r.get('sender_handle') or ''
    title = (r.get('display_name') or '').strip()
    return {'rowid': r['rowid'], 'message_guid': r['message_guid'], 'chat_guid': r['chat_guid'],
            'text': text, 'is_from_me': bool(r.get('is_from_me')), 'handle': handle,
            'group': bool(title) or (r.get('style') == 43),
            'chat_title': title or r.get('chat_identifier') or handle or 'chat',
            'sent_at': apple_date(r.get('date')), 'service': r.get('service')}


def initial_cursor(cx, lookback_days) -> int:
    """First activation never imports years of history: the cursor starts at the newest row,
    or at the first row inside an explicit lookback window."""
    top = cx.execute('SELECT MAX(ROWID), MAX(date) FROM message').fetchone()
    if lookback_days and top[1]:
        cutoff = datetime.now().timestamp() - float(lookback_days) * 86400 - APPLE_EPOCH
        if abs(top[1]) > 1e11: cutoff *= 1e9          # the database's unit, decided once
        r = cx.execute('SELECT MIN(ROWID) FROM message WHERE date >= ?', (cutoff,)).fetchone()[0]
        if r: return int(r) - 1
    return int(top[0] or 0)


def poll(store, c, sources: list, llm=None, file_only=False) -> int:
    """Walk message ROWID past the watermark on the connector, page by page. The watermark
    only moves to the last row of a page that finished ingesting, so a crash mid-page replays
    that page and ExternalId dedupe swallows the overlap. One unreadable row is logged without
    its content and stepped over - a single odd message must not wedge the channel.

    Specific chat ids under Sources LIMIT what comes in (like WhatsApp); with only the '*'
    marker every chat that reaches this Mac is read - and with every row switched OFF, nothing
    is: an explicit off must never widen to everything. Own messages (is_from_me) ride along as
    context on the chat's task through the same ingest_own_message every channel uses - and
    that includes the replies Taskuary itself sent, which come back through chat.db as the
    one canonical copy."""
    from .channels import ingest_own_message
    from .ingest import ingest_message
    cfg = _cfg(c)
    mine = [s for s in sources if s.get('Channel', 'imessage') == 'imessage' and s['Address']]
    known = [s for s in store.list_sources(active_only=False) if s['Channel'] == 'imessage']
    if known and not mine: return 0                   # the owner switched it all off
    want = {s['Address'] for s in mine if s['Address'] != '*'}
    cx, cols = open_db(cfg)
    n = 0
    try:
        cursor = cfg.get('imessage_rowid')
        if cursor is None:
            cursor = initial_cursor(cx, cfg.get('lookback_days'))
            store.set_connector_config(c['ConnectorId'], {**cfg, 'imessage_rowid': cursor})
            cfg = {**cfg, 'imessage_rowid': cursor}
            if not cfg.get('lookback_days'): return 0
        sql = _select(cols)
        while True:
            rows = cx.execute(sql, (int(cursor), POLL_LIMIT)).fetchall()
            if not rows: break
            for row in rows:
                # a row that cannot be READ is stepped over (content-free log); a row that
                # cannot be STORED aborts the page with the watermark where it was, so the
                # message is retried next poll instead of silently lost
                try: m = normalize_row(row)
                except Exception as e:
                    logger.warning(f'imessage: row {row["rowid"]} unreadable, skipped ({type(e).__name__})'); continue
                n += _ingest(store, m, want, llm, file_only, ingest_message, ingest_own_message)
            cursor = rows[-1]['rowid']
            store.set_connector_config(c['ConnectorId'], {**cfg, 'imessage_rowid': cursor})
            if len(rows) < POLL_LIMIT: break
    finally: cx.close()
    return n


def _ingest(store, m, want, llm, file_only, ingest_message, ingest_own_message) -> int:
    if not m: return 0
    if want and m['chat_guid'] not in want: return 0
    conv = f"imessage:{m['chat_guid']}"
    if m['is_from_me']:
        return ingest_own_message(store, {
            'external_id': f"imessage:{m['message_guid']}", 'channel': 'imessage',
            'source_name': m['chat_title'], 'subject': None, 'from_email': None,
            'body': m['text'], 'conversation_id': conv, 'sent_at': m['sent_at']},
            'your message in this chat - kept for context')
    r = ingest_message(store, file_only=file_only, llm=llm, msg={
        'external_id': f"imessage:{m['message_guid']}", 'channel': 'imessage',
        'subject': None, 'body': m['text'], 'from_name': m['handle'] or 'someone',
        'from_email': m['handle'] or None, 'conversation_id': conv, 'sent_at': m['sent_at'],
        'source_name': m['chat_title'] if m['group'] else (m['handle'] or 'Messages')})
    return int(r['status'] != 'duplicate')


# ── sending ──────────────────────────────────────────────────────────────────────────────
def chunks(body: str, limit: int = SEND_MAX) -> list:
    """Split at paragraph breaks, then lines, so nothing is cut mid-sentence."""
    body = (body or '').strip()
    if len(body) <= limit: return [body] if body else []
    out, cur = [], ''
    for para in body.split('\n\n'):
        while len(para) > limit:                     # one huge paragraph: split at a line
            cut = para.rfind('\n', 0, limit)
            cut = cut if cut > 0 else limit
            if cur: out.append(cur); cur = ''
            out.append(para[:cut].strip()); para = para[cut:].strip()
        if len(cur) + len(para) + 2 <= limit: cur = f'{cur}\n\n{para}' if cur else para
        else: out.append(cur); cur = para
    if cur: out.append(cur)
    return out


def _osa(argv: list) -> None:
    """osascript with the script on stdin and everything user-shaped in argv. No shell."""
    r = subprocess.run(['osascript', '-', *argv], input=SEND_SCRIPT, capture_output=True,
                       text=True, timeout=SEND_TIMEOUT)
    if r.returncode != 0:
        err = (r.stderr or '').strip()
        if '-1743' in err: raise SetupError('automation_denied', OSA_ERRORS['-1743'], 'automation')
        why = next((v for k, v in OSA_ERRORS.items() if k in err), None)
        raise RuntimeError(why or f'Messages.app refused the send: {err or "no detail"}')


def send_text(store, chat_guid: str, body: str) -> dict:
    """Into an EXISTING chat by its guid - the id the message row carries. A brand-new
    conversation (a bare number or address) is a different job and not done here."""
    if sys.platform != 'darwin': raise SetupError('macos_required', 'sending through Messages.app needs a Mac')
    c = store.get_connector_by_type('imessage') if store else None
    if not (c and c.get('Active')): raise RuntimeError('the Apple Messages connection is off')
    if not chat_guid: raise RuntimeError('no chat id to send into')
    parts = chunks(body)
    if not parts: raise RuntimeError('nothing to send')
    sent = 0
    try:
        for p in parts:
            _osa([p, chat_guid]); sent += 1
    except subprocess.TimeoutExpired:
        raise RuntimeError(f'Messages.app did not answer within {SEND_TIMEOUT}s'
                           + (f' - {sent} of {len(parts)} parts were sent' if sent else ''))
    except RuntimeError as e:
        if sent: raise RuntimeError(f'{e} - {sent} of {len(parts)} parts were sent before it failed')
        raise
    return {'channel': 'imessage', 'chat': chat_guid, 'parts': sent}
