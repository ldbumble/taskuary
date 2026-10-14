"""Report a bug from where it happened: the facts, scrubbed, and a draft the person checks.

The tracker (`ldbumble/taskuary`) is PUBLIC, and this app reads one person's mail. So the facts are
gathered by code - where, the error, versions, the log around it, action names - never by a model
that might reach for a task title, and every string is scrubbed before the person sees the draft.
Nothing leaves from here: the popup shows the text and the person presses Submit on GitHub.
"""
import hashlib, json, os, platform, re, sys
from datetime import datetime
from pathlib import Path

from . import config

N_LOG, N_ACTIONS = 30, 5
_STAMP = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ')        # logs.setup's file format
_ID = re.compile(r'^(?:\d+|[0-9a-fA-F]{32})$')
_FRAME = re.compile(r'^\s*(?:at\s|File\s|\S+@\S+:\d+)')               # Chrome, Python, Firefox


def _dockerenv(): return Path('/.dockerenv').exists()
def _source(): return (Path(__file__).resolve().parent.parent / 'pyproject.toml').exists()


def install_kind() -> str:
    from . import deps
    if deps.frozen(): return 'exe'
    if _dockerenv() or os.environ.get('TASKUARY_HOME') == '/data': return 'docker'
    return 'source' if _source() else 'pip'


def norm_route(route) -> str:
    """Ids out of a route, so two reports of the same bug on different tasks share a fingerprint."""
    path = str(route or '').split('?')[0]
    return '/'.join(':id' if _ID.match(p) else p for p in path.split('/'))


def _brain(store, slot) -> str:
    """A slot's brain as a CLI name or a connector type - never a Name, which can be an account."""
    from . import agents, llm
    v = str(store.get_setting(slot['key']) or '').strip()
    if slot['pick'] == 'agent': v = f"cli:{v or agents.default_agent(store)}" if ':' not in v else v
    st = llm.brain_status(store, v)
    if st.get('Type') != 'cli': return str(st.get('Type') or '')
    row = agents.agent_row(store, str(st.get('pick') or '')[4:]) or {}
    try: prof = json.loads(row.get('Config') or '{}')
    except (TypeError, ValueError): prof = {}
    return f"{agents.cli_of(prof if isinstance(prof, dict) else {}, row.get('Name') or '') or 'unknown'} (cli)"


def _fact(f, default='?'):
    # one unreadable fact must not cost the person the whole report
    try: return f()
    except Exception: return default


def env(store) -> str:
    from . import __version__, aidefaults
    brains = list(dict.fromkeys(b for b in (_fact(lambda s=s: _brain(store, s), '') for s in aidefaults.SLOTS) if b))
    conns = _fact(lambda: sorted({c['Type'] for c in store.list_connectors() if c.get('Active') and c.get('Type')}), [])
    v = sys.version_info
    return (f"Taskuary {__version__} ({_fact(install_kind)}) · {platform.system()} {platform.release()} · Python {v.major}.{v.minor}"
            f" · brains: {', '.join(brains) or 'none'} · connectors: {', '.join(conns) or 'none'}")


def _when(at):
    """The client's ISO time as the log's own clock: loguru stamps local time, a browser sends UTC."""
    try: t = datetime.fromisoformat(str(at).strip().replace('Z', '+00:00'))
    except ValueError: return None
    return t.astimezone().replace(tzinfo=None) if t.tzinfo else t


def log_near(at, n=N_LOG) -> str:
    """The `n` lines ending with the last record stamped at or just before `at` (a traceback rides with its
    record); the newest lines when there is no time. A missing log is '', never an error."""
    try: lines = (config.home() / 'taskuary.log').read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError: return ''
    t, end = _when(at) if at else None, len(lines)
    if t:
        # the server logs a failure before its answer reaches the page, so what the error left is at or before `at`
        cut, stamped = t.strftime('%Y-%m-%d %H:%M:%S'), [i for i, l in enumerate(lines) if _STAMP.match(l)]
        before = [i for i in stamped if _STAMP.match(lines[i]).group(1) <= cut]
        if before: end = next((i for i in stamped if i > before[-1]), len(lines))
        elif stamped: end = min(len(lines), stamped[0] + n)
    return '\n'.join(lines[max(0, end - n):end])


def _etype(err) -> str:
    first = str(err or '').strip().split('\n')[0]
    m = re.match(r'([A-Za-z_][\w.]*)\s*:', first)
    return m.group(1) if m else first[:40]


def _frame(stack) -> str:
    return next((l.strip() for l in str(stack or '').splitlines() if _FRAME.match(l)), '')


def fingerprint(err, route, stack) -> str:
    return hashlib.sha1(f'{_etype(err)}|{norm_route(route)}|{_frame(stack)}'.encode()).hexdigest()[:10]


def collect(store, client: dict) -> dict:
    """The report's facts, unscrubbed: `client` carries screen, route, error, stack, actions and at (ISO)."""
    c = client or {}
    g = lambda k: str(c.get(k) or '').strip()
    err, stack = g('error'), g('stack')
    # a browser stack repeats the message as its first line; Python's does not
    body = '\n'.join(stack.splitlines()[1:] if stack.startswith(err.split('\n')[0]) and err else stack.splitlines())
    acts = c.get('actions') if isinstance(c.get('actions'), list) else []
    return {'where': ' '.join(x for x in (g('screen'), f"({g('route')})" if g('route') else '') if x),
            'error': '\n'.join(x for x in (err, '\n'.join(body.splitlines()[:40])) if x),
            'env': env(store), 'log': log_near(g('at')),
            'actions': [str(a)[:80] for a in acts[-N_ACTIONS:]],
            'fingerprint': fingerprint(err, g('route'), stack)}


# ── scrub ────────────────────────────────────────────────────────────────────────────────────
REMOVED = '[removed]'
SAFE_MSG = 'could not prepare a safe report - copy the error yourself'
OWN_REPO = 'ldbumble/taskuary'


class Unsafe(Exception):
    """The scrub could not finish, so nothing is offered: a half-scrubbed report is worse than none."""


_WIN_HOME = re.compile(r'(?i)\b[a-z]:[\\/]+users[\\/]+[^\\/\s"\'<>:|]+')
_NIX_HOME = re.compile(r'(?<![\w~.])/(?:home|Users)/[^/\s"\'<>:|]+')
_EMAIL = re.compile(r'[\w.+%-]+@[\w-]+(?:\.[\w-]+)+')
_URL = re.compile(r'\b[a-z][a-z0-9+.-]*://[^\s<>"\'`)\]]+', re.I)
_IP = re.compile(r'(?<![\w.])(\d{1,3})\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\w]|\.\d)')
# a dotted word is a hostname only when it ends in a TLD - `taskuary.server:12` and `index-x.js` are code
_HOST = re.compile(r'(?<![\w@.-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:com|net|org|io|dev|ai|app|co|us|uk|de|fr|nl|ca|au|in|eu|'
                   r'biz|info|me|cloud|local|lan|internal|corp|intranet|home|example|test|invalid|localdomain)(?![\w-])', re.I)
_SAFE_HOSTS = {'localhost', 'github.com', 'taskuary.com', 'pypi.org'}
# never a private string, whatever the store says: the report would lose its own address
_SAFE_WORDS = {'taskuary', 'ldbumble', OWN_REPO, 'github', 'github.com', 'taskuary.com', 'localhost', 'the owner'}
_ACCOUNT_KEY = re.compile(r'user|mail|account|login|address|tenant|host|server|owner|org|repo|domain|site|workspace|team|'
                          r'project|name|url|from|path|folder|dir|cwd', re.I)


def to_home(text) -> str:
    """A user folder becomes `~`: the rest of the path says where it broke, the folder says who."""
    return _NIX_HOME.sub('~', _WIN_HOME.sub('~', str(text or '')))


def _safe_host(h) -> bool:
    h = h.lower().rstrip('.')
    return h in _SAFE_HOSTS or any(h.endswith('.' + s) for s in _SAFE_HOSTS)


def _keep_url(u) -> bool:
    m = re.match(r'[^:]+://([^/:?#]+)(?::\d+)?([^?#]*)', u)
    if not m: return False
    host, path = m.group(1).lower(), m.group(2).lower()
    if host in ('localhost', '127.0.0.1', '[::1]') or host.startswith('127.'): return True
    if host in ('taskuary.com', 'www.taskuary.com') or host.endswith('.taskuary.com'): return True
    return host == 'github.com' and (path + '/').startswith(f'/{OWN_REPO}/')


def _ip(m): return m.group(0) if m.group(1) in ('0', '127') else REMOVED      # 0.x.y.z is a version number, not a peer


def _strings(o, key=''):
    """Every string inside a JSON value, with the key it sat under."""
    if isinstance(o, dict):
        for k, v in o.items(): yield from _strings(v, str(k))
    elif isinstance(o, list):
        for v in o: yield from _strings(v, key)
    elif isinstance(o, str): yield key, o


def _json(s):
    try: return json.loads(s) if isinstance(s, str) and s.strip() else (s or {})
    except ValueError: return {}


def _norm(s): return ' '.join(str(s or '').split())
def _head(s): return s[:48].rsplit(' ', 1)[0]           # logs quote a long title by its start


def _add(out: dict, s, lo=4, hi=300):
    s = _norm(s).strip(' .,;:!?-')
    if lo <= len(s) <= hi and re.search(r'[^\W\d_]', s) and s.lower() not in _SAFE_WORDS:
        out.setdefault(s.lower(), s)
        if len(s) > 60 and len(h := _head(s)) >= 24: out.setdefault(h.lower(), h)


def _add_text(out: dict, s):
    """A body is matched by its sentences and lines: no report quotes a whole mail, and a 20 KB needle is all cost."""
    s = str(s or '')
    if len(s) <= 200: _add(out, s)
    # the hot loop of the whole scrub (every sentence of every mail): str methods only, no regex per piece
    for p in s.replace('. ', '.\n').replace('! ', '!\n').replace('? ', '?\n').splitlines():
        p = p.strip(' \t.,;:!?-')
        if 12 <= len(p) <= 200:
            if '  ' in p or '\t' in p: p = _norm(p)
            k = p.lower()
            if k not in out and k not in _SAFE_WORDS:
                out[k] = p
                if len(p) > 60 and len(h := _head(p)) >= 24: out.setdefault(h.lower(), h)


def _add_person(out: dict, s):
    m = re.match(r'\s*"?([^"<]*?)"?\s*<([^>]+)>', str(s or ''))
    for x in ((m.group(1), m.group(2)) if m else (s,)): _add(out, x)


def private_strings(store) -> list:
    """What this store knows that a report must not carry: mail, tasks, people, accounts, repos and checkouts, lower-cased."""
    from . import senders, terminal
    out = {}
    for r in store._rows('SELECT Title, Summary FROM task'): _add(out, r['Title']); _add_text(out, r['Summary'])
    for r in store._rows('SELECT Subject, FromName, FromEmail, RecipientsJson, substr(BodyText, 1, 20000) BodyText, '
                         'substr(OwnText, 1, 20000) OwnText FROM message'):
        for k in ('Subject', 'FromName', 'FromEmail'): _add(out, r[k])
        _add_text(out, r['BodyText']); _add_text(out, r['OwnText'])
        for _, v in _strings(_json(r['RecipientsJson'])): _add_person(out, v)
    for p in store.people(limit=None): _add(out, p.get('Name')); _add(out, p.get('Email'))
    o = store.owner() or {}
    for k in ('owner', 'owner_first', 'owner_email'): _add(out, o.get(k))
    for a in senders.own_addresses(store): _add(out, a)
    for s in store.list_sources(active_only=False): _add(out, s.get('Address'))
    for c in store.list_connectors():
        _add(out, c.get('Name'))
        for k, v in _strings(_json(c.get('ConfigJson'))):
            if _ACCOUNT_KEY.search(k): _add(out, v); _add(out, to_home(v))
    for r in terminal.known_repos(store, agent='coder'):
        if str(r).lower() != OWN_REPO: _add(out, r)
    for a in store.list_agents(active_only=False):
        prof = _json(a.get('Config'))
        if not isinstance(prof, dict): continue
        cm = prof.get('cwd_map') if isinstance(prof.get('cwd_map'), dict) else {}
        for p in [*cm, *(str(v) for v in cm.values()), str(prof.get('cwd') or '')]:
            if str(p).lower() != OWN_REPO: _add(out, p); _add(out, to_home(p))
    return list(out)                      # lower-cased, as the match reads them; _clean orders the hits


def _present(cands, text) -> list:
    """The candidates the text holds. An interior word of a candidate is a whole word of the text too, so a set
    lookup rules most of ten thousand mails out before any substring search runs."""
    low = _norm(text).lower()
    words = set(low.split())
    return [c for c in cands if words.issuperset(c.split()[1:-1]) and c in low]


def _clean(text, cands) -> str:
    from . import redact
    out = to_home(redact.scrub(text))
    # every hit's spans, merged: one alternation would let "X Y" win over an overlapping "Y Z" and leave "Z" behind
    spans = sorted(m.span() for h in _present(cands, out) for m in re.finditer(r'\s+'.join(map(re.escape, h.split())), out, re.I))
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], b)
        else: merged.append([a, b])
    for a, b in reversed(merged): out = out[:a] + REMOVED + out[b:]
    out = _EMAIL.sub(REMOVED, out)
    out = _URL.sub(lambda m: m.group(0) if _keep_url(m.group(0)) else REMOVED, out)
    out = _IP.sub(_ip, out)
    return _HOST.sub(lambda m: m.group(0) if _safe_host(m.group(0)) else REMOVED, out)


def scrub(text: str, store, known: list = None) -> str:
    """`text` with credentials, mail, names, task text, repos, user folders, addresses and hosts taken out.
    `known` is `private_strings(store)`, for a caller scrubbing many strings against one lookup. Fails closed."""
    try: return _clean(text, private_strings(store) if known is None else known)
    except Exception as e: raise Unsafe(SAFE_MSG) from e


# ── draft ────────────────────────────────────────────────────────────────────────────────────
NO_ERROR = 'Something is wrong'
SYSTEM = ('You write a bug report for a public GitHub tracker from the facts given and nothing else. Answer JSON: '
          '"title" - a GitHub issue title, under 80 characters; "explanation" - two or three plain sentences: what '
          'the person was doing, what happened, what they expected. Use only these facts: never guess or invent '
          'names, people, companies or details, and leave [removed] parts out rather than filling them in.')
WANT = {'type': 'object', 'properties': {'title': {'type': 'string'}, 'explanation': {'type': 'string'}},
        'required': ['title', 'explanation']}


def _ask(store, brain, f) -> dict:
    """The model's title and explanation, or {} - a draft without them is still a report."""
    from . import llm as ai
    try:
        brain = brain or ai.build_llm(store, gear='light')
        if not brain: return {}
        user = '\n'.join([f"Where: {f['where'] or 'unknown'}", f"Recent actions: {', '.join(f['actions']) or 'none'}",
                          f"Error:\n{f['error'] or 'none reported'}", f"Environment: {f['env']}", f"Log lines:\n{f['log'][-3000:]}"])
        d = ai.ask_json(brain, SYSTEM, user, want=WANT, max_tokens=300).data
        return d if isinstance(d, dict) else {}
    except Exception: return {}


def draft(store, client: dict, llm=None) -> dict:
    """The report the popup shows: {title, explanation, where, error, env, log, actions, fingerprint}, every string
    scrubbed. The model is handed the scrubbed facts only, and its answer is scrubbed again. Raises Unsafe."""
    raw = collect(store, client)
    try: known = private_strings(store)
    except Exception as e: raise Unsafe(SAFE_MSG) from e
    S = lambda t: scrub(t, store, known)
    f = {**{k: S(v) for k, v in raw.items() if k != 'actions'}, 'actions': [S(a) for a in raw['actions']]}
    d = _ask(store, llm, f)
    first = next((l.strip() for l in f['error'].splitlines() if l.strip()), '') or NO_ERROR
    title = _norm(S(_norm(d.get('title'))))[:80] or first[:80]
    return {'title': title, 'explanation': S(str(d.get('explanation') or '').strip()), **f}
