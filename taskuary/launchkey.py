"""One-time launch keys: the page carries the owner token only to a window Taskuary opened itself (R29).

The page used to seed the owner token for ANY caller. Host and Origin keep other web sites out, but not another process
on this machine: a restricted session's shell or its agent browser could fetch / and become the owner. So the token is
seeded only for `/?k=<key>`, a key minted here - by the desktop and the CLI in-process, or by the owner-only
POST /api/launch-key - used once, within TTL seconds. A tab already holding the token in localStorage needs none.

Stdlib only, imported before uvicorn starts: cli.open_when_ready's thread must import nothing (its docstring says why)."""
import http.client, json, secrets, threading, time, urllib.parse

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

def link(url: str) -> str: return f"{url.rstrip('/')}/?k={mint()}"

def remote_link(url: str, token: str) -> str:
    "A keyed address from ANOTHER process's server (the instance already running), or the plain one if it gives none."
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
