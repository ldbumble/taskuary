"""Settings > Docs > How it works describes today's rail (2026-10-26): it still read "ranked - not the order it arrived in", rows that
"slide to their slot", and a Timeline that was removed on 2026-10-15. The rail is by arrival and rows never move."""
from fastapi.testclient import TestClient
from taskuary import server


def test_how_it_works_describes_the_rail_by_arrival_and_no_timeline():
    t = TestClient(server.app).get('/api/how-it-works').json()['text']
    for stale in ('ranked', 'slide to their slot', 'Timeline', 'funnel'): assert stale not in t, stale
    assert 'in the order they arrived' in t and 'never move' in t and 'Tasks, then Reports, then FYI' in t
