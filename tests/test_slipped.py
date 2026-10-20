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


# ── the four answers (build step 4, Task 4): Chase, Let it go, They answered elsewhere, Remind me ──────────────────────
from unittest import mock
from taskuary import concierge, server
from fastapi.testclient import TestClient

def run(s, kind, card, text=None):
    """Propose and execute one operation the way the card does, through the server's one handler."""
    target = card.get('tid') or card.get('idea') or card.get('mid') or 0
    with mock.patch.object(server, 'store', s):
        c = TestClient(server.app)
        op = c.post('/api/operations', json={'kind': kind, 'target': target, 'params': {'key': card['key'], **({'text': text} if text else {})}}).json()
        assert 'id' in op, op
        return c.post(f"/api/operations/{op['id']}/execute", json={'version': op['version']})

def test_a_slipped_card_offers_the_four_answers(s):
    t = person_step(s, 7)
    card = next(c for c in rail(s) if c.get('tid') == t)
    assert [c['verb'] for c in concierge.chips_for(s, card)] == ['chase', 'let_go', 'elsewhere', 'defer', 'next']

def test_let_it_go_drops_the_step_and_writes_the_ledger(s):
    t = person_step(s, 7); card = next(c for c in rail(s) if c.get('tid') == t)
    r = run(s, 'task.let_go', card)
    assert r.status_code == 200, r.text
    assert s.get_task(t)['Status'] == 'dropped'
    assert [x['Kind'] for x in outcomes.rows_for(s, 'task', t)][:2] == ['chase.let_go', 'task.closed']
    assert json.loads(outcomes.rows_for(s, 'task', t)[0]['FactsJson'])['who'] == RAY

def test_answered_elsewhere_closes_the_step_with_where(s):
    t = person_step(s, 7); card = next(c for c in rail(s) if c.get('tid') == t)
    assert run(s, 'task.elsewhere', card, 'he called').status_code == 200
    assert s.get_task(t)['Status'] == 'done'
    assert any('he called' in str(c.get('Body')) for c in s.list_comments(t))
    assert json.loads(outcomes.rows_for(s, 'task', t)[0]['FactsJson'])['where'] == 'he called'

def test_three_let_gos_silence_one_person(s):
    for k in range(3): outcomes.record(s, 'chase.let_go', 'message', k, facts={'who': RAY})
    t = s.create_task({'Title': 'Budget'}, 'owner')
    for who, cid in ((RAY, 'c5'), ('gail@northwind.example', 'c6')):
        s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'Budget', 'FromEmail': who, 'SentAt': ago(days=5), 'BodyText': 'q', 'Status': 'filed', 'TaskId': t})
        mid = s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'Re: Budget', 'FromEmail': 'alex@northwind.example', 'SentAt': ago(days=4), 'BodyText': 'Can you send it?', 'Status': 'context', 'TaskId': t})
        s.put_sent_verdict(mid, cid, True, False, None, None, 'test')
    whos = [c['action']['who_email'] for c in assistant.followups(s, 24, ('followup',))]
    assert whos == ['gail@northwind.example']

def test_a_chase_opens_a_draft_on_the_thread_with_the_ledgers_cc(s):
    iid, t = followup_idea(s, 6); card = next(c for c in rail(s) if c.get('idea') == iid)
    for k in range(2):
        t2 = s.create_task({'Title': f'x{k}'}, 'owner')
        i = outcomes.record(s, 'reply.sent', 'task', t2, facts={'cid': f'y{k}', 'mid': 1, 'verb': 'approve', 'who': RAY, 'cc': ['omar@northwind.example'], 'chase': True, 'answer_days': 1.0}, at=ago(days=9))
        outcomes.settle(s, i, 'answered', 'settled')
    with mock.patch('taskuary.responder.write_draft', return_value='Ray - a quick nudge on the budget.') as wd:
        r = run(s, 'task.chase', card)
    assert r.status_code == 200, r.text
    body = r.json(); rv = s.get_review(body['outcome']['reviewId'])
    assert rv['Reason'].startswith('chase:') and body['outcome']['cc'] == 'omar@northwind.example'
    assert 'omar' in (wd.call_args.kwargs.get('nudge') or '')

def test_a_chase_with_no_thread_is_refused_plainly(s):
    t = person_step(s, 7); card = next(c for c in rail(s) if c.get('tid') == t)
    r = run(s, 'task.chase', card)
    assert r.json()['status'] == 'error' and 'task page' in r.text               # refused, never a draft on nothing

def test_the_advisor_counts_chases_from_the_ledger(s):
    for k, ans in enumerate((1.0, None, 2.0)):
        t = s.create_task({'Title': f'x{k}'}, 'owner')
        i = outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': f'w{k}', 'mid': 1, 'verb': 'approve', 'who': RAY, 'cc': [], 'chase': True, **({'answer_days': ans} if ans else {})}, at=ago(days=9))
        outcomes.settle(s, i, 'x', 'settled')
    from taskuary import advisor
    t = s.create_task({'Title': 'Budget'}, 'owner')
    mid = s.add_message({'Channel': 'email', 'Subject': 'Budget', 'FromEmail': RAY, 'BodyText': 'q', 'Status': 'filed', 'TaskId': t})
    # counted for the sender's domain, never over everything (the deep dive, 2026-10-20)
    assert advisor.habit(s, 'chase', {'tid': t, 'mid': mid}) == (2, 3, 'with northwind.example')
    assert advisor.habit(s, 'chase', {})[:2] == (0, 0)


def test_the_followup_line_names_the_persons_day(s):
    t = s.create_task({'Title': 'Budget'}, 'owner')
    s.add_message({'ConversationId': 'c7', 'Channel': 'email', 'Subject': 'Budget', 'FromEmail': RAY, 'FromName': 'Ray Colton', 'SentAt': ago(days=8), 'BodyText': 'q', 'Status': 'filed', 'TaskId': t})
    mid = s.add_message({'ConversationId': 'c7', 'Channel': 'email', 'Subject': 'Re: Budget', 'FromEmail': 'alex@northwind.example', 'SentAt': ago(days=7), 'BodyText': 'Can you send it?', 'Status': 'context', 'TaskId': t})
    s.put_sent_verdict(mid, 'c7', True, False, None, None, 'test')
    c = next(x for x in assistant.followups(s, 24, ('followup',)) if x['kind'] == 'followup')
    assert 'late for them after 5 days' in c['facts']


# ── the review's fix pass (2026-10-12): the lane's lifecycle and the verbs' gate ────────────────────────────────────────
def test_let_it_go_on_a_thread_item_puts_the_follow_up_down_and_keeps_the_task(s):
    iid, t = followup_idea(s, 6); card = next(c for c in rail(s) if c.get('idea') == iid)
    r = run(s, 'task.let_go', card)
    assert r.status_code == 200, r.text
    assert s.get_task(t)['Status'] != 'dropped'                                            # the THREAD's task is not a person's step
    assert s.get_idea(iid)['Status'] != 'open'
    assert r.json()['outcome']['status'] == 'put down'

def test_their_reply_ends_the_slip_and_closes_the_follow_up(s):
    iid, t = followup_idea(s, 6)
    assert next(c for c in rail(s) if c.get('tid') == t)['lane'] == 'forgotten'
    s.add_message({'ConversationId': f'c{t}', 'Channel': 'email', 'Subject': 'Re: Budget', 'FromEmail': RAY, 'FromName': 'Ray Colton', 'SentAt': ago(hours=2), 'BodyText': 'Here it is.', 'Status': 'routed', 'TaskId': t})
    card = next(c for c in rail(s) if c.get('tid') == t)
    assert card['lane'] != 'forgotten' and not card.get('late_days')
    assert s.get_idea(iid)['Status'] == 'done'

def test_a_slipped_why_is_live_not_the_ideas_frozen_text(s):
    iid, t = followup_idea(s, 6)
    card = next(c for c in rail(s) if c.get('tid') == t)
    assert 'late for them after 5' in card['why'] and '6 days' in card['why']

def test_next_keeps_a_slipped_row_on_the_rail_as_passed(s):
    t = person_step(s, 7); card = next(c for c in rail(s) if c.get('tid') == t)
    funnel.settle(s, card['key'], 'surfaced', 'owner', read=True, put_down=True); funnel.invalidate()       # the Next press
    still = next((c for c in processing_unread.build(s, live_state=[])['items'] if c.get('tid') == t), None)
    assert still is not None and (still.get('put_down') or still.get('surfaced'))                        # Passed, never gone

def test_the_three_answers_need_a_slipped_card(s):
    t = s.create_task({'Title': 'Plain work', 'Status': 'open'}, 'owner')
    s.add_message({'ConversationId': 'c8', 'Channel': 'email', 'Subject': 'Plain', 'FromEmail': 'gail@northwind.example', 'SentAt': ago(hours=3), 'BodyText': 'q', 'Status': 'routed', 'TaskId': t})
    card = next(c for c in rail(s) if c.get('tid') == t)
    assert card['lane'] != 'forgotten'
    for v in ('chase', 'let_go', 'elsewhere'): assert concierge.cannot(card, v, s)
    r = run(s, 'task.let_go', card)
    assert r.json()['status'] == 'error' and s.get_task(t)['Status'] == 'open'

def test_a_chase_on_a_step_goes_to_the_person_who_owes_it(s):
    t = person_step(s, 7)
    s.add_message({'ConversationId': 'c9', 'Channel': 'email', 'Subject': 'Schema', 'FromEmail': RAY, 'FromName': 'Ray Colton', 'SentAt': ago(days=9), 'BodyText': 'I will sign off.', 'Status': 'filed', 'TaskId': t})
    gail = s.add_message({'ConversationId': 'c9', 'Channel': 'email', 'Subject': 'Re: Schema', 'FromEmail': 'gail@northwind.example', 'FromName': 'Gail Moreno', 'SentAt': ago(days=8), 'BodyText': 'Any news?', 'Status': 'filed', 'TaskId': t})
    card = next(c for c in rail(s) if c.get('tid') == t)
    with mock.patch('taskuary.responder.write_draft', return_value='Ray - a nudge.') as wd:
        r = run(s, 'task.chase', card)
    assert r.status_code == 200, r.text
    rv = s.get_review(r.json()['outcome']['reviewId'])
    assert rv['MessageId'] != gail and (s.get_message(rv['MessageId']) or {}).get('FromEmail') == RAY
    assert 'ray@northwind.example' in (wd.call_args.kwargs.get('nudge') or '')

def test_answered_elsewhere_on_a_thread_item_is_a_done_not_a_turn_down(s):
    iid, t = followup_idea(s, 6); card = next(c for c in rail(s) if c.get('idea') == iid)
    assert run(s, 'task.elsewhere', card, 'he called').status_code == 200
    assert s.get_idea(iid)['Status'] == 'done' and s.get_task(t)['Status'] == 'open'
