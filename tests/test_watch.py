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


class Watched(unittest.TestCase):
    "A task triage put under Watching, on the rail, and the page's own road for a press on it."
    def setUp(self):
        from taskuary.ingest import ingest_message
        self.s = store()
        brain = lambda *a, **k: json.dumps({'intent': 'watch', 'why': 'Gail Moreno usually answers these', 'title': 'Send the signed vendor form'})
        with mock.patch('taskuary.ingest._spawn'):
            self.t = ingest_message(self.s, {'external_id': 'h1', 'channel': 'email', 'from_email': 'erin@northwind.example', 'from_name': 'Erin Blake',
                                             'conversation_id': 'conv-hand', 'subject': 'Vendor form', 'sent_at': ago(2),
                                             'body': 'Alex - can you send me the signed vendor form today?'}, llm=brain)['task_id']
        self.settle(); self.s.activate_processing_reads(fixed_now=ago(0), live_state=[]); self.settle()
        self.assertEqual(self.level(), 'watching')

    def settle(self): self.s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
    def level(self):
        "Where the row sits on the very next rail read - no settle between the press and it."
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            [i] = [i for i in processing_unread.build(self.s, live_state=[])['items'] if i.get('tid') == self.t]
        return lanes.level_of(i)
    def lines(self):
        from taskuary import general
        return [m['content'][0]['text'] for m in general.press_lines(self.s, self.t)]

    def press(self, kind, params, start=None, hold=None):
        "The page's own road (taskOps.runOperation -> server._run_operation), the agent's start stood in for at the door's inside."
        from fastapi import BackgroundTasks
        self.started = []
        def go(tid, body, background): self.started.append((tid, body.kind, body.handed)); return {'dispatch': 'assistant', 'started': True, 'taskId': tid}
        with mock.patch.object(server, 'store', self.s), mock.patch.object(server, '_no_brain', return_value=''), \
                mock.patch('taskuary.origin.hold', return_value=hold), mock.patch.object(server, '_dispatch_task_to_its_agent', start or go):
            return server._run_operation({'kind': kind, 'target': self.t, 'targetKind': 'task', 'params': params}, BackgroundTasks())


class HandedToAnAgentTests(Watched):
    """THE OWNER'S WATCHED TASK, HANDED TO AN AGENT (the owner, 2026-11-11: "i changed task to general agent and nothing happened also it's
    still on watching rail"): triage read an ask put to the owner as somebody else's, the owner chose who does it on the task - and the
    task wrote "You routing learned.", started nobody, and its row stayed under Watching."""
    def test_who_does_it_changed_to_the_agent_ends_the_watch_starts_it_and_says_so_in_sentences(self):
        for kind, who in (('general', 'the agent'), ('coding', 'the coding agent')):
            with self.subTest(kind=kind):
                self.setUp()
                out = self.press('task.set_kind', {'kind': kind})
                self.assertEqual(self.started, [(self.t, kind, True)], 'the agent he chose was not started - by the one dispatch door, told it was handed over')
                self.assertTrue(out.get('started'))
                self.assertEqual(self.s.get_task(self.t)['Kind'], kind)
                self.assertFalse(watch.watching(self.s.get_task(self.t)))
                self.assertEqual(self.level(), 'task', 'the row stayed under Watching')
                self.assertEqual(self.lines(), [f'You handed it to {who}.', 'You stopped watching it - it is back under Tasks.'])

    def test_the_kind_it_already_has_picked_again_starts_that_agent(self):
        """THE RAIL WALK (2026-11-12): triage left a watched task general with no agent on it; "agent · general" was drawn chosen and
        pressing it did nothing - no line, no agent, the row still under Watching. Picked again, it starts that agent, as a change does."""
        self.s.update_task(self.t, {'Kind': 'general'}, 'triage')
        out = self.press('task.set_kind', {'kind': 'general'})
        self.assertEqual(self.started, [(self.t, 'general', False)], 'the kind it had, picked again, started nobody')
        self.assertTrue(out.get('started'))
        self.assertFalse(watch.watching(self.s.get_task(self.t)))
        self.assertEqual(self.level(), 'task')

    def test_a_line_he_types_to_its_agent_ends_the_watch(self):
        """...and A LINE TYPED IN ITS BOX is a move like any press (the rail walk, 2026-11-12: the agent set to work while the row stayed
        under Watching, "on you"): ended on the line's own road, before the turn starts - the page's request waits for the turn's answer,
        so a watch ended on that answer stood under Watching the whole turn."""
        from taskuary import general
        started = []
        with mock.patch.object(general, '_start_line', lambda *a, **k: started.append(watch.watching(self.s.get_task(self.t)))), \
                mock.patch('taskuary.origin.hold', return_value=None):
            general.take_line(self.s, self.t, 'Please send Erin the signed form.', line_id='l-watch', wait=True)
        self.assertEqual(started, [False], 'the turn started with the task still under Watching')
        self.assertEqual(self.level(), 'task')

    def test_a_start_that_cannot_happen_says_why_in_one_line_and_the_change_still_lands(self):
        from fastapi import HTTPException
        def no(tid, body, background): raise HTTPException(422, 'Connect an AI under Settings to start it.')
        out = self.press('task.set_kind', {'kind': 'general'}, start=no)
        self.assertEqual((out.get('started'), self.s.get_task(self.t)['Kind'], self.level()), (False, 'general', 'task'))
        self.assertIn('Connect an AI', out['why'], 'the press answered nothing about the agent that did not start')

    def test_a_stranger_s_task_waits_behind_its_trust_and_says_so(self):
        out = self.press('task.set_kind', {'kind': 'general'}, hold={'line': 'Erin Blake is not someone you have trusted yet. Trust them and it starts.'})
        self.assertEqual((self.started, out['started'], self.s.get_task(self.t)['Kind']), ([], False, 'general'))
        self.assertIn('Trust them and it starts', out['why'])

    def test_stop_watching_puts_it_back_under_tasks_on_the_next_read(self):
        self.assertEqual(buttons.VERBS['watch']['states']['on'], 'Stop watching', 'the one move back, on the task itself')
        self.press('task.watching', {'off': True})
        self.assertEqual(self.level(), 'task')
        self.assertEqual(self.lines(), ['You stopped watching it - it is back under Tasks.'])
        self.assertEqual(self.started, [], 'back on his list is his to do: nobody starts')
        # ...and its pair says where the task went, as this one does - one composer for both (general.PRESSES)
        from taskuary import general
        self.assertEqual(f"You {general.PRESSES['watch']({})}.", 'You chose Watch it - it is under Watching until the thread moves.')

    def test_a_row_written_in_his_name_with_no_words_is_no_line_of_his(self):
        "The composer said any such row by its bare name: \"You routing learned.\" (routingmemory's bookkeeping, written as the actor it is given)."
        self.s.audit('task', self.t, 'routing_learned', 'owner', detail={'field': 'kind', 'value': 'general'})
        self.assertEqual(self.lines(), [])


class EveryMoveLeavesTheRailAndTheTaskAgreeingTests(Watched):
    "Each move on a watched task: the task says it is not watched, and the next rail read has the row where the task says."
    def where(self): return (watch.watching(self.s.get_task(self.t)), self.level())

    def test_remind_me_puts_it_for_later_and_not_for_me_and_mark_done_take_it_off(self):
        self.press('task.defer', {'until': '1 week'})
        self.assertEqual(self.where(), (False, 'later'))
        self.setUp(); self.press('task.complete', {})
        self.assertEqual(self.s.get_task(self.t)['Status'], 'done'); self.assertFalse(self.s.get_task(self.t)['WatchedAt'])
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            self.assertFalse([i for i in processing_unread.rail_of(processing_unread.build(self.s, live_state=[])['items']) if i.get('tid') == self.t])

    def test_a_new_mail_from_them_brings_it_back_under_tasks(self):
        from taskuary.ingest import ingest_message
        brain = lambda *a, **k: json.dumps({'intent': 'task', 'kind': 'task', 'why': 'she asks again', 'title': 'Send the signed vendor form', 'handled_elsewhere': False})
        with mock.patch('taskuary.ingest._spawn'):
            ingest_message(self.s, {'external_id': 'h2', 'channel': 'email', 'from_email': 'erin@northwind.example', 'from_name': 'Erin Blake',
                                    'conversation_id': 'conv-hand', 'subject': 'RE: Vendor form', 'sent_at': ago(0), 'body': 'Alex, any news on the form?'}, llm=brain)
        self.assertEqual(self.where(), (False, 'task'))


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
