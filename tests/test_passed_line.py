"""A sender's new message handed to a LIVE agent (terminal.say_to_task, ingest._pass_turn): what is typed, and whether it was SENT.

Two failures the owner saw on one passed-in line: it sat typed and unsent in a working Claude's box ("Forming... 13m"), because the
"until it lands" check counted any printed byte as landing and a TUI mid-turn prints its spinner every frame; and what sat there
was the whole mail - signature, phone, address and the quoted chain under it - flattened onto one line. Faked sessions, no pty.
"""
import time, unittest
from unittest import mock

from taskuary import ingest, terminal, triage
from taskuary.store import MemoryStore

COLS, ROWS = 80, 32


class BusyTui:
    """A CLI's screen as the renderer reads it: a spinner that never stops, history and queued lines, then the input box.
    `takes` = which Enter presses submit (1-based); every other one is swallowed, as by a TUI still laying out a paste."""
    def __init__(self, task_id, takes=(1,)):
        self.task_id, self.alive, self.sid, self.cols, self.rows = task_id, True, 'tui1', COLS, ROWS
        self.box, self.queued, self.keys, self.enters, self.takes, self._n = '', [], [], 0, set(takes), 0
    def write(self, s):
        self.keys.append(s)
        if s == '\r':
            self.enters += 1
            if self.enters in self.takes and self.box: self.queued.append(self.box); self.box = ''
        elif s == '\x15': self.box = ''
        else: self.box += s
    @property
    def n(self): self._n += 50; return self._n               # the spinner repaints whether or not anything was sent
    def scrollback(self):
        lines = ['* Forming... 13m 38s (esc to interrupt)', *[f'> {q}' for q in self.queued], '-' * COLS, f'> {self.box}', '-' * COLS, '  ? for shortcuts']
        return '\x1b[2J\x1b[H' + '\r\n'.join(lines)


def wait(cond, secs=10):
    end = time.time() + secs
    while time.time() < end and not cond(): time.sleep(.05)
    return cond()


FAST = dict(SEED_ENTER=.05, TYPED_LAND=.6, TYPED_ECHO=1, SEED_CHUNK_GAP=0)


class TypedLineLandsTests(unittest.TestCase):
    def setUp(self):
        self.patches = [mock.patch.object(terminal, k, v) for k, v in FAST.items()]
        for p in self.patches: p.start()
    def tearDown(self):
        for p in self.patches: p.stop()

    def typed(self, tui, text):
        out = []
        terminal.type_into(tui, text, done=out.append)
        self.assertTrue(wait(lambda: out), 'type_into never said how it went')
        return out[0]

    def test_a_working_agent_has_the_line_submitted_and_queued(self):
        tui = BusyTui(1)
        self.assertTrue(self.typed(tui, 'Gail Moreno wrote again: please price the second site the same way.'))
        self.assertEqual((tui.box, tui.queued), ('', ['Gail Moreno wrote again: please price the second site the same way.']))

    def test_an_enter_the_tui_swallowed_is_pressed_again_until_the_box_empties(self):
        # the byte count read the spinner as the first Enter landing, and never pressed another
        tui = BusyTui(1, takes=(2,))
        self.assertTrue(self.typed(tui, 'x' * 3000 + ' and the October numbers too.'))
        self.assertEqual((tui.enters, tui.box), (2, ''))

    def test_a_line_that_never_leaves_the_box_is_cleared_and_said_as_not_delivered(self):
        tui = BusyTui(1, takes=())
        self.assertFalse(self.typed(tui, 'Use the staging copy, not production.'))
        self.assertEqual((tui.box, tui.queued), ('', []))
        self.assertIn('\x15', tui.keys); self.assertNotIn('\x1b', tui.keys)       # ^U clears; Esc would interrupt the agent

    def test_say_to_task_files_the_outcome_it_saw(self):
        s = MemoryStore(); tid = s.create_task({'Title': 't', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        for takes, said in (((1,), "Passed Gail Moreno's new message to the agent (typed into the live session)."),
                            ((), 'never took it, so it was cleared out of its box. It waits for you.')):
            tui, before = BusyTui(tid, takes), len(s.list_comments(tid))
            with mock.patch.dict(terminal.SESSIONS, {'tui1': tui}, clear=True), mock.patch.object(terminal, 'queue_codex', return_value=False):
                self.assertTrue(terminal.say_to_task(s, tid, {'FromName': 'Gail Moreno', 'Channel': 'email', 'BodyText': 'Price site two.'}, new=True))
                self.assertTrue(wait(lambda: len(s.list_comments(tid)) > before))
            self.assertIn(said, s.list_comments(tid)[-1]['Body'])

    def test_codex_takes_it_through_its_queue_and_says_so(self):
        s = MemoryStore(); tid = s.create_task({'Title': 't', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        with mock.patch.dict(terminal.SESSIONS, {'tui1': BusyTui(tid)}, clear=True), mock.patch.object(terminal, 'queue_codex', return_value=True), \
             mock.patch.object(terminal, 'type_into') as typed:
            terminal.say_to_task(s, tid, {'FromName': 'Gail Moreno', 'BodyText': 'Price site two.'}, new=True)
        typed.assert_not_called()
        self.assertIn('(queued for the live session)', s.list_comments(tid)[-1]['Body'])


SIGNED = 'Gail Moreno\nAccounts lead\nPhone: 555-0100\ngail@vendor.example'
CHAIN = ('From: Alex Doyle <alex@northwind.example>\nSent: Monday, October 27, 2026 9:12 AM\nTo: Gail Moreno <gail@vendor.example>\n'
         'Cc: Erin Blake <erin@northwind.example>\nSubject: RE: pilot plan\n\nThe first site is priced - see attached.')
NEW = 'Thanks - can you also price the second site the same way? Call me on (540) 555-0100 if the numbers look off.'
FOOTER = 'This message and any attachment are for the named recipient only.'


class NewWordsOnlyTests(unittest.TestCase):
    def said(self, msg, store=None):
        s = store or MemoryStore(); tid = s.create_task({'Title': 't', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        typed = []
        with mock.patch.dict(terminal.SESSIONS, {'p1': BusyTui(tid)}, clear=True), \
             mock.patch.object(terminal, 'tell', side_effect=lambda t, x, done=None: typed.append(x) or 'typed into'):
            self.assertTrue(terminal.say_to_task(s, tid, msg, new=True))
        return typed[0]

    def assertClean(self, line):
        for gone in ('@', '555-0100', '555', 'From:', 'Sent:', 'Subject:', 'first site is priced'): self.assertNotIn(gone, line)

    def test_own_text_is_preferred_over_the_whole_body(self):
        line = self.said({'FromName': 'Gail Moreno', 'FromEmail': 'gail@vendor.example', 'Channel': 'email',
                          'OwnText': f'{NEW}\n\n{SIGNED}', 'BodyText': f'{NEW}\n\n{SIGNED}\n\n{CHAIN}'})
        self.assertIn('price the second site the same way?', line); self.assertIn('Gail Moreno wrote again', line)
        self.assertClean(line)

    def test_an_empty_own_text_falls_back_to_the_body_without_its_quoted_chain(self):
        line = self.said({'FromName': 'Gail Moreno', 'Channel': 'email', 'OwnText': '', 'BodyText': f'{NEW}\n\n{SIGNED}\n\n{CHAIN}'})
        self.assertIn('price the second site', line); self.assertClean(line)

    def test_the_wrapper_triage_named_stays_out(self):
        line = self.said({'FromName': 'Gail Moreno', 'body': f'{NEW}\n\n{FOOTER}', 'wrapper': [FOOTER]})
        self.assertIn('second site', line); self.assertNotIn('named recipient', line)

    def test_the_sender_is_never_named_by_their_address(self):
        self.assertTrue(self.said({'FromEmail': 'gail@vendor.example', 'BodyText': NEW}).startswith('the sender wrote again'))
        self.assertTrue(self.said({'FromName': 'gail@vendor.example', 'BodyText': NEW}).startswith('the sender wrote again'))

    def test_the_assistants_road_hands_over_the_same_words(self):
        turn = ingest._pass_turn({'from_name': 'Gail Moreno', 'from_email': 'gail@vendor.example', 'channel': 'email',
                                  'own_text': f'{NEW}\n{SIGNED}', 'body': f'{NEW}\n{SIGNED}\n{CHAIN}'})
        self.assertIn('from Gail Moreno', turn); self.assertIn('second site the same way?', turn); self.assertClean(turn)
        self.assertIn('from the sender', ingest._pass_turn({'from_email': 'gail@vendor.example', 'body': NEW}))

    def test_only_addresses_and_phone_numbers_go(self):
        self.assertEqual(' '.join(triage.unreachable('Ring 555-0100 or +1 540 555 0100 x12, mail <gail@vendor.example>.').split()), 'Ring or , mail .')
        keep = 'Order 12345678 is due 2026-10-29 at 10:30 for $1,234.56 - invoice 2024-10045, 12.345 units, v1.2.3'
        self.assertEqual(triage.unreachable(keep), keep)


if __name__ == '__main__': unittest.main()
