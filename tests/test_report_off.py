"""SWITCH IT OFF (the owner, 2026-10-27: "Yes" - the Advisor may suggest switching a report off). A report run whose findings are all about
something a What you care about line says the owner does not care about may have Pause this report lit by the Advisor; the press is the
owner's, and runs the report's own pause - the report stays under Reports, switched off. Invented Northwind names only."""
import json
from unittest import mock
from taskuary import advisor, buttons, concierge, learned_cut as lc, rulebook, toolcatalog
from taskuary.store import MemoryStore

CARE = 'You no longer care about the legacy vendor export job - it was retired'


def _report(s, active=True):
    sid = s.save_source({'Channel': 'report', 'Address': 'Vendor export check', 'Active': int(active),
                         'ConfigJson': json.dumps({'title': 'Vendor export check'})}, 'owner')
    return sid, {'key': f'report:{sid}', 'kind': 'report', 'title': 'Vendor export check', 'source_id': sid, 'mid': None}


def _care(s, line=CARE):
    from taskuary.learn import _under
    s.save_doc('learned', _under(s.get_doc('learned') or '', lc.SECTIONS['care'], f'- {line}'), 'owner')


def test_it_is_one_button_with_one_name():
    assert buttons.label('report_off') == 'Pause this report' and buttons.hint('report_off')
    assert 'report_off' in concierge.VERBS and 'report_off' in toolcatalog.DECISIONS
    assert concierge.PROPOSALS['report_off'][0] == 'report.pause'


def test_the_row_carries_it_only_over_a_report_still_switched_on():
    s = MemoryStore(); _, it = _report(s)
    assert 'report_off' in [c['verb'] for c in concierge.chips_for(s, it)]
    assert 'report_off' in [b['verb'] for b in concierge.row_buttons(s, it)]
    _, off = _report(s, active=False)
    assert 'report_off' not in [c['verb'] for c in concierge.chips_for(s, off)]
    assert concierge.cannot(off, 'report_off', s)
    assert concierge.cannot({'key': 'msg:1', 'kind': 'fyi', 'mid': 1}, 'report_off', s), 'never over anything but a report'


def test_a_good_run_fills_nothing_and_carries_its_pause():
    s = MemoryStore(); _, it = _report(s); _care(s)
    verbs = advisor.offered(s, it)
    assert 'report_off' in {v['verb'] for v in verbs}
    assert rulebook.facts(s, it, verbs) == {'state': 'report_ok', 'line': ''} and rulebook.recommended(s, it, verbs) is None
    # ...and a run that failed is named so
    assert rulebook.facts(s, {**it, 'bad': True}, verbs)['state'] == 'report_failed'


def test_the_press_switches_the_report_off_by_its_own_road():
    from fastapi.testclient import TestClient
    from taskuary import server
    s = MemoryStore(); sid, it = _report(s)
    prop = concierge.propose_for(s, 0, {'verb': 'report_off'}, it, '')
    assert (prop['kind'], int(prop['target'])) == ('report.pause', sid)
    with mock.patch.object(server, 'store', s):
        r = TestClient(server.app).post(f"/api/operations/{prop['id']}/execute", json={'version': prop.get('version')})
    assert r.status_code == 200, r.text
    assert not (s.get_source(sid) or {}).get('Active'), 'switched off - and still there, under Reports'


def _brain(answer):
    calls = []
    def llm(system, user, max_tokens=400, images=None, want=None, **kw): calls.append((system, user)); return json.dumps(answer)
    llm.takes_want, llm.calls = False, calls
    return llm
