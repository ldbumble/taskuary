"""Finding a person by what the owner remembers of them (the owner, 2026-10-27: "I search 'dynamo' and a list of Dynamo people
should show up... I don't remember the email").

One search over everyone Taskuary knows: who wrote in (store.people), who the owner wrote to or copied (people.written_to),
the org chart (orgchart.chart), the people a connected directory named (Microsoft Graph's /me/people, /me/contacts and /users;
Google's contacts, other contacts and Workspace directory - kept under DIR_KEY so the next search finds them without the network),
and for a chat channel the chats seen on it - on Teams, the organisation's people as well. A query word matches
a word of the name, of the company, of the address's mailbox or of its domain - "dynamo" is everyone at dynamo.example or at
Dynamo Freight, "gail" is Gail Moreno - and the matches are ranked by how often and how lately the owner wrote with them.

The little AI is a fallback, never a gate: asked once (job 'rank', light gear) only when the plain match found nobody or the
words read as a description ("the dynamo billing person"), and it may only pick from the known people - an address it invents
is dropped. No AI connected is plain matching only.
"""
import json, math, re, time
from loguru import logger

DIR_KEY, DIR_CAP = 'people_directory', 800       # directory hits remembered, newest first
TOP, AI_POOL = 12, 300
_STOP = {'the', 'a', 'an', 'at', 'from', 'of', 'in', 'on', 'for', 'person', 'guy', 'lady', 'someone', 'who', 'and', 'my', 'our', 'with'}
_FREE = {'gmail', 'outlook', 'hotmail', 'yahoo', 'icloud', 'live', 'msn', 'aol', 'proton', 'protonmail', 'me', 'mail'}
_TLD = {'com', 'org', 'net', 'co', 'io', 'example', 'test', 'invalid', 'uk', 'us', 'de', 'il', 'au', 'ca'}


def _words(s) -> list: return re.findall(r'[a-z0-9]+', str(s or '').lower())

def org_of(email: str) -> str:
    "A domain read as an organisation: 'dynamo.example' -> 'dynamo'; a free mailbox ('gmail.com') is nobody's company."
    labels = [w for w in str(email or '').lower().rpartition('@')[2].split('.') if w and w not in _TLD]
    return '' if not labels or labels[-1] in _FREE else labels[-1]


def directory_known(store) -> list:
    try: v = json.loads(store.get_setting(DIR_KEY) or '[]')
    except (TypeError, ValueError): return []
    return [r for r in v if isinstance(r, dict) and '@' in str(r.get('email') or '')] if isinstance(v, list) else []


def remember(store, found: list) -> int:
    "Keep what a directory said, so a search tomorrow finds them offline. Newest first, one row per address."
    have, n = directory_known(store), 0
    by = {r['email'].lower(): r for r in have}
    for f in found:
        e = str(f.get('email') or '').strip().lower()
        if '@' not in e: continue
        old = by.get(e)
        row = {'email': e, 'name': f.get('name') or (old or {}).get('name') or '', 'company': f.get('company') or (old or {}).get('company') or '',
               'title': f.get('title') or (old or {}).get('title') or ''}
        if st := f.get('staff') or (old or {}).get('staff'): row['staff'] = st       # whose organisation: a Teams chat can open with them
        if row != old: n += 1
        by[e] = row
    if n: store.set_setting(DIR_KEY, json.dumps(list(by.values())[-DIR_CAP:]), 'directory')
    return n


def known(store, channel: str = 'email') -> list:
    """Everyone a search may offer on `channel`: [{to, name, company, title, n, last, source}]. Email merges every source by
    address; a chat channel offers the chats seen on it (their id is what a send takes)."""
    channel = (channel or 'email').lower()
    if channel == 'teams': return _chats(store, channel) + _colleagues(store)
    if channel != 'email': return _chats(store, channel)
    from . import orgchart
    from .people import written_to
    out = {}
    def add(e, name='', n=0, last='', src='', company='', title=''):
        e = str(e or '').strip().lower()
        if '@' not in e: return
        r = out.setdefault(e, {'to': e, 'name': '', 'company': '', 'title': '', 'n': 0, 'last': '', 'source': src})
        r['name'], r['company'], r['title'] = r['name'] or str(name or ''), r['company'] or str(company or ''), r['title'] or str(title or '')
        r['n'] += int(n or 0); r['last'] = max(r['last'], str(last or ''))
    for p in store.people(None): add(p.get('Email'), p.get('Name'), p.get('N'), p.get('Last'), 'mail')
    # writing TO someone is the stronger tie: they count twice
    for a, (n, last) in written_to(store).items(): add(a, '', 2 * n, last, 'sent')
    for r in orgchart.chart(store): add(r.get('email'), r.get('name'), 0, '', 'org chart')
    for r in directory_known(store): add(r['email'], r.get('name'), 0, '', 'directory', r.get('company'), r.get('title'))
    from .ingest import owner_addresses
    own = {a.lower() for a in owner_addresses(store)}
    return [r for e, r in out.items() if e not in own]


def _colleagues(store) -> list:
    """On Teams, the organisation's people a Microsoft directory named, as well as the chats seen (the owner, 2026-10-27: "search the list
    of people you can message"): picking one sends into the 1:1 chat with them, opened if there is none yet (outbound.one_on_one). Only
    when a Teams card is signed in as the owner - an app may not post into a chat at all (outbound.NO_SENDER)."""
    from .outbound import as_person
    if not any(as_person(store, c) for c in store.connectors_by_type('teams')): return []
    from .ingest import owner_addresses
    own = {a.lower() for a in owner_addresses(store)} | {str(json.loads(c.get('ConfigJson') or '{}').get('account') or '').lower()
                                                        for c in store.connectors_by_type('teams')}
    return [{'to': r['email'], 'name': r.get('name') or '', 'company': r.get('company') or '', 'title': r.get('title') or '', 'n': 0, 'last': '',
             'source': 'directory'} for r in directory_known(store) if r.get('staff') == 'microsoft' and r['email'] not in own]


def _chats(store, channel: str) -> list:
    from .outbound import _chat_id
    rows = [{'to': _chat_id(channel, r['Cid']), 'name': r.get('Name') or '', 'company': '', 'title': '', 'n': int(r.get('N') or 0),
             'last': str(r.get('Last') or ''), 'source': 'chat'} for r in store.chats(None) if (r.get('Channel') or '').lower() == channel]
    if channel == 'whatsapp':
        from . import wanames
        for r in wanames.fill(store, rows, key='to'): r['name'] = wanames.label(r['to'], r['name'])
    return [r for r in rows if r['to']]


def score(words: list, r: dict) -> int:
    """How well every query word fits this person, 0 when one does not. A whole word beats the start of one, the start of one beats
    a fragment; the name counts most, then the company and domain, then the mailbox."""
    e = str(r.get('to') or '')
    local, dom = (e.split('@', 1) + [''])[:2] if '@' in e else (e, '')
    fields = [(_words(r.get('name')), 4), (_words(r.get('company')) + _words(dom), 3), (_words(local), 2)]
    flat = ' '.join(_words(r.get('name'))) + ' ' + re.sub(r'[^a-z0-9]', '', e.lower())
    total = 0
    for w in words:
        best = max([wt + 2 for ws, wt in fields if w in ws] + [wt for ws, wt in fields if any(x.startswith(w) for x in ws)] +
                   [1 if len(w) > 2 and w in flat else 0])
        if not best: return 0
        total += best
    return total


def _rank(r: dict) -> float:
    "How much the owner writes with them: log of the count, plus up to one for having written lately."
    return math.log1p(r.get('n') or 0) + (1.0 if str(r.get('last') or '') >= time.strftime('%Y-%m-%d', time.localtime(time.time() - 30 * 86400)) else 0)


def plain(rows: list, q: str, top: int = TOP) -> list:
    words = _words(q)
    if not words: return sorted(rows, key=lambda r: (_rank(r), r['last']), reverse=True)[:top]
    hits = [(score(words, r), r) for r in rows]
    return [r for s, r in sorted(((s, r) for s, r in hits if s), key=lambda x: (x[0], _rank(x[1]), x[1]['last']), reverse=True)][:top]


def describes(q: str) -> bool:
    "Words that describe a person rather than spell them: three or more, or any of the small words a description has."
    ws = _words(q)
    return len(ws) >= 3 or (len(ws) >= 2 and any(w in _STOP for w in ws))


SYSTEM = ('You help pick a person from the owner\'s own address book. Given what the owner typed and a numbered list of people '
          '(name, company, address), answer with JSON {"picks": [numbers]} - the people the words most likely mean, best first, '
          'at most 5, and [] when none fits. Never invent anyone.')


def ai_pick(store, q: str, rows: list, brain=None) -> list:
    "The model's choice among `rows` for the words `q` - only rows that exist, [] when no AI is connected or it answers nothing."
    if not rows or not _words(q): return []
    from . import llm
    try: brain = brain or llm.build_llm(store, job='rank', gear='light')
    except Exception as e: logger.debug(f'people search: no brain - {e}'); return []
    if not brain: return []
    pool = sorted(rows, key=lambda r: (_rank(r), r['last']), reverse=True)[:AI_POOL]
    listing = '\n'.join(f"{i}. {r.get('name') or '-'} | {r.get('company') or org_of(r['to']) or '-'} | {r['to']}" for i, r in enumerate(pool, 1))
    try:
        a = llm.ask_json(brain, SYSTEM, f'THE OWNER TYPED: {q}\n\nPEOPLE:\n{listing}',
                         want={'type': 'object', 'properties': {'picks': {'type': 'array', 'items': {'type': 'integer'}}}, 'required': ['picks']})
    except Exception as e: logger.debug(f'people search: the model did not answer - {e}'); return []
    picks = (a.data or {}).get('picks') if isinstance(a.data, dict) else None
    out = []
    for p in picks if isinstance(picks, list) else []:
        try: i = int(p)
        except (TypeError, ValueError): continue
        if 1 <= i <= len(pool) and pool[i - 1] not in out: out.append(pool[i - 1])
    return out[:5]


# ---- connected directories ----------------------------------------------------------------------------------------------------
# Microsoft: /me/people (People.Read), /me/contacts (Contacts.Read) and the organisation's /users (User.ReadBasic.All on a Teams sign-in).
# Google, on a Gmail card signed in with Google (googlecal.py): the account's contacts, the ones Gmail saved by itself, and a Workspace
# directory. A sign-in that was not granted one of them skips it - it never asks and fails, and nothing here is an error.
# An address book is read whole and matched here (its search is weaker than score), held ten minutes like a query's answer.

_DIR_HELD, _LISTS, DIR_TTL = {}, {}, 600
G_PEOPLE = 'https://people.googleapis.com/v1'
def forget(): _DIR_HELD.clear(); _LISTS.clear()


def _graph(tok: str, path: str, params: dict, eventual=False) -> list:
    import requests
    from .channels import GRAPH
    h = {'Authorization': f'Bearer {tok}'} | ({'ConsistencyLevel': 'eventual'} if eventual else {})
    r = requests.get(f'{GRAPH}{path}', headers=h, params=params, timeout=5)
    return (r.json() or {}).get('value') or [] if r.status_code == 200 else []


def _pages(url: str, tok: str, params: dict, key: str, next_key: str, cap: int = 3000) -> list:
    "Every page of a list (Graph's @odata.nextLink, Google's nextPageToken) up to `cap` rows; a refusal ends it with what it had."
    import requests
    out, h = [], {'Authorization': f'Bearer {tok}'}
    while url and len(out) < cap:
        r = requests.get(url, headers=h, params=params, timeout=10)
        if r.status_code != 200: break
        j = r.json() or {}
        out += j.get(key) or []
        nxt = j.get(next_key)
        if next_key == 'nextPageToken': params = {**params, 'pageToken': nxt} if nxt else None; url = url if nxt else None
        else: url, params = nxt, None
    return out


def _held(key, fetch) -> list:
    if (h := _LISTS.get(key)) and time.time() - h[0] < DIR_TTL: return h[1]
    rows = fetch()
    _LISTS[key] = (time.time(), rows)
    return rows


def matching(rows: list, q: str) -> list:
    "The rows of an address book every word of `q` fits (score), as the directory's {email, name, company, title} rows."
    ws = _words(q)
    return [r for r in rows if ws and score(ws, {'to': r['email'], 'name': r.get('name'), 'company': r.get('company')})]


def graph_people(tok: str, q: str, me: bool) -> list:
    """Microsoft's directory for `q`: the signed-in person's own relevant people (/me/people - outside contacts included, with their
    company) and the organisation's users (/users?$search). A sign-in whose scope reaches neither answers nothing, never an error.
    `staff` marks the organisation's own people: a Teams chat can be opened with them (outbound.one_on_one)."""
    q = re.sub(r'["\\]', '', q)[:60]
    out = []
    if me:
        for j in _graph(tok, '/me/people', {'$search': f'"{q}"', '$top': 15,
                                            '$select': 'displayName,scoredEmailAddresses,companyName,jobTitle,personType'}):
            org = (j.get('personType') or {}).get('subclass') == 'OrganizationUser'
            for a in (j.get('scoredEmailAddresses') or [])[:1]:
                out.append({'email': a.get('address'), 'name': j.get('displayName'), 'company': j.get('companyName'), 'title': j.get('jobTitle')}
                           | ({'staff': 'microsoft'} if org else {}))
    for j in _graph(tok, '/users', {'$search': f'"displayName:{q}" OR "mail:{q}"', '$top': 15,
                                     '$select': 'displayName,mail,userPrincipalName,companyName,jobTitle'}, eventual=True):
        out.append({'email': j.get('mail') or j.get('userPrincipalName'), 'name': j.get('displayName'), 'company': j.get('companyName'),
                    'title': j.get('jobTitle'), 'staff': 'microsoft'})
    return [f for f in out if '@' in str(f.get('email') or '')]


def graph_contacts(tok: str, q: str, key) -> list:
    "The signed-in person's Outlook contacts that fit `q` - by name, company or any of their addresses (Contacts.Read)."
    from .channels import GRAPH
    def book():
        cs = _pages(f'{GRAPH}/me/contacts', tok, {'$top': 500, '$select': 'displayName,emailAddresses,companyName,jobTitle'}, 'value', '@odata.nextLink')
        return [{'email': str(a.get('address') or '').strip(), 'name': c.get('displayName') or a.get('name') or '', 'company': c.get('companyName') or '',
                 'title': c.get('jobTitle') or ''} for c in cs for a in (c.get('emailAddresses') or [])[:3] if '@' in str(a.get('address') or '')]
    return matching(_held(('contacts', key), book), q)


def _gperson(p: dict, staff=False) -> list:
    "A Google People API person as directory rows, one per address."
    name = next((n.get('displayName') for n in p.get('names') or [] if n.get('displayName')), '')
    o = (p.get('organizations') or [{}])[0]
    return [{'email': e['value'], 'name': name, 'company': o.get('name') or '', 'title': o.get('title') or ''} | ({'staff': 'google'} if staff else {})
            for e in (p.get('emailAddresses') or [])[:3] if '@' in str(e.get('value') or '')]


def google_people(tok: str, q: str, granted: str, key) -> list:
    """A Google account's people for `q`: its contacts (people.connections), the ones Gmail saved by itself (otherContacts) and, on a
    Workspace account, its organisation's directory (searchDirectoryPeople). `granted` is what the sign-in was given ('' unknown: ask)."""
    from .googlecal import G_CONTACTS, G_DIRECTORY, G_OTHER
    has = lambda s: not granted or s in granted.split()
    out = []
    if has(G_CONTACTS):
        out += matching(_held(('gcontacts', key), lambda: [r for p in _pages(f'{G_PEOPLE}/people/me/connections', tok, {
            'personFields': 'names,emailAddresses,organizations', 'pageSize': 1000}, 'connections', 'nextPageToken') for r in _gperson(p)]), q)
    if has(G_OTHER):
        out += matching(_held(('gother', key), lambda: [r for p in _pages(f'{G_PEOPLE}/otherContacts', tok, {
            'readMask': 'names,emailAddresses', 'pageSize': 1000}, 'otherContacts', 'nextPageToken') for r in _gperson(p)]), q)
    if has(G_DIRECTORY):
        import requests
        r = requests.get(f'{G_PEOPLE}/people:searchDirectoryPeople', headers={'Authorization': f'Bearer {tok}'}, timeout=5,
                         params={'query': q[:60], 'readMask': 'names,emailAddresses,organizations', 'pageSize': 15,
                                 'sources': ['DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE', 'DIRECTORY_SOURCE_TYPE_DOMAIN_CONTACT']})
        if r.status_code == 200: out += [x for p in (r.json() or {}).get('people') or [] for x in _gperson(p, staff=True)]
    return out


def missing(cfg: dict, kind: str) -> list:
    """The people-search permissions this card's sign-in was not given - [] when it has them all or never said what it has. The card
    says that signing in again adds them (a sign-in from before Taskuary asked for them keeps working without)."""
    if isinstance(cfg, str):
        try: cfg = json.loads(cfg or '{}')
        except ValueError: return []
    if kind == 'gmail':
        from .googlecal import G_CONTACTS
        g = str((cfg or {}).get('google_scope') or '')
        return [G_CONTACTS] if g and (cfg or {}).get('google_refresh_token') and G_CONTACTS not in g.split() else []
    from .msauth import PEOPLE_SCOPES, granted
    if (cfg or {}).get('auth') != 'user': return []
    return [s for s in PEOPLE_SCOPES.get(kind, ()) if granted(cfg, s) is False]


def directory(store, q: str) -> list:
    """Every connected account's directory asked for `q` - the Outlook and Teams cards' Microsoft sign-ins and a Gmail card's Google
    one - each answer held ten minutes and remembered (DIR_KEY). Nothing connected, the demo, or a query under two letters: []."""
    from . import demo
    q = ' '.join(str(q or '').split())
    if len(q) < 2 or demo.enabled(): return []
    key = q.lower()
    if (held := _DIR_HELD.get(key)) and time.time() - held[0] < DIR_TTL: return held[1]
    from .channels import graph_creds, graph_token
    from .msauth import granted
    found = []
    for c in store.connectors_by_type('outlook') + store.connectors_by_type('teams'):
        if not c.get('Active'): continue
        try:
            c = store.get_connector(int(c['ConnectorId']), with_secret=True) or c
            cfg, sec, _ = graph_creds(store, c)
            if not (sec or cfg.get('client_id')): continue
            tok, user = graph_token(cfg, sec), cfg.get('auth') == 'user'
            found += graph_people(tok, q, user and granted(cfg, 'People.Read') is not False)
            if user and c['Type'] == 'outlook' and granted(cfg, 'Contacts.Read') is not False: found += graph_contacts(tok, q, c['ConnectorId'])
        except Exception as e: logger.debug(f'people search: {c.get("Name")} directory skipped - {e}')
    for c in store.connectors_by_type('gmail'):
        if not c.get('Active'): continue
        try:
            cfg = json.loads((store.get_connector(int(c['ConnectorId']), with_secret=True) or c).get('ConfigJson') or '{}')
            if not cfg.get('google_refresh_token'): continue
            from .googlecal import access_token
            found += google_people(access_token(cfg), q, str(cfg.get('google_scope') or ''), c['ConnectorId'])
        except Exception as e: logger.debug(f'people search: {c.get("Name")} Google people skipped - {e}')
    _DIR_HELD[key] = (time.time(), found)
    if found: remember(store, found)
    return found


def search(store, q: str, channel: str = 'email', ai: bool = False, brain=None, top: int = TOP) -> dict:
    """{'data': ranked people, 'ai': True when the model chose them}. `ai` asks the model only when the plain match is empty or the
    words describe someone - the caller asks for it separately, so typing never waits on a model."""
    channel = (channel or 'email').lower()
    if channel in ('email', 'teams') and len(_words(q)): directory(store, q)
    rows = known(store, channel)
    hits = plain(rows, q, top)
    if ai and (not hits or describes(q)):
        picked = ai_pick(store, q, rows, brain)
        if picked: return {'data': [_out(r) for r in picked], 'ai': True}
    return {'data': [_out(r) for r in hits], 'ai': False}


def _out(r: dict) -> dict:
    return {k: r.get(k) for k in ('to', 'name', 'title', 'n', 'last', 'source')} | {'company': r.get('company') or '',
                                                                                    'org': org_of(r['to']) if '@' in str(r.get('to')) else ''}
