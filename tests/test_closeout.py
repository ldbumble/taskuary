"""The close-out (the owner, 2026-09-27: "it's not closed until then"): what finishes a task depends on where it
lives. A finished agent's open pull request waits for Merge, a task from an issue for Close issue - each a
yes-gated review, and the task is not done until it is answered. See docs/how-a-task-ends.md, The close-out."""
import json, unittest
from unittest import mock

from taskuary import ci, coder, concierge, github, proposals, verdicts
from taskuary.store import MemoryStore

OPEN = {'number': 7, 'url': 'https://github.com/northwind/ledger/pull/7', 'head': 'fix-export', 'sha': 'abc1234def',
        'state': 'open', 'draft': True, 'merged': False, 'mergeable': True, 'node_id': 'PR_x',
        'mergeable_state': 'clean', 'base': 'main', 'maintainer_can_modify': True, 'same_repo': False}
GREEN = {'state': 'success', 'total': 1, 'pending': 0, 'failed': []}
RED = {'state': 'failure', 'total': 1, 'pending': 0, 'failed': [{'name': 'ci / test', 'url': 'u', 'summary': ''}]}
# what GitHub says about the repository: the merge methods it allows and the token's role there
REPO = {'methods': ['squash', 'merge', 'rebase'], 'permissions': {'push': True}, 'default_branch': 'main'}
_repo = mock.patch.object(github, 'repo_info', return_value=REPO)
# ...and what the TOKEN may do there (github.grants): every grant, unless a test takes one away
GRANTS = {'contents': True, 'pull_requests': True, 'issues': True, 'actions': True}
_grants = mock.patch.object(github, 'grants', return_value=GRANTS)
def setUpModule(): _repo.start(); _grants.start()
def tearDownModule(): _repo.stop(); _grants.stop()


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


def closeout_setting(s, repo=None, **choices):
    """The GitHub card's Close out choices - on the connection, or one repository's override."""
    if repo:
        s.save_source({'Channel': 'github', 'Address': repo, 'ConfigJson': json.dumps({'closeout': choices})}, 't')
        return
    c = s.get_connector_by_type('github')
    cfg = json.loads(c.get('ConfigJson') or '{}'); cfg['closeout'] = {**cfg.get('closeout', {}), **choices}
    s.save_connector({'ConnectorId': c['ConnectorId'], 'ConfigJson': json.dumps(cfg)}, 't')


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
        # the repository's own rules block it (GitHub says "blocked"), with a required check red
        with mock.patch.object(github, 'pr', return_value={**OPEN, 'mergeable_state': 'blocked'}), mock.patch.object(github, 'checks', return_value=RED), \
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
        with mock.patch.object(github, 'pr', return_value={**OPEN, 'mergeable_state': 'blocked'}), mock.patch.object(github, 'checks', return_value=RED):
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
        """Red checks the repository does NOT require ("unstable"), with the card set to "stop and ask": the card says so
        and Close out anyway merges past them - the reply rides along."""
        s = armed(MemoryStore()); tid = with_pr(s); finish(s, tid)
        closeout_setting(s, red='ask')
        reply = self._github_reply(s, tid)
        with mock.patch.object(github, 'pr', return_value={**OPEN, 'mergeable_state': 'unstable'}), mock.patch.object(github, 'checks', return_value=RED), \
             mock.patch.object(github, 'merge_pr', return_value='m') as merge, mock.patch.object(github, 'comment_issue', return_value='u') as say:
            out = verdicts.decide(s, proposals.closeout_pending(s, tid), 'approve', reply_text='Thanks - merged.')
            self.assertTrue(out['refused']); self.assertIn('anyway', out['offers'])
            merge.assert_not_called(); say.assert_not_called()
            out = verdicts.decide(s, proposals.closeout_pending(s, tid), 'merge_anyway', reply_text='Thanks - merged.')
        self.assertTrue(out['ok'], out); merge.assert_called_once(); say.assert_called_once()
        self.assertEqual((s.get_review(reply)['Status'], s.get_task(tid)['Status']), ('edited', 'done'))


    def test_close_out_pressed_on_the_reply_card_runs_the_merge_too(self):
        """The phone and the walk put the task's REPLY on the table (TQ-0777): its Close out sent the reply alone and
        never merged. It runs the task's close-out, the reply riding as its comment."""
        s = armed(MemoryStore()); tid = with_pr(s); finish(s, tid)
        reply = self._github_reply(s, tid)
        with mock.patch.object(github, 'pr', return_value=OPEN), mock.patch.object(github, 'checks', return_value=GREEN), \
             mock.patch.object(github, 'merge_pr', return_value='m') as merge, mock.patch.object(github, 'comment_issue', return_value='u') as say:
            out = verdicts.decide(s, s.get_review(reply), 'approve')
        self.assertTrue(out['ok'], out); merge.assert_called_once()
        self.assertEqual(say.call_args[0][3], 'Thanks - approving.')
        self.assertEqual((s.get_review(reply)['Status'], s.get_task(tid)['Status']), ('approved', 'done'))

    def test_the_phone_shows_the_reply_a_finished_agent_wrote(self):
        """`draft_reply` (the agent's own) was never read, so WhatsApp asked for a yes to a reply it did not show."""
        from taskuary import remote_assistant
        s = armed(MemoryStore()); tid = with_pr(s); finish(s, tid)
        reply = self._github_reply(s, tid)
        self.assertEqual(remote_assistant._draft_text(s, {'rid': reply}), 'Thanks - approving.')
        co = proposals.closeout_pending(s, tid)
        self.assertEqual(remote_assistant._draft_text(s, {'rid': co['ReviewId'], 'closeout': 'x'}), 'Thanks - approving.')

    def test_the_phone_never_shows_the_line_triage_reads(self):
        from taskuary import remote_assistant
        said = remote_assistant._plain('[pull request by omarkeller - association: CONTRIBUTOR]\nFixes the export')
        self.assertEqual(said, 'Fixes the export')

    def test_a_close_out_card_does_not_say_the_agent_proposed_it(self):
        s, tid, _ = self._both()
        self.assertEqual(proposals.closeout_pending(s, tid)['Reason'], 'closes the task: merge pull request #7')


class GithubStateTests(unittest.TestCase):
    """THE CARD'S BUTTONS COME FROM GITHUB'S READING of this pull request under this repository's rules (the owner,
    2026-09-28: "the close out should use api to get the state of the pr and have the correct buttons")."""
    def _seen(self, s, **pr):
        from taskuary import ghcloseout
        with mock.patch.object(github, 'pr', return_value={**OPEN, **pr}), mock.patch.object(github, 'checks', return_value=RED):
            return ghcloseout.assess(s, 'northwind/ledger', 7)

    def test_red_checks_the_repo_does_not_require_merge_with_a_note_by_default(self):
        seen = self._seen(armed(MemoryStore()), mergeable_state='unstable')
        self.assertTrue(seen['ok']); self.assertIn('ci / test', seen['note']); self.assertEqual(seen['offers'], ['rerun'])

    def test_blocked_offers_re_run_and_anyway_only_for_an_admin_who_turned_it_on(self):
        s = armed(MemoryStore())
        self.assertEqual(self._seen(s, mergeable_state='blocked')['offers'], ['rerun'])
        closeout_setting(s, anyway=True)
        self.assertEqual(self._seen(s, mergeable_state='blocked')['offers'], ['rerun'])            # not an admin here
        with mock.patch.object(github, 'repo_info', return_value={**REPO, 'permissions': {'admin': True}}):
            self.assertEqual(self._seen(s, mergeable_state='blocked')['offers'], ['rerun', 'anyway'])

    def test_behind_offers_update_branch_only_when_the_author_allows_it(self):
        s = armed(MemoryStore())
        self.assertEqual(self._seen(s, mergeable_state='behind')['offers'], ['update'])
        seen = self._seen(s, mergeable_state='behind', maintainer_can_modify=False)
        self.assertEqual(seen['offers'], []); self.assertIn('has not allowed maintainers', seen['reason'])

    def test_conflicts_say_so_and_offer_nothing(self):
        seen = self._seen(armed(MemoryStore()), mergeable_state='dirty')
        self.assertFalse(seen['ok']); self.assertIn('merge conflicts', seen['reason']); self.assertEqual(seen['offers'], [])

    def test_the_merge_method_is_the_setting_when_the_repo_allows_it_else_the_repos(self):
        s = armed(MemoryStore()); closeout_setting(s, method='rebase')
        self.assertEqual(self._seen(s)['method'], 'rebase')
        with mock.patch.object(github, 'repo_info', return_value={**REPO, 'methods': ['merge']}):
            self.assertEqual(self._seen(s)['method'], 'merge')

    def test_a_repository_overrides_the_connection(self):
        from taskuary import ghcloseout
        s = armed(MemoryStore()); closeout_setting(s, method='rebase'); closeout_setting(s, repo='northwind/ledger', method='merge')
        self.assertEqual((ghcloseout.cfg(s, 'northwind/ledger')['method'], ghcloseout.cfg(s, 'northwind/portal')['method']), ('merge', 'rebase'))

    def test_task_only_raises_no_merge_card(self):
        s = armed(MemoryStore()); closeout_setting(s, pr='task'); tid = with_pr(s)
        self.assertIsNone(finish(s, tid)['closeout'])

    def test_blocked_refuses_even_close_out_anyway_when_it_is_not_offered(self):
        s = armed(MemoryStore()); tid = with_pr(s); finish(s, tid)
        with mock.patch.object(github, 'pr', return_value={**OPEN, 'mergeable_state': 'blocked'}), mock.patch.object(github, 'checks', return_value=RED), \
             mock.patch.object(github, 'merge_pr') as merge:
            out = verdicts.decide(s, proposals.closeout_pending(s, tid), 'merge_anyway')
        merge.assert_not_called(); self.assertFalse(out['ok'])

    def test_the_card_reads_its_state_and_update_branch_runs_only_when_offered(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = armed(MemoryStore()); tid = with_pr(s); finish(s, tid)
        rid = proposals.closeout_pending(s, tid)['ReviewId']
        with mock.patch.object(server, 'store', s), mock.patch.object(github, 'checks', return_value=RED), \
             mock.patch.object(github, 'update_branch', return_value='Updating pull request branch.') as upd:
            c = TestClient(server.app)
            with mock.patch.object(github, 'pr', return_value={**OPEN, 'mergeable_state': 'behind'}):
                st = c.get(f'/api/reviews/{rid}/closeout').json()
                self.assertEqual((st['ok'], st['offers']), (False, ['update']))
                self.assertEqual(c.post(f'/api/reviews/{rid}/closeout/update').status_code, 200)
                self.assertEqual(c.post(f'/api/reviews/{rid}/closeout/rerun').status_code, 422)     # not offered
        upd.assert_called_once()


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


    def test_a_task_the_old_rule_held_open_is_closed_at_startup(self):
        """The poll reads only items changed since it ran: a PR merged before the fix is never read again (2026-09-28)."""
        from taskuary import channels
        s = armed(MemoryStore()); tid = self._reviewed(s, 'waiting'); other = self._reviewed(s, 'waiting')
        rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Thanks - merged.'})
        s.add_comment(tid, 'router', 'agent', 'You merged this pull request on GitHub (org/app#7), so there is nothing left to do here.')
        self.assertEqual(channels.heal_upstream_ended(s), [tid])
        self.assertEqual(s.get_task(tid)['Status'], 'done'); self.assertNotEqual(s.get_review(rid)['Status'], 'pending')
        self.assertEqual(s.get_task(other)['Status'], 'waiting')                    # a PR still open is left alone
        # ...and the next launch leaves it be: done today is still on the Board's list, and it was re-closed - a fresh
        # AI wrap-up and two comments - on every start (the owner, 2026-09-28: startup took over a minute)
        n = len(s.list_comments(tid))
        self.assertEqual(channels.heal_upstream_ended(s), [])
        self.assertEqual(len(s.list_comments(tid)), n)


    def test_a_merged_pr_from_the_issues_list_says_merged(self):
        """The issues list puts a PR's merge under pull_request.merged_at; it read as "closed" (2026-09-28)."""
        from unittest import mock
        from taskuary import channels
        s = armed(MemoryStore()); tid = self._reviewed(s, 'waiting')
        item = {'number': 7, 'pull_request': {'merged_at': '2026-09-28T00:00:00Z'}}
        with mock.patch.object(s, 'task_for_conversation', return_value=tid):
            channels._gh_ended(s, item, 'gh:org/app#7', 'org/app')
        self.assertTrue(any('was merged on GitHub' in c['Body'] for c in s.list_comments(tid)))


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
        self.assertIn('Merge & close', labels)                  # the button says its act (2026-10-06)
        # the same word whether a reply rides along - the sentence under it says the reply goes too
        self.assertIn('Merge & close', [c['label'] for c in concierge.chips_for(MemoryStore(), {**item, 'rides': True})])
        from taskuary import remote_assistant
        line = remote_assistant.then_line({'chips': [{'verb': 'approve', 'label': 'Close out'}], 'item': {**item, 'rides': True}}, MemoryStore())
        self.assertEqual(line, 'Close out: merges the pull request on GitHub, then posts the reply above as its comment.')
        self.assertNotIn('Run it', labels); self.assertNotIn('Not ours', labels)


class TokenGrantTests(unittest.TestCase):
    """THE TOKEN'S GRANTS, NOT THE USER'S ROLE (2026-09-29): a fine-grained token with no write grants read "admin" on GET
    /repos, the card offered Close out, and the merge came back "403 Client Error: Forbidden for url: ..."."""
    def _seen(self, s, grants, **pr):
        from taskuary import ghcloseout
        with mock.patch.object(github, 'grants', return_value={**GRANTS, **grants}), \
             mock.patch.object(github, 'pr', return_value={**OPEN, **pr}), mock.patch.object(github, 'checks', return_value=RED):
            return ghcloseout.assess(s, 'northwind/ledger', 7)

    def test_no_contents_grant_means_no_close_out_and_the_reason_names_the_grant(self):
        seen = self._seen(armed(MemoryStore()), {'contents': False}, draft=False)
        self.assertFalse(seen['ok']); self.assertEqual((seen['state'], seen['kind']), ('denied', 'permission'))
        self.assertIn('Contents: write', seen['reason']); self.assertEqual(seen['offers'], [])

    def test_a_draft_needs_pull_requests_too_because_it_is_marked_ready_before_the_merge(self):
        seen = self._seen(armed(MemoryStore()), {'pull_requests': False}, draft=True)
        self.assertFalse(seen['ok']); self.assertIn('Pull requests: write', seen['reason'])
        self.assertTrue(self._seen(armed(MemoryStore()), {'pull_requests': False}, draft=False)['ok'])

    def test_update_and_rerun_are_offered_only_with_their_grants(self):
        s = armed(MemoryStore())
        self.assertEqual(self._seen(s, {'pull_requests': False}, draft=False, mergeable_state='behind')['offers'], [])
        self.assertEqual(self._seen(s, {'actions': False}, draft=False, mergeable_state='unstable')['offers'], [])

    def test_a_reply_that_cannot_be_posted_is_said_before_the_press(self):
        seen = self._seen(armed(MemoryStore()), {'issues': False}, draft=False)
        self.assertTrue(seen['ok']); self.assertIn('Issues: write', seen['note'])

    def test_the_card_does_not_offer_a_merge_when_github_cannot_be_read(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = armed(MemoryStore()); tid = with_pr(s)
        rid = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'close out',
                            'DraftText': json.dumps({'action': 'merge_pr', 'repo': 'northwind/ledger', 'number': 7, 'closeout': True})})
        with mock.patch.object(server, 'store', s), mock.patch.object(github, 'pr', side_effect=github.Refused('GitHub is down', 503)):
            got = TestClient(server.app).get(f'/api/reviews/{rid}/closeout').json()
        self.assertFalse(got['ok']); self.assertIn('could not be read', got['reason'])


class GithubRefusalWordsTests(unittest.TestCase):
    """GitHub names the missing grant in a header; the owner reads that, not a URL."""
    def setUp(self): _grants.stop()                                  # the real probe, with requests mocked
    def tearDown(self): _grants.start()
    def _r(self, status, message, accepted=''):
        r = mock.Mock(ok=status < 400, status_code=status, text=json.dumps({'message': message}),
                      headers={'x-accepted-github-permissions': accepted} if accepted else {})
        r.json.return_value = {'message': message}
        return r

    def test_a_missing_grant_is_said_in_githubs_own_names(self):
        with self.assertRaises(github.Refused) as e:
            github._ok(self._r(403, 'Resource not accessible by personal access token', 'contents=write; contents=write,workflows=write'), 'merge #7')
        self.assertIn('may not merge #7', str(e.exception)); self.assertIn('Contents: write', str(e.exception))
        self.assertNotIn('api.github.com', str(e.exception)); self.assertEqual(e.exception.needs, 'Contents: write')

    def test_a_revoked_token_and_a_missing_item_read_as_what_they_are(self):
        with self.assertRaises(github.Refused) as e: github._ok(self._r(401, 'Bad credentials'), 'merge #7')
        self.assertIn('expired or revoked', str(e.exception))
        with self.assertRaises(github.Refused) as e: github._ok(self._r(404, 'Not Found'), 'merge #7')
        self.assertIn('cannot see', str(e.exception))

    def test_the_probe_reads_a_403_as_missing_and_anything_else_as_granted(self):
        answers = {'/git/refs': self._r(403, 'Resource not accessible by personal access token', 'contents=write'),
                   '/pulls': self._r(422, 'Validation Failed'), '/issues': self._r(422, 'Validation Failed'),
                   '/actions/runs/0/rerun-failed-jobs': self._r(404, 'Not Found')}
        def req(method, url, **kw): return next(v for k, v in answers.items() if url.endswith(k))
        with mock.patch.object(github.requests, 'request', side_effect=req):
            got = github.grants('tok-probe', 'northwind/ledger', fresh=True)
        self.assertEqual(got, {'contents': False, 'pull_requests': True, 'issues': True, 'actions': True})

    def test_a_refusal_at_the_act_is_remembered_for_the_next_card(self):
        github._GRANTS.clear()
        with mock.patch.object(github.requests, 'request', return_value=self._r(422, 'Validation Failed')):
            self.assertTrue(github.grants('tok-learn', 'northwind/ledger')['contents'])
        github.learn('tok-learn', 'northwind/ledger', github.Refused('no', 403, 'Contents: write'))
        self.assertFalse(github.grants('tok-learn', 'northwind/ledger')['contents'])


if __name__ == '__main__': unittest.main()
