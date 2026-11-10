"""A RUN THAT ENDED ON A QUESTION TO THE OWNER IS STILL WAITING ON THE OWNER (the owner, 2026-11-03: "it's asking me question but the ai
closed the agent why?").

The shape: a coding agent finished its turn with "Ready to push <sha> to main, which deploys the portal to production. Go ahead?" - the turn
judge read the question out of that prose and recorded it. Before anyone answered, Taskuary restarted (an update), so the session was cut off
("disconnected", source shutdown) and nothing restarts by itself. The page then drew a finished run - Continue and Run another agent - with
nothing saying a question was waiting, and the finish check, reading the run as stopped, lit "Reply to the sender" over the agent's ask.

Now the ended run's open question is a fact every reader takes: wrapup.unanswered counts the model's read of the final text, workerstate says
what an ended run left asking, the Advisor's state is the agent asking (no finish check over it, and on a coding agent nothing lit but its
answer), and the task's detail carries the question for the page. Invented Northwind data only (CLAUDE.md)."""
import pytest
from taskuary import advisor, funnel, rulebook, terminal, workerstate as ws, wrapup
from taskuary.store import MemoryStore
from taskuary.testing import Factory

ASK = 'Ready to push a1b2c3d to main, which deploys the portal to production. Go ahead?'
SAID = "The packet download now builds one file per employee. It's committed locally.\n\n" + ASK


@pytest.fixture
def s(monkeypatch):
    s = MemoryStore(); s.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    funnel.invalidate(); yield s; funnel.invalidate()


def ev(s, tid, kind, text='', source='hook', rid=None, sid='c1'):
    s.add_worker_event({'TaskId': tid, 'Sid': sid, 'Kind': kind, 'RequestId': rid, 'Text': text, 'Source': source})


def cut_off_asking(s, kind='coding'):
    """A coding agent's turn ended on a question it asked, the CLI's idle notice after it, then a restart cut the session off."""
    t = Factory(s).task(title='Packet download fails for large teams', kind=kind, status='open')
    ev(s, t, 'working'); ev(s, t, 'turn_end', SAID)
    ev(s, t, 'input_needed', ASK, source='api', rid=ws.request_id_for(ASK))
    ev(s, t, 'input_needed', 'Claude is waiting for your input', rid=ws.request_id_for('Claude is waiting for your input'))
    ev(s, t, 'disconnected', 'the session ended', source='shutdown')
    s.tag_task(t, terminal.INTERRUPTED, True, 'shutdown')
    return t


def test_an_ended_run_says_the_question_it_was_left_asking(s):
    t = cut_off_asking(s)
    assert [r['text'] for r in ws.left_asking(s, t)] == [ASK], "the agent's own question - never the CLI's idle notice"


def test_a_question_the_owner_answered_before_the_cut_is_not_left(s):
    t = cut_off_asking(s)
    ev(s, t, 'working', 'yes, push it'); ev(s, t, 'disconnected', 'the session ended', source='shutdown')
    assert ws.left_asking(s, t) == []


def test_a_run_that_ended_on_a_report_leaves_nothing_asking(s):
    t = Factory(s).task(title='Packet download', kind='coding', status='open')
    ev(s, t, 'working'); ev(s, t, 'turn_end', 'Pushed and deployed - the download works for a team of 40.')
    ev(s, t, 'input_needed', 'Claude is waiting for your input', rid='idle1')
    ev(s, t, 'disconnected', 'the session ended', source='shutdown')
    assert ws.left_asking(s, t) == []


def test_a_cut_off_run_reads_as_the_agent_asking_and_its_row_fills_nothing(s):
    t = cut_off_asking(s)
    for item in ({'key': f'agent:{t}', 'kind': 'agent', 'lane': 'stopped', 'tid': t},
                 {'key': f'task:{t}', 'kind': 'task', 'lane': 'stopped', 'tid': t}):
        st, _ = rulebook.state(s, item, [{'verb': 'continue', 'label': 'Continue'}, {'verb': 'reply', 'label': 'Reply'}])
        assert st == 'agent_asking', item
        assert st in rulebook.QUIET, 'nothing is filled over an agent that waits on the owner: its own pane is the way on'


@pytest.mark.parametrize('verb', ['continue', 'reply', 'next', 'close'])
def test_on_a_coding_agent_left_asking_only_its_answer_may_light(s, verb):
    t = cut_off_asking(s)
    it = {'key': f'task:{t}', 'kind': 'task', 'lane': 'stopped', 'tid': t}
    vs = [{'verb': v, 'label': v} for v in ('continue', 'reply', 'close', 'answer_agent')]
    d = advisor.checked(s, it, vs, {'key': it['key'], 'state': 'agent_asking', 'verb': verb, 'line': 'Reply to Gail about the download', 'evidence': []})
    assert d['verb'] is None and d['line'] == '', d
    assert advisor.checked(s, it, vs, {'key': it['key'], 'state': 'agent_asking', 'verb': 'answer_agent', 'line': ''})['verb'] == 'answer_agent'


def test_a_general_agent_left_asking_is_still_the_models_call(s):
    t = cut_off_asking(s, kind='general')
    it = {'key': f'task:{t}', 'kind': 'task', 'lane': 'stopped', 'tid': t}
    vs = [{'verb': 'close', 'label': 'Mark done'}]
    assert advisor.checked(s, it, vs, {'key': it['key'], 'state': 'agent_asking', 'verb': 'close', 'line': ''})['verb'] == 'close'


def test_the_tasks_detail_carries_the_question_for_the_page(s, monkeypatch):
    from taskuary import server
    monkeypatch.setattr(server, 'store', s)
    t = cut_off_asking(s)
    d = server.task_detail(t)
    assert d['runEnded'] == 'disconnected' and d['leftAsking'] == [ASK]
    done = Factory(s).task(title='Packet download', kind='coding', status='open')
    ev(s, done, 'working', sid='c2'); ev(s, done, 'turn_end', 'Deployed.', sid='c2'); ev(s, done, 'disconnected', 'the session ended', source='shutdown', sid='c2')
    assert server.task_detail(done)['leftAsking'] == []


def test_a_run_that_ended_waiting_on_a_sign_in_offers_its_browser_back_not_an_answer(s, monkeypatch):
    """A restart cut off a general agent waiting on "Sign in to ... to continue": the page said Answer it over a run whose answer is a
    sign-in on a page that was gone (the owner, 2026-11-03: "agent is closed but it shows answer it??"). Its Continue opens the session and
    its browser again; the detail names the site instead of a question."""
    from taskuary import server
    monkeypatch.setattr(server, 'store', s)
    t = Factory(s).task(title='Pay the Payworth invoice', kind='general', status='open')
    ev(s, t, 'working'); ev(s, t, 'turn_end', 'The Payworth sign-in page is open.')
    ev(s, t, 'input_needed', 'Sign in to payworth.example to continue', source='api', rid='signin:payworth.example')
    ev(s, t, 'disconnected', 'the session ended', source='shutdown')
    d = server.task_detail(t)
    assert (d['leftAsking'], d['leftSignin']) == ([], 'payworth.example')
