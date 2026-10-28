"""The owner's email signature is read off their own sent mail - the closing lines most of it shares - and once saved it is
the ONE signature on every email: the writer is told not to sign, a sign-off it writes anyway is taken off, and the saved block
goes on exactly once (the owner, 2026-10-16: "pull the signature from the email and use that in emails ... it should not be based
on prompt but hardcoded to emails").
"""
import unittest
from unittest import mock

from taskuary import chatgptauth, responder
from taskuary.store import MemoryStore

SIG = 'Sincerely,\nAlex Doyle\nFinance Systems Lead | Northwind'


def sent(*bodies): return [{'subject': 'Re: x', 'body': {'content': b}} for b in bodies]


class LearnTests(unittest.TestCase):
    def learn(self, *bodies):
        with mock.patch('taskuary.histgen.sent_mail', return_value=(sent(*bodies), [], 1, 'IMAP')):
            return responder.learn_signature(MemoryStore())

    def test_the_closing_lines_most_sent_mail_shares_are_the_signature(self):
        got = self.learn(f'Hi Erin,\n\nSigned off.\n\n{SIG}', f'Hi Gail,\n\nMapping updated.\n\n\n{SIG}\n',
                         f'Paula - attached.\n\n{SIG}', 'quick one: yes')                 # a one-liner without it is outvoted
        self.assertEqual(got, SIG)

    def test_quoted_history_below_the_reply_is_not_read_as_the_signature(self):
        q = '\n\nOn Tue, Oct 14, 2026 at 9:00 AM Erin Blake <erin@northwind.example> wrote:\n> can you sign off?\n> Erin'
        self.assertEqual(self.learn(f'Done.\n\n{SIG}{q}', f'Yes.\n\n{SIG}{q}', f'Ok.\n\n{SIG}'), SIG)

    def test_no_shared_ending_is_no_signature(self):
        self.assertEqual(self.learn('Thanks - Alex', 'ok', 'Will do. A.'), '')
        self.assertEqual(self.learn(), '')


class OneSignatureTests(unittest.TestCase):
    def test_the_writer_is_never_told_to_sign_saved_or_not(self):
        # with nothing saved it was told to sign "as STYLE.md says", and a STYLE.md with no sign-off sent replies unsigned (2026-10-28)
        s = MemoryStore()
        self.assertIn('Do NOT write a sign-off', responder.email_rule(s))
        s.set_setting('email_signature', SIG, 'owner')
        self.assertIn('Do NOT write a sign-off', responder.email_rule(s))

    def test_the_writers_own_sign_off_is_replaced_by_the_saved_block(self):
        self.assertEqual(responder.signed('Here it is.\n\nBest,\nAlex', SIG), f'Here it is.\n\n{SIG}')
        self.assertEqual(responder.signed(f'Here it is.\n\n{SIG}', SIG), f'Here it is.\n\n{SIG}')
        self.assertEqual(responder.signed('Friday works.', SIG), f'Friday works.\n\n{SIG}')       # a short sentence is the reply
        self.assertEqual(responder.signed('Here it is.\n\nBest,\nAlex', ''), 'Here it is.\n\nBest,\nAlex')   # nothing saved: as written


class ChatGptSignInTests(unittest.TestCase):
    """OpenAI's sign-in answered "error_code: 3p_delegated_access_policy_denied" on a work account (2026-10-16): said plainly."""
    def test_a_workspace_that_refuses_other_apps_is_said_in_plain_words_with_the_way_out(self):
        why = chatgptauth.plain_error('3p_delegated_access_policy_denied')
        self.assertTrue(why.startswith('Use the Codex CLI instead')); self.assertIn('settings', why); self.assertIn('admin can change', why)
        self.assertEqual(chatgptauth.plain_error('access_denied', 'You cancelled'), 'You cancelled')
