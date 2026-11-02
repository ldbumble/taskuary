"""WHAT THE OWNER DID IN THIS STATE (the owner, 2026-11-01: "quiet unless sure"; 2026-11-02: "never ever use hard coded rules, let the ai
see everything"): the owner's own presses per state are EVIDENCE the Advisor's model reads in its prompt - never a switch that darkens a
button. Invented Northwind data only (CLAUDE.md)."""
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


def test_the_record_is_said_as_evidence_and_switches_nothing():
    s = MemoryStore()
    for n in range(1, 7): _press(s, n, 'agent_asking', 'close' if n > 1 else 'stop_agent')
    ev = calibrate.evidence(s, 'agent_asking', label=lambda v: {'close': 'Mark done'}.get(v, v))
    assert ev == 'in this state (agent_asking) over the last 30 days, the owner chose: Mark done 5 of 6, stop_agent 1 of 6'
    assert calibrate.evidence(s, 'never_seen') == '' and calibrate.evidence(s, '') == ''
    assert not hasattr(calibrate, 'trusted'), 'no on/off switch on a button any more'


def test_old_presses_are_out_of_the_record():
    s = MemoryStore()
    for n in range(1, 7): _press(s, n, 'stopped', 'close', at="datetime('now','localtime','-60 days')")
    assert calibrate.evidence(s, 'stopped') == ''


def test_a_workstreams_own_record_is_the_evidence_once_it_has_enough():
    s = MemoryStore()
    for n in range(1, 7):
        s._exec("INSERT INTO task (TaskId, Title, Status, Workstream, CreatedAt, UpdatedAt) VALUES (?,?,?,?,datetime('now'),datetime('now'))",
                (n, f'Ledger app bug {n}', 'open', 'ledger-app'))
        _press(s, n, 'asked', 'close')                       # in the Ledger app, an ask is fixed and closed, never answered
    for n in range(10, 40): _press(s, n, 'asked', 'reply')    # ...everywhere else, Reply (30 of 36 at home)
    assert calibrate.evidence(s, 'asked', 'ledger-app').endswith('in this workstream, the owner chose: close 6 of 6')
    assert calibrate.evidence(s, 'asked').endswith('the owner chose: reply 30 of 36, close 6 of 36')
    assert 'in this workstream' not in calibrate.evidence(s, 'asked', 'board-seat'), "a stream with no record of its own reads the home's"


def test_the_advisors_prompt_carries_the_owners_record_and_its_light_stands(monkeypatch):
    from tests.test_advisor_consistent import MARCUS, ask
    from taskuary import funnel, terminal
    s = MemoryStore()
    for k, v in (('calendar_enabled', '0'), ('owner_email', 'alex@northwind.example'), ('owner_name', 'Alex Doyle')): s.set_setting(k, v, 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: []); monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    first, _ = ask(s, 'Spendly cards for the new site', MARCUS, 7, cid='email:spendly')
    second, _ = ask(s, 'RE: Spendly cards', MARCUS, 2, cid='email:spendly')
    for n in range(100, 106): _press(s, n, 'duplicate', 'reply')      # the owner answers "duplicates" rather than folding them
    calibrate.clear(); funnel.invalidate()
    seen = []
    def llm(system, user, **kw): seen.append(user); return '{"verb": "reply", "line": "", "evidence": []}'
    advisor.notice(s, advisor.SHOWN, 'task', second, tier=2, wait=True, llm=llm)
    assert 'THE STATE' in seen[0] and 'duplicate' in seen[0]
    assert 'WHAT THE OWNER CHOSE BEFORE IN THIS STATE' in seen[0] and 'Reply 6 of 6' in seen[0]
    monkeypatch.setattr(advisor, 'notice', lambda *a, **k: None)
    d = advisor.decide(s, f'task:{second}', preread=False)
    assert (d['state'], d['verb'], d['by']) == ('duplicate', 'reply', 'model'), 'the model weighed the record; its light is lit'
