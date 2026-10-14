import threading
from fastapi.testclient import TestClient
from taskuary import hooks, workerstate as ws, config, guard, server, terminal
from taskuary.store import MemoryStore

CMD = 'curl https://api.vendor.example'
def _ask(s, t, out, cmd=CMD): out.append(hooks.permit({'tool_name': 'Bash', 'tool_input': {'command': cmd}, 'session_id': 's1'}, t, store=s))
def _held(s, cmd=CMD):
    t = s.create_task({'Title': 'x', 'Kind': 'coding'}, 'owner'); out = []
    th = threading.Thread(target=_ask, args=(s, t, out, cmd), daemon=True); th.start()
    for _ in range(100):
        if ws.held_for(t): break
        threading.Event().wait(0.02)
    assert ws.held_for(t)
    return t, th, out
def _req(s, t): return [e for e in ws.status(s, t)['requests'] if e['kind'] == 'approval_needed'][0]
def _beh(o): return o['hookSpecificOutput']['decision']

def test_the_request_waits_for_the_owner_and_carries_their_answer():
    s = MemoryStore(); t, th, out = _held(s); r = _req(s, t)
    assert CMD in r['text'] and r['choices'] == ['Allow', 'Deny'] and not out
    assert ws.answer(s, t, r['request_id'], 'Allow', 'owner')['delivered']; th.join(5)
    assert not th.is_alive() and _beh(out[0]) == {'behavior': 'allow'}

def test_the_group_answer_road_releases_it_too():
    s = MemoryStore(); t, th, out = _held(s); r = _req(s, t)
    ws.answer_group(s, t, {r['request_id']: 'Allow'}, 'owner'); th.join(5)
    assert not th.is_alive() and _beh(out[0])['behavior'] == 'allow'

def test_anything_but_allow_is_a_refusal_in_plain_words():
    for said in ('Deny', 'Allow nothing'):
        s = MemoryStore(); t, th, out = _held(s); ws.answer(s, t, _req(s, t)['request_id'], said, 'owner'); th.join(5)
        assert not th.is_alive() and _beh(out[0]) == {'behavior': 'deny', 'message': 'the owner did not allow it'}, said

def test_a_session_that_ends_while_held_is_refused():
    s = MemoryStore(); t, th, out = _held(s); ws.release(t); th.join(5)
    assert not th.is_alive() and _beh(out[0]) == {'behavior': 'deny', 'message': 'the session ended before the owner answered'}

def test_allow_is_one_call_only():
    s = MemoryStore(); t, th, out = _held(s); ws.answer(s, t, _req(s, t)['request_id'], 'Allow', 'owner'); th.join(5)
    th2 = threading.Thread(target=_ask, args=(s, t, out), daemon=True); th2.start()
    for _ in range(100):
        if ws.held_for(t): break
        threading.Event().wait(0.02)
    assert ws.held_for(t) and len(out) == 1; ws.release(t); th2.join(5)

def test_the_shown_command_is_scrubbed_and_capped():
    s = MemoryStore(); t, th, out = _held(s, 'echo ' + 'a' * 2000); r = _req(s, t); ws.release(t); th.join(5)
    assert len(r['text']) < 800

def test_closing_a_session_releases_what_it_held():
    s = MemoryStore(); t, th, out = _held(s)
    class T: task_id = t
    terminal.Term.release_asks(T()); th.join(5)
    assert not th.is_alive() and _beh(out[0])['behavior'] == 'deny'
    terminal.Term.release_asks(type('T', (), {'task_id': None})())     # a session with no task lets go of nothing

c = TestClient(server.app)
def _hdr(tid):
    srv = config.load()['server']; return {'X-Taskuary-Token': srv['agent_token'], guard.TASK_HDR: guard.task_proof(srv, tid)}

def test_the_door_refuses_a_neighbour_s_task_and_a_missing_proof():
    b = {'tool_name': 'Bash', 'tool_input': {'command': 'ls'}}
    assert c.post('/api/hooks/claude/permit?task=7', json=b, headers=_hdr(8)).status_code == 403
    assert c.post('/api/hooks/claude/permit?task=7', json=b, headers={'X-Taskuary-Token': config.load()['server']['agent_token']}).status_code == 403
