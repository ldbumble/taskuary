"""A PRESS IS KEPT, AND TEACHES NOTHING (the memory redesign, 2026-10-25), END TO END. Phase B keeps every press, on every surface; it
used to become "On asks from vendor.example, presses Mark done (3 of 3)" under "## What you do next" and light Mark done by itself on
the next ask from the domain, with a habit mark. The owner: stop learning from presses and remove the habit mark - context decides,
and a button press is not a fact about a person. This runs the real road: presses on the desk, the decision on the desk and the phone,
the triage prompt, and LEARNED.md. Invented Northwind people only."""
import pytest
from taskuary import advisor, concierge, funnel, ingest, learn, learned_cut, remote_assistant, terminal
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


def test_presses_are_kept_and_never_become_a_line_or_a_lit_button(s):
    nxt = _ask(s, 'Statement question 4', PEOPLE[1])
    before = advisor.decide(s, nxt, preread=False)
    it = advisor._item(s, *advisor.target_of(s, nxt), key=nxt)
    phone = remote_assistant.primary({'chips': concierge.chips_for(s, it), 'item': it}, remote_assistant.decision(s, it))['verb']
    doc = s.doc('learned')
    for n in range(6):
        for i, who in enumerate(PEOPLE): assert _press(s, _ask(s, f'Statement question {n}-{i}', who), 'done')
    assert s._one('SELECT COUNT(*) n FROM advice_press')['n'] == 18, 'every press is kept, as a record'
    assert s.doc('learned') == doc and 'presses' not in s.doc('learned'), 'no line from any number of presses'
    d = advisor.decide(s, nxt, preread=False)
    assert (d['verb'], d['by'], d['line']) == (before['verb'], before['by'], before['line']) and d['by'] != 'habit', d
    assert 'says' not in d and d['pill'] == d['label'], 'no "Your own habit..." line and no "n of m times" mark'
    # ...the same on the phone: its card leads with the button the desk lit
    it = advisor._item(s, *advisor.target_of(s, nxt), key=nxt)
    said = remote_assistant.decision(s, it)
    assert said['verb'] == d['verb'] and said['by'] != 'habit'
    assert remote_assistant.primary({'chips': concierge.chips_for(s, it), 'item': it}, said)['verb'] == phone


def test_a_press_never_reaches_triage(s):
    for i, who in enumerate(PEOPLE): _press(s, _ask(s, f'Remittance {i}', who), 'done')
    seen = {}
    ingest.ingest_message(s, {'external_id': 'e2e-1', 'channel': 'email', 'from_email': 'desk@vendor.example', 'subject': 'Another statement',
                              'body': 'Statement attached.'}, llm=lambda sys_, usr, **k: (seen.update(p=sys_ + usr), '{"intent":"fyi","why":"x"}')[1])
    assert seen['p'] and 'presses Mark done' not in seen['p'] and learn.OLD_NEXT not in seen['p']
    assert 'presses' not in learned_cut.for_reader(s, 'triage') and s.get_setting('learn_pending') in (None, '', '0')
