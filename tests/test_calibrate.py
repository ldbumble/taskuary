"""QUIET UNLESS SURE (the owner, 2026-11-01; the design's S1): a rule's button goes dark in a state where the owner's own presses chose it
under 80% of the time, on at least five decisions. Invented Northwind data only (CLAUDE.md)."""
from taskuary import advisor, calibrate
from taskuary.store import MemoryStore


def _press(s, n, state, pressed, rev='r1', key=None, at="datetime('now','localtime')"):
    s._exec(f"INSERT INTO advice_press (Key,TargetKind,TargetId,Revision,Pressed,State,CreatedAt) VALUES (?,?,?,?,?,?,{at})",
            (key or f'task:{n}', 'task', n, rev, pressed, state))


def test_the_owners_answer_per_decision_is_its_first_press_that_is_not_next():
    rows = [{'Key': 'task:1', 'Revision': 'r1', 'State': 'stopped', 'Pressed': 'next'},
            {'Key': 'task:1', 'Revision': 'r1', 'State': 'stopped', 'Pressed': 'close'},       # came back and closed: the answer
            {'Key': 'task:2', 'Revision': 'r1', 'State': 'stopped', 'Pressed': 'try_again'},   # Try again is Continue
            {'Key': 'task:3', 'Revision': 'r1', 'State': 'stopped', 'Pressed': 'back'},        # moving about is no answer
            {'Key': 'task:4', 'Revision': 'r1', 'State': None, 'Pressed': 'close'}]            # no state kept: not counted
    c = calibrate.choices(rows)
    assert dict(c['stopped']) == {'close': 1, 'continue': 1}
    assert calibrate.share(c['stopped'], 'continue') == (0.5, 2)


def test_a_button_the_owner_rarely_picks_in_its_state_is_not_trusted_and_too_little_record_trusts_the_rule():
    s = MemoryStore()
    for n in range(1, 7): _press(s, n, 'stopped', 'close' if n > 1 else 'continue')   # Continue once in six
    for n in range(10, 15): _press(s, n, 'asked', 'reply')                              # Reply five of five
    for n in range(20, 23): _press(s, n, 'waiting', 'close')                            # three: too few to say
    assert not calibrate.trusted(s, 'stopped', 'continue')
    assert calibrate.trusted(s, 'stopped', 'close')
    assert calibrate.trusted(s, 'asked', 'reply')
    assert calibrate.trusted(s, 'waiting', 'defer')
    assert calibrate.trusted(s, 'never_seen', 'continue')


def test_old_presses_are_out_of_the_record():
    s = MemoryStore()
    for n in range(1, 7): _press(s, n, 'stopped', 'close', at="datetime('now','localtime','-60 days')")
    assert calibrate.trusted(s, 'stopped', 'continue')


def test_a_workstreams_own_record_decides_once_it_has_enough():
    s = MemoryStore()
    for n in range(1, 7):
        s._exec("INSERT INTO task (TaskId, Title, Status, Workstream, CreatedAt, UpdatedAt) VALUES (?,?,?,?,datetime('now'),datetime('now'))",
                (n, f'Ledger app bug {n}', 'open', 'ledger-app'))
        _press(s, n, 'asked', 'close')                       # in the Ledger app, an ask is fixed and closed, never answered
    for n in range(10, 40): _press(s, n, 'asked', 'reply')    # ...everywhere else, Reply (30 of 36 at home)
    assert calibrate.trusted(s, 'asked', 'reply')
    assert not calibrate.trusted(s, 'asked', 'reply', 'ledger-app')
    assert calibrate.trusted(s, 'asked', 'reply', 'board-seat')   # a stream with no record of its own reads the home's


def test_the_advisor_lights_nothing_where_the_rules_button_is_not_trusted(monkeypatch):
    from tests.test_advisor_consistent import MARCUS, ask
    from taskuary import funnel, terminal
    s = MemoryStore()
    for k, v in (('calendar_enabled', '0'), ('owner_email', 'alex@northwind.example'), ('owner_name', 'Alex Doyle')): s.set_setting(k, v, 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: []); monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    monkeypatch.setattr(advisor, 'notice', lambda *a, **k: None)
    first, _ = ask(s, 'Spendly cards for the new site', MARCUS, 7, cid='email:spendly')
    second, _ = ask(s, 'RE: Spendly cards', MARCUS, 2, cid='email:spendly')
    lit = advisor.decide(s, f'task:{second}', preread=False)
    assert (lit['state'], lit['by'], bool(lit['verb'])) == ('duplicate', 'rule', True)
    for n in range(100, 106): _press(s, n, 'duplicate', 'reply')      # the owner answers "duplicates" rather than folding them
    calibrate.clear(); funnel.invalidate()
    d = advisor.decide(s, f'task:{second}', preread=False)
    assert (d['state'], d['verb'], d['line']) == ('duplicate', None, '')
