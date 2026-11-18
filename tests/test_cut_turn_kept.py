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


def test_a_turn_whose_cli_died_part_way_keeps_its_steps_and_its_failure_where_it_happened():
    """THE SAME SHAPE AS A RESTART'S CUT, ON A LIVE CLI (chat-render, 2026-11-18): a turn read a file and its CLI exited. It filed nothing, so the
    chat drew its failure only while it was the task's last word - and once he wrote again the turn read "1 step" with no reason under it, and
    the next turn's clock counted from the dead one's start ("working 12s" the moment he pressed Enter). Invented world."""
    from unittest import mock
    from taskuary import clipool, conversation, terminal
    from test_general_turn_ends_short import a_claude, researcher
    import unittest
    case = unittest.TestCase(); case.addCleanup = lambda f: None
    a_claude(case)
    s = MemoryStore(); tid = researcher(s)
    def dies(profile, prompt, trace, resume=None, **kw):
        trace('tool_call', 'Read', {'tool_call_id': 'tu1', 'args': {'file_path': 'gail.txt'}}); trace('tool_result', 'tu1', {'result': 'Hi Alex'})
        trace('progress', 'text', "Gail's note asks for the renewal terms.")
        raise RuntimeError(clipool.MID_TURN)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch('taskuary.agents.run_cli', side_effect=dies):
        sess = general.start_session(s, tid, pick='cli:claude')
        try: sess.send_prompt('Draft the reply to Gail', pick='cli:claude')
        except Exception: pass
    turns = lambda: [x for x in conversation.items(s, tid)['items'] if x['kind'] == 'turn']
    now = turns()
    assert len(now) == 1 and now[0]['state'] == 'failed' and [x['k'] for x in now[0]['steps']] == ['tool'], now
    assert now[0]['text'] == "Gail's note asks for the renewal terms." and 'middle of its turn' in now[0]['fail'], now
    # ...and once he writes again, it still says so, where it happened - and the next turn's clock is its own
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Carry on, please')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The reply to Gail is drafted.')
    later = turns()
    assert later[0]['id'] == now[0]['id'] and later[0]['state'] == 'failed' and later[0]['fail'] == now[0]['fail'], later
    assert later[0]['text'] == now[0]['text'] and later[1]['text'] == 'The reply to Gail is drafted.', later
    assert later[1]['started'] is None or later[1]['started'] >= now[0]['ended'] - 1, later

