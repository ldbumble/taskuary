"""An Advisor idea read while its triage had failed stays read when the retry writes its verdict.

The read receipt fingerprints the idea, ActionJson and all. Only the failure's own bookkeeping (priority,
pending, error) was kept out of it, so the retry that wrote intent, kind, why, when and the linked task made
it a different idea: one the owner had already read came back unread with nothing new in it to read.
"""
from datetime import datetime
from unittest import mock

import pytest

from taskuary import assistant, funnel
from taskuary.store import SQLiteStore

STAMP = datetime.now().replace(microsecond=0).isoformat(sep=' ')
TEXT = 'Three vendor renewals land in the same week - put them on one calendar?'


@pytest.fixture
def db(tmp_path):
    store = SQLiteStore(str(tmp_path / 'idea.db'))
    store.reconcile_processing_membership(fixed_now=STAMP)
    store.activate_processing_reads(fixed_now=STAMP, live_state=[])
    funnel.invalidate(); funnel.forget_states()
    yield store
    store.cx.close()


def unread(db, iid):
    db.reconcile_processing_membership(fixed_now=STAMP)
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        funnel.invalidate()
        items = funnel.build(db, live_state=[])['items']
    return [i for i in items if str(i.get('idea')) == str(iid) and i.get('unread')]


def test_a_retried_verdict_does_not_bring_a_read_idea_back(db):
    i = db.upsert_idea({'key': 'idea:renewals', 'kind': 'idea', 'text': TEXT, 'sig': 'a',
                        'action': {'triage': {'error': 'the model failed', 'sig': 'a', 'at': STAMP}}}, STAMP)
    shown = unread(db, i['IdeaId'])
    assert shown, 'the idea never reached the rail, so this proves nothing'
    funnel.settle(db, shown[0]['key'], 'surfaced', 'owner', read=True)      # Next: read, and still open
    assert not unread(db, i['IdeaId'])
    verdict = {'intent': 'fyi', 'kind': 'general', 'why': 'nothing to do'}
    with mock.patch('taskuary.ingest.judge', return_value=(verdict, None)):
        assert assistant.triage_ideas(db, [db.get_idea(i['IdeaId'])], object()) == [i['IdeaId']]
    assert (db.get_idea(i['IdeaId'])['ActionJson'] or '').count('"intent": "fyi"'), 'the retry wrote no verdict'
    assert not unread(db, i['IdeaId']), 'the verdict is triage bookkeeping, not something new to read'


def test_new_words_on_a_read_idea_are_still_news(db):
    """The other side: a candidate the hub found reopens with new facts, and those are news."""
    i = db.upsert_idea({'key': 'followup:renewals', 'kind': 'idea', 'text': TEXT, 'sig': 'a', 'action': {}}, STAMP)
    funnel.settle(db, unread(db, i['IdeaId'])[0]['key'], 'surfaced', 'owner', read=True)
    assert not unread(db, i['IdeaId'])
    db.upsert_idea({'key': 'followup:renewals', 'kind': 'idea', 'text': TEXT + ' One of them auto-renews tomorrow.', 'sig': 'b', 'action': {}}, STAMP)
    assert unread(db, i['IdeaId'])


def test_a_receipt_written_before_the_change_still_counts(db):
    """Receipts already on disk hashed the verdict in. The idea they were for must not come back unread for the upgrade."""
    from taskuary import processing_reads
    tri = {'intent': 'fyi', 'kind': 'general', 'why': 'nothing to do', 'sig': 'a', 'at': STAMP, 'linked_task': None, 'error': None}
    i = db.upsert_idea({'key': 'idea:renewals', 'kind': 'idea', 'text': TEXT, 'sig': 'a', 'action': {'triage': tri}}, STAMP)
    assert unread(db, i['IdeaId'])
    row = db.get_idea(i['IdeaId'])
    old = processing_reads.fingerprint({'Text': row['Text'], 'Kind': row['Kind'], 'Sig': row['Sig'],
                                        'ActionJson': {'triage': {k: v for k, v in tri.items() if k != 'error'}}})
    with db.lock:
        cur = db.cx.cursor()
        processing_reads.record(cur, [dict(entity_kind='idea', local_id=str(i['IdeaId']), fingerprint=old)],
                                version=processing_reads.active_version(cur), at=STAMP, by='owner', origin='explicit_done')
        db.cx.commit()
    assert not unread(db, i['IdeaId'])
