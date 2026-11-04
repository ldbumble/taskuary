"""A ROW CLICKED ANSWERS WITHOUT BUILDING THE RAIL (the owner, 2026-11-04: "i clicked a watching task and there is no next/back thing yet?
took a long time to light up why?"). Back and Next stand greyed until a walk move lands (2026-11-03), and the open's own read of the row's
"+N" emptied the pile cache, so its answer built the whole rail before it went: ~0.5 s of a click on 450 rows, more on a real home. The
answer now carries the cached rail only when nothing moved; else none, and the page reads it after the answer has drawn."""
import json
from unittest import mock

from test_walk_table import world, Walk  # noqa: F401 - the walk table's world


def _open(sym_key):
    from taskuary import server
    return json.loads(server.walk_open(server.RailWalkBody(key=sym_key)).body)


def test_a_watched_row_clicked_answers_with_the_walk_and_builds_no_rail(world):
    from taskuary import funnel, server
    s, src = world
    w = Walk(s, src)
    w.do('start'); w.do('watch T5')
    server._pile_along(force=False)                   # the rail on screen, cached
    key = w.key('T5')
    with mock.patch.object(funnel, 'build', wraps=funnel.build) as built:
        out = _open(key)
    assert out['item']['key'] == key and out['walk']['on'] == key and out['walk']['above']
    assert built.call_count == 0, 'the open built the rail before answering'
    assert out['pile'] is None, 'a rail the open itself made stale rode along'
    # ...and the rail the page then reads has the row under Watching, with the row below it for Next
    p = server._pile_along(force=False)
    assert p['walk']['on'] == key and p['walk']['below'] == w.key('R1')
    assert next(r for r in p['items'] if r['key'] == key)['watching']


def test_a_section_heading_still_carries_the_rail(world):
    """Only the row click drops it: a heading opens its first row by the rail it reads, as before."""
    from taskuary import server
    s, src = world
    server._pile_along(force=False)
    out = json.loads(server.walk_open(server.RailWalkBody(level='reports')).body)
    assert out['item']['key'] == Walk(s, src).key('R1') and out['pile'] and out['pile']['walk']
