"""Report a bug from where it happened: the facts, scrubbed, and a draft the person checks.

The tracker (`ldbumble/taskuary`) is PUBLIC, and this app reads one person's mail. So the facts are
gathered by code - where, the error, versions, the log around it, action names - never by a model
that might reach for a task title, and every string is scrubbed before the person sees the draft.
Nothing leaves from here: the popup shows the text and the person presses Submit on GitHub.
"""
import hashlib, html, json, os, platform, posixpath, re, sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

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
    if slot['pick'] == 'cli': v = f"cli:{v or agents.default_brain(store)}" if ':' not in v else v
    st = llm.brain_status(store, v)
    if st.get('Type') != 'cli': return str(st.get('Type') or '')
    key = str(st.get('pick') or '')[4:]
    row = agents.agent_row(store, key) or {}
    try: prof = json.loads(row.get('Config') or '{}')
    except (TypeError, ValueError): prof = {}
    return f"{agents.cli_of(prof if isinstance(prof, dict) else {}, row.get('Name') or key) or 'unknown'} (cli)"


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
    try:
        t = datetime.fromisoformat(str(at).strip().replace('Z', '+00:00'))
        return t.astimezone().replace(tzinfo=None) if t.tzinfo else t
    except (ValueError, OverflowError, OSError): return None


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


# a user name runs to the next separator, spaces and all ("C:\Users\Jordan Smith\AppData"); with none after it, to a space
_UNAME = r'(?:[^\\/\s"\'<>:|]+(?: [^\\/\s"\'<>:|]+)*(?=[\\/])|[^\\/\s"\'<>:|]+)'
_WIN_HOME = re.compile(r'(?i)\b[a-z]:[\\/]+users[\\/]+' + _UNAME)
_NIX_HOME = re.compile(r'(?<![\w~.])(?:/mnt/[a-z]|/[a-z])?/(?:home|Users)/' + _UNAME)      # Linux, macOS, Git Bash, WSL
# a path a quote opened is closed by the quote: "'C:\Users\Pat Lee'" - but only then, or a later quote eats the sentence
_QUOTED_HOME = re.compile(r'(?i)(?<=["\'])(?:[a-z]:[\\/]+users[\\/]+|(?:/mnt/[a-z]|/[a-z])?/(?:home|Users)/)[^\\/"\'<>:|\r\n]{1,64}(?=["\'])')
_EMAIL = re.compile(r'[\w.+%-]+@[\w-]+(?:\.[\w-]+)+')
_URL = re.compile(r'\b[a-z][a-z0-9+.-]*://[^\s<>"\'`)\[\]]+', re.I)      # `[` too: a `[removed]` ends a URL
_GH_HOST = r'(?:[\w-]+\.)*github(?:usercontent)?\.com'
# before the email rule: `git@github.com:org/repo` is a repo, and the email rule would leave `org/repo` behind
_GH = re.compile(r'(?<![\w.-])(' + _GH_HOST + r')[:/]+([\w.-]+/[\w.-]+[^\s<>"\'`)\[\]]*)', re.I)
_IP = re.compile(r'(?<![\w.])(\d{1,3})\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\w]|\.\d)')
_IP6 = re.compile(r'\[[0-9a-f:]*:[0-9a-f:]*\](?::\d+)?|(?<![\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![\w:])', re.I)
_UNC = re.compile(r'(?<![\w\\~])\\\\[^\\\s]+\\[^\\\s]+')
_HOST = re.compile(r'(?<![\w@.-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+([a-z][a-z0-9-]*)(?![\w-]|\.\w)', re.I)
# what makes a dotted word a machine by where it sits: a port, an @, a // or \\ before it, or a word that says so
_HOST_AFTER = re.compile(r':\d+')
_HOST_BEFORE = re.compile(r'(?:@|//|\\\\|(?i:\b(?:host|server|smtp|imap)\s*[=:]?\s*))$')
# ...and by its shape alone only when it ends like an address does: `t.render`, `cfg.store` and `Promise.all` are code
_TLDS = set('com net org io dev app ai co me info biz edu gov mil int uk de fr ch nl be at se no dk fi es it pt ie pl cz ru ua il in '
            'jp cn kr au nz ca us mx br ar za sg hk tw local lan internal corp home intranet example test invalid health cloud '
            'tech online site xyz email'.split())
# a dotted word ending like a file, or starting like a package, is code - `index-x.js:10`, `taskuary.server:12`
_CODE_SUFFIX = set('js py css json ts tsx jsx mjs cjs log md toml yml yaml txt html htm exe dll so cfg ini lock map server pyc pyd '
                   'pdf png jpg jpeg gif svg ico csv xlsx xls docx doc pptx zip gz tar whl sh ps1 bat cmd db sqlite xml env tmp bak '
                   'wasm woff woff2 ttf vue scss less sql jsonl ipynb mp4 webm wav mp3 sock pid conf'.split())
_CODE_HEAD = set('taskuary self this window document os sys json re e err error console math np pd asyncio uvicorn starlette '
                 'fastapi sqlalchemy requests urllib3 sqlite3 http urllib pathlib subprocess threading react node'.split())
_SAFE_HOSTS = {'localhost', 'github.com', 'taskuary.com', 'pypi.org'}
# never a private string, whatever the store says: the report would lose its own address
_SAFE_WORDS = {'taskuary', 'ldbumble', OWN_REPO, 'github', 'github.com', 'taskuary.com', 'localhost', 'the owner', REMOVED}
# a login this generic names no one, and taking it out would eat the word wherever it appears
_GENERIC_LOGINS = {'user', 'users', 'admin', 'administrator', 'root', 'owner', 'default', 'public', 'guest', 'runner', 'localhost', 'home'}
_ACCOUNT_KEY = re.compile(r'user|mail|account|login|address|tenant|host|server|owner|org|repo|domain|site|workspace|team|'
                          r'project|name|url|from|path|folder|dir|cwd|token|secret|password|key', re.I)
_SEP = re.compile(r'[_-]')
_ESC = re.compile(r'\\+u([0-9a-fA-F]{4})|\\+x([0-9a-fA-F]{2})')         # `\\u0020`: an escape inside an escaped string
_JOINERS = re.compile('[\u200c\u200d\u2060\ufeff]')


def _home_dirs() -> list: return [str(_fact(Path.home, ''))]


def _own_homes(text) -> str:
    """This machine's home folder in every spelling a log or a shell gives it, before the generic rule: the generic rule
    cannot know that "C:\\Users\\Jordan Smith said" ends at "Smith", and this one can."""
    forms = set()
    for h in (h for h in _home_dirs() if len(h) > 3):
        fwd = h.replace('\\', '/')
        forms |= {h, fwd, h.replace('\\', '\\\\')}
        if re.match(r'[A-Za-z]:/', fwd): forms |= {f'/{fwd[0].lower()}{fwd[2:]}', f'/mnt/{fwd[0].lower()}{fwd[2:]}'}
    for f in sorted(forms, key=len, reverse=True):
        text = re.sub(re.escape(f) + r'(?![^\\/\s"\'<>:|])', '~', text, flags=re.I)
    return text


def to_home(text) -> str:
    """A user folder becomes `~`: the rest of the path says where it broke, the folder says who."""
    return _NIX_HOME.sub('~', _WIN_HOME.sub('~', _QUOTED_HOME.sub('~', _own_homes(str(text or '')))))


def _safe_host(h) -> bool:
    h = h.lower().rstrip('.')
    return h in _SAFE_HOSTS or any(h.endswith('.' + s) for s in _SAFE_HOSTS)


def _own_repo_path(host, path) -> bool:
    """Is this GitHub path ldbumble/taskuary - after `..`, any case, `.git`, and the API's `/repos` prefix?"""
    p = posixpath.normpath('/' + path.lower().lstrip('/'))
    if host.lower().startswith('api.'): p = re.sub(r'^/repos(?=/)', '', p)
    return bool(re.match(rf'/{OWN_REPO}(?:\.git)?(?:/|$)', p))


def _keep_url(u) -> bool:
    m = re.match(r'[^:]+://([^/:?#]+)(?::\d+)?([^?#]*)', u)
    if not m: return False
    host, path = m.group(1).lower(), m.group(2)
    if host in ('localhost', '127.0.0.1', '[::1]') or host.startswith('127.'): return True
    if host in ('taskuary.com', 'www.taskuary.com') or host.endswith('.taskuary.com'): return True
    return bool(re.fullmatch(_GH_HOST, host)) and _own_repo_path(host, path)


def _url(m):
    """A kept URL loses its query: `?q=` is where a search for a person's name sits."""
    u = m.group(0)
    return re.sub(r'\?[^#]*', '', u) if _keep_url(u) else REMOVED


def _gh(m): return m.group(0) if _own_repo_path(m.group(1), m.group(2)) else REMOVED


def _ip6(m):
    t = m.group(0)
    bare = re.sub(r'^\[(.*)\](?::\d+)?$', r'\1', t)
    return REMOVED if ('::' in bare or bare.count(':') >= 3) and re.search(r'[0-9a-f]{3,4}', bare, re.I) and bare != '::1' else t


def _host(m):
    t, last = m.group(0), m.group(1)
    if _safe_host(t) or t.split('.')[0].lower() in _CODE_HEAD or last.lower() in _CODE_SUFFIX: return t
    # a CamelCase last label is a member or a class (`HTMLButtonElement.onClick`, `exc.OperationalError`); a host's is
    # one case throughout or capitalised, whatever the rest of it is (`Mail.Northwind.com`, `MAIL.NORTHWIND.COM`, `x.Com`)
    if any(c.isupper() for c in last[1:]) and any(c.islower() for c in last): return t
    s, e = m.span()
    before, after = m.string[max(0, s - 12):s], m.string[e:e + 8]
    if _HOST_AFTER.match(after) or _HOST_BEFORE.search(before): return REMOVED
    if after.startswith('('): return t
    return REMOVED if last.lower() in _TLDS else t


def _unescape(t) -> str:
    """The text as a person reads it: `%20`, `%2520`, `\\u0040`, `&#32;` and `+` between letters are how a name hides
    in a URL or a log - decoded until nothing changes, because one layer of decoding uncovers the next."""
    for _ in range(5):
        u = unquote(html.unescape(_ESC.sub(lambda m: c if (c := chr(int(m.group(1) or m.group(2), 16))).isprintable() else m.group(0), t)))
        if u == t: break
        t = u
    # a joiner hides inside a word and goes; a zero-width SPACE stands between two, so it reads as one
    t = _JOINERS.sub('', t).replace('\u200b', ' ').replace('\u00a0', ' ')
    return re.sub(r'(?<=[^\W\d_]{2})\+(?=[^\W\d_]{2})', ' ', t)


def _rules(t) -> str:
    """Everything matched by shape: repos, URLs, addresses, IPs, shares and hosts."""
    t = _URL.sub(_url, _GH.sub(_gh, t))
    t = _IP6.sub(_ip6, _IP.sub(_ip, _EMAIL.sub(REMOVED, t)))
    return _HOST.sub(_host, _UNC.sub(REMOVED, t))


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


def _key(s): return _norm(_SEP.sub(' ', s.lower()))     # `_` and `-` are spaces: `Renew_the_Payworth_contract.pdf`


def _add(out: dict, s, lo=4, hi=300):
    s = _norm(s).strip(' .,;:!?-')
    if lo <= len(s) <= hi and re.search(r'[^\W\d_]', s) and s.lower() not in _SAFE_WORDS:
        out.setdefault(_key(s), s)
        if len(s) > 60 and len(h := _head(s)) >= 24: out.setdefault(_key(h), h)


def _add_name(out: dict, s):
    """A person by full name and by first name - "Hi Erin," names her as well as "Erin Blake" does."""
    _add(out, s)
    ws = _norm(s).split()
    if len(ws) > 1 and len(f := ws[0].strip(',.;:"\'')) >= 4 and f.isalpha(): _add(out, f)


def _add_text(out: dict, s):
    """A body is matched by its sentences and lines: no report quotes a whole mail, and a 20 KB needle is all cost."""
    s = str(s or '')
    if len(s) <= 200: _add(out, s)
    # the hot loop of the whole scrub (every sentence of every mail): str methods only, no regex per piece
    for p in s.replace('. ', '.\n').replace('! ', '!\n').replace('? ', '?\n').splitlines():
        p = p.strip(' \t.,;:!?-')
        if 12 <= len(p) <= 200:
            k = p.lower()
            if '_' in k or '-' in k or '  ' in k or '\t' in k: k = _key(k)
            if k not in out and k not in _SAFE_WORDS:
                out[k] = p
                if len(p) > 60 and len(h := _head(p)) >= 24: out.setdefault(h.lower(), h)


def _add_person(out: dict, s):
    m = re.match(r'\s*"?([^"<]*?)"?\s*<([^>]+)>', str(s or ''))
    if m: _add_name(out, m.group(1)); _add(out, m.group(2))
    else: _add_name(out, s)


def _catalogue() -> set:
    from . import connectorcatalog
    return {str(w).lower() for c in connectorcatalog.cards() for w in [c.get('type'), c.get('title'), *(c.get('match') or [])] if w}


def _machine() -> list:
    """This computer's own names: the login, the host, the home folder - in a path outside the Users folder, or a log line."""
    import getpass, socket
    fs = [lambda: Path.home().name, getpass.getuser, socket.gethostname, lambda: str(Path.home()), lambda: str(config.home())]
    return [str(v) for v in (_fact(f, '') for f in fs) if v]


def private_strings(store) -> list:
    """What this store knows that a report must not carry: mail, tasks, people, accounts, repos and checkouts, lower-cased."""
    from . import senders, terminal
    out = {}
    for r in store._rows('SELECT Title, Summary FROM task'): _add(out, r['Title']); _add_text(out, r['Summary'])
    for r in store._rows('SELECT Subject, FromName, FromEmail, RecipientsJson, substr(BodyText, 1, 20000) BodyText, '
                         'substr(OwnText, 1, 20000) OwnText FROM message'):
        _add(out, r['Subject']); _add_name(out, r['FromName']); _add(out, r['FromEmail'])
        _add_text(out, r['BodyText']); _add_text(out, r['OwnText'])
        for _, v in _strings(_json(r['RecipientsJson'])): _add_person(out, v)
    for p in store.people(limit=None): _add_name(out, p.get('Name')); _add(out, p.get('Email'))
    o = store.owner() or {}
    for k in ('owner', 'owner_first', 'owner_email'): _add(out, o.get(k))
    for a in senders.own_addresses(store): _add(out, a)
    for s in store.list_sources(active_only=False): _add(out, s.get('Address'))
    # a connector named after its own kind ("jira") is the catalogue talking, and the env line says the same word
    cat = _fact(_catalogue, set()) | {str(c.get('Type') or '').lower() for c in store.list_connectors()}
    for c in store.list_connectors():
        vals = [c.get('Name')] + [v for k, v in _strings(_json(c.get('ConfigJson'))) if _ACCOUNT_KEY.search(k)]
        for v in vals:
            if str(v or '').strip().lower() not in cat: _add(out, v); _add(out, to_home(v))
    for r in terminal.known_repos(store):
        if str(r).lower() != OWN_REPO: _add(out, r)
    for a in store.list_agents(active_only=False):
        prof = _json(a.get('Config'))
        if not isinstance(prof, dict): continue
        cm = prof.get('cwd_map') if isinstance(prof.get('cwd_map'), dict) else {}
        for p in [*cm, *(str(v) for v in cm.values()), str(prof.get('cwd') or '')]:
            if str(p).lower() != OWN_REPO: _add(out, p); _add(out, to_home(p))
    for m in _machine():
        if m.lower() not in _GENERIC_LOGINS: _add(out, m)
    # a subject that holds an address meets the text after the address rule took it out: match it in that form too
    for k in [k for k in out if '@' in k or '://' in k]:
        if (r := _rules(k)).strip() != REMOVED: _add(out, r)
    return list(out)                      # lower-cased, as the match reads them; _clean orders the hits


def _present(cands, text) -> list:
    """The candidates the text holds. An interior word of a candidate is a whole word of the text too, so a set
    lookup rules most of ten thousand mails out before any substring search runs."""
    low = _key(text)
    words = set(low.split())
    return [c for c in cands if words.issuperset(c.split()[1:-1]) and c in low]


def _pattern(h) -> str:
    p = r'[\s_-]+'.join(map(re.escape, h.split()))
    return rf'(?<![^\W_]){p}(?![^\W_])' if len(h) < 12 else p     # a short one is a whole word: not `Mark` in `markdown`


def _clean(text, cands) -> str:
    from . import redact
    # URLs first while their queries are still encoded; then every shape rule once decoding is done, and only then
    # the store's strings - a host goes whole, not as `acmecorp.[removed].com`
    out = _URL.sub(_url, _GH.sub(_gh, to_home(redact.scrub(text))))
    out = _rules(to_home(_unescape(out)))
    # every hit's spans, merged: one alternation would let "X Y" win over an overlapping "Y Z" and leave "Z" behind
    spans = sorted(m.span() for h in _present(cands, out) for m in re.finditer(_pattern(h), out, re.I))
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], b)
        else: merged.append([a, b])
    for a, b in reversed(merged): out = out[:a] + REMOVED + out[b:]
    return out


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
        brain = brain or ai.build_llm(store, gear='light', job='summary')
        if not brain: return {}
        user = '\n'.join([f"Where: {f['where'] or 'unknown'}", f"Recent actions: {', '.join(f['actions']) or 'none'}",
                          f"Error:\n{f['error'] or 'none reported'}", f"Environment: {f['env']}", f"Log lines:\n{f['log'][-3000:]}"])
        d = ai.ask_json(brain, SYSTEM, user, want=WANT, max_tokens=300).data
        return d if isinstance(d, dict) else {}
    except Exception: return {}


def _cut(s, n=80) -> str:
    """At most `n` characters, never ending inside a `[removed]` or `[redacted:..]` marker."""
    t = s[:n]
    i = t.rfind('[')
    return (t[:i] if i >= 0 and ']' not in t[i:] and len(s) > n else t).rstrip()


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
    title = _cut(_norm(S(_norm(d.get('title'))))) or _cut(first)
    return {'title': title, 'explanation': S(str(d.get('explanation') or '').strip()), **f}
