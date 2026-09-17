"""The scripted walk: every part of the app, one stop per turn, no AI anywhere in it.

The chip that opens this used to open an AI-led walk-through, which could not run before an AI was
connected - which is exactly when somebody presses it. So the stops are static text plus store
reads, and a typed question is an ordinary assistant turn that happens beside the walk rather than
inside it.
"""
import unittest

from fastapi.testclient import TestClient
from taskuary import server, setup, walk
from taskuary.store import MemoryStore

c = TestClient(server.app)

TABS = {'Assistant', 'Board', 'Tasks', 'Review', 'Reports', 'Connections', 'Docs', 'Settings', 'Hub'}


def _fresh():
    return MemoryStore()


class TheStopsTests(unittest.TestCase):
    def test_the_first_five_stops_are_the_checklist_itself(self):
        """Two surfaces, one source. A walk that listed its own five would be a second list to keep
        in step, and the second one loses."""
        s = _fresh()
        st = walk.state(s)
        keys = [x['key'] for x in st['stops']]
        self.assertEqual(keys[:5], [x['key'] for x in setup.state(s)['steps']])
        self.assertEqual(st['total'], len(walk.STOPS))
        self.assertGreaterEqual(st['total'], 14)

    def test_every_stop_says_what_you_can_do_there(self):
        """The point of a stop is the list of real things, not a paragraph about the tab."""
        for stop in walk.state(_fresh())['stops']:
            self.assertTrue(stop['can'], stop['key'])
            for line in stop['can']:
                self.assertTrue(line['text'].strip(), stop['key'])
                if line['goto'] is not None:
                    self.assertIn(line['goto']['tab'], TABS, stop['key'])
            self.assertIn(stop['goto']['tab'], TABS, stop['key'])

    def test_a_stop_never_states_a_fact_the_panel_would_contradict(self):
        s = _fresh()
        by = {x['key']: x for x in walk.state(s)['stops']}
        self.assertFalse(by['ai']['done'])
        cid = s.get_connector_by_type('anthropic')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'sk-x', 'Active': 1}, 't')
        by = {x['key']: x for x in walk.state(s)['stops']}
        self.assertTrue(by['ai']['done'])
        self.assertEqual(by['ai']['detail'],
                         next(x['detail'] for x in setup.state(s)['steps'] if x['key'] == 'ai'))

    def test_the_facts_count_what_is_really_connected(self):
        """The facts line is the reason a stop cannot lie: it counts, it does not assert. Written
        as a DELTA rather than an absolute, because what a fresh MemoryStore seeds as active is not
        this test's business and a hardcoded "none yet" would break the day a seed changes."""
        s = _fresh()
        fact = lambda: next(x for x in walk.state(s)['stops'] if x['key'] == 'connections')['facts']
        before = fact()
        cid = s.get_connector_by_type('outlook')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1}, 't')
        s.save_source({'Channel': 'email', 'Address': 'me@ours.com', 'ConnectorId': cid, 'Active': 1}, 't')
        after = fact()
        self.assertNotEqual(before, after)
        self.assertIn('connected', after)
        self.assertIn('Outlook', after)

    def test_every_tab_stop_shows_the_tab_and_no_setup_step_does(self):
        """A picture of a form you are filling in below it is noise. A picture of a tab you have
        never opened is the whole reason the tour exists."""
        by = {x['key']: x for x in walk.state(_fresh())['stops']}
        for key in ('owner', 'ai', 'models', 'inbound', 'sync'):
            self.assertIsNone(by[key].get('image'), key)
        for key in ('connections', 'docs', 'settings', 'board', 'tasks', 'review', 'reports',
                    'assistant', 'hub'):
            self.assertEqual(by[key]['image'], f'/walk/{key}.png')

    def test_nothing_on_this_road_can_reach_a_model(self):
        """The whole reason the walk exists is that the old one needed an AI to explain how to
        connect an AI. What is forbidden is REACHING one - importing or calling it. Naming it in a
        comment is allowed on purpose: the first draft of this banned the bare word and so banned
        the docstring that explained the design."""
        src = (__import__('pathlib').Path(walk.__file__)).read_text(encoding='utf-8')
        for banned in ('import llm', 'from .llm', 'import compose', 'from .compose',
                       'import concierge', 'from .concierge',
                       'llm.', 'compose.', 'concierge.', 'build_llm'):
            self.assertNotIn(banned, src)


class KeepingYourPlaceTests(unittest.TestCase):
    def test_the_position_survives_a_reload(self):
        s = _fresh()
        self.assertEqual(walk.state(s)['at'], 0)
        walk.go(s, 6, 't')
        self.assertEqual(walk.state(s)['at'], 6)

    def test_reaching_the_end_clears_it_so_the_next_press_starts_over(self):
        s = _fresh()
        walk.go(s, len(walk.STOPS) - 1, 't')
        self.assertEqual(walk.state(s)['at'], len(walk.STOPS) - 1)
        walk.go(s, len(walk.STOPS), 't')
        self.assertEqual(walk.state(s)['at'], 0)

    def test_a_position_off_the_end_of_the_list_is_clamped_not_crashed(self):
        """The list gets stops added and removed; a stored number outlives the list it indexed."""
        s = _fresh()
        s.set_setting(walk.AT, '999', 't')
        self.assertEqual(walk.state(s)['at'], 0)

    def test_reset_returns_to_the_first_stop(self):
        s = _fresh()
        walk.go(s, 4, 't')
        walk.reset(s, 't')
        self.assertEqual(walk.state(s)['at'], 0)


class TheEndpointsTests(unittest.TestCase):
    def tearDown(self):
        c.post('/api/setup/walk/reset')

    def test_it_answers_the_shape_the_card_reads(self):
        d = c.get('/api/setup/walk').json()
        for k in ('stops', 'at', 'total'):
            self.assertIn(k, d)
        for stop in d['stops']:
            for k in ('key', 'title', 'blurb', 'can', 'goto', 'n'):
                self.assertIn(k, stop, stop.get('key'))

    def test_moving_sticks(self):
        self.assertEqual(c.post('/api/setup/walk', json={'at': 7}).json()['at'], 7)
        self.assertEqual(c.get('/api/setup/walk').json()['at'], 7)

    def test_finishing_clears_the_place(self):
        total = c.get('/api/setup/walk').json()['total']
        self.assertEqual(c.post('/api/setup/walk', json={'at': total}).json()['at'], 0)

    def test_reset_is_its_own_door(self):
        c.post('/api/setup/walk', json={'at': 3})
        self.assertEqual(c.post('/api/setup/walk/reset').json()['at'], 0)


if __name__ == '__main__':
    unittest.main()
