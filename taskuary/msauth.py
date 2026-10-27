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
Teams chat reading (getAllMessages) is app-only in Graph, so the Outlook sign-in covers mail, send and calendar (reading
it, and answering invites - Calendars.ReadWrite). A TEAMS card signs in the same way with chat scopes of its own
(TEAMS_SCOPES): its chats are read one by one (channels._teams_user_delta) and a reply is posted as the person.
"""
import os, time, threading
from urllib.parse import quote
import requests
from loguru import logger

AUTH = 'https://login.microsoftonline.com'
GRAPH = 'https://graph.microsoft.com/v1.0'
# Calendars.ReadWrite answers invites and books meetings (calwrite.py) - and reads, so it replaces Calendars.Read. A sign-in
# from before it was asked for holds Calendars.Read only: its refresh asks for exactly what it was granted (refresh_scope),
# so it keeps reading as it always did, and the next sign-in asks for the rest.
# PEOPLE SEARCH (the owner, 2026-10-27: "ask for contacts for Outlook whenever we can"): People.Read is /me/people - the people the
# account writes with, outside contacts and their companies included - and Contacts.Read its own address book (/me/contacts). Both are
# a user's own consent, no admin. A sign-in from before them refreshes with what it was granted (refresh_scope) and the people search
# skips what it cannot read; the card says a fresh sign-in would add them (peoplesearch.missing).
PEOPLE_SCOPES = {'outlook': ('People.Read', 'Contacts.Read'), 'teams': ('People.Read',)}
SCOPES = 'offline_access User.Read Mail.ReadWrite Mail.Send Calendars.ReadWrite People.Read Contacts.Read'
LEGACY_SCOPES = 'offline_access User.Read Mail.ReadWrite Mail.Send Calendars.Read'
# a Teams card's own sign-in: its chats, their senders' names, marking a chat read, and answering in it - none needs an admin.
# TEAMS_CHAT is what an Outlook sign-in is asked for when a Teams card reads through it (channels.graph_creds): never widened, or every
# Outlook sign-in from before a new scope would be refused it and its chats read as lapsed. User.ReadBasic.All already finds the
# organisation's people (/users?$search); People.Read adds the ones this account writes with.
TEAMS_CHAT = 'offline_access User.Read User.ReadBasic.All Chat.ReadWrite ChatMessage.Send'
TEAMS_SCOPES = f'{TEAMS_CHAT} People.Read'
# ALLOW SAVING FILES (the owner, 2026-10-23): a card that opts in signs in again asking for Files.ReadWrite as well - its own OneDrive,
# where Share puts a result (sharing.onedrive). Off by default: the scopes above are never widened unless the card says so.
FILES_SCOPE = 'Files.ReadWrite'
def scopes_for(kind, files: bool = False) -> str: return (TEAMS_SCOPES if kind == 'teams' else SCOPES) + (f' {FILES_SCOPE}' if files else '')
def granted(cfg, scope: str):
    "Was `scope` granted to this sign-in? None when the card never wrote down what was (a sign-in from before PW-143): ask and see."
    g = str((cfg or {}).get('granted_scope') or '').strip()
    if not g: return None
    return scope.lower() in {s.lower().rpartition('/')[2] for s in g.split()}
def card_of(cfg) -> str: return 'Teams' if (cfg or {}).get('_kind') == 'teams' else 'Outlook'   # whose sign-in this is, said
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


def admin_consent_url(cfg: dict, scope: str = SCOPES) -> str:
    """The link the user forwards to their Microsoft 365 admin. One click + Accept grants the
    delegated scopes for the whole organisation - a consent grant on OUR app id, so nobody on
    their side registers anything. The redirect is the public-client stock URI every such
    registration carries; the admin lands on a blank page saying admin_consent=True."""
    t = tenant(cfg); t = 'organizations' if t == 'common' else t     # personal accounts have no admin
    return (f'{AUTH}/{t}/v2.0/adminconsent?client_id={_need_client(cfg)}&scope={quote(scope)}'
            f'&redirect_uri={quote(f"{AUTH}/common/oauth2/nativeclient", safe="")}')


def _need_client(cfg):
    cid = client_id(cfg)
    if not cid:
        raise RuntimeError("Taskuary's Microsoft app id is not set on this install - set TASKUARY_MS_CLIENT_ID "
                           "(or enter a client_id under the admin fields) and try again")
    return cid


def device_start(cfg: dict, scope: str = SCOPES) -> dict:
    """Begin the device-code flow: what to show the user (code + URL) and what to poll with."""
    r = requests.post(f'{AUTH}/{tenant(cfg)}/oauth2/v2.0/devicecode', timeout=20,
                      data={'client_id': _need_client(cfg), 'scope': scope})
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


def refresh_scope(cfg: dict) -> str:
    """What a refresh asks for: what this sign-in was granted. Asking an older sign-in for Calendars.ReadWrite it never
    consented to is refused (AADSTS65001) - and a refusal reads as the sign-in lapsing, for every read it used to make.
    `_scope`: a Teams card reading through the SAME account's Outlook sign-in asks that sign-in for the chat scopes."""
    if (cfg or {}).get('_scope'): return cfg['_scope']
    granted = [s for s in str((cfg or {}).get('granted_scope') or '').split() if s.lower() not in ('openid', 'profile', 'email')]
    return ' '.join(dict.fromkeys(['offline_access', *granted])) if granted else LEGACY_SCOPES


def refresh(cfg: dict, refresh_token: str) -> dict:
    r = requests.post(f'{AUTH}/{tenant(cfg)}/oauth2/v2.0/token', timeout=20,
                      data={'client_id': _need_client(cfg), 'refresh_token': refresh_token,
                            'grant_type': 'refresh_token', 'scope': refresh_scope(cfg)})
    # only Microsoft REFUSING the token is a lapse: a 5xx or a throttle is their service having a bad minute, and
    # calling it "signed out" would send the owner to sign in again for nothing (problems.py reads LAPSED)
    if r.status_code in (400, 401):
        # ...but an Outlook sign-in never asked for Teams is not lapsed: the Teams card signs in for its chats itself
        if cfg.get('_for') == 'teams' and _needs_admin(_err(r)):
            raise RuntimeError(f"the Outlook sign-in for {cfg.get('account') or 'this account'} was not given Teams access - "
                               'press Sign in with Microsoft on the Teams card')
        raise RuntimeError(f'{LAPSED} - sign in again on the {card_of(cfg)} card ({_friendly(_err(r))})')
    if r.status_code != 200: raise RuntimeError(f'Microsoft did not answer the sign-in check ({r.status_code}) - trying again next time')
    return _tokens(r.json())


LAPSED = 'the Microsoft sign-in has lapsed'


def lapsed(err) -> bool:
    """Is this card's last error Microsoft signing the owner out? The card and the bell both ask."""
    return LAPSED in str(err or '')


def access_token(cfg: dict, refresh_token: str) -> str:
    """A live access token for a signed-in card - cached until a minute before expiry, and a
    rotated refresh token is handed to on_rotate so it survives a restart.

    The mint itself sits inside the lock: Outlook and Teams can share one refresh token,
    and a parallel poll that minted twice would rotate the first token out from under the
    second. Waiters reuse the cache entry the first thread just wrote."""
    if not refresh_token: raise RuntimeError(f'not signed in - click "Sign in with Microsoft" on the {card_of(cfg)} card')
    key = (refresh_token, refresh_scope(cfg))       # one sign-in asked for mail and, by a Teams card, for chats: two tokens
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and hit[1] > time.time() + 60: return hit[0]
        rt_now = hit[2] if hit else refresh_token
        t = refresh(cfg, rt_now)
        new_rt = t.get('refresh_token') or rt_now
        _CACHE[key] = (t['access_token'], time.time() + int(t.get('expires_in') or 3600), new_rt)
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
    # the scopes Microsoft actually granted ride along: a sign-in without Mail.Send is knowable before a send (PW-143)
    return {'access_token': j['access_token'], 'refresh_token': j.get('refresh_token'),
            'expires_in': j.get('expires_in'), 'scope': j.get('scope')}


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
