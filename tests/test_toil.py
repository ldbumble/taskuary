"""The Automation-ideas report: toil.gather's evidence, the registry wiring, and the
weekly seed. No AI needed - the executor's raw output is what's under test.
"""
import json, unittest
from datetime import datetime, timedelta
from taskuary.store import MemoryStore

# the window gather() reads is the last N DAYS, so a stamp written into the test expires: '2026-08-23
# 08:00:00' sat inside a 30-day window until 08:00 on 2026-09-22, and failed every run after it.
def ago(days): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')


class AutomateReportTests(unittest.TestCase):
    def test_gather_and_registry(self):
        from taskuary.reports import REGISTRY, resolve_cfg
        from taskuary.toil import gather
        s = MemoryStore()
        for i in range(4):
            s.add_message({'ExternalId': f'n{i}', 'Channel': 'email', 'FromEmail': 'noise@vendor.com',
                           'Subject': f'Newsletter #{i}', 'SentAt': ago(3), 'Status': 'ignored'})
        txt = gather(s, days=30)
        self.assertIn('noise@vendor.com: 4 msgs', txt); self.assertIn('4 ignored', txt)
        head, body = REGISTRY['automate'](resolve_cfg(s, {'type': 'automate', 'days': 30}))
        self.assertIn('30 days', head); self.assertIn('noise@vendor.com', body)

    def test_a_sender_a_rule_already_drops_is_never_offered_again(self):
        """The report proposed a skip rule for a sender a skip rule had dropped thousands of times that month - the rule
        was the 29th of 32 and the evidence listed 25 (2026-09-29). Case differs, as it does between a rule and a header."""
        from taskuary.toil import gather
        s = MemoryStore()
        for i in range(24): s.save_policy({'Name': f'r{i}', 'Kind': 'sender', 'Pattern': f'other{i}@vendor.example', 'Action': 'ignore'}, 'owner')
        s.save_policy({'Name': 'skip flood', 'Kind': 'sender', 'Pattern': 'Alerts@Payworth.example', 'Action': 'skip'}, 'owner')
        s.save_policy({'Name': 'quiet', 'Kind': 'sender', 'Pattern': 'cards@spendly.example', 'Action': 'ignore'}, 'owner')
        for i in range(5):
            for who, st in (('alerts@payworth.example', 'skipped'), ('cards@spendly.example', 'ignored'), ('digest@trainly.example', 'ignored')):
                s.add_message({'ExternalId': f'{who}{i}', 'Channel': 'email', 'FromEmail': who, 'Subject': 'n', 'SentAt': ago(2), 'Status': st})
        txt = gather(s, days=30)
        inbound = txt.split('EXISTING POLICIES')[0]
        self.assertNotIn('payworth', inbound); self.assertNotIn('spendly', inbound)
        self.assertIn('digest@trainly.example: 5 msgs', inbound); self.assertIn('2 more senders left out', inbound)
        self.assertIn('cards@spendly.example', txt.split('EXISTING POLICIES')[1])     # every rule listed, none cut at 25

    def test_gather_pushes_date_and_status_filters_into_scan(self):
        from taskuary.toil import gather
        s = MemoryStore()
        s.add_message({'ExternalId': 'old', 'Channel': 'email', 'FromEmail': 'noise@vendor.com',
                       'Subject': 'Old', 'SentAt': ago(90), 'Status': 'ignored',
                       'BodyText': 'x' * 10000})
        s.add_message({'ExternalId': 'ctx', 'Channel': 'email', 'FromEmail': 'noise@vendor.com',
                       'Subject': 'Reply', 'SentAt': ago(3), 'Status': 'context',
                       'BodyText': 'x' * 10000})
        for i in range(3):
            s.add_message({'ExternalId': f'n{i}', 'Channel': 'email', 'FromEmail': 'noise@vendor.com',
                           'Subject': f'Newsletter #{i}', 'SentAt': ago(3), 'Status': 'ignored',
                           'BodyText': 'x' * 10000})
        txt = gather(s, days=30)
        self.assertIn('noise@vendor.com: 3 msgs', txt)
        self.assertNotIn('Old', txt)

    def test_gather_still_counts_the_mail_you_answered(self):
        """Only 'context' (your own replies) is excluded. 'sent' is an inbound message you ANSWERED
        and 'history' the other half of an imported thread - drop those and the report's evidence is
        the noise only, which is the one thing it exists to weigh against."""
        from taskuary.toil import gather
        from datetime import datetime, timedelta
        recent = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
        s = MemoryStore()
        for i, st in enumerate(['sent'] * 2 + ['history'] * 2 + ['feed', 'context']):
            s.add_message({'ExternalId': f'e{i}', 'Channel': 'email', 'FromEmail': 'client@real.com',
                           'Subject': f'Thread {i}', 'SentAt': recent, 'Status': st})
        self.assertIn('client@real.com: 5 msgs', gather(s, days=30))     # all but the one 'context' row

    def test_an_older_installs_row_is_weekly(self):
        from tests.automate_fixture import add_automate
        s = MemoryStore(); add_automate(s)                                # a fresh install no longer gets one (2026-09-25)
        src = next(x for x in s.list_sources() if x['Address'] == 'Automation ideas')
        cfg = json.loads(src['ConfigJson'])
        self.assertEqual((cfg['type'], cfg['cron']), ('automate', '0 8 * * 1'))


if __name__ == '__main__':
    unittest.main()
