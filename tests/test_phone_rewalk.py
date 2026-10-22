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


if __name__ == '__main__': unittest.main()
