"""THE DEMO'S WEEKLY DASHBOARD HAS A CLOCK THE SCHEDULER READS (the product audit, 2026-11-08). It was seeded with `weekly_at`, a key
nothing reads, so Reports framed it red with "No schedule" while its task said it refreshes Mondays at 7:00. Invented world (demo.seed)."""
import json

from taskuary import demo, reports
from taskuary.store import MemoryStore


def test_every_seeded_report_with_a_clock_has_one_the_scheduler_reads():
    s = MemoryStore(); demo.seed(s)
    cfgs = {r['Address']: json.loads(r['ConfigJson'] or '{}') for r in s.list_sources(active_only=False) if r['Channel'] == 'report'}
    weekly = cfgs['Vendor spend, weekly']
    assert reports.schedule_error(weekly) is None and reports.schedule_words(weekly) == 'cron 0 7 * * 1'
    for name, c in cfgs.items():
        assert not [k for k in c if k.endswith('_at') and k not in ('daily_at', 'first_run_at_schedule')], f'{name}: a clock no scheduler reads'
