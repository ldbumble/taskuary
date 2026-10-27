"""The one-time cutover reads the frozen message verdicts once, not once per item (perf report 2.4, 2026-10-19):
per item it was O(N^2) and ran before the port opened, so a 2k-message home started in 156 s."""
from datetime import datetime

from taskuary.store import SQLiteStore

NOW = datetime(2026, 10, 19, 9).isoformat(sep=' ')


def cutover_verdict_reads(tmp_path, n):
    db = SQLiteStore(str(tmp_path / f'cut{n}.db'))
    try:
        for i in range(n):
            mid = db.add_message(dict(Channel='email', SourceName='alex@northwind.example', FromEmail='erin@northwind.example',
                                      Subject=f'update {i}', BodyText='Kept for the record.', SentAt=NOW, Status='filed'))
            if i % 2: db.set_funnel_state(f'msg:{mid}', 'surfaced')
        db.reconcile_processing_membership(fixed_now=NOW)
        sql = []; db.cx.set_trace_callback(sql.append)
        db.activate_processing_reads(fixed_now=NOW, live_state=[])
        db.cx.set_trace_callback(None)
        assert db.processing_reads_active()
        return sum('PermanentRead IS NOT NULL' in s for s in sql)
    finally: db.close()


def test_verdicts_are_read_once_however_many_items(tmp_path):
    assert cutover_verdict_reads(tmp_path, 8) == cutover_verdict_reads(tmp_path, 40) == 1
