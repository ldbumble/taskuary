"""Reason Network: teammates' coding agents messaging the owner's - and only the ones the owner trusts.

Reason Network (github.com/reason-machines/reason-network) is a daemon per computer that the OWNER installs and keeps
up to date himself; Taskuary never ships, pins or installs it. It is found at run time (PATH, ~/.local/bin,
~/.reason/bin), spoken to only through its own CLI, and every answer is read defensively: a version that lacks a
command or a flag, or answers in a shape not read here, is said in plain words (Unsupported), never a crash.

WHAT REASON DOES (its README and DESIGN.md, read 2026-10-21): every agent session on every teammate's computer is listed
(`who --json`), and any of them can message one (`send_message` over MCP, `reason-network send` from a shell). A message
lands in the session it is for - Claude Code mid-turn through its own messaging socket, Codex/Cursor/Gemini through
hooks - framed `<reason-message from="person/session" id="...">text</reason-message>`, its text defanged so it can never
close or forge that frame. Small text files ride along and are saved under ~/.reason/network/inbox. `ask_user` puts a
pop-up in front of the session's own person. Each computer has an INBOUND POLICY in its config.toml - `accept`, `hold`
(kept until `reason-network approve <id>`; `held` lists them) or `refuse` - with a default and one entry per person.

WHAT TAKES THE OWNER'S TRUST, AND HOW FAR IT REACHES
- Enforced by Reason itself, Taskuary running or not: with the gate on (apply_gate) the default is `hold`, every fully
  trusted person - and the owner - is `accept`, and the owner's own `refuse` entries stay. Nobody else's message reaches
  ANY agent session on this computer, Taskuary's or the owner's own, until approved. Reason's policy is per PERSON.
- Enforced by Taskuary while it runs: a trust that names one SESSION (erin/api-claude) leaves that person on `hold`, and
  the poll approves only that session's held messages - stopped, they stay held (fail closed). Everything else held
  becomes an owner task (never delivered) to deliver or drop from the card.
- Enforced by Taskuary's PreToolUse hook in its own Claude sessions while it runs: `send_message` to someone untrusted is
  refused, a trusted one is logged on the task, and `ask_user` is the owner's approval card on the task instead of
  Reason's pop-up. A shell `reason-network send` from an agent, another CLI, or Taskuary down (the hook's curl fails
  open) are not caught there - the receiving side's own policy is what holds then.
- Seen, not enforced: messages an agent of ours is shown are put on its task as a note (the transcript and check_inbox),
  scrubbed and fenced. Notes are what the owner reads; nothing is delivered on their account.
"""
import json, os, re, subprocess, threading, time
try: import tomllib
except ImportError: import tomli as tomllib  # py3.10
from pathlib import Path
from loguru import logger

TYPE = 'reason_network'
EXE = 'reason-network'
DOCS = 'https://github.com/reason-machines/reason-network#readme'
TOOL = 'mcp__reason-network__'                  # its MCP server's name, as Claude prefixes the tools
LISTENER = 'taskuary'                           # the session Taskuary asks from: <owner>/taskuary, where replies land
ACTOR = 'reason-network'
POLL_EVERY = 10
_ULID = re.compile(r'^[0-9A-HJKMNP-TV-Z]{26}$')
_NAME = r'[A-Za-z0-9][A-Za-z0-9._-]*'
_ADDR = re.compile(rf'^{_NAME}(?:/{_NAME})?(?:@{_NAME})?$')
# Agent sessions' own variables: Taskuary may run under one, and Reason reads them as "an agent's shell is sending"
_AGENT_ENV = ('CLAUDECODE', 'CLAUDE_CODE_', 'CODEX_', 'CURSOR_', 'GEMINI_CLI', 'GEMINI_SESSION', 'COPILOT_', 'OPENCODE',
              'GROK_SESSION', 'AI_AGENT', 'REASON_NETWORK_SESSION', 'REASON_NETWORK_AGENT')


class Unsupported(RuntimeError):
    "The Reason Network installed here cannot do this (an older or newer version): said, never a crash."


class NotInstalled(RuntimeError): pass


# ── finding it ───────────────────────────────────────────────────────────────────────────────────
def home() -> Path: return Path(os.environ.get('REASON_NETWORK_HOME') or Path.home() / '.reason' / 'network')


def exe() -> str | None:
    "Where the owner's own reason-network is: PATH first, then where its installers put it."
    from . import pathcache
    if hit := pathcache.which(EXE): return hit
    ext = '.exe' if os.name == 'nt' else ''
    return next((str(p) for d in (Path.home() / '.local' / 'bin', Path.home() / '.reason' / 'bin') if (p := d / f'{EXE}{ext}').is_file()), None)


def argv() -> list | None:
    p = exe()
    if not p: return None
    return ['cmd', '/c', p] if p.lower().endswith(('.cmd', '.bat')) else [p]


def detect() -> dict:
    p = exe()
    return {'installed': bool(p), 'path': p, 'home': str(home()), 'state': home().is_dir(), 'docs': DOCS}


def _env() -> dict:
    return {k: v for k, v in os.environ.items() if not k.upper().startswith(_AGENT_ENV)}


def run(args: list, text: str = None, timeout: float = 30) -> subprocess.CompletedProcess:
    a = argv()
    if not a: raise NotInstalled("Reason Network isn't installed on this computer")
    from . import spawn
    kw = {'input': text} if text is not None else {'stdin': subprocess.DEVNULL}
    return spawn.run(a + [str(x) for x in args], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout,
                     env=_env(), cwd=str(Path.home()), **kw)


def _said(r) -> str:
    "What a failed command said, in one line - its JSON error when it gave one."
    raw = ((r.stdout or '').strip() + '\n' + (r.stderr or '').strip()).strip()
    try: raw = str(json.loads(r.stdout).get('error') or raw)
    except (ValueError, TypeError, AttributeError): pass
    return ' '.join(raw.split())[:300] or f'it stopped with code {r.returncode}'


def _ok(r, what: str) -> str:
    if r.returncode != 0: raise RuntimeError(f'Reason Network could not {what}: {_said(r)}')
    return r.stdout or ''


_HELP, _HELP_LOCK = {}, threading.Lock()


def help_text(sub: str = '') -> str:
    "`--help`, once per install and subcommand: what this version can do."
    key = (tuple(argv() or ()), sub)
    with _HELP_LOCK:
        if key not in _HELP:
            try:
                r = run([sub, '--help'] if sub else ['--help'], timeout=15)
                _HELP[key] = (r.stdout or '') + (r.stderr or '')
            except (OSError, subprocess.SubprocessError, NotInstalled): _HELP[key] = ''
        return _HELP[key]


def forget():
    "A new install or update: ask it again what it can do."
    with _HELP_LOCK: _HELP.clear()
    from . import pathcache
    pathcache.forget()


def has(sub: str, flag: str = None) -> bool:
    if flag: return flag in help_text(sub)
    return bool(re.search(rf'^\s+{re.escape(sub)}\b', help_text(), re.M))


def need(sub: str, flag: str = None, what: str = ''):
    if not has(sub, flag):
        raise Unsupported(f"This Reason Network version doesn't support {what or ' '.join(x for x in (sub, flag) if x)} - update it "
                          f"from its own instructions ({DOCS}).")


# ── what it says ─────────────────────────────────────────────────────────────────────────────────
def _s(v) -> str: return v if isinstance(v, str) else ''


def who() -> dict:
    "The team: people, their computers and live sessions, from `who --json` - any field it lacks is simply left empty."
    need('who', '--json', 'listing the team as JSON (`who --json`)')
    out = _ok(run(['who', '--json']), 'list the team')
    try: d = json.loads(out)
    except ValueError: d = None
    if not isinstance(d, dict) or 'error' in d:
        if isinstance(d, dict): raise RuntimeError(f"Reason Network could not list the team: {_s(d.get('error'))[:300]}")
        raise Unsupported("This Reason Network version answered `who --json` in a shape Taskuary doesn't read - update Taskuary or "
                          "Reason Network.")
    sess = [{'address': _s(s.get('address')) or f"{_s(s.get('person'))}/{_s(s.get('name'))}", 'person': _s(s.get('person')),
             'name': _s(s.get('name')), 'agent': _s(s.get('agent')), 'repo': _s(s.get('repo')), 'branch': _s(s.get('branch')),
             'status': _s(s.get('status')), 'doing': _s(s.get('doing')), 'cwd': _s(s.get('cwd')), 'is_me': s.get('is_me') is True}
            for s in (d.get('sessions') if isinstance(d.get('sessions'), list) else []) if isinstance(s, dict)]
    machines = [m for m in (d.get('machines') if isinstance(d.get('machines'), list) else []) if isinstance(m, dict)]
    me = _s(d.get('person'))
    people = {}
    for m in machines:
        p = people.setdefault(_s(m.get('person')), {'person': _s(m.get('person')), 'online': False, 'verified': False, 'me': False})
        p['online'] |= m.get('online') is True; p['verified'] |= m.get('verified') is True
    for s in sess: people.setdefault(s['person'], {'person': s['person'], 'online': True, 'verified': False, 'me': False})
    for p in people.values(): p['me'] = bool(me) and p['person'] == me
    return {'team': _s(d.get('team')), 'person': me, 'machine': _s(d.get('machine')), 'sessions': [s for s in sess if s['person']],
            'people': sorted((p for p in people.values() if p['person']), key=lambda p: (not p['me'], p['person']))}


_HEAD = re.compile(r'^── (?P<from>\S+?)(?: \((?P<meta>[^)\n]*)\))? · .*? · (?P<id>[0-9A-Z]{26})\s*$')


def parse_held(text: str) -> list:
    """`held` as it prints for a reader that is not a person. A teammate's text may contain a line shaped like a header,
    so an id met twice - or with two senders - is AMBIGUOUS, and an ambiguous message is never approved on anyone's trust."""
    out, cur = [], None
    for line in str(text or '').splitlines():
        m = _HEAD.match(line)
        if m:
            meta = [x.strip() for x in (m.group('meta') or '').split(',') if x.strip()]
            cur = {'id': m.group('id'), 'from': m.group('from'), 'agent': meta[0] if meta else '', 'body': [], 'files': []}
            out.append(cur); continue
        if cur is None or line.startswith('`'): continue
        if line.startswith('  file: '): cur['files'].append(line[8:].strip())
        else: cur['body'].append(line)
    seen = {}
    for m in out: seen.setdefault(m['id'], set()).add(m['from'])
    return [{**m, 'body': '\n'.join(m['body']).strip(), 'ambiguous': len(seen[m['id']]) > 1 or [x['id'] for x in out].count(m['id']) > 1}
            for m in out]


def held() -> list:
    "Messages Reason holds for the owner's approval (inbound `hold`)."
    need('held', what='holding messages for approval (`held`)')
    if has('held', '--json'):
        try:
            rows = json.loads(_ok(run(['held', '--json']), 'list held messages'))
            return [{'id': _s(m.get('id')), 'from': _s(m.get('from')), 'agent': _s(m.get('from_agent')), 'to': _s(m.get('to')),
                     'body': _s(m.get('body')).strip(), 'ambiguous': False,
                     'files': [_s(f.get('path')) or _s(f.get('name')) for f in m.get('files') or [] if isinstance(f, dict)]}
                    for m in rows if isinstance(m, dict) and _s(m.get('id'))]
        except (ValueError, TypeError, AttributeError): pass                  # a shape we don't read: the text below still is
    return parse_held(_ok(run(['held']), 'list held messages'))


def settle(ids: list, deliver: bool) -> str:
    ids = [i for i in ids if _ULID.match(str(i))]
    if not ids: raise ValueError('no message to settle')
    sub = 'approve' if deliver else 'reject'
    need(sub, what=f'{"delivering" if deliver else "dropping"} held messages (`{sub}`)')
    return _ok(run([sub, *ids]), f'{"deliver" if deliver else "drop"} the held message').strip()


_FRAME = re.compile(r'<reason-(?P<kind>message|approval) (?P<attrs>[^>\n]*)>\n?(?P<body>.*?)\n?</reason-(?P=kind)>', re.S)
_FILES = re.compile(r'^Files they sent with (\S+?)\b.*?:\n((?:- .*\n?)+)', re.M)


def parse_frames(text: str) -> list:
    "Every framed message in what an agent (or `listen`) was shown: sender, id, text, the files listed after it."
    text = str(text or '')
    files = {m.group(1): [x[2:].strip() for x in m.group(2).splitlines() if x.startswith('- ')] for m in _FILES.finditer(text)}
    out = []
    for m in _FRAME.finditer(text):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group('attrs')))
        mid = a.get('id') or a.get('about') or ''
        if not a.get('from'): continue
        out.append({'id': a.get('id', ''), 'about': a.get('about', ''), 'from': a['from'], 'agent': a.get('agent', ''),
                    'reply_to': a.get('reply_to', ''), 'approval': m.group('kind') == 'approval', 'body': m.group('body').strip(),
                    'files': files.get(mid, [])})
    return out


def listen() -> list:
    "Replies to what Taskuary asked, waiting at <owner>/taskuary. `listen --wait 0` also keeps that session registered."
    need('listen', '--wait', 'reading replies without waiting (`listen --wait`)')
    return parse_frames(_ok(run(['listen', '--as', LISTENER, '--wait', '0']), 'read replies'))


def send(to: str, text: str, me: str, store=None) -> dict:
    "One message from <owner>/taskuary to one session. The text goes on stdin: a message starting with a dash is still a message."
    need('send', '--from', 'sending as a named session (`send --from`)')
    # `listen` first: it registers the session we send from - and a reply already waiting is filed, never lost
    if store is not None: note_replies(store)
    else: listen()
    out = _ok(run(['send', to, '--from', f'{me}/{LISTENER}'], text=text), f'send to {to}')
    m = re.search(r'message id (\S+)', out)
    notes = [ln.split(':', 1)[1].strip() for ln in out.splitlines() if ln.startswith('→') and ':' in ln]
    return {'id': m.group(1) if m else '', 'to': to, 'note': '; '.join(notes)[:300]}


def folder(path: str, off: bool) -> str:
    need('folder', what='keeping a folder off the network (`folder`)')
    if not str(path or '').strip(): raise ValueError('which folder?')
    return _ok(run(['folder', str(path), 'off' if off else 'on']), f'turn the network {"off" if off else "on"} for {path}').strip()


# ── trust ────────────────────────────────────────────────────────────────────────────────────────
def _n(x) -> str: return str(x or '').strip().lower()


def clean_trusted(items) -> list:
    "People (erin) and single sessions (erin/api-claude): no groups, no stars, each once."
    out = []
    for x in items if isinstance(items, (list, tuple)) else str(items or '').replace(',', '\n').splitlines():
        x = _n(x).split('@')[0]
        if x and _ADDR.match(x) and x not in out: out.append(x)
    return out


def is_trusted(addr: str, trusted: list, me: str = '') -> bool:
    a = _n(addr).split('@')[0]
    person = a.split('/')[0]
    if not person or '*' in a or a.startswith('repo:'): return False
    t = set(clean_trusted(trusted))
    return (bool(me) and person == _n(me)) or person in t or a in t


def policy(trusted: list, me: str = '', keep: dict = None) -> dict:
    """Reason's inbound policy for this trust: hold by default, accept the owner and every fully trusted person. A person
    trusted for some sessions only stays on hold - those sessions are approved by the poll. The owner's own refusals stay."""
    t = clean_trusted(trusted)
    people = {k: v for k, v in (keep or {}).items() if v == 'refuse'}
    for p in [x for x in t if '/' not in x] + ([_n(me)] if me else []): people[p] = 'accept'
    return {'default': 'hold', 'people': people}


# ── Reason's own config: the gate ────────────────────────────────────────────────────────────────
def config_path() -> Path: return home() / 'config.toml'


def read_config() -> dict:
    p = config_path()
    try: return tomllib.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
    except (OSError, tomllib.TOMLDecodeError) as e: raise RuntimeError(f"Reason Network's settings file can't be read ({e}) - fix it or ask its own setup to") from e


def gate_status() -> dict:
    try: inb = read_config().get('inbound') or {}
    except RuntimeError as e: return {'on': False, 'default': '', 'people': {}, 'detail': str(e)}
    inb = inb if isinstance(inb, dict) else {}
    people = inb.get('people') if isinstance(inb.get('people'), dict) else {}
    return {'on': inb.get('default') == 'hold', 'default': str(inb.get('default') or 'accept'), 'people': {str(k): str(v) for k, v in people.items()}}


def _q(s: str) -> str: return json.dumps(str(s), ensure_ascii=False)


def _without_inbound(text: str) -> str:
    "The file with every [inbound...] table and any top-level inbound key taken out - everything else as it was written."
    out, skip, top = [], False, True
    for line in text.splitlines(keepends=True):
        s = line.strip()
        if s.startswith('['):
            top = False
            name = s.strip('[] \t\r\n').split('#')[0].strip()
            skip = name == 'inbound' or name.startswith('inbound.') or name.startswith('"inbound"')
            if skip: continue
        if skip: continue
        if top and re.match(r'^\s*"?inbound"?\s*[.=]', line): continue
        out.append(line)
    return ''.join(out)


def write_policy(pol: dict) -> dict:
    """Reason's [inbound] tables rewritten in its own config.toml, the rest of the file untouched - checked by reading it back,
    and put back as it was if anything else moved. A copy of the first file is kept beside it."""
    p = config_path()
    before = p.read_text(encoding='utf-8') if p.exists() else ''
    old = tomllib.loads(before) if before else {}
    body = _without_inbound(before).rstrip()
    lines = ['[inbound]', f"default = {_q(pol['default'])}", '', '[inbound.people]'] + [f'{_q(k)} = {_q(v)}' for k, v in sorted(pol['people'].items())]
    new = (body + '\n\n' if body else '') + '\n'.join(lines) + '\n'
    got = tomllib.loads(new)
    rest = lambda d: {k: v for k, v in d.items() if k != 'inbound'}
    if rest(got) != rest(old) or got.get('inbound') != {'default': pol['default'], 'people': pol['people']}:
        raise RuntimeError("Reason Network's settings could not be changed safely - set `[inbound] default = \"hold\"` in "
                           f"{p} yourself")
    p.parent.mkdir(parents=True, exist_ok=True)
    keep = p.with_name('config.before-taskuary.toml')
    if before and not keep.exists(): keep.write_text(before, encoding='utf-8')
    p.write_text(new, encoding='utf-8')
    return got['inbound']


def restart():
    "The daemon reads its config when it starts: stop it, and the next command starts it on the new one."
    if has('stop'): run(['stop'], timeout=30)


def apply_gate(trusted: list, me: str, on: bool = True) -> dict:
    cur = gate_status()
    pol = policy(trusted, me, cur['people']) if on else {'default': 'accept', 'people': {k: v for k, v in cur['people'].items() if v == 'refuse'}}
    write_policy(pol)
    restart()
    return gate_status()


# ── the card's settings and Taskuary's own memory of what it did ─────────────────────────────────
def connector(store):
    try: return store.get_connector_by_type(TYPE)
    except Exception: return None


def settings(c) -> dict:
    try: cfg = json.loads((c or {}).get('ConfigJson') or '{}')
    except ValueError: cfg = {}
    cfg = cfg if isinstance(cfg, dict) else {}
    return {'trusted': clean_trusted(cfg.get('trusted') or []), 'off': [str(x) for x in cfg.get('off') or [] if isinstance(x, str)],
            'gate': cfg.get('gate') is True}


def save_settings(store, c, actor: str = 'owner', **kw) -> dict:
    try: cfg = json.loads(c.get('ConfigJson') or '{}')
    except ValueError: cfg = {}
    cfg = {**(cfg if isinstance(cfg, dict) else {}), **kw}
    store.save_connector({'ConnectorId': c['ConnectorId'], 'ConfigJson': json.dumps(cfg)}, actor)
    return settings({'ConfigJson': json.dumps(cfg)})


_STATE_LOCK = threading.RLock()


def _state_path() -> Path:
    from . import config
    return Path(config.home()) / 'reason-network.json'


def state() -> dict:
    with _STATE_LOCK:
        try: d = json.loads(_state_path().read_text(encoding='utf-8'))
        except (OSError, ValueError): d = {}
        d = d if isinstance(d, dict) else {}
        for k in ('seen', 'held', 'outbound', 'asked'): d[k] = d.get(k) if isinstance(d.get(k), dict) else {}
        return d


def save_state(d: dict):
    with _STATE_LOCK:
        for k in ('seen', 'held', 'outbound'):            # the newest few thousand: ids are never reused, so old ones only cost room
            if len(d[k]) > 3000: d[k] = dict(list(d[k].items())[-2000:])
        p = _state_path(); p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + '.tmp'); tmp.write_text(json.dumps(d), encoding='utf-8'); os.replace(tmp, p)


def me(refresh: bool = False) -> str:
    "The owner's name on the network: asked of `who` now and then, remembered between."
    d = state()
    if d.get('me') and not refresh and time.time() - float(d.get('me_at') or 0) < 600: return d['me']
    try: name = who()['person']
    except Exception: return d.get('me') or ''
    with _STATE_LOCK:
        d = state(); d['me'], d['me_at'] = name, time.time(); save_state(d)
    return name


# ── on the task ──────────────────────────────────────────────────────────────────────────────────
def _words(text: str, n: int = 4000) -> str:
    "Their words for a note: credentials out, cut where long, between the marks that say someone else wrote them."
    from . import redact, terminal
    t = redact.scrub(str(text or '').strip())
    return terminal.fence(t[:n] + (' …[cut]' if len(t) > n else ''))


def _files(files) -> str:
    fs = [f for f in files or [] if f]
    return ('\nFiles they sent (text, saved by Reason Network, not opened): ' + '; '.join(f[:300] for f in fs[:10])) if fs else ''


def note_message(store, tid: int, m: dict, trusted: list, me_: str) -> bool:
    "A message one of our agents was shown, as a note on its task - once per message id."
    import hashlib
    key = m.get('id') or f"{m.get('from')}:{hashlib.sha1(str(m.get('body')).encode()).hexdigest()[:16]}"
    with _STATE_LOCK:
        d = state()
        if key in d['seen']: return False
        d['seen'][key] = tid; save_state(d)
    who_ = m['from'].split('/')[0]
    tag = '' if is_trusted(m['from'], trusted, me_) else ' (not on your trusted list)'
    head = (f"{who_}'s answer to an approval ({m['from']}){tag}: " if m.get('approval') else f"{who_}'s agent ({m['from']}){tag}: ")
    store.add_comment(tid, ACTOR, 'agent', head + _words(m.get('body')) + _files(m.get('files')))
    store.audit('task', tid, 'reason_message', ACTOR, detail={'id': m.get('id'), 'from': m['from']})
    return True


def _texts(o, out: list, user: bool = False):
    "Every text block of a user (or developer) turn in one transcript line - never a tool's result, which carries pages and files."
    if isinstance(o, list):
        for v in o: _texts(v, out, user)
        return
    if not isinstance(o, dict) or o.get('type') in ('tool_result', 'function_call_output') or o.get('role') in ('assistant', 'system', 'tool'): return
    user = user or o.get('role') in ('user', 'developer')
    if user and o.get('type') in ('text', 'input_text') and isinstance(o.get('text'), str): out.append(o['text'])
    for k, v in o.items():
        if user and k == 'content' and isinstance(v, str): out.append(v)
        elif isinstance(v, (dict, list)): _texts(v, out, user)


def transcript_frames(path: str, max_first: int = 2 << 20) -> list:
    "The framed messages appended to a transcript since we last looked (the first look reads at most its last 2 MB)."
    try: size = os.path.getsize(path)
    except OSError: return []
    with _STATE_LOCK:                 # kept in memory: a restart reads the tail again, and the seen ids keep it to one note each
        at = _OFFSETS.get(path)
        start = at if isinstance(at, int) and 0 <= at <= size else max(0, size - max_first)
        if start == size: return []
        _OFFSETS[path] = size
    try:
        with open(path, 'rb') as f: f.seek(start); raw = f.read(size - start)
    except OSError: return []
    texts = []
    for line in raw.decode('utf-8', 'replace').splitlines():
        if 'reason-' not in line: continue
        try: _texts(json.loads(line), texts)
        except ValueError: continue
    # Reason's delivery IS the turn - it opens on its frame. A frame quoted inside other words (a mail in the seed, a note
    # typed in) is someone writing about a message, and noting it would let any mail put words in a teammate's mouth
    return [m for t in texts if t.lstrip().startswith(('<reason-message ', '<reason-approval ')) for m in parse_frames(t)]


_ACTIVE, _OFFSETS = [0.0, None], {}


def active(store) -> dict | None:
    "The card's settings when it is switched on - read at most every few seconds, since every hook asks."
    if time.time() - _ACTIVE[0] < 5: return _ACTIVE[1]
    c = connector(store)
    _ACTIVE[:] = [time.time(), settings(c) if c and c.get('Active') else None]
    return _ACTIVE[1]


def on_hook(store, tid: int, payload: dict) -> int:
    "A hook from one of our sessions: anything Reason showed its agent goes on the task."
    cfg = active(store) if store is not None and tid else None
    if not cfg: return 0
    msgs = []
    if str(payload.get('tool_name') or '').startswith(TOOL) and payload.get('hook_event_name') == 'PostToolUse':
        res = payload.get('tool_response')
        msgs += parse_frames(json.dumps(res) if not isinstance(res, str) else res) if 'reason-' in str(res) else []
    if payload.get('transcript_path'): msgs += transcript_frames(str(payload['transcript_path']))
    name = me() if msgs else ''
    return sum(note_message(store, tid, m, cfg['trusted'], name) for m in msgs)


def pre_tool(store, tid: int, sid: str, tool: str, inp: dict, wait: float = None) -> dict:
    """Before one of our Claude sessions uses a Reason tool. {} leaves the call to Claude and Reason as they are."""
    cfg = active(store)
    if not cfg: return {}
    inp = inp if isinstance(inp, dict) else {}
    deny = lambda why: {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', 'permissionDecisionReason': why}}
    if tool == 'send_message':
        to = str(inp.get('to') or '')
        if not is_trusted(to, cfg['trusted'], me()):
            store.add_comment(tid, ACTOR, 'agent', f"The agent tried to message {to or 'someone'} over Reason Network - not on your trusted list, so it was stopped.")
            return deny(f"{to or 'That address'} is not on the owner's trusted list for Reason Network, so nothing was sent. Ask the owner "
                        "(they add people on the Reason Network card in Taskuary); never message a group.")
        store.add_comment(tid, ACTOR, 'agent', f"The agent messaged {to}'s agent over Reason Network: " + _words(inp.get('message'), 2000)
                          + ('\nWith files: ' + '; '.join(str(f)[:200] for f in inp['files'][:10]) if isinstance(inp.get('files'), list) and inp['files'] else ''))
        return {}
    if tool == 'ask_user':
        from . import workerstate as ws
        q = str(inp.get('question') or '').strip()
        if not q: return {}
        about = state()['seen'].get(str(inp.get('about') or '')) if inp.get('about') else None
        g = ws.group_key(f'reason-ask:{tid}:{sid}:{time.time_ns()}'); rid = ws.question_id(g, 1)
        ws.hold(tid, sid, g, [rid])
        try: ws.record(store, tid, sid, 'approval_needed', request_id=rid, choices=['Approve', 'Deny'], source='hook',
                       text=f"A teammate's agent wants something only you can OK (Reason Network): {_words(q, 1500)}"
                            + (' - about the message noted on this task' if about else ''))
        except Exception:
            with ws._HELD_LOCK: ws.HELD.pop(g, None)
            raise
        from .hooks import ASK_WAIT
        got = ws.wait_held(g, ASK_WAIT if wait is None else wait)
        if not got: return {}                               # nobody answered here: Reason's own pop-up asks
        ans = str(got.get(rid) or '').strip()
        ok = ans.lower() in ('approve', 'approved', 'allow', 'yes')
        store.add_comment(tid, ACTOR, 'agent', f"You {'approved' if ok else 'did not approve'} the request in Taskuary: {_words(q, 600)}")
        return deny(f"The owner answered in Taskuary instead of the pop-up: {'APPROVED' if ok else 'DENIED'}"
                    + (f' - "{ans}"' if ans.lower() not in ('approve', 'deny') else '') + '. Tell the teammate with send_message.')
    return {}


# ── asking, and the poll ─────────────────────────────────────────────────────────────────────────
class Miss(ValueError):
    "Something the owner can fix, said plainly: nothing was sent."


def resolve(who_: str) -> str:
    "erin -> erin's one live session; erin/api-claude as it is. Several sessions: name one."
    w = _n(who_).lstrip('@')
    if not w or '*' in w or w.startswith('repo:'): raise Miss('Name one person or one of their sessions - never a group.')
    if '/' in w: return w
    d = who()
    mine = [s for s in d['sessions'] if _n(s['person']) == w]
    if not mine: raise Miss(f"{who_} has no session on the network right now - nothing was sent.")
    if len(mine) > 1:
        raise Miss(f"{who_} has {len(mine)} sessions: " + '; '.join(f"{s['address']} ({s['repo'] or s['agent']}{', ' + s['doing'] if s['doing'] else ''})"
                                                         for s in mine[:6]) + ' - say which.')
    return mine[0]['address']


def ask(store, tid: int, who_: str, text: str, actor: str = 'owner') -> dict:
    "Ask a trusted teammate's agent, from <owner>/taskuary; the note goes on the task, and so will the reply."
    from . import redact
    c = connector(store)
    if not c or not c.get('Active'): raise Miss('Reason Network is not switched on here - turn its card on under Connections first.')
    text = redact.scrub(str(text or '').strip())
    if not text: raise Miss('Say what to ask.')
    if not exe(): raise Miss(f"Reason Network isn't installed on this computer ({DOCS}).")
    cfg, name = settings(c), me(refresh=True)
    if not name: raise Miss("Reason Network didn't say who you are on it - is it set up? (`reason-network setup`)")
    to = resolve(who_)
    if not is_trusted(to, cfg['trusted'], name):
        raise Miss(f"{to} is not on your trusted list - add them on the Reason Network card first. Nothing was sent.")
    r = send(to, text, name, store)
    with _STATE_LOCK:
        d = state()
        if r['id']: d['outbound'][r['id']] = tid
        d['asked'][to.split('/')[0]] = tid; save_state(d)
    store.add_comment(tid, actor, 'human', f"Asked {to}'s agent over Reason Network: {text}" + (f" ({r['note']})" if r['note'] else ''))
    store.audit('task', tid, 'reason_ask', actor, detail={'to': to, 'id': r['id']})
    return {'to': to, 'id': r['id'], 'note': r['note']}


def note_replies(store) -> int:
    "Replies at <owner>/taskuary, each on the task it answers (by reply_to, else the last ask of that person)."
    cfg = active(store)
    if not cfg: return 0
    n, name = 0, me()
    for m in listen():
        d = state()
        tid = d['outbound'].get(m.get('reply_to') or '') or d['asked'].get(m['from'].split('/')[0])
        if tid and note_message(store, int(tid), m, cfg['trusted'], name): n += 1
    return n


def _held_task(store, m: dict) -> int:
    who_ = m['from'].split('/')[0] or 'someone'
    tid = store.create_task({'Title': f"{who_}'s agent wants to reach your agent (Reason Network)",
                             'Summary': (f"A message from {m['from']}" + (f" ({m['agent']})" if m.get('agent') else '')
                                         + f", held by Reason Network: it has NOT reached any agent.\n\n{_words(m.get('body'), 2000)}"
                                         + _files(m.get('files')) + f"\n\n{who_} is not on your trusted list. Deliver it or drop it on the Reason "
                                         "Network card under Connections - or add them there if you trust them."),
                             'Kind': 'note', 'Status': 'open', 'Priority': 'normal', 'Source': TYPE, 'SourceRef': f"reason:{m['id']}",
                             'OriginBase': 'stranger'}, ACTOR)
    store.audit('task', tid, 'reason_held', ACTOR, detail={'id': m['id'], 'from': m['from']})
    return tid


def sweep_held(store) -> dict:
    """Held messages: a trusted session's goes on (approve); anyone else's becomes the owner's task, once, and stays held."""
    cfg = active(store)
    if not cfg: return {'delivered': 0, 'tasks': 0}
    name, out = me(), {'delivered': 0, 'tasks': 0}
    for m in held():
        d = state()
        if m['id'] in d['held']: continue
        if not m['ambiguous'] and is_trusted(m['from'], cfg['trusted'], name):
            try: settle([m['id']], True); out['delivered'] += 1; tid = 0
            except Exception as e: logger.warning(f'reason network: a trusted held message was not delivered - {e}'); continue
        else: tid = _held_task(store, m); out['tasks'] += 1
        with _STATE_LOCK:
            d = state(); d['held'][m['id']] = tid; save_state(d)
    return out


def held_rows(store) -> list:
    "What waits on the owner, for the card: never a trusted session's (the poll lets those through)."
    d, cfg, name = state(), settings(connector(store)), me()
    return [{'id': m['id'], 'from': m['from'], 'agent': m.get('agent', ''), 'text': _words(m['body'], 600), 'files': m.get('files') or [],
             'task': d['held'].get(m['id']) or None, 'ambiguous': m['ambiguous']}
            for m in held() if m['ambiguous'] or not is_trusted(m['from'], cfg['trusted'], name)]


def poll(store) -> dict:
    out = {'replies': 0, **sweep_held(store)} if has('held') else {'replies': 0, 'delivered': 0, 'tasks': 0}
    try: out['replies'] = note_replies(store)
    except Unsupported: pass
    return out


def watch(store):
    "The clock: while the card is on and the CLI is here, held messages and replies are looked at every few seconds."
    def loop():
        while True:
            time.sleep(POLL_EVERY)
            try:
                if active(store) and exe(): poll(store)
            except (Unsupported, NotInstalled) as e: logger.debug(f'reason network: {e}')
            except Exception as e: logger.warning(f'reason network poll failed: {e}')
    threading.Thread(target=loop, daemon=True, name='reason-network').start()


def test() -> str:
    "The card's Test: is it here, and does it answer - asked afresh."
    forget()
    p = exe()
    if not p: raise RuntimeError(f"Reason Network isn't installed on this computer - install it from its own instructions ({DOCS})")
    d = who()
    live = [s for s in d['sessions'] if not s['is_me']]
    return (f"found at {p}; you are {d['person'] or 'not named yet'}" + (f" on {d['team']}" if d['team'] else '')
            + f" - {len(d['people'])} people, {len(live)} of their sessions live")


def checkouts(store) -> dict:
    "{repository: its checkout on this machine}, from the agents' cwd_map - the folders that can be put off the network."
    out = {}
    for a in store.list_agents(active_only=False):
        try: out.update({k: v for k, v in (json.loads(a.get('Config') or '{}').get('cwd_map') or {}).items() if v and k not in out})
        except (ValueError, AttributeError): continue
    return out


def assistant_folder() -> str:
    from . import config
    return str(Path(config.home()) / 'assistant')


def _same(a: str, b: str) -> bool:
    n = lambda p: os.path.normcase(os.path.normpath(os.path.expanduser(str(p))))
    return n(a) == n(b) or n(b).startswith(n(a).rstrip(os.sep) + os.sep)


def folder_off(path: str) -> bool:
    "Is `path` off the network by Reason's own config - its own entry or a folder above it?"
    try: f = read_config().get('folders') or {}
    except RuntimeError: return False
    return isinstance(f, dict) and any(v == 'off' and _same(k, path) for k, v in f.items())


def demo_status() -> dict:
    "The demo world: no Reason Network on a machine that does not exist - the card says how it would be installed."
    return {'installed': False, 'path': None, 'home': '', 'state': False, 'docs': DOCS, 'active': False, 'trusted': [], 'gate': None,
            'who': None, 'held': [], 'detail': '', 'folders': [], 'assistant_folder': '', 'assistant_off': False, 'off': [], 'demo': True}


def status(store) -> dict:
    "Everything the card draws, each part said in plain words when it cannot be had."
    det, c = detect(), connector(store)
    cfg = settings(c)
    out = {**det, 'active': bool(c and c.get('Active')), 'trusted': cfg['trusted'], 'gate': gate_status() if det['installed'] else None,
           'who': None, 'held': [], 'detail': '', 'folders': [], 'assistant_folder': assistant_folder(), 'off': cfg['off'],
           'assistant_off': det['installed'] and folder_off(assistant_folder())}
    out['folders'] = [{'repo': r, 'path': p, 'off': p in cfg['off'] or (det['installed'] and folder_off(p))} for r, p in sorted(checkouts(store).items())]
    if not det['installed']: return out
    try: out['who'] = who()
    except Exception as e: out['detail'] = str(e)
    try: out['held'] = held_rows(store) if has('held') else []
    except Exception as e: out['detail'] = out['detail'] or str(e)
    return out
