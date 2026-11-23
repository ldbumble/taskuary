"""A writing rule the owner tells the Assistant is what he SAID (memory.py, r10): kept in his words, and every draft reads it - the drafter
through the memory a task reads (responder.voice_line -> memory.for_task). How he writes is read from his sent mail (STYLE.md) and from
what he said; the model names no section for it."""
from unittest import mock

from taskuary import concierge, responder, memory
from taskuary.store import MemoryStore
from taskuary.testing import Factory

RULE = 'When writing to a woman, greet her as Mrs <surname>, never by her first name'


def test_a_style_rule_is_kept_as_what_he_said():
    s = MemoryStore()
    got = memory.remember(s, RULE, 'how to greet women')
    assert got['ok'] and RULE in (s.get_doc('learned') or '')
    assert RULE not in (s.get_doc('style') or ''), 'one home: his words are the memory\'s, STYLE.md is read from his sent mail'


def test_the_style_rule_reaches_the_drafter_prompt():
    s = MemoryStore()
    memory.remember(s, RULE, 'how to greet women')
    f = Factory(s)
    tid = f.task(title='Budget numbers', kind='reply')
    mid = f.message(tid, from_email='paula@northwind.example', from_name='Paula Vance', subject='Budget numbers', body='Are they final?')
    rid = f.review(tid, mid)
    seen = {}
    def llm(system, user, max_tokens=0): seen['system'] = system + user; return 'Dear Mrs Vance,\n\nYes, they are final.'
    with mock.patch('taskuary.calendar.context_for', return_value=''), mock.patch('taskuary.knowledge.block', return_value=''):
        responder.draft_for_review(s, tid, rid, llm=llm)
    assert RULE in seen['system']


def test_the_memory_is_silent():
    s = MemoryStore()
    tid = Factory(s).task(title='chat')
    with mock.patch.object(concierge, '_did', side_effect=lambda store, t, said, kind, *a: said):
        fact = concierge._memory(s, tid, 'memory.remember', {'note': 'Gail moved to Ops', 'subject': 'gail', 'about': 'Gail Moreno'})
    assert fact == concierge.GOT_IT, 'a fact for the memory is kept without a receipt (the owner, 2026-11-14: memory is silent)'
