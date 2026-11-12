"""KILLER IDEAS, QUIET UNLESS SURE (the design's S7; the owner, 2026-11-01). The rail Advisor says what KIND each of its own lines is;
a kind the owner's record says is under 80% useful is held; a line about work the owner touched today is held; a second model look holds
what the owner would already know; and the habits are tests/test_habits_row.py. Invented people only."""
import json
from datetime import datetime, timedelta
import pytest
from taskuary import assistant, ideacheck, ideagrade
from taskuary.store import MemoryStore
from taskuary.testing import Factory

def ago(**k): return (datetime.now() - timedelta(**k)).strftime('%Y-%m-%d %H:%M:%S')


def _idea(s, n, kind, status='open', by=None, at=None):
    at = at or ago(days=3)
    s._exec('INSERT INTO idea (IdeaId, Key, Kind, Text, ActionJson, Status, FirstSeen, LastSaid, SaidCount, DecidedBy) VALUES (?,?,?,?,?,?,?,?,1,?)',
            (n, f'idea:{kind}-{n}', kind, 'x', '{}', status, at, at, by))


def test_a_kind_under_eighty_percent_useful_on_ten_graded_is_quiet_and_the_apps_own_kinds_never_are():
    s = MemoryStore()
    for n in range(1, 11): _idea(s, n, 'idea', 'done', 'owner' if n <= 6 else 'sweep')          # 6 handled, 4 walked past: 60%
    for n in range(11, 21): _idea(s, n, 'pattern', 'done', 'owner')                               # 10 of 10
    for n in range(21, 31): _idea(s, n, 'health', 'done', 'sweep')                                # the app's own kind: counted, never quiet
    for n in range(31, 36): _idea(s, n, 'clash', 'dismissed', 'owner')                            # five: too few to say
    assert ideagrade.record(s)['idea']['pct'] == 60
    assert ideagrade.quiet_kinds(s) == set(), 'nothing is quiet on the record from before the second look began'
    s.set_setting(ideagrade.SINCE_KEY, ago(days=40), 't')
    assert ideagrade.quiet_kinds(s) == {'idea'}


def _say(key, kind='pattern', **act): return {'key': key, 'kind': kind, 'text': f'line {key}', 'why': 'because', 'action': act}


def test_the_second_look_holds_a_quiet_kind_work_touched_today_and_what_the_owner_would_already_know():
    s = MemoryStore()
    for n in range(1, 11): _idea(s, n, 'idea', 'done', 'sweep')                                   # 'idea' is quiet: 0 of 10
    _idea(s, 11, 'idea', at=ago(hours=1))                                                        # ...and raised its one line today
    s.set_setting(ideagrade.SINCE_KEY, ago(days=40), 't')
    f = Factory(s)
    t = f.task(title='Q4 variance'); u = f.task(title='Board pack')
    s._exec("INSERT INTO outcome (Kind,TargetKind,TargetId,Actor,At,FactsJson) VALUES ('reply.sent','task',?,'owner',?,'{}')", (t, ago(hours=2)))
    say = [_say('idea:plain', 'idea'), _say('idea:touched', tid=t), _say('idea:obvious', tid=u), _say('idea:killer', 'clash', tid=u),
           {'key': 'health:disk', 'kind': 'health', 'text': 'disk', 'action': {}}]
    seen = {}
    def llm(system, user, **k):
        seen['user'] = user
        return json.dumps({'known': [1]})                                                        # NOTE 1 is the obvious one
    kept, held = ideacheck.check(s, say, llm)
    assert [x['key'] for x in kept] == ['idea:killer', 'health:disk']
    assert dict(held) == {'idea:plain': "its kind (idea) is under 80% useful lately - one a day",'idea:touched': 'the owner acted on it in the last day (reply.sent)',
                          'idea:obvious': 'the owner would already know it'}
    assert 'NOTE 1: line idea:obvious' in seen['user'] and 'NOTE 2: line idea:killer' in seen['user']
    # ...and a check that cannot run holds nothing back
    kept, held = ideacheck.check(s, [_say('idea:x', tid=u)], lambda *a, **k: (_ for _ in ()).throw(RuntimeError('down')))
    assert [x['key'] for x in kept] == ['idea:x']


def test_a_quiet_kind_still_raises_one_line_a_day_past_the_second_look_and_a_finished_task_from_an_idea_is_taken():
    """The live shape (2026-11-12): the untyped idea graded 58% on 24 - so every line of it was held, for the whole 30-day window, and
    the owner had no ideas for days. The bar narrows: one line a day of a quiet kind goes on to the second look, the rest wait."""
    s = MemoryStore()
    for n in range(1, 11): _idea(s, n, 'idea', 'done', 'sweep')                                   # 0 of 10: quiet
    s.set_setting(ideagrade.SINCE_KEY, ago(days=40), 't')
    assert ideagrade.quiet_kinds(s) == {'idea'}
    asked = []
    def llm(system, user, **k): asked.append(user); return json.dumps({'known': []})
    say = [_say('idea:board-pack', 'idea'), _say('idea:second', 'idea'), _say('idea:clash', 'clash')]
    kept, held = ideacheck.check(s, say, llm)
    assert [x['key'] for x in kept] == ['idea:board-pack', 'idea:clash'] and [k for k, _ in held] == ['idea:second']
    assert 'NOTE 1: line idea:board-pack' in asked[0], 'it is still judged by the second look'
    s.upsert_idea({'key': 'idea:board-pack', 'kind': 'idea', 'text': 'x', 'action': {}}, ago(minutes=1))
    kept, held = ideacheck.check(s, [_say('idea:third', 'idea')], llm)
    assert kept == [] and held == [('idea:third', 'its kind (idea) is under 80% useful lately - one a day')], 'today it has raised its one'
    # ...and an idea triage made a task of, the task finished, is work done from it - it mends the record
    t = Factory(s).task(title='Chase the Payworth refund', status='done', SourceRef='assistant:idea:3')
    assert t and ideagrade.grade(s._rows, s._one('SELECT * FROM idea WHERE IdeaId=3'), ago()) == 'taken'
    assert ideagrade.grade(s._rows, s._one('SELECT * FROM idea WHERE IdeaId=4'), ago()) == 'walked'


def test_an_idea_the_app_put_down_as_it_was_raised_is_not_graded_and_one_left_alone_is_walked_past():
    """Decided 2026-11-12: an idea the report's judge, the rail or a gate put down inside the run that raised it was never the owner's
    to see - it says nothing about usefulness. One raised, left on the rail and let be is still walked past."""
    s = MemoryStore()
    for n, by, after in ((1, 'report', timedelta(seconds=2)), (2, 'funnel', timedelta(minutes=1)), (3, 'sweep', timedelta(days=2))):
        _idea(s, n, 'idea', 'done', by)
        s._exec('UPDATE idea SET DecidedAt=? WHERE IdeaId=?', ((datetime.now() - timedelta(days=3) + after).strftime('%Y-%m-%d %H:%M:%S'), n))
    _idea(s, 4, 'idea')                                                                           # open, read and let be
    got = {n: ideagrade.grade(s._rows, s._one('SELECT * FROM idea WHERE IdeaId=?', (n,)), ago()) for n in range(1, 5)}
    assert got == {1: 'unseen', 2: 'unseen', 3: 'walked', 4: 'walked'}
    assert ideagrade.record(s)['idea'] == {'taken': 0, 'handled': 0, 'wrong': 0, 'walked': 2, 'pending': 0, 'n': 2, 'pct': 0}


def test_a_line_held_on_the_clocks_look_is_not_asked_about_again_until_something_about_it_changes():
    """The live shape (2026-11-12): a line the second look held is never posted, so every half-hour look raised it again and the second
    look was asked about the same note all night - the 'advisor' job, 3-4K tokens a call, an empty answer each time."""
    s, asked = MemoryStore(), []
    u = Factory(s).task(title='Board pack')
    def llm(system, user, **k): asked.append(user); return json.dumps({'known': [1]})
    look = lambda key, memo='advisor_idea_check_mark:7': ideacheck.check(s, [_say(key, tid=u)], llm, memo=memo)[1]
    for _ in range(3): assert look('idea:obvious') == [('idea:obvious', 'the owner would already know it')]
    assert len(asked) == 1, 'the same note: the verdict stands'
    look('idea:other'); assert len(asked) == 2, 'another note is asked'
    look('idea:other', None); assert len(asked) == 3, 'Run now asks'


def test_the_model_names_the_kind_of_its_own_line():
    s = MemoryStore()
    say = [{'key': 'idea:clash-thursday', 'text': 'The Ledger demo overlaps the Northwind board prep on Thursday', 'type': 'clash', 'why': 'calendar'},
           {'key': 'idea:hunch', 'text': 'Something else worth a look', 'type': 'nonsense', 'why': 'x'}]
    out = assistant.parse(s, json.dumps({'say': say}), [])
    assert [(o['key'], o['kind']) for o in out] == [('idea:clash-thursday', 'clash'), ('idea:hunch', 'idea')]
    assert '"type": "<idea:* only - second_ask' in assistant.CONTRACT and 'One failure row a report already shows is not a line' in assistant.CONTRACT
