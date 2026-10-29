"""The external-sender banner, a mail app's stamp and a legal footer are left off what a screen shows (2026-09-23) - and which
text is one is triage's word (its verdict's `wrapper`), never a phrase list in Python or on the screen (the owner, 2026-10-28)."""
import json, unittest
from unittest import mock
from pathlib import Path

from taskuary import triage

ROOT = Path(__file__).resolve().parents[1]
WRAP = ('This email was sent from outside of Northwind. ** Do not click links or download attachments unless you '
        'know the content is safe.**')
ASK = 'Did you put in my raise to be effective this paycheck? My hire date was September 4.'
SAMPLE = f'{WRAP}\n\n{ASK}'


class WrapperIsTheModelsWordTests(unittest.TestCase):
    def test_no_phrase_list_is_left(self):
        for name in ('_BANNER', '_CLUTTER', '_LEGAL'): self.assertFalse(hasattr(triage, name), name)
        self.assertNotIn('export const BANNER', (ROOT / 'website' / 'src' / 'ui.jsx').read_text(encoding='utf-8'))

    def test_what_triage_named_is_left_out_and_nothing_else(self):
        self.assertEqual(triage.strip_wrapper(SAMPLE, (WRAP,)), ASK)
        self.assertEqual(triage.strip_wrapper(SAMPLE), SAMPLE)                    # not judged: shown as it came
        self.assertEqual(triage.strip_wrapper(WRAP, (WRAP,)), WRAP)               # never cut to nothing

    def test_a_made_up_passage_is_not_kept_on_the_verdict(self):
        self.assertEqual(triage.wrapper_in({'wrapper': [WRAP, 'Unsubscribe here']}, SAMPLE), [WRAP])

    def test_the_verdict_carries_it(self):
        llm = lambda *a, **k: json.dumps({'intent': 'reply_only', 'why': 'asks about pay', 'wrapper': [WRAP, 'not in the mail']})
        v = triage.classify_intent({'subject': 'raise', 'body': SAMPLE, 'from_name': 'Erin Blake'}, llm=llm)
        self.assertEqual(v.get('wrapper'), [WRAP])
        self.assertIn('wrapper', triage.verdict_schema([], None, [], [])['schema']['properties'])

    def test_the_phone_reads_it_the_same_way(self):
        from taskuary import remote_assistant
        from taskuary.store import MemoryStore
        s = MemoryStore()
        mid = s.add_message({'ExternalId': 'b1', 'Channel': 'teams', 'FromName': 'Erin Blake', 'Subject': 'raise',
                             'BodyText': SAMPLE, 'SentAt': '2026-09-23 09:00:00', 'Status': 'open'})
        with mock.patch.object(s, 'message_verdict', lambda m: {'intent': 'fyi', 'wrapper': [WRAP]}):
            block = remote_assistant.decision_block(s, {'mid': mid, 'kind': 'asked'})
        self.assertNotIn('sent from outside', block); self.assertIn('hire date was September 4', block)


if __name__ == '__main__':
    unittest.main()
