"""THE OWNER'S HAND ON THE MEMORY (slices 6 and 7 of the memory redesign, 2026-10-25): Keep, Wrong and Forget from Settings (What changed
and Visualize), and a fact said or closed from the Assistant. A Forget is a tombstone the next reflection does not write back; Wrong is
for what Taskuary learned, never for the owner's own line; Keep makes a line theirs; all of it works with no AI. Invented Northwind people."""
import json
import pytest
from fastapi.testclient import TestClient
from unittest import mock
from taskuary import learn, learned_cut as lc, learnedgraph, learnedlines, memoryedit, server
from tests import memory_cases as C


@pytest.fixture
def w():
    s, facts = C.world()
    ev = ', '.join(f'msg{m}' for m in facts['erin_fast'][:3])
    erin = f'- Erin Blake (erin@northwind.example) is your manager; you answer her asks within the hour [s:4 | ev: {ev} | seen: 2026-10-20 | k: erin manager hour]'
    ray = f"- Payroll questions from site managers go to Ray Colton (ray@northwind.example) [s:4 | ev: task{facts['payroll_ray'][0]} | seen: 2026-10-20 | k: payroll ray]"
    own = '- Paula Vance (paula@northwind.example) prefers a call to a long mail'
    doc = s.get_doc('learned').replace(lc.PEOPLE + '\n', lc.PEOPLE + '\n' + '\n'.join((erin, ray, own)) + '\n', 1)
    s.save_doc('learned', doc, 'reflect')
    return s, facts, erin, ray, own


def _reflect(s, answer): return learn.reflect(s, llm=lambda system, user, **k: answer(s.get_doc('learned')))


def test_forget_is_a_tombstone_the_next_reflection_does_not_write_back(w):
    s, facts, erin, ray, own = w
    assert memoryedit.mark(s, 'payroll ray', 'forget')['ok']
    assert 'Ray Colton' not in s.get_doc('learned') and learnedlines.row(s, 'payroll ray')['Status'] == 'forgotten'
    # the model writes it straight back, on the same evidence - the code keeps it out
    _reflect(s, lambda d: d.replace(lc.PEOPLE + '\n', lc.PEOPLE + '\n' + ray + '\n', 1))
    assert 'Ray Colton' not in s.get_doc('learned')
    assert 'forgotten' in [h['Action'] for h in s.learned_history('payroll ray')]


def test_wrong_is_never_revived_and_keep_makes_a_line_the_owners(w):
    s, facts, erin, ray, own = w
    memoryedit.mark(s, 'payroll ray', 'wrong')
    assert learnedlines.row(s, 'payroll ray')['Status'] == 'wrong'
    more = ray.replace(f"task{facts['payroll_ray'][0]}", ', '.join(f'task{t}' for t in facts['payroll_ray']))
    _reflect(s, lambda d: d.replace(lc.PEOPLE + '\n', lc.PEOPLE + '\n' + more + '\n', 1))
    assert 'Ray Colton' not in s.get_doc('learned'), 'not even on more evidence'
    memoryedit.mark(s, 'erin manager hour', 'keep')
    r = learnedlines.row(s, 'erin manager hour')
    assert r['Status'] == 'in_use' and r['OwnerText'].startswith('Erin Blake') and 'kept' in [h['Action'] for h in s.learned_history('erin manager hour')]
    # ...the owner's words stand over a rewrite
    _reflect(s, lambda d: d.replace('you answer her asks within the hour', 'she gets quick answers'))
    assert 'you answer her asks within the hour' in s.get_doc('learned')


def test_wrong_on_your_own_line_says_why_and_changes_nothing(w):
    s, facts, erin, ray, own = w
    key = next(k for raw, k in lc.lines(s.get_doc('learned'), lc.PEOPLE) if 'Paula' in raw)
    before = s.get_doc('learned')
    with pytest.raises(ValueError, match='That line is yours'): memoryedit.mark(s, key, 'wrong')
    assert s.get_doc('learned') == before
    with mock.patch.object(server, 'store', s):
        c = TestClient(server.app)
        r = c.post('/api/learned/mark', json={'key': key, 'how': 'wrong'})
        assert r.status_code == 409 and 'Forget takes it out' in r.json()['detail']
        assert c.post('/api/learned/mark', json={'key': 'nothing like it', 'how': 'forget'}).status_code == 404
        assert c.post('/api/learned/mark', json={'key': key, 'how': 'forget'}).json()['ok']
    assert 'Paula' not in s.get_doc('learned')


def test_marks_need_no_ai_and_the_page_says_connect_one(w):
    s, *_ = w
    with mock.patch('taskuary.capabilities.has_ai', return_value=False):
        g = learnedgraph.graph(s)
    assert g['ai'] is False
    assert memoryedit.mark(s, 'erin manager hour', 'forget')['ok']


def test_visualize_gets_the_five_subjects_with_their_real_readers_and_your_own_lines(w):
    s, *_ = w
    g = learnedgraph.graph(s)
    assert [x['slug'] for x in g['sections']] == list(lc.SECTIONS)
    reads = {x['slug']: x['reads'] for x in g['sections']}
    assert reads['people'] == 'read by triage (priority only) · drafts · the Advisor · the Assistant · agents'
    assert reads['bring'] == 'read by the Assistant'
    by = {l['key']: l for l in g['lines']}
    assert by['erin manager hour']['subject'] == 'erin@northwind.example' and by['erin manager hour']['section_slug'] == 'people'
    mine = [l for l in g['lines'] if l.get('own')]
    assert len(mine) == 1 and 'Paula' in mine[0]['text'] and mine[0]['subject'] == 'paula@northwind.example'
    # ...and the page's own words for an older server are the server's words
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / 'website' / 'src' / 'learnedGroups.js').read_text(encoding='utf-8')
    for x in g['sections']: assert f'{{ slug: "{x["slug"]}", title: "{x["title"]}", reads: "{x["reads"]}" }}' in js


def test_what_changed_carries_each_lines_key_and_where_it_stands(w):
    s, *_ = w
    memoryedit.mark(s, 'payroll ray', 'forget')
    rows = learnedgraph.changes(s)
    newest = {r['key']: r for r in rows if r['newest']}
    assert newest['payroll ray']['standing'] == 'forgotten'
    assert sum(r['key'] == 'payroll ray' and r['newest'] for r in rows) == 1


# ── slice 7: the Assistant's memory tools ride the same road ──────────────────────────────────────────────────────────────────────
def test_a_fact_said_is_in_use_at_once_and_one_it_replaces_is_closed_not_deleted(w):
    s, facts, erin, ray, own = w
    gail = f"- Gail Moreno (gail@northwind.example) runs headcount in Finance [s:4 | ev: sv{facts['gail_monday'][0]} | seen: 2026-10-01 | k: gail finance headcount]"
    s.save_doc('learned', s.get_doc('learned').replace(lc.PEOPLE + '\n', lc.PEOPLE + '\n' + gail + '\n', 1), 'reflect')
    out = memoryedit.remember(s, 'Gail Moreno moved to Ops', about='gail@northwind.example', replaces='gail finance headcount')
    doc = s.get_doc('learned')
    assert out['section'] == 'people' and '- Gail Moreno moved to Ops (gail@northwind.example)' in lc.section(doc, lc.PEOPLE)
    assert 'in Finance' not in doc
    r = learnedlines.row(s, 'gail finance headcount')
    assert r['Status'] == 'closed' and r['ValidTo'] and out['closed']['until'] == r['ValidTo']
    assert 'Gail Moreno moved to Ops' in lc.for_reader(s, 'advisor'), 'the owner said it: every reader of the section has it now'
    # ...and the reflection never writes the closed line back
    _reflect(s, lambda d: d.replace(lc.PEOPLE + '\n', lc.PEOPLE + '\n' + gail + '\n', 1))
    assert 'in Finance' not in s.get_doc('learned')


def test_whos_gail_to_me_is_read_from_the_lines_and_the_org_chart(w):
    s, *_ = w
    memoryedit.remember(s, 'Gail Moreno moved to Ops', about='gail@northwind.example')
    a = memoryedit.about(s, 'Gail')
    assert 'gail@northwind.example' in a['names'] and [l['text'] for l in a['lines']] == ['Gail Moreno moved to Ops (gail@northwind.example)']
    e = memoryedit.about(s, 'erin@northwind.example')
    assert e['relation'] and any('your manager' in l['text'] for l in e['lines'])
    assert memoryedit.about(s, 'Nobody Here')['lines'] == []


def test_the_chat_keeps_gail_moved_to_ops_and_forgets_rays_payroll_line_at_once(w):
    """The Assistant's road (concierge.call_turn), on the desk as on the phone: said, kept, receipted in the line's own words."""
    from taskuary import concierge
    s, facts, erin, ray, own = w
    gail = f"- Gail Moreno (gail@northwind.example) runs headcount in Finance [s:4 | ev: sv{facts['gail_monday'][0]} | seen: 2026-10-01 | k: gail finance headcount]"
    s.save_doc('learned', s.get_doc('learned').replace(lc.PEOPLE + '\n', lc.PEOPLE + '\n' + gail + '\n', 1), 'reflect')
    dock = concierge.general.dock_task(s, 'owner')[0]['TaskId']
    out = concierge.call_turn(s, dock, {'kind': 'memory.remember', 'params': {'note': 'Gail Moreno moved to Ops', 'about': 'gail@northwind.example',
                                                                         'replaces': 'gail finance headcount'}}, None, 'Gail moved to Ops')
    assert out['did'] == 'memory.remember' and out['say'].startswith('Remembered under Your people') and 'kept as history' in out['say']
    assert learnedlines.row(s, 'gail finance headcount')['Status'] == 'closed' and 'moved to Ops' in s.get_doc('learned')
    out = concierge.call_turn(s, dock, {'kind': 'memory.wrong', 'params': {'key': 'payroll ray', 'how': 'forget'}}, None, 'forget that Ray does payroll')
    assert out['did'] == 'memory.wrong' and 'Ray Colton' in out['say'] and 'Ray Colton' not in s.get_doc('learned')
    # ...a key nobody has, and Wrong on the owner's own line: said back for the model to put in words, nothing changed
    paula = next(k for raw, k in lc.lines(s.get_doc('learned'), lc.PEOPLE) if 'Paula' in raw)
    for p in ({'key': 'no such line', 'how': 'wrong'}, {'key': paula, 'how': 'wrong'}):
        with pytest.raises(concierge.CallMiss, match='Nothing was changed'): concierge._memory(s, dock, 'memory.wrong', p)
    assert 'Paula' in s.get_doc('learned')


def test_the_tools_are_in_the_catalogue_and_a_plain_fact_is_still_a_saved_note(w):
    from taskuary import operations, toolcatalog
    s, *_ = w
    assert 'memory.wrong' in operations.KINDS and toolcatalog.is_read('memory.about')
    assert toolcatalog.valid('memory.about', {}) == 'memory.about needs who' and toolcatalog.valid('memory.wrong', {'key': 'x'}) == ''
    assert 'memory.about' in toolcatalog.block() and 'memory.wrong' in toolcatalog.block()
    with mock.patch.object(server, 'store', s):
        out = server._run_operation({'kind': 'memory.remember', 'target': 0, 'params': {'note': 'The office opens at 8'}}, None)
    assert out.get('memoryId') and 'opens at 8' not in s.get_doc('learned'), 'a fact about nobody is a saved note, as before'
