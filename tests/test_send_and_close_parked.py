"""SEND AND CLOSE CLOSES (the owner's ruling on the stress run, 2026-11-05): on a chat task the agent's session stays parked after every
turn, so the reply went and the task read "Sent. Kept open: The agent session on it is still open." - Send and close never closed once
an agent had run. The owner's own press sends, stops a parked session (saved as Mark done saves it) and closes; an agent still WORKING
keeps it open, and nothing else closes a task on its own. Ray Colton and Alex Doyle are invented."""
from unittest import mock

from taskuary import concierge, terminal
from taskuary.store import MemoryStore


class Ses:
    def __init__(self, tid, busy): self.task_id, self.busy, self.alive, self.mode, self.sid = tid, busy, True, 'assistant', 's1'


def task(s): return s.create_task({'Title': 'Answer Ray about the go-live date', 'Kind': 'general', 'Status': 'open'}, 'router')


def test_send_and_close_stops_a_parked_agent_and_closes():
    s = MemoryStore(); tid = task(s); saved = []
    with mock.patch.dict(terminal.SESSIONS, {'s1': Ses(tid, busy=False)}, clear=True), \
         mock.patch.object(concierge, 'save_live', lambda store, t, actor='owner': saved.append(t) or True):
        out = concierge.close_after_send(s, tid, 'owner')
    assert out['closed'] and s.get_task(tid)['Status'] == 'done' and saved == [tid]


def test_an_agent_still_working_keeps_it_open():
    s = MemoryStore(); tid = task(s)
    with mock.patch.dict(terminal.SESSIONS, {'s1': Ses(tid, busy=True)}, clear=True):
        out = concierge.close_after_send(s, tid, 'owner')
    assert not out['closed'] and s.get_task(tid)['Status'] != 'done' and out['kept_open']
