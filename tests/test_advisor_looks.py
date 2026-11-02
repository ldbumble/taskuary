"""THE ADVISOR LOOKS BEFORE IT DECIDES (the owner, 2026-11-02: "let the ai see everything and all tools in progressive fashion"): the index
of the pop-up Assistant's read-only look-ups rides its instructions, it may run up to LOOKS of them through the Assistant's own round
(concierge.look_rounds) - and it only ever lights; nothing it asks for changes anything. Invented Northwind people only."""
import json
from unittest import mock
from taskuary import advisor, concierge
from taskuary.store import MemoryStore
from taskuary.testing import Factory


def _task(s):
    f = Factory(s)
    t = f.task(title='Vendor W-9 for the new supplier', kind='task')
    f.message(task_id=t, subject='W-9?', body='Can you send the W-9 by Friday?', from_name='Gail Moreno', from_email='gail@northwind.example')
    return t


def brain(*answers):
    """A model that answers each call with the next of `answers` (the last one again once they run out), and keeps what it was asked."""
    calls = []
    def llm(system, user, **kw):
        calls.append((system, user)); return json.dumps(answers[min(len(calls), len(answers)) - 1])
    llm.calls = calls
    return llm


LOOK = {'verb': None, 'line': '', 'evidence': [], 'look': {'kind': 'task.read', 'params': {'ref': 'TQ-0001'}}}


def test_a_look_up_runs_and_what_it_says_reaches_the_model_before_it_lights():
    s = MemoryStore(); t = _task(s)
    llm = brain(LOOK, {'verb': 'reply', 'line': 'Gail wants it by Friday.', 'evidence': []})
    rid = advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True, llm=llm)
    assert len(llm.calls) == 2
    assert 'YOU LOOKED UP task.read' in llm.calls[1][1] and 'Vendor W-9 for the new supplier' in llm.calls[1][1].split('YOU LOOKED UP')[1]
    r = s._one('SELECT Verb, Line FROM advice WHERE Id=?', (rid,))
    assert (r['Verb'], r['Line']) == ('reply', 'Gail wants it by Friday.')


def test_the_look_ups_are_bounded_and_the_last_one_says_so():
    s = MemoryStore(); t = _task(s)
    llm = brain(LOOK)                                              # it would look for ever
    rid = advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True, llm=llm)
    assert len(llm.calls) == 1 + advisor.LOOKS
    assert 'That was your last look-up' in llm.calls[-1][1]
    assert s._one('SELECT Dropped FROM advice WHERE Id=?', (rid,))['Dropped'] == 'nothing to say'


def test_only_a_read_is_run_and_nothing_is_pressed():
    s = MemoryStore(); t = _task(s)
    for look in ({'kind': 'review.approve', 'params': {}}, {'kind': 'app.repair', 'params': {'name': 'outlook', 'how': 'sync'}},
                 {'kind': 'task.read', 'params': {}}):                # an action, a repair, and a read missing what it needs
        s._exec('DELETE FROM advice')
        llm = brain({**LOOK, 'look': look})
        with mock.patch.object(concierge, 'read_op', side_effect=AssertionError('nothing may run')):
            advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True, llm=llm)
        assert len(llm.calls) == 1, look
    assert not s._one("SELECT 1 x FROM operation WHERE Status<>'proposed'"), 'the Advisor lights; it never presses'


def test_a_verb_with_a_look_is_an_answer_and_runs_no_look_up():
    s = MemoryStore(); t = _task(s)
    llm = brain({**LOOK, 'verb': 'reply'})
    advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True, llm=llm)
    assert len(llm.calls) == 1


def test_the_index_rides_the_instructions_and_details_come_on_demand():
    s = MemoryStore()
    sysp = advisor._system(s)
    assert 'LOOK-UPS (' in sysp and 'task.read(ref, id)' in sysp and 'tools.describe(kind)' in sysp
    assert 'Answer it' not in advisor.SYSTEM and 'look' in advisor.WANT['properties']
    assert set(advisor.READS) <= set(__import__('taskuary.toolcatalog', fromlist=['READS']).READS), 'only the Assistant\'s own reads'


def test_the_item_is_read_on_the_standard_model_unless_the_home_says_light():
    s = MemoryStore(); t = _task(s)
    got = []
    def build(store, **kw): got.append(kw.get('gear')); return brain({'verb': None, 'line': '', 'evidence': []})
    with mock.patch.object(advisor, 'build_llm', build):
        advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True)
        s.set_setting(advisor.MODEL_KEY, 'light', 'owner'); s._exec('DELETE FROM advice')
        advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True)
    assert got == ['main', 'light']


def test_the_prompt_carries_every_verb_the_row_offers_and_next():
    s = MemoryStore(); t = _task(s)
    llm = brain({'verb': None, 'line': '', 'evidence': []})
    advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True, llm=llm)
    offered = [v['verb'] for v in advisor.offered(s, advisor._item(s, 'task', t))]
    said = next(l for l in llm.calls[0][1].splitlines() if l.startswith('VERBS OFFERED: '))
    assert all(f'{v} (' in said for v in offered + ['next']), said
