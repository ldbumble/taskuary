"""A held step's row says Approve, and offers no Redraft (the agent walk, 2026-11-09).

The owner made a task by hand - no mail on it - and its agent's `git push` was held for their yes. With no message of its own, the task's
row wears the held step as its card. The chips under the line said Approve; the row said Send, with Redraft beside it - a reply's two
buttons, over a command nobody drafted and no AI may write again. What the Assistant may light is the row's buttons, so it could light
"Redraft" over a push. Invented people."""
from datetime import datetime
from unittest import mock

import pytest

from taskuary import buttons, concierge, funnel, proposals
from taskuary.store import SQLiteStore

STAMP = datetime.now().replace(microsecond=0).isoformat(sep=' ')


@pytest.fixture
def store(tmp_path):
    s = SQLiteStore(str(tmp_path / 'held.db')); s.set_setting('funnel_hours', '72', 'fixture')
    yield s
    s.close()


def row(s, tid):
    s.reconcile_processing_membership(fixed_now=STAMP); s.activate_processing_reads(fixed_now=STAMP, live_state=[])
    funnel.invalidate(); funnel.forget_states()
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        return next(i for i in funnel.build(s, live_state=[], keep_surfaced=True)['items'] if i.get('tid') == tid)


def test_the_row_of_a_held_step_says_approve_and_has_no_redraft(store):
    tid = store.create_task({'Title': 'Fix the ledger typo', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
    held = proposals.queue(store, tid, {'action': 'shell_act', 'sid': 's1', 'turn': 0, 'command': 'git push origin main', 'shell': 'Bash', 'cwd': '',
                                        'what': 'push to origin', 'why': 'it leaves this computer', 'where': ''}, 'agent')
    r = row(store, tid)
    assert (r['kind'], r['rid']) == ('action', held['reviewId']), 'the task has no mail: its held step is its card'
    drawn = {b['verb']: b['label'] for b in concierge.row_buttons(store, r)}
    assert drawn['approve'] == buttons.label('approve', 'action') == next(c['label'] for c in concierge.chips_for(store, r) if c.get('verb') == 'approve')
    assert 'redraft' not in drawn and 'no draft' in concierge.cannot(r, 'redraft', store)


def test_a_drafted_reply_keeps_send_and_redraft(store):
    tid = store.create_task({'Title': 'Seats for Erin', 'Kind': 'general', 'Status': 'in_progress'}, 'triage')
    mid = store.add_message({'TaskId': tid, 'ExternalId': 'x:seats', 'ConversationId': 'c:seats', 'Channel': 'email', 'Subject': 'Seats',
                             'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': STAMP, 'BodyText': 'How many seats?', 'Status': 'routed'})
    store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Forty seats.'})
    r = row(store, tid)
    with mock.patch('taskuary.capabilities.can_send_draft', return_value=True):
        drawn = {b['verb']: b['label'] for b in concierge.row_buttons(store, r)}
    assert r['kind'] == 'review' and (drawn['approve'], drawn['redraft']) == (buttons.label('approve'), buttons.label('redraft'))
