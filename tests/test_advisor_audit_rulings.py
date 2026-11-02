"""THE FIVE RULINGS FROM THE LIVE AUDIT (2026-10-28), AS EVIDENCE NOW (the owner, 2026-11-02: "never ever use hard coded rules"): the swaps
that put Send over the model's Reply and Mark done over a Reply on an answered thread went - the model reads the draft and the sent reply
and decides; a finished stopped agent is a fact the model reads; the Advisor reads How you work first and in full; and a line that cites a
memory without saying it is not shown. Invented Northwind people only (CLAUDE.md)."""
from taskuary import advisor, funnel, learned_cut as lc, rulebook, workerstate
from taskuary.store import MemoryStore
from taskuary.testing import Factory
from tests.test_advisor_memory_reason import w, plant, ask, judged       # noqa: F401 - w is the fixture

V = lambda *vs: [{'verb': v, 'label': v} for v in vs]
def _d(verb, kind, state='draft_ready', line='x'): return {'key': 'task:1', 'state': state, 'verb': verb, 'line': line, 'by': 'model', 'evidence': [], 'kind': kind}
# ── 1. the model's Reply over a waiting draft stands - code no longer swaps in Send ─────────────────────────────────────────────────────
def test_the_models_reply_over_a_waiting_draft_stands_and_a_caution_never_lights_send():
    s = MemoryStore()
    for kind in ('late', 'memory', 'handoff', 'other', 'same_ask', 'draft_caution'):
        d = advisor.checked(s, {'key': 'task:1'}, V('approve', 'reply', 'redraft'), _d('reply', kind, line='Erin wants it today.'))
        assert (d['verb'], d['line'], d.get('checked')) == ('reply', 'Erin wants it today.', None), (kind, d)
    # ...the one check left over a draft: Send on a reason that says the draft is not ready is refused - to nothing, its line kept for the fix
    d = advisor.checked(s, {'key': 'task:1'}, V('approve', 'reply'), _d('approve', 'draft_caution', line='The draft promises Friday.'))
    assert (d['verb'], d['line'], bool(d.get('checked'))) == (None, 'The draft promises Friday.', True), d


def test_the_models_reply_on_a_thread_the_owner_answered_stands():
    """The owner, 2026-10-28, wanted Mark done there; the model reads A REPLY WAS ALREADY SENT itself now - code swaps nothing in."""
    for kind in ('late', 'memory', 'other'):
        d = advisor.checked(MemoryStore(), {'key': 'task:1'}, V('reply', 'close'), _d('reply', kind, 'answered', line='Erin may want more.'))
        assert (d['verb'], d['line']) == ('reply', 'Erin may want more.'), (kind, d)


def drafted(s, who='erin', title='Offsite agenda'):
    t = ask(s, who, title, 'Can you check the offsite agenda before Thursday?')
    mid = s.list_messages(t)[-1]['MessageId']
    Factory(s).review(t, mid, draft='Checked it - Thursday works.'); funnel.invalidate()
    return t


def test_the_decision_over_a_draft_is_the_models(w):
    s, _ = w
    t = drafted(s)
    d, _ = judged(s, t, {'verb': 'reply', 'line': 'Erin prefers a call on agendas.', 'evidence': [], 'kind': 'other'})
    assert (d['state'], d['verb'], d['by']) == ('draft_ready', 'reply', 'model'), d
    s._exec('DELETE FROM advice WHERE TargetId=?', (t,))
    d, _ = judged(s, t, {'verb': 'reply', 'line': 'The draft promises Thursday; nothing set it.', 'evidence': [], 'kind': 'draft_caution'})
    # ...and a caution carries its fix (advisor.fix_of, 2026-10-28): Redraft, the line as its note - not Reply
    assert (d['verb'], d['line'], d['fix']['note']) == ('redraft', 'The draft promises Thursday; nothing set it.', d['line']), d


# ── 3. the model's verb stands, its line or not: no rule to override ─────────────────────────────────────────────────────────────────
def test_a_silent_reply_over_send_is_the_models_light(w):
    """A caution with no line carries no fix (fix_of needs the line): the model's Reply is lit as it said it."""
    s, _ = w
    t = drafted(s)
    d, _ = judged(s, t, {'verb': 'reply', 'line': '', 'evidence': [], 'kind': 'draft_caution'})
    assert (d['verb'], d['by'], d['line']) == ('reply', 'model', ''), d


def test_the_models_verb_stands_with_or_without_its_reason(w):
    s, _ = w
    t = ask(s, 'erin', 'Offsite agenda', 'Can you check the offsite agenda before Thursday?')
    offered = {v['verb'] for v in advisor.offered(s, advisor._item(s, 'task', t, f'task:{t}'))}
    assert {'defer', 'close'} <= offered, offered
    d, _ = judged(s, t, {'verb': 'defer', 'line': '', 'evidence': []})
    assert (d['verb'], d['by']) == ('defer', 'model'), d
    s._exec('DELETE FROM advice WHERE TargetId=?', (t,))
    d, _ = judged(s, t, {'verb': 'defer', 'line': 'Erin is away until Monday.', 'evidence': []})
    assert (d['verb'], d['by'], d['line']) == ('defer', 'model', 'Erin is away until Monday.'), d
    s._exec('DELETE FROM advice WHERE TargetId=?', (t,))
    d, _ = judged(s, t, {'verb': 'close', 'line': '', 'evidence': []})
    assert (d['verb'], d['by']) == ('close', 'model'), 'the model judged the plain move: its button does the talking'


# ── 2. a finished stopped agent, as the fact the model reads ─────────────────────────────────────────────────────────────────────────────────────────
def _stopped(s, *events, title='Reconcile the vendor export'):
    t = s.create_task({'Title': title, 'Status': 'in_progress', 'Kind': 'general'}, 'owner')
    for kind, text in events: workerstate.record(s, t, 'r1', kind, text=text)
    return t, {'key': f'agent:{t}', 'kind': 'agent', 'lane': 'stopped', 'tid': t, 'title': title}


def test_a_stopped_agent_that_left_a_result_is_named_stopped_done():
    s = MemoryStore()
    t, it = _stopped(s, ('working', 'go'), ('finished', 'The export reconciles; two rows were fixed.'), ('stopped', ''))
    assert rulebook.left_result(s, t)
    r = rulebook.facts(s, it, V('continue', 'close'))
    assert r['state'] == 'stopped_done' and r['line'].startswith('Finished ') and r['line'].endswith('; nothing since.'), r
    assert 'verb' not in r, 'a fact for the model, never a light'


def test_a_stopped_agent_mid_work_is_named_stopped():
    """A plain stop is no reason (the measure, 2026-10-28: Continue agreed 5 times of 21) - the finish check lights Continue with this."""
    s = MemoryStore()
    t, it = _stopped(s, ('working', 'go'), ('finished', 'Half done.'), ('working', 'and the rest'), ('stopped', ''))
    assert not rulebook.left_result(s, t), 'a finish a later prompt took up is not the result'
    assert (r := rulebook.facts(s, it, V('continue', 'close')))['state'] == 'stopped' and r['line'] == '', r


def test_a_done_note_or_a_runs_result_is_a_finished_run():
    s = MemoryStore()
    t, it = _stopped(s, ('working', 'go'), ('stopped', ''))
    s.add_note({'TaskId': t, 'Agent': 'general', 'Kind': 'ready', 'Body': 'ready to push'})
    assert rulebook.facts(s, it, V('continue', 'close'))['state'] == 'stopped'
    s.add_note({'TaskId': t, 'Agent': 'general', 'Kind': 'done', 'Body': 'reconciled'})
    assert rulebook.facts(s, it, V('continue', 'close'))['state'] == 'stopped_done'
    t2, it2 = _stopped(s, ('working', 'go'), ('stopped', ''), title='Vendor W-9 lookup')
    rid = s.start_run(t2, 'general', 'look it up', 'owner'); s.update_run(rid, {'Status': 'stopped', 'Result': 'The W-9 is on file.'}, finished=True)
    assert rulebook.facts(s, it2, V('continue', 'close'))['state'] == 'stopped_done'


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
    assert (d['verb'], d['line']) == ('close', ''), 'the hollow line goes; the model\'s button stays'
    s._exec('DELETE FROM advice WHERE TargetId=?', (t,))
    # ...a line in other words than the memory's stands when the model says what the memory says
    d, _ = judged(s, t, {'verb': 'close', 'line': 'Nothing here is yours to act on.', 'evidence': [cite],
                         'memory_says': 'Dependency bump notices from the build robot are never yours to act on'})
    assert (d['verb'], d['line']) == ('close', 'Nothing here is yours to act on.'), d
    assert advisor.rows(s, 'task', t)[0]['MemorySays'].startswith('Dependency bump notices'), 'stored with the row'


def test_the_prompt_asks_the_line_to_say_the_remembered_fact():
    assert 'SAYS what that memory is' in advisor.SYSTEM
    assert 'memory_says' in advisor.SYSTEM and 'memory_says' in advisor.WANT['properties']
