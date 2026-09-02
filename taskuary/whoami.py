"""About you: what the system knows about its owner, gathered in one place.

Every connector learns a piece of who the owner is - the Outlook sign-in knows the account, the
Teams card holds a UPN, Telegram and WhatsApp carry the owner's own chat under notify_chat, the
mailboxes under Sources are theirs. None of it was visible anywhere as a whole, and the agents
that act on the owner's behalf are told about them through SOUL.md alone. This module reads all
of it back - each fact with WHERE it came from - and lets the owner add what nothing can infer
(a phone number, a handle) as plain settings. Later work (a per-person profile the agents can
consult, signing outbound as the right identity per channel) builds on this.

The avatar is generated here too: a deterministic SVG from a seed, in a few styles - no image
model, no upload, and it looks the same on every machine that renders it.
"""
import colorsys, hashlib, json

# the manual facts - plain settings, whitelisted so the endpoint cannot write anything else
FIELDS = {'owner_name': 'name', 'owner_email': 'email', 'owner_title': 'role or title', 'owner_company': 'company',
          'owner_phone': 'phone (WhatsApp / SMS)', 'owner_telegram': 'Telegram handle', 'owner_slack': 'Slack handle',
          'owner_github': 'GitHub login', 'owner_bio': 'a line about you (agents read it)',
          'owner_avatar_style': 'avatar style', 'owner_avatar_seed': 'avatar seed'}
STYLES = ('monogram', 'rings', 'grid', 'waves')


def _cfg(c): return json.loads(c.get('ConfigJson') or '{}')


def profile(store) -> dict:
    st, own = store.get_settings(), store.owner()
    # A connector type is not an identity. People commonly have work + personal GitHub cards
    # (and can have multiple mailboxes or bots); keying this by Type silently kept only the last
    # row returned by SQLite. Keep every card and name it in the provenance so equal-looking
    # identities are still understandable on the About You page.
    conns = {}
    for c in store.list_connectors():
        conns.setdefault(c['Type'], []).append(c)
    cards = lambda typ: conns.get(typ, [])
    card_name = lambda c, label: f'{label} card "{c.get("Name") or c.get("ConnectorId")}"'
    srcs = store.list_sources(active_only=False)
    ids = []
    add = lambda channel, kind, value, source, **kw: value and ids.append({'channel': channel, 'kind': kind, 'value': str(value), 'source': source, **kw})
    add('email', 'address', own.get('owner_email'), 'your owner address (Docs / here)', primary=True)
    for o in cards('outlook'):
        if o.get('Active') and _cfg(o).get('auth') == 'user':
            oc = _cfg(o); add('email', 'Microsoft account', oc.get('account'),
                              f'Sign in with Microsoft on the {card_name(o, "Outlook")}', name=oc.get('name'))
    for s in srcs:
        ch, a = s.get('Channel'), (s.get('Address') or '').strip()
        if not a or a == '*': continue
        if ch == 'email': add('email', 'mailbox', a, 'a mailbox under Sources' + ('' if s.get('Active') else ' (off)'))
        elif ch == 'teams': add('teams', 'UPN' if '@' in a else 'chat id', a, 'the Teams card, under Sources')
    for t, kind in (('telegram', 'your chat id'), ('whatsapp', 'your chat (JID)'), ('teams', 'notify chat id')):
        for c in cards(t):
            if _cfg(c).get('notify_chat'):
                add(t, kind, _cfg(c)['notify_chat'], f'notify chat on the {card_name(c, t)} - where pings and your verdicts go')
    # the paired WhatsApp account IS a phone number - read live off the bridge, best effort
    for wa in cards('whatsapp'):
        if wa.get('Active'):
            try:
                from .messengers import wa_status
                ws = wa_status(store.get_connector(wa['ConnectorId'], with_secret=True))
                if ws.get('connected') and (ws.get('phone') or ws.get('jid')): add('whatsapp', 'your number', ws.get('phone') or ws.get('jid'), f'the WhatsApp account paired through {card_name(wa, "WhatsApp")}', name=ws.get('me'))
                # a bridge started before bridge.mjs learned to report the jid answers without one - say so instead of nothing
                elif ws.get('connected'): add('whatsapp', 'your number', f"paired as {ws.get('me') or 'you'} - restart the bridge (WhatsApp card) to read the number", 'the bridge is running older code than the one on disk')
            except Exception: pass                               # bridge down: the row is simply absent
    for tg in cards('telegram'):
        if tg.get('Active') and not _cfg(tg).get('bot_username'): _learn_telegram(store, tg)
        if _cfg(tg).get('bot_username'):
            add('telegram', 'your bot', '@' + _cfg(tg)['bot_username'], f'{card_name(tg, "Telegram")} (getMe)')
    for gh in cards('github'):
        if gh.get('Active') and not _cfg(gh).get('login'): _learn_github(store, gh)
        if _cfg(gh).get('login'):
            add('github', 'login', _cfg(gh)['login'], f'{card_name(gh, "GitHub")} - who its PAT authenticates as')
    add('telegram', 'handle', st.get('owner_telegram'), 'you typed it here')
    add('whatsapp', 'phone', st.get('owner_phone'), 'you typed it here')
    add('slack', 'handle', st.get('owner_slack'), 'you typed it here')
    add('github', 'login', st.get('owner_github'), 'you typed it here')
    facts = {k: (st.get(k) or '') for k in FIELDS}
    facts['owner_name'], facts['owner_email'] = own.get('owner') if own.get('owner') != 'the owner' else '', own.get('owner_email') or ''
    style, seed = st.get('owner_avatar_style') or 'monogram', st.get('owner_avatar_seed') or facts['owner_name'] or 'taskuary'
    return {'facts': facts, 'identities': ids, 'avatar': avatar_svg(facts['owner_name'], seed, style), 'styles': list(STYLES),
            'told_to_agents': _told(store, facts, ids)}


# The card learns these on Discover / Test - which a connector set up before those existed never ran.
# One live call the first time the page asks, then it is on the card like everything else.
def _learn_github(store, gh):
    try:
        import requests
        from .github import _h
        tok = (store.get_connector(gh['ConnectorId'], with_secret=True) or {}).get('Secret')
        if not tok: return
        r = requests.get('https://api.github.com/user', headers=_h(tok), timeout=8); r.raise_for_status()
        login = r.json().get('login')
        if login: store.set_connector_config(gh['ConnectorId'], {**_cfg(gh), 'login': login}); gh['ConfigJson'] = json.dumps({**_cfg(gh), 'login': login})
    except Exception: pass


def _learn_telegram(store, tg):
    try:
        from .messengers import tg as _tg
        tok = (store.get_connector(tg['ConnectorId'], with_secret=True) or {}).get('Secret')
        if not tok: return
        me = _tg(tok, 'getMe')
        if me.get('username'): store.set_connector_config(tg['ConnectorId'], {**_cfg(tg), 'bot_username': me['username']}); tg['ConfigJson'] = json.dumps({**_cfg(tg), 'bot_username': me['username']})
    except Exception: pass


def _told(store, facts, ids) -> str:
    """What an agent actually reads about the owner - so this page is honest about the gap between
    'known here' and 'told to the agents'."""
    soul = str(store.doc('soul') or '')
    lines = [l.strip() for l in soul.splitlines() if l.strip()]
    hit = [l for l in lines if any(k in l.lower() for k in ('owner', 'you are', 'i am', facts['owner_name'].lower() or '\x00'))][:6]
    return '\n'.join(hit) if hit else 'SOUL.md does not describe the owner yet - the name and email are filled in as {{owner}} tokens where the docs use them.'


def save(store, fields: dict, actor='owner') -> dict:
    bad = [k for k in fields if k not in FIELDS or k in ('owner_name', 'owner_email')]   # name/email go through PUT /api/owner (doc retokening)
    if bad: raise ValueError(f'not a profile field: {", ".join(bad)}')
    for k, v in fields.items():
        if k == 'owner_avatar_style' and v not in STYLES: raise ValueError(f'style must be one of {", ".join(STYLES)}')
        store.set_setting(k, str(v or '').strip(), actor)
    return profile(store)


# ── the avatar ────────────────────────────────────────────────────────────────────────────
def _h(seed: str) -> bytes: return hashlib.sha256((seed or 'taskuary').encode()).digest()
def _hex(h, s, l):
    r, g, b = colorsys.hls_to_rgb(h % 1.0, l, s)
    return '#%02x%02x%02x' % (int(r * 255), int(g * 255), int(b * 255))


def palette(seed: str) -> tuple:
    """Two hues a third of the wheel apart, warm and printable; the same seed always gives the same pair."""
    d = _h(seed)
    h1 = d[0] / 255
    return _hex(h1, 0.42, 0.42), _hex(h1 + 0.33, 0.38, 0.62), _hex(h1 + 0.5, 0.3, 0.92)


def initials(name: str) -> str:
    parts = [p for p in (name or '').replace('-', ' ').split() if p and p[0].isalnum()]
    return ((parts[0][0] + (parts[-1][0] if len(parts) > 1 else '')) if parts else 'T').upper()


def avatar_svg(name: str, seed: str, style: str = 'monogram', size: int = 160) -> str:
    a, b, bg = palette(seed or name)
    d = _h(seed or name)
    head = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160" width="{size}" height="{size}">'
    if style == 'rings':
        rings = ''.join(f'<circle cx="80" cy="80" r="{r}" fill="none" stroke="{a if i % 2 else b}" stroke-width="{4 + d[i] % 9}" '
                        f'stroke-dasharray="{20 + d[i + 8] % 90} {8 + d[i + 16] % 40}" transform="rotate({d[i + 4] % 360} 80 80)"/>'
                        for i, r in enumerate(range(18, 76, 11)))
        body = f'<rect width="160" height="160" rx="32" fill="{bg}"/>{rings}'
    elif style == 'grid':
        cells = ''.join(f'<rect x="{16 + x * 26}" y="{16 + y * 26}" width="24" height="24" rx="5" fill="{a if d[y * 3 + min(x, 4 - x)] % 3 else b}"/>'
                        for y in range(5) for x in range(5) if d[y * 3 + min(x, 4 - x)] % 2)
        body = f'<rect width="160" height="160" rx="32" fill="{bg}"/>{cells}'
    elif style == 'waves':
        waves = ''.join(f'<path d="M0 {40 + i * 22} Q 40 {40 + i * 22 - (d[i] % 30)} 80 {40 + i * 22} T 160 {40 + i * 22}" fill="none" '
                        f'stroke="{a if i % 2 else b}" stroke-width="{6 + d[i + 5] % 6}" stroke-linecap="round" opacity="{0.55 + (d[i + 10] % 40) / 100:.2f}"/>'
                        for i in range(6))
        body = f'<rect width="160" height="160" rx="32" fill="{bg}"/>{waves}'
    else:
        body = (f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient></defs>'
                f'<rect width="160" height="160" rx="32" fill="url(#g)"/>'
                f'<text x="80" y="80" text-anchor="middle" dominant-baseline="central" font-family="Georgia, serif" font-size="72" '
                f'font-weight="700" fill="#fffaf2" letter-spacing="-3">{initials(name)}</text>')
    return head + body + '</svg>'
