"""Watch it (the owner, 2026-11-01): a task that is not the owner's, kept open while somebody else handles it - under Watching at the
foot of Tasks, still walked after Tasks (the owner, 2026-11-02), back in Tasks when its thread moves or after a quiet week, and never
closed for them."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import buttons, concierge, funnel, lanes, processing_unread, railwalk, rulebook, server, watch
from taskuary.store import MemoryStore
from tests.railwalk_rows import RowWalk


def ago(hours=0): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._CACHE.update(cands_at=0.0, cands=[])
    return s


def theirs(s):
    t = s.create_task({'Title': 'Vendor portal access for the new starter', 'Kind': 'task', 'Status': 'open', 'Assignee': 'owner'}, 'o')
    s.add_message({'TaskId': t, 'ExternalId': 'x:portal', 'Channel': 'email', 'SourceName': 'inbox', 'Subject': 'Portal access',
                   'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': ago(3), 'ConversationId': 'conv-watch',
                   'BodyText': 'Gail is setting up the portal access for the new starter - copying you so you know.', 'Status': 'routed'})
    return t


def row(key, tid=None, **k): return {'key': key, 'tid': tid, 'lane': 'yours', 'order_band': 2, 'kind': 'task', 'arrived_at': ago(10 - len(key)), **k}


class StateTests(unittest.TestCase):
    def test_watch_keeps_it_open_and_survives_a_restart_as_a_task_field(self):
        s = store(); t = theirs(s)
        out = watch.watch(s, t)
        self.assertTrue(out['watching'])
        task = s.get_task(t)
        self.assertEqual(task['Status'], 'open', 'a watched task stays open')
        self.assertTrue(task['WatchedAt']); self.assertTrue(watch.watching(task))

    def test_a_watch_drops_a_reminder_and_a_reminder_ends_a_watch(self):
        from taskuary import remind
        s = store(); t = theirs(s)
        remind.set_reminder(s, t, '2 weeks'); watch.watch(s, t)
        self.assertFalse(s.get_task(t)['RemindAt'], 'one road back at a time')
        remind.set_reminder(s, t, '1 week')
        self.assertFalse(watch.watching(s.get_task(t)))

    def test_mark_done_still_closes_it_and_a_closed_task_cannot_be_watched(self):
        s = store(); t = theirs(s); watch.watch(s, t)
        s.update_task(t, {'Status': 'done'}, 'owner')
        self.assertFalse(s.get_task(t)['WatchedAt'])
        with self.assertRaises(ValueError): watch.watch(s, t)

    def test_seven_quiet_days_bring_it_back_once_and_nothing_closes_it(self):
        s = store(); t = theirs(s); watch.watch(s, t)
        self.assertEqual(watch.due(s, datetime.now() + timedelta(days=6)), 0, 'back before the week was out')
        self.assertEqual(watch.due(s, datetime.now() + timedelta(days=7, minutes=1)), 1)
        task = s.get_task(t)
        self.assertEqual((task['Status'], task['WatchBack'], bool(task['WatchedAt'])), ('open', 'quiet', False))
        self.assertEqual(s.list_comments(t)[-1]['Body'], watch.QUIET_NOTE)
        self.assertEqual(watch.due(s, datetime.now() + timedelta(days=30)), 0, 'it comes back once')

    def test_the_reminder_clock_runs_it(self):
        from taskuary import remind
        s = store(); t = theirs(s); watch.watch(s, t)
        remind.tick(s, datetime.now() + timedelta(days=8))
        self.assertEqual(s.get_task(t)['WatchBack'], 'quiet')


class RailTests(unittest.TestCase):
    def rail(self, s, t):
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            return [i for i in processing_unread.build(s, live_state=[])['items'] if i.get('tid') == t]

    def settle(self, s): s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()

    def test_a_watched_task_sits_under_watching_and_stays_on_the_walk(self):
        s = store(); t = theirs(s)
        self.settle(s); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); self.settle(s)
        watch.watch(s, t); self.settle(s)
        rows = self.rail(s, t)
        self.assertTrue(rows, 'a watched task left the rail - it stays open, under Watching')
        self.assertTrue(all(lanes.level_of(i) == 'watching' and i['watching'] and not i['actionable'] for i in rows))
        self.assertEqual(railwalk.line(rows), rows, 'a watched row left the walk - Watch it keeps it on (the owner, 2026-11-02)')
        self.assertEqual(railwalk.kind_of(rows[0]), 'stays', 'Next on a watched row leaves it on the rail, as on a task')

    def test_watching_is_its_own_section_at_the_foot_of_tasks(self):
        order = list(lanes.LEVEL_ORDER)
        self.assertEqual(order.index('watching'), order.index('task') + 1)
        self.assertGreater(funnel.order_key(row('w', 1, watching=True)), funnel.order_key(row('t', 2)))
        self.assertLess(funnel.order_key(row('w', 1, watching=True)), funnel.order_key(row('r', None, lane='report', order_band=3, kind='report')))


class WalkTests(unittest.TestCase):
    def test_next_reaches_watching_after_tasks(self):
        s = store()
        rows = [row('task:1', 1), row('task:2', 2, watching=True), row('task:3', 3)]
        w = RowWalk(s, rows)
        try:
            self.assertEqual(w.start(), 'task:1')
            self.assertEqual(w.next(), 'task:3', 'the watched row sits below Tasks, not in its arrival place')
            self.assertEqual(w.next(), 'task:2', 'Next went past a watched row')
            self.assertEqual(w.back(), 'task:3')
        finally: w.close()

    def test_for_later_is_still_off_the_walk(self):
        rows = [row('task:1', 1), row('task:2', 2, deferred=True), row('task:3', 3, watching=True)]
        self.assertEqual([r['key'] for r in railwalk.line(rows)], ['task:1', 'task:3'])

    def test_watch_it_on_the_table_closes_the_row_and_moves_on(self):
        self.assertEqual(railwalk.HOW['watch'], 'task.watching')


class ComesBackTests(unittest.TestCase):
    """A new inbound message joins the watched task: back on the walk, and Mark done lit only where triage read it as handled."""
    def setUp(self):
        from taskuary.ingest import ingest_message
        self.ingest, self.s = ingest_message, store()
        self.t = self.mail('w1', 'Portal access', 'Gail is setting up the portal - copying you so you know.', 'task', hours=5)['task_id']
        watch.watch(self.s, self.t)

    def mail(self, xid, subject, body, intent, hours=0, handled=None):
        said = []
        def brain(system, user, *a, **k):
            said.append(user)
            return json.dumps({'intent': intent, 'kind': 'task', 'why': 'invented for the test', 'title': subject,
                               **({'handled_elsewhere': handled} if handled is not None else {})})
        self.said = said
        return self.ingest(self.s, {'external_id': xid, 'channel': 'email', 'from_email': 'gail@northwind.example', 'from_name': 'Gail Moreno',
                                    'conversation_id': 'conv-watch', 'subject': subject, 'body': body, 'sent_at': ago(hours)}, llm=brain)

    def test_the_thread_moving_brings_it_back(self):
        self.assertIn(self.mail('w2', 'RE: Portal access', 'Still waiting on the vendor for the login.', 'task', handled=False)['status'],
                      ('attached', 'routed'))
        task = self.s.get_task(self.t)
        self.assertEqual((task['Status'], bool(task['WatchedAt']), task['WatchBack']), ('open', False, 'moved'))
        self.assertIn('watching', self.said[-1], 'triage was not told the task is watched')

    def test_an_fyi_on_the_thread_still_brings_it_back_and_handled_lights_mark_done(self):
        self.assertEqual(self.mail('w3', 'RE: Portal access', 'Done - the starter can log in now.', 'fyi', handled=True)['status'], 'filed')
        task = self.s.get_task(self.t)
        self.assertEqual((task['Status'], task['WatchBack']), ('open', 'handled'), 'a watch is never closed for the owner')
        st, facts = rulebook.state(self.s, {'tid': self.t, 'kind': 'task', 'lane': 'yours', 'key': f'task:{self.t}'}, [{'verb': 'close'}])
        self.assertEqual(st, 'watch_handled'); self.assertEqual(facts['who'], 'Gail Moreno')
        d = rulebook.facts(self.s, {'tid': self.t, 'kind': 'task', 'lane': 'yours', 'key': f'task:{self.t}'}, [{'verb': 'close'}, {'verb': 'next'}])
        self.assertEqual(d, {'state': 'watch_handled', 'line': 'Gail Moreno wrote; it looks handled.'}, 'the fact the model reads; it lights nothing')

    def test_the_owner_writing_on_it_leaves_the_watch_alone(self):
        before = self.s.get_task(self.t)['WatchedAt']
        watch.moved(self.s, self.t, {'from_email': 'alex@northwind.example'}, None, {'alex@northwind.example'}, 'router')
        self.assertEqual(self.s.get_task(self.t)['WatchedAt'], before)


class QuietMovesTests(unittest.TestCase):
    def test_a_quiet_week_lights_chase_them_and_offers_let_it_go(self):
        s = store(); t = theirs(s); watch.watch(s, t); watch.due(s, datetime.now() + timedelta(days=8))
        it = {'tid': t, 'kind': 'task', 'lane': 'yours', 'key': f'task:{t}'}
        self.assertEqual(rulebook.adds(s, it), ['chase', 'let_go'])
        d = rulebook.facts(s, it, [{'verb': 'chase'}, {'verb': 'let_go'}, {'verb': 'next'}])
        self.assertEqual(d, {'state': 'watch_quiet', 'line': 'A week watched; nothing on the thread.'})
        self.assertEqual(concierge.cannot(it, 'let_go', s), '')


class MovesEndTheWatchTests(unittest.TestCase):
    def test_the_operation_door_watches_and_any_other_move_ends_it(self):
        s = store(); t = theirs(s)
        with mock.patch.object(server, 'store', s):
            server._run_operation({'kind': 'task.watching', 'target': t, 'targetKind': 'task', 'params': {}}, None)
            self.assertTrue(watch.watching(s.get_task(t)))
            server._run_operation({'kind': 'task.update', 'target': t, 'targetKind': 'task', 'params': {'priority': 'important'}}, None)
        self.assertFalse(watch.watching(s.get_task(t)), 'a move left the watch on')

    def test_a_press_on_the_task_page_ends_it_and_watch_it_again_ends_it_too(self):
        s = store(); t = theirs(s); watch.watch(s, t)
        with mock.patch.object(server, 'store', s):
            r = TestClient(server.app).patch(f'/api/tasks/{t}', json={'Priority': 'important'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(watch.watching(s.get_task(t)))
        watch.watch(s, t)
        with mock.patch.object(server, 'store', s):
            server._run_operation({'kind': 'task.watching', 'target': t, 'targetKind': 'task', 'params': {'off': True}}, None)
        self.assertFalse(watch.watching(s.get_task(t)))


class ButtonTests(unittest.TestCase):
    def test_watch_it_is_a_button_beside_remind_me_and_assign_is_gone(self):
        self.assertEqual(buttons.VERBS['watch']['label'], 'Watch it')
        self.assertIn('thread moves', buttons.VERBS['watch']['hint'])
        self.assertNotIn('assign', buttons.VERBS)
        for kind in ('task', 'asked', 'todo', 'review', 'agent'):
            chips = concierge.CHIPS[kind]
            self.assertEqual(chips.index('watch'), chips.index('defer') + 1, kind)
        self.assertEqual(concierge._OPS['watch'], ('task.watching', True))


if __name__ == '__main__': unittest.main()
