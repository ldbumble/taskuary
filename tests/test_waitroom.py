"""The waiting room (waitroom.py): notes the owner queues on a task while its agent works, typed
in as one batch when the agent parks - held while it is working, delivered as the ANSWER when it is asking, and
reopening a session when the old one ended. All faked: no pty, no CLI.
"""
import time, unittest
from unittest import mock

from taskuary import terminal, waitroom
from taskuary.store import MemoryStore
from taskuary.testing import Factory


class FakeTerm:
    """Just enough of terminal.Term: a task, a pulse, a screen."""
    def __init__(self, tid, idle=0.0, tail=()): self.task_id, self.alive, self._idle, self._tail, self.n, self.writes = tid, True, idle, list(tail), 0, []
    def idle(self): return self._idle
    def tail(self, n=3): return self._tail[-n:]
    def write(self, x): self.writes.append(x); self.n += 1
    def info(self, tail=0): return {'sid': 'fake', 'taskId': self.task_id, 'alive': True, 'idle': self._idle, 'files': []}
    def typed(self): return ''.join(w for w in self.writes if w not in ('\r', '\n'))


def task(s, status='in_progress'): return Factory(s).task(title='PTO import', kind='coding', status=status)


class PhaseTests(unittest.TestCase):
    """Working vs parked is read off the CLI's own screen; silence is only the fallback. The
    Board flapped between lanes because Claude Code repaints its footer at rest, resetting the
    idle clock every time."""
    def test_claude_code_footer_says_parked_even_when_it_just_repainted(self):
        tail = ['  I updated the three files and the tests pass.', '', '⏵⏵ auto mode on (shift+tab to cycle) · ? for shortcuts']
        self.assertEqual(terminal.phase_of(tail), 'parked')
        t = FakeTerm(1, idle=0.5, tail=tail)                       # printed half a second ago - and still parked
        t.phase = lambda: terminal.phase_of(t.tail(4)); t.waiting = lambda: t.phase() == 'parked' or (t.phase() != 'working' and t.idle() >= terminal.IDLE_WAITING)
        self.assertTrue(t.waiting())

    def test_esc_to_interrupt_says_working_however_long_the_silence(self):
        tail = ['⠹ Thinking… (esc to interrupt)']
        self.assertEqual(terminal.phase_of(tail), 'working')
        t = FakeTerm(1, idle=terminal.IDLE_WAITING + 60, tail=tail)
        t.phase = lambda: terminal.phase_of(t.tail(4)); t.waiting = lambda: t.phase() == 'parked' or (t.phase() != 'working' and t.idle() >= terminal.IDLE_WAITING)
        self.assertFalse(t.waiting())                               # a long test run is not a question

    def test_the_newest_line_wins_over_an_older_frame(self):
        self.assertEqual(terminal.phase_of(['Running tests… (esc to interrupt)', '? for shortcuts']), 'parked')
        self.assertEqual(terminal.phase_of(['? for shortcuts', 'Editing foo.py (esc to interrupt)']), 'working')

    def test_permission_and_choice_prompts_are_parked_without_waiting_for_idle(self):
        for tail in (['Do you want to allow this command?', '❯ 1. Yes', '  2. No'], ['❯ 1. Yes', '  2. No'],
                     ['Press enter to confirm'], ['Yes, I trust this folder', 'Enter to confirm · Esc to cancel']):
            self.assertEqual(terminal.phase_of(tail), 'parked', tail)

    def test_what_the_agent_wrote_decides_nothing(self):
        """Only the CLI's own chrome is read (the owner, 2026-10-11: "everything should be ai"). A turn that ended on a
        question, or a report that closed on a rhetorical one, is left to the clock and to the model's read of the turn."""
        for tail in (['Should I also update the tests?'], ['Overwrite config.toml (y/n)'], ['Which of these files is the right one?'],
                     ['Done. Why did it fail before? The cron ran as the wrong user.'], ['Do you want me to look at the export too?']):
            self.assertEqual(terminal.phase_of(tail), 'unknown', tail)

    def test_an_unknown_screen_falls_back_to_the_clock(self):
        self.assertEqual(terminal.phase_of(['$ make test', 'ok 12 tests']), 'unknown')
        self.assertEqual(terminal.phase_of([]), 'unknown')

    def test_the_waiting_room_reads_the_screen_too(self):
        s = MemoryStore(); tid = task(s)
        t = FakeTerm(tid, idle=1, tail=['Done.', '? for shortcuts'])         # parked, freshly repainted
        t.waiting = lambda: True
        with mock.patch.dict(terminal.SESSIONS, {'a': t}, clear=True):
            self.assertEqual(waitroom.state(s, tid)[0], 'parked')
            t.waiting = lambda: False                                         # working, however quiet
            t._idle = terminal.IDLE_WAITING + 30
            self.assertEqual(waitroom.state(s, tid)[0], 'working')

    def test_a_partial_repaint_cannot_publish_a_stop(self):
        """The rendered screen can briefly contain the bare prompt between two working frames.
        One observation must never put the task in waiting-on-me or ring the hand raise."""
        t = FakeTerm(1, idle=60, tail=['? for shortcuts'])
        t.status_tail = lambda n=8: t._tail[-n:]
        at = 100.0
        self.assertEqual(terminal.stable_phase_of(t, at), 'working')
        self.assertEqual(terminal.stable_phase_of(t, at + terminal.PHASE_DWELL - .1), 'working')
        t._tail = ['Gallivanting… · thinking with high effort', 'esc to interrupt · for agents']
        self.assertEqual(terminal.stable_phase_of(t, at + terminal.PHASE_DWELL + .1), 'working')
        self.assertIsNone(t._phase_candidate)

    def test_a_pane_launched_on_its_prompt_is_at_work_until_its_cli_shows_its_first_turn(self):
        """The recorded flood on a terminal agent, 2026-11-11: its prompt rode the command line, the CLI took a minute to come up with the bare
        prompt on screen, and the waiting room typed thirty lines and notes into it before its first turn - none reached the agent."""
        t = FakeTerm(1, idle=60, tail=['? for shortcuts'])
        t.status_tail = lambda n=8: t._tail[-n:]
        at = 500.0; t.launching = at
        for dt in (0, terminal.PHASE_DWELL + 1, 60): self.assertEqual(terminal.stable_phase_of(t, at + dt), 'working')       # coming up: never parked
        t._tail = ['Reading totals.py', 'esc to interrupt · for agents']
        self.assertEqual(terminal.stable_phase_of(t, at + 61), 'working'); self.assertFalse(t.launching)                     # its first turn: from here the screen says
        t._tail = ['Done.', '? for shortcuts']
        terminal.stable_phase_of(t, at + 70); self.assertEqual(terminal.stable_phase_of(t, at + 71 + terminal.PHASE_DWELL), 'parked')
        # ...its first hook event says the same (a CLI whose screen is not read): its prompt was taken
        from taskuary import hooks
        h = FakeTerm(1, idle=60, tail=['? for shortcuts']); h.launching, h.store, h.sid, h.bg = at, MemoryStore(), 'run1', {}
        hooks._events(h, {'hook_event_name': 'UserPromptSubmit', 'prompt': 'look at the totals'}); self.assertFalse(h.launching)
        # ...and a CLI whose working screen is never recognised is not held for good
        u = FakeTerm(1, idle=60, tail=['? for shortcuts']); u.status_tail = lambda n=8: u._tail[-n:]; u.launching = at
        terminal.stable_phase_of(u, at + terminal.LAUNCH_WAIT + 1)
        self.assertEqual(terminal.stable_phase_of(u, at + terminal.LAUNCH_WAIT + 2 + terminal.PHASE_DWELL), 'parked')

    def test_a_real_prompt_has_to_hold_then_publishes_once(self):
        t = FakeTerm(1, idle=60, tail=['Done. Tests pass.', '? for shortcuts'])
        t.status_tail = lambda n=8: t._tail[-n:]
        at = 200.0
        self.assertEqual(terminal.stable_phase_of(t, at), 'working')
        self.assertEqual(terminal.stable_phase_of(t, at + terminal.PHASE_DWELL + .1), 'parked')
        self.assertEqual(terminal.stable_phase_of(t, at + terminal.PHASE_DWELL + .2), 'parked')

    def test_lifecycle_reads_the_rendered_screen_not_raw_repaint_fragments(self):
        t = FakeTerm(1, idle=90, tail=['? for shortcuts'])
        t.status_tail = lambda n=8: ['Gallivanting… · thinking with high effort',
                                     'bypass permissions on · esc to interrupt · for agents']
        self.assertEqual(terminal.stable_phase_of(t, 300.0), 'working')


class QuestionTests(unittest.TestCase):
    """A chooser on screen is the CLI's own chrome - its key hints, its cursor on a numbered option. A question mark in
    the agent's prose is not (2026-10-11): `looks_like_question` and its word list are gone."""
    def test_a_chooser_the_cli_draws_is_a_question(self):
        for tail in (['Do you want to proceed?', '❯ 1. Yes', '  2. No'], ['Pick one', '↑↓ to select · enter to confirm'],
                     ['› 1. Yes, proceed (y)', '  2. No, and tell Codex what to do differently']):
            self.assertTrue(terminal.chooser_in(tail), tail)

    def test_a_question_in_prose_is_not(self):
        for tail in (['Should I also update the tests?'], ['Overwrite config.toml (y/n)'], ['Which of these files is the right one?'],
                     ['Done. Tests pass (12 passed).', 'Committed as 3f1a2c.'], ['I wondered whether x? No - it is y.', 'Finished.'], [],
                     ['Plan:', '1. Read the export', '2. Fix it']):
            self.assertFalse(terminal.chooser_in(tail), tail)
        self.assertFalse(hasattr(waitroom, 'looks_like_question'))

    def test_a_report_ending_in_a_rhetorical_question_is_parked_not_asking(self):
        s = MemoryStore(); tid = task(s)
        t = FakeTerm(tid, idle=terminal.IDLE_WAITING + 5, tail=['Fixed the export. Why did it break? The cron ran as the wrong user.'])
        t.sid = 'fake'
        with mock.patch.dict(terminal.SESSIONS, {'a': t}, clear=True):
            self.assertEqual(waitroom.state(s, tid)[0], 'parked')


class ChooserTests(unittest.TestCase):
    """A parked pane showing a chooser is ASKING, and only the owner answers it (2026-09-20: a
    queued note typed into Claude's trust dialog chose "No, exit" and respawned the session in a loop)."""
    def test_a_chooser_only_the_rendered_screen_shows_is_a_question(self):
        s = MemoryStore(); tid = task(s)
        t = FakeTerm(tid, idle=60, tail=['? for shortcuts'])                 # the raw stream: an older frame
        t.status_tail = lambda n=8: ['Yes, I trust this folder', 'Enter to confirm · Esc to cancel']
        t.waiting = lambda: True
        with mock.patch.dict(terminal.SESSIONS, {'a': t}, clear=True):
            self.assertEqual(waitroom.state(s, tid)[0], 'asking')

    def test_the_runs_own_open_request_is_a_question_whatever_the_screen_says(self):
        from taskuary import workerstate as ws
        s = MemoryStore(); tid = task(s)
        t = FakeTerm(tid, idle=60, tail=['Done.', '? for shortcuts']); t.sid = 'fake'; t.waiting = lambda: True
        with mock.patch.dict(terminal.SESSIONS, {'a': t}, clear=True):
            self.assertEqual(waitroom.state(s, tid)[0], 'parked')
            ws.record(s, tid, 'fake', 'input_needed', text='alpha or beta?', choices=['alpha', 'beta'], source='hook')
            self.assertEqual(waitroom.state(s, tid)[0], 'asking')


class DeliveryTests(unittest.TestCase):
    def test_held_while_the_agent_works_then_typed_as_one_batch_in_order(self):
        s = MemoryStore(); tid = task(s)
        s.set_setting('waitroom_drip', '0', 't')                     # the batch mode: everything at once
        t = FakeTerm(tid, idle=2)
        with mock.patch.dict(terminal.SESSIONS, {'a': t}, clear=True):
            r1 = waitroom.add(s, tid, 'also handle the null case', 'owner')
            r2 = waitroom.add(s, tid, 'rename the flag to --dry-run')
            self.assertEqual((r1['delivered'], r1['state'], r2['state']), (0, 'working', 'working'))
            self.assertEqual(len(s.waiting_notes(tid)), 2); self.assertEqual(t.writes, [])
            t._idle = terminal.IDLE_WAITING + 1                      # it parked at its prompt
            out = waitroom.tick(s)
            time.sleep(0.5)
        self.assertEqual(out, 2)
        typed = t.typed()
        self.assertIn('(1) also handle the null case', typed); self.assertIn('(2) rename the flag', typed)
        self.assertLess(typed.index('(1)'), typed.index('(2)'))
        self.assertIn('after finishing the step you are on', typed)
        self.assertEqual(s.waiting_notes(tid), [])
        self.assertEqual({w['How'] for w in s.waitroom(tid)}, {'typed'})
        self.assertTrue(any('waiting-room' in c['Body'] for c in s.list_comments(tid)))

    def test_a_full_session_on_a_task_a_stranger_wrote_on_since_gets_nothing_typed(self):
        """A STRANGER'S WORDS NEVER REACH FULL TOOLS UNASKED (the Advisor design rev 2): a batch's later outside item, or a new sender, made
        the task a stranger's after its session started full - nothing is typed in, and the task says why and the way on."""
        from taskuary import origin
        s = MemoryStore(); tid = task(s)
        t = FakeTerm(tid, idle=terminal.IDLE_WAITING + 5, tail=['Done - all tests pass.'])
        with mock.patch.dict(terminal.SESSIONS, {'a': t}, clear=True), mock.patch.object(origin, 'of_task', return_value=('stranger', 'a new sender')):
            out = waitroom.add(s, tid, 'NEW ITEMS JOINED THIS BATCH: (3) outside pull request')
            waitroom.deliver(s, tid)
            time.sleep(0.3)
            self.assertEqual((out['delivered'], out['state']), (0, 'held_stranger'))
            self.assertEqual(t.writes, []); self.assertEqual(len(s.waiting_notes(tid)), 1, 'it keeps its place')
            self.assertEqual(sum(c['Body'] == waitroom.HELD_STRANGER for c in s.list_comments(tid)), 1, 'said once')
            t.mode = 'auto'                                       # ...the owner's Continue relaunched it under the reviewer
            self.assertEqual(waitroom.deliver(s, tid)['state'], 'parked')

    def test_a_parked_agent_gets_the_note_at_once(self):
        s = MemoryStore(); tid = task(s)
        t = FakeTerm(tid, idle=terminal.IDLE_WAITING + 5, tail=['Done - all tests pass.'])
        with mock.patch.dict(terminal.SESSIONS, {'a': t}, clear=True):
            out = waitroom.add(s, tid, 'now do the same for the export path')
            time.sleep(0.5)
        self.assertEqual((out['delivered'], out['state']), (1, 'parked'))
        self.assertIn('export path', t.typed())
        # ...and it was not working (agent walk 2, 2026-11-10: "While you were working, the owner queued 1 note ... after finishing the step
        # you are on", to an agent at rest). The chat still reads the typed line as Taskuary's head and the owner's words (sessionrecord.queued)
        self.assertNotIn('While you were working', t.typed()); self.assertNotIn('the step you are on', t.typed())
        from taskuary import sessionrecord
        self.assertEqual(sessionrecord.queued(t.typed()), [('brief', 'The owner left 1 note for you. Take them in order:'),
                                                           ('you', 'now do the same for the export path')])

    def test_a_question_for_the_owner_is_answered_by_what_they_write_next(self):
        """An agent parked on a question is asking the OWNER: their next words are the answer and go
        in at once, plainly - no "while you were working" preamble. They used to queue behind the
        question and never arrive, while the card said "Told the agent" (2026-09-07 live check). The
        question is one the agent ASKED (its tool, its marker) - never a "?" on the tail, and no model's read of its prose."""
        from taskuary import workerstate as ws
        s = MemoryStore(); tid = task(s)
        said = 'Two repos match. Which one should I use?'
        t = FakeTerm(tid, idle=terminal.IDLE_WAITING + 5, tail=[said]); t.sid = 'fake'
        with mock.patch.dict(terminal.SESSIONS, {'a': t}, clear=True):
            self.assertEqual(waitroom.state(s, tid)[0], 'parked')                     # the words alone ask nothing
            ws.record(s, tid, 'fake', 'turn_end', text=said, source='hook')
            ws.record(s, tid, 'fake', 'input_needed', request_id=ws.request_id_for('Which repo should I use?'), text='Which repo should I use?', source='hook')
            self.assertEqual(waitroom.state(s, tid)[0], 'asking')
            out = waitroom.add(s, tid, 'use the 8/17 file')
            self.assertEqual((out['delivered'], out['state']), (1, 'answered'))
            time.sleep(0.5)
        self.assertEqual(t.typed(), 'use the 8/17 file')               # the answer itself, nothing wrapped round it
        self.assertEqual(s.waiting_notes(tid), [])
        self.assertIn('Answered "Which repo should I use?"', ' '.join(c['Body'] for c in s.list_comments(tid)))   # bound to the request

    def test_no_session_reopens_one_with_the_notes_as_the_ask(self):
        s = MemoryStore(); tid = task(s)
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(terminal, 'start_on_task', return_value={'sid': 'new'}) as start:
            out = waitroom.add(s, tid, 'also fix the header row')
        self.assertEqual((out['delivered'], out['state']), (1, 'restarted'))
        self.assertEqual(start.call_args[0][1], tid)
        self.assertIn('(1) also fix the header row', start.call_args[1]['instruction'])
        self.assertIn('after the last session ended', start.call_args[1]['instruction'])
        self.assertEqual({w['How'] for w in s.waitroom(tid)}, {'seeded'})

    def test_reopen_keeps_the_previous_coder_and_checkout(self):
        import os
        s = MemoryStore(); tid = task(s)
        s.add_transcript(tid, 'old', 'worked here', 'codex-specialist', os.getcwd())
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(terminal, 'start_on_task', return_value={'sid': 'new'}) as start:
            out = waitroom.add(s, tid, 'make the implementation changes')
        self.assertEqual((out['delivered'], out['state']), (1, 'restarted'))
        self.assertEqual(start.call_args.args[:3], (s, tid, 'codex-specialist'))
        self.assertEqual(start.call_args.kwargs['cwd'], os.getcwd())

    def test_a_closed_task_holds_and_a_full_house_waits(self):
        s = MemoryStore(); done = task(s, 'done'); open_ = task(s, 'open')
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(terminal, 'start_on_task') as start:
            self.assertEqual(waitroom.add(s, done, 'x')['state'], 'closed')
            s.set_setting('auto_sessions', '1', 't')
            with mock.patch.dict(terminal.SESSIONS, {'b': FakeTerm(999, idle=1)}, clear=True):
                self.assertEqual(waitroom.add(s, open_, 'y')['state'], 'full')
            start.assert_not_called()
        self.assertEqual(len(s.waiting_notes(open_)), 1)                # still waiting - the clock retries

    def test_withdraw_before_delivery_only(self):
        s = MemoryStore(); tid = task(s)
        with mock.patch.dict(terminal.SESSIONS, {'a': FakeTerm(tid, idle=1)}, clear=True):
            wid = waitroom.add(s, tid, 'scratch that')['wid']
        s.drop_waiting(wid, tid); self.assertEqual(s.waiting_notes(tid), [])
        wid2 = s.add_waiting(tid, 'kept', 'owner'); s.deliver_waiting([wid2], 'typed')
        s.drop_waiting(wid2, tid); self.assertEqual(len(s.waitroom(tid)), 1)

    def test_empty_note_and_unknown_task_are_refused(self):
        s = MemoryStore(); tid = task(s)
        with self.assertRaises(ValueError): waitroom.add(s, tid, '   ')
        with self.assertRaises(ValueError): waitroom.add(s, 9999, 'x')


class GeneralTests(unittest.TestCase):
    """A general agent's chat says who said what (the overnight run, 2026-11-03): the batch was typed into its conversation and filed
    whole as the owner's, so YOU read "While you were working, the owner queued 1 note for you..." - Taskuary's words in the owner's bubble."""
    def general(self, s):
        from taskuary import general
        tid = Factory(s).task(title='Vendor list', kind='general', status='in_progress')
        ses = general.GeneralSession.__new__(general.GeneralSession)
        ses.task_id, ses.alive, ses.sent, ses.sid, ses.buf = tid, True, [], 'g', ''
        ses.waiting = lambda: True
        ses.send_prompt = lambda text, **kw: ses.sent.append((text, kw))
        return tid, ses

    def said(self, s, tid):
        from taskuary import general
        return [('taskuary' if general.is_brief(c) else c['Actor'], c['Body']) for c in s.list_comments(tid, internal=True) if c['ActorType'] == general.USER_TYPE]

    def test_a_parked_general_agent_files_the_note_as_the_owners_and_the_rest_as_taskuarys(self):
        s = MemoryStore(); tid, ses = self.general(s)
        with mock.patch.dict(terminal.SESSIONS, {'g': ses}, clear=True):
            out = waitroom.add(s, tid, 'Also put Northwind Payroll on the list.')
            time.sleep(0.3)
        self.assertEqual((out['delivered'], out['state']), (1, 'parked'))
        # ...his line alone: the head round it is the agent's, typed with it - filed, it drew on his screen as a line saying nothing
        self.assertEqual(self.said(s, tid), [('owner', 'Also put Northwind Payroll on the list.')])
        [(turn, kw)] = ses.sent                                     # the agent's turn is the batch, filed here already
        self.assertIn('The owner left 1 note for you', turn); self.assertNotIn('While you were working', turn)
        self.assertIn('(1) Also put Northwind Payroll on the list.', turn); self.assertEqual(kw, {'kept': True, 'brief': True})

    def test_taskuarys_word_to_a_parked_agent_leaves_no_head_on_the_owners_screen(self):
        """The overnight audit, 2026-11-10: he pressed Approve on a playbook the agent set up; its card left the chat and a grey line "Taskuary
        left 1 note for you. Take them in order:" stood in its place - the head the agent's own words were typed under."""
        from taskuary import general
        s = MemoryStore(); tid, ses = self.general(s)
        said = general.APPROVED.format(press='Approve', what='saved the playbook vendor-review') + 'Say what you did and what comes next.'
        with mock.patch.dict(terminal.SESSIONS, {'g': ses}, clear=True):
            waitroom.add(s, tid, said, 'router'); time.sleep(0.3)
        self.assertEqual(self.said(s, tid), [('taskuary', said)], "the word itself, kept as Taskuary's for the record - and nothing else")
        self.assertIn('Taskuary left 1 note for you', ses.sent[0][0])

    def test_an_ended_general_agent_reopens_with_the_same_split(self):
        from taskuary import general
        s = MemoryStore(); tid, ses = self.general(s)
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude'}]), \
             mock.patch.object(general, 'start_session', return_value=ses):
            out = waitroom.add(s, tid, 'and sort it')
            time.sleep(0.3)
        self.assertEqual(out['state'], 'restarted')
        self.assertEqual([w for w, _ in self.said(s, tid)], ['owner'])
        self.assertIn('after the last session ended', ses.sent[0][0])

class DripTests(unittest.TestCase):
    def test_a_pasted_list_becomes_notes_in_order_and_drips_one_per_stop(self):
        s = MemoryStore(); tid = task(s)
        t = FakeTerm(tid, idle=terminal.IDLE_WAITING + 5, tail=['Done.'])
        with mock.patch.dict(terminal.SESSIONS, {'a': t}, clear=True):
            out = waitroom.add_many(s, tid, '1. add the null check\n2) rename the flag\n- write the test\n\n   for the edge case\n')
            time.sleep(0.4)
            self.assertEqual((out['queued'], out['delivered'], out['left']), (3, 1, 2))
            typed = t.typed()
            self.assertIn('(1) add the null check', typed); self.assertNotIn('rename the flag', typed)
            self.assertIn('2 more notes wait behind this one', typed)               # told, so it does not go looking
            self.assertEqual([w['Note'] for w in s.waiting_notes(tid)], ['rename the flag', 'write the test for the edge case'])
            t.writes.clear(); t._idle = 3
            self.assertEqual(waitroom.tick(s), 0)                                   # working again: the rest wait
            t._idle = terminal.IDLE_WAITING + 5
            self.assertEqual(waitroom.tick(s), 1); time.sleep(0.4)                  # next stop: exactly one more
            self.assertIn('(1) rename the flag', t.typed()); self.assertIn('1 more note waits', t.typed())
            self.assertEqual(len(s.waiting_notes(tid)), 1)

    def test_what_taskuary_tells_a_working_agent_goes_in_together_and_its_shared_closing_is_said_once(self):
        """The recorded flood, 2026-11-11: thirty messages came in on a coding task while its agent worked, each a note of Taskuary's with the
        same closing instructions - dripped one per stop they were thirty turns, and the agent said the same sentence thirty times."""
        from taskuary import ingest
        s = MemoryStore(); tid = task(s)
        t = FakeTerm(tid, idle=3, tail=['Working...'])
        said = [ingest.replan_turn({'body': f'flood {i} of 9', 'from_name': 'Gail Moreno', 'from_email': 'gail@northwind.example', 'channel': 'email'}) for i in range(1, 10)]
        with mock.patch.dict(terminal.SESSIONS, {'a': t}, clear=True):
            for x in said: waitroom.add(s, tid, x, 'router')
            waitroom.add(s, tid, 'and rename the flag')                                       # ...his own queued note keeps its drip
            self.assertEqual(len(s.waiting_notes(tid)), 10); self.assertEqual(t.typed(), '')   # working: all of it waits
            t._idle = terminal.IDLE_WAITING + 5
            self.assertEqual(waitroom.tick(s), 9); time.sleep(0.4)
            typed = t.typed()
            for i in range(1, 10): self.assertEqual(typed.count(f'flood {i} of 9'), 1)
            self.assertEqual(typed.count(' '.join(ingest.REPLAN.split())[:200]), 1)
            self.assertEqual([w['Note'] for w in s.waiting_notes(tid)], ['and rename the flag'])
            # ...and more than one message holds waits whole for the next stop: never cut
            big = [x for x in ({'WId': i, 'CreatedBy': 'router', 'Note': f'{"word " * 300}{i}\n\n{ingest.REPLAN}'} for i in range(9))]
            fit = waitroom.together([], big)
            self.assertEqual(len(waitroom.together([{'Note': 'and the tax line?', 'CreatedBy': 'owner', 'line': 7}], big)), len(fit))      # ...behind a line he typed, too
            self.assertTrue(0 < len(fit) < 9); self.assertLessEqual(len(waitroom.batch(fit, remaining=9 - len(fit))), waitroom.MAX_BATCH - 1)

    def test_split_many_strips_bullets_and_joins_continuations(self):
        self.assertEqual(waitroom.split_many('• one\n* two\n3. three\n  still three\n\nfour'), ['one', 'two', 'three still three', 'four'])
        self.assertEqual(waitroom.split_many('  \n'), [])

    def test_bulk_endpoint(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore(); tid = task(s)
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {'a': FakeTerm(tid, idle=1)}, clear=True):
            c = TestClient(server.app)
            self.assertEqual(c.post(f'/api/tasks/{tid}/waitroom/bulk', json={'text': 'a\nb\nc'}).json()['queued'], 3)
            self.assertEqual(c.post(f'/api/tasks/{tid}/waitroom/bulk', json={'text': '  '}).status_code, 422)
            self.assertEqual(c.get('/api/tasks').json()['data'][0]['Waiting'], 3)


CLAUDE_BOX = '\r\n'.join(['Done - the export path is fixed.', '', '─' * 60, '❯ {}', '─' * 60, '  ⏵⏵ bypass permissions on (shift+tab to cycle)'])
CODEX_BOX = '\r\n'.join(['• Updated the import.', '', '› {}', '', '  ⏎ send   ⌃J newline   ⌃T transcript'])


class ScreenTerm(FakeTerm):
    """A parked session with a rendered screen and the owner's own keys (Term.keyed)."""
    def __init__(self, tid, box=CLAUDE_BOX, text=''):
        super().__init__(tid, idle=terminal.IDLE_WAITING + 5, tail=['Done.'])
        self.cols, self.rows, self.box, self.draft, self.keyed_at = 110, 32, box, '', 0.
        self.show(text)
    def show(self, text): self.screen = self.box.format(text)
    def scrollback(self): return self.screen
    def keyed(self, s): terminal.Term.keyed(self, s)


class OwnerTypingTests(unittest.TestCase):
    """2026-11-02: the owner typed in the box while the agent worked; it stopped, and a queued note went in mid-sentence -
    "also if you cl" + the note + "ick" arrived as one garbled prompt."""
    def test_the_keys_are_replayed_as_the_line_the_owner_has_not_sent(self):
        t = ScreenTerm(1)
        t.keyed('also if you clx\x7f'); self.assertEqual(t.draft, 'also if you cl')
        t.keyed('\x1b[D\x1b[C'); self.assertEqual(t.draft, 'also if you cl', 'arrows change no letters')
        t.keyed('\x1b[200~two\r\nlines\x1b[201~'); self.assertEqual(t.draft, 'also if you cltwo lines', 'a pasted newline is not Enter')
        t.keyed('\r'); self.assertEqual(t.draft, '', 'Enter sent it')
        t.keyed('abc\x15'); self.assertEqual(t.draft, '', '^U cleared it')

    def test_the_box_is_read_off_the_screen_for_claude_and_codex(self):
        for box in (CLAUDE_BOX, CODEX_BOX):
            self.assertEqual(terminal.box_text(ScreenTerm(1, box, 'also if you cl')), 'also if you cl')
            self.assertEqual(terminal.box_text(ScreenTerm(1, box)), '')
        self.assertIsNone(terminal.box_text(FakeTerm(1)), 'no screen to read')

    def test_drafting_needs_the_owners_keys_and_the_screen_to_agree(self):
        t = ScreenTerm(1, text='Try "fix the lint errors"')
        self.assertFalse(terminal.owner_drafting(t), "a CLI's placeholder is not the owner typing")
        t.keyed('also if you cl'); t.show('also if you cl')
        self.assertTrue(terminal.owner_drafting(t))
        t.show(''); self.assertFalse(terminal.owner_drafting(t), 'the box is empty - sent or cleared')
        t.show('Try "fix the lint errors"'); t.keyed_at = time.time() - terminal.DRAFT_FRESH - 1
        self.assertFalse(terminal.owner_drafting(t), 'cleared some way the keys did not show, long ago: not held forever')

    def test_a_note_waits_while_the_owner_types_and_goes_in_once_they_send(self):
        s = MemoryStore(); tid = task(s)
        t = ScreenTerm(tid)
        t.keyed('also if you cl'); t.show('also if you cl')
        with mock.patch.dict(terminal.SESSIONS, {'a': t}, clear=True):
            out = waitroom.add(s, tid, 'Erin wrote again: the download goes to the local computer', 'router')
            for _ in range(3): self.assertEqual(waitroom.tick(s), 0)
            time.sleep(0.3)
            self.assertEqual((out['delivered'], out['state']), (0, 'owner_typing'))
            self.assertEqual(t.writes, [], 'nothing typed into the half-written line')
            self.assertEqual(len(s.waiting_notes(tid)), 1, 'it keeps its place')
            t.keyed('ick\r'); t.show('')                          # the owner sent their own line
            self.assertEqual(waitroom.tick(s), 1)
            time.sleep(0.5)
        self.assertIn('Erin wrote again', t.typed()); self.assertNotIn('also if you', t.typed())

    def test_a_relayed_message_to_a_parked_agent_waits_while_the_owner_types(self):
        s = MemoryStore(); tid = task(s)
        t = ScreenTerm(tid)
        t.keyed('also if you cl'); t.show('also if you cl')
        with mock.patch.dict(terminal.SESSIONS, {'a': t}, clear=True):
            self.assertTrue(terminal.say_to_task(s, tid, {'FromName': 'Erin Blake', 'Channel': 'whatsapp', 'BodyText': 'use the shared folder'}, new=True))
            time.sleep(0.3)
            self.assertEqual(t.writes, [])
            self.assertEqual([n['Note'][:22] for n in s.waiting_notes(tid)], ['Erin Blake wrote again'])
            self.assertTrue(any('until you send what you are typing' in c['Body'] for c in s.list_comments(tid)))


class ApiTests(unittest.TestCase):
    def test_round_trip(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore(); tid = task(s)
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {'a': FakeTerm(tid, idle=1)}, clear=True):
            c = TestClient(server.app)
            self.assertEqual(c.post(f'/api/tasks/{tid}/waitroom', json={'text': ''}).status_code, 422)
            r = c.post(f'/api/tasks/{tid}/waitroom', json={'text': 'check the other repo too'}).json()
            self.assertEqual(r['state'], 'working')
            got = c.get(f'/api/tasks/{tid}/waitroom').json()
            self.assertEqual((len(got['data']), got['state']), (1, 'working'))
            self.assertEqual(c.get('/api/tasks').json()['data'][0]['Waiting'], 1)
            c.delete(f"/api/tasks/{tid}/waitroom/{r['wid']}")
            self.assertEqual(c.get('/api/tasks').json()['data'][0]['Waiting'], 0)
            self.assertEqual(c.get('/api/tasks/9999/waitroom').status_code, 404)

    def test_live_runs_say_when_a_parked_agent_is_asking(self):
        """The hand-raise notification reads this: a session quiet past IDLE_WAITING whose own reading
        is 'asking' (terminal.worker_fields) is asking; one still printing is neither, and the words on
        the tail alone never are (2026-10-11)."""
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore(); tid = task(s)
        asking = FakeTerm(tid, idle=terminal.IDLE_WAITING + 3, tail=['Which repo should I use?'])
        asking.cwd, asking.agent, asking.label, asking.started, asking.sid = 'x', 'coding', 'coding', '', 'a'
        state = {'state': None}
        def info(tail=0): return {'sid': 'a', 'taskId': tid, 'alive': True, 'idle': asking._idle, 'files': [], 'agent': 'coding', 'label': 'coding',
                                  'started': '', 'tail': asking.tail(tail), **state}
        asking.info = info
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {'a': asking}, clear=True):
            rows = TestClient(server.app).get('/api/runs/live').json()['data']
            self.assertEqual((rows[0]['asking'], rows[0]['state']), (False, 'parked'))             # a "?" on the tail is not a question
            state['state'] = 'asking'
            rows = TestClient(server.app).get('/api/runs/live').json()['data']
            self.assertEqual((rows[0]['asking'], rows[0]['Title']), (True, 'PTO import'))
            asking._idle = 2
            self.assertFalse(TestClient(server.app).get('/api/runs/live').json()['data'][0]['asking'])


if __name__ == '__main__': unittest.main()
