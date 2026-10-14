"""One-time launch keys: the page carries the owner token only to a window Taskuary opened itself (R29).

The page used to seed the owner token for ANY caller. Host and Origin keep other web sites out, but not another process
on this machine: a restricted session's shell or its agent browser could fetch / and become the owner. So the token is
seeded only for `/?k=<key>`, a key minted here - by the desktop and the CLI in-process, or by the owner-only
POST /api/launch-key - used once, within TTL seconds. A tab already holding the token in localStorage needs none.

Stdlib only, imported before uvicorn starts: cli.open_when_ready's thread must import nothing (its docstring says why)."""
import html, http.client, json, os, pathlib, re, secrets, threading, time, urllib.parse

TTL = 120
_KEYS, _LOCK = {}, threading.Lock()

def mint() -> str:
    k = secrets.token_urlsafe(24)
    with _LOCK:
        now = time.monotonic()
        for o in [o for o, exp in _KEYS.items() if exp <= now]: _KEYS.pop(o)
        _KEYS[k] = now + TTL
    return k

def redeem(k) -> bool:
    "True once for a key minted here and not yet expired; the key is spent either way."
    with _LOCK: exp = _KEYS.pop(str(k or ''), None)
    return bool(exp and exp > time.monotonic())

# An agent's session, by what Taskuary put in its environment (terminal.session_env): any ONE marker is enough, because a
# session that unsets its token keeps the rest - and with none of them config.toml is the owner's, read in-process.
# guard.stranger_token's shape, matched here without guard: this module imports nothing of ours.
MARKERS = ('TASKUARY_TASK', 'TASKUARY_SID', 'TASKUARY_AGENT', 'TASKUARY_TASK_TOKEN')
STRANGER_TOKEN = re.compile(r's1\.(\d{1,12})\.[0-9a-f]{32}')

def in_session() -> bool:
    return any(os.environ.get(k) for k in MARKERS) or bool(STRANGER_TOKEN.fullmatch(os.environ.get('TASKUARY_TOKEN') or ''))

def link(url: str) -> str: return f"{url.rstrip('/')}/?k={mint()}"

def via_file(url: str, folder) -> str:
    """A file:// address of a page that goes on to `url` - for a keyed `url` handed to a browser process. Its command line
    is in any local process's reach (the process list), so it carries the path of this file instead, and the file sits in
    `folder` (Taskuary's home, which the floor keeps a stranger's session out of), owner-only. Files older than TTL go
    first: by then their key is spent or expired, and the CLI that wrote one has usually exited."""
    d = pathlib.Path(folder); d.mkdir(parents=True, exist_ok=True)
    for o in d.glob('*.html'):
        try:
            if o.stat().st_mtime < time.time() - TTL: o.unlink()
        except OSError: pass
    f = d / f'{secrets.token_hex(8)}.html'
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as w:
        w.write(f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={html.escape(url)}">'
                f'<title>Taskuary</title><script>location.replace({json.dumps(url)})</script>')
    return f.as_uri()

def remote_link(url: str, token: str) -> str:
    """A keyed address from ANOTHER process's server (the instance already running), or the plain one if it gives none.
    Never for a session: a key is the owner token for whoever opens it first (R29), and config.toml's token is in reach
    of any process the session starts."""
    if in_session(): return url
    u = urllib.parse.urlsplit(url)
    try:
        conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=5)
        try:
            conn.request('POST', '/api/launch-key', headers={'X-Taskuary-Token': token or '', 'Content-Length': '0'})
            r = conn.getresponse()
            k = json.loads(r.read() or b'{}').get('key') if r.status == 200 else ''
        finally: conn.close()
    except (OSError, ValueError, http.client.HTTPException): k = ''
    return f"{url.rstrip('/')}/?k={urllib.parse.quote(k)}" if k else url
