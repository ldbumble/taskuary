"""Light work on the one width (the owner, 2026-10-30): "it should count like sub agents, 5 of them are one or something like that.
add this in settings." An agent's own subagents count against "Agents at once" at 1/auto_sessions_light each."""
import threading, time
from types import SimpleNamespace as NS
from unittest import mock
from taskuary import blackboard as bb, ingest, terminal
from taskuary.store import MemoryStore

def home(**kw):
    s = MemoryStore()
    for k, v in kw.items(): s.set_setting(k, v, 't')
    return s

def subs(n, alive=True): return NS(alive=alive, task_id=None, subagents=[{'id': f'a{i}', 'kind': 'agent'} for i in range(n)])

def test_the_setting_defaults_to_five_and_is_clamped():
    assert ingest.light_per_agent(home()) == ingest.LIGHT_PER_AGENT == 5
    for v, want in (('', 5), ('x', 5), ('0', 1), ('-3', 1), ('1', 1), ('12', 12), ('99', 20)): assert ingest.light_per_agent(home(auto_sessions_light=v)) == want, v
    assert MemoryStore().get_setting('auto_sessions_light') == '5'

def test_load_is_sessions_plus_light_work_over_the_setting():
    s = home()
    with mock.patch.dict(terminal.SESSIONS, {'x': subs(2), 'y': subs(3, alive=False)}, clear=True), \
         mock.patch.object(bb, 'live_count', return_value=3):
        assert bb.subagent_count() == 2                                           # an ended session's subagents are gone with it
        assert abs(ingest.agent_load(s) - 3.4) < 1e-9 and not ingest.has_room(s)  # 3 + 2 subagents / 5: no whole slot of four left
        assert ingest.has_room(s, .6)
        s.set_setting('auto_sessions_light', '1', 't'); assert ingest.agent_load(s) == 5

def test_five_light_make_exactly_one():
    s = home(auto_sessions='1')
    with mock.patch.dict(terminal.SESSIONS, {'x': subs(4)}, clear=True), mock.patch.object(bb, 'live_count', return_value=0):
        assert ingest.has_room(s, .2)                                             # 4 x 0.2 + 0.2 is 1, never 1.0000000000000002

def test_light_work_holds_back_a_new_agent_and_says_so_truthfully():
    s = home(); tid = s.create_task({'Title': 'Plan the offsite', 'Kind': 'general'}, 't')
    with mock.patch.dict(terminal.SESSIONS, {'x': subs(5)}, clear=True), mock.patch.object(bb, 'live_count', return_value=3), \
         mock.patch.object(ingest, '_start_general') as start:
        ingest._auto_general(s, tid, 'the brief')
    start.assert_not_called()
    assert s.get_dispatch(tid)['Brief'] == 'the brief'
    said = [c['Body'] for c in s.list_comments(tid) if c['Body'].startswith('Waiting its turn')]
    assert said == ['Waiting its turn: 3 agents plus subagents already fill the 4 agent slots, and it starts by itself when there is room.']
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(bb, 'live_count', return_value=4):
        assert ingest.busy_words(s) == '4 agents are already running'

def test_a_drain_waits_on_light_load_too():
    s = home(auto_sessions='1'); tid = s.create_task({'Title': 'Plan the offsite', 'Kind': 'general'}, 't')
    s.enqueue_dispatch(tid, None, 'assistant', 'full', brief='notes')
    with mock.patch.object(bb, 'live_count', return_value=0), mock.patch.object(ingest, '_start_general', return_value=True) as start:
        with mock.patch.dict(terminal.SESSIONS, {'x': subs(1)}, clear=True): bb.drain(s)
        start.assert_not_called()                                                 # 0.2 + 1 does not fit in 1
        bb.drain(s); assert start.call_args[0][1:] == (tid, 'notes')
