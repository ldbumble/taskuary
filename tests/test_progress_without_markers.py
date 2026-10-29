"""The agent's progress box showed Taskuary's reply markers, and the answer twice: a CLI's final text streams in as a progress line
too, and the progress filter took out the ask marker only (2026-10-15). The reply is shown once, as the answer; what is left of a
progress line is the agent's own words, with no [[TASKUARY-...]] plumbing in it."""
import unittest
from pathlib import Path

from taskuary import selfclose

SAID = 'Looked it up.\n[[TASKUARY-REPLY]]\n2 + 2 is 4.\n[[/TASKUARY-REPLY]]\n[[TASKUARY-ATTACH: C:/work/sum.csv]]\n'


class ForScreenTests(unittest.TestCase):
    def test_the_reply_block_and_attach_lines_leave_the_progress_line(self):
        self.assertEqual(selfclose.for_screen(SAID), 'Looked it up.')

    def test_a_progress_line_that_was_only_the_reply_is_empty(self):
        self.assertEqual(selfclose.for_screen('[[TASKUARY-REPLY]]\n2 + 2 is 4.\n[[/TASKUARY-REPLY]]'), '')

    def test_the_ask_marker_still_goes_and_plain_words_stay(self):
        self.assertEqual(selfclose.for_screen('The page is open.\n[[TASKUARY-ASK]] Signed in? | Yes | No'), 'The page is open.')
        self.assertEqual(selfclose.for_screen('nothing to strip'), 'nothing to strip')

    def test_an_answer_the_agent_also_wrote_out_is_said_once(self):
        """It wrote the answer, then the same words in the reply block; taking the markers out left both (2026-10-15)."""
        said = '3 + 3 is 6.\n\n[[TASKUARY-REPLY]]\n3 + 3 is 6.\n[[/TASKUARY-REPLY]]'
        self.assertEqual(selfclose.reply_marker(said), ('3 + 3 is 6.', '3 + 3 is 6.'))
        self.assertEqual(selfclose.reply_marker('Here is the draft:\n[[TASKUARY-REPLY]]\nHi Erin, done.\n[[/TASKUARY-REPLY]]'),
                         ('Here is the draft:\nHi Erin, done.', 'Hi Erin, done.'))

    def test_the_done_line_leaves_the_progress_line(self):
        """[[TASKUARY-DONE]] stayed in the box, and with it the last paragraph no longer matched the answer, so the answer was
        drawn twice (walk 2026-10-29). Its sentence is the task's comment, never progress."""
        self.assertEqual(selfclose.for_screen('Booked the room for Thursday.\n[[TASKUARY-DONE]] Booked the room.'), 'Booked the room for Thursday.')
        self.assertEqual(selfclose.for_screen('[[TASKUARY-DONE]]: Booked the room.'), '')
        self.assertEqual(selfclose.chat_marker('Booked it.\n[[TASKUARY-DONE]] Booked the room.'), ('Booked it.', 'Booked the room.'))

    def test_the_general_chat_filters_its_progress_through_it(self):
        src = (Path(selfclose.__file__).parent / 'general.py').read_text(encoding='utf-8')
        self.assertIn('detail = _sc.for_screen(detail)', src)


if __name__ == '__main__': unittest.main()
