"""LinkedIn as a Taskuary connection: read who you are, and publish to your own feed.

WHY THIS IS A TOOL AND NOT A CHANNEL. Nothing comes IN from LinkedIn here - there is no inbound
triage, no thread, nobody to reply to. The only verb is "publish", which makes this the same
shape as the QuickBooks bill: an agent drafts it, the card's scope refuses to let the agent send
it, and the owner approves the proposal on the task. `linkedin_post` is a `write` on a card that
ships at `read` (scopes.DEFAULT_SCOPE), so a post reaching the feed is always a click of yours.

THE TWO DOORS TO w_member_social, because picking the wrong one is weeks of your life:

  Share on LinkedIn   consumer, SELF-SERVE. Add the product under My Apps -> Products and the
                      scope is granted. No review. Posts to the authenticated member's own feed,
                      which is the whole of what this card does.
  Community Management  registered legal entity, verified business email, a narrated screencast
                      per use case, and rejection is terminal for that app - you must make a new
                      one. This is the door for posting as an ORGANISATION. We do not use it.

CREDENTIALS ARE A SIGN-IN, not a pasted token. LinkedIn has no device-code flow, so the choice is
a redirect listener or making the owner fetch a token by hand from the app's own portal. Taskuary
already serves a local port, so it takes the redirect: the card holds the app's client id and
secret, Connect opens LinkedIn's consent screen, and the code comes back to
/api/linkedin/callback - the same road QuickBooks and Zoho Invoice take, down to the one-time
state that proves the callback answers a Connect we actually started.

The access token that arrives IS the card's secret. It lasts 60 days, so the card keeps its expiry
and says how long is left rather than waiting for a 401 to explain itself. LinkedIn grants a
refresh token only to approved apps; when one arrives it is kept and spent automatically, and when
one does not, reconnecting is a button rather than a trip back to the portal.

THE AUTHOR URN is not something a person can paste from memory: it is `urn:li:person:{sub}` where
`sub` comes from the OIDC userinfo endpoint. `linkedin_me` fetches it, and `linkedin_post` calls
that itself rather than making the owner find it - a card that needs a hand-copied opaque id is a
card nobody sets up twice.
"""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

API = 'https://api.linkedin.com'
# LinkedIn versions its REST surface by month and rejects a call with no version header. This is
# a floor, not a pin: they accept recent versions, and the card can override it.
VERSION = '202609'
TIMEOUT = 30


def _headers(cfg):
    token = (cfg.get('token') or cfg.get('secret') or '').strip()
    if not token:
        raise RuntimeError('LinkedIn needs an access token - My Apps -> Auth -> OAuth 2.0 token generator')
    return {'Authorization': f'Bearer {token}',
            'LinkedIn-Version': str(cfg.get('version') or VERSION),
            'X-Restli-Protocol-Version': '2.0.0',
            'Content-Type': 'application/json'}


def _fail(r):
    """LinkedIn's errors are readable; pass them through rather than a status code alone."""
    try:
        body = r.json()
        said = body.get('message') or body.get('error_description') or json.dumps(body)[:300]
    except ValueError:
        said = (r.text or '')[:300]
    if r.status_code in (401, 403):
        raise RuntimeError(f'LinkedIn refused the token ({r.status_code}): {said}. '
                           'Check the token has not expired (they last 60 days) and that the app '
                           'has the Share on LinkedIn product added, which grants w_member_social.')
    raise RuntimeError(f'LinkedIn returned {r.status_code}: {said}')


# TWO self-serve products, not one, and this is what stops a first sign-in dead:
#
#   Share on LinkedIn                          -> w_member_social        (the post)
#   Sign In with LinkedIn using OpenID Connect  -> openid, profile, email (who is posting)
#
# An app holding only the first is refused at the CONSENT screen with "Scope openid is not
# authorized for your application" - before any code is issued, so nothing here can catch it
# (2026-09-22). Both are added from the app's Products tab and granted immediately; neither is
# the reviewed Community Management door, where a rejection is terminal for that app.
#
# All four are needed. A post's author is `urn:li:person:{sub}` and `sub` comes from the OIDC
# userinfo endpoint, so without openid there is nobody to author the post as.
SCOPES = 'openid profile email w_member_social'


def missing_product_hint(said: str) -> str:
    """The fix, when LinkedIn's refusal is really a product the app has not added.

    Their wording - "Scope X is not authorized for your application" - reads as "ask whoever
    administers this", which sends the owner looking for permission they already have. It is a
    checkbox on their own app.
    """
    low = str(said or '').lower()
    if 'not authorized for your application' not in low: return ''
    which = ('Sign In with LinkedIn using OpenID Connect' if any(w in low for w in ('openid', 'profile', 'email'))
             else 'Share on LinkedIn' if 'w_member_social' in low else '')
    return ('Add the ' + (f'"{which}" product' if which else 'missing product')
            + ' on the app\'s Products tab at developer.linkedin.com/apps - it is self-serve and '
              'granted immediately - then press Sign in again. This card needs BOTH "Share on '
              'LinkedIn" and "Sign In with LinkedIn using OpenID Connect".')
AUTH = 'https://www.linkedin.com/oauth/v2'


class LinkedInError(RuntimeError): pass


def connection(store, connector_id=None) -> dict:
    """The card as a cfg the OAuth helpers can write back through - `_store`/`_cid` are the handle
    _save needs, the same shape zoho.connection carries."""
    from .reports import _card, _connector
    cfg = _card(store, 'linkedin', 'token', connector_id)
    c = _connector(store, 'linkedin', connector_id)
    return {**cfg, '_store': store, '_cid': (c or {}).get('ConnectorId')}


def redirect_uri(server_cfg: dict) -> str:
    """Where LinkedIn sends the code back. It must be registered on the app's Auth tab EXACTLY,
    so the card shows this string rather than describing it."""
    return f"http://localhost:{server_cfg.get('port') or 7787}/api/linkedin/callback"


def authorize_url(cfg: dict, redirect: str, state: str) -> str:
    if not cfg.get('client_id'):
        raise LinkedInError('add the Client ID and Client Secret from developer.linkedin.com first')
    return AUTH + '/authorization?' + urlencode({
        'response_type': 'code', 'client_id': cfg['client_id'],
        'redirect_uri': redirect, 'state': state, 'scope': SCOPES})


def _save(cfg, token=None, **values):
    store, cid = cfg.get('_store'), cfg.get('_cid')
    if not (store and cid): return
    row = store.get_connector(cid) or {}
    conf = json.loads(row.get('ConfigJson') or '{}'); conf.update({k: v for k, v in values.items() if v})
    body = {'ConnectorId': cid, 'ConfigJson': json.dumps(conf)}
    if token: body['Secret'] = token; cfg['token'] = token
    store.save_connector(body, 'linkedin')
    cfg.update(conf)


def exchange_code(cfg: dict, code: str, redirect: str) -> dict:
    """The code for a token, once. LinkedIn answers 200 with an `error` field for some failures
    rather than a 4xx, so the body is read either way - trusting the status alone stores an empty
    token and the card then says it is connected."""
    r = requests.post(AUTH + '/accessToken', timeout=TIMEOUT,
                      headers={'Content-Type': 'application/x-www-form-urlencoded'},
                      data={'grant_type': 'authorization_code', 'code': code, 'redirect_uri': redirect,
                            'client_id': cfg.get('client_id'), 'client_secret': cfg.get('client_secret')})
    try: j = r.json()
    except ValueError: j = {}
    if r.status_code != 200 or j.get('error') or not j.get('access_token'):
        said = j.get('error_description') or j.get('error') or (r.text or '')[:240]
        raise LinkedInError(f'LinkedIn refused the code ({r.status_code}): {said}')
    expires = int(j.get('expires_in') or 0)
    _save(cfg, j['access_token'],
          expires_at=(datetime.now(timezone.utc) + timedelta(seconds=expires)).isoformat() if expires else '',
          refresh_token=j.get('refresh_token') or '')
    return j


def days_left(cfg: dict):
    """How long this token has, or None when nothing said. A card that goes quiet after 60 days is
    a card the owner reconnects at the worst possible moment."""
    at = str(cfg.get('expires_at') or '').strip()
    if not at: return None
    try: return max(0, (datetime.fromisoformat(at) - datetime.now(timezone.utc)).days)
    except ValueError: return None


def whoami(cfg) -> dict:
    """The signed-in member, and the urn a post has to be authored by."""
    r = requests.get(f'{API}/v2/userinfo', headers=_headers(cfg), timeout=TIMEOUT)
    if not r.ok: _fail(r)
    me = r.json()
    return {'sub': me.get('sub'), 'name': me.get('name'), 'email': me.get('email'),
            'author': f"urn:li:person:{me.get('sub')}" if me.get('sub') else None}


def run_linkedin_me(cfg):
    me = whoami(cfg)
    return {'rows': [me], 'columns': ['sub', 'name', 'email', 'author']}


def run_linkedin_post(cfg):
    """Publish to the member's own feed. A WRITE - reached by proposal, never by an agent alone."""
    text = str(cfg.get('text') or '').strip()
    if not text:
        raise RuntimeError('a LinkedIn post needs `text`')
    if len(text) > 3000:
        raise RuntimeError(f'LinkedIn posts are capped at 3,000 characters; this one is {len(text)}')
    author = str(cfg.get('author') or '').strip() or whoami(cfg)['author']
    if not author:
        raise RuntimeError('could not resolve the author urn - the token may lack the profile scope')
    # PUBLIC unless the owner says otherwise. CONNECTIONS is the only other value LinkedIn takes
    # for a member post, and naming it here means the card can offer the choice later.
    visibility = str(cfg.get('visibility') or 'PUBLIC').upper()
    if visibility not in ('PUBLIC', 'CONNECTIONS'):
        raise RuntimeError("visibility must be PUBLIC or CONNECTIONS")
    body = {'author': author, 'commentary': text, 'visibility': visibility,
            'distribution': {'feedDistribution': 'MAIN_FEED',
                             'targetEntities': [], 'thirdPartyDistributionChannels': []},
            'lifecycleState': 'PUBLISHED', 'isReshareDisabledByAuthor': False}
    r = requests.post(f'{API}/rest/posts', headers=_headers(cfg), json=body, timeout=TIMEOUT)
    if not r.ok: _fail(r)
    # the id comes back in a header, not the body - the body is empty on a 201
    post_id = r.headers.get('x-restli-id') or r.headers.get('X-RestLi-Id') or ''
    return {'rows': [{'id': post_id, 'author': author, 'visibility': visibility,
                      'characters': len(text),
                      'url': f'https://www.linkedin.com/feed/update/{post_id}' if post_id else ''}],
            'columns': ['id', 'author', 'visibility', 'characters', 'url']}
