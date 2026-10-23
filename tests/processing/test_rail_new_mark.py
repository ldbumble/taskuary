"""+N ON A ROW, NEVER A MOVE (the owner, 2026-10-23): rows stay where they arrived and say their arrival age. A reply landing on an item
after the owner last opened it neither moves the row nor changes its age - the row says "+N" beside the age (N = the messages from
others since the owner last opened it), its line under the title is the newest message, and opening it clears the mark. A burst of three
is one row and one "+3". Invented people only."""
from taskuary import concierge, lanes

from tests.processing.test_rail_order_is_fixed import TASKS, ago, db, keys, mail, rail, settle, task_rows  # noqa: F401 (db is a fixture)


def row_of(store, tid): return next(i for i in rail(store) if i.get('tid') == tid)


def opened(store, tid):
    """The owner clicks the row: it lands on the table (a shown-is-read receipt), then the walk moves on."""
    concierge.surface(store, row_of(store, tid)['key'])
    settle(store)


def test_never_opened_has_no_mark(db):
    store, tids = db
    mail(store, TASKS[0][0], 2, tids[0], n=':again')
    settle(store)
    assert not row_of(store, tids[0]).get('new_n'), 'an item the owner never opened is new as a whole - no +N'


def test_a_burst_after_the_open_is_one_row_one_mark_and_nothing_moves(db):
    store, tids = db
    opened(store, tids[0])
    before, arrived = keys(rail(store)), row_of(store, tids[0])['arrived_at']
    for n in range(3): mail(store, TASKS[0][0], 0, tids[0], n=f':burst{n}')
    settle(store)
    row = row_of(store, tids[0])
    assert row['new_n'] == 3, f"three replies said +{row.get('new_n')}"
    assert sum(i.get('tid') == tids[0] for i in rail(store)) == 1, 'a burst made more than one row'
    assert keys(rail(store)) == before and task_rows(store) == tids, 'a reply moved a row'
    assert row['arrived_at'] == arrived, 'a reply changed the age the gutter says'
    assert row['last_at'] > row['arrived_at'] and row['latest']['who'] == 'Erin Blake', 'the newest message is not the row line'
    assert not row_of(store, tids[1]).get('new_n'), 'a row with nothing new got a mark'


def test_the_owners_own_reply_is_not_news(db):
    store, tids = db
    opened(store, tids[0])
    store.add_message({'TaskId': tids[0], 'ExternalId': 'x:mine', 'ConversationId': f'c:{TASKS[0][0]}', 'Channel': 'email', 'Subject': 'Re',
                       'FromName': 'Alex Doyle', 'FromEmail': 'alex@northwind.example', 'SentAt': ago(), 'BodyText': 'On it.',
                       'Status': 'routed', 'Direction': 'out'})
    mail(store, TASKS[0][0], 0, tids[0], n=':theirs')
    settle(store)
    assert row_of(store, tids[0])['new_n'] == 1, "the owner's own reply was counted as news"


def test_opening_clears_the_mark(db):
    store, tids = db
    opened(store, tids[0])
    mail(store, TASKS[0][0], 0, tids[0], n=':again')
    settle(store)
    assert row_of(store, tids[0])['new_n'] == 1
    opened(store, tids[0])
    assert not row_of(store, tids[0]).get('new_n'), 'opening the item did not clear its +N'
    assert lanes.level_of(row_of(store, tids[0])) == 'task' and task_rows(store) == tids


def test_the_phone_says_it_short():
    from taskuary import remote_assistant as ra
    item = {'who': 'Erin Blake', 'channel': 'email', 'ref': 'TQ-0007'}
    assert ra.source_line(item | {'new_n': 3}).endswith('TQ-0007 · +3 new')
    assert '+' not in ra.source_line(item)
