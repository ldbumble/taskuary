"""A session you opened to work IN must not close itself out from under you.

For work that ARRIVED an agent saying `taskuary --done` is exactly right - somebody is waiting on an
answer, and the alternative is a sender waiting on a human to look at a terminal hours later. For a
session the owner opened to sit in it is the opposite: the agent finishing a step is not the owner
finishing the task.

The tag says which kind this is, and it is ONE rule (the owner, 2026-09-25): an agent may close its
own task only when the task allows it. With `stay:open` on, `--done` is refused and the owner keeps
completion; the seed tells the agent exactly that. It used to say so in the docs and the seed while
`declare` closed anyway.
"""
import unittest
from unittest import mock

from taskuary import selfclose
from taskuary.store import MemoryStore


def _task(s, tags=None):
    return s.create_task({'Title': 'work on the export', 'Kind': 'coding',
                          'Status': 'in_progress', 'Tags': tags}, 'owner')


class WhichSessionsMayEndThemselves(unittest.TestCase):
    def test_a_task_you_opened_to_work_in_is_marked(self):
        s = MemoryStore()
        self.assertTrue(selfclose.stays_open(s, _task(s, selfclose.STAY_TAG)))

    def test_a_routed_task_is_not(self):
        s = MemoryStore()
        self.assertFalse(selfclose.stays_open(s, _task(s)))

    def test_the_tag_survives_company_on_the_line(self):
        """Tags arrive comma-joined from newTask.planTask, alongside repo: and needs:browser."""
        s = MemoryStore()
        self.assertTrue(selfclose.stays_open(s, _task(s, f'repo:taskuary,{selfclose.STAY_TAG},needs:browser')))

    def test_a_tag_that_merely_contains_it_does_not_count(self):
        s = MemoryStore()
        self.assertFalse(selfclose.stays_open(s, _task(s, 'stay:open-ish')))

    def test_no_task_at_all_is_not_an_error(self):
        self.assertFalse(selfclose.stays_open(MemoryStore(), 99999))


class TheTaskDecidesWhetherItsAgentMayClose(unittest.TestCase):
    def setUp(self):
        # _DONE is process-wide by design ("task ids a self-close has already run for, this
        # process") and MemoryStore restarts ids at 1, so two tests collide on task 1
        selfclose._DONE.clear()

    def test_taskuary_done_is_refused_on_a_stay_open_task(self):
        """The owner keeps completion: nothing wraps, the task stays open, and the agent's sentence is filed for them."""
        s = MemoryStore()
        tid = _task(s, selfclose.STAY_TAG)
        with mock.patch.object(selfclose, '_wrap') as w:
            out = selfclose.declare(s, tid, 'fixed the export', 'coder')
        self.assertFalse(out['closed']); self.assertEqual(out['why'], selfclose.OWNER_ENDS)
        w.assert_not_called()
        self.assertEqual(s.get_task(tid)['Status'], 'in_progress')
        self.assertIn('The agent says it is finished: fixed the export', [c['Body'] for c in s.list_comments(tid)])
        self.assertNotIn(tid, selfclose._DONE, 'refused is not "already ran": once the owner lifts the mark, --done works')

    def test_taskuary_done_closes_a_task_that_allows_it(self):
        s = MemoryStore()
        tid = _task(s)
        with mock.patch.object(selfclose, '_wrap', return_value={'closed': True}) as w:
            out = selfclose.declare(s, tid, 'fixed the export', 'coder')
        self.assertTrue(out['closed']); w.assert_called_once()
        self.assertIn('The agent closed this itself: fixed the export', [c['Body'] for c in s.list_comments(tid)])

    def test_the_seed_says_what_declare_does(self):
        """The rule and the prompt must not disagree again: the stay-open seed says --done is refused, never 'closes'."""
        self.assertIn('refused', selfclose.STAY_LINE); self.assertIn('taskuary --done', selfclose.STAY_LINE)

    def test_the_quiet_screen_road_is_gone(self):
        self.assertFalse(hasattr(selfclose, 'on_stop')); self.assertFalse(hasattr(selfclose, 'spawn_on_stop'))


class OneModeLeft(unittest.TestCase):
    """'auto' and 'ask' differed only by the judge, which is gone: the setting is on or off."""

    def test_every_old_value_reads_as_on_or_off(self):
        s = MemoryStore()
        for v, want in (('1', 'on'), ('ask', 'on'), ('auto', 'on'), ('', 'on'), ('0', 'off'), ('off', 'off')):
            s.set_setting(selfclose.SETTING, v, 't')
            self.assertEqual(selfclose.mode(s), want, v)

    def test_a_stored_ask_is_settled_to_on_once(self):
        s = MemoryStore(); s.set_setting(selfclose.SETTING, 'ask', 'owner')
        self.assertTrue(selfclose.settle_legacy(s)); self.assertEqual(s.get_settings()[selfclose.SETTING], '1')
        self.assertFalse(selfclose.settle_legacy(s))
        s.set_setting(selfclose.SETTING, '0', 'owner')
        self.assertFalse(selfclose.settle_legacy(s)); self.assertEqual(s.get_settings()[selfclose.SETTING], '0')


if __name__ == '__main__':
    unittest.main()
