"""A TURN THE RESTART CUT KEEPS WHAT IT SAID (the product audit, 2026-11-08). A long ask ran 70 seconds - seven steps and "I've collected the
pricing..." - and a restart erased it all: the turn lived only in the process until it filed its reply, and nothing in the chat said it was
cut. The trace is on disk as it grows; at start-up a turn still there is filed with its words, its steps and one quiet line. Invented world."""
import json, types


from taskuary import general, sessionrecord
from taskuary.store import MemoryStore


def turn(s, tid):
    "A session mid-turn, as send_prompt leaves it, its trace written through _remember_trace."
    me = types.SimpleNamespace(task_id=tid, busy=True, trace=[{'type': 'start', 'session': {}}], trace_revision=0, _trace_detail=lambda k, d: d)
    for k, n, d in [('tool_call', 'WebSearch', {'args': {'query': 'expense tools pricing'}}), ('progress', 'thinking', 'Compare per seat.'),
                    ('progress', 'text', "I've collected the pricing for Spendly and Payworth."), ('live', 'assistant', 'scrolling')]:
        general.GeneralSession._remember_trace(me, k, n, d)
    return me


def test_a_cut_turn_is_filed_with_its_words_its_steps_and_one_line():
    s = MemoryStore(); tid = s.create_task({'Title': 'Expense tools for Northwind', 'Kind': 'general', 'Status': 'open'}, 'owner')
    turn(s, tid)
    assert general.keep_cut_turns(s) == [tid]
    got = [c for c in s.list_comments(tid) if c['ActorType'] == general.ASSISTANT_TYPE]
    assert len(got) == 1 and got[0]['Body'].startswith("I've collected the pricing") and got[0]['Body'].endswith(general.CUT)
    kept = [json.loads(x) for x in sessionrecord._gen_path(tid).read_text(encoding='utf-8').splitlines()]
    assert kept[-1]['reply'] == got[0]['CommentId'] and [x['k'] for x in kept[-1]['steps']][:2] == ['tool', 'thought']
    assert 'restarted' in general.CUT and general.CARRY_ON in general.CUT
    assert general.keep_cut_turns(s) == [], 'taken off disk once filed'


def test_a_turn_that_ended_here_leaves_nothing_and_a_closed_task_gets_no_cut_line():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Vendor list', 'Kind': 'general', 'Status': 'open'}, 'owner')
    turn(s, tid); sessionrecord.drop_live(tid)                       # the turn's own end (send_prompt's finally)
    gone = s.create_task({'Title': 'Old ask', 'Kind': 'general', 'Status': 'done'}, 'owner')
    turn(s, gone)
    assert general.keep_cut_turns(s) == []
    assert not [c for t in (tid, gone) for c in s.list_comments(t) if c['ActorType'] == general.ASSISTANT_TYPE]


def test_a_turn_that_said_nothing_yet_still_says_it_was_cut():
    s = MemoryStore(); tid = s.create_task({'Title': 'Board pack', 'Kind': 'general', 'Status': 'open'}, 'owner')
    sessionrecord.keep_live(tid, [{'type': 'start'}, {'type': 'tool_call', 'name': 'Read', 'detail': {'args': {'file': 'pack.pdf'}}}])
    general.keep_cut_turns(s)
    assert [c['Body'] for c in s.list_comments(tid) if c['ActorType'] == general.ASSISTANT_TYPE] == [general.CUT]
