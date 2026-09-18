"""Which models a CLI agent can be pointed at - read from the CLI's own files, not typed here.

Codex writes the list its /model picker shows to $CODEX_HOME/models_cache.json (slug, display
name, the reasoning levels each supports, hidden ones flagged), and the model it is currently set
to lives in config.toml. A hand-typed list here said gpt-5 while the picker on the same machine
said GPT-5.6-Sol; the owner rightly asked what it was. Claude Code keeps no such file, so its
aliases stay static. A pick is spelled `model` or `model@effort` (gpt-5.4-mini@low); llm and
agents turn the effort into codex's -c model_reasoning_effort=<effort>.
"""
import json, os, re, shutil, subprocess
from functools import lru_cache
from pathlib import Path
try:
    import tomllib
except ImportError:
    import tomli as tomllib

# Only the stable ALIASES, and only as a fallback: the real list is claude_models() below, read from
# Claude Code's own catalog. Spelling ids here is what left a stale `claude-haiku-4-5` and no Fable at
# all in the picker while /model on the same machine said otherwise (the owner, 2026-09-18).
STATIC = {'claude': [{'id': m, 'label': m, 'desc': '', 'efforts': [], 'default_effort': ''}
                     for m in ('opus', 'sonnet', 'haiku')],
          'gemini': [{'id': m, 'label': m, 'desc': '', 'efforts': [], 'default_effort': ''} for m in ('gemini-2.5-pro', 'gemini-2.5-flash')],
          # Verified against Qwen Code 0.23.4's QWEN_OAUTH_MODELS. API-provider
          # configurations replace this alias with their own model ids below.
          'qwen': [{'id': 'coder-model', 'label': 'Qwen OAuth coding model',
                    'desc': 'Requires Qwen OAuth sign-in', 'efforts': [], 'default_effort': ''}],
          # OpenCode 1.18.31's provider catalog uses provider/model, including case.
          # These are suggestions, not a change to the owner's selected provider.
          'opencode': [{'id': m, 'label': m, 'desc': 'Connect this provider in OpenCode first',
                        'efforts': [], 'default_effort': ''} for m in (
                            'deepseek/deepseek-v4-pro', 'deepseek/deepseek-v4-flash',
                            'zai/glm-5.3', 'zhipuai/glm-5.3',
                            'minimax/MiniMax-M3', 'minimax-cn/MiniMax-M3')],
          # Kimi Code 0.43.1 --model takes a CONFIG ALIAS. /login provisions
          # these aliases; customized installations use their config.toml below.
          'kimi': [{'id': m, 'label': m, 'desc': 'Provisioned by Kimi /login',
                    'efforts': [], 'default_effort': ''} for m in (
                        'kimi-code/kimi-for-coding', 'kimi-code/k3', 'kimi-code/kimi-for-coding-highspeed')],
          # Cursor's available set is plan-dependent. These are the CLI's documented portable
          # choices; `auto` remains valid as its account-aware router when a named model is not.
          'cursor-agent': [{'id': m, 'label': m, 'desc': '', 'efforts': [], 'default_effort': ''}
                           for m in ('auto', 'gpt-5', 'sonnet-4-thinking')],
          'cursor': [{'id': m, 'label': m, 'desc': '', 'efforts': [], 'default_effort': ''}
                     for m in ('auto', 'gpt-5', 'sonnet-4-thinking')],
          # Muse Spark, standard tier first: the -contributor ids cost ~12x less because prompts and
          # completions train Meta's products, so nothing here picks one for the owner. `efforts` is
          # deliberately EMPTY even though muse has reasoning levels - the @effort pick is translated
          # to codex's `-c model_reasoning_effort=`, and muse spells it --reasoning-effort, so
          # offering the levels would emit a flag muse does not have.
          'muse': [{'id': 'muse-spark-1.3', 'label': 'Muse Spark 1.3', 'desc': 'newest; standard (private) tier', 'efforts': [], 'default_effort': ''},
                   {'id': 'muse-spark-1.2', 'label': 'Muse Spark 1.2', 'desc': 'standard (private) tier', 'efforts': [], 'default_effort': ''},
                   {'id': 'muse-spark-1.2-contributor', 'label': 'Muse Spark 1.2 (contributor)',
                    'desc': 'far cheaper - Meta trains on your prompts and completions', 'efforts': [], 'default_effort': ''}]}
CODEX_FALLBACK = [{'id': 'gpt-5.5', 'label': 'GPT-5.5', 'desc': '', 'efforts': ['low', 'medium', 'high', 'xhigh'], 'default_effort': 'medium'}]
# Copilot retrieves account policy at startup, but its installed SDK is still the authority for
# model ids this CLI build understands. This fallback is used only when that declaration cannot
# be read (a standalone binary rather than the npm package). `auto` lets Copilot choose from the
# owner's actual entitlement and is therefore the safest first explicit choice.
COPILOT_FALLBACK = ['auto', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-5.3-codex', 'gpt-5.2-codex',
                    'claude-opus-4.7', 'claude-sonnet-4.6', 'claude-haiku-4.5']
DEVIN_FALLBACK = ['claude-opus-5', 'claude-sonnet-5', 'gpt-6-astra', 'gpt-5.6-sol',
                  'gpt-5.6-terra', 'gpt-5.6-luna', 'gemini-3.8-flash', 'swe-2',
                  'swe-1.7-lightning', 'adaptive', 'gpt-5.4', 'gpt-5.4-mini',
                  'claude-sonnet-4.6', 'claude-haiku-4.5', 'gemini-3.1-pro']


def _items(ids, labels=None, source='') -> list:
    labels = labels or {}
    return [{'id': m, 'label': labels.get(m) or m, 'desc': source,
             'efforts': [], 'default_effort': ''} for m in ids]


def parse_devin_models(text: str) -> list:
    """Family choices from `devin models list`.

    Devin prints every priced reasoning variant below a non-indented family heading. The family
    id itself is accepted by --model and keeps the picker usable (49 choices on this account,
    rather than hundreds of low/high/fast combinations).
    """
    out, seen = [], set()
    for line in str(text or '').splitlines():
        if not line or line[:1].isspace(): continue
        m = re.fullmatch(r'(.+?) \(([a-z0-9][a-z0-9._-]*)\)', line.strip())
        if not m or m.group(2) in seen: continue
        seen.add(m.group(2))
        out.append({'id': m.group(2), 'label': m.group(1), 'desc': '',
                    'efforts': [], 'default_effort': ''})
    return out


@lru_cache(maxsize=4)
def _devin_models(exe: str) -> list:
    if not exe: return []
    try:
        p = subprocess.run([exe, 'models', 'list'], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=20)
        return parse_devin_models((p.stdout or '') + '\n' + (p.stderr or '')) if p.returncode == 0 else []
    except Exception:
        # Test/runtime isolation may deliberately forbid child processes. A model picker is not
        # allowed to take the whole Connections or Settings API down with it.
        return []


def devin_models() -> list:
    """The models this signed-in Devin account says it can use, cached for this server run."""
    return _devin_models(shutil.which('devin') or '') or _items(DEVIN_FALLBACK)


def parse_copilot_models(text: str) -> list:
    """Model ids advertised by the installed Copilot SDK's HELP_VISIBLE_MODELS declaration."""
    m = re.search(r'HELP_VISIBLE_MODELS:\s*\((.*?)\)\[\]', str(text or ''), re.S)
    ids = re.findall(r'["\']([^"\']+)["\']', m.group(1)) if m else []
    return _items(list(dict.fromkeys(['auto', *ids])))


@lru_cache(maxsize=4)
def _copilot_models(exe: str) -> list:
    candidates = []
    if exe:
        base = Path(exe).parent
        candidates += [base / 'node_modules' / '@github' / 'copilot' / 'sdk' / 'index.d.ts',
                       base.parent / 'lib' / 'node_modules' / '@github' / 'copilot' / 'sdk' / 'index.d.ts']
    for path in candidates:
        try:
            found = parse_copilot_models(path.read_text(encoding='utf-8', errors='replace'))
            if found: return found
        except OSError:
            pass
    return _items(COPILOT_FALLBACK)


def copilot_models() -> list:
    """Models understood by this installed Copilot CLI build (account policy is enforced by it)."""
    return _copilot_models(shutil.which('copilot') or '')


def claude_home() -> Path: return Path(os.getenv('CLAUDE_CONFIG_DIR') or Path.home() / '.claude')


def _claude_granted() -> list:
    """Models this account was granted on top of the catalog - the [1m] long-context variants."""
    for p in (claude_home() / '.claude.json', Path.home() / '.claude.json'):
        try: rows = json.loads(p.read_text(encoding='utf-8', errors='replace')).get('additionalModelOptionsCache') or []
        except (OSError, ValueError): continue
        return [{'id': r['value'], 'label': r.get('label') or r['value'], 'desc': (r.get('description') or '')[:120],
                 'efforts': [], 'default_effort': ''} for r in rows if isinstance(r, dict) and r.get('value')]
    return []


def claude_models() -> list:
    """The /model list, as Claude Code cached it.

    It writes a catalog per surface under cache/model-catalog/ and leaves the older file behind when a
    signed-in account refetches, so the newest `fetchedAt` wins. `efforts` is deliberately EMPTY even
    though every model lists reasoning levels: an @effort pick is translated into codex's
    `-c model_reasoning_effort=`, and Claude Code takes its effort from settings.json, not from a flag.
    """
    best, models = -1.0, []
    for p in sorted(claude_home().glob('cache/model-catalog/*.json')):
        try: d = json.loads(p.read_text(encoding='utf-8', errors='replace'))
        except (OSError, ValueError): continue
        when = float(d.get('fetchedAt') or 0)
        if when < best: continue
        rows = ((d.get('catalog') or {}).get('config') or {}).get('models') or []
        found = [{'id': m['id'], 'label': m.get('name') or m['id'], 'desc': (m.get('description') or '')[:120],
                  'efforts': [], 'default_effort': ''} for m in rows if isinstance(m, dict) and m.get('id')]
        if found: best, models = when, found
    seen = {m['id'] for m in models}
    return models + [m for m in _claude_granted() if m['id'] not in seen] if models else []


def codex_home() -> Path: return Path(os.getenv('CODEX_HOME') or Path.home() / '.codex')


def codex_models() -> list:
    """The /model list, as Codex cached it: visible models by priority, each with its reasoning levels."""
    p = codex_home() / 'models_cache.json'
    try: d = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError): return []
    out = []
    for m in sorted(d.get('models') or [], key=lambda m: m.get('priority') or 999):
        if (m.get('visibility') or 'list') != 'list' or not m.get('slug'): continue
        out.append({'id': m['slug'], 'label': m.get('display_name') or m['slug'], 'desc': (m.get('description') or '')[:120],
                    'efforts': [l.get('effort') for l in (m.get('supported_reasoning_levels') or []) if l.get('effort')],
                    'default_effort': m.get('default_reasoning_level') or ''})
    return out


def codex_current() -> dict:
    """What Codex itself runs with (config.toml) - the sensible first suggestion."""
    try: text = (codex_home() / 'config.toml').read_text(encoding='utf-8')
    except OSError: return {}
    m = re.search(r'^\s*model\s*=\s*"([^"]+)"', text, re.M); e = re.search(r'^\s*model_reasoning_effort\s*=\s*"([^"]+)"', text, re.M)
    return {k: v for k, v in (('model', m and m.group(1)), ('effort', e and e.group(1))) if v}


def _configured_models(cli: str) -> tuple:
    """Read only model identifiers/labels, never return provider keys or endpoints.

    Re-read on each request so finishing /login or changing a model needs no restart.
    These are user-level suggestions; a project or per-run override can still win.
    """
    try:
        if cli == 'kimi':
            path = Path(os.getenv('KIMI_CODE_HOME') or Path.home() / '.kimi-code') / 'config.toml'
            data = tomllib.loads(path.read_text(encoding='utf-8'))
            entries = data.get('models') or {}
            ids = [alias for alias, m in entries.items() if isinstance(m, dict) and m.get('model') and m.get('provider')]
            labels = {alias: entries[alias].get('display_name') for alias in ids}
            current = data.get('default_model')
        else:
            path = Path(os.getenv('QWEN_HOME') or Path.home() / '.qwen') / 'settings.json'
            data = json.loads(path.read_text(encoding='utf-8'))
            auth = data.get('security', {}).get('auth', {}).get('selectedType')
            if auth == 'qwen-oauth': return [], {}, ''
            entries = (data.get('modelProviders') or {}).get(auth, [])
            ids = [m['id'] for m in entries if isinstance(m, dict) and isinstance(m.get('id'), str)]
            labels = {m['id']: m.get('name') for m in entries if isinstance(m, dict) and m.get('id') in ids}
            current = (data.get('model') or {}).get('name')
            if current and current not in ids: ids.append(current)
        return _items(ids, labels), {'model': current} if current else {}, f'{cli} {path.name}'
    except (OSError, ValueError, TypeError, AttributeError):
        return [], {}, ''


def catalog(cli: str) -> dict:
    """{models, current, choices} for one CLI. `choices` is the flat id list older pickers use."""
    if cli == 'codex':
        models = codex_models() or CODEX_FALLBACK
        return {'models': models, 'current': codex_current(), 'source': 'codex models_cache.json' if codex_models() else 'built-in',
                'choices': [m['id'] for m in models]}
    if cli == 'copilot':
        models = copilot_models()
        return {'models': models, 'current': {}, 'source': 'installed Copilot SDK',
                'choices': [m['id'] for m in models]}
    if cli == 'devin':
        models = devin_models()
        return {'models': models, 'current': {}, 'source': 'devin models list' if models else 'unavailable',
                'choices': [m['id'] for m in models]}
    if cli in ('qwen', 'kimi'):
        models, current, source = _configured_models(cli)
        if not models: models, source = STATIC[cli], 'built-in'
        return {'models': models, 'current': current, 'source': source or 'built-in',
                'choices': [m['id'] for m in models]}
    if cli == 'claude':
        models = claude_models()
        return {'models': models or STATIC['claude'], 'current': {},
                'source': 'claude model catalog' if models else 'built-in',
                'choices': [m['id'] for m in (models or STATIC['claude'])]}
    models = STATIC.get(cli, [])
    return {'models': models, 'current': {}, 'source': 'built-in', 'choices': [m['id'] for m in models]}


def split_pick(pick: str) -> tuple:
    """'gpt-5.4-mini@low' -> ('gpt-5.4-mini', 'low'); 'gpt-5.4-mini' -> ('gpt-5.4-mini', '')."""
    s = str(pick or '').strip()
    return tuple(s.split('@', 1)) if '@' in s else (s, '')
