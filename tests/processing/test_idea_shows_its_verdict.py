"""An assistant idea carries its triage verdict onto the rail row, like a message does.

An idea IS triaged - triage_ideas writes intent/why into its ActionJson, and idea_lane already
reads it - but the row the Timeline draws carried no RouteReason, so the detail pane had nothing to
put under Triage and said "Not routed." Reading the screen, the owner concluded ideas skip triage
altogether (2026-09-15: "from timeline it seems like assistant ideas don't go through triage but
they do no?"). They do; the row simply never repeated the verdict.
"""
from datetime import datetime

import pytest

from taskuary import processing_all
from taskuary.store import SQLiteStore

NOW = datetime.now().replace(microsecond=0)
STAMP = NOW.isoformat(sep=' ')


@pytest.fixture
def db(tmp_path):
    store = SQLiteStore(str(tmp_path / 'ideas.db'))
    yield store
    store.cx.close()


def an_idea(db, key, text, triage=None):
    db.upsert_idea({'key': key, 'kind': 'idea', 'text': text, 'sig': text[:40],
                    'action': {'triage': triage} if triage else {}}, STAMP)
    db.reconcile_processing_membership(fixed_now=STAMP)
    return db.get_idea_by_key(key) if hasattr(db, 'get_idea_by_key') else None


def rows(db):
    snap = db.processing_inventory_snapshot(fixed_now=NOW.isoformat(), live_state=[],
                                            display_only=True, history_days=14)
    out, _cov, _counts = processing_all.compact_inventory(
        snap, processing_all.normalize_query(None, None, 14), include_excluded=True, degraded_ok=True)
    return {r['open_target']['kind'] + ':' + str(r['open_target']['id']): r['row'] for r in out}


def test_a_judged_idea_repeats_its_verdict_on_the_row(db):
    an_idea(db, 'k1', 'The 14:44 error check discards are a duplicate of an existing vendor id.',
            {'intent': 'fyi', 'why': 'an informational note that asks for no action'})
    row = next(r for k, r in rows(db).items() if k.startswith('idea:'))
    assert row['RouteReason'] == 'triage: fyi - an informational note that asks for no action'


def test_the_verdict_names_the_road_it_chose(db):
    an_idea(db, 'k2', 'Maya is still waiting on the PAM review.',
            {'intent': 'task', 'why': 'someone is waiting on an answer'})
    row = next(r for k, r in rows(db).items() if k.startswith('idea:'))
    assert row['RouteReason'] == 'triage: task - someone is waiting on an answer'
    assert row['Lane'] == 'asked', 'the lane and the reason must agree about the same verdict'


def test_an_unjudged_idea_claims_no_verdict(db):
    """Nothing reached a verdict here - saying "fyi" would be inventing one."""
    an_idea(db, 'k3', 'Something nobody has classified yet.')
    row = next(r for k, r in rows(db).items() if k.startswith('idea:'))
    assert not row.get('RouteReason')


def test_a_failed_verdict_says_so_rather_than_reading_as_fyi(db):
    an_idea(db, 'k4', 'The AI was down when this was raised.',
            {'error': 'no AI connector', 'why': 'could not classify'})
    row = next(r for k, r in rows(db).items() if k.startswith('idea:'))
    assert not row.get('RouteReason'), 'a failed verdict is not a road it chose'
