"""The owner-approved phone changes of 2026-10-22 (the overnight review's A1-A18), each pinned by what the phone SHOWS - a typed line or a
tap in through the channel's own poll, the bubbles out of its own send (tests/phone_transcript.py). The owner's rule over all of them:
someone can manage Taskuary from the phone alone, so every message ends with what to do next, and no state is a dead end.
Invented people only: Alex Doyle, Gail Moreno, Ray Colton, northwind.example."""
import json, re, time, unittest
from unittest import mock

from taskuary import remote_assistant as ra
from tests.phone_transcript import GAIL, RAY, Phone, call, text_of


def _two_asks(f):
    a, _ = f._work('Badge access for the new hire', subject='Badge access for the new hire', from_name=RAY[0], from_email=RAY[1],
                   body='Alex, the new AP clerk starts Monday. Can you get her a badge for floors 2 and 3?', sent_at=f.ago(hours=3))
    b, _ = f._work('Visitor parking for Friday', subject='Visitor parking for Friday', from_name=GAIL[0], from_email=GAIL[1],
                   body='Can we get a visitor parking list for Friday? Security needs it by Thursday.', sent_at=f.ago(hours=2))
    return a, b


class PhoneCase(unittest.TestCase):
    channel, brain = 'whatsapp', None

    def setUp(self):
        self.ph = Phone(self.channel, brain=self.brain)
        self.addCleanup(self.ph.close)
        self.s, self.f = self.ph.s, self.ph.f

    def ends_with_choices(self, got):
        self.assertTrue(got and got[-1][1], f'a dead end - nothing to tap under: {text_of(got)!r}')


class RemindHasNoUndoTests(PhoneCase):
    """A15: "Bring it back now" - the undo for the task just put away - rode under the NEXT task's card. The owner dislikes undo buttons,
    and it is gone from the phone; the receipt says when it is back, and the next card's own choices follow."""

    def test_a_remind_offers_no_bring_it_back(self):
        a, b = _two_asks(self.f); self.ph.ready()
        self.ph.walk(); self.ph.tap('Remind me')
        got = self.ph.tap('Tomorrow')
        self.assertRegex(text_of(got), r'TQ-\d{4} is away until')
        self.assertNotIn('Bring it back now', [w for _t, b_ in got for w in b_])
        self.ends_with_choices(got)


class EndOfWalkTests(PhoneCase):
    """A1: the walk's end offered only Open picks, and outside a hand-off there was no way to start again. It offers "Walk me through my
    tasks" first, and the new walk shows every open task again from the top (next-is-seen-in-this-walk)."""

    def test_the_end_offers_a_new_walk_that_shows_every_open_task_again(self):
        a, b = _two_asks(self.f); self.ph.ready()
        first = text_of(self.ph.walk())
        self.ph.tap('Next')
        end = self.ph.tap('Next')
        self.assertIn("That's everything for now", text_of(end))
        self.assertEqual(end[-1][1][0], 'Walk me through my tasks', end[-1][1])
        again = self.ph.tap('Walk me through my tasks')
        ref = next(f'TQ-{t:04d}' for t in (a, b) if f'TQ-{t:04d}' in first)
        self.assertIn(ref, text_of(again))                                    # the first task again, not "nothing waiting"
        self.assertIn('Next', again[-1][1])


if __name__ == '__main__': unittest.main()
