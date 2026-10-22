"""The canvas redesign's rail sections, server side (docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md).

For later holds what Remind me put away and a goal waiting for its next news, each with the time it comes back - what Next
walks past stays under Tasks (the owner, 2026-10-21); the level an
item is in is one rule shared with the page (website/src/funnelPile.js levelOf), pinned by tests/fixtures/rail_levels.json
from both sides, so the phone doorway's section walk and the rail agree on membership.
"""
import json, os, unittest
from datetime import datetime, timedelta
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
        # shaded in its place under Tasks (the owner, 2026-10-22)
        self.assertEqual(list(funnel.SECTION_WORDS), ['task', 'later', 'reports', 'ideas', 'fyi'])
        self.assertEqual(funnel.SECTION_WORDS['later'], 'For later')
        self.assertEqual(funnel.SECTION_WORDS['task'], 'Tasks')


class ForLaterTests(unittest.TestCase):
    def test_a_passed_task_stays_in_tasks_with_no_clock_on_it(self):
        from taskuary import concierge
        s, settle = settled()
        t = s.create_task({'Title': 'Send the August financials', 'Kind': 'task', 'Status': 'open'}, 'triage')
        mid = mail(s, 'August financials', who='Paula Vance', email='paula@vendor.example', hours=1, tid=t)
        s.add_route(mid, t, 'route', 1.0, 'triage: task', [], 'triage')
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            first = concierge.surface(s, llm=lambda *a, **k: 'never')
            concierge.move_on(s, first['item']['key'])                  # Next's mark, the walk not run out yet
            card = next(i for i in rail(s) if i.get('tid') == t)
        self.assertEqual(funnel.level_of(card), 'task')                 # Next moves on; the task stays (2026-10-21)
        self.assertTrue(card['put_down']); self.assertFalse(card['actionable'])
        self.assertNotIn('back_at', card, 'passed for this walk, not for a number of hours')

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
    def test_the_next_of_a_section_is_its_first_row_the_walk_has_not_seen(self):
        items = [{'key': 'a', 'lane': 'fyi', 'order_band': 4}, {'key': 'b', 'lane': 'asked', 'order_band': 2},
                 {'key': 'c', 'lane': 'fyi', 'order_band': 4}, {'key': 'd', 'lane': 'fyi', 'order_band': 4, 'settling': True}]
        self.assertEqual(funnel.section_next(items, 'fyi')['key'], 'a')
        self.assertEqual(funnel.section_next(items, 'fyi', seen={'a'})['key'], 'c')
        self.assertIsNone(funnel.section_next(items, 'fyi', seen={'a', 'c'}), 'triaging is not ready to walk')
        self.assertIsNone(funnel.section_next(items, 'reports'))

    def test_a_section_that_runs_out_says_so_in_its_own_words(self):
        self.assertEqual(funnel.section_done('fyi'), 'FYI done.')
        self.assertEqual(funnel.section_done('later'), 'For later done.')


class LegacyPileForLaterTests(unittest.TestCase):
    """The demo world runs the legacy pile (funnel.build): walked-past open work stays under Tasks there too, and Remind me
    puts it in For later."""
    def test_walked_past_open_work_stays_in_tasks_and_later_says_its_day(self):
        now = datetime.now()
        at = (now - timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
        until = (now + timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
        back = (now + timedelta(minutes=170)).strftime('%Y-%m-%d %H:%M:%S')
        items = [{'key': 'msg:1', 'lane': 'yours', 'tid': 4}, {'key': 'msg:2', 'lane': 'fyi'},
                 {'key': 'msg:3', 'lane': 'yours', 'tid': 5}, {'key': 'msg:4', 'lane': 'yours', 'tid': 6}]
        # Next leaves a mark carrying when it is back (concierge.move_on, put_down); a card merely SHOWN leaves one without
        states = {'msg:1': {'Status': 'surfaced', 'At': at, 'Until': back}, 'msg:2': {'Status': 'surfaced', 'At': at},
                  'msg:3': {'Status': 'later', 'Until': until}, 'msg:4': {'Status': 'surfaced', 'At': at}}
        out = {i['key']: i for i in funnel._apply_states(items, states, now, quiet=180)}
        self.assertEqual(set(out), {'msg:1', 'msg:3', 'msg:4'}, 'a read fyi is gone; open work is not')
        self.assertTrue(out['msg:1']['surfaced'])
        self.assertNotIn('back_at', out['msg:1'], 'an open task walked past is passed for this walk, with no clock')
        self.assertEqual((out['msg:3']['deferred'], out['msg:3']['back_at']), (True, until))
        self.assertEqual({k: funnel.level_of(i | {'order_band': 2}) for k, i in out.items()},
                         {'msg:1': 'task', 'msg:3': 'later', 'msg:4': 'task'},
                         'walked past or clicked away from stays under Tasks (2026-10-08, 2026-10-21); Remind me is For later')
        self.assertNotIn('back_at', out['msg:4'])


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
