"""A GENERAL AGENT FINISHES IN ITS TURN, AND A TURN THAT ENDED SHORT IS NOT "WAITING ON YOU" (the owner, 2026-10-21).

A researcher's last line was "I have the mail side. I'm waiting for the app walkthrough to finish, and then I'll write the brief." Its
CLI (Claude Code, headless) had put a sub-agent in the background, ended its turn, and nothing was left to bring the result back. The
task read "researcher answered · agent waiting on you", and the brief never came.

Both ends: the CLI runs with background work off and the brief says to finish in the turn; and the turn judge (hooks) reads a turn
that ended without delivering as the run FAILING, with its reason - the state every surface reads (workerstate.ended), where Try
again lives - with the session ended and its conversation saved, never parked as waiting on the owner.
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
    """One turn of a general agent on a fake Claude; the turn judge reads it at once with `judge` as its brain."""
    seen, real = {}, hooks.judge_ended
    def run_cli(profile, prompt, trace, resume=None, **kwargs):
        args = list(profile.get('args') or [])
        flag = next((f for f in ('--append-system-prompt-file', '--system-prompt-file') if f in args), None)
        seen.update(prompt=(open(args[args.index(flag) + 1], encoding='utf-8').read() if flag else '') + '\n\n' + prompt,
                    env={**(profile.get('env') or {}), **(kwargs.get('extra_env') or {})})
        return reply, None, None
    judged = lambda *a, **k: real(*a, **{**k, 'wait': True, 'brain': judge or verdict(False)})
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch('taskuary.agents.run_cli', side_effect=run_cli), \
         mock.patch.object(hooks, 'judge_ended', side_effect=judged):
        sess = general.start_session(s, tid, pick='cli:claude')
        sess.send_prompt("Read Gail Moreno's mail about the renewal and brief me", pick='cli:claude')
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


class AShortTurnIsAFailureTests(unittest.TestCase):
    def test_a_turn_that_ended_waiting_on_its_own_work_fails_with_why_and_is_not_waiting_on_you(self):
        s = MemoryStore(); a_claude(self); tid = researcher(s)
        seen = turn(s, tid, SHORT, judge=verdict(True, 'the app walkthrough it started in the background'))
        sess = seen['session']
        self.assertFalse(sess.alive)                                  # ended, its conversation saved
        self.assertEqual(seen['ended'], 'failed')                     # the one reading every surface takes
        last = s.last_worker_event(tid, skip=ws.NOTES)
        self.assertEqual(last['Kind'], 'failed')
        self.assertIn('the app walkthrough it started in the background', last['Text'])
        self.assertIsNone(sess.info()['state'])                       # not parked: nobody is told it waits on them
        self.assertFalse(sess.info()['waiting'])
        self.assertTrue(any(SHORT in str(c['Body']) for c in s.list_comments(tid)))      # what it said is still the record
        # ...and it lands on R2's failed state and words, not a parallel one: "Failed - <reason>", Try again under it
        from taskuary import funnel
        self.assertEqual(funnel.idle_state(s, tid)['line'],
                         'Failed - It ended its turn still waiting on the app walkthrough it started in the background.')

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
        hooks.judge_ended(s, tid, 'g1', SHORT, brain=verdict(True, 'the walkthrough'), wait=True, then=lambda: ended.append(1))
        self.assertEqual(s.last_worker_event(tid, skip=ws.NOTES)['Kind'], 'working')
        self.assertEqual(ended, [])

    def test_an_unreadable_verdict_is_no_verdict(self):
        s = MemoryStore(); tid = researcher(s)
        ws.record(s, tid, 'g2', 'turn_end', text=SHORT, source='api')
        hooks.judge_ended(s, tid, 'g2', SHORT, brain=lambda *a, **k: 'not json', wait=True)
        self.assertEqual(s.last_worker_event(tid, skip=ws.NOTES)['Kind'], 'turn_end')


if __name__ == '__main__':
    unittest.main()
