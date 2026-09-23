"""The external-sender banner is stripped by ONE rule, written twice: triage._BANNER for what the
model and the phone read, ui.jsx BANNER for what every screen shows (2026-09-23). They must match."""
import re, unittest
from pathlib import Path

from taskuary import triage

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ('This email was sent from outside of Northwind. ** Do not click links or download attachments unless you '
          'know the content is safe. If you are not sure whether this email is safe, contact the Northwind Helpdesk.**'
          '\n\nDid you put in my raise to be effective this paycheck? My hire date was September 4.')


class OneBannerRuleTests(unittest.TestCase):
    def test_the_screens_rule_is_triages_rule(self):
        js = (ROOT / 'website' / 'src' / 'ui.jsx').read_text(encoding='utf-8')
        m = re.search(r'export const BANNER = /(.+)/gi;', js)
        self.assertIsNotNone(m, 'ui.jsx lost its BANNER')
        self.assertEqual(m.group(1), triage._BANNER.pattern)

    def test_what_is_shown_is_what_was_said(self):
        self.assertEqual(triage.strip_banner(SAMPLE), 'Did you put in my raise to be effective this paycheck? My hire date was September 4.')
        self.assertEqual(triage.strip_banner('Just the words.'), 'Just the words.')

    def test_the_phone_reads_it_the_same_way(self):
        from taskuary import remote_assistant
        from taskuary.store import MemoryStore
        s = MemoryStore()
        mid = s.add_message({'ExternalId': 'b1', 'Channel': 'teams', 'FromName': 'Erin Blake', 'Subject': 'raise',
                             'BodyText': SAMPLE, 'SentAt': '2026-09-23 09:00:00', 'Status': 'open'})
        block = remote_assistant.decision_block(s, {'mid': mid, 'kind': 'asked'})
        self.assertNotIn('sent from outside', block); self.assertIn('hire date was September 4', block)
