"""MOVES IN LEARNED.md (the deep dive, 2026-10-20): what the owner presses while the Advisor's line is shown is learned where they can
read it - watching, then "## What you do next" once in use (3+ episodes, 2+ people or threads, share 0.6+; two overrides in a row put
it back to watching) - the Advisor reads it and nothing else does, the reflection never sees the presses (the owner, 2026-10-23), and
deleting the line undoes it."""
from pathlib import Path
from unittest import mock
from taskuary import advisor, learn, learnedgraph
from taskuary.store import MemoryStore

TEMPLATE = (Path(learn.__file__).parent / 'templates' / 'learned.md').read_text(encoding='utf-8')


def issue(s, n, who='Ray Colton', repo='northwind/ledger'):
    t = s.create_task({'Title': f'#{n} import fails', 'Status': 'open'}, 'owner')
    mid = s.add_message({'ConversationId': f'github:{n}', 'Channel': 'github', 'Subject': f'#{n} import fails', 'FromName': who,
                         'SourceName': repo, 'BodyText': 'Traceback', 'Status': 'routed', 'TaskId': t})
    return t, mid


def pressed(s, n, verb='regular_agent', who='Ray Colton', advised='reply'):
    t, mid = issue(s, n, who)
    with mock.patch.object(advisor, '_item', lambda store, tk, ti, key=None: {'key': key, 'kind': 'todo', 'tid': t, 'mid': mid, 'channel': 'github'}):
        return advisor.press(s, f'task:{t}', advised, verb)


def store():
    s = MemoryStore(); s.save_doc('learned', TEMPLATE, 'seed'); return s


def section(doc, head):
    return doc.split(head, 1)[1].split('\n## ', 1)[0] if head in doc else ''


def test_a_habit_is_a_hypothesis_first_then_a_move_and_the_advisor_reads_it():
    s = store()
    pressed(s, 1, who='Ray Colton'); pressed(s, 2, who='Ray Colton')
    doc = s.get_doc('learned')
    hyp = learn._block(doc, learn.HYP_START, learn.HYP_END)
    assert 'On GitHub items from northwind/ledger, {{owner_first}} presses Send to agent (2 of 2)' in hyp and '[s:3 |' in hyp
    assert 'Send to agent' not in section(doc, learn.NEXT)
    item = {'key': 'task:1', 'kind': 'todo', 'tid': 1, 'title': 'x'}
    assert 'Send to agent' not in advisor._learned(s), 'a guess is never in a prompt'
    pressed(s, 3, who='Gail Moreno')                                        # s:4, three episodes, two people: it holds
    doc = s.get_doc('learned')
    line = next(l for l in learnedgraph.lines(doc) if l['key'].startswith('move '))
    assert (line['status'], line['score'], line['section']) == ('live', 4, 'What you do next')
    assert 'presses Send to agent (3 of 3)' in section(doc, learn.NEXT) and all(e.startswith('pr') for e in line['ev'])
    assert 'presses Send to agent (3 of 3)' in advisor._learned(s), 'the Advisor reads the moves'
    assert learnedgraph._resolve(s, line['ev'][0])['label'].startswith('pressed regular_agent on GitHub items from northwind/ledger (the Advisor lit reply)')


def test_one_hot_thread_is_not_a_move_and_another_verb_weakens_it():
    s = store()
    for n in (1, 2, 3): pressed(s, n, who='Ray Colton')
    l = next(l for l in learnedgraph.lines(s.get_doc('learned')) if l['key'].startswith('move '))
    assert l['status'] == 'hypothesis', 'three presses from one person prove nothing general'
    pressed(s, 4, verb='not_ours', who='Gail Moreno')
    l = next(l for l in learnedgraph.lines(s.get_doc('learned')) if l['key'].startswith('move '))
    assert l['score'] == 3 and '(3 of 4)' in l['text']


def test_deleting_the_line_undoes_it_and_only_later_presses_count():
    s = store()
    pressed(s, 1, who='Ray Colton'); pressed(s, 2, who='Gail Moreno'); pressed(s, 3, who='Omar Keller')
    doc = s.get_doc('learned')
    raw = next(r for r, l in learnedgraph.walk(doc) if l and l['key'].startswith('move '))
    s.save_doc('learned', doc.replace(raw + '\n', ''), 'owner')                 # the owner deletes it
    pressed(s, 4, who='Ray Colton')
    doc = s.get_doc('learned')
    l = next(l for l in learnedgraph.lines(doc) if l['key'].startswith('move '))
    assert (l['status'], l['score']) == ('hypothesis', 2) and '(1 of 1)' in l['text'], 'counted again from the delete on'


def test_the_reflection_never_sees_the_presses_and_its_rewrite_never_loses_the_count():
    s = store()
    pressed(s, 1); pressed(s, 2, who='Gail Moreno')
    g = learn.gather(s, '2000-01-01')
    assert 'MOVES' not in g and 'pr1' not in g, 'press habits never reach triage - nor the pass that writes what triage reads'
    assert s.get_setting('learn_pending') in (None, '', '0'), 'a press is not a correction for the reflection'
    assert 'pr ids' in learn.REFLECT_SYSTEM
    doc = s.get_doc('learned')
    raw = next(r for r, l in learnedgraph.walk(doc) if l and l['key'].startswith('move '))
    s.save_doc('learned', doc.replace(raw + '\n', ''), 'reflect')               # a rewrite that dropped it
    learn.moves(s, restore=True)
    assert any(l['key'].startswith('move ') for l in learnedgraph.lines(s.get_doc('learned')))


def test_the_habit_under_the_line_is_the_owners_presses_on_this_kind_of_item():
    s = store()
    pressed(s, 1, verb='regular_agent'); pressed(s, 2, verb='reply'); pressed(s, 3, verb='regular_agent')
    t, mid = issue(s, 9)
    n, m, where = advisor.habit(s, 'regular_agent', {'kind': 'todo', 'tid': t, 'mid': mid, 'channel': 'github'})
    assert (n, m) == (2, 3) and where == 'press:GitHub items from northwind/ledger'
    assert advisor.says('regular_agent', (n, m, where)).startswith("Your own habit, not the Advisor's record: you pressed Send to agent 2 of the last 3")


def test_two_overrides_in_a_row_put_a_habit_back_to_watching_under_the_same_key():
    s = store()
    pressed(s, 1, who='Ray Colton'); pressed(s, 2, who='Gail Moreno'); pressed(s, 3, who='Omar Keller')
    pressed(s, 4, who='Erin Blake'); pressed(s, 5, who='Paula Vance')
    key = next(l['key'] for l in learnedgraph.lines(s.get_doc('learned')) if l['key'].startswith('move '))
    assert learnedgraph.lines(s.get_doc('learned'))[0]['status'] == 'live'
    pressed(s, 6, verb='not_ours', who='Ray Colton')                           # one override: still in use (5 of 6)
    l = next(l for l in learnedgraph.lines(s.get_doc('learned')) if l['key'] == key)
    assert l['status'] == 'live'
    pressed(s, 7, verb='not_ours', who='Gail Moreno')                          # two in a row: watching, the same line
    l = next(l for l in learnedgraph.lines(s.get_doc('learned')) if l['key'] == key)
    assert l['status'] == 'hypothesis' and '(5 of 7)' in l['text']
    assert 'presses Send to agent' not in advisor._learned(s), 'a watching habit reaches no prompt'
    assert any(h['Action'] == 'watching' for h in s.learned_history(key))
    assert [h['Action'] for h in s.learned_history(key)].count('born') == 1, 'never deleted and born again'
    from taskuary import learnedlines
    assert learnedlines.row(s, key)['Status'] == 'watching'
    pressed(s, 8, who='Omar Keller')                                           # pressed again: in use again, still one key
    assert learnedlines.row(s, key)['Status'] == 'in_use'


def test_in_use_is_three_episodes_from_two_people_at_a_share_of_six_in_ten_and_under_it_is_no_habit():
    s = store()
    for n, (verb, who) in enumerate([('regular_agent', 'Ray Colton'), ('reply', 'Gail Moreno'), ('regular_agent', 'Omar Keller'),
                                     ('reply', 'Erin Blake'), ('regular_agent', 'Paula Vance')], 1):
        pressed(s, n, verb=verb, who=who)
    assert [l['text'] for l in learnedgraph.lines(s.get_doc('learned')) if l['status'] == 'live'] == [
        'On GitHub items from northwind/ledger, {{owner_first}} presses Send to agent (3 of 5)']
    pressed(s, 6, verb='reply', who='Marcus Reed')                             # 3 of 6: half the time is not a habit
    assert not [l for l in learnedgraph.lines(s.get_doc('learned')) if l['key'].startswith('move ')]
