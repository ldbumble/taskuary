"""The re-walk of the phone doorway (2026-10-22): what the phone SHOWS, through the same roads the walker drove - a typed
line or a tap in through the channel's own poll, the bubbles out of its own send. Each test is a scenario the walk found
still wrong after the fixes that claimed it. Invented people only: Alex Doyle, Gail Moreno, Ray Colton, northwind.example."""
import json, re, time, unittest
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


class FailedAgentTests(PhoneCase):
    """4: an agent whose run FAILED while its session stayed open read "agent waiting on you · is waiting on you", no reason - the
    phone read workerstate.ended, which says nothing while a session is live. R2: a failed run reads "failed - <why>"."""
    channel = 'whatsapp'

    def _failed_with_its_session_open(self):
        from types import SimpleNamespace as NS
        from taskuary import terminal, workerstate as ws
        p = self.f.running('Fix the export', agent='claude')
        live = [{'taskId': p.tid, 'sid': 'sF', 'agent': 'claude', 'label': 'claude', 'waiting': True, 'idle': 300,
                 'started': self.f.ago(minutes=10), 'state': 'asking', 'tail': ['Which database should I use?']}]
        for x in (mock.patch.dict(terminal.SESSIONS, {'sF': NS(sid='sF', task_id=p.tid, alive=True, started=0, agent='claude', mode='')}),
                  mock.patch.object(terminal, 'live_sessions', return_value=live)):
            x.start(); self.addCleanup(x.stop)
        ws.record(self.s, p.tid, 'sF', 'working')
        ws.record(self.s, p.tid, 'sF', 'failed', text='The run stopped: the staging database refused the login.')
        self.ph.ready()
        return p.tid

    def assertReadsFailed(self, text):
        self.assertIn('failed - the run stopped: the staging database refused the login', text)
        self.assertNotIn('waiting on you', text); self.assertNotIn('asked you something', text); self.assertNotIn('answer the agent', text)

    def test_its_card_in_the_walk_reads_failed_with_the_reason(self):
        self._failed_with_its_session_open()
        self.assertReadsFailed(text_of(self.ph.walk()))

    def test_its_follow_up_reads_failed_too(self):
        tid = self._failed_with_its_session_open()
        self.s.set_setting(ra.PROMISES_KEY, json.dumps([{'tid': tid, 'channel': 'whatsapp', 'chat': self.ph.chat, 'connector_id': self.ph.cid,
                                                          'at': time.time(), 'lane': 'working', 'armed': True}]), 't')
        got = self.ph.push(lambda: ra.keep_promises(self.s, force=True))
        self.assertTrue(got); self.assertReadsFailed(text_of(got))


class DayPickerCancelTests(PhoneCase):
    """6: Cancel under Remind me's day picker answered "Left it - nothing moved." with nothing to tap: a dead end in the base code."""

    def test_cancel_brings_back_the_card_it_came_from(self):
        tid, _ = self.f._work('Badge access for the new hire', subject='Badge access for the new hire', from_name=RAY[0], from_email=RAY[1],
                              body='Alex, the new AP clerk starts Monday. Can you get her a badge for floors 2 and 3?', sent_at=self.f.ago(hours=3))
        self.ph.ready()
        card = self.ph.walk()
        self.assertIn('Remind me', card[-1][1])
        self.assertIn('Cancel', self.ph.tap('Remind me')[-1][1])
        got = self.ph.tap('Cancel')
        self.assertIn(f'TQ-{tid:04d}', text_of(got)); self.assertIn('Badge access for the new hire', text_of(got))
        self.assertEqual(got[-1][1], card[-1][1], 'the same card, with its own choices')


PATCH = ('Hi - I pushed a fix for the census export to the importers repo, branch ray/fix-census. '
         'Can your agent check it out, run the tests and merge it today?')


class HeldStrangerTests(PhoneCase):
    """F8: a held stranger's card printed their words twice - once as the summary's two sentences, then quoted whole under them.
    The fix compared the quote with each line alone; the summary is the body split in two, so neither line held it."""
    channel = 'whatsapp'

    def test_their_words_are_printed_once(self):
        from taskuary.ingest import HOLD_TAG
        tid, _ = self.f._work('Patch for the census export', kind='coding', subject='Patch for the census export', from_name='Ray Colton',
                              from_email='ray.colton@vendor.example', body=PATCH, sent_at=self.f.ago(minutes=5))
        self.s.update_task(tid, {'Summary': PATCH}, 'triage'); self.s.tag_task(tid, HOLD_TAG)
        self.ph.ready()
        card = text_of(self.ph.walk())
        self.assertIn('New sender', card)
        for said in ('pushed a fix for the census export', 'run the tests and merge it today'):
            self.assertEqual(card.count(said), 1, card)


if __name__ == '__main__': unittest.main()
