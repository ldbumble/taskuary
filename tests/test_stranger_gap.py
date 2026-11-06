"""THE STRANGER GAP (2026-11-06): a task that turned a stranger's AFTER a full session started on it. The waiting room held its
notes, but every other road into the session - a relayed answer, the owner's answer to a question, the phone's tell_agent, a
bound chat's line, a sign-in's "continue" - still went straight in. Each road now asks at delivery time (terminal.stranger_now):
nothing goes in, the task says so once, and the caller refuses with that line. A session in the stranger's mode ('auto') and a
general chat are untouched. Everything faked: no pty, no CLI."""
import pytest
from types import SimpleNamespace
from unittest import mock

from taskuary import agentchannels as ac, browsergate, devphone, ingest, origin, signin, terminal as term, waitroom, workerstate as ws
from taskuary.store import MemoryStore, task_ref
from taskuary.testing import Factory

NOW = term.STRANGER_NOW


def pane(tid, mode='full', **kw):
    t = SimpleNamespace(sid='run1', mode=mode, alive=True, task_id=tid, cwd='', agent='coding', label='coding', argv=['claude'], cli='claude',
                        ext_id='', draft='', n=0, written=[], tail=lambda n=3: ['Done.'], status_tail=lambda n=6: ['Done.'], waiting=lambda: True, **kw)
    t.write = t.written.append
    return t


@pytest.fixture
def w():
    s = MemoryStore(); tid = Factory(s).task(title='Fix the export', kind='coding')
    with mock.patch.dict(term.SESSIONS, {}, clear=True), mock.patch.object(origin, 'of_task', return_value=('stranger', 'a new sender')), \
         mock.patch.object(term, 'type_into') as typed, mock.patch.object(term, 'tell') as told, mock.patch.object(term, 'answer_form') as form:
        yield SimpleNamespace(s=s, tid=tid, typed=typed, told=told, form=form, lines=lambda: sum(c['Body'] == NOW for c in s.list_comments(tid)))

def live(w, **kw):
    t = pane(w.tid, **kw); term.SESSIONS[t.sid] = t; return t

def nothing_went_in(w):
    w.typed.assert_not_called(); w.told.assert_not_called(); w.form.assert_not_called()


# ── the check itself ─────────────────────────────────────────────────────────────────────────────────────────────
def test_the_check_says_it_once_and_spares_auto_general_and_trusted(w):
    t = live(w)
    assert term.stranger_now(w.s, w.tid) == NOW and term.stranger_now(w.s, w.tid) == NOW and w.lines() == 1
    t.mode = 'auto'; assert term.stranger_now(w.s, w.tid) == ''
    t.mode = 'full'; t.send_prompt = lambda *a, **k: None; assert term.stranger_now(w.s, w.tid) == ''      # a general chat's floor is its own
    del t.send_prompt
    with mock.patch.object(origin, 'of_task', return_value=('trusted', 'you know them')): assert term.stranger_now(w.s, w.tid) == ''
    with mock.patch.object(origin, 'of_task', side_effect=RuntimeError('db')): assert term.stranger_now(w.s, w.tid) == NOW   # unknown is closed


# ── each road ────────────────────────────────────────────────────────────────────────────────────────────────────
MSG = {'FromName': 'Erin Blake', 'Channel': 'email', 'BodyText': 'Use the March numbers.'}

def test_a_relayed_answer_is_refused(w):
    live(w)
    with pytest.raises(origin.Refusal, match='not someone you trust'): term.say_to_task(w.s, w.tid, MSG)
    nothing_went_in(w); assert w.lines() == 1 and w.s.waiting_notes(w.tid) == []

def test_a_relayed_answer_reaches_a_session_in_the_strangers_mode(w):
    live(w, mode='auto')
    with mock.patch.object(waitroom, 'state', return_value=('parked', None)): assert term.say_to_task(w.s, w.tid, MSG)
    w.told.assert_called_once()

def test_an_acp_session_is_refused_the_same(w):
    t = live(w); t.say = mock.Mock()
    with mock.patch.object(term, 'is_acp', return_value=True), pytest.raises(origin.Refusal): term.say_to_task(w.s, w.tid, MSG)
    t.say.assert_not_called()

def test_new_work_joined_by_triage_is_held_not_called_a_dead_session(w):
    live(w)
    assert ingest._said_coding(w.s, w.tid, MSG) is True
    ingest._pass_coding(w.s, w.tid, MSG)
    bodies = [c['Body'] for c in w.s.list_comments(w.tid)]
    assert not any('session ended' in b for b in bodies) and w.lines() == 1
    nothing_went_in(w)

def test_answer_to_agent_auto_holds_quietly(w):
    live(w)
    ingest._hand_to_agent(w.s, {'answer_to_agent': 'auto'}, w.tid, MSG, 'router')
    nothing_went_in(w)

def test_the_owners_answer_to_a_question_is_refused(w):
    t = live(w)
    with mock.patch.object(ws, 'events', return_value=[]):
        out = ws.answer(w.s, w.tid, 'q1', 'main')
        assert (out['delivered'], out['state'], out['why']) == (False, 'held_stranger', NOW)
        out = ws.answer_group(w.s, w.tid, {'q1': 'main', 'q2': 'red'})
        assert out['state'] == 'held_stranger'
    nothing_went_in(w); assert t.written == [] and w.lines() == 1

def test_a_hooks_held_ask_is_not_let_go(w):
    live(w)
    ev = mock.Mock()
    with mock.patch.dict(ws.HELD, {'g1': {'tid': w.tid, 'sid': 'run1', 'rids': ['g1:q1'], 'answers': {}, 'event': ev}}), \
         mock.patch.object(ws, 'group_of', return_value='g1'), mock.patch.object(ws, 'events', return_value=[]):
        assert ws.answer(w.s, w.tid, 'g1:q1', 'main')['state'] == 'held_stranger'
    ev.set.assert_not_called()

def test_the_assistants_and_the_phones_answer_open_is_refused(w):
    live(w)
    with mock.patch.object(ws, 'asking_of', return_value={'request_id': 'q1', 'kind': 'input_needed'}), \
         mock.patch.object(ws, 'question_group', return_value=[{'request_id': 'q1'}]):
        assert ws.answer_open(w.s, w.tid, 'main')['state'] == 'held_stranger'
    nothing_went_in(w)

def test_the_phones_tell_agent_is_refused_and_says_why(w):
    live(w)
    out = devphone.tell(w.s, {'task': task_ref(w.tid), 'text': 'push it'})
    assert out.startswith('Nothing was sent') and NOW in out
    assert w.s.waiting_notes(w.tid) == [] and not any(c['Body'] == 'push it' for c in w.s.list_comments(w.tid))
    nothing_went_in(w)

def test_a_bound_chats_line_is_refused_and_says_why(w):
    live(w)
    said = []
    with mock.patch.object(ac, 'in_repo', return_value=(True, '')), mock.patch.object(ac, 'say', side_effect=lambda s, b, text, tid=None: said.append(text)):
        ac._tell(w.s, {'ChannelId': 1, 'Kind': 'telegram', 'TaskId': None}, w.tid, 'ship it', None)
    assert said and NOW in said[0] and w.s.waiting_notes(w.tid) == []
    nothing_went_in(w)

def test_the_waiting_room_still_holds_its_notes(w):
    live(w)
    out = waitroom.add(w.s, w.tid, 'also handle the null case')
    assert out['state'] == 'held_stranger' and len(w.s.waiting_notes(w.tid)) == 1
    nothing_went_in(w)

def test_a_gates_word_and_a_sign_ins_continue_are_not_typed(w):
    live(w)
    browsergate._tell(w.s, w.tid, 'The owner approved it.')
    assert signin._continue(w.s, w.tid, 'signin:toll.example', 'toll.example', 'owner') is False
    nothing_went_in(w); assert w.lines() == 1
