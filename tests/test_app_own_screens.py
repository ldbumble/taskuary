"""THE APP'S OWN ACTS ARE ITS OWN SCREENS (the owner, 2026-10-23: "i asked assistant to update taskuary and it pulled up general agent
instead of settings page updates... why?"). Updates was a bare "#settings=updates" in a list of addresses, the phone was told of no screen
at all, and every louder line pointed an act with no tool of its own at an agent. The model reads intent - so what it reads has to say
what each screen is for, on the desk and on the phone, and the index has to find it by any words for it. No word list decides anything."""
import unittest

from taskuary import concierge, search, toolcatalog, words
from tests import assistant_queries as Q

UPDATES = words.href('updates')


class TheModelIsToldWhatEachScreenIsFor(unittest.TestCase):
    def setUp(self): self.s = Q._world()

    def test_the_desk_names_updates_by_what_it_does_and_links_it_with_its_button_lit(self):
        block = concierge.pages_block(self.s)
        line = next(l for l in block.splitlines() if UPDATES in l)
        self.assertIn(words.PLACES['updates']['does'], line)
        self.assertTrue(UPDATES.endswith('&key=update'))           # SettingsView lights the Update button (UpdateCard's data-tq-knob)
        for p in (p for p in words.PLACES.values() if p.get('does')): self.assertIn(f"{p['href']} - {p['name']}: {p['does']}", block)
        self.assertIn(concierge.THIS_APP, block)

    def test_the_phone_knows_the_same_screens_by_name_and_is_given_no_link(self):
        with concierge.delivering(concierge.PHONE): system = concierge._system(self.s)
        self.assertIn('APP SCREENS', system); self.assertNotIn('APP PAGES', system)
        self.assertIn(f"{words.name('updates')}: {words.PLACES['updates']['does']}", system)
        self.assertIn(concierge.THIS_APP, system)
        self.assertNotRegex(concierge.phone_screens(), r'#(settings|profiles|report|connector)')

    def test_using_the_app_is_never_an_agents_job_but_changing_its_code_still_is(self):
        self.assertIn('never handed to an agent', concierge.THIS_APP)
        self.assertIn("Changing Taskuary's CODE is a coding job", concierge.THIS_APP)
        self.assertIn('update', toolcatalog.DECISIONS['regular_agent'].split('Never for', 1)[1])


class TheIndexFindsUpdatesByAnyWordsForIt(unittest.TestCase):
    def setUp(self): self.s = Q._world()

    def test_every_way_of_saying_it_finds_updates_first(self):
        for q in ('update', 'update taskuary', 'check for updates', 'install the new version', 'upgrade the app',
                  'install the latest release', 'reinstall taskuary'):
            with self.subTest(q=q): self.assertEqual(search.places(self.s, q)[0]['href'], UPDATES)

    def test_on_a_phone_the_look_up_names_the_screen_instead_of_linking_it(self):
        desk = concierge.read_op(self.s, 'app.find', {'query': 'update taskuary'})
        with concierge.delivering(concierge.PHONE): phone = concierge.read_op(self.s, 'app.find', {'query': 'update taskuary'})
        self.assertIn(f'link it as [{words.name("updates")}]({UPDATES})', desk)
        self.assertNotIn('](#', phone); self.assertIn(f"name it, at their desk: {words.name('updates')}", phone)
        # a setting is named by its group too: "Sound when ..." alone is no place a person can find
        with concierge.delivering(concierge.PHONE): knob = concierge.read_op(self.s, 'app.find', {'query': 'sound'})
        self.assertRegex(knob.splitlines()[0], r'at their desk: Settings → Notifications → ')


class UpdateTaskuaryEndToEnd(unittest.TestCase):
    """The deterministic road under a good answer: the desk opens Updates with its button lit; the phone says where, with no link and no agent."""
    def turn(self, phone: bool): return Q.ideal_turn(next(q for q in Q.CASES if q.text == 'update taskuary' and q.phone == phone))

    def test_desk(self):
        r = self.turn(False)
        self.assertEqual(r['grade'], 'right', r)
        self.assertIn(f'link:{UPDATES}', r['got']); self.assertFalse([g for g in r['got'] if g.startswith(('new:', 'proposal:', 'decision:'))])

    def test_phone(self):
        r = self.turn(True)
        self.assertEqual(r['grade'], 'right', r)
        self.assertNotIn('](#', r['say']); self.assertIn(words.name('updates'), r['say'])
        self.assertFalse([g for g in r['got'] if g.startswith(('new:', 'proposal:', 'decision:', 'link:'))])



class NoAppAskEndsAtAnAgent(unittest.TestCase):
    """An ask about the app itself - a setting, a connection, a brain, its update, or one it does not have - never comes out as a hand-off:
    the owner's rule of 2026-10-23 (app problems and "update things" are not a task or a general agent's)."""
    def test_settings_connections_and_bring_ups_on_desk_and_phone(self):
        asks = [q for q in Q.CASES if q.cat in ('settings', 'connectors', 'bring-up') or (q.phone and q.table is None)]
        self.assertGreater(len(asks), 40)
        for q in asks:
            with self.subTest(q=q.text, phone=q.phone):
                r = Q.ideal_turn(q)
                self.assertFalse([g for g in r['got'] if g.startswith(('new:', 'light:regular_agent', 'light:coding_agent'))], r)
                self.assertNotIn('Send to agent', r['say'])


if __name__ == '__main__': unittest.main()
