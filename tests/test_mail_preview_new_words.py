"""The chat's arrival card previews the first lines of a mail - so they have to be the sender's NEW words (the owner, 2026-11-09: "preview of
the email is the bottom of the email?? it should be the top? ... you can't see anything about the email"). A mail from outside the company opened
with the banner its mail system stamps over every outside mail, and a reply's visible text was the chain it quoted.

The shape: three outside senders' mail all open with the same stamped paragraph; one of them replies on top of a quoted chain with a signature
under the reply. The card reads the reply's first line, and its subject rides beside it."""
import unittest

from taskuary import general
from taskuary.store import MemoryStore

BANNER = 'This message came from outside Northwind. Think twice before opening links or files you did not expect.'
QUOTED = ('On Mon, Nov 9, 2026 at 9:02 AM Erin Blake <erin@northwind.example> wrote:\n> Can you send the October invoice?\n> Thanks\n'
          '> Erin')
SIG = 'Gail Moreno\nAccounts, Vendor Co\n(555) 010-0199\ngail@vendor.example'


def mail(s, tid, who, addr, body, subject='Invoice for October', own=None):
    return s.add_message({'TaskId': tid, 'ExternalId': f'mail:{addr}:{len(body)}', 'Channel': 'email', 'FromName': who, 'FromEmail': addr,
                          'Subject': subject, 'SentAt': '2026-11-09 12:29:00', 'BodyText': body, 'OwnText': own, 'Status': 'routed'})


def room():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Send the October invoice', 'Kind': 'general', 'Status': 'open'}, 't')
    other = s.create_task({'Title': 'Something else', 'Kind': 'general', 'Status': 'open'}, 't')
    for who, a in [('Ray Colton', 'ray@vendor.example'), ('Omar Keller', 'omar@supplies.example')]:
        mail(s, other, who, a, f'{BANNER}\n\nA note of my own about another thing entirely, {who}.')
    return s, tid


class MailPreviewTests(unittest.TestCase):
    def setUp(self): general._LEADS.clear()

    def row(self, s, tid): return [general.mail_row(s, x) for x in s._rows(general.JOINED, (tid,))][-1]

    def test_banner_quoted_chain_and_signature_leave_the_new_words_first(self):
        s, tid = room()
        mail(s, tid, 'Gail Moreno', 'gail@vendor.example', f'{BANNER}\n\nAttached is the October invoice, due on the 30th.\n\n{SIG}\n\n{QUOTED}')
        r = self.row(s, tid)
        self.assertTrue(r['words'].startswith('Attached is the October invoice'), r['words'])
        self.assertNotIn('outside Northwind', r['words'])
        self.assertNotIn('wrote:', r['words'])
        self.assertNotIn('010-0199', r['words'])
        self.assertEqual(r['subject'], 'Invoice for October')

    def test_the_mailbox_own_cut_loses_the_banner_too(self):
        s, tid = room()
        mail(s, tid, 'Gail Moreno', 'gail@vendor.example', f'{BANNER}\n\nSending it today.\n\n{QUOTED}', own=f'{BANNER}\n\nSending it today.')
        self.assertEqual(self.row(s, tid)['words'], 'Sending it today.')

    def test_a_lead_only_one_sender_writes_stays(self):
        s, tid = room()
        lead = 'Following up on the vendor list we talked about on Friday afternoon.'
        mail(s, tid, 'Gail Moreno', 'gail@vendor.example', f'{lead}\n\nCan you confirm by Wednesday?')
        self.assertTrue(self.row(s, tid)['words'].startswith(lead))

    def test_a_message_that_is_only_the_banner_is_never_cut_to_nothing(self):
        s, tid = room()
        mail(s, tid, 'Gail Moreno', 'gail@vendor.example', BANNER)
        self.assertEqual(self.row(s, tid)['words'], BANNER)

    def test_a_chat_line_has_no_subject(self):
        s, tid = room()
        s.add_message({'TaskId': tid, 'ExternalId': 'wa:1', 'Channel': 'whatsapp', 'FromName': 'Ray Colton', 'FromEmail': 'whatsapp:8000',
                       'Subject': 'WhatsApp', 'SentAt': '2026-11-09 12:30:00', 'BodyText': 'is the van booked?', 'Status': 'routed'})
        r = self.row(s, tid)
        self.assertEqual((r['subject'], r['words']), ('', 'is the van booked?'))


if __name__ == '__main__': unittest.main()
