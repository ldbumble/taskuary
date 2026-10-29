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
                           line='You usually merge it here.', verb='continue', label='Keep going', count=(8, 8), evidence=['out3'], model='haiku')
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
    funnel.invalidate(); yield s; funnel.invalidate(); s.close()


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
        rid = s.start_run(t, 'coding', 'move the export', 'owner'); s._exec("UPDATE run SET Status='stopped' WHERE RunId=?", (rid,))   # the agent left: Continue leads
        # ...with its conversation saved, so the task's row draws Continue (concierge.row_buttons) - the only buttons the Advisor picks from
        s._exec("INSERT INTO transcript (TaskId, Sid, Agent, Text, CreatedAt, ExtId) VALUES (?,?,?,?,?,?)", (t, 'run1', 'coding', 'x', (datetime.now() + timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S'), 'ext-1'))
        s.reconcile_processing_membership(); s.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=[]); funnel.invalidate()
        return t

    def _asked_task(self, s, who=('Gail Moreno', 'gail@northwind.example')):
        """Someone asked and nothing is on it - the state the model reads (an ask that is really work, or someone else's): the rule lights
        Reply at once, and the model's verb, where it differs, stands with its line (advisor.decide)."""
        s.set_setting('calendar_enabled', '0', 'test')
        t = s.create_task({'Title': 'Export job', 'Status': 'open', 'Kind': 'task'}, 'owner')
        s.add_message({'ConversationId': f'c{t}', 'Channel': 'email', 'Subject': 'Export job', 'FromEmail': who[1], 'FromName': who[0],
                       'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'BodyText': 'Please move the export.', 'Status': 'routed', 'TaskId': t})
        s.reconcile_processing_membership(); s.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=[]); funnel.invalidate()
        return t


class JudgeTests(_Rail):
    def test_a_verb_the_item_carries_lands_with_the_ledgers_number(self):
        s = MemoryStore(); t = self._asked_task(s)
        for _ in range(3):
            i = outcomes.record(s, 'task.closed', 'task', t); outcomes.settle(s, i, 'held', 'held')
        llm = brain_saying({'verb': 'close', 'line': 'Gail answered it herself.', 'evidence': ['out1']})
        rid = advisor.notice(s, 'reply.arrived', 'task', t, wait=True, llm=llm)
        r = s._one('SELECT * FROM advice WHERE Id=?', (rid,))
        self.assertEqual((r['Verb'], r['Line'], json.loads(r['CountJson']), r['Dropped']), ('close', 'Gail answered it herself.', [3, 3, 'with northwind.example'], None))
        self.assertIn('close (Mark done)', llm.calls[0][1]); self.assertIn('out1', llm.calls[0][1])
        # ...the count is the model's evidence (its ledger line), never a mark on the button (the owner, 2026-10-25)
        self.assertIn('3 of the last 3 tasks the owner closed stayed closed', llm.calls[0][1])
        self.assertEqual(advisor.notes(s, f'task:{t}')[0]['pill'], r['Label'])

    def test_the_same_revision_is_judged_once(self):
        s = MemoryStore(); t = self._asked_task(s)
        llm = brain_saying({'verb': 'regular_agent', 'line': 'x', 'evidence': []})
        advisor.notice(s, 'reply.arrived', 'task', t, wait=True, llm=llm)
        self.assertIsNone(advisor.notice(s, 'agent.asked', 'task', t, wait=True, llm=llm))
        self.assertEqual(len(llm.calls), 1)

    def test_a_state_the_rule_decides_asks_the_model_nothing(self):
        """THE RULE DECIDES FIRST (the design, phase A, 2026-10-23): an agent that stopped is decided from the facts - an event on it
        spends nothing of the hourly cap - and a plain stop lights nothing (NO DEFAULT VERB, the owner, 2026-10-28): its Continue comes
        only from the finish check, with what it dropped."""
        s = MemoryStore(); t = self._stopped_task(s)
        llm = brain_saying({'verb': 'close', 'line': 'x', 'evidence': []})
        rid = advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=llm)
        self.assertEqual((s._one('SELECT Dropped FROM advice WHERE Id=?', (rid,))['Dropped'], llm.calls), ('left to the rule', []))
        with mock.patch.object(advisor, 'notice') as n: d = advisor.decide(s, f'task:{t}')
        self.assertEqual((d['verb'], d['by'], d['state']), (None, 'rule', 'stopped')); n.assert_not_called()

    def test_silence_is_a_row_with_no_verb_and_no_pill(self):
        s = MemoryStore(); t = self._asked_task(s)
        llm = brain_saying({'verb': None, 'line': '', 'evidence': []})
        rid = advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=llm)
        r = s._one('SELECT * FROM advice WHERE Id=?', (rid,))
        self.assertEqual((r['Verb'], r['Dropped']), (None, 'nothing to say'))
        self.assertEqual(len(llm.calls), 1)                                          # silence is the answer, not a missing key

    def test_a_line_that_asks_the_agents_own_question_again_is_dropped(self):
        # the owner, 2026-10-21: the Advisor must not repeat a question the agent is already asking - it is in the agent's pane
        from taskuary import workerstate as ws
        s = MemoryStore(); t = self._asked_task(s)
        st = {'state': 'input_needed', 'requests': [{'kind': 'input_needed', 'text': 'Should I push the fix to ray/census-fix or open a new branch?'}]}
        with mock.patch.object(ws, 'status', return_value=st):
            llm = brain_saying({'verb': 'regular_agent', 'line': 'Which branch should the fix land on?', 'evidence': [], 'repeats_agent_question': True})
            rid = advisor.notice(s, 'agent.asked', 'task', t, wait=True, llm=llm)
        r = s._one('SELECT * FROM advice WHERE Id=?', (rid,))
        self.assertEqual((r['Verb'], r['Dropped']), (None, "repeats the agent's question"))
        with mock.patch.object(ws, 'status', return_value=st), mock.patch.object(advisor, 'notice'):
            self.assertEqual(advisor.for_key(s, f'task:{t}').get('line'), '', 'no line over the question')

    def test_a_line_about_something_else_stands_over_an_asking_agent(self):
        from taskuary import workerstate as ws
        s = MemoryStore(); t = self._asked_task(s)
        st = {'state': 'input_needed', 'requests': [{'kind': 'input_needed', 'text': 'Should I push the fix to ray/census-fix or open a new branch?'}]}
        with mock.patch.object(ws, 'status', return_value=st):
            llm = brain_saying({'verb': 'forward', 'line': 'Ray Colton owns the exports.', 'evidence': [], 'repeats_agent_question': False})
            rid = advisor.notice(s, 'agent.asked', 'task', t, wait=True, llm=llm)
            self.assertIn('THE AGENT IS ASKING: Should I push the fix', llm.calls[-1][1], 'the question is in the prompt the model judges against')
        self.assertEqual(s._one('SELECT * FROM advice WHERE Id=?', (rid,))['Verb'], 'forward')
        self.assertIn('repeats_agent_question', advisor.SYSTEM); self.assertIn('repeats_agent_question', advisor.WANT['properties'])
        # ...a permission or a wall is not a question
        with mock.patch.object(ws, 'status', return_value={'requests': [{'kind': 'approval_needed', 'text': 'Run git push?'}, {'kind': 'input_needed', 'text': 'Which branch?'}]}):
            self.assertEqual(advisor._asking(s, t), ['Which branch?'])

    def test_the_repeat_flag_is_read_only_while_the_agent_is_asking(self):
        # the flag is the model's; with nothing asked there is nothing to repeat, and the line stands
        from taskuary import workerstate as ws
        s = MemoryStore(); t = self._asked_task(s)
        with mock.patch.object(ws, 'status', return_value={'state': 'input_needed', 'requests': [{'kind': 'approval_needed', 'text': 'Run git push?'}]}):
            rid = advisor.notice(s, 'agent.asked', 'task', t, wait=True,
                                 llm=brain_saying({'verb': 'forward', 'line': 'Ray Colton owns the exports.', 'evidence': [], 'repeats_agent_question': True}))
        self.assertEqual(s._one('SELECT * FROM advice WHERE Id=?', (rid,))['Verb'], 'forward')

    def test_a_verb_the_item_cannot_carry_is_dropped(self):
        s = MemoryStore(); t = self._asked_task(s)
        rid = advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=brain_saying({'verb': 'approve', 'line': 'Send it.', 'evidence': []}))
        r = s._one('SELECT * FROM advice WHERE Id=?', (rid,))
        self.assertEqual(r['Verb'], None); self.assertIn('approve', r['Dropped'])

    def test_a_verb_named_as_the_prompt_lists_it_is_the_verb(self):
        # "continue (Keep going)" copied whole from VERBS OFFERED was dropped as not offered
        w = advisor.concierge.CHIP_WORDS['regular_agent']
        for said in (f'regular_agent ({w})', w, 'regular_agent'):
            s = MemoryStore(); t = self._asked_task(s)
            rid = advisor.notice(s, 'reply.arrived', 'task', t, wait=True, llm=brain_saying({'verb': said, 'line': 'Needs the export built.', 'evidence': []}))
            r = s._one('SELECT * FROM advice WHERE Id=?', (rid,))
            self.assertEqual((r['Verb'], r['Dropped']), ('regular_agent', None), said)

    def test_an_item_with_no_actions_is_dropped_without_a_call(self):
        s = MemoryStore()
        mid = s.add_message({'ConversationId': 'c2', 'Channel': 'email', 'Subject': 'Newsletter', 'FromEmail': 'news@vendor.example',
                             'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'BodyText': 'x', 'Status': 'filed'})
        llm = brain_saying({'verb': 'close', 'line': 'x', 'evidence': []})
        with mock.patch.object(advisor.concierge, 'chips_for', return_value=[{'verb': 'next', 'label': 'Next'}]):
            rid = advisor.notice(s, 'report.landed', 'message', mid, wait=True, llm=llm)
        self.assertEqual(s._one('SELECT Dropped FROM advice WHERE Id=?', (rid,))['Dropped'], 'no actions'); self.assertEqual(llm.calls, [])

    def test_the_hourly_cap_drops_without_a_call(self):
        s = MemoryStore(); s.set_setting(advisor.CAP_KEY, '1', 'test'); t = self._asked_task(s); t2 = self._asked_task(s)
        llm = brain_saying({'verb': 'regular_agent', 'line': 'x', 'evidence': []})
        advisor.notice(s, 'reply.arrived', 'task', t, wait=True, llm=llm)
        rid = advisor.notice(s, 'reply.arrived', 'task', t2, wait=True, llm=llm)
        self.assertEqual(s._one('SELECT Dropped FROM advice WHERE Id=?', (rid,))['Dropped'], 'cap'); self.assertEqual(len(llm.calls), 1)
        # ...and over the cap nothing is coming, so the rule's own facts decide at once: an ask under a day old has no fact to say, and
        # NO DEFAULT VERB lights nothing (the owner, 2026-10-28) - never "Thinking..."
        with mock.patch.object(advisor, 'notice'): d = advisor.decide(s, f'task:{t2}')
        self.assertEqual((d['verb'], d['line'], d['by']), (None, '', 'rule'))
        s._exec("UPDATE advice SET CreatedAt=?", ((datetime.now() - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S'),))
        t3 = self._asked_task(s); advisor.notice(s, 'reply.arrived', 'task', t3, wait=True, llm=llm)
        self.assertEqual(len(llm.calls), 2)

    def test_no_brain_is_a_drop_never_an_error(self):
        s = MemoryStore(); t = self._asked_task(s)
        with mock.patch.object(advisor, 'build_llm', return_value=None):
            rid = advisor.notice(s, 'agent.stopped', 'task', t, wait=True)
        self.assertEqual(s._one('SELECT Dropped FROM advice WHERE Id=?', (rid,))['Dropped'], 'no brain')

    def test_the_switch_off_runs_nothing(self):
        s = MemoryStore(); s.set_setting(advisor.ON_KEY, '0', 'test'); t = self._stopped_task(s)
        llm = brain_saying({'verb': 'continue', 'line': 'x', 'evidence': []})
        self.assertIsNone(advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=llm)); self.assertEqual(llm.calls, [])

    def test_habit_counts_come_from_the_ledger_for_this_sender_never_over_everything(self):
        # one global count stood under every item (the deep dive, 2026-10-20): it is the sender's domain's now, or nothing
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        s.add_message({'Channel': 'email', 'Subject': 'x', 'FromEmail': 'gail@northwind.example', 'BodyText': 'x', 'Status': 'routed', 'TaskId': t})
        o = s.create_task({'Title': 'y'}, 'owner')
        s.add_message({'Channel': 'email', 'Subject': 'y', 'FromEmail': 'tom@vendor.example', 'BodyText': 'y', 'Status': 'routed', 'TaskId': o})
        for v in ('held', 'held', 'reopened'):
            i = outcomes.record(s, 'task.closed', 'task', t); outcomes.settle(s, i, v, v)
        i = outcomes.record(s, 'task.closed', 'task', o); outcomes.settle(s, i, 'reopened', 'reopened')
        self.assertEqual(advisor.habit(s, 'close', {'tid': t}), (2, 3, 'with northwind.example'))
        for v in ('approve', 'edit', 'approve'):
            i = outcomes.record(s, 'reply.sent', 'task', t, facts={'verb': v, 'who': 'gail@northwind.example'}); outcomes.settle(s, i, 'settled', 'settled')
        i = outcomes.record(s, 'reply.sent', 'task', o, facts={'verb': 'approve', 'who': 'tom@vendor.example'}); outcomes.settle(s, i, 'settled', 'settled')
        self.assertEqual(advisor.habit(s, 'approve', {'tid': t}), (2, 3, 'with northwind.example'))
        self.assertEqual(advisor.habit(s, 'defer', {'tid': t}), (0, 0, ''))
        self.assertEqual(advisor.habit(s, 'close', {'tid': s.create_task({'Title': 'z'}, 'owner')}), (0, 0, ''), 'nobody to count it for')


class DoorTests(unittest.TestCase):
    def _session(self, s, tid):
        from types import SimpleNamespace
        return SimpleNamespace(sid='run1', alive=True, task_id=tid, cwd='C:/x', agent='coding', label='coding', argv=['claude'], last=1.0,
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
        """Taskuary closed while the coding agent had TQ-1048: the Stop hook never fires for a close, so no door told the Advisor and the card
        carried no line (the owner, 2026-10-12). The close itself may run no model, so the startup is where it hears of it."""
        from taskuary import terminal
        s = MemoryStore()
        t = s.create_task({'Title': 'x', 'Status': 'in_progress', 'Assignee': 'agent:coding'}, 'owner')
        terminal.release_task(s, t, 'shutdown', 'closed')                                   # the close, already recorded
        u = s.create_task({'Title': 'y', 'Status': 'in_progress', 'Assignee': 'agent:coding'}, 'owner')   # died with the process
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
        s = MemoryStore(); t = self._asked_task(s)
        rid = advisor.notice(s, 'reply.arrived', 'task', t, wait=True, llm=brain_saying({'verb': 'defer', 'line': 'Gail is away until Monday.', 'evidence': []}))
        return s, t, rid

    def test_for_key_reads_the_rows_line_and_pill(self):
        s, t, rid = self._advised()
        with mock.patch.object(advisor, 'notice') as n:
            d = advisor.for_key(s, f'task:{t}')
        self.assertEqual((d['verb'], d['line'], d['pill'], d['by']), ('defer', 'Gail is away until Monday.', d['label'], 'model'))
        n.assert_not_called()                     # a line stands: a bigger read swapped it, and the button, under the owner's hand (B5)

    def test_advice_vanishes_when_the_item_moves(self):
        s, t, rid = self._advised()
        s.update_task(t, {'Status': 'waiting'}, 'owner')
        with mock.patch.object(advisor, 'notice'): d = advisor.for_key(s, f'task:{t}')
        self.assertEqual((d['by'], d['line']), ('rule', ''), 'the line judged before the move is gone; the rule lights the move now')

    def test_the_item_on_the_table_is_judged_when_no_event_ever_was(self):
        """Never left guessing (the Advisor audit, 2026-10-15): only eight events judged an item, so a task that moved since its last
        one had an empty bar for good. Read for the table, it is judged at its revision - once."""
        s = MemoryStore(); t = self._asked_task(s)
        with mock.patch.object(advisor, 'notice') as n:
            self.assertEqual(advisor.for_key(s, f'task:{t}')['verb'], None, "nothing is lit while the model reads it (the owner, 2026-10-28)")
        self.assertEqual((n.call_args.args[1], n.call_args.kwargs.get('tier')), (advisor.SHOWN, 2))
        self.assertIn('item.shown', advisor.SYSTEM)                               # the prompt owes it a next step

    def test_the_prompt_carries_what_the_agent_said_and_asks(self):
        # the card's preview is the sender's mail: without the agent's own words a finished draft read as "stop the agent"
        from taskuary import workerstate as ws
        s = MemoryStore(); t = self._stopped_task(s)
        st = {'said': 'The reply above is ready for you to review and send.', 'requests': [{'text': 'Send it now?'}], 'state': 'unknown'}
        with mock.patch.object(ws, 'status', return_value=st):
            p = advisor._prompt(s, 'agent.stopped', advisor._item(s, 'task', t) or {'ref': 'x'}, [{'verb': 'continue', 'label': 'Keep going'}], 1, 'task', t)
        self.assertIn('THE AGENT LAST SAID: The reply above is ready for you to review and send.', p)
        self.assertIn('THE AGENT IS ASKING: Send it now?', p)
        self.assertIn('reviews or sends it', advisor.SYSTEM)

    def test_an_agent_at_work_has_no_line_until_it_stops_again(self):
        # a continue writes nothing the revision sees until the prompt lands: the stop's line stood over a working coding agent
        from taskuary import workerstate as ws
        s = MemoryStore(); t = self._stopped_task(s)
        with mock.patch.object(advisor, 'notice'), mock.patch.object(ws, 'status', return_value={'state': 'working'}):
            d = advisor.for_key(s, f'task:{t}')
        self.assertEqual((d['verb'], d['line'], d['state']), ('next', '', 'working'), 'an agent at work: Next lit, nothing said')
        for state in ('input_needed', 'approval_needed', 'unknown', 'disconnected'):
            with mock.patch.object(advisor, 'notice'), mock.patch.object(ws, 'status', return_value={'state': state}):
                self.assertEqual(advisor.for_key(s, f'task:{t}')['verb'], None, state)     # a plain stop: nothing lit

    def test_notes_say_what_was_decided_and_dropped(self):
        s, t, rid = self._advised()
        advisor.notice(s, 'agent.asked', 'task', t, wait=True, llm=brain_saying({'verb': 'approve', 'line': 'x', 'evidence': []}))   # same revision: skipped, no row
        s.add_message({'ConversationId': f'c{t}', 'Channel': 'email', 'Subject': 'RE: Export job', 'FromEmail': 'gail@northwind.example', 'FromName': 'Gail Moreno',
                       'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'BodyText': 'Any news?', 'Status': 'routed', 'TaskId': t}); funnel.invalidate()
        advisor.notice(s, 'reply.arrived', 'task', t, wait=True, llm=brain_saying({'verb': 'approve', 'line': 'Send it.', 'evidence': []}))
        ns = advisor.notes(s, f'task:{t}')
        self.assertEqual([(n['verb'], bool(n['dropped'])) for n in ns], [(None, True), ('defer', False)])
        self.assertIn('approve', ns[0]['dropped'])

    def test_the_chat_block_carries_the_line_for_why(self):
        s, t, rid = self._advised()
        self.assertIn('Gail is away until Monday.', advisor.block(s, {'key': f'task:{t}', 'tid': t}))
        self.assertEqual(advisor.block(s, {'key': 'conn:1'}), '')


class ApiTests(unittest.TestCase):
    def test_the_routes_answer(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'in_progress'}, 'owner')
        with mock.patch.object(server, 'store', s), mock.patch.object(advisor, 'notice'):
            c = TestClient(server.app)
            # one decision, at once: an own task with nothing asked lights Next and says nothing - never a spinner (the owner, 2026-10-23)
            got = c.get(f'/api/advice?key=task:{t}').json()
            self.assertEqual((got['verb'], got['line'], 'pending' in got), ('next', '', False))
            self.assertEqual(c.get(f'/api/advice/notes?key=task:{t}').json(), {'rows': []})
            self.assertEqual(c.get('/api/advice?key=conn:1').json(), {'none': 'nothing'})


class SchemaTests(unittest.TestCase):
    def test_the_two_knobs_are_in_the_advisor_group(self):
        import pathlib
        d = json.loads(pathlib.Path('taskuary/settings_schema.json').read_text(encoding='utf-8'))
        self.assertEqual(d['knobs']['advisor_events']['group'], 'Advisor')
        self.assertEqual(d['knobs']['advisor_event_cap']['group'], 'Advisor')


class FixPassTests(_Rail):
    """The review's fix pass (2026-10-12): what a real install does that the first tests did not reach."""
    def _advised(self):
        s = MemoryStore(); t = self._asked_task(s)
        rid = advisor.notice(s, 'reply.arrived', 'task', t, wait=True, llm=brain_saying({'verb': 'defer', 'line': 'Gail is away until Monday.', 'evidence': []}))
        return s, t, rid

    def test_the_rails_own_key_resolves_to_the_card(self):
        s, t, rid = self._advised()
        card = next(i for i in funnel.pile(s, quiet=True)['items'] if i.get('tid') == t)
        self.assertTrue(card['key'].startswith('processing:'))
        self.assertEqual(advisor.target_of(s, card['key']), ('task', t))
        with mock.patch.object(advisor, 'notice'):
            self.assertEqual(advisor.for_key(s, card['key'])['verb'], 'defer')
            self.assertEqual(len(advisor.notes(s, card['key'])), 1)
            self.assertIn('Gail is away until Monday.', advisor.block(s, {'key': card['key'], 'tid': t}))

    def test_one_revision_is_judged_once_even_when_two_events_race(self):
        s = MemoryStore(); t = self._asked_task(s); rev = advisor.revision(s, 'task', t)
        llm = brain_saying({'verb': 'regular_agent', 'line': 'x', 'evidence': []})
        a = advisor.judge(s, 'agent.stopped', 'task', t, rev, 1, llm); b = advisor.judge(s, 'reply.arrived', 'task', t, rev, 1, llm)
        self.assertEqual((a, b, len(llm.calls)), (a, a, 1))                            # the second judge finds the row and calls nothing
        advisor._INFLIGHT.add(('task', t, rev, 1))
        try: self.assertIsNone(advisor.notice(s, 'agent.asked', 'task', t, wait=True, llm=llm))
        finally: advisor._INFLIGHT.discard(('task', t, rev, 1))

    def test_a_stop_that_asked_is_the_ask_not_the_stop(self):
        from taskuary import hooks, selfclose
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        from types import SimpleNamespace
        sess = SimpleNamespace(sid='run1', alive=True, task_id=t, cwd='C:/x', agent='coding', label='coding', argv=['claude'], last=1.0, ext_id='',
                               started='2026-10-12 09:00:00', typed=[], files=lambda: [], tail=lambda n=3: [], idle=lambda: 0.0,
                               witness=SimpleNamespace(note=lambda n: None), store=s, bg={})
        with mock.patch.object(advisor, 'notice') as n, mock.patch.object(selfclose, 'ask_markers', return_value=('Open the PR?', [('Open the PR?', ['yes', 'no'])])):
            hooks._events(sess, {'hook_event_name': 'Stop', 'last_assistant_message': 'Open the PR?'})
        self.assertEqual([c.args[1] for c in n.call_args_list], ['agent.asked'])

    def test_the_cap_counts_model_calls_only(self):
        s = MemoryStore(); s.set_setting(advisor.CAP_KEY, '1', 'test'); t = self._asked_task(s)
        llm = brain_saying({'verb': 'regular_agent', 'line': 'x', 'evidence': []})
        self.assertEqual(s._one('SELECT Dropped FROM advice WHERE Id=?', (advisor.notice(s, 'task.closed', 'task', 999, wait=True, llm=llm),))['Dropped'], 'no item')
        advisor.notice(s, 'reply.arrived', 'task', t, wait=True, llm=llm)
        self.assertEqual(len(llm.calls), 1)                                              # a drop that called no model spends no cap

    def test_a_closed_task_with_no_session_is_no_item(self):
        s = MemoryStore(); t = self._asked_task(s); llm = brain_saying({'verb': 'close', 'line': 'x', 'evidence': []})
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
        self.assertEqual(plain('You should stop_agent because out13 shows it resumed.', 'stop_agent', 'Stop and save'),
                         'You should "Stop and save" because an earlier outcome shows it resumed.')
        self.assertEqual(plain('Remind me later, the meeting moved (out4, mem2).', 'defer', 'Remind me'), 'Remind me later, the meeting moved.')
        self.assertEqual(plain('Close it - Erin already answered.', 'close', 'Close'), 'Close it - Erin already answered.')

    def test_an_id_is_said_as_what_it_is_and_a_dangling_citation_goes(self):
        """A memory line cited after the sentence read "Automated bank notice; no action asked. an earlier outcome" (the sweep, 2026-10-27)."""
        from taskuary.advisor import plain
        self.assertEqual(plain('Automated vendor notice; no action asked. lrn372574', 'not_ours', 'Not ours'), 'Automated vendor notice; no action asked.')
        self.assertEqual(plain('Vendor notice, no ask here - lrn12, mem3', 'not_ours', 'Not ours'), 'Vendor notice, no ask here')
        self.assertEqual(plain('Erin wrote again?  msg44', 'reply', 'Reply'), 'Erin wrote again?')
        self.assertEqual(plain('As lrn12 says, Ray handles payroll', 'forward', 'Hand off'), 'As what Taskuary knows says, Ray handles payroll')
        self.assertEqual(plain('Erin asked the same in msg44 last week', 'reply', 'Reply'), 'Erin asked the same in an earlier message last week')
        self.assertEqual(plain('lrn12', 'reply', 'Reply'), '')

    def test_continued_is_not_success_and_a_wrong_verb_is_silence(self):
        from taskuary.advisor import SYSTEM
        self.assertIn('never call it a success', SYSTEM)
        self.assertIn('say nothing', SYSTEM)


class AuditFixTests(_Rail):
    """The non-coder audit (2026-10-17): a drop for an outside reason is retried, a line stands once shown, the Advisor keeps out
    where the row's own move is right, and what it hands the owner and the chat is in plain words."""
    def test_no_ai_then_an_ai_is_retried_and_the_strip_is_told(self):
        s = MemoryStore(); t = self._asked_task(s)
        with mock.patch.object(advisor, 'build_llm', return_value=None):
            advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True); advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True)
            with mock.patch.object(advisor, 'notice'): self.assertEqual(advisor.for_key(s, f'task:{t}')['none'], 'no_ai')
        self.assertEqual([r['Dropped'] for r in advisor.rows(s, 'task', t)], ['no brain'])           # once per revision, or the re-read loops
        llm = brain_saying({'verb': 'defer', 'line': 'Gail is away until Monday.', 'evidence': []})
        advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True, llm=llm)
        self.assertEqual(len(llm.calls), 1)
        with mock.patch.object(advisor, 'notice'): self.assertEqual(advisor.for_key(s, f'task:{t}')['verb'], 'defer')
        # ...and a state the rule decides needs no AI at all: an agent that stopped is decided with none connected - a plain stop lights
        # nothing (NO DEFAULT VERB, the owner, 2026-10-28), and says no AI is missing
        u = self._stopped_task(s)
        with mock.patch.object(advisor, 'build_llm', return_value=None), mock.patch.object(advisor, 'notice'):
            d = advisor.for_key(s, f'task:{u}')
        self.assertEqual((d['state'], d['verb'], d.get('none')), ('stopped', None, None))

    def test_a_cap_or_a_bad_answer_is_tried_again(self):
        s = MemoryStore(); t = self._asked_task(s); rev = advisor.revision(s, 'task', t)
        for d in ('cap', 'no answer: timed out'):
            advisor._write(s, target_kind='task', target_id=t, key=f'task:{t}', event='x', revision=rev, tier=2, dropped=d)
        self.assertIsNone(advisor.row(s, 'task', t, rev))
        llm = brain_saying({'verb': 'defer', 'line': 'Gail is away until Monday.', 'evidence': []})
        advisor.notice(s, 'reply.arrived', 'task', t, wait=True, llm=llm); self.assertEqual(len(llm.calls), 1)

    def test_a_later_drop_never_hides_a_line_and_a_line_is_never_reread(self):
        s = MemoryStore(); t = self._asked_task(s); rev = advisor.revision(s, 'task', t)
        advisor.notice(s, 'reply.arrived', 'task', t, wait=True, llm=brain_saying({'verb': 'defer', 'line': 'Gail is away until Monday.', 'evidence': []}))
        advisor._write(s, target_kind='task', target_id=t, key=f'task:{t}', event='x', revision=rev, tier=2, dropped='nothing to say', model='m')
        self.assertEqual(advisor.row(s, 'task', t, rev)['Verb'], 'defer')
        llm = brain_saying({'verb': 'defer', 'line': 'Put it off.', 'evidence': []})
        self.assertIsNone(advisor.notice(s, 'reply.arrived', 'task', t, tier=2, wait=True, llm=llm)); self.assertEqual(llm.calls, [])
        self.assertEqual(advisor.judge(s, 'reply.arrived', 'task', t, rev, 2, llm), advisor.row(s, 'task', t, rev)['Id']); self.assertEqual(llm.calls, [])

    def test_the_small_reads_silence_still_earns_the_bigger_read(self):
        s = MemoryStore(); t = self._asked_task(s)
        advisor.notice(s, 'reply.arrived', 'task', t, wait=True, llm=brain_saying({'verb': None, 'line': '', 'evidence': []}))
        llm = brain_saying({'verb': 'defer', 'line': 'Gail is away until Monday.', 'evidence': []})
        advisor.notice(s, 'reply.arrived', 'task', t, tier=2, wait=True, llm=llm); self.assertEqual(len(llm.calls), 1)

    def test_unsorted_mail_and_a_report_that_ran_fine_get_no_advice(self):
        # ...the rulebook's now (quiet() folded in, the design phase A): its own button lit at once, the model never asked
        from taskuary import rulebook
        s = MemoryStore(); t = self._asked_task(s); llm = brain_saying({'verb': 'not_ours', 'line': 'x', 'evidence': []})
        for it, state in (({'kind': 'fyi', 'lane': 'unjudged', 'mid': 1}, 'unsorted'), ({'kind': 'report', 'lane': 'report', 'mid': 1}, 'report_ok')):
            self.assertEqual(rulebook.state(s, it, [])[0], state)
            s._exec('DELETE FROM advice')
            with mock.patch.object(advisor, '_item', return_value=it):
                rid = advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True, llm=llm)
            self.assertEqual((s._one('SELECT Dropped FROM advice WHERE Id=?', (rid,))['Dropped'], llm.calls), ('left to the rule', []))
        self.assertEqual(rulebook.state(s, {'kind': 'report', 'lane': 'broken', 'bad': True, 'why': 'mailbox signed out'}, [])[0], 'report_failed')

    def test_an_agent_waiting_on_you_is_answered_in_its_pane_never_by_a_lit_answer_it(self):
        """No "Answer it" button (owner-approved, 2026-10-20): it was even the lit one over a finished agent whose reply waited on the
        owner's approval. The Advisor is never offered it and its prompt never names it; a live agent's row leads with Stop and save."""
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'in_progress'}, 'owner')
        with mock.patch.object(advisor.concierge, '_agent_running', return_value=True):
            vs = advisor.offered(s, {'kind': 'agent', 'lane': 'blocked', 'tid': t, 'asking': True, 'key': f'agent:{t}'})
        self.assertNotIn('answer_agent', [v['verb'] for v in vs]); self.assertIn('stop_agent', [v['verb'] for v in vs])
        self.assertNotIn('next', [v['verb'] for v in vs]); self.assertNotIn('Answer it', advisor.SYSTEM)
        self.assertIn('answered in its own pane', advisor.SYSTEM)

    def test_the_prompt_speaks_by_the_owners_voice_and_says_where_it_stands_in_words(self):
        s = MemoryStore(); s.save_doc('counsel', '# Mine\n\n## Voice\n- Speak like a butler.\n', 'owner')
        self.assertIn('Speak like a butler.', advisor._system(s))
        item = {'ref': 'TQ-0001', 'kind': 'asked', 'lane': 'asked', 'title': 'Lease renewal'}
        p = advisor._prompt(s, 'agent.stopped', item, [{'verb': 'reply', 'label': 'Reply'}], 1, 'message', 1)
        self.assertIn('"where it stands": "asked you"', p); self.assertNotIn('"lane"', p); self.assertNotIn('"kind"', p)

    def test_each_count_is_evidence_in_words_of_what_it_measures(self):
        # the counts are evidence the model reads, never a line on the strip (the owner, 2026-10-25: remove "Your own habit...")
        self.assertEqual(advisor.measured('close', (2, 3)), '2 of the last 3 tasks the owner closed stayed closed.')
        self.assertEqual(advisor.measured('chase', (1, 4, 'with northwind.example')), "1 of the owner's last 4 nudges got an answer with northwind.example.")
        self.assertEqual((advisor.measured('defer', (3, 4)), advisor.measured('close', (1, 1))), ('', ''))
        self.assertTrue(all('moment like this' not in m and 'habit' not in m for m in advisor.MEASURES.values()))
        self.assertFalse(hasattr(advisor, 'says') or hasattr(advisor, 'habit_pick'))

    def test_the_chat_block_names_the_button_and_what_the_evidence_says(self):
        s = MemoryStore(); t = self._stopped_task(s)
        i = outcomes.record(s, 'agent.stopped', 'task', t, 'agent:coding', facts={}); outcomes.settle(s, i, 'continued 2 min later', 'continued')
        # ...a stop's Continue is the finish check's, with what the agent dropped as its line
        advisor.finish_check(s, t, wait=True, llm=brain_saying({'verdict': 'dropped', 'line': 'Attach the export it said it would', 'evidence': [f'out{i}']}))
        with mock.patch.object(advisor, 'notice'): b = advisor.block(s, {'key': f'task:{t}', 'tid': t})
        self.assertIn(advisor.concierge.CHIP_WORDS['continue'], b); self.assertNotIn('verb continue', b); self.assertNotIn(f'out{i}', b)
