"""Which step does this serve (spec 2026-10-12, build step 5): triage names the goal and the step, the mail lands under it."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock
from taskuary import context, ingest, triage
from taskuary.store import MemoryStore

def ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')

def goal(s):
    g = s.create_task({'Title': 'Migrate the census export', 'Kind': 'task', 'Status': 'open', 'DoneWhen': 'the nightly census lands in the new ledger'}, 'owner')
    s.set_task_checklist(g, ['Gail sends the accruals', 'Ray: schema sign-off', 'Export job on the new schema'], 'owner')
    return g, [x['id'] for x in s.goal_steps(g)]

def verdict(**kw):
    return {'intent': 'fyi', 'kind': None, 'why': 'x', 'title': 'Accruals', 'summary': 'x', 'urgent': False, 'sender_class': 'person', **kw}

def mail(v, who='gail@northwind.example', name='Gail Moreno', subject='Accruals for September'):
    return {'external_id': f'm-{subject}', 'channel': 'email', 'from_email': who, 'from_name': name, 'subject': subject,
            'body': 'Attached, as promised.', 'conversation_id': f'c-{subject}', 'sent_at': ago(hours=1), '_verdict': (v, {})}

def ingest_one(s, msg):
    with mock.patch('taskuary.ingest._spawn'): return ingest.ingest_message(s, msg, actor='test', llm=lambda *a, **k: '{}')


class ServesTests(unittest.TestCase):
    def test_open_goals_carry_their_steps_for_the_prompt(self):
        s = MemoryStore(); g, ids = goal(s)
        og = context.open_goals(s)
        self.assertEqual((og[0]['tid'], og[0]['done_when'][:11], [x['text'] for x in og[0]['steps']][:1]), (g, 'the nightly', ['Gail sends the accruals']))

    def test_the_prompt_shows_the_goals_and_asks_which_step(self):
        s = MemoryStore(); g, ids = goal(s)
        def llm(system, user, **kw): llm.user, llm.want = user, kw.get('want'); return json.dumps(verdict(serves={'task': g, 'step': ids[0], 'done': False}))
        llm.takes_want = True
        out = triage.classify_intent({'from_email': 'gail@northwind.example', 'subject': 'Accruals', 'body': 'x'}, llm=llm, thread={'open_goals': context.open_goals(s)})
        self.assertIn('Gail sends the accruals', llm.user); self.assertIn('serves', llm.want['schema']['properties'])
        self.assertEqual(out['serves'], {'task': g, 'step': ids[0], 'done': False})

    def test_no_goals_no_serves_in_the_schema(self):
        self.assertNotIn('serves', triage.verdict_schema()['schema']['properties'])

    def test_a_mail_that_serves_a_step_lands_under_it_and_may_tick_it(self):
        s = MemoryStore(); g, ids = goal(s)
        out = ingest_one(s, mail(verdict(serves={'task': g, 'step': ids[0], 'done': True})))
        self.assertEqual(out['task_id'], g)
        self.assertTrue(s.goal_steps(g)[0]['done'])
        self.assertEqual(list(s.step_arrivals(g)), [ids[0]])
        self.assertEqual(s.step_arrivals(g)[ids[0]][0]['who'], 'Gail Moreno')

    def test_a_held_step_gets_the_mail_and_keeps_its_box(self):
        s = MemoryStore(); g, ids = goal(s)
        c = s.create_task({'Title': 'Ray: schema sign-off', 'Status': 'waiting', 'Assignee': 'agent:coder'}, 'owner'); s.link_step(g, ids[1], c, 'owner')
        out = ingest_one(s, mail(verdict(serves={'task': g, 'step': ids[1], 'done': True}), 'ray@northwind.example', 'Ray Colton', 'Schema v2'))
        self.assertEqual(out['task_id'], c); self.assertFalse(s.goal_steps(g)[1]['done'])
        self.assertEqual(list(s.step_arrivals(g)), [ids[1]])

    def test_a_step_not_shown_is_ignored(self):
        s = MemoryStore(); g, ids = goal(s)
        def llm(system, user, **kw): return json.dumps(verdict(serves={'task': g, 'step': 'nope', 'done': True}))
        out = triage.classify_intent({'from_email': 'omar@northwind.example', 'subject': 'Other', 'body': 'x'}, llm=llm, thread={'open_goals': context.open_goals(s)})
        self.assertNotIn('serves', out)
        def llm2(system, user, **kw): return json.dumps(verdict(serves={'task': g + 99, 'step': ids[0], 'done': True}))
        self.assertNotIn('serves', triage.classify_intent({'from_email': 'o@northwind.example', 'subject': 'O', 'body': 'x'}, llm=llm2, thread={'open_goals': context.open_goals(s)}))

    def test_the_steps_endpoint_lists_each_steps_arrivals(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore(); g, ids = goal(s)
        ingest_one(s, mail(verdict(serves={'task': g, 'step': ids[2], 'done': False}), subject='Export dry run'))
        with mock.patch.object(server, 'store', s): steps = TestClient(server.app).get(f'/api/tasks/{g}/steps').json()['steps']
        self.assertEqual(([len(x['arrivals']) for x in steps], steps[2]['arrivals'][0]['subject'], steps[2]['done']), ([0, 0, 1], 'Export dry run', False))

    def test_a_held_step_takes_the_mails_urgency_and_day(self):
        """review: the step branch returned before urgent/due, which same_as applies - a step mail asking for today lost both"""
        s = MemoryStore(); g, ids = goal(s)
        c = s.create_task({'Title': 'Ray: schema sign-off', 'Status': 'waiting', 'Assignee': 'person:ray@northwind.example'}, 'owner'); s.link_step(g, ids[1], c, 'owner')
        ingest_one(s, mail(verdict(intent='task', urgent=True, due=ago()[:10], serves={'task': g, 'step': ids[1], 'done': False}), 'ray@northwind.example', 'Ray Colton', 'Sign-off today'))
        t = s.get_task(c)
        self.assertEqual((t['Priority'], str(t['DueAt'])[:10]), ('urgent', ago()[:10]))
        self.assertFalse(s.get_task(g).get('DueAt'))          # a step's day never moves the goal's date

    def test_a_closed_steps_task_reopens_on_a_new_ask(self):
        """review: a follow-up on a finished step sat on a closed card nobody looks at"""
        s = MemoryStore(); g, ids = goal(s)
        c = s.create_task({'Title': 'Export job', 'Status': 'open'}, 'owner'); s.link_step(g, ids[2], c, 'owner'); s.update_task(c, {'Status': 'done'}, 'owner')
        ingest_one(s, mail(verdict(intent='task', serves={'task': g, 'step': ids[2], 'done': False}), subject='The export used the old file'))
        self.assertNotIn(s.get_task(c)['Status'], ('done', 'dropped'))


class GoalKindTests(unittest.TestCase):
    def _v(self, **kw):
        return {'intent': 'task', 'kind': 'general', 'why': 'x', 'title': 'Move the census to the new ledger', 'summary': 'several sites, Gail and Ray',
                'urgent': False, 'sender_class': 'person', 'goal': True, 'done_when': 'the census lands in the new ledger for all three sites', **kw}

    def test_triage_answers_goal_only_with_a_done_when(self):
        self.assertIn('goal', triage.verdict_schema()['schema']['properties'])
        def ask(**kw):
            return triage.classify_intent({'from_email': 'gail@northwind.example', 'subject': 'Census', 'body': 'x'}, llm=lambda *a, **k: json.dumps(self._v(**kw)))
        self.assertEqual((ask()['goal'], ask()['done_when'][:10]), (True, 'the census'))
        self.assertNotIn('goal', ask(done_when=''))
        self.assertNotIn('goal', ask(intent='reply_only'))

    def test_an_open_ended_ask_becomes_a_goal_with_no_steps_and_the_planner_runs(self):
        s = MemoryStore()
        with mock.patch('taskuary.goals.plan_later') as plan:
            out = ingest_one(s, mail({**self._v(checklist=['a', 'b']), 'due': '2026-12-01'}, subject='Census migration'))
        t = s.get_task(out['task_id'])
        self.assertEqual((t['DoneWhen'][:10], str(t['DueAt'])[:10], t.get('Tags'), t['Kind'], t.get('Assignee')), ('the census', '2026-12-01', 'goal', 'task', None))
        self.assertEqual(s.task_checklist(t['TaskId']), []); plan.assert_called_once()
        self.assertIn('Done when: the census lands', plan.call_args[0][2])

    def test_a_goal_without_done_when_is_a_task(self):
        s = MemoryStore()
        v = self._v(); v.pop('goal'); v.pop('done_when')
        out = ingest_one(s, mail(v, subject='Quick one'))
        self.assertFalse(s.get_task(out['task_id']).get('DoneWhen'))

    def test_not_a_goal_clears_done_when_and_teaches(self):
        from fastapi.testclient import TestClient
        from taskuary import server, routingmemory as rmem
        s = MemoryStore()
        with mock.patch('taskuary.goals.plan_later'): out = ingest_one(s, mail(self._v(), subject='Census migration'))
        g = out['task_id']; s.set_task_checklist(g, ['a', 'b'], 'owner')
        with mock.patch.object(server, 'store', s):
            c = TestClient(server.app)
            op = c.post('/api/operations', json={'kind': 'task.set_kind', 'target': g, 'params': {'kind': 'task'}}).json()
            c.post(f"/api/operations/{op['id']}/execute", json={'version': op['version']})
        self.assertFalse(s.get_task(g).get('DoneWhen')); self.assertEqual(len(s.task_checklist(g)), 2)
        self.assertNotIn('goal', str(s.get_task(g).get('Tags') or ''))
        self.assertTrue(any(f['field'] == 'kind' and f['value'] == 'task' for f in rmem.facts_for(s, {'from_email': 'gail@northwind.example', 'subject': 'Census migration'})))

    def test_made_a_goal_by_hand_takes_a_done_when_and_teaches(self):
        from fastapi.testclient import TestClient
        from taskuary import server, routingmemory as rmem
        s = MemoryStore()
        v = self._v(); v.pop('goal'); v.pop('done_when')
        g = ingest_one(s, mail(v, subject='Census migration'))['task_id']
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.goals.plan_later') as later:
            c = TestClient(server.app)
            op = c.post('/api/operations', json={'kind': 'task.set_kind', 'target': g, 'params': {'kind': 'goal'}}).json()
            c.post(f"/api/operations/{op['id']}/execute", json={'version': op['version']})
        t = s.get_task(g)
        self.assertEqual((t['DoneWhen'], 'goal' in str(t.get('Tags'))), ('several sites, Gail and Ray', True)); later.assert_called_once()
        self.assertTrue(any(f['field'] == 'kind' and f['value'] == 'goal' for f in rmem.facts_for(s, {'from_email': 'gail@northwind.example', 'subject': 'Census migration'})))


if __name__ == '__main__': unittest.main()
