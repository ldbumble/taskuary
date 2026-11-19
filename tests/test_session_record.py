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


# A CALL'S ARGUMENTS ARRIVE AS A JSON STRING on Codex's function_call (the walk, 2026-11-17): kept as a string, a write had no file or edit and
# a draft no arguments at all, so the chat drew "Writing <its own text>" and "Running a command" for an email
def test_a_codex_call_with_json_string_arguments_keeps_them_as_arguments(home):
    body = 'Hi Erin,' + chr(10) * 2 + 'The run sheet is attached - see n @path for the totals.'
    jsonl(home / '.codex' / 'sessions' / '2026' / '11' / '17' / 'rollout-2026-11-17T09-00-00-s1.jsonl', [
        {'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'write_file',
                                              'arguments': json.dumps({'path': '/work/run-sheet.md', 'content': body})}},
        {'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'mcp__taskuary__propose_email',
                                              'arguments': json.dumps({'to': 'erin@northwind.example', 'subject': 'Run sheet', 'text': body})}}])
    wrote, drafted = sessionrecord.cli_steps('codex', 's1')[0]
    assert (wrote.get('args'), wrote.get('file')) == ({'path': '/work/run-sheet.md'}, '/work/run-sheet.md')
    assert wrote['edit'] == {'parts': [{'old': '', 'new': body}]}
    assert drafted['name'] == 'mcp__taskuary__propose_email' and body not in json.dumps(drafted)      # ...and the draft's body stays in the draft


def test_copilot_events_read_and_an_unknown_cli_keeps_its_screen(home):
    jsonl(home / '.copilot' / 'session-state' / 'k1' / 'events.jsonl', [
        {'type': 'user.message', 'data': {'content': 'List the stale branches.'}},
        {'type': 'assistant.message', 'data': {'content': '', 'reasoningText': 'git for-each-ref sorts by date.'}},
        {'type': 'tool.execution_start', 'data': {'toolCallId': 't1', 'toolName': 'powershell', 'arguments': {'command': 'git for-each-ref'}}},
        # ...a tool's failure is its call's, failed, as Claude's is - never a note of its own with the tool's words whole (design round 5, 2026-11-19)
        {'type': 'tool.execution_complete', 'data': {'toolCallId': 't1', 'success': False, 'error': {'message': 'not a git repository'}}},
        {'type': 'assistant.message', 'data': {'content': 'Three branches are older than 90 days.'}}])
    steps, _ = sessionrecord.cli_steps('copilot', 'k1')
    assert [s['k'] for s in steps] == ['you', 'thought', 'tool', 'said']
    assert (steps[2]['status'], steps[2]['output']) == ('failed', 'not a git repository')
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
    "A quick answer filed while it was one JSON call kept its raw object as the turn's working, cut at SAID_N: read back, it is dropped."
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
    # ...AND A SESSION OVER ACP THAT REOPENS THAT CONVERSATION IS NEVER READ AS ITS CLI'S LOG (the recorded restart, 2026-11-11): before it
    # has kept its first update it holds nothing yet - read as a pane's it was the whole log again, every earlier turn stamped now, and one
    # read of the chat drew all his lines first and all the turns after them
    from types import SimpleNamespace
    from unittest import mock
    from taskuary import terminal as term
    live = SimpleNamespace(sid='acp-new', task_id=tid, alive=True, mode='auto', acp=True, cli='claude', ext_id='k1', started='2026-11-11 23:37:00')
    with mock.patch.dict(term.SESSIONS, {'acp-new': live}):
        got = codingchat.sessions(s, tid)
    assert [(x['sid'], x['source'], x.get('updates')) for x in got if x['live']] == [('acp-new', 'acp', [])], got


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


def test_a_note_taskuary_typed_before_it_marked_its_notes_is_its_brief(home):
    """2026-11-10: a coding chat showed "You - The owner approved it and Taskuary ran `gh pr comment 12` ..." - an approval typed into the session
    the day before notes were marked. Its fixed opening, Taskuary's own words, makes it Taskuary's line."""
    s = MemoryStore(); tid = Factory(s).task(title='Answer the review')
    told = 'The owner approved it and Taskuary ran `gh pr comment 12 --body ok` in C:/work/ledger. It said: https://github.com/northwind/ledger/pull/12. Carry on.'
    steps = sessionrecord.mark_briefs(tid, [{'k': 'you', 'text': 'Answer the review comment'}, {'k': 'you', 'text': told}])
    assert [x['k'] for x in steps] == ['you', 'brief']


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


def test_a_coding_chat_polled_again_reads_each_cli_log_once_per_version(home, monkeypatch):
    """The owner's live app, 2026-11-16: a coding task's chat took 15-43 s a poll - every poll parsed each session's whole CLI log again
    (~1 s per 100 MB) while the page polled every few seconds. The conversation is built from a log read once per (file, mtime, size): polled
    again it reads nothing, and only a log that grew is read again."""
    import os
    from taskuary import conversation
    monkeypatch.setattr(sessionrecord, '_STEPS', {}, raising=False)
    s = MemoryStore(); tid = s.create_task({'Title': 'Fix the March import', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
    for i in range(3):
        claude_log(home, f'big{i}')
        s._exec("INSERT INTO transcript (TaskId, Sid, Brain, ExtId, CreatedAt) VALUES (?,?,?,?,datetime('now'))", (tid, f's{i}', 'claude', f'big{i}'))
    reads, real = [], sessionrecord.READERS['claude']
    monkeypatch.setitem(sessionrecord.READERS, 'claude', (real[0], lambda f: reads.append(f.name) or real[1](f), real[2]))
    first = conversation.items(s, tid)
    assert sorted(reads) == ['big0.jsonl', 'big1.jsonl', 'big2.jsonl']
    for _ in range(5): assert conversation.items(s, tid)['rev'] == first['rev']
    assert len(reads) == 3, f'a poll read a log again: {reads}'
    f = home / '.claude' / 'projects' / 'C--work-ledger' / 'big1.jsonl'
    f.write_text(f.read_text(encoding='utf-8') + '\n' + json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'One more check.'}]}}), encoding='utf-8')
    os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 10**9))
    conversation.items(s, tid)
    assert reads[3:] == ['big1.jsonl'], 'only the log that grew is read again'


def test_a_log_that_grows_while_its_agent_works_is_read_once_byte_for_byte(home, monkeypatch):
    """The owner's live app, 2026-11-16: a WORKING coding agent's Claude Code log grows every few seconds, so the per-version cache missed on
    every poll and each poll parsed the whole multi-hundred-MB log again - 25-40 s a call. Polled while it grows by small appends - a line cut
    in half among them - each byte is read once, and the steps are the ones a whole read gives. A log replaced by another is read afresh."""
    monkeypatch.setattr(sessionrecord, '_STEPS', {})
    f = home / '.claude' / 'projects' / 'C--work-ledger' / 'grow.jsonl'; f.parent.mkdir(parents=True, exist_ok=True)
    pad = 'x' * 20000                                     # long lines, as a real log's tool results are
    line = lambda i: json.dumps({'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'id': f'u{i}', 'name': 'Read', 'input': {'file_path': f'ledger/f{i}.py'}}, {'type': 'text', 'text': f'step {i} {pad}'}]}}) + '\n'
    done = lambda i: json.dumps({'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': f'u{i}', 'is_error': True, 'content': 'no such file'}]}}) + '\n'
    f.write_text(''.join(line(i) for i in range(500)), encoding='utf-8')        # ~10 MB to start
    read, real = [], sessionrecord._read_from
    monkeypatch.setattr(sessionrecord, '_read_from', lambda p, pos: (lambda b: read.append(len(b)) or b)(real(p, pos)))
    first, _ = sessionrecord.cli_steps('claude', 'grow')
    for k in range(10):
        add = line(500 + k) + done(500 + k)
        cut = len(add) // 3 if k == 4 else len(add)
        with open(f, 'a', encoding='utf-8') as h: h.write(add[:cut])
        steps, _ = sessionrecord.cli_steps('claude', 'grow')
        if cut < len(add):
            with open(f, 'a', encoding='utf-8') as h: h.write(add[cut:])
    steps, _ = sessionrecord.cli_steps('claude', 'grow')
    size = f.stat().st_size
    assert sum(read) - size < len(line(504)), f'read {sum(read)} bytes of a {size}-byte log: a byte read twice is only the half line that waited'
    assert steps == sessionrecord._claude(f), 'the same steps a whole read gives'
    assert [s.get('status') for s in steps if s['k'] == 'tool'][-1] == 'failed', 'a call its later line completes is completed'
    f.write_text(line(0), encoding='utf-8')                                     # replaced, shorter: read from the start
    assert len(sessionrecord.cli_steps('claude', 'grow')[0]) == 2


def test_five_reads_of_one_task_at_once_are_one_build(home, monkeypatch):
    "The old build (frozen for migration, conversation_legacy): reads of one task at once wait for one build and share it."
    import threading, time
    from taskuary import conversation_legacy as conversation
    s = MemoryStore(); tid = s.create_task({'Title': 'Fix the March import', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
    builds, real = [], conversation._items
    monkeypatch.setattr(conversation, '_items', lambda st, t: (builds.append(t), time.sleep(0.5), real(st, t))[2])
    got, go = [], threading.Barrier(5)
    ts = [threading.Thread(target=lambda: (go.wait(), got.append(conversation.items(s, tid)))) for _ in range(5)]
    for t in ts: t.start()
    for t in ts: t.join(10)
    assert len(builds) == 1 and len(got) == 5 and all(g is got[0] for g in got)
    conversation.items(s, tid); assert len(builds) == 2, 'a read after the build is its own'


def test_a_thought_being_written_is_one_open_step_its_snapshots_update(monkeypatch):
    """The owner, 2026-11-16: "Thinking..." for three minutes with nothing else - the ACP road traced a thought only once it was whole. As it
    streams its newest words go out about once a second (agents.ACPSteps), read here as ONE open thought the whole paragraph then replaces."""
    from taskuary import agents
    said, clock = [], [0.0]
    monkeypatch.setattr(agents.time, 'monotonic', lambda: clock[0])
    feed = agents.ACPSteps(lambda *e: said.append(e), 'claude')
    for i, w in enumerate(['The owner wants ', 'two bakeries. ', 'Tatte opens at 7, ', 'so check Bakey next.']):
        clock[0] = i * 0.6
        feed({'sessionUpdate': 'agent_thought_chunk', 'content': {'type': 'text', 'text': w}})
    live = [d for k, n, d in said if k == 'live' and n == 'thinking']
    assert live == ['The owner wants', 'The owner wants two bakeries. Tatte opens at 7,'], live      # ...about once a second, not per chunk
    feed({'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': 'Tatte opens first.'}})    # ...the thought is whole
    steps = sessionrecord.trace_steps([{'type': k, 'name': n, 'detail': d} for k, n, d in said])
    assert [s['k'] for s in steps] == ['thought'] and not steps[0].get('live') and steps[0]['text'].endswith('so check Bakey next.')
    mid = sessionrecord.trace_steps([{'type': 'live', 'name': 'thinking', 'detail': x} for x in live])
    assert [(s['k'], s['text'], s.get('live')) for s in mid] == [('thought', live[-1], True)], 'mid-thought: one open step, its newest words'
    # ...and the answer as it streams: snapshots too, the turn's line of what it is doing (a long answer read "Thinking..." for 85 s)
    said.clear(); clock[0] = 10.0
    for w in ['Salem is close. ', 'Providence is cheaper.']: feed({'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': w}})
    assert [d for k, n, d in said if (k, n) == ('live', 'writing')] == ['Tatte opens first.Salem is close.']    # ...the words as they streamed


def test_a_call_whose_result_came_back_has_finished_while_the_model_writes():
    """Walk evidence, 2026-11-17: "Reading notes.md" stood on the working line for 10 s after the read was done, while the model wrote its
    answer - the turn at work's steps never said a call had its result, so the newest call read as running until another step came."""
    tr = [{'type': 'tool_call', 'name': 'Read', 'detail': {'tool_call_id': 'c1', 'args': {'file_path': 'notes.md'}}},
          {'type': 'tool_result', 'name': 'c1', 'detail': {'tool_call_id': 'c1', 'result': '1 line'}},
          {'type': 'tool_call', 'name': 'Grep', 'detail': {'tool_call_id': 'c2', 'args': {'pattern': 'budget'}}},
          {'type': 'live', 'name': 'writing', 'detail': 'The plan is'}]
    st = sessionrecord.trace_steps(tr)
    assert [(s['name'], s.get('status')) for s in st] == [('Read', 'completed'), ('Grep', None)], 'only a call still waiting on its result runs'


def test_the_turn_at_work_says_when_its_agent_is_still_opening_and_what_it_is_writing(monkeypatch):
    """Recorded on the real CLI, 2026-11-16: a cold adapter took most of a minute to open under "Thinking...", then a long answer streamed in
    under the same word. The turn at work says it is `opening` until its road hands the agent the prompt, and carries the answer being
    written as `doing` while that is the newest thing it did."""
    from types import SimpleNamespace
    from taskuary import conversation
    s = MemoryStore(); tid = s.create_task({'Title': 'Plan the offsite', 'Kind': 'general', 'Status': 'in_progress'}, 'owner')
    ses = SimpleNamespace(busy=True, trace=[{'type': 'start', 'name': None, 'detail': {}}], sid='s1', last=0, task_id=tid)
    monkeypatch.setattr(general, 'session_for', lambda t: ses if t == tid else None)
    monkeypatch.setattr(general, 'at_work', lambda t: True); monkeypatch.setattr(general, 'working', lambda st, t: True)      # ...its turn is at work
    turn = lambda: [x for x in conversation.items(s, tid)['items'] if x['kind'] == 'turn'][-1]
    assert 'opening' not in turn(), 'a turn a beat in, its trace holding only its start, is no start-up (a kept conversation)'
    ses.trace.append({'type': 'opening', 'name': 'claude', 'detail': ''})            # ...the road really opens one (clipool.take)
    assert turn().get('opening') is True and 'doing' not in turn()
    ses.trace += [{'type': 'prompt', 'name': 'prompt_sent_to_agent', 'detail': 'x'}, {'type': 'live', 'name': 'writing', 'detail': 'Option one is Salem.'}]
    assert 'opening' not in turn() and turn()['doing'] == 'Option one is Salem.'
    ses.trace.append({'type': 'tool_call', 'name': 'WebSearch', 'detail': {'tool_call_id': 'c1', 'args': {'query': 'Salem hotels'}}})
    assert 'doing' not in turn(), 'a step after the words leads'


def test_a_failed_calls_note_is_named_by_its_call():
    """The UI judge, 2026-11-18: a Taskuary tool's refusal filed as its own "⚠" note on the general road read whole, the agent's next step and
    all - the page leaves that line out of a Taskuary tool's words only (stepWhy.forOwner), so the note says which call it came from."""
    steps = sessionrecord.trace_steps([
        {'type': 'tool_call', 'name': 'mcp__taskuary__share', 'detail': {'tool_call_id': 'c1', 'args': {'report': 9}}},
        {'type': 'tool_result', 'name': 'c1', 'detail': {'tool_call_id': 'c1', 'result': 'there is no report 9\nNext: ...', 'is_error': True}},
        {'type': 'error', 'name': 'assistant', 'detail': {'result': 'the turn failed', 'is_error': True}}])
    assert [(s['k'], s.get('name')) for s in steps] == [('tool', 'mcp__taskuary__share'), ('error', 'mcp__taskuary__share'), ('error', None)], steps


def test_a_failed_calls_note_is_cut_in_what_happened_never_across_its_next_step():
    """The UI judge, 2026-11-18: the note was cut at 400 characters, inside the refusal's " ⏎ Next: ..." line for a 391-399-character one (a
    stranger's long name and address), and the owner's note ended "...on the task. Nex…" - the page no longer saw a step to leave out."""
    from taskuary import agenttools
    who = 'Paula Alexandra Vance-Whitcombe <paula.alexandra.vance-whitcombe@vendor.example>'
    for n in range(391, 400):
        what = (f"a stranger's task does not read the owner's mail: this task carries a message from someone the owner has not vouched for ({who}). "
                "If the owner knows the sender, they can press Trust by that name on the task.")
        what = what + 'x' * (n - len(what))
        said = agenttools.refusal(what, 'work from what your brief already shows of this task')
        for kept in (said, said.replace('\n', agenttools.LINE_MARK)):           # ...as the CLI's road keeps a result: its breaks the app's mark
            steps = sessionrecord.trace_steps([
                {'type': 'tool_call', 'name': 'mcp__taskuary__search_messages', 'detail': {'tool_call_id': 'c1', 'args': {}}},
                {'type': 'tool_result', 'name': 'c1', 'detail': {'tool_call_id': 'c1', 'result': kept, 'is_error': True}}])
            note = steps[1]['text']
            assert note.endswith(f'{agenttools.NEXT_STEP}work from what your brief already shows of this task'), (n, note[-80:])
            assert note.startswith(what), n
