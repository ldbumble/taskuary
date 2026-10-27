"""ONE MEMORY (the owner, 2026-10-27: "everything that learns about the user should be saved in memory"; of the Settings notes page,
"probably garbage, remove it"). Every verdict and every fact the owner gave is a LEARNED.md line under the section it is about - a line
about one sender, domain or topic ends `(about: ...)` and a newer verdict on the same thing replaces the older; the notes table is the
verdicts' record and no decision reads it. Existing notes move in once, at start. Invented Northwind world."""
import json
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import assistant, funnel, ingest, learn, learned_cut as lc, memoryedit, memorylines, server
from taskuary.store import MemoryStore


def _row(s, note, scope='global', key=None, source='manual', active=1):
    """A row as an install from before 2026-10-27 holds it: in the table, not yet in LEARNED.md (store.add_memory writes both now)."""
    from taskuary.store import MEMORY_COLS, _now
    return s._insert('memory', {'Scope': scope, 'ScopeKey': key, 'Note': note, 'Source': source, 'Active': active, 'CreatedBy': 'owner'},
                     MEMORY_COLS, {'CreatedAt': _now()})


def test_a_new_record_is_its_line_at_once():
    s = MemoryStore()
    mid = s.add_memory({'Scope': 'sender', 'ScopeKey': 'ar@vendor.example', 'Note': '"Statement" - NOT OURS: other people\'s work',
                        'Source': 'verdict', 'Active': 1, 'CreatedBy': 'owner'})
    raw = memorylines.of_row(s.list_memories()[0])
    assert raw in _section(s, 'care')
    s.set_memory_active(mid, False); assert raw not in (s.get_doc('learned') or '')
    s.set_memory_active(mid, True); assert raw in _section(s, 'care')


def _section(s, slug): return [raw for raw, _ in lc.lines(s.get_doc('learned') or '', lc.SECTIONS[slug])]


def test_every_note_moves_into_learned_once_and_nothing_is_lost():
    s = MemoryStore()
    _row(s, 'Payroll questions are never mine - Ray Colton handles them')                                        # global, typed
    _row(s, 'Prefers a call to a long mail', 'sender', 'paula@northwind.example')                                 # about one person
    _row(s, '2026-10-01: "Statement of account" from ar@vendor.example - NOT OURS: other people\'s work, no task, no reply',
         'sender_domain', 'vendor.example', 'verdict')
    _row(s, '"Resident refund request - Doe" - NOT A TASK: filed', 'subject', 'resident refund request', 'verdict')
    _row(s, 'Close every reply with the next step', source='writing')
    _row(s, 'A note the owner switched off', active=0)
    assert memorylines.migrate(s) == 4
    care, people = _section(s, 'care'), _section(s, 'people')
    assert '- Payroll questions are never mine - Ray Colton handles them' in care
    assert '- Prefers a call to a long mail (about: paula@northwind.example)' in people
    assert any(r.endswith('(about: anyone at vendor.example)') and r.startswith('- "Statement of account"') for r in care), 'the date goes'
    assert any(r.endswith('(about: the topic "resident refund request")') for r in care)
    assert 'next step' in s.get_doc('style') and 'next step' not in s.get_doc('learned'), "a writing note is the drafter's"
    assert 'switched off' not in s.get_doc('learned')
    doc = s.get_doc('learned')
    assert memorylines.migrate(s) == 0 and s.get_doc('learned') == doc, 'idempotent'
    # ...and a line the owner then Forgets is not brought back by the next start
    k = next(k for raw, k in lc.lines(doc, lc.CARE) if 'Payroll questions' in raw)
    memoryedit.mark(s, k, 'forget')
    memorylines.migrate(s)
    assert 'Payroll questions' not in s.get_doc('learned')


def test_the_readers_find_the_lines_by_what_they_are_about():
    s = MemoryStore()
    mid = _row(s, '"Statement of account" from ar@vendor.example - NOT OURS: other people\'s work', 'sender', 'ar@vendor.example', 'verdict')
    memorylines.keep_row(s, mid)
    hit = ingest.notes_for(s, {'from_email': 'AR@vendor.example', 'subject': 'Statement', 'body': 'balance'})
    assert any('NOT OURS' in n for n in hit)
    assert ingest.notes_for(s, {'from_email': 'erin@northwind.example', 'subject': 'Lunch', 'body': 'x'}) == []
    # ...and it is not the general memory of every other reader: a line about one other sender comes after every general line
    assert lc.rank(memorylines.of_row(s.list_memories()[0]), 'k', {'sender': 'erin@northwind.example'}) == 5


def test_a_newer_verdict_on_the_same_thing_replaces_the_older():
    s = MemoryStore()
    a = _row(s, '"Ledger export" - NOT A TASK: filed', 'subject', 'ledger export', 'verdict'); memorylines.keep_row(s, a)
    b = _row(s, '"Ledger export failed" - MADE A TASK: promoted', 'subject', 'ledger export', 'verdict'); memorylines.keep_row(s, b)
    care = _section(s, 'care')
    assert [r for r in care if 'ledger export' in r] == [memorylines.of_row(s.list_memories()[0])]
    # ...while the owner's own words about the same topic are never replaced by a verdict
    memorylines.keep(s, 'The ledger export is legacy - I do not care about it', 'subject', 'ledger export', verdict=False)
    c = _row(s, '"Ledger export" - NOT OURS: someone else', 'subject', 'ledger export', 'verdict'); memorylines.keep_row(s, c)
    assert any('legacy' in r for r in _section(s, 'care')) and sum('NOT' in r or 'MADE' in r for r in _section(s, 'care')) == 1


def test_not_ours_lands_in_learned_and_undo_takes_it_out():
    s = MemoryStore()
    mid = s.add_message({'ExternalId': 'n1', 'Channel': 'email', 'Subject': 'Resident refund request - Doe', 'FromEmail': 'refunds@vendor.example',
                         'BodyText': 'Please process.', 'Status': 'filed', 'SentAt': '2026-10-20 09:00'})
    with mock.patch.object(server, 'store', s):
        out = TestClient(server.app).post(f'/api/messages/{mid}/not-mine', json={'note': None, 'scope': 'subject'}).json()
    row = next(m for m in s.list_memories() if m['MemoryId'] == out['memoryId'])
    assert memorylines.of_row(row) in _section(s, 'care')
    assert memorylines.drop_row(s, out['memoryId']) and memorylines.of_row(row) not in (s.get_doc('learned') or '')


def test_the_old_verdicts_block_goes():
    s = MemoryStore()
    s.save_doc('learned', s.get_doc('learned') + f'\n{learn.VERD_HEADER}\n_(every verdict)_\n{learn.VERD_START}\n- old [mem1 · sender]\n{learn.VERD_END}\n', 't')
    learn.note_verdicts(s)
    assert learn.VERD_START not in s.get_doc('learned') and learn.VERD_HEADER not in s.get_doc('learned')
    assert lc.CARE in s.get_doc('learned')


def test_a_routing_correction_is_a_line_too():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Timesheet hours wrong', 'Kind': 'coding', 'Status': 'open'}, 'router')
    s.add_message({'TaskId': tid, 'ExternalId': 'r1', 'Channel': 'email', 'Subject': 'Timesheet hours wrong for October',
                   'FromEmail': 'marcus@northwind.example', 'BodyText': 'fix my hours', 'Status': 'routed'})
    with mock.patch.object(server, 'store', s):
        server._teach_routing(tid, 'kind', 'task')
        server._teach_routing(tid, 'kind', 'general')
    lines = [r for r in _section(s, 'care') if 'ROUTING KIND' in r]
    assert len(lines) == 1 and 'general' in lines[0] and '(about: the topic "' in lines[0], lines


def test_no_more_ideas_like_this_is_a_bring_up_line():
    s = MemoryStore()
    assistant._keep_verdict(s, {'Key': 'idea:x', 'Text': 'Unsubscribe from the vendor newsletter'}, 'dismiss_kind', 'owner')
    assistant._keep_verdict(s, {'Key': 'idea:y', 'Text': 'Chase Erin about the budget'}, 'dismiss', 'owner')
    bring = _section(s, 'bring')
    assert bring == ['- No more ideas like this: "Unsubscribe from the vendor newsletter"']


def test_an_old_mute_is_said_once_in_learned():
    s = MemoryStore()
    s.set_setting(funnel.MUTES_KEY, json.dumps([{'sender': 'reports@vendor.example', 'words': ['statement'], 'why': 'finance handles these'}]), 'o')
    memorylines.migrate(s); memorylines.migrate(s)
    assert _section(s, 'care').count('- Not worth showing you: finance handles these (about: reports@vendor.example)') == 1


def test_the_reflection_never_sees_the_verdict_lines_and_puts_them_back():
    s = MemoryStore()
    for i in range(3):
        memorylines.keep(s, f'"Report {i}" - NOT A TASK: filed', 'subject', f'weekly report {i}')
    memorylines.keep(s, 'I do not care about the legacy export job', verdict=False)
    seen = {}
    def llm(system, user, **k):
        seen['user'] = user
        return user.split('CURRENT LEARNED.md:\n', 1)[1].split('\n\nSOUL.md', 1)[0]
    with mock.patch('taskuary.episodes.block', return_value=('', set(), None)):
        assert learn.reflect(s, llm=llm)
    assert 'NOT A TASK' not in seen['user'] and 'legacy export' in seen['user']
    assert sum('NOT A TASK' in r for r in _section(s, 'care')) == 3


def test_a_forgotten_verdict_line_switches_its_record_off():
    s = MemoryStore()
    mid = _row(s, '"Ledger export" - NOT A TASK: filed', 'subject', 'ledger export', 'verdict'); memorylines.keep_row(s, mid)
    k = next(k for raw, k in lc.lines(s.get_doc('learned'), lc.CARE) if 'Ledger' in raw)
    memoryedit.mark(s, k, 'forget')
    assert not s.list_memories(active_only=True) and 'Ledger' not in s.get_doc('learned')
