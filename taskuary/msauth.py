"""Sign in with Microsoft - Graph for a regular user, no Azure portal.

The Outlook card used to need an app registration of the user's own: tenant id, client id, a
client secret, admin-consented APPLICATION permissions. Fine for a tenant owner; impossible
for an employee. This is the other road, the one Thunderbird / Apple Mail / rclone take:
Taskuary ships ONE public client registration (no secret - it is public by design) and the
user signs in to it with the OAuth device-code flow: a short code, microsoft.com/devicelogin,
their own account, consent to THEIR OWN mailbox. We keep the refresh token as the card's
secret and mint access tokens from it silently from then on.

Graph accepts /users/{upn} with a delegated token for the signed-in user's own mailbox, so
the pollers, sender and calendar reader do not change - they get a token from graph_token
as before, and graph_token asks here when the card says auth=user.

Caveats the card states: a tenant that forbids user consent ends the sign-in at "Need admin
approval" - the admin approves ONCE for everyone (a consent grant, not an app registration).
Teams chat reading (getAllMessages) is app-only in Graph, so the sign-in covers mail, send
and calendar; Teams still needs the tenant app.
"""
import os, time, threading
from urllib.parse import quote
import requests
from loguru import logger

AUTH = 'https://login.microsoftonline.com'
GRAPH = 'https://graph.microsoft.com/v1.0'
SCOPES = 'offline_access User.Read Mail.ReadWrite Mail.Send Calendars.Read'
# Taskuary's own registration (multi-tenant + personal accounts, public client, device code
# on). Overridable per install with TASKUARY_MS_CLIENT_ID, or per card with client_id.
PUBLIC_CLIENT_ID = os.getenv('TASKUARY_MS_CLIENT_ID', 'd32e53c9-f00d-49fc-8b93-227b3e0190f0')

_CACHE, _LOCK = {}, threading.Lock()      # refresh token -> (access, expires_at, current refresh token)
on_rotate = None                          # set by the server: (connector id, new refresh token) -> None


def client_id(cfg: dict) -> str: return (cfg.get('client_id') or PUBLIC_CLIENT_ID or '').strip()
def tenant(cfg: dict) -> str: return (cfg.get('tenant_id') or 'common').strip()   # common = work + personal
def is_user(cfg: dict) -> bool: return (cfg or {}).get('auth') == 'user'


class AdminConsent(RuntimeError):
    """The tenant wants an admin to approve Taskuary before its people may sign in."""


def admin_consent_url(cfg: dict) -> str:
    """The link the user forwards to their Microsoft 365 admin. One click + Accept grants the
    delegated scopes for the whole organisation - a consent grant on OUR app id, so nobody on
    their side registers anything. The redirect is the public-client stock URI every such
    registration carries; the admin lands on a blank page saying admin_consent=True."""
    t = tenant(cfg); t = 'organizations' if t == 'common' else t     # personal accounts have no admin
    return (f'{AUTH}/{t}/v2.0/adminconsent?client_id={_need_client(cfg)}&scope={quote(SCOPES)}'
            f'&redirect_uri={quote(f"{AUTH}/common/oauth2/nativeclient", safe="")}')


def _need_client(cfg):
    cid = client_id(cfg)
    if not cid:
        raise RuntimeError("Taskuary's Microsoft app id is not set on this install - set TASKUARY_MS_CLIENT_ID "
                           "(or enter a client_id under the admin fields) and try again")
    return cid


def device_start(cfg: dict) -> dict:
    """Begin the device-code flow: what to show the user (code + URL) and what to poll with."""
    r = requests.post(f'{AUTH}/{tenant(cfg)}/oauth2/v2.0/devicecode', timeout=20,
                      data={'client_id': _need_client(cfg), 'scope': SCOPES})
    if r.status_code != 200: raise RuntimeError(f'Microsoft refused to start sign-in ({r.status_code}): {_err(r)}')
    j = r.json()
    return {'device_code': j['device_code'], 'user_code': j['user_code'], 'verification_uri': j['verification_uri'],
            'expires_in': int(j.get('expires_in') or 900), 'interval': int(j.get('interval') or 5), 'message': j.get('message', '')}


def device_poll(cfg: dict, device_code: str) -> dict:
    """One poll. {'pending': True} until the user finishes; tokens when they have; raises when
    they declined or the code expired."""
    r = requests.post(f'{AUTH}/{tenant(cfg)}/oauth2/v2.0/token', timeout=20,
                      data={'client_id': _need_client(cfg), 'device_code': device_code,
                            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'})
    if r.status_code == 200: return _tokens(r.json())
    err = (r.json() if r.headers.get('content-type', '').startswith('application/json') else {}).get('error', '')
    if err in ('authorization_pending', 'slow_down'): return {'pending': True, 'slow': err == 'slow_down'}
    if err == 'expired_token': raise RuntimeError('the code expired before you finished - start the sign-in again')
    if err == 'authorization_declined': raise RuntimeError('you declined the sign-in')
    desc = _err(r)
    raise (AdminConsent if _needs_admin(desc) else RuntimeError)(_friendly(desc))


def refresh(cfg: dict, refresh_token: str) -> dict:
    r = requests.post(f'{AUTH}/{tenant(cfg)}/oauth2/v2.0/token', timeout=20,
                      data={'client_id': _need_client(cfg), 'refresh_token': refresh_token,
                            'grant_type': 'refresh_token', 'scope': SCOPES})
    if r.status_code != 200:
        raise RuntimeError('the Microsoft sign-in has lapsed - sign in again on the Outlook card '
                           f'({_friendly(_err(r))})')
    return _tokens(r.json())


def access_token(cfg: dict, refresh_token: str) -> str:
    """A live access token for a signed-in card - cached until a minute before expiry, and a
    rotated refresh token is handed to on_rotate so it survives a restart.

    The mint itself sits inside the lock: Outlook and Teams can share one refresh token,
    and a parallel poll that minted twice would rotate the first token out from under the
    second. Waiters reuse the cache entry the first thread just wrote."""
    if not refresh_token: raise RuntimeError('not signed in - click "Sign in with Microsoft" on the Outlook card')
    with _LOCK:
        hit = _CACHE.get(refresh_token)
        if hit and hit[1] > time.time() + 60: return hit[0]
        rt_now = hit[2] if hit else refresh_token
        t = refresh(cfg, rt_now)
        new_rt = t.get('refresh_token') or rt_now
        _CACHE[refresh_token] = (t['access_token'], time.time() + int(t.get('expires_in') or 3600), new_rt)
    if new_rt != refresh_token and on_rotate and cfg.get('_cid'):
        try: on_rotate(cfg['_cid'], new_rt)
        except Exception as e: logger.warning(f'could not persist the rotated Microsoft refresh token: {e}')
    return t['access_token']


def me(token: str) -> dict:
    """Who signed in - the address the mailbox source is created for."""
    r = requests.get(f'{GRAPH}/me', params={'$select': 'displayName,mail,userPrincipalName'},
                     headers={'Authorization': f'Bearer {token}'}, timeout=20)
    r.raise_for_status()
    j = r.json()
    return {'account': (j.get('mail') or j.get('userPrincipalName') or '').strip(), 'name': j.get('displayName') or ''}


def _tokens(j: dict) -> dict:
    return {'access_token': j['access_token'], 'refresh_token': j.get('refresh_token'), 'expires_in': j.get('expires_in')}


def _err(r) -> str:
    try: j = r.json(); return j.get('error_description') or j.get('error') or r.text[:300]
    except ValueError: return r.text[:300]


def _needs_admin(desc: str) -> bool:
    d = desc or ''
    return 'AADSTS65001' in d or 'AADSTS90094' in d or ('consent' in d.lower() and 'admin' in d.lower())


def _friendly(desc: str) -> str:
    """Entra's error prose, said the way the card should say it."""
    d = desc or ''
    if _needs_admin(d):
        return ('your organisation requires an admin to approve Taskuary once ("Need admin approval") - '
                'forward the approval link below to your Microsoft 365 admin, then sign in again')
    if 'AADSTS700016' in d or 'AADSTS90002' in d:
        return "Taskuary's Microsoft app is not visible to this account's tenant - check TASKUARY_MS_CLIENT_ID"
    if 'AADSTS50076' in d or 'AADSTS50079' in d: return 'your organisation needs multi-factor sign-in - complete it in the browser and try again'
    if 'AADSTS53003' in d or 'conditional access' in d.lower(): return 'a Conditional Access policy in your organisation blocks this sign-in - your admin can allow Taskuary'
    return d[:300]
