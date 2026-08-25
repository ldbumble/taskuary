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

    def test_a_cc_with_nothing_asked_stops_being_assumed_work(self):
        """The old blind default was 'task' - which is exactly wrong for the thread you are
        merely kept informed of, and it opened a task every single time."""
        cc = {'source_name': ME, 'to': ['dana@vendor.com'], 'cc': [ME], 'subject': 'Ledger'}
        self.assertEqual(triage.heuristic_intent({**cc, 'body': 'Attaching the reconciled ledger.'})['intent'], 'fyi')
        # ...but a cc that ASKS is still an ask, and a picture still goes to the AI to be read
        self.assertEqual(triage.heuristic_intent({**cc, 'body': 'Uri, please fix the export.'})['intent'], 'task')
        self.assertEqual(triage.heuristic_intent({**cc, 'body': 'Any update on the export?'})['intent'], 'reply_only')
        self.assertEqual(triage.heuristic_intent({**cc, 'body': 'See below.',
                                                  'images': [('image/png', 'AAAA')]})['intent'], 'task')
        # on the To line nothing changes: the same mail is still assumed to be real work
        to = {**cc, 'to': [ME], 'cc': [], 'body': 'Attaching the reconciled ledger.'}
        self.assertEqual(triage.heuristic_intent(to)['intent'], 'task')

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

    def test_a_triage_doc_written_before_addressing_existed_still_gets_the_rule(self):
        """Templates seed on first run only and the owner's edits are never overwritten, so
        every TRIAGE.md already on disk predates the field. The code that supplies the fact
        supplies the rule for reading it - unless the doc speaks about it itself."""
        seen = {}
        def llm(system, user, images=None):
            seen['system'] = system
            return '{"intent": "fyi", "why": "copied only"}'
        msg = {'source_name': ME, 'from_email': 'dana@vendor.com', 'subject': 'Ledger',
               'body': 'Attaching it.', 'to': ['dana@vendor.com'], 'cc': [ME]}
        triage.classify_intent(msg, llm=llm, system='My own rules. Answer JSON only.')
        self.assertIn('not an assignment', seen['system'])
        triage.classify_intent(msg, llm=llm, system='I decide addressed_to_you my own way.')
        self.assertNotIn('not an assignment', seen['system'])           # the doc keeps the last word
        # a channel with no recipient lines is never given a rule about lines it does not have
        triage.classify_intent({'source_name': ME, 'from_email': 'x@y.com', 'subject': 'hi', 'body': 'ping'},
                               llm=llm, system='My own rules.')
        self.assertNotIn('not an assignment', seen['system'])


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

    def test_a_silent_cc_files_without_spending_an_ai_call_at_all(self):
        """It used to become a task. Now the keyword pass settles it before any model is asked -
        no ask in it, no question in it, and the owner is only copied."""
        s = MemoryStore()
        cid = s.get_connector_by_type('outlook')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1,
                          'ConfigJson': '{"tenant_id": "t", "client_id": "c"}'}, 't')
        s.save_source({'Channel': 'email', 'Address': ME, 'ConnectorId': cid, 'Active': 1}, 't')
        with mock.patch.object(channels, 'graph_token', return_value='tok'), \
             mock.patch.object(channels, '_mail_msgs',
                               side_effect=lambda t, u, since, folder='inbox': [] if folder == 'sentitems'
                               else [_mail(['dana@vendor.com'], [ME])]), \
             mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: '{}'), \
             mock.patch('taskuary.ingest.classify_intent') as classify:
            channels.poll_channels(s)
        classify.assert_not_called()
        row = s.feed(limit=5)[0]
        self.assertEqual((row['MsgStatus'], row['TaskId']), ('filed', None))
        self.assertIn('only in cc', row['RouteReason'])       # the timeline says why, in those words

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
