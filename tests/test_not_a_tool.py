"""A call to a name that is no tool says what the name is and the way in (TQ-1354, 2026-11-08): an agent sending from a Gmail mailbox
called run_system with "gmail" and read only "unknown tool type: gmail". The fix there stopped listing the mailbox as a tool; this is the
general one - whatever card an agent reaches for, the refusal names the right next call."""
from taskuary import docsync
from taskuary.store import MemoryStore


def test_a_card_with_tools_names_them():
    assert 'handbook_search' in docsync.not_a_tool(MemoryStore(), 'handbook')

def test_a_mailbox_points_at_propose_email():
    w = docsync.not_a_tool(MemoryStore(), 'gmail')
    assert 'mailbox' in w and 'propose_email' in w and 'unknown' not in w

def test_a_vendor_mcp_server_points_at_its_own_tools():
    from taskuary import connectorcatalog
    t = next(c['type'] for c in connectorcatalog.cards() if c.get('mcp'))
    assert 'MCP server' in docsync.not_a_tool(MemoryStore(), t)

def test_a_near_miss_offers_the_real_name():
    w = docsync.not_a_tool(MemoryStore(), 'handbook_serch')
    assert 'did you mean' in w and 'handbook_search' in w

def test_every_answer_says_where_the_list_is():
    for t in ('gmail', 'nothing_like_this', 'handbook'): assert 'YOUR SYSTEMS' in docsync.not_a_tool(MemoryStore(), t)

def test_no_type_at_all_says_run_system_needs_one():
    "run_system {} read 'unknown tool type:  YOUR SYSTEMS...' - a blank where the name should be."
    w = docsync.not_a_tool(MemoryStore(), '')
    assert 'unknown tool type' not in w and '`type`' in w and 'YOUR SYSTEMS' in w


def test_a_connector_id_that_is_no_card_is_said_as_that():
    """A wrong connector_id was answered "intacct has no connection card an owner turned on - it is not an agent tool" while the Intacct
    card stood on, marked a tool: untrue, and it sent the agent away from a system it could use. A number that is no card says so."""
    import json
    from unittest import mock
    from test_agent_toolbox import server, tool, world
    s, tid, _ = world()
    with mock.patch.object(server, 'store', s):
        card = s.get_connector_by_type('intacct')
        s.save_connector({'ConnectorId': card['ConnectorId'], 'Active': 1, 'Roles': 'tool'}, 'test')
        said, err = tool(tid, 'run_system', type='intacct', object='VENDOR', connector_id=card['ConnectorId'] + 9999)
    assert err and 'turned on' not in said and 'not an agent tool' not in said
    assert str(card['ConnectorId'] + 9999) in said and 'list_systems' in said


def test_two_cards_of_a_type_are_never_picked_between_silently():
    """Two Intacct companies, each a card marked a tool: a call with no connector_id ran on whichever row came first - one company's
    books read as the other's. With one tool card of the type it is that one, even beside a card that is no tool; with two the call
    names them and runs nothing."""
    import json
    from unittest import mock
    from test_agent_toolbox import server, tool, world
    from taskuary.reports import REGISTRY
    s, tid, _ = world()
    ran = []
    with mock.patch.object(server, 'store', s), mock.patch.dict(REGISTRY, {'intacct': lambda cfg: ran.append(cfg['connector_id']) or ('1 row', 'x')}):
        first = s.get_connector_by_type('intacct')
        s.save_connector({'ConnectorId': first['ConnectorId'], 'Active': 1, 'Roles': 'report'}, 'test')     # on, but no agent tool
        second = s.save_connector({'Type': 'intacct', 'Name': 'Intacct - Northwind West', 'Active': 1, 'Roles': 'tool'}, 'test')
        second = second if isinstance(second, int) else second['ConnectorId']
        said, err = tool(tid, 'run_system', type='intacct', object='VENDOR')
        assert not err and ran == [second], said
        s.save_connector({'ConnectorId': first['ConnectorId'], 'Roles': 'tool'}, 'test')
        said, err = tool(tid, 'run_system', type='intacct', object='VENDOR')
        assert err and ran == [second], said
        assert str(first['ConnectorId']) in said and str(second) in said and 'connector_id' in said
