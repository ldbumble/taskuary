"""THE GENERAL CHAT'S ACP ROAD KEEPS ARRIVAL ORDER (the owner, 2026-11-06: "the quick update was put above the spinning stuff ... never write above
what was written already"). The chat draws the agent's own updates in the order they came (chatlog.feed); agents.ACPSteps writes the run's
trace for what else reads it, each call once it has ended."""
import json, pytest
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


def test_a_streamed_row_never_shows_taskuarys_own_marks_whole_or_arriving():
    # 2026-11-17 / ACP rows 2026-11-23: words stream into their own row, and an agent with no end_turn tool writes the summary mark into its
    # message - it must never reach his screen, whole or cut off mid-arrival
    from taskuary import conversation
    prose = 'Checked the ledger against the invoice and the totals agree.'
    whole = conversation.acp_steps([say(prose + '\n[[TASKUARY-SUMMARY]]{"did": "checked it", "nothing_left": false}')])
    arriving = conversation.acp_steps([say(prose + '\n[[TASKUARY-SUMM')])
    for got in (whole, arriving):
        said = [s['text'] for s in got if s['k'] == 'said']
        assert said == [prose], said


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


SPEC = {'title': 'Vendor spend', 'root': 't', 'elements': {'t': {'type': 'table', 'props': {'columns': ['Vendor', 'Total'], 'rows': [['Payworth', '$4,200']]}}}}
SHOWN = "Shown in the owner's chat. TASKUARY-VIEW " + json.dumps(SPEC)
SHOW_ROADS = {
    # claude-agent-acp: the MCP answer as the call's content blocks
    'claude': ('acp', [{'sessionUpdate': 'tool_call', 'toolCallId': 'c1', 'kind': 'other', 'title': 'show', 'status': 'pending', 'rawInput': SPEC,
                        '_meta': {'claudeCode': {'toolName': 'mcp__taskuary__show'}}},
                       {'sessionUpdate': 'tool_call_update', 'toolCallId': 'c1', 'status': 'completed',
                        'content': [{'type': 'content', 'content': {'type': 'text', 'text': SHOWN}}]}]),
    # codex-acp (Codex CLI and HIPAA AI): no content - the answer is rawOutput {result: CallToolResult, error}
    'codex': ('acp', [{'sessionUpdate': 'tool_call', 'toolCallId': 'm1', 'kind': 'execute', 'title': 'mcp.taskuary.show', 'status': 'in_progress',
                       'rawInput': {'server': 'taskuary', 'tool': 'show', 'arguments': SPEC}},
                      {'sessionUpdate': 'tool_call_update', 'toolCallId': 'm1', 'status': 'completed',
                       'rawOutput': {'result': {'content': [{'type': 'text', 'text': SHOWN}], 'structuredContent': None}, 'error': None}}]),
    # the API agent's loop: its trace
    'api': ('trace', [{'type': 'tool_call', 'name': 'show', 'detail': {'tool_call_id': 'tool-0', 'args': SPEC}},
                      {'type': 'tool_result', 'name': 'tool-0', 'detail': {'tool_call_id': 'tool-0', 'result': SHOWN}}]),
}


@pytest.mark.parametrize('road', SHOW_ROADS)
def test_a_view_the_agent_showed_rides_on_its_step_to_the_page_live_and_after_a_reload(road):
    # walk 11, 2026-11-23: show answered "Shown in the owner's chat" on Codex and HIPAA AI, yet the chat's step came with no answer - 0 of 5
    # drawn, not after a reload either: the chat's row read codex-acp's rawOutput {result} as nothing, and only the old build put kept views back
    from taskuary import chatlog, conversation, general
    from taskuary.store import MemoryStore
    from taskuary.viewspec import MARK
    s = MemoryStore(); tid = s.create_task({'Title': 'Vendor spend', 'Kind': 'general', 'Status': 'open'}, 'owner')
    conversation.items(s, tid); conversation.hear(s, tid, turn=True)          # ...the page has the task open: its chat is the log
    road_, ups = SHOW_ROADS[road]
    def spec(read):
        st = [x for t in read(s, tid)['items'] if t['kind'] == 'turn' for x in t.get('steps') or [] if 'show' in str(x.get('name'))]
        assert len(st) == 1 and MARK in str(st[0].get('output') or ''), st
        return json.loads(st[0]['output'].split(MARK, 1)[1])
    for u in ups: chatlog.feed(s, tid, 'sid1', road_, u)
    assert spec(lambda s, tid: chatlog.read(s, tid, 'summary')) == SPEC, 'live, as the turn works'
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The table is above.')
    assert spec(conversation.items) == SPEC, 'its answer filed'
    chatlog._FEEDS.clear()
    assert spec(conversation.items) == SPEC, 'a fresh read'



# WALK 26 (2026-11-27): every agent read his skill by its name (their own logs) and every road's line said "read your skills" - the kept step
# had dropped what the tool was called with. One reader (conversation._served) for each shape a road sends a Taskuary tool's call in
NAMED = {'name': 'social-posts'}
def _tc(raw, meta=None, **k): return {'sessionUpdate': 'tool_call', 'toolCallId': 'k1', 'status': 'in_progress', 'rawInput': raw, **({'_meta': meta} if meta else {}), **k}
SKILL_ROADS = {
    # claude-agent-acp: the input bare, the tool named beside it
    'claude': [_tc(NAMED, {'claudeCode': {'toolName': 'mcp__taskuary__skills'}}, kind='other', title='skills')],
    # codex-acp: {server, tool, arguments} - whole at the start, or named first and its arguments on the update that ends it, or as JSON text
    'codex': [_tc({'server': 'taskuary', 'tool': 'skills', 'arguments': NAMED}, kind='execute', title='mcp.taskuary.skills')],
    'codex, arguments late': [_tc({'server': 'taskuary', 'tool': 'skills', 'arguments': None}, kind='execute', title='mcp.taskuary.skills'),
                              {'sessionUpdate': 'tool_call_update', 'toolCallId': 'k1', 'status': 'completed',
                               'rawInput': {'server': 'taskuary', 'tool': 'skills', 'arguments': NAMED}}],
    'codex, arguments as text': [_tc({'server': 'taskuary', 'tool': 'skills', 'arguments': json.dumps(NAMED)}, kind='execute')],
    # the HIPAA AI card's harness: use_tool around it, the inner arguments as JSON text - and the outer ones too
    'card': [_tc({'server': 'taskuary', 'tool': 'use_tool', 'arguments': {'name': 'skills', 'arguments': json.dumps(NAMED)}}, kind='execute')],
    'card, arguments as text': [_tc({'server': 'taskuary', 'tool': 'use_tool', 'arguments': json.dumps({'name': 'skills', 'arguments': json.dumps(NAMED)})}, kind='execute')],
    # the API agent's loop: its trace, the tool bare or through use_tool
    'api': [('trace', {'type': 'tool_call', 'name': 'skills', 'detail': {'tool_call_id': 'k1', 'args': NAMED}})],
    'api, arguments as text': [('trace', {'type': 'tool_call', 'name': 'skills', 'detail': {'tool_call_id': 'k1', 'args': json.dumps(NAMED)}})],
    'api, use_tool': [('trace', {'type': 'tool_call', 'name': 'use_tool', 'detail': {'tool_call_id': 'k1', 'args': {'name': 'skills', 'arguments': json.dumps(NAMED)}}})],
}


@pytest.mark.parametrize('road', SKILL_ROADS)
def test_the_skill_a_turn_read_is_kept_by_its_name_on_every_road(road):
    from taskuary.conversation import acp_of_trace, acp_steps
    ups = [x for u in SKILL_ROADS[road] for x in (acp_of_trace(u[1]) if isinstance(u, tuple) else [u])]
    [s] = acp_steps(ups)
    assert s['name'].split('__')[-1] == 'skills' and s['args'] == NAMED, s
    # ...and it is on the row the page draws, which reads the line's name from it (agentSteps OWN.skills: "Read your skill 'social-posts'")
    from taskuary.chatlog import one_step
    assert one_step(s)['args'] == NAMED


def test_a_cli_tool_of_its_own_keeps_only_what_its_row_says():
    # ...and nothing else changes: a CLI's own Write is not Taskuary's tool, and its content is not kept on the step
    from taskuary.conversation import acp_steps
    [s] = acp_steps([_tc({'file_path': 'C:/work/menu.md', 'content': 'x' * 5000}, {'claudeCode': {'toolName': 'Write'}}, kind='edit', title='Write')])
    assert s['name'] == 'Write' and s['args'] == {'file_path': 'C:/work/menu.md'}
