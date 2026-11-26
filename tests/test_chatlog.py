"""ONE LOG PER TASK (chatlog.py; the owner's approved redesign A, 2026-11-19). A task's chat is appended once, at the place each thing gets
then, and only what can change is updated in place. Invented people only."""
import json, sqlite3

import pytest

from taskuary import chatlog
from taskuary.store import MemoryStore


def world(kind='general'):
    s = MemoryStore()
    return s, s.create_task({'Title': 'Vendor review for Erin', 'Kind': kind, 'Status': 'in_progress'}, 'owner')


def test_an_item_is_appended_once_and_keeps_its_place_through_every_update():
    s, tid = world()
    a = chatlog.put(s, tid, 'line', 'l-1', {'text': 'Send Erin the review', 'at': 100.0})
    t = chatlog.put(s, tid, 'turn', 't:1', {'started': 101.0, 'text': ''}, state='working')
    assert chatlog.put(s, tid, 'line', 'l-1', {'text': 'Send Erin the review', 'at': 100.0}) == a, 'the same key is the same row'
    r0 = chatlog.rev(s, tid)
    chatlog.update(s, tid, 't:1', state='done', text='Sent it to Erin.')
    assert chatlog.rev(s, tid) > r0
    got = chatlog.read(s, tid, 'everything')['items']
    assert [(x['id'], x['kind'], x.get('state')) for x in got] == [('l-1', 'line', None), ('t:1', 'turn', 'done')]
    assert got[1]['text'] == 'Sent it to Erin.' and got[1]['started'] == 101.0
    assert s._rows('SELECT Id FROM chatlog WHERE Key=?', ('t:1',))[0]['Id'] == t, 'an update never moves it'


def test_what_he_saw_is_frozen_once_written():
    s, tid = world()
    chatlog.put(s, tid, 'line', 'l-1', {'text': 'Send Erin the review', 'at': 100.0})
    chatlog.put(s, tid, 'turn', 't:1', {'started': 101.0}, state='working')
    with pytest.raises(chatlog.Frozen): chatlog.update(s, tid, 'l-1', at=200.0)
    with pytest.raises(chatlog.Frozen): chatlog.update(s, tid, 't:1', started=150.0)
    chatlog.update(s, tid, 't:1', state='done', text='Done.')
    with pytest.raises(chatlog.Frozen): chatlog.update(s, tid, 't:1', text='Something else.')
    assert chatlog.get(s, tid, 't:1')['text'] == 'Done.'


def test_one_action_box_per_task_by_construction():
    s, tid = world()
    chatlog.put(s, tid, 'turn', 't:1', {'started': 1.0}, state='done')
    chatlog.put(s, tid, 'card', 'r:7', {'review': 7}, parent='t:1', state='pending')
    with pytest.raises(sqlite3.IntegrityError): chatlog.put(s, tid, 'card', 'r:8', {'review': 8}, parent='t:1', state='pending')
    chatlog.update(s, tid, 'r:7', state='sent')
    chatlog.put(s, tid, 'card', 'r:8', {'review': 8}, parent='t:1', state='pending')
    assert [(c['id'], c['state']) for c in chatlog.read(s, tid, 'everything')['items'][0]['cards']] == [('r:7', 'sent'), ('r:8', 'pending')]


def test_a_turn_at_work_draws_its_steps_and_holds_its_card_back():
    s, tid = world()
    chatlog.put(s, tid, 'turn', 't:1', {'started': 1.0}, state='working')
    chatlog.step(s, tid, 'sid1', 'call-1', {'k': 'tool', 'what': 'Read the vendor sheet'}, state='completed')
    chatlog.put(s, tid, 'card', 'r:7', {'review': 7}, parent='t:1', state='pending')
    t = chatlog.read(s, tid, 'everything')['items'][0]
    assert [x['what'] for x in t['fold']] == ['Read the vendor sheet'] and t['level'] == 'live' and t['cards'] == [], 'at work: its work counted, shut'
    chatlog.update(s, tid, 't:1', state='done')
    assert [c['id'] for c in chatlog.read(s, tid, 'everything')['items'][0]['cards']] == ['r:7']


def test_a_turns_run_is_to_the_last_thing_it_did_never_only_to_its_answer():
    """The owner, 2026-11-23: a head read "ran 1m 15s" while its steps went on for five minutes. The answer filed at 1m 15s ended the turn, and
    its session went on writing steps under it; a wake after it was a turn of its own, drawn under the same head. Each turn says how long it
    ran, to its last step (chatlog.run_of) - the page adds up the turns under one head (chatStream.ranUnder)."""
    s, tid = world()
    chatlog.put(s, tid, 'turn', 't:1', {'started': 100.0, 'ended': 175.0, 'text': 'Posted it; checking it went up.'}, state='done')
    for i, at in enumerate((150.0, 260.0, 400.0)): chatlog.put(s, tid, 'step', f's:1:{i}', {'k': 'tool', 'name': 'Bash', 'text': 'look'}, parent='t:1', at=at)
    chatlog.put(s, tid, 'turn', 't:2', {'started': 400.0, 'ended': 430.0, 'text': 'It is up.'}, state='done')
    chatlog.put(s, tid, 'turn', 't:3', {'started': 500.0}, state='working')
    got = {x['id']: x for x in chatlog.read(s, tid, 'everything')['items']}
    assert (got['t:1']['ran'], got['t:2']['ran']) == (300.0, 30.0), 'to its last step, never to the answer alone'
    assert 'ran' not in got['t:3'], 'one at work has its running clock'


def test_a_summary_block_streamed_across_steps_is_never_drawn():
    """Walk 2, 2026-11-21 (Codex): the reply streamed as said steps, its summary block opening in one and closing three later - each cleaned
    alone, the chat drew '"about": ...' and '_left": false}' as the agent's words."""
    s, tid = world()
    chatlog.put(s, tid, 'turn', 't:1', {'started': 1.0}, state='working')
    for n, t in enumerate(['I searched and found nothing.', 'Is it in another folder?\n[[TASKUARY-ASK]]\n\n[[TASKUARY-SUMMARY]]{"name": "Find", ',
                           '"about": "You asked where the plan is.", "did": "Searched,', '_left": false, "answer_is_result": false}[[/TASKUARY-SUMMARY]]']):
        chatlog.step(s, tid, 'sid1', f's{n}', {'k': 'said', 'text': t})
    chatlog.update(s, tid, 't:1', state='done')
    said = ' '.join(x['text'] for x in chatlog.read(s, tid, 'everything')['items'][0]['steps'] if x['k'] == 'said')
    assert 'Is it in another folder?' in said and '"about"' not in said and 'false}' not in said, said


def test_a_turn_heard_twice_keeps_the_start_it_was_first_heard_at():
    """CI, 2026-11-22: a press and his line taken in the same beat heard one turn twice, and the second hearing rewrote its start - the
    record of what he saw (chatlog.Frozen). Hearing a turn is append-once."""
    s, tid = world()
    chatlog.heard(s, tid, [('turn', '42')], 100.0)
    chatlog.heard(s, tid, [('turn', '42')], 105.0)
    rows = s.cx.execute("SELECT Body FROM chatlog WHERE TaskId=? AND Key='t:42'", (tid,)).fetchall()
    assert len(rows) == 1 and json.loads(rows[0][0])['started'] == 100.0


def test_a_step_after_his_line_goes_on_in_a_new_turn_under_it_with_its_files():
    """A MID-TURN LINE (the spec's stage 2 shape): Paula's line heard by a running turn - the rest of the turn is a new turn row under her
    line, and the file the step after it made is kept on that step."""
    s, tid = world()
    chatlog.put(s, tid, 'turn', 't:1', {'started': 1.0}, state='working')
    chatlog.step(s, tid, 'sid1', 'call-1', {'k': 'tool', 'what': 'Read the vendor sheet'})
    chatlog.put(s, tid, 'line', 'l-2', {'text': 'Paula says use the March export', 'by': 'Paula Vance', 'at': 5.0})
    chatlog.step(s, tid, 'sid1', 'call-2', {'k': 'tool', 'what': 'Wrote march-totals.csv', 'files': ['march-totals.csv']})
    chatlog.step(s, tid, 'sid1', 'call-1', {'k': 'tool', 'what': 'Read the vendor sheet', 'status': 'completed'})    # ...an update of the first
    items = chatlog.read(s, tid, 'everything')['items']
    assert [(x['kind'], x['id']) for x in items][:2] == [('turn', 't:1'), ('line', 'l-2')]
    assert items[2]['kind'] == 'turn' and items[2]['cont'] == 't:1' and items[2]['started'] > 1.0      # ...from its own time (decided 2026-11-20: never "working 18m" from the turn before)
    assert [x['what'] for x in items[0]['steps']] == ['Read the vendor sheet'] and items[0]['steps'][0]['status'] == 'completed'
    assert items[2]['fold'][0]['files'] == ['march-totals.csv'], 'still at work: its work under the count'


def test_the_roads_write_the_log_as_they_hand_over_a_mid_turn_line_and_its_answer():
    """DUAL-WRITE (stage 2): the hand-over (conversation.hear) appends what it took and the turn it began; a step the turn takes after his
    line is heard goes on in a new turn under that line; the answer filed ends that turn in place. Paula's line, invented."""
    from taskuary import conversation, general
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    chatlog.step(s, tid, 'sid1', 'call-1', {'k': 'tool', 'what': 'Read the vendor sheet'})
    general.wait_line(s, tid, 'Paula says use the March export', line_id='l-paula')
    conversation.hear(s, tid, ['l-paula'])
    chatlog.step(s, tid, 'sid1', 'call-2', {'k': 'tool', 'what': 'Wrote march-totals.csv', 'files': ['march-totals.csv']})
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Totals from the March export are in march-totals.csv.')
    items = chatlog.read(s, tid, 'everything')['items']
    assert [(x['kind'], x.get('state')) for x in items] == [('turn', 'done'), ('line', None), ('turn', 'done')]
    assert items[1]['id'] == 'l-paula' and items[1]['text'] == 'Paula says use the March export'
    assert items[2]['text'].startswith('Totals from the March export') and items[2]['steps'][0]['files'] == ['march-totals.csv']
    assert conversation.hear(s, tid, ['l-paula']) == 0 and len(chatlog.read(s, tid, 'everything')['items']) == 3, 'told once, written once'


def test_his_press_stands_where_he_made_it_and_his_stop_ends_the_turn_at_work_in_place():
    """A PRESS (the one hook in store.audit): at rest it is a line of the chat at once; pressed while a turn works it waits for the turn to
    hear it - except his stop, which ends that turn where it stands. A note Taskuary files while a turn works stands above the rest of it."""
    from taskuary import conversation, general
    s, tid = world()
    s.audit('task', tid, 'remind', 'owner', detail={'to': '2026-11-20 09:00:00'})
    conversation.hear(s, tid, turn=True)
    s.audit('task', tid, 'remind', 'owner', detail={})                 # ...pressed while it works: heard at its end
    s.audit('task', tid, 'stopped_turn', 'owner')
    items = chatlog.read(s, tid, 'everything')['items']
    assert [x['kind'] for x in items] == ['press', 'press'] and items[1]['stop'], items
    assert chatlog.get(s, tid, items[0]['id'])['text'].startswith('You set a reminder')
    assert [r['State'] for r in s._rows("SELECT State FROM chatlog WHERE TaskId=? AND Kind='turn'", (tid,))] == ['stopped']


# THE SAME TURN, EVERY ROAD (the owner's addition to the redesign, 2026-11-19): the API agent once showed no steps and Codex "Ran a command".
# One turn - a described command, a file written, an answer - fed as each road records it, reads the same at every level, general and coding.
CMD, DESC, FILE = 'ls vendors', 'List the vendor files', 'totals.csv'
ROADS = {
    'trace': [{'type': 'tool_call', 'name': 'Bash', 'detail': {'tool_call_id': 'c1', 'args': {'command': CMD, 'description': DESC}}},
              {'type': 'tool_result', 'name': 'Bash', 'detail': {'tool_call_id': 'c1', 'result': 'payworth.csv trainly.csv'}},
              {'type': 'tool_call', 'name': 'Write', 'detail': {'tool_call_id': 'c2', 'args': {'file_path': FILE, 'content': 'vendor,total'}}},
              {'type': 'tool_result', 'name': 'Write', 'detail': {'tool_call_id': 'c2', 'result': 'ok'}},
              {'type': 'progress', 'name': 'text', 'detail': 'Two vendor files; the totals are in totals.csv.'}],
    'acp': [{'sessionUpdate': 'tool_call', 'toolCallId': 'c1', 'kind': 'execute', 'title': CMD, 'rawInput': {'command': CMD, 'description': DESC},
             '_meta': {'claudeCode': {'toolName': 'Bash'}}},
            {'sessionUpdate': 'tool_call_update', 'toolCallId': 'c1', 'status': 'completed'},
            {'sessionUpdate': 'tool_call', 'toolCallId': 'c2', 'kind': 'edit', 'title': f'Write {FILE}', 'rawInput': {'file_path': FILE, 'content': 'vendor,total'},
             '_meta': {'claudeCode': {'toolName': 'Write'}}, 'content': [{'type': 'diff', 'path': FILE, 'oldText': '', 'newText': 'vendor,total'}]},
            {'sessionUpdate': 'tool_call_update', 'toolCallId': 'c2', 'status': 'completed'},
            {'sessionUpdate': 'agent_message_chunk', 'messageId': 'm1', 'content': {'type': 'text', 'text': 'Two vendor files; the totals are in totals.csv.'}}],
    'claude-log': [{'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 'c1', 'name': 'Bash', 'input': {'command': CMD, 'description': DESC}}]}},
                   {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'c1', 'content': 'payworth.csv trainly.csv'}]}},
                   {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 'c2', 'name': 'Write', 'input': {'file_path': FILE, 'content': 'vendor,total'}}]}},
                   {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'Two vendor files; the totals are in totals.csv.'}]}}],
}


@pytest.mark.parametrize('kind', ['general', 'coding'])
@pytest.mark.parametrize('level', ['summary', 'steps', 'everything'])
def test_the_same_turn_reads_the_same_on_every_road_at_every_level(kind, level):
    from taskuary import conversation, general
    seen = {}
    for road, events in ROADS.items():
        s = MemoryStore(); tid = s.create_task({'Title': 'Vendor totals', 'Kind': kind, 'Status': 'in_progress'}, 'owner')
        conversation.hear(s, tid, turn=True)
        for e in events: chatlog.feed(s, tid, 'sid1', road, e)
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Two vendor files; the totals are in totals.csv.')
        t = chatlog.read(s, tid, level)['items'][-1]
        core = lambda xs: [(x['k'], x.get('name'), x.get('text'), x.get('detail'), x.get('file')) for x in xs]
        seen[road] = (core(t['steps']), core(t.get('fold') or []), t.get('folded'), t['level'])
    assert seen['acp'] == seen['trace'] == seen['claude-log'], seen
    steps, fold, n, lvl = seen['trace']
    assert ('tool', 'Bash', DESC, CMD, None) in (fold if level == 'summary' else steps), 'its words, the real command beside them'
    assert (n, lvl) == ((2, 'summary') if level == 'summary' else (None, level))


def test_a_thread_joining_with_its_history_is_one_line_at_the_foot():
    """A THREAD THAT JOINED WITH OLD HISTORY (the owner's answer, 2026-11-19): Ray's thread of five - three from last week - joins a task mid-
    conversation. Nothing is drawn above his newest line: one line at the foot says whose thread joined and how many are earlier (it opens
    them), and the two that came after the chat's foot stand as they came."""
    import time as t_
    from taskuary import conversation, general
    from taskuary.store import set_owner
    s, tid = world()
    set_owner(s, 'Alex Doyle', 'alex@northwind.example')       # Ray is a colleague: a stranger's thread waits behind Trust, never joins the chat
    general.wait_line(s, tid, 'Check what Ray sent about the ledger', line_id='l-1'); conversation.hear(s, tid, ['l-1'], turn=True)
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Nothing from Ray yet.')
    foot = max(r['At'] for r in s._rows('SELECT At FROM chatlog WHERE TaskId=?', (tid,)))
    stamp = lambda ts: t_.strftime('%Y-%m-%d %H:%M:%S', t_.localtime(ts))
    for i, when in enumerate([foot - 7 * 86400, foot - 6 * 86400, foot - 5 * 86400, foot + 60, foot + 120]):
        s.add_message({'TaskId': tid, 'ExternalId': f'ray-{i}', 'Channel': 'email', 'FromName': 'Ray Colton', 'FromEmail': 'ray@northwind.example',
                       'ToEmail': 'alex@northwind.example', 'Subject': 'Ledger totals', 'ConversationId': 'conv-ray', 'SentAt': stamp(when),
                       'BodyText': f'Ledger note {i}. Ray', 'Status': 'routed'})
    s._exec("UPDATE message SET CreatedAt=SentAt WHERE TaskId=?", (tid,))
    items = chatlog.read(s, tid)['items']
    kinds = [(x['kind'], x['id'][:2]) for x in items]
    assert kinds[:2] == [('line', 'l-'), ('turn', 't:')], kinds
    assert kinds[2:] == [('arrival', 'j:'), ('arrival', 'm:'), ('arrival', 'm:')], kinds
    assert items[2]['head'] == "Ray Colton's thread joined (5 messages, 3 earlier)" and len(items[2]['thread']['mids']) == 3
    assert len(chatlog.read(s, tid)['items']) == 5, 'found once, written once'


def _rv(s, tid, mid=None, act=None, text='Hi Gail, you are invited. Alex'):
    import json
    if act: return s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent', 'Reason': f'held before it ran: {act}',
                                 'DraftText': json.dumps({'action': 'browser_act', 'sid': 'fx', 'site': 'portal.vendor.example', 'what': act, 'command': act})})
    return s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'Channel': 'email', 'DraftText': text})


def test_one_action_box_a_held_browser_step_with_the_reply_behind_it():
    """TQ-1435'S SHAPE (the owner's live task, 2026-11-19): a held browser step fronts the line, the reply to Gail behind it. The log holds ONE
    pending card - the step's, its line naming the reply - and the reply has no row to draw anywhere until the step is pressed."""
    from taskuary import conversation, general
    s, tid = world()
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'g1', 'Channel': 'email', 'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example',
                         'ToEmail': 'alex@northwind.example', 'Subject': 'Portal access?', 'BodyText': 'Can you get me in? Gail', 'Status': 'routed'})
    conversation.hear(s, tid, turn=True)
    act, reply = _rv(s, tid, act="Send Gail's invite on the vendor portal"), _rv(s, tid, mid)
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The invite waits on your press, then the reply to Gail.')
    items = chatlog.read(s, tid)['items']
    cards = [c for x in items for c in x.get('cards') or []]
    assert [(c['review'], c['status']) for c in cards] == [(act, 'pending')]
    # ...by name, as the mail knows her (the design walk, 2026-11-20: the line read 'next: the reply to gail@northwind.example')
    assert '1 of 2 · next: the reply to Gail Moreno' in cards[0]['line'] and chatlog.live_card(s, tid)['review'] == act
    s.decide_review(act, 'approved', None, 'owner')
    general.PRESSED.pop(tid, None)
    from taskuary import cardqueue
    cardqueue._SEEN.clear()
    items = chatlog.read(s, tid)['items']
    assert [(c['review'], c['status']) for x in items for c in x.get('cards') or []][0] == (act, 'approved'), 'pressed where it stood'


def test_a_card_pressed_after_later_turns_turns_sent_where_it_stood():
    """A CARD PRESSED AFTER LATER TURNS (stage 5): the reply raised in turn 1; two turns later he presses Send - the card turns sent in turn 1,
    and nothing moves."""
    from taskuary import cardqueue, conversation, general
    s, tid = world()
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'e1', 'Channel': 'email', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                         'ToEmail': 'alex@northwind.example', 'Subject': 'Review?', 'BodyText': 'Your review? Erin', 'Status': 'routed'})
    conversation.hear(s, tid, turn=True); rid = _rv(s, tid, mid, text='Hi Erin, the review is attached. Alex')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Drafted the reply to Erin.')
    chatlog.read(s, tid)
    for n in (2, 3):
        conversation.hear(s, tid, turn=True)                           # ...turns Taskuary woke (a check-back): nothing he wrote past it
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, f'Noted {n}.')
    chatlog.read(s, tid)
    where = s._rows("SELECT Id, Parent FROM chatlog WHERE TaskId=? AND Key=?", (tid, f'r:{rid}'))[0]
    s.decide_review(rid, 'approved', 'Hi Erin, the review is attached. Alex', 'owner'); cardqueue._SEEN.clear()
    items = chatlog.read(s, tid, 'everything')['items']
    first = next(x for x in items if x['kind'] == 'turn')
    assert [(c['review'], c['status']) for c in first['cards']] == [(rid, 'approved')]
    assert s._rows("SELECT Id, Parent FROM chatlog WHERE TaskId=? AND Key=?", (tid, f'r:{rid}'))[0] == where, 'nothing moved'


def test_a_card_pressed_on_its_tab_behind_the_front_stands_beside_its_run_never_in_the_turn_open_at_the_press():
    """THE CARD LINE (the owner, 2026-11-25): three posts raised in one turn are one card with a tab each. He opens the third's tab two turns
    later and posts it while the first still waits: its row goes beside the run's - the page draws the run there - never into the turn open
    at the press, which carried the one card down the chat (recorded: it jumped 250 px and lost the tab he was on). Invented posts."""
    from taskuary import cardqueue, conversation, general
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    ids = [s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent', 'Reason': 'the post you asked for',
                         'DraftText': json.dumps({'action': 'run_tool', 'type': t, 'text': 'We shipped the ledger export.'})}) for t in ('x_post', 'linkedin_post', 'reddit_post')]
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Three posts are set up.')
    chatlog.read(s, tid)
    home = s._rows("SELECT Parent FROM chatlog WHERE TaskId=? AND Key=?", (tid, f'r:{ids[0]}'))[0]['Parent']
    assert not s._rows("SELECT 1 AS x FROM chatlog WHERE TaskId=? AND Key=?", (tid, f'r:{ids[2]}')), 'held behind the front: no row of its own'
    for n in (2, 3):
        conversation.hear(s, tid, turn=True); s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, f'Noted {n}.')
    chatlog.read(s, tid)
    s.decide_review(ids[2], 'approved', None, 'owner'); cardqueue._SEEN.clear()
    chatlog.read(s, tid)
    assert s._rows("SELECT Parent FROM chatlog WHERE TaskId=? AND Key=?", (tid, f'r:{ids[2]}'))[0]['Parent'] == home
    [run] = cardqueue.tabs(s, cardqueue.state(s, tid))
    assert [(t['name'], t['done'], t['front']) for t in run] == [('X', False, True), ('LinkedIn', False, False), ('Reddit', True, False)]


def test_the_held_step_of_a_cards_browser_road_is_drawn_on_that_card_as_its_next_press():
    """Walk 22, 2026-11-25, both homes: X and LinkedIn posts; Post via the browser on the X card; he signs in, says "post without the picture",
    and the agent's final Post is held - joined to the X card he had already pressed, whose row read `approved`, so NOTHING could be pressed
    anywhere and both agents said a card waited. The step is that card's next press: the card waits again carrying it, no card of its own
    is drawn for it - held, set aside by his next line, or pressed - and its press ends the card."""
    from unittest import mock
    from taskuary import cardqueue, conversation, general, proposals
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    x, li = [s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent', 'Reason': 'the post you asked for',
                           'DraftText': json.dumps({'action': 'run_tool', 'type': t, 'text': 'We close the month in four days.'})}) for t in ('x_post', 'linkedin_post')]
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Two posts are set up.')
    chatlog.read(s, tid)
    with mock.patch.object(general, 'to_agent', return_value='woke'): assert proposals.via_browser(s, x, '')['ok']
    cards = lambda: {c['review']: c for i in chatlog.read(s, tid)['items'] for c in ([i] if i['kind'] == 'card' else i.get('cards') or [])}
    cardqueue._SEEN.clear()
    assert cards()[x]['status'] == 'approved' and not cards()[x].get('step'), 'handed: the agent has it, nothing of his to press yet'
    hold = lambda: proposals.queue(s, tid, {'action': 'browser_act', 'sid': 's1', 'args': ['click', '@e20'], 'command': 'agent-browser click @e20',
                                            'site': 'x.example', 'what': 'Publish your post on X', 'why': 'it speaks for you'}, 'agent')['reviewId']
    held = hold(); cardqueue._SEEN.clear()
    got = cards()
    assert got[x]['status'] == 'pending' and got[x]['step'] == {'review': held, 'what': 'Publish your post on X'}, got[x]
    assert held not in got and li not in got and chatlog.live_card(s, tid)['review'] == x, 'one card: the step is on it, never beside it'
    said = cardqueue.screen(s, tid)
    assert 'Waiting for his press now, drawn on the card he pressed' in said and 'Publish your post on X' in said and 'NOT done yet - do it' not in said, said
    # ...his next line sets the step aside as it does every waiting card: the card is handed again, and no greyed card of the step is drawn
    s.decide_review(held, 'superseded', None, 'taskuary', note=proposals.SET_ASIDE); cardqueue._SEEN.clear()      # ...as set_aside_drafts settles it
    got = cards()
    assert s.get_review(held)['Status'] == 'superseded' and held not in got and got[x]['status'] == 'approved' and not got[x].get('step'), got
    # ...the agent presses Post again: held anew, on the same card; his press runs it and the card is done - LinkedIn comes forward
    again = hold(); cardqueue._SEEN.clear()
    assert again != held and cards()[x]['step']['review'] == again
    s.decide_review(again, 'approved', None, 'owner'); assert cardqueue.done(s, tid, 'Posted on x.example') == [x]; cardqueue._SEEN.clear()
    got = cards()
    assert got[x]['status'] == 'approved' and not got[x].get('step') and again not in got and held not in got, got
    assert cardqueue.state(s, tid)['live'] == [got[li]['review']] if li in got else True


def test_a_tab_he_said_no_to_is_marked_so_never_as_one_that_went():
    """The card gallery, 2026-11-25: three emails in a line - one sent, the next dropped - and the dropped one's tab was ticked like the sent
    one. A card settled without going (his no, a press that failed) says so on its tab (`no`); one that went, or still waits, does not."""
    from taskuary import cardqueue, conversation, general
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    ids = [s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent', 'Reason': 'the post you asked for',
                         'DraftText': json.dumps({'action': 'run_tool', 'type': t, 'text': 'We shipped the ledger export.'})}) for t in ('x_post', 'linkedin_post', 'reddit_post')]
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Three posts are set up.')
    chatlog.read(s, tid)
    s.decide_review(ids[0], 'approved', None, 'owner'); s.decide_review(ids[1], 'rejected', None, 'owner'); cardqueue._SEEN.clear()
    [run] = cardqueue.tabs(s, cardqueue.state(s, tid))
    assert [(t['name'], t['done'], bool(t.get('no'))) for t in run] == [('X', True, False), ('LinkedIn', True, True), ('Reddit', False, False)]


def test_a_card_raised_the_second_before_its_turns_answer_waits_lit_in_that_turn():
    """The card gallery, 2026-11-25: three emails raised as one card at :49.99 by a turn whose answer was filed at :50.01, the task first read
    after (its chat frozen then - migrate). A stamp is a whole second, so the card read as older than its turn: it stood ABOVE the turn,
    and greyed as a version the turn had rewritten - while it still waited. It stands lit, in the turn that raised it; and a bulk card left
    standing alone (raised seconds before) waits lit where it is - it has no words of its own a later turn could rewrite. Invented people."""
    from datetime import datetime, timedelta
    from unittest import mock
    from taskuary import general, server
    from test_bulk_card import call
    def chat(gap):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Tell the three approvers', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        s.add_comment(tid, general.BRIEF_ACTOR, general.USER_TYPE, 'Tell Erin, Gail and Paula the portal goes live Monday.')
        with mock.patch.object(server, 'store', s):
            call(tid, 'propose', kind='email', why='one note to each approver',
                 items=[{'to': f'{w}@northwind.example', 'subject': 'The ledger portal is live Monday', 'text': f'Hello {w},\n\nIt is live Monday.\n\nAlex'}
                        for w in ('erin', 'gail', 'paula')])
        now = datetime.utcnow(); at = lambda d: f'{now - timedelta(seconds=d):%Y-%m-%d %H:%M:%S}'
        s._exec('UPDATE comment SET CreatedAt=? WHERE TaskId=?', (at(5), tid)); s._exec('UPDATE review SET CreatedAt=? WHERE TaskId=?', (at(gap), tid))
        cid = s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Three emails, one card.')
        s._exec('UPDATE comment SET CreatedAt=? WHERE CommentId=?', (at(0), cid))
        return [(x['kind'], x.get('status'), [c.get('status') for c in x.get('cards') or []]) for x in chatlog.serve(s, tid)['items']]
    assert chat(1) == [('turn', None, ['pending'])]
    assert chat(3) == [('card', 'pending', []), ('turn', None, [])]


def test_a_card_raised_during_its_tasks_first_read_stands_in_its_turn():
    """The card gallery, 2026-11-25: a sign-in asked on the agent's page, its turn answered, and the task first read after - its card was raised
    in that read, under the turn noted for it in the log the read then froze afresh, whose Id was the card's own by then: drawn nowhere."""
    from taskuary import general, workerstate as ws
    s = MemoryStore()
    tid = s.create_task({'Title': 'Download the October statement', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
    s.add_comment(tid, general.BRIEF_ACTOR, general.USER_TYPE, 'Get the October statement from the vendor portal.')
    ws.record(s, tid, 'run1', 'input_needed', request_id='signin:portal.vendor.example', text='Sign in to Vendor portal to continue', source='api')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The portal wants you signed in before I can download it.')
    assert [(x['kind'], [c.get('status') for c in x.get('cards') or []]) for x in chatlog.serve(s, tid)['items']] == [('turn', ['pending'])]


def test_a_tab_names_a_thing_as_its_card_writes_it():
    """The card gallery, 2026-11-25: the pull request's tab read "Northwind/ledger#31" over a card saying northwind/ledger#31 - a name is
    written as it is; only a phrase in his words ('Push') starts with a capital."""
    from taskuary import cardqueue, conversation, general
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    ids = [s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent', 'Reason': 'the agent proposes to merge it',
                         'DraftText': json.dumps(p)}) for p in ({'action': 'merge_pr', 'repo': 'northwind/ledger', 'number': 31, 'text': ''},
                                                              {'action': 'push', 'cwd': '.', 'why': 'the fix'})]
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Merge it, then push.')
    chatlog.read(s, tid)
    [run] = cardqueue.tabs(s, cardqueue.state(s, tid))
    assert run[0]['name'] == 'northwind/ledger#31' and run[1]['name'][:1].isupper(), run


def test_every_tool_call_is_one_row_in_plain_words_and_summary_folds_them_to_one_line():
    """"BETTER SHOWING WHAT TOOLS ARE RUN, BUT NOT A BILLION DETAILS" (the owner, 2026-11-19): each call one row of what it did and on what,
    its outcome in a few words, its output capped behind it; summary - one line that opens. ONE ROW PER CALL, ALWAYS (2026-11-23): the same
    call again is the page's to fold ("(3 times)", agentSteps.group, keyed by its first call) - never a row taken out under its key."""
    big = 'x' * 10000 + '\n4 passed in 0.2s'
    steps = [{'k': 'tool', 'name': 'Bash', 'text': 'pytest tests/test_totals.py', 'output': big},
             {'k': 'tool', 'name': 'Read', 'file': 'C:/work/board-data-asks.txt'},
             {'k': 'tool', 'name': 'Read', 'file': 'C:/work/board-data-asks.txt'},
             {'k': 'tool', 'name': 'Read', 'file': 'C:/work/board-data-asks.txt'},
             {'k': 'tool', 'name': 'WebSearch', 'args': {'query': 'printer prices'}},
             {'k': 'tool', 'name': 'WebFetch', 'args': {'url': 'https://www.uprinting.com/business-cards'}},
             {'k': 'said', 'text': 'Four tests pass; uprinting is cheapest.'}]
    rows = chatlog.tool_rows(steps)
    assert [(r.get('line'), r.get('outcome')) for r in rows[:6]] == [
        ('Ran pytest tests/test_totals.py', '4 passed'), *[('Read board-data-asks.txt', None)] * 3,
        ('Searched the web for printer prices', None), ('Opened uprinting.com', None)]
    assert rows[0]['size'] == len(big) and len(rows[0]['output']) < 3200, 'the output capped: its head and tail, and how big it was'
    t = chatlog.detailed({'kind': 'turn', 'state': 'done', 'text': 'Done.', 'steps': steps}, 'summary')
    assert [s['k'] for s in t['steps'] if s not in t['fold']] == ['said'] and t['folded'] == 6      # ...its one line is the page's (chatStream.foldLine)
    assert len(chatlog.detailed({'kind': 'turn', 'state': 'done', 'steps': steps}, 'everything')['steps']) == 7


def test_migration_freezes_what_he_saw_and_a_turn_at_work_goes_on_in_its_own_row(tmp_path, monkeypatch):
    """MIGRATION (the spec's §4): the list as last served is written as it stood, after a copy of the database is made; a turn at work keeps
    working in the same row across a restart; of two cards that stood lit at once the front stays and the other is held - one box."""
    from taskuary.store import SQLiteStore
    monkeypatch.setenv('TASKUARY_HOME', str(tmp_path))
    s = SQLiteStore(str(tmp_path / 'taskuary.db'))
    tid = s.create_task({'Title': 'Vendor review for Erin', 'Kind': 'general', 'Status': 'in_progress'}, 'owner')
    legacy = {'items': [{'id': 'l-1', 'kind': 'line', 'at': '2026-11-19 09:00:00', 'text': 'Review the vendor tool', 'files': []},
                        {'id': 't:l-1:0', 'kind': 'turn', 'state': 'done', 'text': 'Drafted both.', 'started': 1.0, 'steps': [{'k': 'tool', 'name': 'Read', 'file': 'tool.md'}],
                         'cards': [{'id': 'r:7', 'kind': 'card', 'review': 7, 'what': 'draft_reply', 'status': 'pending'},
                                   {'id': 'r:8', 'kind': 'card', 'review': 8, 'what': 'draft_reply', 'status': 'pending'}]},
                        {'id': 'l-2', 'kind': 'line', 'at': '2026-11-19 09:05:00', 'text': 'Also check the price', 'files': []},
                        {'id': 't:l-2:0', 'kind': 'turn', 'state': 'working', 'sid': 'sid9', 'text': '', 'started': 2.0, 'steps': []}]}
    import time as t_
    assert not chatlog.migrate(s, tid, legacy=legacy), 'nothing is frozen before the copy, which is made on its own thread - never in the read'
    end = t_.time() + 10
    while not chatlog.backed_up(s) and t_.time() < end: t_.sleep(0.05)
    assert chatlog.migrate(s, tid, legacy=legacy) and not chatlog.migrate(s, tid, legacy=legacy), 'once'
    assert s.get_setting('chatlog_backup', '') and (tmp_path / 'backups').exists(), 'a copy before anything was written'
    rows = {r['Key']: r['State'] for r in s._rows('SELECT Key, State FROM chatlog WHERE TaskId=?', (tid,))}
    assert (rows['r:7'], rows['r:8'], rows['t:l-2:0']) == ('pending', 'held', 'working')
    chatlog._FEEDS.clear()                                               # ...a restart in the middle: the road comes back and goes on
    chatlog.feed(s, tid, 'sid9', 'trace', {'type': 'progress', 'name': 'text', 'detail': 'The price is on the second page.'})
    t = s._rows("SELECT Id FROM chatlog WHERE Key='t:l-2:0'")[0]['Id']
    assert [r['Parent'] for r in s._rows("SELECT Parent FROM chatlog WHERE TaskId=? AND Kind='step' AND Src LIKE 'sid9:%'", (tid,))] == [t]


def test_the_page_reads_the_log_through_a_timeline_and_nothing_he_saw_moves():
    """THE READER SWITCH (stage 7): what the page reads is the log - a message, a turn with its reply card, his line, a restart in the middle,
    his Send and a second press. Every read keeps what the one before drew in its place (flow_breaks), and the card stands where it stood."""
    from taskuary import cardqueue, conversation, general
    from taskuary.store import set_owner
    s, tid = world()
    set_owner(s, 'Alex Doyle', 'alex@northwind.example')       # Erin is a colleague: a stranger's task draws no card until Trust
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'e1', 'Channel': 'email', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                         'ToEmail': 'alex@northwind.example', 'Subject': 'Review?', 'BodyText': 'Your review of the tool? Erin', 'Status': 'routed'})
    reads, was = [], None
    def look():
        nonlocal was
        cardqueue._SEEN.clear()
        got = chatlog.serve(s, tid)
        assert conversation.flow_breaks(got, was) == [], conversation.flow_breaks(got, was)
        was = got; reads.append([x['id'] for x in got['items']]); return got
    look()
    conversation.hear(s, tid, turn=True); look()
    rid = _rv(s, tid, mid, text='Hi Erin, the review is attached. Alex')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Drafted the reply to Erin.'); got = look()
    assert [c['review'] for x in got['items'] for c in x.get('cards') or [] if c['status'] == 'pending'] == [rid]
    general.wait_line(s, tid, 'Add that the pricing page is out of date', line_id='l-2'); conversation.hear(s, tid, ['l-2'], turn=True); look()
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Noted - the reply says so now.'); look()
    chatlog._FEEDS.clear()                                               # ...a restart in the middle
    look()
    s.decide_review(rid, 'approved', 'Hi Erin, the review is attached. Alex', 'owner'); got = look()
    s.decide_review(rid, 'approved', 'Hi Erin, the review is attached. Alex', 'owner'); look()      # ...pressed twice: nothing moves
    assert all(r[:len(a)] == a for a, r in zip(reads, reads[1:])), reads
    assert len({c['review'] for x in got['items'] for c in x.get('cards') or []}) <= 1


def test_codex_and_a_terminal_cli_log_write_their_steps_as_every_other_road():
    """EVERY BRAIN READS THE SAME (the owner's addition, 2026-11-19: Codex showed "Ran a command"): Codex's own log and a terminal CLI's log
    are written through the one door, each call one row in plain words - the command as he would type it, never a list's repr."""
    events = [{'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'shell', 'arguments': '{"command": ["bash", "-lc", "ls vendors"]}'}},
              {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Two vendor files.'}]}}]
    from taskuary import conversation, general
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    for e in events: chatlog.feed(s, tid, 'cx1', 'codex-log', e)
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Two vendor files.')
    t = chatlog.read(s, tid, 'everything')['items'][-1]
    tool = next(x for x in t['steps'] if x['k'] == 'tool')
    assert (tool['text'], tool['line']) == ('ls vendors', 'Ran ls vendors')
    chatlog.steps_of(s, tid, 'pty1', [{'k': 'tool', 'name': 'Bash', 'text': 'pytest -q', 'output': '3 passed in 1s'}, {'k': 'you', 'text': 'his line'}])
    rows = s._rows("SELECT Body FROM chatlog WHERE TaskId=? AND Src LIKE 'pty1:%'", (tid,))
    assert len(rows) == 1, 'his line is the hand-over\'s, never a step'


def test_what_waits_by_the_box_is_read_beside_the_log_never_drawn_twice():
    """STAGE 8: the reader says what waits for the agent itself - his line kept while nothing heard it yet - and an input is in one place:
    waiting, or in the chat once heard. The line of cards and the turn's state ride beside it."""
    from taskuary import conversation, general
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    general.wait_line(s, tid, 'Also the March numbers', line_id='l-wait')
    got = chatlog.serve(s, tid)
    assert [p['id'] for p in got['pending']] == ['l-wait'] and 'l-wait' not in [x['id'] for x in got['items']]
    assert set(got) >= {'rev', 'items', 'pending', 'working', 'asking', 'permissions', 'queue', 'hold', 'letters', 'published', 'ran'}
    conversation.hear(s, tid, ['l-wait'])
    got = chatlog.serve(s, tid)
    assert got['pending'] == [] and 'l-wait' in [x['id'] for x in got['items']]


def test_for_you_to_do_stays_on_the_turn_that_wrote_it_and_is_not_said_again():
    """"FOR YOU TO DO" IS THE TURN'S OWN (design round 5, I3): settled on the turn whose summary left it, kept there when he writes under it,
    never moved to the next turn, and not said again by a next turn that leaves the same."""
    import json as j
    from taskuary import conversation, general
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The vendor form is ready.')
    s.add_comment(tid, 'assistant', general.SUMMARY_TYPE, j.dumps({'about': 'the form', 'did': 'filled it', 'on_you': ['Sign the vendor form']}))
    first = [x for x in chatlog.serve(s, tid)['items'] if x['kind'] == 'turn'][0]
    assert first.get('on_you') and first['summary']['on_you'] == ['Sign the vendor form']
    general.wait_line(s, tid, 'Signed', line_id='l-2'); conversation.hear(s, tid, ['l-2'], turn=True)
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Thanks - filed.')
    s.add_comment(tid, 'assistant', general.SUMMARY_TYPE, j.dumps({'about': 'the form', 'did': 'filed it', 'on_you': ['Sign the vendor form']}))
    turns = [x for x in chatlog.serve(s, tid)['items'] if x['kind'] == 'turn']
    assert [bool(t.get('on_you')) for t in turns] == [True, False], 'kept on its own turn; the same words not said again'


def test_a_card_press_and_a_chat_read_on_two_threads_both_finish():
    """Walk 2, 2026-11-19: the server froze ~20 s after an Approve - a review's write put its card under whatever its caller held, and a read
    of the chat took the same locks the other way. A press and a read with steps written beside it, on two threads, both finish at once."""
    import threading, time as t_
    from taskuary import conversation, general
    s, tid = world()
    general.wait_line(s, tid, 'Send Erin the review', line_id='l-1'); conversation.hear(s, tid, ['l-1'], turn=True)
    done, stop = [], t_.time() + 2
    def press():
        while t_.time() < stop:
            rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'Channel': 'email', 'DraftText': 'Hi Erin, attached. Alex'})
            with s.lock: s.decide_review(rid, 'approved', 'Hi Erin, attached. Alex', 'owner')      # ...a press under the store's own lock
        done.append('press')
    def read():
        n = 0
        while t_.time() < stop:
            chatlog.step(s, tid, 'sid1', f'r{n}', {'k': 'said', 'text': f'step {n}'}); conversation.items(s, tid); n += 1
        done.append('read')
    ts = [threading.Thread(target=f, daemon=True) for f in (press, read)]
    for x in ts: x.start()
    for x in ts: x.join(8)
    assert sorted(done) == ['press', 'read'], f'a thread never finished: {done}'
    rest = conversation.items(s, tid)       # ...and at rest, every card the presses left is where it stood (chatlog.missing)
    assert chatlog.missing(s, tid, rest) == []


def test_a_task_search_and_a_chat_read_that_migrates_on_two_threads_both_finish():
    """Walk 3, 2026-11-19 (a py-spy dump of the freeze): a chat read checked `migrated` on the writer's connection without the store's lock,
    holding the GIL, while New's same-work check searched the open tasks on it - a query whose own function (tq_fold) needs the GIL. Neither
    moved. A search over many tasks and chat reads that freeze tasks into the log, on two threads, both finish."""
    import threading, time as t_
    from taskuary import conversation
    s, _ = world()
    tids = [s.create_task({'Title': f'Vendor review {i} for Erin', 'Summary': 'the ledger totals ' * 20, 'Kind': 'general', 'Status': 'open'}, 'owner')
            for i in range(150)]
    done, stop = [], t_.time() + 2
    def search():
        while t_.time() < stop: s.list_tasks(q='ledger totals')
        done.append('search')
    def read():
        for tid in tids:
            if t_.time() > stop: break
            conversation.items(s, tid)
        done.append('read')
    ts = [threading.Thread(target=f, daemon=True) for f in (search, read)]
    for x in ts: x.start()
    for x in ts: x.join(10)
    assert sorted(done) == ['read', 'search'], f'a thread never finished: {done}'


def test_a_reply_raised_empty_and_written_after_his_line_stands_under_the_turn_that_wrote_it():
    """WALK 8 (2026-11-20): Marcus asked for free times; the first turn asked the owner which (its reply raised empty, with what it needs), he
    answered, and the next turn wrote the letter - "drafted for your Send" - but its card stood in the first turn, above his line, where nobody
    looked. The card is the last thing of the turn that wrote its words. Invented people."""
    import time as t_
    from taskuary import conversation, general, wrapup
    from taskuary.store import set_owner
    s, tid = world()
    set_owner(s, 'Alex Doyle', 'alex@northwind.example')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'mr1', 'Channel': 'email', 'FromName': 'Marcus Reed', 'FromEmail': 'marcus@northwind.example',
                         'ToEmail': 'alex@northwind.example', 'Subject': 'Thursday', 'BodyText': 'Send me your free times Thursday? Marcus', 'Status': 'routed'})
    conversation.hear(s, tid, turn=True)
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'Channel': 'email', 'DraftText': '', 'Origin': 'triage'})
    s._exec('UPDATE review SET DraftNeeds=? WHERE ReviewId=?', ('Which Thursday times are you free?', rid))
    chatlog.advance_soon(s, tid, rid)
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Which Thursday times are you free?')
    chatlog.settled(); chatlog.read(s, tid)
    t_.sleep(1.1)
    general.wait_line(s, tid, '10-11am or 2-3pm', line_id='l-times'); conversation.hear(s, tid, ['l-times'], turn=True)
    assert wrapup.agent_reply(s, tid, 'Hi Marcus, 10-11am or 2-3pm Thursday. Alex', to='marcus@northwind.example')['review_id'] == rid
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The reply to Marcus is drafted for your Send.')
    chatlog.settled()
    from taskuary import cardqueue
    cardqueue._SEEN.clear()
    items = chatlog.read(s, tid)['items']
    at = {c['review']: i for i, x in enumerate(items) for c in x.get('cards') or []}
    assert [x['kind'] for x in items] == ['arrival', 'turn', 'line', 'turn'] and at.get(rid) == 3, (at, [x['kind'] for x in items])


@pytest.mark.parametrize('kind', ['general', 'coding'])
def test_a_reply_rewritten_in_place_by_the_next_turn_stands_under_that_turn(kind):
    """THE OWNER'S LIVE APP (2026-11-25: "why is there text after the card?"): one turn wrote the reply to a sender, the next - the agent going on
    by itself, nothing of his between - rewrote that same card in place, and the card stayed in the first turn with the second's words, the
    turn that wrote them drawn after it. A card whose words a later turn wrote is that turn's last thing - on a coding task exactly as on a chat
    task (the owner, 2026-11-25: "it should be exactly the same"): its chat is the same log. Invented people."""
    import time as t_
    from taskuary import cardqueue, conversation, general, wrapup
    from taskuary.store import set_owner
    s, tid = world(kind)
    set_owner(s, 'Alex Doyle', 'alex@northwind.example')
    s.add_message({'TaskId': tid, 'ExternalId': 'mr2', 'Channel': 'email', 'FromName': 'Marcus Reed', 'FromEmail': 'marcus@northwind.example',
                   'ToEmail': 'alex@northwind.example', 'Subject': 'Harness', 'BodyText': 'How do the tools fit together? Marcus', 'Status': 'routed'})
    conversation.hear(s, tid, turn=True)
    rid = wrapup.agent_reply(s, tid, 'Hi Marcus, the harness hands the model its tools. Alex', to='marcus@northwind.example')['review_id']
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'I drafted the reply to Marcus.')
    chatlog.settled(); chatlog.read(s, tid)
    t_.sleep(1.1)
    conversation.hear(s, tid, turn=True)
    assert wrapup.agent_reply(s, tid, 'Hi Marcus, the harness hands the model a menu of tools and skills. Alex', to='marcus@northwind.example')['review_id'] == rid
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'I updated the reply to Marcus with the skills.')
    chatlog.settled(); cardqueue._SEEN.clear()
    items = chatlog.read(s, tid)['items']
    at = {c['review']: i for i, x in enumerate(items) for c in x.get('cards') or []}
    assert [x['kind'] for x in items] == ['arrival', 'turn', 'turn'] and at.get(rid) == 2, (at, [x['kind'] for x in items])
    # ...AND WHAT IT SAID BEFORE STAYS IN THE FIRST TURN, greyed with its own words (the owner's plan, 2026-11-25): nothing he saw vanishes
    [old] = items[1].get('cards') or [None]
    assert old and old['review'] == rid and old['status'] == 'passed' and 'a menu of tools' not in old['was']['text'], old
    [new] = items[2]['cards']
    assert new['status'] == 'pending' and 'a menu of tools' in new['was']['text']
    chatlog.settled(); cardqueue._SEEN.clear()
    again = chatlog.read(s, tid)['items']
    assert [(c['id'], c['status']) for x in again for c in x.get('cards') or []] == [(old['id'], 'passed'), (new['id'], 'pending')], 'read again, it stays'


def test_a_turn_a_message_began_after_another_turn_keeps_why_it_began():
    """The coordinator's live shape (2026-11-25): Marcus's mail came in while nothing worked and was drawn at the foot; the turn begun next never
    heard it - it was typed into the session once that turn ended, and began the second, and nothing said what began it. What is drawn never
    moves (the mail stays where it came), and the turn it began keeps why it began: the message by id (data, drawn nowhere). Invented people."""
    from taskuary import conversation
    s, tid = world()
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'mr9', 'Channel': 'email', 'FromName': 'Marcus Reed', 'FromEmail': 'marcus@northwind.example',
                         'ToEmail': 'alex@northwind.example', 'Subject': 'Harness', 'BodyText': 'One more question. Marcus', 'Status': 'routed'})
    chatlog.came_in(s, tid)
    chatlog.put(s, tid, 'turn', 't:first', {'started': 1.0, 'text': 'Looked up the tools.'}, state='done')     # ...a turn that never heard it
    assert [x['kind'] for x in chatlog.read(s, tid)['items']] == ['arrival', 'turn']
    conversation.hear(s, tid, turn=True)
    items = chatlog.read(s, tid)['items']
    assert [x['kind'] for x in items] == ['arrival', 'turn', 'turn'], [x['kind'] for x in items]
    assert items[0]['id'] == f'm:{mid}' and items[2]['why'] == {'mail': [str(mid)]}, items[2]


def test_the_agents_own_words_are_the_question_the_marker_only_marks_the_wait():
    """WALK 8 (2026-11-20, decided that day): asked in its prose and again in its [[TASKUARY-ASK]], the turn asked Marcus's times twice. The
    marker sets the wait; its text is drawn only under a turn that said nothing of its own."""
    from unittest import mock
    from taskuary import conversation, general, taskstate
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'I cannot see your calendar. Which Thursday times work for you?')
    out = chatlog.read(s, tid)['items']
    ask = {'text': 'Which Thursday 26 November times are you free for the call?', 'request_id': 'r1', 'source': 'marker'}
    with mock.patch.object(taskstate, 'asking', return_value=ask):
        assert chatlog.beside(s, tid, out, False, None)['asking'].get('said') is True, 'its own words asked it: the marker text is not drawn again'
        bare = [{**x, 'text': '', 'steps': []} if x['kind'] == 'turn' else x for x in out]
        assert not chatlog.beside(s, tid, bare, False, None)['asking'].get('said'), 'a turn with no words: the marker text is the question'


def test_an_owed_replys_needs_line_is_said_once_by_the_one_rule_the_ask_follows():
    """WALK 8 (2026-11-20, decided: never duplicate): the turn asked Ray's times in its own words, and the empty reply under it asked them again
    on its card - with the app's own link written out. The card stays lit (the 11-13 ruling); its line goes where its turn said anything
    (turn_words, the ask's one rule), and a line it keeps never shows an address of the app's own."""
    from taskuary import conversation, general
    s, tid = world()
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'rc1', 'Channel': 'email', 'FromName': 'Ray Colton', 'FromEmail': 'ray@northwind.example',
                         'ToEmail': 'alex@northwind.example', 'Subject': 'Tuesday', 'BodyText': 'Free Tuesday? Ray', 'Status': 'routed'})
    conversation.hear(s, tid, turn=True)
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'Channel': 'email', 'DraftText': '', 'Origin': 'triage'})
    assert general.reply_needs(s, tid, summ={'on_you': ['Tell me your Tuesday times (Connect a calendar: #connector=outlook).']}) == 'Tell me your Tuesday times.'
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Which Tuesday times work for you?')
    chatlog.settled(); chatlog.read(s, tid)
    assert chatlog.card_said(s, tid, rid), 'its turn asked it in words: the card says it no more'
    assert chatlog.turn_words({'text': '', 'steps': []}) == '' and not chatlog.card_said(s, tid, 9999)


def test_a_turn_that_asks_him_carries_no_try_again_under_its_question():
    """The walk, 2026-11-21: a turn ended asking him to choose between two ways on, its summary asked for Try again, and Try again was the one
    button under the question - which answered neither. The question is that turn's move."""
    import json
    from unittest import mock
    from taskuary import conversation, general, taskstate
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The price page did not load. Should I put the estimate in as a placeholder, or wait?')
    s.add_comment(tid, 'assistant', general.SUMMARY_TYPE, json.dumps({'did': 'Looked up the price', 'on_you': [], 'retry': True}))
    out = chatlog.read(s, tid)['items']
    turn = lambda: next(x for x in out if x['kind'] == 'turn')
    assert (turn().get('summary') or {}).get('retry'), 'the summary asked for it'
    ask = {'text': 'Should I put the estimate in as a placeholder, or wait?', 'request_id': 'r1', 'source': 'marker'}
    with mock.patch.object(taskstate, 'asking', return_value=ask): chatlog.beside(s, tid, out, False, None)
    assert not (turn().get('summary') or {}).get('retry')


def test_a_row_written_this_beat_on_another_connection_is_updated_not_lost(tmp_path):
    """CI, three times on macOS 2026-11-22: a card press and a chat read on two threads (two connections) both found the card's row missing;
    the second insert failed on the key, the rest of its write was dropped and the card that waited on him stood nowhere. The key names a
    row for good: written meanwhile, it is updated in place."""
    from unittest import mock
    from taskuary.store import SQLiteStore
    db = str(tmp_path / 'race.db')
    a, b = SQLiteStore(db), SQLiteStore(db)
    tid = a.create_task({'Title': 'Pay the vendor', 'Kind': 'general', 'Status': 'open'}, 'owner')
    chatlog.put(a, tid, 'card', 'r:7', {'review': 7, 'what': 'slot'}, state='pending')
    real, seen = chatlog._row, []
    with mock.patch.object(chatlog, '_row', side_effect=lambda st, t, k: None if not seen and not seen.append(1) else real(st, t, k)):
        n = chatlog.put(b, tid, 'card', 'r:7', {'review': 7, 'what': 'slot', 'line': '1 of 1'}, state='pending')
    rows = [r for r in b.cx.execute("SELECT Id, Body FROM chatlog WHERE TaskId=? AND Key='r:7'", (tid,))]
    assert len(rows) == 1 and rows[0]['Id'] == n and '1 of 1' in rows[0]['Body']


# ── EVERY STEP BY THE AGENT'S OWN ID (the owner, 2026-11-23: adopt the open-source model - Zed, Toad, agent-shell key a row by the tool call) ──
def _rows(s, tid):
    return {r['Key']: (r['Id'], r['Rev'], json.loads(r['Body'])) for r in s._rows("SELECT Key, Id, Rev, Body FROM chatlog WHERE TaskId=? AND Kind='step' ORDER BY Id", (tid,))}


def test_a_step_is_its_agents_own_id_and_an_update_patches_that_row_alone():
    """A call announced with a generic title, words said while it runs, the call's own update, another call: each is ONE row keyed by the id the
    agent gave it - and an update touches its own row and no other (a re-reading of the whole turn by place rewrote them all)."""
    from taskuary import conversation
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    put = lambda u: chatlog.feed(s, tid, 'sid1', 'acp', u)
    put({'sessionUpdate': 'tool_call', 'toolCallId': 'toolu_1', 'kind': 'read', 'title': 'Read File', 'status': 'pending'})
    put({'sessionUpdate': 'agent_message_chunk', 'messageId': 'msg_1', 'content': {'type': 'text', 'text': 'Reading the vendor sheet.'}})
    before = _rows(s, tid)
    put({'sessionUpdate': 'tool_call_update', 'toolCallId': 'toolu_1', 'title': 'Read vendors.csv', 'locations': [{'path': 'C:/work/vendors.csv'}],
         'rawInput': {'file_path': 'C:/work/vendors.csv'}, 'status': 'completed'})
    put({'sessionUpdate': 'tool_call', 'toolCallId': 'toolu_2', 'kind': 'execute', 'title': 'ls vendors', 'rawInput': {'command': 'ls vendors'}})
    after = _rows(s, tid)
    assert list(after) == ['s:sid1:toolu_1', 's:sid1:m:msg_1', 's:sid1:toolu_2'], list(after)
    assert after['s:sid1:m:msg_1'][:2] == before['s:sid1:m:msg_1'][:2], 'the words were not touched by the call\'s update'
    assert after['s:sid1:toolu_1'][0] == before['s:sid1:toolu_1'][0] and after['s:sid1:toolu_1'][2]['title'] == 'Read vendors.csv'
    assert after['s:sid1:toolu_1'][2]['paths'] == ['C:/work/vendors.csv'] and after['s:sid1:toolu_1'][2]['tool_kind'] == 'read'


def test_a_call_that_ends_after_his_line_ends_in_its_own_row_above_it():
    """A command still running when Paula's line is heard: the rest of the turn goes on under her line, and the command's end is ITS row's -
    read again from that point on by place, its completion had nothing to land on and the row above spun for good."""
    from taskuary import conversation, general
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    for e in [{'type': 'prompt', 'name': 'prompt_sent_to_agent', 'detail': 'go'},
              {'type': 'tool_call', 'name': 'Bash', 'detail': {'tool_call_id': 'c1', 'args': {'command': 'pytest -q'}}}]: chatlog.feed(s, tid, 'sid1', 'trace', e)
    general.wait_line(s, tid, 'Paula says use the March export', line_id='l-paula'); conversation.hear(s, tid, ['l-paula'])
    chatlog.feed(s, tid, 'sid1', 'trace', {'type': 'tool_result', 'name': 'c1', 'detail': {'result': '3 passed'}})
    chatlog.feed(s, tid, 'sid1', 'trace', {'type': 'progress', 'name': 'text', 'detail': 'Tests pass; switching to the March export.'})
    items = chatlog.read(s, tid, 'everything')['items']
    assert [x['kind'] for x in items] == ['turn', 'line', 'turn']
    assert [(x['k'], x.get('status')) for x in items[0]['steps']] == [('tool', 'completed')] and items[0]['steps'][0]['output'] == '3 passed'
    assert [x['k'] for x in items[2]['steps']] == ['said']


def test_an_api_agent_turn_and_an_acp_turn_write_the_same_rows():
    """ONE RECORD SHAPE FOR EVERY AI (the owner, 2026-11-23: "Does this work for both ACP and HIPAA AI or any AI we use?"): the API agent's own
    tool loop (apiagent.turn, the HIPAA AI card's road) and an ACP agent doing the same work write one row per call keyed by its call id, each
    with its input, its output and - for a file it wrote - its diff, and its words as their own row; nothing on either road is a second shape."""
    from unittest import mock
    from taskuary import apiagent, conversation, general
    said = 'Two vendor files; the totals are in totals.csv.'
    def api(s, tid):
        steps = iter([{'role': 'assistant', 'content': None, 'tool_calls': [
                           {'id': 'call_1', 'type': 'function', 'function': {'name': 'run_command', 'arguments': '{"command": "ls vendors"}'}},
                           {'id': 'call_2', 'type': 'function', 'function': {'name': 'file_write', 'arguments': '{"path": "totals.csv", "text": "vendor,total"}'}}]},
                      {'role': 'assistant', 'content': said}])
        class Brain:
            def chat(self, msgs, tools, max_tokens, **kw): return next(steps)
        feed = lambda kind, name, detail=None: chatlog.feed(s, tid, 'sid1', 'trace', {'type': kind, 'name': name, 'detail': detail})
        with mock.patch.object(apiagent, 'run_tool', side_effect=lambda st, t, sid, name, a: 'payworth.csv trainly.csv' if name == 'run_command' else 'ok'):
            assert apiagent.turn(Brain(), s, tid, 'sid1', 'sys', 'go', 500, trace=feed) == said
        feed('progress', 'text', said)
    def acp(s, tid):
        for u in [{'sessionUpdate': 'tool_call', 'toolCallId': 'call_1', 'kind': 'execute', 'title': 'ls vendors', 'rawInput': {'command': 'ls vendors'}},
                  {'sessionUpdate': 'tool_call_update', 'toolCallId': 'call_1', 'status': 'completed',
                   'content': [{'type': 'content', 'content': {'type': 'text', 'text': 'payworth.csv trainly.csv'}}]},
                  {'sessionUpdate': 'tool_call', 'toolCallId': 'call_2', 'kind': 'edit', 'title': 'Write totals.csv', 'locations': [{'path': 'totals.csv'}],
                   'rawInput': {'path': 'totals.csv'}, 'content': [{'type': 'diff', 'path': 'totals.csv', 'oldText': '', 'newText': 'vendor,total'}]},
                  {'sessionUpdate': 'tool_call_update', 'toolCallId': 'call_2', 'status': 'completed', 'content': [{'type': 'content', 'content': {'type': 'text', 'text': 'ok'}}]},
                  {'sessionUpdate': 'agent_message_chunk', 'messageId': 'm1', 'content': {'type': 'text', 'text': said}}]:
            chatlog.feed(s, tid, 'sid1', 'acp', u)
    seen = {}
    for road, run in (('api', api), ('acp', acp)):
        s, tid = world(); conversation.hear(s, tid, turn=True)
        run(s, tid)
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, said)
        t = chatlog.read(s, tid, 'everything')['items'][-1]
        seen[road] = ([(x['k'], x.get('status'), x.get('output'), x.get('file'), [p['new'] for p in (x.get('edit') or {}).get('parts') or []]) for x in t['steps']],
                      [k.rsplit('.', 1)[-1].rsplit(':', 1)[-1] for k in _rows(s, tid) if ':m:' not in k])
    assert seen['api'] == seen['acp'], seen
    assert seen['acp'][1] == ['call_1', 'call_2'], 'each row keyed by its own call id'


# ── WORDS STAY WHERE THEY WERE SAID (the owner, 2026-11-23: "the live layout IS the finished layout") ──────────────────────────────────
def test_the_words_it_streamed_stay_its_rows_once_the_answer_is_filed_and_only_the_rest_of_the_answer_is_drawn():
    """A turn says a line, works, and streams its answer; the answer is filed. Its rows as they stood while it worked are its rows filed -
    nothing taken out of them, nothing moved - and of the filed answer only what they did not say is drawn under them (`tail`): here nothing."""
    from taskuary import conversation, general
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    say = lambda mid, t: chatlog.feed(s, tid, 'sid1', 'acp', {'sessionUpdate': 'agent_message_chunk', 'messageId': mid, 'content': {'type': 'text', 'text': t}})
    say('m1', 'Checking the vendor sheet first.')
    chatlog.feed(s, tid, 'sid1', 'acp', {'sessionUpdate': 'tool_call', 'toolCallId': 'c1', 'kind': 'read', 'title': 'Read vendors.csv', 'status': 'completed'})
    say('m2', 'Payworth is cheapest at $40 a seat.'); say('m2', '\n\nShall I draft the reply to Erin?')
    chatlog.flush(s, tid)
    live = [x['id'] for x in chatlog.read(s, tid, 'summary')['items'][-1]['steps']]
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Payworth is cheapest at $40 a seat.\n\nShall I draft the reply to Erin?')
    t = chatlog.read(s, tid, 'summary')['items'][-1]
    assert [x['id'] for x in t['steps']] == live and [x['k'] for x in t['steps']] == ['said', 'tool', 'said'], 'the same rows, in place'
    assert t['tail'] == '' and t['text'].startswith('Payworth'), 'the answer is not drawn a second time; its words are still the turn\'s'


def test_words_held_behind_a_first_token_are_written_once_they_settle_while_the_agent_thinks():
    """His live chat, 2026-11-25: "I", then 10-20 s of Thinking, then the rest. The message's first token was written at once, the rest of its
    sentence came a beat later and was held for the next thing the agent did - and it reasoned, then wrote a tool call's input, for seconds."""
    import time
    from taskuary import conversation
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    say = lambda u: chatlog.feed(s, tid, 'sid1', 'acp', u)
    say({'sessionUpdate': 'agent_message_chunk', 'messageId': 'm1', 'content': {'type': 'text', 'text': 'I'}})
    say({'sessionUpdate': 'agent_message_chunk', 'messageId': 'm1', 'content': {'type': 'text', 'text': '’ll check the vendor sheet first.'}})
    say({'sessionUpdate': 'agent_thought_chunk', 'content': {'type': 'text', 'text': 'Which sheet is newest?'}})
    said = lambda: [x.get('text') for x in chatlog.read(s, tid, 'everything')['items'][-1]['steps'] if x['k'] == 'said']
    assert said() == ['I'], 'the first token is drawn at once'
    end = time.time() + 3
    while said() != ['I’ll check the vendor sheet first.'] and time.time() < end: time.sleep(0.05)
    assert said() == ['I’ll check the vendor sheet first.'], 'nothing else came, and the sentence is whole within a beat'


def test_a_message_pushed_as_it_streams_reads_as_the_turn_reads_it_its_repeated_opener_said_once():
    """Walk 21 (S7, Codex): "I see you confirmed 2 p.m. with Erin." - a step - then the answer opening on that sentence again. A read of the turn
    said it once; the row pushed to the open chat as it streamed was read alone, and the open chat drew the sentence twice."""
    from taskuary import conversation, live
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    said = 'I see you confirmed 2 p.m. with Erin and told her you’d move the invite.'
    say = lambda mid, t: chatlog.feed(s, tid, 'sid1', 'acp', {'sessionUpdate': 'agent_message_chunk', 'messageId': mid, 'content': {'type': 'text', 'text': t}})
    say('m1', said)
    chatlog.feed(s, tid, 'sid1', 'acp', {'sessionUpdate': 'tool_call', 'toolCallId': 'c1', 'kind': 'other', 'title': 'Marked the reply as not needed', 'status': 'completed'})
    say('m2', f'{said}\n\nI marked the reply as no longer needed.')
    chatlog.flush(s, tid)
    n = s._one("SELECT Id FROM chatlog WHERE TaskId=? AND Key=?", (tid, 's:sid1:m:m2'))['Id']
    assert chatlog.pushed(s, tid, n)['step']['text'] == 'I marked the reply as no longer needed.'
    assert [x.get('text') for x in chatlog.read(s, tid, 'everything')['items'][-1]['steps'] if x['k'] == 'said'] == [said, 'I marked the reply as no longer needed.']


def test_the_answer_draws_only_what_its_words_did_not_say_a_file_by_its_name_or_its_path():
    from taskuary.conversation import unsaid
    path = 'C:\\Users\\alex\\AppData\\Local\\Temp\\home\\scratch\\outputs\\TQ-0003\\Wellness_Flyer.pdf'
    said = [{'k': 'said', 'text': f'Created the one-page flyer at `{path}` and showed it in the chat.'}]
    assert unsaid('Created the one-page flyer at `Wellness_Flyer.pdf` and showed it in the chat.', said) == ''
    report, after, draft = 'My recommendation is to send Erin alone.', "If you'd rather send both, tell me.", 'Hi Erin,\n\nYes, we should go.\n\nAlex Doyle'
    assert unsaid(f'{report}\n\n{draft}\n\n{after}', [{'k': 'said', 'text': f'{report}\n\n{after}'}]) == draft, 'only what the stream left out'
    assert unsaid('Two vendor files.', []) == 'Two vendor files.' and unsaid('Two vendor files.', [{'k': 'tool'}]) == 'Two vendor files.'


def test_a_permission_asked_is_its_calls_update_with_the_agents_options_and_clears_when_it_runs():
    """THE ASK BELONGS TO THE CALL'S ROW (the ACP spec: a request_permission's toolCall IS that call's update; Zed draws it in the call's card):
    Codex announces a read with no input and asks for it with the input and its own kind - the ask fills only what the call left out, the row
    carries the agent's options while it waits, and they are gone from it once the call runs."""
    from taskuary import acp, conversation, permissions
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    put = lambda u: chatlog.feed(s, tid, 'sid1', 'acp', u)
    put({'sessionUpdate': 'tool_call', 'toolCallId': 'call_9', 'kind': 'read', 'title': 'Read', 'status': 'pending'})
    put(acp.asked_update({'toolCall': {'toolCallId': 'call_9', 'kind': 'execute', 'title': "powershell.exe -Command 'Get-Content notes.md'",
                                       'rawInput': {'command': ['powershell.exe', '-Command', 'Get-Content notes.md']}},
                          'options': [{'optionId': 'ok', 'name': 'Yes', 'kind': 'allow_once'}, {'optionId': 'no', 'name': 'No', 'kind': 'reject_once'}]}))
    row = lambda: next(x for x in chatlog.read(s, tid, 'everything')['items'][-1]['steps'] if x['k'] == 'tool')
    r = row()
    assert (r['title'], r['tool_kind'], r['call']) == ('Read', 'read', 'call_9'), 'what the call said stands; the ask only fills its gaps'
    assert r['text'] == 'Get-Content notes.md' and [o['name'] for o in r['ask']] == ['Yes', 'No'], r
    put({'sessionUpdate': 'tool_call_update', 'toolCallId': 'call_9', 'status': 'in_progress'})
    assert not row().get('ask'), 'answered and running: nothing waits on the row'
    # ...and a request put to him names that call, so the page draws its buttons on that row (chatStream.askOn)
    with permissions._LOCK: permissions.PENDING['t-row'] = {'id': 't-row', 'tid': tid, 'store': s, 'req': permissions.normal({'call': 'call_9', 'tool': 'Bash'}),
                                                           'g': 'g', 'rid': 'r', 'sid': 'sid1', 'at': '2026-11-23 10:00:00', 'until': '2026-11-23 10:05:00'}
    try: assert [p['call'] for p in permissions.pending(tid, s)] == ['call_9']
    finally: permissions.PENDING.pop('t-row', None)


def test_a_plan_is_one_row_replaced_whole_and_the_sessions_state_is_no_row():
    """THE PLAN IS ONE OBJECT (the ACP spec: every plan update carries the whole list, and the client replaces it): a run's plans - an ACP
    agent's, or claude's TodoWrite on the argv road - are one row, replaced in place where it first stood; the newer plan_update by its planId.
    Commands, mode and usage are the session's state (acp.ACPClient.state), never a line of the chat."""
    from taskuary import acp, conversation
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    entries = lambda *st: [{'content': c, 'status': x} for c, x in zip(('Read the ledger', 'Fix the tax line'), st)]
    chatlog.feed(s, tid, 'sid1', 'acp', {'sessionUpdate': 'plan', 'entries': entries('in_progress', 'pending')})
    chatlog.feed(s, tid, 'sid1', 'acp', {'sessionUpdate': 'agent_message_chunk', 'messageId': 'm1', 'content': {'type': 'text', 'text': 'Reading.'}})
    chatlog.feed(s, tid, 'sid1', 'acp', {'sessionUpdate': 'plan', 'entries': entries('completed', 'in_progress')})
    for k in ('available_commands_update', 'current_mode_update', 'usage_update'): chatlog.feed(s, tid, 'sid1', 'acp', {'sessionUpdate': k, 'availableCommands': []})
    for todo in ('pending', 'completed'):
        chatlog.feed(s, tid, 'sid2', 'trace', {'type': 'tool_call', 'name': 'TodoWrite', 'detail': {'tool_call_id': f't-{todo}', 'args': {'todos': [{'content': 'Send it', 'status': todo}]}}})
    chatlog.feed(s, tid, 'sid1', 'acp', {'sessionUpdate': 'plan_update', 'planId': 'pl-1', 'entries': entries('pending', 'pending')})
    chatlog.feed(s, tid, 'sid1', 'acp', {'sessionUpdate': 'plan_update', 'planId': 'pl-1', 'entries': entries('completed', 'completed')})
    steps = chatlog.read(s, tid, 'everything')['items'][-1]['steps']
    assert [x['k'] for x in steps] == ['plan', 'said', 'plan', 'plan'], 'one row per plan, where it first stood; no row of the session\'s state'
    assert [i['status'] for i in steps[0]['items']] == ['completed', 'in_progress'] and steps[2]['items'] == [{'text': 'Send it', 'status': 'completed'}]
    assert [i['status'] for i in steps[3]['items']] == ['completed', 'completed']
    c = object.__new__(acp.ACPClient); c.state, c.options, c.on_update = {}, [], None
    c._notified({'method': 'session/update', 'params': {'update': {'sessionUpdate': 'available_commands_update', 'availableCommands': [{'name': 'compact'}]}}})
    c._notified({'method': 'session/update', 'params': {'update': {'sessionUpdate': 'current_mode_update', 'currentModeId': 'plan'}}})
    c._notified({'method': 'session/update', 'params': {'update': {'sessionUpdate': 'usage_update', 'used': 1200, 'size': 200000}}})
    assert c.state == {'commands': [{'name': 'compact'}], 'mode': 'plan', 'usage': {'used': 1200, 'size': 200000}}


def test_a_plan_updated_after_his_line_is_drawn_under_it_and_the_turn_above_keeps_its_own():
    """A PLAN IS THE TURN'S THAT LAST UPDATED IT: one ACP session keeps its plan across turns, and its next update - after his line - redrew the
    row where it first stood, ABOVE that line. The newest plan stands in the newest turn; the turn above keeps the plan as it stood there."""
    from taskuary import conversation, general
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    plan = lambda *st: chatlog.feed(s, tid, 'sid1', 'acp', {'sessionUpdate': 'plan', 'entries': [
        {'content': c, 'status': x} for c, x in zip(('Read the ledger', 'Fix the tax line'), st)]})
    plan('in_progress', 'pending'); plan('completed', 'in_progress')
    general.wait_line(s, tid, 'Gail says the tax line is fine', line_id='l-gail'); conversation.hear(s, tid, ['l-gail'])
    plan('completed', 'completed'); plan('completed', 'completed')
    items = chatlog.read(s, tid, 'everything')['items']
    assert [x['kind'] for x in items] == ['turn', 'line', 'turn'], [x['kind'] for x in items]
    st = lambda t: [[i['status'] for i in x['items']] for x in t['steps'] if x['k'] == 'plan']
    assert st(items[0]) == [['completed', 'in_progress']], 'the turn above keeps the plan as it stood there, replaced in place within it'
    assert st(items[2]) == [['completed', 'completed']], 'the newest plan is under his line, once'
    # ...and the same rule on a session's own record read whole (conversation.acp_steps)
    up = lambda x: {'sessionUpdate': 'plan', 'entries': [{'content': 'Fix the tax line', 'status': x}]}
    got = conversation.acp_steps([up('pending'), up('in_progress'), {'sessionUpdate': 'user_message_chunk', 'content': {'type': 'text', 'text': 'Gail says fine'}},
                                  up('completed'), up('completed')])
    assert [(x['k'], x.get('items', [{}])[0].get('status')) for x in got] == [('plan', 'in_progress'), ('you', None), ('plan', 'completed')]


def test_a_row_is_pushed_to_the_open_chat_as_it_is_written():
    """THE WORDS STREAM INTO THEIR ROW (the owner, 2026-11-23): each write of a row goes out on the task's run-tail with the row as a read
    serves it and the turn it stands in - the page patches it in place (chatStream.patchSteps), never waiting on a 600 ms read."""
    from taskuary import conversation, live
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    tab = object(); live.attach(tab)
    try:
        chatlog.feed(s, tid, 'sid1', 'acp', {'sessionUpdate': 'tool_call', 'toolCallId': 'c1', 'kind': 'execute', 'title': 'pytest -q', 'status': 'in_progress'})
        chatlog.feed(s, tid, 'sid1', 'acp', {'sessionUpdate': 'agent_message_chunk', 'messageId': 'm1', 'content': {'type': 'text', 'text': 'Running the suite.'}})
        got = live._pending['run-tail']['steps']
    finally: live.reset()
    turn = chatlog.read(s, tid, 'everything')['items'][-1]
    assert [(p['tid'], p['turn'], p['step']['id']) for p in got] == [(tid, turn['id'], 's:sid1:c1'), (tid, turn['id'], 's:sid1:m:m1')]
    assert got[0]['step']['line'] and got[1]['step']['text'] == 'Running the suite.', 'in the read\'s own shape'


def test_a_check_back_made_as_the_turn_filed_is_said_under_that_turn():
    """Walk 18 (L4b): restarted 5 s into its turn, the agent's check_back call never reached the app; the agent wrote the check-back was "not
    scheduled", and the app made the call as the turn filed - the chip read "Checks back" beside words saying it did not. What the app did
    stands under the turn as its own line, once, from the state it set (checkback.of_task) - below the answer that ended the turn."""
    from taskuary import agenttools, checkback, remind
    s, tid = world()
    chatlog.put(s, tid, 'turn', 't:1', {'started': 101.0}, state='working')
    call = [{'type': 'tool_call', 'name': 'mcp__taskuary__check_back',
             'detail': {'args': {'when': '2026-11-26 07:00:00', 'what': 'Dana sent the corrected quote'}}}]
    late = agenttools.made_late(s, tid, call, set())
    chatlog.update(s, tid, 't:1', state='done', text='The Thursday check-back is therefore not scheduled.')      # ...its answer ends the turn (general._file)
    chatlog.made_late(s, tid, late); chatlog.made_late(s, tid, late)
    cb = checkback.of_task(s.get_task(tid))
    got = chatlog.read(s, tid, 'everything')['items']
    assert [x['kind'] for x in got] == ['turn', 'note'], 'one line, under the turn, never splitting it'
    assert f"set for {remind.when(cb['at'])}: Dana sent the corrected quote" in got[1]['text']
    assert agenttools.made_late(s, tid, [], set()) == ''


def test_an_answer_filed_is_never_read_without_its_turn():
    """Windows CI, 2026-11-24: an answer's comment was written, and its turn's row a beat later (chatlog.answered) - a read at rest in that
    beat held an answer filed in no turn (chatlog.missing). Filing one is one step under the store's lock: a read waits for both."""
    import threading
    from unittest import mock
    from taskuary import conversation, general
    s, tid = world()
    general.wait_line(s, tid, 'Send Erin the review', line_id='l-1'); conversation.hear(s, tid, ['l-1'], turn=True)
    conversation.items(s, tid)                  # ...read once: its log is the record from here
    real, between, go, gaps = chatlog.answered, threading.Event(), threading.Event(), []
    def slow(*a, **k): between.set(); go.wait(5); return real(*a, **k)
    def read(): gaps.extend(chatlog.missing(s, tid, conversation.items(s, tid)))
    with mock.patch.object(chatlog, 'answered', slow):
        w = threading.Thread(target=lambda: s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Sent Erin the review.'), daemon=True); w.start()
        assert between.wait(5)
        r = threading.Thread(target=read, daemon=True); r.start(); r.join(0.5)
        go.set(); w.join(5); r.join(5)
    assert not r.is_alive() and gaps == [], gaps


def test_a_card_raised_after_his_newest_line_stands_under_that_line_never_as_a_tab_of_the_card_above_it():
    """Walk 24 (2026-11-25, all three roads): a post waited; the agent asked a question; he answered (an answer greys no card); the turn his
    answer began raised a second card - told "it stands as its card under your answer" - and it became tab 2 of the card that stood ABOVE his
    answer, with nothing to press under his newest line; when the first was pressed the one card came down the chat. A run never crosses his
    line: the second is its own card in the turn that raised it, both wait for his press, and a press moves nothing. Invented posts."""
    import time
    from unittest import mock
    from taskuary import cardqueue, general, selfclose, taskstate
    s, tid = world()
    raised = {}
    def turn(said, raise_, answer):
        "His line and the turn it starts, on the chat's own road: mid-turn the agent's card is raised, then it answers."
        def brain(system, user, **kw):
            time.sleep(1.1)                       # ...a model's answer takes longer than a stamp's one second: the card is raised after his line
            raised[said] = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent', 'Reason': 'the post you asked for',
                                         'DraftText': json.dumps({'action': 'run_tool', 'type': raise_, 'text': 'Our AP team closed October in four days.'})})
            return answer
        with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')): sess = general.GeneralSession(s, tid)
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=brain): sess.send_prompt(said)
    turn('Post on LinkedIn that we closed October in four days.', 'linkedin_post', f'The post is set up. {selfclose.ASK_MARKER} Shall I put it on Bluesky too? | Yes | No')
    post = raised['Post on LinkedIn that we closed October in four days.']
    assert taskstate.open_question(s, tid) and s.get_review(post)['Status'] == 'pending'
    time.sleep(1.1)
    turn('Yes', 'bluesky_post', 'The Bluesky post is set up.')
    mail = raised['Yes']
    assert s.get_review(post)['Status'] == 'pending', 'his answer to the question greys no card'
    q = cardqueue.state(s, tid)
    assert [[u['rids'] for u in r] for r in q['runs']] == [[[post]], [[mail]]], 'his answer parts the two: each is its own card'
    assert (q['live'], q['fronts']) == ([post], [[mail]])
    assert [[(t['key'], t['front']) for t in r] for r in cardqueue.tabs(s, q)] == [[(str(mail), True)]], 'the later card alone - no tabs with the one above'
    items = chatlog.read(s, tid, 'everything')['items']
    order = [(x['kind'], [c['review'] for c in x.get('cards') or []] if x['kind'] == 'turn' else x.get('text')) for x in items if x['kind'] in ('line', 'turn')]
    assert order[-3:] == [('turn', [post]), ('line', 'Yes'), ('turn', [mail])], order
    assert [c['status'] for x in items if x['kind'] == 'turn' for c in x.get('cards') or []] == ['pending', 'pending'], 'both wait for his press'
    told = cardqueue.screen(s, tid)
    assert told.count('Waiting for his press now') == 2 and 'tab of the same card' not in told, told
    # ...and his press on the one above moves nothing: the email is the one card left, where it stood
    where = lambda: s._rows("SELECT Id, Parent FROM chatlog WHERE TaskId=? AND Key=?", (tid, f'r:{mail}'))[0]
    was = where()
    s.decide_review(post, 'rejected', None, 'owner'); cardqueue._SEEN.clear(); chatlog.read(s, tid)
    assert where() == was and chatlog.live_card(s, tid)['review'] == mail


def test_a_step_held_on_a_cards_road_that_the_agent_went_on_without_ends_with_the_card_nothing_stays_pending_with_no_button():
    """Walk 24 (2026-11-25, the real Claude CLI): Post via the browser on the X card; on the way a look at the page was held, then the final
    Post; the Post stood as the card's step, he approved it and the post went up - and the look stayed pending for good, a row of a card that
    read "Posted": no button anywhere, and the task's header and rail said the agent waited on him. A step held on a card's road ends with
    that road, with its one true line. Invented posts."""
    from unittest import mock
    from taskuary import cardqueue, conversation, general, proposals, taskstate
    s, tid = world()
    conversation.hear(s, tid, turn=True)
    x = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent', 'Reason': 'the post you asked for',
                      'DraftText': json.dumps({'action': 'run_tool', 'type': 'x_post', 'text': 'We close the month in four days.'})})
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The post is set up.')
    chatlog.read(s, tid)
    with mock.patch.object(general, 'to_agent', return_value='woke'): assert proposals.via_browser(s, x, '')['ok']
    hold = lambda what, **p: proposals.queue(s, tid, {'action': 'browser_act', 'sid': 's1', 'site': 'x.example', 'what': what, 'why': 'it is his to allow', **p}, 'agent')['reviewId']
    look = hold('Run a script on the page', args=['eval', 'document.title'], command='agent-browser eval document.title')
    post = hold('Publish your post on X', args=['click', '@e20'], command='agent-browser click @e20')
    s.decide_review(post, 'approved', None, 'owner'); assert cardqueue.done(s, tid, 'Posted on x.example') == [x]; cardqueue._SEEN.clear()
    rv = s.get_review(look)
    assert proposals.passed(rv) and rv['DecideNote'] == proposals.NOT_NEEDED, 'the look it went on without is over with the card'
    assert not s._rows("SELECT 1 AS x FROM review WHERE TaskId=? AND Status='pending'", (tid,)) and cardqueue.row_over(s, tid)
    assert taskstate.standing(s, tid)['waits_on'] != 'you', 'nothing waits on him'
    assert chatlog.live_card(s, tid) is None
