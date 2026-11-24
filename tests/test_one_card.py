"""ONE CARD (the design review, change 6): whatever waits on the owner is one object with one state machine, four questions and one press
road (card.py) - read the same by the desk, the phone and the Assistant. Each test names where two roads used to disagree. Invented people."""
import json
from unittest import mock

from taskuary import card, workerstate as ws
from taskuary.browserview import TURN_PREFIX
from taskuary.store import MemoryStore
from taskuary import terminal as term
from test_worker_events import live


def task(s, title='Close the quarter'):
    return s.create_task({'Title': title, 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')


def act(s, tid, p, reason='the agent proposes to do it', **kw):
    return s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': reason, 'DraftText': json.dumps(p), **kw})


def reply(s, tid, words='Hi Erin - the numbers are attached.', **kw):
    mid = s.add_message({'TaskId': tid, 'ExternalId': f'm{tid}', 'ConversationId': f'c{tid}', 'Channel': 'email', 'Subject': 'Quarter',
                         'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': '2026-11-23 09:00:00', 'BodyText': 'Numbers?',
                         'Status': 'routed'})
    return s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': words, **kw})


def every_kind(s):
    "A task holding one card of every kind the owner presses, and the agent's question and a step on a page."
    from taskuary import slots
    tid = task(s)
    ids = {'reply': reply(s, tid)}
    ids['email'] = slots.draft(s, tid, 'Hi Gail - the plan is attached.', 'gail@northwind.example', 'Plan')
    ids['email'] = s._one("SELECT ReviewId FROM review WHERE TaskId=? AND Kind='slot'", (tid,))['ReviewId']
    ids['post'] = act(s, tid, {'action': 'run_tool', 'type': 'linkedin_post', 'text': 'A good quarter.'}, 'the agent proposes to post on LinkedIn')
    ids['held'] = act(s, tid, {'action': 'shell_act', 'what': 'push to northwind/ledger', 'command': 'git push', 'turn': 1}, 'held before it ran')
    ids['act'] = act(s, tid, {'action': 'save_routine', 'title': 'Weekly ledger', 'runs': 'weekly'})
    ids['closeout'] = act(s, tid, {'action': 'merge_pr', 'repo': 'northwind/ledger', 'number': 7}, 'finishing it: merge pull request #7')
    ids['playbook'] = act(s, tid, {'action': 'write_playbook', 'slug': 'quarter-close', 'text': 'x'})
    return tid, ids


# ── the state machine ────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_every_review_state_is_one_of_the_machines():
    from taskuary.proposals import SET_ASIDE
    s = MemoryStore(); tid = task(s)
    def r(**kw):
        rid = act(s, tid, {'action': 'save_routine', 'title': 'x', 'runs': 'daily'})
        if kw: s._exec(f"UPDATE review SET {', '.join(f'{k}=?' for k in kw)} WHERE ReviewId=?", (*kw.values(), rid))
        return s.get_review(rid)
    cases = {'pending': r(), 'pressed': r(DeliveryState='sending'),
             'done': r(Status='approved', DecidedBy='owner', DecidedAt='2026-11-23 10:00:00'),
             'set_aside': r(Status='superseded', DecideNote=SET_ASIDE, DecidedBy='taskuary', DecidedAt='2026-11-23 10:00:00'),
             'withdrawn': r(Status='superseded', DecidedBy='agent', DecidedAt='2026-11-23 10:00:00'),
             'failed': r(Status='superseded', ActError='the site refused', DecidedBy='owner', DecidedAt='2026-11-23 10:00:00'),
             'handed': r(Status='approved', DecidedBy='owner', DecidedAt='2026-11-23 10:00:00', FinalText=json.dumps({'result': {'browser': True}}))}
    for want, row in cases.items(): assert card.state_of(row) == want, (want, card.state_of(row))
    no = r(Status='rejected', DecidedBy='owner', DecidedAt='2026-11-23 10:00:00')
    assert (card.state_of(no), card.of_review(s, no)['verb']) == ('done', 'no'), 'his no settles the card - it is not taken back'
    assert set(card.STATES) >= {card.state_of(x) for x in cases.values()}


# ── what waits ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_what_waits_is_every_kind_in_the_order_the_page_brings_them():
    s = MemoryStore(); tid, ids = every_kind(s)
    term.SESSIONS['q1'] = live(tid, 'q1')
    try:
        ws.record(s, tid, 'q1', 'input_needed', text='Include the March accruals?', source='api')
        got, lines = card.waiting(s, tid), card.lines(s, tid)
    finally: term.SESSIONS.pop('q1', None)
    sorts = [c['sort'] for c in got]
    for k in ids: assert k in sorts or k == 'closeout', (k, sorts)
    assert ids['closeout'] in got[0]['rids'], 'a close-out is pressed with the reply it closes: one card'
    assert sorts[-1] == 'question' and got[-1]['kind'] == card.ANSWER and 'March accruals' in got[-1]['what']
    assert [c['front'] for c in got].count(True) == 1 and got[0]['front'] and got[0]['id'] == f"rv{ids['reply']}"
    assert {c['state'] for c in got} == {'pending'}
    # ...and its lines say each, the agent's question last
    assert lines[0]['line'] == 'a reply to erin@northwind.example is drafted - Send sends it' and lines[-1]['verb'] == 'answer_agent'


def test_a_step_handed_to_him_on_a_page_waits_as_its_own_card_not_as_the_agents_question():
    """The Assistant's list read a sign-in or a robot check as "the agent asks: ..." while the screen fact said it was handed to him on the
    page: one card, kind on_page, on every surface."""
    s = MemoryStore(); tid = task(s)
    ws.record(s, tid, 'run1', 'working')
    ws.record(s, tid, 'run1', 'input_needed', request_id=f'{TURN_PREFIX}robot1', text='Your turn in the browser on news.example: tick the check')
    (c,) = card.waiting(s, tid)
    assert (c['kind'], c['sort'], c['id']) == (card.ON_PAGE, 'turn', f'page:{tid}:{TURN_PREFIX}robot1')
    assert card.lines(s, tid)[0]['line'].startswith('handed to you on the page: ')


def test_a_reply_nobody_has_written_is_no_card_anywhere():
    """The page draws no card for a reply owed that nobody has written (conversation.unwritten); the Assistant's list said "a reply to ... is
    drafted - Send sends it" of it, and a Send and close was kept open over it."""
    s = MemoryStore(); tid = task(s)
    reply(s, tid, words='')
    assert card.waiting(s, tid) == [] and card.lines(s, tid) == []


def test_a_bulk_card_is_one_card():
    from taskuary import bulkcard
    s = MemoryStore(); tid = task(s); key = bulkcard.new_key()
    rs = [s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': f'Hi {n}', 'Deliver': json.dumps({'to': [f'{n}@northwind.example']})})
          for n in ('ray', 'omar', 'paula')]
    for r in rs: s._exec('UPDATE review SET Batch=? WHERE ReviewId=?', (key, r))
    (c,) = card.waiting(s, tid, asks=False)
    assert c['rids'] == rs and c['what'] == '3 emails'


# ── what is in front ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_card_his_press_handed_to_the_agent_is_in_front_but_the_phone_offers_no_press_on_it():
    """Post via the browser on the LinkedIn card: it is the agent's to do now. The phone read the line's front review and drew Approve and
    Dismiss on a card already pressed - each press then answered "not waiting any more"."""
    from taskuary import remote_assistant as ra
    s = MemoryStore(); tid = task(s)
    li = act(s, tid, {'action': 'run_tool', 'type': 'linkedin_post', 'text': 'A good quarter.'})
    act(s, tid, {'action': 'run_tool', 'type': 'x_post', 'text': 'A good quarter.'})
    s.decide_review(li, 'approved', json.dumps({'action': 'run_tool', 'type': 'linkedin_post', 'result': {'browser': True}}), 'owner')
    f = card.front(s, tid)
    assert (f['id'], f['state']) == (f'rv{li}', 'handed') and card.front_review(s, tid) == {}
    assert ra.card_picks(s, {'tid': tid, 'rid': None}) == []
    assert 'Handed' in card.did(s, f) and 'not done yet' in card.did(s, f)


def test_a_stranger_started_task_has_its_trust_in_front_and_no_send_on_the_phone():
    """The page draws no card to press on a task a stranger's mail started - its Trust is the one move (server.task_detail). The phone read
    the line's front and offered Send on the reply drafted to the stranger."""
    from taskuary import remote_assistant as ra
    s = MemoryStore()
    tid = s.create_task({'Title': 'A question from outside', 'Kind': 'reply', 'Status': 'waiting'}, 'router')
    reply(s, tid)
    with mock.patch('taskuary.origin.keeps_him', return_value={'line': 'You have not trusted this sender yet.'}):
        assert card.front(s, tid)['kind'] == card.TRUST
        assert ra.front_card(s, {'tid': tid}) == {}
        # ...and what waits on him there is its Trust, in its hold's words - a list of what needs him left held tasks out (walk 16)
        assert card.lines(s, tid) == [{'rid': None, 'verb': 'trust', 'says': '', 'line': 'You have not trusted this sender yet.'}]
        assert card.press(s, f'trust:{tid}', 'approve')['ok'] is False


# ── may this close ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_send_and_close_is_offered_only_where_the_close_after_the_send_closes():
    """A reply held while the agent worked (or a workflow's own step) stood outside the line: the desk's Send and close read the line and
    offered the close, then the close after the send found it and kept the task open - "Sent. Kept open: ...". One answer now."""
    from taskuary import concierge
    s = MemoryStore(); tid = task(s)
    front = reply(s, tid)
    s.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'held', 'DraftText': 'Hi Ray - a second note.', 'Reason': 'held while the agent works'})
    assert card.may_close(s, tid) and card.may_close(s, tid, f'rv{front}')
    item = {'tid': tid, 'rid': front, 'kind': 'review', 'ref': f'TQ-{tid:04d}', 'draft': True}
    assert 'stays open' in concierge.cannot(item, 'send_close', s)


def test_the_last_card_may_close_and_a_handed_one_holds_it():
    s = MemoryStore(); tid = task(s)
    front = reply(s, tid)
    assert card.may_close(s, tid) == ''
    li = act(s, tid, {'action': 'run_tool', 'type': 'linkedin_post', 'text': 'x'})
    assert card.may_close(s, tid) == 'a LinkedIn post' or card.may_close(s, tid)
    s.decide_review(li, 'approved', json.dumps({'action': 'run_tool', 'type': 'linkedin_post', 'result': {'browser': True}}), 'owner')
    assert card.may_close(s, tid, f'rv{front}'), 'an act handed to the agent is not done - the close waits for it'


def test_a_check_back_its_agent_set_holds_send_and_close():
    """Walk 16: the reply asking the vendor for a fresh order-form link stood with Send and close first, while the agent's own check-back said
    it would look again Friday. Its check-back holds the close as another card does - on the page, the desk and the chat's read alike."""
    from taskuary import checkback, concierge
    s = MemoryStore(); tid = task(s, 'Sort out the Trainly renewal')
    front = reply(s, tid, 'Hi Dana - could you send a fresh link to the order form?')
    assert card.may_close(s, tid) == ''
    checkback.set_check(s, tid, 'in 2 days', 'Dana sent the signed order form')
    assert card.may_close(s, tid) == 'the check-back the agent set (Dana sent the signed order form)'
    item = {'tid': tid, 'rid': front, 'kind': 'review', 'ref': f'TQ-{tid:04d}', 'draft': True}
    assert 'stays open' in concierge.cannot(item, 'send_close', s)
    checkback.cancel(s, tid)
    assert card.may_close(s, tid) == ''


# ── what the press did, by the one road ──────────────────────────────────────────────────────────────────────────────────────────────
def test_the_desk_the_phone_and_the_phones_pick_press_through_the_one_road():
    """The phone's pick of an email (asks.send_picked) sent through verdicts.decide directly, past the desk's check that the thread moved
    since the draft; the phone's card and the Assistant went through server.decide. Every press is card.press -> server.press_review now, on the store it was pressed in."""
    from taskuary import asks, remote_assistant as ra, server
    s = MemoryStore(); tid = task(s); rid = reply(s, tid)
    with mock.patch.object(server, 'press_review', return_value={'ok': True, 'status': 'approved'}) as door:
        a = card.press(s, rid, 'approve')
        b = ra.press_card(s, rid, 'approve')
        c = asks.send_picked(s, [(rid, None)])
    assert door.call_count == 3 and {x.args[:2] for x in door.call_args_list} == {(s, rid)}
    assert a['ok'] and a['did'].startswith('Sent the reply to') and 'Sent the reply to' in b and c.startswith('Sent to')


def test_a_press_on_a_card_no_longer_his_presses_nothing_and_says_what_became_of_it():
    from taskuary import server
    s = MemoryStore(); tid = task(s)
    rid = act(s, tid, {'action': 'save_routine', 'title': 'Weekly ledger', 'runs': 'weekly'}, Status='rejected', DecidedBy='owner', DecidedAt='2026-11-23 10:00:00')
    with mock.patch.object(server, 'press_review') as door: got = card.press(s, rid, 'approve')
    assert not door.called and got['ok'] is False and 'not waiting any more' in got['did'] and 'Dismissed' in got['did']


def test_a_failed_send_says_why_and_nothing_is_said_sent():
    from taskuary import server
    s = MemoryStore(); tid = task(s); rid = reply(s, tid)
    with mock.patch.object(server, 'press_review', return_value={'ok': True, 'status': 'pending', 'send_error': 'No mailbox is connected'}):
        got = card.press(s, rid, 'approve')
    assert got == {'ok': False, 'did': 'Not sent - No mailbox is connected', 'out': got['out']}


def test_the_agents_question_is_pressed_by_the_answer_road():
    s = MemoryStore(); tid = task(s)
    term.SESSIONS['q2'] = live(tid, 'q2')
    try:
        ws.record(s, tid, 'q2', 'input_needed', text='Which quarter?', source='api')
        (q,) = card.waiting(s, tid)
        with mock.patch.object(ws, 'answer', return_value={'delivered': True, 'state': 'delivered'}) as ans:
            got = card.press(s, q['id'], 'answer', 'The third.')
    finally: term.SESSIONS.pop('q2', None)
    assert got['ok'] and ans.call_args.args[:4] == (s, tid, q['request'], 'The third.')


def test_what_the_agents_events_read_of_the_presses_since_its_cursor():
    s = MemoryStore(); tid = task(s)
    a = act(s, tid, {'action': 'save_routine', 'title': 'Weekly ledger', 'runs': 'weekly'})
    s.decide_review(a, 'rejected', None, 'owner')
    (c,) = card.settled(s, tid, '')
    assert (c['id'], c['state'], c['verb']) == (f'rv{a}', 'done', 'no') and c['did'].startswith('Dismissed')
    assert card.settled(s, tid, '9999') == []


# ── the Assistant reads the same ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_task_whose_only_card_is_its_playbook_has_an_approve_for_the_assistant():
    """The Assistant's check for an Approve on a task row read proposals.held_pending, which skipped playbooks and close-outs: the page drew
    the playbook's Approve and the Assistant said there was nothing to approve. Its rulebook state read the same and lit nothing."""
    from taskuary import concierge, rulebook
    s = MemoryStore(); tid = task(s)
    rid = act(s, tid, {'action': 'write_playbook', 'slug': 'quarter-close', 'text': 'x'})
    item = {'tid': tid, 'kind': 'task', 'ref': f'TQ-{tid:04d}', 'lane': 'approve'}
    assert concierge.cannot(item, 'approve', s) == ''
    assert rulebook.state(s, item, [])[0] == 'action_held' and rulebook.state(s, item, [])[1][rulebook.EV] == [f'rv{rid}']
