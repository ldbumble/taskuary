"""A sign-in the agent only SAID in words is raised all the same (the owner, 2026-11-05: an agent wrote "the sign-in page is open" and ended its
turn; the browser shows only for an open sign-in ask, so nothing showed). Invented sites only."""
from unittest import mock
from taskuary import general, signin, llm
from taskuary.store import MemoryStore


class Page:
    def __init__(self, f): self.f = f
    def fields(self, want=''): return self.f
    def close(self): pass


def test_a_login_form_on_a_password_site_is_a_sign_in_page():
    with mock.patch('taskuary.browserview.state', return_value={'open': True, 'url': 'https://portal.vendor.example/login'}):
        assert signin.on_signin_page('s1', conn=Page({'top': True, 'password': True}))
        assert not signin.on_signin_page('s1', conn=Page({'top': True, 'password': False}))
    with mock.patch('taskuary.browserview.state', return_value={'open': False}):
        assert not signin.on_signin_page('s1', conn=Page({'top': True, 'password': True}))


def _turn(answer, on_login):
    s = MemoryStore()
    tid = s.create_task({'Title': 'Pull the portal statement', 'Kind': 'general', 'Status': 'open'}, 'owner')
    session = general.GeneralSession(s, tid); session.pick, session.provider = 'cli:claude', 'claude'
    with mock.patch.object(llm, 'build_llm', return_value=lambda *a, **k: answer), \
         mock.patch.object(signin, 'on_signin_page', return_value=on_login), mock.patch.object(signin, 'needs') as needs:
        session.send_prompt('Get the statement')
    return needs


def test_a_turn_that_ends_on_a_login_form_raises_the_sign_in():
    assert _turn('The sign-in page is open in the browser - sign in and I will go on.', True).called


def test_a_sign_in_he_set_aside_in_words_is_not_put_back_in_front_of_him():
    """Recorded on a real site (2026-11-15): a code was asked of him, he wrote "leave it for today", the agent left it - and its turn ending on
    the code page raised the sign-in again by itself. His words answered that ask; only the agent asking again puts it back."""
    from taskuary import workerstate as ws
    s = MemoryStore()
    tid = s.create_task({'Title': 'Pull the portal statement', 'Kind': 'general', 'Status': 'open'}, 'owner')
    session = general.GeneralSession(s, tid); session.pick, session.provider = 'cli:claude', 'claude'
    with mock.patch.object(llm, 'build_llm', return_value=lambda *a, **k: 'Left where it is.'), \
         mock.patch.object(signin, 'on_signin_page', return_value=True), mock.patch.object(signin, 'needs') as needs:
        ws.record(s, tid, session.sid, 'input_needed', request_id='signin:portal.example', text='portal.example asks for a code', source='api')
        session.send_prompt('Leave it for today.')
        assert not needs.called
        # ...and with no ask of that kind set aside, a turn ending on the form still raises it (the next time he asks for the statement)
        ws.record(s, tid, session.sid, 'answered', request_id='signin:portal.example', text='x', source='owner')
        session.send_prompt('Get the statement now.')
        assert needs.called


def test_a_turn_that_ends_elsewhere_raises_nothing():
    assert not _turn('Here is the statement summary.', False).called


def test_a_turn_that_ends_on_its_own_held_step_raises_no_sign_in_beside_it():
    """The HIPAA walk, 2026-11-22: the sign-up's held step stood as an Approve card, and the turn that ended on that form - its password box
    read as a sign-in page - raised "Sign in to 127.0.0.10 to continue" under it: two moves on one page. The held card is his one move there."""
    from taskuary import browsergate
    with mock.patch.object(browsergate, 'holds_any', return_value=True):
        assert not _turn('Once you approve that step, I will finish the sign-up.', True).called


def test_a_step_held_on_another_tab_still_counts():
    """The Codex walk, 2026-11-22: the held sign-up stood on one tab, the turn ended on a sign-in page the agent opened in another."""
    import json
    from taskuary import browsergate
    s = MemoryStore(); tid = s.create_task({'Title': 'Get the listings', 'Kind': 'general', 'Status': 'open'}, 'owner')
    s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'held',
                  'DraftText': json.dumps({'action': 'browser_act', 'sid': 's1', 'tab': 't1', 'site': 'vendor.example'})})
    assert browsergate.holds_any(s, tid, 's1') and not browsergate.holds_any(s, tid, 's2')
