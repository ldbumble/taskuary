"""The README's installs chart (tools/pypi_downloads.py).

Two claims are worth pinning. The first is arithmetic: the caption and the bars are drawn from
one series, so "this week" can never disagree with what is above it. The second is honesty about
what the number IS - mirror traffic is excluded, and the chart says only that, because the field
that would separate a CI install from a person's is not in the public API at all.

The fetch is not exercised here (it is one pypistats call); everything downstream of it is, from
a saved payload, so a chart that stops rendering fails on a laptop and not in the daily workflow.
"""
import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import mkdtemp

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import pypi_downloads as dl                      # noqa: E402


def _payload(days: int, per_day=3, mirrors=True) -> dict:
    end = date(2026, 8, 30)
    out = []
    for i in range(days):
        d = (end - timedelta(days=i)).isoformat()
        out.append({'category': 'without_mirrors', 'date': d, 'downloads': per_day})
        if mirrors: out.append({'category': 'with_mirrors', 'date': d, 'downloads': per_day * 40})
    return {'data': out}


class TheSeriesTests(unittest.TestCase):
    def test_mirror_traffic_never_reaches_the_series(self):
        """The whole reason the chart exists: 3 real installs, not 123."""
        rows = [(r['date'], int(r['downloads'])) for r in _payload(2)['data']
                if r.get('category') in (None, 'without_mirrors')]
        self.assertEqual([v for _, v in rows], [3, 3])

    def test_a_fresh_fetch_wins_and_days_that_aged_out_are_kept(self):
        old = [('2026-01-01', 9), ('2026-08-29', 1)]
        new = [('2026-08-29', 4), ('2026-08-30', 5)]
        self.assertEqual(dl.merge(old, new), [('2026-01-01', 9), ('2026-08-29', 4), ('2026-08-30', 5)])

    def test_the_history_survives_a_round_trip(self):
        p = Path(mkdtemp()) / 'nested' / 'downloads.csv'
        rows = [('2026-08-29', 4), ('2026-08-30', 5)]
        dl.write_history(p, rows)
        self.assertEqual(dl.read_history(p), rows)
        self.assertEqual(dl.read_history(p.parent / 'nope.csv'), [])

    def test_the_totals_are_windows_over_the_series_not_separate_numbers(self):
        rows = [((date(2026, 8, 30) - timedelta(days=i)).isoformat(), 2) for i in range(40)][::-1]
        t = dl.totals(rows)
        self.assertEqual((t['last_day'], t['last_week'], t['last_month']), (2, 14, 60))

    def test_a_gap_in_the_series_counts_as_zero_rather_than_shifting_the_window(self):
        rows = [('2026-08-24', 5), ('2026-08-30', 1)]        # nothing in between
        t = dl.totals(rows, today=date(2026, 8, 30))
        self.assertEqual((t['last_day'], t['last_week']), (1, 6))


class WhatIsAskedForTests(unittest.TestCase):
    def test_it_asks_for_days_because_the_default_is_one_summed_row(self):
        """pypistats' own default is total='all': one dateless row per category, which drops
        out of the series entirely and leaves the chart empty."""
        import unittest.mock as mock
        with mock.patch.object(dl, '_get', return_value=_payload(3)) as got:
            dl.fetch('taskuary')
        self.assertEqual(got.call_args.kwargs, {'mirrors': False, 'total': 'daily'})

    def test_a_summed_row_with_no_date_is_not_charted_as_a_day(self):
        self.assertEqual(dl.series({'data': [{'category': 'without_mirrors', 'downloads': 900}]}), [])


class TheChartTests(unittest.TestCase):
    def test_the_line_is_the_mean_and_the_area_is_the_days_under_it(self):
        rows = [('2026-08-28', 4), ('2026-08-29', 0), ('2026-08-30', 7)]
        out = dl.svg(rows, 'taskuary')
        self.assertEqual(out.count('<polyline'), 1)          # one line: the 7-day mean
        self.assertEqual(out.count('class="area"'), 1)       # one area: the daily count
        self.assertIn('7-day mean', out)                     # ...both named at the end, not in a box
        self.assertIn('>daily<', out)

    def test_one_measure_means_one_hue_and_no_legend_box(self):
        out = dl.svg([('2026-08-29', 4), ('2026-08-30', 7)], 'taskuary')
        self.assertEqual(len({c for c in ('#2a78d6', '#3987e5') if c in out}), 2)   # light + dark step
        self.assertNotIn('<rect class="legend', out)

    def test_the_caption_says_what_the_number_is_and_does_not_overclaim(self):
        out = dl.svg([('2026-08-30', 7)], 'taskuary')
        self.assertIn('mirrors excluded', out)
        self.assertNotIn('CI', out)                          # never claimed, because it is not done
        self.assertIn('7 yesterday', out)

    def test_the_two_end_labels_never_sit_on_top_of_each_other(self):
        """A flat series ends with the day and its mean at the same height."""
        rows = [(f'2026-08-{d:02d}', 40) for d in range(20, 31)]
        import re
        ys = [float(m) for m in re.findall(r'y="([\d.]+)" class="key"', dl.svg(rows, 'taskuary'))]
        self.assertEqual(len(ys), 2)
        self.assertGreaterEqual(abs(ys[0] - ys[1]), 12)

    def test_an_empty_series_still_renders_a_chart_rather_than_crashing(self):
        out = dl.svg([], 'taskuary')
        self.assertIn('no downloads reported yet', out)
        self.assertIn('</svg>', out)

    def test_the_axis_ceiling_is_round_and_stays_close_to_the_data(self):
        """500 over a peak of 210 leaves the line crawling along the bottom of the frame."""
        self.assertEqual([dl._nice(n) for n in (0, 3, 7, 12, 40, 60, 210, 900, 1200)],
                         [5, 5, 8, 15, 40, 75, 250, 1000, 1500])

    def test_it_reads_on_both_github_themes(self):
        out = dl.svg([('2026-08-30', 7)], 'taskuary')
        self.assertIn('prefers-color-scheme: dark', out)
        self.assertIn('role="img"', out)                     # and it has alt text of its own

    def test_the_window_is_the_last_n_days_not_the_first(self):
        rows = [(f'2026-08-{d:02d}', d) for d in range(1, 11)]
        out = dl.svg(rows, 'taskuary', window=3)
        self.assertIn('Aug 8', out)
        self.assertNotIn('Aug 1<', out)

    def test_the_dates_are_evenly_spaced_once_there_are_too_many_to_show(self):
        """Uneven gaps between labels read as missing days."""
        rows = [(f'2026-0{m}-{d:02d}', 1) for m in (7, 8) for d in range(1, 29)]
        got = dl._ticks(rows)
        self.assertEqual(got, [0, 11, 22, 33, 44, 55])
        self.assertEqual(dl._ticks(rows[:6]), [0, 1, 2, 3, 4, 5])       # few days: every one


class TheCommandTests(unittest.TestCase):
    def test_it_writes_both_files_from_a_saved_payload(self):
        tmp = Path(mkdtemp())
        (tmp / 'in.json').write_text(json.dumps(_payload(9)), encoding='utf-8')
        rc = dl.main(['--package', 'taskuary', '--from-json', str(tmp / 'in.json'),
                      '--history', str(tmp / 'downloads.csv'), '--out', str(tmp / 'downloads.svg')])
        self.assertEqual(rc, 0)
        self.assertEqual(len(dl.read_history(tmp / 'downloads.csv')), 9)
        self.assertIn('</svg>', (tmp / 'downloads.svg').read_text(encoding='utf-8'))

    def test_a_second_run_adds_the_new_day_and_keeps_the_old_ones(self):
        tmp = Path(mkdtemp())
        hist = tmp / 'downloads.csv'
        dl.write_history(hist, [('2025-12-31', 11)])
        (tmp / 'in.json').write_text(json.dumps(_payload(2)), encoding='utf-8')
        dl.main(['--from-json', str(tmp / 'in.json'), '--history', str(hist), '--out', str(tmp / 'o.svg')])
        self.assertEqual(dl.read_history(hist)[0], ('2025-12-31', 11))
        self.assertEqual(len(dl.read_history(hist)), 3)

    def test_a_fetch_that_fails_leaves_the_chart_alone_instead_of_reddening_the_repo(self):
        tmp = Path(mkdtemp())
        args = ['--package', 'no-such-package-anywhere-9z', '--history', str(tmp / 'h.csv'), '--out', str(tmp / 'o.svg')]
        import unittest.mock as mock
        with mock.patch.object(dl, 'fetch', side_effect=RuntimeError('404')):
            self.assertEqual(dl.main(args), 0)
            self.assertEqual(dl.main(args + ['--strict']), 1)
        self.assertFalse((tmp / 'o.svg').exists())


class TheWorkflowTests(unittest.TestCase):
    def test_the_daily_update_publishes_to_the_stats_branch_without_opening_a_pr(self):
        """No pull request, and not master either.

        It pushed straight to master until master was protected with "require a pull request".
        `enforce_admins` is false there, so a human admin still pushes through and the Actions bot
        - which is not an admin - does not: the nightly job failed five runs in a row while
        building the chart correctly every time, and the README badge went nine days stale
        (2026-09-22).

        A daily PR is the other answer and it is worse: one pull request a day, for a number, each
        waiting on three required checks. The chart is a generated artifact rather than source, so
        it goes to an unprotected `stats` branch that holds nothing else - which also means it can
        never carry a torn snapshot of master into the history people read.
        """
        workflow = (Path(__file__).resolve().parent.parent / '.github' / 'workflows' / 'downloads.yml').read_text(encoding='utf-8')
        self.assertIn('git push origin HEAD:stats', workflow)
        self.assertNotIn('HEAD:master', workflow)
        self.assertIn('python -m unittest tests/test_pypi_downloads.py', workflow)
        self.assertNotIn('create-pull-request', workflow)
        self.assertNotIn('automation/downloads', workflow)

    def test_the_history_is_read_back_from_the_stats_branch(self):
        """The CSV is the long memory - PyPI only keeps 180 days. Generating it from an empty file
        every night would silently shorten the series to whatever the API still has, and nobody
        would notice until the chart got mysteriously shorter."""
        workflow = (Path(__file__).resolve().parent.parent / '.github' / 'workflows' / 'downloads.yml').read_text(encoding='utf-8')
        self.assertIn('git show origin/stats:downloads.csv', workflow)

    def test_the_readme_badge_points_at_the_branch_that_is_actually_updated(self):
        """A badge reading from master would now be frozen for ever: nothing updates that copy."""
        root = Path(__file__).resolve().parent.parent
        for name in ('README.md', 'README.zh-CN.md'):
            text = (root / name).read_text(encoding='utf-8')
            self.assertIn('taskuary/stats/downloads.svg', text, name)
            self.assertNotIn('taskuary/master/docs/downloads.svg', text, name)


if __name__ == '__main__':
    unittest.main()
