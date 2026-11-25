"""THE ONE MEMORY, THREE STORES (memory.py, r10 2026-11-23): what the owner SAID is kept in his words and used everywhere it bears, a
correction on the same subject replaces it, what was INFERRED from what he did is never his word and goes into use by itself once his own
acts bear it out - never by asking him - the memory stays short, and his signature has one home.
Each test is a shape a walk found broken, with invented Northwind people."""
import json
from unittest import mock
from taskuary import context, general, learning, memory, responder, signatures
from taskuary.store import MemoryStore, SQLiteStore
from tests.memlines import teacher

ERIN, GAIL, RAY, PAULA = 'erin@northwind.example', 'gail@northwind.example', 'ray@northwind.example', 'paula@northwind.example'


def _store(s=None):
    s = s or MemoryStore()
    s.set_setting('owner_name', 'Alex Doyle', 't'); s.set_setting('owner_email', 'alex@northwind.example', 't')
    return s


def _task(s, kind, frm=RAY, title='Move the review?'):
    tid = s.create_task({'Title': title, 'Kind': kind, 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
    s.add_message({'TaskId': tid, 'ExternalId': f'm{tid}', 'Channel': 'email', 'FromName': 'Ray Colton', 'FromEmail': frm,
                   'Subject': title, 'BodyText': 'Could we move it to Friday at 9?', 'Status': 'routed'})
    return tid


def test_his_meeting_hours_said_on_one_task_reach_every_other_task_after_a_reload(tmp_path):
    """Walk 6, H5: "only meetings between 10am and 2pm, never on Fridays" was filed under Your people, named nobody on any task and reached no
    agent - three 2:00 PM slots were proposed. What he said about nobody rides into every task, the coding brief and the general agent's
    turn alike, and it is kept: a restart reads it back from the store."""
    db = str(tmp_path / 'tq.db')
    s = _store(SQLiteStore(db))
    memory.remember(s, 'Only meetings between 10am and 2pm, never on Fridays', 'meeting hours', about='Alex')
    memory.remember(s, 'Gail Moreno books the offsites', 'gail and offsites', about=GAIL)
    s = SQLiteStore(db)                                                                                 # ...the app restarts
    for read in (context.build(s, _task(s, 'coding')), general.learned_block(s, _task(s, 'general')),
                 responder.voice_line(s, [RAY]), memory.whole(s, 'triage')):
        assert 'Only meetings between 10am and 2pm, never on Fridays' in read, read
    assert 'Gail Moreno books' not in context.build(s, _task(s, 'coding')), 'a line about someone else stays with the tasks they are on'


def test_a_correction_on_the_same_subject_replaces_the_old_line_and_nobody_reads_both():
    """Walk 6: a correction left both lines standing, and two lines that disagree were read as two truths. Matched by the subject, never
    by the words - and his word replaces a line Taskuary had learned on that subject too."""
    s = _store()
    memory.infer(s, 'Payroll questions go to Erin', 'Who handles payroll questions', ['msg1', 'msg2'], confirmed=True)
    first = memory.remember(s, 'Erin handles payroll questions', 'who handles payroll questions', about=ERIN)
    assert first['replaced'] == 'Payroll questions go to Erin'
    r = memory.remember(s, 'Erin left - send payroll questions to Gail now', 'Who handles payroll questions?', about=GAIL)
    assert r['replaced'] == 'Erin handles payroll questions'
    live = [x['Text'] for x in memory.in_use(s)]
    assert live == ['Erin left - send payroll questions to Gail now']
    for read in (memory.whole(s, 'triage'), s.get_doc('learned'), memory.for_task(s, {GAIL, ERIN})):
        assert 'send payroll questions to Gail now' in read and 'Erin handles payroll' not in read and 'go to Erin' not in read
    assert memory.remember(s, 'erin left - send payroll questions to gail now.', 'who handles payroll questions')['already'], 'said again is not twice'
    assert len(memory.rows(s, memory.SAID)) == 1


def _taught(s, line, subject, *srcs, against=''):
    with mock.patch.object(learning, '_llm', lambda st, llm=None: teacher(line, subject, only_this=False, against=against)):
        for src in srcs: learning.teach(s, 'watch', src, 'From: Payworth Billing\nSubject: Invoice 88')


def test_a_lesson_his_own_acts_keep_bearing_out_goes_into_use_with_no_press_from_him():
    """Walk 6, 2026-11-23: one Watch it press taught "you leave paying vendor invoices to someone else" as his own line, read at once. Then
    r10 made every learned line wait on an Adopt on a habits row - and the owner: "we don't want to have to confirm manually. that's
    useless. it has to learn from confirmation". One press is evidence, unused; the same lesson in three of his episodes is in use by
    itself, still what was learned and never what he said, with nothing put to him to confirm."""
    s = _store()
    line = 'You leave paying vendor invoices to someone else'
    readers = lambda: memory.whole(s, 'triage') + memory.for_task(s, {'billing@payworth.example'}) + s.get_doc('learned')
    _taught(s, line, 'vendor invoices', 'task7', 'task8')
    r = memory.get(s, 'vendor invoices · watch')
    assert r['Kind'] == memory.INFERRED and not r['Confirmed'] and r['ev'] == ['task7', 'task8']
    assert line not in readers(), 'two episodes are not yet how he works'
    assert {l['key']: l for l in memory.page(s)['lines']}[r['key']]['status'] == 'hypothesis', 'the Memory page shows it still being learned'
    _taught(s, line, 'vendor invoices', 'task9')
    assert memory.get(s, r['key'])['Confirmed'] and line in readers(), 'the third of his own episodes puts it in use - no press from him'
    assert memory.get(s, r['key'])['Kind'] == memory.INFERRED and not memory.has_said(s, line), '...still learned, never his word'
    assert {l['key']: l for l in memory.page(s)['lines']}[r['key']]['status'] == 'live'
    assert not s._rows("SELECT 1 FROM idea WHERE Key LIKE 'habit%'"), 'nothing is put to him to confirm'
    memory.mark(s, r['key'], 'wrong')
    assert line not in readers(), 'his Wrong takes it down at once'
    _taught(s, line, 'vendor invoices', 'task10', 'task11', 'task12')
    assert line not in readers() and not memory.get(s, 'vendor invoices · watch'), '...and it is never learned again'


def test_an_act_of_his_that_goes_against_a_line_in_use_weakens_it_until_his_acts_bear_it_out_again():
    s = _store()
    line = 'You leave paying vendor invoices to someone else'
    _taught(s, line, 'vendor invoices', 'task7', 'task8', 'task9')
    assert line in memory.whole(s, 'triage')
    _taught(s, 'You pay the vendor invoices you approved yourself', 'paying approved invoices', 'task10', against='vendor invoices · watch')
    assert memory.get(s, 'vendor invoices · watch')['N'] == 2 and line not in memory.whole(s, 'triage'), 'a contradicting act takes it out of use'
    _taught(s, line, 'vendor invoices', 'task11')
    assert line in memory.whole(s, 'triage'), 'borne out again, in use again'


def test_the_memory_stays_short_conclusions_within_its_caps_never_a_record():
    """The owner, 2026-11-23: "don't write too much detail in memory, otherwise it's basically the hub". A learned line is a conclusion of
    one sentence; at most PER_ABOUT about one person, CAP in use and LEARNING still being seen - the line least recently borne out goes
    first - and what he said is never trimmed. The Memory page shows the same lines every reader has."""
    s = _store()
    memory.remember(s, 'Only meetings between 10am and 2pm', 'meeting hours')
    for i in range(memory.CAP + 15): memory.infer(s, f'You sign off on spend category {i} yourself', f'spend {i}', [f'rv{i}a', f'rv{i}b', f'rv{i}c'])
    for i in range(memory.LEARNING + 10): memory.infer(s, f'You might batch topic {i} on Fridays', f'batch {i}', [f'msg{i}'])
    for i in range(memory.PER_ABOUT + 4): memory.infer(s, f'Erin handles vendor question kind {i}', f'erin {i}', [f'task{i}'], people=[ERIN])
    live = memory.rows(s, memory.INFERRED)
    used, waiting = [r for r in live if r['Confirmed']], [r for r in live if not r['Confirmed']]
    assert len(used) == memory.CAP and len(waiting) == memory.LEARNING, 'never past its caps'
    assert sum(ERIN in r['people'] for r in live) <= memory.PER_ABOUT, 'nor past its share about one person'
    assert not memory.get(s, 'spend 0') and memory.get(s, f'spend {memory.CAP + 14}'), 'the oldest fell out first, the newest stays'
    assert memory.has_said(s, 'Only meetings between 10am and 2pm'), 'what he said is never trimmed'
    learned = [l for l in memory.page(s)['lines'] if not l['own'] and not l.get('fact')]
    assert {l['key'] for l in learned} == {r['key'] for r in live}, 'the Memory page shows the same lines'
    record = ('Invoice 4471 from Payworth for 12,480.00 was approved on 2026-11-03 by Erin Blake after the second reminder, then paid by wire '
              'on 2026-11-07 against purchase order 88-301 with the late fee waived')
    assert memory.infer(s, record, 'payworth invoice 4471', ['rv90', 'rv91', 'rv92']) == {} and not memory.get(s, 'payworth invoice 4471'), \
        'a record is the ledger\'s, never a memory line'


def test_one_make_it_a_task_acts_once_and_three_of_them_make_a_line():
    """The owner, 2026-11-24: one Make it a task was taught as a rule for all mail like it, in use at once. A one-off press is one episode;
    the same press on the same sender repeated AUTO_AT times is the line in use (2026-11-25) - never presses of other kinds or senders."""
    s = _store()
    line, ray, gail = 'Facilities scheduling mail is real work for you', 'ray@northwind.example', 'gail@northwind.example'
    subj = lambda kind, who: memory.get(s, f'facilities scheduling · {kind} · {who}')
    with mock.patch.object(learning, '_llm', lambda st, llm=None: teacher(line, 'facilities scheduling', only_this=False)):
        for src in ('msg21', 'msg22'): learning.teach(s, 'made_task', src, 'From: Ray\nSubject: Room bookings', 'sender', ray)
        assert not subj('made_task', ray)['Confirmed'] and line not in memory.whole(s, 'triage'), 'two presses are two episodes'
        learning.teach(s, 'not_a_task', 'msg23', 'From: Ray\nSubject: Room bookings', 'sender', ray)
        learning.teach(s, 'made_task', 'msg24', 'From: Gail\nSubject: Room bookings', 'sender', gail)
        assert line not in memory.whole(s, 'triage'), 'a press of another kind, or on another sender, is no third'
        learning.teach(s, 'made_task', 'msg25', 'From: Ray\nSubject: Room bookings', 'sender', ray)
    assert subj('made_task', ray)['Confirmed'] and line in memory.whole(s, 'triage'), 'the third of the same press on the same sender is the pattern'


def test_a_press_for_mail_like_this_from_now_on_is_his_confirmation_and_a_wrong_is_never_learned_again():
    s = _store()
    with mock.patch.object(learning, '_llm', lambda st, llm=None: teacher("Their weekly sign-off sheets are not yours to act on", 'sign-off sheets')):
        learning.teach(s, 'not_ours', 'msg12', 'From: Ray', 'sender', RAY)
    line = memory.get(s, 'sign-off sheets')
    assert line['Confirmed'] and line['Scope'] == 'sender' and RAY in memory.whole(s, 'triage')
    s._exec('INSERT INTO correction (MessageId) VALUES (12)')
    memory.mark(s, line['key'], 'wrong')
    assert 'sign-off sheets' not in memory.whole(s, 'triage') and not s._rows('SELECT 1 FROM correction WHERE MessageId=12')
    assert memory.infer(s, 'Their weekly sign-off sheets are not yours to act on', 'sign-off sheets', ['msg13']) == {}, 'never written back'
    try: memory.mark(s, memory.remember(s, 'I sign off sheets myself', 'my sheets')['key'], 'wrong'); assert False
    except ValueError as e: assert 'yours' in str(e), 'his own line is not something learned wrong'


def test_his_sign_off_has_one_home_and_every_card_carries_it():
    """The walk, 2026-11-21: "I sign every email 'Best, Alex'" was kept as a memory line, and the signer put "Alex Doyle" under every card -
    and a "Sign off:" line in STYLE.md was a second home read under the setting. What he says of it is the saved signature, the one the
    signer reads; STYLE.md says nothing of it any more."""
    s = _store()
    s.save_doc('style', '# STYLE.md\n\n- Sign off: "Cheers, Al"\n', 'owner')
    assert responder.signature_for(s) == 'Alex Doyle', 'STYLE.md is no home for the signature'
    r = memory.remember(s, 'Best,\nAlex', signature=True, actor='agent:coding')
    assert r['signature'] and s.get_setting('email_signature') == 'Best,\nAlex'
    rv = {'Deliver': json.dumps({'kind': 'email', 'channel': 'email'})}
    assert signatures.agent_signed(s, rv, 'Hi Gail,\n\nThe contract is attached.\n\nThanks,\nAlex Doyle').endswith('Best,\nAlex')
    assert not memory.rows(s), 'never a memory line fighting the signer'
    assert any(l['key'] == 'signature' and 'Best, / Alex' in l['text'] for l in memory.page(s)['lines']), 'shown among what he said'


def test_learned_md_is_read_into_the_three_stores_once_without_loss():
    s = _store()
    s._exec("INSERT INTO learned_history (Key,Text,Action,Actor,Ev,At) VALUES ('k1', '- Venue quotes are Paula''s (about: gail@northwind.example)', "
            "'said', 'verdict:not_ours', 'msg4', '2026-11-01')")
    s._exec("INSERT INTO learned_line (Key,Status,Text) VALUES ('stale guess', 'wrong', 'x')")
    doc = ('# LEARNED.md\n\n## How you work\n- No meetings before 10, none on Fridays\n'
           '- {{owner_first}} batches approvals on Mondays [s:5 | ev: rv1, rv2 | seen: 2026-11-01 | k: monday approvals]\n'
           "\n## What you care about\n- Venue quotes are Paula's (about: gail@northwind.example)\n"
           '- A stale guess [s:4 | ev: rv3 | seen: 2026-11-01 | k: stale guess]\n'
           '\n## Watching — not read by anyone yet\n<!-- hypotheses:start -->\n- Maybe Gail matters [s:2 | ev: msg9 | seen: 2026-11-01 | k: gail matters]\n<!-- hypotheses:end -->\n')
    s.save_doc('learned', doc, 'reflect')
    assert memory.migrate(s) == 4 and memory.migrate(s) == 0, 'once'
    said, inferred = memory.rows(s, memory.SAID), {r['Subject']: r for r in memory.rows(s, memory.INFERRED)}
    assert [r['Text'] for r in said] == ['No meetings before 10, none on Fridays'], 'his own untagged line is what he said'
    assert inferred['monday approvals']['Text'] == 'You batches approvals on Mondays' or 'Alex' in inferred['monday approvals']['Text']
    assert inferred['monday approvals']['ev'] == ['rv1', 'rv2'] and inferred['monday approvals']['Confirmed'], 'in use before r10: in use still'
    assert not inferred['gail matters']['Confirmed'], 'Watching was read by nobody: it waits for his acts, as before'
    v = next(r for r in inferred.values() if r['Source'] == 'verdict:not_ours')
    assert v['Confirmed'] and v['Scope'] == 'sender' and v['ScopeKey'] == GAIL, 'a verdict his press made for good is a confirmed learned line'
    assert 'gail matters' in inferred and 'stale guess' not in inferred, 'Watching is waiting; a Wrong stays down'
    assert s.get_doc(memory.BACKUP) == doc, 'the document as it stood is kept whole'
    assert 'No meetings before 10' in s.get_doc('learned') and '[s:' not in s.get_doc('learned'), 'LEARNED.md is now the stores\' face'
    assert 'approvals on Mondays' in memory.whole(s, 'triage')


def test_an_install_r10s_first_cut_migrated_gets_its_lines_in_use_back_once():
    """The owner, 2026-11-23: r10's first cut read LEARNED.md in and demoted the learned lines that were in use to wait on a Keep. On such
    an install the lines that stood in a section of the document as it was are in use again, once; Watching's stay learning."""
    s = _store()
    doc = ('# LEARNED.md\n\n## How you work\n- You batch approvals on Mondays [s:5 | ev: rv1, rv2 | seen: 2026-11-01 | k: monday approvals]\n'
           '\n## Watching — not read by anyone yet\n<!-- hypotheses:start -->\n- Maybe Gail matters [s:2 | ev: msg9 | seen: 2026-11-01 | k: gail matters]\n'
           '<!-- hypotheses:end -->\n')
    s.save_doc('learned', doc, 'reflect')
    memory.migrate(s)
    s._exec('UPDATE memory_line SET Confirmed=0'); s.set_setting(memory.IN_USE_FIX, '', 't')       # ...as the first cut left it
    assert 'approvals on Mondays' not in memory.whole(s, 'triage')
    assert memory.migrate(s) == 1 and memory.migrate(s) == 0, 'once'
    assert memory.get(s, 'monday approvals')['Confirmed'] and 'approvals on Mondays' in memory.whole(s, 'triage')
    assert not memory.get(s, 'gail matters')['Confirmed']


def test_a_line_one_press_put_in_use_waits_for_three_episodes_once_the_install_updates():
    """The owner, 2026-11-24: lines learned from a single press were in use, read like his word. On an install that has them, once: a press's
    line borne out fewer than AUTO_AT times goes back to being seen; one his acts bore out three times, a "from now on" press's and a
    reflected one stay in use."""
    s = _store()
    s.set_setting(memory.MIGRATED, 'x', 't'); s.set_setting(memory.IN_USE_FIX, 'x', 't')
    memory.infer(s, 'Facilities scheduling mail is real work for you', 'facilities scheduling', ['msg5'], source='verdict:made_task', confirmed=True)
    memory.infer(s, 'Payworth billing notices are FYI for you', 'payworth notices', ['msg6', 'msg7', 'msg8'], source='verdict:not_a_task')
    memory.infer(s, 'You approve spend on Mondays', 'monday spend', ['rv1'], source='reflect', confirmed=True)
    memory.infer(s, "Ray's sign-off sheets are not yours", 'sign-off sheets', ['msg4'], source='verdict:not_ours', confirmed=True)
    assert 'Facilities scheduling' in memory.whole(s, 'triage')
    memory.migrate(s)
    assert not memory.get(s, 'facilities scheduling')['Confirmed'] and 'Facilities scheduling' not in memory.whole(s, 'triage')
    assert all(memory.get(s, k)['Confirmed'] for k in ('payworth notices', 'monday spend', 'sign-off sheets'))
    memory.infer(s, 'Facilities scheduling mail is real work for you', 'facilities scheduling', ['msg9', 'msg10'], source='verdict:made_task')
    assert memory.get(s, 'facilities scheduling')['Confirmed'], 'borne out three times, in use'
    memory.migrate(s)
    assert memory.get(s, 'facilities scheduling')['Confirmed'], 'once: never set back again'



def test_an_address_he_typed_is_on_the_record_as_his_words_and_memory_says_only_the_address():
    """Walk 10, 2026-11-23: memory filed his own typed line as raw JSON "about" a person - `paula@... <{"text": "...", "after": 2}>` - and a
    bare subject line as a fact about Gail - `gail@... <Q3 board pack>`. The ledger keeps the line as he typed it; memory says the address."""
    from taskuary import ledger
    s = _store()
    tid = s.create_task({'Title': 'Board pack', 'Kind': 'general', 'Status': 'open'}, 'owner')
    general.wait_line(s, tid, f'One email each: Paula Vance ({PAULA}).', None, 'line-1')
    ledger.write(s, 'address', GAIL, 'Q3 board pack', 'mailed', 'rv1', tid)
    assert [line for a, line in ledger.given(s, tid) if a == PAULA] == [f'One email each: Paula Vance ({PAULA}).']
    said = [f['text'] for f in memory.facts(s, [PAULA, GAIL]) if f['source'] == 'ledger']
    assert said and not any('{' in t or 'Q3 board pack' in t for t in said), said
    assert f'address {PAULA} (he gave it)' in said and f'address {GAIL} (mailed)' in said
