"""The Advisor's event path (spec 2026-10-12, build step 3): one small judgement per item per revision, a pill that
presses the card's own button, and a rail that never reads any of it."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock
import pytest
from taskuary import advisor, funnel, outcomes, processing_unread, terminal
from taskuary.store import MemoryStore


class RowTests(unittest.TestCase):
    def test_a_row_is_keyed_by_target_and_revision_and_read_back(self):
        s = MemoryStore(); t = s.create_task({'Title': 'Export job'}, 'owner')
        rev = advisor.revision(s, 'task', t)
        self.assertEqual(len(rev), 16)
        i = advisor._write(s, target_kind='task', target_id=t, key='task:%d' % t, event='agent.stopped', revision=rev, tier=1,
                           line='You usually merge it here.', verb='continue', label='Continue session', count=(8, 8), evidence=['out3'], model='haiku')
        r = advisor.row(s, 'task', t, rev)
        self.assertEqual((r['Id'], r['Verb'], json.loads(r['CountJson']), json.loads(r['EvidenceJson'])), (i, 'continue', [8, 8], ['out3']))
        self.assertIsNone(advisor.row(s, 'task', t, 'other'))
        self.assertEqual([x['Id'] for x in advisor.rows(s, 'task', t)], [i])

    def test_the_revision_moves_with_the_task_and_its_agent_events(self):
        from taskuary import workerstate as ws
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'open'}, 'owner')
        a = advisor.revision(s, 'task', t)
        s.update_task(t, {'Status': 'in_progress'}, 'owner'); b = advisor.revision(s, 'task', t)
        ws.record(s, t, 'run1', 'turn_end', text='done'); c = advisor.revision(s, 'task', t)
        self.assertEqual(len({a, b, c}), 3)
        self.assertEqual(c, advisor.revision(s, 'task', t))                             # stable while nothing changes

    def test_keys_round_trip(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        self.assertEqual(advisor.key_of('task', t), f'task:{t}')
        self.assertEqual(advisor.target_of(s, f'task:{t}'), ('task', t))
        self.assertEqual(advisor.target_of(s, 'agent:7'), ('task', 7))
        self.assertEqual(advisor.target_of(s, 'msg:9'), ('message', 9))
        self.assertIsNone(advisor.target_of(s, 'conn:3'))


@pytest.fixture
def rail(monkeypatch):
    s = MemoryStore()
    s.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    for n in range(5):
        t = s.create_task({'Title': f'Arrival {n}', 'Status': 'open'}, 'owner')
        s.add_message({'ConversationId': f'c{n}', 'Channel': 'email', 'Subject': f'Arrival {n}', 'FromEmail': f'p{n}@vendor.example',
                       'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'BodyText': 'x', 'Status': 'routed', 'TaskId': t})
    s.reconcile_processing_membership()
    s.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=[])
    funnel.invalidate(); yield s; funnel.invalidate(); s.cx.close()


def order(s):
    s.reconcile_processing_membership(); funnel.invalidate()
    return [c['key'] for c in processing_unread.build(s, live_state=[], include_read=True)['items']]


def test_the_rail_is_the_same_with_and_without_advice(rail):
    before = order(rail)
    assert len(before) >= 5
    for t in rail._rows('SELECT TaskId FROM task'):
        advisor._write(rail, target_kind='task', target_id=t['TaskId'], key=f"task:{t['TaskId']}", event='task.closed',
                       revision=advisor.revision(rail, 'task', t['TaskId']), tier=1, line='Close it.', verb='close', label='Mark done',
                       count=(3, 3), evidence=[], model='haiku')
    assert order(rail) == before


def brain_saying(answer: dict):
    """A light brain that answers one JSON object, and counts its calls."""
    calls = []
    def llm(system, user, max_tokens=400, images=None, want=None, **kw):
        calls.append((system, user)); return json.dumps(answer)
    llm.takes_want = False; llm.calls = calls
    return llm


class _Rail(unittest.TestCase):
    """The rail is built the way a real install builds it (processing reads on), so the card is the one the owner sees."""
    def setUp(self):
        self._p = [mock.patch.object(terminal, 'live_sessions', lambda tail=0: []), mock.patch.object(funnel, '_agenda', lambda _s, **kw: [])]
        for p in self._p: p.start()
        funnel.invalidate()
    def tearDown(self):
        for p in self._p: p.stop()
        funnel.invalidate()

    def _stopped_task(self, s):
        s.set_setting('calendar_enabled', '0', 'test')
        t = s.create_task({'Title': 'Export job', 'Status': 'in_progress', 'Kind': 'code'}, 'owner')
        s.add_message({'ConversationId': f'c{t}', 'Channel': 'email', 'Subject': 'Export job', 'FromEmail': 'gail@northwind.example', 'FromName': 'Gail Moreno',
                       'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'BodyText': 'Please move the export.', 'Status': 'routed', 'TaskId': t})
        rid = s.start_run(t, 'coder', 'move the export', 'owner'); s._exec("UPDATE run SET Status='stopped' WHERE RunId=?", (rid,))   # the agent left: Continue leads
        s.reconcile_processing_membership(); s.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=[]); funnel.invalidate()
        return t


class JudgeTests(_Rail):
    def test_a_verb_the_item_carries_lands_with_the_ledgers_number(self):
        s = MemoryStore(); t = self._stopped_task(s)
        for _ in range(3):
            i = outcomes.record(s, 'agent.stopped', 'task', t, 'agent:coder', facts={'pr': False}); outcomes.settle(s, i, 'continued 2 min later', 'continued')
        llm = brain_saying({'verb': 'continue', 'line': 'You usually continue it here.', 'evidence': ['out1']})
        rid = advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=llm)
        r = s._one('SELECT * FROM advice WHERE Id=?', (rid,))
        self.assertEqual((r['Verb'], r['Line'], json.loads(r['CountJson']), r['Dropped']), ('continue', 'You usually continue it here.', [3, 3], None))
        self.assertIn('CONTINUE', llm.calls[0][1].upper()); self.assertIn('out1', llm.calls[0][1])
        self.assertEqual(advisor.pill(r['Label'], json.loads(r['CountJson'])), f"{r['Label']} · 3 of 3 times")

    def test_the_same_revision_is_judged_once(self):
        s = MemoryStore(); t = self._stopped_task(s)
        llm = brain_saying({'verb': 'continue', 'line': 'x', 'evidence': []})
        advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=llm)
        self.assertIsNone(advisor.notice(s, 'agent.asked', 'task', t, wait=True, llm=llm))
        self.assertEqual(len(llm.calls), 1)

    def test_silence_is_a_row_with_no_verb_and_no_pill(self):
        s = MemoryStore(); t = self._stopped_task(s)
        llm = brain_saying({'verb': None, 'line': '', 'evidence': []})
        rid = advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=llm)
        r = s._one('SELECT * FROM advice WHERE Id=?', (rid,))
        self.assertEqual((r['Verb'], r['Dropped']), (None, 'nothing to say'))
        self.assertEqual(len(llm.calls), 1)                                          # silence is the answer, not a missing key

    def test_a_verb_the_item_cannot_carry_is_dropped(self):
        s = MemoryStore(); t = self._stopped_task(s)
        rid = advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=brain_saying({'verb': 'approve', 'line': 'Send it.', 'evidence': []}))
        r = s._one('SELECT * FROM advice WHERE Id=?', (rid,))
        self.assertEqual(r['Verb'], None); self.assertIn('approve', r['Dropped'])

    def test_an_item_with_no_actions_is_dropped_without_a_call(self):
        s = MemoryStore()
        mid = s.add_message({'ConversationId': 'c2', 'Channel': 'email', 'Subject': 'Newsletter', 'FromEmail': 'news@vendor.example',
                             'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'BodyText': 'x', 'Status': 'filed'})
        llm = brain_saying({'verb': 'close', 'line': 'x', 'evidence': []})
        with mock.patch.object(advisor.concierge, 'chips_for', return_value=[{'verb': 'next', 'label': 'Next'}]):
            rid = advisor.notice(s, 'report.landed', 'message', mid, wait=True, llm=llm)
        self.assertEqual(s._one('SELECT Dropped FROM advice WHERE Id=?', (rid,))['Dropped'], 'no actions'); self.assertEqual(llm.calls, [])

    def test_the_hourly_cap_drops_without_a_call(self):
        s = MemoryStore(); s.set_setting(advisor.CAP_KEY, '1', 'test'); t = self._stopped_task(s); t2 = self._stopped_task(s)
        llm = brain_saying({'verb': 'continue', 'line': 'x', 'evidence': []})
        advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=llm)
        rid = advisor.notice(s, 'agent.stopped', 'task', t2, wait=True, llm=llm)
        self.assertEqual(s._one('SELECT Dropped FROM advice WHERE Id=?', (rid,))['Dropped'], 'cap'); self.assertEqual(len(llm.calls), 1)
        s._exec("UPDATE advice SET CreatedAt=?", ((datetime.now() - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S'),))
        t3 = self._stopped_task(s); advisor.notice(s, 'agent.stopped', 'task', t3, wait=True, llm=llm)
        self.assertEqual(len(llm.calls), 2)

    def test_no_brain_is_a_drop_never_an_error(self):
        s = MemoryStore(); t = self._stopped_task(s)
        with mock.patch.object(advisor, 'build_llm', return_value=None):
            rid = advisor.notice(s, 'agent.stopped', 'task', t, wait=True)
        self.assertEqual(s._one('SELECT Dropped FROM advice WHERE Id=?', (rid,))['Dropped'], 'no brain')

    def test_the_switch_off_runs_nothing(self):
        s = MemoryStore(); s.set_setting(advisor.ON_KEY, '0', 'test'); t = self._stopped_task(s)
        llm = brain_saying({'verb': 'continue', 'line': 'x', 'evidence': []})
        self.assertIsNone(advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=llm)); self.assertEqual(llm.calls, [])

    def test_habit_counts_come_from_the_ledger(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        for v in ('held', 'held', 'reopened'):
            i = outcomes.record(s, 'task.closed', 'task', t); outcomes.settle(s, i, v, v)
        self.assertEqual(advisor.habit(s, 'close', {'tid': t}), (2, 3))
        for v in ('approve', 'edit', 'approve'):
            i = outcomes.record(s, 'reply.sent', 'task', t, facts={'verb': v}); outcomes.settle(s, i, 'settled', 'settled')
        self.assertEqual(advisor.habit(s, 'approve', {'tid': t}), (2, 3))
        self.assertEqual(advisor.habit(s, 'defer', {'tid': t}), (0, 0))


class DoorTests(unittest.TestCase):
    def _session(self, s, tid):
        from types import SimpleNamespace
        return SimpleNamespace(sid='run1', alive=True, task_id=tid, cwd='C:/x', agent='coder', label='coder', argv=['claude'], last=1.0,
                               ext_id='', started='2026-10-12 09:00:00', typed=[], files=lambda: [], tail=lambda n=3: [], idle=lambda: 0.0,
                               witness=SimpleNamespace(note=lambda n: None), store=s, bg={})

    def test_a_stop_notices_once_per_stretch_and_an_ask_notices(self):
        from taskuary import hooks, workerstate as ws
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner'); sess = self._session(s, t)
        with mock.patch.object(advisor, 'notice') as n:
            for _ in range(3): hooks._events(sess, {'hook_event_name': 'Stop', 'last_assistant_message': ''})
            self.assertEqual([c.args[1] for c in n.call_args_list], ['agent.stopped'])
            ws.record(s, t, 'run1', 'input_needed', text='Open the PR?')
            self.assertEqual([c.args[1] for c in n.call_args_list], ['agent.stopped', 'agent.asked'])

    def test_an_interrupted_agent_is_noticed_at_startup(self):
        """Taskuary closed while the coder had TQ-1048: the Stop hook never fires for a close, so no door told the Advisor and the card
        carried no line (the owner, 2026-10-12). The close itself may run no model, so the startup is where it hears of it."""
        from taskuary import terminal
        s = MemoryStore()
        t = s.create_task({'Title': 'x', 'Status': 'in_progress', 'Assignee': 'agent:coder'}, 'owner')
        terminal.release_task(s, t, 'shutdown', 'closed')                                   # the close, already recorded
        u = s.create_task({'Title': 'y', 'Status': 'in_progress', 'Assignee': 'agent:coder'}, 'owner')   # died with the process
        s.create_task({'Title': 'z', 'Status': 'open'}, 'owner')                               # nobody's stop
        with mock.patch.object(advisor, 'notice') as n:
            terminal.recover_after_restart(s)
        self.assertEqual(sorted(c.args[1:] for c in n.call_args_list), [('agent.stopped', 'task', t), ('agent.stopped', 'task', u)])

    def test_a_close_notices_through_the_one_door(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        with mock.patch.object(advisor, 'notice') as n:
            s.update_task(t, {'Status': 'done'}, 'owner')
        self.assertEqual(n.call_args.args[1:], ('task.closed', 'task', t))

    def test_a_late_due_notices_once(self):
        from taskuary import remind
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'open', 'DueAt': '2026-01-01'}, 'owner')
        with mock.patch.object(advisor, 'notice') as n:
            remind.deadlines(s, datetime(2026, 1, 9, 9)); remind.deadlines(s, datetime(2026, 1, 10, 9))
        self.assertEqual([c.args[1:] for c in n.call_args_list], [('due.late', 'task', t)])


class ReadTests(_Rail):
    def _advised(self):
        s = MemoryStore(); t = self._stopped_task(s)
        rid = advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=brain_saying({'verb': 'continue', 'line': 'You usually continue it.', 'evidence': []}))
        return s, t, rid

    def test_for_key_reads_the_rows_line_and_pill(self):
        s, t, rid = self._advised()
        with mock.patch.object(advisor, 'notice') as n:
            d = advisor.for_key(s, f'task:{t}')
        self.assertEqual((d['verb'], d['line'], d['pill']), ('continue', 'You usually continue it.', d['label']))
        self.assertEqual(n.call_args.kwargs.get('tier'), 2)                         # the item on the table earns the bigger read, once

    def test_advice_vanishes_when_the_item_moves(self):
        s, t, rid = self._advised()
        s.update_task(t, {'Status': 'waiting'}, 'owner')
        with mock.patch.object(advisor, 'notice'): self.assertEqual(advisor.for_key(s, f'task:{t}'), {})

    def test_notes_say_what_was_decided_and_dropped(self):
        s, t, rid = self._advised()
        advisor.notice(s, 'agent.asked', 'task', t, wait=True, llm=brain_saying({'verb': 'approve', 'line': 'x', 'evidence': []}))   # same revision: skipped, no row
        s.update_task(t, {'Status': 'waiting'}, 'owner'); funnel.invalidate()
        advisor.notice(s, 'agent.asked', 'task', t, wait=True, llm=brain_saying({'verb': 'approve', 'line': 'Send it.', 'evidence': []}))
        ns = advisor.notes(s, f'task:{t}')
        self.assertEqual([(n['verb'], bool(n['dropped'])) for n in ns], [(None, True), ('continue', False)])
        self.assertIn('approve', ns[0]['dropped'])

    def test_the_chat_block_carries_the_line_for_why(self):
        s, t, rid = self._advised()
        self.assertIn('You usually continue it.', advisor.block(s, {'key': f'task:{t}', 'tid': t}))
        self.assertEqual(advisor.block(s, {'key': 'conn:1'}), '')


class ApiTests(unittest.TestCase):
    def test_the_routes_answer(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'in_progress'}, 'owner')
        with mock.patch.object(server, 'store', s), mock.patch.object(advisor, 'notice'):
            c = TestClient(server.app)
            self.assertEqual(c.get(f'/api/advice?key=task:{t}').json(), {})
            self.assertEqual(c.get(f'/api/advice/notes?key=task:{t}').json(), {'rows': []})
            self.assertEqual(c.get('/api/advice?key=conn:1').json(), {})


class SchemaTests(unittest.TestCase):
    def test_the_two_knobs_are_in_the_advisor_group(self):
        import pathlib
        d = json.loads(pathlib.Path('taskuary/settings_schema.json').read_text(encoding='utf-8'))
        self.assertEqual(d['knobs']['advisor_events']['group'], 'Advisor')
        self.assertEqual(d['knobs']['advisor_event_cap']['group'], 'Advisor')


class FixPassTests(_Rail):
    """The review's fix pass (2026-10-12): what a real install does that the first tests did not reach."""
    def _advised(self):
        s = MemoryStore(); t = self._stopped_task(s)
        rid = advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=brain_saying({'verb': 'continue', 'line': 'You usually continue it.', 'evidence': []}))
        return s, t, rid

    def test_the_rails_own_key_resolves_to_the_card(self):
        s, t, rid = self._advised()
        card = next(i for i in funnel.pile(s, quiet=True)['items'] if i.get('tid') == t)
        self.assertTrue(card['key'].startswith('processing:'))
        self.assertEqual(advisor.target_of(s, card['key']), ('task', t))
        with mock.patch.object(advisor, 'notice'):
            self.assertEqual(advisor.for_key(s, card['key'])['verb'], 'continue')
            self.assertEqual(len(advisor.notes(s, card['key'])), 1)
            self.assertIn('You usually continue it.', advisor.block(s, {'key': card['key'], 'tid': t}))

    def test_one_revision_is_judged_once_even_when_two_events_race(self):
        s = MemoryStore(); t = self._stopped_task(s); rev = advisor.revision(s, 'task', t)
        llm = brain_saying({'verb': 'continue', 'line': 'x', 'evidence': []})
        a = advisor.judge(s, 'agent.stopped', 'task', t, rev, 1, llm); b = advisor.judge(s, 'reply.arrived', 'task', t, rev, 1, llm)
        self.assertEqual((a, b, len(llm.calls)), (a, a, 1))                            # the second judge finds the row and calls nothing
        advisor._INFLIGHT.add(('task', t, rev, 1))
        try: self.assertIsNone(advisor.notice(s, 'agent.asked', 'task', t, wait=True, llm=llm))
        finally: advisor._INFLIGHT.discard(('task', t, rev, 1))

    def test_a_stop_that_asked_is_the_ask_not_the_stop(self):
        from taskuary import hooks, selfclose
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        from types import SimpleNamespace
        sess = SimpleNamespace(sid='run1', alive=True, task_id=t, cwd='C:/x', agent='coder', label='coder', argv=['claude'], last=1.0, ext_id='',
                               started='2026-10-12 09:00:00', typed=[], files=lambda: [], tail=lambda n=3: [], idle=lambda: 0.0,
                               witness=SimpleNamespace(note=lambda n: None), store=s, bg={})
        with mock.patch.object(advisor, 'notice') as n, mock.patch.object(selfclose, 'ask_markers', return_value=('Open the PR?', [('Open the PR?', ['yes', 'no'])])):
            hooks._events(sess, {'hook_event_name': 'Stop', 'last_assistant_message': 'Open the PR?'})
        self.assertEqual([c.args[1] for c in n.call_args_list], ['agent.asked'])

    def test_the_cap_counts_model_calls_only(self):
        s = MemoryStore(); s.set_setting(advisor.CAP_KEY, '1', 'test'); t = self._stopped_task(s)
        llm = brain_saying({'verb': 'continue', 'line': 'x', 'evidence': []})
        self.assertEqual(s._one('SELECT Dropped FROM advice WHERE Id=?', (advisor.notice(s, 'task.closed', 'task', 999, wait=True, llm=llm),))['Dropped'], 'no item')
        advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=llm)
        self.assertEqual(len(llm.calls), 1)                                              # a drop that called no model spends no cap

    def test_a_closed_task_with_no_session_is_no_item(self):
        s = MemoryStore(); t = self._stopped_task(s); llm = brain_saying({'verb': 'close', 'line': 'x', 'evidence': []})
        with mock.patch.object(advisor, 'notice'): s.update_task(t, {'Status': 'done'}, 'owner')
        funnel.invalidate()
        rid = advisor.notice(s, 'task.closed', 'task', t, wait=True, llm=llm)
        self.assertEqual(s._one('SELECT Dropped FROM advice WHERE Id=?', (rid,))['Dropped'], 'no item'); self.assertEqual(llm.calls, [])

    def test_a_pill_pressed_on_a_moved_item_is_refused(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'open'}, 'owner')
        with mock.patch.object(server, 'store', s):
            c = TestClient(server.app)
            r = c.post('/api/concierge/propose', json={'verb': 'close', 'key': f'task:{t}', 'table': True, 'revision': 'stale'})
        self.assertEqual(r.status_code, 409); self.assertIn('changed', r.json()['detail'])


class PlainLineTests(unittest.TestCase):
    """The line is read by the owner: "You should stop_agent because out13 shows..." reached the prompt box (2026-10-13)."""
    def test_ids_never_reach_the_owner(self):
        from taskuary.advisor import plain
        self.assertEqual(plain('You should stop_agent because out13 shows it resumed.', 'stop_agent', 'Save and end session'),
                         'You should "Save and end session" because an earlier outcome shows it resumed.')
        self.assertEqual(plain('Remind me later, the meeting moved (out4, mem2).', 'defer', 'Remind me'), 'Remind me later, the meeting moved.')
        self.assertEqual(plain('Close it - Erin already answered.', 'close', 'Close'), 'Close it - Erin already answered.')

    def test_continued_is_not_success_and_a_wrong_verb_is_silence(self):
        from taskuary.advisor import SYSTEM
        self.assertIn('never call it a success', SYSTEM)
        self.assertIn('say nothing', SYSTEM)
