"""The audit corpus (tests/audit_scenarios.py) on every backend: each scenario's snapshots hold the goal rules (audit_scenarios.broken), and the
general agent reads the same on every backend it runs on but for what is the backend's own (audit_scenarios.parity) - the roads are one where
they should be one. AUDIT_DUMP=<folder> keeps each cell's snapshots and prompts there, for the replay sheet and for reading a failure.

OPEN names what the audit found and has not fixed yet, each with its reason: a cell must break exactly those rules - a new break fails, and a
fixed one fails too until it is taken off the list. The coding chat's parity with the general one is the largest of them (see OPEN_PARITY)."""
import json, os

import pytest

import audit_scenarios as A

pytestmark = pytest.mark.acp            # the stand-in adapter is this suite's own (conftest.no_real_acp_adapters)
RUNS = {}                               # (scenario, backend) -> its run, for the parity check after the cells
# (scenario, backend) -> the rules it still breaks, by their mark - each a finding of the audit (2026-11-10), open:
OPEN = {}
# the coding agent and its chat against the general one, not yet one road: its chip after a turn ('stopped' where a chat reads 'approve' or
# 'agent done'), what each turn is told (the coding prompt carries none of general.turn_facts), where its cards stand (the coding payload
# names no turn for them: the page places them by time), and a mail joining a parked coding session
OPEN_PARITY = {'coding'}


@pytest.mark.parametrize('backend', A.BACKENDS)
@pytest.mark.parametrize('name', sorted(A.SCENARIOS))
def test_scenario(name, backend, tmp_path, monkeypatch):
    if not A.runs_on(name, backend): pytest.skip(f'{name} is not a {backend} shape')
    try:
        with A.world(backend, tmp_path, monkeypatch) as r: A.SCENARIOS[name](r)
    finally:
        if 'r' in locals(): RUNS[name, backend] = r
        if os.environ.get('AUDIT_DUMP') and 'r' in locals():
            with open(os.path.join(os.environ['AUDIT_DUMP'], f'{name}-{backend}.json'), 'w', encoding='utf-8') as f:
                json.dump({'snaps': r.snaps, 'prompts': r.prompts, 'extra': r.extra, 'sent': r.sent, 'broken': A.broken(r),
                           'typed': r.typed, 'pressed': r.pressed, 'raised': r.raised, 'systems': r.systems}, f, indent=1, default=str)
    assert sorted(x.split(' ')[0] for x in A.broken(r)) == sorted(OPEN.get((name, backend), [])), A.broken(r)


@pytest.mark.parametrize('name', sorted(A.SCENARIOS))
def test_parity(name):
    runs = {b: RUNS[name, b].snaps for b in A.BACKENDS if (name, b) in RUNS and b not in OPEN_PARITY}
    if len(runs) < 2: pytest.skip('fewer than two backends ran it')
    assert A.parity(runs) == []
