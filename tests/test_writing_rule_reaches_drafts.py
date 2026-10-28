"""A writing rule told to the Assistant goes to the writing style, STYLE.md, and every draft reads it (the owner, 2026-10-28: "when I
ask the chat to write Mrs X to women from now on it should go to STYLE.md ... It should know where each memory goes"). The model names
where by what the fact IS - `section: style` on memory.remember - never a keyword rule; facts about people and work stay LEARNED.md's."""
from unittest import mock

from taskuary import concierge, memoryedit, responder, toolcatalog
from taskuary.store import MemoryStore
from taskuary.testing import Factory

RULE = 'When writing to a woman, greet her as Mrs <surname>, never by her first name'


def test_the_tool_offers_the_writing_style_as_a_destination():
    said = toolcatalog.PURPOSE['memory.remember']
    assert '| style:' in said and 'STYLE.md' in said and 'salutations' in said


def test_a_style_rule_lands_in_style_md_owner_notes_and_not_in_learned_md():
    s = MemoryStore()
    got = memoryedit.remember(s, RULE, section='style')
    assert got['doc'] == 'style'
    style = s.get_doc('style') or ''
    assert responder.OWNER_NOTES in style and RULE in style.split(responder.OWNER_NOTES, 1)[1]
    assert RULE not in (s.get_doc('learned') or '')


def test_the_style_rule_reaches_the_drafter_prompt():
    s = MemoryStore()
    memoryedit.remember(s, RULE, section='style')
    f = Factory(s)
    tid = f.task(title='Budget numbers', kind='reply')
    mid = f.message(tid, from_email='paula@northwind.example', from_name='Paula Vance', subject='Budget numbers', body='Are they final?')
    rid = f.review(tid, mid)
    seen = {}
    def llm(system, user, max_tokens=0): seen['system'] = system; return 'Dear Mrs Vance,\n\nYes, they are final.'
    with mock.patch('taskuary.calendar.context_for', return_value=''), mock.patch('taskuary.knowledge.block', return_value=''):
        responder.draft_for_review(s, tid, rid, llm=llm)
    assert RULE in seen['system']


def test_the_assistant_says_where_it_saved_it():
    s = MemoryStore()
    tid = Factory(s).task(title='chat')
    with mock.patch.object(concierge, '_did', side_effect=lambda store, t, said, kind: said):
        said = concierge._memory(s, tid, 'memory.remember', {'note': RULE, 'section': 'style'})
        fact = concierge._memory(s, tid, 'memory.remember', {'note': 'Gail moved to Ops', 'section': 'people', 'about': 'Gail Moreno'})
    assert said.startswith('Saved to your writing style:') and 'Mrs <surname>' in said
    assert fact.startswith('Remembered under Your people')
