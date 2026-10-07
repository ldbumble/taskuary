"""THE settings vocabulary, once. The Settings page (SettingsView.jsx) and the assistant (appfacts.py,
the setting look-ups) read the same taskuary/settings_schema.json, so a knob cannot be called one thing
on the page and another in the chat - the rule lanes.json already keeps for the lanes. The schema used
to live only in the JSX, which is why the assistant knew the pile and not one of the 52 knobs."""
import json, math
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).with_name('settings_schema.json')


@lru_cache(maxsize=1)
def _load() -> dict: return json.loads(_PATH.read_text(encoding='utf-8'))


def knobs() -> dict: return _load()['knobs']
def panel_owned() -> list: return _load()['panel_owned']
GROUPS = _load()['groups']


def _word(meta: dict, value) -> str:
    v = '' if value is None else str(value)
    if meta.get('type') == 'switch': return 'on' if v.strip().lower() in ('1', 'true', 'on') else 'off'
    return v or '(blank)'


def describe(key: str, value) -> str:
    """'Triage brain (Triage & agents): connector:80' - the label, the group, the value as the schema
    says it. An unknown key is said plainly rather than dressed up."""
    meta = knobs().get(key)
    if not meta: return f'{key}: {value}'
    return f"{meta['label']} ({meta['group']}): {_word(meta, value)}"


def refuse(key: str, value) -> str:
    """'' when `value` may be stored under `key`, else the sentence why not. A number knob takes 0 or more, or blank for its
    default: -5 days of Timeline said Saved and emptied the Timeline (the 2026-10-07 click-through)."""
    meta = knobs().get(key)
    if not meta or meta.get('type') != 'number': return ''
    v = str('' if value is None else value).strip()
    if not v: return ''
    try: n = float(v)
    except ValueError: n = None
    return '' if n is not None and math.isfinite(n) and n >= 0 else f"{meta['label']} takes a number, 0 or more - not {v!r}"
