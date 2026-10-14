"""The draft's title and explanation are written by a model from the SCRUBBED facts only: it never
sees mail or tasks, so it cannot put them in, and what it writes is scrubbed again anyway."""
import json, tempfile, unittest
from pathlib import Path
from unittest import mock

from taskuary import bugreport
from test_bugreport_scrub import PRIVATE, seeded

CLIENT = {'screen': 'Work', 'route': '/api/tasks/12/code',
          'error': "TypeError: cannot read 'Renew the Payworth contract' for erin@northwind.example",
          'stack': 'at openTask (C:\\Users\\alexd\\app\\index.js:10:5)',
          'actions': ['opened a task', 'pressed Code'], 'at': '2026-10-14T10:00:50'}


class FakeBrain:
    def __init__(self, answer): self.answer, self.calls = answer, []
    def __call__(self, system, user, **kw):
        self.calls.append((system, user, kw)); return json.dumps(self.answer)


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.s, home = seeded(), Path(tempfile.mkdtemp())
        (home / 'taskuary.log').write_text('2026-10-14 10:00:50 ERROR   taskuary.server:9 failed for Erin Blake on northwind/ledger\n',
                                           encoding='utf-8')
        p = mock.patch('taskuary.config.home', return_value=home); p.start(); self.addCleanup(p.stop)

    def test_the_brain_sees_only_scrubbed_facts(self):
        b = FakeBrain({'title': 'Opening a task fails', 'explanation': 'Pressed Code. It failed. It should open.'})
        d = bugreport.draft(self.s, CLIENT, llm=b)
        system, user, kw = b.calls[0]
        for p in PRIVATE: self.assertNotIn(p.lower(), (system + user).lower(), p)
        self.assertIn('TypeError', user); self.assertIn('[removed]', user); self.assertEqual(300, kw.get('max_tokens'))
        self.assertEqual('Opening a task fails', d['title']); self.assertEqual('Pressed Code. It failed. It should open.', d['explanation'])
        self.assertEqual({'title', 'explanation', 'where', 'error', 'env', 'log', 'actions', 'fingerprint'}, set(d))

    def test_every_string_in_the_draft_is_scrubbed(self):
        d = bugreport.draft(self.s, CLIENT, llm=FakeBrain({'title': 't', 'explanation': 'e'}))
        blob = json.dumps(d).lower()
        for p in PRIVATE: self.assertNotIn(p.lower(), blob, p)
        self.assertIn('~\\\\app\\\\index.js', blob)

    def test_the_answer_is_scrubbed_again(self):
        b = FakeBrain({'title': 'Erin Blake cannot open Renew the Payworth contract ' + 'x' * 80,
                       'explanation': 'Gail Moreno pressed Code for erin@northwind.example.'})
        d = bugreport.draft(self.s, CLIENT, llm=b)
        self.assertNotIn('Erin', d['title']); self.assertIn('[removed]', d['title']); self.assertLessEqual(len(d['title']), 80)
        self.assertNotIn('Gail', d['explanation']); self.assertNotIn('northwind', d['explanation'])

    def test_no_brain_means_the_errors_first_line(self):
        with mock.patch('taskuary.llm.build_llm', return_value=None) as build:
            d = bugreport.draft(self.s, {**CLIENT, 'error': 'RangeError: ' + 'y' * 200 + '\nsecond line'})
        build.assert_called_once(); self.assertEqual('light', build.call_args.kwargs.get('gear'))
        self.assertEqual(('RangeError: ' + 'y' * 200)[:80], d['title']); self.assertEqual('', d['explanation'])

    def test_a_brain_that_fails_or_says_nothing_falls_back(self):
        def broken(*a, **kw): raise RuntimeError('down')
        d = bugreport.draft(self.s, CLIENT, llm=broken)
        self.assertTrue(d['title'].startswith('TypeError')); self.assertEqual('', d['explanation'])
        d = bugreport.draft(self.s, CLIENT, llm=FakeBrain({}))
        self.assertTrue(d['title'].startswith('TypeError'))

    def test_no_error_at_all_still_has_a_title(self):
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertEqual('Something is wrong', bugreport.draft(self.s, {})['title'])

    def test_unsafe_propagates(self):
        b = FakeBrain({'title': 't', 'explanation': 'e'})
        with mock.patch.object(self.s, 'people', side_effect=RuntimeError('db locked')), self.assertRaises(bugreport.Unsafe):
            bugreport.draft(self.s, CLIENT, llm=b)
        self.assertEqual([], b.calls)                                 # nothing reached the model either


if __name__ == '__main__':
    unittest.main()
