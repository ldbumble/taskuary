"""Every "Settings → X" the app prints names a place the Settings page actually has. The Ollama, OpenRouter
and Meta how-tos sent you to "Settings → Triage & routing" to pick a brain that lives in "Triage & agents",
and the Assistant tab brain's help put the default coding agent under "Coding agent agent" - the same place
written four ways, two of them wrong (the 2026-10-11 copy audit). The places come from the files the page
draws itself from (settings_schema.json, SettingsView.jsx's PAGES, settingsMap.js), never a list kept here."""
import json, re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC, SCHEMA = ROOT / 'website' / 'src', ROOT / 'taskuary' / 'settings_schema.json'
REF = re.compile(r'Settings → ')
# another product's own Settings ("GitHub → Settings →", "System Settings →", "In Element: Settings →")
THEIRS = re.compile(r'(→|:|\b[A-Z][a-z]+)\s*$')


def _places():
    s = json.loads(SCHEMA.read_text(encoding='utf-8'))
    view, smap = (SRC / 'SettingsView.jsx').read_text(encoding='utf-8'), (SRC / 'settingsMap.js').read_text(encoding='utf-8')
    pages = re.findall(r'\w+: \{ title: "([^"]+)", icon:', view)
    secs = [x for arr in re.findall(r'export const \w+_SECTIONS = \[([^\]]*)\]', smap) for x in re.findall(r'"([^"]+)"', arr)]
    return s, set(s['groups']) | set(pages) | set(secs) | {'Profiles'} | {k['label'] for k in s['knobs'].values()}


WORDS = ROOT / 'taskuary' / 'words.json'
_NAMES = {k: v['name'] for k, v in json.loads(WORDS.read_text(encoding='utf-8'))['places'].items() if not k.startswith('_')}
# A PLACE IS NAMED BY ITS ID NOW (words.json): `${placeName("sorting")}` reads as the path it prints, and words.json's own names
# are references like any other - words.js, the reader, only explains the rule
_PLACE = re.compile(r'\$\{\s*placeName\(\s*"(\w+)"\s*\)\s*\}|placeName\(\s*"(\w+)"\s*\)')


def _refs():
    "(file, text before, the place named) for every reference that is ours, `Configuration →` stepped through"
    for p in [*sorted(SRC.rglob('*.js')), *sorted(SRC.rglob('*.jsx')), SCHEMA, WORDS]:
        if p.name == 'words.js': continue
        s = _PLACE.sub(lambda m: _NAMES.get(m.group(1) or m.group(2), m.group(0)), p.read_text(encoding='utf-8'))
        for m in REF.finditer(s):
            pre = s[max(0, m.start() - 80):m.start()]
            if THEIRS.search(pre): continue
            after = s[m.end():m.end() + 80]
            if after.startswith('Configuration → '): after = after[len('Configuration → '):]
            yield p.name, pre, after


class SettingsPathTests(unittest.TestCase):
    def test_every_settings_path_names_a_place_that_exists(self):
        _, places = _places()
        self.assertIn('How mail is sorted', places)
        bad = [(f, a[:40]) for f, _, a in _refs() if not any(re.match(re.escape(n) + r'(?![\w&])', a) for n in places)]
        self.assertEqual(bad, [])

    def test_pick_a_brain_points_where_the_brain_pickers_are(self):
        s, _ = _places()
        home, seen = s['knobs']['triage_ai']['group'], 0
        for f, pre, after in _refs():
            if not re.search(r'\bpick it\b', pre.split('.')[-1], re.I): continue
            seen += 1
            self.assertTrue(after.startswith(home), f'{f}: "pick it under Settings → {after[:30]}" - the brains are in {home}')
        self.assertGreaterEqual(seen, 5)

    def test_schema_help_says_where_the_other_defaults_live(self):
        s = json.loads(SCHEMA.read_text(encoding='utf-8'))
        k = s['knobs']
        for key in ('triage_ai', 'default_agent'): self.assertEqual(k[key]['group'], k['concierge_ai']['group'])
        self.assertNotIn('(Triage & routing)', k['concierge_ai']['help'])
        self.assertNotIn('(Coding agent)', k['concierge_ai']['help'])
        # one section now (U19, "How mail is sorted"): the brain and the switch it drives sit together, the panel above the knobs
        self.assertEqual(k['triage_ai']['group'], k['intent_classify_enabled']['group'])
        self.assertNotIn('Triage & agents', s['groups']); self.assertNotIn('Triage & routing', s['groups'])
        self.assertNotIn('brain below', k['intent_classify_enabled']['help'])


if __name__ == '__main__':
    unittest.main()
