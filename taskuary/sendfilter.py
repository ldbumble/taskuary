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


def scan(store, brain=None) -> dict:
    """List every server's tools and judge each one that is not marked read-only. Slow (each stdio server is started once), so it runs
    in the background (refresh); its answer is cached for the launches in between."""
    every = [(cli, n, c) for cli, found in (('claude', claude_servers()), ('codex', codex_servers())) for n, c in found.items()]
    if brain is None and every:                      # no servers, no brain started
        try:
            from .llm import build_llm
            brain = build_llm(store)
        except Exception as e: logger.info(f'send filter has no brain to judge with ({e}) - unjudged tools stay out'); brain = None
    cache = _load(store, CACHE, {})
    verdicts = cache.get('verdicts') or {}
    servers = {}
    for cli, name, cfg in every:
        try: tools = _list(cfg); err = ''
        except Exception as e: tools, err = [], str(e)[:200]
        servers[f'{cli}:{name}'] = {'cli': cli, 'name': name, 'error': err,
                                    'tools': [{**t, **judge(store, name, t, verdicts, brain)} for t in tools]}
    out = {'at': time.time(), 'servers': servers, 'verdicts': verdicts}
    store.set_setting(CACHE, json.dumps(out), 'sendfilter')
    return out


def refresh(store, force: bool = False) -> bool:
    "Start a background scan when the cached one is stale or missing. True when one was started."
    from . import demo
    if demo.enabled(): return False                    # the demo world starts nobody's servers
    cache = _load(store, CACHE, {})
    if not force and time.time() - float(cache.get('at') or 0) < FRESH: return False
    with _LOCK:
        if _RUNNING['on']: return False
        _RUNNING['on'] = True
    def go():
        try: scan(store)
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
    for name in (claude_servers() if cli == 'claude' else codex_servers()):
        s = seen.get(f'{cli}:{name}')
        whole = fix.get(f'{name}/*')
        if not s or s.get('error') or not s.get('tools'):
            why = (s or {}).get('error') or ('its tools are not listed yet' if not s else 'it lists no tools')
            out.append({'server': name, 'error': why, 'blocked': whole != 'keep', 'tools': []}); continue
        tools = []
        for t in s['tools']:
            mine = fix.get(f'{name}/{t["name"]}')
            sends = {'keep': False, 'block': True}.get(mine, t.get('sends'))
            tools.append({'name': t['name'], 'sends': sends, 'why': t.get('why'), 'by': 'owner' if mine else t.get('by'),
                          'blocked': sends is not False})
        out.append({'server': name, 'error': '', 'blocked': False, 'tools': tools})
    return out


def claude_denied(store) -> list:
    "--disallowedTools for a trusted Claude session: mcp__<server>__<tool> per send, mcp__<server> for a server left out whole."
    refresh(store)
    out = []
    for s in verdicts(store, 'claude'):
        n = re.sub(r'[^A-Za-z0-9_-]', '_', s['server'])          # Claude's own spelling of a server in a tool's name
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
