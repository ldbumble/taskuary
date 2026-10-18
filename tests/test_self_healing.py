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
