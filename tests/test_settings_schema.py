"""The settings schema is one file both sides read, so the assistant and the Settings page can never
disagree about what a knob is called or what it takes (the rule lanes.json already keeps for lanes)."""
import unittest
from pathlib import Path
from taskuary import settings_schema

ROOT = Path(__file__).resolve().parents[1]


class SchemaTests(unittest.TestCase):
    def test_every_knob_has_a_group_a_label_and_a_type(self):
        k = settings_schema.knobs()
        self.assertGreater(len(k), 40)
        for key, meta in k.items():
            for field in ('group', 'label', 'type', 'desc'):
                self.assertTrue(meta.get(field), f'{key} lacks {field}')
            self.assertIn(meta['group'], settings_schema.GROUPS, key)
            if meta['type'] == 'select': self.assertTrue(meta.get('options'), f'{key} is a select with no options')

    def test_the_file_is_the_one_the_page_imports(self):
        view = (ROOT / 'website' / 'src' / 'SettingsView.jsx').read_text(encoding='utf-8')
        self.assertIn('settings_schema.json', view)
        self.assertNotIn('const KNOB_META = {', view)

    def test_describe_says_the_value_in_the_schemas_words(self):
        self.assertEqual(settings_schema.describe('intent_classify_enabled', '1'), 'Intent triage (Triage & routing): on')
        self.assertEqual(settings_schema.describe('intent_classify_enabled', '0'), 'Intent triage (Triage & routing): off')
        self.assertIn('Triage brain', settings_schema.describe('triage_ai', 'connector:80'))
        self.assertEqual(settings_schema.describe('no_such_key', 'x'), 'no_such_key: x')


if __name__ == '__main__':
    unittest.main()
