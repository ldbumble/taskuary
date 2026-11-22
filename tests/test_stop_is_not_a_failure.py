"""A general agent the owner stopped is stopped - not failed, and not started again (the overnight run, 2026-11-03).

Stop and save on a general agent mid-turn closed its session, its Claude Code exited, and the turn read as a CLI that died part-way:
the pane said "Claude: the agent stopped in the middle of its turn ... (the CLI exited (1))" and "Couldn't start yet ... - trying
again at 00:38" - the start queue was about to run the agent the owner had just stopped."""
from unittest import mock

from taskuary import blackboard as bb, general, ingest, workerstate as ws
from taskuary.clipool import MID_TURN
from taskuary.store import MemoryStore


def task(s): return s.create_task({'Title': 'Write vendor notes', 'Summary': 'Write the vendor notes.', 'Kind': 'general', 'Status': 'in_progress'}, 'router')


def test_a_start_whose_turn_the_owner_stopped_is_neither_failed_nor_retried():
    s = MemoryStore(); tid = task(s)
    ses = mock.Mock(); ses.send_prompt.side_effect = general.Stopped(MID_TURN)
    with mock.patch.object(general, 'start_session', return_value=ses), mock.patch.object(bb, 'record_failure') as failed:
        assert ingest._start_general(s, tid) is True
    failed.assert_not_called()
    assert not s.get_dispatch(tid)


def test_a_turn_cut_by_close_is_recorded_stopped():
    s = MemoryStore(); tid = task(s)
    with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')):
        ses = general.GeneralSession(s, tid)
    def cut(*a, **k):
        ses.closing = True                                   # Stop and save closed the session under the turn
        raise RuntimeError(f'{MID_TURN} (the CLI exited (1))')
    with mock.patch.object(general.llm_mod, 'build_llm', return_value=cut), mock.patch.object(ses, 'close'):
        try: ses.send_prompt('Write the vendor notes.', brief=True)
        except general.Stopped: pass
        else: raise AssertionError('a stopped turn says so to its caller')
    assert s.last_worker_event(tid, skip=ws.NOTES)['Kind'] == 'stopped'


def test_a_turn_he_stopped_reads_stopped_never_waiting_on_him():
    """The walk, 2026-11-22: after his Stop the chat said "You stopped the agent" while the chip and the rail's hand said "agent waiting on
    you" - a parked session whose last word is his stop fell to `blocked`. It reads stopped, on every surface that reads the key."""
    from taskuary import taskstate
    s = MemoryStore(); tid = task(s)
    ws.record(s, tid, 'sid1', 'working', text='', source='api'); ws.record(s, tid, 'sid1', 'stopped', text='stopped', source='api')
    session = {'alive': True, 'waiting': True, 'state': 'parked', 'sid': 'sid1', 'mode': 'assistant'}
    assert taskstate.state(s, s.get_task(tid), session) == 'stopped'


def test_the_rail_says_stopped_over_a_session_he_stopped():
    "Round 3, 2026-11-22: the rail's row said \"waiting on you\" over his Stop, off the live session at rest."
    from types import SimpleNamespace
    from taskuary import funnel
    s = MemoryStore(); tid = task(s)
    ws.record(s, tid, 'sid9', 'working', text='', source='api'); ws.record(s, tid, 'sid9', 'stopped', text='stopped', source='api')
    sess = SimpleNamespace(alive=True, store=s, sid='sid9', waiting=lambda: True)
    with mock.patch('taskuary.terminal.session_for', return_value=sess):
        line, row = funnel.live_session_state(tid, 'the assistant')
    assert line.startswith('Stopped.') and 'waiting' not in row


def test_a_session_he_stopped_makes_no_waiting_row_on_the_rail():
    "Round 4, 2026-11-22: after his Stop the header said \"agent stopped\" and the rail's agent row \"Agent is waiting on you\" with the hand."
    from taskuary import funnel
    s = MemoryStore(); tid = task(s)
    ws.record(s, tid, 'sid7', 'working', text='', source='api'); ws.record(s, tid, 'sid7', 'stopped', text='stopped', source='api')
    live = [{'taskId': tid, 'sid': 'sid7', 'alive': True, 'waiting': True, 'mode': 'assistant', 'started': '2026-11-22 05:00:00'}]
    rows = funnel.from_agents(s, live_state=live)
    assert not [r for r in rows if r.get('tid') == tid and r.get('lane') == 'blocked'], rows


def test_stop_pressed_fast_is_heard_once_a_turn():
    "Walk 5, 2026-11-22: Stop pressed fast wrote \"You stopped the agent\" 10 times - one press per line, all on the same turn."
    from unittest import mock
    from types import SimpleNamespace
    from taskuary import general
    s = MemoryStore(); tid = task(s); general.STOPPED_AT.pop(tid, None)
    ses = SimpleNamespace(stop=lambda: True, busy=True, turn_at=1000.0)
    with mock.patch.object(general, 'session_for', return_value=ses), mock.patch.object(general, 'turn_started', return_value=1000.0):
        assert all(general.stop_turn(s, tid) for _ in range(10))
    assert len([a for a in s._rows("SELECT * FROM audit WHERE EntityId=? AND Action='stopped_turn'", (tid,))]) == 1


def test_a_session_he_stopped_never_reads_working_on_the_rail_search_or_the_assistant():
    """Walk 5, 2026-11-22: 25 minutes after his Stop the rail row, Search and the Assistant said "An agent is working on this" - the session
    stays up after a stop, and the row read working off it being alive while the header read stopped."""
    from types import SimpleNamespace
    from taskuary import funnel, processing_unread
    from test_funnel import ago
    s = MemoryStore()
    t = s.create_task({'Title': 'Printer quotes', 'Kind': 'general', 'Status': 'open'}, 'owner')
    s.add_message({'TaskId': t, 'ExternalId': 'p1', 'Channel': 'email', 'Subject': 'Printer', 'FromName': 'Erin Blake',
                   'FromEmail': 'erin@northwind.example', 'SentAt': ago(1), 'BodyText': 'Get three printer quotes?', 'Status': 'routed'})
    m = s._rows('SELECT MessageId FROM message WHERE TaskId=?', (t,))[0]['MessageId']
    s.add_route(m, t, 'route', 1.0, 'triage: task', [], 'triage')
    ws.record(s, t, 'sid7', 'working', text='', source='api'); ws.record(s, t, 'sid7', 'stopped', text='stopped', source='api')
    s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
    live = [{'taskId': t, 'sid': 'sid7', 'alive': True, 'waiting': True, 'mode': 'assistant', 'started': ago(2)}]
    ses = SimpleNamespace(alive=True, store=s, sid='sid7', waiting=lambda: True, busy=False)
    with mock.patch('taskuary.terminal.live_sessions', return_value=live), mock.patch('taskuary.terminal.session_for', return_value=ses):
        rows = [i for i in processing_unread.build(s, live_state=live, include_read=True)['items'] if i.get('tid') == t]
    assert rows and not [r for r in rows if r['lane'] == 'working' or 'is working' in str(r.get('why'))], [(r['lane'], r.get('why')) for r in rows]
