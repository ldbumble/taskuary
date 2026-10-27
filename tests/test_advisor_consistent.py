"""ONE DECISION PER ITEM, PRESSABLE AND AGREEING WITH ITS OWN WORDS (the Advisor audit and its independent judge, 2026-10-26). The judge found:
both twins of a duplicate pair lit "Remove - not a task", each naming the other; a wait "2 days late" by its header lit Remind me; a late
line counted from mail said "within the hour" while LEARNED.md said "the same day", and Wrong on that line changed nothing on the task; a
draft caution stood beside a lit Send; a late line on a drafted task lit Reply over the draft's own Send; and a failed run lit a Try again
nobody could press. Each is pinned here on its shape, with invented Northwind people (CLAUDE.md)."""
import json
from datetime import date, datetime, timedelta
from unittest import mock
import pytest
from taskuary import advisor, funnel, learn, learned_cut as lc, memoryedit, rulebook, terminal, usual
from taskuary.store import MemoryStore
from taskuary.testing import Factory

ERIN, MARCUS, RAY = ('Erin Blake', 'erin@northwind.example'), ('Marcus Reed', 'marcus@northwind.example'), ('Ray Colton', 'ray@northwind.example')
def at(**k): return (datetime.now() - timedelta(**k)).strftime('%Y-%m-%d %H:%M:%S')
def V(*vs): return [{'verb': v, 'label': v} for v in vs]


@pytest.fixture
def s(monkeypatch):
    s = MemoryStore()
    for k, v in (('calendar_enabled', '0'), ('owner_email', 'alex@northwind.example'), ('owner_name', 'Alex Doyle')): s.set_setting(k, v, 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    monkeypatch.setattr(advisor, 'notice', lambda *a, **k: None)
    funnel.invalidate(); yield s; funnel.invalidate()


def ask(s, title, who, hours, cid=None):
    f = Factory(s)
    t = f.task(title=title, kind='task')
    m = f.message(task_id=t, subject=title, body='Can you?', from_name=who[0], from_email=who[1], sent_at=at(hours=hours), conversation_id=cid or f'email:{title}')
    funnel.invalidate()
    return t, m


# ── 1. a duplicate pair: one survivor, decided once ───────────────────────────────────────────────────────────────────────────────────
def test_a_duplicate_pair_has_one_survivor_and_only_the_other_is_folded_into_it(s):
    first, _ = ask(s, 'Spendly cards for the new site', MARCUS, 7, cid='email:spendly')
    second, _ = ask(s, 'RE: Spendly cards', MARCUS, 2, cid='email:spendly')
    a, b = (advisor.decide(s, f'task:{t}', preread=False) for t in (first, second))
    assert [d['state'] for d in (a, b)].count('duplicate') == 1, (a, b)
    assert a['state'] != 'duplicate' and a['verb'] not in ('remove', 'split'), 'the one asked first keeps its own move'
    assert b['state'] == 'duplicate' and b['line'] == 'Same ask as TQ-0001 - fold it into that one.', 'the other names the one that stays'
    # ...decided once for the pair and kept: a new message on the survivor does not flip it
    assert json.loads(s._one("SELECT Json FROM advice_decision WHERE Key=?", (f'pair:{first}:{second}',))['Json'])['survivor'] == first
    Factory(s).message(task_id=first, subject='RE: Spendly cards', body='And a third card?', from_name=MARCUS[0], from_email=MARCUS[1],
                       sent_at=at(minutes=5), conversation_id='email:spendly')
    funnel.invalidate()
    assert rulebook.survivor(s, second, first) == first
    # ...and every surface reads the same kept decision
    for t, d in ((first, a), (second, b)):
        kept = json.loads(s._one("SELECT Json FROM advice_decision WHERE Key=?", (f'task:{t}',))['Json'])
        assert (kept['verb'], kept['state']) == (advisor.decide(s, f'task:{t}', preread=False)['verb'], d['state'])


def test_a_model_folding_the_survivor_into_its_twin_is_refused(s):
    first, _ = ask(s, 'Spendly cards', MARCUS, 7, cid='email:spendly')
    ask(s, 'RE: Spendly cards', MARCUS, 2, cid='email:spendly')
    it = {'key': f'task:{first}', 'tid': first, 'kind': 'asked', 'lane': 'asked'}
    d = advisor.checked(s, it, V('reply', 'remove'), {'key': it['key'], 'state': 'asked', 'verb': 'remove', 'line': 'Same ask as TQ-0002.', 'by': 'model',
                        'evidence': [], 'kind': 'same_ask'}, {'verb': 'reply', 'line': '', 'evidence': []})
    assert (d['verb'], d['by'], d['line']) == ('reply', 'rule', '') and 'survivor' in d['checked']


# ── 2. late on a wait: one pick, one clock ────────────────────────────────────────────────────────────────────────────────────────────
def test_a_wait_past_its_due_day_is_chase_counted_like_the_header_and_its_goal(s):
    g = s.create_task({'Title': 'Move payroll', 'Status': 'open', 'DoneWhen': 'payroll runs on the new system'}, 'owner')
    s.set_task_checklist(g, ['schema sign-off'], 'owner')
    k = s.create_task({'Title': 'Ray: schema sign-off', 'Status': 'waiting', 'Assignee': f'person:{RAY[1]}', 'ParentId': g,
                       'DueAt': (date.today() - timedelta(days=2)).isoformat()}, 'owner')
    s.link_step(g, s.checklist_id('schema sign-off'), k, 'owner')
    Factory(s).message(task_id=k, subject='Schema', body='Can you sign the schema off?', direction='out', sent_at=at(hours=20))
    Factory(s).message(task_id=k, subject='RE: Schema', body='Looking.', from_name=RAY[0], from_email=RAY[1], sent_at=at(hours=19))
    step = rulebook.decide(s, {'key': f'task:{k}', 'tid': k, 'lane': 'theirs', 'kind': 'task'}, V('defer', 'chase'))
    goal = rulebook.decide(s, {'key': f'task:{g}', 'tid': g, 'lane': 'yours', 'kind': 'goal_slipped'}, V('defer', 'chase'))
    assert (step['state'], step['verb']) == ('waiting_overdue', 'chase'), 'not Remind me'
    assert step['line'].startswith('Ray') and step['line'].endswith(': 2 days late.'), 'the days past due, not since the ask'
    assert goal['verb'] == 'chase' and goal['line'] == "Ray's schema sign-off: 2 days late.", 'the goal and its step say one count'
    assert rulebook.adds(s, {'key': f'task:{k}', 'tid': k, 'lane': 'theirs', 'kind': 'task'}) == ['chase'], 'Chase is on the row it is lit on'


# ── 3. the usual is ONE line, and the owner's hand on it reaches the task ─────────────────────────────────────────────────────────────
def _erins_habit(s):
    f = Factory(s)
    for n in range(3):
        old = f.task(title=f'Erin: vendor form {n}', kind='task', status='done')
        f.message(task_id=old, subject=f'Form {n}', body='Sign this?', from_name=ERIN[0], from_email=ERIN[1], sent_at=at(days=10 + n), conversation_id=f'email:old{n}')
        f.message(task_id=old, subject=f'RE: Form {n}', body='Signed.', direction='out', sent_at=at(days=10 + n, minutes=-20), conversation_id=f'email:old{n}')


def test_the_late_line_reads_the_learned_line_and_wrong_on_it_takes_the_line_off_the_task(s):
    _erins_habit(s)
    t, _ = ask(s, 'Trainly renewal', ERIN, 5)
    assert advisor.decide(s, f'task:{t}', preread=False)['state'] == 'asked', 'the count alone says no usual'
    s.save_doc('learned', learn.answer_lines(s, s.get_doc('learned') or ''), 'reflect')
    line = usual.answer_line(s, ERIN[1])
    assert line['text'] == 'You answer Erin Blake (erin@northwind.example) within the hour'
    d = advisor.status(s, f'task:{t}')
    assert (d['state'], d['line']) == ('asked_late', 'You usually answer Erin within the hour; this is 5h.')
    memory = [r for r in d['rests'] if r['kind'] == 'memory']
    assert memory == [{'id': line['cite'], 'kind': 'memory', 'key': line['key'], 'own': False, 'section': 'work', 'label': line['text']}], 'Why? quotes the one line'
    assert advisor.resting_on(s, [line['cite']]) == [f'task:{t}']
    with mock.patch.object(advisor, '_emit') as emit:
        memoryedit.mark(s, line['key'], 'wrong')
    emit.assert_called_with(f'task:{t}', 'task', t)
    assert advisor.decide(s, f'task:{t}', preread=False)['line'] == '', 'Wrong on the line: the task says it no more'
    s.save_doc('learned', learn.answer_lines(s, s.get_doc('learned') or ''), 'reflect')
    assert usual.answer_line(s, ERIN[1]) is None, '...and the count does not write it back'


def test_the_owners_own_words_about_the_person_are_the_usual(s):
    _erins_habit(s)
    t, _ = ask(s, 'Trainly renewal', ERIN, 5)
    s.save_doc('learned', learn.answer_lines(s, s.get_doc('learned') or ''), 'reflect')
    doc = s.get_doc('learned')
    s.save_doc('learned', learn._under(doc, lc.SECTIONS['people'], '- You answer Erin Blake (erin@northwind.example) the same day'), 'owner')
    assert usual.answer_line(s, ERIN[1])['text'].endswith('the same day')
    assert advisor.decide(s, f'task:{t}', preread=False)['state'] == 'asked', 'by the line she is answered the same day: 5h is not late'


def test_a_model_answer_resting_on_a_forgotten_memory_line_stands_no_more(s):
    t, _ = ask(s, 'Offsite agenda', ERIN, 30)
    raw = '- Erin Blake (erin@northwind.example) is your manager [s:5 | ev: out41, out57, rv12 | seen: 2026-10-20 | k: erin manager]'
    s.save_doc('learned', learn._under(s.get_doc('learned') or '', lc.SECTIONS['people'], raw), 'reflect')
    assert not advisor.withdrawn(s, [lc.cite_of('erin manager')])
    s.save_doc('learned', s.get_doc('learned').replace(raw + '\n', ''), 'owner')
    assert advisor.withdrawn(s, [lc.cite_of('erin manager')]) and not advisor.withdrawn(s, ['msg3'])


# ── 4. the lit button is pressable and agrees with its reason ─────────────────────────────────────────────────────────────────────────
def _d(verb, kind, state='asked', line='x'):
    return {'key': 'task:1', 'state': state, 'verb': verb, 'line': line, 'by': 'model', 'evidence': [], 'kind': kind}


def test_a_caution_about_the_draft_never_lights_send(s):
    d = advisor.checked(s, {'key': 'task:1'}, V('approve', 'redraft'), _d('approve', 'draft_caution', 'draft_ready',
                        'The draft promises Friday; nothing backs it.'), {'verb': 'approve', 'line': '', 'evidence': []})
    assert (d['verb'], d['line']) == ('redraft', 'The draft promises Friday; nothing backs it.'), 'Redraft, with the caution as its reason'
    d = advisor.checked(s, {'key': 'task:1'}, V('approve'), _d('approve', 'draft_caution', 'draft_ready'), {'verb': 'approve', 'line': '', 'evidence': []})
    assert d['verb'] == 'next', 'never Send - nothing else to light, so Next'


def test_late_on_a_drafted_task_lights_the_drafts_send(s):
    d = advisor.checked(s, {'key': 'task:1'}, V('approve', 'reply', 'redraft'), _d('reply', 'late', 'asked_late', 'You usually answer Erin within the hour; this is 5h.'),
                        {'verb': 'reply', 'line': '', 'evidence': []})
    assert (d['verb'], d['line'], d['checked']) == ('approve', 'You usually answer Erin within the hour; this is 5h.', 'late on a drafted task: the draft is the answer')
    # ...with no draft, Reply stands
    assert advisor.checked(s, {'key': 'task:1'}, V('reply'), _d('reply', 'late'), {'verb': 'reply', 'line': '', 'evidence': []})['verb'] == 'reply'


def test_a_verb_the_page_greys_is_never_lit_and_the_next_sensible_one_is(s, monkeypatch):
    advisor.AGENT_CHECK = True
    try:
        it = {'key': 'task:1', 'tid': 1}
        rule = {'verb': 'continue', 'line': 'Failed: the run stopped', 'evidence': []}
        d = advisor.checked(s, it, V('continue', 'new_task'), _d('continue', 'failure', 'failed_cause', 'Failed: the run stopped') | {'by': 'rule'}, rule)
        assert d['verb'] == 'new_task' and d['line'] == 'Failed: the run stopped' and d['checked'].startswith('continue: no AI'), d
        assert advisor.pressable(s, it, 'continue', V('continue')) == 'no AI is connected'
        assert advisor.pressable(s, it, 'chase', V('reply')) == 'not on the row'
        # ...an AI and a brain to run on: Try again is pressable, and stands
        from taskuary import capabilities, general
        monkeypatch.setattr(capabilities, 'has_ai', lambda st: True)
        monkeypatch.setattr(general, 'provider_options', lambda st: [{'type': 'anthropic', 'pick': 'connector:1'}])
        assert advisor.checked(s, it, V('continue', 'new_task'), _d('continue', 'failure', 'failed_cause') | {'by': 'rule'}, rule)['verb'] == 'continue'
    finally: advisor.AGENT_CHECK = False


def test_the_model_states_its_kind_and_it_is_kept(s):
    t, _ = ask(s, 'Vendor form', ERIN, 30)
    rev = advisor.revision(s, 'task', t)
    brain = lambda system, user, **kw: json.dumps({'verb': 'reply', 'line': 'She asked yesterday.', 'evidence': [], 'kind': 'late'})
    advisor.judge(s, advisor.SHOWN, 'task', t, rev, tier=2, llm=brain, key=f'task:{t}')
    assert advisor.rows(s, 'task', t)[0]['Kind'] == 'late'
    assert '"kind"' in advisor.SYSTEM and 'draft_caution' in advisor.SYSTEM


def test_the_learned_page_says_a_kept_line_is_kept(s):
    raw = '- Ray Colton (ray@northwind.example) runs payroll [s:4 | ev: task1 | seen: 2026-10-20 | k: payroll ray colton]'
    s.save_doc('learned', learn._under(s.get_doc('learned') or '', lc.SECTIONS['people'], raw), 'reflect')
    from taskuary import learnedgraph
    line = lambda: next(l for l in learnedgraph.graph(s)['lines'] if l['key'] == 'payroll ray colton')
    assert not line()['kept']
    memoryedit.mark(s, 'payroll ray colton', 'keep')
    assert line()['kept']
