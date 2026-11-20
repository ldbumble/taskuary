"""AN API CARD'S AGENT RUNS ON A CLI HARNESS (the owner, 2026-11-20: "make HIPAA AI usable"): the Codex CLI road every Codex agent already takes -
its install, Taskuary's tools, the chat, Stop, sessions - pointed at the card's own endpoint. Or OpenCode, where the owner picks it on the card.

A card's agent is the pick `cli:card-<id>`, whose row (agents.agent_row) is built here: the CLI, its gears in the card's own models, and an
environment holding a home of its own per card (CODEX_HOME / OpenCode's config) and the card's key. The key rides that environment only -
the config names the variable it is read from, and nothing written to disk holds it.

Triage and the other one-shot jobs stay on llm.make_llm. Where neither CLI can run here (not installed and no way to install it), the
agent keeps Taskuary's own loop (apiagent.py) and the card says so in one line (line)."""
import json
from pathlib import Path

from loguru import logger

HARNESSES = ('codex', 'opencode')
LABEL = {'codex': 'Codex', 'opencode': 'OpenCode'}
KEY_ENV = 'TASKUARY_AI_KEY'            # the variable the card's key is handed in at launch - named in the config, never its value
PREFIX = 'card-'                       # cli:card-<id>
_MARK = '\x00key\x00'                  # stands in for the key while llm.endpoint says which header carries it
_TRIED: set = set()                    # harnesses whose install already failed in this process: not started again on every turn
ON = True                              # tests/conftest.py turns it off: a test's API card keeps its own loop and installs nothing


def harness_of(cfg: dict) -> str:
    "The card's chosen harness: Codex unless it names OpenCode."
    return h if (h := str((cfg or {}).get('harness') or '').strip().lower()) in HARNESSES else 'codex'


def _card(store, pick) -> dict | None:
    "The active, keyed, OpenAI-shaped AI card a pick names (connector:<id>, connector:<type>, or blank = the default brain), else None."
    from . import llm
    p = str(pick or '').strip() or llm.effective_pick(store, '')
    if not p.startswith('connector:'): return None
    want = p[10:]
    for c in store.list_connectors():
        if c['Type'] not in llm.AI_TYPES or c['Type'] in ('anthropic', 'chatgpt'): continue    # not the OpenAI shape a harness speaks
        if not (c['ConnectorId'] == int(want) if want.isdigit() else c['Type'] == want): continue
        return c if c['Active'] and (c['HasSecret'] or c['Type'] == 'ollama') else None
    return None


def _cfg(store, cid: int) -> tuple:
    "(type, config, key) of a card."
    full = store.get_connector(int(cid), with_secret=True) or {}
    try: cfg = json.loads(full.get('ConfigJson') or '{}')
    except ValueError: cfg = {}
    return full.get('Type') or '', cfg, full.get('Secret') or ''


def where(name: str, install: bool = True) -> str:
    """The harness CLI's path here, or ''. Missing, it is installed in the background as every CLI is (cliinstall.start) - only for the
    harness a card that needs it chose, once per process if it failed; meanwhile the agent keeps its own loop."""
    if not ON: return ''
    from . import cliinstall
    if (p := cliinstall.find(name)): return p
    st = cliinstall.state()
    if install and name not in _TRIED and cliinstall.plan(name) and st.get('phase') != 'installing':
        _TRIED.add(name); logger.info(f'harness: installing {name} for an AI card agent'); cliinstall.start(name)
    return ''


def road(store, pick) -> str:
    "The pick an API card's agent runs on: `cli:card-<id>` where its harness runs here, else the pick itself (apiagent's loop)."
    c = _card(store, pick)
    if not c: return str(pick or '')
    _, cfg, _ = _cfg(store, c['ConnectorId'])
    return f"cli:{PREFIX}{c['ConnectorId']}" if where(harness_of(cfg)) else str(pick or '')


def card_id(name: str) -> int | None:
    "5 for 'card-5' (or 'cli:card-5'); None for any other CLI name."
    n = str(name or '').removeprefix('cli:')
    return int(n[len(PREFIX):]) if n.startswith(PREFIX) and n[len(PREFIX):].isdigit() else None


def gears(cfg: dict, model: str) -> tuple:
    """(quick, normal, hard) for a card's agent (brainroute's three gears): its model thinking less, its model, its strong model - else its
    model thinking hard. Never its light model: Flash is for triage and one-shot jobs, not agent work (the owner's ruling)."""
    from .climodels import split_pick
    m, e = split_pick(model)
    strong = str(cfg.get('strong_model') or '').strip()
    return f'{m}@low', f'{m}@{e}' if e else m, strong or f'{m}@high'


def spell(store, pick: str, model: str) -> str:
    """A model the router chose (a card model, maybe '@effort') as this card's harness names it - '' for its light model, which agent work
    never runs on, so the gear picks instead."""
    cid = card_id(pick)
    if cid is None or not model: return model or ''
    from .climodels import split_pick
    _, cfg, _ = _cfg(store, cid)
    m, e = split_pick(model)
    if m and m == str(cfg.get('light_model') or '').strip(): return ''
    return oc_name(model) if harness_of(cfg) == 'opencode' else model


def oc_name(model: str) -> str:
    "'m@low' as OpenCode names it: 'card/m-low', an entry of its own in the card's opencode.json carrying that effort (opencode_config)."
    from .climodels import split_pick
    m, e = split_pick(model)
    return f'card/{m}-{e}' if e else f'card/{m}'


def folder(cid: int) -> Path:
    from . import config
    d = config.home() / 'harness' / f'card-{int(cid)}'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _provider(t: str, cfg: dict) -> tuple:
    "(base url, the header carrying the key ('' = a Bearer token), other headers, model) - read off llm.endpoint, the card's own calls."
    from . import llm
    from .climodels import split_pick
    m, _ = split_pick(cfg.get('model'))
    urls, headers, model = llm.endpoint(t, {**cfg, 'model': m}, _MARK)
    base = urls[0].split('?')[0].removesuffix('/chat/completions')
    keyed = next((k for k, v in headers.items() if _MARK in str(v)), '')
    return base, '' if keyed == 'Authorization' else keyed, {k: v for k, v in headers.items() if k != keyed}, model


def _toml(v) -> str:
    if isinstance(v, bool): return 'true' if v else 'false'
    if isinstance(v, dict): return '{ ' + ', '.join(f'{json.dumps(k)} = {_toml(x)}' for k, x in v.items()) + ' }'
    if isinstance(v, (list, tuple)): return '[' + ', '.join(_toml(x) for x in v) + ']'
    return json.dumps(str(v))             # a TOML basic string takes JSON's escapes


def codex_config(cid: int, name: str, base: str, header: str, extra: dict, model: str) -> str:
    """config.toml for a card's own CODEX_HOME: the card as Codex's model provider, and every road out of this computer but the card's own
    endpoint closed - nothing reaches OpenAI. Each switch is named where it is set."""
    prov = f'card{int(cid)}'
    p = {'name': name, 'base_url': base, 'wire_api': 'responses'}           # Codex speaks only the Responses API (chat was removed)
    if header: p['env_http_headers'] = {header: KEY_ENV}                   # Azure's api-key, Vertex's x-goog-api-key: read from the env
    else: p['env_key'] = KEY_ENV                                           # a Bearer token, read from the env at launch
    if extra: p['http_headers'] = extra
    top = {'model': model, 'model_provider': prov,
           'check_for_update_on_startup': False,      # the update check (it asks GitHub / OpenAI for the latest release)
           'web_search': 'disabled',                  # hosted web_search is OpenAI's tool: the model's own search or Taskuary's web tools
           'forced_login_method': 'api'}              # no ChatGPT login: the key in the env is the only sign-in
    tables = {
        'analytics': {'enabled': False},              # analytics upload
        'feedback': {'enabled': False},               # /feedback upload of logs
        'otel': {'exporter': 'none', 'trace_exporter': 'none', 'metrics_exporter': 'none', 'log_user_prompt': False},   # telemetry / OTEL
        # features that reach OpenAI's own services: ChatGPT apps/connectors, the plugin marketplace, hosted image generation, tool
        # suggestions, in-app updates, OpenAI's fast service tiers, skill dependencies fetched from the network
        'features': {'apps': False, 'plugins': False, 'remote_plugin': False, 'image_generation': False, 'tool_suggest': False,
                     'in_app_updates': False, 'fast_mode': False, 'ultrafast_mode': False, 'skill_mcp_dependency_install': False},
        'shell_environment_policy': {'exclude': [KEY_ENV]},     # the key never reaches a command the agent runs
        f'model_providers.{prov}': p,
    }
    out = [f'# Written by Taskuary for AI card {int(cid)} - rewritten on each start. The key is read from ${KEY_ENV}, never stored here.']
    out += [f'{k} = {_toml(v)}' for k, v in top.items()]
    for t, kv in tables.items(): out += ['', f'[{t}]', *(f'{k} = {_toml(v)}' for k, v in kv.items())]
    return '\n'.join(out) + '\n'


def opencode_config(name: str, base: str, header: str, extra: dict, model: str, strong: str) -> dict:
    """opencode.json for a card: the card as its one provider, its models with the efforts the gears ask for, and its own roads out closed
    (sharing, auto-update) - the rest is closed by its environment (row)."""
    opts = {'baseURL': base, 'apiKey': f'{{env:{KEY_ENV}}}'} if not header else {'baseURL': base, 'headers': {header: f'{{env:{KEY_ENV}}}'}}
    if extra: opts['headers'] = {**opts.get('headers', {}), **extra}
    # ...each model once as itself and once per effort (oc_name), so a gear is a model name - the one thing its command line takes
    models = {}
    for m in dict.fromkeys(x for x in (model, strong) if x):
        models[m] = {'name': m}
        models.update({f'{m}-{e}': {'id': m, 'name': f'{m} ({e})', 'options': {'reasoningEffort': e}} for e in ('low', 'medium', 'high')})
    return {'$schema': 'https://opencode.ai/config.json', 'model': f'card/{model}',
            'provider': {'card': {'npm': '@ai-sdk/openai-compatible', 'name': name, 'options': opts, 'models': models}},
            'enabled_providers': ['card'],     # no other provider is loaded
            'share': 'disabled',               # session sharing uploads to opencode.ai
            'autoupdate': False}               # the update check


def _write(path: Path, text: str):
    if not path.exists() or path.read_text(encoding='utf-8') != text: path.write_text(text, encoding='utf-8')


def row(store, name: str) -> dict | None:
    """The agent row `cli:card-<id>` runs (agents.agent_row): the card's harness CLI, its gears in the card's models, and its environment.
    None for any other name, or a card whose harness cannot run here."""
    cid = card_id(name)
    if cid is None: return None
    t, cfg, key = _cfg(store, cid)
    if not t: return None
    h = harness_of(cfg)
    if not (cmd := where(h, install=False)): return None
    from .clis import preset_args
    from .climodels import split_pick
    base, header, extra, model = _provider(t, cfg)
    e = split_pick(cfg.get('model'))[1]
    quick, normal, hard = gears(cfg, f'{model}@{e}' if e else model)
    d, label = folder(cid), f'{(store.get_connector(cid) or {}).get("Name") or t} (card {cid})'
    if h == 'codex':
        home = d / 'codex'; home.mkdir(exist_ok=True)
        _write(home / 'config.toml', codex_config(cid, label, base, header, extra, model))
        env = {'CODEX_HOME': str(home)}
    else:
        strong = split_pick(hard)[0] if cfg.get('strong_model') else ''
        f = d / 'opencode.json'
        _write(f, json.dumps(opencode_config(label, base, header, extra, model, strong), indent=2))
        quick, normal, hard = (oc_name(x) for x in (quick, normal, hard))
        # its own config and data folders, so the owner's other providers and sign-ins are not loaded, and nothing is fetched for them
        env = {'OPENCODE_CONFIG': str(f), 'XDG_CONFIG_HOME': str(d / 'config'), 'XDG_DATA_HOME': str(d / 'data'),
               'XDG_STATE_HOME': str(d / 'state'), 'XDG_CACHE_HOME': str(d / 'cache'),
               'OPENCODE_DISABLE_AUTOUPDATE': '1',          # the update check
               'OPENCODE_DISABLE_MODELS_FETCH': '1',        # models.dev catalogue download
               'OPENCODE_DISABLE_LSP_DOWNLOAD': '1',        # language servers fetched from the network
               'OPENCODE_DISABLE_DEFAULT_PLUGINS': '1',     # plugins installed from npm
               'OPENCODE_DISABLE_CLAUDE_CODE': '1'}         # the owner's ~/.claude prompts and skills are not read into a card's agent
    env[KEY_ENV] = key
    prof = {'cmd': cmd, 'args': preset_args(h), 'model': normal, 'light_model': quick, 'strong_model': hard, 'env': env, 'card': cid}
    return {'Name': name, 'Kind': 'general', 'Runner': 'cli', 'Config': json.dumps(prof)}


def line(store, c: dict) -> dict | None:
    """What an API card says of its agent's harness, for the card: {harness, choices, line}. None for a card no harness runs (Claude, the
    ChatGPT plan). An active card starts its chosen harness's install here, as its agent will need it."""
    from . import llm, cliinstall
    if c.get('Type') not in llm.AI_TYPES or c.get('Type') in ('anthropic', 'chatgpt'): return None
    try: cfg = json.loads(c.get('ConfigJson') or '{}')
    except ValueError: cfg = {}
    h = harness_of(cfg)
    on = bool(c.get('Active') and (c.get('HasSecret') or c.get('Type') == 'ollama'))
    p = where(h, install=on)
    st = cliinstall.state()
    if p: said = f'Its agent runs on {LABEL[h]}, pointed at this card - nothing goes anywhere else.'
    elif st.get('phase') == 'installing' and st.get('name') == h: said = f'Installing {LABEL[h]} for its agent - it uses Taskuary\'s own agent until then.'
    elif not on: said = f'Its agent will run on {LABEL[h]} once this card is on.'
    else: said = f"{LABEL[h]} can't run on this computer, so its agent uses Taskuary's own, simpler agent."
    return {'harness': h, 'choices': [{'value': k, 'label': LABEL[k]} for k in HARNESSES], 'line': said}
