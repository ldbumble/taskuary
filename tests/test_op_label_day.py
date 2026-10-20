"""A Remind me proposal says its day the way the page does ("Remind me: Fri 30 Oct"), not the model's ISO date: the button read
"Remind me: 2026-10-20" (2026-10-19 UI walk)."""
import re, unittest
from taskuary import buttons, concierge


class DeferLabel(unittest.TestCase):
    def test_the_day_is_said_not_stamped(self):
        for until in ('2030-10-30', 'tomorrow', 'monday', '2 weeks'):
            lbl = concierge.op_label('task.defer', {'until': until})
            self.assertTrue(lbl.startswith(buttons.label('defer') + ': '), lbl)
            self.assertNotRegex(lbl, r'\d{4}-\d{2}-\d{2}', until)
        self.assertEqual(concierge.op_label('task.defer', {'until': '2030-10-30'}), f"{buttons.label('defer')}: Wed 30 Oct")

    def test_words_it_cannot_read_are_kept_and_none_brings_it_back(self):
        self.assertEqual(concierge.op_label('task.defer', {'until': 'after the audit'}), f"{buttons.label('defer')}: after the audit")
        self.assertEqual(concierge.op_label('task.defer', {'until': 'none'}), 'Bring it back now')


if __name__ == '__main__': unittest.main()
