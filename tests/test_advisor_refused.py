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
