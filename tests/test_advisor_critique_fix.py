"""A CRITIQUE CARRIES ITS FIX (the owner, 2026-10-28: "if the advisor is saying the agent did not do its job then it should tell you to
continue the agent or something. just judging without action is not worth much"). A line saying the work leaves something out lights the
move that puts it right, the line as its note: the agent's Continue where an agent made the work, Redraft where the drafter did. Read from
the decision's kind and whether an agent ran - never the line's words. Invented Northwind people only (CLAUDE.md)."""
from taskuary import advisor, funnel
from taskuary.testing import Factory
from tests.test_advisor_memory_reason import w, ask, judged       # noqa: F401 - w is the fixture

V = lambda *vs: [{'verb': v, 'label': v} for v in vs]
GAP = 'The draft leaves her start-date question unanswered.'


def drafted(s, by_agent=False):
    t = ask(s, 'erin', 'Grant application questions', 'Which category do we apply under, and what start date should we give?')
    mid = s.list_messages(t)[-1]['MessageId']
    if by_agent: Factory(s).comment(t, 'I drafted the reply from the thread.', actor='agent', actor_type='assistant_agent')
    Factory(s).review(t, mid, draft='We apply under the community category.'); funnel.invalidate()
    return t


def test_a_critique_of_the_drafters_draft_lights_redraft_with_the_line_as_its_note(w):
    s, _ = w
    t = drafted(s)
    d, _ = judged(s, t, {'verb': 'reply', 'line': GAP, 'evidence': [], 'kind': 'draft_caution'})
    assert (d['verb'], d['line']) == ('redraft', GAP), d
    assert d['fix'] == {'verb': 'redraft', 'label': 'Redraft with this', 'note': GAP}, d


def test_a_critique_of_an_agents_work_lights_continue_with_the_line_as_its_note(w):
    s, _ = w
    t = drafted(s, by_agent=True)
    item = advisor._item(s, 'task', t, f'task:{t}')
    d = {'key': f'task:{t}', 'state': 'draft_ready', 'verb': 'reply', 'line': GAP, 'by': 'model', 'evidence': [], 'kind': 'work_gap'}
    fix = advisor.fix_of(s, item, V('approve', 'reply', 'redraft', 'continue'), d)
    assert fix == {'verb': 'continue', 'label': 'Continue with this', 'note': GAP}
    # ...and where the row carries no Continue, the draft is written again instead - never a button the owner cannot press
    assert advisor.fix_of(s, item, V('approve', 'reply', 'redraft'), d)['verb'] == 'redraft'


def test_a_general_agents_work_found_short_is_continued_from_the_strip_and_its_send_is_not_lit(w):
    """The owner's report: a general agent's Result, "the draft leaves her question unanswered", and Reply lit. A general agent's row draws
    no Continue (its chat is the way on), so the strip's own Continue with this carries the fix and the row lights Redraft - never Send."""
    s, _ = w
    t = drafted(s, by_agent=True)
    s.update_task(t, {'Kind': 'general'}, 'owner'); funnel.invalidate()
    d, _ = judged(s, t, {'verb': 'reply', 'line': GAP, 'evidence': [], 'kind': 'work_gap'})
    assert d['fix'] == {'verb': 'continue', 'label': 'Continue with this', 'note': GAP}, d
    assert (d['verb'], d['line']) == ('redraft', GAP), d


def test_no_gap_or_no_line_carries_no_fix(w):
    s, _ = w
    t = drafted(s)
    item = advisor._item(s, 'task', t, f'task:{t}')
    for kind, line in (('late', 'Erin wrote two hours ago.'), ('draft_caution', ''), ('other', GAP)):
        assert advisor.fix_of(s, item, V('approve', 'redraft'), {'kind': kind, 'line': line}) is None, kind
    d, _ = judged(s, t, {'verb': 'reply', 'line': 'Erin prefers a call on agendas.', 'evidence': [], 'kind': 'other'})
    assert 'fix' not in d and d['verb'] == 'approve', d


def test_the_kind_is_one_the_model_may_name():
    assert 'work_gap' in advisor.KINDS and 'work_gap' in advisor.SYSTEM
    assert advisor.GAPS <= set(advisor.KINDS)
