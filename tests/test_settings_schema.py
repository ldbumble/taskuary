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


    def test_every_ai_slot_is_owned_by_its_card_and_named_in_the_schema(self):
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
                self.assertTrue(knobs.get(key), f'{key} has no schema entry for search, a link or the Assistant to name it by')

    def test_no_setting_is_both_on_the_panel_and_a_row_and_the_page_speaks_plainly(self):
        """WHICH AI DOES WHAT (the owner, 2026-11-23): nine settings were drawn twice - a card, and a row "normally set on the card
        above; this row is the fallback if that panel cannot load". A panel's setting is named in the schema and has no row: no row
        text (`help`), and SettingsView draws no row for it. And the page's words are a person's, not the builder's."""
        owned, knobs = settings_schema.panel_owned(), settings_schema.knobs()
        self.assertEqual([k for k in owned if knobs[k].get('help') and knobs[k]['group'] == 'Which AI does what'], [], 'a panel setting carries row text')
        view = (ROOT / 'website' / 'src' / 'SettingsView.jsx').read_text(encoding='utf-8')
        self.assertIn('meta(s.Name).group === g && !PANEL_OWNED.has(s.Name)', view)
        self.assertNotIn('panelOk', view)
        for k in ('profile_brains', 'default_agent'): self.assertNotIn(k, knobs)
        page = [m for m in knobs.values() if m['group'] == 'Which AI does what']
        said = ' '.join(f"{m['label']} {m['desc']} {m.get('help', '')}" for m in page)
        for w in ('fallback if that panel', 'heart of the funnel', 'TWO BRAINS', 'TQ-', 'raw value', 'SOUL.md', '--model', 'model@effort'):
            self.assertNotIn(w, said)

    def test_every_settings_link_the_app_writes_opens_a_section_that_exists(self):
        "A section renamed leaves no link behind on its old name: the words the Assistant, the walk and the docs say all land."
        import re
        from urllib.parse import unquote
        files = [*(ROOT / 'taskuary').glob('*.py'), ROOT / 'taskuary' / 'words.json', *(ROOT / 'website' / 'src').glob('*.js*')]
        groups = {unquote(g) for f in files for g in re.findall(r'settings=config&group=([A-Za-z0-9%&]+?)(?:[&"\')\s]|$)', f.read_text(encoding='utf-8'))}
        self.assertIn('Which AI does what', groups)
        self.assertEqual(groups - set(settings_schema.GROUPS), set())

    def test_a_stamp_is_never_a_knob(self):
        # the page treats any key ending `_at` as machine state (`setup_walk_at`, `phone_morning_line_at`
        # and four others are all "when we last did this"), which only holds while no knob is named so
        self.assertEqual([k for k in settings_schema.knobs() if k.endswith('_at')], [])

    def test_describe_says_the_value_in_the_schemas_words(self):
        self.assertEqual(settings_schema.describe('intent_classify_enabled', '1'), 'Sort new mail with AI (Which AI does what): on')
        self.assertEqual(settings_schema.describe('intent_classify_enabled', '0'), 'Sort new mail with AI (Which AI does what): off')
        self.assertIn('AI that sorts your mail', settings_schema.describe('triage_ai', 'connector:80'))
        self.assertEqual(settings_schema.describe('no_such_key', 'x'), 'no_such_key: x')

    def test_your_mail_goes_to_is_gone_and_the_stored_setting_still_reads(self):
        """Triage picks no worker for a task (the owner, 2026-11-04), so "Your mail goes to" chose nothing: the row goes, and
        the setting with it (2026-11-26: nothing read it)."""
        from taskuary.store import DEFAULT_SETTINGS
        self.assertNotIn('default_profile', settings_schema.knobs())
        self.assertNotIn('Your mail goes to', (ROOT / 'taskuary' / 'settings_schema.json').read_text(encoding='utf-8'))
        self.assertNotIn('default_profile', DEFAULT_SETTINGS)
        view = (ROOT / 'website' / 'src' / 'SettingsView.jsx').read_text(encoding='utf-8')
        self.assertNotIn('m.type === "profile"', view); self.assertNotIn('profileNames', view)

    def test_the_top_search_finds_a_panel_by_what_it_holds(self):
        """The saved sign-ins are a panel, not a knob: "password" and "vault" found nothing in the top search (2026-11-10)."""
        from taskuary import search
        for q in ('password', 'vault', 'saved sign-ins', 'saved sign', 'saved passwords'):
            hrefs = [h['href'] for h in search._settings(q.split())]
            self.assertIn('#settings=config&group=Agent%20permissions&key=panel%3Asignins', hrefs, q)

    def test_a_panel_is_added_beside_the_setting_never_in_its_place(self):
        """"where do I change my signature" is the Email signature knob: the hand signature panel took the Assistant's link (CI, 2026-11-10).
        A panel joins for a word only it has ("hand signature", "password"), or a heading that says more ("saved sign") - and one whose own
        words hold a word typed joins BEHIND the knob, never dropped (the owner, 2026-11-10: "login" found no Saved sign-ins)."""
        from taskuary import search
        from taskuary.store import MemoryStore
        s, sig = MemoryStore(), '#settings=config&group=Replies&key=email_signature'
        for q in ('where do I change my signature', 'change my signature', 'signature'):
            got = [h['href'] for h in search.places(s, q)]
            self.assertEqual(got[0], sig, q)
            self.assertGreater(got.index('#settings=config&group=Replies&key=panel%3Ahandsig'), got.index(sig), q)
        self.assertIn('#settings=config&group=Replies&key=panel%3Ahandsig', [h['href'] for h in search.places(s, 'my hand signature')])
        self.assertEqual(search.places(s, 'saved passwords')[0]['title'], 'Saved sign-ins')
        self.assertEqual(search.places(s, 'saved sign')[0]['title'], 'Saved sign-ins')
        for k, p in settings_schema.panels().items():
            self.assertIn(p['group'], settings_schema.GROUPS, k)


if __name__ == '__main__':
    unittest.main()
