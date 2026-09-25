"""A session you opened to work IN must not close itself out from under you.

The self-close judge reads a screen that has gone quiet and decides the run is over. For work
that ARRIVED that is exactly right - somebody is waiting on an answer, and the alternative is a
sender waiting on a human to look at a terminal hours later. For a session the owner opened to
sit in it is the opposite: they alt-tab, the agent stops printing, the judge says finished, and
the task closes with a reply drafted to nobody.

Nothing distinguished the two. selfclose knew the transcript and the clock and nothing about who
had opened the session, so `+ New -> give an agent a job` behaved exactly like a routed email.

The tag says which kind this is. The JUDGE is refused; `taskuary --done` is not - an agent saying
in words that it has finished outranks a guess about who the session was for.
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


class TheJudgeIsRefusedButNotTheAgent(unittest.TestCase):
    """The distinction that matters: a GUESS is refused, a DECLARATION is not."""

    def setUp(self):
        # _DONE is process-wide by design ("task ids a self-close has already run for, this
        # process") and MemoryStore restarts ids at 1, so two tests collide on task 1
        selfclose._DONE.clear()

    def _term(self, tid):
        return mock.Mock(task_id=tid, agent='coder', started_ts=0, n=99999,
                         tail=lambda n=0: 'all done, the export is fixed')

    def test_a_quiet_screen_never_ends_a_task(self):
        """The judge is gone (the owner, 2026-09-24): only the agent SAYING done, or the owner, ends a task - never a
        guess read off a quiet screen, whoever opened the session."""
        s = MemoryStore()
        for tid in (_task(s, selfclose.STAY_TAG), _task(s)):
            with mock.patch.object(selfclose, '_wrap') as w:
                out = selfclose.on_stop(s, self._term(tid))
            self.assertFalse(out['closed']); self.assertTrue(out['why']); w.assert_not_called()

    def test_taskuary_done_closes_the_task_even_on_a_stay_open_session(self):
        """The stay-open tag is the JUDGE's veto and says so: "only an explicit ending counts".

        This road had been reading it as a veto on itself, so an agent that did the work and said so
        left the task open with nothing left to work and a heading still reading "coder is working"
        (the owner, 2026-09-17: "if the agent did it's job and hit --done it should close it").

        It reverses TQ-0297, where an explicit finish closed under the owner mid-review - and what
        makes that survivable is that closing no longer takes anything away: the agent's sentence is
        a comment, the report and any drafted reply wait in Review, and the task reopens.
        """
        s = MemoryStore()
        tid = _task(s, selfclose.STAY_TAG)
        with mock.patch.object(selfclose, '_wrap', return_value={'closed': True}) as w:
            out = selfclose.declare(s, tid, 'fixed the export', 'coder')
        self.assertTrue(out['closed'])
        w.assert_called_once()
        self.assertIn('The agent closed this itself: fixed the export', [c['Body'] for c in s.list_comments(tid)])


if __name__ == '__main__':
    unittest.main()
