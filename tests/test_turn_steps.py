"""tools/turn_steps.py on a synthetic home: what an agent's turns on an AI card did, in keys and counts - never a word of what they read."""
import importlib.util, pathlib, tempfile
from unittest import mock
from taskuary import general, sessionrecord, session_artifacts
from taskuary.store import SQLiteStore

spec = importlib.util.spec_from_file_location('turn_steps', pathlib.Path(__file__).parents[1] / 'tools' / 'turn_steps.py')
ts = importlib.util.module_from_spec(spec); spec.loader.exec_module(ts)
call = lambda n, **a: {'type': 'tool_call', 'name': n, 'detail': {'args': a}}


def home():
    "A home with one task worked on an AI card (two turns) and one on a CLI - Erin's renewal mail on the first."
    d = pathlib.Path(tempfile.mkdtemp(prefix='turn-steps-test-')); s = SQLiteStore(d / 'taskuary.db')
    card, cli = (s.create_task({'Title': f'Payworth renewal {i}', 'Kind': 'general', 'Status': 'open'}, 'owner') for i in range(2))
    mid = s.add_message({'TaskId': card, 'ExternalId': 'x-1', 'Channel': 'email', 'Subject': 'Payworth renewal', 'FromName': 'Erin Blake',
                         'FromEmail': 'erin@northwind.example', 'SentAt': '2026-11-09 09:00:00', 'BodyText': 'Do we renew by Friday?', 'Status': 'routed'})
    for tid, pick, calls in ((card, 'connector:1', (6, 60_000, 30_000)), (cli, 'cli:claude', (1, 9_000, 0))):
        s.add_brain_route({'At': '2026-01-01 00:00:00', 'Job': 'general', 'TaskId': tid, 'Pick': pick, 'Calls': calls[0], 'TokensIn': calls[1], 'Cached': calls[2]})
    turn = lambda tid, *steps: sessionrecord.keep_turn(tid, s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'done'), list(steps))
    with mock.patch.object(session_artifacts, 'root', return_value=d / 'artifacts'):
        turn(card, call('my_task'), call('search_messages', words='renewal'), call('read_message', id=f'm{mid}'), call('search_messages', words='renewal'),
             call('person', name='Erin Blake'), call('read_message', id='m9999'))
        turn(cli, call('Read', file_path='notes.md'), call('Read', file_path='notes.md'))
    return s, d


def test_a_turn_on_a_card_is_counted_by_its_steps_repeats_and_reads_of_what_its_prompt_held():
    s, d = home()
    got = ts.turns(s, d / 'artifacts')
    assert got == [{'steps': 6, 'tools': ['my_task', 'search_messages', 'read_message', 'search_messages', 'person', 'read_message'],
                    'repeats': 1, 'prompt_had': 3, 'calls': 6, 'in': 60_000, 'cached': 30_000, 'in_per_call': 10_000}], 'the CLI turn is not counted'
    out = ts.summary(got)
    assert (out['turns'], out['repeats'], out['prompt_had'], out['cached_pct'], out['first:my_task']) == (1, 1, 3, 50, 1)


def test_run_on_a_copy_it_prints_keys_and_counts_and_no_word_of_the_mail(capsys):
    s, d = home()
    assert ts.main(['--db', str(d / 'taskuary.db'), '--each']) == 0
    out = capsys.readouterr().out
    assert 'turns: 1' in out and 'repeats: 1' in out and 'turn 1: steps 6 | my_task>search_messages>' in out
    assert not any(w in out for w in ('Erin', 'northwind', 'renew', 'Payworth', 'm9999')), out
