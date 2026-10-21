"""A GENERAL AGENT'S QUESTION ONCE ON THE CANVAS (the owner, 2026-10-21: "general agent question should only be once on the canvas. No
need for twice. save 'The agent asked' for whatsapp"). The desktop draws it in the Agent work pane's answer box only, so its pile carries
no "<agent> asked you: ..." by-the-way line; the phone, which has no box, still gets that line."""
import inspect
from unittest import mock

from taskuary import funnel, remote_assistant
from taskuary.store import MemoryStore

ASKING = {'key': 'agent:7', 'kind': 'agent', 'lane': 'blocked', 'tid': 7, 'ref': 'TQ-0007', 'title': 'Reconcile the export',
          'agent': 'researcher', 'asking': True, 'why': 'researcher asked you: Keep the inter-company rows?'}
PARKED = {**ASKING, 'key': 'agent:8', 'tid': 8, 'ref': 'TQ-0008', 'asking': False, 'why': 'researcher is waiting on you'}


def test_the_phone_keeps_the_agent_asked_line_and_the_desk_does_not():
    with mock.patch.object(MemoryStore, 'funnel_states', return_value={}, create=True), \
         mock.patch.object(funnel, 'notices', return_value=[]):
        every = funnel.alerts(MemoryStore(), [ASKING, PARKED])
    assert any('asked you: Keep the inter-company rows?' in a['text'] for a in every), 'the phone still says the agent asked'
    desk = funnel.desk_alerts(every)
    assert not any('asked you' in a['text'] for a in desk), 'the canvas shows the question once - in its answer box'
    assert any(a['item'] == 'agent:8' for a in desk), 'an agent waiting without a question still interrupts'


def test_the_phone_reads_the_piles_own_alerts_not_the_desks():
    src = inspect.getsource(remote_assistant.push_alerts)
    assert "p.get('alerts')" in src and 'desk_alerts' not in src
