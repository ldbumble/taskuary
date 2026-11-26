"""A CHAT TASK'S WAITING MOVE IS THE AGENT'S (the owner, 2026-11-05: "we can remove reply ready for you since it can be any action"). The rail
marks a general task's ready-to-send or waiting-agent row `chat`, and the page says "agent ready for you" over it (railStatus.chatReady); a
coding task's row is not marked and keeps its own words. Invented world only."""
from taskuary import funnel
from taskuary.store import MemoryStore


def test_the_phone_and_the_assistant_say_agent_ready_for_you_for_a_chat_task_and_a_coding_task_keeps_its_words():
    """The sentence words (funnel.lane_word) that the phone's card (remote_assistant.status_line, story_block) and the Assistant's prompt lines
    read: a chat row's ready reply and its waiting agent both say the chat word; a coding row's say its lane's."""
    from taskuary import funnel_presentation, lanes, remote_assistant
    ready = lanes.word('chat_ready')
    for lane in funnel.CHAT_READY_LANES:
        assert funnel.lane_word({'lane': lane, 'chat': True}) == ready
        assert funnel.lane_word({'lane': lane}) == funnel.LANE_WORDS[lane][0]
        assert funnel_presentation.state_of({'lane': lane, 'chat': True, 'kind': 'action'}) == ready
    assert funnel.lane_word({'lane': 'working', 'chat': True}) == funnel.LANE_WORDS['working'][0], 'only the waiting move changes words'
    assert remote_assistant.status_line({'lane': 'approve', 'chat': True, 'why': 'a draft to Erin Blake'}).startswith(ready)


def test_a_parked_chat_agent_is_ready_for_you_and_a_coding_one_waits_on_you(monkeypatch):
    from taskuary import lanes, terminal
    class GeneralSession:
        alive = True
        def waiting(self): return True
    class PtySession(GeneralSession): pass
    monkeypatch.setattr(terminal, 'session_for', lambda tid: GeneralSession())
    assert funnel.live_session_state(1)[1] == lanes.word('chat_ready')
    monkeypatch.setattr(terminal, 'session_for', lambda tid: PtySession())
    assert funnel.live_session_state(1)[1] == 'waiting on you'


def test_after_the_owner_sends_a_chat_agent_is_done_until_typed_to_again():
    """ONE CYCLE (the owner, 2026-11-06): working, waiting on you, and after a Send "agent done" - the rail row, the task's state and the
    sentence words all read taskstate.chat_moved_on."""
    from taskuary import general, lanes, taskstate
    s = MemoryStore()
    tid = s.create_task({'Title': 'Pay date for Gail', 'Kind': 'general', 'Status': 'in_progress'}, 'owner')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Drafted Gail a reply.')
    rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Gail, Friday. Alex'})
    live = {'alive': True, 'waiting': True, 'state': 'parked'}
    assert not taskstate.chat_moved_on(s, tid), 'a draft waits: the agent waits on you'
    s._exec("UPDATE review SET Status='approved', FinalText=DraftText, DecidedAt='2999-01-01 00:00:00' WHERE ReviewId=?", (rid,))
    assert taskstate.chat_moved_on(s, tid)
    assert taskstate.state(s, s.get_task(tid), session=live) == 'agentdone'
    assert taskstate.state(s, s.get_task(tid), session={**live, 'waiting': False}) == 'working', 'typed to again: working'
    s._exec("UPDATE comment SET CreatedAt='2999-01-02 00:00:00' WHERE TaskId=?", (tid,))
    assert not taskstate.chat_moved_on(s, tid), 'it answered again since the send: waiting on you'
    assert funnel.lane_word({'lane': 'yours', 'kind': 'wrapup', 'chat_done': True}) == lanes.word('chat_done') == 'agent done'


def test_a_chat_agent_whose_turn_was_stopped_is_not_done():
    """The audit, 2026-11-10 (CI, on a slow runner): Remind me pressed while the agent worked stopped its turn, and in the beat before its
    session rested the row lit Mark done - "agent done" over a turn that answered nothing. A stopped turn is no turn that ended."""
    from taskuary import taskstate, workerstate as ws
    s = MemoryStore()
    tid = s.create_task({'Title': 'Plan the offsite', 'Kind': 'general', 'Status': 'in_progress'}, 'owner')
    live = {'alive': True, 'waiting': True, 'state': 'parked', 'sid': 'g-1', 'mode': 'assistant'}
    ws.record(s, tid, 'g-1', 'turn_end', text='The plan is above.', source='api')
    assert taskstate.done_for_now(s, s.get_task(tid), live)
    ws.record(s, tid, 'g-1', 'stopped', text='stopped', source='api')
    assert not taskstate.done_for_now(s, s.get_task(tid), live) and taskstate.state(s, s.get_task(tid), session=live) != 'agentdone'


def test_after_his_press_settles_the_one_card_the_rail_row_reads_agent_done_never_on_you():
    """The card gallery, 2026-11-25: a QuickBooks bill's card, pressed and entered - nothing owed, the agent's turn over - and the header went
    "waiting for your input" -> "on you": the row kept its own lane, as the task's state ("agent done") is no lane. It reads what is owed."""
    import json
    from unittest import mock
    from fastapi.testclient import TestClient
    from taskuary import general, reports, server
    s = MemoryStore()
    tid = s.create_task({'Title': 'Enter the Payworth bill', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
    s.add_comment(tid, general.BRIEF_ACTOR, general.USER_TYPE, "Enter Payworth's November invoice in QuickBooks.")
    qb = s.get_connector_by_type('quickbooks'); s.save_connector({'ConnectorId': qb['ConnectorId'], 'Active': 1, 'Secret': 'stand-in'}, 'owner')
    rid = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent', 'Reason': 'the agent proposes to enter the bill',
                        'DraftText': json.dumps({'action': 'run_tool', 'type': 'quickbooks_bill', 'connector_id': qb['ConnectorId'], 'vendor': 'Payworth',
                                                 'amount': 200, 'account': 'Software subscriptions'})})
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The Payworth bill is set up for your press.')
    c, owner = TestClient(server.app), {'X-Taskuary-Token': 'pytest-owner-token'}
    row = lambda: next((i['lane'], (i.get('status') or {}).get('word')) for i in c.get('/api/funnel/pile', params={'force': 1}, headers=owner).json()['items']
                       if i.get('tid') == tid)
    with mock.patch.object(server, 'store', s), mock.patch.object(general, 'to_agent', lambda *a, **k: 'woke'), \
         mock.patch.dict(reports.REGISTRY, {'quickbooks_bill': lambda cfg: {'rows': [{'url': 'https://quickbooks.example/bill/1'}], 'columns': ['url']}}):
        assert row() == ('blocked', 'waiting for your input')
        assert c.post(f'/api/reviews/{rid}/decide', headers=owner, json={'verb': 'approve'}).json()['ok']
        assert row() == ('yours', 'agent done'), 'nothing is on him'
