"""The Automation-ideas report: toil.gather's evidence, the registry wiring, and the
weekly seed. No AI needed - the executor's raw output is what's under test.
"""
import json, unittest
from taskuary.store import MemoryStore


class AutomateReportTests(unittest.TestCase):
    def test_gather_and_registry(self):
        from taskuary.reports import REGISTRY, resolve_cfg
        from taskuary.toil import gather
        s = MemoryStore()
        for i in range(4):
            s.add_message({'ExternalId': f'n{i}', 'Channel': 'email', 'FromEmail': 'noise@vendor.com',
                           'Subject': f'Newsletter #{i}', 'SentAt': '2026-08-23 08:00:00', 'Status': 'ignored'})
        txt = gather(s, days=30)
        self.assertIn('noise@vendor.com: 4 msgs', txt); self.assertIn('4 ignored', txt)
        head, body = REGISTRY['automate'](resolve_cfg(s, {'type': 'automate', 'days': 30}))
        self.assertIn('30 days', head); self.assertIn('noise@vendor.com', body)

    def test_gather_pushes_date_and_status_filters_into_scan(self):
        from taskuary.toil import gather
        s = MemoryStore()
        s.add_message({'ExternalId': 'old', 'Channel': 'email', 'FromEmail': 'noise@vendor.com',
                       'Subject': 'Old', 'SentAt': '2026-07-01 08:00:00', 'Status': 'ignored',
                       'BodyText': 'x' * 10000})
        s.add_message({'ExternalId': 'ctx', 'Channel': 'email', 'FromEmail': 'noise@vendor.com',
                       'Subject': 'Reply', 'SentAt': '2026-09-10 08:00:00', 'Status': 'context',
                       'BodyText': 'x' * 10000})
        for i in range(3):
            s.add_message({'ExternalId': f'n{i}', 'Channel': 'email', 'FromEmail': 'noise@vendor.com',
                           'Subject': f'Newsletter #{i}', 'SentAt': '2026-09-10 08:00:00', 'Status': 'ignored',
                           'BodyText': 'x' * 10000})
        txt = gather(s, days=30)
        self.assertIn('noise@vendor.com: 3 msgs', txt)
        self.assertNotIn('Old', txt)

    def test_seeded_weekly(self):
        s = MemoryStore()
        src = next(x for x in s.list_sources() if x['Address'] == 'Automation ideas')
        cfg = json.loads(src['ConfigJson'])
        self.assertEqual((cfg['type'], cfg['cron']), ('automate', '0 8 * * 1'))


if __name__ == '__main__':
    unittest.main()
