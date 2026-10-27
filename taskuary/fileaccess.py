"""ALLOW SAVING FILES, per card (the owner, 2026-10-23): Share can put a result in the owner's OneDrive or Google Drive only through a
sign-in that may write files - and no sign-in asks for that by default. Each card opts in on its own:

- Outlook / Teams (msauth.py): the card's switch signs in again with Files.ReadWrite added (server.ms_signin `files`); a tenant app
  is granted Files.ReadWrite.All in Azure by its admin - nothing here can ask for that.
- Gmail (here): the Google refresh token on the card was pasted from a consent round of the owner's own OAuth client. Allowing files
  runs that round again from this server - the scopes the token already holds plus drive.file (which sees only the files this app
  makes) - and keeps the new refresh token; turning it off runs it once more without drive.file.

Never wider than that: no Drive-wide scope, no SharePoint sites."""
import base64, hashlib, json, secrets, time
from urllib.parse import urlencode
import requests

G_AUTH, G_TOKEN = 'https://accounts.google.com/o/oauth2/v2/auth', 'https://oauth2.googleapis.com/token'
DRIVE_FILE = 'https://www.googleapis.com/auth/drive.file'
_STATES: dict = {}       # state -> {cid, verifier, on, scope, at}: a return must answer a round this server started
TTL = 900


def redirect_uri(server: dict) -> str:
    """Back to this server on this computer - a Desktop OAuth client accepts any loopback port."""
    return f"http://127.0.0.1:{server.get('port') or 7787}/api/google/files/callback"


def _gmail(store, cid):
    c = store.get_connector(int(cid), with_secret=True)
    if not c or c.get('Type') != 'gmail': raise LookupError('Allow saving files for Google lives on the Gmail card')
    return c, json.loads(c.get('ConfigJson') or '{}')


def google_url(store, cid: int, server: dict, on: bool = True) -> str:
    """Where the browser goes to say yes. The scopes are the ones the card's token holds now, plus drive.file (on) or minus it (off)."""
    c, cfg = _gmail(store, cid)
    from .googlecal import UNAVAILABLE, client      # the client the card's token was minted with: Taskuary's own, or the card's
    if not all(client(cfg)): raise ValueError(UNAVAILABLE)
    held = []
    if cfg.get('google_refresh_token'):
        from .calwrite import _google_token
        try: held = _google_token(cfg)[1].split()
        except Exception: held = []
    scope = [s for s in held if s != DRIVE_FILE] + ([DRIVE_FILE] if on else [])
    if not scope: raise ValueError('nothing to sign in for - the card holds no Google access to keep')
    for k, v in list(_STATES.items()):
        if time.time() - v['at'] > TTL: _STATES.pop(k, None)
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    _STATES[state] = {'cid': int(cid), 'verifier': verifier, 'on': bool(on), 'at': time.time()}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    return G_AUTH + '?' + urlencode({'client_id': client(cfg)[0], 'redirect_uri': redirect_uri(server), 'response_type': 'code',
                                     'scope': ' '.join(scope), 'access_type': 'offline', 'prompt': 'consent', 'state': state,
                                     'include_granted_scopes': 'false', 'code_challenge': challenge, 'code_challenge_method': 'S256'})


def google_callback(store, server: dict, code: str, state: str, error: str = None) -> tuple:
    """(ok, what to say). Exchanges the code with the round's own verifier and keeps the new refresh token on the card."""
    f = _STATES.pop(str(state or ''), None)
    if not f or time.time() - f['at'] > TTL: return False, 'This sign-in was not started here, or it is too old - press Allow saving files on the Gmail card again.'
    if error: return False, f'Google said: {error}'
    if not code: return False, 'Google sent no code back.'
    try: c, cfg = _gmail(store, f['cid'])
    except LookupError as e: return False, str(e)
    from .googlecal import client
    gid, gsec = client(cfg)
    r = requests.post(G_TOKEN, timeout=20, data={'client_id': gid, 'client_secret': gsec,
                                                'code': code, 'code_verifier': f['verifier'], 'grant_type': 'authorization_code',
                                                'redirect_uri': redirect_uri(server)})
    if r.status_code != 200: return False, f'Google refused the sign-in ({r.status_code}).'
    j = r.json() or {}
    if not j.get('refresh_token'): return False, 'Google returned no refresh token - nothing was changed.'
    granted = str(j.get('scope') or '')
    if f['on'] and DRIVE_FILE not in granted.split(): return False, 'Google did not grant file access - the box for it was left unticked. Nothing was changed.'
    cfg.update({'google_refresh_token': j['refresh_token'], 'allow_files': f['on'], 'google_scope': granted})
    store.save_connector({'ConnectorId': f['cid'], 'ConfigJson': json.dumps(cfg)}, 'owner')
    store.audit('connector', f['cid'], 'google_files', 'owner', detail={'on': f['on'], 'scope': granted})
    from . import sharing
    sharing._CACHE.clear()
    return True, ('Taskuary may now save files you share to your Google Drive, in a Taskuary folder.' if f['on']
                  else 'Taskuary no longer asks Google to save files.')
