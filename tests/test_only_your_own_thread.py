"""The row marked Myself has to actually be you.

WhatsApp gives the owner's own "Message yourself" thread a legacy GROUP jid,
`<their number>-<when it was made>@g.us` - and gives every group they CREATED the same shape. The
card read the number prefix as proof, so a real group called "Jogging", with people in it, sat in
the list marked Myself with a button offering it to the assistant (the owner, 2026-09-17). One
click and answers about their mail would have been posted in front of everyone in that room.

What settles it is how many people are in the group. The bridge already had the participant list
from groupFetchAllParticipating and was throwing it away.
"""
import json

import pytest

from taskuary import remote_assistant
from taskuary.store import MemoryStore

ME = '15550100100'
MINE = f'{ME}-1600000001@g.us'        # a Message-yourself thread
JOGGING = f'{ME}-1600000002@g.us'     # a group the owner made, same shape, other people in it


@pytest.fixture
def conn():
    s = MemoryStore()
    cid = s.get_connector_by_type('whatsapp')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Active': 1,
                      'ConfigJson': json.dumps({'me_number': ME, 'assistant_chat': MINE})}, 'o')
    return s, s.get_connector_by_type('whatsapp', with_secret=True)


def row(jid, people=None, group=True):
    return {'jid': jid, 'group': group, 'name': '', 'n': 0, 'last': 0, 'snippet': '', 'people': people}


def test_your_own_thread_is_your_own_thread(conn):
    s, c = conn
    assert remote_assistant.own_thread(s, c, row(MINE, people=1)) is True


def test_a_group_you_made_is_not_you_however_its_jid_looks(conn):
    """The whole bug, in one line: same prefix, same shape, other people in the room."""
    s, c = conn
    assert remote_assistant.own_thread(s, c, row(JOGGING, people=14)) is False


def test_a_group_of_two_is_still_a_group(conn):
    s, c = conn
    assert remote_assistant.own_thread(s, c, row(JOGGING, people=2)) is False


def test_somebody_elses_group_was_never_eligible(conn):
    s, c = conn
    assert remote_assistant.own_thread(s, c, row('120363000000000001@g.us', people=1)) is False


def test_a_direct_chat_needs_no_counting(conn):
    s, c = conn
    assert remote_assistant.own_thread(s, c, row('15551234567@s.whatsapp.net', group=False)) is True


# ── a bridge that cannot say yet ────────────────────────────────────────────────────────
def test_an_older_bridge_keeps_the_chat_you_already_configured(conn):
    """Unknown is not "nobody". Someone set up before this must not lose their doorway."""
    s, c = conn
    assert remote_assistant.own_thread(s, c, row(MINE, people=None), MINE) is True


def test_an_older_bridge_offers_nothing_new(conn):
    """...and it does not get to hand out a new one on a guess."""
    s, c = conn
    assert remote_assistant.own_thread(s, c, row(JOGGING, people=None), MINE) is False


def test_the_shape_check_is_still_only_a_shape_check(conn):
    """is_private stays what it is - the thing that changed is what the card offers FROM."""
    s, c = conn
    assert remote_assistant.is_private(s, c, JOGGING) is True
    assert remote_assistant.own_thread(s, c, row(JOGGING, people=14)) is False
