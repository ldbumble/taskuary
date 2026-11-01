"""KILLER IDEAS, QUIET UNLESS SURE (the design's S7; the owner, 2026-11-01). The rail Advisor says what KIND each of its own lines is;
a kind the owner's record says is under 80% useful is held; a line about work the owner touched today is held; a second model look holds
what the owner would already know; and a habit the Advisor is sure of is adopted, an unsure useful one asked once. Invented people only."""
import json
from datetime import datetime, timedelta
import pytest
from taskuary import assistant, habits, ideacheck, ideagrade, learn, learnedgraph as lg
from taskuary.store import MemoryStore
from taskuary.testing import Factory

def ago(**k): return (datetime.now() - timedelta(**k)).strftime('%Y-%m-%d %H:%M:%S')
TODAY = datetime.now().strftime('%Y-%m-%d')


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
    assert ideagrade.quiet_kinds(s) == {'idea'}


def _say(key, kind='pattern', **act): return {'key': key, 'kind': kind, 'text': f'line {key}', 'why': 'because', 'action': act}


def test_the_second_look_holds_a_quiet_kind_work_touched_today_and_what_the_owner_would_already_know():
    s = MemoryStore()
    for n in range(1, 11): _idea(s, n, 'idea', 'done', 'sweep')                                   # 'idea' is quiet: 0 of 10
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
    assert dict(held) == {'idea:plain': "its kind (idea) is under 80% useful lately", 'idea:touched': 'the owner acted on it in the last day (reply.sent)',
                          'idea:obvious': 'the owner would already know it'}
    assert 'NOTE 1: line idea:obvious' in seen['user'] and 'NOTE 2: line idea:killer' in seen['user']
    # ...and a check that cannot run holds nothing back
    kept, held = ideacheck.check(s, [_say('idea:x', tid=u)], lambda *a, **k: (_ for _ in ()).throw(RuntimeError('down')))
    assert [x['key'] for x in kept] == ['idea:x']


def test_the_model_names_the_kind_of_its_own_line():
    s = MemoryStore()
    say = [{'key': 'idea:clash-thursday', 'text': 'The Ledger demo overlaps the Northwind board prep on Thursday', 'type': 'clash', 'why': 'calendar'},
           {'key': 'idea:hunch', 'text': 'Something else worth a look', 'type': 'nonsense', 'why': 'x'}]
    out = assistant.parse(s, json.dumps({'say': say}), [])
    assert [(o['key'], o['kind']) for o in out] == [('idea:clash-thursday', 'clash'), ('idea:hunch', 'idea')]
    assert '"type": "<idea:* only - second_ask' in assistant.CONTRACT and 'One failure row a report already shows is not a line' in assistant.CONTRACT


def _doc(*lines):
    return f"# LEARNED\n\n## What you care about\n\n## Proposed rules — your call\n{learn.PROP_START}\n" + '\n'.join(lines) + f"\n{learn.PROP_END}\n"


def test_a_sure_habit_is_adopted_and_said_once_and_an_unsure_useful_one_is_asked_once():
    s = MemoryStore()
    sure = lg.fmt({'key': 'friendly chat', 'text': 'Friendly chat with no ask is not a task', 'ev': [f'rv{i}' for i in range(1, 9)],
                   'score': 12, 'seen': TODAY, 'status': 'proposed'})
    unsure = lg.fmt({'key': 'fyi forwards', 'text': 'Forwarded FYI mail needs no reply', 'ev': ['rv20', 'rv21'], 'score': 5, 'seen': TODAY, 'status': 'proposed'})
    weak = lg.fmt({'key': 'weak one', 'text': 'Something seen twice', 'ev': ['rv30'], 'score': 2, 'seen': TODAY, 'status': 'proposed'})
    s.save_doc('learned', _doc(sure, unsure, weak), 'reflect')
    out = habits.tick(s)
    assert out == {'adopted': ['friendly chat'], 'asked': ['fyi forwards']}
    live = {l['key']: l['status'] for l in lg.lines(s.get_doc('learned'))}
    assert live['friendly chat'] == 'live' and live['fyi forwards'] == 'proposed' and live['weak one'] == 'proposed'
    asked = s._one("SELECT * FROM idea WHERE Key='idea:habit-fyi-forwards'")
    assert asked['Kind'] == 'habit' and asked['Text'].startswith('Is this a habit of yours')
    # No: never asked again
    assistant.act(s, asked['IdeaId'], 'dismiss')
    assert habits.tick(s)['asked'] == []
    # ...and Keep it / No on the adopted one: No takes it back for good
    adopted = s._one("SELECT * FROM idea WHERE Key='idea:habit-friendly-chat'")
    assistant.act(s, adopted['IdeaId'], 'dismiss')
    assert 'friendly chat' not in {l['key'] for l in lg.lines(s.get_doc('learned')) if l['status'] == 'live'}


def test_adopt_on_an_asked_habit_moves_it_live():
    s = MemoryStore()
    unsure = lg.fmt({'key': 'fyi forwards', 'text': 'Forwarded FYI mail needs no reply', 'ev': ['rv20', 'rv21'], 'score': 6, 'seen': TODAY, 'status': 'proposed'})
    s.save_doc('learned', _doc(unsure), 'reflect')
    habits.tick(s)
    i = s._one("SELECT * FROM idea WHERE Key='idea:habit-fyi-forwards'")
    assistant.act(s, i['IdeaId'], 'accept')
    assert {l['key']: l['status'] for l in lg.lines(s.get_doc('learned'))}['fyi forwards'] == 'live'
