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


class PositionTests(PhoneCase):
    """A11: a long walk gave no sense of progress. Each card's first line says where it is in its section: "📋 on you · TQ-0001 · 1 of 3"."""
    channel = 'telegram'

    def test_each_card_says_where_it_is_in_its_section(self):
        _two_asks(self.f)
        self.f._work('Printer on 3 is jammed again', subject='Printer on 3 is jammed again', from_name=RAY[0], from_email=RAY[1],
                     body='The big printer on floor 3 is jammed again, can someone call the vendor?', sent_at=self.f.ago(hours=1))
        self.ph.ready()
        firsts = [text_of(self.ph.walk()).split('\n')[0]] + [text_of(self.ph.tap('Next')).split('\n')[0] for _ in range(2)]
        for n, line in enumerate(firsts, 1): self.assertRegex(line, rf'^\S+ on you · TQ-\d{{4}} · {n} of 3$', firsts)

    def test_a_section_of_one_says_nothing(self):
        self.f._work('Printer on 3 is jammed again', subject='Printer on 3 is jammed again', from_name=RAY[0], from_email=RAY[1],
                     body='The big printer on floor 3 is jammed again, can someone call the vendor?', sent_at=self.f.ago(hours=1))
        self.ph.ready()
        self.assertNotIn(' of 1', text_of(self.ph.walk()).split('\n')[0])


def _report(ph):
    """A scheduled report that landed: eight rows of helpdesk tickets."""
    rows = '\n'.join('{"day": "2026-10-%02d", "tickets": %d}' % (d, 30 + d) for d in range(12, 20))
    sid = ph.s.save_source({'Channel': 'report', 'Address': 'Helpdesk tickets by day', 'Active': 1,
                            'ConfigJson': '{"type": "mssql", "title": "Helpdesk tickets by day"}'}, 't')
    ph.s.touch_source(sid)
    mid = ph.f.message(task_id=None, status='filed', channel='report', subject='Helpdesk tickets by day - 8 rows',
                       source_name='Helpdesk tickets by day', from_name='Helpdesk tickets by day', conversation_id=f'report:{sid}', body=rows)
    ph.f.route(mid, None, 'file', 'scheduled report', by='report')
    return mid


class FyiLeadsWithGotItTests(PhoneCase):
    """A8: an FYI led with "Put it on my list", and one tap sent a newsletter to an agent. FYI cards lead with Got it - their read-and-next
    - and offer no Send to agent."""

    def setUp(self):
        super().setUp()
        for s in ('FW: Quarterly newsletter', 'Office closed Monday'): self.f.filed_fyi(subject=s)
        self.ph.ready()

    def test_the_batch_is_passed_with_got_it_and_never_sent_to_an_agent(self):
        got = self.ph.walk()
        btns = got[-1][1]
        self.assertIn('Got it', btns); self.assertNotIn('Next', btns); self.assertNotIn('Send to agent', btns)
        self.assertNotIn('Got it', self.ph.tap('Got it')[-1][1])            # passed: the walk moved on

    def test_one_fyi_opened_leads_with_got_it_and_can_still_go_on_your_list(self):
        batch = self.ph.walk()
        one = self.ph.tap(next(b for b in batch[-1][1] if 'Quarterly newsletter' in b))
        btns = one[-1][1]
        self.assertEqual(btns[0], 'Got it', btns)
        self.assertNotIn('Send to agent', btns); self.assertIn('Put it on my list', btns); self.assertIn('Not ours', btns)
        self.assertNotIn('Put it on my list:', text_of(one))                   # no "then" line for a verb that does not lead
        self.assertRegex(text_of(self.ph.tap('Put it on my list')), r'TQ-\d{4} is on your list\.')


class ReportLeadsWithNextTests(PhoneCase):
    """A9: a report "needs nothing", yet its first choice was Put it on my list, which made it a to-do that then offered Reply to a report.
    A report card leads with Next, and Put it on my list goes."""

    def test_a_report_card_leads_with_next(self):
        _report(self.ph); self.ph.ready(); self.ph.opener()
        got = self.ph.tap('Walk Reports')
        self.assertIn('Helpdesk tickets by day', text_of(got))
        btns = got[-1][1]
        self.assertEqual(btns[0], 'Next', btns)
        self.assertNotIn('Put it on my list', btns)
        self.assertNotIn('Put it on my list:', text_of(got))


class ShortOpenerTests(PhoneCase):
    """A7: the day's opener offered nine options, walks beside section walks beside browse areas ("Walk me through my tasks" next to
    "Walk Tasks", "Reports" next to "Walk Reports"). It offers about four, and More… keeps every other one reachable."""
    EVERYTHING = {'Walk me through my tasks', 'Set up a report', 'Walk Tasks', 'Walk Reports', 'Walk FYI', 'Connections', 'Reports', 'Hub', 'Settings'}

    def setUp(self):
        super().setUp()
        _two_asks(self.f); _report(self.ph); self.f.filed_fyi(subject='Office closed Monday'); self.ph.ready()

    def test_the_opener_offers_four_clear_options(self):
        got = self.ph.opener()
        self.assertEqual(got[-1][1], ['Walk me through my tasks', 'Walk Reports', 'Walk FYI', 'More…'])
        self.assertIn('TASKS · 2', text_of(got))                               # the summary itself is unchanged

    def test_more_reaches_everything_the_nine_options_did(self):
        opener = self.ph.opener()[-1][1]
        more = self.ph.tap('More…')
        self.assertEqual(self.EVERYTHING - set(opener) - set(more[-1][1]), set(), more[-1][1])
        self.assertIn('Connections', text_of(self.ph.tap('Connections')))      # each still goes where it went

    def test_the_walk_off_the_menu_goes_straight_to_the_first_card(self):
        self.ph.opener(); self.ph.tap('More…')
        got = self.ph.tap('Walk me through my tasks')
        self.assertNotIn('TASKS · ', text_of(got)); self.assertRegex(text_of(got), r'TQ-\d{4}')


PATCH = ('Hi - I pushed a fix for the census export to the importers repo, branch ray/fix-census. '
         'Can your agent check it out, run the tests and merge it today?')


def _held(f, s):
    from taskuary.ingest import HOLD_TAG
    tid, _ = f._work('Patch for the census export', kind='coding', subject='Patch for the census export', from_name='Ray Colton',
                     from_email='ray.colton@vendor.example', body=PATCH, sent_at=f.ago(minutes=5))
    s.update_task(tid, {'Summary': PATCH}, 'triage'); s.tag_task(tid, HOLD_TAG)
    return tid


class HeldStrangerChoicesTests(PhoneCase):
    """A3: a held stranger's card offered Send to agent - one tap ran a new sender's branch. Until the sender is accepted it offers no
    hand-off: its choices lead with Trust them (the task page's own vouch) and Not ours, and the card says what it asks."""

    def test_a_held_card_offers_trust_and_not_ours_and_no_agent(self):
        _held(self.f, self.s); self.ph.ready()
        got = self.ph.walk()
        btns = got[-1][1]
        self.assertEqual(btns[:2], ['Trust them', 'Not ours'], btns)
        self.assertNotIn('Send to agent', btns); self.assertNotIn('Send to coding agent', btns)
        self.assertIn('Next', btns)
        self.assertIn('do you know this sender?', text_of(got))

    def test_trusting_them_lifts_the_hold_and_offers_the_hand_off_without_starting_anything(self):
        from taskuary import general
        from taskuary.ingest import HOLD_TAG
        tid = _held(self.f, self.s); self.ph.ready(); self.ph.walk()
        with mock.patch.object(general, 'start_session', side_effect=AssertionError('nothing starts on a vouch')):
            got = self.ph.tap('Trust them')
        self.assertFalse(self.s.task_has_tag(tid, HOLD_TAG))
        said = text_of(got)
        self.assertIn(f'TQ-{tid:04d}', said); self.assertIn('nothing has started', said); self.assertNotIn('New sender', said)
        self.assertIn('Send to agent', got[-1][1]); self.assertNotIn('Trust them', got[-1][1])


if __name__ == '__main__': unittest.main()
