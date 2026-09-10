"""The worker-lifecycle scenarios the walkthrough enumerates (PW-142, PW-228, PW-229, PW-234), one test each, against
the real status model (workerstate.py), the funnel, the hand-raise, self-close and the wrap."""
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import blackboard as bb, coder, funnel, selfclose, server, terminal as term, workerstate as ws
from tests.test_worker_events import Base, live


# ── PW-142: question relay ─────────────────────────────────────────────────────────────────
class Relay(Base):
    def test_two_waiting_agents_each_get_their_own_answer(self):
        other = self.fx.task(title='Other job', kind='coding')
        a, b = live(self.tid, 'a'), live(other, 'b'); a.send_prompt = lambda t: a.typed.append(t); b.send_prompt = lambda t: b.typed.append(t)
        term.SESSIONS.update(a=a, b=b)
        ws.record(self.s, self.tid, 'a', 'input_needed', text='Branch?', source='hook'); ws.record(self.s, other, 'b', 'input_needed', text='Region?', source='hook')
        self.assertTrue(ws.answer_open(self.s, self.tid, 'main', 'owner')['delivered'])
        self.assertEqual((a.typed, b.typed), (['main'], []))
        self.assertEqual([r['text'] for r in ws.status(self.s, other)['requests']], ['Region?'], 'the other agent still waits')

    def test_a_duplicate_click_delivers_once(self):
        a = live(self.tid); a.send_prompt = lambda t: a.typed.append(t); term.SESSIONS['run1'] = a
        ws.record(self.s, self.tid, 'run1', 'input_needed', request_id='q1', text='Branch?', source='hook')
        first, second = ws.answer(self.s, self.tid, 'q1', 'main'), ws.answer(self.s, self.tid, 'q1', 'main')
        self.assertEqual((first['delivered'], second['delivered'], second['state'], a.typed), (True, False, 'resolved', ['main']))

    def test_a_stale_approval_after_a_run_change_is_refused(self):
        ws.record(self.s, self.tid, 'run1', 'approval_needed', request_id='p1', text='Run the migration?', source='hook')
        b = live(self.tid, 'run2'); b.send_prompt = lambda t: b.typed.append(t); term.SESSIONS['run2'] = b
        out = ws.answer(self.s, self.tid, 'p1', 'yes')
        self.assertEqual((out['delivered'], out['state'], b.typed), (False, 'stale', []))

    def test_restart_recovery_keeps_the_open_request_and_says_disconnected(self):
        term.SESSIONS['run1'] = live(self.tid)
        ws.record(self.s, self.tid, 'run1', 'input_needed', request_id='q1', text='Branch?', source='hook')
        term.SESSIONS.clear()                                                   # the process restarted: sessions are gone, events are not
        st = ws.status(self.s, self.tid)
        # the question survives the restart and is still the state that shows; `live` says nobody is there to take the answer
        self.assertEqual((st['state'], st['live'], [r['request_id'] for r in st['requests']]), ('input_needed', False, ['q1']))
        out = ws.answer(self.s, self.tid, 'q1', 'main')
        self.assertEqual(out['state'], 'disconnected'); self.assertIn('Open the workspace', self.s.list_comments(self.tid)[-1]['Body'])

    def test_acceptance_is_visible_in_the_discussion(self):
        a = live(self.tid); a.send_prompt = lambda t: a.typed.append(t); term.SESSIONS['run1'] = a
        ws.record(self.s, self.tid, 'run1', 'input_needed', request_id='q1', text='Branch?', source='hook')
        ws.answer(self.s, self.tid, 'q1', 'main')
        body = self.s.list_comments(self.tid)[-1]['Body']
        self.assertIn('delivered to coder (run run1)', body); self.assertIn('main', body)

    def test_a_general_and_a_coding_agent_relay_through_the_same_road(self):
        general = self.fx.task(title='Compare vendors', kind='general')
        g = live(general, 'g', agent='assistant'); g.send_prompt = lambda t: g.typed.append(t)
        c = live(self.tid, 'c'); term.SESSIONS.update(g=g, c=c)
        ws.record(self.s, general, 'g', 'input_needed', text='Which vendor?', source='api'); ws.record(self.s, self.tid, 'c', 'input_needed', text='Which branch?', source='hook')
        with mock.patch.object(term, 'type_into', side_effect=lambda t, text: t.typed.append(text)):
            self.assertEqual(ws.answer_open(self.s, general, 'Acme')['path'], 'api'); self.assertEqual(ws.answer_open(self.s, self.tid, 'main')['path'], 'pty')
        self.assertEqual((g.typed, c.typed), (['Acme'], ['main']))


# ── PW-229: every provider, every ending ───────────────────────────────────────────────────
class Providers(Base):
    def test_long_silence_of_a_working_run_raises_no_hand(self):
        a = live(self.tid); a.idle = lambda: 3600.0; a.tail = lambda n=3: ['> ']; term.SESSIONS['run1'] = a
        ws.record(self.s, self.tid, 'run1', 'working', source='hook')
        self.assertIs(ws.waiting_of(self.s, a), False); self.assertEqual(ws.status(self.s, self.tid)['state'], 'working')

    def test_repaint_noise_is_not_a_question(self):
        a = live(self.tid); a.tail = lambda n=3: ['Do you want to continue? (y/n)', '\x1b[2J> ']; term.SESSIONS['run1'] = a
        ws.record(self.s, self.tid, 'run1', 'working', source='hook')
        self.assertIs(ws.waiting_of(self.s, a), False, 'the run said working; the screen is repaint noise')

    def test_approval_allow_and_deny_are_both_answers(self):
        a = live(self.tid); a.send_prompt = lambda t: a.typed.append(t); term.SESSIONS['run1'] = a
        ws.record(self.s, self.tid, 'run1', 'approval_needed', request_id='p1', text='Delete the branch?', source='hook')
        self.assertTrue(ws.answer(self.s, self.tid, 'p1', 'no')['delivered'])
        self.assertEqual(ws.status(self.s, self.tid)['requests'], []); self.assertEqual(a.typed, ['no'])

    def test_response_end_without_completion_is_unknown(self):
        term.SESSIONS['run1'] = live(self.tid)
        ws.record(self.s, self.tid, 'run1', 'working', source='hook'); ws.record(self.s, self.tid, 'run1', 'turn_end', text='Looked around.', source='hook')
        self.assertEqual(ws.status(self.s, self.tid)['state'], 'unknown')

    def test_explicit_finish_is_finished_with_its_result(self):
        term.SESSIONS['run1'] = live(self.tid)
        ws.record(self.s, self.tid, 'run1', 'finished', text='Fixed and tested.', source='cli')
        self.assertEqual((ws.status(self.s, self.tid)['state'], ws.status(self.s, self.tid)['result']), ('finished', 'Fixed and tested.'))

    def test_an_error_or_interruption_is_never_completion(self):
        for kind in ('failed', 'disconnected', 'stopped'):
            tid = self.fx.task(title=kind, kind='coding'); term.SESSIONS[kind] = live(tid, kind)
            ws.record(self.s, tid, kind, 'working', source='hook'); ws.record(self.s, tid, kind, kind, text='boom', source='hook')
            self.assertEqual(ws.status(self.s, tid)['state'], kind); self.assertIsNone(ws.status(self.s, tid)['result'])

    def test_an_empty_workspace_has_no_status(self):
        term.SESSIONS['run1'] = live(self.tid)
        st = ws.status(self.s, self.tid)
        self.assertEqual((st['state'], st['requests'], st['result']), ('unknown', [], None))
        self.assertIsNone(ws.waiting_of(self.s, term.SESSIONS['run1']), 'never reported: the caller may fall back to the screen')

    def test_duplicate_and_stale_events_are_dropped(self):
        term.SESSIONS['run1'] = live(self.tid)
        self.assertTrue(ws.record(self.s, self.tid, 'run1', 'input_needed', text='Branch?', source='hook', event_id='e1'))
        self.assertFalse(ws.record(self.s, self.tid, 'run1', 'input_needed', text='Branch?', source='hook', event_id='e1'), 'replayed event id')
        self.assertFalse(ws.record(self.s, self.tid, 'run1', 'input_needed', text='Branch?', source='hook'), 'same open question')
        self.assertFalse(ws.record(self.s, self.tid, 'old', 'working', source='hook'), 'a run that is not the live one')
        self.assertEqual(len(ws.status(self.s, self.tid)['requests']), 1)

    def test_reconnection_replays_nothing(self):
        term.SESSIONS['run1'] = live(self.tid)
        for _ in range(3): ws.record(self.s, self.tid, 'run1', 'working', source='hook', event_id='boot-1')
        self.assertEqual(len(ws.events(self.s, self.tid)), 1)

    def test_one_hand_raise_per_request_in_the_pile(self):
        funnel.invalidate()
        req = {'request_id': 'q1', 'kind': 'input_needed', 'text': 'Which branch?', 'choices': []}
        state = [{'taskId': self.tid, 'sid': 'run1', 'agent': 'coder', 'started': '2026-09-06 12:00:00', 'waiting': True, 'request': req, 'tail': ['> ']},
                 {'taskId': self.tid, 'sid': 'run1', 'agent': 'coder', 'started': '2026-09-06 12:00:00', 'waiting': True, 'request': req, 'tail': ['> ']}]
        items = funnel.from_agents(self.s, live_state=state)
        self.assertEqual(len({i['key'] for i in items}), 1)


# ── PW-228: Working stays in Unread, not in the chat ───────────────────────────────────────
class Unread(Base):
    def test_a_working_run_is_no_blocked_row_and_no_chat_turn(self):
        funnel.invalidate()
        state = [{'taskId': self.tid, 'sid': 'run1', 'agent': 'coder', 'started': '2026-09-06 12:00:00', 'waiting': False, 'idle': 900, 'tail': ['> ']}]
        with mock.patch('taskuary.concierge.record') as rec:
            self.assertEqual(funnel.from_agents(self.s, live_state=state), [])
        self.assertFalse(rec.called)

    def test_a_request_is_promoted_with_its_text_and_a_finished_run_is_not_blocked_work(self):
        funnel.invalidate()
        asking = [{'taskId': self.tid, 'sid': 'run1', 'agent': 'coder', 'started': '2026-09-06 12:00:00', 'waiting': True,
                   'request': {'request_id': 'q1', 'kind': 'input_needed', 'text': 'Which branch?', 'choices': ['main']}, 'tail': ['> ']}]
        it = funnel.from_agents(self.s, live_state=asking)[0]
        self.assertEqual((it['lane'], it['asking']), ('blocked', True)); self.assertIn('Which branch?', it['why'])
        term.SESSIONS['run1'] = live(self.tid)
        ws.record(self.s, self.tid, 'run1', 'finished', text='Done: exports fixed.', source='cli')
        finished = [{'taskId': self.tid, 'sid': 'run1', 'agent': 'coder', 'started': '2026-09-06 12:00:00', 'waiting': False, 'tail': ['> ']}]
        self.assertEqual(funnel.from_agents(self.s, live_state=finished), [], 'a result is a result, not a raised hand')
        self.assertEqual(ws.status(self.s, self.tid)['result'], 'Done: exports fixed.')

    def test_the_same_event_is_announced_once(self):
        funnel.forget_states(); funnel.invalidate()
        with mock.patch.object(funnel, 'agent_states', return_value={self.tid: ('working', 'coder')}), mock.patch.object(funnel, 'DWELL', 0):
            funnel.announce(self.s)                                                   # the first look only remembers
            self.assertEqual(funnel.announce(self.s), [])
            with mock.patch.object(funnel, 'agent_states', return_value={self.tid: ('asking', 'coder')}):
                first = funnel.announce(self.s); again = funnel.announce(self.s)
        self.assertEqual(len(first), 1); self.assertEqual(again, [])

    def test_a_waiting_session_still_takes_a_desk(self):
        a = live(self.tid); term.SESSIONS['run1'] = a
        ws.record(self.s, self.tid, 'run1', 'approval_needed', text='Run it?', source='hook')
        self.assertEqual(bb.live_count(), 1)


# ── PW-234: explicit completion ────────────────────────────────────────────────────────────
class Completion(Base):
    def gates(self):
        return [mock.patch.object(selfclose, 'blocked', return_value=''), mock.patch.object(selfclose, 'stays_open', return_value=False),
                mock.patch.object(selfclose, 'mode', return_value='auto')]

    def test_save_before_close_a_failed_save_keeps_the_session_and_says_so(self):
        a = live(self.tid); term.SESSIONS['run1'] = a; selfclose.forget(self.tid)
        patches = self.gates() + [mock.patch.object(coder, 'wrap', side_effect=RuntimeError('disk full'))]
        for p in patches: p.start()
        try: out = selfclose.declare(self.s, self.tid, 'done', 'coder')
        finally:
            for p in patches: p.stop()
        self.assertFalse(out['closed']); self.assertTrue(a.alive)
        self.assertIn('could not', self.s.list_comments(self.tid)[-1]['Body']); self.assertEqual(self.s.get_task(self.tid)['Status'], 'open')
        self.assertEqual(selfclose.declare(self.s, self.tid, 'done', 'coder')['closed'], False, 'retryable: the mark was dropped')

    def test_duplicate_finish_signals_do_not_duplicate_the_finish(self):
        a = live(self.tid); term.SESSIONS['run1'] = a; selfclose.forget(self.tid)
        patches = self.gates() + [mock.patch.object(selfclose, '_wrap', return_value={'closed': True})]
        for p in patches: p.start()
        try: first, second = selfclose.declare(self.s, self.tid, 'done', 'coder'), selfclose.declare(self.s, self.tid, 'done', 'coder')
        finally:
            for p in patches: p.stop()
        self.assertTrue(first['closed']); self.assertFalse(second['closed'])
        self.assertEqual([e['Kind'] for e in ws.events(self.s, self.tid)].count('finished'), 1)

    def test_a_pending_approval_blocks_the_automatic_road(self):
        a = live(self.tid); a.started_ts = 0; a.n = 10_000; a.tail = lambda n=3: ['all done']; term.SESSIONS['run1'] = a; selfclose.forget(self.tid)
        ws.record(self.s, self.tid, 'run1', 'approval_needed', request_id='p1', text='Push to main?', source='hook')
        self.assertIn('approval', selfclose.blocked(self.s, self.tid, a).lower())

    def test_the_owner_stopping_a_run_is_stopped_not_finished(self):
        a = live(self.tid); term.SESSIONS['run1'] = a
        ws.record(self.s, self.tid, 'run1', 'working', source='hook'); ws.record(self.s, self.tid, 'run1', 'stopped', text='stopped by the owner', source='owner')
        self.assertEqual(ws.status(self.s, self.tid)['state'], 'stopped')

    def test_follow_up_context_is_retained_after_a_finish(self):
        self.s.add_comment(self.tid, 'coder', 'agent', 'CODER REPORT\nFixed the cron; the schedule was UTC.')
        seed = term.seed_text(self.s, self.tid, repo='org/exports', cwd=None)
        self.assertIn('PREVIOUS SESSION RESULT', seed); self.assertIn('schedule was UTC', seed)


class Routes(Base):
    def test_the_status_route_reports_requests_after_a_restart(self):
        ws.record(self.s, self.tid, 'run1', 'input_needed', request_id='q1', text='Branch?', source='hook')
        with mock.patch.object(server, 'store', self.s):
            st = TestClient(server.app).get(f'/api/tasks/{self.tid}/worker').json()
        self.assertEqual((st['state'], st['requests'][0]['request_id'], st['live']), ('input_needed', 'q1', False))
