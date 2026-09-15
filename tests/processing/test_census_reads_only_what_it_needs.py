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
    assert 'Subject' in cols and 'ConversationId' in cols, 'everything else still arrives'
    row = next(iter(cur.execute(f'SELECT {cols} FROM message')))
    assert 'SECRET-PROSE-NOBODY-NEEDS' not in str(tuple(row))


def test_the_skip_list_is_a_subtraction_so_new_columns_keep_arriving(store):
    """Named as what is NOT read: a column added to `message` tomorrow reaches the census by
    default, and only what is listed here can ever go missing."""
    assert processing_membership._UNREAD_COLUMNS == {'message': ('BodyText',)}
    cur = store.cx.cursor()
    every = [r[1] for r in cur.execute('PRAGMA table_info(message)')]
    got = processing_membership._columns(cur, 'message')
    assert len([c for c in every if f'"{c}"' in got]) == len(every) - 1


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
