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

CREDENTIALS. The card takes an access token, not a client id and secret, on purpose: LinkedIn has
no device-code flow, so a desktop app either ships a redirect listener or asks for a token that
LinkedIn's own portal will generate for you (My Apps -> Auth -> OAuth 2.0 token generator). The
token is short-lived (60 days), which the card says, and a refresh_token is stored when the owner
has one so a later version can renew it without asking again.

THE AUTHOR URN is not something a person can paste from memory: it is `urn:li:person:{sub}` where
`sub` comes from the OIDC userinfo endpoint. `linkedin_me` fetches it, and `linkedin_post` calls
that itself rather than making the owner find it - a card that needs a hand-copied opaque id is a
card nobody sets up twice.
"""
import json

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
