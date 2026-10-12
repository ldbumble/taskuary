"""The chat on a goal (the owner, 2026-10-12, 'make sure the advisor works well ui/ux wise'): the opener says what the
goal is and what it needs, and the chips are a task's, not Next alone."""
import unittest
from taskuary import concierge
from taskuary.store import MemoryStore


def goal_item(kind='goal_slipped', why='3 of 7 · coder on step 5 · Ray owes step 4, chased twice · slipped 4d'):
    return {'key': 'processing:x', 'kind': kind, 'lane': 'yours', 'tid': 7, 'ref': 'TQ-0007', 'due': '2026-12-01', 'news': True,
            'title': 'Migrate the census export off the old portal', 'why': why, 'steps': 7, 'steps_done': 3}


class GoalOpenerTests(unittest.TestCase):
    def test_a_slipped_goal_says_its_date_its_facts_and_what_it_needs(self):
        line = concierge.fallback(goal_item(), opening=True)
        self.assertIn('Migrate the census export off the old portal', line); self.assertIn('1 Dec', line)
        self.assertIn('Ray owes step 4', line); self.assertIn('slipped', line)
        self.assertIn('move the date', line.lower())

    def test_a_fresh_goal_offers_its_first_step(self):
        line = concierge.fallback(goal_item('goal_fresh', 'no steps yet'), opening=True)
        self.assertIn('first step', line.lower())

    def test_a_goal_on_track_needs_nothing(self):
        line = concierge.fallback(goal_item('goal', '2 of 7 · coder on step 3'), opening=True)
        self.assertIn('nothing needs you', line.lower())


class GoalChipsTests(unittest.TestCase):
    def test_a_goal_gets_a_tasks_chips_not_next_alone(self):
        verbs = [c['verb'] if isinstance(c, dict) else c for c in concierge.chips_for(MemoryStore(), goal_item())]
        self.assertEqual(verbs, ['close', 'defer', 'next'])
