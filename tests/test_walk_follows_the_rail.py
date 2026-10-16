"""The rail and the walk are one order (the owner, 2026-10-14: "the first task was skipped"). A coding agent session the owner had just
closed left its task first under On you - shown once, its lane `saved` - and Walk me through my tasks went past it to the next
unread row."""
import unittest
from unittest import mock

from taskuary import funnel, funnel_selection
from taskuary.store import MemoryStore


def row(key, lane, band, surfaced=False, **kw):
    return {'key': key, 'kind': 'todo', 'lane': lane, 'order_band': band, 'surfaced': surfaced, 'title': key, **kw}


class WalkFollowsTheRailTests(unittest.TestCase):
    def pick(self, items):
        with mock.patch.object(funnel, 'present', side_effect=lambda store, p: p):
            return funnel_selection.capture_selection(MemoryStore(), pile={'items': items}).selected

    def test_a_shown_row_under_on_you_is_walked_in_its_place(self):
        saved, fresh = row('task:1', 'saved', 2, surfaced=True), row('task:2', 'yours', 2)
        self.assertEqual(funnel.level_of(saved), 'task', 'the rail draws it under On you')
        self.assertEqual(self.pick([saved, fresh])['key'], 'task:1')

    def test_a_shown_quiet_row_still_waits_behind_what_is_unread(self):
        shown_fyi, unread_fyi = row('m:1', 'fyi', 4, surfaced=True), row('m:2', 'fyi', 4)
        self.assertFalse(funnel.leads(shown_fyi))
        self.assertTrue(funnel.leads(unread_fyi))

    def test_put_down_still_holds_it_back(self):
        later, fresh = row('task:1', 'saved', 2, surfaced=True, put_down=True), row('task:2', 'yours', 2)
        self.assertEqual(self.pick([later, fresh])['key'], 'task:2')


if __name__ == '__main__':
    unittest.main()
