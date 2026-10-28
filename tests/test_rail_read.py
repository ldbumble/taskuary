"""pipe.read: every row on the work rail with what its sender wrote, in one call - "summarize the FYI emails for me" (2026-10-28)."""
import unittest
from unittest import mock
from taskuary import concierge, ingest, lookups, toolcatalog
import tests.test_assistant_reactions as T

PEOPLE = ('Erin Blake', 'Gail Moreno', 'Paula Vance', 'Ray Colton', 'Marcus Reed', 'Omar Keller')

def fyi(s, n, who='Erin Blake', words='The loading dock reopens Monday.', hours=1):
    first = who.split()[0].lower()
    T.arrive(s, subject=f'Heads up {n}', body=f'{words} (note {n})\n\nOn Friday, Gail wrote:\n> the old chain under it', who=who,
             email=f'{first}@northwind.example', conv=f'c:fyi{n}', hours=hours, llm=T.brain('fyi', None, 'telling you something'))

def world(n_fyi=3):
    s = T.store()
    with mock.patch.object(ingest, '_spawn'):
        T.arrive(s, subject='Can you fix the export?', body='The nightly export drops inter-company rows.', who='Ray Colton',
                 email='ray@northwind.example', llm=T.brain('task', 'general'))
        for n in range(n_fyi): fyi(s, n, PEOPLE[n % len(PEOPLE)], hours=1 + n * 0.1)
    return s

def read(s, **p): return concierge.read_op(s, 'pipe.read', p)


class RailReadTests(unittest.TestCase):
    def test_the_fyi_section_comes_back_whole_with_each_senders_own_words(self):
        s = world(3)
        out = read(s, section='fyi')
        for n in range(3): self.assertIn(f'Heads up {n}', out); self.assertIn(f'(note {n})', out)
        self.assertIn('Erin Blake', out); self.assertIn('Paula Vance', out)
        self.assertNotIn('the old chain under it', out)           # the quoted history is cut, as on the batch card
        self.assertNotIn('Can you fix the export?', out)          # a task is not an FYI
        self.assertRegex(out, r'THE RAIL: \d+ rows \(.*FYI 3')

    def test_a_section_or_a_sender_narrows_it_and_a_wrong_name_says_the_right_ones(self):
        s = world(3)
        self.assertIn('Can you fix the export?', read(s, section='tasks'))
        self.assertNotIn('Heads up', read(s, section='task'))
        everything = read(s)
        self.assertIn('Can you fix the export?', everything); self.assertIn('Heads up 2', everything)
        gail = read(s, who='gail')
        self.assertIn('Heads up 1', gail); self.assertNotIn('Heads up 0', gail)
        self.assertIn('no rail section', read(s, section='bogus'))

    def test_a_long_lane_shortens_its_quotes_then_says_how_many_it_left_out(self):
        s = world(0); s.set_setting('funnel_max', '200', 't')       # the rail itself holds all 130
        long_words = 'The quarterly freight audit found nothing new. ' * 30
        with mock.patch.object(ingest, '_spawn'):
            for n in range(130): fyi(s, n, PEOPLE[n % len(PEOPLE)], long_words, hours=1 + n * 0.01)
        out = read(s, section='fyi')
        self.assertLessEqual(len(out), lookups.RAIL_READ_CHARS + 400)
        self.assertLessEqual(len(out), concierge.read_chars('pipe.read'))    # the turn never cuts it silently
        shown = out.count('\n- ')
        self.assertRegex(out, rf'\.\.\.and {130 - shown} more not shown - narrow it')
        self.assertGreater(shown, 60)                                         # quotes shrank before rows were dropped
        few = read(world(2), section='fyi')
        self.assertNotIn('more not shown', few)
        s.set_setting('funnel_max', '30', 't')                                # ...and what its limit holds back is said
        self.assertRegex(read(s, section='fyi'), r"\d+ more wait behind the rail's limit")

    def test_the_turn_is_told_the_whole_rail_and_the_read_that_holds_it(self):
        items = [{'ref': f'TQ-{n:04}', 'who': 'Erin Blake', 'title': f'Task {n}', 'lane': 'yours'} for n in range(25)]
        items += [{'mid': 100 + n, 'who': 'Gail Moreno', 'title': f'Notice {n}', 'lane': 'fyi'} for n in range(12)]
        block = concierge._rail_block({'items': items})
        self.assertIn('...and 17 more', block)
        self.assertIn('THE WHOLE RAIL: 37 rows (Tasks 25, FYI 12)', block)
        self.assertIn('pipe.read', block)

    def test_it_is_a_look_up_the_model_is_offered(self):
        self.assertTrue(toolcatalog.is_read('pipe.read')); self.assertEqual(toolcatalog.valid('pipe.read', {}), '')
        self.assertIn('pipe.read', toolcatalog.block()); self.assertIn('summarize my FYI', toolcatalog.describe('pipe.read'))


if __name__ == '__main__': unittest.main()
