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


def test_a_turn_that_ends_elsewhere_raises_nothing():
    assert not _turn('Here is the statement summary.', False).called
