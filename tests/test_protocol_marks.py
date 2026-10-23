"""Before a model reads a mail, only its PROTOCOL may say what it is - an auto-reply, a calendar message, a system or
a list sender. Subject prefixes and address/footer word lists decided it before, and a person's mail landed as a robot
(the owner, 2026-10-11: "everything should be ai"). After the model reads it, its `sender_class` is the word."""
import email, json, unittest
from unittest import mock

from taskuary import ingest, triage
from taskuary.imapmail import protocol_marks
from taskuary.store import MemoryStore


def raw(head, body='hello'): return email.message_from_string(f'{head}\n\n{body}')


class ImapMarksTests(unittest.TestCase):
    def test_what_the_raw_mail_says(self):
        self.assertEqual(protocol_marks(raw('From: Erin Blake <erin@northwind.example>\nSubject: Out of office coverage - can you?')), {})
        self.assertEqual(protocol_marks(raw('Auto-Submitted: auto-replied')), {'auto_reply': True, 'sender_class': 'automated'})
        self.assertEqual(protocol_marks(raw('List-Unsubscribe: <mailto:u@vendor.example>')),
                         {'sender_class': 'bulk', 'unsub': {'via': 'mailto', 'mailto': 'mailto:u@vendor.example'}})
        ics = raw('Subject: Budget sync\nContent-Type: multipart/mixed; boundary=b',
                  '--b\nContent-Type: text/plain\n\nJoin\n--b\nContent-Type: text/calendar; method=REQUEST\n\nBEGIN:VCALENDAR\nEND:VCALENDAR\n--b--\n')
        self.assertEqual(protocol_marks(ics), {'invite': True, 'mail_meta': {'invite': True}})


class VerdictClassTests(unittest.TestCase):
    def test_the_schema_asks_and_the_answer_is_validated(self):
        self.assertEqual(triage.verdict_schema()['schema']['properties']['sender_class']['enum'], ['person', 'automated', 'bulk'])
        def llm(cls): return lambda system, user, **k: json.dumps({'intent': 'fyi', 'why': 'x', 'title': 't', 'summary': 's', 'sender_class': cls})
        self.assertEqual(triage.classify_intent({'subject': 'x', 'body': 'y'}, llm=llm('automated'))['sender_class'], 'automated')
        self.assertNotIn('sender_class', triage.classify_intent({'subject': 'x', 'body': 'y'}, llm=llm('robot')))

    def test_a_colleague_at_info_is_a_person_on_the_timeline(self):
        """No header, and the model says person: the info@ address and the footer no longer make it promo or automated."""
        s = MemoryStore(); s.set_setting('coding_auto_enabled', '0', 't')
        llm = lambda system, user, **k: json.dumps({'intent': 'fyi', 'why': 'keeps you posted', 'title': 'Q3 figures posted',
                                                     'summary': 'Erin posted them.', 'sender_class': 'person'})
        with mock.patch.object(ingest, '_spawn'):
            out = ingest.ingest_message(s, {'external_id': 'g:info', 'channel': 'email', 'subject': 'Q3 figures', 'from_name': 'Erin Blake',
                                            'from_email': 'info@northwind.example', 'body': 'Posted. Please do not reply to this email. Unsubscribe',
                                            'source_name': 'alex@northwind.example'}, llm=llm)
        self.assertEqual(s.get_message(out['message_id'])['SenderClass'], 'person')
        self.assertEqual(s.feed(limit=3)[0]['Category'], 'info')

    def test_a_list_header_rides_in_until_the_verdict(self):
        s = MemoryStore()
        with mock.patch.object(ingest, '_spawn'):
            out = ingest.ingest_message(s, {'external_id': 'g:news', 'channel': 'email', 'subject': 'September deals', 'from_email': 'news@vendor.example',
                                            'body': 'Deals.', 'source_name': 'alex@northwind.example', 'sender_class': 'bulk'}, llm=None)
        self.assertEqual(s.get_message(out['message_id'])['SenderClass'], 'bulk')


if __name__ == '__main__': unittest.main()
