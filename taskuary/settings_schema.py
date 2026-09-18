"""THE settings vocabulary, once. The Settings page (SettingsView.jsx) and the assistant (appfacts.py,
the setting look-ups) read the same taskuary/settings_schema.json, so a knob cannot be called one thing
on the page and another in the chat - the rule lanes.json already keeps for the lanes. The schema used
to live only in the JSX, which is why the assistant knew the pile and not one of the 52 knobs."""
import json
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).with_name('settings_schema.json')


@lru_cache(maxsize=1)
def _load() -> dict: return json.loads(_PATH.read_text(encoding='utf-8'))


def knobs() -> dict: return _load()['knobs']
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
