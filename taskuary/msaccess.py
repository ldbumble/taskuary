"""Which kind of Microsoft permission a card reads with, and whether it has what the card needs - said the same on every Microsoft card.

Two kinds, and they mean different things to an owner (the owner, 2026-11-13). A SIGN-IN (delegated: auth=user, a refresh token from the
browser sign-in or a device code) acts as that person and sees what they can see. A COMPANY APP (app-only: client credentials) reads
across the whole organisation, with permissions an admin approved. `access` decides which a card uses - through the same roads its reads
take (channels.graph_creds, sharepoint.sharepoint_connection, the Outlook card for the files reads) - and lists each permission the
card's code calls Graph with, against what the token itself carries: an app token's `roles` claim, a sign-in token's `scp`. A token that
does not say (a personal account's is opaque) falls back to what Microsoft said at sign-in (granted_scope), else says it cannot tell.
Nothing here returns or logs a token or a secret."""
import hashlib, json, os, time
from loguru import logger

CARDS = ('outlook', 'teams', 'ms_planner', 'sharepoint', 'onedrive', 'office365_files')
# what each permission is for, in the owner's words
FOR = {'user.read': 'who you are', 'user.readbasic.all': "people's names and addresses", 'mail.read': 'reading mail',
       'mail.readwrite': 'reading and filing mail, drafts', 'mail.send': 'sending what you approve', 'calendars.read': 'reading the calendar',
       'calendars.readwrite': 'the calendar and answering invites', 'people.read': 'finding the people you write with',
       'contacts.read': 'your contacts', 'chat.readwrite': 'reading your chats and marking them read', 'chatmessage.send': 'answering in chats',
       'chat.read.all': "reading the organisation's chats", 'chatmessage.read.all': 'pictures in chat messages',
       'tasks.read': 'your Planner tasks', 'tasks.read.all': "people's Planner tasks", 'sites.read.all': 'SharePoint sites and lists',
       'sites.readwrite.all': 'saving files to SharePoint', 'files.read': 'your OneDrive files', 'files.read.all': 'files shared with you',
       'files.readwrite': 'saving files to your OneDrive'}
# a company app's needs, by card - from the calls each card's code makes (the sign-in's come from msauth, the scopes it asks for)
APP = {'outlook': ['Mail.Read', 'Mail.Send', 'Calendars.Read', ('Mail.ReadWrite',), ('Calendars.ReadWrite',)],
       'teams': ['Chat.Read.All', 'ChatMessage.Read.All', 'User.ReadBasic.All'],
       'ms_planner': ['Tasks.Read.All'], 'sharepoint': ['Sites.Read.All', ('Sites.ReadWrite.All',)],
       'onedrive': ['Files.Read.All'], 'office365_files': ['Files.Read.All', 'Sites.Read.All']}
FILES = {'onedrive': 'Files.Read', 'office365_files': 'Files.Read.All Sites.Read.All'}
TTL, _CACHE = 300, {}


def covers(grant: str, need: str) -> bool:
    "Does `grant` give what `need` asks? ReadWrite covers Read, a tenant-wide .All covers the person's own, never the other way."
    g, n = grant.lower(), need.lower()
    base = n[:-4] if n.endswith('.all') else n
    alts = {base, base.replace('.read', '.readwrite')}
    ok = {a + '.all' for a in alts} | (set() if n.endswith('.all') else alts)
    return g in ok or (n == 'user.readbasic.all' and g in ('user.read.all', 'user.readwrite.all', 'directory.read.all'))


def _needs(c, cfg, user) -> list:
    "[(permission, optional)] this card uses on this kind of sign-in."
    from . import msauth
    t = c['Type']
    if not user: return [(x[0], True) if isinstance(x, tuple) else (x, False) for x in APP[t]]
    if t in FILES: want = FILES[t]
    elif cfg.get('_scope'): want = cfg['_scope']        # a card reading through the Outlook card's sign-in asks for its own scope there
    else: want = msauth.scopes_for(t, bool(cfg.get('allow_files')), people=not cfg.get('people_refused'))
    opt = {s.lower() for v in msauth.PEOPLE_SCOPES.values() for s in v} | {msauth.FILES_SCOPE.lower()}
    return [(s, s.lower() in opt) for s in want.split() if s != 'offline_access']


def _creds(store, c):
    "(cfg, token minter, borrowed-from card type or '') for the road this card's reads take."
    from . import channels
    if c['Type'] == 'sharepoint':
        from .sharepoint import sharepoint_connection, _token
        cfg = sharepoint_connection(store, c['ConnectorId'])
        if not (cfg.get('client_id') and cfg.get('client_secret')): return None, None, ''
        return cfg, lambda: _token(cfg), cfg.get('borrowed') or ''
    if c['Type'] in FILES:
        o = next(iter(store.connectors_by_type('outlook', with_secret=True)), None)
        if not (o and o.get('Secret')): return None, None, ''
        cfg, sec, _ = channels.graph_creds(store, o)
        return cfg, lambda: channels.graph_token(cfg, sec), 'outlook'
    full = store.get_connector(c['ConnectorId'], with_secret=True)
    cfg, sec, borrowed = channels.graph_creds(store, full)
    if not (sec or os.getenv('AZURE_CLIENT_SECRET')): return None, None, ''      # not signed in, no app secret: nothing reads yet
    return cfg, lambda: channels.graph_token(cfg, sec), 'outlook' if borrowed else ''


def _held(cfg, user, mint) -> tuple:
    "(the permissions held or None when nothing says, the app's name from the token, a note)."
    from .calwrite import _claims
    try: claims = _claims(mint())
    except Exception as e:
        from .channels import plain_failure
        return None, '', f"Microsoft could not be asked just now: {plain_failure(e, user)[:200]}"
    held = claims.get('scp', '').split() if user else list(claims.get('roles') or [])
    name = str(claims.get('app_displayname') or '')
    if held: return held, name, ''
    if user and str(cfg.get('granted_scope') or '').strip():      # an opaque token (a personal account): what Microsoft said at sign-in
        return [s.rpartition('/')[2] for s in cfg['granted_scope'].split()], name, 'As Microsoft granted them at sign-in.'
    return None, name, ("This app's token lists no permissions - none granted yet, or not admin-approved." if claims and not user
                        else "This sign-in's token does not say what it was granted.")


def _when(at) -> str:
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(at)).strftime('%d %b %Y')
    except (TypeError, ValueError): return ''


def access(store, c: dict) -> dict:
    """{kind: 'user'|'app'|'', line, needs: [{name, for, granted, optional}], known, note, behind} for a Microsoft card - kind '' when it
    reads through no Microsoft sign-in yet (nothing to say). Asked of Microsoft at most every TTL seconds per card and config."""
    from . import teamsweb
    from .channels import BEHIND
    behind = str(c.get('LastError') or '') if str(c.get('LastError') or '').startswith(BEHIND) else ''
    if c.get('Type') not in CARDS or (c['Type'] == 'teams' and teamsweb.personal(c)): return {'kind': '', 'behind': behind}
    cfg, mint, borrowed = _creds(store, c)
    if not mint: return {'kind': '', 'behind': behind}
    user = cfg.get('auth') == 'user'
    key = (c['ConnectorId'], hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest(), bool(c.get('HasSecret')))
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < TTL: return {**hit[1], 'behind': behind}
    held, app, note = _held(cfg, user, mint)
    via = f" - through the {borrowed.replace('_', ' ').title()} card's {'sign-in' if user else 'app'}" if borrowed else ''
    if user:
        how = {'browser': 'browser sign-in', 'code': 'sign-in with a code'}.get(cfg.get('signed_in_via'), '')
        how = ', '.join(x for x in (how, _when(cfg.get('signed_in_at'))) if x)
        line = f"Signed in as {cfg.get('account') or 'your Microsoft account'} - sees what you can see{f' ({how})' if how else ''}{via}"
    else:
        app = app or cfg.get('client_id') or "your organisation's app"
        line = f"Company app: {app} - reads across your organisation; your admin approves its permissions{via}"
    needs = [{'name': n, 'for': FOR.get(n.lower(), ''), 'optional': o, 'granted': None if held is None else any(covers(g, n) for g in held)}
             for n, o in _needs(c, cfg, user)]
    out = {'kind': 'user' if user else 'app', 'line': line, 'needs': needs, 'known': held is not None, 'note': note}
    if held is not None: _CACHE[key] = (time.time(), out)        # a failed ask is asked again, not remembered
    logger.debug(f"ms access for card {c['ConnectorId']}: {out['kind']}, {sum(not x['granted'] for x in needs if held)} missing")
    return {**out, 'behind': behind}
