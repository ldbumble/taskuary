"""What a run took and cost (the owner, 2026-10-22): kept in the run's record - its working time, and the tokens and cost its CLI's
own log counts, from the run's start only (a resumed conversation's log holds the earlier runs too). A CLI that prices nothing
leaves no cost: an unknown cost is said by saying nothing, never $0."""
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
    monkeypatch.setattr(session_artifacts, 'root', lambda: tmp_path / 'artifacts')
    return tmp_path


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')


def said(at, mid, usage, text='ok', **kw):
    return {'type': 'assistant', 'timestamp': at, **kw, 'message': {'id': mid, 'usage': usage, 'content': [{'type': 'text', 'text': text}]}}


U = lambda i, o, cr=0, cc=0: {'input_tokens': i, 'output_tokens': o, 'cache_read_input_tokens': cr, 'cache_creation_input_tokens': cc}


def claude_log(home, ext):
    # a resumed conversation: the first turn is an earlier run's; the second message spans two lines, one usage
    jsonl(home / '.claude' / 'projects' / 'C--work-ledger' / f'{ext}.jsonl', [
        said('2026-10-22 08:00:00', 'm0', U(500, 500)),
        {'type': 'user', 'timestamp': '2026-10-22 09:00:00', 'message': {'content': 'Fix the March import.'}},
        said('2026-10-22 09:01:00', 'm1', U(100, 40, cr=9000, cc=200), costUSD=0.25),
        said('2026-10-22 09:12:30', 'm2', U(10, 60, cr=9500), text='Fixed: the cursor reset on retry.'),
        said('2026-10-22 09:12:30', 'm2', U(10, 60, cr=9500), text='(same message, its next block)')])


def test_claude_counts_from_the_runs_start_once_per_message(home):
    claude_log(home, 'c1')
    use = sessionrecord.cli_usage('claude', 'c1', '2026-10-22 09:00:00')
    assert use == {'in': 100 + 200 + 9000 + 10 + 9500, 'cached': 18500, 'out': 100, 'cost': 0.25}
    assert sessionrecord.cli_usage('claude', 'c1')['in'] > use['in']            # the whole log holds the earlier run too


def test_a_log_with_no_price_gives_no_cost(home):
    jsonl(home / '.codex' / 'sessions' / '2026' / '10' / '22' / 'rollout-2026-10-22T09-00-00-x1.jsonl', [
        {'type': 'event_msg', 'timestamp': '2026-10-22 08:00:00', 'payload': {'type': 'token_count', 'info': {'last_token_usage': {'input_tokens': 999, 'output_tokens': 9}}}},
        {'type': 'event_msg', 'timestamp': '2026-10-22 09:05:00', 'payload': {'type': 'token_count', 'info': {'last_token_usage': {'input_tokens': 3000, 'cached_input_tokens': 2000, 'output_tokens': 120}}}},
        {'type': 'event_msg', 'timestamp': '2026-10-22 09:06:00', 'payload': {'type': 'token_count', 'info': None}}])
    assert sessionrecord.cli_usage('codex', 'x1', '2026-10-22 09:00:00') == {'in': 3000, 'cached': 2000, 'out': 120}
    assert sessionrecord.cli_usage('cursor', 'x1', '2026-10-22 09:00:00') == {}     # a CLI that keeps no count: nothing said


def test_took_is_start_to_the_last_thing_it_did_not_to_the_pane_closing():
    steps = [{'k': 'said', 'at': '2026-10-22 08:30:00'}, {'k': 'tool', 'at': '2026-10-22 09:02:00'}, {'k': 'said', 'at': '2026-10-22 09:12:30'}]
    assert sessionrecord.took(steps, '2026-10-22 09:00:00', '2026-10-22 13:00:00') == 750
    assert sessionrecord.took([{'k': 'screen', 'text': 'x'}], '2026-10-22 09:00:00', '2026-10-22 09:04:00') == 240   # no times: to its end
    assert sessionrecord.took(steps, '') is None


def test_the_run_record_keeps_them_and_the_card_reads_them(home):
    claude_log(home, 'c1')
    s = MemoryStore(); tid = Factory(s).task(title='March import doubled')
    s.add_transcript(tid, 'pane-1', 'screen text', 'coding', 'C:/work/ledger', 'c1', brain='claude')
    rec = sessionrecord.save(s, tid, 'pane-1', 'claude', 'c1', 'screen text', started='2026-10-22 09:00:00')
    assert rec['took'] == 750 and rec['usage']['cost'] == 0.25
    got = sessionrecord.record(s, tid)['sessions'][0]
    assert (got['took'], got['usage']['out']) == (750, 100)


def test_a_conversation_is_timed_by_its_turns(home):
    s = MemoryStore(); tid = Factory(s).task(title='Vendor spend', kind='general')
    for n, secs in ((1, 40), (2, 25)):
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, f'answer {n}')
        s.audit('task', tid, 'assistant_reply', 'assistant', 'agent', {'provider': 'claude', 'model': 'm', 'chars': 8, 'took': secs})
    got = sessionrecord.record(s, tid)['sessions'][0]
    assert got['took'] == 65 and 'usage' not in got                                 # an API turn counts no tokens here: nothing said
