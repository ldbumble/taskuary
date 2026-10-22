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


def _two_asks(f):
    a, _ = f._work('Badge access for the new hire', subject='Badge access for the new hire', from_name=RAY[0], from_email=RAY[1],
                   body='Alex, the new AP clerk starts Monday. Can you get her a badge for floors 2 and 3?', sent_at=f.ago(hours=3))
    b, _ = f._work('Visitor parking for Friday', subject='Visitor parking for Friday', from_name=GAIL[0], from_email=GAIL[1],
                   body='Can we get a visitor parking list for Friday? Security needs it by Thursday.', sent_at=f.ago(hours=2))
    return a, b


class TypedWalkTests(PhoneCase):
    """F9: "walk me through my tasks" typed. The tool the model is told to call is script.start; on the phone that came back as
    "Start a script by its name: ... Nothing happens until you say yes", and the yes said "Done - Start a script ..." and walked
    nowhere. The F9 fix sat on the auto road, which a typed script never took. A walk sends nothing: it starts, at the table."""
    channel = 'whatsapp'
    brain = staticmethod(lambda said: ('Starting with the first one.\n' + call('script.start', name='walk me through my tasks'))
                         if 'walk me through' in said.lower() else 'Ok.')

    def test_a_typed_walk_starts_at_the_card_on_the_table(self):
        self.ph.ready()
        self.ph.s.set_setting(ra.MORNING_KEY, '1', 't')
        a, b = _two_asks(self.f); self.ph.ready()
        first = text_of(self.ph.walk())
        table = next(f'TQ-{t:04d}' for t in (a, b) if f'TQ-{t:04d}' in first)
        got = self.ph.type('walk me through my tasks')
        said = text_of(got)
        self.assertNotIn('Nothing happens until you say yes', said); self.assertNotIn('Start a script', said)
        self.assertIn(table, said, said)                                       # the card on the table, not the one after it
        self.assertEqual({'Send to agent', 'Next'} - set(got[-1][1]), set(), got[-1][1])

    def test_a_typed_set_up_is_its_question_not_the_tools_description(self):
        with mock.patch.object(self.ph, 'brain_fn', lambda said: 'Ok.\n' + call('script.start', name='set up a report')):
            said = text_of(self.ph.type('set up a report'))
        self.assertIn('Tell me what to set up', said)
        self.assertNotIn('Start a script', said); self.assertNotIn('Nothing happens until you say yes', said)


class ReceiptTests(PhoneCase):
    """F13: receipts in plain past tense, said once. The re-walk still read "Done - Not ours · Printer on 3 is jammed again.", "Done - Remind
    me: Fri 23 Oct · TQ-0001. Away until ...", and the model's "Ok." stapled onto "Not sent - ..." - the past tense covered the send and
    the close only, and the "Ok." came from the failure's own explanation (concierge.recover), not the turn."""
    brain = staticmethod(lambda said: ('Putting it away until tomorrow.\n' + call('task.defer', until='tomorrow 9am'))
                         if 'remind me' in said.lower() else 'Ok.')

    def setUp(self):
        super().setUp()
        self.a, self.b = _two_asks(self.f); self.ph.ready()
        self.first = text_of(self.ph.walk())
        self.ref = next(f'TQ-{t:04d}' for t in (self.a, self.b) if f'TQ-{t:04d}' in self.first)

    def test_not_ours_says_what_happened(self):
        (receipt, _), *rest = self.ph.tap('Not ours')
        self.assertRegex(receipt, r'^(Taskuary:\n)?(TQ-\d{4} filed as not ours|Filed as not ours: Badge access for the new hire)\.$')
        self.assertTrue(rest and rest[-1][1], 'the next card follows with its choices')

    def test_a_typed_remind_and_its_yes_say_when_it_is_back(self):
        said = text_of(self.ph.type('remind me about this tomorrow'))
        if 'yes, go ahead' in self.ph.choices(): said = text_of(self.ph.tap('yes, go ahead'))
        self.assertNotIn('Done -', said); self.assertNotIn('Nothing happens until you say yes', said)
        self.assertRegex(said, rf'{self.ref} is away until \w{{3}} \d+ \w{{3}}')



class FailedSendReceiptTests(PhoneCase):
    """F13: "Not sent - no mailbox is connected to send from. The reply is kept; TQ-0001 is where it was. Ok." - the model's bare
    acknowledgement, asked to explain the failure (concierge.recover), went out after the receipt."""
    brain = staticmethod(lambda said: 'Ok.')

    def test_a_failed_send_is_not_followed_by_the_models_ok(self):
        self.f.pending_draft(title='Q3 vendor contract renewal', subject='Q3 vendor contract renewal', from_name=GAIL[0], from_email=GAIL[1],
                             body='Are we renewing the Payworth contract for Q3?', draft='Hi Gail - yes, renew it for Q3.', sent_at=self.f.ago(hours=1))
        self.ph.ready(); self.ph.walk()
        said = text_of(self.ph.tap('Send'))
        self.assertIn('Not sent', said)
        self.assertNotRegex(said, r'\bOk\.', said)


class ReportTaskTests(PhoneCase):
    """F16: rows through chatformat.table everywhere, never raw JSON - "including after Put it on my list". The report card was fixed;
    the TASK it became still printed its summary, which is the rows, as one line of braces and quotes."""
    channel = 'whatsapp'

    def test_a_report_put_on_the_list_shows_its_rows_as_a_table(self):
        rows = '\n'.join('{"day": "2026-10-%02d", "tickets": %d}' % (d, 30 + d) for d in range(12, 20))
        sid = self.s.save_source({'Channel': 'report', 'Address': 'Helpdesk tickets by day', 'Active': 1,
                                  'ConfigJson': '{"type": "mssql", "title": "Helpdesk tickets by day"}'}, 't')
        self.s.touch_source(sid)
        mid = self.f.message(task_id=None, status='filed', channel='report', subject='Helpdesk tickets by day - 8 rows',
                             source_name='Helpdesk tickets by day', from_name='Helpdesk tickets by day', conversation_id=f'report:{sid}', body=rows)
        self.f.route(mid, None, 'file', 'scheduled report', by='report')
        self.ph.ready(); self.ph.opener()
        self.ph.tap('Walk Reports')
        self.ph.tap('Put it on my list')
        self.ph.ready()                                                        # the rail takes the new task in, as the background does
        said = text_of(self.ph.walk())
        self.assertIn('TQ-', said)
        self.assertNotIn('{"', said, said)
        self.assertIn('2026-10-12 · 42', said)
        self.assertEqual(said.count('2026-10-12'), 1, said)


class UnheardVoiceTests(PhoneCase):
    """F22: a voice note that could not be heard named the fix's place twice on Telegram - "...add one under Connections > Voice. Type
    it, or add a voice connector under Connections → AI — voice." The fix skipped the second only when the reason used the app's
    own spelling of the place; a reason that names it any other way still got it again."""

    def setUp(self):
        super().setUp()
        _two_asks(self.f); self.ph.ready(); self.card = self.ph.walk()

    def _heard(self, why=None):
        from taskuary import voice
        with mock.patch.object(voice, 'transcribe', side_effect=RuntimeError(why)) if why else mock.patch.object(voice, 'transcribe', wraps=voice.transcribe):
            got = self.ph.voice()
        (said, btns), = got
        self.assertEqual(btns, self.card[-1][1], 'the card\'s choices still stand')
        self.assertEqual(getattr(self.ph, 'reacted', 0), 1, 'the note gets its thumb')
        return said

    def test_no_voice_connector_names_the_place_once(self):
        said = self._heard()
        self.assertEqual(said.count('Connections'), 1, said)

    def test_a_reason_that_already_says_where_is_not_told_again(self):
        said = self._heard('no voice connector is set up - add one under Connections > Voice')
        self.assertEqual(said.count('Connections'), 1, said)


class ClearFyiTests(PhoneCase):
    """F23: "clear all the FYI" with none left answered "Nothing waiting matches kind: fyi, so there is nothing to clear." and nothing to
    tap. The fix put the hit's receipt in words; the miss still read the selector out and dropped the card's choices."""
    brain = staticmethod(lambda said: call('pipe.clear', select={'kind': 'fyi'}) if 'clear' in said.lower() else 'Ok.')

    def test_nothing_to_clear_is_said_in_words_with_the_cards_choices(self):
        _two_asks(self.f); self.ph.ready()
        card = self.ph.walk()
        (said, btns), = self.ph.type('clear all the FYI')
        self.assertNotIn('kind:', said); self.assertIn('FYI', said)
        self.assertEqual(set(btns), set(card[-1][1]), said)                   # the table card's own choices, still live

    def test_with_some_it_says_how_many_it_marked(self):
        for s in ('Weekly platform digest', 'Office closed Monday'): self.f.filed_fyi(subject=s)
        _two_asks(self.f); self.ph.ready(); self.ph.walk()
        self.assertIn('Mark 2 FYI read', text_of(self.ph.type('clear all the FYI')))
        self.assertRegex(text_of(self.ph.tap('yes, go ahead')), r'Marked 2 FYI read')


class AlikeFyiTests(PhoneCase):
    """F26: lines alike in an FYI batch "told apart by who sent them, not (2)". The re-walk's were the same notice from the same sender
    in the same minute, so neither the sender nor the age told them apart, and the buttons read "... (just now)" and "... (just now) (2)"."""

    def test_lines_alike_read_as_which_of_how_many(self):
        for _ in range(3): self.f.filed_fyi(subject='New expense policy PDF')
        self.f.filed_fyi(subject='Office closed Monday')
        self.ph.ready()
        btns = [b for b in self.ph.walk()[-1][1] if 'expense policy' in b]          # the walk brings FYI together, four at a time
        self.assertEqual(len(btns), 3, btns); self.assertEqual(len(set(btns)), 3, btns)
        self.assertFalse([b for b in btns if re.search(r'\(\d\)$|just now', b)], btns)
        self.assertEqual(sorted(re.search(r'\((\d) of 3\)$', b).group(1) for b in btns), ['1', '2', '3'], btns)


class OpenerAgentNameTests(PhoneCase):
    """F6 in the opener: the card said General agent, the day's opener still listed "Coding agent - Printer vendor call". The opener's
    rows named the agent with no store to read the task's kind by, and a general run carries no session mode to say it."""

    def test_a_general_agents_row_in_the_opener_says_general_agent(self):
        tid, _ = self.f._work('Printer vendor call - floor 3', status='in_progress', kind='general', subject='Printer vendor call - floor 3',
                              from_name=RAY[0], from_email=RAY[1], body='Can someone call the printer vendor about floor 3?', sent_at=self.f.ago(hours=1))
        self.f.run(tid, agent='claude')
        self.ph.ready()
        (said, _), = self.ph.opener()
        row = next(l for l in said.splitlines() if 'Printer vendor call' in l)
        self.assertNotIn('Coding agent', row); self.assertNotIn('claude', row)


if __name__ == '__main__': unittest.main()
