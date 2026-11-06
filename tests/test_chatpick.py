"""The chat picker's one list (chatpick.py, GET /api/chats/{kind}): every picker on Settings > Phone & chats and a task's "Talk to this
agent from…" reads it - the Assistant chat takes the rows the owner is alone in, an agent channel any row, with the ones a binding
cannot take marked and why (the owner, 2026-11-06: "why is it not the same code with dropdown above")."""
import tempfile
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import agentchannels as ac, chatpick, messengers, remote_assistant, server, terminal as term
from taskuary.store import MemoryStore, task_ref
from taskuary.testing import Factory

c = TestClient(server.app)
ME = '15550001111'
OWN, CODING, TEAM, GAIL = f'{ME}-1600000000@g.us', f'{ME}-1700000000@g.us', '120363000000000001@g.us', '15550102233@s.whatsapp.net'
ROSTER = [{'jid': OWN, 'group': True, 'name': 'Alex Doyle (you)', 'people': 1, 'last': '2026-11-06 09:00'},
          {'jid': CODING, 'group': True, 'name': 'Coding', 'people': 1, 'last': '2026-11-06 08:00'},
          {'jid': TEAM, 'group': True, 'name': 'Northwind ledger team', 'people': 5, 'last': '2026-11-05 17:00'},
          {'jid': GAIL, 'group': False, 'name': 'Gail Moreno', 'people': None, 'last': '2026-11-04 12:00'}]


@pytest.fixture
def s(monkeypatch):
    st = MemoryStore()
    st.set_setting('owner_name', 'Alex Doyle', 'owner'); st.set_setting('developer_mode', '1', 'owner')
    for k in ('whatsapp', 'telegram', 'slack'):
        st.save_connector({'Type': k, 'Name': k, 'Active': 1, 'Roles': 'tool', 'Secret': 'tok', 'ConfigJson': '{}'}, 'test')
    monkeypatch.setattr(server, 'store', st)
    monkeypatch.setattr(messengers, 'wa_chats', lambda conn, store=None, kept=False: [dict(r) for r in ROSTER])
    monkeypatch.setattr(messengers, 'wa_self_number', lambda store, conn: ME)
    yield st
    ac._changed(st)


def wa(s): return chatpick.connector(s, 'whatsapp')
def by(rows): return {r['to']: r for r in rows}


def test_whatsapp_rows_are_named_and_marked_only_you_group_or_direct(s):
    rows = chatpick.chats(s, 'whatsapp')
    assert [r['to'] for r in rows] == [OWN, CODING, TEAM, GAIL], 'the roster order - newest first - is kept'
    k = {r['name']: (r['kind'], r['people']) for r in rows}
    assert k == {'Alex Doyle (you)': ('you', 1), 'Coding': ('you', 1), 'Northwind ledger team': ('group', 5), 'Gail Moreno': ('direct', None)}
    assert not by(rows)[TEAM]['mine'], 'a group with people in it is never the owner-alone kind'


def test_the_assistant_picker_reads_the_same_list(s):
    assert TEAM not in [o['to'] for o in remote_assistant.candidates(s, wa(s))]
    assert {OWN, CODING} <= {o['to'] for o in remote_assistant.candidates(s, wa(s))}


def test_a_bridge_that_will_not_answer_leaves_the_seen_chats(s, monkeypatch):
    def down(*a, **k): raise RuntimeError('bridge /chats failed (503)')
    monkeypatch.setattr(messengers, 'wa_chats', down)
    with mock.patch.object(s, 'chats', return_value=[{'Channel': 'whatsapp', 'Cid': f'whatsapp:{TEAM}', 'Name': 'Northwind ledger team', 'N': 3,
                                                      'Last': '2026-11-05 17:00'}]):
        rows = chatpick.chats(s, 'whatsapp')
    assert [(r['to'], r['kind']) for r in rows] == [(TEAM, 'group')]
    assert remote_assistant.candidates(s, wa(s)) == [], 'a seen chat is never offered as the Assistant chat on its word alone'


def test_telegram_groups_are_marked_by_their_negative_id(s):
    cid = chatpick.connector(s, 'telegram')['ConnectorId']
    s.save_source({'Channel': 'telegram', 'Address': '4242', 'ConnectorId': cid, 'Active': 0, 'Owner': 'discovered: Alex Doyle'}, 'o')
    s.save_source({'Channel': 'telegram', 'Address': '-1001234567890', 'ConnectorId': cid, 'Active': 0, 'Owner': 'discovered: Coding'}, 'o')
    s.save_source({'Channel': 'telegram', 'Address': '*', 'ConnectorId': cid, 'Active': 1}, 'o')
    assert {(r['name'], r['kind'], r['mine']) for r in chatpick.chats(s, 'telegram')} == {('Alex Doyle', 'direct', True), ('Coding', 'group', False)}


def test_slack_lists_the_channels_its_token_is_in_and_falls_back_to_the_seen_ones(s):
    page = {'ok': True, 'channels': [{'id': 'C0LEDGER', 'name': 'ledger', 'is_private': True}, {'id': 'G0MPIM', 'name': 'mpdm-gail--ray', 'is_mpim': True}]}
    with mock.patch('taskuary.channels._slack', return_value=page) as call:
        rows = chatpick.chats(s, 'slack')
    assert call.call_args.args[1] == 'users.conversations'
    assert [(r['to'], r['name'], r['kind'], r['hint']) for r in rows] == [('C0LEDGER', '#ledger', 'group', 'private channel'),
                                                                          ('G0MPIM', 'group DM mpdm-gail--ray', 'group', '')]
    seen = [{'Channel': 'slack', 'Cid': 'slack:C0PORTAL', 'Name': 'Ray Colton', 'N': 2, 'Last': '2026-11-05'}]
    with mock.patch('taskuary.channels._slack', side_effect=RuntimeError('slack users.conversations: missing_scope')), \
         mock.patch.object(s, 'chats', return_value=seen):
        assert [(r['to'], r['kind']) for r in chatpick.chats(s, 'slack')] == [('C0PORTAL', 'group')]


def test_the_endpoint_marks_what_an_agent_channel_cannot_bind_and_why(s):
    s.merge_connector_config(wa(s)['ConnectorId'], {'assistant_chat': OWN})
    tid = Factory(s).task(title='Ledger rounding', kind='coding')
    term.SESSIONS[f's{tid}'] = SimpleNamespace(alive=True, task_id=tid, cwd=tempfile.mkdtemp(), argv=['claude'], quick=False, sid=f's{tid}',
                                               mode='full', draft='')
    try: ac.bind(s, 'whatsapp', TEAM, tid, members=[])
    finally: term.SESSIONS.pop(f's{tid}', None)
    rows = by(c.get('/api/chats/whatsapp', params={'agent': 1}).json()['data'])
    assert rows[OWN]['blocked'] == ac.ASSISTANT_CHAT and 'already reaches the coding agents' in rows[OWN]['blocked']
    assert rows[TEAM]['blocked'] == f"already talks to {task_ref(tid)}'s agent"
    assert rows[CODING]['blocked'] == rows[GAIL]['blocked'] == ''
    plain = c.get('/api/chats/whatsapp').json()['data']
    assert [r['to'] for r in plain] == [OWN, CODING, TEAM, GAIL] and not any('blocked' in r for r in plain)
    assert c.get('/api/chats/fax').status_code == 404


def test_the_setup_read_no_longer_carries_its_own_chat_list(s):
    v = c.get('/api/agent-channels').json()['data']
    assert v['kinds'] and not any('chats' in k for k in v['kinds']), 'the picker reads /api/chats/{kind}, one list for every picker'
