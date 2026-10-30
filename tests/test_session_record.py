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
    assert steps[2] == {'k': 'tool', 'name': 'Grep', 'text': 'cursor in ledger/', 'at': None}
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
