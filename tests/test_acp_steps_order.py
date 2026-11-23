"""THE GENERAL CHAT'S ACP ROAD KEEPS ARRIVAL ORDER (the owner, 2026-11-06: "the quick update was put above the spinning stuff ... never write above
what was written already"). The chat draws the agent's own updates in the order they came (chatlog.feed); agents.ACPSteps writes the run's
trace for what else reads it, each call once it has ended."""
from taskuary import agents


def traced(ups):
    out = []
    s = agents.ACPSteps(lambda kind, name, detail=None: out.append((kind, name if kind != 'progress' else detail)), 'claude')
    for u in ups: s(u)
    s.flush('end_turn')
    return [(k, n) for k, n in out if k != 'live']


def say(t): return {'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': t}}


RUN = [say('Running the suite.'),
       {'sessionUpdate': 'tool_call', 'toolCallId': 't1', 'kind': 'execute', 'title': 'Terminal', 'status': 'pending'},
       {'sessionUpdate': 'tool_call_update', 'toolCallId': 't1', 'status': 'in_progress', 'title': 'pytest -q', 'rawInput': {'command': 'pytest -q'}},
       say('Quick update: '), say('half of it passed.'),
       {'sessionUpdate': 'tool_call_update', 'toolCallId': 't1', 'status': 'completed'},
       say('All 212 pass.')]


def test_words_after_a_running_step_are_drawn_after_it_and_the_call_is_drawn_at_once():
    """THE CHAT DRAWS THE AGENT'S OWN UPDATES (chatlog.feed): the call is its row from the moment it is announced - generic title and all,
    upgraded in place - and what it said while the call ran stands under it. Nothing is held back to look settled."""
    from taskuary import chatlog, conversation
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = s.create_task({'Title': 'Run the suite', 'Kind': 'general', 'Status': 'open'}, 'owner')
    conversation.hear(s, tid, turn=True)
    chatlog.feed(s, tid, 'sid1', 'acp', RUN[0]); chatlog.feed(s, tid, 'sid1', 'acp', RUN[1])
    assert [x.get('title') for x in chatlog.read(s, tid, 'everything')['items'][-1]['steps'] if x['k'] == 'tool'] == ['Terminal'], 'drawn at once'
    for u in RUN[2:]: chatlog.feed(s, tid, 'sid1', 'acp', u)
    chatlog.flush(s, tid)
    got = [(x['k'], x.get('title') or x.get('text')) for x in chatlog.read(s, tid, 'everything')['items'][-1]['steps']]
    assert got == [('said', 'Running the suite.'), ('tool', 'pytest -q'), ('said', 'Quick update: half of it passed.'), ('said', 'All 212 pass.')]


def test_the_trace_of_a_run_has_each_call_once_with_the_input_it_ended_on():
    "What reads a run's trace (the pane, the transcript, a stopped turn's account) gets each call once it has ended, never 'Terminal' with nothing."
    got = traced(RUN)
    assert got == [('progress', 'Running the suite.'), ('progress', 'Quick update: half of it passed.'), ('tool_call', 'execute'),
                   ('tool_result', 't1'), ('progress', 'All 212 pass.')]


def test_the_writing_line_never_shows_the_summary_cut_from_its_tag():
    # 2026-11-17: the line of what it is writing kept the last 600 characters, and once the summary block passed them its opening
    # tag fell off the front - the line read '..."], "nothing_left": false, "answ' since nothing downstream could tell it was the summary
    out, prose = [], ' '.join(['Checked the ledger against the invoice and the totals agree.'] * 34)
    s = agents.ACPSteps(lambda kind, name, detail=None: out.append((kind, name, detail)), 'claude')
    s(say(prose + '\n[[TASKUARY-SUMMARY]]{"did": "checked it", "on_you": ["press Send on the reply to Erin Blake"], "nothing_left": false, "answ'))
    live = [d for k, n, d in out if k == 'live' and n == 'writing']
    assert live and live[-1].endswith('totals agree.') and '[[' not in live[-1] and 'nothing_left' not in live[-1]


def test_a_message_cut_by_a_line_he_typed_mid_turn_is_its_own_step():
    # design round 6, D2 (the Claude CLI walk, 2026-11-19): his line came in while the agent wrote, the adapter cut its message at "The Q" and
    # began another - one step held both, run together ("The QPaula's address is..."), while the answer (acp.prompt) kept them two paragraphs
    m = lambda mid, t: {**say(t), 'messageId': mid}
    got = traced([m('a', 'The drafts need the same correction. '), m('a', 'The Q'), m('b', "Paula's address is paula@northwind.example."),
                  m('c', 'Is it 212 or 214?')])
    assert got == [('progress', 'The drafts need the same correction. The Q'), ('progress', "Paula's address is paula@northwind.example."),
                   ('progress', 'Is it 212 or 214?')]


def test_a_taskuary_tools_answer_on_codex_is_its_steps_result():
    # the HIPAA walk, 2026-11-21: codex-acp sends an MCP call's answer as rawOutput {result: CallToolResult, error} - only a string was read, so
    # every Taskuary tool's answer reached the page empty and a show drew no chart
    out, view = [], "Shown in the owner's chat. TASKUARY-VIEW {\"root\": \"c\"}"
    s = agents.ACPSteps(lambda kind, name, detail=None: out.append((kind, name, detail)), 'codex')
    s({'sessionUpdate': 'tool_call', 'toolCallId': 'm1', 'kind': 'execute', 'title': 'mcp.taskuary.show', 'status': 'in_progress',
       'rawInput': {'server': 'taskuary', 'tool': 'show', 'arguments': {'root': 'c'}}})
    s({'sessionUpdate': 'tool_call_update', 'toolCallId': 'm1', 'status': 'completed',
       'rawOutput': {'result': {'content': [{'type': 'text', 'text': view}], 'structuredContent': None}, 'error': None}})
    s({'sessionUpdate': 'tool_call', 'toolCallId': 'm2', 'kind': 'execute', 'title': 'mcp.taskuary.tick', 'status': 'in_progress', 'rawInput': {}})
    s({'sessionUpdate': 'tool_call_update', 'toolCallId': 'm2', 'status': 'failed', 'rawOutput': {'result': None, 'error': {'message': 'no such to-do'}}})
    s.flush('end_turn')
    res = {n: d for k, n, d in out if k == 'tool_result'}
    assert res['m1']['result'] == view and res['m2'] == {'result': 'no such to-do', 'is_error': True}
