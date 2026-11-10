"""A chat agent nobody has spoken to for a while closes QUIETLY, and the next input brings it back (the owner, 2026-11-05: "if there is no
action on a agent for a while instead of keeping it open forever it should just shut down keeping the chat same ui, and then you type in
something or new input comes in it can restart in backend").

The shape: a mail came in, the agent answered with a draft, and nobody touched the task for longer than a live CLI is kept open
(clipool.IDLE_SECONDS). The session closes with no report, no learning, no draft touched, no line in the chat and the task as it was.
Then the owner types a correction, or the sender writes again, and the same run picks the saved conversation back up.
"""
import json, threading, time, unittest
from unittest import mock

from taskuary import clipool, continuity, general, ingest, llm as llm_mod, senders, terminal, workerstate as ws
from taskuary.store import MemoryStore


class Brain:
    "The model on Claude Code: keeps what each turn was handed, and the conversation id its CLI gave it."
    session_id = 'cli-conv-1'
    def __init__(self, delay=0.0): self.calls, self.delay = [], delay
    def __call__(self, system, user, **k): time.sleep(self.delay); self.calls.append(user); return 'Here is the plan for the pilot.'


def store():
    s = MemoryStore()
    s.set_setting('owner_email', 'alex@northwind.example', 't')
    s.upsert_agent('claude', 'general', 'cli', json.dumps({'cmd': 'claude'}))
    return s


def chat(s, tid): return [(c['ActorType'], c['Body']) for c in general.chat_rows(s, tid)]


class IdleOut(unittest.TestCase):
    def setUp(self):
        self.brain, self.built = Brain(), []
        def build(*a, **k): self.built.append(k); return self.brain
        for p in [mock.patch.object(llm_mod, 'build_llm', side_effect=build),
                  mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli', 'label': 'Claude Code', 'model': ''}]),
                  mock.patch('taskuary.agents.ready_brains', return_value=['claude']),
                  mock.patch.object(continuity, 'can_resume', return_value=True),
                  mock.patch('taskuary.hooks.judge_ended', lambda *a, **k: None),
                  mock.patch.object(clipool, 'IDLE_SECONDS', 60)]:
            p.start(); self.addCleanup(p.stop)
        self.s = s = store()
        self.tid = s.create_task({'Title': 'Pilot plan for Gail', 'Kind': 'general'}, 'o')
        self.addCleanup(self.end)
        self.ses = general.start_session(s, self.tid, actor='owner')
        self.ses.send_prompt('Draft a pilot plan for the new box.')
        self.sid = self.ses.sid

    def end(self):
        if (g := general.session_for(self.tid)): g.close(learn=False, report=False)
        general.drop_session(self.tid); general.IDLED.pop(self.tid, None); general.OPENING.discard(self.tid)

    def later(self, secs=61): return self.ses.last + secs

    def test_a_cli_that_died_while_idle_closes_the_session_at_the_next_sweep(self):
        # the product audit, 2026-11-08: its CLI tree killed, the session read alive - "waiting on you" over an agent that did not exist
        self.ses.cli_up = True
        with mock.patch.object(clipool, 'is_live', return_value=True):
            self.assertNotIn(self.tid, general.idle_sweep(self.ses.last + 1))       # alive and not idle long enough: it stays
        # ...and its browser goes with it, its view answering or not (the product audit, 2026-11-08: the daemon and Chrome outlived it)
        from taskuary import browserview
        with mock.patch.object(clipool, 'is_live', return_value=False), mock.patch.object(browserview, 'state', return_value={'open': False}),              mock.patch.object(browserview, 'close') as shut:
            self.assertIn(self.tid, general.idle_sweep(self.ses.last + 1))          # gone: closed quietly, as idle time would
        self.assertFalse(self.ses.alive); self.assertTrue(general.idled(self.tid, self.s))
        shut.assert_called_once_with(self.sid, self.tid)

    def test_an_idle_session_closes_quietly_after_the_period(self):
        s, tid = self.s, self.tid
        before = (chat(s, tid), len(s.list_comments(tid)), len(s.worker_events(tid)), s.get_task(tid)['Status'],
                  s._rows('SELECT ReviewId, Status FROM review WHERE TaskId=?', (tid,)), s.get_task(tid)['Tags'])
        self.assertEqual(general.idle_sweep(self.ses.last + 30), [])            # not yet: half the period
        with mock.patch.object(clipool, 'close') as closed, mock.patch('taskuary.general.report_note') as report, \
             mock.patch('taskuary.handbook.learn_from_session') as learn:
            self.assertEqual(general.idle_sweep(self.later()), [tid])
        closed.assert_called_once_with(f'general:{tid}')                           # its CLI stops
        report.assert_not_called(); learn.assert_not_called()                      # no result, no wrap-up
        self.assertIsNone(general.session_for(tid))                                # no agent running...
        self.assertNotIn(self.sid, terminal.SESSIONS)
        self.assertTrue(general.idled(tid, s))
        after = (chat(s, tid), len(s.list_comments(tid)), len(s.worker_events(tid)), s.get_task(tid)['Status'],
                 s._rows('SELECT ReviewId, Status FROM review WHERE TaskId=?', (tid,)), s.get_task(tid)['Tags'])
        self.assertEqual(after, before)                                            # ...and nothing else changed: chat, events, state, drafts

    def test_an_idled_task_reads_as_the_task_never_stopped_or_saved(self):
        "The stress run, 2026-11-05: the page said 'agent stopped' and the rail 'the assistant's conversation ... is saved' over an idled agent."
        from taskuary import funnel, lanes, taskstate
        general.idle_sweep(self.later())
        item = {'tid': self.tid, 'lane': 'yours', 'kind': 'task'}
        # ...and as it read live (the owner, 2026-11-07): a turn that asked nothing is done for now, never "waiting on you"
        row = funnel.paused_conversation(self.s, item)
        self.assertEqual((row['kind'], row.get('chat_done'), funnel.lane_word(row)), ('wrapup', True, 'agent done'))
        # ...under Tasks, where the open task was: it jumped to the Reports pile when its agent was done (the agent walk, 2026-11-09)
        self.assertEqual(lanes.lane_section(row['lane']), 'task')
        self.assertEqual(taskstate.state(self.s, self.s.get_task(self.tid)), 'agentdone')

    def test_the_task_reads_the_same_live_or_idled_out(self):
        """The audit, 2026-11-07: the agent asked, idled out, and the question vanished from the chip, the rail and the Assistant though nobody
        answered it; after the restart a turn that asked nothing read "waiting on you" until the next idle-out. Its question is the run's own
        recorded ask - open until answered - and a turn that asked nothing is done for now, whether its process is alive or not."""
        from taskuary import funnel, server, taskstate
        s, tid = self.s, self.tid
        state = lambda: taskstate.state(s, s.get_task(tid), (general.session_for(tid) or mock.Mock(info=lambda: None)).info())
        self.assertEqual(state(), 'agentdone')                                     # live, asked nothing
        ws.record(s, tid, self.sid, 'input_needed', text='Which site goes first?', source='api')
        self.assertEqual(state(), 'blocked')                                       # live, asking
        general.idle_sweep(self.later())
        self.assertEqual(state(), 'blocked')                                       # idled out: still asking...
        self.assertEqual(taskstate.open_question(s, tid)['text'], 'Which site goes first?')
        row = funnel.paused_conversation(s, {'tid': tid, 'lane': 'yours', 'kind': 'task'})
        self.assertEqual((row['lane'], row['tail']), ('blocked', ['Which site goes first?']))      # ...on the rail...
        from taskuary import stages
        self.assertEqual(stages.of_task(s, s.get_task(tid)), 'agent_result')       # ...its question to answer, no "agent working" with nothing running
        with mock.patch.object(server, 'store', s):
            asked = server._assistant_payload(tid)['asking']
        self.assertEqual((asked['text'], asked['resting']), ('Which site goes first?', True))     # ...and on the page, answered by typing
        general.start_session(s, tid, actor='owner').send_prompt('Riverside first.')
        self.assertEqual(state(), 'agentdone')                                     # answered, and the turn after it asked nothing
        general.idle_sweep(general.session_for(tid).last + 61)
        self.assertEqual(state(), 'agentdone')                                     # ...the same once idled out again

    def test_a_turn_running_is_never_cut_off(self):
        self.ses.busy = True
        self.assertEqual(general.idle_sweep(self.later(10_000)), [])
        self.ses.busy = False
        self.assertTrue(self.ses._lock.acquire())                                   # a turn holding the floor
        try: self.assertEqual(general.idle_sweep(self.later(10_000)), [])
        finally: self.ses._lock.release()
        self.assertIs(general.session_for(self.tid), self.ses)

    def test_an_input_on_its_way_keeps_it(self):
        self.s.add_waiting_note(self.tid, 'and the second site', 'owner') if hasattr(self.s, 'add_waiting_note') else \
            self.s._exec("INSERT INTO waitroom (TaskId, Note, CreatedBy) VALUES (?,?,?)", (self.tid, 'and the second site', 'owner'))
        self.assertEqual(general.idle_sweep(self.later()), [])

    def test_the_owner_looking_at_it_keeps_it(self):
        self.ses.seen = self.later(50)
        self.assertEqual(general.idle_sweep(self.later()), [])

    def test_a_step_on_its_page_waiting_for_the_owner_keeps_it(self):
        ws.record(self.s, self.tid, self.sid, 'input_needed', request_id='yourturn:abc', text='Your turn in the browser: sign the form', source='api')
        self.assertEqual(general.idle_sweep(self.later()), [])

    def test_a_question_in_words_idles_out_and_the_answer_brings_it_back(self):
        "Waiting on the owner's answer is idle too: the question stays in the chat as text, and the answer is the next turn."
        ws.record(self.s, self.tid, self.sid, 'input_needed', text='Which site goes first?', source='api')
        self.assertEqual(general.idle_sweep(self.later()), [self.tid])
        ses = general.start_session(self.s, self.tid, actor='owner')
        ses.send_prompt('Riverside first.')
        self.assertEqual(ses.sid, self.sid)
        self.assertIn('Riverside first.', self.brain.calls[-1])
        self.assertIsNone(ws.asking_of(self.s, ses))                               # answered by speaking

    def test_a_typed_line_restarts_it_on_the_saved_conversation(self):
        s, tid = self.s, self.tid
        general.idle_sweep(self.later())
        was = chat(s, tid)
        ses = general.start_session(s, tid, actor='owner')                        # the chat's door: assistant/messages and /stream
        self.assertEqual(ses.sid, self.sid)                                         # the same run - its drafts and questions still its own
        self.assertEqual(ses.cli_sid, 'cli-conv-1')
        self.assertEqual(ses.resume_notice, '')                                     # nothing says it stopped
        self.assertFalse(general.idled(tid, s))
        ses.send_prompt('Make it two weeks, not one.')
        self.assertEqual(self.built[-1]['resume'], 'cli-conv-1')                   # resumed by its CLI's own id
        self.assertIn('Make it two weeks, not one.', self.brain.calls[-1])
        self.assertEqual(chat(s, tid)[:len(was)], was)                              # the history above is unchanged...
        self.assertEqual([b for _a, b in chat(s, tid)[len(was):]], ['Make it two weeks, not one.', 'Here is the plan for the pilot.'])

    def test_a_joined_mail_restarts_it(self):
        s, tid = self.s, self.tid
        general.idle_sweep(self.later())
        self.assertEqual(ingest.live_agent(s, tid), 'general')                     # still the task's agent: the mail is its next turn
        own = general.start_session                 # the router's start is a process boundary in tests: the same start, as the owner's
        with mock.patch.object(ingest, 'PASS_GATHER', 0), mock.patch.object(general, 'start_session', lambda st, t, **k: own(st, t, **{**k, 'actor': 'owner'})):
            ingest._pass_general(s, tid, {'from_name': 'Gail Moreno', 'channel': 'email', 'body': 'Also price the Riverside site?', 'message_id': 9})
        ses = general.session_for(tid)
        self.assertEqual(ses.sid, self.sid)
        self.assertEqual(self.built[-1]['resume'], 'cli-conv-1')
        self.assertIn('Riverside', self.brain.calls[-1])
        self.assertTrue(any(general.is_brief(c) and 'Riverside' in c['Body'] for c in s.list_comments(tid, internal=True)))

    def test_a_closed_task_is_not_idled_but_over(self):
        general.idle_sweep(self.later())
        self.s.update_task(self.tid, {'Status': 'done'}, 'owner')
        self.assertFalse(general.idled(self.tid, self.s))
        self.assertEqual(ingest.live_agent(self.s, self.tid), '')

    def test_the_dock_never_idles_out(self):
        with mock.patch.object(general, 'is_dock', return_value=True):
            self.assertEqual(general.idle_sweep(self.later()), [])


if __name__ == '__main__': unittest.main()
