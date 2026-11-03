"""SHOULD BE A TASK ON ONE LINE OF AN FYI BATCH (the owner, 2026-11-03: "keep it there but say was moved to task"): the line is the new task
now, under Tasks, while the page keeps it in the batch wearing where it went. The batch's All read, next reads the other lines and never
marks the task read a second time - by Next's read or by a card's Done - and the walk still ends on the last batch with the task left
unread under Tasks. The walk table's world (tests/walkworld.py): Paula Vance's floor notices, Northwind, *.example."""
import pytest
from fastapi.testclient import TestClient

import walkworld
from test_walk_table import world  # noqa: F401 - the fixture


def _moved(world, read):
    from taskuary import funnel, railwalk, server
    s, src = world
    f = {n: walkworld.key_of(s, src, f'F{n}') for n in range(1, 8)}
    b1 = 'fyis:' + ','.join(f[n] for n in range(1, 5))
    on = railwalk.open(s, b1)['walk']['on']
    assert on == b1, on
    r = TestClient(server.app).post(f"/api/messages/{src['F2']['mid']}/mine", json={'kind': 'task'})
    assert r.status_code == 200, r.text
    walkworld.reconcile(s)
    was = s.funnel_states().get(f[2])
    out = read(railwalk, s, b1)
    walkworld.reconcile(s)
    assert s.funnel_states().get(f[2]) == was, f'the batch read wrote on the task it became: {s.funnel_states().get(f[2])}'
    rows = {i['key']: i for i in funnel.build(s, keep_surfaced=True)['items']}
    task = rows[f[2]]
    assert task.get('tid') == r.json()['taskId'] and not task.get('surfaced'), f'the task it became is unread under Tasks: {task}'
    assert all(rows.get(f[n], {}).get('surfaced') or f[n] not in [x['key'] for x in walkworld.rows(s)] for n in (1, 3, 4)), 'the rest were read'
    return s, f, out


def test_all_read_next_reads_the_batch_but_never_the_line_made_a_task(world):
    s, f, out = _moved(world, lambda w, s, b1: w.next(s, b1))
    assert f[2] not in (out.get('read') or []), out.get('read')
    assert out['item']['key'] == 'fyis:' + ','.join(f[n] for n in range(5, 8)), 'Next goes on to the batch below'


def test_a_cards_done_reads_the_batch_but_never_the_line_made_a_task(world):
    _moved(world, lambda w, s, b1: w.leave(s, b1, 'settle'))


def test_the_walk_still_ends_after_the_last_batch(world):
    from taskuary import railwalk
    s, f, out = _moved(world, lambda w, s, b1: w.next(s, b1))
    end = railwalk.next(s, out['item']['key'])
    assert end.get('item') is None and end['walk']['ended'], 'the walk ends - the task it became is above, under Tasks, never offered as FYI'
