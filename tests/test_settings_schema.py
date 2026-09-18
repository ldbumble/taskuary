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

    def test_every_ai_slot_is_owned_by_its_card_and_has_a_fallback_row(self):
        """A slot the AI-defaults panel draws must be named in `panel_owned`, or the Settings page
        offers it a SECOND time as a bare box - and since a slot key carries no KNOB_META entry of
        its own by default, that box lands in the empty "Other" group with the raw key for a label.
        `assistant_ai` did it (d3bde8bd), then `judge_ai` did it again once aidefaults grew a fifth
        slot and the page's hand-written set did not (the owner, 2026-09-18: "what is the other
        settings in configuration"). The list is in the schema now and this is what keeps it true."""
        from taskuary import aidefaults
        owned, knobs = settings_schema.panel_owned(), settings_schema.knobs()
        for slot in aidefaults.SLOTS:
            for key in (slot['key'], slot.get('model_setting')):
                if not key: continue
                self.assertIn(key, owned, f'{key} is drawn as a card but the knob list still offers it')
                self.assertTrue(knobs.get(key), f'{key} has no schema entry to fall back to when the panel fails')

    def test_a_stamp_is_never_a_knob(self):
        # the page treats any key ending `_at` as machine state (`setup_walk_at`, `phone_morning_line_at`
        # and four others are all "when we last did this"), which only holds while no knob is named so
        self.assertEqual([k for k in settings_schema.knobs() if k.endswith('_at')], [])

    def test_describe_says_the_value_in_the_schemas_words(self):
        self.assertEqual(settings_schema.describe('intent_classify_enabled', '1'), 'Intent triage (Triage & routing): on')
        self.assertEqual(settings_schema.describe('intent_classify_enabled', '0'), 'Intent triage (Triage & routing): off')
        self.assertIn('Triage brain', settings_schema.describe('triage_ai', 'connector:80'))
        self.assertEqual(settings_schema.describe('no_such_key', 'x'), 'no_such_key: x')


if __name__ == '__main__':
    unittest.main()
