"""The assistant remembers what you asked, and says when it moves (spec 2026-10-05-assistant-remembers-asks-design.md).

An ask is a task marked with where you asked. Its state is its rail lane; a move into a lane that needs you, or its end,
is said once at that door - the phone only when you asked from it or the walk is handed there.
"""
from unittest import mock

import pytest

from taskuary import asks, concierge, remote_assistant
from taskuary.store import MemoryStore


@pytest.fixture
def s():
    v = MemoryStore(); yield v; v.close()


def made(s, text='Check the four tabs', **k):
    with mock.patch('taskuary.concierge._handoff_brief', side_effect=lambda st, tid, job: job), \
         mock.patch('taskuary.concierge._handoff_title', return_value=text):
        return concierge.setup_task(s, text, 'owner', kind='general', agent_job=True, **k)['taskId']


# ── the mark ─────────────────────────────────────────────────────────────────────────────
def test_a_chat_ask_on_the_desktop_is_marked_desktop(s):
    assert s.get_task(made(s))['AskedVia'] == 'desktop'


def test_an_ask_from_the_phone_is_marked_with_its_chat(s):
    remote_assistant._ASKING.chat = {'channel': 'whatsapp', 'chat': 'c1@example.com', 'connector_id': 3}
    try: tid = made(s)
    finally: remote_assistant._ASKING.chat = None
    assert s.get_task(tid)['AskedVia'] == 'whatsapp:c1@example.com' and asks.of(s.get_task(tid)) == 'whatsapp:c1@example.com'


def test_a_task_made_with_new_is_marked_desktop(s):
    from fastapi.testclient import TestClient
    from taskuary import server
    with mock.patch.object(server, 'store', s):
        tid = TestClient(server.app).post('/api/tasks', json={'Title': 'Pull the August numbers'}).json()['taskId']
    assert s.get_task(tid)['AskedVia'] == 'desktop'


def test_triage_work_is_not_an_ask_and_the_mark_survives_an_update(s):
    mail = s.create_task({'Title': 'From mail', 'Kind': 'task', 'Source': 'email'}, 'triage')
    assert asks.of(s.get_task(mail)) is None
    tid = made(s); s.update_task(tid, {'Priority': 'high'}, 'owner')
    assert s.get_task(tid)['AskedVia'] == 'desktop'


# ── where an ask stands: its rail lane, in the rail's words ──────────────────────────────
def rail(*items):
    return mock.patch('taskuary.asks._rail', return_value=list(items))


def test_the_state_is_the_rail_lane_and_its_sentence(s):
    tid = made(s)
    with rail({'tid': tid, 'lane': 'blocked', 'why': 'the agent asked you: which branch?'}):
        assert asks.state(s, tid) == ('blocked', 'the agent asked you: which branch?')


def test_an_approve_lane_with_emails_says_how_many(s):
    from taskuary import slots
    tid = made(s); slots.add(s, tid, [{'to': 'paula@northwind.example'}, {'to': 'ray@northwind.example'}], 'owner')
    slots.draft(s, tid, 'Tab 1 is fine.', to='paula@northwind.example')
    with rail({'tid': tid, 'lane': 'approve', 'why': '1 email drafted for you to send'}):
        lane, says = asks.state(s, tid)
    assert lane == 'approve' and '1 of 2 emails drafted' in says


def test_a_closed_ask_is_finished_with_the_agents_summary(s):
    tid = made(s); s.add_comment(tid, 'coder', 'agent', 'CODER REPORT\nSummary: checked all four tabs, two hold items.')
    s.update_task(tid, {'Status': 'done'}, 'coder')
    with rail():
        lane, says = asks.state(s, tid)
    assert lane == 'finished' and 'two hold items' in says


def test_off_the_rail_and_open_is_quiet(s):
    tid = made(s)
    with rail(): assert asks.state(s, tid)[0] == 'quiet'


def test_an_agent_touched_it_or_not(s):
    tid = made(s); todo = s.create_task({'Title': 'Call the bank', 'AskedVia': 'desktop'}, 'owner')
    assert asks.agent_touched(s, tid) and not asks.agent_touched(s, todo)


def test_the_real_rail_reads_approve_for_drafted_emails(s):
    from taskuary import funnel, slots
    tid = made(s); slots.add(s, tid, [{'to': 'paula@northwind.example'}], 'owner')
    slots.draft(s, tid, 'Tab 1 is fine.', to='paula@northwind.example'); funnel.invalidate()
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        assert asks.state(s, tid)[0] == 'approve'


# ── saying it moved: once, at its door ───────────────────────────────────────────────────
from taskuary import general


def dock_lines(s):
    dock = general.dock_task(s, 'owner')[0]['TaskId']
    return [c['Body'] for c in s.list_comments(dock) if 'TQ-' in str(c.get('Body') or '')]


def at(s, tid, lane, why='x'):
    return rail({'tid': tid, 'lane': lane, 'why': why})


def test_a_move_into_a_said_lane_is_said_once_on_the_desktop(s):
    tid = made(s)
    with at(s, tid, 'blocked', 'the agent asked you: which tab first?'):
        line = asks.check(s, tid); again = asks.check(s, tid)
    assert line and 'which tab first?' in line and again is None
    assert len(dock_lines(s)) == 1 and s.get_task(tid)['AskedTold'] == 'blocked'


def test_working_is_never_said_but_is_remembered(s):
    tid = made(s)
    with at(s, tid, 'working'): assert asks.check(s, tid) is None
    assert dock_lines(s) == [] and s.get_task(tid)['AskedTold'] == 'working'
    with at(s, tid, 'approve', '2 of 4 emails drafted, waiting on your yes'): assert asks.check(s, tid)


def test_finishing_is_said_with_the_summary(s):
    tid = made(s); s.add_comment(tid, 'coder', 'agent', 'CODER REPORT\nSummary: all four tabs checked.')
    s.update_task(tid, {'Status': 'done'}, 'coder')
    with at(s, tid, 'working'): line = asks.check(s, tid)
    assert line and 'all four tabs checked' in line


def test_a_restart_does_not_repeat_what_was_told(s):
    tid = made(s)
    with at(s, tid, 'blocked'): asks.check(s, tid)
    asks._Q['pending'].clear()                                       # nothing in memory survives a restart...
    with at(s, tid, 'blocked'): assert asks.check(s, tid) is None    # ...and nothing needed to


def test_mail_born_work_and_a_to_do_never_speak(s):
    mail = s.create_task({'Title': 'From mail', 'Kind': 'task', 'Source': 'email'}, 'triage')
    todo = s.create_task({'Title': 'Call the bank', 'AskedVia': 'desktop'}, 'owner')
    with rail({'tid': mail, 'lane': 'blocked', 'why': 'x'}, {'tid': todo, 'lane': 'blocked', 'why': 'x'}):
        assert asks.check(s, mail) is None and asks.check(s, todo) is None


PHONE = {'channel': 'whatsapp', 'chat': 'c1@example.com', 'connector_id': 3}


def phone_ask(s):
    remote_assistant._ASKING.chat = PHONE
    try: return made(s)
    finally: remote_assistant._ASKING.chat = None


def test_a_phone_ask_answers_on_the_phone_when_the_chat_is_quiet(s):
    tid = phone_ask(s)
    with at(s, tid, 'approve', 'a draft waits'), mock.patch.object(remote_assistant, 'quiet', return_value=True), \
         mock.patch.object(remote_assistant, 'connector_for_chat', return_value={'ConnectorId': 3}), \
         mock.patch.object(remote_assistant, 'send') as send:
        assert asks.check(s, tid)
    assert send.call_args[0][1:3] == ('whatsapp', 'c1@example.com') and s.get_task(tid)['AskedTold'] == 'approve'


def test_a_busy_phone_chat_is_retried_not_lost(s):
    tid = phone_ask(s)
    with at(s, tid, 'approve'), mock.patch.object(remote_assistant, 'quiet', return_value=False), \
         mock.patch.object(remote_assistant, 'connector_for_chat', return_value={'ConnectorId': 3}), \
         mock.patch.object(remote_assistant, 'send') as send:
        assert asks.check(s, tid) is None
    assert not send.called and not s.get_task(tid)['AskedTold']


def test_a_desktop_ask_goes_to_the_phone_while_the_walk_is_handed_there(s):
    tid = made(s)
    with at(s, tid, 'blocked'), mock.patch.object(remote_assistant, 'handoff', return_value=dict(PHONE, at='now')), \
         mock.patch.object(remote_assistant, 'quiet', return_value=True), mock.patch.object(remote_assistant, 'send') as send:
        asks.check(s, tid)
    assert send.called and dock_lines(s) and all('TQ-' in l for l in dock_lines(s))


def test_notice_is_nothing_until_the_watcher_runs_and_then_dedupes(s):
    tid = made(s)
    asks._Q['on'] = False; asks.notice(s, tid)
    assert not asks._Q['pending']
    asks._Q['on'] = True
    try:
        for _ in range(50): asks.notice(s, tid)
        with mock.patch.object(asks, 'check') as check: asks.drain()
        assert check.call_count == 1
    finally: asks._Q['on'] = False; asks._Q['pending'].clear()


def test_a_task_write_queues_the_task_and_the_checks_own_writes_do_not_loop(s):
    tid = made(s)
    asks._Q['on'] = True
    try:
        s.update_task(tid, {'Priority': 'high'}, 'owner')
        assert tid in asks._Q['pending']
        with at(s, tid, 'blocked'): asks.drain()
        assert tid not in asks._Q['pending']                  # saying it (the dock comment, the told mark) queued nothing
    finally: asks._Q['on'] = False; asks._Q['pending'].clear()


def test_a_phone_ask_whose_connection_is_gone_falls_back_to_the_desktop(s):
    tid = phone_ask(s)
    with at(s, tid, 'approve'), mock.patch.object(remote_assistant, 'send') as send:
        assert asks.check(s, tid)
    assert not send.called and dock_lines(s)


def test_the_sweep_checks_only_open_asks(s):
    tid, mail = made(s), s.create_task({'Title': 'From mail', 'Source': 'email'}, 'triage')
    with mock.patch.object(asks, 'check') as check: asks.sweep(s)
    assert [c[0][1] for c in check.call_args_list] == [tid]


# ── the assistant knows your asks ────────────────────────────────────────────────────────
def test_the_block_lists_open_asks_with_ref_door_and_state(s):
    a = made(s, 'Check the four tabs'); b = phone_ask(s)
    with rail({'tid': a, 'lane': 'working', 'why': 'the agent is on it'}, {'tid': b, 'lane': 'approve', 'why': 'a draft waits'}):
        out = asks.block(s)
    lines = out.splitlines()
    assert lines[0] == 'YOUR OPEN ASKS' and 'TQ-0002' in lines[1] and 'WhatsApp' in lines[1] and 'a draft waits' in lines[1]
    assert 'TQ-0001' in lines[2] and 'the agent is on it' in lines[2]


def test_the_block_is_capped_and_short(s):
    tids = [made(s, f'Ask number {n} about the quarterly numbers for the region') for n in range(20)]
    with rail(*[{'tid': t, 'lane': 'working', 'why': 'the agent is on it'} for t in tids]):
        out = asks.block(s)
    assert len(out.splitlines()) == 1 + asks.BLOCK_CAP and len(out) < 900


def test_a_finished_ask_leaves_the_block_once_it_is_off_the_rail(s):
    tid = made(s); s.update_task(tid, {'Status': 'done'}, 'coder')
    with rail({'tid': tid, 'lane': 'saved', 'why': 'finished'}): assert 'TQ-0001' in asks.block(s)
    with rail(): assert asks.block(s) == ''


def test_no_asks_no_block(s):
    with rail(): assert asks.block(s) == ''


def test_the_look_up_lists_older_and_finished_asks(s):
    from taskuary import lookups
    a = made(s, 'Check the four tabs'); b = made(s, 'Research vendor pricing'); s.update_task(a, {'Status': 'done'}, 'coder')
    with rail():
        both, open_ = lookups.read(s, 'asks.list', {'status': 'all'}), lookups.read(s, 'asks.list', {})
    assert 'Check the four tabs' in both and 'Research vendor pricing' in both
    assert 'Check the four tabs' not in open_


def test_every_turn_carries_the_block(s):
    seen = []
    with mock.patch.object(asks, 'block', return_value='YOUR OPEN ASKS\n- TQ-0009 Check the tabs - a draft waits'):
        concierge.say(s, "where's the tab check?", llm=lambda sys, user, **k: seen.append(user) or 'Waiting on your yes.')
    assert seen and 'YOUR OPEN ASKS' in seen[0]


# ── the Advisor never repeats what a task just said ──────────────────────────────────────
import json
from datetime import datetime, timedelta


def hours_ago(h): return (datetime.now() - timedelta(hours=h)).isoformat(' ', 'seconds')


def cand(tid=None, mid=None, conv='conv-1', kind='followup'):
    return {'key': f'{kind}:{conv}', 'kind': kind, 'facts': 'x', 'text': 'follow up?', 'action': {'type': kind, 'mid': mid, 'tid': tid}}


def test_a_candidate_on_a_task_told_an_hour_ago_is_dropped_and_25h_later_comes_back(s):
    tid = made(s)
    s._exec('UPDATE task SET AskedTold=?, AskedToldAt=? WHERE TaskId=?', ('approve', hours_ago(1), tid))
    assert asks.not_just_said(s, [cand(tid=tid)], 24) == []
    s._exec('UPDATE task SET AskedToldAt=? WHERE TaskId=?', (hours_ago(25), tid))
    assert len(asks.not_just_said(s, [cand(tid=tid)], 24)) == 1


def test_a_candidate_whose_person_just_got_an_email_from_a_task_is_dropped(s):
    tid = made(s)
    mid = s.add_message({'ExternalId': 'in-p', 'ConversationId': 'conv-p', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                         'FromName': 'Paula Vance', 'FromEmail': 'paula@northwind.example', 'Subject': 'Tabs', 'BodyText': 'Any news?',
                         'SentAt': hours_ago(30), 'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'approved', 'DraftText': 'Tab 1 is fine.',
                        'Deliver': json.dumps({'channel': 'email', 'to': ['paula@northwind.example'], 'subject': 'Tab 1'})})
    s._exec("UPDATE review SET DeliveryState='sent', DecidedAt=? WHERE ReviewId=?", (hours_ago(1), rid))
    assert asks.not_just_said(s, [cand(mid=mid, conv='conv-p')], 24) == []


def test_an_untouched_candidate_comes_through(s):
    assert len(asks.not_just_said(s, [cand(conv='conv-z')], 24)) == 1


def test_the_advisor_drops_them_before_the_model_sees_them(s):
    from taskuary import assistant
    tid = made(s); s._exec('UPDATE task SET AskedTold=?, AskedToldAt=? WHERE TaskId=?', ('finished', hours_ago(1), tid))
    with mock.patch.object(assistant, '_asks_and_promises', return_value=[cand(tid=tid), cand(conv='conv-z')]):
        out = assistant.candidates(s, {'producers': (), 'cold_d': 3, 'followup_h': 24})
    assert [c['key'] for c in out] == ['followup:conv-z']


def test_already_said_carries_what_tasks_told_the_owner(s):
    from taskuary import assistantblocks
    tid = made(s, 'Check the four tabs'); s._exec('UPDATE task SET AskedTold=?, AskedToldAt=? WHERE TaskId=?', ('approve', hours_ago(2), tid))
    text, _ = assistantblocks._already_said(s, {})
    assert 'Check the four tabs' in text and 'TQ-0001' in text
