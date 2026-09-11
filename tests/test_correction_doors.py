"""One judgement is worth the same whichever control gives it.

There are four ways to tell Taskuary it read a task wrong - the kind selector on the task page,
the button beside it, a Timeline card's operation, and the assistant's own words - and on
2026-09-11 they wrote four different things. The selector wrote the field and nothing else; a
card's operation wrote the column directly, skipping both memories AND the live-session close;
and the assistant's "put it on my list" short-circuited on any message that already had a task,
so it claimed the task, left the kind exactly as the verdict it was overturning, and taught
nothing at all.

These tests compare the doors against each other rather than against a remembered list, because
the failure mode is drift: a new road added later that quietly teaches less than the old one.
"""
import unittest
from unittest import mock

from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from taskuary import server

c, s = TestClient(server.app), server.store


def arrived(start='coding'):
    """A task as triage left it, with the verdict on file to be overturned."""
    tid = s.create_task({'Title': 'Clock out Mindy at 3:40', 'Kind': start, 'Source': 'teams'}, 'router')
    mid = s.add_message({'TaskId': tid, 'Channel': 'teams', 'FromEmail': 'm@mfa.net', 'Direction': 'in',
                         'Subject': 'Teams chat with Mindy', 'BodyText': 'clock me out', 'Status': 'routed'})
    s.add_route(mid, tid, 'create', None, 'r', [], 'triage',
                verdict={'intent': 'task', 'kind': start, 'profile': 'analyst', 'repository': 'mfaVita/FanApp'})
    return tid, mid


def wrote(go, start='coding'):
    """Everything one door leaves behind: both memories, and where the task ended up."""
    tid, mid = arrived(start)
    mem = len(s.list_memories())
    facts = sum(int(x['EvidenceCount'] or 0) for x in s.routing_facts())
    bg = BackgroundTasks()
    with mock.patch('taskuary.learn.learn_from') as lessons:
        go(tid, mid, bg)
        for t in bg.tasks: t.func(*t.args, **t.kwargs)
    return {'memory': len(s.list_memories()) - mem,
            'LEARNED': lessons.call_count,
            'routing': sum(int(x['EvidenceCount'] or 0) for x in s.routing_facts()) - facts,
            'kind': (s.get_task(tid) or {}).get('Kind')}


def op(kind, params, on_message=False):
    return lambda t, m, bg: server._run_operation({'kind': kind, 'target': (m if on_message else t), 'params': params}, bg)


class MineNotTheAgents(unittest.TestCase):
    """Three doors, one judgement: the work is real and it is the owner's."""

    DOORS = {
        'the kind selector': lambda t, m, bg: c.patch(f'/api/tasks/{t}', json={'Kind': 'task'}),
        'the task button': lambda t, m, bg: c.post(f'/api/tasks/{t}/not-coding', json={'learn': True}),
        "a card's operation": op('task.set_kind', {'kind': 'task'}),
        "the assistant's words": op('task.create_from_message', {'kind': 'task'}, True),
    }

    def test_every_door_writes_the_same_records(self):
        got = {name: wrote(go) for name, go in self.DOORS.items()}
        first = next(iter(got.values()))
        for name, row in got.items():
            self.assertEqual(row, first, f'{name} teaches differently from the others: {got}')

    def test_and_all_of_them_actually_teach(self):
        row = wrote(self.DOORS['the kind selector'])
        self.assertEqual(row['kind'], 'task')
        for what in ('memory', 'LEARNED', 'routing'):
            self.assertGreater(row[what], 0, f'the verdict wrote no {what}')


class HandItToTheAssistant(unittest.TestCase):
    """...and the same for `general`, which is still agent work - so no not-for-the-agent
    evidence line, but the routing fact and the learned lesson both hold."""

    DOORS = {
        'the kind selector': lambda t, m, bg: c.patch(f'/api/tasks/{t}', json={'Kind': 'general'}),
        "a card's operation": op('task.set_kind', {'kind': 'general'}),
        "the assistant's words": op('task.create_from_message', {'kind': 'general'}, True),
    }

    def test_every_door_writes_the_same_records(self):
        got = {name: wrote(go) for name, go in self.DOORS.items()}
        first = next(iter(got.values()))
        for name, row in got.items():
            self.assertEqual(row, first, f'{name} teaches differently from the others: {got}')

    def test_it_is_a_weaker_signal_than_taking_it_yourself(self):
        row = wrote(self.DOORS['the kind selector'])
        self.assertEqual(row['kind'], 'general')
        self.assertEqual(row['memory'], 0, 'general is still agent work - no not-for-the-agent line')
        self.assertGreater(row['routing'], 0)
        self.assertGreater(row['LEARNED'], 0)


class TheOtherCorrections(unittest.TestCase):
    def test_reassigning_the_worker_teaches(self):
        row = wrote(lambda t, m, bg: c.patch(f'/api/tasks/{t}', json={'Assignee': 'agent:coder'}))
        self.assertGreater(row['routing'], 0)
        self.assertGreater(row['LEARNED'], 0)

    def test_choosing_a_different_repository_teaches(self):
        row = wrote(lambda t, m, bg: c.put(f'/api/tasks/{t}/repo', json={'repo': 'mfaVita/TopE', 'agent': 'coder'}))
        self.assertGreater(row['LEARNED'], 0, 'a rerouted checkout reached the profile as nothing at all')

    def test_saying_where_it_belongs_teaches_twice(self):
        plain = wrote(lambda t, m, bg: c.post(f'/api/tasks/{t}/not-coding', json={'learn': True}))
        named = wrote(lambda t, m, bg: c.post(f'/api/tasks/{t}/not-coding', json={'learn': True, 'belongs_to': 'ADP'}))
        self.assertGreater(named['routing'], plain['routing'])
        self.assertGreater(named['LEARNED'], plain['LEARNED'])

    def test_not_a_task_is_not_a_routing_correction(self):
        # "there was no work here" says nothing about WHO should have done the work
        row = wrote(lambda t, m, bg: c.post(f'/api/tasks/{t}/not-a-task', json={'learn': True}))
        self.assertEqual(row['routing'], 0)
        self.assertGreater(row['memory'], 0)



class TheAssistantCanSetRoutingMemory(unittest.TestCase):
    """The chat could keep a free-text fact every verdict then reads, but not a SCOPED, weighted
    one about this sender and this field - triage corrections were deliberately left out of the
    catalogue. They are in it now, as a teaching-only call that moves no task."""

    def run_call(self, tid, params):
        from fastapi import BackgroundTasks
        bg = BackgroundTasks()
        out = server._run_operation({'kind': 'routing.remember', 'target': tid, 'params': params}, bg)
        for t in bg.tasks: t.func(*t.args, **t.kwargs)
        return out

    def test_the_call_is_one_the_registry_runs(self):
        from taskuary import toolcatalog
        self.assertEqual(toolcatalog.valid('routing.remember', {'field': 'system', 'value': 'ADP'}), '')
        self.assertIn('needs value', toolcatalog.valid('routing.remember', {'field': 'system'}))

    def test_it_writes_a_scoped_weighted_fact(self):
        tid, _ = arrived()
        self.run_call(tid, {'field': 'system', 'value': 'ADP'})
        got = [f for f in s.routing_facts('system') if f['SignalKey'] == 'm@mfa.net']
        self.assertEqual([f['Value'] for f in got], ['ADP'])
        self.assertTrue(got[0]['Confirmed'], "the owner said it in words - that is their word, not a guess")

    def test_it_teaches_without_moving_the_task(self):
        tid, _ = arrived()
        self.run_call(tid, {'field': 'kind', 'value': 'task'})
        self.assertEqual(s.get_task(tid)['Kind'], 'coding',
                         'a lesson about work LIKE this must not reclassify the task it was said about')
        self.assertTrue([f for f in s.routing_facts('kind') if f['Value'] == 'task'])

    def test_it_refuses_a_field_that_is_not_a_routing_field(self):
        from fastapi import HTTPException
        tid, _ = arrived()
        with self.assertRaises(HTTPException):
            self.run_call(tid, {'field': 'summary', 'value': 'shorter'})

    def test_saying_it_twice_about_one_task_does_not_inflate_it(self):
        tid, _ = arrived()
        self.run_call(tid, {'field': 'system', 'value': 'ADP'})
        again = self.run_call(tid, {'field': 'system', 'value': 'ADP'})
        self.assertTrue(again.get('already'))

if __name__ == '__main__':
    unittest.main()
