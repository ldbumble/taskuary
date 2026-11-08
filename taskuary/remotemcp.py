"""A VENDOR'S OWN REMOTE MCP SERVER IN YOUR AGENT CLI (the owner, 2026-11-08: "add more connections ... make them work well").

One road for every vendor that hosts an official MCP server: the card's Add registers it in the agent CLIs the owner has (Claude Code:
`claude mcp add --transport http --scope user <type> <url>`; Codex: `codex mcp add <type> --url <url>`), and its Sign in runs that CLI's
own `mcp login`, which opens the vendor's OAuth page in the browser. Taskuary never holds the token, so it cannot list the server's tools
either, and the send filter (sendfilter.py) would leave it out whole: the owner's Add press is their word on it, so the server is marked
kept there (sendfilter.correct '*'), which the card says.

THE TABLE IS THE CATALOGUE: a card in connectorcatalog.json with `mcp: {url, docs}` rides this road - `docs` is the vendor's own page
the URL was read off - and its type is the CLI's server name. A new vendor is a catalogue row, no code. Video tools that also ship a skill
(videotools.py) build on this module. The Add / Sign in press is the owner's (guard.DENIED); the demo world reaches nothing.
"""
import json, time
from loguru import logger
from . import connectorcatalog

MCPS = {c['type']: (c['title'], c['mcp']['url']) for c in connectorcatalog.cards() if c.get('mcp')}    # type -> (title, url)
CLIS = {'claude': 'Claude Code', 'codex': 'Codex'}
SIGN_IN = {'claude': 'in a Claude Code terminal type /mcp and pick {n}', 'codex': 'run `codex mcp login {n}` once'}
# SIGN IN, ONE PRESS (the owner, 2026-11-08): both CLIs sign in to a server themselves - `<cli> mcp login <name>` opens the vendor's page in the
# browser and waits for its answer - so the card's press starts that, hidden, and the card reads the CLI's own record of it (signed_in)
LOGINS, LOGIN_WAIT = {}, 600          # (cli, name) -> (the login running, when it began)


def _which(c):
    from . import clis
    return clis.which(c) or ''
def add_argv(cli: str, exe: str, name: str, url: str) -> list:
    return ([exe, 'mcp', 'add', '--transport', 'http', '--scope', 'user', name, url] if cli == 'claude' else [exe, 'mcp', 'add', name, '--url', url])
def login_argv(cli: str, exe: str, name: str) -> list: return [exe, 'mcp', 'login', name]
def registered(name: str) -> dict:
    from . import sendfilter
    return {'claude': name in sendfilter.claude_servers(), 'codex': name in sendfilter.codex_servers()}
def signed_in(cli: str, name: str):
    """True / False by the CLI's own record, None where it cannot be read here. Claude Code keeps its MCP sign-ins in .credentials.json
    (`mcpOAuth`, each with its serverName - the macOS keychain instead, unread); Codex says it in `codex mcp list --json` (`auth_status`)."""
    try:
        if cli == 'claude':
            from .climodels import claude_home
            f = claude_home() / '.credentials.json'
            if not f.exists(): return None
            return any(isinstance(v, dict) and v.get('serverName') == name and v.get('accessToken')
                       for v in (json.loads(f.read_text(encoding='utf-8')).get('mcpOAuth') or {}).values())
        from . import spawn
        r = spawn.run([_which('codex'), 'mcp', 'list', '--json'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
        row = next((x for x in json.loads(r.stdout or '[]') if x.get('name') == name), None)
        return bool(row) and str(row.get('auth_status') or '').lower() in ('o_auth', 'oauth', 'bearer_token')
    except Exception as e:
        logger.info(f'remotemcp: whether {cli} is signed in to {name} was not read: {e}'); return None
def signing_in(cli: str, name: str) -> bool:
    p, t0 = LOGINS.get((cli, name), (None, 0))
    if p is None or p.poll() is not None: return False
    if time.time() - t0 < LOGIN_WAIT: return True
    p.kill(); return False                                       # the browser page was left: the next press starts it again


def _run(argv, cwd=None, timeout=900) -> tuple:
    from . import spawn
    r = spawn.run(argv, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    return int(r.returncode or 0), ((r.stdout or '') + (r.stderr or '')).strip()


def state(store, t: str) -> dict:
    "What the card shows: per CLI whether it is here, has the server, and is signed in to it - and what is still missing."
    from . import demo
    if t not in MCPS: raise ValueError(f'{t} has no remote MCP server')
    title, url = MCPS[t]
    out = {'type': t, 'title': title, 'url': url, 'docs': connectorcatalog.by_type(t)['mcp'].get('docs', ''), 'clis': {}, 'skill': None,
           'missing': [], 'sign_in': []}
    if demo.enabled(): return {**out, 'demo': True}          # the demo world shows nobody's machine
    on = registered(t)
    out['clis'] = {c: {'here': bool(_which(c)), 'added': on[c], 'signed_in': signed_in(c, t) if on[c] else False,
                       'signing_in': signing_in(c, t)} for c in CLIS}
    out['sign_in'] = [SIGN_IN[c].format(n=t) for c, v in out['clis'].items() if v['added'] and not v['signed_in']]
    if not any(v['here'] for v in out['clis'].values()): out['missing'].append('Claude Code or Codex on this computer')
    out['ready'] = not out['missing'] and all(v['added'] for v in out['clis'].values() if v['here'])
    return out


def register(store, t: str, actor: str = 'owner', run=None) -> list:
    "Add the server to each CLI here that lacks it, and keep it for the send filter once one has it. One line said per CLI."
    from . import sendfilter
    run, said, st = run or _run, [], state(store, t)
    for c, v in st['clis'].items():
        if not v['here'] or v['added']: continue
        rc, out = run(add_argv(c, _which(c), t, MCPS[t][1]), None, 120)
        said.append(f"{CLIS[c]}: {'added' if rc == 0 else f'did not add it ({out[-200:]})'}")
    if any(v['added'] for v in state(store, t)['clis'].values()):
        sendfilter.correct(store, t, '*', 'keep', actor)       # its tools cannot be listed without the vendor's sign-in: the owner's Add keeps it
    return said


def finish(store, t: str, st: dict, said: list, actor: str, event: str) -> dict:
    "The card turns on once everything answered; the press is audited; the card gets state() with `said`."
    if st.get('ready') and (c := store.get_connector_by_type(t)) and not c.get('Active'):
        store.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1}, actor)
    store.audit('connector', 0, event, actor, detail={'type': t, 'said': said})
    return {**st, 'said': said}


def add(store, t: str, actor: str = 'owner', runner=None) -> dict:
    "The card's Add press - the owner's only (guard.DENIED)."
    from . import demo
    if demo.enabled(): raise RuntimeError('This is the demo - nothing is installed here.')
    said = register(store, t, actor, runner)
    return finish(store, t, state(store, t), said, actor, 'mcp_tool_added')


def sign_in(store, t: str, actor: str = 'owner', start=None) -> dict:
    """The card's Sign in press - the owner's only (guard.DENIED): each CLI here that has the server and is not signed in to it runs its own
    `mcp login`, which opens the vendor's sign-in in the browser. Returns state() with `said`; the card asks again until it says signed in."""
    from . import demo, spawn
    if demo.enabled(): raise RuntimeError('This is the demo - nothing signs in here.')
    if t not in MCPS: raise RuntimeError(f'{t} has no sign-in of its own')
    start, said = start or (lambda argv: spawn.popen(argv, stdin=spawn.subprocess.DEVNULL, stdout=spawn.subprocess.DEVNULL,
                                                      stderr=spawn.subprocess.DEVNULL)), []
    clis = state(store, t)['clis']
    for c, v in clis.items():
        if not v['added'] or v['signed_in'] or v['signing_in']: continue
        try: LOGINS[(c, t)] = (start(login_argv(c, _which(c), t)), time.time()); said.append(f'{CLIS[c]}: sign-in opened in your browser')
        except OSError as e: said.append(f'{CLIS[c]}: sign-in did not start ({e})')
    if not said: said.append('Add it first - there is nothing to sign in to yet' if not any(v['added'] for v in clis.values()) else
                             'The sign-in is open in your browser' if any(v['signing_in'] for v in clis.values()) else 'Already signed in')
    store.audit('connector', 0, 'mcp_tool_sign_in', actor, detail={'type': t, 'said': said})
    return {**state(store, t), 'said': said}


def test(store, t: str, st: dict | None = None) -> str:
    "The card's Test: what is in place, or what is still missing (raised, so the card shows it as a failure)."
    st = st or state(store, t)
    if st['missing']: raise RuntimeError('still needs ' + '; '.join(st['missing']))
    have = [CLIS[c] for c, v in st['clis'].items() if v['added']] + ([st['skill']['name']] if st['skill'] and st['skill']['here'] else [])
    if not have: raise RuntimeError(f"{st['title']} is not added yet - press Add on its card")
    return f"{st['title']} is ready in {', '.join(have)}" + (f" - to sign in, {' or '.join(st['sign_in'])}" if st['sign_in'] else '')


def road(t: str):
    "The module a tool card's Add / Sign in / Test runs on: videotools for a card that also ships a skill, this one for a bare server, else None."
    from . import videotools
    import sys
    return videotools if t in videotools.SKILLS else sys.modules[__name__] if t in MCPS else None
