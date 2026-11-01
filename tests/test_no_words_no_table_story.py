"""An answer with no words is never filled with the story of the task on the table (TQ-1251: asked to set up a mailbox, the chat
told the bank mail under it - "if it asks a different question don't respond about the task")."""
from contextlib import ExitStack
from unittest import mock
from taskuary import concierge, server
from tests import assistant_queries as aq

VIEW = {'area': 'connections', 'title': 'Any mailbox (IMAP)', 'fields': [{'key': 'host', 'label': 'IMAP server', 'value': ''}]}


def ask(answer, view=None):
    s = aq._world()
    with ExitStack() as st:
        aq._guards(st, None, None); st.enter_context(mock.patch.object(server, 'store', s))
        item = concierge.funnel.item_for_key(s, aq.TABLES['todo'])
        return item, concierge.say(s, 'Help me set up Any mailbox (IMAP)', key=aq.TABLES['todo'], llm=lambda *a, **k: answer, view=view)


def test_no_words_back_says_so_and_never_tells_the_table():
    item, out = ask('')
    assert out['say'] == concierge.NO_ANSWER and item['title'] not in out['say']
    assert [c['ask'] for c in out['chips']] == ['Help me set up Any mailbox (IMAP)']


def test_only_page_steps_back_is_the_steps_alone():
    item, out = ask('VIEW: {"op": "point", "target": "host"}', VIEW)
    assert out['say'] == '' and out.get('view_ops')
