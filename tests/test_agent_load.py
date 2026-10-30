"""Light work on the one width (the owner, 2026-10-30): "it should count like sub agents, 5 of them are one or something like that.
add this in settings." Quick answers and an agent's own subagents count against "Agents at once" at 1/auto_sessions_light each."""
import threading, time
from types import SimpleNamespace as NS
from unittest import mock
from taskuary import blackboard as bb, ingest, quickwork, terminal
from taskuary.store import MemoryStore

def home(**kw):
    s = MemoryStore()
    for k, v in kw.items(): s.set_setting(k, v, 't')
    return s

def subs(n, alive=True): return NS(alive=alive, quick=False, subagents=[{'id': f'a{i}', 'kind': 'agent'} for i in range(n)])

def test_the_setting_defaults_to_five_and_is_clamped():
    assert ingest.light_per_agent(home()) == ingest.LIGHT_PER_AGENT == 5
    for v, want in (('', 5), ('x', 5), ('0', 1), ('-3', 1), ('1', 1), ('12', 12), ('99', 20)): assert ingest.light_per_agent(home(auto_sessions_light=v)) == want, v
    assert MemoryStore().get_setting('auto_sessions_light') == '5'

def test_load_is_sessions_plus_light_work_over_the_setting():
    s = home()
    with mock.patch.dict(terminal.SESSIONS, {'x': subs(2), 'y': subs(3, alive=False)}, clear=True), \
         mock.patch.object(bb, 'live_count', return_value=2), mock.patch.object(quickwork, 'in_flight', return_value=3):
        assert bb.subagent_count() == 2                                           # an ended session's subagents are gone with it
        assert ingest.agent_load(s) == 3.0 and ingest.has_room(s)                 # 2 + (3 quick + 2 subagents) / 5: one slot of four left
        terminal.SESSIONS['z'] = subs(1)
        assert abs(ingest.agent_load(s) - 3.2) < 1e-9 and not ingest.has_room(s) and ingest.has_room(s, .2)
        s.set_setting('auto_sessions_light', '1', 't'); assert ingest.agent_load(s) == 8

def test_five_light_make_exactly_one():
    s = home(auto_sessions='1')
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(bb, 'live_count', return_value=0), \
         mock.patch.object(quickwork, 'in_flight', return_value=4):
        assert ingest.has_room(s, .2)                                             # 4 x 0.2 + 0.2 is 1, never 1.0000000000000002

def test_light_work_holds_back_a_new_agent_and_says_so_truthfully():
    s = home(); tid = s.create_task({'Title': 'Plan the offsite', 'Kind': 'general'}, 't')
    with mock.patch.dict(terminal.SESSIONS, {'x': subs(5)}, clear=True), mock.patch.object(bb, 'live_count', return_value=3), \
         mock.patch.object(ingest, '_start_general') as start:
        ingest._auto_general(s, tid, 'the brief', deep=True)
    start.assert_not_called()
    assert s.get_dispatch(tid)['Brief'] == 'the brief'
    said = [c['Body'] for c in s.list_comments(tid) if c['Body'].startswith('Waiting its turn')]
    assert said == ['Waiting its turn: 3 agents plus quick answers and subagents already fill the 4 agent slots, and it starts by itself when there is room.']
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(bb, 'live_count', return_value=4):
        assert ingest.busy_words(s) == '4 agents are already running'

def test_a_drain_waits_on_light_load_too():
    s = home(auto_sessions='1'); tid = s.create_task({'Title': 'Plan the offsite', 'Kind': 'general'}, 't')
    s.enqueue_dispatch(tid, None, 'assistant', 'full', brief='notes')
    with mock.patch.object(bb, 'live_count', return_value=0), mock.patch.object(ingest, '_start_general', return_value=True) as start:
        with mock.patch.object(quickwork, 'in_flight', return_value=1): bb.drain(s)
        start.assert_not_called()                                                 # 0.2 + 1 does not fit in 1
        bb.drain(s); assert start.call_args[0][1:] == (tid, 'notes')

def test_a_quick_call_waits_for_room_and_its_timeout_starts_with_its_slot():
    s = home(auto_sessions='1', auto_sessions_light='2'); tid = s.create_task({'Title': 'Friday?', 'Kind': 'general'}, 't')
    live, seen = [1], []
    def ask(store, tid_, ask_, steps, cancel): seen.append(cancel.is_set()); return None
    with mock.patch.object(bb, 'live_count', side_effect=lambda: live[0]), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
         mock.patch.object(quickwork, 'ask', side_effect=ask), mock.patch.object(quickwork, 'WAIT_POLL', .05), \
         mock.patch.object(quickwork, 'QUICK_TIMEOUT', .2):
        th = threading.Thread(target=quickwork._call, args=(s, tid, 'Friday?', [])); th.start()
        time.sleep(.5)
        assert th.is_alive() and not seen and quickwork.in_flight() == 0          # every slot is an agent's: it waits, holding nothing
        live[0] = 0; th.join(5)
    assert seen == [False] and quickwork.in_flight() == 0                         # 0.5s waited, the 0.2s timeout had not started
    assert any('the quick answer comes when there is room' in c['Body'] for c in s.list_comments(tid))

def test_quick_calls_never_pass_the_ceiling_and_free_their_slot():
    s = home(auto_sessions='1', auto_sessions_light='2'); gate, now, most, lock = threading.Event(), [0], [0], threading.Lock()
    def ask(*a):
        with lock: now[0] += 1; most[0] = max(most[0], now[0])
        gate.wait(5)
        with lock: now[0] -= 1
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(quickwork, 'ask', side_effect=ask), \
         mock.patch.object(quickwork, 'WAIT_POLL', .05):
        ts = [threading.Thread(target=quickwork._call, args=(s, i, 'q', [])) for i in range(6)]
        for t in ts: t.start()
        time.sleep(.4); assert most[0] == 2 == quickwork.in_flight()             # 1 agent slot x 2 per agent
        gate.set()
        for t in ts: t.join(5)
    assert most[0] == 2 and quickwork.in_flight() == 0

def test_a_finished_quick_call_lets_a_queued_agent_start():
    s = home(); tid = s.create_task({'Title': 'Plan the offsite', 'Kind': 'general'}, 't')
    with mock.patch.object(quickwork, 'ask', return_value=None), mock.patch.object(bb, 'drain_later') as drain:
        quickwork._call(s, tid, 'q', []); drain.assert_not_called()               # nothing queued: no drain
        s.enqueue_dispatch(tid, None, 'assistant', 'full')
        quickwork._call(s, tid, 'q', []); drain.assert_called_once()
