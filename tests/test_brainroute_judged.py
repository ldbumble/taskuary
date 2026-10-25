"""Difficulty and `sure` (the router, 2026-10-25): two judgements triage writes on the call it already makes - how much thought the
work takes, and whether the reader could tell what it is. A verdict of their own, apart from the priority: they never move a task,
they are shown on it, the owner can correct them, and in Auto mode they pick the model tier. No word list decides either one."""
import json
from pathlib import Path

import taskuary
from taskuary import brainroute, triage
from taskuary.store import MemoryStore
from taskuary.triage import INTENT_SYSTEM, classify_intent, verdict_schema

DOC = (Path(taskuary.__file__).parent / 'templates' / 'triage.md').read_text(encoding='utf-8')
MSG = {'subject': 'Q3 numbers', 'body': 'Could you send the Q3 numbers by Friday?', 'from_email': 'erin@northwind.example',
       'from_name': 'Erin Blake', 'channel': 'email'}


def _verdict(**extra):
    return json.dumps({'intent': 'task', 'kind': 'task', 'why': 'w', 'title': 't', 'summary': 's', **extra})


def test_the_schema_names_them_and_both_prompts_explain_them():
    p = verdict_schema()['schema']['properties']
    assert p['difficulty']['enum'] == ['quick', 'standard', 'hard', None] and p['sure']['type'] == ['boolean', 'null']
    assert set(verdict_schema()['schema']['required']) >= {'difficulty', 'sure'}
    # the schema names only what the prompt explains (TQ-0665): a bullet in section 5, and the answer's line in section 7
    for text, name in ((DOC, 'triage.md'), (INTENT_SYSTEM, 'INTENT_SYSTEM')):
        assert '- **difficulty** - for every verdict' in text and '- **sure** - for every verdict' in text, name
        assert '"difficulty": "quick|standard|hard"' in triage.shipped_section('## 7.'), name
    # its own verdict: the bullet says so, and it is not the urgency or the priority
    assert 'says nothing about how soon it is due or how much it matters' in triage.DIFFICULTY


def test_the_verdict_carries_them_and_drops_what_is_not_one():
    v = classify_intent(MSG, llm=lambda s, u, **k: _verdict(difficulty='hard', sure=False))
    assert (v['difficulty'], v['sure']) == ('hard', False)
    v = classify_intent(MSG, llm=lambda s, u, **k: _verdict(difficulty='very hard', sure='no'))
    assert 'difficulty' not in v and 'sure' not in v
    assert 'difficulty' not in classify_intent(MSG, llm=lambda s, u, **k: _verdict())   # an older brain's answer: nothing judged


def test_an_owner_document_that_never_asks_gets_the_two_lines():
    seen = {}
    def llm(system, user, **kw): seen['s'] = system; return _verdict(difficulty='quick', sure=True)
    mine = 'Triage my mail. Answer JSON with "intent", "title", "summary", "checklist".'
    classify_intent(MSG, llm=llm, system=mine)
    assert triage.DIFFICULTY in seen['s'] and triage.SURE in seen['s']


def test_the_task_keeps_the_newest_reading_and_the_owner_word_stands():
    s = MemoryStore(); tid = s.create_task({'Title': 'Q3 numbers', 'Status': 'open'}, 'owner')
    s.add_route(None, tid, 'create', None, 'triage: task', [], 'triage', verdict={'intent': 'task', 'difficulty': 'quick', 'sure': True})
    assert brainroute.judged(s, tid) == {'difficulty': 'quick', 'sure': True, 'data_class': '', 'by': 'triage'}
    s.add_route(None, tid, 'attach', None, 'triage: more', [], 'triage', verdict={'intent': 'task', 'difficulty': 'hard', 'sure': False})
    assert brainroute.judged(s, tid)['difficulty'] == 'hard'
    s.judge_task(tid, {'difficulty': 'standard'}, 'owner')
    s.add_route(None, tid, 'attach', None, 'triage: again', [], 'triage', verdict={'intent': 'task', 'difficulty': 'quick'})
    assert brainroute.judged(s, tid)['difficulty'] == 'standard'                 # the owner's correction holds
    assert brainroute.choose(s, 'draft', task=tid).difficulty == 'standard'        # ...and the route carries it into the log
    assert brainroute.judged(s, 9999) == {'difficulty': '', 'sure': None, 'data_class': '', 'by': ''}


def test_difficulty_never_touches_the_priority():
    s = MemoryStore(); tid = s.create_task({'Title': 'Q3 numbers', 'Status': 'open'}, 'owner')
    before = s.get_task(tid)['Priority']
    s.add_route(None, tid, 'create', None, 'triage: task', [], 'triage', verdict={'intent': 'task', 'difficulty': 'hard', 'sure': False})
    assert s.get_task(tid)['Priority'] == before
