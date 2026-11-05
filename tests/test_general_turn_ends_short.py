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


if __name__ == '__main__':
    unittest.main()
