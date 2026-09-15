"""An unsettled census answers with what it has, and says what it could not group.

`compact_inventory` raised 409 with no rows whenever membership reconciliation was behind, had
conflicts, or left any entity uncatalogued. Two of those are transient and `wait_settled` already
waits them out; `conflicted` is not - wait_settled returns on it immediately and it persists until
somebody resolves it, so the canonical All served NOTHING and every page fell through to the legacy
/api/feed. Refusing is not a degraded mode.

Now the page arrives with `coverage.degraded` naming exactly what is missing, and the caller decides:
nothing missing means read it and mention it; entities that could not be grouped at all mean the page
is genuinely incomplete and only the legacy transport can show them.
"""
import pytest

from taskuary import processing_all


def _snapshot(*, pending=False, status='complete', uncatalogued=None, conflicts=()):
    return {'as_of': '2026-09-15 12:00:00', 'snapshot_revision': 'r1', 'items': [],
            'coverage': {'canonical_item_count': 0, 'uncatalogued': uncatalogued or {},
                         'processing_reconciliation': {
                             'pending': pending, 'status': status, 'conflicts': list(conflicts),
                             'dirty_generation': 9, 'reconciled_generation': 9 - int(pending)}}}


QUERY = {'days': 14, 'channel': None, 'source': None}


def test_a_settled_census_carries_no_manifest():
    _, coverage, _ = processing_all.compact_inventory(_snapshot(), QUERY, degraded_ok=True)
    assert 'degraded' not in coverage


def test_a_conflicted_census_still_serves_its_rows():
    """The state that used to mean a permanently blank All."""
    _, coverage, counts = processing_all.compact_inventory(
        _snapshot(status='conflicted', conflicts=[{'code': 'split'}]), QUERY, degraded_ok=True)
    assert coverage['degraded']['reason'] == 'conflicted'
    assert coverage['degraded']['missing'] == 0
    assert coverage['degraded']['conflicts'] == [{'code': 'split'}]
    assert counts['total'] == 0


def test_a_census_that_is_merely_behind_says_so():
    _, coverage, _ = processing_all.compact_inventory(_snapshot(pending=True), QUERY, degraded_ok=True)
    assert coverage['degraded']['reason'] == 'reconciling'
    assert coverage['degraded']['dirty_generation'] == 9
    assert coverage['degraded']['reconciled_generation'] == 8


def test_uncatalogued_entities_are_counted_as_missing():
    """They have no membership row, so they cannot appear as items at all - the page IS incomplete
    and the caller must be told in a number it can branch on."""
    _, coverage, _ = processing_all.compact_inventory(
        _snapshot(pending=True, uncatalogued={'message': 3, 'task': 0, 'review': 1}), QUERY, degraded_ok=True)
    assert coverage['degraded']['missing'] == 4
    assert coverage['degraded']['uncatalogued'] == {'message': 3, 'review': 1}, 'zeroes are not noise'


def test_without_permission_it_still_refuses():
    """Callers that cannot present an incomplete answer keep the old contract."""
    with pytest.raises(processing_all.AllError) as e:
        processing_all.compact_inventory(_snapshot(pending=True), QUERY)
    assert e.value.detail['code'] == 'processing_coverage_pending'
    assert e.value.status == 409


def test_the_page_route_asks_to_degrade_and_the_pile_does_on_its_last_try():
    import inspect
    page = inspect.getsource(processing_all.AllInventory.page)
    assert 'compact_inventory(snapshot, query, degraded_ok=True)' in page
    from taskuary import processing_unread
    build = inspect.getsource(processing_unread.build)
    assert 'degraded_ok=attempt == 2' in build, 'one retry for a race, then take what there is'
    assert 'if attempt == 2 or' in build, 'and the retry itself is still guarded'


def test_conflicts_are_capped_so_one_bad_census_cannot_flood_the_response():
    many = [{'code': f'c{i}'} for i in range(50)]
    _, coverage, _ = processing_all.compact_inventory(
        _snapshot(status='conflicted', conflicts=many), QUERY, degraded_ok=True)
    assert len(coverage['degraded']['conflicts']) == 20
