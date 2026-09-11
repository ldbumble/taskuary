"""An agent that stopped and is waiting on you wears its own word.

The lane table has always had one for it - funnelPile.LANE_META.blocked, the 👋 - but `row_lane`
never returned `blocked`: with `AgentWaiting` set it fell into `approve`, so a parked coder wore
"needs your yes", the same pill a drafted reply wears. Both are the owner's task (band 2, "your
task", which is right); they are not the same thing to do (the owner, 2026-09-11).
"""
from taskuary.processing_all import row_lane


def _waiting(**over):
    row = {'TaskStatus': 'in_progress', 'Working': 'coder', 'AgentWaiting': True, 'NeedsYou': 1,
           'Assignee': 'agent:coder'}
    row.update(over)
    return row


def test_a_parked_agent_is_waving_not_a_draft_awaiting_a_yes():
    assert row_lane(_waiting()) == 'blocked'


def test_a_drafted_reply_still_needs_your_yes():
    assert row_lane({'TaskStatus': 'open', 'ReviewStatus': 'pending', 'NeedsYou': 1}) == 'approve'


def test_a_waving_agent_outranks_a_draft_sitting_on_the_same_row():
    """Both are true at once when a coder parks on a task that also has a draft waiting. The
    agent is the thing blocking work, so it is the thing the row says."""
    assert row_lane(_waiting(ReviewStatus='pending')) == 'blocked'


def test_an_agent_still_working_is_not_waving():
    assert row_lane({'TaskStatus': 'in_progress', 'Working': 'coder', 'AgentWaiting': False,
                     'Assignee': 'agent:coder'}) == 'working'


def test_handed_over_and_not_started_is_still_queued():
    assert row_lane({'TaskStatus': 'open', 'Assignee': 'agent:coder'}) == 'queued'


def test_the_waving_row_stays_in_the_owner_s_level():
    """`blocked` and `approve` are both band 2, so the rail still files it under "your task" -
    the grouping the owner confirmed is right. Only the word on the row changes."""
    from taskuary.processing_order import feed_band
    assert feed_band(_waiting()) == feed_band({'TaskStatus': 'open', 'ReviewStatus': 'pending', 'NeedsYou': 1}) == 2
