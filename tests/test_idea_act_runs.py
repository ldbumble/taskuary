"""An Advisor idea's own words run (the button stress, 2026-11-02): Put it on my list and Not ours on an idea answered "✗ Not done - local
variable 'assistant' referenced before assignment" - the slipped card's branch of server._run_kind imported `assistant` inside the function,
which made the name local to all of it, so the idea.act branch above it never reached the module. Invented people only."""
from datetime import datetime, timedelta
from unittest import mock

from taskuary import operations, server
from tests.test_chat_proposals import store


def _idea(s):
    at = (datetime.now() - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
    return s.upsert_idea({'key': 'idea:weekly-ageing', 'kind': 'idea', 'sig': 'x', 'text': 'The AP ageing is pulled by hand every Monday.', 'action': {}}, at)


def test_not_ours_on_an_idea_puts_it_down():
    s = store(); i = _idea(s)
    op = operations.propose(s, 'idea.act', i['IdeaId'], {'verb': 'dismiss'})
    with mock.patch.object(server, 'store', s):
        server._run_kind(operations.get(s, op['id']), None)
    assert s.get_idea(i['IdeaId'])['Status'] == 'dismissed'
