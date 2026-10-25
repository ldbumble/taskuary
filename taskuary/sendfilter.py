"""THE OWNER'S OWN MCP TOOLS, MINUS THE ONES THAT SEND (the owner, 2026-10-25, revised: "agents keep my MCP tools; only the tools
that send mail or chat are removed, and sending goes through Taskuary").

An agent session loads every MCP server the owner set up for their own CLI - a mail server, a chat server, a tracker. Most of what
those expose is reading and filing, and the agents keep all of it. A tool that puts words in front of another person (sends a mail,
posts in a chat, comments on a Jira or GitHub issue) is left out of the session by name: Claude's --disallowedTools, Codex's
per-server disabled_tools. The agent sends through Taskuary's propose tools instead (agenttools), which only ever light a button.

WHICH TOOLS SEND is decided per tool, never from a word list over names:
  1. the server's own MCP annotation: a tool it marks readOnlyHint is kept, no question asked;
  2. otherwise a model reads the tool's name, description and annotations and answers whether calling it reaches a person;
  3. the owner's correction beats both (`overrides`), and is what the card shows beside each verdict.
Each verdict is cached by the tool's own words, so a server that changes a description is asked again. FAIL CLOSED: a tool no model
has judged yet, and a server whose tools could not be listed (an OAuth server Taskuary cannot open), are left out until they are -
"never sent without the owner's press" outranks keeping a tool.

CLAUDE.AI ACCOUNT CONNECTORS (mcp__claude_ai_*) live on the owner's claude.ai account, not in any file here, and Taskuary cannot open
them. Their names are read ONCE from the init event of a short `claude -p` start that is stopped before the model is asked anything
(claude_ai_list), cached, and read again only on the owner's "Check again". Only the names are known, so the model judges a name.
"""
import hashlib, json, os, re, threading, time
from pathlib import Path
from loguru import logger

CACHE, OVERRIDES = 'sendfilter_cache', 'sendfilter_overrides'      # settings rows: what was seen and judged; the owner's corrections
FRESH = 6 * 3600                                                     # a scan older than this is redone in the background
_LOCK, _RUNNING = threading.Lock(), {'on': False}

JUDGE = ("You decide whether an MCP tool SENDS. A tool sends when calling it puts words in front of another person or publishes them: "
         "sending or forwarding an email, posting or replying in a chat or channel, a comment on an issue, ticket or pull request "
         "(Jira, GitHub, Linear...), a post on social media, an invitation sent to attendees. It does NOT send when it only reads, "
         "searches or lists; saves a draft nobody receives; saves, moves or uploads a file; or changes a record without notifying "
         "anyone. When the description is unclear, say it sends. Answer JSON only: {\"sends\": true|false, \"why\": \"<one short "
         "sentence>\"}.")


# ── what the owner set up ───────────────────────────────────────────────────────────────────────────────────────────────────
def _claude_json() -> dict:
    from .climodels import claude_home
    for p in (claude_home() / '.claude.json', Path.home() / '.claude.json'):
        try: return json.loads(p.read_text(encoding='utf-8', errors='replace'))
        except (OSError, ValueError): continue
    return {}


def claude_servers() -> dict:
    "The owner's Claude MCP servers: user scope, and every folder's local scope in ~/.claude.json. name -> its config."
    j = _claude_json()
    out = dict(j.get('mcpServers') or {})
    for proj in (j.get('projects') or {}).values():
        for k, v in ((proj or {}).get('mcpServers') or {}).items(): out.setdefault(k, v)
    return {k: v for k, v in out.items() if isinstance(v, dict)}


def codex_servers() -> dict:
    "The owner's Codex MCP servers ([mcp_servers.*] in CODEX_HOME/config.toml). name -> its config."
    try: import tomllib
    except ImportError: import tomli as tomllib       # py3.10
    p = Path(os.getenv('CODEX_HOME') or Path.home() / '.codex') / 'config.toml'
    try: return {k: v for k, v in (tomllib.loads(p.read_text(encoding='utf-8')).get('mcp_servers') or {}).items() if isinstance(v, dict)}
    except (OSError, ValueError) as e:
        if p.exists(): logger.info(f'codex config not read for the send filter: {e}')
        return {}


def _bare(name: str) -> str: return re.sub(r'[^A-Za-z0-9_-]', '_', name)     # Claude's own spelling of a server in a tool's name


def claude_ai_list(timeout: float = 90) -> dict:
    """The claude.ai account connectors and their tool names, from the init event of `claude -p --output-format stream-json`
    (verified on Claude Code 2.1.310, 2026-10-25: init lists every server with its `source` and `status`, and the tools of the
    connected ones). The process is stopped the moment init arrives, so no turn is spent. The owner's own hooks are not loaded
    (--setting-sources project,local in an empty folder), so the start posts nothing to a running Taskuary.
    {name: {'status', 'tools': [tool names]}}; raises when Claude is not installed or no init came."""
    import subprocess, tempfile
    from . import clis, spawn
    exe = clis.which('claude')
    if not exe: raise RuntimeError('Claude Code is not installed')
    env = {k: v for k, v in os.environ.items() if not k.startswith('TASKUARY_')}      # nothing of this server's goes to the child
    with tempfile.TemporaryDirectory(prefix='tq-claudeai-') as d:
        p = spawn.popen([exe, '-p', '--output-format', 'stream-json', '--verbose', '--setting-sources', 'project,local', '--max-turns', '1',
                         'Reply OK.'], cwd=d, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        def stop():
            if os.name == 'nt': spawn.run(['taskkill', '/PID', str(p.pid), '/T', '/F'], capture_output=True)   # the npm shim's node too
            else: p.kill()
        timer = threading.Timer(timeout, stop); timer.start()
        init = None
        try:
            for line in p.stdout:
                try: e = json.loads(line)
                except ValueError: continue
                if e.get('type') == 'system' and e.get('subtype') == 'init': init = e; break
        finally:
            timer.cancel()
            if p.poll() is None: stop()
            p.wait(10)
    if not init: raise RuntimeError('Claude started but never said which connectors it has')
    tools = [str(t) for t in init.get('tools') or []]
    out = {}
    for s in init.get('mcp_servers') or []:
        if s.get('source') != 'claudeai' or not s.get('name'): continue
        pre = f"mcp__{_bare(s['name'])}__"
        out[s['name']] = {'status': str(s.get('status') or ''), 'tools': [t[len(pre):] for t in tools if t.startswith(pre)]}
    return out


def _claude_ai(cache: dict, relist: bool) -> dict:
    "The cached claude.ai listing, read once (and on the owner's Check again). A failed read keeps the last one and is tried next scan."
    old = cache.get('claudeai') or {}
    if old.get('at') and not relist: return old
    try: return {'at': time.time(), 'servers': claude_ai_list(), 'error': ''}
    except Exception as e:
        logger.info(f'claude.ai connectors not read for the send filter: {e}')
        return {**old, 'at': 0, 'error': str(e)[:200], 'servers': old.get('servers') or {}}


def _expand(v):
    "${VAR} in a server's config, the way the CLI expands it (the owner's own environment)."
    if isinstance(v, str): return os.path.expandvars(v)
    if isinstance(v, dict): return {k: _expand(x) for k, x in v.items()}
    if isinstance(v, list): return [_expand(x) for x in v]
    return v


def _list(cfg: dict) -> list:
    """The server's tools as it describes them - annotations included, which mcp.list_tools folds away."""
    from . import mcp
    c = _expand(cfg)
    url = c.get('url')
    if url and str(c.get('type') or 'http') not in ('http', 'sse', 'streamable_http'): url = None
    one = {'url': url, 'headers': c.get('headers') or c.get('http_headers'), 'timeout': 20} if url else \
          {'cmd': c.get('command'), 'args': c.get('args'), 'env': c.get('env'), 'timeout': 20}
    s = mcp._session(one)
    try: return [{'name': t['name'], 'description': str(t.get('description') or '')[:600], 'annotations': t.get('annotations') or {}}
                 for t in s.list_tools()]
    finally: s.close()


def _ai_tools(v: dict) -> list:
    "A claude.ai connector's tools: names only. One that lists none (it needs signing in) cannot be judged, so it is left out whole."
    if not v.get('tools'):
        raise RuntimeError('it needs signing in on claude.ai before its tools can be read' if v.get('status') == 'needs-auth'
                           else f"Claude listed no tools for it ({v.get('status') or 'no status'})")
    return [{'name': t, 'description': '', 'annotations': {}} for t in v['tools']]


def _key(server: str, t: dict) -> str:
    h = hashlib.sha256(json.dumps([t.get('description'), t.get('annotations')], sort_keys=True).encode()).hexdigest()[:12]
    return f'{server}/{t["name"]}/{h}'


def _load(store, k, d):
    try: return json.loads(store.get_setting(k) or '') or d
    except ValueError: return d


def judge(store, server: str, t: dict, verdicts: dict, brain=None) -> dict:
    """{'sends': bool|None, 'why', 'by': 'annotation'|'model'|''}. None is "not judged yet" - left out until it is (fail closed)."""
    if (t.get('annotations') or {}).get('readOnlyHint') is True: return {'sends': False, 'why': 'its server marks it read-only', 'by': 'annotation'}
    k = _key(server, t)
    if k in verdicts: return verdicts[k]
    if not brain: return {'sends': None, 'why': 'not judged yet - no brain was connected to judge it', 'by': ''}
    from .llm import ask_json
    a = ask_json(brain, JUDGE, json.dumps({'server': server, 'tool': t['name'], 'description': t.get('description'),
                                           'annotations': t.get('annotations')}, ensure_ascii=False),
                 want={'type': 'object', 'properties': {'sends': {'type': 'boolean'}, 'why': {'type': 'string'}}, 'required': ['sends', 'why']},
                 need=('why',))
    d = a.data or {}
    if not isinstance(d.get('sends'), bool): return {'sends': None, 'why': 'the model gave no verdict', 'by': ''}
    verdicts[k] = v = {'sends': d['sends'], 'why': str(d.get('why') or '')[:200], 'by': 'model'}
    return v


def scan(store, brain=None, relist: bool = False) -> dict:
    """List every server's tools and judge each one that is not marked read-only. Slow (each stdio server is started once), so it runs
    in the background (refresh); its answer is cached for the launches in between. `relist` reads the claude.ai connectors again."""
    cache = _load(store, CACHE, {})
    ai = _claude_ai(cache, relist)
    every = [(cli, n, c) for cli, found in (('claude', claude_servers()), ('codex', codex_servers())) for n, c in found.items()]
    every += [('claude', n, {'claudeai': v}) for n, v in (ai.get('servers') or {}).items() if n not in claude_servers()]
    if brain is None and every:                      # no servers, no brain started
        try:
            from .llm import build_llm
            brain = build_llm(store)
        except Exception as e: logger.info(f'send filter has no brain to judge with ({e}) - unjudged tools stay out'); brain = None
    verdicts = cache.get('verdicts') or {}
    servers = {}
    for cli, name, cfg in every:
        try: tools = _ai_tools(cfg['claudeai']) if 'claudeai' in cfg else _list(cfg); err = ''
        except Exception as e: tools, err = [], str(e)[:200]
        servers[f'{cli}:{name}'] = {'cli': cli, 'name': name, 'error': err,
                                    'tools': [{**t, **judge(store, name, t, verdicts, brain)} for t in tools]}
    out = {'at': time.time(), 'servers': servers, 'verdicts': verdicts, 'claudeai': ai}
    store.set_setting(CACHE, json.dumps(out), 'sendfilter')
    return out


def refresh(store, force: bool = False) -> bool:
    "Start a background scan when the cached one is stale or missing. True when one was started. `force` also re-reads claude.ai."
    from . import demo
    if demo.enabled(): return False                    # the demo world starts nobody's servers
    cache = _load(store, CACHE, {})
    if not force and time.time() - float(cache.get('at') or 0) < FRESH: return False
    with _LOCK:
        if _RUNNING['on']: return False
        _RUNNING['on'] = True
    def go():
        try: scan(store, relist=force)
        except Exception as e: logger.warning(f'send filter scan failed: {e}')
        finally: _RUNNING['on'] = False
    threading.Thread(target=go, daemon=True, name='sendfilter').start()
    return True


# ── the answer a launch reads ───────────────────────────────────────────────────────────────────────────────────────────────
def verdicts(store, cli: str) -> list:
    """Every server this CLI loads, with each tool's verdict and the owner's correction applied - what the card shows, and what the
    launch flags are built from. A server set up since the last scan has no list yet, so it is left out whole until it has one."""
    cache, fix = _load(store, CACHE, {}), _load(store, OVERRIDES, {})
    seen = cache.get('servers') or {}
    out = []
    names = list(claude_servers() if cli == 'claude' else codex_servers())
    if cli == 'claude': names += [n for n in ((cache.get('claudeai') or {}).get('servers') or {}) if n not in names]
    for name in names:
        s = seen.get(f'{cli}:{name}')
        whole = fix.get(f'{name}/*')
        if not s or s.get('error') or not s.get('tools'):
            why = (s or {}).get('error') or ('its tools are not listed yet' if not s else 'it lists no tools')
            out.append({'server': name, 'error': why, 'blocked': whole != 'keep', 'unchecked': not s, 'by': 'owner' if whole else '',
                        'tools': []}); continue
        tools = []
        for t in s['tools']:
            mine = fix.get(f'{name}/{t["name"]}')
            sends = {'keep': False, 'block': True}.get(mine, t.get('sends'))
            tools.append({'name': t['name'], 'sends': sends, 'why': t.get('why'), 'by': 'owner' if mine else t.get('by'),
                          'blocked': sends is not False, 'unchecked': sends is None})
        out.append({'server': name, 'error': '', 'blocked': False, 'tools': tools})
    return out


def claude_denied(store) -> list:
    "--disallowedTools for a trusted Claude session: mcp__<server>__<tool> per send, mcp__<server> for a server left out whole."
    refresh(store)
    out = []
    for s in verdicts(store, 'claude'):
        n = _bare(s['server'])
        if s['blocked']: out.append(f'mcp__{n}')
        out += [f"mcp__{n}__{t['name']}" for t in s['tools'] if t['blocked']]
    return out


def codex_args(store) -> list:
    """Codex's spelling, per server (verified on codex-cli 0.164, 2026-10-25): `-c mcp_servers.<name>.disabled_tools=[...]`, and
    `.enabled=false` for a server left out whole. Only servers its config defines - a -c on a name it does not know fails its start."""
    refresh(store)
    out = []
    for s in verdicts(store, 'codex'):
        if s['blocked']: out += ['-c', f"mcp_servers.{s['server']}.enabled=false"]; continue
        off = [t['name'] for t in s['tools'] if t['blocked']]
        if off: out += ['-c', f"mcp_servers.{s['server']}.disabled_tools={json.dumps(off)}"]
    return out


def correct(store, server: str, tool: str, verdict: str, actor: str = 'owner') -> dict:
    """The owner's word on one tool ('keep' or 'block'), or on a whole server whose tools could not be listed (tool '*'). '' clears it."""
    if verdict not in ('keep', 'block', ''): raise ValueError("a correction is 'keep', 'block', or '' to clear it")
    fix = _load(store, OVERRIDES, {})
    k = f'{server}/{tool or "*"}'
    if verdict: fix[k] = verdict
    else: fix.pop(k, None)
    store.set_setting(OVERRIDES, json.dumps(fix), actor)
    store.audit('setting', 0, 'sendfilter_correct', actor, detail={'tool': k, 'verdict': verdict})
    return fix
