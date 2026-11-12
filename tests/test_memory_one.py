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


def test_one_topic_keeps_the_newest_word_and_a_lesson_in_other_spacing_is_said_once():
    """The memory audit, 2026-11-12: the model named no `replaces`, so "not a task" and then "made a task" on one topic left two lines
    contradicting each other in front of triage; and the same lesson in other case or spacing was written as a second line."""
    s = MemoryStore()
    a = memorylines.teach(s, 'not_a_task', 'msg1', 'Subject: Ledger export', 'subject', 'ledger export', llm=teacher('Ledger export mail is reading only'))
    b = memorylines.teach(s, 'made_task', 'msg2', 'Subject: Ledger export', 'subject', 'ledger export',
                          llm=teacher('Ledger export failures are yours to fix - real work'))
    assert a not in lines(s) and lines(s).count(b) == 1, 'the newer verdict on the same topic stands, the older retires'
    assert s._one("SELECT 1 x FROM learned_history WHERE Action='replaced' AND Text=?", (a,)), 'and the retiring is in the history'
    other = memorylines.teach(s, 'not_a_task', 'msg3', 'Subject: Room booking', 'subject', 'room booking', llm=teacher('Room bookings are reading only'))
    assert other in lines(s) and b in lines(s), 'another topic is another line'
    assert memorylines.teach(s, 'made_task', 'msg4', 'Subject: Ledger export', 'subject', 'ledger export',
                             llm=teacher('ledger  export failures are yours to fix -  real work.')) == '', 'said once'


def test_wrong_takes_a_verdicts_line_out_and_it_is_not_taught_back():
    """A line a verdict taught has no tag, so Wrong answered "That line is yours - you wrote it" - untrue, and the owner could only Forget the
    model's words (2026-11-12). Wrong now takes it out for good; a line he typed himself still is his to Forget, not Wrong."""
    from taskuary import memoryedit
    s = MemoryStore()
    raw = memorylines.teach(s, 'not_ours', 'msg1', 'Subject: Payroll run', 'subject', 'payroll run', llm=teacher('Payroll runs are not yours'))
    key = next(k for r, k in lc.lines(s.get_doc('learned'), lc.CARE) if r.strip() == raw)
    assert memoryedit.mark(s, key, 'wrong')['ok'] and raw not in lines(s)
    assert memorylines.teach(s, 'not_ours', 'msg2', 'Subject: Payroll run', 'subject', 'payroll run', llm=teacher('Payroll runs are not yours')) == ''
    assert raw not in lines(s) and not memorylines.said(s), 'what it fed no longer counts as the owner having said it'
    memorylines.keep(s, 'Payroll questions go to Ray Colton', verdict=False)
    mine = next(k for r, k in lc.lines(s.get_doc('learned'), lc.CARE) if 'Ray Colton' in r)
    try: memoryedit.mark(s, mine, 'wrong'); assert False, 'his own words are not Wrong'
    except ValueError as e: assert 'you wrote it' in str(e)


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
    """The owner, 2026-10-27: "we should always learn" - no setting and no toggle; and 2026-11-01: Pause learning is dropped, so the
    startup pass that deleted an old learn_enabled is gone too - nothing reads one, and a verdict teaches whatever an old install said."""
    import json
    from pathlib import Path
    from taskuary.store import SQLiteStore
    root = Path(server.__file__).parent
    for f in ('settings_schema.json', 'settings_defaults.json'):
        assert 'learn_enabled' not in json.loads((root / f).read_text(encoding='utf-8')), f
    src = '\n'.join(p.read_text(encoding='utf-8') for p in root.glob('*.py'))
    assert 'learn_enabled' not in src, 'no code reads, writes or deletes an off switch'
    # ...and a verdict teaches whatever an old install had said
    s = MemoryStore(); s.set_setting('learn_enabled', '0', 'owner')
    assert memorylines.teach(s, 'not_ours', 'msg1', 'Subject: Payroll run', llm=teacher('Payroll runs are not yours', only_this=False))


def test_each_correction_is_one_line_the_next_mail_and_the_next_agent_read():
    """THE SCRATCH TIMELINE (the memory audit, 2026-11-12): the owner re-routes a kind, changes a priority, says Not ours, edits a draft's tone
    and puts a thread under Watching - each is one line, said once, in its section; then the next mail like each one is triaged with that
    line in the CACHED memory block (the same bytes for every sender), and the next agent on such a task starts with it. A changed priority
    and a Watch taught nothing before."""
    from fastapi import BackgroundTasks
    from taskuary import general, responder
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 'o')
    said = {'routing': 'Timesheet fixes are a talk with the Assistant, not code', 'priority': 'Headcount sheets come first - urgent the day they come',
            'not_ours': "Facilities bookings are the site managers' work, not yours", 'watch': "Audit follow-ups are the controller's - you keep them in sight"}
    def model(system, user, **k):
        kind = next(k for k, w in memorylines.WORDS.items() if f'THE VERDICT: {w}\n' in user)
        return json.dumps({'line': said[kind], 'replaces': '', 'only_this': True})
    def task(xid, who, subj, kind='general'):
        tid = s.create_task({'Title': subj, 'Kind': kind, 'Status': 'open'}, 'router')
        return tid, s.add_message({'TaskId': tid, 'ExternalId': xid, 'Channel': 'email', 'Subject': subj, 'FromEmail': who, 'BodyText': subj, 'Status': 'routed'})
    a, b, (_, c), e = (task('t1', 'marcus@northwind.example', 'Timesheet hours wrong for October', 'coding')[0],
                       task('t2', 'gail@northwind.example', 'Headcount sheet for Monday')[0], task('t3', 'rooms@facilities.example', 'Boardroom booking request'),
                       task('t5', 'omar@northwind.example', 'Audit follow-up on accruals')[0])
    with mock.patch.object(server, 'store', s), mock.patch.object(memorylines, '_llm', lambda st: model):
        c_ = TestClient(server.app)
        assert c_.patch(f'/api/tasks/{a}', json={'Kind': 'general'}).status_code == 200                                  # (a) re-routed
        assert c_.patch(f'/api/tasks/{b}', json={'Priority': 'urgent'}).status_code == 200                               # (b) priority
        assert c_.post(f'/api/messages/{c}/not-mine', json={}).status_code == 200                                         # (c) not ours
        responder.style_feedback(s, 'Keep replies to two lines, no greeting')                     # (d) the note an edited draft carries
        bg = BackgroundTasks(); server._run_operation({'kind': 'task.watching', 'target': e, 'targetKind': 'task', 'params': {}}, bg)  # (e)
        for t in bg.tasks: t.func(*t.args, **t.kwargs)
    care = _section(s, 'care')
    for w in said.values(): assert sum(w in r for r in care) == 1, w
    assert len(care) == 4 and 'two lines, no greeting' in s.get_doc('style'), 'one line each, in its place'
    seen = []
    def triage(system, user, **k): seen.append(system); return '{"intent":"fyi","why":"x"}'
    for i, (who, subj) in enumerate((('marcus@northwind.example', 'Timesheet hours wrong for November'), ('gail@northwind.example', 'Headcount sheet again'),
                                     ('rooms@facilities.example', 'Boardroom booking for Friday'), ('omar@northwind.example', 'Audit follow-up: one more'))):
        ingest.ingest_message(s, {'external_id': f'n{i}', 'channel': 'email', 'from_email': who, 'subject': subj, 'body': subj}, llm=triage)
    memory = {x.blocks[-1] for x in seen}
    assert len(seen) == 4 and len(memory) == 1, 'one memory block, the same bytes for every sender: cached once'
    for w in said.values(): assert w in next(iter(memory)), w
    nxt, _ = task('t9', 'marcus@northwind.example', 'Timesheet hours missing for November')
    system = general._prompt(s, nxt)[0]
    assert said['routing'] in system and 'two lines, no greeting' in system, 'the next agent starts with the lesson and the voice'
    assert said['not_ours'] not in system, 'and not the lesson about another sender'
