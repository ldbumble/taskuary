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


class ReadTests(_Rail):
    def _advised(self):
        s = MemoryStore(); t = self._asked_task(s)
        rid = advisor.notice(s, 'reply.arrived', 'task', t, wait=True, llm=brain_saying({'verb': 'defer', 'line': 'Gail is away until Monday.', 'evidence': []}))
        return s, t, rid

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

    def test_one_revision_is_judged_once_even_when_two_events_race(self):
        s = MemoryStore(); t = self._asked_task(s); rev = advisor.revision(s, 'task', t)
        llm = brain_saying({'verb': 'regular_agent', 'line': 'x', 'evidence': []})
        a = advisor.judge(s, 'agent.stopped', 'task', t, rev, 1, llm); b = advisor.judge(s, 'reply.arrived', 'task', t, rev, 1, llm)
        self.assertEqual((a, b, len(llm.calls)), (a, a, 1))                            # the second judge finds the row and calls nothing
        advisor._INFLIGHT.add(('task', t, rev, 1))
        try: self.assertIsNone(advisor.notice(s, 'agent.asked', 'task', t, wait=True, llm=llm))
        finally: advisor._INFLIGHT.discard(('task', t, rev, 1))

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
