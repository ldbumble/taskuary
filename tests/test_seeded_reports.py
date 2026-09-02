"""What a fresh install already has running.

Three reports ship: the Morning digest (an AI pass over the hub's own data), the Assistant (a
voice on the Timeline) and Automation ideas (the weekly 'what should you automate next' brief).
Each is a real report - prompt on the Reports tab, deleting the row is the off switch, and a
sentinel setting keeps a deletion deleted across restarts.

Automation ideas was the odd one out: seeded on a Monday cron alone, so a fresh install saw
nothing from the third shipped report until the following Monday. It now greets a launch too -
at most once a WEEK, because a weekly brief filed on seven launches running is exactly the noise
once_per_day was invented to stop, one rung up.
"""
import json
import unittest
from datetime import datetime, timedelta

from taskuary.reports import is_due
from taskuary.store import MemoryStore


def _reports(s):
    return {r['Address']: json.loads(r['ConfigJson'] or '{}') for r in s.list_sources() if r['Channel'] == 'report'}


def _ago(days):
    return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')


class WhatShipsTests(unittest.TestCase):
    def test_the_three_shipped_reports_are_there_and_active(self):
        got = _reports(MemoryStore())
        self.assertEqual(sorted(got), ['Assistant', 'Automation ideas', 'Morning digest'])
        self.assertEqual([got[n]['type'] for n in ('Morning digest', 'Automation ideas', 'Assistant')],
                         ['digest', 'automate', 'assistant'])

    def test_all_three_have_something_to_say_the_moment_the_app_opens(self):
        """The tab is worth opening on day one only if every shipped report has filed."""
        got = _reports(MemoryStore())
        for name in ('Morning digest', 'Automation ideas', 'Assistant'):
            self.assertTrue(is_due(got[name], None, startup=True), name)

    def test_automation_ideas_keeps_its_monday_clock(self):
        cfg = _reports(MemoryStore())['Automation ideas']
        self.assertEqual(cfg['cron'], '0 8 * * 1')
        self.assertTrue(cfg['once_per_week'])


class OncePerWeekTests(unittest.TestCase):
    """The launch rule on its own - a clock beside it fires on its own terms, as it always did."""
    CFG = {'on_startup': True, 'once_per_week': True}

    def test_a_second_launch_the_same_week_files_nothing(self):
        self.assertFalse(is_due(self.CFG, _ago(2), startup=True))

    def test_a_launch_after_a_week_of_silence_files_again(self):
        self.assertTrue(is_due(self.CFG, _ago(8), startup=True))

    def test_a_plain_sync_is_never_the_launch_rule(self):
        self.assertFalse(is_due(self.CFG, _ago(8), startup=False))

    def test_the_daily_brief_still_gets_a_launch_a_day(self):
        daily = {'on_startup': True, 'once_per_day': True}
        self.assertFalse(is_due(daily, datetime.now().strftime('%Y-%m-%d 06:00:00'), startup=True))
        self.assertTrue(is_due(daily, _ago(1), startup=True))

    def test_a_never_run_report_is_due_whatever_the_rule_says(self):
        self.assertTrue(is_due(self.CFG, None, startup=True))
        self.assertTrue(is_due({'on_startup': True, 'once_per_day': True}, None, startup=True))

    def test_a_stamp_it_cannot_read_is_not_a_reason_to_stay_silent(self):
        self.assertTrue(is_due(self.CFG, 'not a date', startup=True))


class HealingAnOlderInstallTests(unittest.TestCase):
    """The heal runs where every other one does: opening the store. So it is tested the way it
    happens - write the old shape, close, open again."""
    def _reopen(self, cfg, address='Stock brief'):
        import tempfile
        from pathlib import Path
        from taskuary.store import SQLiteStore
        path = str(Path(tempfile.mkdtemp()) / 'hub.db')
        s = SQLiteStore(path)
        s.save_source({'Channel': 'report', 'Address': address, 'Active': 1, 'ConfigJson': json.dumps(cfg)}, 'o')
        s.cx.close()
        return _reports(SQLiteStore(path))[address]

    def test_a_stock_monday_only_brief_learns_to_greet_a_launch(self):
        from taskuary.toil import PROMPT
        cfg = self._reopen({'type': 'automate', 'title': 'x', 'days': 30, 'cron': '0 8 * * 1', 'ai_prompt': PROMPT})
        self.assertTrue(cfg['on_startup'] and cfg['once_per_week'])

    def test_an_owner_who_rescheduled_it_is_left_alone(self):
        from taskuary.toil import PROMPT
        cfg = self._reopen({'type': 'automate', 'title': 'x', 'days': 30, 'cron': '0 6 * * 5', 'ai_prompt': PROMPT})
        self.assertNotIn('on_startup', cfg)

    def test_an_owner_who_rewrote_the_prompt_is_left_alone(self):
        cfg = self._reopen({'type': 'automate', 'title': 'x', 'days': 30, 'cron': '0 8 * * 1', 'ai_prompt': 'my own words'})
        self.assertNotIn('on_startup', cfg)

    def test_the_previous_stock_digest_prompt_learns_to_honor_memory(self):
        from taskuary.digest import PROMPT, _PROMPT_WITHOUT_STANDING_MEMORY
        cfg = self._reopen({'type': 'digest', 'title': 'x', 'days': 1, 'daily_at': '08:00',
                            'ai_prompt': _PROMPT_WITHOUT_STANDING_MEMORY})
        self.assertEqual(cfg['ai_prompt'], PROMPT)
        self.assertIn('WHAT THE OWNER HAS ALREADY DECIDED', cfg['ai_prompt'])


if __name__ == '__main__':
    unittest.main()
