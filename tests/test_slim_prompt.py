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


def test_the_figure_walkthrough_rides_only_where_figures_live():
    s = MemoryStore(); tid = chat(s)
    system = general._prompt(s, tid)[0]
    assert 'TEACHING YOU A NUMBER' not in system and general.NUMBER_LINE not in system
    on(s, 'mssql')
    if docsync.data_cards(s): assert general.NUMBER_LINE in general._prompt(s, tid)[0]
    assert 'TEACHING YOU A NUMBER' in guides.read('number')


def test_the_browser_offer_is_short_and_its_rules_are_one_read_away():
    held, asks = browserview.offer(held=True), browserview.offer(held=False)
    for want in ('NO BROWSER IS OPEN', 'agent-browser open <url>', 'never a browser tool of your own CLI', 'guide `browser`', 'NEVER type a password',
                 'CAPTCHA'):
        assert want in held, want
    # ...and a sign-in is the page's, from the offer itself: an agent that never opens the browser never reads the guide (the recorded walk,
    # 2026-11-11: it fetched the form from its shell and asked the owner for the password, twice)
    for want in ('no connection', 'you do not need the password', '[[TASKUARY-SIGNIN:', 'Never ask for a password', 'never work a sign-in from your shell', 'keeps it for next time'): assert want in held, want
    assert 'THEY press it' in held and 'TASKUARY CANNOT HOLD' in asks and 'TASKUARY CANNOT HOLD' not in held
    assert len(held) < len(browserview.brief(held=True, open_now=False)) / 2
    g = guides.read('browser')
    for want in ('TASKUARY-SIGNIN', 'TASKUARY-YOURTURN', 'snapshot -i -c', 'WHEN YOU ASK FOR A SIGN-IN'): assert want in g, want
    assert browserview.HOLD_LINE not in g and browserview.ASK_FIRST_LINE not in g      # the hold is the session's, said in its offer
    with pytest.raises(ValueError, match='browser'): guides.read('nope')


def test_the_guide_is_a_tool_and_the_coding_tools_stay_with_coding():
    assert 'guide' in agenttools.TOOLS and agenttools.TOOLS['guide'][0] == 'read'
    assert 'TEACHING YOU A NUMBER' in agenttools.call(MemoryStore(), 1, 'guide', {'topic': 'number'}, {})
    names = {t['name'] for t in agenttools.listing(agenttools.CODING_TOOLS)}
    assert not names & set(agenttools.CODING_TOOLS) and {'guide', 'show', 'propose_reply'} <= names


def test_each_rule_is_said_once_and_true():
    s = MemoryStore(); system = general._prompt(s, chat(s))[0]
    assert 'nothing wakes you again' not in system and 'plan on nothing else' in general.FINISH_LINE
    assert 'Several questions' not in selfclose.ASK_LINE and 'recommended answer' in selfclose.ASK_LINE
    assert "own artifact tool" not in system and 'Ask when a necessary fact is missing' not in system
    for once in ('Check each step by what the tool returned', 'Never the same failing call', 'Deliver one final file'):
        assert system.count(once) <= 1, once
    # the new lines, each in one place
    for want in ("beats triage's", 'never a guess written as their answer', 'never close with an offer'):
        assert want in system, want
    # ...and AGENT.md agrees with it: "draft their most likely answer ... ask only when it hangs on someone else" (2026-11-08) told the same
    # agent the opposite of the owner's newer word, for the same case - a fact or choice only the owner has
    assert 'their most likely answer' not in system and 'truly hangs on someone else' not in system
    # the reply is the agent's to write or to ask about (the owner, 2026-11-10: "think through what the user would want and ask clarifying
    # question, if you know the answer then just create reply") - said once
    for once in ('A MESSAGE THAT NEEDS AN ANSWER IS YOURS TO ANSWER', 'ask them that one thing here in the task instead of drafting a guess'):
        assert system.count(once) == 1, once
    assert 'IS the confirmation' in selfclose.SUMMARY_LINE and 'group chat' in selfclose.SUMMARY_LINE
    assert 'the thread wins' in general.learned_block(s, 'x') or not general.learned_block(s, 'x')


def test_the_rarer_proposal_shapes_are_a_guide_away_not_in_every_tools_list():
    # the tool descriptions were shortened (2026-11-09): what a post, a GitHub issue or a tracker write takes is read when one is made
    d = agenttools.TOOLS['propose'][1]
    assert '`propose` topic' in d and 'jira_move' not in d
    got = agenttools.call(MemoryStore(), 1, 'guide', {'topic': 'propose'}, {})
    for want in ('linkedin_post', 'github_issue', 'jira_move', 'monday_', 'Post button'): assert want in got, want


# A STEP THAT WAITS ON THE OWNER IS A CARD, AND ITS PRESS IS WHAT THE AGENT PLANS ON (the owner, 2026-11-10: "it shoudl prompt you, should i
# deploy and respond once deployed??? isnt' this the goal?"): told "say what you would do and wait" and "ask for the go-ahead", a coding agent
# asked to release a committed fix answered "releasing it is your decision" and drafted "I'll confirm once it is live" - no card, no press
def test_a_step_that_waits_on_the_owner_is_set_up_as_its_card_and_says_what_follows_the_press():
    s = MemoryStore(); system = general._prompt(s, chat(s))[0]
    for gone in ('Say what you would do and wait', 'ask for the go-ahead and wait', 'when a step needs their say-so'): assert gone not in system, gone
    assert 'never a question in words: set the step up as its card' in system
    assert 'their press on a card you set up wakes you' in general.FINISH_LINE and 'say in one line what you will do once they press it' in system
    # ...every press on its card wakes it (verdicts.decide -> general.approved): "send" is no longer a wake it has to ask for
    assert '"send" (a draft' not in selfclose.SUMMARY_LINE and '"handoff"' in selfclose.SUMMARY_LINE
    from pathlib import Path
    assert 'say in one line what follows it' in (Path(general.__file__).parent / 'templates' / 'coding.md').read_text(encoding='utf-8')
