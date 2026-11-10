"""One record of an act an agent asks for (the spine audit, 2026-11-09).

What an agent may ask for was two lists that had drifted: the marker's refused a held step, the tool's did not - an agent could file its
own "held step" and have the owner's Approve run it. A press that FAILED lived only in the answer to that press: after a reload the card
stood as if never pressed, and the agent was told nothing. An approved held step told only an agent that was running - one that rested was
left asleep. The owner's words typed into an empty merge box went nowhere. Invented people."""
import json, time, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import agenttools, general, proposals, shellgate as sg, terminal as term, verdicts
from taskuary.store import MemoryStore
from taskuary.testing import Factory

HELD = r'C:\work\ledger'
SAID = 'https://github.com/northwind/ledger/pull/12#issuecomment-1'


class WhatAnAgentMayAsk(unittest.TestCase):
    def test_the_tool_and_the_marker_refuse_the_same_acts(self):
        self.assertLessEqual(set(proposals.HELD_ACTS), set(proposals.NOT_ASKED), 'a held step is raised by its hook, never asked for')
        for a in proposals.NOT_ASKED:
            with self.subTest(a):
                ask = {'action': a, 'sid': 'run1', 'command': 'git push origin main', 'args': ['click', '@e1']}
                with self.assertRaises(ValueError): agenttools.proposal_of(ask)
                self.assertEqual(proposals.parse(f'{proposals.MARK} {json.dumps(ask)}'), [])

    def test_neither_lets_an_agent_mark_its_own_ask(self):
        ask = {'action': 'comment_issue', 'body': 'Fixed in the next release.', 'closeout': True, 'flow_run': {'run': 1}}
        want = {'action': 'comment_issue', 'body': 'Fixed in the next release.'}
        self.assertEqual(agenttools.proposal_of({**ask, 'task_id': 4}), want)
        self.assertEqual(proposals.parse(f'{proposals.MARK} {json.dumps(ask)}'), [want])


class Acts(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Answer the review on the ledger fix'); general._WOKEN.clear(); proposals._PRESSED.clear()

    def action(self, p):
        rid = Factory(self.s).review(self.tid, kind='action', reason='The agent asks', draft=json.dumps(p))
        return self.s.get_review(rid if isinstance(rid, int) else rid['ReviewId'])

    def answered(self):
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'The comment is ready - press Approve.')
        self.s._exec("UPDATE comment SET CreatedAt='2000-01-01 00:00:00' WHERE TaskId=?", (self.tid,))


class APressThatFailed(Acts):
    WHY = 'GitHub refused it: the token may not comment on northwind/ledger'
    def fail(self, rv, why=None):
        with mock.patch.object(proposals, 'execute', side_effect=RuntimeError(why or self.WHY)):
            return verdicts.decide(self.s, rv, 'approve')

    def test_is_kept_on_the_review_that_still_waits(self):
        rv = self.action({'action': 'comment_issue', 'body': 'Fixed.'})
        out = self.fail(rv)
        self.assertEqual((out['ok'], out['status'], out['send_error']), (False, 'pending', self.WHY))
        now = self.s.get_review(rv['ReviewId'])
        self.assertEqual((now['Status'], now['ActError']), ('pending', self.WHY), 'a reload drew the card as if it had never been pressed')
        self.fail(now, 'GitHub is not answering')
        self.assertEqual(self.s.get_review(rv['ReviewId'])['ActError'], 'GitHub is not answering', 'the newest press is the one it says')

    def test_is_told_to_its_agent_with_the_owners_next_line(self):
        self.answered(); rv = self.action({'action': 'comment_issue', 'body': 'Fixed.'})
        self.fail(rv)
        did = ' | '.join(general.owner_did(self.s, self.tid))
        self.assertIn(f"rv{rv['ReviewId']}", did); self.assertIn('IT FAILED', did); self.assertIn('the token may not comment', did)
        self.assertIn('still waits', did)

    def test_one_that_then_went_is_told_as_gone(self):
        self.answered(); rv = self.action({'action': 'comment_issue', 'body': 'Fixed.'})
        self.fail(rv)
        with mock.patch.object(proposals, 'execute', return_value={'commented': 'northwind/ledger#7', 'url': SAID}), mock.patch.object(general, 'approved'):
            self.assertTrue(verdicts.decide(self.s, self.s.get_review(rv['ReviewId']), 'approve')['ok'])
        did = ' | '.join(general.owner_did(self.s, self.tid))
        self.assertNotIn('IT FAILED', did); self.assertIn(f"approved (sent, if it sends) rv{rv['ReviewId']}", did)

    def test_a_held_step_that_failed_says_so_on_its_row(self):
        sg.check(self.s, self.tid, 'run1', 'git push origin fix-export', 'Bash', HELD)
        [rv] = self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))
        run = mock.patch.object(sg.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stdout='', stderr='remote: Permission to northwind/ledger denied'))
        with mock.patch.object(sg.os.path, 'isdir', lambda p: p == HELD), run:
            self.assertFalse(verdicts.decide(self.s, rv, 'approve')['ok'])
        self.assertIn('Permission to northwind/ledger denied', self.s.get_review(rv['ReviewId'])['ActError'])


class AnApprovedHeldStepWakesItsAgent(Acts):
    def setUp(self):
        super().setUp()
        sg.check(self.s, self.tid, 'run1', "gh pr comment 12 --body 'Thanks - merged after the fix'", 'Bash', HELD)
        [self.rv] = self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))

    def press(self, verb, told):
        ses = SimpleNamespace(send_prompt=lambda text, **kw: told.append((text, kw)))
        run = mock.patch.object(sg.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=SAID, stderr=''))
        with mock.patch('taskuary.workerstate._live', return_value=None), mock.patch.object(sg.os.path, 'isdir', lambda p: p == HELD), run, \
             mock.patch.object(general, 'start_session', return_value=ses), mock.patch.object(general, 'handles', return_value=True):
            self.assertTrue(verdicts.decide(self.s, self.rv, verb)['ok'])
            end = time.time() + (5 if verb == 'approve' else .3)
            while not told and time.time() < end: time.sleep(.01)

    def notes(self): return [c['Body'] for c in self.s.list_comments(self.tid, internal=True) if c.get('Actor') == 'taskuary']

    def test_a_resting_agent_that_answered_is_started_on_what_it_did(self):
        self.answered(); told = []
        self.press('approve', told)
        [(text, kw)] = told
        self.assertFalse(kw.get('as_owner', True), "Taskuary's words, never the owner's line")
        self.assertIn('The owner approved it', text); self.assertIn(SAID, text); self.assertIn('what comes next', text)
        self.assertFalse(any('No agent is running' in n for n in self.notes()), 'it was told: the task does not say nobody was')

    def test_a_step_dismissed_wakes_nobody(self):
        self.answered(); told = []
        self.press('reject', told)
        self.assertEqual(told, [], 'a no is heard with the owner\'s next line - it starts no turn')
        self.assertTrue(any('No agent is running' in n for n in self.notes()))

    def test_with_no_agent_ever_on_it_the_task_says_nobody_was_told(self):
        told = []
        self.press('approve', told)
        self.assertEqual(told, []); self.assertTrue(any('No agent is running' in n for n in self.notes()))


class APartThatIsAnotherJob(Acts):
    """Triage joined a second matter to the task - a chat line, a mail on another subject. The agent asks to break it out through the one
    record every ask of its takes; the owner's press runs the task page's own split. It had no way to ask: the mix-up came back as prose."""
    def setUp(self):
        super().setUp()
        f = Factory(self.s)
        self.fix = f.message(self.tid, from_name='Erin Blake', subject='Ledger fix review', body='Two comments on the rounding change.')
        self.other = f.message(self.tid, from_name='Ray Colton', subject='Parking permits', body='Can you renew the two parking permits by Friday?')
        self.s._write_checklist(self.tid, [{'id': 'a1', 'text': 'Answer the review'}, {'id': 'b2', 'text': 'Renew the parking permits'}], 'triage')
        self.ask = {'action': 'break_out', 'title': 'Renew the parking permits', 'summary': 'Ray asks for two permits renewed by Friday.',
                    'messages': [f'm{self.other}'], 'items': ['b2'], 'why': 'the permits have nothing to do with the ledger review'}

    def queue(self, **kw):
        q = proposals.queue(self.s, self.tid, agenttools.proposal_of({**self.ask, **kw, 'task_id': self.tid}), refused=(why := []))
        return (q and self.s.get_review(q['reviewId'])), why

    def test_it_is_a_card_that_says_what_goes_and_moves_nothing(self):
        rv, _ = self.queue()
        p = json.loads(rv['DraftText'])
        self.assertEqual((rv['Kind'], rv['Status'], p['messages'], p['items']), ('action', 'pending', [self.other], ['b2']))
        self.assertIn('move 1 message and 1 to-do to a task of its own, "Renew the parking permits"', rv['Reason'])
        self.assertIn('Ray Colton: Can you renew', p['moves']); self.assertIn('to-do: Renew the parking permits', p['moves'])
        self.assertEqual(len(self.s.list_messages(self.tid)), 2, 'nothing moves before the press')

    def test_the_press_runs_the_split(self):
        rv, _ = self.queue()
        out = verdicts.decide(self.s, rv, 'approve')
        self.assertTrue(out['ok'], out)
        new = out['result']['task']
        self.assertEqual([m['MessageId'] for m in self.s.list_messages(new)], [self.other])
        self.assertEqual([m['MessageId'] for m in self.s.list_messages(self.tid)], [self.fix])
        self.assertEqual(([i['id'] for i in self.s.task_checklist(new)], [i['id'] for i in self.s.task_checklist(self.tid)]), (['b2'], ['a1']))
        self.assertEqual(self.s.get_task(new)['Title'], 'Renew the parking permits')
        self.assertTrue(any('split part of it off' in what for _, _, what, *_ in general.presses(self.s, self.tid)), 'its agent hears the press')

    def test_what_is_not_on_the_task_is_refused_with_the_way_on(self):
        for kw, said in (({'messages': ['m99999'], 'items': []}, 'not on this task'), ({'messages': [], 'items': []}, 'needs what goes'),
                         ({'messages': [self.fix, self.other]}, 'every message'), ({'title': ''}, 'needs title')):
            with self.subTest(kw):
                rv, why = self.queue(**kw)
                self.assertIsNone(rv); self.assertIn(said, why[0])

    def test_a_message_gone_by_the_press_moves_nothing(self):
        rv, _ = self.queue()
        self.s.attach_message(self.other, Factory(self.s).task('Parking'))
        out = verdicts.decide(self.s, rv, 'approve')
        self.assertEqual((out['ok'], out['status']), (False, 'pending')); self.assertIn('not on this task', out['send_error'])
        self.assertEqual([i['id'] for i in self.s.task_checklist(self.tid)], ['a1', 'b2'])

    def test_the_agent_is_told_it_can(self):
        self.assertIn('break_out', agenttools.TOOLS['propose'][1])
        self.assertIn('"action": "break_out"', general.action_line(self.s))


class TheOwnersWordsInAnEmptyBox(Acts):
    def test_typed_over_a_merge_with_no_summary_they_are_its_body(self):
        from taskuary import ci, ghcloseout, github, outcomes
        rv = self.action({'action': 'merge_pr', 'repo': 'northwind/ledger', 'number': 12, 'sha': 'f0ce6ca', 'closeout': True})
        seen = {'pr': {'sha': 'f0ce6ca', 'url': SAID}, 'state': 'open', 'ok': True, 'offers': [], 'method': 'squash', 'note': '', 'reason': ''}
        went = []
        def merge(secret, repo, num, sha, title, body, **kw): went.append(body); return 'f0ce6ca0000'
        with mock.patch.object(proposals, 'validate', return_value=(True, '')), mock.patch.object(ci, '_conn', return_value={'Secret': 'x'}), \
             mock.patch.object(ghcloseout, 'assess', return_value=seen), mock.patch.object(github, 'merge_pr', merge), \
             mock.patch.object(ci, 'pr_of', return_value=None), mock.patch.object(outcomes, 'record'):
            proposals.execute(self.s, rv, 'owner', 'Export keeps its header row')
            proposals.execute(self.s, rv, 'owner', rv['DraftText'])          # the box untouched: as proposed, GitHub writes the message
        self.assertEqual(went, ['Export keeps its header row', None])


if __name__ == '__main__': unittest.main()
