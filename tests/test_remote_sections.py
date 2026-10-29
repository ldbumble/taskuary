"""The phone doorway matches the canvas redesign (docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md):
the rail's sections are offered as picks and walked one at a time, For later says when each comes back, and Connections
and Settings are browsed as numbered picks - sections, then the list, then one - the way the canvas browses them."""
import unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import concierge, doorway_browse as db, funnel, remote_assistant as ra
from taskuary.store import MemoryStore


def later(minutes):
    return (datetime.now() + timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


# built per test, not at import: a slow suite reached this file minutes after collection, and "back in 3h" read
# "back in 2h" (2026-10-01)
def pile():
    return [{'key': 'msg:1', 'lane': 'asked', 'order_band': 2, 'title': 'Approve the Q3 invoice', 'who': 'Paula Vance'},
            {'key': 'msg:2', 'lane': 'yours', 'order_band': 2, 'deferred': True, 'back_at': later(185), 'title': 'Lease renewal', 'who': 'Ray Colton'},
            {'key': 'msg:5', 'lane': 'working', 'order_band': 2, 'title': 'Census export', 'working': 'coding'},
            {'key': 'msg:3', 'lane': 'fyi', 'order_band': 4, 'title': 'Quarterly newsletter', 'who': 'Marcus Reed'},
            {'key': 'msg:4', 'lane': 'fyi', 'order_band': 4, 'title': 'Back Tuesday', 'who': 'Gail Moreno'}]


class ForLaterTests(unittest.TestCase):
    def test_for_later_is_its_own_group_and_says_when_each_comes_back(self):
        text = ra.who_wants_what(pile())
        self.assertIn('FOR LATER · 1', text)
        self.assertIn('Lease renewal (back in 3h)', text)
        # every open task is under Tasks, the one an agent is working included (the owner, 2026-10-21)
        self.assertIn('TASKS · 2', text); self.assertNotIn('AGENTS WORKING', text)

    def test_the_sections_are_offered_as_picks(self):
        rows = db.section_rows(pile())
        self.assertEqual([label for label, _ in rows], ['Walk Tasks', 'Walk For later', 'Walk FYI'])
        self.assertEqual(rows[-1][1], {'t': 'section', 'section': 'fyi'})


class SectionWalkTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.shown = []
        def surface(store, key=None, **kw):
            self.shown.append(key)
            return {'say': f'shown {key}', 'item': {'key': key} if key else None}
        self.patches = [mock.patch.object(funnel, 'pile', return_value={'items': pile()}),
                        mock.patch.object(concierge, 'surface', side_effect=surface),
                        mock.patch.object(ra, 'carry_out', side_effect=lambda store, out, item, actor='owner', lead='', picked=False, extra=None: (lead + ' ' + out['say']).strip()),
                        mock.patch.object(ra, 'asking', return_value={'channel': 'whatsapp', 'chat': 'c1'})]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in self.patches: p.stop()

    def test_a_section_pick_walks_that_section_and_next_stays_in_it_until_it_is_empty(self):
        # (the first line: a pick's answer with nothing to tap gets the way on under it - 2026-10-22)
        self.assertEqual(ra.run_act(self.s, {'t': 'section', 'section': 'fyi'}, None).splitlines()[0], 'shown msg:3')
        self.assertEqual(ra.run_act(self.s, {'t': 'next'}, {'key': 'msg:3'}).splitlines()[0], 'shown msg:4')
        done = ra.run_act(self.s, {'t': 'next'}, {'key': 'msg:4'})
        self.assertTrue(done.startswith('FYI done.'), done)
        self.assertEqual(self.shown, ['msg:3', 'msg:4', None], 'then the normal walk takes over')

    def test_an_empty_section_says_so(self):
        said = ra.run_act(self.s, {'t': 'section', 'section': 'reports'}, None)
        self.assertEqual(said.splitlines()[0], 'Nothing in Reports right now.')
        self.assertIn('Walk me through my tasks', said, 'and never a dead end')


class BrowseTests(unittest.TestCase):
    def test_connections_browse_sections_then_the_list_then_one(self):
        s = MemoryStore()
        first = ra.run_act(s, {'t': 'browse', 'area': 'connections'}, None)
        self.assertIn('Connections', first)
        self.assertIn('Messaging', first)
        cards = ra.run_act(s, {'t': 'browse', 'area': 'connections', 'section': 'Messaging'}, None)
        self.assertIn('Outlook mail', cards)
        one = ra.run_act(s, {'t': 'browse', 'area': 'connections', 'section': 'Messaging', 'open': 'outlook'}, None)
        self.assertIn('Outlook mail', one)
        self.assertRegex(one, r'Outlook mail - (off|not connected)\.', "its state, in the desktop card's own words")
        self.assertIn('Back to Messaging', one)

    def test_settings_browse_groups_then_its_settings_with_their_values(self):
        s = MemoryStore()
        self.assertIn('Replies', ra.run_act(s, {'t': 'browse', 'area': 'settings'}, None))
        group = ra.run_act(s, {'t': 'browse', 'area': 'settings', 'section': 'Replies'}, None)
        from taskuary import doorway_browse
        key, meta = next((k, m) for k, m in doorway_browse._schema()['knobs'].items() if m.get('group') == 'Replies')
        self.assertIn(meta['label'], group)
        one = ra.run_act(s, {'t': 'browse', 'area': 'settings', 'section': 'Replies', 'open': key}, None)
        self.assertIn(meta['label'], one)
        self.assertIn('now:', one)

    def test_connections_and_settings_are_offered_every_morning(self):
        labels = [label for label, _ in ra.SCRIPT_LINES]
        self.assertIn('Connections', labels)
        self.assertIn('Settings', labels)


class SectionWalkEndsTests(unittest.TestCase):
    """The final review: a phone section walk abandoned today captured Next days later. It ends with a new walk, a named
    pick, or when it is older than the quiet hours."""
    def test_a_held_section_expires_and_a_new_walk_drops_it(self):
        s = MemoryStore()
        chat = {'channel': 'whatsapp', 'chat': 'c1'}
        db.hold(s, chat, 'fyi', ['msg:3'])
        self.assertEqual(db.held(s, chat)['section'], 'fyi')
        with mock.patch.object(db, '_now', return_value=datetime.now() + timedelta(hours=4)):
            self.assertIsNone(db.held(s, chat), 'past the quiet hours it is over')
        with mock.patch.object(ra, 'asking', return_value=chat), mock.patch.object(ra, 'walk', return_value='walked'):
            ra.run_act(s, {'t': 'walk'}, None)
        self.assertIsNone(db.held(s, chat), 'a new walk is not the old section')


class SummaryWordsTests(unittest.TestCase):
    """F15: "1 tasks, 1 reports", a sender read as the word of their address ("example") or an agent as its CLI ("claude"), and
    "(fyi)" on every row under the FYI heading."""
    def rows(self):
        return [{'key': 'msg:1', 'lane': 'asked', 'kind': 'asked', 'order_band': 2, 'title': 'Approve the Q3 invoice',
                 'who': 'Gail Moreno', 'email': 'gail@mail.example'},
                {'key': 'task:2', 'lane': 'working', 'kind': 'agent', 'order_band': 2, 'title': 'Census export', 'who': 'claude',
                 'agent': 'claude', 'working': 'claude', 'mode': 'assistant'},
                {'key': 'report:3', 'lane': 'report', 'kind': 'report', 'title': 'AP ageing - 5 rows', 'who': 'AP ageing'},
                {'key': 'msg:4', 'lane': 'fyi', 'kind': 'fyi', 'order_band': 4, 'title': 'Back Tuesday', 'who': 'Ray Colton', 'email': 'ray@northwind.example'}]

    def test_one_is_singular(self):
        text = ra.who_wants_what(self.rows()[2:])
        self.assertIn('1 report', text); self.assertNotIn('1 reports', text)
        self.assertIn('1 task', ra.who_wants_what(self.rows()[:1])); self.assertNotIn('1 tasks', ra.who_wants_what(self.rows()[:1]))

    def test_rows_name_the_sender_and_the_agent_and_drop_their_headings_word(self):
        text = ra.who_wants_what(self.rows())
        self.assertIn('· Gail Moreno - Approve the Q3 invoice', text)
        self.assertNotIn('· example', text); self.assertNotIn('· claude', text)
        self.assertIn('· Taskuary - Census export', text)
        self.assertIn('· Ray Colton - Back Tuesday', text); self.assertNotIn('(fyi)', text)
