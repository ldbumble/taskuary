"""A failed act is never the end of the road (the owner, 2026-10-18: "the advisor should handle and create the button to fix it.
not new buttons but from the list"). A known fix is the row's `fix`; anything else, the Advisor is told what failed and picks the
move past it; nothing here can fix it - New task, in its "fix" state, makes the task that will."""
import json, smtplib, unittest
from unittest import mock
from taskuary import advisor, buttons, operations, outbound
from taskuary.store import MemoryStore
from tests.test_advisor import brain_saying
from tests.test_capabilities import draft


def failed_send(s, why='Not sent: graph sendMail failed (401): token expired.', state='failed', fix=None):
    it = draft(s, 'email', deliver={'kind': 'reply', 'delivery': state, **({'fix': fix} if fix else {})})
    s._exec('UPDATE review SET DeliveryState=?, Reason=? WHERE ReviewId=?', (state, why, it['rid']))
    return it


def failed_act(s, it, err='the repository could not be reached', outcome=None):
    s.add_operation({'OpId': 'op1', 'Kind': 'task.complete', 'TargetKind': 'task', 'TargetId': it['tid'], 'Status': 'error',
                     'Error': err, 'OutcomeJson': json.dumps(outcome or {}), 'ParamsJson': '{}'})


class SignInAgainTests(unittest.TestCase):
    def test_a_refused_sign_in_is_fixed_by_signing_in_not_by_sending(self):
        for e in (smtplib.SMTPAuthenticationError(535, b'5.7.8 Authentication unsuccessful'), RuntimeError('graph sendMail failed (401): expired'),
                  RuntimeError('graph sendMail failed (403): forbidden'), RuntimeError('AADSTS700082: the refresh token has expired')):
            self.assertEqual(outbound.fix_of(e), {'label': 'Sign in again', 'href': outbound.MAIL[1]}, e)

    def test_a_rejected_recipient_is_not_a_sign_in(self):
        for e in (smtplib.SMTPRecipientsRefused({'x@northwind.example': (550, b'no such user')}), RuntimeError('graph sendMail failed (400): bad')):
            self.assertIsNone(outbound.fix_of(e), e)

    def test_a_fix_the_failure_named_wins(self):
        self.assertEqual(outbound.fix_of(outbound.Fixable('no mailbox (401)', 'Connect a mailbox', '#x'))['label'], 'Connect a mailbox')


class TheAdvisorIsToldWhatFailedTests(unittest.TestCase):
    def test_a_failed_send_reaches_the_prompt_with_its_reason(self):
        s = MemoryStore(); it = failed_send(s)
        f = advisor.failure(s, it)
        self.assertEqual((f['what'], f['why'], f['unknown']), ('the reply was not sent', 'graph sendMail failed (401): token expired', False))
        llm = brain_saying({'verb': None, 'line': '', 'evidence': []})
        with mock.patch.object(advisor, '_item', return_value=it):
            advisor.judge(s, advisor.SHOWN, 'task', it['tid'], advisor.revision(s, 'task', it['tid']), 2, llm, key=it['key'])
        self.assertIn('WHAT FAILED: the reply was not sent - graph sendMail failed (401)', llm.calls[0][1])
        self.assertIn('Never advise the act that failed again', llm.calls[0][0])

    def test_a_send_nobody_knows_went_is_said_so_and_never_made_a_task(self):
        s = MemoryStore(); it = failed_send(s, why='the provider did not answer', state='unknown')
        self.assertTrue(advisor.failure(s, it)['unknown'])
        self.assertNotIn('new_task', [v['verb'] for v in advisor.offered(s, it)])

    def test_a_failure_moves_the_revision_so_an_old_send_line_is_judged_again(self):
        s = MemoryStore(); it = draft(s, 'email')
        before = advisor.revision(s, 'task', it['tid'])
        failed_act(s, it)
        self.assertNotEqual(advisor.revision(s, 'task', it['tid']), before)

    def test_nothing_failed_is_no_failure(self):
        s = MemoryStore(); it = draft(s, 'email')
        self.assertIsNone(advisor.failure(s, it))
        self.assertNotIn('new_task', [v['verb'] for v in advisor.offered(s, it)])


class MakeATaskToFixThisTests(unittest.TestCase):
    def test_a_failure_with_no_fix_offers_the_list_s_own_button_in_its_fix_state(self):
        s = MemoryStore(); it = draft(s, 'email'); failed_act(s, it)
        nt = next(v for v in advisor.offered(s, it) if v['verb'] == 'new_task')
        self.assertEqual(nt['label'], buttons.label('new_task', 'fix'))
        self.assertIn(nt['label'], buttons.labels(), 'a state of a listed button - never a new word')
        self.assertIn('the repository could not be reached', nt['task']['text'])
        self.assertIn(it['ref'], nt['task']['text'])

    def test_a_failure_with_a_fix_offers_the_fix_not_a_task(self):
        s = MemoryStore(); it = failed_send(s, fix={'label': 'Sign in again', 'href': outbound.MAIL[1]})
        verbs = [v['verb'] for v in advisor.offered(s, it)]
        self.assertEqual(verbs[0], 'fix'); self.assertNotIn('new_task', verbs)

    def test_the_advisor_picking_it_hands_the_page_the_task_to_make(self):
        s = MemoryStore(); it = draft(s, 'email'); failed_act(s, it)
        lbl = buttons.label('new_task', 'fix')
        with mock.patch.object(advisor, '_item', return_value=it):
            advisor.judge(s, advisor.SHOWN, 'task', it['tid'], advisor.revision(s, 'task', it['tid']), 2,
                          brain_saying({'verb': lbl, 'line': 'The repository could not be reached - make it a task to fix.', 'evidence': []}), key=it['key'])
            got = advisor.for_key(s, it['key'])
        self.assertEqual((got['verb'], got['label']), ('new_task', lbl))
        self.assertIn('could not be reached', got['task']['text'])

    def test_the_task_it_makes_runs_on_the_tool_the_assistant_uses(self):
        op = operations.propose(MemoryStore(), 'task.create_from_text', 0, {'text': 'Fix: x', 'title': 'Fix: x', 'kind': 'task'})
        self.assertEqual((op['kind'], op['status']), ('task.create_from_text', 'proposed'))


class TheChatKeepsTheSendsFixTests(unittest.TestCase):
    def test_a_halted_send_carries_its_fix_to_recover(self):
        """server.py dropped `send_fix` on the way into the Halt, so a send confirmed in chat with no mailbox offered no Connect a
        mailbox - read from the source, the one place both halts are raised."""
        import pathlib, re
        src = (pathlib.Path(__file__).parents[1] / 'taskuary/server.py').read_text(encoding='utf-8')
        halts = re.findall(r"raise operations\.Halt\(out(?:\.get\('send_error'\)|\['send_error'\]).*?\n(?:.*\n){0,2}", src)
        self.assertEqual(len(halts), 2)
        self.assertTrue(all("send_fix" in h for h in halts), halts)


class OneFailureShapeTests(unittest.TestCase):
    """failures.py: every road says a failure one way - {sentence, fix, retry, unknown} - and leaves it as the agreed op row."""
    def test_a_missing_coding_tool_is_said_plainly_with_its_fix(self):
        from taskuary import failures, words
        c = failures.classify(FileNotFoundError(2, 'No such file or directory', 'claude'), act='dispatch.prepare')
        self.assertEqual(c['sentence'], "The coding tool isn't installed on this computer")
        self.assertEqual(c['fix'], {'label': 'Connect a coding tool', 'href': words.href('ai_apps')})
        self.assertFalse(c['retry'], 'pressing it again starts the same missing program')

    def test_each_kind_of_failure_names_its_place_or_says_try_again(self):
        from taskuary import failures, words
        self.assertEqual(failures.classify(ValueError('working directory does not exist: portal'))['fix']['href'], words.href('coding'))
        self.assertEqual(failures.classify(RuntimeError('no AI connector is set up to write replies'))['fix']['href'], words.href('ai'))
        self.assertEqual(failures.classify(RuntimeError('graph sendMail failed (401): expired'))['fix']['label'], 'Sign in again')
        plain = failures.classify(RuntimeError('the remote end hung up'))
        self.assertEqual((plain['fix'], plain['retry'], plain['unknown']), (None, True, False))

    def test_only_a_send_can_be_unknown(self):
        from taskuary import failures
        self.assertTrue(failures.classify(TimeoutError('read timed out'), act='review.approve')['unknown'])
        self.assertFalse(failures.classify(TimeoutError('read timed out'), act='task.complete')['unknown'])

    def test_credentials_never_reach_the_sentence(self):
        from taskuary import failures
        self.assertNotIn('sk-ant-api03', failures.classify(RuntimeError('bad key sk-ant-api03-' + 'a' * 40))['sentence'])

    def test_the_record_is_the_row_the_advisor_reads(self):
        from taskuary import failures
        s = MemoryStore(); it = draft(s, 'email')
        failures.record(s, task_id=it['tid'], kind='report.run', error=RuntimeError('the site changed its layout'),
                        what='the Monday invoices workflow stopped at step 3', source='workflow', step=3)
        f = advisor.failure(s, it)
        self.assertEqual((f['what'], f['why'], f['source']), ('the Monday invoices workflow stopped at step 3', 'the site changed its layout', 'workflow'))
        verbs = [v['verb'] for v in advisor.offered(s, it)]
        self.assertIn('report_bug', verbs); self.assertNotIn('new_task', verbs)       # a workflow run already IS a task

    def test_a_confirmed_act_that_throws_keeps_the_shape(self):
        s = MemoryStore(); it = draft(s, 'email')
        op = operations.propose(s, 'dispatch.prepare', it['tid'], {'kind': 'coding'})
        def run(): raise FileNotFoundError(2, 'No such file or directory', 'claude')
        out = operations.execute(s, op['id'], op['version'], run)
        self.assertEqual((out['status'], out['error']), ('error', "The coding tool isn't installed on this computer"))
        self.assertEqual(out['outcome']['fix']['label'], 'Connect a coding tool')

    def test_recover_offers_report_this_bug_when_nothing_else_will_work(self):
        from taskuary import concierge
        chips = []
        with mock.patch.object(concierge, 'restore_current', return_value=None), mock.patch.object(concierge, 'chips_for', return_value=[]):
            got = concierge.recover(MemoryStore(), {'id': 'x', 'version': 1, 'status': 'error', 'kind': 'task.complete', 'error': 'it broke',
                                                    'outcome': {'retry': False}}, llm=False)
        self.assertIn(buttons.label('report_bug'), [c['label'] for c in got['chips']])
        self.assertNotIn(buttons.label('try_again'), [c['label'] for c in got['chips']])

    def test_a_closed_task_says_how_to_reopen_it(self):
        from taskuary import remind
        s = MemoryStore(); t = s.create_task({'Title': 'Order badges', 'Status': 'done'}, 'owner')
        with self.assertRaises(ValueError) as e: remind.set_reminder(s, t, 'tomorrow')
        self.assertEqual(outbound.fix_of(e.exception)['href'], f'#task={t}')


class OneGateTests(unittest.TestCase):
    """concierge.gate: a reply cut off mid-CALL reached the owner as `CALL: {"kind": "approve", "par` (the error sweep, 2026-10-18)."""
    def test_half_a_call_is_never_shown(self):
        from taskuary import concierge
        self.assertEqual(concierge.gate('Sending it now.\nCALL: {"kind": "approve", "par'), ('Sending it now.', True))
        self.assertEqual(concierge.gate('{"kind": "approve", "params": {'), ('', True))
        self.assertEqual(concierge.gate('Erin asked for the invoice by Friday.'), ('Erin asked for the invoice by Friday.', False))

    def test_the_gate_judges_shape_never_words(self):
        """A word list once blanked right answers for mentioning access (2026-10-11) - only the shape is judged."""
        from taskuary import concierge
        self.assertFalse(concierge.gate("I don't have access to that folder, so Gail sent it instead.")[1])

    def test_a_cut_off_answer_is_asked_again_once_then_said_plainly(self):
        from taskuary import concierge
        s = MemoryStore(); said = []
        def llm(system, user, max_tokens=400, **kw):
            said.append(user); return 'Let me CALL: {"kind": "task.upd'
        llm.takes_want = False
        out = concierge.say(s, 'what is on my list?', llm=llm)
        self.assertEqual(len(said), 2, 'asked once more, never looped')
        self.assertIn('CUT OFF', said[1])
        txt = json.dumps(out)
        self.assertNotIn('CALL:', txt); self.assertIn(concierge.LOST, txt)
