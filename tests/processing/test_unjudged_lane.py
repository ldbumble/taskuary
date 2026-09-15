"""A row NOTHING judged must not wear the word for a verdict.

The `error` state exists precisely so a message the AI could not classify is not filed as
"nothing to do" (ingest, PW-036) - and then both rails handed it the word `fyi` anyway, because
it has no task and nobody waiting, so it fell to the quiet band like a newsletter. On the morning
Azure answered 500 to six refund threads, the work rail called every one of them "a person told
you something; nothing to do" (the owner, 2026-09-15: "were they put to fyi even with a error?
that's a bad bug").

The band is not the bug - an unjudged row is not work until somebody decides it is. The WORD is.
"""
import pytest

from taskuary.funnel import LANES, LANE_MARKS, LANE_WORDS
from taskuary.processing_all import row_lane
from taskuary.processing_order import feed_band

ERR = {'MsgStatus': 'error', 'Channel': 'email', 'Category': 'error',
       'RouteReason': 'AI triage failed (azure_openai error 500) - unclassified; fix the AI connector and retry'}


def test_an_unjudged_row_says_so_instead_of_fyi():
    assert row_lane(ERR) == 'unjudged'


def test_a_row_triage_did_judge_keeps_its_own_quiet_word():
    assert row_lane({'MsgStatus': 'filed', 'Channel': 'email',
                     'RouteReason': 'triage: fyi - an automated notice'}) == 'fyi'


def test_the_unjudged_row_stays_in_the_quiet_band():
    """Same level as fyi, so nothing jumps into "your task" - only the word changes."""
    assert feed_band(ERR) == feed_band({'MsgStatus': 'filed', 'Channel': 'email'}) == 4


def test_a_failed_report_is_still_its_own_thing():
    """`broken` is a check that RAN and failed; `unjudged` is one nothing ever judged."""
    assert row_lane({'MsgStatus': 'feed', 'Channel': 'report', 'ReportFailed': True}) == 'broken'


def test_the_lane_is_in_the_shared_vocabulary():
    assert 'unjudged' in LANES
    assert LANE_WORDS['unjudged'][0] == 'triage failed'
    assert LANE_MARKS['unjudged']


def test_a_standing_mute_cannot_hide_a_triage_failure():
    """MUTED_LANES is "what has nothing to do". Nothing judged this, so no rule can say it is."""
    from taskuary.funnel import MUTED_LANES
    assert 'unjudged' not in MUTED_LANES


@pytest.mark.parametrize('lane', sorted(LANES))
def test_every_lane_has_a_word_and_a_mark(lane):
    assert LANE_WORDS.get(lane) and LANE_MARKS.get(lane)
