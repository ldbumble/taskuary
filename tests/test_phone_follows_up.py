"""The phone never drops you (the owner, 2026-10-08: "it never sends close out email draft to whatsapp?" - "make sure the
assistant on the phone never just drops you"). Work handed to an agent from a chat is followed up IN that chat when the agent
stops working; the line that hands it over says so, and offers the walk's way on meanwhile."""
import json
from unittest import mock

from taskuary import concierge, funnel, messengers, remote_assistant as ra
from tests.test_remote_assistant import JID, armed_store


def pile(*rows): return {'items': [dict(r) for r in rows], 'alerts': []}


def from_the_chat(store, tid):
    ra._ASKING.chat = {'channel': 'whatsapp', 'chat': JID, 'connector_id': 1}
    try: return ra.promise(store, tid)
    finally: ra._ASKING.chat = None


def look(store, rows):
    with mock.patch.object(funnel, 'pile', return_value=pile(*rows)), \
         mock.patch.object(concierge, 'surface', return_value={'say': 'The draft is ready.', 'item': None}) as surfaced, \
         mock.patch.object(messengers, 'wa_send') as sent:
        n = ra.keep_promises(store, force=True)
    return n, surfaced, sent


def test_an_answered_agent_comes_back_to_the_chat_with_its_draft_once():
    store, _c = armed_store()
    with mock.patch.object(funnel, 'pile', return_value=pile({'key': 'agent:7', 'tid': 7, 'lane': 'blocked'})):
        assert from_the_chat(store, 7)
    # still `blocked` a moment after the answer: nothing yet - that is the question it was just answered on
    assert look(store, [{'key': 'agent:7', 'tid': 7, 'lane': 'blocked'}])[0] == 0
    assert look(store, [{'key': 'agent:7', 'tid': 7, 'lane': 'working'}])[0] == 0
    n, surfaced, sent = look(store, [{'key': 'review:9', 'tid': 7, 'lane': 'approve'}])
    assert n == 1 and surfaced.call_args.args[1] == 'review:9'
    assert 'TQ-0007 is back' in sent.call_args.args[2]
    assert look(store, [{'key': 'review:9', 'tid': 7, 'lane': 'approve'}])[0] == 0          # said once


def test_a_task_that_finished_with_nothing_for_you_says_so_with_a_way_on():
    store, _c = armed_store()
    with mock.patch.object(funnel, 'pile', return_value=pile({'key': 'agent:7', 'tid': 7, 'lane': 'working'})):
        from_the_chat(store, 7)
    with mock.patch.object(store, 'get_task', return_value={'TaskId': 7, 'Status': 'done'}):
        n, _s, sent = look(store, [])
    assert n == 1
    assert 'TQ-0007 is finished' in sent.call_args.args[2]
    offered = json.loads(store.get_setting(f'{ra.OFFERED_KEY}:whatsapp:{JID}') or '[]')         # the poll under it
    assert 'Open TQ-0007' in offered and concierge.CHIP_WORDS['next'] in offered


def test_the_desk_makes_no_promise_to_a_phone():
    store, _c = armed_store()
    assert not ra.promise(store, 7)
    assert json.loads(store.get_setting(ra.PROMISES_KEY) or '[]') == []


def test_nothing_is_pushed_while_the_chat_is_talking():
    store, _c = armed_store()
    with mock.patch.object(funnel, 'pile', return_value=pile({'key': 'agent:7', 'tid': 7, 'lane': 'working'})):
        from_the_chat(store, 7)
    ra.talked(store, 'whatsapp', JID)
    with mock.patch.object(funnel, 'pile', return_value=pile({'key': 'review:9', 'tid': 7, 'lane': 'approve'})), \
         mock.patch.object(messengers, 'wa_send') as sent:
        assert ra.keep_promises(store) == 0
    sent.assert_not_called()
    assert len(json.loads(store.get_setting(ra.PROMISES_KEY))) == 1                     # kept for the next look


def test_telling_the_agent_is_never_the_last_word():
    store, _c = armed_store()
    item = {'kind': 'agent', 'tid': 7, 'key': 'agent:7', 'agent': 'coder', 'asking': True, 'choices': ['hand it off to Gail']}
    ra._ASKING.chat = {'channel': 'whatsapp', 'chat': JID, 'connector_id': 1}
    try:
        with mock.patch('taskuary.workerstate.answer_open', return_value={'delivered': True}), \
             mock.patch.object(funnel, 'pile', return_value=pile({'key': 'agent:7', 'tid': 7, 'lane': 'blocked'})):
            said = ra.answer_the_agent(store, item, 'hand it off to Gail', True)        # the agent's own answer, picked
    finally: ra._ASKING.chat = None
    assert said.startswith('Told coder: "hand it off to Gail".') and ra.PROMISE_LINE in said
    assert concierge.CHIP_WORDS['next'] in said
    assert [p['tid'] for p in json.loads(store.get_setting(ra.PROMISES_KEY))] == [7]
