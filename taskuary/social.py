"""Bluesky and Mastodon: read your own feed, and publish to it.

SHAPED LIKE LINKEDIN, NOT LIKE A CHAT SERVER. Nothing here lands on the Timeline as work. A public
timeline is not an inbox - it has no thread waiting on you and nobody expecting a reply - so both
cards are report sources and tools, and the only verb that leaves the house is a post. Both ship
at authority `read` (scopes.DEFAULT_SCOPE), so an agent drafts and the owner approves, which is
the same road a QuickBooks bill and a LinkedIn post take.

WHY THESE TWO AND NOT X. Both are open by design: an app password on Bluesky and a token on your
own Mastodon instance, issued by you, in a minute, with no review board, no company to be approved
by, and no way for either to be taken away. Neither charges. That is the whole test a connector
has to pass here.

THE AUTHENTICATION DIFFERS AND IT MATTERS:

  Bluesky   TWO steps. An app password is not a bearer token - it buys a SESSION
            (com.atproto.server.createSession), which returns a short-lived accessJwt and the
            account's `did`. The did is the repo every write is addressed to, so a post cannot be
            made without having logged in first. Sessions are cached per card; a 400 on refresh
            simply logs in again.
  Mastodon  ONE step. The access token IS the credential, and every instance is its own server -
            so the card carries the instance url and there is no central host to default to that
            would be right for anyone but the mastodon.social crowd.
"""
import json
import time

import requests

TIMEOUT = 30
BSKY_HOST = 'https://bsky.social'
MASTO_HOST = 'https://mastodon.social'
# Bluesky posts are capped in GRAPHEMES (300) and bytes (3000); Mastodon's default is 500
# characters, which an instance may raise. Both are checked before the call rather than after,
# because a post refused for length is a proposal the owner already approved.
BSKY_CHARS, MASTO_CHARS = 300, 500
_SESSIONS = {}          # card id -> (accessJwt, did, handle, expires at)


def _host(cfg, key, fallback) -> str:
    return (str(cfg.get(key) or '').strip() or fallback).rstrip('/')


def _rows(cfg, rows, unit):
    from .reports import row_limit, rows_out
    lim, mine = row_limit(cfg)
    return rows_out(rows, lim, unit=unit, mine=mine)


# ── Bluesky (AT Protocol) ────────────────────────────────────────────────────────────────
def session(cfg) -> tuple:
    """(accessJwt, did, handle). An app password buys a session, not a bearer token.

    Cached for an hour per card: createSession is rate-limited far more tightly than the read
    endpoints, and a report that logs in on every run is a report that stops working on a busy day.
    """
    handle = str(cfg.get('handle') or '').strip().lstrip('@')
    password = str(cfg.get('app_password') or cfg.get('secret') or '').strip()
    if not handle: raise RuntimeError('no Bluesky handle saved - e.g. alex.bsky.social')
    if not password:
        raise RuntimeError('no Bluesky app password saved - Settings → Privacy and security → '
                           'App passwords (never your account password)')
    key = cfg.get('_cid') or handle
    hit = _SESSIONS.get(key)
    if hit and hit[3] > time.time(): return hit[0], hit[1], hit[2]
    r = requests.post(f"{_host(cfg, 'base_url', BSKY_HOST)}/xrpc/com.atproto.server.createSession",
                      json={'identifier': handle, 'password': password}, timeout=TIMEOUT)
    if r.status_code >= 400:
        said = ''
        try: said = (r.json() or {}).get('message') or ''
        except ValueError: said = (r.text or '')[:200]
        if 'App password' in said or r.status_code == 401:
            said += ' - use an APP PASSWORD (Settings → Privacy and security), not your login password'
        raise RuntimeError(f'Bluesky refused the sign-in ({r.status_code}): {said}')
    j = r.json()
    out = (j['accessJwt'], j['did'], j.get('handle') or handle)
    _SESSIONS[key] = (*out, time.time() + 3600)
    return out


def _bsky(cfg, method, nsid, **kw):
    jwt, _did, _h = session(cfg)
    r = requests.request(method, f"{_host(cfg, 'base_url', BSKY_HOST)}/xrpc/{nsid}", timeout=TIMEOUT,
                         headers={'Authorization': f'Bearer {jwt}'}, **kw)
    if r.status_code >= 400: raise RuntimeError(f'bluesky {nsid} {r.status_code}: {r.text[:300]}')
    return r.json()


def run_bluesky_me(cfg):
    """{} - who this card is signed in as. The Test button's whole job."""
    _jwt, did, handle = session(cfg)
    p = _bsky(cfg, 'get', 'app.bsky.actor.getProfile', params={'actor': did})
    return {'rows': [{'handle': handle, 'did': did, 'name': p.get('displayName') or '',
                      'followers': p.get('followersCount'), 'following': p.get('followsCount'),
                      'posts': p.get('postsCount')}],
            'columns': ['handle', 'did', 'name', 'followers', 'following', 'posts']}


def run_bluesky_timeline(cfg):
    """{"num", "author"} - your home feed, or one account's posts when `author` names a handle."""
    _jwt, did, _h = session(cfg)
    num = max(1, min(int(cfg.get('num') or 30), 100))
    if str(cfg.get('author') or '').strip():
        j = _bsky(cfg, 'get', 'app.bsky.feed.getAuthorFeed',
                  params={'actor': str(cfg['author']).strip().lstrip('@'), 'limit': num})
    else:
        j = _bsky(cfg, 'get', 'app.bsky.feed.getTimeline', params={'limit': num})
    rows = []
    for it in j.get('feed') or []:
        post = it.get('post') or {}
        rec = post.get('record') or {}
        rows.append({'who': (post.get('author') or {}).get('handle') or '',
                     'text': (rec.get('text') or '').strip()[:1000],
                     'at': rec.get('createdAt') or '',
                     'likes': post.get('likeCount'), 'reposts': post.get('repostCount'),
                     'replies': post.get('replyCount'), 'uri': post.get('uri') or ''})
    return _rows(cfg, rows, 'posts')


def run_bluesky_post(cfg):
    """{"text"} - publish to your own feed. A WRITE, reached by proposal and never by an agent
    alone (the card ships at `read`).

    createdAt is sent as the client's time on purpose: the AT Protocol treats the record as yours
    to author, and a server-stamped time would reorder a post the owner approved minutes ago.
    """
    text = str(cfg.get('text') or '').strip()
    if not text: raise RuntimeError('a Bluesky post needs `text`')
    if len(text) > BSKY_CHARS:
        raise RuntimeError(f'Bluesky posts are capped at {BSKY_CHARS} characters; this one is {len(text)}')
    _jwt, did, handle = session(cfg)
    at = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
    j = _bsky(cfg, 'post', 'com.atproto.repo.createRecord',
              json={'repo': did, 'collection': 'app.bsky.feed.post',
                    'record': {'$type': 'app.bsky.feed.post', 'text': text, 'createdAt': at}})
    uri = j.get('uri') or ''
    return {'rows': [{'uri': uri, 'handle': handle, 'characters': len(text),
                      'url': f"https://bsky.app/profile/{handle}/post/{uri.rsplit('/', 1)[-1]}" if uri else ''}],
            'columns': ['uri', 'handle', 'characters', 'url']}


# ── Mastodon ─────────────────────────────────────────────────────────────────────────────
def _masto(cfg, method, path, **kw):
    token = str(cfg.get('token') or cfg.get('secret') or '').strip()
    if not token:
        raise RuntimeError('no Mastodon access token saved - your instance → Preferences → '
                           'Development → New application')
    r = requests.request(method, f"{_host(cfg, 'base_url', MASTO_HOST)}/api/v1{path}", timeout=TIMEOUT,
                         headers={'Authorization': f'Bearer {token}'}, **kw)
    if r.status_code >= 400:
        said = ''
        try: said = (r.json() or {}).get('error') or ''
        except ValueError: said = ''
        raise RuntimeError(f'mastodon {r.status_code}: {said or r.text[:300]}')
    return r.json()


def run_mastodon_me(cfg):
    """{} - the account this token belongs to, and which instance it lives on."""
    me = _masto(cfg, 'get', '/accounts/verify_credentials')
    return {'rows': [{'handle': me.get('acct') or me.get('username') or '',
                      'name': me.get('display_name') or '',
                      'instance': _host(cfg, 'base_url', MASTO_HOST).split('//', 1)[-1],
                      'followers': me.get('followers_count'), 'following': me.get('following_count'),
                      'posts': me.get('statuses_count')}],
            'columns': ['handle', 'name', 'instance', 'followers', 'following', 'posts']}


def run_mastodon_timeline(cfg):
    """{"num", "timeline"} - home by default; `public` or `local` read the instance's own feeds.

    The HTML is stripped here rather than passed on. A summary that has to parse <p> tags before
    it can read a toot is a summary spending its context on markup.
    """
    num = max(1, min(int(cfg.get('num') or 30), 40))
    which = str(cfg.get('timeline') or 'home').strip().lower()
    if which not in ('home', 'public', 'local'):
        raise RuntimeError("timeline must be home, public or local")
    path = '/timelines/home' if which == 'home' else '/timelines/public'
    params = {'limit': num, **({'local': 'true'} if which == 'local' else {})}
    rows = []
    for t in _masto(cfg, 'get', path, params=params) or []:
        acct = t.get('account') or {}
        rows.append({'who': acct.get('acct') or '', 'text': _text(t.get('content'))[:1000],
                     'at': t.get('created_at') or '', 'boosts': t.get('reblogs_count'),
                     'favourites': t.get('favourites_count'), 'replies': t.get('replies_count'),
                     'url': t.get('url') or ''})
    return _rows(cfg, rows, 'posts')


def run_mastodon_post(cfg):
    """{"text", "visibility", "spoiler"} - publish to your own timeline. A WRITE, by proposal.

    Idempotency-Key is sent because a retry after a timeout is the ordinary case for a scheduled
    job, and Mastodon dedupes on it. Without one, a network hiccup posts twice.
    """
    text = str(cfg.get('text') or '').strip()
    if not text: raise RuntimeError('a Mastodon post needs `text`')
    cap = int(cfg.get('max_chars') or MASTO_CHARS)
    if len(text) > cap:
        raise RuntimeError(f'this instance caps posts at {cap} characters; this one is {len(text)}')
    vis = str(cfg.get('visibility') or 'public').strip().lower()
    if vis not in ('public', 'unlisted', 'private', 'direct'):
        raise RuntimeError('visibility must be public, unlisted, private or direct')
    body = {'status': text, 'visibility': vis}
    if str(cfg.get('spoiler') or '').strip(): body['spoiler_text'] = str(cfg['spoiler']).strip()
    import hashlib
    t = _masto_post(cfg, body, hashlib.sha256(f'{vis}:{text}'.encode('utf-8')).hexdigest())
    return {'rows': [{'id': t.get('id') or '', 'url': t.get('url') or '',
                      'visibility': t.get('visibility') or vis, 'characters': len(text)}],
            'columns': ['id', 'url', 'visibility', 'characters']}


def _masto_post(cfg, body, idem_key):
    """Its own function only so the Idempotency-Key rides alongside the Authorization header
    without _masto having to know about either."""
    token = str(cfg.get('token') or cfg.get('secret') or '').strip()
    if not token: raise RuntimeError('no Mastodon access token saved')
    r = requests.post(f"{_host(cfg, 'base_url', MASTO_HOST)}/api/v1/statuses", json=body, timeout=TIMEOUT,
                      headers={'Authorization': f'Bearer {token}', 'Idempotency-Key': idem_key})
    if r.status_code >= 400:
        said = ''
        try: said = (r.json() or {}).get('error') or ''
        except ValueError: said = ''
        raise RuntimeError(f'mastodon {r.status_code}: {said or r.text[:300]}')
    return r.json()


_TAGS = None


def _text(html: str) -> str:
    """A toot's content is HTML. Block ends become newlines, the rest is stripped - the same cut
    channels._clean makes for mail, kept here so this module does not import the mail pipeline."""
    global _TAGS
    if _TAGS is None:
        import re
        _TAGS = (re.compile(r'(?i)<br\s*/?>|</(p|div|li|blockquote)>'), re.compile(r'<[^>]+>'))
    from html import unescape
    brk, tag = _TAGS
    return unescape(tag.sub('', brk.sub('\n', html or ''))).strip()
