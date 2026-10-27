"""ONE MEMORY (the owner, 2026-10-27: "everything that learns about the user should be saved in memory"; of the Settings notes page,
"probably garbage, remove it"; of the notes table, "we don't need it"). Every fact the owner gives is a LEARNED.md line under the section it
is about, and a verdict is a line only when it TEACHES something about the owner - in words, the kind of work and why ("just 'this not for
agent' doesn't add to understanding of the user") - and only when it is not already said ("as long as it's not bloat"). A line about one
sender, domain or topic ends `(about: ...)`. The old table's rows move in once, at start, and the table goes. Invented Northwind world."""
import json
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import assistant, funnel, ingest, learn, learned_cut as lc, learnedgraph, memoryedit, memorylines, recentlydeleted, server
from taskuary.store import MemoryStore
from tests.memlines import legacy_row, teacher, teaching, lines


def _section(s, slug): return [raw for raw, _ in lc.lines(s.get_doc('learned') or '', lc.SECTIONS[slug])]
def _table(s): return bool(s._one("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory'"))


def test_a_fresh_install_has_no_notes_table():
    s = MemoryStore()
    assert not _table(s) and not hasattr(s, 'add_memory') and not hasattr(s, 'list_memories')


def test_every_note_moves_into_learned_once_and_the_table_goes():
    s = MemoryStore()
    legacy_row(s, 'Payroll questions are never mine - Ray Colton handles them')                                          # global, typed
    legacy_row(s, 'Prefers a call to a long mail', 'sender', 'paula@northwind.example')                                   # about one person
    legacy_row(s, '2026-10-01: "Statement of account" from ar@vendor.example - NOT OURS: other people\'s work, no task, no reply',
               'sender_domain', 'vendor.example', 'verdict')
    legacy_row(s, '"Resident refund request - Doe" - NOT A TASK: filed', 'subject', 'resident refund request', 'verdict')
    legacy_row(s, 'Close every reply with the next step', source='writing')
    legacy_row(s, 'A note the owner switched off', active=0)
    assert memorylines.migrate(s) == 4
    assert not _table(s), 'drained, then dropped'
    care, people = _section(s, 'care'), _section(s, 'people')
    assert '- Payroll questions are never mine - Ray Colton handles them' in care
    assert '- Prefers a call to a long mail (about: paula@northwind.example)' in people
    assert any(r.endswith('(about: anyone at vendor.example)') and r.startswith('- "Statement of account"') for r in care), 'the date goes'
    assert any(r.endswith('(about: the topic "resident refund request")') for r in care)
    assert 'next step' in s.get_doc('style') and 'next step' not in s.get_doc('learned'), "a writing note is the drafter's"
    assert 'switched off' not in s.get_doc('learned')
    doc = s.get_doc('learned')
    assert memorylines.migrate(s) == 0 and s.get_doc('learned') == doc, 'idempotent'
    # ...an old evidence id still resolves (a learned line citing mem3 is not a made-up one), a later one does not
    assert learnedgraph.resolves(s, 'mem3') and not learnedgraph.resolves(s, 'mem99')


def test_a_crash_after_the_lines_before_the_drop_writes_nothing_twice():
    s = MemoryStore()
    legacy_row(s, 'Payroll questions are never mine')
    memorylines.migrate(s)
    legacy_row(s, 'Payroll questions are never mine')          # the table back, holding a row already written (id 1 again)
    memorylines.migrate(s)
    assert _section(s, 'care').count('- Payroll questions are never mine') == 1 and not _table(s)


def test_the_readers_find_the_lines_by_what_they_are_about():
    s = MemoryStore()
    raw = memorylines.keep(s, '"Statement of account" from ar@vendor.example - NOT OURS: other people\'s work', 'sender', 'ar@vendor.example')
    hit = ingest.notes_for(s, {'from_email': 'AR@vendor.example', 'subject': 'Statement', 'body': 'balance'})
    assert any('NOT OURS' in n for n in hit)
    assert ingest.notes_for(s, {'from_email': 'erin@northwind.example', 'subject': 'Lunch', 'body': 'x'}) == []
    # ...and it is not the general memory of every other reader: a line about one other sender comes after every general line
    assert lc.rank(raw, 'k', {'sender': 'erin@northwind.example'}) == 5


def _msg(s, subj='Resident refund request - Doe', frm='refunds@vendor.example', **kw):
    return s.add_message({'ExternalId': f'n{subj}', 'Channel': 'email', 'Subject': subj, 'FromEmail': frm,
                          'BodyText': 'Please process the refund.', 'Status': 'filed', 'SentAt': '2026-10-20 09:00', **kw})


def test_not_ours_writes_what_it_teaches_in_words_and_undo_takes_it_back():
    s = MemoryStore()
    mid, seen = _msg(s), []
    lesson = "Resident refund requests are the business office's work, not yours"
    with mock.patch.object(server, 'store', s), mock.patch.object(memorylines, '_llm', lambda st: teacher(lesson, seen=seen)):
        out = TestClient(server.app).post(f'/api/messages/{mid}/not-mine', json={'note': None, 'scope': 'subject'}).json()
    assert out['learned'] == f'msg{mid}' and 'memoryId' not in out
    raw = next(r for r in _section(s, 'care') if lesson in r)
    assert raw.endswith('(about: the topic "resident refund request")'), 'it holds for this topic only'
    assert 'Not ours' in seen[0] and 'refunds@vendor.example' in seen[0], 'the model reads the verdict and the item'
    assert memorylines.said(s) == {f'msg{mid}'}
    # ...and its Undo: the line comes out, and it no longer counts as the owner having said it
    assert memorylines.untaught(s, f'msg{mid}') == 1
    assert lesson not in s.get_doc('learned') and memorylines.said(s) == set()


def test_a_verdict_that_teaches_nothing_writes_nothing():
    s = MemoryStore()
    mid = _msg(s, 'Re: lunch', 'gail@northwind.example')
    before = s.get_doc('learned')
    with mock.patch.object(server, 'store', s), teaching(''):
        TestClient(server.app).post(f'/api/messages/{mid}/file', json={})
    assert s.get_doc('learned') == before
    # ...and with no brain at all, no bare verdict line stands in for a lesson
    with mock.patch.object(server, 'store', s), mock.patch.object(memorylines, '_llm', lambda st: None):
        TestClient(server.app).post(f'/api/messages/{_msg(s, "Weekly ledger export")}/not-mine', json={'scope': 'subject'})
    assert s.get_doc('learned') == before and not any('NOT OURS' in l for l in lines(s))


def test_a_lesson_already_said_is_not_said_twice_and_a_sharper_one_replaces_it():
    s = MemoryStore()
    old = 'You leave facilities scheduling to the site managers'
    memorylines.keep(s, old, verdict=False)
    assert memorylines.teach(s, 'not_ours', 'msg1', 'Subject: HVAC visit', llm=teacher(old)) == '', 'already said: nothing'
    sharp = 'Facilities scheduling - HVAC, cleaning, room bookings - is the site managers\' work, never yours'
    raw = memorylines.teach(s, 'not_ours', 'msg2', 'Subject: Room booking', llm=teacher(sharp, replaces=old, only_this=False))
    assert raw == f'- {sharp}' and f'- {old}' not in lines(s) and lines(s).count(raw) == 1
    # ...and an Undo of the sharper one puts the older line back
    memorylines.untaught(s, 'msg2')
    assert f'- {old}' in lines(s) and raw not in lines(s)


def test_not_for_the_agent_is_one_line_that_says_why():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Invoice dispute with vendor', 'Kind': 'coding', 'Status': 'open'}, 'router')
    s.add_message({'TaskId': tid, 'ExternalId': 'v1', 'Channel': 'email', 'Subject': 'Invoice 4411 disputed - credit note?',
                   'FromEmail': 'billing@vendor.example', 'BodyText': 'We dispute the credit.', 'Status': 'routed'})
    lesson = 'You handle vendor invoice disputes yourself - not agent work'
    with mock.patch.object(server, 'store', s), teaching(lesson):
        out = TestClient(server.app).post(f'/api/tasks/{tid}/not-coding', json={}).json()
    assert out['learned'] == f'task{tid}'
    care = _section(s, 'care')
    assert [r for r in care if 'agent' in r.lower()] == [next(r for r in care if lesson in r)], 'one line, no ROUTING KIND line beside it'
    assert not any('NOT A CODING TASK' in l or 'ROUTING' in l for l in lines(s))


def test_a_routing_correction_teaches_in_words_once():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Timesheet hours wrong', 'Kind': 'coding', 'Status': 'open'}, 'router')
    s.add_message({'TaskId': tid, 'ExternalId': 'r1', 'Channel': 'email', 'Subject': 'Timesheet hours wrong for October',
                   'FromEmail': 'marcus@northwind.example', 'BodyText': 'fix my hours', 'Status': 'routed'})
    from fastapi import BackgroundTasks
    seen, bg = [], BackgroundTasks()
    # ...the lesson is taught off the press: handed a BackgroundTasks it runs here, in order - called with none, teach_soon starts a
    # thread, and asserting on what that thread has not written yet is a race (it failed one run in a few)
    with mock.patch.object(server, 'store', s), mock.patch.object(memorylines, '_llm', lambda st: teacher('Timesheet fixes are a talk with the Assistant, not code', seen=seen)):
        server._teach_routing(tid, 'kind', 'general', background=bg)
        server._teach_routing(tid, 'kind', 'general', background=bg)  # the same press again teaches nothing new
        for t in bg.tasks: t.func(*t.args, **t.kwargs)
    assert len(seen) == 1 and 'general' in seen[0]
    assert sum('Timesheet fixes' in r for r in _section(s, 'care')) == 1 and not any('ROUTING' in l for l in lines(s))


def test_an_advisor_idea_taken_up_or_turned_down_is_a_line_only_when_it_adds():
    s = MemoryStore()
    a = s._exec("INSERT INTO idea (Key, Text, Kind, Status) VALUES ('idea:x', 'Unsubscribe from the vendor newsletter', 'cleanup', 'open')")
    b = s._exec("INSERT INTO idea (Key, Text, Kind, Status) VALUES ('idea:y', 'Unsubscribe from the vendor digest', 'cleanup', 'open')")
    ia, ib = (s._one('SELECT * FROM idea WHERE IdeaId=?', (i,)) for i in (a, b))
    said = 'You do not want newsletter clean-up raised - you unsubscribe yourself'
    with teaching(said), mock.patch('threading.Thread', _Inline):
        assistant._keep_verdict(s, ia, 'dismiss_kind', 'owner')
    with teaching(''), mock.patch('threading.Thread', _Inline):
        assistant._keep_verdict(s, ib, 'dismiss', 'owner')              # the same again: nothing new, no line
    with teaching('never written'), mock.patch('threading.Thread', _Inline):
        assistant._keep_verdict(s, ib, 'done', 'owner')                 # handled some other way says nothing about the owner
    assert _section(s, 'bring') == [f'- {said}']


class _Inline:
    def __init__(self, target=None, args=(), kwargs=None, **k): self.f, self.a, self.k = target, args, kwargs or {}
    def start(self): self.f(*self.a, **self.k)


def test_an_old_mute_is_said_once_in_learned():
    s = MemoryStore()
    s.set_setting(funnel.MUTES_KEY, json.dumps([{'sender': 'reports@vendor.example', 'words': ['statement'], 'why': 'finance handles these'}]), 'o')
    memorylines.migrate(s); memorylines.migrate(s)
    assert _section(s, 'care').count('- Not worth showing you: finance handles these (about: reports@vendor.example)') == 1


def test_the_old_verdicts_block_goes():
    s = MemoryStore()
    s.save_doc('learned', s.get_doc('learned') + f'\n{learn.VERD_HEADER}\n_(every verdict)_\n{learn.VERD_START}\n- old [mem1 · sender]\n{learn.VERD_END}\n', 't')
    learn.note_verdicts(s)
    assert learn.VERD_START not in s.get_doc('learned') and learn.VERD_HEADER not in s.get_doc('learned')
    assert lc.CARE in s.get_doc('learned')


def test_the_reflection_never_sees_the_scoped_lines_and_puts_them_back():
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


def test_a_forgotten_verdict_line_withdraws_what_it_fed():
    s = MemoryStore()
    raw = memorylines.teach(s, 'not_a_task', 'msg7', 'Subject: Ledger export', 'subject', 'ledger export',
                            llm=teacher('The nightly ledger export is noise to you'))
    assert memorylines.said(s) == {'msg7'}
    k = next(k for r, k in lc.lines(s.get_doc('learned'), lc.CARE) if r.strip() == raw)
    with mock.patch.object(learn, 'withdraw') as w:
        memoryedit.mark(s, k, 'forget')
    w.assert_called_once_with(s, 'msg7')
    assert raw not in lines(s) and memorylines.said(s) == set()


def test_the_lessons_are_the_reflections_evidence_and_the_digests_window():
    s = MemoryStore()
    memorylines.teach(s, 'not_ours', 'msg3', 'Subject: Payroll run', llm=teacher('Payroll runs are the payroll team\'s, not yours', only_this=False))
    assert 'msg3 [not_ours] - Payroll runs' in learn.gather(s, '2000-01-01')
    ev = learnedgraph._resolve(s, 'msg3')
    assert ev['kind'] == 'verdict' and 'Payroll runs' in ev['label']


def test_learning_has_no_off_switch(tmp_path):
    """The owner, 2026-10-27: "we should always learn" - no setting, no toggle, and an old learn_enabled=0 is dropped at start."""
    import json
    from pathlib import Path
    from taskuary.store import SQLiteStore
    root = Path(server.__file__).parent
    for f in ('settings_schema.json', 'settings_defaults.json'):
        assert 'learn_enabled' not in json.loads((root / f).read_text(encoding='utf-8')), f
    db = str(tmp_path / 't.db')
    s = SQLiteStore(db); s.set_setting('learn_enabled', '0', 'owner')
    assert SQLiteStore(db).get_setting('learn_enabled') is None, 'an old off switch is dropped'
    # ...and a verdict teaches whatever an old install had said
    s = MemoryStore(); s.set_setting('learn_enabled', '0', 'owner')
    assert memorylines.teach(s, 'not_ours', 'msg1', 'Subject: Payroll run', llm=teacher('Payroll runs are not yours', only_this=False))
