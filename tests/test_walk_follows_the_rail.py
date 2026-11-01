"""The rail and the walk are one order (the owner, 2026-10-14: "the first task was skipped"). A coding agent session the owner had just
closed left its task first under On you - shown once, its lane `saved` - and Walk me through my tasks went past it to the next
unread row. The walk now starts at the top of the rail whatever was shown, read or passed before (railwalk, 2026-10-30)."""
import unittest

from taskuary import funnel
from taskuary.store import MemoryStore

from railwalk_rows import RowWalk


def row(key, lane, band, **kw):
    return {'key': key, 'kind': 'todo', 'lane': lane, 'order_band': band, 'title': key, **kw}


class WalkFollowsTheRailTests(unittest.TestCase):
    def walk(self, items):
        w = RowWalk(MemoryStore(), items); self.addCleanup(w.close)
        return w

    def test_a_shown_row_under_on_you_is_walked_in_its_place(self):
        saved, fresh = row('task:1', 'saved', 2, tid=1, unread=False), row('task:2', 'yours', 2, tid=2)
        self.assertEqual(funnel.level_of(saved), 'task', 'the rail draws it under On you')
        self.assertEqual(self.walk([saved, fresh]).start(), 'task:1')

    def test_the_walk_starts_at_the_top_even_with_a_row_waiting_on_you_below(self):
        """What waits on you no longer leads the walk (2026-09-10, replaced 2026-10-30: walk start is the top)."""
        mine, waiting = row('task:1', 'yours', 2, tid=1, since='2026-10-29 08:00:00'), row('task:2', 'blocked', 2, tid=2, since='2026-10-29 09:00:00')
        self.assertEqual(self.walk(funnel._order([waiting, mine])).start(), 'task:1')

    def test_nothing_holds_a_task_back_after_next(self):
        """Next on a task writes nothing, so the next walk starts with it again (rule 6: never skip)."""
        a, b = row('task:1', 'saved', 2, tid=1), row('task:2', 'yours', 2, tid=2)
        w = self.walk([a, b])
        w.start(); self.assertEqual(w.next(), 'task:2')
        self.assertEqual(w.start(), 'task:1')


if __name__ == '__main__':
    unittest.main()
