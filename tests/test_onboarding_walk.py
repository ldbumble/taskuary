"""The scripted walk: every part of the app, one stop per turn, no AI anywhere in it.

The chip that opens this used to open an AI-led walk-through, which could not run before an AI was
connected - which is exactly when somebody presses it. So the stops are static text plus store
reads, and a typed question is an ordinary assistant turn that happens beside the walk rather than
inside it.
"""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient
from taskuary import server, setup, walk
from taskuary.store import MemoryStore

c = TestClient(server.app)

# Review retired as a tab of its own and Docs became a section of Settings (2026-09-22): a stop
# may only send you somewhere that still exists.
TABS = {'Assistant', 'Board', 'Tasks', 'Reports', 'Connections', 'Settings', 'Hub'}


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
        self.assertGreaterEqual(st['total'], 13)

    def test_the_first_five_stops_land_where_the_checklist_lands(self):
        """`goto` is the fifth field the checklist owns. It was the one copied into STOPS by hand,
        which made the button on a stop and the button on its own checklist row two answers to the
        same question - identical that day, and nothing keeping them so."""
        s = _fresh()
        rows = {x['key']: x['goto'] for x in setup.state(s)['steps']}
        for stop in walk.state(s)['stops'][:5]:
            self.assertEqual(stop['goto'], rows[stop['key']], stop['key'])
        # and STOPS does not carry its own copy to drift back to
        for stop in walk.STOPS[:5]:
            self.assertNotIn('goto', stop, stop['key'])

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
        for key in ('connections', 'docs', 'settings', 'board', 'tasks', 'reports',
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


class ThePicturesAreServedTests(unittest.TestCase):
    """The files were on disk, in the vite output and in the wheel, and every one of them still
    404ed: only /assets was mounted, and these are not build output. Three layers of "the file is
    there" passed while the app was broken, so this asks the SERVER for them, over HTTP."""
    def test_every_stop_with_a_picture_serves_it(self):
        shots = [(x['key'], x['image']) for x in walk.state(_fresh())['stops'] if x.get('image')]
        self.assertEqual(len(shots), len([x for x in walk.STOPS if x.get('image')]))
        self.assertGreaterEqual(len(shots), 8)
        for key, url in shots:
            r = c.get(url)
            self.assertEqual(r.status_code, 200, f'{key}: {url}')
            self.assertTrue(r.headers['content-type'].startswith('image/'), f'{key}: {r.headers["content-type"]}')
            self.assertTrue(r.content, key)

    def test_a_picture_needs_no_token(self):
        """An <img src> cannot carry a header. A shot that 401s is the same broken picture, so this
        walks in with an empty token - the way the browser's image request arrives."""
        anon = TestClient(server.app, headers={'X-Taskuary-Token': ''})
        self.assertEqual(anon.get('/favicon.png').status_code, 200)   # the standard this has to meet
        self.assertEqual(anon.get('/walk/docs.png').status_code, 200)

    def test_nothing_else_under_web_is_reachable_through_it(self):
        """A static mount is a hole in the shape of its directory. /walk holds the tab pictures, so
        it must not be a road to index.html or to anything above it."""
        self.assertEqual(c.get('/walk/../index.html').status_code, 404)
        self.assertEqual(c.get('/walk/nope.png').status_code, 404)


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


class TheAiStopKnowsWhatYouAlreadyHaveTests(unittest.TestCase):
    """Azure OpenAI is not a CLI tool, and you cannot sign in to it in a terminal.

    The stop offered "install a coding CLI and sign in to it" first and twice, and the checklist
    row sent everyone to the AI CLI agents page - so an install already running on Azure was told
    both that it needed a CLI and that a terminal was how its own provider got set up (the owner,
    2026-09-17: "you cant setup azure ai from here. It's not a cli tool").
    """

    def _ai_step(self, store):
        from taskuary import setup
        return next(r for r in setup.state(store)['steps'] if r['key'] == 'ai')

    def test_a_key_provider_sends_you_to_its_own_card(self):
        s = MemoryStore()
        cid = s.get_connector_by_type('azure_openai')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': 'k', 'Name': 'Azure OpenAI'}, 'o')
        step = self._ai_step(s)
        self.assertTrue(step['done'])
        self.assertEqual(step['goto']['hash'], 'connector=azure_openai')
        self.assertIn('Azure OpenAI', step['goto']['label'])
        self.assertNotIn('CLI', step['goto']['label'])

    def test_with_nothing_connected_the_cli_page_is_still_the_door(self):
        """It is a real way in, and the one most people arrive with something for."""
        self.assertEqual(self._ai_step(MemoryStore())['goto']['hash'], 'cli-agents')

    def test_the_api_key_road_is_not_an_afterthought(self):
        """Both roads exist; the stop used to list the CLI one first and again second."""
        can = [c['text'] for c in next(st for st in walk.STOPS if st['key'] == 'ai')['can']]
        self.assertIn('API key', can[0])
        self.assertIn('Azure OpenAI', can[0])
        self.assertTrue(any('coding CLI' in t for t in can), 'the CLI road is still offered')
        self.assertEqual(sum('coding CLI' in t for t in can), 1, 'and offered once')


class _NoRows:
    """A store that holds nothing, so 'none yet' can be tested without unseeding the real one."""
    def list_sources(self, *a, **k): return []
    def list_tasks(self, *a, **k): return []
    def list_reviews(self, *a, **k): return []      # the tasks stop counts the replies waiting on it


class EveryStopSaysWhatYouAlreadyHaveTests(unittest.TestCase):
    """The walk is a tour of an INSTALL, not of the product. A stop that could not say what is
    already set up made you go and look, which is the trip the walk exists to save (the owner,
    2026-09-17: "for each step it should include if step was already completed and what is setup for
    each step. So for reports show the reports setup and workflows").
    """

    def test_every_stop_either_ticks_or_counts_something(self):
        s = MemoryStore()
        stops = walk.state(s)['stops']
        for o in stops:
            self.assertTrue('done' in o or 'facts' in o, f"{o['key']} says nothing about this install")

    def test_the_reports_stop_answers_for_both_things_it_names(self):
        """"3 reports" on a card about reports AND workflows leaves you wondering which three."""
        s = MemoryStore()
        for title, flow in [('Process errors', False), ('Chase overdue invoices', True)]:
            s.save_source({'Channel': 'report', 'Address': title, 'Active': 1, 'Owner': 'o',
                           'ConfigJson': json.dumps({'type': 'mssql', 'title': title, 'is_workflow': flow})}, 'o')
        said = next(o for o in walk.state(s)['stops'] if o['key'] == 'reports')['facts']
        # both halves counted and named separately; only the first few names are listed, because a
        # card is not a directory - the count is the answer and the names are the sanity check
        self.assertIn('4 reports:', said)                   # the three shipped + one of theirs
        self.assertIn('1 workflows: Chase overdue invoices', said)

    def test_a_stop_with_nothing_to_count_says_none_yet_rather_than_nothing(self):
        """A blank where a number belongs reads as a failed read, not as an empty shelf."""
        self.assertEqual(walk._fact_reports(_NoRows()), 'none yet')
        self.assertEqual(walk._fact_tasks(_NoRows()), 'none yet')

    def test_a_counter_that_throws_does_not_take_the_walk_down(self):
        """The install that most needs the walk is the half-configured one where a read throws."""
        s = MemoryStore()
        with mock.patch.dict(walk.FACTS, {'hub': lambda _s: (_ for _ in ()).throw(RuntimeError('no table'))}):
            stops = walk.state(s)['stops']
        self.assertEqual(len(stops), len(walk.STOPS))
        self.assertNotIn('facts', next(o for o in stops if o['key'] == 'hub'))


if __name__ == '__main__':
    unittest.main()
