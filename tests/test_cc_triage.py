"""Being COPIED on a thread is not being handed a job - and the funnel could not tell, because
nothing ever collected the To/Cc lines. These cover the whole path: the recipients arriving off
Graph and IMAP, the relationship derived from them, and both classifiers using it.
"""
import unittest
from datetime import datetime, timedelta
from email.message import EmailMessage
from unittest import mock

from taskuary import channels, imapmail, triage
from taskuary.store import MemoryStore

ME = 'owner@ours.com'
FRESH = (datetime.now() - timedelta(minutes=5)).isoformat()


def _mail(to, cc, subject='Quarterly ledger', body='<html><body>Attaching the reconciled ledger.</body></html>'):
    return {'id': 'm1', 'subject': subject, 'body': {'contentType': 'html', 'content': body},
            'from': {'emailAddress': {'name': 'Dana', 'address': 'dana@vendor.com'}},
            'toRecipients': [{'emailAddress': {'address': a}} for a in to],
            'ccRecipients': [{'emailAddress': {'address': a}} for a in cc],
            'receivedDateTime': FRESH, 'conversationId': 'c1', 'webLink': 'http://x', 'isRead': True}


class AddressingTests(unittest.TestCase):
    def test_how_the_owner_sits_on_a_message(self):
        m = lambda to, cc: {'source_name': ME, 'to': to, 'cc': cc}
        self.assertEqual(triage.addressed_to_you(m(['dana@vendor.com'], [ME])), 'cc')
        self.assertEqual(triage.addressed_to_you(m(['OWNER@Ours.com'], [])), 'to')       # case is not identity
        self.assertEqual(triage.addressed_to_you(m(['ops-list@ours.com'], [])), 'not named')
        self.assertEqual(triage.addressed_to_you({'source_name': ME}), '')               # chat: no lines at all
        self.assertEqual(triage.addressed_to_you({'to': [ME]}), '')                      # no mailbox to compare

    def test_the_keyword_pass_never_decides_a_cc_by_itself(self):
        """It used to: a quiet cc was FILED as fyi by keyword, before any model saw it. But plenty
        of cc'd mail is genuinely yours - the sender put you in cc and addressed you in the body -
        and reading that off the header alone is a guess wearing a rule's clothing. The signal goes
        to the classifier as evidence; the classifier decides."""
        cc = {'source_name': ME, 'to': ['dana@vendor.com'], 'cc': [ME], 'subject': 'Ledger'}
        quiet = triage.heuristic_intent({**cc, 'body': 'Attaching the reconciled ledger.'}, {ME})
        self.assertNotEqual(quiet['intent'], 'fyi')
        self.assertNotIn('cc', quiet['why'])
        # the keyword pass still reads what the message SAYS - that part was never the problem
        self.assertEqual(triage.heuristic_intent({**cc, 'body': 'Uri, please fix the export.'})['intent'], 'task')
        self.assertEqual(triage.heuristic_intent({**cc, 'body': 'Any update on the export?'})['intent'], 'reply_only')
        self.assertEqual(triage.heuristic_intent({**cc, 'body': 'FYI - no action needed.'})['intent'], 'fyi')

    def test_the_classifier_is_told_the_relationship_and_never_the_mailbox(self):
        seen = {}
        def llm(system, user, images=None):
            seen['system'], seen['user'] = system, user
            return '{"intent": "fyi", "why": "you are only copied"}'
        msg = {'source_name': ME, 'from_email': 'dana@vendor.com', 'subject': 'Ledger',
               'body': 'Attaching it.', 'to': ['dana@vendor.com', 'b@vendor.com'], 'cc': [ME]}
        self.assertEqual(triage.classify_intent(msg, llm=llm)['intent'], 'fyi')
        self.assertIn('"addressed_to_you": "cc"', seen['user'])
        self.assertIn('"recipients": 3', seen['user'])
        # 0.2.1 decided no addresses go into prompts; the relationship is the fact, not the mailbox
        self.assertNotIn(ME, seen['user'] + seen['system'])

    def test_the_code_supplies_the_signal_and_never_a_rule_about_it(self):
        """How much a cc counts for is a judgement, and judgement belongs in TRIAGE.md where the
        owner can argue with it - so nothing is appended to their document behind their back. An
        untouched doc tracks the shipped template, which is how the paragraph gets there."""
        seen = {}
        def llm(system, user, images=None):
            seen['system'], seen['user'] = system, user
            return '{"intent": "task", "why": "addressed to me in the body"}'
        msg = {'source_name': ME, 'from_email': 'dana@vendor.com', 'subject': 'Ledger',
               'body': 'Uri - can you confirm the ledger?', 'to': ['dana@vendor.com'], 'cc': [ME]}
        out = triage.classify_intent(msg, llm=llm, system='My own rules. Answer JSON only.', mine={ME})
        self.assertEqual(seen['system'], 'My own rules. Answer JSON only.')   # not one word added
        self.assertIn('"addressed_to_you": "cc"', seen['user'])               # the signal is there
        # and a cc CAN be the owner's work: nothing in the pipeline overrides that verdict
        self.assertEqual(out['intent'], 'task')

    def test_the_shipped_document_carries_the_signal_as_a_signal(self):
        from pathlib import Path
        doc = (Path(__file__).parent.parent / 'taskuary' / 'templates' / 'triage.md').read_text(encoding='utf-8')
        self.assertIn('SIGNALS to weigh, not rules to obey', doc)
        self.assertIn('a cc can plainly be yours', doc)
        self.assertIn('never decide on them alone', doc)
        # the fallback for a blanked document says the same thing
        self.assertIn('never rules to obey', triage.INTENT_SYSTEM)


class RecipientsOffTheWireTests(unittest.TestCase):
    def test_graph_hands_the_lines_to_triage_and_a_cc_only_mail_files_itself(self):
        s = MemoryStore()
        cid = s.get_connector_by_type('outlook')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1,
                          'ConfigJson': '{"tenant_id": "t", "client_id": "c"}'}, 't')
        s.save_source({'Channel': 'email', 'Address': ME, 'ConnectorId': cid, 'Active': 1}, 't')
        self.assertIn('ccRecipients', channels.MAIL_SELECT)      # it was never even requested before
        seen = {}
        def classify(msg, **kw):
            seen.update(msg)
            return {'intent': 'fyi', 'why': 'you are only in cc'}
        # a QUESTION, so the heuristic hands it on and the classifier is the one that sees the
        # lines - the silent cc-only mail never gets that far, which is the next test
        mail = _mail(['dana@vendor.com', 'lee@vendor.com'], [ME],
                     body='<html><body>Any update on the ledger?</body></html>')
        with mock.patch.object(channels, 'graph_token', return_value='tok'), \
             mock.patch.object(channels, '_mail_msgs',
                               side_effect=lambda t, u, since, folder='inbox': [] if folder == 'sentitems' else [mail]), \
             mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: '{}'), \
             mock.patch('taskuary.ingest.classify_intent', classify):
            channels.poll_channels(s)
        self.assertEqual((seen['to'], seen['cc']), (['dana@vendor.com', 'lee@vendor.com'], [ME]))
        row = s.feed(limit=5)[0]
        self.assertEqual((row['MsgStatus'], row['TaskId']), ('filed', None))

    def test_a_silent_cc_reaches_the_classifier_rather_than_being_settled_for_free(self):
        """The cheap answer was to file it by keyword. The right answer is to let the model read
        it with the signal in hand, because some of that mail is the owner's."""
        s = MemoryStore()
        cid = s.get_connector_by_type('outlook')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1,
                          'ConfigJson': '{"tenant_id": "t", "client_id": "c"}'}, 't')
        s.save_source({'Channel': 'email', 'Address': ME, 'ConnectorId': cid, 'Active': 1}, 't')
        seen = {}
        def classify(msg, **kw):
            seen.update(msg)
            return {'intent': 'fyi', 'why': 'copied on somebody else\'s ledger thread'}
        with mock.patch.object(channels, 'graph_token', return_value='tok'), \
             mock.patch.object(channels, '_mail_msgs',
                               side_effect=lambda t, u, since, folder='inbox': [] if folder == 'sentitems'
                               else [_mail(['dana@vendor.com'], [ME])]), \
             mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: '{}'), \
             mock.patch('taskuary.ingest.classify_intent', classify):
            channels.poll_channels(s)
        self.assertEqual(seen['cc'], [ME])                    # the classifier got the signal
        row = s.feed(limit=5)[0]
        self.assertEqual((row['MsgStatus'], row['TaskId']), ('filed', None))
        self.assertIn('copied on', row['RouteReason'])         # and its OWN reason, not a keyword's

    def test_imap_reads_the_same_two_headers(self):
        m = EmailMessage()
        m['From'], m['Subject'] = 'Dana <dana@vendor.com>', 'Ledger'
        m['To'] = 'Lee <lee@vendor.com>, ops@vendor.com'
        m['Cc'] = f'Owner <{ME}>'
        m.set_content('Attaching it.')
        self.assertEqual(imapmail._hdr_addrs(m, 'To'), ['lee@vendor.com', 'ops@vendor.com'])
        self.assertEqual(imapmail._hdr_addrs(m, 'Cc'), [ME])
        self.assertEqual(imapmail._hdr_addrs(m, 'Bcc'), [])        # a header that is not there


if __name__ == '__main__':
    unittest.main()
