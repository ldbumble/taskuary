"""One row per goal, under Tasks - with news or quiet, walked past or not (the owner, 2026-10-22) - and never gone; its steps
are task rows of their own whoever holds them - they folded into it while an agent or a person had them (the owner, 2026-10-21)."""
import unittest
from datetime import datetime, timedelta
from unittest import mock
from taskuary import funnel, processing_unread
from taskuary.store import MemoryStore
from test_funnel import ago, store

checklist_id = MemoryStore.checklist_id


def settled():
    s = store()
    def settle():
        s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
    return s, settle


def rail(s, **kw):
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        return processing_unread.build(s, live_state=[], **kw)['items']


def day(n): return (datetime.now() + timedelta(days=n)).strftime('%Y-%m-%d')


def goal(s, due=None, steps=('Inventory the fields', 'Map the schema', 'Schema sign-off')):
    g = s.create_task({'Title': 'Migrate the census export off the old portal', 'Kind': 'task', 'Status': 'open',
                       'DoneWhen': 'the nightly census lands in the new ledger', 'DueAt': due or day(50)}, 'owner')
    if steps: s.set_task_checklist(g, list(steps), 'owner')
    return g


def card(s, tid): return next(i for i in rail(s, include_read=True) if i.get('tid') == tid)


class GoalRowTests(unittest.TestCase):
    def test_a_goal_with_no_boxes_is_fresh_and_in_tasks(self):
        s, settle = settled(); g = goal(s, steps=()); settle()
        c = card(s, g)
        self.assertEqual((c['kind'], c['steps'], c['steps_done'], c['due']), ('goal_fresh', 0, 0, day(50)))
        self.assertEqual(funnel.level_of(c), 'task'); self.assertTrue(c['back_at'].startswith(day(50)))

    def test_a_quiet_goal_on_track_sits_in_tasks_with_its_count(self):
        s, settle = settled(); g = goal(s)
        s.tick_checklist_item(g, checklist_id('Inventory the fields'), True, 'owner'); settle()
        c = card(s, g)
        self.assertEqual(c['kind'], 'goal'); self.assertEqual(funnel.level_of(c), 'task')
        self.assertTrue(c['why'].startswith('1 of 3'), c['why'])

    def test_a_goal_past_its_date_is_slipped_and_in_tasks(self):
        s, settle = settled(); g = goal(s, due=day(-4)); settle()
        c = card(s, g)
        self.assertEqual((c['kind'], c['news']), ('goal_slipped', True)); self.assertEqual(funnel.level_of(c), 'task')
        self.assertIn('slipped 4d', c['why'])

    def test_a_goal_with_every_box_done_is_not_slipped(self):
        s, settle = settled(); g = goal(s, due=day(-4), steps=('Only step',))
        s.tick_checklist_item(g, checklist_id('Only step'), True, 'owner'); settle()
        self.assertEqual(card(s, g)['kind'], 'goal')

    def test_a_step_closed_today_is_news(self):
        s, settle = settled(); g = goal(s)
        c = s.create_task({'Title': 'Map the schema', 'Kind': 'general', 'ParentId': g}, 'owner'); s.link_step(g, checklist_id('Map the schema'), c, 'owner')
        s.update_task(c, {'Status': 'done'}, 'agent:coding'); settle()
        k = card(s, g)
        self.assertTrue(k['news']); self.assertEqual(funnel.level_of(k), 'task')

    def test_a_goal_walked_past_stays_in_tasks_and_only_remind_me_puts_it_for_later(self):
        """GOALS STAY IN TASKS (the owner, 2026-10-22): Next walking past a goal with news moved it to For later (spec 2026-10-12)
        - a row jumping sections under the owner's hand, which the rail-order rule forbids."""
        row = {'kind': 'goal', 'lane': 'yours', 'order_band': 2, 'news': True}
        for seen in ({}, {'surfaced': True, 'put_down': True}, {'news': False}): self.assertEqual(funnel.level_of(row | seen), 'task', seen)
        self.assertEqual(funnel.level_of(row | {'deferred': True}), 'later')

    def test_a_goal_and_its_steps_made_in_one_second_keep_one_order(self):
        """A goal and the steps made with it arrive in the same second, and the tie fell to the rows' keys - hashes, so a step could
        stand above its goal. The tie goes to the task number: the goal first, then its steps as they were made."""
        at = ago(1)
        rows = [{'key': f'processing:{h}', 'tid': t, 'lane': 'yours', 'order_band': 2, 'arrived_at': at, **({'goal': 'TQ-0010'} if t > 10 else {'kind': 'goal'})}
                for h, t in (('a1', 12), ('ff', 10), ('0c', 11))]
        self.assertEqual([r['tid'] for r in sorted(rows, key=funnel.order_key)], [10, 11, 12])
        self.assertEqual([r['tid'] for r in sorted(rows[::-1], key=funnel.order_key)], [10, 11, 12])


class StepRowTests(unittest.TestCase):
    def test_a_child_waiting_on_them_is_its_own_row_and_the_goal_names_who(self):
        s, settle = settled(); g = goal(s)
        c = s.create_task({'Title': 'Schema sign-off', 'Kind': 'task', 'Status': 'waiting', 'Assignee': 'person:ray@northwind.example', 'ParentId': g}, 'owner')
        s.link_step(g, checklist_id('Schema sign-off'), c, 'owner'); settle()
        items = rail(s, include_read=True)
        self.assertEqual(card(s, c)['goal'], funnel.task_ref(g))                # a row of its own, naming its goal
        self.assertNotIn(c, [i.get('tid') for i in items if i.get('folded')])
        k = card(s, g)
        self.assertIn('Ray owes step 3', k['why']); self.assertEqual(k['who'], 'Ray')   # the holder, named, is the row's who

    def test_a_child_that_is_the_owners_move_stays_a_row_and_names_its_goal(self):
        s, settle = settled(); g = goal(s)
        c = s.create_task({'Title': 'Tell the sites the cutover date', 'Kind': 'task', 'Status': 'open', 'ParentId': g}, 'owner')
        s.link_step(g, checklist_id('Map the schema'), c, 'owner'); settle()
        k = card(s, c)
        self.assertEqual((k['lane'], k['folded'], k['goal']), ('yours', False, funnel.task_ref(g)))
        self.assertIn('step 2 is on you', card(s, g)['why'])

    def test_a_closed_goal_leaves_the_rail(self):
        s, settle = settled(); g = goal(s); settle()
        self.assertIn(g, [i.get('tid') for i in rail(s)])                       # open: on the rail, read or not
        s.update_task(g, {'Status': 'done'}, 'owner'); settle()
        self.assertNotIn(g, [i.get('tid') for i in rail(s)])


class DemoTests(unittest.TestCase):
    def test_the_demo_world_has_one_goal_with_a_started_step(self):
        from taskuary import demo
        from taskuary.store import is_goal
        s = MemoryStore(); demo.seed(s)
        goals = [t for t in s.list_tasks() if is_goal(t) and t.get('Status') == 'open']
        self.assertEqual(len(goals), 1)
        steps = s.goal_steps(goals[0]['TaskId'])
        self.assertGreaterEqual(len(steps), 4); self.assertTrue(any(x['child'] for x in steps))


class FixPassTests(unittest.TestCase):
    """The whole-branch review's findings (2026-10-12): a goal came back on the quiet hours instead of on news. A running
    child is a row of its own under Tasks, its icon ringed, since 2026-10-21 - it was folded into the goal's row."""
    def test_a_child_an_agent_is_running_is_its_own_row_under_tasks(self):
        s, settle = settled(); g = goal(s)
        c = s.create_task({'Title': 'Map the schema', 'Kind': 'coding', 'Status': 'in_progress', 'ParentId': g}, 'owner')
        s.link_step(g, checklist_id('Map the schema'), c, 'owner'); s.start_run(c, 'coding', 'map it', 'owner'); settle()
        row = card(s, c)
        self.assertEqual((row['lane'], funnel.level_of(row), row['goal']), ('working', 'task', funnel.task_ref(g)))
        k = card(s, g); self.assertIn('coding on step 2', k['why']); self.assertEqual(k['who'], 'coding')

    def test_a_read_goal_comes_back_on_a_childs_close_and_not_on_the_quiet_hours(self):
        s, settle = settled(); g = goal(s)
        c = s.create_task({'Title': 'Map the schema', 'Kind': 'general', 'ParentId': g}, 'owner'); s.link_step(g, checklist_id('Map the schema'), c, 'owner')
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()      # reads register once active
        k = card(s, g); funnel.settle(s, k['key'], 'surfaced', read=True, shown={k['key']: k.get('view_revision')}, put_down=True); settle()
        k = card(s, g); self.assertTrue(k['surfaced']); self.assertFalse(k['actionable']); self.assertEqual(funnel.level_of(k), 'task')   # read: walked past till news, still in Tasks (2026-10-22)
        later = datetime.now() + timedelta(hours=4)                         # past the quiet hours, with no news
        k = next(i for i in rail(s, include_read=True, now=later) if i.get('tid') == g)
        self.assertTrue(k['surfaced']); self.assertFalse(k['actionable']); self.assertEqual(funnel.level_of(k), 'task')
        s.update_task(c, {'Status': 'done'}, 'agent:coding'); settle()      # news: a step closed since you read it
        k = card(s, g); self.assertFalse(k.get('surfaced')); self.assertTrue(k['actionable']); self.assertEqual(funnel.level_of(k), 'task')
