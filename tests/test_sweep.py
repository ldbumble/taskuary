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


def ask(s, days, who=('Paula Vance', 'paula@contoso.example'), intent='reply_only', cid=None, sender_class='person', **kw):
    """Their mail, asking (triage's own verdict), on no task."""
    f, cid = Factory(s), cid or f'conv-{days}-{who[1]}'
    mid = f.message(None, status='routed', subject='Can you send the board pack?', body='Can you send me the board pack before Thursday?',
                    from_name=who[0], from_email=who[1], sent_at=ago(days), conversation_id=cid, source_name='alex@contoso.example', **kw)
    s.add_route(mid, None, 'file', None, 'they ask for the board pack', [], 'triage',
                verdict={'intent': intent, 'kind': 'reply', 'why': 'they ask for the board pack', 'sender_class': sender_class})
    return mid


def lines(s): return {i['Key']: i for i in s.list_ideas()}


@pytest.fixture
def s():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled', 'learn_enabled'): s.set_setting(k, '0', 't')
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
    s.reconcile_processing_membership()
    item = s._one("SELECT ItemId FROM processing_member WHERE EntityKind='message' AND LocalId=?", (str(ruled),))['ItemId']
    funnel.settle(s, f'processing:{item}', 'done', 'owner')
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


# ── the open task in no state ────────────────────────────────────────────────────────────────

def waiting(s, **kw): return Factory(s).task(title='Vendor contract renewal', status='waiting', kind='general', source='manual', **kw)


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
    no_day = waiting(s, Assignee='person:ray.colton@northwind.example')
    on_day = waiting(s, Assignee='person:erin@northwind.example', DueAt=(datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d'))
    check(s)
    assert card_of(s, no_day)['why'] == f'{task_ref(no_day)} is waiting on Ray Colton with no date'
    assert not card_of(s, on_day).get('loose')


def test_a_date_takes_the_line_off_at_once_and_the_next_check_puts_it_down(s):
    tid = waiting(s, Assignee='person:ray.colton@northwind.example')
    check(s)
    s.update_task(tid, {'DueAt': (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')}, 'owner')
    assert not card_of(s, tid).get('loose') and card_of(s, tid)['lane'] == 'theirs'
    assert check(s)['cleared'] == 1


def test_remind_me_and_an_agent_are_states(s):
    later = waiting(s, RemindAt=(datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d 08:00:00'))
    assert check(s)['loose'] == 0 and not card_of(s, later).get('loose')


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
