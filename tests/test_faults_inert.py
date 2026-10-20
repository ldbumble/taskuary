"""The dead-end walk's failures on purpose (taskuary/faults.py) never touch a real run: without TASKUARY_FAULTS, or with a home that
is not a scratch one, install() changes nothing - no boundary is patched and no switch is added."""
import os, tempfile
from pathlib import Path
from unittest import mock
from fastapi import FastAPI
from taskuary import faults, outbound, terminal


def routes(app): return {getattr(r, 'path', '') for r in app.routes}


def test_without_the_flag_nothing_is_installed():
    app, send = FastAPI(), outbound.reply_to_message
    with mock.patch.dict(os.environ, {faults.ENV: ''}):
        assert faults.install(app) is False
    assert '/api/test/fault' not in routes(app) and outbound.reply_to_message is send


def test_the_flag_alone_is_not_enough_outside_a_scratch_home():
    app, start = FastAPI(), terminal.start_on_task
    real = str(Path.home() / '.taskuary')
    with mock.patch.dict(os.environ, {faults.ENV: '1', 'TASKUARY_HOME': real}):
        assert faults.active() is False and faults.install(app) is False
    assert '/api/test/fault' not in routes(app) and terminal.start_on_task is start


def test_a_scratch_home_and_the_flag_install_the_switch():
    app = FastAPI()
    patched = ('reply_to_message', 'reconcile_sent', 'send_probe')
    keep = {n: getattr(outbound, n) for n in patched}
    from taskuary import advisor, agents, concierge, general, llm
    others = [(terminal, 'start_on_task'), (general, 'start_session'), (agents, 'coding_ready'), (llm, 'build_llm'), (advisor, 'build_llm'), (concierge, 'brain')]
    saved = [(m, n, getattr(m, n)) for m, n in others]
    try:
        with mock.patch.dict(os.environ, {faults.ENV: '1', 'TASKUARY_HOME': tempfile.mkdtemp()}):
            assert faults.install(app) is True
        assert '/api/test/fault' in routes(app)
        faults.NOW['fault'] = 'auth'
        try: outbound.reply_to_message(None, {}, 'x'); raise AssertionError('the auth fault did not fail the send')
        except Exception as e: assert outbound.fix_of(e)['label'] == 'Sign in again'
    finally:
        faults.NOW['fault'] = ''
        for n, f in keep.items(): setattr(outbound, n, f)
        for m, n, f in saved: setattr(m, n, f)


def test_the_matrix_world_and_its_scripted_advisor_are_inert_outside_a_walk():
    """faults.world seeds the advisor matrix's states and faults.scripted wires the demo's Advisor in - never in a real install."""
    from taskuary import advisor
    from taskuary.store import MemoryStore
    s, brain = MemoryStore(), advisor.build_llm
    with mock.patch.dict(os.environ, {faults.ENV: ''}):
        assert faults.world(s) == {} and faults.scripted() is False
    assert not s.list_tasks() and advisor.build_llm is brain


def test_the_matrix_world_holds_every_state_it_names():
    from taskuary import advisor, demo, terminal, workerstate
    from taskuary.store import MemoryStore
    s, sessions = MemoryStore(), dict(terminal.SESSIONS)
    try:
        with mock.patch.dict(os.environ, {faults.ENV: '1', 'TASKUARY_HOME': tempfile.mkdtemp()}):
            demo.seed(s); w = faults.world(s)
        st = lambda k: workerstate.status(s, w[k])['state']
        assert (st('coding-working'), st('coding-asking'), st('general-finished'), st('coding-failed'), st('general-stopped-saved')) == \
               ('working', 'input_needed', 'finished', 'failed', 'stopped')
        assert s.resumable_session(w['coding-stopped-saved'])
        assert advisor.sent_line(s, 'task', w['sent-quiet']).endswith('NOTHING HAS COME IN SINCE IT WENT.')
        assert 'WRITTEN TO THE OWNER SINCE' in advisor.sent_line(s, 'task', w['sent-then-new'])
        assert s.get_review(s.pending_review(w['send-failed'])['ReviewId'])['DeliveryState'] == 'failed'
    finally:
        from taskuary import assistant
        assistant._AGENDA.clear()                          # the world holds its meetings fresh for the walk: none for the next test
        for k in set(terminal.SESSIONS) - set(sessions): terminal.SESSIONS.pop(k).close()
