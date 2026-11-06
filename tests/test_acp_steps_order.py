"""THE GENERAL CHAT'S ACP ROAD KEEPS ARRIVAL ORDER (the owner, 2026-11-06: "the quick update was put above the spinning stuff ... never write above
what was written already"). agents.ACPSteps traces a recorded update sequence: a step announced and still running, then the agent's words, then
the step's result - the words are traced after the step they followed, never before it, and the answer rule (what it said after its last tool
call) leaves earlier words where they were said."""
from taskuary import agents


def traced(ups):
    out = []
    s = agents.ACPSteps(lambda kind, name, detail=None: out.append((kind, name if kind != 'progress' else detail)), 'claude')
    for u in ups: s(u)
    s.flush('end_turn')
    return [(k, n) for k, n in out if k != 'live']


def say(t): return {'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': t}}


def test_words_after_a_running_step_trace_after_it():
    got = traced([say('Running the suite.'),
                  {'sessionUpdate': 'tool_call', 'toolCallId': 't1', 'kind': 'execute', 'title': 'Terminal', 'status': 'pending'},
                  {'sessionUpdate': 'tool_call_update', 'toolCallId': 't1', 'status': 'in_progress', 'rawInput': {'command': 'pytest -q'}},
                  say('Quick update: '), say('half of it passed.'),
                  {'sessionUpdate': 'tool_call_update', 'toolCallId': 't1', 'status': 'completed'},
                  say('All 212 pass.')])
    assert got == [('progress', 'Running the suite.'), ('tool_call', 'execute'), ('progress', 'Quick update: half of it passed.'),
                   ('tool_result', 't1'), ('progress', 'All 212 pass.')]
