"""The docs print each knob's shipped default from settings_defaults.json (#87-#90).

The docs build runs in node and cannot import Python, so the defaults are copied into a JSON
file next to the schema: store.DEFAULT_SETTINGS, plus the few knobs whose fallback is a named
constant in code rather than a DEFAULT_SETTINGS entry. This keeps the copy honest: change a
default, or add a knob, and this fails until the file is regenerated.
"""
import importlib, json, unittest
from pathlib import Path

from taskuary.store import DEFAULT_SETTINGS

HERE = Path(__file__).resolve().parents[1] / 'taskuary'

# knobs read as `get_setting(key) or CONSTANT`: the constant IS the shipped default
CODE_DEFAULTS = {
    'funnel_hours': ('taskuary.funnel', 'HOURS_DEFAULT'),
    'funnel_max': ('taskuary.funnel', 'MAX_DEFAULT'),
    'meeting_grace_minutes': ('taskuary.funnel', 'STARTED_MIN'),
    'task_return_minutes': ('taskuary.processing_unread', 'RETURN_MINUTES'),
}


def expected() -> dict:
    knobs = json.loads((HERE / 'settings_schema.json').read_text(encoding='utf-8'))['knobs']
    out = {}
    for key in knobs:
        if key in DEFAULT_SETTINGS:
            out[key] = DEFAULT_SETTINGS[key]
        elif key in CODE_DEFAULTS:
            module, name = CODE_DEFAULTS[key]
            out[key] = str(getattr(importlib.import_module(module), name))
    return out


def regenerate() -> None:
    path = HERE / 'settings_defaults.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['defaults'] = expected()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


class SettingsDefaultsJson(unittest.TestCase):
    def test_the_copy_matches_the_shipped_defaults(self):
        got = json.loads((HERE / 'settings_defaults.json').read_text(encoding='utf-8'))['defaults']
        self.assertEqual(got, expected(), 'settings_defaults.json is out of date - regenerate it with:\n'
                         '  python -c "from tests.test_settings_defaults_json import regenerate; regenerate()"')

    def test_every_code_default_is_a_knob_with_no_store_default(self):
        knobs = json.loads((HERE / 'settings_schema.json').read_text(encoding='utf-8'))['knobs']
        for key in CODE_DEFAULTS:
            with self.subTest(key=key):
                self.assertIn(key, knobs)
                self.assertNotIn(key, DEFAULT_SETTINGS)


if __name__ == '__main__':
    unittest.main()
