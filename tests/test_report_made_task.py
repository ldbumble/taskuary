"""A task the owner made from a report is their own work, never "asked you" (2026-10-26): Put it on my list on a report run, and
Reopen task on a report-born task, filed the row in the asked lane - "a person asked you for something", the 🙋 pill and a lit
Reply - over a report no person wrote (the owner, 2026-09-16: "i don't like this asked you" on rows derived from a report)."""
from unittest import mock

from taskuary import concierge, demo, funnel, operations, server, terminal
from taskuary.store import MemoryStore


def _world():
    s = MemoryStore(); demo.seed(s); funnel.invalidate()
    return s


def _lane(s, tid):
    funnel.invalidate()
    with mock.patch.object(terminal, 'live_sessions', return_value=[]):
        got = [i for i in funnel.build(s, keep_surfaced=True)['items'] if i.get('tid') == tid]
        return [(i['kind'], i['lane']) for i in got], funnel.item_for_key(s, f'task:{tid}')


def test_put_it_on_my_list_on_a_report_is_the_owners_own_work_and_so_is_reopening_it():
    s = _world()
    mid = s._one("SELECT MessageId FROM message WHERE Channel='report' ORDER BY MessageId LIMIT 1")['MessageId']
    with mock.patch.object(terminal, 'live_sessions', return_value=[]), mock.patch.object(server, 'store', s):
        concierge.run_proposal(s, operations.propose(s, 'task.create_from_message', mid, {'kind': 'task'}, 'owner'), 'owner')
    tid = s._one('SELECT TaskId FROM message WHERE MessageId=?', (mid,))['TaskId']
    assert tid
    rows, it = _lane(s, tid)
    assert rows == [('todo', 'yours')], rows
    assert (it['kind'], it['lane']) == ('todo', 'yours') and 'asked you' not in str(it.get('why'))
    s.update_task(tid, {'Status': 'done'}, 'owner'); s.update_task(tid, {'Status': 'open'}, 'owner')       # Reopen task
    rows, _ = _lane(s, tid)
    assert rows == [('todo', 'yours')], rows
