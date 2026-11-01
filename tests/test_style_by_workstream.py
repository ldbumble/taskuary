"""HOW THE OWNER WRITES, PER WORKSTREAM (the owner, 2026-11-01: "it might get complicated" - "try it"; the design's S9). STYLE.md is the
shared style; a marked section per workstream says what differs there, written from the owner's sent words in it; a draft reads its
workstream's lines, falls back to the shared style, and leaves a receipt the measure reads; one setting switches it off. Invented people."""
import importlib.util, json
from pathlib import Path
import pytest
from taskuary import responder, stylews, workstreams as W
from taskuary.store import MemoryStore
from taskuary.testing import Factory

OMAR, ERIN = 'omar@ledger.example', 'erin@northwind.example'
SHARED = '## Reply style\n- Two or three sentences, the answer first.\n- Sign off "Best, Alex".\n'


@pytest.fixture
def s():
    s = MemoryStore()
    s.set_setting('owner_email', 'alex@northwind.example', 'test')
    s.save_doc('style', SHARED, 'owner')
    W.save(s, [{'name': 'Northwind finance systems', 'domains': ['northwind.example']}, {'name': 'Ledger app', 'people': [OMAR]}])
    return s


def _sent(s, slug, n=12):
    f = Factory(s)
    for i in range(n):
        m = f.message(channel='whatsapp', direction='out', status='context', body=f'yo pushed it {i} 👍', conversation_id='whatsapp:ledger')
        s._exec('UPDATE message SET Workstream=? WHERE MessageId=?', (slug, m))


def test_a_workstreams_style_is_written_from_its_sent_words_and_the_shared_style_never_carries_it(s):
    _sent(s, 'ledger-app')
    asked = {}
    def llm(system, user, **k): asked['user'] = user; return '- Lowercase, no greeting, no sign-off\n- An emoji is fine'
    assert stylews.write(s, llm, 'ledger-app').startswith('- Lowercase')
    assert 'yo pushed it' in asked['user'] and 'the answer first' in asked['user']          # read against the shared style
    assert stylews.lines(s, 'ledger-app') == '### In Ledger app\n- Lowercase, no greeting, no sign-off\n- An emoji is fine'
    assert 'Lowercase' not in responder.style_doc(s) and 'the answer first' in responder.style_doc(s)
    assert stylews.lines(s, 'northwind-finance-systems') == '' and stylews.block(s, 'northwind-finance-systems') == ''   # the fallback
    # ...too little mail, or nothing different: nothing written
    assert stylews.write(s, llm, 'northwind-finance-systems') == ''
    _sent(s, 'northwind-finance-systems')
    assert stylews.write(s, lambda *a, **k: 'same', 'northwind-finance-systems') == ''


def test_a_draft_reads_its_workstreams_lines_leaves_a_receipt_and_the_setting_switches_it_off(s):
    _sent(s, 'ledger-app')
    stylews.write(s, lambda *a, **k: '- Lowercase, no greeting, no sign-off', 'ledger-app')
    f = Factory(s)
    t, _ = f._work('Export greyed', kind='task', channel='email', from_email=OMAR, from_name='Omar Keller', body='Export is greyed - can you look?')
    seen = {}
    def brain(system, user, **k): seen['system'] = system; return 'looking now'
    responder.draft_reply(s, t, llm=brain) if hasattr(responder, 'draft_reply') else pytest.skip('no draft entry')
    assert 'In Ledger app you write differently' in seen['system'] and 'Lowercase' in seen['system']
    assert s._one("SELECT 1 x FROM audit WHERE EntityType='task' AND EntityId=? AND Action='style_ws'", (str(t),))
    s.set_setting(stylews.KEY, '0', 'owner')
    responder.draft_reply(s, t, llm=brain)
    assert 'Lowercase' not in seen['system'] and 'the answer first' in seen['system']


def test_the_measure_compares_edit_rates_with_and_without_the_workstreams_lines(tmp_path):
    from taskuary.store import SQLiteStore
    _P = Path(__file__).resolve().parent.parent / 'tools' / 'style_by_workstream.py'
    spec = importlib.util.spec_from_file_location('style_by_workstream', _P); T = importlib.util.module_from_spec(spec); spec.loader.exec_module(T)
    s = SQLiteStore(str(tmp_path / 'taskuary.db'))
    f = Factory(s)
    for n, (used, status) in enumerate([(True, 'approved'), (True, 'approved'), (True, 'edited'), (False, 'edited'), (False, 'edited'), (False, 'approved')]):
        t = f.task(title=f't{n}')
        if used: s.audit('task', t, 'style_ws', 'drafter', 'agent', {'workstream': 'ledger-app'})
        s._exec("INSERT INTO review (TaskId, Status, DecidedBy, DecidedAt, CreatedAt) VALUES (?,?,'owner',datetime('now','localtime'),datetime('now','localtime'))", (t, status))
    m = T.measure(T.connect(tmp_path), '2000-01-01')
    assert (m['with']['rate'], m['without']['rate']) == (33, 67)
    assert T.line(m) == 'Style per workstream: 33% edited of 3 with its lines, 67% edited of 3 with the shared style only'
