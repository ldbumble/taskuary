"""Four more chat servers, shaped exactly like Discord: Mattermost, Rocket.Chat, Matrix and
Google Chat.

Discord is the model rather than Slack because these four share its two properties. Each watched
room is its OWN source - a channel id under Sources, polled on its own watermark, so a rate limit
in one room cannot skip the rooms after it. And each can carry a reply BACK, which is what makes
a chat server worth connecting at all: a channel you can only read is a feed.

Three of them are the same object with different spelling - a base url you host yourself and a
token. Which is the point of putting them together: the differences are one header name and one
path, and pretending each needs its own module would hide how alike they are.

  Mattermost   Bearer <token>                         /api/v4
  Rocket.Chat  X-Auth-Token + X-User-Id (two values)  /api/v1
  Matrix       Bearer <token>                         /_matrix/client/v3

Google Chat is the odd one: Google's, so OAuth rather than a token, and it borrows the Gmail
card's client the way SharePoint borrows Outlook's app - one registration, not two. Its rooms are
spaces (spaces/AAAA...), and a Chat app must be added to a space before the API can see it, which
no amount of correct code can do for you. The card says so.
"""
import json
import time
import uuid
from urllib.parse import quote

import requests

from .pm import CAP, _cfg, _seed_source, _stamp
from .devtools import _die, _new

TIMEOUT = 30


def _base(c, fallback='') -> str:
    """The server you host, without its trailing slash. Empty is an error everywhere but Matrix's
    and Google's, which have one home each."""
    return (_cfg(c).get('base_url') or fallback).strip().rstrip('/')


def _ingest(store, src, channel, ext, body, who, at, llm, file_only) -> int:
    """One message onto the Timeline, through the same triage as mail. Returns 1 unless it was
    already here - a poll that re-reads its own window is normal, not an error."""
    from .ingest import ingest_message
    out = ingest_message(store, file_only=file_only, msg={
        'external_id': f'{channel}:{ext}', 'channel': channel, 'subject': None, 'body': body,
        'from_name': who or channel.title(), 'conversation_id': f"{channel}:{src['Address']}",
        'sent_at': at, 'source_name': src['Address']}, llm=llm)
    return out['status'] != 'duplicate'


# ── Mattermost ───────────────────────────────────────────────────────────────────────────
def _mm(c, method, path, **kw):
    base = _base(c)
    if not base: raise RuntimeError('no Mattermost server url saved - e.g. https://chat.acme.com')
    r = requests.request(method, f'{base}/api/v4{path}', timeout=TIMEOUT,
                         headers={'Authorization': f"Bearer {c.get('Secret') or ''}"}, **kw)
    _die(r, 'Mattermost', 'check the personal access token - and that the account can see the channel')
    return r.json()


def test_mattermost(store, c) -> str:
    if not c.get('Secret'):
        raise RuntimeError('no token saved - Mattermost: Profile → Security → Personal Access Tokens '
                           '(an admin must enable them first)')
    me = _mm(c, 'get', '/users/me')
    _seed_source(store, c, _base(c).split('//', 1)[-1])
    return (f"authenticated as {me.get('username')} - add channel IDs under Sources "
            '(View Info on a channel shows its ID)')


def poll_mattermost(store, c, src, since, llm=None, file_only=False) -> int:
    """`since` is milliseconds here, and the server does the filtering - unlike Discord, where the
    window is trimmed on our side because the API only offers a count."""
    posts = _mm(c, 'get', f"/channels/{src['Address']}/posts",
                params={'since': int(since.timestamp() * 1000), 'per_page': CAP})
    order = (posts or {}).get('order') or []
    rows = (posts or {}).get('posts') or {}
    n = 0
    for pid in reversed(order):
        m = rows.get(pid) or {}
        if m.get('type') or not (m.get('message') or '').strip(): continue   # typed posts are joins/leaves
        who = (m.get('props') or {}).get('override_username') or m.get('user_id') or 'Mattermost'
        at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime((m.get('create_at') or 0) / 1000))
        n += _ingest(store, src, 'mattermost', pid, m['message'], who, at, llm, file_only)
    return n


def mattermost_send(store, channel_id: str, body: str, connector_id=None) -> dict:
    c = _card(store, 'mattermost', connector_id)
    _mm(c, 'post', '/posts', json={'channel_id': channel_id, 'message': body[:16000]})
    return {'channel': 'mattermost', 'chat': channel_id}


# ── Rocket.Chat ──────────────────────────────────────────────────────────────────────────
def _rc(c, method, path, **kw):
    """Two values, not one: Rocket.Chat authenticates with a token AND the user id it belongs to.
    The id is ordinary config; only the token is the Secret."""
    base, cfg = _base(c), _cfg(c)
    if not base: raise RuntimeError('no Rocket.Chat server url saved - e.g. https://chat.acme.com')
    if not cfg.get('user_id'): raise RuntimeError('no Rocket.Chat user id saved - it is issued beside the token')
    r = requests.request(method, f'{base}/api/v1{path}', timeout=TIMEOUT,
                         headers={'X-Auth-Token': c.get('Secret') or '', 'X-User-Id': cfg['user_id']}, **kw)
    _die(r, 'Rocket.Chat', 'check the personal access token and the user id beside it')
    return r.json()


def test_rocketchat(store, c) -> str:
    if not c.get('Secret'):
        raise RuntimeError('no token saved - Rocket.Chat: avatar → My Account → Personal Access Tokens')
    me = _rc(c, 'get', '/me')
    _seed_source(store, c, _base(c).split('//', 1)[-1])
    return (f"authenticated as {me.get('username')} - add room IDs under Sources "
            '(kebab menu on a channel → Prune/Admin shows the rid, or use the channel name)')


def poll_rocketchat(store, c, src, since, llm=None, file_only=False) -> int:
    hist = _rc(c, 'get', '/channels.history',
               params={'roomId': src['Address'], 'oldest': since.astimezone().isoformat(), 'count': CAP})
    n = 0
    for m in reversed(hist.get('messages') or []):
        if m.get('t') or not (m.get('msg') or '').strip(): continue        # typed = a room event
        who = (m.get('u') or {}).get('name') or (m.get('u') or {}).get('username') or 'Rocket.Chat'
        n += _ingest(store, src, 'rocketchat', m['_id'], m['msg'], who, _stamp(m.get('ts')), llm, file_only)
    return n


def rocketchat_send(store, room_id: str, body: str, connector_id=None) -> dict:
    c = _card(store, 'rocketchat', connector_id)
    _rc(c, 'post', '/chat.postMessage', json={'roomId': room_id, 'text': body[:20000]})
    return {'channel': 'rocketchat', 'chat': room_id}


# ── Matrix ───────────────────────────────────────────────────────────────────────────────
MATRIX_HOME = 'https://matrix-client.matrix.org'


def _mx(c, method, path, **kw):
    r = requests.request(method, f'{_base(c, MATRIX_HOME)}/_matrix/client/v3{path}', timeout=TIMEOUT,
                         headers={'Authorization': f"Bearer {c.get('Secret') or ''}"}, **kw)
    _die(r, 'Matrix', 'check the access token - and that this account has joined the room')
    return r.json()


def test_matrix(store, c) -> str:
    if not c.get('Secret'):
        raise RuntimeError('no access token saved - Element: Settings → Help & About → Access Token')
    me = _mx(c, 'get', '/account/whoami')
    _seed_source(store, c, _base(c, MATRIX_HOME).split('//', 1)[-1])
    return (f"authenticated as {me.get('user_id')} - add room IDs under Sources "
            '(Room Settings → Advanced → Internal room ID, !abc:server)')


def poll_matrix(store, c, src, since, llm=None, file_only=False) -> int:
    """Backwards from the live end, then trimmed to the window on our side.

    Matrix pages by an opaque token rather than a timestamp, and the token from the last poll is
    the server's, not ours to invent. Walking back from now and dropping what is older is the
    honest version of that - the same thing Discord does, for the same reason.
    """
    room = quote(src['Address'], safe='')
    res = _mx(c, 'get', f'/rooms/{room}/messages',
              params={'dir': 'b', 'limit': CAP, 'filter': json.dumps({'types': ['m.room.message']})})
    floor, n = _new(since), 0
    for e in reversed(res.get('chunk') or []):
        content = e.get('content') or {}
        if content.get('msgtype') != 'm.text' or not (content.get('body') or '').strip(): continue
        at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime((e.get('origin_server_ts') or 0) / 1000))
        if at < floor: continue
        n += _ingest(store, src, 'matrix', e['event_id'], content['body'], e.get('sender'), at, llm, file_only)
    return n


def matrix_send(store, room_id: str, body: str, connector_id=None) -> dict:
    """PUT with a transaction id we mint: Matrix dedupes on it, so a retry after a timeout posts
    once rather than twice."""
    c = _card(store, 'matrix', connector_id)
    room = quote(room_id, safe='')
    _mx(c, 'put', f'/rooms/{room}/send/m.room.message/{uuid.uuid4().hex}',
        json={'msgtype': 'm.text', 'body': body[:30000]})
    return {'channel': 'matrix', 'chat': room_id}


# ── Google Chat ──────────────────────────────────────────────────────────────────────────
GCHAT = 'https://chat.googleapis.com/v1'


def _google_access(store, c) -> str:
    """An access token from a refresh token, borrowing the Gmail card's OAuth client when this
    card carries none - one registration in Google Cloud, not two."""
    cfg = _cfg(c)
    cid, sec = cfg.get('google_client_id'), cfg.get('google_client_secret')
    if not (cid and sec):
        mail = store.get_connector_by_type('gmail', with_secret=True) or {}
        mcfg = _cfg(mail) if mail else {}
        cid, sec = cid or mcfg.get('google_client_id'), sec or mcfg.get('google_client_secret')
    rt = c.get('Secret') or cfg.get('google_refresh_token')
    if not (cid and sec and rt):
        raise RuntimeError('Google Chat needs an OAuth client and a refresh token - fill the client '
                           'id/secret here, or leave them blank to reuse the Gmail card\'s')
    t = requests.post('https://oauth2.googleapis.com/token', timeout=20,
                      data={'client_id': cid, 'client_secret': sec, 'refresh_token': rt,
                            'grant_type': 'refresh_token'})
    if t.status_code != 200: raise RuntimeError(f'Google token failed ({t.status_code}): {t.text[:200]}')
    return t.json()['access_token']


def _gc(store, c, method, path, **kw):
    r = requests.request(method, f'{GCHAT}{path}', timeout=TIMEOUT,
                         headers={'Authorization': f'Bearer {_google_access(store, c)}'}, **kw)
    _die(r, 'Google Chat', 'check the OAuth scopes (chat.messages, chat.spaces.readonly) - and that '
                           'this account is a member of the space')
    return r.json()


def test_google_chat(store, c) -> str:
    spaces = (_gc(store, c, 'get', '/spaces', params={'pageSize': 10}) or {}).get('spaces') or []
    _seed_source(store, c, 'chat.google.com')
    if not spaces:
        return ('authenticated, but this account is in no spaces the API can see - a space must be '
                'joined before it appears')
    names = ', '.join((s.get('displayName') or s.get('name') or '?') for s in spaces[:5])
    return f'authenticated - {len(spaces)} spaces ({names}). Add space names under Sources (spaces/AAAA…)'


def poll_google_chat(store, c, src, since, llm=None, file_only=False) -> int:
    space = src['Address'] if str(src['Address']).startswith('spaces/') else f"spaces/{src['Address']}"
    res = _gc(store, c, 'get', f'/{space}/messages',
              params={'pageSize': CAP, 'orderBy': 'createTime desc',
                      'filter': f'createTime > "{since.astimezone().isoformat()}"'})
    n = 0
    for m in reversed(res.get('messages') or []):
        if not (m.get('text') or '').strip(): continue      # a card-only post has nothing to triage
        who = (m.get('sender') or {}).get('displayName') or 'Google Chat'
        n += _ingest(store, src, 'google_chat', m['name'], m['text'], who,
                     _stamp(m.get('createTime')), llm, file_only)
    return n


def google_chat_send(store, space: str, body: str, connector_id=None) -> dict:
    c = _card(store, 'google_chat', connector_id)
    if not str(space).startswith('spaces/'): space = f'spaces/{space}'
    _gc(store, c, 'post', f'/{space}/messages', json={'text': body[:4000]})
    return {'channel': 'google_chat', 'chat': space}


# ── the seams the rest of the app reaches through ────────────────────────────────────────
def _card(store, typ, connector_id=None) -> dict:
    """The card to send with. A connector_id naming a DIFFERENT type is ignored rather than
    obeyed - the same rule discord_send has, so a tool call cannot redirect one server's token at
    another server."""
    c = store.get_connector(int(connector_id), with_secret=True) if connector_id else \
        store.get_connector_by_type(typ, with_secret=True)
    if c and c.get('Type') != typ: c = None
    if not (c and c.get('Secret')): raise RuntimeError(f'no {typ} token saved')
    return c


TESTS = {'mattermost': test_mattermost, 'rocketchat': test_rocketchat,
         'matrix': test_matrix, 'google_chat': test_google_chat}
POLLS = {'mattermost': poll_mattermost, 'rocketchat': poll_rocketchat,
         'matrix': poll_matrix, 'google_chat': poll_google_chat}
SENDS = {'mattermost': mattermost_send, 'rocketchat': rocketchat_send,
         'matrix': matrix_send, 'google_chat': google_chat_send}
TYPES = tuple(TESTS)


def test(store, c) -> str: return TESTS[c['Type']](store, c)


def send(store, typ: str, room: str, body: str, connector_id=None) -> dict:
    return SENDS[typ](store, room, body, connector_id)
