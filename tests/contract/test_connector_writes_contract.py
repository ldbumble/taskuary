"""EVERY WRITE TO A CONNECTOR WAITS FOR HIS PRESS, AND HIS PRESS DOES IT - LOCKED (the owner, 2026-11-25: "why would file uploads, QuickBooks
bills or Intacct records have their own rules? If you want to run a report that pulls data that's fine, but to write to the systems or any
connector should require approval mechanically, correct? ... And the approval by the user sends it without further triggering the agent
unless it fails of course or there are next steps"; and on routines: "for a routine that writes to a system we can have a saved 'always
approved' option for this specific call that will be allowed, correct?").

Through the real code: a stand-in agent calls run_system over the route every CLI uses (/api/mcp), the owner presses through his page's
route, a routine walks its steps (flow.execute). Each connector's far side is stood in at its executor, so nothing leaves the machine. No
browser, no model. The people and the company are invented.

THIS FILE IS THE OWNER'S: no agent edits it, or tests/contract/LOCK, without his written OK (tests/test_contract_lock.py holds its hash).
A test here that fails is a broken product, never a test to adjust.
"""
import json, time
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import config, flow, general, guard, reports, server, terminal as term
from taskuary.store import SQLiteStore

c = TestClient(server.app)
SRV = config.load()['server']
OWNER = {'X-Taskuary-Token': 'pytest-owner-token'}


class Books:
    "QuickBooks, stood in at its executors: every bill posted is kept; `fail` refuses the post."
    def __init__(self): self.posted, self.fail = [], ''
    def bill(self, cfg):
        if self.fail: raise RuntimeError(self.fail)
        self.posted.append({k: cfg.get(k) for k in ('vendor', 'amount')}); return 'bill created', 'Id 41'
    def vendors(self, cfg): return '2 vendors', 'Payworth\nTrainly'


class Share:
    "The network share, stood in at smb_write: every file put is kept by its path."
    def __init__(self): self.put = []
    def write(self, cfg): self.put.append(cfg.get('path')); return f"wrote {cfg.get('path')}", ''


class World:
    """One owner's Taskuary on a database file of its own: QuickBooks connected at FULL Authority as an agent tool, one task its agent works,
    and that agent's live session AT WORK (not waiting on him) - the shape where a press used to tell it as its next turn."""
    def __init__(self, path):
        self.s = SQLiteStore(str(path))
        self._on = [mock.patch.object(server, 'store', self.s)]
        for m in self._on: m.start()
        general._WOKEN.clear()
        self.tid = self.s.create_task({'Title': 'Post the Payworth bill', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        qb = self.s.get_connector_by_type('quickbooks')
        self.s.save_connector({'ConnectorId': qb['ConnectorId'], 'Active': 1, 'Roles': 'tool', 'Scope': 'admin', 'Secret': 'stand-in'}, 'owner')
        smb = self.s.get_connector_by_type('smb_file')
        self.s.save_connector({'ConnectorId': smb['ConnectorId'], 'Active': 1, 'Scope': 'admin'}, 'owner')
        self.qb, self.books, self.share, self.woken = qb['ConnectorId'], Books(), Share(), []
        self.live = SimpleNamespace(sid='run1', task_id=self.tid, alive=True, waiting=lambda: False, status_tail=lambda n=8: [],
                                    send_prompt=lambda text, **k: self.woken.append(text))
        self._on += [mock.patch.dict(reports.REGISTRY, {'quickbooks_bill': self.books.bill, 'quickbooks_vendors': self.books.vendors,
                                                        'smb_write': self.share.write}),
                     mock.patch.dict(term.SESSIONS, {'run1': self.live}, clear=True),
                     mock.patch.object(general, 'to_agent', lambda st, t, said='', actor='owner', heard=None, **k:
                                       self.woken.append(said or k.get('frm') or 'woke') or (heard and heard('woke')) or 'woke')]
        for m in self._on[1:]: m.start()

    def close(self):
        for m in reversed(self._on): m.stop()
        general._WOKEN.clear()

    def agent(self, name, **args):
        "One tool call of the task's agent over /api/mcp: (what it was answered, was it an error)."
        hdr = {'X-Taskuary-Token': SRV['agent_token'], guard.TASK_HDR: guard.task_proof(SRV, self.tid)}
        r = c.post(f'/api/mcp?task={self.tid}', headers=hdr, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': args}})
        assert r.status_code == 200, r.text
        res = r.json()['result']; return res['content'][0]['text'], res['isError']

    def cards(self, tid=None):
        return self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending' ORDER BY ReviewId", (tid or self.tid,))

    def press(self, rid, **more):
        "His press on a card, as his page sends it (the card as drawn rides along as `shown`): the route's answer."
        p = json.loads(self.s.get_review(rid)['DraftText'])
        out = c.post(f'/api/reviews/{rid}/decide', headers=OWNER, json={'verb': 'approve', 'shown': p, **more}).json()
        time.sleep(.3)                                                    # ...any wake on its own thread has landed
        return out

    def routine(self, steps):
        "A routine he saved: (its source row, the task one run of it works on)."
        cfg = {'type': 'agent', 'access': 'write', 'title': 'File the AP export', 'agent': 'assistant', 'flow': steps}
        sid = self.s.save_source({'Channel': 'report', 'Address': cfg['title'], 'Owner': 'owner', 'Active': 1, 'ConfigJson': json.dumps(cfg)}, 'owner')
        return self.s.get_source(sid)

    def run(self, src):
        "One run of the routine on its own task: (the run, its task)."
        tid = self.s.create_task({'Title': 'run', 'Kind': 'general', 'Status': 'open', 'Source': 'workflow', 'SourceRef': f"workflow:{src['SourceId']}"}, 'owner')
        return flow.execute(self.s, src, tid, llm=lambda *a, **k: ''), tid


@pytest.fixture
def w(tmp_path):
    world = World(tmp_path / 'taskuary.db')
    yield world
    world.close()


BILL = {'type': 'quickbooks_bill', 'vendor': 'Payworth', 'amount': 1200, 'account': 'Payroll services', 'date': '2026-11-25', 'memo': 'November'}


# ── 1. A WRITE IS A CARD, A READ RUNS ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_connector_write_an_agent_raises_is_a_card_and_nothing_runs_before_his_press(w):
    """Mechanically, at any Authority - the card here is FULL: the bill is a card on the agent's own task and QuickBooks is not touched until
    he presses; his press posts it, once."""
    said, err = w.agent('run_system', connector_id=w.qb, **BILL)
    assert not err and w.books.posted == [], said
    [rv] = w.cards()
    assert json.loads(rv['DraftText'])['type'] == 'quickbooks_bill'
    out = w.press(rv['ReviewId'])
    assert out['ok'], out
    assert w.books.posted == [{'vendor': 'Payworth', 'amount': 1200}]


def test_a_connector_read_runs_at_once_with_no_card(w):
    "A read pulls data: it runs on the agent's call and its rows come back - nothing is put to him."
    said, err = w.agent('run_system', connector_id=w.qb, type='quickbooks_vendors')
    assert not err and 'Payworth' in said, said
    assert w.cards() == []


# ── 2. HIS PRESS DOES IT; THE AGENT IS WOKEN ONLY BY A NEXT STEP OR A FAILURE ─────────────────────────────────────────────────────────────

def test_a_press_with_no_then_that_succeeds_wakes_nobody_even_while_its_agent_works(w):
    "The approval sends it without further triggering the agent: no `then`, it went - nobody is woken, at work or at rest."
    w.agent('run_system', connector_id=w.qb, **BILL)
    [rv] = w.cards()
    assert w.press(rv['ReviewId'])['ok'] and w.books.posted
    assert w.woken == [], 'a press with no then that went wakes nobody'


def test_a_press_whose_execution_fails_wakes_its_agent_once_with_the_reason(w):
    "Unless it fails: the failure stays on its card, with why, and its agent is woken once to set up what goes next."
    w.agent('run_system', connector_id=w.qb, **BILL)
    [rv] = w.cards()
    w.books.fail = 'the vendor Payworth is inactive in QuickBooks'
    out = w.press(rv['ReviewId'])
    assert not out['ok'] and 'inactive' in out['send_error'], out
    assert 'inactive' in (w.s.get_review(rv['ReviewId'])['ActError'] or '')
    assert len(w.woken) == 1, w.woken


# ── 3. A ROUTINE'S WRITE: A CARD, UNLESS HE ALWAYS APPROVED EXACTLY THAT CALL ─────────────────────────────────────────────────────────────

def test_a_routines_write_with_his_standing_approval_for_exactly_that_call_runs_and_another_target_is_a_card(w):
    """His saved routine writes the export to the share. Its first run waits on a card; he presses "Always approve this step", and it goes.
    The next run puts that same file with no card - and a step of the same routine writing somewhere else still waits for his press."""
    put = {'id': 's1', 'kind': 'source', 'label': 'File the export', 'type': 'smb_write', 'path': 'exports/ap.csv', 'text': 'x'}
    src = w.routine([put])
    out, tid = w.run(src)
    assert out['waiting'] and w.share.put == [], 'a routine write waits for his press until he says always'
    [rv] = w.cards(tid)
    got = w.press(rv['ReviewId'], always=True)
    assert got['ok'] and got.get('always') and w.share.put == ['exports/ap.csv'], got
    out, tid = w.run(src)
    assert not out['waiting'] and w.cards(tid) == [] and w.share.put == ['exports/ap.csv'] * 2, 'that exact call runs unpressed'
    w.s.save_source({'SourceId': src['SourceId'], 'ConfigJson': json.dumps({**json.loads(src['ConfigJson']),
                    'flow': [put, {**put, 'id': 's2', 'path': 'payroll/ap.csv'}]})}, 'owner')
    out, tid = w.run(w.s.get_source(src['SourceId']))
    assert out['waiting'] and w.share.put == ['exports/ap.csv'] * 3, 'the approved step ran; the other target waits'
    [rv] = w.cards(tid)
    assert json.loads(rv['DraftText'])['path'] == 'payroll/ap.csv'
