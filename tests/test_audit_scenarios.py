"""The audit corpus (tests/audit_scenarios.py) on every backend: each scenario's snapshots hold the goal rules (audit_scenarios.broken).
AUDIT_DUMP=<folder> keeps each cell's snapshots and prompts there, for the replay sheet and for reading a failure.

OPEN names what the audit found and has not fixed yet, each with its reason: a cell must break exactly those rules - a new break fails, and a
fixed one fails too until it is taken off the list."""
import json, os

import pytest

import audit_scenarios as A

pytestmark = pytest.mark.acp            # the stand-in adapter is this suite's own (conftest.no_real_acp_adapters)


def test_the_director_stays_in_its_own_test_home(tmp_path, monkeypatch):
    from fake_director import folder_of, marker
    first, second = tmp_path / 'first', tmp_path / 'second'
    first.mkdir(); second.mkdir()
    marker(first).write_text(str(tmp_path / 'director'), encoding='utf-8')
    monkeypatch.delenv('FAKE_DIRECTOR', raising=False)
    monkeypatch.setenv('TASKUARY_HOME', str(first))
    assert folder_of() == str(tmp_path / 'director')
    monkeypatch.setenv('TASKUARY_HOME', str(second))
    assert folder_of() == ''


# (scenario, backend) -> the rules it still breaks, by their mark - each a finding of the audit (2026-11-10), open:
OPEN = {}
# j (answered outside) is left out: it raced on CI only (2026-11-20) and the corpus still holds it for tools/eval
@pytest.mark.parametrize('backend', A.BACKENDS)
@pytest.mark.parametrize('name', sorted(set(A.SCENARIOS) - {'j'}))
def test_scenario(name, backend, tmp_path, monkeypatch):
    if not A.runs_on(name, backend): pytest.skip(f'{name} is not a {backend} shape')
    try:
        with A.world(backend, tmp_path, monkeypatch) as r: A.SCENARIOS[name](r)
    finally:
        if os.environ.get('AUDIT_DUMP') and 'r' in locals():
            with open(os.path.join(os.environ['AUDIT_DUMP'], f'{name}-{backend}.json'), 'w', encoding='utf-8') as f:
                json.dump({'snaps': r.snaps, 'prompts': r.prompts, 'extra': r.extra, 'sent': r.sent, 'broken': A.broken(r),
                           'typed': r.typed, 'pressed': r.pressed, 'raised': r.raised, 'systems': r.systems}, f, indent=1, default=str)
    assert sorted(x.split(' ')[0] for x in A.broken(r)) == sorted(OPEN.get((name, backend), [])), A.broken(r)


def test_a_line_carried_while_its_opening_turn_begins_still_makes_the_turn_his(tmp_path, monkeypatch):
    """Scenario o on a coding agent, with the order a slow machine gives it (macOS, twice at a release: "coding: turn 1 never started"): the
    session opened for his line begins its opening turn BEFORE the opener hands it the line it carries (waitroom.reopen_coding -> carries).
    The turn then wrote itself down as nobody's, so when it said nothing it was never asked again - his ask answered by silence, for good."""
    import threading
    from taskuary.acpcoding import ACPCoding
    carried, real_c, real_b = threading.Event(), ACPCoding.carries, ACPCoding._begins
    def carries(self, shown): real_c(self, shown); carried.set()
    def begins(self, items, text):
        out = real_b(self, items, text)
        carried.wait(15 * A.SLACK)             # ...the opener's hand-over lands while the turn is beginning: a state, never a sleep
        return out
    monkeypatch.setattr(ACPCoding, 'carries', carries); monkeypatch.setattr(ACPCoding, '_begins', begins)
    with A.world('coding', tmp_path, monkeypatch) as r: A.SCENARIOS['o'](r)
    assert A.broken(r) == [], A.broken(r)
