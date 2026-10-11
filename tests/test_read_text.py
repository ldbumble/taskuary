"""What every screen shows of a message: the sender's words, not the chain or the contact lines under them (2026-09-23).

Since 2026-10-11 a NOTICE footer and a sign-off stay: they were found by English words (_LEGAL, _VALEDICTION), and
the same words cut a sender's real sentence and every P.S. after a "Thanks," - "Everything should be ai"."""
import unittest

from taskuary import triage

MAIL = ('You will have to resubmit for the correct amount, I will reject\n\n\nErin Blake\n\nBilling Analyst\n\n'
        'Email: erin@northwind.example\nPhone: 555-0100\n')


class ReadTextTests(unittest.TestCase):
    def test_the_contact_lines_go_and_the_words_stay(self):
        out = triage.read_text(MAIL)
        self.assertTrue(out.startswith('You will have to resubmit for the correct amount'))
        self.assertNotIn('erin@northwind.example', out); self.assertNotIn('555-0100', out)

    def test_the_mailboxs_own_cut_is_used_when_there_is_one(self):
        words = 'Yes - Thursday works for the review, and I will bring the reconciled export and the vendor list.'
        own = words + '\n\nRegards,\nErin Blake\nPhone: 555-0100'
        self.assertEqual(triage.read_text(words + '\n\nOn Mon, Ray wrote:\n> earlier', own), words + '\n\nRegards,\nErin Blake')

    def test_the_endpoints_carry_it_beside_the_body(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        from taskuary.store import MemoryStore
        s = MemoryStore()
        mid = s.add_message({'ExternalId': 'r1', 'Channel': 'email', 'FromName': 'Erin Blake', 'Subject': 'refund',
                             'BodyText': MAIL, 'SentAt': '2026-09-23 09:00:00', 'Status': 'open'})
        with unittest.mock.patch.object(server, 'store', s):
            got = TestClient(server.app).get(f'/api/messages/{mid}').json()
        self.assertEqual(got['BodyText'], MAIL)                          # the mail as stored, whole
        self.assertNotIn('555-0100', got['ReadText'])


import unittest.mock  # noqa: E402
