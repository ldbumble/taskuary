"""HONEST MEMORY, ONE SECTION PER READER (phase C of the Advisor and memory design, 2026-10-23).

LEARNED.md reached every prompt whole and was cut at a character count; the Advisor's press habits rode into triage; a line the owner
deleted came straight back at the next reflection; the opener counted every rebirth; and the voice lessons were learned where no drafter
reads. The owner, 2026-10-23: "why would we want button presses to do with triage" - triage reads "How you sort mail", the Advisor
"What you do next", the drafter STYLE.md's "By recipient", each within its own budget, and hand edits stick."""
from taskuary import advisor, assistantblocks, byrecipient, context, ingest, learn, learned_cut, learnedgraph, learnedlines, since
from taskuary.store import MemoryStore

SORT_LINE = '- Vendor statements from vendor.example are fyi, never a task. [s:5 | ev: mem1, mem2, mem3 | seen: 2026-10-20 | k: vendor statements]'
MOVE_LINE = ('- On asks from northwind.example, {{owner_first}} presses Send to agent (4 of 4) '
             '[s:5 | ev: pr1, pr2, pr3, pr4 | seen: 2026-10-20 | k: move todo email northwind.example]')
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
<!-- hypotheses:end -->

## Verdicts - the evidence
<!-- verdicts:start -->
- something [mem1 · sender]
<!-- verdicts:end -->
"""


def both() -> MemoryStore:
    """A store whose LEARNED.md has a sorting line and a press habit, each in its reader's section."""
    s = MemoryStore()
    doc = s.get_doc('learned').replace(learn.SORT + '\n', f'{learn.SORT}\n{SORT_LINE}\n', 1).replace(learn.NEXT + '\n', f'{learn.NEXT}\n{MOVE_LINE}\n', 1)
    s.save_doc('learned', doc, 'reflect')
    return s


def test_press_habits_never_reach_triage():
    """The ruling as a test: the triage prompt carries the sorting section and never the "What you do next" one - whatever is in it."""
    s, seen = both(), {}
    ingest.ingest_message(s, {'external_id': 'r11-1', 'channel': 'email', 'from_email': 'ap@vendor.example', 'subject': 'Statement',
                              'body': 'Your September statement is attached.'},
                          llm=lambda sys_, usr, **k: (seen.update(p=sys_ + usr), '{"intent":"fyi","why":"x"}')[1])
    assert 'Vendor statements from vendor.example are fyi' in seen['p']
    assert learn.NEXT not in seen['p'] and 'presses Send to agent' not in seen['p'] and 'pr1' not in seen['p']
    assert learned_cut.for_reader(s, 'triage').startswith(learn.SORT) and learn.NEXT not in learned_cut.for_reader(s, 'triage')


def test_each_reader_reads_its_own_section_and_nothing_else():
    s = both()
    adv = advisor._learned(s)
    assert 'presses Send to agent' in adv and 'Vendor statements' not in adv
    told, _ = assistantblocks._learned(s, {})
    assert 'Vendor statements' in told and 'presses Send to agent' not in told
    tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 'owner')
    s.add_message({'TaskId': tid, 'ExternalId': 'e1', 'Channel': 'email', 'Subject': 'export', 'FromEmail': 'erin@northwind.example',
                   'BodyText': 'The export fails.', 'Status': 'routed'})
    page = context.build(s, tid)
    assert 'Vendor statements' in page and 'presses Send to agent' not in page


def test_a_habit_the_model_put_under_sorting_goes_back_to_watching():
    """Code is the law, the prompt only asks: a sorting line resting on presses or the ledger alone is not triage's to read."""
    s = MemoryStore()
    stray = '- Alex runs every GitHub issue through an agent. [s:4 | ev: pr1, pr2, out3 | seen: 2026-10-20]'
    out = learn.settle(s, '', s.get_doc('learned').replace(learn.SORT + '\n', f'{learn.SORT}\n{stray}\n{SORT_LINE}\n', 1))
    assert 'Vendor statements' in learned_cut.section(out, learn.SORT) and 'GitHub issue' not in learned_cut.section(out, learn.SORT)
    assert 'GitHub issue' in learn._block(out, learn.HYP_START, learn.HYP_END)


def test_budget_takes_whole_lines_closest_scope_first_and_records_what_did_not_fit():
    s = MemoryStore()
    general = [f'- A general sorting habit number {i} that applies to everybody. [s:5 | ev: mem{i} | seen: 2026-10-01 | k: general {i}]'
               for i in range(40)]
    mine = '- Erin Blake at northwind.example: her exports are always a task. [s:5 | ev: mem99 | seen: 2026-10-01 | k: erin exports]'
    s.save_doc('learned', s.get_doc('learned').replace(learn.SORT + '\n', learn.SORT + '\n' + '\n'.join(general + [mine]) + '\n', 1), 'reflect')
    out = learned_cut.for_reader(s, 'triage', {'sender': 'erin@northwind.example', 'domain': 'northwind.example'}, budget=600)
    body = out.split('\n')[1:]
    assert body[0] == mine.strip(), 'the line about this sender leads'
    assert all(l in general + [mine] for l in body), 'whole lines, never a cut through one'
    over = learned_cut.over_budget(s)
    assert len(over) == 41 - len(body) and all(r == ['triage'] for r in over.values()), 'what did not fit is marked, not silently dropped'
    g = {l['key']: l for l in learnedgraph.graph(s)['lines']}                   # ...where the memory list (phase D) can say so
    assert g['erin exports']['over_budget'] == [] and g['general 39']['over_budget'] == ['triage']
    assert (g['erin exports']['reads'], g['erin exports']['standing']) == ('triage', 'in_use')


def test_the_owners_delete_is_a_tombstone_the_reflection_cannot_write_back():
    s = both()
    doc = s.get_doc('learned')
    s.save_doc('learned', doc.replace(SORT_LINE + '\n', ''), 'owner')                     # the owner removes it by hand
    assert learnedlines.row(s, 'vendor statements')['Status'] == 'forgotten'
    assert learn.reflect(s, llm=lambda *a, **k: doc)                                       # the reflection writes the old doc back
    assert 'Vendor statements' not in s.get_doc('learned'), 'a removed line stays removed'
    grown = SORT_LINE.replace('mem1, mem2, mem3', ', '.join(f'mem{i}' for i in range(1, 10)))
    assert learn.reflect(s, llm=lambda *a, **k: doc.replace(SORT_LINE, grown))           # ...until its evidence grows threefold
    assert 'Vendor statements' in learned_cut.section(s.get_doc('learned'), learn.SORT)
    assert learnedlines.row(s, 'vendor statements')['Status'] == 'in_use'
    assert [h['Action'] for h in s.learned_history('vendor statements')].count('born') <= 1


def test_the_owners_wording_sticks():
    s = both()
    doc = s.get_doc('learned')
    mine = SORT_LINE.replace('are fyi, never a task', 'are fyi - Alex reads them on Fridays')
    s.save_doc('learned', doc.replace(SORT_LINE, mine), 'owner')
    assert learn.reflect(s, llm=lambda *a, **k: doc)                                       # the model's old wording comes back...
    assert 'Alex reads them on Fridays' in s.get_doc('learned') and 'never a task' not in s.get_doc('learned')   # ...the owner's stays
    assert any(h['Action'] == 'edited' for h in s.learned_history('vendor statements'))


def test_migration_puts_each_line_with_its_reader_and_voice_with_the_drafter():
    s = MemoryStore()
    s.save_doc('learned', OLD, 'reflect')
    assert learn.migrate(s) and not learn.migrate(s), 'once'
    doc = s.get_doc('learned')
    sort, nxt = learned_cut.section(doc, learn.SORT), learned_cut.section(doc, learn.NEXT)
    assert 'owns the payroll import' in sort and 'Vendor statements' in sort and 'My own line about Payworth' in sort
    assert '### Role & responsibilities' in sort and '### What becomes a task' in sort and 'learned yet' not in sort
    assert 'presses Send to agent' in nxt and 'presses Send to agent' not in sort
    assert 'Voice & style' not in doc and 'skip the greeting' not in doc
    assert learn.WATCH_HEADER in doc and 'Gail Moreno' in learn._block(doc, learn.HYP_START, learn.HYP_END)
    assert learn.PROP_START in doc and learn.VERD_START in doc and 'Taskuary writes this document itself, from what you do' in doc
    assert ('everyone', 'Replies to Erin Blake skip the greeting.') in byrecipient.lines(s)
    assert learnedlines.row(s, 'replies erin blake skip greeting')['Reader'] == 'drafter'
    assert since.learned(s)['line'] == '', 'the move itself is not this week\'s learning'
    assert learnedlines.row(s, 'vendor statements')['InUseAt'] == '-', 'in use since before there were records'


def test_a_switched_off_note_withdraws_what_it_fed():
    s = MemoryStore()
    ids = [s.add_memory({'Scope': 'sender', 'ScopeKey': 'news@vendor.example', 'Note': f'2026-10-0{i}: "Newsletter" - NOT A TASK', 'Source': 'verdict',
                         'Active': 1, 'CreatedBy': 'owner'}) for i in (1, 2, 3)]
    rule = f'- Newsletters from vendor.example are fyi. [s:4 | ev: {", ".join(f"mem{i}" for i in ids)} | seen: 2026-10-03 | k: newsletters fyi]'
    s.save_doc('learned', learn._put_block(s.get_doc('learned'), learn.PROP_START, learn.PROP_END, rule), 'reflect')
    assert learn.auto_adopt(s) == ['Newsletters from vendor.example are fyi.']
    assert 'Newsletters' in learned_cut.section(s.get_doc('learned'), learn.SORT)
    s.set_memory_active(ids[0], False); learn.withdraw(s, ids[0])
    s.set_memory_active(ids[1], False); learn.withdraw(s, ids[1])
    doc = s.get_doc('learned')
    assert 'Newsletters' not in learned_cut.section(doc, learn.SORT), 'no longer the owner\'s word: back to Proposed'
    assert 'Newsletters' in learn._block(doc, learn.PROP_START, learn.PROP_END) and f'mem{ids[0]}' not in doc
    assert learn.auto_adopt(s) == [], 'auto-adopt reads only the notes still switched on'


def test_the_hot_pass_never_rewrites_a_press_line():
    s = MemoryStore()
    press = '- On asks from northwind.example, {{owner_first}} presses Reply (2 of 2) [s:3 | ev: pr1, pr2 | seen: 2026-10-20 | k: move todo email northwind.example]'
    s.save_doc('learned', learn._put_block(s.get_doc('learned'), learn.HYP_START, learn.HYP_END, press), 'moves')
    sent = {}
    def llm(sys_, usr, **k):
        sent['u'] = usr
        return '- {{owner_first}} owns the payroll import. [s:2 | ev: mem9 | seen: 2026-10-21]\n- presses Reply (9 of 9) [s:9 | ev: pr1 | seen: x]'
    learn.learn_from(s, 'mem9: owner said not ours', llm=llm)
    hyp = learn._block(s.get_doc('learned'), learn.HYP_START, learn.HYP_END)
    assert 'pr1' not in sent['u'] and press in hyp and '9 of 9' not in hyp and 'owns the payroll import' in hyp
