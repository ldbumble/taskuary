"""A GENERAL AGENT FINISHES IN ITS TURN, AND A TURN THAT ENDED SHORT IS NOT "WAITING ON YOU" (the owner, 2026-10-21).

A researcher's last line was "I have the mail side. I'm waiting for the app walkthrough to finish, and then I'll write the brief." Its
CLI (Claude Code, headless) had put a sub-agent in the background, ended its turn, and nothing was left to bring the result back. The
task read "researcher answered · agent waiting on you", and the brief never came.

Both ends: the CLI runs with background work off and the brief says to finish in the turn; and the turn judge (hooks) reads a turn
that ended without delivering and WAKES the agent once to do it now. It used to file the run as failed and end the session; the owner,
2026-11-05: "failure means nothing to the user" - so nothing fails in the chat, and the session stays open.
"""
import json
import unittest
from unittest import mock

from taskuary import clis, config, general, hooks, terminal, workerstate as ws
from taskuary.store import MemoryStore

SHORT = "I have the mail side. I'm waiting for the app walkthrough to finish, and then I'll write the brief."


def a_claude(test):
    from taskuary import agents
    real, conns = config.load, {'claude': {'cmd': 'claude', 'args': ['-p', '--dangerously-skip-permissions']}}
    for p in (mock.patch.object(config, 'load', side_effect=lambda: {**real(), 'cli_connections': conns}),
              mock.patch.object(agents, 'connection_brains', getattr(agents.connection_brains, 'real', agents.connection_brains))):
        p.start(); test.addCleanup(p.stop)


def researcher(s):
    s.upsert_agent('researcher', 'research', 'cli', '{}')
    return s.create_task({'Title': 'Brief me before the renewal meeting', 'Kind': 'general', 'Status': 'open',
                          'Assignee': 'agent:researcher', 'OriginBase': 'owner'}, 'owner')


def verdict(unfinished, why=''):
    return lambda *a, **k: json.dumps({'unfinished': unfinished, 'why': why})


def turn(s, tid, reply, judge=None):
    """One turn of a general agent on a fake Claude; the turn judge reads it at once with `judge` as its brain. `reply` may be a list:
    one answer per turn the CLI runs (a woken turn is the second), the last one repeated."""
    seen, real, replies = {'prompts': []}, hooks.judge_ended, list(reply) if isinstance(reply, list) else [reply]
    def run_cli(profile, prompt, trace, resume=None, **kwargs):
        args = list(profile.get('args') or [])
        flag = next((f for f in ('--append-system-prompt-file', '--system-prompt-file') if f in args), None)
        seen.update(prompt=(open(args[args.index(flag) + 1], encoding='utf-8').read() if flag else '') + '\n\n' + prompt,
                    env={**(profile.get('env') or {}), **(kwargs.get('extra_env') or {})})
        seen['prompts'].append(prompt)
        return (replies.pop(0) if len(replies) > 1 else replies[0]), None, None
    judged = lambda *a, **k: real(*a, **{**k, 'wait': True, 'brain': judge or verdict(False)})
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch('taskuary.agents.run_cli', side_effect=run_cli), \
         mock.patch.object(hooks, 'judge_ended', side_effect=judged):
        sess = general.start_session(s, tid, pick='cli:claude')
        sess.send_prompt("Read Gail Moreno's mail about the renewal and brief me", pick='cli:claude')
        while getattr(sess, 'waking', None) and sess.waking.is_alive(): sess.waking.join(10)     # the woken turn, inside the fakes
        seen['session'] = sess
        seen['ended'] = ws.ended(s, tid)
    return seen


class TheCliFinishesInItsTurnTests(unittest.TestCase):
    def test_background_work_is_off_and_the_brief_says_to_finish_now(self):
        s = MemoryStore(); a_claude(self)
        seen = turn(s, researcher(s), 'Here is the brief: Gail wants a three-year term.')
        self.assertEqual(seen['env'].get('CLAUDE_CODE_DISABLE_BACKGROUND_TASKS'), '1')
        # ...and the CLI's own memory folder is off: what a chat agent learns goes through Taskuary's tools, for one press
        self.assertEqual(seen['env'].get('CLAUDE_CODE_DISABLE_AUTO_MEMORY'), '1')
        self.assertEqual(clis.HEADLESS_ENV, {'CLAUDE_CODE_DISABLE_BACKGROUND_TASKS': '1', 'CLAUDE_CODE_DISABLE_AUTO_MEMORY': '1'})
        self.assertIn(general.FINISH_LINE, seen['prompt'])

    def test_no_cli_taskuary_starts_keeps_a_memory_of_its_own(self):
        """It was off for a chat agent only (2026-11-11): a coding agent in a pane - whose start strips every inherited CLAUDE_CODE_* - an
        ACP coding agent and a one-shot with tools still wrote into Claude Code's own memory folder, where no card holds it (2026-11-12)."""
        from taskuary import agents, acpcoding
        off = lambda env: env.get('CLAUDE_CODE_DISABLE_AUTO_MEMORY') == '1'
        with mock.patch.dict('os.environ', {'CLAUDE_CODE_DISABLE_AUTO_MEMORY': '0', 'CLAUDECODE': '1'}):
            self.assertTrue(off(agents.child_env()) and off(agents.spawn_env({})) and off(agents.spawn_env({'strict_env': True})))
            self.assertTrue(off(terminal.clean_env()) and off(terminal.clean_env({'TASKUARY_TASK': '7'}, strict=True)), 'the pane: coding agents')
            sess = acpcoding.ACPCoding.__new__(acpcoding.ACPCoding)
            sess.profile, sess.args, sess.model, sess.agent, sess.label, sess.task_id, sess.cwd, sess.sid = {'cmd': 'claude'}, [], None, 'coding', 'coding', 7, '.', 's7'
            with mock.patch.object(agents, 'acp_launch', return_value={'cmd': ['adapter'], 'env': {'CLAUDE_CODE_EXECUTABLE': 'claude'}}):
                self.assertTrue(off(sess._launch()[2]), 'the ACP adapter, whose Claude inherits its environment')


class AShortTurnWakesTheAgentOnceTests(unittest.TestCase):
    def test_a_turn_that_ended_waiting_on_its_own_work_wakes_it_once_and_never_fails(self):
        s = MemoryStore(); a_claude(self); tid = researcher(s)
        seen = turn(s, tid, [SHORT, 'Here is the brief: Gail wants a three-year term.'], judge=verdict(True, 'waiting for the app walkthrough'))
        sess = seen['session']
        self.assertTrue(sess.alive)                                   # the session stays open
        self.assertIsNone(seen['ended'])                              # ...and nothing reads "failed"
        self.assertNotIn('failed', [e['Kind'] for e in ws.events(s, tid, sess.sid)])
        self.assertEqual(len(seen['prompts']), 2)                     # woken once...
        self.assertIn('ended still waiting on the app walkthrough. Nothing wakes you', seen['prompts'][1])
        bodies = [str(c['Body']) for c in s.list_comments(tid)]
        self.assertTrue(any(SHORT in b for b in bodies)); self.assertTrue(any('three-year term' in b for b in bodies))
        self.assertFalse(any('TASKUARY: your last answer' in b for b in bodies))      # ...never in the chat as anyone's words

    def test_an_answer_that_asks_the_owner_for_a_password_is_taken_back_by_its_agent_on_the_sign_in_road(self):
        """Five recorded walks, 2026-11-11: asked to sign in to a site with no connection, the agent fetched the form from its shell and asked
        the owner to paste the password - four times of five, with the browser's offer in its prompt."""
        from taskuary import browserview
        s = MemoryStore(); a_claude(self); tid = researcher(s)
        asked = 'I have no Payworth login. Send me the email and password, or name a file that holds them.'
        # ...ending on its summary, as every turn does - "Gail asked Alex ..." is the summary of the words taken back, and goes with them
        summ = ' [[TASKUARY-SUMMARY]]{"about": "Gail asked Alex for the payroll date.", "did": "Nothing read yet."}[[/TASKUARY-SUMMARY]]'
        seen = turn(s, tid, [asked + summ, 'There is no connection for Payworth, so I am using the browser.'],
                    judge=lambda *a, **k: json.dumps({'unfinished': False, 'why': '', 'asks_secret': True}))
        self.assertEqual(len(seen['prompts']), 2)                     # told once, by the one wake
        for want in ('asked the owner for a password', 'you do not need the password', '[[TASKUARY-SIGNIN:'): self.assertIn(want, seen['prompts'][1])
        self.assertIn(browserview.SIGNIN_LINE, browserview.offer())  # ...the same words its prompt offers the browser with
        bodies = [str(c['Body']) for c in s.list_comments(tid)]
        self.assertTrue(any('using the browser' in b for b in bodies)); self.assertFalse(any('TASKUARY: your last answer' in b for b in bodies))
        self.assertIn('asks_secret', hooks.ENDED_SYSTEM)
        # ...and the ask it took back is a step of the work, never an answer standing in the chat above the page it then opened
        from taskuary import conversation
        turns = [x for x in conversation.items(s, tid)['items'] if x['kind'] == 'turn']
        self.assertEqual([x['text'] for x in turns], ['', 'There is no connection for Payworth, so I am using the browser.'])
        self.assertEqual([st.get('text') for st in turns[0]['steps'] if st.get('k') == 'note'], [conversation.TOOK_BACK])
        self.assertNotIn(asked, str(turns))
        self.assertNotIn('summary', turns[0], "the taken-back answer's summary goes with its words (the recorded walk, 2026-11-12)")
        self.assertNotIn('Gail asked Alex', str(turns))
        self.assertIn('do not mention it', seen['prompts'][1])

    def test_a_woken_turn_that_ends_short_again_is_not_woken_again(self):
        s = MemoryStore(); a_claude(self); tid = researcher(s)
        seen = turn(s, tid, SHORT, judge=verdict(True, 'the app walkthrough'))
        self.assertEqual(len(seen['prompts']), 2)                     # the turn and its one wake, then it stands
        self.assertTrue(seen['session'].alive); self.assertIsNone(seen['ended'])

    def test_a_turn_that_delivered_stays_an_answer(self):
        s = MemoryStore(); a_claude(self); tid = researcher(s)
        seen = turn(s, tid, 'Here is the brief: Gail wants a three-year term and a 6% uplift.', judge=verdict(False))
        self.assertTrue(seen['session'].alive)
        self.assertIsNone(seen['ended'])
        self.assertEqual(s.last_worker_event(tid, skip=ws.NOTES)['Kind'], 'turn_end')

    def test_a_verdict_after_the_owner_wrote_again_changes_nothing(self):
        s = MemoryStore(); tid = researcher(s)
        ws.record(s, tid, 'g1', 'turn_end', text=SHORT, source='api')
        ws.record(s, tid, 'g1', 'working', text='go on', source='api')
        ended = []
        hooks.judge_ended(s, tid, 'g1', SHORT, brain=verdict(True, 'the walkthrough'), wait=True, then=ended.append)
        self.assertEqual(s.last_worker_event(tid, skip=ws.NOTES)['Kind'], 'working')
        self.assertEqual(ended, [])

    def test_a_turn_that_ended_on_a_held_step_waits_on_the_owner(self):
        """The overnight run, 2026-11-03: a delete held for Approve, the agent said it was waiting for it, and the judge read the turn as
        short. A held step is waiting on the owner: no wake. Another session's held step does not count."""
        s = MemoryStore(); tid = researcher(s)
        said = 'Nothing has changed yet, because the delete is waiting for your approval.'
        for sid, held in (('g3', 'g3'), ('g4', 'someone-else')):
            ws.record(s, tid, sid, 'turn_end', text=said, source='api')
            s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'DraftText': json.dumps({'action': 'shell_act', 'sid': held}),
                          'Reason': 'held before it ran'})
            woke = []
            hooks.judge_ended(s, tid, sid, said, brain=verdict(True, 'waiting on Approve'), wait=True, then=woke.append)
            self.assertEqual(woke, [] if sid == 'g3' else ['Approve'])
            self.assertEqual(s.last_worker_event(tid, skip=ws.NOTES)['Kind'], 'turn_end')        # never a failure

    def test_a_turn_that_set_its_own_check_back_is_not_woken_before_it_is_due(self):
        """Recorded on the real CLI, 2026-11-13 (invented people): two emails went on the owner's Send; the agent said "I'll check back in two
        days for Ray's quote" and set the check-back; the judge read that as work of its own, and the agent was woken ten seconds later to
        say that nobody had answered yet. The check-back is the wake: a stored fact, read before any model. One set by an EARLIER turn says
        nothing of this one, and a turn that says the same with none set is still the judge's to read."""
        from taskuary import checkback
        said = "Both emails, to Ray and to Erin, have gone out. I'll check back in two days for Ray's quote and Erin's answer on the budget."
        short, asked = verdict(True, "its own check-in in two days for Ray's quote"), []
        def judge(*a, **k): asked.append(1); return short(*a, **k)
        s = MemoryStore(); tid = researcher(s)
        ws.record(s, tid, 'g7', 'working', text='', source='api')
        checkback.set_check(s, tid, 'in 2 days', 'Ray Colton sent the bus quote', 'assistant')
        ws.record(s, tid, 'g7', 'turn_end', text=said, source='api')
        woke = []
        hooks.judge_ended(s, tid, 'g7', said, brain=judge, wait=True, then=woke.append)
        self.assertEqual((woke, asked), ([], []), 'no wake, and no model was asked')
        # ...a later turn on the same task, the old check-back still waiting: that turn's own short end is read as before
        s._exec("UPDATE audit SET CreatedAt='2026-11-01 09:00:00' WHERE Action='check_back'")
        ws.record(s, tid, 'g7', 'working', text='go on', source='api'); ws.record(s, tid, 'g7', 'turn_end', text=SHORT, source='api')
        hooks.judge_ended(s, tid, 'g7', SHORT, brain=verdict(True, 'the walkthrough'), wait=True, then=woke.append)
        self.assertEqual(woke, ['the walkthrough'])
        # ...and with none set, the same words are the judge's to read
        s2 = MemoryStore(); t2 = researcher(s2)
        ws.record(s2, t2, 'g8', 'working', text='', source='api'); ws.record(s2, t2, 'g8', 'turn_end', text=said, source='api')
        hooks.judge_ended(s2, t2, 'g8', said, brain=judge, wait=True, then=woke.append)
        self.assertEqual(len(asked), 1)

    def test_a_turn_is_not_woken_while_something_it_set_up_waits_for_the_owners_press(self):
        """Recorded on the real CLI, 2026-11-13 (invented people): the agent wrote two emails; the owner sent the first; the agent, told so,
        said the second "hasn't been sent yet" - and the judge read that as work left unfinished, so it was woken to answer "Only you can
        send the email to Omar. Nothing else is needed from me for it." A card waiting for his press is a stored fact: he moves next."""
        said = "Your email asking Marcus to book the AV went out. The email to Omar asking for the attendee list hasn't been sent yet."
        asked, woke = [], []
        def judge(*a, **k): asked.append(1); return json.dumps({'unfinished': True, 'why': 'email to Omar not yet sent'})
        s = MemoryStore(); tid = researcher(s)
        rid = s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': 'Hi Omar, could you send me the attendee list? Alex',
                            'Deliver': json.dumps({'channel': 'email', 'to': ['omar@northwind.example'], 'cc': [], 'subject': 'Attendee list', 'slot': 's1'})})
        ws.record(s, tid, 'g9', 'working', text='', source='api'); ws.record(s, tid, 'g9', 'turn_end', text=said, source='api')
        hooks.judge_ended(s, tid, 'g9', said, brain=judge, wait=True, then=woke.append)
        self.assertEqual((woke, asked), ([], []), 'no wake, and no model was asked')
        s.decide_review(rid, 'approved', None, 'owner')                # ...nothing waits on him any more: the same words are the judge's to read
        hooks.judge_ended(s, tid, 'g9', said, brain=judge, wait=True, then=woke.append)
        self.assertEqual((woke, asked), (['email to Omar not yet sent'], [1]))

    def test_an_unreadable_verdict_is_no_verdict(self):
        s = MemoryStore(); tid = researcher(s)
        ws.record(s, tid, 'g2', 'turn_end', text=SHORT, source='api')
        hooks.judge_ended(s, tid, 'g2', SHORT, brain=lambda *a, **k: 'not json', wait=True)
        self.assertEqual(s.last_worker_event(tid, skip=ws.NOTES)['Kind'], 'turn_end')


class TheTurnsOwnRecordAnswersFirstTests(unittest.TestCase):
    """"No model call where stored facts already answer" (the owner's rule, 2026-11-10): what the turn put aside - sub-agents, background
    jobs - is in its own record. Still running wakes it, all of it back does not, and only a turn that put nothing aside is read."""
    def no_model(self, *a, **k): raise AssertionError('a model was asked what the record already says')

    def test_a_subagent_that_came_back_is_finished_and_no_model_is_asked(self):
        from taskuary import background
        s = MemoryStore(); tid = researcher(s)
        ws.record(s, tid, 'g5', 'turn_end', text=SHORT, source='api')
        trace = [{'type': 'tool_call', 'name': 'Task', 'detail': {'tool_call_id': 't1', 'args': {'description': 'app walkthrough'}}},
                 {'type': 'tool_result', 'name': 't1', 'detail': {'result': 'the walkthrough notes'}}]
        self.assertEqual(background.left(trace), [])
        woke = []
        hooks.judge_ended(s, tid, 'g5', SHORT, brain=self.no_model, wait=True, then=woke.append, jobs=background.left(trace))
        self.assertEqual(woke, [])

    def test_work_still_running_wakes_it_without_a_model(self):
        import os, tempfile, time
        from datetime import datetime, timezone
        from taskuary import background
        s = MemoryStore(); tid = researcher(s)
        ws.record(s, tid, 'g6', 'turn_end', text=SHORT, source='api')
        use = {'type': 'tool_use', 'id': 'u1', 'name': 'Bash', 'input': {'command': 'pull the walkthrough', 'run_in_background': True}}
        res = {'timestamp': datetime.now(timezone.utc).isoformat(), 'toolUseResult': {'backgroundTaskId': 'b1'},
               'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'u1'}]}}
        fd, path = tempfile.mkstemp(suffix='.jsonl'); os.close(fd); self.addCleanup(os.remove, path)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(json.dumps({'message': {'content': [use]}}, separators=(',', ':')) + chr(10) + json.dumps(res, separators=(',', ':')) + chr(10))
        trace = [{'type': 'tool_call', 'name': 'Bash', 'detail': {'tool_call_id': 'u1', 'args': use['input']}},
                 {'type': 'tool_result', 'name': 'u1', 'detail': {'result': 'started b1'}}]
        jobs = background.left(trace, path)
        self.assertEqual([j['kind'] for j in jobs], ['shell'])
        self.assertIsNone(background.left(trace))                    # ...a background job with no record of its end: the data cannot tell
        woke = []
        hooks.judge_ended(s, tid, 'g6', SHORT, brain=self.no_model, wait=True, then=woke.append, jobs=jobs)
        self.assertEqual(woke, ['1 shell still running'])

    def test_a_turn_that_put_nothing_aside_is_left_to_the_model(self):
        from taskuary import background
        self.assertIsNone(background.left([{'type': 'tool_call', 'name': 'WebSearch', 'detail': {'tool_call_id': 'w1', 'args': {}}},
                                           {'type': 'tool_result', 'name': 'w1', 'detail': {}}]))
        s = MemoryStore(); tid = researcher(s)
        ws.record(s, tid, 'g7', 'turn_end', text=SHORT, source='api')
        woke = []
        hooks.judge_ended(s, tid, 'g7', SHORT, brain=verdict(True, 'the walkthrough'), wait=True, then=woke.append, jobs=None)
        self.assertEqual(woke, ['the walkthrough'])

    def test_a_turn_that_left_a_letter_for_the_owners_send_is_never_read_as_short_or_as_asking_for_a_sign_in(self):
        """The owner's live task, 2026-11-13 (invented people): he corrected the agent; its turn rewrote the reply to Erin and said the
        login she needs "comes separately, so that one is still yours". The judge read those words as asking him for a sign-in: the answer
        was taken back, its agent woken with "your last answer asked the owner for a password", and that second turn left a second letter
        to Erin under the first card, its words under both. The turn's own record says it left a letter for his Send (the summary's
        `drafted`): a person moves next, so nothing is read and nobody is woken."""
        s = MemoryStore(); tid = researcher(s)
        said = 'The reply to Erin is rewritten with the three files. It says the portal login comes separately, so that one is still yours.'
        ws.record(s, tid, 'g8', 'turn_end', text=said, source='api')
        woke, asked = [], []
        brain = lambda *a, **k: asked.append(1) or json.dumps({'unfinished': False, 'why': '', 'asks_secret': True})
        hooks.judge_ended(s, tid, 'g8', said, brain=brain, wait=True, then=lambda *a: woke.append(a), summ={'did': 'Rewrote the reply.', 'nothing_left': False, 'drafted': [{'review': 7}]})
        self.assertEqual((woke, asked), ([], []))                                   # no wake, and no model call: the stored fact answers
        # ...a turn that left the draft as it was (`drafted` empty) is read as before
        hooks.judge_ended(s, tid, 'g8', said, brain=brain, wait=True, then=lambda *a: woke.append(a), summ={'did': 'Looked again.', 'drafted': []})
        self.assertEqual(len(woke), 1)
        # ...and work the turn itself put aside that still runs wakes it, a letter left or not
        woke.clear()
        hooks.judge_ended(s, tid, 'g8', said, brain=brain, wait=True, then=lambda *a: woke.append(a), summ={'drafted': [{'review': 7}]},
                          jobs=[{'kind': 'shell'}])
        self.assertEqual(len(woke), 1)


class AnOwnersAskAnsweredWithNothingTests(unittest.TestCase):
    """The owner, 2026-11-10: "it created reply with nothing in it. that's dumb. if you have nothing to reply just ask what should i reply?" -
    a task from a mail listed an email to someone on the thread, the owner asked the agent to respond, and its turn ended with no words, no
    card and no question. The agent is asked once to answer what he asked; if it says nothing again, its one question is "I could not draft
    anything for that. What should I say, or what should I do?". An email nobody wrote is no debt the app chases ("goal is to help user not to
    do action"): a turn that answered leaves it alone."""
    EMPTY = '[[TASKUARY-DRAFT to="office@vendor.example" subject="Hello"]] [[/TASKUARY-DRAFT]]'
    def no_judge(self, *a, **k): raise AssertionError('the rows already say the turn said nothing')

    def test_it_is_woken_once_to_answer_and_an_empty_turn_again_asks_its_one_question(self):
        s = MemoryStore(); a_claude(self); tid = researcher(s)
        seen = turn(s, tid, self.EMPTY, judge=self.no_judge)
        self.assertEqual(len(seen['prompts']), 2, 'once - never a loop')
        self.assertIn('without a word to the owner', seen['prompts'][1]); self.assertIn('ask them your one question', seen['prompts'][1])
        said = [c['Body'] for c in s.list_comments(tid) if c['ActorType'] == general.ASSISTANT_TYPE]
        self.assertEqual(said[-1], general.COULD_NOT, 'in the chat, in its own name')
        asked = s.last_worker_event(tid, skip=ws.NOTES)
        self.assertEqual((asked['Kind'], asked['Text']), ('input_needed', general.COULD_NOT), 'the normal ask: the agent waits on the owner')

    def test_a_turn_with_no_words_at_all_is_the_same_turn_that_said_nothing(self):
        """The audit, 2026-11-10: a CLI's turn that ended on tool calls alone came back '' - filed as "the model returned an empty response",
        the session ended and Continue lit, the owner's ask unanswered. It is the turn that said nothing: woken once, then its one question."""
        s = MemoryStore(); a_claude(self); tid = researcher(s)
        seen = turn(s, tid, '', judge=self.no_judge)
        self.assertEqual(len(seen['prompts']), 2, 'woken once')
        said = [c['Body'] for c in s.list_comments(tid) if c['ActorType'] == general.ASSISTANT_TYPE]
        self.assertEqual(said[-1], general.COULD_NOT)
        self.assertEqual(s.last_worker_event(tid, skip=ws.NOTES)['Kind'], 'input_needed', 'its question waits - never a failure')

    def test_a_woken_turn_that_answers_keeps_its_own_words(self):
        s = MemoryStore(); a_claude(self); tid = researcher(s)
        seen = turn(s, tid, [self.EMPTY, 'I could not tell what to say to the vendor - keep the 12 seats, or change them?'], judge=self.no_judge)
        said = [c['Body'] for c in s.list_comments(tid) if c['ActorType'] == general.ASSISTANT_TYPE]
        self.assertEqual(len(seen['prompts']), 2); self.assertIn('keep the 12 seats', said[-1]); self.assertNotIn(general.COULD_NOT, said)

    def test_a_turn_that_answered_or_set_up_a_card_is_not_woken_whatever_the_task_lists(self):
        from taskuary import slots
        for said in ('Done.', '[[TASKUARY-DRAFT to="office@vendor.example" subject="Hello"]]Hi - checking in.[[/TASKUARY-DRAFT]]'):
            with self.subTest(said[:20]):
                s = MemoryStore(); a_claude(self); tid = researcher(s)
                slots.add(s, tid, [{'to': 'gail@vendor.example', 'about': 'the renewal'}], 'owner')     # an email nobody wrote: not chased
                self.assertEqual(len(turn(s, tid, said)['prompts']), 1)


if __name__ == '__main__':
    unittest.main()
