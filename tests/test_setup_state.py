"""ONE setup state (2026-10-18). There were two: setup.py's checklist (who you are, an AI, a source; `setup_dismissed`) behind the walk
and /api/setup, and firstrun.py's canvas (AI, email, About your work; `first_run_dismissed`) behind /api/setup/first-run - and the page
re-derived the canvas's rail from `step` a third time. Now firstrun.state is the state, the checklist and /api/setup are read off it,
the rail comes over the wire, and one flag says setup is put away."""
from contextlib import ExitStack
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import firstrun, server, setup
from taskuary.store import MemoryStore


def _world(ready=True, inbound=('Work mail',), items=()):
    """The readers every step is built on, set by hand - the endpoints' own state is what is under test."""
    st = ExitStack()
    for p in (mock.patch('taskuary.setup._ai', return_value={'ready': ready, 'Name': 'Anthropic', 'Type': 'anthropic', 'pick': 'connector:1'}),
              mock.patch('taskuary.setup._inbound', return_value=list(inbound)),
              mock.patch('taskuary.setup._first_items', return_value=list(items)),
              mock.patch('taskuary.clis.detect', return_value=[])): st.enter_context(p)
    return st


@pytest.fixture
def s():
    s = MemoryStore()
    with mock.patch.object(server, 'store', s): yield s


def test_one_state_drives_both_endpoints_the_same(s):
    s.set_setting('triage_ai', 'connector:1', 't')
    c = TestClient(server.app)
    with _world():
        page, first = c.get('/api/setup').json(), c.get('/api/setup/first-run').json()
    # /api/setup is the first run's state with the walk's checklist on it: every field the canvas reads, the same value
    assert {k: page[k] for k in first} == first
    assert (first['step'], first['todo'], first['left']) == ('reading', 'about your work', 1)
    assert [r['key'] for r in first['rail']] == ['ai', 'mail', 'about', 'other', 'finish']
    # ...and the checklist's rows tick by the same rows the rail does
    rows = {r['key']: r['done'] for r in page['steps']}
    rail = {r['key']: r['done'] for r in first['rail']}
    assert (rows['ai'], rows['inbound']) == (rail['ai'], rail['mail']) == (True, True)


def test_the_checklist_ticks_the_ai_once_it_is_picked_and_the_email_once_the_ai_is(s):
    """Where the two disagreed, the canvas's rule (firstrun: "step 1 is a choice") won: a working brain nobody picked is a guess."""
    with _world():
        rows = {r['key']: r for r in setup.state(s)['steps']}
    assert not rows['ai']['done'] and rows['ai']['detail'] == 'running on Anthropic'
    assert not rows['inbound']['done'] and rows['inbound']['detail'] == 'already connected: Work mail'
    s.set_setting('triage_ai', 'connector:1', 't')
    with _world():
        rows = {r['key']: r for r in setup.state(s)['steps']}
    assert rows['ai']['done'] and rows['inbound']['done']
    assert rows['ai']['goto'] == {'tab': 'Connections', 'hash': 'connector=anthropic', 'label': 'Open the Anthropic card'}


def test_dismissing_on_either_road_dismisses_both(s):
    c = TestClient(server.app)
    both = lambda: (c.get('/api/setup').json()['dismissed'], c.get('/api/setup/first-run').json()['dismissed'])
    with _world():
        assert both() == (False, False)
        c.post('/api/setup/dismiss', json={'dismissed': True})
        assert both() == (True, True)
        c.post('/api/setup/dismiss', json={'dismissed': False})
        assert both() == (False, False)
        s.set_setting('triage_ai', 'connector:1', 't')
        with mock.patch.object(firstrun, 'first_digest'):
            assert c.post('/api/setup/first-run/finish').status_code == 200
        assert both() == (True, True)
    assert s.get_setting(setup.DISMISSED) == '1' and setup.DISMISSED == firstrun.DISMISSED


@pytest.mark.parametrize('old,new,put_away', [('1', None, True), (None, '1', True), ('1', '0', True), ('0', None, False), (None, None, False)])
def test_an_old_install_with_either_flag_reads_right(s, old, new, put_away):
    if old is not None: s.set_setting(firstrun.OLD_DISMISSED, old, 't')
    if new is not None: s.set_setting(firstrun.DISMISSED, new, 't')
    with _world():
        assert firstrun.state(s)['dismissed'] is put_away
        assert setup.page(s)['dismissed'] is put_away


def test_the_old_flag_is_folded_once_then_only_the_one_is_kept(s):
    s.set_setting(firstrun.OLD_DISMISSED, '1', 't')
    assert firstrun.dismissed(s)
    assert (s.get_setting(firstrun.DISMISSED), s.get_setting(firstrun.OLD_DISMISSED)) == ('1', '')
    # reopened afterwards, it stays open: the folded flag does not put it away again
    firstrun.set_dismissed(s, False)
    assert not firstrun.dismissed(s)
    # ...and the start-up settle does not overwrite what the old flag said
    s2 = MemoryStore(); s2.set_setting(firstrun.OLD_DISMISSED, '1', 't')
    with _world(ready=False, inbound=()): firstrun.settle_existing(s2)
    assert s2.get_setting(firstrun.DISMISSED) == '1'


# THE RAIL'S RULE, here once (it was setupSteps.js's): what is done, what can be opened, what a waiting row waits for
def _rows(**st): return {r['key']: r for r in firstrun.rail(st)['rail']}


def test_the_rail_says_what_is_done_and_what_waits():
    ai = _rows(step='ai')
    assert not ai['ai']['done'] and ai['ai']['open']
    assert not ai['mail']['open'] and ai['mail']['sub'] == 'waits - pick an AI that works first'
    assert not ai['about']['open'] and ai['about']['sub'] == 'waits - connect your email first'
    assert ai['other']['open'], 'the optional ones never wait'
    reading = _rows(step='reading', about_done=False, brain={'name': 'Claude'}, empty=True)
    assert reading['ai']['sub'] == 'Claude' and reading['mail']['sub'] == 'connected - nothing new yet' and reading['about']['open']
    assert _rows(step='email', dismissed=True)['finish']['done'] is False, 'put away is not finished'
    assert _rows(step='done', about_done=True, dismissed=True)['finish']['done'] is True
    assert _rows(step='reading', about_done=False)['finish']['sub'] == 'after AI, email and About your work'
    assert _rows(step='reading', about_done=True)['finish']['sub'].startswith('ready')
    assert (_rows(more_connected=0, step='done')['other']['done'], _rows(more_connected=3, step='done')['other']['sub']) == (False, '3 connected')


def test_the_rail_says_where_setup_opens_and_what_is_left():
    f = lambda **st: (firstrun.rail(st)['frontier'], firstrun.rail(st)['left'], firstrun.rail(st)['ready'])
    assert f(step='ai') == ('ai', 3, False)
    assert f(step='email') == ('mail', 2, False)
    assert f(step='reading', about_done=False) == ('about', 1, False)
    assert f(step='done', about_done=True) == ('other', 0, True)
