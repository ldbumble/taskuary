"""The re-walk of the phone doorway (2026-10-22): what the phone SHOWS, through the same roads the walker drove - a typed
line or a tap in through the channel's own poll, the bubbles out of its own send. Each test is a scenario the walk found
still wrong after the fixes that claimed it. Invented people only: Alex Doyle, Gail Moreno, Ray Colton, northwind.example."""
import re, unittest
from unittest import mock

from taskuary import remote_assistant as ra
from tests.phone_transcript import GAIL, RAY, Phone, call, text_of

LONG = ("Hi Alex,\n\nFollowing up on the vendor review. " + " ".join(
    f"Point {i}: the renewal terms for line {i} need a decision on the price cap, the notice period and who signs off at Northwind."
    for i in range(1, 40)) + "\n\nCan you confirm by Thursday which of these you want to keep?\n\nThanks,\nGail")


class PhoneCase(unittest.TestCase):
    channel, brain = 'telegram', None

    def setUp(self):
        self.ph = Phone(self.channel, brain=self.brain)
        self.addCleanup(self.ph.close)
        self.s, self.f = self.ph.s, self.ph.f


class MoreTests(PhoneCase):
    """1: More on a long one-paragraph mail came as six Telegram bubbles - the first "THEY WROTE / > Hi Alex," alone, the rest cut
    every 1,200 characters mid-sentence ("a decision on the" | "price cap")."""

    def test_more_pages_a_long_mail_into_as_few_whole_sentence_bubbles_as_telegram_holds(self):
        self.f._work('Vendor review - 39 renewal points', kind='reply', subject='Vendor review - 39 renewal points', from_name=GAIL[0],
                     from_email=GAIL[1], body=LONG, sent_at=self.f.ago(hours=4))
        self.ph.ready()
        self.ph.walk()
        got = self.ph.tap('More')
        bodies = [t for t, _b in got]
        self.assertEqual(len(bodies), 2, [len(b) for b in bodies])             # ~4,700 characters: two of Telegram's 4,096
        self.assertTrue(all(len(b) <= 4096 for b in bodies), [len(b) for b in bodies])
        self.assertGreater(len(bodies[0]), 1000, bodies[0][:80])               # never a tiny first bubble
        for b in bodies[:-1]: self.assertRegex(b.rstrip(), r'[.!?]$', f'cut mid-sentence: ...{b[-60:]!r}')
        for b in bodies[1:]: self.assertRegex(b.lstrip('> '), r'^[A-Z]', f'starts mid-sentence: {b[:60]!r}')
        whole = ' '.join(re.sub(r'(?m)^>\s?', '', b) for b in bodies)
        self.assertEqual([whole.count(f'Point {i}:') for i in (1, 20, 39)], [1, 1, 1], 'every point once')
        self.assertIn('Reply', got[-1][1])                                     # and the choices come back under the last


class NoAiFreshInstallTests(PhoneCase):
    """2: a fresh install with no AI and nothing waiting answered "until then pick from the choices below" - and sent none."""
    channel = 'whatsapp'

    def test_with_nothing_to_pick_the_line_promises_no_choices(self):
        for said in ('hi', 'what can you do?', '1'):
            (text, poll), = self.ph.type(said)
            self.assertIn('Connect an AI', text)
            if not poll: self.assertNotIn('choices', text, f'{said!r} -> {text!r}')

    def test_with_a_card_on_the_table_the_choices_it_names_are_sent(self):
        self.f._work('Badge access for the new hire', subject='Badge access for the new hire', from_name=RAY[0], from_email=RAY[1],
                     body='Alex, the new AP clerk starts Monday. Can you get her a badge for floors 2 and 3?', sent_at=self.f.ago(hours=3))
        self.ph.ready(); self.ph.walk()
        (text, poll), = self.ph.type('can you chase Gail?')
        self.assertIn('choices below', text); self.assertIn('Next', poll)


class FailedSendToAgentTests(PhoneCase):
    """3: Send to agent whose agent would not start said "Done - Send to agent · TQ-0001. It is on TQ-0001, but the agent did not
    start - ..." and brought the same card back with Send to agent first again."""
    brain = staticmethod(lambda said: 'Ok.')

    def test_a_start_that_failed_says_so_why_and_what_next_never_done(self):
        from taskuary import general
        tid, _ = self.f._work('Badge access for the new hire', subject='Badge access for the new hire', from_name=RAY[0], from_email=RAY[1],
                              body='Alex, the new AP clerk starts Monday. Can you get her a badge for floors 2 and 3?', sent_at=self.f.ago(hours=3))
        self.ph.ready(); self.ph.walk()
        with mock.patch.object(general, 'start_session', side_effect=RuntimeError('the claude CLI is not installed on this computer')):
            got = self.ph.tap('Send to agent')
        said = text_of(got)
        self.assertNotIn('Done', said)
        self.assertRegex(said, r"(?i)did not start|didn't start")
        self.assertIn('the claude CLI is not installed on this computer', said)                 # why
        self.assertNotIn('I will tell you here when it finishes', said)                          # no promise over nothing
        ref = f'TQ-{tid:04d}'
        self.assertIn(ref, said)
        self.assertEqual(got[-1][1][:1], [f'Open {ref}'], got[-1][1])                          # what next: back to it, or on
        self.assertIn('Next', got[-1][1])
        self.assertFalse(any(b[:1] == ['Send to agent'] for _t, b in got), 'the same card, Send to agent first again')


if __name__ == '__main__': unittest.main()
