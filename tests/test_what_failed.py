"""WHAT FAILED IS KEPT WHERE IT HAPPENED, AND NEVER SENT AGAIN AS IT STOOD (2026-10-19). A send refused by the mail server, and a Send the
demo refused, both left Send lit: the demo's refusal left no trace for the revision to see. Now a refusal is the act's own row, the
revision moves with it, and what failed (rulebook.failure) leads the row with its own fix."""
from taskuary import demo, funnel, rulebook
from taskuary.store import MemoryStore
from tests.test_row_decision import _Rail
import pytest

@pytest.fixture(autouse=True)
def _mailbox_connected(monkeypatch):
    """These drafts go by email in a world with no mailbox card: as if one were connected, so the Send is what is judged (a card that says
    Connect email lights nothing - rulebook.unconnected, tests/test_agent_lights.py)."""
    monkeypatch.setattr(rulebook, 'unconnected', lambda store, item: False)


class RefusedTests(_Rail):
    def _world(self):
        s = MemoryStore(); demo.seed(s); funnel.invalidate(); return s

    def _draft(self, s, channel='email'):
        """A draft waiting for its yes on a mail the demo's world has - its rail key and its review."""
        for i in funnel.pile(s)['items']:
            if i['kind'] != 'review': continue
            r = s.get_review(i['rid'])
            if (s.get_message(r['MessageId']) or {}).get('Channel') == channel: return i['key'], r
        self.fail(f'the demo has no {channel} draft on its rail')

    def test_a_refused_proposal_is_kept_on_its_target_and_paths_with_no_item_leave_nothing(self):
        s = self._world(); key, r = self._draft(s)
        s._exec("INSERT INTO operation (OpId, Kind, TargetKind, TargetId, ParamsJson, Status, CreatedAt) VALUES ('op9','review.approve','task',?,'{}','proposed','2026-10-19 09:00:00')",
                (r['TaskId'],))
        oid = demo.refused(s, '/api/operations/op9/execute', demo.SENDS)
        got = s.get_operation(oid)
        self.assertEqual((got['TargetKind'], got['TargetId'], got['Status']), ('task', r['TaskId'], 'refused'))
        self.assertEqual(s.get_operation('op9')['Status'], 'proposed', 'the proposal itself is left as it was')
        self.assertEqual(demo.refused(s, '/api/connectors/3', demo.OFF), '')

    def test_what_the_demo_refused_is_not_a_failure_on_the_items_row(self):
        """The walk, 2026-11-15: the tour says "press Send - nothing leaves the demo", and after the press the rail row read "Failed: This
        is the demo - nothing is sent..." in the words of a real fault. The Advisor still reads the refusal (above); the row says what
        the item is."""
        from taskuary import rulebook
        s = self._world(); key, r = self._draft(s)
        it = rulebook._item(s, 'task', r['TaskId'], key)
        before = rulebook.state(s, it, [])[0]
        demo.refused(s, f"/api/reviews/{r['ReviewId']}/decide", demo.SENDS)
        self.assertEqual(rulebook.failure(s, it)['cause'], 'demo')
        self.assertEqual(rulebook.state(s, it, [])[0], before)
        self.assertNotIn(before, rulebook.FAILED)


    def test_a_draft_that_could_not_be_written_is_what_failed_and_an_email_is_never_copied(self):
        """The advisor matrix (2026-10-19): Reply with no AI left an empty box and "no AI connector is set up to write replies" - and the
        line, never told, read the email's box with no Send as a chat's draft: "copy it ... then mark it done", Mark done lit."""
        s = self._world(); key, r = self._draft(s)
        before = rulebook.revision(s, 'task', r['TaskId'])
        s._exec("UPDATE review SET DraftText='' WHERE ReviewId=?", (r['ReviewId'],))
        s.set_review_draft_error(r['ReviewId'], 'no AI connector is set up to write replies')
        self.assertNotEqual(before, rulebook.revision(s, 'task', r['TaskId']), 'a draft that failed moves the revision')
        it = rulebook._item(s, 'task', r['TaskId'], key)
        f = rulebook.failure(s, it)
        self.assertEqual(f['what'], 'the reply could not be drafted'); self.assertEqual(f['fix']['label'], 'Connect an AI')
        self.assertEqual(rulebook.offered(s, it)[0]['label'], 'Connect an AI', 'its fix leads the verbs offered')
        got = rulebook.decide(s, key)
        self.assertEqual((got.get('verb'), got.get('state')), (None, 'failed'), 'offered, never filled: the agent suggests (2026-11-15)')
        self.assertTrue(got.get('line', '').startswith('Failed:'), 'what failed is said')

    def test_whichever_failed_last_is_what_failed(self):
        """The matrix (2026-10-20): Reply failed with no AI, then Send to agent failed - the card showed the agent's error and the line still
        said the reply could not be drafted. The draft's error had no time; it is an act on the task now, and the newer failure leads."""
        from taskuary import failures
        s = self._world(); key, r = self._draft(s)
        s.set_review_draft_error(r['ReviewId'], 'no AI connector is set up to write replies')
        it = rulebook._item(s, 'task', r['TaskId'], key)
        self.assertEqual(rulebook.failure(s, it)['what'], 'the reply could not be drafted')
        failures.record(s, task_id=r['TaskId'], kind='dispatch.prepare', error='the assistant could not start', what='the agent did not start')
        self.assertEqual(rulebook.failure(s, it)['what'], 'the agent did not start')
        u = s.create_task({'Title': 'Badge access for the new AP clerk?', 'Status': 'open'}, 'owner')
        v = s.add_review({'TaskId': u, 'DraftText': '', 'Status': 'pending'})
        s.set_review_draft_error(v, 'no AI connector is set up to write replies')
        s.update_review_draft(v, 'Approved - the badge is ready Friday.', None, 'ai')
        self.assertIsNone(rulebook.failure(s, {'tid': u}), 'a draft written since clears it')

    def test_an_agent_start_that_failed_is_left_on_the_task_for_the_advisor(self):
        """The advisor matrix (2026-10-19): Send to agent failed with its error on the card, and the line over it still said the reply
        had gone and to mark it done - the failure was said only in the answer, never kept where the Advisor reads it."""
        from unittest import mock
        from fastapi.testclient import TestClient
        from taskuary import general, server
        s = self._world(); key, r = self._draft(s)
        s._exec("UPDATE task SET Kind='general' WHERE TaskId=?", (r['TaskId'],))
        with mock.patch.object(server, 'store', s), mock.patch.object(general, 'start_session', side_effect=RuntimeError('the assistant could not start')), \
             mock.patch('taskuary.origin.hold', return_value=None):          # ...from a sender he trusts: a held start is its own test (test_stranger_live_fixes)
            got = TestClient(server.app).post(f"/api/tasks/{r['TaskId']}/dispatch", json={})
        self.assertEqual(got.status_code, 422, got.text)
        f = rulebook.failure(s, rulebook._item(s, 'task', r['TaskId'], key))
        self.assertEqual(f['what'], 'the agent did not start'); self.assertIn('could not start', f['why'])

    def test_a_goals_step_that_did_not_start_is_left_on_the_goal_and_a_start_since_clears_it(self):
        """The matrix's verify (2026-10-20): Send to agent on a goal starts its step's own task; the failed start was left on the step - a
        task nobody had pressed - and the goal's line never moved. `via` names the goal the press was made on, the failure comes back
        with its way past it, and a start that went since is the newest act."""
        from unittest import mock
        from fastapi.testclient import TestClient
        from taskuary import general, server
        s = MemoryStore()
        g = s.create_task({'Title': 'Move payroll to Payworth', 'Status': 'open', 'Kind': 'task'}, 'owner')
        s.set_task_checklist(g, ['Export the pay rules'], 'owner')
        c = TestClient(server.app)
        with mock.patch.object(server, 'store', s):
            step = c.post(f"/api/tasks/{g}/steps/{s.task_checklist(g)[0]['id']}/start").json()['taskId']
            with mock.patch.object(general, 'start_session', side_effect=RuntimeError('No AI is connected to answer')):
                got = c.post(f'/api/tasks/{step}/dispatch', json={'kind': 'general', 'via': g})
            self.assertEqual(got.status_code, 422, got.text)
            f = rulebook.failure(s, {'tid': g})
            self.assertEqual((f['what'], (f['fix'] or {}).get('label')), ('the agent did not start', 'Connect an AI'), 'with its way past it')
            self.assertIsNone(rulebook.failure(s, {'tid': step}), 'the step nobody pressed carries nothing')
            # `via` is only ever the step's own goal: another task named there is not where the press was made
            other = s.create_task({'Title': 'Renew the PhishGuard licence', 'Status': 'open'}, 'owner')
            with mock.patch.object(general, 'start_session', side_effect=RuntimeError('the assistant could not start')):
                c.post(f'/api/tasks/{step}/dispatch', json={'kind': 'general', 'via': other})
            self.assertIsNone(rulebook.failure(s, {'tid': other}))
            sess = mock.Mock(provider='claude', model='', info=lambda tail=3: {})
            with mock.patch.object(general, 'start_session', return_value=sess), mock.patch.object(general, 'history', return_value=[1]):
                self.assertEqual(c.post(f'/api/tasks/{step}/dispatch', json={'kind': 'general', 'via': g}).status_code, 200)
            self.assertIsNone(rulebook.failure(s, {'tid': g}), 'a start that went since clears it')


