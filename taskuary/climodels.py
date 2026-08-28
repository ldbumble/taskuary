"""Which models a CLI agent can be pointed at - read from the CLI's own files, not typed here.

Codex writes the list its /model picker shows to $CODEX_HOME/models_cache.json (slug, display
name, the reasoning levels each supports, hidden ones flagged), and the model it is currently set
to lives in config.toml. A hand-typed list here said gpt-5 while the picker on the same machine
said GPT-5.6-Sol; the owner rightly asked what it was. Claude Code keeps no such file, so its
aliases stay static. A pick is spelled `model` or `model@effort` (gpt-5.4-mini@low); llm and
agents turn the effort into codex's -c model_reasoning_effort=<effort>.
"""
import json, os, re
from pathlib import Path

STATIC = {'claude': [{'id': m, 'label': m, 'desc': '', 'efforts': [], 'default_effort': ''}
                     for m in ('opus', 'sonnet', 'haiku', 'claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5')],
          'gemini': [{'id': m, 'label': m, 'desc': '', 'efforts': [], 'default_effort': ''} for m in ('gemini-2.5-pro', 'gemini-2.5-flash')]}
CODEX_FALLBACK = [{'id': 'gpt-5.5', 'label': 'GPT-5.5', 'desc': '', 'efforts': ['low', 'medium', 'high', 'xhigh'], 'default_effort': 'medium'}]


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


def catalog(cli: str) -> dict:
    """{models, current, choices} for one CLI. `choices` is the flat id list older pickers use."""
    if cli == 'codex':
        models = codex_models() or CODEX_FALLBACK
        return {'models': models, 'current': codex_current(), 'source': 'codex models_cache.json' if codex_models() else 'built-in',
                'choices': [m['id'] for m in models]}
    models = STATIC.get(cli, [])
    return {'models': models, 'current': {}, 'source': 'built-in', 'choices': [m['id'] for m in models]}


def split_pick(pick: str) -> tuple:
    """'gpt-5.4-mini@low' -> ('gpt-5.4-mini', 'low'); 'gpt-5.4-mini' -> ('gpt-5.4-mini', '')."""
    s = str(pick or '').strip()
    return tuple(s.split('@', 1)) if '@' in s else (s, '')
