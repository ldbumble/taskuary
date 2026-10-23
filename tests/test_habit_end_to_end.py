"""PRESS -> HABIT -> LIT BUTTON, END TO END (phases A, B and C together, 2026-10-23). Phase B keeps every press, phase C turns 3+
real choices from 2+ people into an in-use line under "## What you do next", phase A's habit tier lights that line's button - on the
desk and on the phone, the same decision - and the line never reaches triage (ruling 11: "why would we want button presses to do
with triage"). Each piece had its own test with the others stubbed; this one runs the real road. Invented Northwind people only."""
from unittest import mock
import pytest
from taskuary import advisor, concierge, funnel, ingest, learn, learned_cut, learnedlines, remote_assistant, terminal
from taskuary.store import MemoryStore
from taskuary.testing import Factory

PEOPLE = [('Vendor Desk', 'desk@vendor.example'), ('Accounts Payable', 'ap@vendor.example'), ('Vendor Desk', 'desk@vendor.example')]


@pytest.fixture
def s(monkeypatch):
    s = MemoryStore(); s.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    monkeypatch.setattr(advisor, 'notice', lambda *a, **k: None)
    funnel.invalidate(); yield s; funnel.invalidate()


def _ask(s, title, who):
    f = Factory(s)
    t = f.task(title=title, kind='task')
    f.message(task_id=t, subject=title, body='can you?', from_name=who[0], from_email=who[1], conversation_id=f'email:{title}')
    return f'task:{t}'


def _press(s, key, verb):
    """One desk press as the page sends it: what was pressed, what was lit, and what else the row had live."""
    it = advisor._item(s, *advisor.target_of(s, key), key=key)
    live = [v['verb'] for v in advisor.offered(s, it)] + ['next']
    d = advisor.decide(s, key, preread=False)
    return advisor.press(s, key, None, verb, surface='desk', lit=d.get('verb') or '', live=live)


def test_three_choices_from_two_people_become_a_habit_that_lights_its_button_and_never_reaches_triage(s):
    keys = [_ask(s, f'Statement question {i}', who) for i, who in enumerate(PEOPLE)]
    nxt = _ask(s, 'Statement question 4', PEOPLE[1])
    before = advisor.decide(s, nxt, preread=False)
    assert before['verb'] != 'close' and before['by'] != 'habit', before
    assert 'close' in [v['verb'] for v in advisor.offered(s, advisor._item(s, *advisor.target_of(s, nxt), key=nxt))]
    for k in keys[:2]: assert _press(s, k, 'done')
    assert learned_cut.lines(s.doc('learned'), learned_cut.NEXT) == [], 'two episodes are watching, not in use'
    assert _press(s, keys[2], 'done')
    # PHASE C: an in-use line under the Advisor's own section, recorded as in use
    ls = learned_cut.lines(s.doc('learned'), learned_cut.NEXT)
    assert len(ls) == 1 and 'presses Mark done (3 of 3)' in ls[0][0], ls
    key = ls[0][1]
    assert key.startswith('move ') and key.endswith('vendor.example'), key
    assert learnedlines.row(s, key)['Status'] == 'in_use' and learnedlines.row(s, key)['Reader'] == 'advisor'
    # PHASE A: the habit tier lights that button on the next such item, with nothing said - and never presses it (ruling 9)
    d = advisor.decide(s, nxt, preread=False)
    assert (d['verb'], d['by'], d['line']) == ('close', 'habit', ''), d
    assert s._one('SELECT COUNT(*) n FROM advice_press')['n'] == 3, 'a habit lights a button; it presses nothing'
    # ...the same on the phone: its card leads with the button the desk lit
    it = advisor._item(s, *advisor.target_of(s, nxt), key=nxt)
    chips = concierge.chips_for(s, it)
    said = remote_assistant.decision(s, it)
    assert said['verb'] == 'close' and said['by'] == 'habit'
    assert 'close' in {c['verb'] for c in chips}, chips
    assert remote_assistant.primary({'chips': chips, 'item': it}, said)['verb'] == 'close'
    assert remote_assistant.advice_line({'item': it}, said) == ''
    # RULING 11: triage reads "How you sort mail" only - the habit is nowhere in its prompt
    seen = {}
    ingest.ingest_message(s, {'external_id': 'e2e-1', 'channel': 'email', 'from_email': 'desk@vendor.example', 'subject': 'Another statement',
                              'body': 'Statement attached.'}, llm=lambda sys_, usr, **k: (seen.update(p=sys_ + usr), '{"intent":"fyi","why":"x"}')[1])
    assert seen['p'] and 'presses Mark done' not in seen['p'] and learn.NEXT not in seen['p'] and key not in seen['p']
    assert 'presses' not in learned_cut.for_reader(s, 'triage')


def test_a_habit_the_owner_removed_lights_nothing(s):
    """The owner deletes the line (a tombstone - phase D's Forget hangs on it): the Advisor goes back to its rule at once."""
    keys = [_ask(s, f'Remittance {i}', who) for i, who in enumerate(PEOPLE)]
    nxt = _ask(s, 'Remittance 4', PEOPLE[0])
    for k in keys: _press(s, k, 'done')
    assert advisor.decide(s, nxt, preread=False)['by'] == 'habit'
    doc = s.doc('learned')
    raw = learned_cut.lines(doc, learned_cut.NEXT)[0][0]
    s.save_doc('learned', doc.replace(raw + '\n', ''), 'owner')
    assert advisor.decide(s, nxt, preread=False)['by'] != 'habit'


def test_a_habit_line_left_in_the_doc_but_marked_wrong_lights_nothing(s):
    keys = [_ask(s, f'Credit memo {i}', who) for i, who in enumerate(PEOPLE)]
    nxt = _ask(s, 'Credit memo 4', PEOPLE[1])
    for k in keys: _press(s, k, 'done')
    key = learned_cut.lines(s.doc('learned'), learned_cut.NEXT)[0][1]
    s._exec("UPDATE learned_line SET Status='wrong' WHERE Key=?", (key,))
    assert advisor.decide(s, nxt, preread=False)['by'] != 'habit'
