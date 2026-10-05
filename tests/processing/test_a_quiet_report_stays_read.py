"""A report run the judge kept off the Timeline stays put down once its files are attached.

The read receipt is a fingerprint of the row, and the row's attachments are part of it. The run was
put down BEFORE its spreadsheet and chart were attached, so the row it marked read was not the row
that stayed: every "all clear" the judge held back came back unread, and the Assistant announced it
("... all clear landed 58 min ago. It is open below") - the owner, 2026-10-04.
"""
import json
from datetime import datetime
from unittest import mock

import pytest

from taskuary import funnel, reports
from taskuary.store import SQLiteStore

STAMP = datetime.now().replace(microsecond=0).isoformat(sep=' ')
ROWS = '\n'.join(json.dumps(r) for r in [{'job': 'ledger sync', 'took': 41.5}, {'job': 'portal export', 'took': 206.2},
                                         {'job': 'vendor import', 'took': 15.7}])


@pytest.fixture
def db(tmp_path):
    store = SQLiteStore(str(tmp_path / 'quiet.db'))
    store.reconcile_processing_membership(fixed_now=STAMP)
    store.activate_processing_reads(fixed_now=STAMP, live_state=[])
    funnel.invalidate(); funnel.forget_states()
    yield store
    store.cx.close()


def a_run(db, route):
    sid = db.save_source({'Channel': 'report', 'Address': 'Nightly job check', 'Active': 1,
                          'ConfigJson': json.dumps({'title': 'Nightly job check', 'route': route})}, 't')
    with mock.patch.object(reports, 'render_report', return_value=('3 rows', ROWS)):
        out = reports.run_report_source(db, db.get_source(sid), None)
    assert db.list_attachments(out['message_id']), 'the row did not grow its files, so this proves nothing'
    return out['message_id']


def offered(db, mid):
    db.reconcile_processing_membership(fixed_now=STAMP)              # the background pass the live app runs
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        funnel.invalidate()
        items = funnel.build(db, live_state=[])['items']
    return [i for i in items if str(i.get('mid')) == str(mid) and i.get('actionable') and i.get('unread')]


def test_a_run_kept_off_the_timeline_is_not_offered_again(db):
    assert not offered(db, a_run(db, {'timeline': {'how': 'never'}}))


def test_a_run_that_reaches_you_is_still_offered(db):
    """The other side: the fix puts down only what the card said to put down."""
    assert offered(db, a_run(db, {'timeline': {'how': 'always'}}))
