"""What every screen shows of a message: the sender's words, not the NOTICE under them (2026-09-23)."""
import unittest

from taskuary import triage

MAIL = ('You will have to resubmit for the correct amount, I will reject\n\n\nErin Blake\n\nBilling Analyst\nEmail:\n\n'
        'erin@northwind.example\n\nNOTICE: This confidential message/attachment contains information intended for a '
        'specific individual(s) and purpose.\nAny inappropriate use, distribution or copying is strictly prohibited. '
        'If received in error, notify the sender and immediately delete the message.')


class ReadTextTests(unittest.TestCase):
    def test_the_legal_footer_and_contact_lines_go_and_the_words_stay(self):
        out = triage.read_text(MAIL)
        self.assertTrue(out.startswith('You will have to resubmit for the correct amount'))
        self.assertNotIn('NOTICE', out); self.assertNotIn('erin@northwind.example', out)

    def test_the_mailboxs_own_cut_is_used_when_there_is_one(self):
        words = 'Yes - Thursday works for the review, and I will bring the reconciled export and the vendor list.'
        own = words + '\n\nRegards,\nErin Blake\nBilling Analyst'
        self.assertEqual(triage.read_text(words + '\n\nOn Mon, Ray wrote:\n> earlier', own), words)

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
        self.assertNotIn('NOTICE', got['ReadText'])


import unittest.mock  # noqa: E402
