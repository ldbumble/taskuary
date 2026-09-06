"""P0-FIXTURE behavioral checks for the five reported processing regression shapes."""
import json
from unittest import mock

from taskuary import funnel, terminal

from tests.processing.fixtures import processing_picture


def test_existing_feed_marks_reported_missing_shapes_unread_without_resurrecting_a_read_row():
    picture = processing_picture()
    rows = {row['MessageId']: row for row in picture.store.feed(limit=100, days=30)}

    assert rows[picture.unread_message]['Unread'] == 1
    assert rows[picture.quiet_unread_message]['Unread'] == 1
    assert rows[picture.handled_message]['Unread'] == 0
    assert rows[picture.grouped_messages[0]]['Unread'] == 0  # the owner's context line answered it
    assert {mid for mid, row in rows.items() if row['Unread']} == {
        picture.unread_message, picture.quiet_unread_message,
        picture.grouped_messages[-1], picture.waiting_message}


def test_grouped_fixture_has_one_visible_item_and_keeps_the_latest_line():
    picture = processing_picture()
    items = [item for item in funnel.build(picture.store)['items']
             if item.get('tid') == picture.grouped_task]

    assert len(items) == 1
    assert items[0]['mid'] == picture.grouped_messages[-1]
    assert items[0]['more'] == 1


def test_waiting_agent_fixture_is_visible_as_owner_attention():
    picture = processing_picture()
    with mock.patch.object(terminal, 'live_sessions', return_value=[picture.waiting_session]):
        row = next(row for row in picture.store.feed(limit=100, days=30)
                   if row['MessageId'] == picture.waiting_message)
        item = next(item for item in funnel.build(picture.store)['items']
                    if item.get('tid') == picture.waiting_task)

    assert (row['Working'], row['AgentWaiting'], row['Unread']) == ('fixture-coder', True, 1)
    assert (item['key'], item['lane'], item['agent']) == (
        f'agent:{picture.waiting_task}', 'blocked', 'fixture-coder')


def test_duplicate_turn_fixture_persists_one_identical_assistant_turn():
    picture = processing_picture()
    comments = picture.store.list_comments(picture.duplicate_task)

    assert [row['CommentId'] for row in comments] == [picture.duplicate_comment]
    assert [row['Body'] for row in comments] == ['One durable synthetic response.']


def test_terminal_replay_fixture_renders_visible_lines_without_control_queries():
    picture = processing_picture()
    rendered = terminal.replay_text(type('Replay', (), {
        'cols': 80, 'rows': 12, 'scrollback': lambda self: picture.replay_raw})())

    assert all(line in rendered for line in picture.replay_lines)
    assert '[6n' not in rendered
    assert chr(27) not in rendered[len(terminal.REPLAY_RESET):]


def test_fixture_payload_is_redacted_and_contains_no_credentials():
    picture = processing_picture()
    payload = json.dumps({
        'messages': picture.store.feed(limit=100, days=30),
        'comments': picture.store.list_comments(picture.duplicate_task),
        'waiting': picture.waiting_session,
    }).lower()

    assert '@example.test' in payload
    assert all(secret not in payload for secret in ('bearer ', 'refresh_token', 'client_secret', 'sk-'))
