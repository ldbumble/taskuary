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
    item = {'kind': 'agent', 'tid': 7, 'key': 'agent:7', 'agent': 'coding', 'asking': True, 'choices': ['hand it off to Gail']}
    ra._ASKING.chat = {'channel': 'whatsapp', 'chat': JID, 'connector_id': 1}
    try:
        with mock.patch('taskuary.workerstate.answer_open', return_value={'delivered': True}), \
             mock.patch.object(funnel, 'pile', return_value=pile({'key': 'agent:7', 'tid': 7, 'lane': 'blocked'})):
            said = ra.answer_the_agent(store, item, 'hand it off to Gail', True)        # the agent's own answer, picked
    finally: ra._ASKING.chat = None
    assert said.startswith('Told coding: "hand it off to Gail".') and ra.PROMISE_LINE in said
    assert concierge.CHIP_WORDS['next'] in said
    assert [p['tid'] for p in json.loads(store.get_setting(ra.PROMISES_KEY))] == [7]


def test_closing_taskuary_tells_each_promised_chat_once_what_happened():
    # "I will tell you here when it finishes" - then the window closed, the agent stopped, and the chat heard nothing (B3, 2026-10-11)
    from taskuary import terminal
    store, _c = armed_store()
    stopped = store.create_task({'Title': 'Fix the ledger export', 'Summary': 'x'}, 'owner')
    other = store.create_task({'Title': 'Draft the vendor reply', 'Summary': 'x'}, 'owner')
    with mock.patch.object(funnel, 'pile', return_value=pile({'key': f'agent:{stopped}', 'tid': stopped, 'lane': 'working'})):
        from_the_chat(store, stopped); from_the_chat(store, other)
    store.tag_task(stopped, terminal.INTERRUPTED, True, 'shutdown')
    with mock.patch.object(messengers, 'wa_send') as sent:
        assert ra.promises_closing(store) == 2
    said = [c.args[2] for c in sent.call_args_list]
    assert any(f'TQ-{stopped:04d} stopped before it finished' in t for t in said), said
    assert any(f'TQ-{other:04d}' in t and 'closing' in t for t in said), said
    assert json.loads(store.get_setting(ra.PROMISES_KEY)) == []
    with mock.patch.object(messengers, 'wa_send') as sent:
        assert ra.promises_closing(store) == 0                                   # said once
    sent.assert_not_called()


def test_send_to_agent_tapped_starts_the_agent_and_is_followed_up_once():
    """F3: Send to agent tapped on the phone made the general task and said "It's being worked on now" - on the desk the page
    asks the agent its question when the chat opens, and a phone has no page, so nothing started and nothing came back."""
    from taskuary import general, server
    store, _c = armed_store()
    t = store.create_task({'Title': 'Summarise the vendor contract', 'Kind': 'general', 'Status': 'open', 'Tags': server.ASK_TAG}, 'owner')
    m = store.add_message({'TaskId': t, 'Channel': 'email', 'Subject': 'Vendor contract', 'FromName': 'Gail Moreno',
                           'FromEmail': 'gail@northwind.example', 'BodyText': 'Can someone summarise this?', 'Status': 'open'})
    table = {'key': f'msg:{m}', 'kind': 'fyi', 'mid': m, 'title': 'Vendor contract', 'who': 'Gail Moreno'}
    store.set_setting(f'{ra.OFFERED_KEY}:whatsapp:{JID}', json.dumps(['Send to agent', 'Next']), 't')
    store.set_setting(f'{ra.ACTS_KEY}:whatsapp:{JID}', json.dumps({'Send to agent': {'t': 'verb', 'verb': 'regular_agent', 'key': f'msg:{m}'}}), 't')
    prop = {'id': 'op7', 'version': 1, 'status': 'proposed', 'verb': 'regular_agent', 'kind': 'task.create_from_message', 'key': f'msg:{m}',
            'settles': True, 'alts': [], 'params': {'kind': 'general'}}
    done = {**prop, 'status': 'done', 'outcome': {'taskId': t, 'ref': f'TQ-{t:04d}', 'chat': True}}
    session = mock.Mock(provider='assistant', model='m'); session.info.return_value = {}
    sent = []
    with mock.patch.object(server, 'store', store), \
         mock.patch.object(general, 'start_session', return_value=session) as start, \
         mock.patch('taskuary.general.dock_task', return_value=({'TaskId': 1}, False)), \
         mock.patch.object(concierge, 'restore_current', return_value=table), \
         mock.patch.object(concierge, 'say', side_effect=AssertionError('a pick never reaches the model')), \
         mock.patch.object(concierge, 'propose_direct', return_value=prop), \
         mock.patch.object(concierge, 'run_proposal', return_value=done), \
         mock.patch.object(concierge, 'surface', return_value={'say': 'Nothing else is waiting.', 'item': None}), \
         mock.patch.object(funnel, 'next_item', return_value=table), \
         mock.patch.object(funnel, 'pile', return_value=pile({'key': f'task:{t}', 'tid': t, 'lane': 'working'})), \
         mock.patch.object(messengers, 'wa_send', side_effect=lambda st, chat, body, connector_id=None, poll=None: sent.append(body)):
        ra.respond(store, 'whatsapp', JID, 'Send to agent', 1, poll=True)
        start.assert_not_called()                                   # it asks what first (the owner, 2026-10-23)...
        assert 'What should it do?' in sent[-1], sent
        ra.respond(store, 'whatsapp', JID, 'Send to agent', 1, poll=True)       # ...and its own button hands it over as it is
    start.assert_called_once()
    assert server.ASK_TAG not in str(store.get_task(t).get('Tags') or ''), 'the page would ask it again'
    assert any(ra.PROMISE_LINE in b for b in sent), sent
    assert [p['tid'] for p in json.loads(store.get_setting(ra.PROMISES_KEY))] == [t]
    assert look(store, [{'key': f'task:{t}', 'tid': t, 'lane': 'working'}])[0] == 0
    n, _s, out = look(store, [{'key': f'agent:{t}', 'tid': t, 'lane': 'report'}])          # its turn ended: the card comes back
    assert n == 1 and f'TQ-{t:04d} is back' in out.call_args.args[2]
    assert look(store, [{'key': f'agent:{t}', 'tid': t, 'lane': 'report'}])[0] == 0       # said once
