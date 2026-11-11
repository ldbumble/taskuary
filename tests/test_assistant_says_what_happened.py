"""THE ASSISTANT SAYS ONLY WHAT HAPPENED (the owner, 2026-11-04: "stress test the assistant popup - it says it's doing things and it does
not do them" - "Rewriting the draft on TQ-n." and "✓ Rewritten - read it below before you send it" over an EMPTY draft box).

A receipt is written from what the act left in the store (effects.py), never from the plan: every operation is checked after it ran
(operations.execute), so are the writes the chat makes itself (concierge._landed), and a reply's draft is a receipt from the review as it
now is (server._draft_receipt), which also says the Assistant's under-way line again in its place (concierge.settle). Every action family
has a case here where the act fails - it raises, comes back empty, changes nothing, is refused or names a task that is not there - and the
line must not claim it. tests/assistant_stress.py is the walk these come from; `python -m tests.assistant_stress --real` runs it on the
installed claude. Invented people only."""
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import concierge, effects, general, operations, server
from taskuary.store import MemoryStore
from tests import assistant_stress as S


# ---- the walk: every ask, what it said against what changed -------------------------------------------------------------------------
@pytest.fixture(scope='module')
def walk(): return S.run(S.ASKS, real=False, quiet=False)


def test_every_ask_in_the_walk_says_only_what_happened(walk):
    bad = [f"{r['ask'].family}: {r['ask'].text!r} said {r['said']!r} ({r['claim']}) - {r['changed']}" for r in walk if not r['match']]
    assert not bad, '\n'.join(bad)


def test_the_walk_is_thirty_asks_and_every_family_has_a_failure(walk):
    assert len(walk) >= 30
    fams = {r['ask'].family for r in walk}
    for f in ('redraft', 'reply', 'put-down', 'not-a-task', 'agent', 'merge', 'todo', 'note', 'remember', 'wrong-task'):
        assert any(r['ask'].family == f and not r['did'] and r['claim'] != 'done' for r in walk), f'{f}: no failure case said as one'
    assert {'redraft', 'reply', 'cc', 'put-down', 'remind', 'watch', 'not-a-task', 'agent', 'merge', 'todo', 'open', 'remember', 'setting',
            'handoff', 'email', 'search'} <= fams


@pytest.mark.parametrize('family,fault', [('redraft', 'drafter returns nothing'), ('redraft', 'drafter returns the same words'),
                                          ('redraft', 'drafter times out'), ('reply', 'drafter returns nothing')])
def test_a_draft_that_did_not_change_never_wears_the_tick(walk, family, fault):
    r = next(r for r in walk if r['ask'].family == family and r['ask'].note == fault)
    assert '✓' not in r['said'] and '✗' in r['said'], r['said']
    assert r['claim'] == 'failed'


def test_a_rewrite_that_landed_says_so_from_the_box(walk):
    r = next(r for r in walk if r['ask'].family == 'redraft' and not r['ask'].note)
    assert r['did'] and '✓ Rewrote the draft on TQ-0004' in r['said']


# ---- operations: what an act promised is looked at after it ran ---------------------------------------------------------------------
@pytest.fixture
def s():
    v = MemoryStore()
    with mock.patch.object(server, 'store', v): yield v
    v.close()


def task(s, **kw): return s.create_task({'Title': 'Send Erin Blake the signed form', 'Kind': 'task', 'Status': 'open', 'Priority': 'normal', **kw}, 'owner')


def run(s, kind, target, params=None, handler=None):
    op = operations.propose(s, kind, target, params or {}, 'owner')
    return operations.execute(s, op['id'], op['version'], handler or (lambda: {'ok': True}), 'owner')


@pytest.mark.parametrize('kind,params,why', [
    ('task.complete', {}, 'is still open'),
    ('task.not_a_task', {}, 'is still on your list'),
    ('task.reopen', {}, None),                                   # a reopen over an open task promised nothing it broke
    ('task.defer', {'until': 'tomorrow 9am'}, 'no day to come back'),
    ('task.watching', {}, 'not under Watching'),
    ('task.merge', {'into': 'TQ-0099'}, 'still a task of its own'),
    ('task.comment', {'text': 'waiting on the vendor'}, 'no note landed'),
    ('task.checklist', {'add': ['call the bank']}, "to-dos did not change"),
    ('task.update', {'title': 'Census export cutover'}, 'did not change'),
    ('dispatch.prepare', {'kind': 'general'}, 'did not start'),
    ('agent.continue', {}, 'did not pick up'),
])
def test_an_operation_that_changed_nothing_is_not_done(s, kind, params, why):
    t = task(s)
    out = run(s, kind, t, params)
    if why is None: assert out['status'] == 'done'; return
    assert out['status'] == 'error' and why in out['error'], out
    assert concierge.receipt_turn(s, out)['say'].startswith('Not done'), 'the receipt says it did not happen'


def test_an_operation_that_did_it_is_done(s):
    t = task(s)
    def close(): s.update_task(t, {'Status': 'done'}, 'owner'); return {'status': 'done'}
    assert run(s, 'task.complete', t, handler=close)['status'] == 'done'
    t2 = task(s)
    assert run(s, 'dispatch.prepare', t2, {'kind': 'general'}, lambda: {'started': True, 'taskId': t2})['status'] == 'done'


def test_a_memory_write_that_wrote_nothing_and_a_setting_that_did_not_move(s):
    out = run(s, 'memory.remember', 0, {'note': 'Ray Colton signs off every schema change'}, lambda: {'ok': True, 'text': 'x'})
    assert out['status'] == 'error' and 'nothing was written to your memory' in out['error']
    out = run(s, 'setting.set', 0, {'setting': 'sounds', 'value': 'off'}, lambda: {'key': 'sounds', 'label': 'Sounds', 'value': 'off'})
    assert out['status'] == 'error' and 'Sounds is still' in out['error']


def test_a_send_still_waiting_is_not_sent(s):
    t = task(s)
    rid = s.add_review({'TaskId': t, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Thanks - Friday works.'})
    out = run(s, 'review.approve', rid)
    assert out['status'] == 'error' and 'still waiting' in out['error']


def test_a_check_that_cannot_read_never_fails_a_done_act(s):
    with mock.patch.dict(effects.PROMISES, {'task.complete': (lambda *a: None, lambda *a: 1 / 0)}):
        assert effects.missed(s, 'task.complete', 1, {}, None, {}) == ''


# ---- the chat's own writes: a store that failed, or a write that changed nothing -----------------------------------------------------
def say(s, call, key=None):
    return concierge.say(s, 'do it', key=key, llm=lambda system, user, max_tokens=None, **k: 'CALL: ' + json.dumps(call))


def test_a_note_the_store_refused_is_said_plainly_and_kept_as_a_cross(s):
    t = task(s)
    with mock.patch.object(s, 'add_comment', side_effect=RuntimeError('disk I/O error')):
        out = say(s, {'kind': 'task.comment', 'params': {'ref': f'TQ-{t:04d}', 'text': 'waiting on the vendor'}})
    assert out['say'].startswith('Not done - disk I/O error') and out['failed'] == 'task.comment'
    assert not any('Added a note' in (c.get('Body') or '') for c in s.list_comments(general.dock_task(s)[0]['TaskId']))


def test_a_to_do_write_that_changed_nothing_is_said_in_the_lines_place(s):
    t = task(s)
    with mock.patch.object(s, 'merge_task_checklist', return_value=[{'id': 1, 'text': 'call the bank'}]):
        out = say(s, {'kind': 'task.checklist', 'params': {'ref': f'TQ-{t:04d}', 'add': ['call the bank']}})
    assert out['say'].startswith('Not done') and "to-dos did not change" in out['say']
    rows = [c['Body'] for c in s.list_comments(general.dock_task(s)[0]['TaskId'])]
    assert not any(b.startswith('Added 1 to-do') for b in rows) and any(b.startswith('Not done') for b in rows)


def test_remembered_only_when_it_was_written(s):
    from taskuary import memoryedit
    with mock.patch.object(memoryedit, 'remember', return_value={'ok': True, 'text': 'Paula Vance runs the portal', 'section': 'people', 'title': 'Your people'}):
        out = say(s, {'kind': 'memory.remember', 'params': {'note': 'Paula Vance runs the portal', 'about': 'Paula Vance'}})
    assert out['say'].startswith('Not done') and 'nothing was written to your memory' in out['say']
    out = say(s, {'kind': 'memory.remember', 'params': {'note': 'Paula Vance runs the vendor portal', 'about': 'Paula Vance'}})
    assert out['say'].startswith('Remembered') and 'Paula Vance runs the vendor portal' in (s.get_doc('learned') or '')
    out = say(s, {'kind': 'memory.remember', 'params': {'note': 'Paula Vance runs the vendor portal', 'about': 'Paula Vance'}})
    assert 'Not done' not in out['say'], 'a fact already there is no failure'


# ---- an agent: on it only when it started -------------------------------------------------------------------------------------------
def test_an_agent_is_said_on_it_only_when_it_started(s):
    t = task(s)
    concierge.set_current(s, general.dock_task(s)[0]['TaskId'], f'task:{t}')
    with mock.patch.object(server, '_dispatch_task_to_its_agent', lambda tid, body, bg: {'dispatch': 'session', 'started': False, 'taskId': tid, 'ref': f'TQ-{tid:04d}'}), \
         mock.patch.object(server, '_brainless', lambda coding: ''):
        it = {'key': f'task:{t}', 'tid': t, 'ref': f'TQ-{t:04d}', 'kind': 'todo'}
        with mock.patch.object(concierge, '_label_on', return_value='Send to agent'):
            out = concierge._start_agent(s, general.dock_task(s)[0]['TaskId'], it, it, 'regular_agent', 'find the 4,180')
    assert 'on it now' not in out['say'] and 'did not start' in out['say'], out['say']


def test_a_start_the_door_refused_says_its_reason(s):
    t = task(s)
    # ...the door's refusal is raised with its way past it (server.StartRefused), never handed back as an answer to misread
    refusal = server.StartRefused({'sentence': 'Claude Code is not installed', 'fix': {'label': 'Connect a coding tool', 'href': '#x'}, 'retry': False})
    with mock.patch.object(server, 'dispatch_task', side_effect=refusal):
        out = run(s, 'dispatch.prepare', t, {'kind': 'general'}, lambda: server._run_operation({'kind': 'dispatch.prepare', 'target': t, 'params': {'kind': 'general'}}, None))
    assert out['status'] == 'error' and 'installed' in out['error'] and 'JSONResponse' not in out['error'], out
    assert out['outcome']['fix']['label'] == 'Connect a coding tool', out


# ---- a reply's draft: the receipt is the box as it now is, and the under-way line says how it went (the walk drives the door itself) ---
def under_way(s, text='Rewriting the draft on TQ-0001.'):
    dock = general.dock_task(s)[0]['TaskId']
    return concierge.record(s, dock, 'assistant', text), dock


@pytest.mark.parametrize('before,after,why', [('Thanks - we pay on Friday.', '', 'came back empty'),
                                              ('Thanks - we pay on Friday.', 'Thanks - we pay on Friday.', 'same as before'),
                                              ('Thanks - we pay on Friday.', "Thanks - it goes out with Friday's run.", None)])
def test_a_rewrite_says_what_the_box_holds_and_settles_its_line(s, before, after, why):
    t = task(s, Kind='reply')
    rid = s.add_review({'TaskId': t, 'Kind': 'draft', 'Status': 'pending', 'DraftText': before})
    cid, dock = under_way(s)
    s.update_review_draft(rid, after, None)                   # an empty one is refused there and said (store.EMPTY_DRAFT)
    rc = server._draft_receipt(t, server._rewritten(rid, before), True, cid)
    line = next(c_ for c_ in s.list_comments(dock) if c_['CommentId'] == cid)['Body']
    if why: assert rc['status'] == 'failed' and why in rc['text'] and line.startswith('The draft on TQ-'), rc
    else: assert rc['status'] == 'done' and rc['text'].startswith('Rewrote the draft on') and line.startswith('Rewrote the draft')
    assert '"receipt": "' + ('error' if why else 'done') + '"' in line, 'the line kept says it as a receipt, tick or cross'


def test_settle_touches_only_the_assistants_own_chat_line(s):
    t = task(s)
    cid = s.add_comment(t, 'owner', 'human', 'my own note')
    concierge.settle(s, cid, 'Rewrote the draft on TQ-0001.', True)
    assert s.list_comments(t)[0]['Body'] == 'my own note'
    concierge.settle(s, None, 'x', True)                       # no line: nothing to say again
