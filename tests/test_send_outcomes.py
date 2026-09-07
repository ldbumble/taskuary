"""Confirmed sent, definitely failed, or unknown - and an explicit close when sending is unavailable (PW-143 to PW-150).

A send that timed out was reported as NOT SENT and offered for a retry that could deliver the same
mail twice; a channel that could not carry the reply left the owner with "No response required"
as the only exit; a reply that went out closed its task only from some doors. Now: a confirmed
send closes the task the reply belongs to - unchecked checklist items and all; a definite failure
keeps the draft and the task open with the error and a retry; a provider that did not answer is
delivery UNKNOWN - reconciled against the provider before any retry, never called sent or not sent
until it is known; and when sending is unavailable the owner has a separate, explicit Close without
sending that keeps the unsent draft, records the closure with its reason and never reads as Sent.
A clarification stays the one send that does not end the task: it asks, it does not answer.
"""
import json, unittest
from unittest import mock
import requests

from taskuary import outbound, verdicts
from taskuary.store import MemoryStore


def thread(kind='draft', channel='email'):
    s = MemoryStore()
    tid = s.create_task({'Title': 'August export', 'Kind': 'reply', 'Status': 'open', 'Priority': 'normal', 'Source': channel}, 'router')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'm1', 'ConversationId': 'AAQk-x', 'Channel': channel, 'SourceName': 'me@northwind.example',
                         'Subject': 'August export', 'FromName': 'Dana', 'FromEmail': 'dana@vendor.example', 'SentAt': '2026-09-06 09:00:00',
                         'BodyText': 'Could you send the August export?', 'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': kind, 'Status': 'pending', 'DraftText': 'Here it is.', 'Reason': 'needs a reply'})
    s.set_task_checklist(tid, ['Send the export', 'Confirm the totals'], 'triage')
    return s, tid, mid, rid


SENT = {'channel': 'email', 'to': ['dana@vendor.example'], 'cc': []}


class OutcomeTests(unittest.TestCase):
    def test_a_confirmed_send_closes_the_task_whatever_its_checklist_says(self):
        s, tid, mid, rid = thread()
        with mock.patch.object(outbound, 'reply_to_message', return_value=SENT):
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertTrue(out['ok']); self.assertEqual(out['status'], 'approved')
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        self.assertEqual([i['done'] for i in s.task_checklist(tid)], [False, False])      # closure ticks nothing
        self.assertEqual(s.get_review(rid)['Status'], 'approved')

    def test_a_definite_failure_keeps_the_draft_and_the_task_open_with_a_retry(self):
        s, tid, mid, rid = thread()
        with mock.patch.object(outbound, 'reply_to_message', side_effect=RuntimeError('graph sendMail failed (403): forbidden')):
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertIn('403', out['send_error']); self.assertEqual(out.get('delivery'), 'failed')
        self.assertEqual(s.get_task(tid)['Status'], 'open'); self.assertEqual(s.get_review(rid)['Status'], 'pending')
        self.assertEqual(s.get_review(rid)['DraftText'], 'Here it is.')
        with mock.patch.object(outbound, 'reply_to_message', return_value=SENT) as send:
            out2 = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertTrue(out2['ok']); send.assert_called_once(); self.assertEqual(s.get_task(tid)['Status'], 'done')

    def test_a_provider_that_did_not_answer_is_delivery_unknown_not_a_failure(self):
        s, tid, mid, rid = thread()
        with mock.patch.object(outbound, 'reply_to_message', side_effect=requests.exceptions.ReadTimeout('read timed out')), \
             mock.patch.object(outbound, 'reconcile_sent', return_value=None) as rec:
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        rec.assert_called_once()
        self.assertEqual(out['delivery'], 'unknown'); self.assertIn('unknown', out['send_error'].lower())
        self.assertNotIn('not sent', out['send_error'].lower())
        self.assertEqual(s.get_task(tid)['Status'], 'open'); self.assertEqual(s.get_review(rid)['Status'], 'pending')
        self.assertEqual(json.loads(s.get_review(rid)['Deliver'])['delivery'], 'unknown')

    def test_reconciliation_that_finds_the_mail_settles_it_as_sent_without_a_second_send(self):
        s, tid, mid, rid = thread()
        with mock.patch.object(outbound, 'reply_to_message', side_effect=requests.exceptions.ReadTimeout('read timed out')), \
             mock.patch.object(outbound, 'reconcile_sent', return_value={'channel': 'email', 'to': ['dana@vendor.example'], 'id': 'AAMk'}):
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertTrue(out['ok']); self.assertEqual(out['delivery'], 'reconciled')
        self.assertEqual(s.get_task(tid)['Status'], 'done'); self.assertEqual(s.get_review(rid)['Status'], 'approved')

    def test_a_retry_while_unknown_reconciles_first_and_sends_only_when_the_provider_has_nothing(self):
        s, tid, mid, rid = thread()
        with mock.patch.object(outbound, 'reply_to_message', side_effect=requests.exceptions.ReadTimeout('t')), \
             mock.patch.object(outbound, 'reconcile_sent', return_value=None):
            verdicts.decide(s, s.get_review(rid), 'approve')
        with mock.patch.object(outbound, 'reply_to_message', return_value=SENT) as send, \
             mock.patch.object(outbound, 'reconcile_sent', return_value={'channel': 'email', 'to': ['dana@vendor.example'], 'id': 'AAMk'}) as rec:
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        rec.assert_called_once(); send.assert_not_called(); self.assertTrue(out['ok'])                  # it had gone out after all
        s2, tid2, mid2, rid2 = thread()
        with mock.patch.object(outbound, 'reply_to_message', side_effect=requests.exceptions.ReadTimeout('t')), \
             mock.patch.object(outbound, 'reconcile_sent', return_value=None):
            verdicts.decide(s2, s2.get_review(rid2), 'approve')
        with mock.patch.object(outbound, 'reply_to_message', return_value=SENT) as send2, \
             mock.patch.object(outbound, 'reconcile_sent', return_value=None):
            out2 = verdicts.decide(s2, s2.get_review(rid2), 'approve')
        send2.assert_called_once(); self.assertTrue(out2['ok'])                                          # nothing there: the retry is safe


class CloseWithoutSendingTests(unittest.TestCase):
    def test_when_sending_is_unavailable_the_owner_can_close_without_sending_and_nothing_reads_as_sent(self):
        s, tid, mid, rid = thread(channel='github')
        s.set_setting('github_reply_enabled', '0', 't')
        with mock.patch.object(outbound, 'can_reply', return_value=False), mock.patch.object(outbound, 'send_block', return_value='GitHub replies are off (GitHub card)'), \
             mock.patch.object(outbound, 'reply_to_message') as send:
            out = verdicts.decide(s, s.get_review(rid), 'close_unsent')
        send.assert_not_called()
        self.assertTrue(out['ok']); self.assertEqual(out['status'], 'closed_unsent'); self.assertIsNone(out['sent'])
        rv = s.get_review(rid)
        self.assertEqual((rv['Status'], rv['DraftText']), ('closed_unsent', 'Here it is.'))                # the unsent draft is kept
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        bodies = ' '.join(c['Body'] for c in s.list_comments(tid))
        self.assertIn('without sending', bodies); self.assertIn('GitHub replies are off', bodies); self.assertNotIn('Sent by', bodies)
        again = verdicts.decide(s, s.get_review(rid), 'close_unsent')
        self.assertTrue(again.get('already'))

    def test_closing_without_sending_is_the_owners_word_never_an_automatic_consequence_of_a_failed_send(self):
        s, tid, mid, rid = thread()
        with mock.patch.object(outbound, 'reply_to_message', side_effect=RuntimeError('graph sendMail failed (500): boom')):
            verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertEqual(s.get_task(tid)['Status'], 'open'); self.assertEqual(s.get_review(rid)['Status'], 'pending')


class ClarificationTests(unittest.TestCase):
    def test_a_clarification_asks_and_leaves_the_task_waiting(self):
        s, tid, mid, rid = thread(kind='clarification')
        with mock.patch.object(outbound, 'reply_to_message', return_value=SENT):
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertTrue(out['ok']); self.assertEqual(s.get_task(tid)['Status'], 'waiting')



class SendProbeTests(unittest.TestCase):
    """PW-143/146: a permission that is already known to be missing is said BEFORE the first send is tried -
    Send is hidden with the reason on it, while drafting and reading carry on."""
    def _card(self, s, ctype, cfg):
        cid = next(c['ConnectorId'] for c in s.list_connectors() if c['Type'] == ctype)
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'ConfigJson': json.dumps(cfg)}, 'owner')
        return cid

    def test_an_imap_card_with_no_smtp_host_hides_send_and_names_the_missing_host(self):
        s, *_ = thread()
        cid = self._card(s, 'imap', {'address': 'me@northwind.example'})
        self.assertIn('SMTP', outbound.send_probe(s, 'email'))
        self.assertIn('me@northwind.example', outbound.send_probe(s, 'email'))
        self.assertFalse(outbound.can_reply(s, 'email')); self.assertIn('SMTP', outbound.send_block(s, 'email'))
        s.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps({'address': 'me@northwind.example', 'imap_host': 'imap.northwind.example',
                                                                       'smtp_host': 'smtp.northwind.example'})}, 'owner')
        self.assertEqual(outbound.send_probe(s, 'email'), ''); self.assertTrue(outbound.can_reply(s, 'email'))

    def test_a_microsoft_sign_in_without_mail_send_is_named_before_any_send_is_tried(self):
        s, *_ = thread()
        cid = self._card(s, 'outlook', {'account': 'me@northwind.example', 'granted_scope': 'User.Read Mail.Read offline_access'})
        self.assertIn('Mail.Send', outbound.send_probe(s, 'email'))
        self.assertFalse(outbound.can_reply(s, 'email')); self.assertIn('Outlook card', outbound.send_block(s, 'email'))
        s.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps({'account': 'me@northwind.example',
                                                                       'granted_scope': 'User.Read Mail.ReadWrite Mail.Send'})}, 'owner')
        self.assertEqual(outbound.send_probe(s, 'email'), ''); self.assertTrue(outbound.can_reply(s, 'email'))

    def test_a_sign_in_that_never_recorded_its_scopes_is_not_accused_of_missing_one(self):
        s, *_ = thread()
        self._card(s, 'outlook', {'account': 'me@northwind.example'})
        self.assertEqual(outbound.send_probe(s, 'email'), '')

    def test_one_card_that_can_send_is_enough(self):
        s, *_ = thread()
        self._card(s, 'imap', {'address': 'broken@northwind.example'})
        self._card(s, 'outlook', {'account': 'me@northwind.example', 'granted_scope': 'Mail.Send'})
        self.assertEqual(outbound.send_probe(s, 'email'), '')
        self.assertIn('SMTP', outbound.send_probe(s, 'email', mailbox='broken@northwind.example'))

    def test_the_review_payload_hides_send_with_the_reason_on_it(self):
        s, tid, mid, rid = thread()
        self._card(s, 'imap', {'address': 'me@northwind.example'})
        msg = s.get_message(mid)
        can = outbound.can_reply(s, msg['Channel'])
        self.assertFalse(can); self.assertIn('SMTP', outbound.send_block(s, msg['Channel']))

    def test_the_token_exchange_keeps_the_scopes_microsoft_granted(self):
        from taskuary import msauth
        self.assertEqual(msauth._tokens({'access_token': 'a', 'refresh_token': 'r', 'expires_in': 3600,
                                         'scope': 'User.Read Mail.Send'})['scope'], 'User.Read Mail.Send')
        self.assertIsNone(msauth._tokens({'access_token': 'a'})['scope'])

if __name__ == '__main__':
    unittest.main()
