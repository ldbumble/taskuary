"""A read row stays read when Taskuary only writes something down about it.

The receipt hashed every column, so the app's own later writes - a WhatsApp group's older messages given the group's name, a
report's files filed a second after it was read, a profile renamed under every note it wrote, a workflow tag, the Assistant's
"Next up" under a task - each made a read row a different row, and ~400 came back unread at once (2026-10-29). What someone
SAID is still news. And a receipt written under the old formula still counts, so the upgrade brings nothing back either.
"""
from datetime import datetime

import pytest

from taskuary import agents, messengers, processing_reads
from taskuary.concierge import DISCUSSION_ASSISTANT_TYPE
from taskuary.processing_projection import _row_order
from taskuary.store import SQLiteStore

NOW = datetime.now().replace(microsecond=0).isoformat(sep=' ')
JID = '120000000000000001@g.us'


@pytest.fixture
def db(tmp_path):
    store = SQLiteStore(str(tmp_path / 'news.db'))
    yield store
    store.close()


def activate(db):
    db.reconcile_processing_membership(fixed_now=NOW)
    db.activate_processing_reads(fixed_now=NOW, live_state=[])


def key(db, mid): return 'processing:' + db.resolve_processing_target('legacy_funnel', f'msg:{mid}')['item_id']
def unread(db, mid):
    db.reconcile_processing_membership(fixed_now=NOW)
    return processing_reads.state(db.processing_snapshot(key(db, mid)[11:]), NOW)['unread']


def group_message(db, body='Erin Blake: the vendor call moved to 3pm'):
    return db.add_message(dict(Channel='whatsapp', ConversationId=f'whatsapp:{JID}', ExternalId=f'whatsapp:{JID}:{body[:8]}',
                               SourceName=messengers.GROUP_CHAT, FromName='Erin Blake', BodyText=body, SentAt=NOW, Status='filed'))


def report_task(db):
    tid = db.create_task({'Title': 'Nightly export failed', 'Kind': 'coding'}, 'fixture')
    mid = db.add_message(dict(TaskId=tid, Channel='report', ConversationId='report:1', ExternalId='report:1:' + NOW,
                              SourceName='Nightly check', FromName='Nightly check', BodyText='2 rows failed', SentAt=NOW, Status='filed'))
    return tid, mid


def test_naming_a_group_filing_a_reports_files_and_tagging_are_not_news(db):
    wa, (tid, rep) = group_message(db), report_task(db)
    activate(db)
    for mid in (wa, rep): db.set_funnel_state(key(db, mid), 'done')
    assert not unread(db, wa) and not unread(db, rep)
    messengers._RENAMED.discard(JID)
    messengers._group_named(db, JID, 'Northwind ops')                      # the group's own name reaches its older rows
    assert db.get_message(wa)['SourceName'] == 'Northwind ops'
    db.add_attachment(dict(MessageId=rep, ExternalId='report:1:xlsx', Name='check.xlsx', ContentType='application/xlsx', Size=10, Path='1/check.xlsx'))
    db._exec("UPDATE message SET MailMetaJson=json_set(IFNULL(MailMetaJson,'{}'),'$.unsub.done',?) WHERE MessageId=?", (NOW, rep))
    db.tag_task(tid, 'interrupted')
    db.add_comment(tid, 'Taskuary', DISCUSSION_ASSISTANT_TYPE, 'Next up: this task.')
    assert not unread(db, wa), 'naming the group is not a new message'
    assert not unread(db, rep), 'the report, its files, its tags and the Assistant pointing at it are what was already read'


def test_what_someone_said_is_still_news(db):
    wa, (tid, rep) = group_message(db), report_task(db)
    activate(db)
    for mid in (wa, rep): db.set_funnel_state(key(db, mid), 'done')
    db.update_message_body(wa, 'Erin Blake: the vendor call moved to 4pm')            # a voice note transcribed: new words
    db.add_comment(tid, 'coding', 'agent', 'Found it: the export skips divested sites.')
    assert unread(db, wa) and unread(db, rep)


def _old_message(row, attachments=()):
    """The fingerprint a message was read under through 0.3.9.68: every column, every attachment."""
    keep = ('ExternalId', 'ConversationId', 'Channel', 'SourceName', 'Subject', 'FromName', 'FromEmail', 'SentAt', 'BodyText',
            'SourceLink', 'Direction', 'RecipientsJson', 'MailMetaJson')
    return {**{k: row.get(k) for k in keep}, 'attachments': list(attachments)}


def _record(db, kind, lid, substance):
    with db.lock:
        cur = db.cx.cursor()
        processing_reads.record(cur, [dict(entity_kind=kind, local_id=str(lid), fingerprint=processing_reads.fingerprint(substance))],
                                version=processing_reads.active_version(cur), at=NOW, by='owner', origin='explicit_done')
        db.cx.commit()


def test_a_receipt_read_before_the_rewrite_still_counts(db):
    """Receipts on disk were hashed over the group's placeholder name, before a report's files, and over the profile's old
    name (with the notes in the order that name sorted them). Each is still the row the owner read."""
    wa, (tid, rep) = group_message(db), report_task(db)
    for body in ('Found it: the export skips divested sites.', 'Asked Gail Moreno for the site list.'):
        db.add_comment(tid, 'coder', 'agent', body)
    activate(db)
    assert unread(db, wa) and unread(db, rep)
    _record(db, 'message', wa, _old_message(db.get_message(wa)))
    _record(db, 'message', rep, _old_message(db.get_message(rep)))
    notes = _row_order([dict(r) for r in db.cx.execute('SELECT * FROM comment WHERE TaskId=?', (tid,))])
    t = db.get_task(tid)
    _record(db, 'task', tid, {**{k: t.get(k) for k in ('Title', 'Summary', 'Kind', 'Tags')}, 'checklist': None, 'artifacts': [],
                              'comments': [{k: c[k] for k in ('CommentId', 'Actor', 'ActorType', 'Body')} for c in notes]})
    assert not unread(db, wa) and not unread(db, rep)
    messengers._RENAMED.discard(JID)
    messengers._group_named(db, JID, 'Northwind ops')
    db.add_attachment(dict(MessageId=rep, ExternalId='report:1:chart', Name='check.svg', ContentType='image/svg+xml', Size=10, Path='1/check.svg'))
    agents._retire_old_name(db)                                           # every note the profile wrote, relabelled
    assert {c['Actor'] for c in db.list_comments(tid)} == {'coding'}
    assert not unread(db, wa) and not unread(db, rep)
