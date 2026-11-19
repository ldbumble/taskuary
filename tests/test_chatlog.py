"""ONE LOG PER TASK (chatlog.py; the owner's approved redesign A, 2026-11-19). A task's chat is appended once, at the place each thing gets
then, and only what can change is updated in place. Invented people only."""
import sqlite3

import pytest

from taskuary import chatlog
from taskuary.store import MemoryStore


def world():
    s = MemoryStore()
    return s, s.create_task({'Title': 'Vendor review for Erin', 'Kind': 'general', 'Status': 'in_progress'}, 'owner')


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
    assert items[2]['kind'] == 'turn' and items[2]['cont'] == 't:1' and items[2]['started'] == 1.0
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
    s, tid = world()
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


def test_every_tool_call_is_one_row_in_plain_words_and_summary_folds_them_to_one_line():
    """"BETTER SHOWING WHAT TOOLS ARE RUN, BUT NOT A BILLION DETAILS" (the owner, 2026-11-19): each call one row of what it did and on what,
    its outcome in a few words, its output capped behind it; the same call again folded into its row; summary - one line that opens."""
    big = 'x' * 10000 + '\n4 passed in 0.2s'
    steps = [{'k': 'tool', 'name': 'Bash', 'text': 'pytest tests/test_totals.py', 'output': big},
             {'k': 'tool', 'name': 'Read', 'file': 'C:/work/board-data-asks.txt'},
             {'k': 'tool', 'name': 'Read', 'file': 'C:/work/board-data-asks.txt'},
             {'k': 'tool', 'name': 'Read', 'file': 'C:/work/board-data-asks.txt'},
             {'k': 'tool', 'name': 'WebSearch', 'args': {'query': 'printer prices'}},
             {'k': 'tool', 'name': 'WebFetch', 'args': {'url': 'https://www.uprinting.com/business-cards'}},
             {'k': 'said', 'text': 'Four tests pass; uprinting is cheapest.'}]
    rows = chatlog.tool_rows(steps)
    assert [(r.get('line'), r.get('outcome'), r.get('times')) for r in rows[:4]] == [
        ('Ran pytest tests/test_totals.py', '4 passed', None), ('Read board-data-asks.txt', None, 3),
        ('Searched the web for printer prices', None, None), ('Opened uprinting.com', None, None)]
    assert rows[0]['size'] == len(big) and len(rows[0]['output']) < 3200, 'the output capped: its head and tail, and how big it was'
    t = chatlog.detailed({'kind': 'turn', 'state': 'done', 'text': 'Done.', 'steps': steps}, 'summary')
    assert [s['k'] for s in t['steps'] if s not in t['fold']] == ['said'] and t['fold_line'] == '6 steps - ran a command, read 3 files, searched the web, opened a site'
    assert len(chatlog.detailed({'kind': 'turn', 'state': 'done', 'steps': steps}, 'everything')['steps']) == 5


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
    assert chatlog.migrate(s, tid, legacy=legacy) and not chatlog.migrate(s, tid, legacy=legacy), 'once'
    assert s.get_setting('chatlog_backup', '') and (tmp_path / 'backups').exists(), 'a copy before anything was written'
    rows = {r['Key']: r['State'] for r in s._rows('SELECT Key, State FROM chatlog WHERE TaskId=?', (tid,))}
    assert (rows['r:7'], rows['r:8'], rows['t:l-2:0']) == ('pending', 'held', 'working')
    chatlog._FEEDS.clear()                                               # ...a restart in the middle: the road comes back and goes on
    chatlog.feed(s, tid, 'sid9', 'trace', {'type': 'progress', 'name': 'text', 'detail': 'The price is on the second page.'})
    t = s._rows("SELECT Id FROM chatlog WHERE Key='t:l-2:0'")[0]['Id']
    assert [r['Parent'] for r in s._rows("SELECT Parent FROM chatlog WHERE TaskId=? AND Kind='step' AND Src LIKE 'sid9:%'", (tid,))] == [t]
