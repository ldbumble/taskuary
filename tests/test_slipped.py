"""The slipped lane (spec 2026-10-12, 'What was not followed up'): a thread or a step gone quiet past THAT person's day."""
import json
from datetime import datetime, timedelta
import pytest
from taskuary import assistant, funnel, outcomes, processing_unread, terminal
from taskuary.store import MemoryStore

def ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
RAY = 'ray@northwind.example'

@pytest.fixture
def s(monkeypatch):
    s = MemoryStore(); s.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    s.reconcile_processing_membership(); s.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=[])
    funnel.invalidate(); yield s; funnel.invalidate(); s.cx.close()

def rail(s):
    s.reconcile_processing_membership(); funnel.invalidate()
    return processing_unread.build(s, live_state=[], include_read=True)['items']

def person_step(s, days_past_due, who=RAY):
    return s.create_task({'Title': 'Schema sign-off', 'Status': 'waiting', 'Assignee': f'person:{who}',
                          'DueAt': (datetime.now() - timedelta(days=days_past_due)).strftime('%Y-%m-%d')}, 'owner')

def followup_idea(s, days_ago, who=RAY, away=False):
    t = s.create_task({'Title': 'Budget'}, 'owner')
    mid = s.add_message({'ConversationId': f'c{t}', 'Channel': 'email', 'Subject': 'Budget', 'FromEmail': who, 'FromName': 'Ray Colton', 'SentAt': ago(days=days_ago + 1), 'BodyText': 'q', 'Status': 'filed', 'TaskId': t})
    row = s.upsert_idea({'key': f'followup:c{t}', 'kind': 'followup', 'text': f'No answer from Ray in {days_ago} days on "Budget" - follow up?', 'sig': 'x',
                         'action': {'type': 'followup', 'mid': mid, 'tid': t, 'who_email': who, 'asked_at': ago(days=days_ago), 'away': away}}, ago(hours=1))
    return row['IdeaId'], t


def test_a_step_past_the_persons_day_is_slipped_and_counted(s):
    t = person_step(s, 7)
    card = next(c for c in rail(s) if c.get('tid') == t)
    assert (card['lane'], card['who_email'], card['late_days']) == ('forgotten', RAY, 2)       # default day 5: two days late
    assert 'quiet' in card['why'] and card['actionable']
    assert funnel.LANE_COUNTED['forgotten'] == 'slipped'
    assert funnel.level_of(card) == 'task'                                                 # inside On you, never an fyi

def test_a_step_inside_the_persons_day_is_still_theirs(s):
    t = person_step(s, 2)
    assert next(c for c in rail(s) if c.get('tid') == t)['lane'] == 'theirs'

def test_the_persons_own_day_comes_from_the_ledger(s):
    for k in range(3):
        t = s.create_task({'Title': f'x{k}'}, 'owner')
        i = outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': f'z{k}', 'mid': 1, 'verb': 'approve', 'who': RAY, 'cc': [], 'chase': False, 'answer_days': 1.0}, at=ago(days=9))
        outcomes.settle(s, i, 'answered', 'settled')
    t = person_step(s, 3)                                                                   # late for Ray after 2 days
    assert next(c for c in rail(s) if c.get('tid') == t)['lane'] == 'forgotten'

def test_a_quiet_thread_past_the_day_is_slipped(s):
    iid, _ = followup_idea(s, 6)
    card = next(c for c in rail(s) if c.get('idea') == iid)
    assert card['lane'] == 'forgotten' and card['late_days'] == 1 and funnel.level_of(card) == 'task'

def test_someone_away_never_slips(s):
    iid, t = followup_idea(s, 20, away=True)
    card = next(c for c in rail(s) if c.get('tid') == t)                                     # folded into its thread's item, as before
    assert card['lane'] != 'forgotten' and not card.get('late_days')

def test_followups_carry_the_address_and_the_day_asked(s):
    t = s.create_task({'Title': 'Budget'}, 'owner')
    s.add_message({'ConversationId': 'c2', 'Channel': 'email', 'Subject': 'Budget', 'FromEmail': RAY, 'FromName': 'Ray Colton', 'SentAt': ago(days=5), 'BodyText': 'q', 'Status': 'filed', 'TaskId': t})
    mid = s.add_message({'ConversationId': 'c2', 'Channel': 'email', 'Subject': 'Re: Budget', 'FromEmail': 'alex@northwind.example', 'SentAt': ago(days=4), 'BodyText': 'Can you send it?', 'Status': 'context', 'TaskId': t})
    s.put_sent_verdict(mid, 'c2', True, False, None, None, 'test')
    c = next(x for x in assistant.followups(s, 24, ('followup',)) if x['kind'] == 'followup')
    assert c['action']['who_email'] == RAY and c['action']['asked_at'][:10] == ago(days=4)[:10] and c['action']['away'] is False
