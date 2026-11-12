"""The audit corpus (tests/audit_scenarios.py) on every backend: each scenario's snapshots hold the goal rules (audit_scenarios.broken), and the
general agent reads the same on every backend it runs on but for what is the backend's own (audit_scenarios.parity) - the roads are one where
they should be one. AUDIT_DUMP=<folder> keeps each cell's snapshots and prompts there, for the replay sheet and for reading a failure.

OPEN names what the audit found and has not fixed yet, each with its reason: a cell must break exactly those rules - a new break fails, and a
fixed one fails too until it is taken off the list. OPEN_PARITY names the cells whose reads are not yet one road with the rest."""
import json, os

import pytest

import audit_scenarios as A

pytestmark = pytest.mark.acp            # the stand-in adapter is this suite's own (conftest.no_real_acp_adapters)
RUNS = {}                               # (scenario, backend) -> its run, for the parity check after the cells
# (scenario, backend) -> the rules it still breaks, by their mark - each a finding of the audit (2026-11-10), open:
OPEN = {}
# (scenario, backend) whose reads are not yet one road with the others', each with its reason - the coding agent's chat and turns are one road
# with the general chat's (2026-11-11); what is left is the rail's and the arrival's, not the chat's:
OPEN_PARITY = {('j', 'coding'),     # a reply owed on arrival is a 'draft' review the general road opens and a joined mail marks behind; a coding
                                    # task's reply is the agent's own draft_reply, which no join marks (ingest: behind = pending_review(kind='draft'))
               ('m', 'coding'),     # put to rest, the rail lights Continue on a coding task (rulebook MOVES 'stopped') and nothing on a chat
               ('r', 'coding'),     # held for a stranger, the rail lights Send to agent (regular_agent) on a general task and nothing on a coding one
               ('s', 'coding'),     # a coding task's close writes its session up (wrapup): a playbook it proposes is put down with the close, a card no chat has
               ('t', 'coding'),
               # a reply owed is drafted at the arrival where a quick call can (cli, acp): its card stands from then, above the turn that goes on to
               # rewrite it, until that turn ends and keeps it; an AI card has no quick call, so its turn raises the card itself
               ('s', 'api'), ('t', 'api')}     # a reply sent while its coding turn still worked is named by no turn in the coding payload (found 2026-11-11, open),
                                    # and a coding session takes the queued word at its turn's end, a chat at the waiting room's next look


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
    runs = {b: RUNS[name, b].snaps for b in A.BACKENDS if (name, b) in RUNS and (name, b) not in OPEN_PARITY}
    if len(runs) < 2: pytest.skip('fewer than two backends ran it')
    assert A.parity(runs) == []


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
