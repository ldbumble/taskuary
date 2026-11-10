"""A GENERAL AGENT'S QUESTION ONCE ON THE CANVAS (the owner, 2026-10-21: "general agent question should only be once on the canvas. No
need for twice. save 'The agent asked' for whatsapp"). The desktop draws it in the Agent work pane's answer box only; the phone, which has
no box, still gets that line. Since 2026-11-10 the desk's pile carries no by-the-way alerts at all ("the agents don't tell the assistant
anything unless you ask assistant questions") - they are the phone's alone."""
import inspect
from unittest import mock

from taskuary import funnel, remote_assistant, server
from taskuary.store import MemoryStore

ASKING = {'key': 'agent:7', 'kind': 'agent', 'lane': 'blocked', 'tid': 7, 'ref': 'TQ-0007', 'title': 'Reconcile the export',
          'agent': 'researcher', 'asking': True, 'why': 'researcher asked you: Keep the inter-company rows?'}
PARKED = {**ASKING, 'key': 'agent:8', 'tid': 8, 'ref': 'TQ-0008', 'asking': False, 'why': 'researcher is waiting on you'}


def test_the_phone_keeps_the_agent_asked_line_and_the_desk_reads_none():
    with mock.patch.object(MemoryStore, 'funnel_states', return_value={}, create=True), \
         mock.patch.object(funnel, 'notices', return_value=[]):
        every = funnel.alerts(MemoryStore(), [ASKING, PARKED])
    assert any('asked you: Keep the inter-company rows?' in a['text'] for a in every), 'the phone still says the agent asked'
    src = inspect.getsource(server._pile_payload)
    assert "'alerts', 'events'" in src and 'funnel.alerts' not in src, 'the desk pile drops them'


def test_the_phone_reads_the_piles_own_alerts():
    assert "p.get('alerts')" in inspect.getsource(remote_assistant.push_alerts)
