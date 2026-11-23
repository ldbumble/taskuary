"""The goal's doors: its steps, starting one, planning them (spec 2026-10-12, build step 1)."""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import concierge, goals, server

c = TestClient(server.app)
checklist_id = server.store.checklist_id


import contextlib
@contextlib.contextmanager
def planner(steps):
    "The goal planner's model, answering `steps` (goals.steps_of)."
    with mock.patch.object(concierge, 'brain', return_value=object()), mock.patch.object(goals, 'steps_of', return_value=list(steps)) as ex: yield ex


def goal(done_when='the nightly census lands'):
    return c.post('/api/tasks', json={'Title': 'Migrate the census export', 'Kind': 'task', 'DoneWhen': done_when, 'DueAt': '2026-12-01'}).json()['taskId']


class StepsTests(unittest.TestCase):
    def test_a_goal_is_created_with_its_sentence_and_date(self):
        t = server.store.get_task(goal())
        self.assertEqual((t['DoneWhen'], t['DueAt']), ('the nightly census lands', '2026-12-01'))

    def test_steps_of_a_goal_with_no_checklist_is_empty(self):
        self.assertEqual(c.get(f'/api/tasks/{goal()}/steps').json(), {'steps': []})

    def test_starting_a_step_makes_a_child_and_links_it(self):
        g = goal()
        server.store.set_task_checklist(g, ['Inventory the fields', 'Map the schema'], 'owner')
        r = c.post(f'/api/tasks/{g}/steps/{checklist_id("Map the schema")}/start').json()
        child = server.store.get_task(r['taskId'])
        self.assertEqual((child['ParentId'], child['Title'], child['Kind']), (g, 'Map the schema', 'general'))
        self.assertIn('Done when: the nightly census lands', child['Summary'])
        steps = c.get(f'/api/tasks/{g}/steps').json()['steps']
        self.assertEqual((steps[1]['tid'], steps[1]['ref'], steps[1]['status'], steps[0]['tid']), (r['taskId'], r['ref'], 'open', None))
        server.store.update_task(r['taskId'], {'Assignee': 'person:ray.colton@northwind.example', 'Status': 'waiting'}, 'owner')
        self.assertEqual(c.get(f'/api/tasks/{g}/steps').json()['steps'][1]['who'], 'Ray Colton')   # a person, named; never the raw address
        self.assertEqual(c.post(f'/api/tasks/{g}/steps/{checklist_id("Map the schema")}/start').json()['taskId'], r['taskId'])  # once

    def test_starting_a_step_that_is_not_there_is_404(self):
        self.assertEqual(c.post(f'/api/tasks/{goal()}/steps/nosuch/start').status_code, 404)

    def test_replanning_keeps_started_steps(self):
        g = goal()
        server.store.set_task_checklist(g, ['Inventory the fields', 'Map the schema'], 'owner')
        child = c.post(f'/api/tasks/{g}/steps/{checklist_id("Map the schema")}/start').json()['taskId']
        ask = ['Inventory the fields', 'Map them onto the ledger schema', 'Schema sign-off']
        with planner(ask):
            server.plan_goal(g, 'anything')
        steps = server.store.goal_steps(g)
        # a started step is never reworded away: it stays, in its place, and the model's new words come after it
        self.assertEqual([x['text'] for x in steps], ['Inventory the fields', 'Map the schema', 'Map them onto the ledger schema', 'Schema sign-off'])
        self.assertEqual([x['tid'] for x in steps], [None, child, None, None])

    def test_a_replan_that_inserts_a_step_does_not_move_the_started_one(self):
        g = goal()
        server.store.set_task_checklist(g, ['Inventory the fields', 'Map the schema'], 'owner')
        child = c.post(f'/api/tasks/{g}/steps/{checklist_id("Map the schema")}/start').json()['taskId']
        ask = ['Inventory the fields', 'Agree the field list with Gail', 'Map them onto the ledger schema']
        with planner(ask):
            server.plan_goal(g, 'anything')
        steps = server.store.goal_steps(g)
        self.assertEqual([(x['text'], x['tid']) for x in steps if x['tid']], [('Map the schema', child)])
        self.assertEqual(len(steps), 4)

    def test_read_ask_on_a_goal_plans_its_steps(self):
        g = goal()
        with planner(['Inventory the fields', 'Map the schema']) as ex:
            self.assertEqual(c.post(f'/api/tasks/{g}/read-ask', json={'goal': True}).json(), {'ok': True})
        self.assertIn('Done when: the nightly census lands', ex.call_args.args[0])
        self.assertEqual([x['text'] for x in server.store.goal_steps(g)], ['Inventory the fields', 'Map the schema'])


class StepInheritsTests(unittest.TestCase):
    def test_a_started_step_inherits_the_goals_repository_tag(self):
        g = goal()
        server.store.tag_task(g, 'repo:northwind/ledger', actor='owner')
        server.store.set_task_checklist(g, ['Export job on the new schema'], 'owner')
        child = c.post(f'/api/tasks/{g}/steps/{checklist_id("Export job on the new schema")}/start').json()['taskId']
        self.assertIn('repo:northwind/ledger', str(server.store.get_task(child)['Tags'] or ''))
