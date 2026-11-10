"""The canvas redesign's rail sections, server side (docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md).

For later holds what Remind me put away and a goal waiting for its next news, each with the time it comes back - what Next
walks past stays under Tasks (the owner, 2026-10-21); the level an
item is in is one rule shared with the page (website/src/funnelPile.js levelOf), pinned by tests/fixtures/rail_levels.json
from both sides, so the phone doorway's section walk and the rail agree on membership.
"""
import json, os, unittest
from unittest import mock

from taskuary import funnel, processing_unread, remind
from test_funnel import ago, mail, store

FIXTURE = os.path.join(os.path.dirname(__file__), 'fixtures', 'rail_levels.json')


def settled():
    s = store()
    def settle():
        s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
    return s, settle


def rail(s, **kw):
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        return processing_unread.build(s, live_state=[], **kw)['items']


class LevelOfTests(unittest.TestCase):
    def test_the_server_puts_every_fixture_row_where_the_page_does(self):
        for item, level in json.load(open(FIXTURE, encoding='utf-8')):
            self.assertEqual(funnel.level_of(item), level, item)

    def test_every_section_has_its_heading_word(self):
        # no Agents working and no Goals: every open task is under Tasks (the owner, 2026-10-21) - and no Urgent: an urgent row is
        # shaded in its place under Tasks (the owner, 2026-10-22) - and Watching at the foot of Tasks, what Watch it keeps open (2026-11-01)
        self.assertEqual(list(funnel.SECTION_WORDS), ['task', 'watching', 'later', 'reports', 'ideas', 'fyi'])
        self.assertEqual(funnel.SECTION_WORDS['watching'], 'Watching')
        self.assertEqual(funnel.SECTION_WORDS['later'], 'For later')
        self.assertEqual(funnel.SECTION_WORDS['task'], 'Tasks')


class ForLaterTests(unittest.TestCase):
    def test_a_task_next_walked_past_stays_in_tasks_with_no_clock_on_it(self):
        """Next moves on; the task stays (2026-10-21) - and since 2026-10-30 it is not even marked: Next on a task writes nothing."""
        from taskuary import concierge, railwalk
        s, settle = settled()
        t = s.create_task({'Title': 'Send the August financials', 'Kind': 'task', 'Status': 'open'}, 'triage')
        mid = mail(s, 'August financials', who='Paula Vance', email='paula@vendor.example', hours=1, tid=t)
        s.add_route(mid, t, 'route', 1.0, 'triage: task', [], 'triage')
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            first = concierge.surface(s, llm=lambda *a, **k: 'never')
            railwalk.next(s, first['item']['key'])
            card = next(i for i in rail(s) if i.get('tid') == t)
        self.assertEqual(funnel.level_of(card), 'task')
        self.assertTrue(card['actionable']); self.assertNotIn('put_down', card)
        self.assertNotIn('back_at', card, 'nothing is passed, so nothing has a time to come back')

    def test_remind_me_keeps_the_task_on_the_rail_in_for_later_until_its_day(self):
        s, settle = settled()
        t = s.create_task({'Title': 'Renew the domain', 'Kind': 'task', 'Status': 'open'}, 'owner')
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        remind.set_reminder(s, t, 'monday'); settle()
        cards = [i for i in rail(s) if i.get('tid') == t]
        self.assertEqual(len(cards), 1, 'put away is still on the rail, in For later')
        self.assertEqual(funnel.level_of(cards[0]), 'later')
        self.assertEqual(cards[0]['back_at'], s.get_task(t)['RemindAt'])
        self.assertFalse(cards[0]['actionable'], 'the walk does not offer it before its day')


class SectionWalkTests(unittest.TestCase):
    def test_a_heading_opens_its_first_row_and_next_walks_on_down_the_rail(self):
        """A heading clicked opens its section's first ready row, and Next carries on down the rail - past the section's end, with no
        "seen" set and no section stop (Q6, 2026-10-30; railwalk.section)."""
        from railwalk_rows import RowWalk
        from taskuary.store import MemoryStore
        items = [{'key': 'd', 'lane': 'fyi', 'order_band': 4, 'settling': True, 'since': '2026-10-29 07:00:00'},
                 {'key': 'b', 'lane': 'asked', 'order_band': 2, 'since': '2026-10-29 07:30:00'},
                 {'key': 'a', 'lane': 'fyi', 'order_band': 4, 'since': '2026-10-29 08:00:00'},
                 {'key': 'r', 'lane': 'report', 'kind': 'report', 'order_band': 3, 'since': '2026-10-29 08:30:00'},
                 {'key': 'c', 'lane': 'fyi', 'order_band': 4, 'since': '2026-10-29 09:00:00'}]
        w = RowWalk(MemoryStore(), items); self.addCleanup(w.close)
        self.assertEqual(w.key(w.rw.section(w.s, 'reports')), 'r')
        self.assertEqual(w.next(), 'fyis:a,c', 'on down the rail, out of Reports, with no stop - FYI a handful at a time')
        self.assertEqual(w.key(w.rw.section(w.s, 'fyi')), 'a', 'triaging is not ready to walk')
        self.assertIsNone(w.key(w.rw.section(w.s, 'ideas')))

    def test_a_section_that_runs_out_says_so_in_its_own_words(self):
        self.assertEqual(funnel.section_done('fyi'), 'FYI done.')
        self.assertEqual(funnel.section_done('later'), 'For later done.')


class ServedRailTests(unittest.TestCase):
    """The final review: Remind me rows were kept by processing_unread.build but dropped by funnel.pile - the rail the page
    is actually served. Tested through the road the page reads."""
    def test_a_task_put_away_is_on_the_served_rail(self):
        s, settle = settled()
        t = s.create_task({'Title': 'Renew the domain', 'Kind': 'task', 'Status': 'open'}, 'owner')
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        remind.set_reminder(s, t, 'monday'); settle()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            rows = [i for i in funnel.pile(s, force=True)['items'] if i.get('tid') == t]
        self.assertEqual([(funnel.level_of(i), i['actionable']) for i in rows], [('later', False)])
