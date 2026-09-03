import unittest
import json
from datetime import datetime, timedelta
from unittest import mock

from taskuary import evening, reports
from taskuary.store import MemoryStore


def _ago(hours):
    return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def _mail(store, external, subject, sender='person@example.com', hours=1, status='filed', body='Please review this.'):
    return store.add_message({'ExternalId': external, 'Channel': 'email', 'SourceName': 'owner@example.com',
                              'Subject': subject, 'FromName': sender.split('@')[0].title(), 'FromEmail': sender,
                              'SentAt': _ago(hours), 'BodyText': body, 'Status': status})


class EveningGatherTests(unittest.TestCase):
    def test_it_keeps_sent_invites_and_open_work_but_excludes_noise_and_old_mail(self):
        s = MemoryStore()
        s.set_setting('owner_email', 'owner@example.com', 'test')
        s.add_message({'ExternalId': 'sent', 'ConversationId': 'thread-1', 'Channel': 'email',
                       'SourceName': 'owner@example.com', 'Subject': 'Re: Budget', 'FromName': 'You',
                       'FromEmail': 'owner@example.com', 'SentAt': _ago(1), 'BodyText': 'Approved.',
                       'Status': 'context'})
        invite = _mail(s, 'invite', 'Invitation: Budget sync')
        s.add_route(invite, None, 'file', None, 'triage: fyi - a calendar invite - a meeting to be ready for', [], 'triage')
        open_mid = _mail(s, 'open', 'Renewal decision')
        tid = s.create_task({'Title': 'Renewal decision', 'Kind': 'general', 'Priority': 'urgent'}, 'test')
        s._exec('UPDATE message SET TaskId=?, Status=? WHERE MessageId=?', (tid, 'routed', open_mid))
        flagged = _mail(s, 'flagged', 'Contract question')
        s._exec('UPDATE message SET MailMetaJson=? WHERE MessageId=?',
                (json.dumps({'folder': 'inbox', 'focus': 'other', 'flag': 'flagged'}), flagged))
        custom = _mail(s, 'custom', 'Filed vendor note')
        s._exec('UPDATE message SET MailMetaJson=? WHERE MessageId=?',
                (json.dumps({'folder': 'custom-folder-id', 'focus': 'focused'}), custom))
        _mail(s, 'promo', 'September deals', 'marketing@vendor.example', body='Unsubscribe from this newsletter')
        _mail(s, 'receipt', 'Payment receipt', body='Your payment confirmation is attached.')
        _mail(s, 'old', 'Yesterday', hours=9)

        text = evening.gather(s, 8)
        self.assertIn('Re: Budget', text)
        self.assertIn('Invitation: Budget sync', text)
        self.assertIn('invite handled', text)
        self.assertIn('Renewal decision', text)
        self.assertIn('priority=urgent', text)
        self.assertIn('Contract question', text)
        self.assertIn('flagged=yes', text)
        self.assertIn('inbox_lane=other', text)
        self.assertNotIn('Filed vendor note', text)
        self.assertNotIn('September deals', text)
        self.assertNotIn('Payment receipt', text)
        self.assertNotIn('Yesterday', text)

    def test_the_evening_report_uses_the_assistant_voice_contract(self):
        s = MemoryStore()
        cfg = {'type': 'evening_inbox', 'hours': 8, 'ai_prompt': evening.PROMPT}
        seen = {}
        reports.render_report(s, cfg, llm=lambda system, user, **kw: seen.update(system=system, user=user) or 'brief')
        self.assertIn('EVENING INBOX BRIEF', seen['system'])
        self.assertIn('ACCOMPLISHED EVIDENCE', seen['user'])

    def test_a_stale_server_explains_that_the_new_report_type_needs_a_restart(self):
        s = MemoryStore()
        cfg = {'type': 'evening_inbox', 'hours': 8, 'ai_prompt': evening.PROMPT}
        with mock.patch.dict(reports.REGISTRY, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "not available in this running Taskuary.*Restart Taskuary"):
                reports.render_report(s, cfg)


class FirstScheduleTests(unittest.TestCase):
    def test_a_first_run_ritual_waits_until_its_daily_time(self):
        future_time = datetime.now() + timedelta(minutes=2)
        if future_time.day != datetime.now().day:
            self.skipTest('too close to midnight')
        self.assertFalse(reports.is_due({'daily_at': future_time.strftime('%H:%M'),
                                         'first_run_at_schedule': True}, None))

    def test_the_existing_immediate_first_run_default_is_unchanged(self):
        self.assertTrue(reports.is_due({'daily_at': '23:59'}, None))


if __name__ == '__main__':
    unittest.main()
