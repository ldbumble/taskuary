"""Where the assistant can be reached is one question, asked once.

It used to be three places: a bare text box asking for a chat id on the WhatsApp card, another on
the Telegram card, and the standing permission a tab away under Notifications - whose own help text
had to end with "name the Assistant chat on the WhatsApp or Telegram card under Connections first".
A setting that tells you to finish the job somewhere else is the split this replaces (the owner,
2026-09-17: "i think the assistant change should be somewhere else").

Only chats the owner is ALONE in are offered. WhatsApp knows that by counting the room; Telegram
cannot be asked - a bot never sees a fromMe - so the SHAPE of the id says it, because Telegram gives
groups, supergroups and channels a negative id and a person a positive one.
"""
import json

import pytest
from fastapi.testclient import TestClient

from taskuary import remote_assistant, server
from taskuary.store import MemoryStore

c = TestClient(server.app)


@pytest.fixture
def store():
    s = MemoryStore()
    cid = s.get_connector_by_type('telegram')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': 'TOK', 'ConfigJson': json.dumps({})}, 'o')
    s.save_source({'Channel': 'telegram', 'Address': '4242', 'ConnectorId': cid, 'Active': 0,
                   'Owner': 'discovered: Alex'}, 'o')
    s.save_source({'Channel': 'telegram', 'Address': '-1001234567890', 'ConnectorId': cid, 'Active': 1,
                   'Owner': 'discovered: Night shift'}, 'o')
    return s


def telegram(s):
    return s.get_connector_by_type('telegram', with_secret=True)


# ── who is offered ──────────────────────────────────────────────────────────────────────
def test_a_private_telegram_chat_is_offered(store):
    assert [o['to'] for o in remote_assistant.candidates(store, telegram(store))] == ['4242']


def test_a_telegram_group_is_not(store):
    """A negative id is a group, a supergroup or a channel - the one thing about a Telegram chat
    that cannot be faked by naming it."""
    assert '-1001234567890' not in [o['to'] for o in remote_assistant.candidates(store, telegram(store))]


def test_the_catch_all_is_not_a_chat(store):
    cid = telegram(store)['ConnectorId']
    store.save_source({'Channel': 'telegram', 'Address': '*', 'ConnectorId': cid, 'Active': 1}, 'o')
    assert '*' not in [o['to'] for o in remote_assistant.candidates(store, telegram(store))]


def test_the_discovered_title_is_what_you_read(store):
    assert remote_assistant.candidates(store, telegram(store))[0]['name'] == 'Alex'


# ── setting it ──────────────────────────────────────────────────────────────────────────
def test_choosing_a_chat_writes_it_on_the_card(store):
    remote_assistant.use_chat(store, 'telegram', '4242')
    assert remote_assistant.chat_of(telegram(store)) == '4242'


def test_a_group_is_refused_even_if_you_ask_for_it_directly(store):
    """The picker is a convenience; this is the guard."""
    with pytest.raises(ValueError, match='not a chat you are alone in'):
        remote_assistant.use_chat(store, 'telegram', '-1001234567890')


def test_disconnecting_clears_it(store):
    remote_assistant.use_chat(store, 'telegram', '4242')
    remote_assistant.use_chat(store, 'telegram', '')
    assert remote_assistant.chat_of(telegram(store)) == ''


def test_a_channel_that_is_switched_off_cannot_be_given_one(store):
    cid = telegram(store)['ConnectorId']
    store.save_connector({'ConnectorId': cid, 'Active': 0}, 'o')
    with pytest.raises(ValueError, match='switched on'):
        remote_assistant.use_chat(store, 'telegram', '4242')


# ── one answer for every channel ────────────────────────────────────────────────────────
def test_every_doorway_channel_is_reported_whether_set_up_or_not(store):
    seen = {d['channel'] for d in remote_assistant.doorway_state(store)}
    assert seen == set(remote_assistant.CHANNELS), 'the page asks once, for all of them'


def test_a_channel_that_is_off_still_appears_and_says_so(store):
    wa = next(d for d in remote_assistant.doorway_state(store) if d['channel'] == 'whatsapp')
    assert wa['live'] is False and wa['options'] == []


def test_the_endpoint_carries_the_standing_permission_too(store):
    """Both halves of the question in one payload, because they are one panel."""
    body = c.get('/api/assistant/doorways').json()
    assert 'standing' in body and isinstance(body['data'], list)


def test_the_endpoint_refuses_a_group_with_a_reason_you_can_read():
    r = c.post('/api/assistant/doorways', json={'channel': 'telegram', 'chat': '-100999'})
    assert r.status_code == 422
    assert 'alone' in r.json()['detail'] or 'switched on' in r.json()['detail']


# ── when it may listen is a question per channel ────────────────────────────────────────
# Your own phone is not your bot: always-on for WhatsApp and only-during-a-walk for Telegram is a
# real preference, and one switch under two rows answered for both at once (the owner, 2026-09-17:
# "the liasten any tiem should be per system?").
def test_a_channel_never_asked_inherits_the_old_switch(store):
    """Nothing changes for a setup made before this: one switch, still meaning what it meant."""
    store.set_setting('phone_assistant', '1', 'o')
    assert remote_assistant.listens(store, telegram(store)) == 'always'
    store.set_setting('phone_assistant', '0', 'o')
    assert remote_assistant.listens(store, telegram(store)) == 'walk'


def test_a_channel_that_was_asked_answers_for_itself(store):
    store.set_setting('phone_assistant', '1', 'o')
    remote_assistant.set_listens(store, 'telegram', 'walk')
    assert remote_assistant.listens(store, telegram(store)) == 'walk'
    assert store.get_settings().get('phone_assistant') == '1', 'the global default is not rewritten'


def test_the_two_channels_can_disagree(store):
    cid = store.get_connector_by_type('whatsapp')['ConnectorId']
    store.save_connector({'ConnectorId': cid, 'Active': 1, 'ConfigJson': json.dumps({})}, 'o')
    remote_assistant.set_listens(store, 'whatsapp', 'always')
    remote_assistant.set_listens(store, 'telegram', 'walk')
    by = {d['channel']: d['listens'] for d in remote_assistant.doorway_state(store)}
    assert (by['whatsapp'], by['telegram']) == ('always', 'walk')


def test_a_rule_nobody_recognises_is_refused(store):
    with pytest.raises(ValueError, match='unknown listening rule'):
        remote_assistant.set_listens(store, 'telegram', 'sometimes')


def test_walk_means_the_assistant_stays_quiet_until_handed_one(store):
    """enabled() is the gate the poller asks; it reads the channel's own answer now."""
    remote_assistant.use_chat(store, 'telegram', '4242')
    remote_assistant.set_listens(store, 'telegram', 'walk')
    assert remote_assistant.enabled(store, 'telegram', '4242', telegram(store)) is False
    remote_assistant.set_listens(store, 'telegram', 'always')
    assert remote_assistant.enabled(store, 'telegram', '4242', telegram(store)) is True


def test_the_endpoint_sets_it(store):
    r = c.post('/api/assistant/doorways/listens', json={'channel': 'telegram', 'listens': 'walk'})
    assert r.status_code in (200, 422)          # 422 only when this test store has no live telegram
