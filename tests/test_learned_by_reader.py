"""HONEST MEMORY, ONE SECTION PER SUBJECT (phase C 2026-10-23; the memory redesign 2026-10-25).

LEARNED.md reached every prompt whole and was cut at a character count; then it was one section per reader, and the Advisor's was a
press count - "On asks from X, presses Next (1 of 1)" (the owner, 2026-10-25: a button press is not a fact about a person). Now the
sections are about the owner at work - Your people, What you care about, How you work, Promises, What to bring up - and each reader
takes the ones that help it (learned_cut.READS): triage what you care about, the Advisor your people, what you care about, how you
work and your promises, the agents the people on their own task, what you care about and your promises, the Assistant all of it.
Each within its budget, every read with a receipt, and hand edits stick."""
import pytest
from taskuary import advisor, assistantblocks, byrecipient, context, ingest, learn, learned_cut, learnedgraph, learnedlines, since
from taskuary.store import MemoryStore

CARE_LINE = '- Vendor statements from vendor.example are fyi, never a task. [s:5 | ev: mem1, mem2, mem3 | seen: 2026-10-20 | k: vendor statements]'
ERIN_LINE = '- Erin Blake (erin@northwind.example) is your manager; you answer her the same morning [s:5 | ev: out1, out2, rv3 | seen: 2026-10-20 | k: erin manager]'
GAIL_LINE = '- Gail Moreno (gail@northwind.example) gets the headcount questions [s:4 | ev: out4, out5, task6 | seen: 2026-10-20 | k: gail headcount]'
WORK_LINE = '- Vendor renewals are put off to Friday and handled together [s:4 | ev: out7, out8, out9 | seen: 2026-10-20 | k: renewals friday]'
PROMISE_LINE = '- You send Gail Moreno the headcount sheet every Monday [s:4 | ev: out10, out11, out12 | seen: 2026-10-20 | k: headcount monday]'
BRING_LINE = '- Newsletter unsubscribe ideas are dismissed [s:4 | ev: out13, out14, out15 | seen: 2026-10-20 | k: newsletter ideas]'
OLD = """# LEARNED.md — what the system has learned about {{owner_first}}

_Taskuary writes this document itself, from your verdicts: every draft you edit ..._

## Role & responsibilities
_(what you turn out to be responsible for — nothing
learned yet)_
- {{owner_first}} owns the payroll import. [s:5 | ev: mem7, mem8, mem9 | seen: 2026-09-01 | k: owns payroll import]

## What becomes a task
_(learned refinements)_
- Vendor statements from vendor.example are fyi, never a task. [s:5 | ev: mem1, mem2, mem3 | seen: 2026-10-20 | k: vendor statements]
- My own line about Payworth.

## Voice & style
_(how you actually write)_
- Replies to Erin Blake skip the greeting. [s:4 | ev: rv1, rv2, rv3 | seen: 2026-10-01 | k: replies erin blake skip greeting]

## Moves
_(what you press)_
- On asks from northwind.example, {{owner_first}} presses Send to agent (4 of 4) [s:5 | ev: pr1, pr2, pr3, pr4 | seen: 2026-10-20 | k: move todo email northwind.example]

## Proposed rules — your call
<!-- proposed:start -->
_(rules that hide things wait here)_
<!-- proposed:end -->

## Hypotheses — still being tested
<!-- hypotheses:start -->
- Gail Moreno's asks are urgent. [s:2 | ev: mem5 | seen: 2026-10-10 | k: gail moreno asks urgent]
- On drafts to vendor.example, {{owner_first}} presses Send (2 of 2) [s:3 | ev: pr5, pr6 | seen: 2026-10-20 | k: move review email vendor.example]
<!-- hypotheses:end -->

## Verdicts - the evidence
<!-- verdicts:start -->
- something [mem1 · sender]
<!-- verdicts:end -->
"""
# the 2026-10-23 shape, as an install on 0.3.9.34 holds it: a sorting section, a press-count section with the owner's own line in it
V1 = """# LEARNED.md — what the system has learned about {{owner_first}}

_Taskuary writes this document itself, from what you do. Each section is read by ONE reader and no
other._

## How you sort mail
_(triage reads only this: what you are responsible for and what becomes a task, learned from your
sorting verdicts — Not ours, Not a task, a kind or repository you moved, rules you approved)_

### What becomes a task
- Vendor statements from vendor.example are fyi, never a task. [s:5 | ev: mem1, mem2, mem3 | seen: 2026-10-20 | k: vendor statements]
- My own line about Payworth.

## What you do next
_(the Advisor reads only this: what you press on each kind of item, learned from your own presses —
it lights that button, never presses it; delete a line to undo it)_
- On asks from northwind.example, {{owner_first}} presses Send to agent (4 of 4) [s:5 | ev: pr1, pr2, pr3, pr4 | seen: 2026-10-20 | k: move todo email northwind.example]
- I batch the vendor renewals on Fridays.
- After an agent stops on a ledger export, {{owner_first}} continues it [s:4 | ev: out3, out4, out5 | seen: 2026-10-19 | k: continues ledger export]

## Proposed rules — your call
<!-- proposed:start -->
_(rules that hide things wait here)_
<!-- proposed:end -->

## Watching — not read by anyone yet
<!-- hypotheses:start -->
- On drafts to vendor.example, {{owner_first}} presses Send (2 of 2) [s:3 | ev: pr5, pr6 | seen: 2026-10-20 | k: move review email vendor.example]
- Gail Moreno's asks are urgent. [s:2 | ev: mem5 | seen: 2026-10-10 | k: gail moreno asks urgent]
<!-- hypotheses:end -->

## Verdicts - the evidence
<!-- verdicts:start -->
- something [mem1 · sender]
<!-- verdicts:end -->
"""


@pytest.fixture(autouse=True)
def cited_ids_resolve(monkeypatch):
    """These lines cite ids no row backs: here every id resolves, so what is tested is the reading. The books - an id that does not
    resolve, a line resting on nothing the owner did - are tests/test_episodes.py's."""
    monkeypatch.setattr(learnedgraph, 'resolves', lambda store, ev: True)


def put(doc: str, head: str, *ls) -> str: return doc.replace(head + '\n', head + '\n' + '\n'.join(ls) + '\n', 1)


def full() -> MemoryStore:
    """A store whose LEARNED.md has a line in every subject section."""
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 'test')
    doc = s.get_doc('learned')
    for head, ls in ((learned_cut.CARE, [CARE_LINE]), (learned_cut.PEOPLE, [ERIN_LINE, GAIL_LINE]), (learned_cut.WORK, [WORK_LINE]),
                     (learned_cut.PROMISES, [PROMISE_LINE]), (learned_cut.BRING, [BRING_LINE])):
        doc = put(doc, head, *ls)
    s.save_doc('learned', doc, 'reflect')
    return s


def test_a_fresh_doc_has_the_five_subjects_in_order_and_nothing_about_presses():
    doc = MemoryStore().get_doc('learned')
    at = [doc.index(h) for h in learned_cut.SECTIONS.values()]
    assert at == sorted(at) and at[-1] < doc.index(learn.PROP_START)
    assert learn.OLD_NEXT not in doc and learn.OLD_SORT not in doc and 'press' not in doc.split('## Your people')[1].split('## Proposed')[0]


def test_triage_reads_what_you_care_about_and_the_people_on_this_mail_and_nothing_else():
    """...the people lines for the PRIORITY alone (the owner, 2026-10-25: important is "anything from certain people")."""
    s, seen = full(), {}
    ingest.ingest_message(s, {'external_id': 'r11-1', 'channel': 'email', 'from_email': 'erin@northwind.example', 'subject': 'Statement',
                              'body': 'Your September statement is attached.'},
                          llm=lambda sys_, usr, **k: (seen.update(p=sys_ + usr), '{"intent":"fyi","why":"x"}')[1])
    assert 'Vendor statements from vendor.example are fyi' in seen['p'] and ERIN_LINE.split('[')[0].strip() in seen['p']
    assert 'weigh the priority only, never whether it is a task' in seen['p']
    for l in (GAIL_LINE, WORK_LINE, PROMISE_LINE, BRING_LINE): assert l.split('[')[0].strip() not in seen['p']
    assert learned_cut.for_reader(s, 'triage').startswith(learned_cut.CARE) and learned_cut.READS['triage'] == ('care', 'people')


def test_the_drafter_reads_the_people_lines_about_whoever_it_writes_to():
    from taskuary import responder
    s = full()
    said = responder.voice_line(s, ['Gail@northwind.example'])
    assert 'gets the headcount questions' in said and 'Erin Blake' not in said and 'Vendor statements' not in said
    assert responder.voice_line(s, ['omar@northwind.example']) == ''


def test_each_reader_reads_the_sections_of_the_matrix():
    s = full()
    adv = advisor._learned(s)
    assert all(x in adv for x in ('Erin Blake', 'Vendor statements', 'Vendor renewals', 'headcount sheet every Monday')) and 'Newsletter' not in adv
    told, _ = assistantblocks._learned(s, {})
    assert all(x in told for x in ('Erin Blake', 'Vendor statements', 'Vendor renewals', 'every Monday', 'Newsletter'))
    assert 'people' in learned_cut.READS['triage'] and not {'work', 'promises', 'bring'} & set(learned_cut.READS['triage']), \
        'a defer or a reply lag never decides whether mail is a task'


def test_an_agent_reads_the_people_on_its_own_task_and_nothing_on_a_strangers():
    s = full()
    tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 'owner')
    s.add_message({'TaskId': tid, 'ExternalId': 'e1', 'Channel': 'email', 'Subject': 'export', 'FromEmail': 'erin@northwind.example',
                   'BodyText': 'The export fails.', 'Status': 'routed'})
    page = context.build(s, tid)
    assert 'Vendor statements' in page and 'Erin Blake (erin@northwind.example)' in page and 'every Monday' in page
    assert 'gets the headcount questions' not in page, "Gail is not on this task: the owner's notes on her are not the agent's"
    assert 'Vendor renewals' not in page and 'Newsletter' not in page
    assert learned_cut.used(s, f'task:{tid}', 'agents')[0]['keys'], 'the read left a receipt'
    from taskuary import origin
    orig = origin.of_task
    try:
        origin.of_task = lambda store, t: ('stranger', 'test')
        assert 'Erin Blake (erin' not in context.build(s, tid) and 'Vendor statements' not in context.build(s, tid)
    finally: origin.of_task = orig


def test_every_read_leaves_a_receipt_of_the_lines_it_was_given():
    s = full()
    learned_cut.for_reader(s, 'advisor', {'sender': 'erin@northwind.example'}, target='task:7')
    r = learned_cut.used(s, 'task:7')[0]
    assert r['reader'] == 'advisor' and r['keys'][0] == 'erin manager' and 'newsletter ideas' not in r['keys']


def test_a_care_line_resting_on_the_ledger_alone_goes_back_to_watching():
    """Code is the law, the prompt only asks: what triage reads rests on sorting verdicts."""
    s = MemoryStore()
    stray = '- Alex runs every GitHub issue through an agent. [s:4 | ev: pr1, pr2, out3 | seen: 2026-10-20]'
    out = learn.settle(s, '', put(s.get_doc('learned'), learned_cut.CARE, stray, CARE_LINE))
    assert 'Vendor statements' in learned_cut.section(out, learned_cut.CARE) and 'GitHub issue' not in learned_cut.section(out, learned_cut.CARE)
    assert 'GitHub issue' in learn._block(out, learn.HYP_START, learn.HYP_END)


def test_a_section_past_its_cap_sends_its_weakest_to_watching():
    s = MemoryStore()
    ls = [f'- Topic number {i} matters to you. [s:{4 + i % 3} | ev: mem{i}, mem{i + 100}, task{i} | seen: 2026-10-01 | k: topic {i}]' for i in range(18)]
    out = learn.settle(s, '', put(s.get_doc('learned'), learned_cut.CARE, *ls, '- My own topic.'))
    care = learned_cut.lines(out, learned_cut.CARE)
    assert len(care) == learn.CAP + 1 and '- My own topic.' in [r for r, _ in care], 'the owner\'s line is never counted or moved'
    assert all('[s:4' in l for l in learn._block(out, learn.HYP_START, learn.HYP_END).splitlines() if 'Topic' in l), 'the weakest wait'


def test_budget_takes_whole_lines_closest_scope_first_and_records_what_did_not_fit():
    s = MemoryStore()
    general = [f'- A general sorting habit number {i} that applies to everybody. [s:5 | ev: mem{i} | seen: 2026-10-01 | k: general {i}]'
               for i in range(14)]
    mine = '- Erin Blake at northwind.example: her exports are always a task. [s:5 | ev: mem99 | seen: 2026-10-01 | k: erin exports]'
    s.save_doc('learned', put(s.get_doc('learned'), learned_cut.CARE, *general, mine), 'owner')
    out = learned_cut.for_reader(s, 'triage', {'sender': 'erin@northwind.example', 'domain': 'northwind.example'}, budget=600)
    body = out.split('\n')[1:]
    assert body[0] == mine.strip(), 'the line about this sender leads'
    assert all(l in general + [mine] for l in body), 'whole lines, never a cut through one'
    over = learned_cut.over_budget(s)
    assert len(over) == 15 - len(body) and all(r == ['triage'] for r in over.values()), 'what did not fit is marked, not silently dropped'
    g = {l['key']: l for l in learnedgraph.graph(s)['lines']}
    assert g['erin exports']['over_budget'] == [] and g['general 13']['over_budget'] == ['triage']
    assert (g['erin exports']['section_slug'], g['erin exports']['standing']) == ('care', 'in_use') and 'triage' in g['erin exports']['reads']


def test_a_people_line_knows_whom_it_is_about():
    s = full()
    assert learnedlines.row(s, 'erin manager')['Subject'] == 'erin@northwind.example' and learnedlines.row(s, 'erin manager')['Reader'] == 'people'
    assert learnedlines.row(s, 'vendor statements')['Reader'] == 'care' and not learnedlines.row(s, 'vendor statements')['Subject']


def test_the_owners_delete_is_a_tombstone_the_reflection_cannot_write_back():
    s = full()
    doc = s.get_doc('learned')
    s.save_doc('learned', doc.replace(CARE_LINE + '\n', ''), 'owner')
    assert learnedlines.row(s, 'vendor statements')['Status'] == 'forgotten'
    assert learn.reflect(s, llm=lambda *a, **k: doc)
    assert 'Vendor statements' not in s.get_doc('learned'), 'a removed line stays removed'
    grown = CARE_LINE.replace('mem1, mem2, mem3', ', '.join(f'mem{i}' for i in range(1, 10)))
    assert learn.reflect(s, llm=lambda *a, **k: doc.replace(CARE_LINE, grown))
    assert 'Vendor statements' in learned_cut.section(s.get_doc('learned'), learned_cut.CARE)
    assert learnedlines.row(s, 'vendor statements')['Status'] == 'in_use'
    assert [h['Action'] for h in s.learned_history('vendor statements')].count('born') <= 1


def test_the_owners_wording_sticks():
    s = full()
    doc = s.get_doc('learned')
    mine = CARE_LINE.replace('are fyi, never a task', 'are fyi - Alex reads them on Fridays')
    s.save_doc('learned', doc.replace(CARE_LINE, mine), 'owner')
    assert learn.reflect(s, llm=lambda *a, **k: doc)
    assert 'Alex reads them on Fridays' in s.get_doc('learned') and 'never a task' not in s.get_doc('learned')
    assert any(h['Action'] == 'edited' for h in s.learned_history('vendor statements'))


def test_a_reflection_that_drops_a_section_is_refused():
    s = full()
    doc = s.get_doc('learned')
    assert not learn.reflect(s, llm=lambda *a, **k: doc.replace(learned_cut.PROMISES + '\n', '## Things\n'))
    assert learned_cut.PROMISES in s.get_doc('learned')


def test_migration_from_the_oldest_doc_lands_in_subjects_and_voice_with_the_drafter():
    s = MemoryStore()
    s.save_doc('learned', OLD, 'reflect')
    assert learn.migrate(s) and not learn.migrate(s), 'once'
    doc = s.get_doc('learned')
    care = learned_cut.section(doc, learned_cut.CARE)
    assert 'owns the payroll import' in care and 'Vendor statements' in care and 'My own line about Payworth' in care
    assert '### Role & responsibilities' in care and '### What becomes a task' in care and 'learned yet' not in care
    assert 'presses' not in doc and learn.OLD_NEXT not in doc and learn.OLD_SORT not in doc
    assert all(h in doc for h in learned_cut.SECTIONS.values())
    assert 'Voice & style' not in doc and 'skip the greeting' not in doc
    assert learn.WATCH_HEADER in doc and 'Gail Moreno' in learn._block(doc, learn.HYP_START, learn.HYP_END)
    assert learn.PROP_START in doc and learn.VERD_START in doc and 'learned about how {{owner_first}} works' in doc
    assert ('everyone', 'Replies to Erin Blake skip the greeting.') in byrecipient.lines(s)
    assert learnedlines.row(s, 'replies erin blake skip greeting')['Reader'] == 'drafter'
    assert since.learned(s)['line'] == '', "the move itself is not this week's learning"
    assert learnedlines.row(s, 'vendor statements')['InUseAt'] == '-', 'in use since before there were records'
    for k in ('move todo email northwind.example', 'move review email vendor.example'):
        assert learnedlines.row(s, k)['Status'] == 'retired' and s.learned_history(k)[-1]['Action'] == 'retired'


def test_migration_from_the_reader_sections_keeps_every_owner_line_byte_for_byte():
    s = MemoryStore()
    s.set_setting('learn_moves_cut', '{"move x": 3}', 'learn'); s.set_setting('learn_moves_written', '{"move x": 4}', 'learn')
    s.save_doc('learned', V1, 'reflect')
    assert learn.migrate_v2(s) and not learn.migrate_v2(s) and not learn.migrate(s), 'once, and a no-op after'
    doc = s.get_doc('learned')
    care, work = learned_cut.section(doc, learned_cut.CARE), learned_cut.section(doc, learned_cut.WORK)
    assert '### What becomes a task\n- Vendor statements from vendor.example are fyi, never a task. [s:5 | ev: mem1, mem2, mem3 | seen: 2026-10-20 | k: vendor statements]\n- My own line about Payworth.' in care
    assert 'triage reads only this' not in doc and 'lights that button' not in doc
    assert '- I batch the vendor renewals on Fridays.' in work.splitlines(), 'the owner\'s own line moved byte for byte'
    assert 'continues ledger export]' in work, 'a habit from the ledger is how you work'
    assert 'presses' not in doc and 'Gail Moreno\'s asks are urgent.' in learn._block(doc, learn.HYP_START, learn.HYP_END)
    for k in ('move todo email northwind.example', 'move review email vendor.example'):
        r = learnedlines.row(s, k)
        assert r['Status'] == 'retired' and [h['Action'] for h in s.learned_history(k)][-1] == 'retired'
    assert s.get_setting('learn_moves_cut') is None and s.get_setting('learn_moves_written') is None
    assert learnedlines.row(s, 'vendor statements')['Reader'] == 'care'
    # a reflection that writes a retired press count back cannot land it
    assert learn.reflect(s, llm=lambda *a, **k: put(doc, learned_cut.WORK, '- On asks from northwind.example, {{owner_first}} presses Send to agent (4 of 4) [s:5 | ev: pr1, pr2, pr3, pr4 | seen: 2026-10-20 | k: move todo email northwind.example]'))
    assert 'presses Send to agent' not in s.get_doc('learned')


def test_migration_seeds_one_pass_over_the_last_thirty_days_only_with_an_ai(monkeypatch):
    from taskuary import capabilities
    for ai, want in ((False, None), (True, str(learn.REFLECT_AT))):
        s = MemoryStore(); s.save_doc('learned', V1, 'reflect')
        monkeypatch.setattr(capabilities, 'has_ai', lambda store, ai=ai: ai)
        assert learn.migrate_v2(s)
        assert s.get_setting('learn_pending') == want, 'no AI: nothing is guessed, the sections wait'
        if ai: assert s.get_setting('learn_last_reflect')[:10] == (learn.datetime.now() - learn.timedelta(days=30)).strftime('%Y-%m-%d')


def test_the_owners_lines_on_a_persons_page_become_people_lines():
    s = MemoryStore()
    s.save_doc('person-ray@northwind.example', '- Ray covers payroll when I am out.\n<!-- ledger:start -->\n- answers in a day [ev: out1]\n<!-- ledger:end -->\n', 'owner')
    s.save_doc('learned', V1, 'reflect')
    learn.migrate_v2(s)
    people = learned_cut.section(s.get_doc('learned'), learned_cut.PEOPLE)
    assert '- ray@northwind.example: Ray covers payroll when I am out.' in people and 'answers in a day' not in people
    assert 'Ray covers payroll' in s.get_doc('person-ray@northwind.example'), 'copied, never moved'


def test_a_switched_off_note_withdraws_what_it_fed():
    s = MemoryStore()
    ids = [s.add_memory({'Scope': 'sender', 'ScopeKey': 'news@vendor.example', 'Note': f'2026-10-0{i}: "Newsletter" - NOT A TASK', 'Source': 'verdict',
                         'Active': 1, 'CreatedBy': 'owner'}) for i in (1, 2, 3)]
    rule = f'- Newsletters from vendor.example are fyi. [s:4 | ev: {", ".join(f"mem{i}" for i in ids)} | seen: 2026-10-03 | k: newsletters fyi]'
    s.save_doc('learned', learn._put_block(s.get_doc('learned'), learn.PROP_START, learn.PROP_END, rule), 'reflect')
    assert learn.auto_adopt(s) == ['Newsletters from vendor.example are fyi.']
    assert 'Newsletters' in learned_cut.section(s.get_doc('learned'), learned_cut.CARE)
    s.set_memory_active(ids[0], False); learn.withdraw(s, ids[0])
    s.set_memory_active(ids[1], False); learn.withdraw(s, ids[1])
    doc = s.get_doc('learned')
    assert 'Newsletters' not in learned_cut.section(doc, learned_cut.CARE), "no longer the owner's word: back to Proposed"
    assert 'Newsletters' in learn._block(doc, learn.PROP_START, learn.PROP_END) and f'mem{ids[0]}' not in doc
    assert learn.auto_adopt(s) == [], 'auto-adopt reads only the notes still switched on'


def test_adopting_a_line_about_someone_files_it_under_your_people():
    s = MemoryStore()
    line = '- Omar Keller (omar@northwind.example) gets the audit questions [s:3 | ev: out1, task2 | seen: 2026-10-20 | k: omar audit]'
    s.save_doc('learned', learn._put_block(s.get_doc('learned'), learn.HYP_START, learn.HYP_END, line), 'reflect')
    learn.adopt(s, 'omar audit')
    assert 'Omar Keller' in learned_cut.section(s.get_doc('learned'), learned_cut.PEOPLE)


def test_the_hot_pass_is_told_never_to_count_presses():
    assert 'button' in learn.LESSON_SYSTEM and 'pr ids' not in learn.LESSON_SYSTEM
    assert 'never a count of button presses' in learn.REFLECT_SYSTEM and 'pr ids' not in learn.REFLECT_SYSTEM
