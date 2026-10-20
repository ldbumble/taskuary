"""THE WALK AND THE RAIL ARE ONE ORDER (an owner screenshot, 2026-10-20). A task whose coding agent was working stood on the table and
was drawn under On you, at the bottom of it - below rows a day younger. The rail now keeps such a row under Agents working (funnelPile
bandsOf); here, the walk's side: a working agent's task is never the walk's item, and Next from it - the agent still working, the task
open - brings the FIRST On you row, the one the rail draws first."""
import os, tempfile, unittest

from taskuary import funnel, funnel_selection
from taskuary.store import SQLiteStore


class WalkOrderIsRailOrder(unittest.TestCase):
    def setUp(self):
        self.s = SQLiteStore(os.path.join(tempfile.mkdtemp(), 'walk.db'))
        # the rail's order is the server's (funnel._order): bands, then oldest first inside one
        self.items = funnel._order([
            dict(key='task:1', tid=1, lane='working', order_band=5, since='2026-10-19 08:00:00', surfaced=True),   # its agent working
            dict(key='task:3', tid=3, lane='yours', order_band=2, since='2026-10-20 09:00:00'),
            dict(key='task:2', tid=2, lane='yours', order_band=2, since='2026-10-19 20:00:00'),
        ])

    def pick(self, exclude=None):
        cap = funnel_selection.capture_selection(self.s, exclude=exclude, pile={'items': self.items})
        return cap.selected and cap.selected['key']

    def test_the_rail_draws_on_you_oldest_first_and_the_agent_last(self):
        self.assertEqual([i['key'] for i in self.items], ['task:2', 'task:3', 'task:1'])

    def test_next_from_a_working_agent_on_the_table_brings_the_first_on_you_row(self):
        self.assertEqual(self.pick(exclude='task:1'), 'task:2')

    def test_a_working_agent_is_never_the_walk_item(self):
        self.assertEqual(self.pick(), 'task:2')
        self.items = [i for i in self.items if i['lane'] == 'working']
        self.assertIsNone(self.pick(), 'only the agent left: nothing to walk to')


if __name__ == '__main__': unittest.main()
