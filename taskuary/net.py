"""Outbound HTTP for the connectors that poll: one pooled Session, a (connect, read) timeout, and a
cache for app-only bearer tokens.

Why: every call used to be a bare requests.get, a fresh TCP + TLS handshake each time - a Graph call
measured 630 ms bare against 46 ms on a kept connection, a token mint 804 ms against 102 ms - and a
30 s Teams poll paid three of them (token, user lookup, delta) to learn nothing had changed.

The call shape and the exceptions are requests' own, so a module can bind this as its `requests` and
every test that patches `<module>.requests.get` still catches the call. Named net, not http: the exe
is built from taskuary/desktop.py, whose folder lands on the import path, and an http.py there would
shadow the standard library's under requests itself."""
import threading, time
from http import cookiejar
import requests
from requests.adapters import HTTPAdapter
from requests import RequestException, ConnectionError, HTTPError, Timeout   # noqa: F401 - callers catch these by this name

# A single number is BOTH timeouts, so a dead IPv6 route held a Telegram call for Windows' own ~21 s
# give-up before IPv4 was tried. The connect half is short; the read half stays whatever the caller said.
CONNECT = 4
READ = 30

_S, _S_LOCK = None, threading.Lock()


def session() -> requests.Session:
    """The one Session every connector shares. Nothing mutates it after creation (headers and auth
    ride on each call), so the poll's worker threads can share its urllib3 pool safely."""
    global _S
    if _S is None:
        with _S_LOCK:
            if _S is None:
                s = requests.Session()
                # a bare requests.get never carried a cookie into the next call; a Session shared by every
                # connector must not start, or one tenant's cookie rides along on another's request
                s.cookies.set_policy(cookiejar.DefaultCookiePolicy(allowed_domains=[]))
                a = HTTPAdapter(pool_connections=16, pool_maxsize=16)   # up to 8 connectors poll at once
                s.mount('https://', a); s.mount('http://', a)
                _S = s
    return _S


def timeout(t=None):
    """A number becomes (CONNECT, number); a tuple is the caller's own and passes as is."""
    if t is None: return (CONNECT, READ)
    return (CONNECT, t) if isinstance(t, (int, float)) else t


def request(method: str, url: str, **kw) -> requests.Response:
    kw['timeout'] = timeout(kw.get('timeout'))
    r = session().request(method, url, **kw)
    # a cached bearer the server now refuses (revoked consent, a rotated secret) must not be handed out
    # again until it expires: drop it, and the next caller mints a fresh one
    if r.status_code == 401:
        auth = str((kw.get('headers') or {}).get('Authorization') or '')
        if auth.startswith('Bearer '): forget(auth[7:])
    return r


def get(url, **kw): return request('GET', url, **kw)
def post(url, **kw): return request('POST', url, **kw)
def patch(url, **kw): return request('PATCH', url, **kw)


# ── app-only tokens ───────────────────────────────────────────────────────────────────────
# Client-credentials tokens live an hour; minting one per poll was ~2,880 mints a day for one Teams card.
_TOKENS, _T_LOCK = {}, threading.Lock()      # key -> (token, good until)


def token(key, mint) -> str:
    """A cached bearer for `key`. `mint()` returns (token, expires_in seconds) and runs again only a
    minute before expiry, or after a 401 dropped the entry. Minted outside the lock: two threads racing
    a cold cache cost one spare mint, never a stall behind the other's network call."""
    with _T_LOCK:
        hit = _TOKENS.get(key)
        if hit and hit[1] > time.time(): return hit[0]
    tok, ttl = mint()
    with _T_LOCK: _TOKENS[key] = (tok, time.time() + int(ttl or 3600) - 60)
    return tok


def forget(tok: str):
    if not tok: return
    with _T_LOCK:
        for k in [k for k, v in _TOKENS.items() if v[0] == tok]: del _TOKENS[k]


def clear():
    with _T_LOCK: _TOKENS.clear()
