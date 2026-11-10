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
        self.assertEqual(clis.HEADLESS_ENV, {'CLAUDE_CODE_DISABLE_BACKGROUND_TASKS': '1'})
        self.assertIn(general.FINISH_LINE, seen['prompt'])


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


class WhatATurnLeavesUnwrittenTests(unittest.TestCase):
    """The owner, 2026-11-10: "it created reply with nothing in it. that's dumb. if you have nothing to reply just ask what should i reply?" -
    a task from a mail owed an email to someone on the thread (triage's slot), the owner asked the agent to respond, and its turn ended with the
    email still "to draft": no words in it, no card, no question, and only Drop beside it. Each way a turn can end so: told once to write it or
    ask, never by a judge (the rows say it), and after that the row lights its start with one line."""
    def no_judge(self, *a, **k): raise AssertionError('the rows already say what is owed')

    def owing(self, s):
        from taskuary import slots
        tid = researcher(s); slots.add(s, tid, [{'to': 'office@vendor.example', 'about': 'the renewal'}], 'triage')
        return tid

    def test_a_slot_left_to_draft_wakes_the_agent_once_to_write_it_or_ask(self):
        from taskuary import rulebook
        for said in ('Done.', '[[TASKUARY-DRAFT to="office@vendor.example" subject="Renewal"]]  [[/TASKUARY-DRAFT]]'):
            with self.subTest(said[:20]):
                s = MemoryStore(); a_claude(self); tid = self.owing(s)
                seen = turn(s, tid, said, judge=self.no_judge)
                self.assertEqual(len(seen['prompts']), 2, 'told once - the woken turn that left it again is not told twice')
                self.assertIn('email to office@vendor.example (slot ', seen['prompts'][1])
                self.assertIn('ask them that one question', seen['prompts'][1])
                f = rulebook.facts(s, {'tid': tid, 'kind': 'task', 'key': f'task:{tid}'}, [])
                self.assertEqual(f, {'state': 'needs_agent', 'line': 'Email to office@vendor.example unwritten - waits on your word'})

    def test_a_turn_that_wrote_it_or_asked_is_not_woken(self):
        for said in ('[[TASKUARY-DRAFT to="office@vendor.example" subject="Renewal"]]Hi - the renewal terms are fine by us.[[/TASKUARY-DRAFT]]',
                     '[[TASKUARY-ASK]] What should the email to the vendor say about the price?'):
            with self.subTest(said[:20]):
                s = MemoryStore(); a_claude(self); tid = self.owing(s)
                self.assertEqual(len(turn(s, tid, said)['prompts']), 1)

    def test_a_reply_owed_and_left_unwritten_wakes_it_the_same_way(self):
        from taskuary.testing import Factory
        from taskuary import origin
        s = MemoryStore(); a_claude(self); tid = researcher(s); f = Factory(s)
        p = mock.patch.object(origin, '_claude_version', return_value=origin.MIN_CLAUDE); p.start(); self.addCleanup(p.stop)
        f.review(tid, f.message(tid, from_email='erin@northwind.example', from_name='Erin Blake', subject='Renewal', body='Can you confirm?'),
                 kind='draft', draft='')
        seen = turn(s, tid, 'Looked into it.', judge=self.no_judge)
        self.assertEqual(len(seen['prompts']), 2)
        self.assertIn('the reply to Erin Blake still unwritten', seen['prompts'][1])


if __name__ == '__main__':
    unittest.main()
