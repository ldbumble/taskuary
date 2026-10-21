"""A report's clock is saved only when the scheduler can run it (the 2026-10-21 UI audit, B3).

"daily at 7am" was typed into the report editor's free box, confirmed "saved - enabled and scheduled", and then never ran at seven:
the scheduler reads HH:MM. The editor now uses the workflow editor's picker, and the save door refuses what the scheduler cannot read.
"""
import json
from datetime import datetime
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import reports, server
from taskuary.store import MemoryStore

# what the picker writes (WorkflowEditor.withSchedule): one key per choice
PICKED = [{'daily_at': '07:00'}, {'cron': '0 8 * * 1,3'}, {'cron': '30 9 1 * *'}, {'every_minutes': 45}, {'cron': '0 8 * * 1-5'}]


def test_every_clock_the_picker_writes_is_one_the_scheduler_reads():
    for c in PICKED:
        assert reports.schedule_error(c) is None, c
        assert reports.runs_per_day(c) > 0, c
    assert reports._daily_slot({'daily_at': '07:00'}, datetime(2026, 10, 21, 1, 0)).hour == 7


def test_a_clock_it_cannot_read_is_named():
    for bad in ({'daily_at': '7am'}, {'cron': 'every monday'}, {'cron': '0 25 * * *'}, {'every_minutes': 'thirty'}):
        assert reports.schedule_error(bad), bad


def _save(s, cfg):
    with mock.patch.object(server, 'store', s):
        return TestClient(server.app).post('/api/sources', json={'Channel': 'report', 'Address': 'Units by site',
                                                                 'ConfigJson': json.dumps({'title': 'Units by site', **cfg}), 'Active': 1})


def test_the_save_door_refuses_7am_and_keeps_nothing():
    s = MemoryStore()
    r = _save(s, {'type': 'file', 'daily_at': '7am'})
    assert r.status_code == 422 and '7am' in r.json()['detail']
    assert not [x for x in s.list_sources(active_only=False) if x.get('Channel') == 'report' and x.get('Address') == 'Units by site']
    assert _save(s, {'type': 'file', 'daily_at': '07:00'}).status_code == 200
