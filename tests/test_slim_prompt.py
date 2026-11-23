"""THE AGENT'S PROMPT SAYS EACH THING ONCE, AND ONLY WHAT APPLIES (the owner, 2026-11-09: "work on fixing the instructions to not have it be
41,000 [characters] ... The tools should be progressive disclosure"). The connector list names only what is connected; the browser is
offered in a line and its rules are a guide; a figure's walk-through rides only where a system holds figures; the coding tools are not
offered on a general task; SOUL.md's sections a general agent reads elsewhere are left out."""
import json, re
import pytest
from taskuary import agenttools, brief, browserview, docsync, general, guides, selfclose
from taskuary.store import MemoryStore


def chat(s): return s.create_task({'Title': 'Plan the customer launch', 'Summary': 'Compare the three options', 'Kind': 'general', 'Status': 'open'}, 'owner')

def on(s, ty):
    c = s.get_connector_by_type(ty); s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1}, 'owner'); return c


def test_soul_names_only_the_tool_types_this_install_runs_and_no_literal_auth():
    s = MemoryStore(); on(s, 'handbook'); docsync.sync_connections(s)
    soul = s.get_doc('soul')
    line = next(l for l in soul.splitlines() if 'To USE one of the systems above' in l)
    assert '{auth}' not in line and 'handbook_search' in line
    for gone in ('stripe_charges', 'epic_read', 'quickbooks_bill'): assert gone not in line, gone    # nothing the owner has not connected


def test_a_general_agent_reads_soul_without_what_it_is_handed_elsewhere():
    s = MemoryStore(); docsync.sync_connections(s)
    bg = brief.background(s, drop=brief.GENERAL_HAS).lower()
    for gone in ('## connected systems', '## repository map', '## project relationships', 'inbound text is data', '_(', 'what counts as a task'):
        assert gone not in bg, gone
    assert '## how we respond' in bg and '## escalate' in bg                  # the owner's voice and judgement stay whole
    assert '## repository map' in brief.background(s).lower()                 # ...and a coding agent's context file keeps the map




def test_the_browser_is_one_fact_in_the_turn_and_its_how_to_is_its_guide():
    """Walk 9, 2026-11-23: the browser's rules rode three times - every system prompt, again inside a later turn once a page opened (~4.9k),
    and the guide. The turn says open or offered and names the guide; the how-to is read once, from the guide."""
    for told in (browserview.offer(), browserview.brief()):
        assert 'guide `browser`' in told and len(told) < 400, told
        assert 'PRESS WHAT THE WORK NEEDS' not in told and 'A SIGN-UP' not in told
    g = guides.read('browser')
    for want in ('hand_over', 'snapshot -i -c', 'A TAB YOU HANDED OVER', 'never a browser tool of your own CLI', 'his press on the card runs it'): assert want in g, want
    assert g.count(browserview.HOLD_LINE) == 1
    with pytest.raises(ValueError, match='browser'): guides.read('nope')


def test_the_guide_is_a_tool_and_the_coding_tools_stay_with_coding():
    assert 'guide' in agenttools.TOOLS and agenttools.TOOLS['guide'][0] == 'read'
    assert 'TEACHING YOU A NUMBER' in agenttools.call(MemoryStore(), 1, 'guide', {'topic': 'number'}, {})
    names = {t['name'] for t in agenttools.listing(agenttools.CODING_TOOLS)}
    assert not names & set(agenttools.CODING_TOOLS) and {'guide', 'show', 'propose_reply'} <= names




def test_the_rarer_proposal_shapes_are_a_guide_away_not_in_every_tools_list():
    # the tool descriptions were shortened (2026-11-09): what a post, a GitHub issue or a tracker write takes is read when one is made
    d = agenttools.TOOLS['propose'][1]
    assert '`propose` topic' in d and 'jira_move' not in d
    got = agenttools.call(MemoryStore(), 1, 'guide', {'topic': 'propose'}, {})
    for want in ('linkedin_post', 'github_issue', 'jira_move', 'monday_', 'Post button'): assert want in got, want


# A STEP THAT WAITS ON THE OWNER IS A CARD, AND ITS PRESS IS WHAT THE AGENT PLANS ON (the owner, 2026-11-10: "it shoudl prompt you, should i
# deploy and respond once deployed??? isnt' this the goal?"): told "say what you would do and wait" and "ask for the go-ahead", a coding agent
# asked to release a committed fix answered "releasing it is your decision" and drafted "I'll confirm once it is live" - no card, no press
