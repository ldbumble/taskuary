"""THE FIVE RULINGS FROM THE LIVE AUDIT (2026-10-28): the lit button agreed with what the owner then did under half the time. Send stays lit
over a waiting draft, a finished stopped agent is put down, an override says its reason, the Advisor reads How you work first and in full,
and a line that cites a memory without saying it is not shown. Invented Northwind people only (CLAUDE.md)."""
from taskuary import advisor, funnel, learned_cut as lc, rulebook, workerstate
from taskuary.store import MemoryStore
from taskuary.testing import Factory
from tests.test_advisor_memory_reason import w, plant, ask, judged       # noqa: F401 - w is the fixture

V = lambda *vs: [{'verb': v, 'label': v} for v in vs]
def _d(verb, kind, state='draft_ready', line='x'): return {'key': 'task:1', 'state': state, 'verb': verb, 'line': line, 'by': 'model', 'evidence': [], 'kind': kind}
RULE = {'verb': 'approve', 'line': '', 'evidence': []}


# ── 1. Send stays lit while a draft waits ─────────────────────────────────────────────────────────────────────────────────────────────
def test_reply_over_a_waiting_draft_lights_its_send_for_any_reason_but_a_caution():
    s = MemoryStore()
    for kind in ('late', 'memory', 'handoff', 'other', 'same_ask'):
        d = advisor.checked(s, {'key': 'task:1'}, V('approve', 'reply', 'redraft'), _d('reply', kind, line='Erin wants it today.'), RULE)
        assert (d['verb'], d['line']) == ('approve', 'Erin wants it today.'), (kind, d)
    d = advisor.checked(s, {'key': 'task:1'}, V('approve', 'reply'), _d('reply', 'draft_caution', line='The draft promises Friday.'), RULE)
    assert (d['verb'], d.get('checked')) == ('reply', None), 'a caution about the draft itself is the one reason Reply stands'
    assert advisor.checked(s, {'key': 'task:1'}, V('reply'), _d('reply', 'memory', 'asked'), RULE)['verb'] == 'reply', 'no draft: Reply stands'


def test_the_models_reply_on_a_thread_the_owner_answered_lights_mark_done():
    """The owner, 2026-10-28: a sent reply's row lit Reply - their reply went after the sender's newest mail, so Mark done, whatever the reason."""
    rule = {'verb': 'close', 'line': '', 'evidence': []}
    for kind in ('late', 'memory', 'other'):
        d = advisor.checked(MemoryStore(), {'key': 'task:1'}, V('reply', 'close'), _d('reply', kind, 'answered', line='Erin may want more.'), rule)
        assert (d['verb'], d['line']) == ('close', ''), (kind, d)


def drafted(s, who='erin', title='Offsite agenda'):
    t = ask(s, who, title, 'Can you check the offsite agenda before Thursday?')
    mid = s.list_messages(t)[-1]['MessageId']
    Factory(s).review(t, mid, draft='Checked it - Thursday works.'); funnel.invalidate()
    return t


def test_the_decision_over_a_draft_keeps_send_lit(w):
    s, _ = w
    t = drafted(s)
    d, _ = judged(s, t, {'verb': 'reply', 'line': 'Erin prefers a call on agendas.', 'evidence': [], 'kind': 'other'})
    assert (d['state'], d['verb']) == ('draft_ready', 'approve'), d
    s._exec('DELETE FROM advice WHERE TargetId=?', (t,))
    d, _ = judged(s, t, {'verb': 'reply', 'line': 'The draft promises Thursday; nothing set it.', 'evidence': [], 'kind': 'draft_caution'})
    # ...and a caution carries its fix (advisor.fix_of, 2026-10-28): Redraft, the line as its note - not Reply
    assert (d['verb'], d['line'], d['fix']['note']) == ('redraft', 'The draft promises Thursday; nothing set it.', d['line']), d


# ── 3. no silent override ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_silent_reply_over_send_lights_nothing(w):
    """...and NO DEFAULT VERB (the owner, 2026-10-28): with no reason said either way, the draft's Send is not lit for it."""
    s, _ = w
    t = drafted(s)
    d, _ = judged(s, t, {'verb': 'reply', 'line': '', 'evidence': [], 'kind': 'draft_caution'})
    assert (d['verb'], d['by'], d['line']) == (None, 'rule', ''), d


def test_a_silent_override_lights_nothing_and_one_with_its_reason_stands(w):
    s, _ = w
    t = ask(s, 'erin', 'Offsite agenda', 'Can you check the offsite agenda before Thursday?')
    offered = {v['verb'] for v in advisor.offered(s, advisor._item(s, 'task', t, f'task:{t}'))}
    assert {'defer', 'close'} <= offered, offered
    d, _ = judged(s, t, {'verb': 'defer', 'line': '', 'evidence': []})
    assert (d['verb'], d['by']) == (None, 'rule'), d
    s._exec('DELETE FROM advice WHERE TargetId=?', (t,))
    d, _ = judged(s, t, {'verb': 'defer', 'line': 'Erin is away until Monday.', 'evidence': []})
    assert (d['verb'], d['by'], d['line']) == ('defer', 'model', 'Erin is away until Monday.'), d
    s._exec('DELETE FROM advice WHERE TargetId=?', (t,))
    d, _ = judged(s, t, {'verb': 'close', 'line': '', 'evidence': []})
    assert (d['verb'], d['by']) == (None, 'rule'), 'Mark done is never lit without its reason (the owner, 2026-10-28)'


# ── 2. Mark done for a finished stopped agent ─────────────────────────────────────────────────────────────────────────────────────────
def _stopped(s, *events, title='Reconcile the vendor export'):
    t = s.create_task({'Title': title, 'Status': 'in_progress', 'Kind': 'general'}, 'owner')
    for kind, text in events: workerstate.record(s, t, 'r1', kind, text=text)
    return t, {'key': f'agent:{t}', 'kind': 'agent', 'lane': 'stopped', 'tid': t, 'title': title}


def test_a_stopped_agent_that_left_a_result_lights_mark_done():
    s = MemoryStore()
    t, it = _stopped(s, ('working', 'go'), ('finished', 'The export reconciles; two rows were fixed.'), ('stopped', ''))
    assert rulebook.left_result(s, t)
    r = rulebook.decide(s, it, V('continue', 'close'))
    assert (r['state'], r['verb']) == ('stopped_done', 'close') and r['line'].startswith('Finished ') and r['line'].endswith('; nothing since.'), r
    assert rulebook.decide(s, it, V('continue'))['verb'] == 'next', 'no Mark done on the row: nothing of the rule is lit - never Continue'


def test_a_stopped_agent_mid_work_lights_nothing_of_the_rules():
    """A plain stop is no reason (the measure, 2026-10-28: Continue agreed 5 times of 21) - the finish check lights Continue with this."""
    s = MemoryStore()
    t, it = _stopped(s, ('working', 'go'), ('finished', 'Half done.'), ('working', 'and the rest'), ('stopped', ''))
    assert not rulebook.left_result(s, t), 'a finish a later prompt took up is not the result'
    assert (r := rulebook.decide(s, it, V('continue', 'close')))['state'] == 'stopped' and r['verb'] is None, r


def test_a_done_note_or_a_runs_result_is_a_finished_run():
    s = MemoryStore()
    t, it = _stopped(s, ('working', 'go'), ('stopped', ''))
    s.add_note({'TaskId': t, 'Agent': 'general', 'Kind': 'ready', 'Body': 'ready to push'})
    assert rulebook.decide(s, it, V('continue', 'close'))['state'] == 'stopped'
    s.add_note({'TaskId': t, 'Agent': 'general', 'Kind': 'done', 'Body': 'reconciled'})
    assert rulebook.decide(s, it, V('continue', 'close'))['state'] == 'stopped_done'
    t2, it2 = _stopped(s, ('working', 'go'), ('stopped', ''), title='Vendor W-9 lookup')
    rid = s.start_run(t2, 'general', 'look it up', 'owner'); s.update_run(rid, {'Status': 'stopped', 'Result': 'The W-9 is on file.'}, finished=True)
    assert rulebook.decide(s, it2, V('continue', 'close'))['verb'] == 'close'


def test_the_prompt_says_whether_a_stopped_run_finished():
    assert 'stopped mid-work' in advisor.SYSTEM and 'a done note' in advisor.SYSTEM


# ── 4. the Advisor reads How you work first, and more of it ───────────────────────────────────────────────────────────────────────────
def test_how_you_work_arrives_however_many_care_lines_there_are():
    s = MemoryStore()
    assert lc.BUDGET['advisor'] >= 4000 and advisor.PROMPT_CAP >= 9000 + lc.BUDGET['advisor'] - 2000
    care = '\n'.join(f'- A vendor statement from supplier {i} is a task when it shows a balance past thirty days' for i in range(80))
    work = '- You close the books on the third working day and answer vendor asks after that'
    s.save_doc('learned', f"{lc.SECTIONS['care']}\n{care}\n\n{lc.SECTIONS['work']}\n{work}\n", 'owner')
    got = lc.for_reader(s, 'advisor', {'domain': 'vendor.example'})
    assert work in got and got.index(lc.SECTIONS['work']) < got.index(lc.SECTIONS['care']), got[:300]
    assert len(got) > 2000, 'the budget is no longer spent at 2000'
    # ...every other reader keeps what it cares about first
    assert work not in lc.for_reader(s, 'assistant', {'domain': 'vendor.example'})


# ── 5. a line that cites a memory without saying it is not shown ──────────────────────────────────────────────────────────────────────
BUMPS = '- Dependency bump notices from the build robot are never yours to act on [s:5 | ev: out21, out22 | seen: 2026-10-20 | k: robot bumps]'


def test_a_line_citing_a_memory_it_does_not_say_is_dropped_and_the_button_kept(w):
    s, _ = w
    plant(s, 'care', BUMPS)
    t = ask(s, 'erin', 'GitHub notice: dependency bump', 'A new dependency bump was opened on northwind/ledger.')
    cite = lc.cite_of('robot bumps')
    it = advisor._item(s, 'task', t, f'task:{t}')
    # ...whether the line says it is the model's own field (memory_says), never the line's words held against the memory's
    assert advisor.hollow(s, it, ('task', t), '', [cite])
    assert advisor.hollow(s, it, ('task', t), '   ', [cite])
    assert not advisor.hollow(s, it, ('task', t), 'Robot bumps are never yours to act on', [cite])
    assert not advisor.hollow(s, it, ('task', t), '', []), 'citing no memory, the check does not apply'
    assert not advisor.hollow(s, it, ('task', t), '', ['out999']), 'an outcome id is no memory line'
    d, _ = judged(s, t, {'verb': 'close', 'line': 'GitHub notice; no ask here.', 'memory_says': '', 'evidence': [cite]})
    assert (d['verb'], d['line']) == (None, ''), d
    s._exec('DELETE FROM advice WHERE TargetId=?', (t,))
    # ...a line in other words than the memory's stands when the model says what the memory says
    d, _ = judged(s, t, {'verb': 'close', 'line': 'Nothing here is yours to act on.', 'evidence': [cite],
                         'memory_says': 'Dependency bump notices from the build robot are never yours to act on'})
    assert (d['verb'], d['line']) == ('close', 'Nothing here is yours to act on.'), d
    assert advisor.rows(s, 'task', t)[0]['MemorySays'].startswith('Dependency bump notices'), 'stored with the row'


def test_the_prompt_asks_the_line_to_say_the_remembered_fact():
    assert 'SAYS what that memory is' in advisor.SYSTEM
    assert 'memory_says' in advisor.SYSTEM and 'memory_says' in advisor.WANT['properties']
