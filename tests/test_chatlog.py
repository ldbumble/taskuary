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
    got = chatlog.read(s, tid)['items']
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
    assert [(c['id'], c['state']) for c in chatlog.read(s, tid)['items'][0]['cards']] == [('r:7', 'sent'), ('r:8', 'pending')]


def test_a_turn_at_work_draws_its_steps_and_holds_its_card_back():
    s, tid = world()
    chatlog.put(s, tid, 'turn', 't:1', {'started': 1.0}, state='working')
    chatlog.step(s, tid, 'sid1', 'call-1', {'k': 'tool', 'what': 'Read the vendor sheet'}, state='completed')
    chatlog.put(s, tid, 'card', 'r:7', {'review': 7}, parent='t:1', state='pending')
    t = chatlog.read(s, tid)['items'][0]
    assert [x['what'] for x in t['steps']] == ['Read the vendor sheet'] and t['cards'] == []
    chatlog.update(s, tid, 't:1', state='done')
    assert [c['id'] for c in chatlog.read(s, tid)['items'][0]['cards']] == ['r:7']


def test_a_step_after_his_line_goes_on_in_a_new_turn_under_it_with_its_files():
    """A MID-TURN LINE (the spec's stage 2 shape): Paula's line heard by a running turn - the rest of the turn is a new turn row under her
    line, and the file the step after it made is kept on that step."""
    s, tid = world()
    chatlog.put(s, tid, 'turn', 't:1', {'started': 1.0}, state='working')
    chatlog.step(s, tid, 'sid1', 'call-1', {'k': 'tool', 'what': 'Read the vendor sheet'})
    chatlog.put(s, tid, 'line', 'l-2', {'text': 'Paula says use the March export', 'by': 'Paula Vance', 'at': 5.0})
    chatlog.step(s, tid, 'sid1', 'call-2', {'k': 'tool', 'what': 'Wrote march-totals.csv', 'files': ['march-totals.csv']})
    chatlog.step(s, tid, 'sid1', 'call-1', {'k': 'tool', 'what': 'Read the vendor sheet', 'status': 'completed'})    # ...an update of the first
    items = chatlog.read(s, tid)['items']
    assert [(x['kind'], x['id']) for x in items][:2] == [('turn', 't:1'), ('line', 'l-2')]
    assert items[2]['kind'] == 'turn' and items[2]['cont'] == 't:1' and items[2]['started'] == 1.0
    assert [x['what'] for x in items[0]['steps']] == ['Read the vendor sheet'] and items[0]['steps'][0]['status'] == 'completed'
    assert items[2]['steps'][0]['files'] == ['march-totals.csv']


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
    items = chatlog.read(s, tid)['items']
    assert [(x['kind'], x.get('state')) for x in items] == [('turn', 'done'), ('line', None), ('turn', 'done')]
    assert items[1]['id'] == 'l-paula' and items[1]['text'] == 'Paula says use the March export'
    assert items[2]['text'].startswith('Totals from the March export') and items[2]['steps'][0]['files'] == ['march-totals.csv']
    assert conversation.hear(s, tid, ['l-paula']) == 0 and len(chatlog.read(s, tid)['items']) == 3, 'told once, written once'
