"""Nothing falls through (sweep.py): a person's ask nobody answered comes back past its day, wherever the rail's window ends;
an open task in no state says so on its own row. No model, said once per set of facts, and nothing else on the rail moves."""
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import demo, funnel, processing_startup, processing_unread, sweep
from taskuary.store import MemoryStore, task_ref
from taskuary.testing import Factory


def ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def rail(s, **kw):
    s.reconcile_processing_membership(); funnel.invalidate()
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        return processing_unread.build(s, live_state=[], **kw)['items']


def check(s):
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]): return sweep.run(s)


def item_of(s, mid):
    s.reconcile_processing_membership()
    return s._one("SELECT ItemId FROM processing_member WHERE EntityKind='message' AND LocalId=? AND RetiredAt IS NULL", (str(mid),))['ItemId']


def let_go(s, mid):
    """The owner read its row and moved on (Next): the mail has left the rail - the ask this check is for."""
    funnel.settle(s, f'processing:{item_of(s, mid)}', 'surfaced', 'owner', read=True)


def ask(s, days, who=('Paula Vance', 'paula@contoso.example'), intent='reply_only', cid=None, sender_class='person', seen=True, **kw):
    """Their mail, asking (triage's own verdict), on no task - read and let go unless `seen` is False (then the rail still draws it)."""
    f, cid = Factory(s), cid or f'conv-{days}-{who[1]}'
    mid = f.message(None, status='routed', subject='Can you send the board pack?', body='Can you send me the board pack before Thursday?',
                    from_name=who[0], from_email=who[1], sent_at=ago(days), conversation_id=cid, source_name='alex@contoso.example', **kw)
    s.add_route(mid, None, 'file', None, 'they ask for the board pack', [], 'triage',
                verdict={'intent': intent, 'kind': 'reply', 'why': 'they ask for the board pack', 'sender_class': sender_class})
    if seen: let_go(s, mid)
    return mid


def lines(s): return {i['Key']: i for i in s.list_ideas()}


@pytest.fixture
def s():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states()
    processing_startup.initialize(s, live_state=[])        # the canonical rail, as every install runs it
    return s


# ── the aged ask ──────────────────────────────────────────────────────────────────────────────

def test_an_ask_past_its_day_comes_back_under_on_you_as_an_ask(s):
    mid = ask(s, 6)
    assert check(s)['asks'] == 1
    i = next(i for i in s.list_ideas() if i['Kind'] == sweep.ASK)
    assert 'Paula Vance asked' in i['Text'] and 'no answer, no task, nothing decided' in i['Text']
    card = next(c for c in rail(s) if c.get('idea') == i['IdeaId'])
    assert (card['lane'], card['kind'], card['mid']) == ('asked', 'idea', mid)


def test_an_ask_older_than_the_rails_window_is_still_found(s):
    ask(s, 40)
    assert check(s)['asks'] == 1


def test_a_fresh_ask_a_notice_and_a_handled_ask_are_left_alone(s):
    ask(s, 2)                                                                        # not yet past its day
    ask(s, 8, ('Trainly', 'noreply@vendor.example'), sender_class='automated')       # never automated or bulk mail
    ask(s, 8, ('Spendly', 'news@vendor.example'), sender_class='bulk')
    ask(s, 9, intent='fyi', cid='told')                                              # told, not asked
    tasked = ask(s, 9, ('Erin Blake', 'erin@northwind.example'))
    s.add_message({'TaskId': Factory(s).task(title='Board pack'), 'ExternalId': 'e2', 'ConversationId': 'conv-9-erin@northwind.example',
                   'Channel': 'email', 'FromEmail': 'erin@northwind.example', 'SentAt': ago(9, 1), 'Status': 'routed'})
    drafted = ask(s, 9, ('Gail Moreno', 'gail@northwind.example'))
    Factory(s).review(None, drafted, kind='draft_reply', draft='Here it is.')
    ask(s, 9, ('Ray Colton', 'ray@northwind.example'), cid='answered')
    s.add_message({'ExternalId': 'mine', 'ConversationId': 'answered', 'Channel': 'email', 'Status': 'context', 'Direction': 'out',
                   'FromEmail': 'alex@northwind.example', 'SentAt': ago(8), 'BodyText': 'Sent.'})
    ruled = ask(s, 9, ('Omar Keller', 'omar@northwind.example'))
    funnel.settle(s, f'processing:{item_of(s, ruled)}', 'done', 'owner')
    assert check(s)['asks'] == 0, [i['Text'] for i in s.list_ideas()]
    assert tasked and not s.list_ideas()


def test_it_is_said_once_and_a_line_put_down_stays_down(s):
    ask(s, 6)
    assert check(s)['said'] == 1
    assert check(s) == {'asks': 1, 'loose': 0, 'said': 0, 'cleared': 0}             # not again tomorrow for the same ask, and kept
    i = next(iter(lines(s).values()))
    assert i['Status'] == 'open' and i['SaidCount'] == 1
    s.set_idea_status(i['IdeaId'], 'dismissed', 'owner')
    assert check(s)['said'] == 0 and s.get_idea(i['IdeaId'])['Status'] == 'dismissed'


def test_an_answer_puts_the_line_down(s):
    ask(s, 6, cid='c1')
    check(s)
    s.add_message({'ExternalId': 'mine', 'ConversationId': 'c1', 'Channel': 'email', 'Status': 'context', 'Direction': 'out',
                   'FromEmail': 'alex@northwind.example', 'SentAt': ago(0, 1), 'BodyText': 'Sent.'})
    assert check(s)['cleared'] == 1 and next(iter(lines(s).values()))['Status'] == 'done'


# ── one mail, one place (2026-10-28: an aged ask under On you beside the same mail's own row in FYI) ──────────

def test_a_mail_the_rail_still_draws_is_not_raised_whatever_its_lane(s):
    mid = ask(s, 6, seen=False)
    row = next(c for c in rail(s) if c.get('mid') == mid)
    assert row['lane'] == 'fyi'                                       # a mail with no task is drawn under FYI
    assert check(s)['asks'] == 0 and not lines(s)                     # ...and is not said a second time under On you
    let_go(s, mid)
    assert check(s)['asks'] == 1                                      # once it has left the rail, it is the slipped ask


def test_not_a_task_on_its_thread_is_a_ruling(s):
    # Paula's thread: her first mail became a task, the owner pressed Not a task on it, and her later mail on the same thread
    # (reopened onto that task, gone back to the feed with it) is what the owner ruled on - no "nothing decided" a week on
    first = ask(s, 9, cid='pack')
    ask(s, 7, cid='pack', intent='task')
    s.add_route(first, None, 'ignore', None, 'not a task - Re: board pack', [], 'owner')
    assert check(s)['asks'] == 0 and not lines(s)
    # ...and a chat line ruled on itself, where the thread's verdict does not carry
    line = ask(s, 8, ('Erin Blake', 'erin@northwind.example'), cid='teams:chat-1', channel='teams')
    s.add_route(line, None, 'ignore', None, 'not a task - lunch?', [], 'owner')
    assert check(s)['asks'] == 0


def test_a_thread_whose_task_is_closed_is_that_tasks(s):
    f = Factory(s)
    for cid, closed in (('before', ago(8)), ('after', ago(1))):      # closed before the ask (it is the task's), and after (it answered it)
        tid = f.task(title='Board pack', status='done', ClosedAt=closed)
        f.message(tid, subject='Board pack', from_name='Gail Moreno', from_email='gail@northwind.example', sent_at=ago(10),
                  conversation_id=cid, source_name='alex@contoso.example')
        ask(s, 6, ('Gail Moreno', 'gail@northwind.example'), cid=cid)
    assert check(s)['asks'] == 0 and not lines(s)


def test_a_line_raised_before_the_ruling_is_put_down(s):
    mid = ask(s, 6, cid='pack')
    assert check(s)['asks'] == 1
    i = next(iter(lines(s).values()))
    s.add_route(mid, None, 'ignore', None, 'not a task - Re: board pack', [], 'owner')
    assert check(s)['cleared'] == 1 and s.get_idea(i['IdeaId'])['Status'] == 'done'


# ── the open task in no state ────────────────────────────────────────────────────────────────

def waiting(s, quiet=0, **kw):
    """A task waiting on them, its last word `quiet` days old."""
    tid = Factory(s).task(title='Vendor contract renewal', status='waiting', kind='general', source='manual', **kw)
    s._exec('UPDATE task SET CreatedAt=?, UpdatedAt=? WHERE TaskId=?', (ago(quiet), ago(quiet), tid))
    return tid


def card_of(s, tid): return next(c for c in rail(s, include_read=True) if c.get('tid') == tid)


def test_waiting_on_nobody_named_says_so_on_the_tasks_own_row(s):
    tid = waiting(s)
    assert card_of(s, tid)['lane'] == 'theirs'
    n = len(rail(s))
    assert check(s)['loose'] == 1
    c = card_of(s, tid)
    assert (c['lane'], c['why']) == ('yours', f'{task_ref(tid)} is waiting on nobody named') and c['unread']
    assert len(rail(s)) == n                                                          # its own row, not a second one


def test_waiting_on_a_person_with_no_date_and_with_one(s):
    no_day = waiting(s, 8, Assignee='person:ray.colton@northwind.example')
    on_day = waiting(s, 8, Assignee='person:erin@northwind.example', DueAt=(datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d'))
    check(s)
    assert card_of(s, no_day)['why'] == f'{task_ref(no_day)} is waiting on Ray Colton with no date'
    assert not card_of(s, on_day).get('loose')


def test_no_date_is_late_only_past_their_own_answer_time(s):
    # nobody's history: five days. Two days quiet is still a wait; eight is late
    inside, past = waiting(s, 2, Assignee='person:ray.colton@northwind.example'), waiting(s, 8, Assignee='person:gail@northwind.example')
    assert check(s)['loose'] == 1
    assert not card_of(s, inside).get('loose') and card_of(s, past).get('loose')
    # ...and someone the ledger knows takes ten days to answer is not late at eight: the line comes off
    with mock.patch('taskuary.outcomes.late_after', return_value=10):
        assert not card_of(s, past).get('loose') and check(s) == {'asks': 0, 'loose': 0, 'said': 0, 'cleared': 1}


def test_a_date_takes_the_line_off_at_once_and_the_next_check_puts_it_down(s):
    tid = waiting(s, 8, Assignee='person:ray.colton@northwind.example')
    assert check(s)['loose'] == 1
    s.update_task(tid, {'DueAt': (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')}, 'owner')
    assert not card_of(s, tid).get('loose') and card_of(s, tid)['lane'] == 'theirs'
    assert check(s)['cleared'] == 1


def test_a_task_whose_only_mail_is_your_own_is_drawn_and_carries_the_line(s):
    # its only mail is the owner's own (read back from Sent): the rail drew no row for it, so the line stood as a row of its own -
    # an open task is on the rail however its mail reads (Store._rail_selected, 2026-10-29), so the line rides on the task's row
    tid = waiting(s, 8)
    Factory(s).message(tid, status='context', direction='out', subject='RE: renewal', body='Sent it.', from_email='alex@northwind.example',
                       sent_at=ago(8), conversation_id='renewal')
    assert [c['tid'] for c in rail(s, include_read=True) if c.get('tid') == tid] == [tid]
    assert check(s)['loose'] == 1
    [row] = [c for c in rail(s) if c.get('loose')]
    # the task's OWN name and mark: the line says why it is here, never what it is called (2026-10-29: "of course leave task name")
    assert (row['kind'], row['lane'], row['tid'], row['title'], row['channel']) == ('todo', 'yours', tid, 'Vendor contract renewal', 'own')
    assert row['why'] == f'{task_ref(tid)} is waiting on nobody named'                  # ...its own row reads its own state
    # ...and it is THAT task's row: its own verbs, never an idea's Make a task - pressing it made the same work twice
    from taskuary import concierge
    verbs = [c.get('verb') or c.get('id') for c in concierge.chips_for(s, row)]
    assert concierge.cannot(row, 'mine', s) and not concierge.cannot(row, 'close', s) and not concierge.cannot(row, 'defer', s)
    assert 'mine' not in verbs and 'close' in verbs, verbs
    n = len(s.list_tasks())
    s.update_task(tid, {'Status': 'done'}, 'owner')                                   # closed: the row goes at once
    assert not [c for c in rail(s) if c.get('loose')] and len(s.list_tasks()) == n


def test_remind_me_and_an_agent_are_states(s):
    later = waiting(s, RemindAt=(datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d 08:00:00'))
    assert check(s)['loose'] == 0 and not card_of(s, later).get('loose')


def test_a_task_left_open_on_purpose_is_not_a_loose_end(s):
    """The owner, 2026-10-29: "it's not stale, it's what I want to leave it open". A task they keep to complete themselves (the
    session mark), and one an agent holds - its result kept - are states, drawn by the rail or not."""
    from taskuary import selfclose
    mine, agents = waiting(s, 8), waiting(s, 8, Assignee='agent:coding')
    selfclose.claim(s, mine, 'owner')
    for tid in (mine, agents):
        Factory(s).message(tid, status='context', direction='out', subject='RE: renewal', body='Sent it.', from_email='alex@northwind.example',
                           sent_at=ago(8), conversation_id=f'renewal-{tid}')
    assert check(s)['loose'] == 0 and not [c for c in rail(s) if c.get('loose')]
    # ...and a line said before the owner kept it comes off at once, the way a date takes it off; the next check puts it down
    late = waiting(s, 8)
    Factory(s).message(late, status='context', direction='out', subject='RE: renewal', body='Sent it.', from_email='alex@northwind.example',
                       sent_at=ago(8), conversation_id='renewal-late')
    assert check(s)['loose'] == 1 and [c for c in rail(s) if c.get('loose')]
    selfclose.claim(s, late, 'owner')
    assert not [c for c in rail(s) if c.get('loose')] and check(s)['cleared'] == 1


def test_the_owners_move_is_a_state(s):
    Factory(s).task(title='Draft the board pack', status='open', kind='general', source='manual')
    assert check(s)['loose'] == 0


def test_it_runs_once_a_day(s):
    waiting(s)
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        assert sweep.run_if_due(s)['loose'] == 1 and sweep.run_if_due(s) is None
        assert sweep.run_if_due(s, datetime.now() + timedelta(days=1))['said'] == 0     # tomorrow: checked, nothing said again


# ── and nothing else moves ───────────────────────────────────────────────────────────────────

KEEP = ('key', 'lane', 'why', 'title', 'tid', 'mid', 'unread', 'deferred', 'kind')


def test_the_demo_world_is_in_order_and_its_rail_is_unchanged(s):
    demo.seed(s)
    before = [{k: c.get(k) for k in KEEP} for c in rail(s)]
    assert check(s) == {'asks': 0, 'loose': 0, 'said': 0, 'cleared': 0}
    assert [{k: c.get(k) for k in KEEP} for c in rail(s)] == before


def test_in_the_demo_world_only_the_new_rows_appear(s):
    demo.seed(s)
    before = {c['key']: {k: c.get(k) for k in KEEP} for c in rail(s)}
    mid, tid = ask(s, 7), waiting(s)
    added = {c['key']: {k: c.get(k) for k in KEEP} for c in rail(s)}
    check(s)
    after = {c['key']: {k: c.get(k) for k in KEEP} for c in rail(s)}
    new = [after[k] for k in after if k not in added]
    assert [(c['kind'], c['lane'], c['mid']) for c in new] == [('idea', 'asked', mid)]        # the aged ask, once
    moved = [k for k in added if k in after and after[k] != added[k]]
    assert [after[k]['tid'] for k in moved] == [tid] and after[moved[0]]['lane'] == 'yours'  # the loose task's own row
    assert all(after[k] == before[k] for k in before)                                           # every demo row as it was
