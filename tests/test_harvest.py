"""Reading a terminal. The wrap-up report is written from this text, so if the rendering is wrong
the report is confidently wrong - and it was: a real 27-minute Claude Code session harvested down
to 216 characters of glued-together debris, and the AI dutifully reported that the transcript was
unreadable. The sequences below are the ones a real agent CLI actually emits.
"""
import unittest
from taskuary.terminal import declutter, harvest, letters, plain, render

ESC = '\x1b'


class Fake:
    """Just enough Term for harvest()."""
    def __init__(self, raw, seeded='', rows=32, cols=110):
        self._raw, self.seeded, self.rows, self.cols = raw, seeded, rows, cols
    def scrollback(self): return self._raw


class RenderTests(unittest.TestCase):
    def test_absolute_column_moves_are_gaps_not_nothing(self):
        """The bug, in one line. Claude Code lays a two-column layout out with ESC[<n>G; deleting
        those instead of obeying them ran every word together - "Run/inittocreateaCLAUDE.md"."""
        raw = f'Welcome back{ESC}[54GTips for getting started\r\n{ESC}[54GRun /init to create a CLAUDE.md file\r\n'
        out = render(raw, cols=110, rows=6)
        self.assertIn('Run /init to create a CLAUDE.md file', out)
        self.assertNotIn('Run/inittocreate', out)
        # the two columns really are side by side, as the screen shows them
        self.assertRegex(out, r'Welcome back\s{10,}Tips for getting started')
        # ...and this is precisely what the hand-rolled renderer could not do: it deletes the move,
        # so the two columns collide and the words fuse
        self.assertIn('Welcome backTips for getting started', plain(raw))

    def test_cursor_down_and_erase_land_where_the_screen_puts_them(self):
        raw = f'first line{ESC}[1B{ESC}[1Gsecond line\r\n'
        out = render(raw, cols=40, rows=6)
        self.assertIn('first line', out)
        self.assertIn('second line', out)
        self.assertNotIn('first linesecond', out.replace(' ', ''))

    def test_a_repainted_spinner_does_not_become_a_hundred_lines(self):
        frames = ''.join(f'\r{ESC}[2K{ESC}[36m*{ESC}[0m Levitating... ({i}s - esc to interrupt)' for i in range(200))
        raw = f'{frames}\r{ESC}[2KDone: the batch date now comes from the payroll date field.\r\n'
        out = declutter(render(raw, cols=110, rows=10))
        self.assertIn('the batch date now comes from the payroll date field', out)
        self.assertNotIn('Levitating', out)
        self.assertLess(len(out.splitlines()), 6)

    def test_a_stream_it_cannot_parse_still_yields_the_words(self):
        """Falling back beats losing the session: a transcript is the only record of the work."""
        self.assertIn('real work here', render('real work here\r\n' + '\x1b' * 3, cols=80, rows=4))
        self.assertEqual(render(''), '')
        self.assertEqual(render('   '), '')


class HarvestTests(unittest.TestCase):
    AGENT = ('I read the payroll import and the GLBATCH header - the adjustment rows carry the date of '
             'the FIRST line, not the payroll date, so they post to the wrong month.\r\n'
             'Fixed in run_pto_intacct.py: the batch date now comes from the payroll date field.\r\n')

    def test_the_agents_words_survive_and_the_chrome_does_not(self):
        banner = (f'{ESC}[2m+--------------------------------+{ESC}[0m\r\n'
                  f'| Claude Code v2.1.237           |\r\n'
                  f'+--------------------------------+\r\n')
        raw = banner + self.AGENT + f'{ESC}[2m? for shortcuts{ESC}[0m\r\n  8593 tokens\r\n'
        out = harvest(Fake(raw))
        self.assertIn('adjustment rows carry the date', out)
        self.assertIn('run_pto_intacct.py', out)
        self.assertNotIn('? for shortcuts', out)
        self.assertNotIn('8593 tokens', out)
        self.assertGreater(letters(out), 160)

    def test_the_prompt_we_typed_is_not_read_back_as_something_the_agent_said(self):
        """A pty echoes what was typed. The seed is 8000 characters of task context, and a real
        terminal WRAPS it across dozens of lines - so matching a fixed 60-char head never fired."""
        seed = ('TASK TQ-0014 - Payroll file imports. REPO: northwind/TopE - you are already in it. '
                'FROM Dana Reyes on email, subject "Payroll File Imports": the adjustments import '
                'into the wrong month and finance has to unpick it every run. RULES: work only here.')
        # the echo, wrapped the way a terminal wraps it inside its input box
        wrapped = '\r\n'.join(f'| {seed[i:i + 60]} |' for i in range(0, len(seed), 60))
        out = harvest(Fake(wrapped + '\r\n' + self.AGENT, seeded=seed))
        self.assertIn('adjustment rows carry the date', out)
        self.assertNotIn('subject "Payroll File Imports"', out)
        self.assertNotIn('TASK TQ-0014', out)

    def test_a_session_that_printed_nothing_reports_nothing_rather_than_debris(self):
        self.assertEqual(harvest(Fake('')), '')
        # ...and pure chrome must not masquerade as a transcript
        self.assertLess(letters(harvest(Fake(f'{ESC}[?1003h{ESC}[3H{ESC}[2K'))), 20)

    def test_the_216_character_regression(self):
        """The exact shape of the failure: private-mode sets, absolute positioning and a wrapped
        question. plain() left "1003hh", a literal "3H", and "toadditto.gitignoreanddeleteit"."""
        raw = (f'{ESC}[?1003h{ESC}[?25l'
               f'Want me{ESC}[24G to add it to .gitignore and delete it?{ESC}[1B{ESC}[1G'
               f"It'll keep showing up as noise in git status otherwise.\r\n"
               f'{ESC}[3H{ESC}[2K')
        out = harvest(Fake(raw))
        self.assertNotIn('1003h', out)
        self.assertNotIn('3H', out)
        self.assertIn('.gitignore', out)
        self.assertIn('git status', out)
        self.assertIn('add it to .gitignore and delete it', out)      # the spaces the gap stood for
        self.assertIn("It'll keep showing up as noise in git status", out)


if __name__ == '__main__':
    unittest.main()
