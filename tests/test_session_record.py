"""One record of what an agent did and thought, whoever the agent was (the owner, 2026-10-10: "unify what gets saved ...
different cli tools, general agent vs regular ... everything the agent did and thought about ... don't duplicate").
Each CLI's own log is read into the same steps; a CLI with no log still leaves its screen; a general chat keeps the
tool calls of every turn; and the result is the fullest account the session left, said once."""
import json

import pytest

from taskuary import general, session_artifacts, sessionrecord
from taskuary.store import MemoryStore
from taskuary.testing import Factory


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(sessionrecord, '_home', lambda: tmp_path)
    monkeypatch.setattr(sessionrecord, '_FOUND', {})
    (tmp_path / 'artifacts').mkdir()
    monkeypatch.setattr(session_artifacts, 'root', lambda: tmp_path / 'artifacts')     # task ids repeat across tests' stores
    return tmp_path


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')


def claude_log(home, ext):
    jsonl(home / '.claude' / 'projects' / 'C--work-ledger' / f'{ext}.jsonl', [
        {'type': 'user', 'message': {'content': 'Why did the March import double-count invoices?'}},
        {'type': 'user', 'isMeta': True, 'message': {'content': '<system-reminder>ignore me</system-reminder>'}},
        {'type': 'assistant', 'message': {'content': [
            {'type': 'thinking', 'thinking': 'The importer probably re-reads the file when the cursor resets.'},
            {'type': 'tool_use', 'name': 'Grep', 'input': {'pattern': 'cursor', 'path': 'ledger/'}},
            {'type': 'tool_use', 'name': 'TodoWrite', 'input': {'todos': [
                {'content': 'Find the double read', 'status': 'completed'}, {'content': 'Patch the cursor', 'status': 'in_progress'}]}}]}},
        {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'content': 'ledger/importer.py:40: cursor = 0'}]}},
        {'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'name': 'Edit', 'input': {'file_path': 'ledger/importer.py', 'old_string': 'a', 'new_string': 'b'}},
            {'type': 'text', 'text': 'Fixed: the cursor reset on retry, so March was read twice.'}]}}])


def test_claude_log_reads_thinking_tools_plan_and_files(home):
    claude_log(home, 'c1')
    steps, source = sessionrecord.cli_steps('claude', 'c1')
    assert source == 'Claude Code log'
    assert [s['k'] for s in steps] == ['you', 'thought', 'tool', 'plan', 'tool', 'said']
    assert steps[2] == {'k': 'tool', 'name': 'Grep', 'text': 'cursor in ledger/', 'at': None, 'args': {'pattern': 'cursor', 'path': 'ledger/'}}
    summary = sessionrecord.summarise(steps)
    assert summary['files'] == ['ledger/importer.py'] and [i['status'] for i in summary['plan']] == ['completed', 'in_progress']
    assert summary['counts'] == {'thought': 1, 'tool': 2, 'said': 1, 'you': 1}


def test_codex_rollout_reads_reasoning_commands_patches_and_message(home):
    patch = '*** Begin Patch\n*** Update File: portal/app.js\n@@\n-a\n+b\n*** End Patch'
    jsonl(home / '.codex' / 'sessions' / '2026' / '10' / '10' / 'rollout-2026-10-10T09-00-00-x1.jsonl', [
        {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'Make the portal log-in remember the user.'}},
        {'type': 'response_item', 'payload': {'type': 'reasoning', 'summary': [{'type': 'summary_text', 'text': 'Cookie expiry is the lever.'}],
                                              'encrypted_content': 'gAAAA'}},
        {'type': 'response_item', 'payload': {'type': 'custom_tool_call', 'name': 'exec', 'input': 'tools.exec_command({cmd:"rg -n remember portal"})'}},
        {'type': 'response_item', 'payload': {'type': 'custom_tool_call', 'name': 'apply_patch', 'input': patch}},
        {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Done - 30 day cookie.'}]}}])
    steps, source = sessionrecord.cli_steps('codex', 'x1')
    assert source == 'Codex rollout'
    assert [(s['k'], s.get('text')) for s in steps] == [
        ('you', 'Make the portal log-in remember the user.'), ('thought', 'Cookie expiry is the lever.'),
        ('tool', 'rg -n remember portal'), ('tool', 'portal/app.js'), ('said', 'Done - 30 day cookie.')]
    assert sessionrecord.summarise(steps)['files'] == ['portal/app.js']


def test_copilot_events_read_and_an_unknown_cli_keeps_its_screen(home):
    jsonl(home / '.copilot' / 'session-state' / 'k1' / 'events.jsonl', [
        {'type': 'user.message', 'data': {'content': 'List the stale branches.'}},
        {'type': 'assistant.message', 'data': {'content': '', 'reasoningText': 'git for-each-ref sorts by date.'}},
        {'type': 'tool.execution_start', 'data': {'toolName': 'powershell', 'arguments': {'command': 'git for-each-ref'}}},
        {'type': 'assistant.message', 'data': {'content': 'Three branches are older than 90 days.'}}])
    steps, _ = sessionrecord.cli_steps('copilot', 'k1')
    assert [s['k'] for s in steps] == ['you', 'thought', 'tool', 'said']
    assert sessionrecord.cli_steps('cursor-agent', 'whatever') == ([], '')
    assert sessionrecord.screen_steps('  $ make test\n12 passed  ') == [{'k': 'screen', 'text': '$ make test\n12 passed'}]


def test_a_coding_session_is_one_record_with_its_report_and_result_said_once(home):
    s = MemoryStore(); tid = Factory(s).task(title='March import doubled')
    claude_log(home, 'c1')
    s.add_comment(tid, 'claude', 'agent', 'AGENT REPORT\nDetermination: the cursor reset on retry\nActions: patched importer.py\n'
                                          'Summary: March was read twice; fixed.\n\nLAST MESSAGE\nFixed: the cursor reset on retry, so March was read twice.')
    s.add_transcript(tid, 'pane-1', 'screen text', 'coding', 'C:/work/ledger', 'c1', brain='claude')
    [rec] = sessionrecord.record(s, tid)['sessions']
    assert rec['cli'] == 'claude' and rec['source'] == 'Claude Code log'
    assert rec['report']['decided'] == 'the cursor reset on retry' and rec['report']['changed'] == 'patched importer.py'
    assert rec['result'] == 'Fixed: the cursor reset on retry, so March was read twice.'
    assert rec['files'] == ['ledger/importer.py'] and rec['counts']['thought'] == 1


def test_a_saved_answer_is_the_result_and_the_snapshot_outlives_the_cli_log(home):
    s = MemoryStore(); tid = Factory(s).task(title='Vendor list')
    claude_log(home, 'c2')
    s.add_transcript(tid, 'pane-2', 'screen', 'coding', '', 'c2', brain='claude')
    sessionrecord.save(s, tid, 'pane-2', 'claude', 'c2', 'screen')
    (home / '.claude' / 'projects' / 'C--work-ledger' / 'c2.jsonl').unlink()           # the CLI pruned its logs
    session_artifacts.result(s, tid, '1. Payworth\n2. Trainly\n3. Spendly')
    [rec] = sessionrecord.record(s, tid)['sessions']
    assert rec['result'] == '1. Payworth\n2. Trainly\n3. Spendly'
    assert rec['counts']['tool'] == 2                                                   # read from the snapshot


def test_a_quick_answers_raw_json_kept_before_the_fix_is_not_a_said_step(home):
    "A quick answer filed before quickwork.answer_text kept its raw object as the turn's working, cut at SAID_N: read back, it is dropped."
    s = MemoryStore(); tid = Factory(s).task(title='Partner day', kind='general')
    rid = s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Worth going: Erin presents at 10.')
    sessionrecord.keep_turn(tid, rid, [{'type': 'progress', 'name': 'text', 'detail': '```json\n{\n  "report": "Worth going: Erin presents at 10.",\n  "dra'}])
    [rec] = sessionrecord.record(s, tid)['sessions']
    assert [(x['k'], x['text']) for x in rec['steps']] == [('said', 'Worth going: Erin presents at 10.')]


def test_a_general_chat_keeps_every_turns_working_and_no_reply_twice(home):
    s = MemoryStore(); tid = Factory(s).task(title='Vendor spend', kind='general')
    s.add_comment(tid, 'owner', general.USER_TYPE, 'How did vendor spend move?')
    rid = s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'August was $192,600, up 8% on July.')
    sessionrecord.keep_turn(tid, rid, [
        {'type': 'start', 'session': {}},
        {'type': 'progress', 'name': 'thinking', 'detail': 'Compare the two monthly totals.'},
        {'type': 'tool_call', 'name': 'Read', 'detail': {'args': {'file_path': 'spend.csv'}}},
        {'type': 'progress', 'name': 'text', 'detail': 'August was $192,600, up 8% on July.'}])
    [rec] = sessionrecord.record(s, tid)['sessions']
    assert rec['source'] == 'conversation'
    assert [(x['k'], x['text']) for x in rec['steps']] == [
        ('you', 'How did vendor spend move?'), ('thought', 'Compare the two monthly totals.'),
        ('tool', 'spend.csv'), ('said', 'August was $192,600, up 8% on July.')]
    assert rec['result'] == 'August was $192,600, up 8% on July.'


# TASKUARY'S OWN NOTE IN THE CHAT IS NOT THE AGENT'S ANSWER (the owner, 2026-10-27: a finished agent's Result read the reply receipt): a note
# filed by Taskuary - by its actor, or an older one with no agent turn audited with it - is a `note` step, and the result stays the agent's
def test_a_receipt_in_the_chat_is_a_note_never_the_agents_last_words(home):
    s = MemoryStore(); tid = Factory(s).task(title='Snag list', kind='general')
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Who signs the snag list?')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Ray Colton signs it on Thursday.')
    s.audit('task', tid, 'assistant_reply', 'assistant', 'agent', {'chars': 31})
    s.add_comment(tid, sessionrecord.NOTE_ACTOR, general.ASSISTANT_TYPE, 'You replied in WhatsApp on TQ-0001. I removed the unused draft.')
    [rec] = sessionrecord.record(s, tid)['sessions']
    assert [x['k'] for x in rec['steps']] == ['you', 'said', 'note']
    assert rec['result'] == 'Ray Colton signs it on Thursday.'
    # ...an older note, filed under the agent's own actor, is told by having no turn audited with it
    s2 = MemoryStore(); t2 = Factory(s2).task(title='Snag list', kind='general')
    s2.add_comment(t2, 'assistant', general.ASSISTANT_TYPE, 'Ray Colton signs it on Thursday.')
    s2.audit('task', t2, 'assistant_reply', 'assistant', 'agent', {'chars': 31})
    s2._exec("INSERT INTO comment (TaskId,Actor,ActorType,Body,CreatedAt) VALUES (?,?,?,?,datetime('now','localtime','+1 minute'))",
             (t2, 'assistant', general.ASSISTANT_TYPE, 'You replied in WhatsApp on TQ-0001.'))
    [rec2] = sessionrecord.record(s2, t2)['sessions']
    assert [x['k'] for x in rec2['steps']] == ['said', 'note']


# TASKUARY'S INSTRUCTIONS ARE NOT THE OWNER'S WORDS (the owner, 2026-10-30): the brief an agent started on is marked where it is filed -
# a chat turn by general.BRIEF_ACTOR, a coding seed kept as sent - and is a `brief` step; what the owner typed stays `you`
def test_an_auto_start_brief_is_taskuarys_and_the_owners_words_stay_theirs(home):
    s = MemoryStore(); tid = Factory(s).task(title='Partner day', kind='general')
    s.add_comment(tid, general.BRIEF_ACTOR, general.USER_TYPE, 'THIS TASK IS A REPLY OWED to Erin Blake. Work out the answer.')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Friday works.')
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Check Saturday too.')
    assert [m.get('brief', False) for m in general.history(s, tid)] == [True, False, False]
    [rec] = sessionrecord.record(s, tid)['sessions']
    assert [x['k'] for x in rec['steps']] == ['brief', 'said', 'you']


def test_a_coding_seed_is_a_brief_and_a_line_typed_after_it_is_the_owners(home):
    s = MemoryStore(); tid = Factory(s).task(title='March import doubled')
    seed = 'TASK TQ-0001 - March import doubled.  REPO: C:/work/ledger - you are already in it; work only here.'
    jsonl(home / '.claude' / 'projects' / 'C--work-ledger' / 'c9.jsonl', [
        {'type': 'user', 'message': {'content': ' '.join(seed.split())}},
        {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'Looking at the importer.'}]}},
        {'type': 'user', 'message': {'content': 'Only March, please.'}}])
    sessionrecord.keep_seed(tid, seed)
    s.add_transcript(tid, 'pane-9', 'screen', 'coding', 'C:/work/ledger', 'c9', brain='claude')
    [rec] = sessionrecord.record(s, tid)['sessions']
    assert [x['k'] for x in rec['steps']] == ['brief', 'said', 'you']
    assert [x['k'] for x in sessionrecord.save(s, tid, 'pane-9', 'claude', 'c9')['steps']] == ['brief', 'said', 'you']


def test_the_owners_words_in_a_resume_seed_are_their_line_and_the_rest_is_ours(home):
    """2026-11-09: a resumed stranger's task, typed into its pane, landed "FROM THE OWNER: trynow The owner chose Resume..." - a space
    lost from the seed it was kept as, so no kept seed matched, and the chat drew the whole wrapper as the owner's line."""
    from taskuary.continuity import RESUME_PROMPT
    from taskuary import codingchat
    s = MemoryStore(); tid = Factory(s).task(title='Export failed')
    sessionrecord.keep_seed(tid, f'FROM THE OWNER: try now\n\n{RESUME_PROMPT}')
    jsonl(home / '.claude' / 'projects' / 'C--work-ledger' / 'r1.jsonl', [
        {'type': 'user', 'message': {'content': ' '.join(f'FROM THE OWNER: trynow {RESUME_PROMPT}'.split())}},
        {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'Reachable now.'}]}}])
    s.add_transcript(tid, 'pane-1', 'screen', 'coding', 'C:/work/ledger', 'r1', brain='claude')
    want = [('you', 'trynow'), ('brief', RESUME_PROMPT), ('said', 'Reachable now.')]
    [rec] = sessionrecord.record(s, tid)['sessions']
    assert [(x['k'], x['text']) for x in rec['steps']] == want
    saved = sessionrecord.save(s, tid, 'pane-1', 'claude', 'r1')['steps']
    assert [(x['k'], x['text']) for x in saved] == want
    # ...and a record saved the old way, the wrapper as a `you` step, is drawn right as it is read
    old = sessionrecord._saved_path(tid, 'pane-1')
    old.write_text(json.dumps({'steps': [{'k': 'you', 'text': f'FROM THE OWNER: trynow {RESUME_PROMPT}'}]}), encoding='utf-8')
    [ses] = [x for x in codingchat.sessions(s, tid)]
    assert [(x['k'], x['text']) for x in ses['steps']] == [('you', 'trynow'), ('brief', RESUME_PROMPT)]


SUMMARY = ('This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier '
           'portion of the conversation.\n\n<system-reminder>context</system-reminder>\nSummary:\n1. Primary Request and Intent: Erin Blake asked '
           'why the March import doubled.')


def test_a_compaction_is_one_quiet_step_never_the_owners_line(home):
    """2026-11-10: Claude compacted its context mid-task, and its summary - written into its log as a user entry - was drawn as the owner's
    own bubble. The log marks it (a compact_boundary system entry, then the summary marked isCompactSummary): one `compact` step instead."""
    from taskuary import codingchat
    s = MemoryStore(); tid = Factory(s).task(title='March import doubled')
    jsonl(home / '.claude' / 'projects' / 'C--work-ledger' / 'k1.jsonl', [
        {'type': 'user', 'message': {'content': 'Why did March double?'}, 'timestamp': '2026-11-10T08:00:00Z'},
        {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'Reading the importer.'}]}, 'timestamp': '2026-11-10T08:01:00Z'},
        {'type': 'system', 'subtype': 'compact_boundary', 'content': 'Conversation compacted', 'timestamp': '2026-11-10T08:20:00Z',
         'compactMetadata': {'trigger': 'auto', 'preTokens': 160000}},
        {'type': 'user', 'isCompactSummary': True, 'isVisibleInTranscriptOnly': True, 'message': {'role': 'user', 'content': SUMMARY},
         'timestamp': '2026-11-10T08:20:01Z'},
        {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'Found it: the cursor reset.'}]}, 'timestamp': '2026-11-10T08:21:00Z'}])
    steps, _ = sessionrecord.cli_steps('claude', 'k1')
    assert [x['k'] for x in steps] == ['you', 'said', 'compact', 'said'] and steps[2]['at'] == '2026-11-10T08:20:00Z'
    assert not any('continued from a previous conversation' in str(x.get('text')) for x in steps)
    assert sessionrecord.summarise(steps)['counts']['you'] == 1
    # ...Codex's rollout says the same with its `compacted` item
    jsonl(home / '.codex' / 'sessions' / '2026' / '11' / '10' / 'rollout-2026-11-10T08-00-00-k2.jsonl', [
        {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'Why did March double?'}},
        {'type': 'compacted', 'payload': {'message': 'the earlier turns, summed up'}, 'timestamp': '2026-11-10T08:20:00Z'}])
    assert [x['k'] for x in sessionrecord.cli_steps('codex', 'k2')[0]] == ['you', 'compact']
    # ...and a record SAVED before the fix, the summary kept as a told step, reads as the compaction it was
    s.add_transcript(tid, 'pane-k', 'screen', 'coding', 'C:/work/ledger', 'k9', brain='claude')
    sessionrecord._saved_path(tid, 'pane-k').write_text(json.dumps({'steps': [{'k': 'you', 'text': SUMMARY[:3000]}, {'k': 'said', 'text': 'Go on.'}]}), encoding='utf-8')
    [ses] = codingchat.sessions(s, tid)
    assert [(x['k'], x['text']) for x in ses['steps']] == [('compact', sessionrecord.COMPACTED), ('said', 'Go on.')]


# NOTHING THE OWNER DID NOT TYPE IS HIS (the owner, 2026-11-10: "this is obvious stuff that your stress test should be catching.."): every
# shape a real Claude Code log takes, read into the chat's steps. A user-role entry is the owner's only where the log says a human typed it -
# and what they typed mid-turn, which the log keeps as a queued attachment, is theirs too
U = lambda text, **kw: {'type': 'user', 'message': {'role': 'user', 'content': text}, **kw}
A = lambda *blocks, model='claude-x', **kw: {'type': 'assistant', 'message': {'role': 'assistant', 'model': model, 'content': list(blocks)}, **kw}
SAID = lambda t: {'type': 'text', 'text': t}
HUMAN = {'origin': {'kind': 'human'}}
TOOL = A({'type': 'tool_use', 'id': 'tu1', 'name': 'Bash', 'input': {'command': 'pytest -q ledger'}})
SHAPES = {
    'a background task finishing': [U('Run the tests in the background.', **HUMAN), TOOL,
        U('<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n</task-notification>',
          origin={'kind': 'task-notification', 'producer': 'session-task'}), A(SAID('The tests passed.'))],
    "another agent's message": [U('Ask the helper.', **HUMAN), U('The helper says: done with the importer.', origin={'kind': 'peer', 'from': 'a1'})],
    'an interrupted turn': [U('Fix the importer.', **HUMAN), TOOL,
        U([{'type': 'tool_result', 'tool_use_id': 'tu1', 'is_error': True, 'content': "The user doesn't want to proceed with this tool use."}]),
        U([SAID('[Request interrupted by user for tool use]')]), U([SAID('[Request interrupted by user]')]),
        A(SAID('No response requested.'), model='<synthetic>')],
    'a line typed mid-turn': [U('Fix the importer.', **HUMAN), TOOL,
        {'type': 'attachment', 'attachment': {'type': 'queued_command', 'prompt': 'Only March, please.', 'commandMode': 'prompt', 'origin': {'kind': 'human'}}},
        {'type': 'attachment', 'attachment': {'type': 'queued_command', 'prompt': [SAID('And this screenshot.'), {'type': 'image', 'source': {}}],
                                              'commandMode': 'prompt', 'origin': {'kind': 'human'}}},
        {'type': 'attachment', 'attachment': {'type': 'queued_command', 'prompt': '<task-notification>b1 done</task-notification>',
                                              'commandMode': 'task-notification', 'origin': {'kind': 'task-notification'}}}],
    'a hook, a reminder and a slash command': [U('Fix the importer.', **HUMAN),
        {'type': 'attachment', 'attachment': {'type': 'hook_additional_context', 'content': ['Taskuary: 2 notes wait.']}},
        U('<system-reminder>The task list is empty.</system-reminder>', isMeta=True),
        U('<command-name>/compact</command-name>\n<command-message>compact</command-message>'),
        U('<local-command-stdout>Compacted.</local-command-stdout>')],
    'an API error': [U('Fix the importer.', **HUMAN), A(SAID('API Error: 529 Overloaded. Try again in a moment.'), isApiErrorMessage=True,
                                                        model='<synthetic>')],
    'a tool that failed': [U('Fix the importer.', **HUMAN), TOOL,
        U([{'type': 'tool_result', 'tool_use_id': 'tu1', 'is_error': True, 'content': 'Exit code 1\nE   ModuleNotFoundError: ledger'}])],
    "a helper's sidechain and its result": [U('Find the double read.', **HUMAN),
        A({'type': 'tool_use', 'id': 'tk1', 'name': 'Task', 'input': {'description': 'find the double read', 'prompt': 'Search the importer.'}}),
        U('Search the importer.', isSidechain=True), A(SAID('It is in importer.py.'), isSidechain=True),
        U([{'type': 'tool_result', 'tool_use_id': 'tk1', 'content': [SAID('It is in importer.py:40.\n<system-reminder>x</system-reminder>')]}])],
    'a pasted image': [U([SAID('[Image #1] Why is this red?'), {'type': 'image', 'source': {'type': 'base64', 'data': 'AAAA'}}], **HUMAN)],
    'an empty and a thinking-only answer': [U('Fix the importer.', **HUMAN), A(), A({'type': 'thinking', 'thinking': 'The cursor resets.'})],
}
OWNER = {'a background task finishing': ['Run the tests in the background.'], "another agent's message": ['Ask the helper.'],
         'a line typed mid-turn': ['Fix the importer.', 'Only March, please.', 'And this screenshot.'], 'a pasted image': ['[Image #1] Why is this red?'],
         "a helper's sidechain and its result": ['Find the double read.']}


@pytest.mark.parametrize('shape', list(SHAPES))
def test_nothing_the_owner_did_not_type_is_his(home, shape):
    from taskuary import codingchat
    s = MemoryStore(); tid = Factory(s).task(title='March import doubled')
    lines = [json.dumps(r) for r in SHAPES[shape]]
    # ...the log as it stands when the CLI is killed mid-write: its last line half there
    (p := home / '.claude' / 'projects' / 'C--work-ledger' / 'sh1.jsonl').parent.mkdir(parents=True, exist_ok=True)
    p.write_text('\n'.join(lines) + '\n' + lines[-1][:20], encoding='utf-8')
    s.add_transcript(tid, 'pane-s', 'screen', 'coding', 'C:/work/ledger', 'sh1', brain='claude')
    [ses] = codingchat.sessions(s, tid)
    assert [x['text'] for x in ses['steps'] if x['k'] == 'you'] == OWNER.get(shape, ['Fix the importer.'])
    said = [x['text'] for x in ses['steps'] if x['k'] == 'said']
    assert not any(w in ' '.join(said) for w in ('No response requested', 'API Error')), said
    if shape == 'an API error': assert [x['k'] for x in ses['steps']][-1] == 'error'
    if shape in ('a tool that failed', 'an interrupted turn'):
        [tool] = [x for x in ses['steps'] if x['k'] == 'tool']
        assert tool['status'] == 'failed' and tool['output']
    if shape == 'an empty and a thinking-only answer': assert [x['k'] for x in ses['steps']] == ['you', 'thought']


def test_a_resumed_conversation_is_each_session_with_its_own_turns_never_the_log_twice(home):
    """A pane resumed on its conversation (`claude --resume`) writes on into the same log: the record read that whole log once per session, and
    the Agent work card drew every earlier turn twice (the stress round, 2026-11-10). Each session keeps the turns up to its own end."""
    s = MemoryStore(); tid = Factory(s).task(title='March import doubled')
    jsonl(home / '.claude' / 'projects' / 'C--work-ledger' / 'rs1.jsonl', [
        U('Why did March double?', **HUMAN, timestamp='2026-11-10T08:00:00Z'), A(SAID('The cursor resets.'), timestamp='2026-11-10T08:01:00Z'),
        U('Now fix it.', **HUMAN, timestamp='2026-11-10T09:00:00Z'), A(SAID('Fixed.'), timestamp='2026-11-10T09:01:00Z')])
    end1, end2 = sessionrecord._local('2026-11-10T08:05:00Z'), sessionrecord._local('2026-11-10T09:05:00Z')
    for sid, at in (('pane-1', end1), ('pane-2', end2)):
        s._exec("INSERT INTO transcript (TaskId,Sid,Agent,Text,Brain,ExtId,CreatedAt) VALUES (?,?,?,?,?,?,?)", (tid, sid, 'coding', 'x', 'claude', 'rs1', at))
    recs = {r['sid']: [x['text'] for x in r['steps']] for r in sessionrecord.record(s, tid)['sessions']}
    assert recs == {'pane-1': ['Why did March double?', 'The cursor resets.'], 'pane-2': ['Now fix it.', 'Fixed.']}


def test_sessions_come_newest_first_each_with_its_own_report(home):
    s = MemoryStore(); tid = Factory(s).task(title='Two runs')
    s._exec("INSERT INTO comment (TaskId,Actor,ActorType,Body,CreatedAt) VALUES (?,?,?,?,?)",
            (tid, 'codex', 'agent', 'AGENT REPORT\nSummary: first pass', '2026-10-09 10:00:00'))
    s._exec("INSERT INTO transcript (TaskId,Sid,Agent,Text,Brain,CreatedAt) VALUES (?,?,?,?,?,?)", (tid, 'a', 'coding', 'one', 'codex', '2026-10-09 10:00:05'))
    s._exec("INSERT INTO comment (TaskId,Actor,ActorType,Body,CreatedAt) VALUES (?,?,?,?,?)",
            (tid, 'claude', 'agent', 'AGENT REPORT\nSummary: second pass', '2026-10-10 09:00:00'))
    s._exec("INSERT INTO transcript (TaskId,Sid,Agent,Text,Brain,CreatedAt) VALUES (?,?,?,?,?,?)", (tid, 'b', 'coding', 'two', 'devin', '2026-10-10 09:00:03'))
    recs = sessionrecord.record(s, tid)['sessions']
    assert [(r['sid'], r['report']['summary'], r['source']) for r in recs] == [('b', 'second pass', 'screen'), ('a', 'first pass', 'screen')]


# ONE ACCOUNT, THE LATEST (the owner, 2026-11-02: "it conflicts with each other 10 times saying it was merged but it was not"). The agent's
# `gh pr merge` was held (shellgate); its turn ended "not merged yet - held for your approval"; the owner approved, Taskuary ran the merge
# and told the agent, whose next turn said it was merged. The page showed both turns' words as its result, side by side.
HELD = 'PR #7 is not merged yet. Taskuary held the merge command and it is waiting for you to approve it on the task.'
MERGED = 'After your approval PR #7 was squash-merged into main.'


def merge_session(home, s, tid, ext, decided, second=True, last=None):
    """Turn 1 tries the merge and says it is held; the owner answers at `decided`; turn 2 (when `second`) says it is merged."""
    rows = [{'type': 'user', 'timestamp': '2026-11-02 12:40:00', 'message': {'content': 'Review northwind/ledger#7 and merge it if it is sound.'}},
            {'type': 'assistant', 'timestamp': '2026-11-02 12:45:00', 'message': {'content': [{'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'gh pr merge 7 --squash'}}]}},
            {'type': 'assistant', 'timestamp': '2026-11-02 12:45:10', 'message': {'content': [{'type': 'text', 'text': HELD}]}}]
    if second: rows += [{'type': 'user', 'timestamp': '2026-11-02 12:51:45', 'message': {'content': 'The owner approved it and Taskuary ran it. Carry on.'}},
                        {'type': 'assistant', 'timestamp': '2026-11-02 12:52:00', 'message': {'content': [{'type': 'text', 'text': MERGED}]}}]
    jsonl(home / '.claude' / 'projects' / 'C--work-ledger' / f'{ext}.jsonl', rows)
    rid = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': "held before it ran, in the agent's shell",
                        'DraftText': json.dumps({'action': 'shell_act', 'sid': 'pane-m', 'command': 'gh pr merge 7 --squash', 'what': 'merge a pull request'})})
    if decided: s._exec("UPDATE review SET Status='approved', DecidedBy='owner', DecidedAt=? WHERE ReviewId=?", (decided, rid))
    s._exec("INSERT INTO comment (TaskId,Actor,ActorType,Body,CreatedAt) VALUES (?,?,?,?,?)",
            (tid, 'claude', 'agent', 'AGENT REPORT\nSummary: Reviewed PR #7 and squash-merged it after the owner approved.\n\nLAST MESSAGE\n'
             + (last if last is not None else f'{HELD}\n\n{MERGED}'), '2026-11-02 12:52:30'))
    s._exec("INSERT INTO transcript (TaskId,Sid,Agent,Text,Brain,ExtId,CreatedAt) VALUES (?,?,?,?,?,?,?)",
            (tid, 'pane-m', 'coding', 'screen', 'claude', ext, '2026-11-02 12:52:40'))
    return sessionrecord.record(s, tid)


def test_the_turn_after_the_owners_yes_is_the_one_account_and_the_held_turn_is_not_its_result(home):
    s = MemoryStore(); tid = Factory(s).task(title='1 pull request on northwind/ledger')
    rec = merge_session(home, s, tid, 'm1', '2026-11-02 12:51:39')
    [r] = rec['sessions']
    assert r['result'] == MERGED and HELD not in r['report']['last']
    assert [x.get('stale', False) for x in r['steps'] if x['k'] == 'said'] == [True, False]       # still in the record, as earlier words
    assert [(h['what'], h['state'], h['answered']) for h in rec['held']] == [('merge a pull request', 'done', '2026-11-02 12:51:39')]


def test_a_second_turn_with_no_words_of_its_own_still_never_shows_the_held_turn(home):
    s = MemoryStore(); tid = Factory(s).task(title='1 pull request on northwind/ledger')
    [r] = merge_session(home, s, tid, 'm2', '2026-11-02 12:51:39', second=False, last=f'{HELD}\n\nReviewed and merged PR #7')['sessions']
    assert r['result'] == 'Reviewed and merged PR #7'


def test_a_step_still_held_is_said_held_and_nothing_is_moved_past(home):
    s = MemoryStore(); tid = Factory(s).task(title='1 pull request on northwind/ledger')
    rec = merge_session(home, s, tid, 'm3', None, second=False, last=HELD)
    [r] = rec['sessions']
    assert r['result'] == HELD and not any(x.get('stale') for x in r['steps'])
    assert [(h['state'], h['answered']) for h in rec['held']] == [('held', '')]


def test_a_view_the_agent_showed_is_still_drawn_once_its_turn_is_filed(home):
    # the kept step cut the show call's arguments to strings, so a filed turn's table was gone from the chat (2026-11-09)
    from taskuary import viewspec
    s = MemoryStore(); tid = Factory(s).task(title='Renewals', kind='general')
    rid = s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Two renewals are due.')
    answer = viewspec.shown({'root': 'a', 'elements': {'a': {'type': 'list', 'props': {'items': ['Payworth', 'Trainly']}}}})
    sessionrecord.keep_turn(tid, rid, [
        {'type': 'tool_call', 'name': 'mcp__taskuary__show', 'detail': {'tool_call_id': 'v1', 'args': {'root': 'a', 'elements': {}}}},
        {'type': 'tool_result', 'name': 'v1', 'detail': {'tool_call_id': 'v1', 'result': answer}},
        {'type': 'tool_call', 'name': 'Read', 'detail': {'tool_call_id': 'r1', 'args': {'file_path': 'x.csv'}}},
        {'type': 'tool_result', 'name': 'r1', 'detail': {'tool_call_id': 'r1', 'result': 'a,b'}}])
    show, read = [x for x in sessionrecord.general_steps(s, tid) if x['k'] == 'tool']
    assert show['output'] == answer and 'output' not in read
