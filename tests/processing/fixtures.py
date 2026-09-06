"""Redacted Phase 0 pictures of the processing failures reported by the owner.

The rows use only reserved ``.example`` identities and local in-memory stores.  They describe the
pre-migration API shape so later phases can evolve storage while proving the same visible facts.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from taskuary.store import MemoryStore


def _ago(minutes: int) -> str:
    return (datetime.now() - timedelta(minutes=minutes)).isoformat(sep=' ', timespec='seconds')


@dataclass(frozen=True)
class ProcessingPicture:
    store: MemoryStore
    unread_message: int
    quiet_unread_message: int
    handled_message: int
    grouped_task: int
    grouped_messages: tuple[int, int]
    waiting_task: int
    waiting_message: int
    waiting_session: dict
    duplicate_task: int
    duplicate_comment: int
    replay_raw: str
    replay_lines: tuple[str, ...]


def processing_picture() -> ProcessingPicture:
    """Seed missing-Unread, grouping, wait, duplicate-turn, and terminal-replay cases."""
    store = MemoryStore()
    store.set_setting('feed_days', '30', 'fixture')
    store.set_setting('funnel_hours', '72', 'fixture')

    reply = store.create_task({'Title': 'Confirm the synthetic renewal', 'Kind': 'reply'}, 'fixture')
    unread = store.add_message({
        'TaskId': reply, 'ExternalId': 'fixture:unread:ask', 'ConversationId': 'mail:renewal',
        'Channel': 'email', 'SourceName': 'fixture-inbox@example.test',
        'Subject': 'Can you confirm the renewal date?', 'FromName': 'Avery Example',
        'FromEmail': 'avery@example.test', 'SentAt': _ago(9),
        'BodyText': 'Please confirm whether the redacted renewal date still works.', 'Status': 'routed'})

    quiet_unread = store.add_message({
        'ExternalId': 'fixture:unread:quiet', 'ConversationId': 'mail:release-notes',
        'Channel': 'email', 'SourceName': 'fixture-inbox@example.test',
        'Subject': 'Synthetic product release notes', 'FromName': 'Example Product',
        'FromEmail': 'updates@example.test', 'SentAt': _ago(14),
        'BodyText': 'A synthetic informational message with no action requested.', 'Status': 'filed'})

    handled = store.add_message({
        'ExternalId': 'fixture:read:handled', 'ConversationId': 'mail:handled',
        'Channel': 'email', 'SourceName': 'fixture-inbox@example.test',
        'Subject': 'Synthetic item already read', 'FromName': 'Casey Example',
        'FromEmail': 'casey@example.test', 'SentAt': _ago(18),
        'BodyText': 'This item was explicitly surfaced before the fixture reopened.', 'Status': 'filed'})
    store.set_funnel_state(f'msg:{handled}', 'surfaced', 'fixture-owner')

    grouped_task = store.create_task({'Title': 'Repair the synthetic export', 'Kind': 'coding'}, 'fixture')
    grouped_first = store.add_message({
        'TaskId': grouped_task, 'ExternalId': 'fixture:group:1', 'ConversationId': 'teams:fixture-export',
        'Channel': 'teams', 'SourceName': 'fixture-team@example.test', 'Subject': 'Synthetic export thread',
        'FromName': 'Devon Example', 'FromEmail': 'devon@example.test', 'SentAt': _ago(8),
        'BodyText': 'The synthetic export omitted its final row.', 'Status': 'routed'})
    store.add_message({
        'TaskId': grouped_task, 'ExternalId': 'fixture:group:owner', 'ConversationId': 'teams:fixture-export',
        'Channel': 'teams', 'SourceName': 'fixture-team@example.test', 'Subject': 'Synthetic export thread',
        'FromName': 'Fixture Owner', 'FromEmail': 'owner@example.test', 'SentAt': _ago(6),
        'BodyText': 'I can reproduce it with the redacted sample.', 'Status': 'context', 'Direction': 'out'})
    grouped_last = store.add_message({
        'TaskId': grouped_task, 'ExternalId': 'fixture:group:2', 'ConversationId': 'teams:fixture-export',
        'Channel': 'teams', 'SourceName': 'fixture-team@example.test', 'Subject': 'Synthetic export thread',
        'FromName': 'Devon Example', 'FromEmail': 'devon@example.test', 'SentAt': _ago(4),
        'BodyText': 'The duplicate retry also appeared in the synthetic log.', 'Status': 'routed'})

    waiting_task = store.create_task({'Title': 'Synthetic agent needs an answer', 'Kind': 'coding'}, 'fixture')
    waiting_message = store.add_message({
        'TaskId': waiting_task, 'ExternalId': 'fixture:wait:1', 'ConversationId': 'mail:agent-wait',
        'Channel': 'email', 'SourceName': 'fixture-inbox@example.test', 'Subject': 'Choose the fixture format',
        'FromName': 'Robin Example', 'FromEmail': 'robin@example.test', 'SentAt': _ago(2),
        'BodyText': 'Should the synthetic export use CSV or JSON?', 'Status': 'routed'})
    waiting_session = {'sid': 'fixture-session', 'taskId': waiting_task, 'agent': 'fixture-coder',
                       'label': 'fixture-coder', 'alive': True, 'waiting': True}

    duplicate_task = store.create_task({'Title': 'Synthetic assistant conversation', 'Kind': 'general'}, 'fixture')
    duplicate_comment = store.add_comment_once(
        duplicate_task, 'assistant', 'assistant_agent', 'One durable synthetic response.')
    assert duplicate_comment == store.add_comment_once(
        duplicate_task, 'assistant', 'assistant_agent', 'One durable synthetic response.')

    esc = chr(27)
    replay_raw = esc + '[2J' + esc + '[1;1Hfixture worker started' + esc + '[3;1Hwaiting for synthetic approval' + esc + '[6n'
    return ProcessingPicture(
        store=store, unread_message=unread, quiet_unread_message=quiet_unread,
        handled_message=handled, grouped_task=grouped_task,
        grouped_messages=(grouped_first, grouped_last), waiting_task=waiting_task,
        waiting_message=waiting_message, waiting_session=waiting_session,
        duplicate_task=duplicate_task, duplicate_comment=duplicate_comment,
        replay_raw=replay_raw, replay_lines=('fixture worker started', 'waiting for synthetic approval'))
