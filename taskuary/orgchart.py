"""Who is who to the owner: their manager, the people who report to them, and who owns what.

Triage read a request from the owner's own manager exactly as it read one from anybody on the To line, and an agent asked
"send this to whoever runs payroll" had nobody to name. Both are facts about the owner's organisation, not about a message,
so they are kept here, once: Microsoft's directory fills in the manager and the direct reports where the sign-in may read
them (/me/manager, /me/directReports), and the owner says the rest through the Assistant ("Erin is my manager", "Ray owns
payroll" - toolcatalog `people.relate`). The owner's word outranks the directory: a relation they set is never overwritten
by a sync, and one they cleared stays cleared.

One setting, `org_chart`: [{email, name, relation: manager|report|'', owns: [areas], pinned}] - `pinned` is the owner having
set the relation. Read by triage (`sender_relation`), the dossier every drafter and agent reads, and the agent's context file.
"""
import json
from datetime import datetime
from loguru import logger

KEY, SYNCED_KEY = 'org_chart', 'org_chart_synced'
RELATIONS = {'manager': 'your manager', 'report': 'reports to you'}
# what the model may call a relation, in the owner's words, -> the stored one; 'none' clears it
SAID = {'manager': 'manager', 'boss': 'manager', 'my manager': 'manager', 'report': 'report', 'reports': 'report', 'direct report': 'report',
        'direct': 'report', 'reports to me': 'report', 'none': '', 'no': '', 'nothing': '', '': ''}


def chart(store) -> list:
    try: v = json.loads(store.get_setting(KEY) or '[]')
    except (TypeError, ValueError): return []
    return [r for r in v if isinstance(r, dict)] if isinstance(v, list) else []


def _save(store, rows: list, actor: str):
    # a row that says nothing is no row - but an owner-cleared relation is kept, so a sync cannot bring it back
    keep = [r for r in rows if r.get('relation') or r.get('owns') or r.get('pinned')]
    store.set_setting(KEY, json.dumps(keep), actor)


def _words(s) -> set:
    from .people import _words as w
    return set(w(s))


def _same(r: dict, email: str = '', name: str = '') -> bool:
    "This row is this person: the address when both have one, else every word of the row's name in theirs."
    e = (email or '').strip().lower()
    if e and r.get('email'): return r['email'] == e
    rn, n = _words(r.get('name')), _words(name) | (_words(e.split('@')[0]) if e else set())
    return bool(rn) and rn <= n


def find(store, email: str = '', name: str = '') -> dict | None:
    return next((r for r in chart(store) if _same(r, email, name)), None)


def _areas(v) -> list:
    xs = v if isinstance(v, list) else str(v or '').replace(';', ',').split(',')
    return [' '.join(str(x).split()) for x in xs if str(x).strip()]


def relate(store, who: str, relation=None, owns=None, drops=None, forget: bool = False, actor: str = 'owner') -> dict:
    """The owner's word on one person. `who` a name or an address - a name the mail resolves to one address is kept by that
    address, a name it cannot is kept by the name (someone the owner never wrote to still runs payroll). `relation`: manager |
    report | none; `owns` areas to add, `drops` areas to take off; `forget` takes the person off the chart. ValueError when the
    name could be several people, or nothing was said."""
    who = ' '.join(str(who or '').split())
    if not who: raise ValueError('say who - a name or an address')
    rel = None if relation is None else SAID.get(str(relation).strip().lower())
    if relation is not None and rel is None: raise ValueError(f"relation is manager, report or none - not {str(relation)[:40]!r}")
    from . import people
    got = people.resolve(store, who)
    if got.get('candidates') and not got.get('address'):
        raise ValueError(f'"{who}" could be ' + ', '.join(got['candidates'][:5]) + ' - say which address')
    email = (got.get('address') or '').lower()
    name = '' if '@' in who else who
    rows = chart(store)
    r = next((x for x in rows if _same(x, email, name)), None)
    if forget:
        if not r: raise ValueError(f'{who} is not on your org chart')
        rows.remove(r); _save(store, rows, actor)
        return {**r, 'forgotten': True}
    if rel is None and not _areas(owns) and not _areas(drops): raise ValueError('say what they are to you (manager, report) or what they own')
    if not r: r = {'email': email, 'name': name, 'relation': '', 'owns': []}; rows.append(r)
    r['email'], r['name'] = r.get('email') or email, r.get('name') or name
    if rel is not None:
        # one manager per mailbox's organisation is the usual shape, but two jobs are two managers - so nobody else is demoted here
        r['relation'], r['pinned'] = rel, True
    low = {a.lower() for a in _areas(drops)}
    r['owns'] = [a for a in r.get('owns') or [] if a.lower() not in low]
    r['owns'] += [a for a in _areas(owns) if a.lower() not in {x.lower() for x in r['owns']}]
    _save(store, rows, actor)
    return r


def words(r: dict) -> str:
    "One row in words: \"your manager; owns payroll, benefits\" - '' for a row that says nothing."
    bits = [RELATIONS[r['relation']]] if r.get('relation') in RELATIONS else []
    if r.get('owns'): bits.append('owns ' + ', '.join(r['owns']))
    return '; '.join(bits)


def relation_of(store, email: str = '', name: str = '') -> str:
    "What this person is to the owner, in words - '' when the chart says nothing about them."
    return words(find(store, email, name) or {})


def line(r: dict) -> str:
    who = r.get('name') or r.get('email') or '?'
    if r.get('name') and r.get('email'): who += f" <{r['email']}>"
    return f'- {who}: {words(r)}'


def block(store) -> str:
    "The whole chart as prompt lines, the manager first - '' when nobody is on it."
    order = {'manager': 0, 'report': 1}
    rows = sorted((r for r in chart(store) if r.get('relation') or r.get('owns')), key=lambda r: order.get(r.get('relation'), 2))
    return '\n'.join(line(r) for r in rows)


# ---- Microsoft's directory --------------------------------------------------------------------------------------------------

def _person(j: dict) -> tuple: return (str(j.get('mail') or j.get('userPrincipalName') or '').lower(), str(j.get('displayName') or ''))


def _get(tok: str, path: str) -> list | dict | None:
    """One directory read: a dict, a list (paged), {} for nobody there (404 - no manager is an answer), or None when Graph will
    not say (403 - a sign-in whose scope does not reach the directory). Neither is a failure: the chart keeps what the owner said."""
    import requests
    from .channels import GRAPH
    url, out = f'{GRAPH}{path}', []
    for _ in range(10):
        r = requests.get(url, headers={'Authorization': f'Bearer {tok}'}, timeout=20,
                         params=None if '?' in url else {'$select': 'displayName,mail,userPrincipalName'})
        if r.status_code == 404: return {}
        if r.status_code != 200: return None
        j = r.json() or {}
        if 'value' not in j: return j
        out += j['value']
        if not (url := j.get('@odata.nextLink')): return out
    return out


def from_directory(store, tok: str, me: str = '/me') -> dict:
    """{'manager': (email, name) | () for none, 'reports': [(email, name)]} for the signed-in person (`me` = /me) or a mailbox an
    app reads (/users/<address>); None for either half the directory will not give."""
    m, rs = _get(tok, f'{me}/manager'), _get(tok, f'{me}/directReports')
    return {'manager': None if m is None else _person(m) if isinstance(m, dict) and _person(m)[0] else (),
            'reports': None if rs is None else [_person(j) for j in (rs if isinstance(rs, list) else []) if isinstance(j, dict) and _person(j)[0]]}


def merge(store, found: list, actor: str = 'directory') -> int:
    """Fold what the directory said into the chart. `found`: from_directory results, one per Microsoft account. A relation the
    owner set (pinned) is never touched; a directory relation the directory no longer gives is taken off - but only for a half
    the directory actually answered, so a sign-in that cannot read reports does not wipe them. Returns how many rows changed."""
    rows, said, asked = chart(store), {}, set()
    for f in found:
        if f.get('manager') is not None: asked.add('manager')
        if f.get('reports') is not None: asked.add('report')
        if f.get('manager'): said[f['manager'][0]] = ('manager', f['manager'][1])
        for e, n in f.get('reports') or []: said.setdefault(e, ('report', n))
    changed = 0
    for r in rows:
        if r.get('pinned'): continue
        want = said.get(r.get('email'), ('', ''))[0]
        if r.get('relation') != want and (want or r.get('relation') in asked): r['relation'] = want; changed += 1
    have = {r.get('email') for r in rows}
    for e, (rel, n) in said.items():
        if e in have: continue
        # someone the owner named before the directory had their address ("Ray owns payroll"): the same row, now with it
        r = next((r for r in rows if not r.get('email') and _same(r, '', n)), None)
        if r: r['email'], r['relation'] = e, r['relation'] if r.get('pinned') else rel
        else: rows.append({'email': e, 'name': n, 'relation': rel, 'owns': []})
        changed += 1
    if changed: _save(store, rows, actor)
    return changed


def sync(store) -> dict:
    """Read the manager and the direct reports for every Microsoft account connected, and fold them in."""
    from .channels import graph_creds, graph_token
    found, skipped = [], []
    for c in store.connectors_by_type('outlook'):
        if not c.get('Active'): continue
        try:
            c = store.get_connector(int(c['ConnectorId']), with_secret=True) or c
            cfg, sec, _ = graph_creds(store, c)
            tok = graph_token(cfg, sec)
            if cfg.get('auth') == 'user': me = '/me'
            else:   # an app registration reads mailboxes, and has no /me: the mailbox this card reads is whose chart it is
                box = next((s['Address'] for s in store.list_sources() if s.get('ConnectorId') == c['ConnectorId'] and '@' in str(s.get('Address') or '')), '')
                if not box: continue
                me = f'/users/{box}'
            f = from_directory(store, tok, me)
            # only both halves refused means the scope does not reach the directory
            if f['manager'] is None and f['reports'] is None: skipped.append(c.get('Name') or 'outlook'); continue
            found.append(f)
        except Exception as e:
            logger.debug(f'org chart: {c.get("Name")} skipped - {e}'); skipped.append(c.get('Name') or 'outlook')
    return {'changed': merge(store, found) if found else 0, 'accounts': len(found), 'skipped': skipped}


def sync_if_due(store, now: datetime = None):
    "Once a day, from the poll's housekeeping: None when today's read already ran."
    today = (now or datetime.now()).strftime('%Y-%m-%d')
    if store.get_setting(SYNCED_KEY, '') == today: return None
    store.set_setting(SYNCED_KEY, today, 'directory')       # before the read: a directory that hangs is not asked again every poll
    return sync(store)
