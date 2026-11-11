"""SEND AND CLOSE CLOSES (the owner's ruling on the stress run, 2026-11-05): on a chat task the agent's session stays parked after every
turn, so the reply went and the task read "Sent. Kept open: The agent session on it is still open." - Send and close never closed once
an agent had run. The owner's own press sends, stops a parked session (saved as Mark done saves it) and closes; and so does one still
WORKING (the owner, 2026-11-11: "Why is agent still going .... there is nothing left to do") - it is his close, as Mark done is. Nothing
else closes a task on its own. Ray Colton and Alex Doyle are invented."""
from unittest import mock

from taskuary import concierge, terminal
from taskuary.store import MemoryStore


class Ses:
    def __init__(self, tid, busy): self.task_id, self.busy, self.alive, self.mode, self.sid, self.started = tid, busy, True, 'assistant', 's1', 1


def task(s): return s.create_task({'Title': 'Answer Ray about the go-live date', 'Kind': 'general', 'Status': 'open'}, 'router')


def closes(busy):
    "The gate over a live agent: closed, by the write-up job Mark done's press starts - the session kept, then the task closed."
    s = MemoryStore(); tid = task(s)
    with mock.patch.dict(terminal.SESSIONS, {'s1': Ses(tid, busy=busy)}, clear=True), mock.patch('taskuary.writeup.start') as job:
        out = concierge.close_after_send(s, tid, 'owner')
    assert out['closed'] and out['status'] == 'done' and not out['kept_open']
    job.assert_called_once_with(s, tid, close=True, actor='owner', no_reply=True, sid='s1')


def test_send_and_close_stops_a_parked_agent_and_closes(): closes(busy=False)
def test_send_and_close_stops_an_agent_at_work_and_closes(): closes(busy=True)
