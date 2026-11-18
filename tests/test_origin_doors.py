"""The doors an owner's own task comes through start at `owner`; Trust this task raises one; release remembers the sender."""
from fastapi.testclient import TestClient
from taskuary import server, origin, terminal

c = TestClient(server.app)
agent = lambda: {'X-Taskuary-Token': server.cfg['server']['agent_token']}

def _stranger_task(base=None, frm='someone@vendor.example', meta=None):
    tid = server.store.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'email', **({'OriginBase': base} if base else {})}, 'router')
    server.store.add_message({'TaskId': tid, 'Channel': 'email', 'SourceName': 'box@northwind.example', 'FromEmail': frm, 'Status': 'routed',
                              **({'MailMetaJson': meta} if meta else {})})
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

def test_trust_remembers_the_first_inbound_email_sender(monkeypatch):
    from taskuary import ingest
    tid = _stranger_task(frm='released@vendor.example'); server.store.tag_task(tid, ingest.HOLD_TAG, on=True, actor='t')
    monkeypatch.setattr(server, 'start_session', lambda *a, **k: 'sid')
    assert c.post(f'/api/tasks/{tid}/trust').json()['origin'] != 'stranger'
    assert server.store._rows('SELECT Reason FROM sender_trust WHERE Mailbox=? AND Address=?', ('box@northwind.example', 'released@vendor.example'))

def test_trust_of_a_task_with_no_email_does_nothing_extra(monkeypatch):
    from taskuary import ingest
    tid = server.store.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'teams'}, 'router')
    server.store.add_message({'TaskId': tid, 'Channel': 'teams', 'SourceName': 'room', 'FromName': 'Erin Blake', 'Status': 'routed'})
    server.store.tag_task(tid, ingest.HOLD_TAG, on=True, actor='t')
    monkeypatch.setattr(server, 'start_session', lambda *a, **k: 'sid')
    assert c.post(f'/api/tasks/{tid}/trust').json()['origin'] != 'stranger'

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


def test_the_hold_names_the_address_says_trust_is_kept_and_settings_takes_it_back(monkeypatch):
    """A stranger named like a colleague read as that colleague on the hold line, and a Trust was kept for good with no way back (the
    readiness review, 2026-11-14): the line carries the address, the note under it says the trust is kept, and Remove ends it."""
    from taskuary import ingest
    tid = server.store.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'email'}, 'router')
    server.store.add_message({'TaskId': tid, 'Channel': 'email', 'SourceName': 'box@northwind.example', 'FromName': 'Erin Blake',
                              'FromEmail': 'erin@lookalike.example', 'Status': 'routed'})
    server.store.tag_task(tid, ingest.HOLD_TAG, on=True, actor='t')
    h = origin.hold(server.store, tid)
    assert 'Erin Blake (erin@lookalike.example)' in h['line'] and 'Settings' in h['after']
    # ...and the task's own read says it is held, so Came from stands aside for the chat's one line and one Trust (2026-11-15: it said it
    # again in other words, with two more buttons) - and stops saying so the moment it is trusted
    assert c.get(f'/api/tasks/{tid}').json()['origin'].get('held') is True
    monkeypatch.setattr(server, 'start_session', lambda *a, **k: 'sid')
    c.post(f'/api/tasks/{tid}/trust')
    assert 'held' not in c.get(f'/api/tasks/{tid}').json()['origin']
    row = next(r for r in c.get('/api/trusted').json()['data'] if r['label'] == 'erin@lookalike.example')
    assert c.post('/api/trusted/remove', json={'kind': row['kind'], 'key': row['key']}, headers=agent()).status_code == 403
    assert c.post('/api/trusted/remove', json={'kind': row['kind'], 'key': row['key']}).json()['ok']
    assert not server.store.trusted_sender('box@northwind.example', 'erin@lookalike.example')
    assert c.post('/api/trusted/remove', json={'kind': row['kind'], 'key': row['key']}).status_code == 404

def test_trust_on_a_forged_from_vouches_the_task_but_never_remembers_the_address(monkeypatch):
    """A From the receiving server could not verify may be forged: Trust vouches for this task, and its address is NOT kept as trusted
    (senders.vouch's own rule) - the endpoint used to remember the opener a second way, around that rule, so the forger's next mail
    started its agent by itself."""
    from taskuary import ingest
    tid = _stranger_task(frm='spoof@vendor.example', meta='{"auth": "fail"}')
    server.store.tag_task(tid, ingest.HOLD_TAG, on=True, actor='t')
    monkeypatch.setattr(server, 'start_session', lambda *a, **k: 'sid')
    assert c.post(f'/api/tasks/{tid}/trust').json()['origin'] != 'stranger'
    assert not server.store.trusted_sender('box@northwind.example', 'spoof@vendor.example')

def test_a_second_stranger_s_trust_remembers_them_not_the_opener_he_took_back(monkeypatch):
    """Timeline on one task: a stranger opens it, Trust; the owner takes that trust back in Settings; someone else writes on the thread
    and the task is held again, its button naming THEM. Trust remembers the person the button named - it used to re-trust the opener the
    owner had just removed and leave the new writer a stranger, held again on their next mail."""
    from taskuary import ingest
    tid = _stranger_task(frm='first@vendor.example')
    monkeypatch.setattr(server, 'start_session', lambda *a, **k: 'sid')
    c.post(f'/api/tasks/{tid}/trust')
    assert server.store.trusted_sender('box@northwind.example', 'first@vendor.example')
    assert c.post('/api/trusted/remove', json={'kind': 'person', 'key': {'mailbox': 'box@northwind.example', 'address': 'first@vendor.example'}}).json()['ok']
    server.store.add_message({'TaskId': tid, 'Channel': 'email', 'SourceName': 'box@northwind.example', 'FromName': 'Omar Keller',
                              'FromEmail': 'second@other.example', 'Status': 'routed'})
    server.store.tag_task(tid, ingest.HOLD_TAG, on=True, actor='t')
    assert origin.of_task(server.store, tid)[0] == 'stranger'
    assert c.get(f'/api/tasks/{tid}').json()['origin']['trust']['person'] == 'Trust Omar'
    c.post(f'/api/tasks/{tid}/trust')
    assert server.store.trusted_sender('box@northwind.example', 'second@other.example')
    assert not server.store.trusted_sender('box@northwind.example', 'first@vendor.example')
