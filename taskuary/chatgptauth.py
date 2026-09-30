"""Sign in with ChatGPT - the owner's ChatGPT plan as a brain, no API key.

OpenAI's plan sharing for open-source, locally hosted apps (DevDay 2026, developers.openai.com/siwc):
the owner signs in once in their own browser, OpenAI registers a client for THIS install on the fly
(dynamic registration - there is no Taskuary app id to ship), and model calls are billed to their
ChatGPT allowance under a weekly cap they set per app. The Codex CLI already rode the plan for coding;
this is the same plan for the one-message jobs - triage, the Assistant, reports - which only ever
spoke to API keys.

The shape is msauth's: the refresh token is the card's secret, access tokens are minted from it and
cached, a rotated refresh token is handed to on_rotate so it survives a restart. What differs is the
sign-in itself: a browser redirect to a loopback listener on 127.0.0.1 (the only redirect OpenAI
takes for desktop apps), with PKCE, state and nonce fresh per attempt.

Limits the card states: text only (no images out, no file search, no code interpreter), streamed and
never stored on OpenAI's side, and a cap reached stops the brain until the owner raises it in ChatGPT.
"""
import base64, hashlib, json, secrets, threading, time, uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse
import requests
from loguru import logger

AUTH = 'https://auth.openai.com'
API = 'https://api.openai.com/v1'
SCOPES = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
PLAN_SCOPE = 'chatgpt.tokens.use.direct'   # without it the sign-in worked and no call will
PORT = 1455                                # OpenAI's example; anything on loopback is taken, so a busy port is not fatal
AGENT_NAME = 'Taskuary'

_CACHE, _LOCK = {}, threading.Lock()       # refresh token -> (access, expires_at, current refresh token)
_FLOWS = {}                                # flow id -> one sign-in in progress
on_rotate = None                           # set by the server: (connector id, new refresh token) -> None


def host_id(cfg: dict) -> str:
    """This install's stable, opaque id - usage is counted per host. Minted once, kept on the card."""
    return (cfg or {}).get('host_id') or f'urn:uuid:{uuid.uuid4()}'


def _b64(b: bytes) -> str: return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


class _Callback(BaseHTTPRequestHandler):
    """One GET, the browser coming back from auth.openai.com. Everything else is a 404."""
    def do_GET(self):
        u = urlparse(self.path)
        f = self.server.flow
        if u.path != '/auth/callback':
            self.send_response(404); self.end_headers(); return
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if q.get('state') != f['state']: f['error'] = 'the sign-in came back for a different attempt - start it again'
        elif q.get('error'): f['error'] = q.get('error_description') or q['error']
        else: f['code'], f['client_id'], f['scope'] = q.get('code'), q.get('client_id') or f['client_id'], q.get('scope', '')
        ok = not f.get('error')
        body = (f"<!doctype html><meta charset=utf-8><title>Taskuary</title><body style='font:15px system-ui;margin:3em'>"
                f"<h2>{'Signed in to ChatGPT' if ok else 'The sign-in did not finish'}</h2>"
                f"<p>{'You can close this tab - Taskuary is finishing on its own.' if ok else f.get('error', '')}</p>").encode()
        self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.end_headers()
        self.wfile.write(body)
        threading.Thread(target=self.server.shutdown, daemon=True).start()
    def log_message(self, *a): pass       # the request line would carry the code into the log


def _listen() -> HTTPServer:
    for port in (PORT, 0):
        try: return HTTPServer(('127.0.0.1', port), _Callback)
        except OSError: continue          # a Codex login holding 1455 is not a reason to fail
    raise RuntimeError('could not open a local port for the sign-in to return to')


def start(cfg: dict) -> dict:
    """Begin a sign-in: the URL to open in the browser, and a flow id to poll with."""
    for k, v in list(_FLOWS.items()):
        if time.time() - v['at'] > 900: _stop(k)
    verifier = _b64(secrets.token_bytes(32))
    srv = _listen()
    redirect = f'http://127.0.0.1:{srv.server_address[1]}/auth/callback'
    flow = {'state': secrets.token_urlsafe(24), 'nonce': secrets.token_urlsafe(24), 'verifier': verifier, 'redirect': redirect,
            'host_id': host_id(cfg), 'client_id': (cfg or {}).get('client_id') or 'dynamic_agent_client', 'at': time.time(), 'srv': srv}
    srv.flow = flow
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    q = {'client_id': flow['client_id'], 'response_type': 'code', 'redirect_uri': redirect, 'scope': SCOPES,
         'resource': API, 'state': flow['state'], 'nonce': flow['nonce'], 'code_challenge_method': 'S256',
         'code_challenge': _b64(hashlib.sha256(verifier.encode()).digest())}
    # a first sign-in registers this install; a card that already holds a client id signs back in to it
    if q['client_id'] == 'dynamic_agent_client': q.update(agent_name_hint=AGENT_NAME, ext_agent_host_id=flow['host_id'])
    fid = secrets.token_urlsafe(12)
    _FLOWS[fid] = flow
    return {'flow': fid, 'url': f'{AUTH}/api/accounts/authorize?{urlencode(q)}'}


def _stop(fid):
    f = _FLOWS.pop(fid, None)
    if f:
        try: f['srv'].shutdown(); f['srv'].server_close()
        except Exception: pass


def poll(fid: str) -> dict:
    """{'pending': True} until the browser comes back; then the tokens and who signed in. Raises on refusal."""
    f = _FLOWS.get(fid)
    if not f: raise RuntimeError('no such sign-in in progress - start it again')
    if f.get('error'): _stop(fid); raise RuntimeError(f['error'])
    if not f.get('code'):
        if time.time() - f['at'] > 900: _stop(fid); raise RuntimeError('the sign-in took too long - start it again')
        return {'pending': True}
    _stop(fid)
    r = requests.post(f'{AUTH}/api/accounts/oauth/token', timeout=20, data={
        'grant_type': 'authorization_code', 'client_id': f['client_id'], 'code': f['code'],
        'code_verifier': f['verifier'], 'redirect_uri': f['redirect'], 'resource': API})
    if r.status_code != 200: raise RuntimeError(f'OpenAI refused the sign-in ({r.status_code}): {_err(r)}')
    t = r.json()
    granted = str(t.get('scope') or f.get('scope') or '')
    if PLAN_SCOPE not in granted.split():
        raise RuntimeError('signed in, but ChatGPT plan usage was not granted - sign in again and allow it')
    if not t.get('refresh_token'): raise RuntimeError('OpenAI returned no refresh token - offline access was not granted')
    who = _identity(t.get('id_token'), f['nonce'])
    return {'client_id': f['client_id'], 'host_id': f['host_id'], 'refresh_token': t['refresh_token'],
            'access_token': t['access_token'], 'expires_in': t.get('expires_in'), 'scope': granted, **who}


def _identity(id_token: str, nonce: str) -> dict:
    """Who signed in, from the ID token. It came straight from the token endpoint over TLS, which OpenID Connect
    accepts in place of a signature check (Core 3.1.3.7); issuer, expiry and our nonce are still checked."""
    if not id_token: return {'sub': '', 'email': '', 'name': ''}
    try:
        part = id_token.split('.')[1]
        c = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
    except (IndexError, ValueError): raise RuntimeError('OpenAI sent an ID token that does not parse')
    if c.get('nonce') != nonce: raise RuntimeError('the sign-in answer does not belong to this attempt (nonce) - start it again')
    if not str(c.get('iss') or '').startswith(AUTH): raise RuntimeError(f"unexpected token issuer {c.get('iss')!r}")
    if c.get('exp') and float(c['exp']) < time.time(): raise RuntimeError('the sign-in answer had already expired - start it again')
    return {'sub': c.get('sub', ''), 'email': c.get('email', ''), 'name': c.get('name', '')}


_DEAD = {'invalid_grant', 'invalid_refresh_token', 'token_expired', 'refresh_token_expired', 'refresh_token_invalidated', 'refresh_token_reused'}


def refresh(cfg: dict, refresh_token: str) -> dict:
    r = requests.post(f'{AUTH}/api/accounts/oauth/token', timeout=20, data={
        'grant_type': 'refresh_token', 'client_id': cfg.get('client_id') or '', 'refresh_token': refresh_token, 'resource': API})
    if r.status_code != 200:
        code = _code(r)
        if code in _DEAD: raise RuntimeError('the ChatGPT sign-in has lapsed - sign in again on the ChatGPT card')
        raise RuntimeError(f'OpenAI would not renew the ChatGPT sign-in ({r.status_code}): {_err(r)}')
    return r.json()


def access_token(cfg: dict, refresh_token: str) -> str:
    """A live access token - cached until a minute before expiry; the mint is inside the lock so two callers never rotate
    the refresh token out from under each other (a reused one is refused: refresh_token_reused)."""
    if not refresh_token: raise RuntimeError('not signed in - click "Sign in with ChatGPT" on the ChatGPT card')
    with _LOCK:
        hit = _CACHE.get(refresh_token)
        if hit and hit[1] > time.time() + 60: return hit[0]
        rt_now = hit[2] if hit else refresh_token
        t = refresh(cfg, rt_now)
        new_rt = t.get('refresh_token') or rt_now
        _CACHE[refresh_token] = (t['access_token'], time.time() + int(t.get('expires_in') or 3600), new_rt)
    if new_rt != refresh_token and on_rotate and cfg.get('_cid'):
        try: on_rotate(cfg['_cid'], new_rt)
        except Exception as e: logger.warning(f'could not persist the rotated ChatGPT refresh token: {e}')
    return t['access_token']


def revoke(cfg: dict, refresh_token: str) -> None:
    """Sign out: end the renewable session at OpenAI, not just forget it here."""
    try:
        conf = requests.get(f'{AUTH}/.well-known/openid-configuration', timeout=15).json()
        requests.post(conf['revocation_endpoint'], timeout=15, data={
            'token': refresh_token, 'token_type_hint': 'refresh_token', 'client_id': cfg.get('client_id') or ''})
    except Exception as e: logger.warning(f'could not revoke the ChatGPT session at OpenAI: {e}')
    with _LOCK: _CACHE.pop(refresh_token, None)


def models(token: str) -> list:
    """[(slug, display name)] the plan offers - the ones OpenAI marks for listing."""
    r = requests.get(f'{API}/models', headers={'Authorization': f'Bearer {token}'}, timeout=20)
    if r.status_code != 200: raise RuntimeError(f'OpenAI would not list the plan models ({r.status_code}): {_err(r)}')
    return [(m.get('slug') or m.get('id'), m.get('display_name') or m.get('slug') or m.get('id'))
            for m in r.json().get('data') or [] if m.get('visibility', 'list') == 'list' and (m.get('slug') or m.get('id'))]


# what each refusal means, and whether trying again can help (errors-and-recovery)
_CALL_ERRORS = {
    'subscription_sharing_usage_limit_exceeded': 'the weekly cap for Taskuary on your ChatGPT plan is used up - raise it in ChatGPT → Settings, or wait for it to reset',
    'subscription_sharing_user_not_eligible': 'this ChatGPT account is not eligible to share its plan with apps',
    'subscription_sharing_unsupported_capability': 'the plan does not serve this kind of request (text only - no images, files or tools)',
    'subscription_sharing_invalid_user': 'the ChatGPT sign-in is no longer valid - sign in again on the ChatGPT card',
}


def complete(token: str, model: str, system: str, user: str, max_tokens: int, want: dict = None, timeout: int = 120) -> str:
    """One answer, streamed (the plan serves nothing else) and never stored. Only `response.completed` is success:
    a stream that stops early is a failure, not a short answer."""
    body = {'model': model, 'instructions': system, 'store': False, 'stream': True, 'max_output_tokens': max_tokens,
            'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': user}]}]}
    if want: body['text'] = {'format': {'type': 'json_schema', 'name': want.get('name') or 'answer',
                                        'schema': want.get('schema') or want, 'strict': True}}
    with requests.post(f'{API}/responses', json=body, stream=True, timeout=timeout,
                       headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}) as r:
        if r.status_code != 200:
            code = _code(r)
            raise RuntimeError(_CALL_ERRORS.get(code) or f'ChatGPT plan call failed ({r.status_code}): {_err(r)}')
        out, done = [], False
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith('data:'): continue
            data = line[5:].strip()
            if data == '[DONE]': break
            try: ev = json.loads(data)
            except ValueError: continue
            kind = ev.get('type')
            if kind == 'response.output_text.delta': out.append(ev.get('delta') or '')
            elif kind == 'response.completed': done = True; break
            elif kind in ('response.failed', 'error'):
                err = (ev.get('response') or {}).get('error') or ev.get('error') or {}
                raise RuntimeError(_CALL_ERRORS.get(err.get('code')) or f"ChatGPT plan call failed: {err.get('message') or err.get('code') or kind}")
    if not done: raise RuntimeError('the ChatGPT plan answer stopped before it finished - try again')
    return ''.join(out)


def _code(r) -> str:
    try: j = r.json()
    except ValueError: return ''
    e = j.get('error')
    return (e.get('code') if isinstance(e, dict) else e) or ''


def _err(r) -> str:
    try:
        j = r.json(); e = j.get('error')
        return (e.get('message') if isinstance(e, dict) else j.get('error_description') or e) or r.text[:300]
    except ValueError: return r.text[:300]
