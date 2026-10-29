"""AN OPEN TASK IS ON THE RAIL HOWEVER OLD (2026-10-29). The owner found a deep-dive task of their own from a week before through search -
it had been closed once and opened again by a session started on it - ran agent steps on it, pressed Next, and it was gone from Tasks.
Nothing had closed it: its one message, the owner's own ask, had aged past the rail's history window (feed_days), and the rail's root
selection and its inventory both kept only roots with activity inside the window. A task with work going on it is live work, and Next
passes it for this walk only (processing_unread.this_walk); the window is for mail. Invented task and people."""
from datetime import datetime, timedelta
from unittest import mock

from taskuary import concierge, funnel, processing_unread, terminal, workerstate as ws
from tests.test_funnel import ago, store


def test_a_closed_task_opened_from_search_and_worked_stays_in_tasks_after_next():
    s = store(); s.set_setting('feed_days', '7', 't')
    settle = lambda: (s.reconcile_processing_membership(fixed_now=ago(0)), funnel.invalidate())
    t = s.create_task({'Title': 'Deep-dive the ledger tie-out for one site', 'Kind': 'coding', 'Status': 'open', 'Source': 'assistant',
                       'SourceRef': 'assistant:handoff', 'Assignee': 'agent:coding'}, 'owner')
    mid = s.add_message({'TaskId': t, 'Channel': 'own', 'ExternalId': f'own-{t}', 'FromName': 'Alex Doyle', 'FromEmail': 'alex@northwind.example',
                         'BodyText': 'Tie out the ledger for one site, month by month.', 'SentAt': ago(days=8), 'Status': 'routed'})
    s._exec('UPDATE task SET CreatedAt=? WHERE TaskId=?', (ago(days=8), t)); s._exec('UPDATE message SET CreatedAt=? WHERE MessageId=?', (ago(days=8), mid))
    settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
    concierge.close_task(s, t, 'owner'); settle()                                       # closed once, two days back
    on_rail = lambda: [i for i in funnel.pile(s, force=True)['items'] if i.get('tid') == t]
    assert on_rail() == []
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        # opened from search and an agent run on it: the session door puts it back in progress (server: an explicit restart)
        s.update_task(t, {'Status': 'in_progress'}, 'owner')
        ws.record(s, t, f'sid-{t}', 'working', source='hook'); ws.record(s, t, f'sid-{t}', 'turn_end', text='The tie-out is in v10.', source='hook')
        s.add_transcript(t, f'sid-{t}', 'built v10 of the tie-out workbook', agent='coding', cwd='C:/work', brain='claude')
        s.add_comment(t, 'coding', 'agent', 'AGENT REPORT\nDetermination: The tie-out is in v10.\nSummary: v10 is ready.')
        s.update_task(t, {'Status': 'open'}, 'owner'); s.tag_task(t, terminal.SAVED, True, 'owner'); settle()   # Stop and save
        [card] = on_rail()
        s.set_funnel_state(card['key'], 'surfaced', read=True); settle()                                  # it is on the table
        funnel.settle(s, card['key'], 'surfaced', read=True, put_down=True); settle()                   # Next
        [card] = on_rail()
        assert funnel.level_of(card) == 'task', 'drawn under Tasks'
        assert (card['unread'], card['put_down'], card['actionable']) == (True, True, False), 'in Tasks, passed for this walk'
        s.set_setting(processing_unread.WALK_KEY, (datetime.now() + timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S'), 't'); funnel.invalidate()
        later = datetime.now() + timedelta(seconds=2)
        [again] = [i for i in processing_unread.build(s, now=later, live_state=[])['items'] if i.get('tid') == t]
        assert again['actionable'], 'a new walk offers it again'
    assert s.get_task(t)['Status'] == 'open'
