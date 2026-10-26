"""The doors an owner's own task comes through start at `owner`; Trust this task raises one; release remembers the sender."""
from fastapi.testclient import TestClient
from taskuary import server, origin, terminal

c = TestClient(server.app)
agent = lambda: {'X-Taskuary-Token': server.cfg['server']['agent_token']}

def _stranger_task(base=None, frm='someone@vendor.example'):
    tid = server.store.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'email', **({'OriginBase': base} if base else {})}, 'router')
    server.store.add_message({'TaskId': tid, 'Channel': 'email', 'SourceName': 'box@northwind.example', 'FromEmail': frm, 'Status': 'routed'})
    return tid

def test_a_task_the_owner_types_is_the_owner_s():
    r = c.post('/api/tasks', json={'Title': 'Rename the export', 'Kind': 'coding'})
    assert origin.of_task(server.store, r.json()['taskId'])[0] == 'owner'

def test_a_note_and_a_setup_task_are_the_owner_s():
    from taskuary import concierge
    n = c.post('/api/notes', json={'title': 'chase the vendor'}).json()['taskId']
    assert server.store.get_task(n)['OriginBase'] == 'owner'
    t = concierge.setup_task(server.store, 'Add Erin to payroll', kind='general')['taskId']
    assert server.store.get_task(t)['OriginBase'] == 'owner'

def test_trust_this_task_is_the_owner_s_and_refused_to_an_agent():
    tid = _stranger_task(frm='vouched@vendor.example')          # Trust them remembers the address since 2026-10-26: its own sender
    assert origin.of_task(server.store, tid)[0] == 'stranger'
    assert c.post(f'/api/tasks/{tid}/trust', headers=agent()).status_code == 403
    assert c.post(f'/api/tasks/{tid}/trust').json()['origin'] == 'trusted'
    assert c.get(f'/api/tasks/{tid}').json()['origin']['origin'] == 'trusted'
    assert c.post('/api/tasks/99999999/trust').status_code == 404

def test_release_remembers_the_first_inbound_email_sender(monkeypatch):
    from taskuary import ingest
    tid = _stranger_task(frm='released@vendor.example'); server.store.tag_task(tid, ingest.HOLD_TAG, on=True, actor='t')
    monkeypatch.setattr(server, 'start_session', lambda *a, **k: 'sid')
    assert c.post(f'/api/tasks/{tid}/release', json={}).json()['released']
    assert server.store._rows('SELECT Reason FROM sender_trust WHERE Mailbox=? AND Address=?', ('box@northwind.example', 'released@vendor.example'))

def test_release_of_a_task_with_no_email_does_nothing_extra(monkeypatch):
    from taskuary import ingest
    tid = server.store.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'teams'}, 'router')
    server.store.add_message({'TaskId': tid, 'Channel': 'teams', 'SourceName': 'room', 'FromName': 'Erin Blake', 'Status': 'routed'})
    server.store.tag_task(tid, ingest.HOLD_TAG, on=True, actor='t')
    monkeypatch.setattr(server, 'start_session', lambda *a, **k: 'sid')
    assert c.post(f'/api/tasks/{tid}/release', json={}).json()['released']

def _hand(monkeypatch, mode):
    from taskuary import ingest
    tid = _stranger_task('owner'); typed = []
    monkeypatch.setattr(terminal, 'say_to_task', lambda *a, **k: typed.append(a))
    monkeypatch.setattr(terminal, 'mode_of_task', lambda tid: mode)
    ingest._hand_to_agent(server.store, {'answer_to_agent': 'auto'}, tid, {'from_email': 'someone@vendor.example'}, 'router')
    return typed

def test_a_stranger_s_line_is_not_typed_into_a_full_session(monkeypatch): assert _hand(monkeypatch, 'full') == []
def test_a_stranger_s_line_reaches_an_auto_session(monkeypatch): assert len(_hand(monkeypatch, 'auto')) == 1

def test_an_owner_task_s_line_is_typed_into_a_full_session(monkeypatch):
    from taskuary import ingest
    tid = server.store.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner'); typed = []
    monkeypatch.setattr(terminal, 'say_to_task', lambda *a, **k: typed.append(a)); monkeypatch.setattr(terminal, 'mode_of_task', lambda tid: 'full')
    ingest._hand_to_agent(server.store, {'answer_to_agent': 'auto'}, tid, {'from_email': 'a@b.example'}, 'router')
    assert len(typed) == 1

def test_mode_of_task_is_empty_without_a_session_and_a_term_defaults_to_full():
    assert terminal.mode_of_task(987654) == ''
    # conftest wraps Term.__init__ (no unreviewed pty), so the default is read from the source, and mode_of_task from a stand-in
    import inspect; assert "mode='full'" in inspect.getsource(terminal.Term.__init__) or "mode='full'" in inspect.getsource(terminal.Term)
    live = type('T', (), {'task_id': 424242, 'alive': True, 'mode': 'auto'})()
    terminal.SESSIONS['zz'] = live
    try: assert terminal.mode_of_task(424242) == 'auto'
    finally: terminal.SESSIONS.pop('zz', None)
