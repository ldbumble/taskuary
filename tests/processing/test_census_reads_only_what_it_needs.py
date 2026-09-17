"""A census reads what it uses - and is invalidated by more than it reads, on purpose.

`SELECT * FROM message` pulled every body into Python on every pass: 8 MB of prose on a real mailbox,
inside BEGIN IMMEDIATE, with wait_settled holding readers behind it. Membership is decided from ids,
kinds and links; a body has never moved an entity between items. That part is pure subtraction.

The other half of this file is a WARNING, written because the obvious next cut is wrong.
PROCESSING_DIRTY_TABLES lists eleven tables and reconcile_membership reads six, so route,
funnel_state, comment, task_artifact and transcript look like free deletions (2026-09-15 - I tried
it). They are not: the display cache is keyed on `self._writes`, a PER-CONNECTION counter, so a
write from another process never moves it, and these triggers are the only thing that turns an
external write into a local generation change. Removing them makes this process serve a stale view
after an agent writes a comment or a peer writes a read receipt - invisible, and hard to trace back.
The thing to attack is the SIZE of the pass, not the length of the list.
"""
import inspect

import pytest

from taskuary import processing_membership
from taskuary.store import PROCESSING_DIRTY_TABLES, SQLiteStore


@pytest.fixture
def store(tmp_path):
    return SQLiteStore(str(tmp_path / 'census.db'))


def test_the_census_does_not_read_message_bodies(store):
    store.add_message({'TaskId': None, 'ExternalId': 'x3', 'Channel': 'email', 'Subject': 'body test',
                       'BodyText': 'SECRET-PROSE-NOBODY-NEEDS', 'SentAt': '2026-09-15 10:02:00',
                       'Status': 'routed'})
    cur = store.cx.cursor()
    cols = processing_membership._columns(cur, 'message')
    assert 'BodyText' not in cols
    assert 'RecipientsJson' not in cols and 'MailMetaJson' not in cols
    assert 'Subject' in cols and 'ConversationId' in cols, 'everything else still arrives'
    row = next(iter(cur.execute(f'SELECT {cols} FROM message')))
    assert 'SECRET-PROSE-NOBODY-NEEDS' not in str(tuple(row))


def test_the_census_does_not_read_task_prose(store):
    store.create_task({'Title': 'SECRET-TASK-TITLE', 'Summary': 'SECRET-TASK-SUMMARY',
                       'Kind': 'general', 'Status': 'open'}, 'fixture')
    cur = store.cx.cursor()
    cols = processing_membership._columns(cur, 'task')
    assert 'Title' not in cols and 'Summary' not in cols and 'Checklist' not in cols
    assert 'TaskId' in cols and 'SourceRef' in cols
    row = next(iter(cur.execute(f'SELECT {cols} FROM task')))
    assert 'SECRET-TASK-TITLE' not in str(tuple(row))
    assert 'SECRET-TASK-SUMMARY' not in str(tuple(row))


def test_the_skip_list_is_a_subtraction_so_new_columns_keep_arriving(store):
    """Named as what is NOT read: a column added to `message` tomorrow reaches the census by
    default, and only what is listed here can ever go missing."""
    assert processing_membership._UNREAD_COLUMNS['message'] == ('BodyText', 'RecipientsJson', 'MailMetaJson')
    assert processing_membership._UNREAD_COLUMNS['task'] == ('Title', 'Summary', 'Checklist')
    cur = store.cx.cursor()
    every = [r[1] for r in cur.execute('PRAGMA table_info(message)')]
    got = processing_membership._columns(cur, 'message')
    assert len([c for c in every if f'"{c}"' in got]) == len(every) - 3


def test_nothing_the_census_skips_is_referenced_by_it():
    """Minus the declaration itself, which necessarily names them."""
    src = inspect.getsource(processing_membership)
    src = src[:src.index('_UNREAD_COLUMNS = {')] + src[src.index('def _columns'):]
    for table, columns in processing_membership._UNREAD_COLUMNS.items():
        for column in columns:
            assert column not in src, f'{table}.{column} is skipped but the census reads it'


def test_grouping_is_unchanged_by_the_trim(store):
    """The whole point: no census reaches a different answer for want of a body."""
    tid = store.create_task({'Title': 'Thread', 'Kind': 'reply', 'Status': 'open'}, 'fixture')
    mids = [store.add_message({'TaskId': tid, 'ExternalId': f'g{i}', 'Channel': 'email',
                               'Subject': f'part {i}', 'BodyText': 'x' * 500,
                               'SentAt': f'2026-09-15 10:0{i}:00', 'Status': 'routed'}) for i in range(3)]
    store.reconcile_processing_membership()
    items = {r[0] for r in store.cx.execute(
        'SELECT ItemId FROM processing_member WHERE EntityKind=? AND LocalId IN (?,?,?) AND RetiredAt IS NULL',
        ('message', *[str(m) for m in mids]))}
    assert len(items) == 1, 'one thread, one item - as before'


# --- rows, not just columns: mail the app will never show ---


def _skipped(store, ext='flood1'):
    return store.add_message({'TaskId': None, 'ExternalId': ext, 'Channel': 'email',
                              'Subject': 'nightly log', 'BodyText': 'x', 'FromEmail': 'logs@example.net',
                              'SentAt': '2026-09-17 06:00:00', 'Status': 'skipped'})


def test_flood_mail_is_never_given_an_identity(store):
    """A skip policy's mail is stored so dedupe recognises it and is hidden from every surface. It
    has no task, groups with nothing, and merges with nothing - so it needs no durable item. It was
    5,631 of 8,065 items on the owner's database (2026-09-17), all of them re-derived every pass."""
    mid = _skipped(store)
    kept = store.add_message({'TaskId': None, 'ExternalId': 'real1', 'Channel': 'email',
                              'Subject': 'a real one', 'SentAt': '2026-09-17 06:01:00', 'Status': 'routed'})
    store.reconcile_processing_membership()
    live = {r[0] for r in store.cx.execute(
        "SELECT LocalId FROM processing_member WHERE EntityKind='message' AND RetiredAt IS NULL")}
    assert str(mid) not in live, 'flood mail must not get a processing item'
    assert str(kept) in live, '...and everything else still does'


def test_the_pile_does_not_go_degraded_over_mail_it_never_shows(store):
    """The trap: `uncatalogued` counts every message with no member row, and compact_inventory
    REFUSES while any is non-zero. Leaving flood mail out of the census without leaving it out of
    that count turns the whole Timeline degraded, permanently."""
    _skipped(store)
    store.reconcile_processing_membership()
    snap = store.processing_inventory_snapshot(fixed_now='2026-09-17T07:00:00', display_only=True,
                                               live_state=[], history_days=14)
    assert snap['coverage']['uncatalogued']['message'] == 0


def test_mail_that_stops_being_skipped_is_grouped_on_the_next_pass(store):
    """Nothing re-statuses flood mail today, but the exclusion must not be a one-way door: the
    status change is a write, so the next census simply finds it qualifying."""
    mid = _skipped(store)
    store.reconcile_processing_membership()
    store.cx.execute("UPDATE message SET Status='routed' WHERE MessageId=?", (mid,))
    store.cx.commit()
    store.reconcile_processing_membership()
    live = {r[0] for r in store.cx.execute(
        "SELECT LocalId FROM processing_member WHERE EntityKind='message' AND RetiredAt IS NULL")}
    assert str(mid) in live


def test_an_attachment_on_flood_mail_is_not_reported_as_dangling(store):
    """Its message is ungrouped on purpose, which is not the same as its message being GONE - the
    real dangling case still has to report."""
    mid = _skipped(store)
    store.add_attachment({'MessageId': mid, 'Name': 'log.txt', 'ContentType': 'text/plain', 'Size': 9})
    store.add_attachment({'MessageId': 999999, 'Name': 'orphan.txt', 'ContentType': 'text/plain', 'Size': 9})
    result = store.reconcile_processing_membership()
    codes = [(d.get('code'), d.get('detail', {}).get('message_id')) for d in result['diagnostics']]
    assert ('dangling_attachment_message', str(mid)) not in codes
    assert ('dangling_attachment_message', '999999') in codes, 'a truly orphaned one still reports'


def test_skipped_mail_that_carries_a_task_stays_with_it(store):
    """The premise was "a skip policy's mail never gets a task". Four of 5,635 did, and one with a
    review on it took the app down: the census dropped the message, the review's MessageId dangled
    into its own item, and store.backfill_processing - which still read every message - put the same
    review with the task. Two builders, one table: "review:13 belongs to another processing item",
    raised inside the lifespan (CI, 2026-09-17). Ungrouped means status AND no task, in both."""
    tid = store.create_task({'Title': 'Desk', 'Kind': 'reply', 'Status': 'open'}, 'fixture')
    mid = store.add_message({'TaskId': tid, 'ExternalId': 'skip-with-task', 'Channel': 'email',
                             'Subject': 'Refresh succeeded with critical warnings',
                             'SentAt': '2026-09-17 06:00:00', 'Status': 'skipped'})
    rid = store.add_review({'MessageId': mid, 'TaskId': tid, 'Kind': 'reply', 'Status': 'pending', 'Draft': 'x'})
    store.reconcile_processing_membership()
    item_of = lambda kind, lid: (store.cx.execute(
        'SELECT ItemId FROM processing_member WHERE EntityKind=? AND LocalId=? AND RetiredAt IS NULL',
        (kind, str(lid))).fetchone() or [None])[0]
    assert item_of('message', mid) == item_of('task', tid), 'it has a task, so it is grouped with it'
    assert item_of('review', rid) == item_of('task', tid), 'and so is the review hanging off it'
    # ...and the startup road that runs the OTHER builder over the same table must agree with it
    from taskuary.processing_startup import initialize
    initialize(store, live_state=[])                       # raised ValueError before the fix


# --- the warning, kept executable so it argues back ---

UNREAD_BY_THE_CENSUS = ('route', 'funnel_state', 'comment', 'task_artifact', 'transcript')


def test_the_dirty_list_is_wider_than_what_the_census_reads_and_must_stay_so():
    src = inspect.getsource(processing_membership.reconcile_membership)
    for table in UNREAD_BY_THE_CENSUS:
        assert table in PROCESSING_DIRTY_TABLES, (
            f'{table} was removed from PROCESSING_DIRTY_TABLES. It is not read by the census, but its '
            'trigger is how ANOTHER process\'s write becomes visible to this one - the display cache '
            'is keyed on a per-connection counter. See this file\'s docstring.')
        assert f'FROM {table} ' not in src, f'{table} is now read by the census - update this test'


def test_another_process_writing_makes_this_one_notice(tmp_path):
    """The invariant the extra triggers exist for, stated as behaviour rather than as a list."""
    path = str(tmp_path / 'peer.db')
    mine = SQLiteStore(path)
    tid = mine.create_task({'Title': 'Shared', 'Kind': 'reply', 'Status': 'open'}, 'fixture')
    mine.reconcile_processing_membership()
    assert not mine.processing_reconcile_status()['pending']
    SQLiteStore(path).add_comment(tid, 'coder', 'agent', 'an agent wrote this from its own process')
    assert mine.processing_reconcile_status()['pending'], (
        "this connection must notice another one's write; nothing else tells it")
