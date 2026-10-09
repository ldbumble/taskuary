"""A chat's work ends with the same note a coding session's does (the owner, 2026-10-09: "general agent should also have the
summary like cli no? ... that's all people want to see, it's the core thing what the agent did"). Only Save and end session
filed it; a chat closed by the agent or put away left the Agent work step with nothing to show."""
from taskuary import general
from taskuary.store import MemoryStore
from taskuary.testing import Factory


def chat(s):
    tid = Factory(s).task(title='Vendor spend', kind='general')
    s.add_comment(tid, 'owner', general.USER_TYPE, 'How did vendor spend move?')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'August was $192,600, up 8% on July.')
    return tid


def notes(s, tid): return [c['Body'] for c in s.list_comments(tid) if str(c['Body']).startswith('CODER REPORT')]


def test_its_last_answer_is_filed_verbatim_once():
    s = MemoryStore(); tid = chat(s)
    general.report_note(s, tid); general.report_note(s, tid)
    assert notes(s, tid) == ['CODER REPORT\nAugust was $192,600, up 8% on July.']


def test_a_later_answer_is_filed_again_and_a_chat_with_none_files_nothing():
    s = MemoryStore(); tid = chat(s)
    general.report_note(s, tid)
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Supplies drove most of it.')
    general.report_note(s, tid)
    assert notes(s, tid)[-1] == 'CODER REPORT\nSupplies drove most of it.'
    empty = Factory(s).task(title='Nothing said yet', kind='general')
    assert general.report_note(s, empty) is None and notes(s, empty) == []


def test_closing_the_session_files_it():
    s = MemoryStore(); tid = chat(s)
    session = general.GeneralSession.__new__(general.GeneralSession)        # no provider: only what close() reads
    session.store, session.task_id, session.alive, session.sid, session.subs, session.pick, session.model = s, tid, True, 'x', [], '', ''
    session._emit = lambda *a: None
    session.close(learn=False)
    assert notes(s, tid) == ['CODER REPORT\nAugust was $192,600, up 8% on July.']
