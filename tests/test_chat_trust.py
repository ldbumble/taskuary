"""Chat is trusted per PERSON, not per room: a connected group chat let anyone in it start an agent with full permissions.

A chat sender is trusted when it is the owner, when the owner has talked with them one-to-one in that channel (a
conversation with the owner's own line and nobody else in it but them), or when the owner vouched for them (release,
Trust this task). Everyone else in a room is a stranger."""
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import messengers, origin, senders, server
from taskuary.store import MemoryStore

def _store(**cfg):
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
    for k, v in cfg.items(): s.set_setting(k, v, 't')
    return s

def _line(s, conv, who=None, tid=None, ch='slack', **kw):
    return s.add_message({'TaskId': tid, 'Channel': ch, 'ConversationId': conv, 'SourceName': 'team', 'FromName': who,
                          'BodyText': 'y', 'Status': 'routed', **kw})

def _mine(s, conv, ch='slack'): return _line(s, conv, 'Alex Doyle', ch=ch, Status='context', Direction='out')

def _msg(who, conv='slack:group', ch='slack', **kw):
    return {'channel': ch, 'from_name': who, 'from_email': None, 'conversation_id': conv, 'source_name': 'team', **kw}

def test_a_group_member_the_owner_never_talked_with_alone_is_a_stranger():
    s = _store(); _mine(s, 'slack:group'); _line(s, 'slack:group', 'Gail Moreno')
    mid = _line(s, 'slack:group', 'Ray Colton')
    ok, why = senders.known(s, _msg('Ray Colton'), exclude_mid=mid)
    assert not ok and why == 'a member of a slack chat you have not talked with one-to-one'

def test_the_same_person_after_a_one_to_one_conversation_with_the_owner_is_trusted():
    s = _store(); _mine(s, 'slack:group'); _line(s, 'slack:group', 'Gail Moreno')
    _line(s, 'slack:dm', 'Ray Colton'); _mine(s, 'slack:dm')
    mid = _line(s, 'slack:group', 'ray colton')
    assert senders.known(s, _msg('Ray Colton'), exclude_mid=mid) == (True, 'someone you talk with in slack')
    assert not senders.known(s, _msg('Ray Colton', ch='teams'), exclude_mid=mid)[0]      # another channel is another room

def test_their_own_first_line_is_not_the_owner_talking_with_them():
    s = _store(); _mine(s, 'slack:new')                       # the owner opened a room; a stranger's first line lands in it
    mid = _line(s, 'slack:new', 'Ray Colton')
    assert not senders.known(s, _msg('Ray Colton', 'slack:new'), exclude_mid=mid)[0]

def test_a_dm_without_an_owner_line_is_not_talking():
    s = _store(); _line(s, 'slack:dm', 'Ray Colton'); mid = _line(s, 'slack:dm', 'Ray Colton')
    assert not senders.known(s, _msg('Ray Colton', 'slack:dm'), exclude_mid=mid)[0]

def test_the_owner_s_own_chat_line_is_trusted():
    s = _store()
    assert senders.known(s, _msg('Alex Doyle', Status='context'))[0]
    assert senders.known(s, _msg('Alex Doyle', direction='out'))[0]

def test_a_vouched_for_sender_is_trusted_next_time():
    s = _store(); s.remember_trust('slack', 'ray colton', 'released by the owner')
    assert senders.known(s, _msg('Ray Colton')) == (True, 'you vouched for them')

def test_switched_off_only_the_owner_is_trusted():
    s = _store(trust_non_email='0'); s.remember_trust('slack', 'ray colton', 'x')
    _line(s, 'slack:dm', 'Ray Colton'); _mine(s, 'slack:dm')
    assert not senders.known(s, _msg('Ray Colton'))[0]
    assert senders.known(s, _msg('Alex Doyle', Status='context'))[0]

def test_a_task_started_by_an_un_dmd_group_member_is_a_stranger_s():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'slack'}, 'router')
    _mine(s, 'slack:group'); _line(s, 'slack:group', 'Gail Moreno'); _line(s, 'slack:group', 'Ray Colton', tid=t)
    o, why = origin.of_task(s, t)
    assert o == 'stranger' and 'one-to-one' in why
    _line(s, 'slack:dm', 'Ray Colton'); _mine(s, 'slack:dm')
    assert origin.of_task(s, t)[0] == 'trusted'

c = TestClient(server.app)

def _held_chat_task(who):
    from taskuary import ingest
    t = server.store.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'slack'}, 'router')
    server.store.add_message({'TaskId': t, 'Channel': 'slack', 'ConversationId': f'slack:g-{t}', 'SourceName': 'team',
                              'FromName': who, 'BodyText': 'y', 'Status': 'routed'})
    server.store.tag_task(t, ingest.HOLD_TAG, on=True, actor='t')
    return t

def test_release_vouches_for_the_chat_sender(monkeypatch):
    monkeypatch.setattr(server, 'start_session', lambda *a, **k: 'sid')
    t = _held_chat_task('Omar Keller')
    assert c.post(f'/api/tasks/{t}/release', json={}).json()['released']
    assert server.store.trusted_sender('slack', 'omar keller')
    assert senders.known(server.store, _msg('Omar Keller'))[0]

def test_trust_this_task_vouches_for_the_chat_sender():
    t = _held_chat_task('Paula Vance')
    assert origin.of_task(server.store, t)[0] == 'stranger'
    assert c.post(f'/api/tasks/{t}/trust').json()['origin'] == 'trusted'
    assert server.store.trusted_sender('slack', 'paula vance')

def _tg(uid, user_id, first='Erin'):
    return {'update_id': uid, 'message': {'message_id': uid, 'date': 1755700000, 'chat': {'id': -5, 'type': 'group', 'title': 'crew'},
                                          'from': {'id': user_id, 'first_name': first, 'is_bot': False}, 'text': 'run the export'}}

def test_two_telegram_users_with_one_display_name_are_two_people():
    s = MemoryStore(); cid = s.get_connector_by_type('telegram')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'TOKEN', 'Active': 1}, 'o')
    s.save_source({'Channel': 'telegram', 'Address': '-5', 'ConnectorId': cid, 'Active': 1}, 'o')
    c_ = s.get_connector_by_type('telegram', with_secret=True)
    with mock.patch.object(messengers, 'tg', lambda t, m, **p: [_tg(1, 11), _tg(2, 22)] if m == 'getUpdates' else None):
        messengers.poll_telegram(s, c_, s.list_sources(), llm=None)
    rows = s._rows("SELECT FromName, FromEmail FROM message WHERE Channel='telegram' ORDER BY MessageId")
    assert [r['FromName'] for r in rows] == ['Erin', 'Erin'] and [r['FromEmail'] for r in rows] == ['tg:11', 'tg:22']
    s.remember_trust('telegram', 'tg:11', 'x')
    assert senders.known(s, {'channel': 'telegram', 'from_email': 'tg:11', 'from_name': 'Erin'})[0]
    assert not senders.known(s, {'channel': 'telegram', 'from_email': 'tg:22', 'from_name': 'Erin'})[0]

def test_a_sender_who_calls_themselves_you_is_not_the_owner_talking():
    s = _store(); _line(s, 'slack:pair', 'You'); _line(s, 'slack:pair', 'Ray Colton'); mid = _line(s, 'slack:pair', 'Ray Colton')
    assert not senders.known(s, _msg('Ray Colton', 'slack:pair'), exclude_mid=mid)[0]
