"""The close-out (the owner, 2026-09-27: "it's not closed until then"): what finishes a task depends on where it
lives. A finished agent's open pull request waits for Merge, a task from an issue for Close issue - each a
yes-gated review, and the task is not done until it is answered. See docs/how-a-task-ends.md, The close-out."""
import json, unittest
from unittest import mock

from taskuary import ci, coder, concierge, github, proposals, verdicts
from taskuary.store import MemoryStore

OPEN = {'number': 7, 'url': 'https://github.com/northwind/ledger/pull/7', 'head': 'fix-export', 'sha': 'abc1234def',
        'state': 'open', 'draft': True, 'merged': False, 'mergeable': True, 'node_id': 'PR_x'}
GREEN = {'state': 'success', 'total': 1, 'pending': 0, 'failed': []}


def armed(s, tracker=False):
    cid = s.get_connector_by_type('github')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'ghp_x', 'Active': 1, 'ConfigJson': json.dumps({'use_as_tracker': tracker})}, 't')
    s.set_setting('agent_push_enabled', '1', 't')
    return s


def with_pr(s, **over):
    tid = s.create_task({'Title': 'Fix the nightly export', 'Kind': 'coding', 'Status': 'in_progress', **over}, 'triage')
    ci._save_pr(s, tid, {'number': 7, 'url': OPEN['url'], 'head': 'fix-export', 'base': 'main', 'state': 'open',
                         'repo': 'northwind/ledger', 'sha': 'abc1234def'})
    return tid


def finish(s, tid, pr=OPEN, **kw):
    prev, coder.REFRESH = coder.REFRESH, None
    try:
        with mock.patch('taskuary.responder.write_draft', return_value='Fixed - it runs tonight.'), \
             mock.patch.object(github, 'pr', return_value=pr):
            return coder.finish(s, tid, {'summary': 'the export reads the new view', 'outcome': 'did_work'}, None, 'coder', **kw)
    finally: coder.REFRESH = prev


def pending(s, tid): return [r for r in s._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending'", (tid,))]


class MergeCloseOutTests(unittest.TestCase):
    def test_a_finished_agent_with_an_open_pull_request_waits_for_merge(self):
        s = armed(MemoryStore()); tid = with_pr(s)
        out = finish(s, tid)
        self.assertEqual((out['closeout'], s.get_task(tid)['Status']), ('merge_pr', 'waiting'))
        rv = proposals.closeout_pending(s, tid)
        p = json.loads(rv['DraftText'])
        self.assertEqual((p['action'], p['repo'], p['number']), ('merge_pr', 'northwind/ledger', 7))
        self.assertIn('the export reads the new view', p['text'])        # the summary is the card's text

    def test_merge_squashes_the_reviewed_head_and_closes_the_task(self):
        s = armed(MemoryStore()); tid = with_pr(s); finish(s, tid)
        rv = proposals.closeout_pending(s, tid)
        with mock.patch.object(github, 'pr', return_value=OPEN), mock.patch.object(github, 'checks', return_value=GREEN), \
             mock.patch.object(github, 'merge_pr', return_value='merged123') as merge:
            out = verdicts.decide(s, rv, 'approve', final_text='Edited summary')
        self.assertTrue(out['ok'], out)
        args = merge.call_args[0]
        self.assertEqual((args[1], args[2], args[3], args[5]), ('northwind/ledger', 7, 'abc1234def', 'Edited summary'))
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        self.assertTrue(ci.pr_of(s, tid)['merged'])

    def test_the_merge_pins_the_head_the_card_was_raised_on(self):
        s = armed(MemoryStore()); tid = with_pr(s); finish(s, tid, pr={**OPEN, 'sha': 'agentslast'})
        with mock.patch.object(github, 'pr', return_value={**OPEN, 'sha': 'pushedlater'}), mock.patch.object(github, 'checks', return_value=GREEN), \
             mock.patch.object(github, 'merge_pr', return_value='m') as merge:
            verdicts.decide(s, proposals.closeout_pending(s, tid), 'approve')
        self.assertEqual(merge.call_args[0][3], 'agentslast')           # GitHub answers 409, never merges the later push

    def test_a_pr_already_merged_is_not_offered(self):
        s = armed(MemoryStore()); tid = with_pr(s)
        self.assertIsNone(finish(s, tid, pr={**OPEN, 'state': 'closed', 'merged': True})['closeout'])
        self.assertEqual(s.get_task(tid)['Status'], 'done')

    def test_red_checks_refuse_the_merge_and_the_task_stays(self):
        s = armed(MemoryStore()); tid = with_pr(s); finish(s, tid)
        red = {'state': 'failure', 'total': 1, 'pending': 0, 'failed': [{'name': 'ci / test', 'url': 'u', 'summary': ''}]}
        with mock.patch.object(github, 'pr', return_value=OPEN), mock.patch.object(github, 'checks', return_value=red), \
             mock.patch.object(github, 'merge_pr') as merge:
            out = verdicts.decide(s, proposals.closeout_pending(s, tid), 'approve')
        merge.assert_not_called()
        self.assertFalse(out['ok']); self.assertIn('ci / test', out['send_error'])
        self.assertEqual(s.get_task(tid)['Status'], 'waiting')
        self.assertTrue(proposals.closeout_pending(s, tid))

    def test_not_yet_keeps_it_open_and_a_merge_on_github_then_closes_it(self):
        s = armed(MemoryStore()); tid = with_pr(s); finish(s, tid)
        verdicts.decide(s, proposals.closeout_pending(s, tid), 'reject')
        self.assertEqual(s.get_task(tid)['Status'], 'open')
        with mock.patch.object(github, 'pr', return_value={**OPEN, 'state': 'closed', 'merged': True}):
            self.assertTrue(ci.pr_ended(s, tid, ci.landing_of(s, tid)))
        self.assertEqual(s.get_task(tid)['Status'], 'done')

    def test_merging_on_github_answers_a_pending_close_out(self):
        s = armed(MemoryStore()); tid = with_pr(s); finish(s, tid)
        with mock.patch.object(github, 'pr', return_value={**OPEN, 'state': 'closed', 'merged': True}):
            ci.pr_ended(s, tid, ci.landing_of(s, tid))
        self.assertEqual((pending(s, tid), s.get_task(tid)['Status']), ([], 'done'))

    def test_a_pr_nobody_offered_to_merge_is_not_polled(self):
        s = armed(MemoryStore()); tid = with_pr(s)
        with mock.patch.object(github, 'pr') as look:
            self.assertFalse(ci.pr_ended(s, tid, ci.landing_of(s, tid)))
        look.assert_not_called()

    def test_mark_done_and_a_saved_session_keep_the_old_ending(self):
        s = armed(MemoryStore()); tid = with_pr(s)
        self.assertIsNone(finish(s, tid, owner_done=True)['closeout'])
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        s = armed(MemoryStore()); tid = with_pr(s)
        finish(s, tid, keep_open=True)
        self.assertIsNone(proposals.closeout_pending(s, tid))

    def test_the_close_out_is_the_owners_act_so_agent_switches_do_not_hide_it(self):
        s = armed(MemoryStore()); s.set_setting('agent_push_enabled', '0', 't'); tid = with_pr(s)
        finish(s, tid)
        self.assertEqual(s.get_task(tid)['Status'], 'waiting')
        self.assertTrue(proposals.closeout_pending(s, tid))

    def test_close_pr_closes_it_unmerged_and_ends_the_task(self):
        s = armed(MemoryStore()); tid = with_pr(s); finish(s, tid)
        rv = proposals.closeout_pending(s, tid)
        with mock.patch.object(github, 'pr', return_value=OPEN), mock.patch.object(github, 'close_pr') as close, \
             mock.patch.object(github, 'merge_pr') as merge:
            out = verdicts.decide(s, rv, 'close_pr')
        self.assertTrue(out['ok'], out)
        close.assert_called_once_with('ghp_x', 'northwind/ledger', 7); merge.assert_not_called()
        self.assertEqual((s.get_review(rv['ReviewId'])['Status'], s.get_task(tid)['Status']), ('rejected', 'done'))
        self.assertFalse(ci.pr_of(s, tid)['merged'])

    def test_close_pr_on_a_reply_is_refused(self):
        s = MemoryStore(); tid = s.create_task({'Title': 't', 'Status': 'waiting'}, 't')
        rid = s.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Hi'})
        self.assertFalse(verdicts.decide(s, s.get_review(rid), 'close_pr')['ok'])
        self.assertEqual(s.get_review(rid)['Status'], 'pending')

    def test_an_agent_cannot_propose_the_merge_itself(self):
        self.assertEqual(proposals.parse('TASKUARY-PROPOSE {"action": "merge_pr", "repo": "o/r", "number": 1}'), [])


class ReplyAndCloseOutTests(unittest.TestCase):
    def _both(self):
        s = armed(MemoryStore()); tid = with_pr(s)
        s.add_message({'TaskId': tid, 'ExternalId': 'm1', 'Channel': 'email', 'Subject': 'Export broken', 'FromName': 'Erin Blake',
                       'FromEmail': 'erin@northwind.example', 'BodyText': 'The nightly export is empty - can you fix it?', 'Status': 'routed'})
        finish(s, tid)
        return s, tid

    def test_both_wait_and_the_merge_is_shown_first(self):
        s, tid = self._both()
        kinds = sorted(r['Kind'] for r in pending(s, tid))
        self.assertEqual(kinds, ['action', 'draft_reply'])
        self.assertEqual(s.pending_review(tid, live_only=False)['Kind'], 'action')     # the newest leads

    def test_a_sent_reply_does_not_close_over_a_waiting_merge(self):
        s, tid = self._both()
        reply = next(r for r in pending(s, tid) if r['Kind'] == 'draft_reply')
        verdicts._settle_task_after_sent_reply(s, reply, 'owner', True)
        self.assertEqual(s.get_task(tid)['Status'], 'waiting')
        self.assertTrue(proposals.closeout_pending(s, tid))

    def test_the_merge_leaves_the_reply_waiting(self):
        s, tid = self._both()
        with mock.patch.object(github, 'pr', return_value=OPEN), mock.patch.object(github, 'checks', return_value=GREEN), \
             mock.patch.object(github, 'merge_pr', return_value='m'):
            verdicts.decide(s, proposals.closeout_pending(s, tid), 'approve')
        self.assertNotEqual(s.get_task(tid)['Status'], 'done')
        self.assertEqual([r['Kind'] for r in pending(s, tid)], ['draft_reply'])


class OnePressTests(unittest.TestCase):
    """Merge & send (the owner, 2026-09-27: "shouldn't we combine this?"): the act first, the reply only after it."""
    def _both(self):
        s = armed(MemoryStore()); tid = with_pr(s); finish(s, tid)
        reply = s.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Thanks - approving.'})
        return s, tid, reply

    def test_merge_and_send_merges_then_sends_the_edited_reply(self):
        s, tid, reply = self._both()
        with mock.patch.object(github, 'pr', return_value=OPEN), mock.patch.object(github, 'checks', return_value=GREEN), \
             mock.patch.object(github, 'merge_pr', return_value='m') as merge:
            out = verdicts.decide(s, proposals.closeout_pending(s, tid), 'approve', reply_text='Thanks - merged.')
        merge.assert_called_once()
        self.assertTrue(out['ok'] and out['reply']['ok'], out)
        self.assertEqual((s.get_review(reply)['Status'], s.get_review(reply)['FinalText']), ('edited', 'Thanks - merged.'))

    def test_a_refused_merge_sends_nothing(self):
        s, tid, reply = self._both()
        red = {'state': 'failure', 'total': 1, 'pending': 0, 'failed': [{'name': 'ci / test', 'url': 'u', 'summary': ''}]}
        with mock.patch.object(github, 'pr', return_value=OPEN), mock.patch.object(github, 'checks', return_value=red):
            out = verdicts.decide(s, proposals.closeout_pending(s, tid), 'approve', reply_text='Thanks - merged.')
        self.assertFalse(out['ok']); self.assertNotIn('reply', out)
        self.assertEqual(s.get_review(reply)['Status'], 'pending')

    def test_not_yet_leaves_the_reply_unsent(self):
        s, tid, reply = self._both()
        verdicts.decide(s, proposals.closeout_pending(s, tid), 'reject', reply_text=None)
        self.assertEqual((s.get_review(reply)['Status'], s.get_task(tid)['Status']), ('pending', 'open'))

    def _github_reply(self, s, tid):
        mid = s.add_message({'TaskId': tid, 'ExternalId': 'gh:northwind/ledger#7', 'Channel': 'github', 'Subject': 'Fix export',
                             'FromName': 'omarkeller', 'FromEmail': 'omarkeller@users.noreply.github.com', 'BodyText': 'please review',
                             'Status': 'routed'})
        return s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Thanks - approving.'})

    def test_the_merge_carries_a_github_reply_as_its_comment_with_replies_off(self):
        """TQ-0780: "GitHub replies are off" refused the thank-you; it is the PR comment the close-out posts."""
        s = armed(MemoryStore()); tid = with_pr(s); finish(s, tid)
        reply = self._github_reply(s, tid)
        with mock.patch.object(github, 'pr', return_value=OPEN), mock.patch.object(github, 'checks', return_value=GREEN), \
             mock.patch.object(github, 'merge_pr', return_value='m') as merge, \
             mock.patch.object(github, 'comment_issue', return_value='https://github.com/northwind/ledger/pull/7#c1') as say:
            out = verdicts.decide(s, proposals.closeout_pending(s, tid), 'approve', reply_text='Thanks - merged.')
        self.assertTrue(out['ok'] and out['reply']['ok'], out)
        self.assertEqual(say.call_args[0][1:], ('northwind/ledger', 7, 'Thanks - merged.'))
        merge.assert_called_once()
        self.assertEqual((s.get_review(reply)['Status'], s.get_task(tid)['Status']), ('edited', 'done'))

    def test_red_checks_say_so_and_merge_anyway_overrules_them(self):
        s = armed(MemoryStore()); tid = with_pr(s); finish(s, tid)
        reply = self._github_reply(s, tid)
        red = {'state': 'failure', 'total': 1, 'pending': 0, 'failed': [{'name': 'browser', 'url': 'u', 'summary': ''}]}
        with mock.patch.object(github, 'pr', return_value=OPEN), mock.patch.object(github, 'checks', return_value=red), \
             mock.patch.object(github, 'merge_pr', return_value='m') as merge, mock.patch.object(github, 'comment_issue', return_value='u') as say:
            out = verdicts.decide(s, proposals.closeout_pending(s, tid), 'approve', reply_text='Thanks - merged.')
            self.assertTrue(out['checks_red']); merge.assert_not_called(); say.assert_not_called()
            out = verdicts.decide(s, proposals.closeout_pending(s, tid), 'merge_anyway', reply_text='Thanks - merged.')
        self.assertTrue(out['ok'], out); merge.assert_called_once(); say.assert_called_once()
        self.assertEqual((s.get_review(reply)['Status'], s.get_task(tid)['Status']), ('edited', 'done'))

    def test_a_close_out_card_does_not_say_the_agent_proposed_it(self):
        s, tid, _ = self._both()
        self.assertEqual(proposals.closeout_pending(s, tid)['Reason'], 'closes the task: merge pull request #7')


class IssueCloseOutTests(unittest.TestCase):
    def test_a_task_from_an_issue_waits_to_close_it_with_a_comment(self):
        s = armed(MemoryStore(), tracker=True)
        tid = s.create_task({'Title': 'Export is empty', 'Kind': 'coding', 'Status': 'in_progress',
                             'SourceRef': 'https://github.com/northwind/ledger/issues/12'}, 'triage')
        self.assertEqual(finish(s, tid)['closeout'], 'close_issue')
        rv = proposals.closeout_pending(s, tid)
        with mock.patch.object(github, 'close_issue') as close:
            self.assertTrue(verdicts.decide(s, rv, 'approve', final_text='Fixed in the nightly run.')['ok'])
        self.assertEqual(close.call_args[0][1:], ('northwind/ledger', 12, 'Fixed in the nightly run.'))
        self.assertEqual(s.get_task(tid)['Status'], 'done')

    def test_the_tracker_switch_does_not_hide_the_issue_close_out(self):
        s = armed(MemoryStore(), tracker=False)
        tid = s.create_task({'Title': 'Export is empty', 'Kind': 'coding', 'Status': 'in_progress',
                             'SourceRef': 'https://github.com/northwind/ledger/issues/12'}, 'triage')
        self.assertEqual(finish(s, tid)['closeout'], 'close_issue')


class ContributorPullRequestTests(unittest.TestCase):
    """The task came FROM somebody else's PR (the owner, 2026-09-27: "don't see the merge PR button?")."""
    REF = 'https://github.com/northwind/ledger/pull/84'

    def _reviewed(self, s, status='in_progress'):
        return s.create_task({'Title': 'Review startup crash-output PR', 'Kind': 'coding', 'Status': status, 'SourceRef': self.REF}, 'triage')

    def test_a_reviewed_contributor_pr_waits_for_merge_without_the_push_switch(self):
        s = armed(MemoryStore()); s.set_setting('agent_push_enabled', '0', 't'); tid = self._reviewed(s)
        self.assertEqual(finish(s, tid, pr={**OPEN, 'number': 84})['closeout'], 'merge_pr')
        p = json.loads(proposals.closeout_pending(s, tid)['DraftText'])
        self.assertEqual((p['repo'], p['number'], p['text'], p.get('theirs')), ('northwind/ledger', 84, '', True))
        with mock.patch.object(github, 'pr', return_value={**OPEN, 'number': 84}), mock.patch.object(github, 'checks', return_value=GREEN), \
             mock.patch.object(github, 'merge_pr', return_value='m') as merge:
            self.assertTrue(verdicts.decide(s, proposals.closeout_pending(s, tid), 'approve')['ok'])
        self.assertEqual((merge.call_args[0][2], merge.call_args[0][4]), (84, None))    # GitHub titles the squash
        self.assertIsNone(ci.pr_of(s, tid))                                               # no "we opened it" mark invented

    def test_a_task_finished_before_the_close_out_existed_is_offered_it_once(self):
        s = armed(MemoryStore()); tid = self._reviewed(s, 'waiting')
        s.add_comment(tid, 'coder', 'agent', 'The agent closed this itself: PR #84 reviewed: accept')
        with mock.patch.object(github, 'pr', return_value={**OPEN, 'number': 84}):
            self.assertEqual(proposals.backfill(s), 1)
            verdicts.decide(s, proposals.closeout_pending(s, tid), 'reject')
            self.assertEqual(proposals.backfill(s), 0)                                      # "not yet" is not asked again
        self.assertIsNone(proposals.closeout_pending(s, tid))

    def test_a_saved_session_that_drafted_its_reply_gets_the_merge_too(self):
        """TQ-0767: Save and end session wrote "Merging this one." - the answer says the work is done."""
        s = armed(MemoryStore()); tid = self._reviewed(s)
        s.add_message({'TaskId': tid, 'ExternalId': 'gh-74', 'Channel': 'email', 'Subject': 'PR', 'FromName': 'Omar Keller',
                       'FromEmail': 'omar@vendor.example', 'BodyText': 'Adds tests for _cut', 'Status': 'routed'})
        self.assertEqual(finish(s, tid, pr={**OPEN, 'number': 84}, keep_open=True)['closeout'], 'merge_pr')
        self.assertEqual(s.get_task(tid)['Status'], 'in_progress')                       # a saved session still leaves the status alone

    def test_an_open_saved_task_with_its_reply_ready_is_backfilled(self):
        s = armed(MemoryStore()); tid = self._reviewed(s, 'open')
        s.add_comment(tid, 'coder', 'agent', 'CODER REPORT\nDetermination: accept')
        s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Merging this one.'})
        with mock.patch.object(github, 'pr', return_value={**OPEN, 'number': 84}):
            self.assertEqual(proposals.backfill(s), 1)

    def test_an_open_task_without_a_reply_is_not_backfilled(self):
        s = armed(MemoryStore()); tid = self._reviewed(s, 'open')
        s.add_comment(tid, 'coder', 'agent', 'CODER REPORT\nDetermination: half done')
        with mock.patch.object(github, 'pr', return_value={**OPEN, 'number': 84}):
            self.assertEqual(proposals.backfill(s), 0)

    def test_an_agent_cannot_mark_its_own_ask_as_a_close_out(self):
        ps = proposals.parse('TASKUARY-PROPOSE {"action": "close_issue", "closeout": true}')
        self.assertNotIn('closeout', ps[0])
        self.assertFalse(proposals.validate(MemoryStore(), ps[0])[0])                     # the tracker switch still gates it

    def test_your_merge_closes_the_task_and_retires_the_unsent_thank_you(self):
        """Merged is finished (the owner, 2026-09-28: "if they were merged in, they should just close")."""
        from taskuary import channels
        s = armed(MemoryStore()); tid = self._reviewed(s, 'waiting')
        rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Thanks - merged.'})
        channels.close_upstream_ended(s, tid, 'You merged this pull request on GitHub.', 'merged', 'owner')
        self.assertEqual(s.get_task(tid)['Status'], 'done'); self.assertNotEqual(s.get_review(rid)['Status'], 'pending')


class ResumeNoteTests(unittest.TestCase):
    def test_the_owners_note_leads_the_resume(self):
        from taskuary import terminal
        seed = terminal.resume_seed('merge it please')
        self.assertTrue(seed.startswith('FROM THE OWNER: merge it please'))


class HeldPullRequestWordsTests(unittest.TestCase):
    def test_a_first_time_contributor_hold_says_a_free_slot_will_not_start_it(self):
        from taskuary import ingest
        s = MemoryStore()
        s.save_source({'Channel': 'github', 'Address': 'northwind/ledger', 'ConfigJson': json.dumps({'auto': 'contributors'})}, 't')
        why = ingest.gh_hold_why(s, {'source_name': 'northwind/ledger',
                                     'body': '[pull request by someone - association: FIRST_TIME_CONTRIBUTOR]\nFix'})
        self.assertIn('a first-time contributor', why); self.assertIn('the team and past contributors', why)
        self.assertIn('press Start', why); self.assertIn('free slot will not start it', why)


class WordsTests(unittest.TestCase):
    def test_the_walk_offers_merge_not_run_it_and_never_not_ours(self):
        item = {'kind': 'action', 'lane': 'approve', 'rid': 1, 'tid': 1, 'mid': 1, 'closeout': proposals.CLOSEOUT['merge_pr'], 'title': 'Fix the nightly export'}
        labels = [c['label'] for c in concierge.chips_for(MemoryStore(), item)]
        self.assertIn('Close out', labels)
        # ONE word whatever the system and whether a reply rides along - only the sentence under it says what it does
        self.assertIn('Close out', [c['label'] for c in concierge.chips_for(MemoryStore(), {**item, 'rides': True})])
        from taskuary import remote_assistant
        line = remote_assistant.then_line({'chips': [{'verb': 'approve', 'label': 'Close out'}], 'item': {**item, 'rides': True}}, MemoryStore())
        self.assertEqual(line, 'Close out: merges the pull request on GitHub, then posts the reply above as its comment.')
        self.assertNotIn('Run it', labels); self.assertNotIn('Not ours', labels)


if __name__ == '__main__': unittest.main()
