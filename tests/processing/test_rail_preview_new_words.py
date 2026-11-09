"""The LEFT list's preview line reads a mail as the chat's arrival card does (general.mail_row): the sender's NEW words first.

The chat card lost the external-sender banner (2026-11-09) while the rail row beside it still read "<sender>: This message came from
out..." - its preview only left out what triage NAMED, and a message triage named nothing on kept the stamp. The rail counts the stamp
the same way the chat does - a lead paragraph that opens the mail of several different senders - but over its own snapshot, so the
row stays a pure function of what it was built from. No phrase list (the owner, 2026-10-28).

The shape: three outside senders' mail opens with one stamped paragraph; one of them writes on top of a quoted chain."""
from datetime import datetime

import pytest

from taskuary import processing_all
from taskuary.store import SQLiteStore

NOW = datetime.now().replace(microsecond=0)
STAMP = NOW.isoformat(sep=' ')
BANNER = 'This message came from outside Northwind. Think twice before opening links or files you did not expect.'
QUOTED = 'On Mon, Nov 9, 2026 at 9:02 AM Erin Blake <erin@northwind.example> wrote:\n> Can you send the October invoice?\n> Erin'


@pytest.fixture
def db(tmp_path):
    store = SQLiteStore(str(tmp_path / 'railpreview.db'))
    yield store
    store.close()


def mail(db, who, addr, body, own=None):
    mid = db.add_message({'ExternalId': f'x:{addr}', 'ConversationId': f'c:{addr}', 'Channel': 'email', 'Subject': f'From {who}',
                          'FromName': who, 'FromEmail': addr, 'SentAt': STAMP, 'BodyText': body, 'OwnText': own, 'Status': 'routed'})
    db.reconcile_processing_membership(fixed_now=STAMP)
    return mid


def preview(db, mid):
    snap = db.processing_inventory_snapshot(fixed_now=NOW.isoformat(), live_state=[], display_only=True, history_days=14)
    out, _c, _n = processing_all.compact_inventory(snap, processing_all.normalize_query(None, None, 14), include_excluded=True, degraded_ok=True)
    return next(r['row'] for r in out if r['row'].get('MessageId') == mid)['Preview']


def others(db):
    for who, a in [('Ray Colton', 'ray@vendor.example'), ('Omar Keller', 'omar@supplies.example')]:
        mail(db, who, a, f'{BANNER}\n\nA note of my own about another thing entirely, {who}.')


def test_the_rail_preview_of_a_bannered_outside_mail_starts_at_the_new_words(db):
    others(db)
    mid = mail(db, 'Gail Moreno', 'gail@vendor.example', f'{BANNER}\n\nAttached is the October invoice, due on the 30th.\n\n{QUOTED}')
    p = preview(db, mid)
    assert p.startswith('Attached is the October invoice'), p
    assert 'outside Northwind' not in p and 'wrote:' not in p


def test_the_mailbox_own_cut_is_what_the_rail_reads(db):
    others(db)
    mid = mail(db, 'Gail Moreno', 'gail@vendor.example', f'{BANNER}\n\nSending it today.\n\n{QUOTED}', own=f'{BANNER}\n\nSending it today.')
    assert preview(db, mid) == 'Sending it today.'


def test_a_lead_two_senders_share_is_still_the_message(db):
    """The stamp is counted, never assumed: two senders opening alike is not enough, and the row reads as it came."""
    mail(db, 'Ray Colton', 'ray@vendor.example', f'{BANNER}\n\nA note of my own.')
    mid = mail(db, 'Gail Moreno', 'gail@vendor.example', f'{BANNER}\n\nSending it today.')
    assert preview(db, mid).startswith(BANNER)


def test_a_message_that_is_only_the_banner_is_never_cut_to_nothing(db):
    others(db)
    assert preview(db, mail(db, 'Gail Moreno', 'gail@vendor.example', BANNER)) == BANNER


def test_the_count_is_the_snapshots_so_a_new_sender_changes_the_row():
    """The remembered preview is keyed on the leads it was cut with: a stamp counted later reaches a row built earlier."""
    def item(mid, addr, body): return {'view': {'messages': [{'MessageId': mid, 'FromEmail': addr, 'BodyText': body}]}}
    body = f'{BANNER}\n\nSending it today.'
    two = [item(1, 'a@vendor.example', body), item(2, 'b@supplies.example', f'{BANNER}\n\nOther.')]
    assert processing_all._preview(body, 400, leads=processing_all.stamped_leads(two)).startswith(BANNER)
    three = [*two, item(3, 'c@parts.example', f'{BANNER}\n\nMore.')]
    assert processing_all._preview(body, 400, leads=processing_all.stamped_leads(three)) == 'Sending it today.'
