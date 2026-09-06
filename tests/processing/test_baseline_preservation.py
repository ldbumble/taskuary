"""P0-FIXTURE frozen 2689679 database baseline for future migration/reopen gates."""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from taskuary.store import SQLiteStore


# Relevant tables copied from the pre-additive portion of SCHEMA at checkpoint 2689679. This is
# test-owned SQL so later schema edits must migrate this fixed old picture rather than redefining it.
LEGACY_SCHEMA_2689679 = """
CREATE TABLE task (TaskId INTEGER PRIMARY KEY, Title TEXT, Summary TEXT,
  Kind TEXT DEFAULT 'general', Status TEXT DEFAULT 'open', Priority TEXT DEFAULT 'normal',
  Assignee TEXT, Source TEXT DEFAULT 'manual', SourceRef TEXT, Tags TEXT,
  CreatedBy TEXT, CreatedAt TEXT, UpdatedBy TEXT, UpdatedAt TEXT, ClosedAt TEXT);
CREATE TABLE message (MessageId INTEGER PRIMARY KEY, TaskId INTEGER, ExternalId TEXT,
  ConversationId TEXT, Channel TEXT, SourceName TEXT, Subject TEXT, FromName TEXT, FromEmail TEXT,
  SentAt TEXT, BodyText TEXT, SourceLink TEXT, Status TEXT DEFAULT 'routed', CreatedAt TEXT);
CREATE TABLE attachment (AttachmentId INTEGER PRIMARY KEY, MessageId INTEGER, ExternalId TEXT,
  Name TEXT, ContentType TEXT, Size INTEGER, ContentId TEXT, Inline INTEGER DEFAULT 0, Path TEXT, CreatedAt TEXT);
CREATE TABLE transcript (TranscriptId INTEGER PRIMARY KEY, TaskId INTEGER, Sid TEXT,
  Agent TEXT, Cwd TEXT, Text TEXT, CreatedAt TEXT);
CREATE TABLE route (RouteId INTEGER PRIMARY KEY, MessageId INTEGER, TaskId INTEGER,
  Decision TEXT, Score REAL, Reason TEXT, CandidatesJson TEXT, RoutedBy TEXT, CreatedAt TEXT);
CREATE TABLE comment (CommentId INTEGER PRIMARY KEY, TaskId INTEGER, Actor TEXT,
  ActorType TEXT, Body TEXT, CreatedAt TEXT);
CREATE TABLE run (RunId INTEGER PRIMARY KEY, TaskId INTEGER, AgentName TEXT,
  Status TEXT DEFAULT 'running', Instruction TEXT, TraceJson TEXT, Result TEXT, LastError TEXT,
  SessionId TEXT, DiffText TEXT, DispatchedBy TEXT, StartedAt TEXT, UpdatedAt TEXT, FinishedAt TEXT);
CREATE TABLE setting (Name TEXT PRIMARY KEY, Value TEXT, Description TEXT, UpdatedBy TEXT);
CREATE TABLE doc (Name TEXT PRIMARY KEY, Content TEXT, UpdatedBy TEXT, UpdatedAt TEXT);
CREATE TABLE funnel_state (Key TEXT PRIMARY KEY, Status TEXT, Until TEXT, Note TEXT, By TEXT, At TEXT);
"""


def _legacy_picture(path: Path):
    now = datetime.now().isoformat(sep=' ', timespec='seconds')
    later = (datetime.now() + timedelta(days=3)).isoformat(sep=' ', timespec='seconds')
    attachment_file = path.parent / 'synthetic-attachment.txt'
    attachment_file.write_text('synthetic attachment bytes', encoding='utf-8')
    cx = sqlite3.connect(path)
    try:
        cx.executescript(LEGACY_SCHEMA_2689679)
        cx.executemany('INSERT INTO setting (Name,Value,UpdatedBy) VALUES (?,?,?)', (
            ('feed_days', '37', 'fixture-owner'),
            ('fixture_owner_preference', 'keep this exact value', 'fixture-owner')))
        cx.executemany('INSERT INTO doc (Name,Content,UpdatedBy,UpdatedAt) VALUES (?,?,?,?)', (
            ('soul', '# Synthetic owner document\nKeep this custom instruction.', 'fixture-owner', now),
            ('counsel', '# Synthetic COUNSEL\nKeep the owner\'s exact assistant policy.', 'fixture-owner', now),
            ('quarter-close', '# Custom synthetic procedure\nNever replace this file.', 'fixture-owner', now)))
        cx.execute('INSERT INTO task VALUES (41,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('Preserve the synthetic historical task', 'Owner-edited baseline summary', 'coding', 'open', 'high',
                    'agent:fixture-coder', 'email', 'fixture:legacy', 'owner:custom', 'fixture-owner', now,
                    'fixture-owner', now, None))
        messages = (
            (71, 'fixture:legacy:surfaced', 'Synthetic historical request', 'Keep the message body and its history across migrations.'),
            (72, 'fixture:legacy:done', 'Synthetic completed read state', 'Keep the done state.'),
            (73, 'fixture:legacy:later', 'Synthetic deferred read state', 'Keep the defer state.'),
            (74, 'fixture:legacy:skip', 'Synthetic skipped read state', 'Keep the skip state.'),
        )
        for mid, external, subject, body in messages:
            cx.execute('''INSERT INTO message
                (MessageId,TaskId,ExternalId,ConversationId,Channel,SourceName,Subject,FromName,FromEmail,
                 SentAt,BodyText,SourceLink,Status,CreatedAt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (mid, 41, external, f'mail:legacy:{mid}', 'email', 'fixture-inbox@example.test', subject,
                 'Morgan Example', 'morgan@example.test', now, body, f'https://example.test/messages/{mid}', 'routed', now))
        cx.execute('''INSERT INTO attachment VALUES
            (91,71,'fixture:legacy:attachment','redacted-note.txt','text/plain',?,NULL,0,?,?)''',
            (attachment_file.stat().st_size, str(attachment_file), now))
        cx.execute("INSERT INTO route VALUES (101,71,41,'create',.91,'synthetic owner-approved route','[]','fixture-router',?)", (now,))
        cx.executemany('INSERT INTO comment VALUES (?,?,?,?,?,?)', (
            (111, 41, 'fixture-owner', 'human', 'Preserve this owner history turn.', now),
            (112, 41, 'assistant', 'assistant_agent', 'Preserve this assistant history turn.', now)))
        cx.execute('''INSERT INTO run VALUES
            (121,41,'fixture-coder','done','Use only synthetic inputs.','[]','Synthetic run completed.',NULL,
             'fixture-provider-session','synthetic diff','fixture-owner',?,?,?)''', (now, now, now))
        cx.execute("INSERT INTO transcript VALUES (131,41,'fixture-session','fixture-coder',?,'synthetic terminal history',?)",
                   (str(path.parent), now))
        cx.executemany('INSERT INTO funnel_state VALUES (?,?,?,?,?,?)', (
            ('msg:71', 'surfaced', None, 'owner saw this exact item', 'fixture-owner', now),
            ('msg:72', 'done', None, 'owner completed this exact item', 'fixture-owner', now),
            ('msg:73', 'later', later, 'owner deferred this exact item', 'fixture-owner', now),
            ('msg:74', 'skip', later, 'owner skipped this exact item', 'fixture-owner', now)))
        cx.commit()
    finally:
        cx.close()
    return {'attachment_file': attachment_file, 'at': now, 'later': later}


def _assert_preserved(reopened: SQLiteStore, expected):
    settings = reopened.get_settings()
    assert settings['feed_days'] == '37'
    assert settings['fixture_owner_preference'] == 'keep this exact value'
    assert (reopened.get_doc('soul'), reopened.doc_owner('soul')) == (
        '# Synthetic owner document\nKeep this custom instruction.', 'fixture-owner')
    assert (reopened.get_doc('counsel'), reopened.doc_owner('counsel')) == (
        "# Synthetic COUNSEL\nKeep the owner's exact assistant policy.", 'fixture-owner')
    assert (reopened.get_doc('quarter-close'), reopened.doc_owner('quarter-close')) == (
        '# Custom synthetic procedure\nNever replace this file.', 'fixture-owner')

    detail = reopened.task_detail(41)
    for key, value in {'TaskId': 41, 'Summary': 'Owner-edited baseline summary', 'Priority': 'high',
                       'Assignee': 'agent:fixture-coder', 'Tags': 'owner:custom'}.items():
        assert detail['task'][key] == value
    assert [(row['MessageId'], row['BodyText']) for row in detail['messages']] == [
        (71, 'Keep the message body and its history across migrations.'),
        (72, 'Keep the done state.'), (73, 'Keep the defer state.'), (74, 'Keep the skip state.')]
    assert [(row['AttachmentId'], row['Name'], row['Path']) for row in detail['attachments']] == [
        (91, 'redacted-note.txt', str(expected['attachment_file']))]
    assert [(row['RouteId'], row['Reason']) for row in detail['routes']] == [(101, 'synthetic owner-approved route')]
    assert [(row['CommentId'], row['Body']) for row in detail['comments']] == [
        (111, 'Preserve this owner history turn.'), (112, 'Preserve this assistant history turn.')]
    assert [(row['RunId'], row['Result'], row['SessionId']) for row in detail['runs']] == [
        (121, 'Synthetic run completed.', 'fixture-provider-session')]
    transcript = reopened.last_transcript(41)
    assert (transcript['TranscriptId'], transcript['Text']) == (131, 'synthetic terminal history')
    assert expected['attachment_file'].read_text(encoding='utf-8') == 'synthetic attachment bytes'

    states = reopened.funnel_states()
    got = {key: (states[key]['Status'], states[key]['Until'], states[key]['Note'], states[key]['By'], states[key]['At'])
           for key in ('msg:71', 'msg:72', 'msg:73', 'msg:74')}
    assert got == {
        'msg:71': ('surfaced', None, 'owner saw this exact item', 'fixture-owner', expected['at']),
        'msg:72': ('done', None, 'owner completed this exact item', 'fixture-owner', expected['at']),
        'msg:73': ('later', expected['later'], 'owner deferred this exact item', 'fixture-owner', expected['at']),
        'msg:74': ('skip', expected['later'], 'owner skipped this exact item', 'fixture-owner', expected['at']),
    }
    rows = {row['MessageId']: row for row in reopened.feed(limit=100, days=37)}
    assert {mid: rows[mid]['Unread'] for mid in (71, 72, 73, 74)} == {71: 0, 72: 0, 73: 0, 74: 0}


def test_frozen_2689679_database_preserves_owner_state_and_history_on_migration(tmp_path):
    db = tmp_path / 'legacy-taskuary.db'
    expected = _legacy_picture(db)
    reopened = SQLiteStore(str(db))
    try: _assert_preserved(reopened, expected)
    finally: reopened.cx.close()


def test_migration_and_repeated_reopen_do_not_duplicate_or_rewrite_history(tmp_path):
    db = tmp_path / 'legacy-taskuary.db'
    expected = _legacy_picture(db)
    for _ in range(2):
        reopened = SQLiteStore(str(db))
        try: _assert_preserved(reopened, expected)
        finally: reopened.cx.close()
