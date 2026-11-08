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
