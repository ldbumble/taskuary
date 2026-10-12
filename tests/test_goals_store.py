"""A goal is a task with a done-when sentence; its boxes may point at child tasks (spec 2026-10-12, build step 1)."""
import unittest
from taskuary.store import MemoryStore, is_goal

checklist_id = MemoryStore.checklist_id          # a staticmethod on the store, not a module function


def goal(s, title='Migrate the census export off the old portal', steps=('Inventory the fields', 'Map the schema', 'Schema sign-off')):
    tid = s.create_task({'Title': title, 'Kind': 'task', 'Status': 'open', 'DoneWhen': 'the nightly census lands in the new ledger',
                         'DueAt': '2026-12-01'}, 'owner')
    s.set_task_checklist(tid, list(steps), 'owner')
    return tid


class ColumnsTests(unittest.TestCase):
    def test_done_when_and_parent_are_written_and_read(self):
        s = MemoryStore()
        g = goal(s)
        c = s.create_task({'Title': 'Map the schema', 'Kind': 'general', 'ParentId': g}, 'owner')
        self.assertEqual(s.get_task(g)['DoneWhen'], 'the nightly census lands in the new ledger')
        self.assertEqual(s.get_task(c)['ParentId'], g)
        self.assertTrue(is_goal(s.get_task(g))); self.assertFalse(is_goal(s.get_task(c))); self.assertFalse(is_goal(None))

    def test_children_come_back_oldest_first(self):
        s = MemoryStore()
        g = goal(s)
        a = s.create_task({'Title': 'first', 'ParentId': g}, 'owner'); b = s.create_task({'Title': 'second', 'ParentId': g}, 'owner')
        self.assertEqual([t['TaskId'] for t in s.children(g)], [a, b])
        self.assertEqual(s.children(b), [])


class StepsTests(unittest.TestCase):
    def test_link_step_puts_the_child_on_the_box_and_the_parent_on_the_child(self):
        s = MemoryStore()
        g = goal(s)
        c = s.create_task({'Title': 'Map the schema', 'Kind': 'general', 'ParentId': g}, 'owner')
        self.assertTrue(s.link_step(g, checklist_id('Map the schema'), c, 'owner'))
        self.assertFalse(s.link_step(g, 'nosuchbox', c, 'owner'))
        steps = s.goal_steps(g)
        self.assertEqual([x['text'] for x in steps], ['Inventory the fields', 'Map the schema', 'Schema sign-off'])
        self.assertEqual(steps[1]['tid'], c); self.assertEqual(steps[1]['child']['TaskId'], c); self.assertIsNone(steps[0]['child'])

    def test_closing_a_child_ticks_the_parents_box_and_dropping_does_not(self):
        s = MemoryStore()
        g = goal(s)
        a = s.create_task({'Title': 'Map the schema', 'ParentId': g}, 'owner'); s.link_step(g, checklist_id('Map the schema'), a, 'owner')
        b = s.create_task({'Title': 'Schema sign-off', 'ParentId': g}, 'owner'); s.link_step(g, checklist_id('Schema sign-off'), b, 'owner')
        s.update_task(a, {'Status': 'done'}, 'agent:coder')          # whoever closes it
        s.update_task(b, {'Status': 'dropped'}, 'owner')
        done = {x['text']: x['done'] for x in s.goal_steps(g)}
        self.assertEqual(done, {'Inventory the fields': False, 'Map the schema': True, 'Schema sign-off': False})
        self.assertEqual(s.get_task(g)['Status'], 'open')             # the parent is never closed for it

    def test_a_replan_keeps_a_started_boxs_child_when_its_words_are_unchanged(self):
        s = MemoryStore()
        g = goal(s)
        c = s.create_task({'Title': 'Map the schema', 'ParentId': g}, 'owner'); s.link_step(g, checklist_id('Map the schema'), c, 'owner')
        s.set_task_checklist(g, ['Inventory the fields', 'Map the schema', 'Schema sign-off', 'Switch the old export off'], 'triage')
        self.assertEqual([x['tid'] for x in s.goal_steps(g)], [None, c, None, None])

    def test_goal_steps_of_a_task_with_no_checklist_is_empty(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'plain', 'DoneWhen': 'it is done'}, 'owner')
        self.assertEqual(s.goal_steps(t), [])
