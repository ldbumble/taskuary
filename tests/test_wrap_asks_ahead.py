"""A wrap asks its three questions at once and applies the answers in today's order (2026-10-20).

The report, the handbook and the playbook question were asked one after another - 18 s of a Mark done with a 6-second brain.
The handbook's and the playbook's are now asked AHEAD, beside the report's, exactly as they will be asked; each function still
runs at its own place in the ending and takes the answer to the question it asks there. With a deterministic brain the
ending writes exactly what the serial one wrote - the same comments, entries, proposals, reviews, audit and status - the
brain is asked the same questions, and no more than three at once."""
import json, re, threading, time
from unittest import mock

import pytest

from taskuary import handbook, playbooks, wrapup
from taskuary.store import MemoryStore

BILL = """# Post a card transaction as an AP bill
when:      a transaction or statement line from the card feed
uses:      quickbooks (write: bills, vendors)
steps:     match the merchant to a vendor -> pick the expense account -> create the bill
alone:     bills under $500 to a vendor seen before
ask first: a new vendor
done when: the bill exists in QuickBooks
"""
SESSION = 'matched the hardware store to vendor 87, expense account 6120, created bill 1043 for 84.10. ' * 8
LAT = 0.4


class Brain:
    """Deterministic, slow, and counting how many questions it holds at once."""
    def __init__(self):
        self.asked, self.now, self.most, self.lock = [], 0, 0, threading.Lock()

    def __call__(self, system, user, **kw):
        with self.lock: self.asked.append((system, user)); self.now += 1; self.most = max(self.most, self.now)
        try:
            time.sleep(LAT); s = str(system)
            if 'determination' in s:
                return json.dumps({'determination': 'Matched the charge.', 'actions': 'Created bill 1043', 'summary': 'Posted the bill.', 'outcome': 'did_work'})
            if 'playbook' in s.lower() and 'entries' not in s:
                return json.dumps({'playbook': {'slug': 'card-bill', 'text': BILL, 'why': 'card charges recur every week'}})
            return json.dumps({'entries': [{'earned': True, 'why_earned': 'took three tries to find the vendor mapping rule',
                                            'title': 'Card charges map to vendor 87', 'body': 'Use expense account 6120.',
                                            'topic': 'finance', 'kind': 'howto'}]})
        finally:
            with self.lock: self.now -= 1


def world():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Post the hardware store charge', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
    s.add_message({'TaskId': tid, 'ExternalId': f'm{tid}', 'Channel': 'email', 'Subject': 'Charge', 'FromEmail': 'alerts@card.example',
                   'BodyText': 'a new transaction posted', 'Status': 'routed'})
    return s, tid


def ended(s, tid):
    """Every row of every table the ending can write, without the clock (columns named *At / *Time) or the session id."""
    out = {}
    for (name,) in s.cx.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        cur = s.cx.execute(f'SELECT * FROM "{name}"')
        cols = [d[0] for d in cur.description]
        keep = [i for i, c in enumerate(cols) if not (c.endswith('At') or c.endswith('Time') or c in ('Detail', 'StartedAt'))]
        # ...nor the clock in an artifact's file name, nor the content hashes that name carries into
        out[name] = sorted(re.sub(r'[0-9a-f]{64}', 'H', re.sub(r'\d{8}-\d{6}-\d{6}', 'TS', json.dumps([r[i] for i in keep], default=str)))
                           .replace('sid-serial', 'SID').replace('sid-ahead', 'SID') for r in cur.fetchall())
    return out


@pytest.mark.parametrize('close', [False, True])
def test_asked_ahead_the_ending_writes_what_the_serial_ending_wrote(close, monkeypatch, tmp_path):
    monkeypatch.setattr(playbooks, 'folder', lambda: tmp_path / 'playbooks')
    monkeypatch.setattr(handbook, 'enabled', lambda store: True)
    monkeypatch.setattr(handbook, 'from_stranger', lambda store, tid: False)
    runs = {}
    for how in ('serial', 'ahead'):
        s, tid = world(); brain = Brain()
        with mock.patch('taskuary.terminal.transcript_for', return_value=(SESSION, 'coding', f'sid-{how}')), \
             mock.patch('taskuary.terminal.close', return_value=True), \
             mock.patch('taskuary.llm.build_llm', return_value=brain), \
             mock.patch.object(wrapup, '_ask_ahead', (lambda store, qs: {}) if how == 'serial' else wrapup._ask_ahead):
            t = time.perf_counter(); out = wrapup.wrap(s, tid, close=close, actor='owner', no_reply=True); took = time.perf_counter() - t
        wrapup.forget(tid)
        runs[how] = (ended(s, tid), sorted(brain.asked), {k: v for k, v in out.items() if k != 'artifacts'}, took, brain.most)
    (a, qa, oa, ta, _), (b, qb, ob, tb, most) = runs['serial'], runs['ahead']
    assert b == a, {k: (a[k], b[k]) for k in a if a[k] != b.get(k)}
    assert qb == qa and len(qa) == 3, 'the brain was asked the same three questions'
    assert ob == oa
    written = json.dumps(a)
    assert 'Card charges map to vendor 87' in written and 'write_playbook' in written and 'AGENT REPORT' in written, 'all three answers were applied'
    assert most <= 3 and tb < ta - LAT, f'asked at once: {tb:.2f} s against {ta:.2f} s serial'


def test_a_question_whose_inputs_moved_is_asked_again_at_its_place(monkeypatch, tmp_path):
    """Asked ahead, then the state the question reads changed before its place: the answer ahead is not used."""
    monkeypatch.setattr(playbooks, 'folder', lambda: tmp_path / 'playbooks')
    monkeypatch.setattr(handbook, 'enabled', lambda store: True)
    monkeypatch.setattr(handbook, 'from_stranger', lambda store, tid: False)
    s, tid = world(); brain = Brain()
    real_report = wrapup.report_from_transcript
    def report_then_retitle(store, task_id, *a, **k):
        out = real_report(store, task_id, *a, **k); store.update_task(task_id, {'Title': 'Retitled while the report was written'}, 'owner'); return out
    with mock.patch('taskuary.terminal.transcript_for', return_value=(SESSION, 'coding', 'sid-moved')), \
         mock.patch('taskuary.terminal.close', return_value=True), mock.patch('taskuary.llm.build_llm', return_value=brain), \
         mock.patch.object(wrapup, 'report_from_transcript', report_then_retitle):
        wrapup.wrap(s, tid, close=False, actor='owner', no_reply=True)
    wrapup.forget(tid)
    users = [u for _, u in brain.asked]
    assert sum('Retitled while the report was written' in u for u in users) == 2, 'both later questions were asked again, as they now read'
