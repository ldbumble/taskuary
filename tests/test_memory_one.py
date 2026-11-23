"""THE ONE MEMORY, THREE STORES (memory.py, r10 2026-11-23): what the owner SAID is kept in his words and used everywhere it bears, a
correction on the same subject replaces it, what was INFERRED from what he did is never his word and never used before he confirms it,
and his signature has one home. Each test is a shape a walk found broken, with invented Northwind people."""
import json
from unittest import mock
from taskuary import context, general, learning, memory, responder, signatures
from taskuary.store import MemoryStore, SQLiteStore
from tests.memlines import teacher

ERIN, GAIL, RAY = 'erin@northwind.example', 'gail@northwind.example', 'ray@northwind.example'


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


def test_a_press_is_evidence_never_his_word_and_never_used_before_he_confirms_it():
    """Walk 6, 2026-11-23: one Watch it press taught "you leave paying vendor invoices to someone else" as his own line, read by triage and
    every agent at once - while on that very task he had typed "set the payment up for my approval". A press teaches a learned line, with
    its evidence; it is used only once he confirms it, and it is never shown as what he said."""
    s = _store()
    with mock.patch.object(learning, '_llm', lambda st, llm=None: teacher('You leave paying vendor invoices to someone else', 'vendor invoices', only_this=False)):
        learning.teach(s, 'watch', 'task7', 'From: Payworth Billing\nSubject: Invoice 88')
    line = memory.get(s, 'vendor invoices')
    assert line['Kind'] == memory.INFERRED and not line['Confirmed'] and line['ev'] == ['task7']
    readers = lambda: memory.whole(s, 'triage') + memory.for_task(s, {'billing@payworth.example'}) + s.get_doc('learned')
    assert 'vendor invoices to someone else' not in readers(), 'a guess in a prompt is a rule'
    page = {l['key']: l for l in memory.page(s)['lines']}[line['key']]
    assert page['status'] == 'hypothesis' and not page['own'], 'the Memory page shows it as learned, waiting on his word'
    learning.tick(s)
    assert line['key'] not in learning._asked(s), 'seen once is not asked'
    for e in ('task8', 'task9'): memory.infer(s, 'You leave paying vendor invoices to someone else', 'vendor invoices', [e])
    learning.tick(s)
    assert learning._asked(s)[line['key']]['state'] == 'open', 'seen three times, it is asked on the habits row'
    learning.answer(s, line['key'], True)
    assert 'vendor invoices to someone else' in memory.whole(s, 'triage'), 'confirmed: used from now on'
    assert memory.get(s, line['key'])['Kind'] == memory.INFERRED, '...and still what was learned, never what he said'


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
    assert inferred['monday approvals']['ev'] == ['rv1', 'rv2'] and not inferred['monday approvals']['Confirmed'], 'tagged: learned, not confirmed'
    v = next(r for r in inferred.values() if r['Source'] == 'verdict:not_ours')
    assert v['Confirmed'] and v['Scope'] == 'sender' and v['ScopeKey'] == GAIL, 'a verdict his press made for good is a confirmed learned line'
    assert 'gail matters' in inferred and 'stale guess' not in inferred, 'Watching is waiting; a Wrong stays down'
    assert s.get_doc(memory.BACKUP) == doc, 'the document as it stood is kept whole'
    assert 'No meetings before 10' in s.get_doc('learned') and '[s:' not in s.get_doc('learned'), 'LEARNED.md is now the stores\' face'
