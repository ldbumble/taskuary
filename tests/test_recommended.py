"""THE TASK'S OWN RECOMMENDED MOVE (the owner, 2026-11-09: "the agents while running should recommend actions, no assistant" /
"assistant/advisor should only be on rail"). The one filled button on a task's row is read off the agent's own latest turn and the task's
facts (rulebook.recommended) - the same for a general agent, an API-card agent, a coding agent and a task no agent touched - and no model
judges it: the Advisor reads its own idea rows and nothing else. The task page and the rail's item on the table carry the same field, and
the walk onto a row whose task has an agent asks the Assistant for no line about it. Invented Northwind people only (CLAUDE.md)."""
import json
from unittest import mock
import pytest
from fastapi.testclient import TestClient
from taskuary import advisor, concierge, funnel, general, rulebook, server, terminal
from taskuary.store import MemoryStore
from taskuary.testing import Factory


def no_model(*a, **kw): raise AssertionError('no model reads a task')


@pytest.fixture
def s(monkeypatch):
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: []); monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    monkeypatch.setattr(advisor, 'build_llm', no_model)
    st = MemoryStore(); st.set_setting('calendar_enabled', '0', 'test'); funnel.invalidate()
    yield st
    funnel.invalidate()


def agent_task(s, kind='general', summary=None, title='Post the safety numbers'):
    tid = s.create_task({'Title': title, 'Kind': kind, 'Status': 'in_progress'}, 't')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Wrote the post.')
    if summary is not None: s.add_comment(tid, 'assistant', general.SUMMARY_TYPE, json.dumps(summary))
    return tid


def rec(s, tid): return (rulebook.recommended_task(s, tid) or {}).get('verb')
def verbs(*vs): return [{'verb': v, 'label': v} for v in vs]
def item(tid, **kw): return {'key': f'task:{tid}', 'kind': 'todo', 'lane': 'mine', 'tid': tid, **kw}


# ── each fact, its move ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_agents_own_word_is_the_move_whatever_brain_wrote_it(s):
    """A general agent and an API-card agent both close their turn on a summary: nothing left fills Mark done, a turn that says neither
    fills nothing, and a step it left on the owner fills nothing."""
    done = agent_task(s, summary={'about': 'Erin asked', 'did': 'Erin answered herself', 'nothing_left': True})
    r = rulebook.recommended_task(s, done)
    assert (r['verb'], r['label'], r['why']) == ('close', 'Mark done', rulebook.NOTHING_LEFT)
    assert rec(s, agent_task(s, summary={'about': 'Erin asked', 'did': 'Looked it up', 'on_you': []})) is None
    assert rulebook.agent_word(s, agent_task(s)) is None, 'a run that wrote no summary said nothing'


def test_a_draft_that_waits_fills_its_send_whoever_wrote_it(s):
    """Triage's draft on a task no agent touched, and an agent's draft, are one fact: a reply waiting on the owner. Its Send is the move -
    over the agent's "nothing left" too - and never while its channel is not connected."""
    f = Factory(s)
    plain = f.task(title='Q3 accruals', kind='reply'); f.review(plain, f.message(plain), draft='Here are the Q3 accruals.')
    agent = agent_task(s, summary={'about': 'Gail asked', 'did': 'Drafted the answer', 'nothing_left': True}); f.review(agent, f.message(agent), draft='Friday.')
    with mock.patch.object(advisor, 'unconnected', return_value=False), mock.patch.object(advisor, 'pressable', return_value=''):
        assert rec(s, plain) == rec(s, agent) == 'send_close'
    with mock.patch.object(advisor, 'unconnected', return_value=True), mock.patch.object(advisor, 'pressable', return_value=''):
        assert rec(s, plain) is None and rec(s, agent) is None, 'its card says Connect: no Send is filled'


def test_an_agent_at_work_or_asking_fills_nothing(s):
    tid = agent_task(s, kind='coding', summary=None)
    for st in ('working', 'agent_asking', 'closed'):
        with mock.patch.object(rulebook, 'facts', return_value={'state': st, 'line': ''}):
            assert rulebook.recommended(s, item(tid), verbs('close', 'continue', 'stop_agent')) is None, st


def test_a_reply_nothing_has_written_fills_the_agents_start(s):
    """Nothing drafts a reply but the task's agent (the owner, 2026-11-10). Where none started by itself, its start is the one move."""
    tid = agent_task(s, kind='reply', summary=None)
    with mock.patch.object(rulebook, 'facts', return_value={'state': 'needs_agent', 'line': ''}):
        assert rulebook.recommended(s, item(tid), verbs('reply', 'regular_agent', 'close'))['verb'] == 'regular_agent'
        assert rulebook.recommended(s, item(tid), verbs('reply', 'continue', 'regular_agent'))['verb'] == 'continue', 'the one that worked it first'
        assert rulebook.recommended(s, item(tid), verbs('reply', 'close')) is None, 'no agent to start: nothing is filled'


def test_a_run_that_is_over_fills_mark_done_where_no_summary_was_written(s):
    """A coding agent's terminal writes no summary, and a task no agent touched has none: the facts say it is over."""
    tid = agent_task(s, kind='coding')
    for st in sorted(rulebook.OVER):
        with mock.patch.object(rulebook, 'facts', return_value={'state': st, 'line': 'Finished at 10:02; nothing since.'}):
            r = rulebook.recommended(s, item(tid), verbs('close', 'defer'))
            assert (r['verb'], r['why'], r['state']) == ('close', 'Finished at 10:02; nothing since.', st)
    # ...and where it is not over - stopped mid-work, work not pushed, an ask, a wait - nothing is filled
    for st in ('stopped', 'unpushed', 'asked', 'asked_late', 'waiting_late', 'own', 'untouched', 'fyi', 'report_ok'):
        with mock.patch.object(rulebook, 'facts', return_value={'state': st, 'line': ''}):
            assert rulebook.recommended(s, item(tid), verbs('close', 'continue', 'reply', 'review_changes')) is None, st


def test_a_failed_run_fills_its_own_way_past_it_and_never_the_send_that_failed(s):
    tid = agent_task(s, kind='coding')
    failed = {'state': 'failed_cause', 'line': 'Failed: the test database was not reachable'}
    with mock.patch.object(rulebook, 'facts', return_value=failed), mock.patch.object(advisor, 'pressable', return_value=''):
        assert rulebook.recommended(s, item(tid), verbs('continue', 'close'))['verb'] == 'continue', 'Try again leads its row'
        assert rulebook.recommended(s, item(tid), verbs('fix', 'send_close', 'close'))['verb'] == 'fix', 'the place that fixes it'
        assert rulebook.recommended(s, item(tid), verbs('new_task', 'send_close', 'close')) is None, 'what failed is not sent again as it stood'
        assert rulebook.recommended(s, item(tid), verbs('close', 'continue')) is None, 'Continue that does not lead the row is no fix'


def test_a_held_action_fills_its_approve(s):
    tid = agent_task(s, kind='coding')
    with mock.patch.object(rulebook, 'facts', return_value={'state': 'action_held', 'line': ''}), mock.patch.object(advisor, 'pressable', return_value=''):
        assert rulebook.recommended(s, item(tid), verbs('approve', 'stop_agent'))['verb'] == 'approve'


def test_only_a_button_the_owner_can_press_is_filled_and_an_unreadable_row_fills_nothing(s):
    tid = agent_task(s, summary={'about': 'x', 'did': 'y', 'nothing_left': True})
    with mock.patch.object(advisor, 'pressable', return_value='greyed'): assert rec(s, tid) is None
    assert rulebook.recommended(s, None) is None and rulebook.recommended(None, {'key': 'task:9', 'tid': 9}) is None, 'never raises'
    assert rulebook.recommended(s, {'key': 'idea:1', 'kind': 'idea'}) is None, "an idea is the Advisor's own row"


# ── nothing of the Advisor's reads a task ───────────────────────────────────────────────────────────────────────────────────────────
def test_no_event_on_a_task_or_a_message_reaches_the_advisors_model(s):
    tid = agent_task(s, summary={'about': 'x', 'did': 'y', 'nothing_left': True})
    for ev, kind in (('agent.stopped', 'task'), ('reply.arrived', 'task'), ('task.closed', 'task'), (advisor.SHOWN, 'message')):
        assert advisor.notice(s, ev, kind, tid, tier=2, wait=True, llm=no_model) is None
    assert not s._one('SELECT 1 x FROM advice'), 'nothing was judged, and nothing written'
    d = advisor.decide(s, f'task:{tid}')
    assert (d['verb'], d['label'], d['by'], d['line']) == ('close', 'Mark done', 'agent', ''), 'the old shape, for the surfaces that still ask here'
    assert not hasattr(advisor, 'finish_check') and not hasattr(advisor, 'fix_of') and not hasattr(advisor, 'CHECK_SYSTEM')


def test_the_assistants_turn_reads_the_tasks_own_move_not_an_advisors_pick(s):
    tid = agent_task(s, summary={'about': 'x', 'did': 'y', 'nothing_left': True})
    block = advisor.block(s, {'key': f'task:{tid}', 'tid': tid})
    assert "THE TASK'S RECOMMENDED MOVE" in block and 'Mark done' in block and 'ADVISOR' not in block.upper().replace("THE TASK'S", '')


# ── one field, both pages ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_task_page_and_the_rails_item_on_the_table_carry_the_same_field(s, monkeypatch):
    f = Factory(s); tid = f.task(title='Q3 accruals', kind='reply'); f.message(tid)      # a row the rail carries, and an agent answered on it
    s.add_comment(tid, 'assistant', general.SUMMARY_TYPE, json.dumps({'about': 'Gail asked', 'did': 'Gail has the file', 'nothing_left': True}))
    quiet = agent_task(s, summary={'about': 'x', 'did': 'y'}, title='Look up the pay date')
    funnel.invalidate(); monkeypatch.setattr(server, 'store', s)
    c = TestClient(server.app)
    assert c.get(f'/api/tasks/{tid}').json()['recommended']['verb'] == 'close'
    assert c.get(f'/api/tasks/{quiet}').json()['recommended'] is None, 'present and empty: the page fills nothing and asks nobody'
    key = advisor._item(s, 'task', tid)['key']
    cur = c.get('/api/funnel/pile', params={'current': key}).json()['current']
    assert cur['key'] == key and cur['recommended']['verb'] == 'close'
    assert all('recommended' not in i for i in funnel.pile(s)['items']), 'a copy carries it - never the cached card'


# ── the walk onto a row whose task has an agent ──────────────────────────────────────────────────────────────────────────────────────
def test_the_walk_asks_the_assistant_for_no_line_about_a_task_with_an_agent(s):
    tid = agent_task(s, summary={'about': 'x', 'did': 'y', 'nothing_left': True})
    it = advisor._item(s, 'task', tid)
    assert concierge.agent_row(s, it), 'an agent took a turn on it'
    asked = []
    out = concierge.present_turn(s, it, llm=lambda *a, **k: asked.append(a) or 'The agent finished the post.', record=True)
    assert not asked and out['say'] == concierge.brought_up(it) and out['options'] == [], 'the few words that name any row; no model'
    assert [c['verb'] for c in out['chips']] == [c['verb'] for c in concierge.chips_for(s, it)], "the row's own buttons, in their own order"
    assert out['item']['recommended']['verb'] == 'close'
    for card in ({'kind': 'agent', 'lane': 'blocked'}, {'kind': 'agentdone'}, {'kind': 'wrapup'}, {'kind': 'todo', 'lane': 'stopped'}, {'kind': 'todo', 'lane': 'working'}):
        assert concierge.agent_row(s, {'key': 'k', **card}), card


def test_a_row_with_no_agent_is_walked_as_before(s):
    f = Factory(s); tid = f.task(title='Badge access for the new AP clerk', kind='reply'); f.message(tid)
    it = advisor._item(s, 'task', tid)
    assert not concierge.agent_row(s, it)
    asked = []
    concierge.present_turn(s, it, llm=lambda *a, **k: asked.append(a) or 'Erin wants badge access.', record=True)
    assert asked, 'the walk words it as it did'
