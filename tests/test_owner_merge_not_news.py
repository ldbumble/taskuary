"""A PULL REQUEST THE OWNER MERGED IS NOT NEWS (the owner, 2026-11-02: a merged PR's batch sat under Reports as "1 pull request on
<repo> 1/1 - 1 of 1 done", its task already closed). The agent's `gh pr merge` was held (shellgate), the owner approved it on the
task, Taskuary ran it, and the agent then closed its own task - so the rail read the close as the agent's and kept its result as an
unread report. The ending was the owner's own yes: like their own merge on GitHub (channels._gh_ended), theirs is never news. An
agent's close with no such yes - or after the owner said no - is still a result to read once."""
import json, os, tempfile, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import lanes, server
from taskuary.processing_unread import _agent_finished, finish_evidence
from taskuary.store import SQLiteStore
from taskuary.testing import Factory


def agent_closed(s, f, n, held=None):
    """A coding task on northwind/ledger#n its agent closed itself - with, when `held` is a verdict, the agent's held `gh pr merge`
    answered by the owner first."""
    tid = f.task(title=f'1 pull request on northwind/ledger ({n})', status='in_progress', kind='coding', source='github')
    mid = f.message(task_id=tid, channel='github', subject=f'northwind/ledger#{n} Add the March import', from_name='gail-moreno',
                    body='[pull request by gail-moreno - association: CONTRIBUTOR]\nAdds the March import.',
                    from_email='gail-moreno@users.noreply.github.com', conversation_id=f'gh:northwind/ledger#{n}')
    f.route(mid, tid, 'batch', 'item 1 of the batch')
    if held:
        rid = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': "held before it ran, in the agent's shell",
                            'DraftText': json.dumps({'action': 'shell_act', 'sid': 's1', 'command': f'gh pr merge {n} --squash',
                                                     'shell': 'Bash', 'cwd': '', 'what': 'merge a pull request'})})
        s.decide_review(rid, held, None, 'owner')
    s.add_comment(tid, 'coding', 'agent', f'The agent closed this itself: Reviewed and merged PR #{n}')
    s.update_task(tid, {'Status': 'done'}, 'coding')
    return tid


class OwnerMergeNotNewsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = mock.patch.dict(os.environ, {'TASKUARY_HOME': tempfile.mkdtemp()}); cls.home.start()
        cls.s = SQLiteStore(os.path.join(tempfile.mkdtemp(), 'w.db'))
        from taskuary import processing_startup
        processing_startup.initialize(cls.s)                   # before the work: the cutover reads everything there already
        f = Factory(cls.s)
        cls.merged, cls.plain, cls.declined = agent_closed(cls.s, f, 7, 'approved'), agent_closed(cls.s, f, 8), agent_closed(cls.s, f, 9, 'rejected')
        cls.s.reconcile_processing_membership()
        with mock.patch.object(server, 'store', cls.s):
            c = TestClient(server.app, base_url='http://127.0.0.1')
            cls.pile = {i['tid']: i for i in c.get('/api/funnel/pile', params={'force': 1}).json()['items'] if i.get('tid')}

    @classmethod
    def tearDownClass(cls): cls.s.close(); cls.home.stop()

    def test_a_merge_the_owner_approved_leaves_the_rail(self):
        self.assertNotIn(self.merged, self.pile)
        self.assertFalse(_agent_finished(self.s, self.merged, False, None, None, None)['unread'])

    def test_the_page_still_says_the_agent_closed_it(self):
        self.assertEqual(finish_evidence(self.s, self.merged)['summary'], 'Reviewed and merged PR #7')

    def test_an_agents_own_close_is_still_a_result_to_read(self):
        for tid in (self.plain, self.declined):
            row = self.pile.get(tid, {})                # ...in Tasks until read, never under Reports (the owner, 2026-11-02)
            self.assertEqual((row.get('kind'), lanes.level_of(row)), ('agentdone', 'task'), tid)
            self.assertTrue(_agent_finished(self.s, tid, False, None, None, None)['unread'])
