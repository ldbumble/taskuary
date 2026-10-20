"""THE ADVISOR NEVER SENDS THE OWNER BACK TO THE ACT THAT JUST FAILED (2026-10-19). A send refused by the mail server, and a Send the
demo refused, both left the line saying "The draft is ready - read it, then send it." with Send lit: the demo's refusal left no trace
for the revision to see, and the scripted Advisor ignored the WHAT FAILED line it was given. A chat draft with no Send got no line
at all, and the strip told the owner nothing needed a move over a question nobody had answered."""
import json
from taskuary import advisor, buttons, demo, funnel
from taskuary.store import MemoryStore
from tests.test_advisor import _Rail


class RefusedTests(_Rail):
    def _world(self):
        s = MemoryStore(); demo.seed(s); funnel.invalidate(); return s

    def _advise(self, s, key):
        """The scripted Advisor's pick for the item keyed `key`, judged inline at the item's revision as it stands."""
        tk, ti = advisor.target_of(s, key)
        advisor.notice(s, advisor.SHOWN, tk, ti, wait=True, llm=demo.brain(store=s), key=key)
        return advisor.for_key(s, key)

    def _draft(self, s, channel='email'):
        """A draft waiting for its yes on a mail the demo's world has - its rail key and its review."""
        for i in funnel.pile(s)['items']:
            if not i['key'].startswith('review:'): continue
            r = s.get_review(int(i['key'][7:]))
            if (s.get_message(r['MessageId']) or {}).get('Channel') == channel: return i['key'], r
        self.fail(f'the demo has no {channel} draft on its rail')

    def test_a_send_the_demo_refused_is_an_act_and_the_line_moves_off_send(self):
        s = self._world(); key, r = self._draft(s)
        self.assertEqual(self._advise(s, key).get('verb'), 'approve', 'a draft waiting: the scripted line advises Send')
        before = advisor.revision(s, 'task', r['TaskId'])
        self.assertTrue(demo.refused(s, f"/api/reviews/{r['ReviewId']}/decide", demo.SENDS), 'the refusal is left on the item')
        self.assertNotEqual(before, advisor.revision(s, 'task', r['TaskId']), 'a refused press moves the revision')
        f = advisor.failure(s, advisor._item(s, 'task', r['TaskId'], key))
        self.assertIn('This is the demo', f['why'])
        offered = [v['verb'] for v in advisor.offered(s, advisor._item(s, 'task', r['TaskId'], key))]
        self.assertNotIn('new_task', offered, 'no task to fix the demo for not sending'); self.assertNotIn('report_bug', offered)
        after = self._advise(s, key)
        self.assertNotEqual(after.get('verb'), 'approve', f'the line still sends the owner to the refused Send: {after}')
        self.assertTrue(after.get('line'))

    def test_a_refused_proposal_is_kept_on_its_target_and_paths_with_no_item_leave_nothing(self):
        s = self._world(); key, r = self._draft(s)
        s._exec("INSERT INTO operation (OpId, Kind, TargetKind, TargetId, ParamsJson, Status, CreatedAt) VALUES ('op9','review.approve','task',?,'{}','proposed','2026-10-19 09:00:00')",
                (r['TaskId'],))
        oid = demo.refused(s, '/api/operations/op9/execute', demo.SENDS)
        got = s.get_operation(oid)
        self.assertEqual((got['TargetKind'], got['TargetId'], got['Status']), ('task', r['TaskId'], 'refused'))
        self.assertEqual(s.get_operation('op9')['Status'], 'proposed', 'the proposal itself is left as it was')
        self.assertEqual(demo.refused(s, '/api/connectors/3', demo.OFF), '')

    def test_a_send_the_mail_server_refused_is_redrafted_not_sent_again(self):
        s = self._world(); key, r = self._draft(s)
        s._exec("UPDATE review SET DeliveryState='failed', Reason=? WHERE ReviewId=?",
                ('Not sent: the mail server refused erin.blake@northwind.example (5.1.1 no such user)', r['ReviewId']))
        got = self._advise(s, key)
        self.assertEqual(got.get('verb'), 'redraft', got)

    def test_the_scripted_advisor_reads_what_failed(self):
        ask = lambda verbs, extra='': json.loads(demo.brain()('Answer with JSON only', f'EVENT: item.shown\n\nVERBS OFFERED: {verbs}{extra}'))
        send = 'approve (Send), redraft (Redraft), close (Mark done)'
        self.assertEqual(ask(send)['verb'], 'approve')
        self.assertEqual(ask(f'fix (Sign in again), {send}', '\n\nWHAT FAILED: the reply was not sent - the mailbox refused the sign-in')['verb'], 'fix')
        self.assertIn('Sign in again', ask(f'fix (Sign in again), {send}', '\n\nWHAT FAILED: x - y')['line'])
        unknown = '\n\nWHAT FAILED: the reply may not have gone - timeout (nobody knows whether it went: check before sending again)'
        self.assertEqual(ask(f"approve ({buttons.label('approve', 'check')}), close (Mark done)", unknown)['verb'], 'approve')
        self.assertEqual(ask(send, unknown)['verb'], 'redraft', 'a plain Send is never advised over a send nobody can confirm')
        self.assertEqual(ask(send, f'\n\nWHAT FAILED: the reply was not sent - {demo.SENDS}')['verb'], 'close')

    def test_a_chat_draft_with_no_send_is_copied_and_closed_not_left_silent(self):
        s = self._world(); key, r = self._draft(s, 'teams')
        got = self._advise(s, key)
        self.assertEqual(got.get('verb'), 'close', got)
        self.assertIn('copy', got.get('line', '').lower())

    def test_a_draft_that_could_not_be_written_is_what_failed_and_an_email_is_never_copied(self):
        """The advisor matrix (2026-10-19): Reply with no AI left an empty box and "no AI connector is set up to write replies" - and the
        line, never told, read the email's box with no Send as a chat's draft: "copy it ... then mark it done", Mark done lit."""
        s = self._world(); key, r = self._draft(s)
        before = advisor.revision(s, 'task', r['TaskId'])
        s._exec("UPDATE review SET DraftText='' WHERE ReviewId=?", (r['ReviewId'],))
        s.set_review_draft_error(r['ReviewId'], 'no AI connector is set up to write replies')
        self.assertNotEqual(before, advisor.revision(s, 'task', r['TaskId']), 'a draft that failed moves the revision')
        it = advisor._item(s, 'task', r['TaskId'], key)
        f = advisor.failure(s, it)
        self.assertEqual(f['what'], 'the reply could not be drafted'); self.assertEqual(f['fix']['label'], 'Connect an AI')
        self.assertEqual(advisor.offered(s, it)[0]['label'], 'Connect an AI', 'its fix leads the verbs offered')
        got = self._advise(s, key)
        self.assertEqual((got.get('verb'), got.get('label')), ('fix', 'Connect an AI'), got)
        self.assertTrue(got.get('href'), 'the fix opens its place')
        self.assertNotIn('copy', got.get('line', '').lower())
        # ...and an email's empty box with no failure is not a chat's draft either
        ask = lambda item: json.loads(demo.brain()('Answer with JSON only', f'EVENT: item.shown\n\nTHE ITEM: {json.dumps(item)}\n\nVERBS OFFERED: redraft (Redraft), close (Mark done)'))
        self.assertNotIn('copy', ask({'channel': 'email'})['line'].lower())
        self.assertIn('copy', ask({'channel': 'teams'})['line'].lower())

    def test_an_agent_start_that_failed_is_left_on_the_task_for_the_advisor(self):
        """The advisor matrix (2026-10-19): Send to agent failed with its error on the card, and the line over it still said the reply
        had gone and to mark it done - the failure was said only in the answer, never kept where the Advisor reads it."""
        from unittest import mock
        from fastapi.testclient import TestClient
        from taskuary import general, server
        s = self._world(); key, r = self._draft(s)
        s._exec("UPDATE task SET Kind='general' WHERE TaskId=?", (r['TaskId'],))
        with mock.patch.object(server, 'store', s), mock.patch.object(general, 'start_session', side_effect=RuntimeError('the assistant could not start')):
            got = TestClient(server.app).post(f"/api/tasks/{r['TaskId']}/dispatch", json={})
        self.assertEqual(got.status_code, 422, got.text)
        f = advisor.failure(s, advisor._item(s, 'task', r['TaskId'], key))
        self.assertEqual(f['what'], 'the agent did not start'); self.assertIn('could not start', f['why'])

    def test_the_prompt_says_an_agent_run_is_over_and_a_list_has_nothing_left(self):
        """The advisor matrix (2026-10-19): a finished agent and a task with every todo ticked stood under "No suggestion" - the prompt
        carried neither the agent's finish nor an empty list, so nothing told the model the work was done."""
        from taskuary import workerstate
        s = MemoryStore()
        t = s.create_task({'Title': 'Fix the export', 'Status': 'in_progress', 'Kind': 'coding'}, 'owner')
        workerstate.record(s, t, 'r1', 'working'); workerstate.record(s, t, 'r1', 'finished', text='Done - the export keeps the rows now.')
        p = advisor._prompt(s, advisor.SHOWN, {'key': f'task:{t}', 'tid': t}, [{'verb': 'close', 'label': 'Mark done'}], 1, 'task', t)
        self.assertIn("THE AGENT'S RUN ENDED (finished): Done - the export keeps the rows now.", p)
        u = s.create_task({'Title': 'Close the August books', 'Status': 'open'}, 'owner')
        s.set_task_checklist(u, ['Bank reconciliation', 'Accruals posted'], 'owner')
        for x in ('Bank reconciliation', 'Accruals posted'): s.tick_checklist_item(u, s.checklist_id(x), True, 'owner')
        p = advisor._prompt(s, advisor.SHOWN, {'key': f'task:{u}', 'tid': u}, [{'verb': 'close', 'label': 'Mark done'}], 1, 'task', u)
        self.assertIn('EVERY TODO ON THE TASK IS TICKED (2 of 2)', p); self.assertNotIn('STILL TO DO', p)
        self.assertEqual(json.loads(demo.brain()('JSON', p))['verb'], 'close', 'the scripted Advisor reads it the same way')

    def test_the_scripted_advisor_redrafts_only_past_a_failed_reply(self):
        ask = lambda failed: json.loads(demo.brain()('JSON', f'EVENT: item.shown\n\nVERBS OFFERED: new_task (New task to fix this), redraft (Redraft), close (Mark done)\n\nWHAT FAILED: {failed}'))
        self.assertEqual(ask('the reply was not sent - refused')['verb'], 'redraft')
        self.assertEqual(ask('the agent did not start - no coding tool')['verb'], 'new_task', 'an agent that did not start is not redrafted')
