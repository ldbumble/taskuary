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

DM = '{"dm": true}'          # the platform said this conversation is one-to-one (the poller records it)
def _dm(s, conv, who, ch='slack'): return _line(s, conv, who, ch=ch, MailMetaJson=DM)

def _msg(who, conv='slack:group', ch='slack', **kw):
    return {'channel': ch, 'from_name': who, 'from_email': None, 'conversation_id': conv, 'source_name': 'team', **kw}

def test_a_group_member_the_owner_never_talked_with_alone_is_a_stranger():
    s = _store(); _mine(s, 'slack:group'); _line(s, 'slack:group', 'Gail Moreno')
    mid = _line(s, 'slack:group', 'Ray Colton')
    ok, why = senders.known(s, _msg('Ray Colton'), exclude_mid=mid)
    # a whole sentence: who, which channel (capitalised), and what follows from it (the owner, 2026-10-16)
    assert not ok and why == ("Ray Colton wrote in Slack, and you haven't talked with them one-to-one or answered them there, "
                              "so no agent starts on their words by itself.")

def test_the_same_person_after_a_one_to_one_conversation_with_the_owner_is_trusted():
    s = _store(); _mine(s, 'slack:group'); _line(s, 'slack:group', 'Gail Moreno')
    _dm(s, 'slack:dm', 'Ray Colton'); _mine(s, 'slack:dm')
    mid = _line(s, 'slack:group', 'ray colton')
    assert senders.known(s, _msg('Ray Colton'), exclude_mid=mid) == (True, 'You talk with Ray Colton one-to-one on Slack.')
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
    assert senders.known(s, _msg('Ray Colton')) == (True, 'You vouched for Ray Colton.')

def test_switched_off_only_the_owner_is_trusted():
    s = _store(trust_non_email='0'); s.remember_trust('slack', 'ray colton', 'x')
    _dm(s, 'slack:dm', 'Ray Colton'); _mine(s, 'slack:dm')
    assert not senders.known(s, _msg('Ray Colton'))[0]
    assert senders.known(s, _msg('Alex Doyle', Status='context'))[0]

def test_a_task_started_by_an_un_dmd_group_member_is_a_stranger_s():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'slack'}, 'router')
    _mine(s, 'slack:group'); _line(s, 'slack:group', 'Gail Moreno'); _line(s, 'slack:group', 'Ray Colton', tid=t)
    o, why = origin.of_task(s, t)
    assert o == 'stranger' and 'one-to-one' in why
    _dm(s, 'slack:dm', 'Ray Colton'); _mine(s, 'slack:dm')
    assert origin.of_task(s, t)[0] == 'trusted'

def test_a_chat_stranger_s_hold_is_the_stranger_hold_with_its_trust_presses():
    # a monitor's reply owed in a group chat said "No agent started: ... wrote in Teams" in its log, and the task's own box said "Nothing has
    # started the agent on this" with no Trust to press: the chat rule's sentence was not marked the first-time-sender hold the mail rule's is
    from taskuary import funnel, ingest
    s = _store(); _mine(s, 'slack:group'); _line(s, 'slack:group', 'Gail Moreno')
    t = s.create_task({'Title': 'x', 'Kind': 'reply', 'Source': 'slack'}, 'router')
    mid = _line(s, 'slack:group', 'Ray Colton', tid=t)
    ok, why = senders.known(s, _msg('Ray Colton'), exclude_mid=mid)
    ingest.not_started(s, t, why)
    st = funnel.idle_state(s, t)
    assert not ok and st['kind'] == 'held' and "haven't talked with them" in st['line'] and st['row'] == 'held for you - not started' and st.get('trust')

c = TestClient(server.app)

def _held_chat_task(who):
    from taskuary import ingest
    t = server.store.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'slack'}, 'router')
    server.store.add_message({'TaskId': t, 'Channel': 'slack', 'ConversationId': f'slack:g-{t}', 'SourceName': 'team',
                              'FromName': who, 'BodyText': 'y', 'Status': 'routed'})
    server.store.tag_task(t, ingest.HOLD_TAG, on=True, actor='t')
    return t

def test_trust_vouches_for_the_chat_sender_and_starts_its_agent(monkeypatch):
    monkeypatch.setattr(server, 'start_session', lambda *a, **k: 'sid')
    t = _held_chat_task('Omar Keller')
    assert c.post(f'/api/tasks/{t}/trust').json()['started'] == 'started'           # Trust records it and starts the agent (the owner, 2026-11-11)
    assert server.store.trusted_sender('slack', 'omar keller')
    assert senders.known(server.store, _msg('Omar Keller'))[0]
def ingest_hold():
    from taskuary import ingest
    return ingest.HOLD_TAG

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


def test_a_group_where_only_one_member_has_spoken_is_not_one_to_one():
    s = _store(); _mine(s, 'slack:big'); _line(s, 'slack:big', 'Mallory'); mid = _line(s, 'slack:big', 'Mallory')
    assert not senders.known(s, _msg('Mallory', 'slack:big'), exclude_mid=mid)[0]

def test_the_owner_must_answer_after_them_in_the_dm():
    s = _store(); _mine(s, 'slack:dm'); _dm(s, 'slack:dm', 'Ray Colton'); mid = _dm(s, 'slack:dm', 'Ray Colton')
    assert not senders.known(s, _msg('Ray Colton', 'slack:dm'), exclude_mid=mid)[0]
    _mine(s, 'slack:dm'); mid = _dm(s, 'slack:dm', 'Ray Colton')
    assert senders.known(s, _msg('Ray Colton', 'slack:dm'), exclude_mid=mid)[0]

def test_vouching_trusts_only_the_task_s_opener():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'slack'}, 'r')
    _line(s, 'slack:g', 'U1', tid=t); _line(s, 'slack:g', 'U2', tid=t)
    origin.raise_to(s, t, 'trusted', 'owner')
    assert s.trusted_sender('slack', 'u1') and not s.trusted_sender('slack', 'u2')

def _rows(s, ch): return s._rows(f"SELECT FromName, FromEmail, MailMetaJson FROM message WHERE Channel='{ch}' ORDER BY MessageId")
def _is_dm(r): return '"dm": true' in (r['MailMetaJson'] or '')

def test_telegram_marks_a_private_chat_as_one_to_one_and_a_group_not():
    s = MemoryStore(); cid = s.get_connector_by_type('telegram')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'TOKEN', 'Active': 1}, 'o')
    for a in ('-5', '9'): s.save_source({'Channel': 'telegram', 'Address': a, 'ConnectorId': cid, 'Active': 1}, 'o')
    dm = _tg(2, 11); dm['message']['chat'] = {'id': 9, 'type': 'private'}
    with mock.patch.object(messengers, 'tg', lambda t, m, **p: [_tg(1, 11), dm] if m == 'getUpdates' else None):
        messengers.poll_telegram(s, s.get_connector_by_type('telegram', with_secret=True), s.list_sources(), llm=None)
    assert [_is_dm(r) for r in _rows(s, 'telegram')] == [False, True]

def test_whatsapp_marks_a_direct_chat_as_one_to_one_and_a_group_not():
    s = MemoryStore(); cid = s.get_connector_by_type('whatsapp')['ConnectorId']; s.save_connector({'ConnectorId': cid, 'Active': 1}, 'o')
    for a in ('155@s.whatsapp.net', '120363@g.us'): s.save_source({'Channel': 'whatsapp', 'Address': a, 'ConnectorId': cid, 'Active': 1}, 'o')
    feed = {'seq': 2, 'messages': [{'seq': 1, 'id': 'a', 'jid': '155@s.whatsapp.net', 'name': 'Marcus', 'text': 'hi', 'ts': 1755700000},
                                   {'seq': 2, 'id': 'b', 'jid': '120363@g.us', 'group': True, 'sender': '166@s.whatsapp.net',
                                    'name': 'Gail', 'text': 'hey', 'ts': 1755700001}]}
    with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: feed):
        messengers.poll_whatsapp(s, s.get_connector_by_type('whatsapp', with_secret=True), s.list_sources(), llm=None)
    assert [_is_dm(r) for r in _rows(s, 'whatsapp')] == [True, False]

# ── worked with: the owner ANSWERING someone in a group counts, sitting in the room with them does not (2026-10-20) ──
def test_a_group_member_the_owner_has_answered_is_worked_with():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'whatsapp'}, 'router')
    g = 'whatsapp:120363@g.us'
    _line(s, g, 'Gail Moreno', ch='whatsapp', FromEmail='whatsapp:155'); _mine(s, g, ch='whatsapp')      # weeks ago: she wrote, the owner answered
    _line(s, g, 'Gail Moreno', ch='whatsapp', FromEmail='whatsapp:155', tid=t)
    ok, why = senders.known(s, _msg('Gail Moreno', g, ch='whatsapp', from_email='whatsapp:155'))
    assert ok and why == 'You have answered Gail Moreno on WhatsApp before.'
    assert origin.of_task(s, t)[0] == 'trusted'

def test_answering_someone_else_in_the_room_does_not_vouch_for_them():
    s = _store(); g = 'slack:group'
    _line(s, g, 'Ray Colton'); _line(s, g, 'Gail Moreno'); _mine(s, g)       # the owner answered Gail, after Ray had spoken
    mid = _line(s, g, 'Ray Colton')
    assert not senders.known(s, _msg('Ray Colton', g), exclude_mid=mid)[0]
    assert senders.known(s, _msg('Gail Moreno', g), exclude_mid=mid)[0]

def test_the_owner_answering_their_only_line_is_not_judged_on_that_line():
    s = _store(); g = 'slack:group'; mid = _line(s, g, 'Ray Colton'); _mine(s, g)
    assert not senders.known(s, _msg('Ray Colton', g), exclude_mid=mid)[0]  # the message under judgement never vouches for itself

def test_whatsapp_s_phone_and_lid_forms_are_one_person():
    s = _store(); g, d = 'whatsapp:120363@g.us', 'whatsapp:155@s.whatsapp.net'
    _dm(s, d, 'Gail Moreno', ch='whatsapp'); s._exec("UPDATE message SET FromEmail='whatsapp:155' WHERE ConversationId=?", (d,))
    _mine(s, d, ch='whatsapp')                                               # the direct chat names her by phone...
    meta = {'alias': 'whatsapp:155'}                                         # ...the group by LID, with the phone beside it
    assert senders.known(s, _msg('Gail Moreno', g, ch='whatsapp', from_email='whatsapp:9917', mail_meta=meta))[0]
    assert not senders.known(s, _msg('Gail Moreno', g, ch='whatsapp', from_email='whatsapp:9917'))[0]

def test_whatsapp_records_the_bridge_s_other_id_as_the_alias():
    s = MemoryStore(); cid = s.get_connector_by_type('whatsapp')['ConnectorId']; s.save_connector({'ConnectorId': cid, 'Active': 1}, 'o')
    s.save_source({'Channel': 'whatsapp', 'Address': '120363@g.us', 'ConnectorId': cid, 'Active': 1}, 'o')
    feed = {'seq': 2, 'messages': [{'seq': 1, 'id': 'a', 'jid': '120363@g.us', 'group': True, 'sender': '9917@lid',
                                    'senderAlt': '155@s.whatsapp.net', 'name': 'Gail', 'text': 'hey', 'ts': 1755700000},
                                   {'seq': 2, 'id': 'b', 'jid': '120363@g.us', 'group': True, 'sender': '166@s.whatsapp.net',
                                    'senderAlt': '166@s.whatsapp.net', 'name': 'Ray', 'text': 'hi', 'ts': 1755700001}]}
    with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: feed):
        messengers.poll_whatsapp(s, s.get_connector_by_type('whatsapp', with_secret=True), s.list_sources(), llm=None)
    r = _rows(s, 'whatsapp')
    assert r[0]['FromEmail'] == 'whatsapp:9917' and senders.chat_aliases(r[0]) == ('whatsapp:155',) and not _is_dm(r[0])
    assert senders.chat_aliases(r[1]) == ()                                  # the same id twice is no alias

def test_slack_marks_a_dm_channel_as_one_to_one():
    from taskuary import channels
    assert channels.slack_msg({'Address': 'D0123'}, {'ts': '1755700000.1', 'user': 'U9', 'text': 'x'})['mail_meta'] == {'dm': True}
    assert not channels.slack_msg({'Address': 'C0123'}, {'ts': '1755700000.1', 'user': 'U9', 'text': 'x'}).get('mail_meta')

def test_imessage_marks_only_a_known_one_to_one_chat():
    from taskuary import imessage
    base = {'rowid': 1, 'message_guid': 'g', 'chat_guid': 'c', 'text': 'hi', 'is_from_me': 0, 'sender_handle': '+15550100', 'date': 0}
    assert imessage.normalize_row({**base, 'style': 45})['dm'] is True
    assert imessage.normalize_row({**base, 'style': 43})['dm'] is False
    assert imessage.normalize_row(base)['dm'] is False                   # not known is not one-to-one

def test_teams_keys_an_addressless_sender_by_their_id_and_marks_one_on_one():
    from taskuary import channels
    s = MemoryStore(); channels._TEAMS_ME['alex@northwind.example'] = 'me-id'
    ms = [{'id': '1', 'chatId': 'c1', 'messageType': 'message', 'from': {'user': {'id': 'oid-7', 'displayName': 'Erin'}},
           'body': {'content': 'hi'}, 'createdDateTime': '2026-10-14T09:00:00Z'}]
    with mock.patch.object(channels, '_teams_delta', return_value=ms), mock.patch.object(channels, '_chat_meta', return_value=('', 'oneOnOne')), \
         mock.patch.object(channels, '_graph_user', return_value=('Teams user', '')), mock.patch.object(channels, 'hosted_images', return_value=[]):
        channels.ingest_teams_chats(s, 'alex@northwind.example', 'tok', __import__('datetime').datetime(2026, 10, 14, 8))
    r = _rows(s, 'teams')[0]
    assert r['FromEmail'] == 'teams:oid-7' and _is_dm(r)

# ── TEAMS IS INTERNAL (the owner, 2026-10-21): a colleague in the owner's tenant needs no history; a guest does ──────
def _jwt(claims):
    import base64, json
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip('=')
    return f"{b({'alg': 'none'})}.{b(claims)}.sig"

TENANT = '11111111-2222-3333-4444-555555555555'

def _teams_line(oid, tenant=TENANT, kind='aadUser', guest=False, chat='group'):
    from taskuary import channels
    s = _store(); channels._TEAMS_ME['alex@northwind.example'] = 'me-id'
    ms = [{'id': oid, 'chatId': 'c1', 'messageType': 'message', 'body': {'content': 'run the export'}, 'createdDateTime': '2026-10-14T09:00:00Z',
           'from': {'user': {'id': oid, 'displayName': 'Gail Moreno', 'tenantId': tenant, 'userIdentityType': kind}}}]
    def who(tok, o, cache): cache[('guest', o)] = guest; return ('Gail Moreno', f'{o}@vendor.example')
    with mock.patch.object(channels, '_teams_delta', return_value=ms), mock.patch.object(channels, '_chat_meta', return_value=('crew', chat)), \
         mock.patch.object(channels, '_graph_user', side_effect=who), mock.patch.object(channels, 'hosted_images', return_value=[]):
        channels.ingest_teams_chats(s, 'alex@northwind.example', _jwt({'tid': TENANT}), __import__('datetime').datetime(2026, 10, 14, 8))
    return s, s._rows("SELECT * FROM message WHERE Channel='teams'")[0]

def test_a_teams_colleague_in_the_owner_s_tenant_is_trusted_without_history():
    s, r = _teams_line('oid-7')
    ok, why = senders.known(s, {'channel': 'teams', 'from_email': r['FromEmail'], 'from_name': r['FromName'], 'MailMetaJson': r['MailMetaJson']},
                            exclude_mid=r['MessageId'])
    assert ok and why == 'Gail Moreno is in your own organisation on Teams.'
    assert origin.of_message(s, r)[0] == 'trusted'

def test_a_teams_sender_on_the_owner_s_own_domain_is_trusted():
    s = _store()
    assert senders.known(s, {'channel': 'teams', 'from_email': 'erin@northwind.example', 'from_name': 'Erin Blake'})[0]

def test_a_teams_guest_or_outsider_waits_until_the_owner_has_talked_with_them():
    for kw in ({'guest': True}, {'tenant': '99999999-0000-0000-0000-000000000000'}, {'kind': 'federatedUser'}, {'kind': 'anonymousGuest'}):
        s, r = _teams_line('oid-9', **kw)
        assert not __import__('json').loads(r['MailMetaJson'] or '{}').get('internal'), kw
        assert origin.of_message(s, r)[0] == 'stranger', kw
    s, r = _teams_line('oid-9', guest=True, chat='oneOnOne')                  # ...until the owner has answered them
    s.add_message({'Channel': 'teams', 'ConversationId': r['ConversationId'], 'FromName': 'Gail Moreno', 'FromEmail': r['FromEmail'],
                   'BodyText': 'also the totals', 'Status': 'routed', 'MailMetaJson': '{"dm": true}'})
    s.add_message({'Channel': 'teams', 'ConversationId': r['ConversationId'], 'FromName': 'You', 'FromEmail': 'alex@northwind.example',
                   'BodyText': 'on it', 'Status': 'context', 'Direction': 'out'})
    assert origin.of_message(s, r)[0] == 'trusted'

def test_a_token_that_is_not_a_jwt_trusts_nobody_by_tenant():
    from taskuary import channels
    assert channels._token_tenant('tok') == '' and not channels.teams_internal({'tenantId': TENANT}, '')

# ── A COLLEAGUE BY THEIR DIRECTORY ENTRY (2026-10-21): a Teams line often carries only id + name, and Graph's /users answer
# is what says Member or Guest - through the Teams card's own token, cached; old lines re-resolved on read ──────────────
class _Graph:
    "Fake Graph /users/{id}: `users` id -> entry, `refuse` the selects that answer 403, `down` every call fails."
    def __init__(self, users=None, refuse=(), down=False): self.users, self.refuse, self.down, self.calls = users or {}, refuse, down, []
    def __call__(self, url, headers=None, params=None, timeout=None):
        import requests
        self.calls.append(url)
        if self.down: raise requests.ConnectionError('graph unreachable')
        sel, oid = (params or {}).get('$select', ''), url.rsplit('/', 1)[-1]
        code = 403 if any(x in sel for x in self.refuse) else 200 if oid in self.users else 404
        j = {k: v for k, v in self.users.get(oid, {}).items() if code == 200 and k in sel.split(',')}
        return mock.Mock(status_code=code, json=lambda: j)

GAIL = {'displayName': 'Gail Moreno', 'mail': 'gail@northwind.example', 'userPrincipalName': 'gail@northwind.example', 'userType': 'Member'}
GUEST = {'displayName': 'Gail Moreno', 'mail': 'gail@vendor.example', 'userType': 'Guest',
         'userPrincipalName': 'gail_vendor.example#EXT#@northwind.example'}

def _bare_line(graph):
    "A Teams line whose from.user is id + name only, polled with a token that is not a JWT - only the directory can tell."
    from taskuary import channels
    s = _store(); channels._TEAMS_ME['alex@northwind.example'] = 'me-id'; channels._ORG.clear()
    ms = [{'id': 'm1', 'chatId': 'c1', 'messageType': 'message', 'body': {'content': 'run the export'}, 'createdDateTime': '2026-10-14T09:00:00Z',
           'from': {'user': {'id': 'oid-7', 'displayName': 'Gail Moreno'}}}]
    with mock.patch.object(channels, '_teams_delta', return_value=ms), mock.patch.object(channels, '_chat_meta', return_value=('crew', 'group')), \
         mock.patch.object(channels.requests, 'get', graph), mock.patch.object(channels, 'hosted_images', return_value=[]):
        channels.ingest_teams_chats(s, 'alex@northwind.example', 'tok', __import__('datetime').datetime(2026, 10, 14, 8))
    return s, s._rows("SELECT * FROM message WHERE Channel='teams'")[0]

def test_a_teams_member_resolved_by_id_is_trusted_though_the_message_names_no_address():
    s, r = _bare_line(_Graph({'oid-7': GAIL}))
    assert r['FromEmail'] == 'gail@northwind.example' and '"internal": true' in r['MailMetaJson']
    assert origin.of_message(s, r) == ('trusted', 'Gail Moreno is in your own organisation on Teams.')

def test_a_sign_in_that_may_not_read_user_type_still_resolves_the_colleague():
    "User.ReadBasic.All refuses userType outright: the address must not be lost with it (0.3.9.15 lost it)."
    s, r = _bare_line(_Graph({'oid-7': GAIL}, refuse=('userType',)))
    assert r['FromEmail'] == 'gail@northwind.example'                        # on the Teams account's own domain
    assert origin.of_message(s, r)[0] == 'trusted'

def test_a_teams_guest_resolved_by_id_is_not_trusted():
    s, r = _bare_line(_Graph({'oid-7': GUEST}))
    assert '"internal": false' in r['MailMetaJson']
    o, why = origin.of_message(s, r)
    assert o == 'stranger' and "haven't talked with them" in why

def _old_line(s, key='teams:oid-7'):
    "A Teams line stored before 0.3.9.15: no sender tenant, no address (the lookup was refused), no 'internal'."
    return s.add_message({'Channel': 'teams', 'ConversationId': 'teams:c1', 'SourceName': 'alex@northwind.example', 'FromName': 'Gail Moreno',
                          'FromEmail': key, 'BodyText': 'run the export', 'Status': 'routed'})

def test_a_line_ingested_before_the_fix_is_re_resolved_once_and_remembered():
    from taskuary import channels, outbound
    s = _store(); channels._ORG.clear(); mid = _old_line(s); g = _Graph({'oid-7': GAIL})
    with mock.patch.object(outbound, '_graph_token', return_value='tok'), mock.patch.object(channels.requests, 'get', g):
        assert origin.of_message(s, s.get_message(mid)) == ('trusted', 'Gail Moreno is in your own organisation on Teams.')
        n = len(g.calls); origin.of_message(s, s.get_message(mid))
    assert g.calls[0].endswith('/users/oid-7') and len(g.calls) == n                  # asked once
    assert s.trusted_sender('teams', 'teams:oid-7') == channels.ORG_REASON

def test_a_graph_that_fails_falls_back_to_the_chat_rule_without_a_crash():
    from taskuary import channels, outbound
    s = _store(); channels._ORG.clear(); mid = _old_line(s)
    with mock.patch.object(outbound, '_graph_token', return_value='tok'), mock.patch.object(channels.requests, 'get', _Graph(down=True)):
        o, why = origin.of_message(s, s.get_message(mid))
    assert o == 'stranger' and "haven't talked with them" in why
    channels._ORG.clear()                                                    # and no connection at all: the same, quietly
    assert origin.of_message(s, s.get_message(mid))[0] == 'stranger'

def _held_task(s, tag=True):
    from taskuary.ingest import HOLD_TAG
    t = s.create_task({'Title': 'Run the export', 'Kind': 'general', 'Status': 'open', 'Assignee': 'agent:assistant'}, 'triage')
    mid = _old_line(s); s._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (t, mid))
    if tag: s.tag_task(t, HOLD_TAG)
    s.add_route(mid, t, 'create', 0.0, "triage: work \u00b7 held for you: Gail Moreno wrote in Teams, and you haven't talked with them "
                "one-to-one or answered them there, so no agent starts on their words by itself.", [], 'router')
    return t

def test_a_held_task_from_a_colleague_resolved_since_is_no_longer_held_but_does_not_start_by_itself():
    from taskuary import channels, funnel, outbound
    from taskuary.ingest import HOLD_TAG
    for tag in (True, False):                                     # a chat hold is not always tagged; its route sentence still is stale
        s = _store(); channels._ORG.clear(); t = _held_task(s, tag)
        with mock.patch.object(outbound, '_graph_token', return_value='tok'), mock.patch.object(channels.requests, 'get', _Graph({'oid-7': GAIL})):
            st = funnel.idle_state(s, t)
        assert (st['kind'], st['row']) == ('idle', 'not started yet') and 'talked with' not in st['line'], st
        assert not s.task_has_tag(t, HOLD_TAG) and not s.get_dispatch(t) and not s.list_runs(t)

def test_a_held_task_whose_sender_cannot_be_resolved_stays_held():
    from taskuary import channels, funnel, origin, outbound
    from taskuary.ingest import HOLD_TAG
    s = _store(); channels._ORG.clear(); t = _held_task(s)
    with mock.patch.object(outbound, '_graph_token', return_value='tok'), mock.patch.object(channels.requests, 'get', _Graph(down=True)):
        st, o = funnel.idle_state(s, t), origin.of_task(s, t)
    assert st['kind'] == 'held' and "haven't talked with them" in st['line'] and s.task_has_tag(t, HOLD_TAG) and o[0] == 'stranger'

def test_the_task_list_read_alone_drops_the_stale_hold():
    from taskuary import channels, origin, outbound
    from taskuary.ingest import HOLD_TAG
    s = _store(); channels._ORG.clear(); t = _held_task(s)
    with mock.patch.object(outbound, '_graph_token', return_value='tok'), mock.patch.object(channels.requests, 'get', _Graph({'oid-7': GAIL})):
        assert origin.of_task(s, t)[0] == 'trusted'
    assert not s.task_has_tag(t, HOLD_TAG)

def test_discord_and_chat_servers_key_a_sender_by_the_platform_id():
    from datetime import datetime
    from taskuary import devtools, chatservers
    s = MemoryStore(); src = {'Address': 'room1'}; since = datetime(2020, 1, 1)
    with mock.patch.object(devtools, '_discord', return_value=[{'id': '5', 'timestamp': '2026-10-14T09:00:00+00:00', 'content': 'hi',
                                                                 'author': {'id': '42', 'global_name': 'Erin', 'username': 'erin'}}]):
        devtools.poll_discord(s, {}, src, since)
    with mock.patch.object(chatservers, '_mm', return_value={'order': ['p1'], 'posts': {'p1': {'message': 'hi', 'user_id': 'u77', 'create_at': 1,
                                                                                                 'props': {'override_username': 'Erin'}}}}):
        chatservers.poll_mattermost(s, {}, src, since)
    with mock.patch.object(chatservers, '_rc', return_value={'messages': [{'_id': 'm1', 'msg': 'hi', 'ts': '2026-10-14T09:00:00Z',
                                                                            'u': {'_id': 'r9', 'name': 'Erin', 'username': 'erin'}}]}):
        chatservers.poll_rocketchat(s, {}, src, since)
    with mock.patch.object(chatservers, '_gc', return_value={'messages': [{'name': 'spaces/A/messages/1', 'text': 'hi', 'createTime': '2026-10-14T09:00:00Z',
                                                                            'sender': {'name': 'users/123', 'displayName': 'Erin'}}]}):
        chatservers.poll_google_chat(s, {}, src, since)
    got = {ch: _rows(s, ch)[0] for ch in ('discord', 'mattermost', 'rocketchat', 'google_chat')}
    assert {ch: r['FromEmail'] for ch, r in got.items()} == {'discord': 'discord:42', 'mattermost': 'mm:u77', 'rocketchat': 'rocket:r9',
                                                             'google_chat': 'gchat:users/123'}
    assert {r['FromName'] for r in got.values()} == {'Erin'}

# A TEAMS SENDER'S HISTORY BEFORE THEIR ID (2026-10-26, the owner: "we have talked to this person a million times"): a colleague in a
# sister tenant - the directory cannot place them, so 'internal' is false - was stored by display name until their Graph id replaced it
SISTER = '{"internal": false, "tenant": "tenant-sister"}'
def _sister(s, conv='teams:19:crew', key='teams:oid-9', **kw):
    return _line(s, conv, 'Marcus Reed', ch='teams', SourceName='alex@northwind.example', FromEmail=key, MailMetaJson=SISTER, **kw)

def _sister_msg(conv='teams:19:crew'):
    return {'channel': 'teams', 'from_name': 'Marcus Reed', 'from_email': 'teams:oid-9', 'conversation_id': conv,
            'source_name': 'alex@northwind.example', 'MailMetaJson': SISTER}

def test_a_teams_colleague_the_owner_answered_under_their_name_is_known_by_their_id_too():
    s = _store()
    _line(s, 'teams:19:crew', 'Erin Blake', ch='teams'); _line(s, 'teams:19:crew', 'Marcus Reed', ch='teams', FromEmail='')   # stored by name
    _mine(s, 'teams:19:crew', ch='teams')                                                                                 # ...and answered
    mid = _sister(s)
    assert senders.known(s, _sister_msg(), exclude_mid=mid) == (True, 'You have answered Marcus Reed on Teams before.')
    t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'teams'}, 'router'); s._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (t, mid))
    assert origin.of_task(s, t)[0] == 'trusted'                                                   # the held task is released on read

def test_a_copied_name_in_another_teams_chat_borrows_nothing():
    s = _store(); _line(s, 'teams:19:crew', 'Marcus Reed', ch='teams', FromEmail=''); _mine(s, 'teams:19:crew', ch='teams')
    mid = _sister(s, conv='teams:19:other')
    ok, why = senders.known(s, _sister_msg('teams:19:other'), exclude_mid=mid)
    assert not ok and "haven't talked with them" in why
    # ...nor does a name-keyed line nobody answered, nor someone else's answered line
    s = _store(); _line(s, 'teams:19:crew', 'Marcus Reed', ch='teams', FromEmail=''); _line(s, 'teams:19:crew', 'Erin Blake', ch='teams')
    _mine(s, 'teams:19:crew', ch='teams'); mid = _sister(s)
    assert not senders.known(s, _sister_msg(), exclude_mid=mid)[0]


def test_trust_on_a_held_reply_task_starts_the_agent_that_writes_the_reply():
    """Recorded on the real CLI, 2026-11-13: a question in a chat from a sender not yet vouched for made a REPLY task - a reply owed, no
    draft, its start held ("you haven't talked with them one-to-one"). Trust lifted the hold and returned no start (only an agent's kind
    of task started one): the chat stood on "You trusted the sender" over an empty reply box, nothing at work and nothing lit. The start
    the hold refused is the one Trust makes - the reply's own hand-over (ingest.reply_to_agent), as at arrival."""
    from unittest import mock
    from taskuary import general, ingest
    s = server.store
    t = s.create_task({'Title': 'What is the total?', 'Kind': 'reply', 'Source': 'whatsapp'}, 'router')
    mid = s.add_message({'TaskId': t, 'Channel': 'whatsapp', 'ConversationId': f'wa:g-{t}', 'SourceName': 'Gail Moreno', 'FromName': 'Gail Moreno',
                         'BodyText': 'Alex, what is the total on the March invoice?', 'Status': 'routed'})
    rid = s.add_review({'TaskId': t, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'needs a reply'})
    s.tag_task(t, ingest.HOLD_TAG, on=True, actor='t')
    # ...the app's own store is shared by every test in the run: one before it left "start by itself" off (CI, 2026-11-13: started '' - the
    # task said "Starting an agent by itself is switched off"), so the switch this start goes through is set here, as the owner's default
    was = s.get_settings().get('general_auto_enabled')
    s.set_setting('general_auto_enabled', '1', 't')
    try:
        with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
            got = c.post(f'/api/tasks/{t}/trust').json()
        assert got['started'] == 'started', got
        assert [x[0][0].__name__ for x in spawn.call_args_list] == ['_auto_general'] and spawn.call_args[0][2] == t
        assert s.get_task(t)['Kind'] == 'general' and s.get_review(rid)['Status'] == 'pending'       # the agent's to fill, for his Send
    finally:
        general.OPENING.discard(t)
        if was is not None: s.set_setting('general_auto_enabled', was, 't')


# ── A QUOTED TEAMS LINE KEEPS WHAT IT QUOTES (the owner, 2026-11-25): Graph puts a quote in `attachments` as a messageReference - the quoted
# message's id, its sender and a preview - and only a tag in the body. It came in as a bare "any news on this one", and the agent could not
# tell which one ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _quoting(content=None, graph=None, before=()):
    "Gail's line quoting message q1 in chat c1, polled through a stand-in Graph `graph` (url -> (status, json)); `before`: rows stored first."
    import json
    from taskuary import channels, general
    s = _store(); channels._TEAMS_ME['alex@northwind.example'] = 'me-id'
    for r in before: s.add_message(r)
    att = {'id': 'q1', 'contentType': 'messageReference', 'content': json.dumps(content) if content is not None else None}
    ms = [{'id': 'm2', 'chatId': 'c1', 'messageType': 'message', 'createdDateTime': '2026-11-20T10:00:00Z', 'attachments': [att],
           'body': {'content': '<attachment id="q1"></attachment><p>Hi Alex, any news on this one please?</p>'},
           'from': {'user': {'id': 'oid-7', 'displayName': 'Gail Moreno'}}}]
    calls = []
    def get(url, headers=None, params=None, timeout=None):
        calls.append(url); code, j = (graph or {}).get(url, (404, {}))
        return mock.Mock(status_code=code, json=lambda: j)
    with mock.patch.object(channels, '_teams_delta', return_value=ms), mock.patch.object(channels, '_chat_meta', return_value=('crew', 'group')), \
         mock.patch.object(channels, '_graph_user', return_value=('Gail Moreno', 'gail@vendor.example')), \
         mock.patch.object(channels.requests, 'get', get), mock.patch.object(channels, 'hosted_images', return_value=[]):
        channels.ingest_teams_chats(s, 'alex@northwind.example', 'tok', __import__('datetime').datetime(2026, 11, 20, 8))
    r = s.message_by_external('teams:c1:m2')
    return r, general.mail_row(s, r), calls

Q1 = 'https://graph.microsoft.com/v1.0/chats/c1/messages/q1'
QUOTED = {'id': 'q1', 'createdDateTime': '2026-11-18T14:05:00Z', 'from': {'user': {'id': 'oid-8', 'displayName': 'Ray Colton'}},
          'body': {'content': '<p>The March export is missing the second site - can you rerun it?</p>'}}

def test_a_teams_quote_rides_on_the_arrival_read_by_its_id():
    _r, row, calls = _quoting({'messageId': 'q1', 'messagePreview': 'The March export is missing', 'messageSender': {'user': {'displayName': 'Ray Colton'}}},
                              graph={Q1: (200, QUOTED)})
    assert row['words'] == 'Hi Alex, any news on this one please?' and calls == [Q1]
    assert row['reply']['who'] == 'Ray Colton' and row['reply']['text'] == 'The March export is missing the second site - can you rerun it?'
    assert row['reply']['at'].startswith('2026-11-18')

def test_a_teams_quote_carrying_only_the_id_is_fetched_and_one_graph_refuses_keeps_its_preview():
    _r, row, _c = _quoting(None, graph={Q1: (200, QUOTED)})                       # no preview, no sender: read whole by its id
    assert row['reply']['who'] == 'Ray Colton' and 'second site' in row['reply']['text']
    _r, row, _c = _quoting({'messagePreview': 'The March export is missing', 'messageSender': {'user': {'displayName': 'Ray Colton'}}},
                           graph={Q1: (403, {})})                                # an app outside the chat is refused: the preview stands
    assert row['reply'] == {'who': 'Ray Colton', 'text': 'The March export is missing'}

def test_a_teams_quote_of_a_stored_line_is_read_from_the_store():
    stored = {'ExternalId': 'teams:c1:q1', 'Channel': 'teams', 'ConversationId': 'teams:c1', 'FromName': 'Ray Colton',
              'SentAt': '2026-11-18 15:05:00', 'BodyText': 'Can you rerun the March export?', 'Status': 'routed'}
    _r, row, calls = _quoting({'messagePreview': 'Can you rerun'}, before=[stored])
    assert calls == [] and row['reply'] == {'who': 'Ray Colton', 'at': '2026-11-18 15:05:00', 'text': 'Can you rerun the March export?'}

def test_a_slack_thread_reply_and_a_whatsapp_quote_name_what_they_answer():
    from taskuary import channels, ingest
    m = channels.slack_msg({'Address': 'C0123'}, {'ts': '1755700005.1', 'thread_ts': '1755700000.1', 'subtype': 'thread_broadcast', 'user': 'U9', 'text': 'done?'})
    assert m['reply_to'] == {'ext': 'slack:C0123:1755700000.1'}
    s = _store(); s.add_message({'ExternalId': 'slack:C0123:1755700000.1', 'Channel': 'slack', 'FromName': 'Erin Blake', 'BodyText': 'ship the fix', 'Status': 'routed'})
    assert ingest.with_parent(s, m)['mail_meta']['reply_to']['text'] == 'ship the fix'
    assert ingest.with_parent(s, {'reply_to': {'ext': 'whatsapp:j:none', 'text': 'which export?'}})['mail_meta']['reply_to'] == \
        {'ext': 'whatsapp:j:none', 'text': 'which export?'}
    assert 'mail_meta' not in ingest.with_parent(s, {'reply_to': {'ext': 'slack:C0123:unknown'}})          # nothing to show: nothing kept

def test_a_mail_names_the_mail_it_answers_only_where_that_one_is_not_on_its_task():
    import json
    from taskuary import general, ingest
    s = _store(); t1, t2 = (s.create_task({'Title': x, 'Kind': 'reply'}, 't') for x in ('a', 'b'))
    s.add_message({'TaskId': t1, 'ExternalId': 'e1', 'ConversationId': 'cv', 'Channel': 'email', 'FromName': 'Erin Blake', 'BodyText': 'Rates for 2027?',
                   'Status': 'routed', 'MailMetaJson': json.dumps({'mid': '<a1@vendor.example>'})})
    meta = ingest.with_parent(s, {'conversation_id': 'cv', 'mail_meta': {'refs': ['<a1@vendor.example>']}})['mail_meta']
    assert meta['reply_to']['text'] == 'Rates for 2027?' and meta['reply_to']['ext'] == 'e1'
    row = lambda tid: {'TaskId': tid, 'Channel': 'email', 'MailMetaJson': json.dumps(meta)}
    assert general.replied(s, row(t1)) == {} and general.replied(s, row(t2))['who'] == 'Erin Blake'
