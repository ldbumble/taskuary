"""THE WALK AND THE RAIL ARE ONE ORDER (an owner screenshot, 2026-10-20). A task whose coding agent was working stood on the table and
was drawn at the bottom of its section, below rows a day younger. Since 2026-10-21 there is no Agents working section: every open
task is under Tasks, an agent at work on it or not (a spinning ring on its icon says which), and the walk takes them all in the
rail's order - oldest first. Next from the row on the table brings the next row the rail draws, whatever its agent is doing."""
import os, tempfile, unittest

from taskuary import funnel, funnel_selection, lanes
from taskuary.store import SQLiteStore


class WalkOrderIsRailOrder(unittest.TestCase):
    def setUp(self):
        self.s = SQLiteStore(os.path.join(tempfile.mkdtemp(), 'walk.db'))
        # the rail's order is the server's (funnel._order): bands, then oldest first inside one
        self.items = funnel._order([
            dict(key='task:1', tid=1, lane='working', order_band=2, since='2026-10-19 08:00:00'),   # its agent working
            dict(key='task:3', tid=3, lane='yours', order_band=2, since='2026-10-20 09:00:00'),
            dict(key='task:2', tid=2, lane='yours', order_band=2, since='2026-10-19 20:00:00'),
        ])

    def pick(self, exclude=None):
        cap = funnel_selection.capture_selection(self.s, exclude=exclude, pile={'items': self.items})
        return cap.selected and cap.selected['key']

    def test_the_rail_draws_every_task_oldest_first_whatever_its_agent_is_doing(self):
        self.assertEqual([i['key'] for i in self.items], ['task:1', 'task:2', 'task:3'])
        self.assertEqual({lanes.level_of(i) for i in self.items}, {'task'})

    def test_the_walk_starts_on_the_first_row_even_with_its_agent_working(self):
        self.assertEqual(self.pick(), 'task:1')

    def test_next_from_a_working_agent_on_the_table_brings_the_next_row(self):
        self.assertEqual(self.pick(exclude='task:1'), 'task:2')

    def test_a_task_its_agent_is_working_stays_in_tasks_when_the_agent_asks_or_stops(self):
        for lane in ('working', 'blocked', 'stopped', 'saved', 'queued'):
            self.assertEqual(lanes.level_of({'lane': lane, 'tid': 1}), 'task', lane)

    def test_next_moves_on_and_the_task_stays_in_tasks(self):
        self.items[0] |= {'surfaced': True, 'put_down': True}       # Next's mark on task:1
        self.assertEqual(lanes.level_of(self.items[0]), 'task')
        self.assertEqual(self.pick(), 'task:2')                     # ...and the walk does not offer it again
        self.items[1] |= {'deferred': True}                          # Remind me puts task:2 in For later
        self.assertEqual(lanes.level_of(self.items[1]), 'later')


if __name__ == '__main__': unittest.main()
