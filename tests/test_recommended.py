"""THE TASK'S OWN RECOMMENDED MOVE (the owner, 2026-11-09: "the agents while running should recommend actions, no assistant" /
"assistant/advisor should only be on rail"). The one filled button on a task's row is read off the agent's own latest turn and the task's
facts (rulebook.recommended) - the same for a general agent, an API-card agent, a coding agent and a task no agent touched - and no model
judges it: the Advisor reads its own idea rows and nothing else. The task page and the rail's item on the table carry the same field, and
the walk onto a row whose task has an agent asks the Assistant for no line about it. Invented Northwind people only (CLAUDE.md)."""
import json
from datetime import datetime, timedelta
from unittest import mock
import pytest
from fastapi.testclient import TestClient
from taskuary import concierge, funnel, general, rulebook, server, terminal
from taskuary.store import MemoryStore
from taskuary.testing import Factory




@pytest.fixture
def s(monkeypatch):
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: []); monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
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
    with mock.patch.object(rulebook, 'unconnected', return_value=False):
        assert rec(s, plain) == rec(s, agent) == 'send_close'
    with mock.patch.object(rulebook, 'unconnected', return_value=True):
        assert rec(s, plain) is None and rec(s, agent) is None, 'its card says Connect: no Send is filled'


def test_an_agent_at_work_or_asking_fills_nothing(s):
    tid = agent_task(s, kind='coding', summary=None)
    for st in ('working', 'agent_asking', 'closed'):
        with mock.patch.object(rulebook, 'facts', return_value={'state': st, 'line': ''}):
            assert rulebook.recommended(s, item(tid), verbs('close', 'continue', 'stop_agent')) is None, st


def test_nothing_else_is_filled_the_agent_suggests_it(s):
    """The owner, 2026-11-15: "nothing for now. the agent should suggest what to do." Only a send waiting for his yes and the agent's own
    "nothing left" fill a button. A run that is over with no word of its agent's, a late wait, work unpushed, a stopped agent, an ask nobody
    took, a phish, a duplicate, a failure - each fills nothing, and says its one sentence where it has one."""
    tid = agent_task(s, kind='coding')
    every = verbs('close', 'chase', 'review_changes', 'continue', 'regular_agent', 'not_ours', 'remove', 'split', 'fix', 'new_task', 'send_close', 'defer')
    for st in ('agent_done', 'stopped_done', 'answered', 'done_list', 'watch_handled', 'waiting_late', 'waiting_overdue', 'goal_late', 'unpushed',
               'stopped', 'asked', 'needs_agent', 'fyi_danger', 'duplicate', 'failed', 'failed_cause', 'report_failed', 'own', 'fyi', 'report_ok'):
        with mock.patch.object(rulebook, 'facts', return_value={'state': st, 'line': 'Its fact.'}):
            assert rulebook.recommended(s, item(tid), every) is None, st
            assert rulebook.recommended(s, item(tid), every, unlit=True) == {'verb': None, 'label': '', 'why': 'Its fact.', 'state': st}, st
    # ...save an agent that writes no summary (a coding agent's terminal): its own finished word is its "nothing left" - not the owner's reply
    for line, want in (('Finished at 10:02; nothing since.', 'close'), ('Your reply went at 10:02; nothing since.', None)):
        with mock.patch.object(rulebook, 'facts', return_value={'state': 'agent_done', 'line': line}):
            assert (rulebook.recommended(s, item(tid), every) or {}).get('verb') == want, line
    for gone in ('OVER', 'MOVES', 'pressable', 'landing_asks', 'AGENT_VERBS'): assert not hasattr(rulebook, gone), gone
    assert rulebook.recommended(s, None) is None and rulebook.recommended(None, {'key': 'task:9', 'tid': 9}) is None, 'never raises'
    assert rulebook.recommended(s, {'key': 'idea:1', 'kind': 'idea'}) is None, "an Advisor idea's row fills nothing"


def late_wait(s, d=7):
    tid = s.create_task({'Title': 'Vendor W-9', 'Kind': 'general', 'Status': 'waiting'}, 'owner')
    s._exec("UPDATE task SET WaitingOn='ray.colton@northwind.example' WHERE TaskId=?", (tid,))
    Factory(s).message(task_id=tid, subject='W-9?', direction='out', sent_at=f'{datetime.now() - timedelta(days=d):%Y-%m-%d %H:%M:%S}')
    return tid, {'key': f'task:{tid}', 'kind': 'todo', 'lane': 'theirs', 'tid': tid}


def test_a_row_with_nothing_lit_says_why_in_its_states_one_sentence(s):
    """Plain buttons and no word stood over a late wait whose agent was woken, a first mail from a stranger, a landing card that asks
    (the owner, 2026-11-10): the line was dropped unless something failed or a draft was ready. Wherever nothing is lit it is said now."""
    tid, it = late_wait(s)
    s.audit('task', tid, 'check_back', 'late', 'agent', {'state': 'waiting_late'})
    with mock.patch.object(rulebook, '_item', lambda *a, **k: it):
        d = rulebook.decide(s, f'task:{tid}')
    assert d['verb'] is None and d['state'] == 'waiting_late' and d['line'].startswith('Ray Colton: ') and d['line'].endswith('no answer.')
    assert not hasattr(rulebook, 'UNTOUCHED_DAYS') and 'untouched' not in rulebook.RULES, 'a state with no line, no move and no wake is gone'


def test_a_held_action_fills_its_approve(s):
    tid = agent_task(s, kind='coding')
    with mock.patch.object(rulebook, 'facts', return_value={'state': 'action_held', 'line': ''}):
        assert rulebook.recommended(s, item(tid), verbs('approve', 'stop_agent'))['verb'] == 'approve'


# ── nothing of the Advisor's reads a task ───────────────────────────────────────────────────────────────────────────────────────────

def test_the_assistants_turn_reads_the_tasks_own_move_not_an_advisors_pick(s):
    tid = agent_task(s, summary={'about': 'x', 'did': 'y', 'nothing_left': True})
    block = rulebook.block(s, {'key': f'task:{tid}', 'tid': tid})
    assert "THE TASK'S RECOMMENDED MOVE" in block and 'Mark done' in block and 'ADVISOR' not in block.upper().replace("THE TASK'S", '')


# ── one field, both pages ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_task_page_and_the_rails_item_on_the_table_carry_the_same_field(s, monkeypatch):
    # ...from a colleague: a stranger's mail would hold Trust in front, and nothing is closed over his Trust still to press (taskstate.standing)
    s.set_setting('owner_email', 'alex@northwind.example', 't')
    f = Factory(s); tid = f.task(title='Q3 accruals', kind='reply'); f.message(tid, from_email='gail.moreno@northwind.example', from_name='Gail Moreno')
    s.add_comment(tid, 'assistant', general.SUMMARY_TYPE, json.dumps({'about': 'Gail asked', 'did': 'Gail has the file', 'nothing_left': True}))
    quiet = agent_task(s, summary={'about': 'x', 'did': 'y'}, title='Look up the pay date')
    funnel.invalidate(); monkeypatch.setattr(server, 'store', s)
    c = TestClient(server.app)
    assert c.get(f'/api/tasks/{tid}').json()['recommended']['verb'] == 'close'
    assert c.get(f'/api/tasks/{quiet}').json()['recommended'] is None, 'present and empty: the page fills nothing and asks nobody'
    key = rulebook._item(s, 'task', tid)['key']
    cur = c.get('/api/funnel/pile', params={'current': key}).json()['current']
    assert cur['key'] == key and cur['recommended']['verb'] == 'close'
    assert all('recommended' not in i for i in funnel.pile(s)['items']), 'a copy carries it - never the cached card'


# ── the walk onto a row whose task has an agent ──────────────────────────────────────────────────────────────────────────────────────
def test_the_walk_asks_the_assistant_for_no_line_about_a_task_with_an_agent(s):
    tid = agent_task(s, summary={'about': 'x', 'did': 'y', 'nothing_left': True})
    it = rulebook._item(s, 'task', tid)
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
    it = rulebook._item(s, 'task', tid)
    assert not concierge.agent_row(s, it)
    asked = []
    concierge.present_turn(s, it, llm=lambda *a, **k: asked.append(a) or 'Erin wants badge access.', record=True)
    assert asked, 'the walk words it as it did'


def test_a_row_with_nothing_lit_carries_the_line_the_phone_says(s):
    """A row with nothing lit says why on the desk too (the owner, 2026-11-10: "if it's consistent do it"): what the desk's row reads
    (the task's own read, the rail's item on the table) carries the very sentence rulebook.decide gives the phone, with no verb."""
    tid = agent_task(s, kind='coding')
    line = 'Stopped mid-work: the test database was not reachable.'
    with mock.patch.object(rulebook, 'facts', return_value={'state': 'stopped', 'line': line}), \
         mock.patch.object(rulebook, 'offered', return_value=verbs('close', 'reply')):
        phone = rulebook.decide(s, f'task:{tid}')
        assert (phone['verb'], phone['line']) == (None, line)
        assert rulebook.recommended(s, item(tid)) is None, 'the plain read still fills nothing'
        desk = rulebook.recommended(s, item(tid), unlit=True)
        assert (desk['verb'], desk['why'], desk['state']) == (None, line, 'stopped')
        assert rulebook.recommended_task(s, tid)['why'] == phone['line'], 'the task page reads the same words'
    with mock.patch.object(rulebook, 'facts', return_value={'state': 'stopped', 'line': ''}):
        assert rulebook.recommended(s, item(tid), verbs('close'), unlit=True) is None, 'no line, nothing to say'


def test_review_changes_stays_on_the_row_after_the_session_is_gone(s):
    """Work left to review keeps Review changes on its row with no session open (the owner, 2026-11-10: "yes, keep it"): the same fact that
    offers it (rulebook.changes_waiting); nothing fills it (the owner, 2026-11-15)."""
    tid = s.create_task({'Title': 'Fix the ledger export', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
    it = {'key': f'task:{tid}', 'kind': 'agentdone', 'lane': 'yours', 'tid': tid}     # its agent finished; no session stands
    assert not concierge._shows(s, it, 'review_changes'), 'nothing to review, nothing offered'
    s._exec("INSERT INTO boardnote (TaskId, Agent, Cwd, Kind, Body, CreatedAt) VALUES (?, 'codex', '/w', 'ready', 'Ready to push.', ?)",
            (tid, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    assert rulebook.changes_waiting(s, tid) and not s.resumable_session(tid)
    assert concierge._shows(s, it, 'review_changes'), 'offered with no session open'
    assert 'review_changes' in [v['verb'] for v in rulebook.offered(s, it)]
    assert (rulebook.recommended(s, it) or {}).get('verb') is None, 'offered, never lit: what to do next is the task agent to suggest'


def test_a_chat_room_shared_by_two_asks_makes_neither_the_others_duplicate(s):
    """The Codex walk, 2026-11-19: a colleague's question in a Teams chat joined his code fix, and her sign-up list in the same chat a minute
    later read "Same ask as TQ-0003 - fold it into that one". A chat's conversation id names its room, never one topic (routing.CHAT_CHANNELS);
    two mails on one email thread still are one conversation."""
    fix = s.create_task({'Title': 'Fix the rounding bug in northwind/ledger totals', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
    trials = s.create_task({'Title': 'Get trial accounts for the vendors on the list', 'Kind': 'general', 'Status': 'open'}, 'triage')
    for tid, body in ((fix, 'did the ledger sync finish last night?'), (trials, 'can you sign us up for the 13 vendor trials?')):
        s.add_message({'TaskId': tid, 'Channel': 'teams', 'ConversationId': 'teams:chat-erin', 'FromName': 'Erin Blake', 'BodyText': body, 'Status': 'routed'})
    assert rulebook.same_thread(s, item(trials)) is None
    mail = s.create_task({'Title': 'Invoice question', 'Kind': 'general', 'Status': 'open'}, 'triage')
    again = s.create_task({'Title': 'Invoice question again', 'Kind': 'general', 'Status': 'open'}, 'triage')
    for tid in (mail, again):
        s.add_message({'TaskId': tid, 'Channel': 'email', 'ConversationId': 'thread-77', 'FromEmail': 'gail@northwind.example', 'BodyText': 'the invoice', 'Status': 'routed'})
    assert rulebook.same_thread(s, item(again)) == mail
