"""A write the census never reads does not run the census.

Every write to a PROCESSING_DIRTY_TABLES table bumps DirtyGeneration, and the membership worker answered each
bump with a full census under store.lock - 1-4 s on a real mailbox, every few seconds, for a task's Status, a
route or a funnel_state row (2026-10-28). The census's own inputs now bump a second counter; when it has not
moved since the last clean census, the generations advance and the pass is skipped. Same inputs, same answer.
"""
import inspect, re

import pytest

from taskuary import processing_membership as pm
from taskuary.store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    return SQLiteStore(str(tmp_path / 'census.db'))


@pytest.fixture
def censuses(monkeypatch):
    "Census passes that answered: a dry pass that stopped at its first write is not one - the pass under the lock is."
    calls, real = [], pm.reconcile_membership
    def counted(*a, **k):
        r = real(*a, **k); calls.append(1); return r
    monkeypatch.setattr(pm, 'reconcile_membership', counted)
    return calls


def _members(store, kind, local):
    return [r[0] for r in store.cx.execute('SELECT ItemId FROM processing_member WHERE EntityKind=? AND LocalId=? AND RetiredAt IS NULL',
                                           (kind, str(local)))]


def _status(store): return store.processing_reconcile_status()


def test_a_write_the_census_does_not_read_skips_it(store, censuses):
    tid = store.create_task({'Title': 'Thread', 'Kind': 'reply', 'Status': 'open'}, 'fixture')
    store.reconcile_processing_membership()
    assert censuses == [1]
    with store.lock:
        store.cx.execute("UPDATE task SET Status='in_progress' WHERE TaskId=?", (tid,))
        store.cx.execute("INSERT INTO funnel_state(Key, Status) VALUES ('task:1', 'surfaced')")
        store.cx.commit()
    assert _status(store)['pending'], 'readers still see the write'
    store.reconcile_processing_membership()
    assert censuses == [1], 'no census for a write it cannot see'
    st = _status(store)
    assert not st['pending'] and st['attempted_generation'] == st['dirty_generation']


def test_a_new_message_still_runs_it(store, censuses):
    tid = store.create_task({'Title': 'Thread', 'Kind': 'reply', 'Status': 'open'}, 'fixture')
    store.reconcile_processing_membership()
    mid = store.add_message({'TaskId': tid, 'ExternalId': 'n1', 'Channel': 'email', 'Subject': 'new', 'BodyText': 'x',
                             'SentAt': '2026-10-28 08:00:00', 'Status': 'routed'})
    store.reconcile_processing_membership()
    assert censuses == [1, 1]
    assert _members(store, 'message', mid) == _members(store, 'task', tid) != []


def test_a_message_moving_task_runs_it(store, censuses):
    a, b = (store.create_task({'Title': t, 'Kind': 'reply', 'Status': 'open'}, 'fixture') for t in ('A', 'B'))
    mid = store.add_message({'TaskId': a, 'ExternalId': 'm1', 'Channel': 'email', 'Subject': 's', 'BodyText': 'x',
                             'SentAt': '2026-10-28 08:00:00', 'Status': 'routed'})
    store.reconcile_processing_membership()
    with store.lock: store.cx.execute('UPDATE message SET TaskId=? WHERE MessageId=?', (b, mid)); store.cx.commit()
    store.reconcile_processing_membership()
    assert len(censuses) == 2 and _members(store, 'message', mid) == _members(store, 'task', b)


def test_a_conflicted_census_is_never_skipped(store, censuses):
    store.create_task({'Title': 'A', 'Kind': 'reply', 'Status': 'open'}, 'fixture')
    store.reconcile_processing_membership()
    with store.lock: pm.mark_census(store.cx.cursor(), False); store.cx.execute('UPDATE task SET Status=Status'); store.cx.commit()
    store.reconcile_processing_membership()
    assert len(censuses) == 2


def test_every_column_the_census_reads_is_watched(store):
    """A column the census starts reading but CENSUS_INPUTS leaves out would let a real change skip it."""
    src = inspect.getsource(pm.reconcile_membership) + inspect.getsource(pm.census_inputs)
    named = {a or b for a, b in re.findall(r"\['(\w+)'\]|get\('(\w+)'", src)}
    named -= set(pm.CENSUS_INPUTS['processing_item'])      # read off processing_item rows (Kind, CreatedAt), watched there
    keys = {'task': 'TaskId', 'message': 'MessageId', 'review': 'ReviewId', 'idea': 'IdeaId', 'attachment': 'AttachmentId', 'run': 'RunId'}
    for table in keys:
        cols = {r[1] for r in store.cx.execute(f'PRAGMA table_info({table})')}
        # another table's id read off that table's rows (run['RunId']) shares a name with a column here (review.RunId)
        read = cols & named - {k for t, k in keys.items() if t != table and k not in pm.CENSUS_INPUTS[table]}
        assert read <= set(pm.CENSUS_INPUTS[table]), f'{table}: {read - set(pm.CENSUS_INPUTS[table])} read but not watched'
    assert set(pm.UNGROUPED_MESSAGE_STATUS) and {'Status', 'TaskId'} <= set(pm.CENSUS_INPUTS['message']), 'ungrouped_message_sql reads these'
