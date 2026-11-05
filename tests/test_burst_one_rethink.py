"""A BURST IS ONE RE-THINK (the owner's stress run, 2026-11-05): five mails landed on the thread within seconds while the agent worked,
and each became its own queued turn - the agent re-thought four times, one line at a time, a summary each. Lines that arrive while
the session is busy wait together and go in as ONE turn once it is free. Paula Vance and Alex Doyle are invented."""
import threading, time
from unittest import mock

from taskuary import general, ingest
from taskuary.store import MemoryStore


class Ses:
    def __init__(self): self.busy, self.quick, self.alive, self.sent = True, False, True, []
    def send_prompt(self, text, *a, **k): self.sent.append(text)


def mail(words): return {'channel': 'email', 'from_name': 'Paula Vance', 'from_email': 'paula@northwind.example', 'body': words, 'subject': 'Re: badges'}


def test_lines_that_land_while_the_agent_works_go_in_as_one_turn():
    s = MemoryStore(); tid = s.create_task({'Title': 'Badge list', 'Kind': 'general', 'Status': 'open'}, 'router'); ses = Ses()
    with mock.patch.object(general, 'session_for', return_value=ses), mock.patch.object(ingest, 'PASS_GATHER', 0.3):
        ts = [threading.Thread(target=ingest._pass_general, args=(s, tid, mail(w))) for w in ('One more thing.', 'Ideally by today.', 'That is all.')]
        for t in ts: t.start(); time.sleep(0.1)
        time.sleep(0.5); ses.busy = False
        for t in ts: t.join(5)
    assert len(ses.sent) == 1, ses.sent
    assert all(w in ses.sent[0] for w in ('One more thing.', 'Ideally by today.', 'That is all.'))


def test_a_lone_line_on_an_idle_agent_still_goes_at_once():
    s = MemoryStore(); tid = s.create_task({'Title': 'Badge list', 'Kind': 'general', 'Status': 'open'}, 'router'); ses = Ses(); ses.busy = False
    with mock.patch.object(general, 'session_for', return_value=ses), mock.patch.object(ingest, 'PASS_GATHER', 0.2):
        ingest._pass_general(s, tid, mail('One more thing.'))
    assert len(ses.sent) == 1 and 'One more thing.' in ses.sent[0]


def test_a_line_that_finds_the_session_ended_starts_it_again_instead_of_being_dropped():
    """email-9 of the run: the agent closed its session at the end of its turn while a mail waited for it - "The assistant couldn't take
    Payworth Billing's new message: this assistant session has ended" - and the mail sat unread until a Continue."""
    s = MemoryStore(); tid = s.create_task({'Title': 'Invoice', 'Kind': 'general', 'Status': 'open'}, 'router'); ses = Ses(); ses.busy = False
    def ended(*a, **k): ses.alive = False; raise RuntimeError('this assistant session has ended - reload the page and ask again')
    ses.send_prompt = ended
    again = []
    with mock.patch.object(general, 'session_for', return_value=ses), mock.patch.object(ingest, 'PASS_GATHER', 0.1), \
         mock.patch.object(ingest, '_replan_general', lambda store, t, turn: again.append(turn)):
        ingest._pass_general(s, tid, mail('Following up: a late fee was added.'))
    assert len(again) == 1 and 'late fee' in again[0]
    assert not any("couldn't take" in c['Body'] for c in s.list_comments(tid))


def test_a_change_on_the_thread_is_said_plainly_first():
    """The owner, 2026-11-05: "if i respond myself or user in the channel that takes care of the task that should also trigger the chat to
    say i see you responded there. we are good or whatever they feel like is next steps"."""
    own = ingest.replan_turn(mail('Done - sent it over this morning.'), own=True)
    assert 'I see you answered' in own and 'took care of it' in own and 'nothing left' in own
    assert own.startswith("THE THREAD CHANGED: you already answered")
